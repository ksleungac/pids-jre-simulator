"""Auto-input driver — same-process integration.

Reads the JR EAST Train Sim HUD via dxcam in a background thread, runs OCR + a
simple state machine, and queues PA-fire requests onto the simulator's main
thread via the `pending_next_pa` flag. The simulator's existing input loop
checks that flag alongside `keyboard.is_pressed("page down")`, so the same
`_next_pa()` call path runs for auto-fire and manual fire.

Manual-press precedence is implicit: the auto-driver inspects `sim.state.curr_stop`
and `sim.state.cnt_pa` directly. If the user manually pressed PageDown ahead of
an auto-fire (advancing the simulator state), the auto-fire detects the mismatch
and skips. No synthetic keystrokes, no keyboard hooks, no parallel route loading.

Architecture pointer: AUTO_INPUT.md "Architecture" section.

Usage (from `main.py`):
    driver = AutoDriver(sim, lead_m=900, interval_s=5)
    driver.start()
    sim.run()  # blocks main thread
    driver.stop()
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TextIO

import dxcam
import numpy as np
import pygame

from hud_layout import BADGE_BBOX, DISTANCE_VALUE_BBOX, HUD_BBOX, SPEED_LIMIT_VALUE_BBOX, SPEED_VALUE_BBOX
from ocr import (
    build_templates,
    classify_badge_state,
    load_badge_anchors,
    read_distance,
    read_speed,
    read_speed_limit,
    read_stopping_offset,
)

if TYPE_CHECKING:
    from app import PASimulator


SAMPLE_INTERVAL_S = 5
SPEED_DEPARTURE_KMH = 30
DEFAULT_LEAD_M = 900


class Layer3State:
    """Canonical names for AutoDriver's inferred view of the IRL game state.

    See AUTO_INPUT.md § "Layer 3 — AutoDriver's inferred game state" for the
    full inference truth table. Values are bare strings so they round-trip
    cleanly through the status dict and JSONL drive log.
    """

    STOPPING_FRESH = "STOPPING_FRESH"
    STOPPING_AFTER_ARR = "STOPPING_AFTER_ARR"
    APPROACHING_BEFORE_DEP = "APPROACHING_BEFORE_DEP"
    APPROACHING_AFTER_DEP = "APPROACHING_AFTER_DEP"
    MOVING_AFTER_ARR = "MOVING_AFTER_ARR"
    UNKNOWN = "UNKNOWN"


# ─────────────────────────── drive recorder (blackbox) ────────────────────────
# Per-drive JSONL log written by AutoDriver. Each file is one drive session.
# Three record types (`_type` field discriminates):
#
#   _type=meta    — line 0, written once at session start. Route metadata + a
#                   richer per-stop list (stops_here flag distinguishes PASSING
#                   stations; english/furigana included for self-containment;
#                   scheduled_time is the route.json "time" field passed through
#                   verbatim — null for passing stations).
#   _type=event   — emitted whenever the OCR badge transitions: arrival,
#                   departure, passing_start, passing_end. Carries `curr_stop`
#                   at the moment of transition. Plot tools read these directly
#                   to place stop markers — no need to derive from sample stream.
#   _type=sample  — one per OCR cycle (~5s). All OCR fields + sim state.
#
# Local-only (gitignored). Crash-safe: each line flushed immediately. Plot
# generator (separate script — TODO) reads all three record types.
from app_paths import project_root

RECORDINGS_DIR = project_root() / "_recordings"


def _build_stops_meta(sim) -> list[dict]:
    """Per-stop dicts for the meta line. Self-contained — plot tool doesn't need
    to re-load route.json. PASSING stations included in geographic order with
    stops_here=False so the plot can mark them on the timeline.

    `stops_here` discriminator: per project convention (DATA_FORMAT.md), passing
    stations have NO `time` field while stopping stations always have one (even
    `time: 0` for the start station). NOT `bool(pa)` — terminus / starting
    stations may have empty `pa` but the train still stops there.
    """
    out = []
    for s in sim.stops:
        out.append(
            {
                "name": s.get("name", ""),
                "english": s.get("english", ""),
                "furigana": s.get("furigana", ""),
                "stops_here": s.get("time") is not None,
                "scheduled_time": s.get("time"),
                "sta_code": s.get("sta_code"),
            }
        )
    return out


def _open_drive_log(sim) -> tuple[Optional[TextIO], Optional[Path]]:
    """Open a fresh JSONL log for this drive session and write the meta header.

    Returns (file_handle, path) or (None, None) if anything goes wrong.
    Caller is responsible for closing the handle on shutdown.
    """
    try:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        work_path = Path(sim.work_dir)
        diagram = work_path.name or "unknown"
        line = work_path.parent.name or "unknown"
        ts_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RECORDINGS_DIR / f"drive_{line}_{diagram}_{ts_str}.jsonl"
        f = open(path, "w", encoding="utf-8")
        meta = {
            "_type": "meta",
            "start_ts": time.time(),
            "line": line,
            "diagram": diagram,
            "route": sim.route_data.get("route", ""),
            "dest": sim.route_data.get("dest", ""),
            "stops": _build_stops_meta(sim),
        }
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        f.flush()
        return f, path
    except Exception as e:
        print(f"[AutoDriver] Could not open drive log: {e}")
        return None, None


def _write_sample(f: TextIO, sample: dict) -> None:
    """Write one sample line + flush. Swallow errors so logging never crashes the capture loop."""
    try:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        f.flush()
    except Exception as e:
        print(f"[AutoDriver] Drive-log write failed: {e}")


def _write_event(f: TextIO, kind: str, curr_stop: int, ts: float) -> None:
    """Write a transition event line. `kind` ∈ {arrival, departure, passing_start, passing_end}."""
    try:
        f.write(
            json.dumps(
                {
                    "_type": "event",
                    "ts": ts,
                    "kind": kind,
                    "curr_stop": curr_stop,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        f.flush()
    except Exception as e:
        print(f"[AutoDriver] Drive-log event write failed: {e}")


def _badge_transition_kind(prev: Optional[str], curr: Optional[str]) -> Optional[str]:
    """Map a badge state change to an event kind. Returns None if no event applies."""
    if prev is None or curr is None or prev == curr:
        return None
    if prev == "STOPPED" and curr in ("MOVING", "PASSING"):
        return "departure"
    if prev in ("MOVING", "PASSING") and curr == "STOPPED":
        return "arrival"
    if prev == "MOVING" and curr == "PASSING":
        return "passing_start"
    if prev == "PASSING" and curr == "MOVING":
        return "passing_end"
    return None


# ─────────────────────────── debug panel rendering ────────────────────────────
# Panel logic is fully self-contained in this module — no imports from displays/,
# no dependency on LCD constants. The caller (PASimulator) provides a sub-surface
# at the size it wants; the panel auto-fits to the surface's width.

# Confidence color thresholds for OCR readings. Score is "fraction of pixels matching
# template" (1.0 = perfect, 0.5 = random for binary glyphs).
_CONF_GREEN = 0.90
_CONF_YELLOW = 0.75
# Badge classifier returns "diff" (lower = better); these are the inverse cutoffs.
_BADGE_GREEN = 5.0
_BADGE_YELLOW = 15.0

# Panel-specific colors (intentionally NOT the LCD's DARK_BG — visually distinct so
# the panel reads as a separate subsystem, not part of the LCD).
_PANEL_BG = (18, 22, 28)
_TEXT_WHITE = (220, 220, 220)
_TEXT_GRAY = (140, 140, 140)
_COLOR_GREEN = (110, 220, 110)
_COLOR_YELLOW = (230, 220, 90)
_COLOR_ORANGE = (240, 140, 60)

# Cached font (Latin + CJK support so station names in the state line render correctly).
_panel_font: Optional[pygame.font.Font] = None


def _get_panel_font() -> pygame.font.Font:
    global _panel_font
    if _panel_font is None:
        _panel_font = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 14)
    return _panel_font


def _conf_color(score: Optional[float]) -> tuple[int, int, int]:
    """OCR-score → RGB. Green for high, yellow for medium, orange for low, gray for None."""
    if score is None:
        return _TEXT_GRAY
    if score >= _CONF_GREEN:
        return _COLOR_GREEN
    if score >= _CONF_YELLOW:
        return _COLOR_YELLOW
    return _COLOR_ORANGE


def _badge_color(diff: Optional[float]) -> tuple[int, int, int]:
    """Badge-diff → RGB (lower diff = better match)."""
    if diff is None:
        return _TEXT_GRAY
    if diff <= _BADGE_GREEN:
        return _COLOR_GREEN
    if diff <= _BADGE_YELLOW:
        return _COLOR_YELLOW
    return _COLOR_ORANGE


def _blit_text(surf: pygame.Surface, font: pygame.font.Font, text: str, pos: tuple[int, int], color: tuple[int, int, int]) -> int:
    """Render `text` at `pos`; return the x-coordinate after the rendered glyphs.
    Lets callers chain: x = _blit_text(...) + gap."""
    rendered = font.render(text, True, color)
    surf.blit(rendered, pos)
    return pos[0] + rendered.get_width()


# ── Click-through-state for the in-panel buttons. Recomputed each draw call,
# read by `handle_panel_click()` when the simulator forwards a MOUSEBUTTONDOWN.
_report_button_rect: Optional[pygame.Rect] = None


def _draw_report_button(surface: pygame.Surface, font: pygame.font.Font) -> None:
    """Top-right pill-style button. Click triggers HTML drive-report rendering."""
    global _report_button_rect
    label = "Report ↓"
    text = font.render(label, True, _TEXT_WHITE)
    pad_x, pad_y = 12, 4
    btn_w = text.get_width() + 2 * pad_x
    btn_h = text.get_height() + 2 * pad_y
    btn_x = surface.get_width() - btn_w - 8
    btn_y = 4
    btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
    pygame.draw.rect(surface, (52, 116, 145), btn_rect, border_radius=btn_h // 2)
    surface.blit(text, (btn_x + pad_x, btn_y + pad_y))
    _report_button_rect = btn_rect


def _render_report_async(log_path: Path) -> None:
    """Background-thread report generation so the simulator UI doesn't freeze.

    `auto_input.py` and `plot_drive.py` both live at the project root, so
    the import resolves via the standard sys.path that the launching
    `main.py` set up — no per-call sys.path.insert needed (and previously
    accumulated duplicate entries on every click).
    """
    try:
        from plot_drive import render_html_report, load_jsonl

        out_path = project_root() / f"{log_path.stem}.html"
        meta, events, samples = load_jsonl(log_path)
        render_html_report(meta, events, samples, 5, out_path)
        print(f"[Drive recorder] Report saved -> {out_path}")
    except Exception as e:
        print(f"[Drive recorder] Report generation failed: {e}")


def handle_panel_click(sim, pos: tuple[int, int]) -> bool:
    """Dispatch a MOUSEBUTTONDOWN that landed inside the debug panel.

    Returns True if a button absorbed the click (caller can stop propagating).
    Today we only have one button (the Report download); easy to extend.
    """
    if _report_button_rect is None or not _report_button_rect.collidepoint(pos):
        return False
    log_path = getattr(sim, "drive_log_path", None)
    if log_path is None:
        print("[Drive recorder] No drive log open yet — wait for the AutoDriver to capture some samples.")
        return True
    print(f"[Drive recorder] Generating report from {log_path.name} ...")
    threading.Thread(target=_render_report_async, args=(log_path,), daemon=True).start()
    return True


def draw_debug_panel(surface: pygame.Surface, status: dict, sim_state, stops: list) -> None:
    """Render the auto-input debug panel onto `surface`.

    Public entry point for the simulator. Pure render — no pygame.flip(), no state
    mutation. The simulator decides where the surface lives (size / position); this
    function fills it.

    Args:
        surface: target sub-surface (any width — panel adapts to it)
        status: latest OCR + detector state dict (written by AutoDriver)
        sim_state: simulator's AppState (for live curr_stop, cnt_pa)
        stops: simulator's stops list (for station-name lookup)
    """
    font = _get_panel_font()
    surface.fill(_PANEL_BG)

    # Always-on Report button (top-right). Drawn even before first capture
    # so the user can find it; clicking before any samples just logs a hint.
    _draw_report_button(surface, font)

    if not status:
        _blit_text(surface, font, "[AUTO-INPUT]  waiting for first capture...", (8, 6), _TEXT_GRAY)
        return

    gap = 10  # px gap between chunks on the same line

    # Line 1: header + badge state + diff
    badge = status.get("badge")
    badge_diff = status.get("badge_diff")
    badge_str = badge if badge else "?"
    x = 8
    x = _blit_text(surface, font, "[AUTO-INPUT]", (x, 6), _TEXT_WHITE) + gap + 4
    x = _blit_text(surface, font, "badge:", (x, 6), _TEXT_GRAY) + gap
    x = _blit_text(surface, font, badge_str, (x, 6), _badge_color(badge_diff)) + gap
    if badge_diff is not None:
        _blit_text(surface, font, f"(d={badge_diff:.1f})", (x, 6), _TEXT_GRAY)

    # Line 2: speed + distance/offset + cnt_pa + Layer 2 observed-flags
    s_val = status.get("speed")
    s_score = status.get("speed_score")
    d_val = status.get("distance")
    d_score = status.get("distance_score")
    offset_val = status.get("stopping_offset_cm")
    offset_score = status.get("stopping_offset_score")
    sl_val = status.get("speed_limit")
    sl_score = status.get("speed_limit_score")
    y2 = 28
    x = 8
    x = _blit_text(surface, font, "spd:", (x, y2), _TEXT_GRAY) + gap
    spd_str = f"{s_val:>3} km/h" if s_val is not None else " -- km/h"
    x = _blit_text(surface, font, spd_str, (x, y2), _conf_color(s_score if s_val is not None else None)) + gap + 6
    # Cell-content priority: cm reading wins (only shows briefly after arrival, then
    # the cell swaps back to m-distance to next station even while parked at platform).
    # Fall through to m otherwise.
    if offset_val is not None:
        x = _blit_text(surface, font, "off:", (x, y2), _TEXT_GRAY) + gap
        x = _blit_text(surface, font, f"{offset_val:+d}cm", (x, y2), _conf_color(offset_score)) + gap + 6
    else:
        x = _blit_text(surface, font, "dst:", (x, y2), _TEXT_GRAY) + gap
        dst_str = f"{d_val:>5}m" if d_val is not None else "  ---m"
        x = _blit_text(surface, font, dst_str, (x, y2), _conf_color(d_score if d_val is not None else None)) + gap + 6
    # Speed limit (line-dependent, often empty — only show when present).
    if sl_val is not None:
        x = _blit_text(surface, font, "lim:", (x, y2), _TEXT_GRAY) + gap
        x = _blit_text(surface, font, f"{sl_val} km/h", (x, y2), _conf_color(sl_score)) + gap + 6
    x = _blit_text(surface, font, f"cnt_pa={sim_state.cnt_pa}", (x, y2), _TEXT_GRAY) + gap + 6
    dep_obs = bool(status.get("departure_observed"))
    arr_obs = bool(status.get("arrival_observed"))
    atstn_obs = bool(status.get("at_station_observed"))
    x = _blit_text(surface, font, "dep✓" if dep_obs else "dep·", (x, y2), _TEXT_WHITE if dep_obs else _TEXT_GRAY) + gap
    x = _blit_text(surface, font, "arr✓" if arr_obs else "arr·", (x, y2), _TEXT_WHITE if arr_obs else _TEXT_GRAY) + gap
    _blit_text(surface, font, "atstn✓" if atstn_obs else "atstn·", (x, y2), _TEXT_WHITE if atstn_obs else _TEXT_GRAY)

    # Line 3: App-layer position description + Layer 3 inferred game state.
    inferred = status.get("inferred_state", Layer3State.UNKNOWN)
    inferred_suffix = f"  ·  game: {inferred}"
    seg_start = status.get("segment_start_stop")
    y3 = 50
    if badge == "STOPPED" and 0 <= sim_state.curr_stop < len(stops):
        cur = stops[sim_state.curr_stop].get("name", "?")
        _blit_text(surface, font, f"app: stopped at {cur}{inferred_suffix}", (8, y3), _TEXT_WHITE)
    elif seg_start is not None and 0 <= seg_start < len(stops) and 0 <= sim_state.curr_stop < len(stops):
        from_name = stops[seg_start].get("name", "?")
        to_name = stops[sim_state.curr_stop].get("name", "?")
        passing = "  (passing through — arrival skipped)" if badge == "PASSING" else ""
        _blit_text(
            surface, font, f"app: between {from_name} -> {to_name}  (curr_stop={sim_state.curr_stop}){passing}{inferred_suffix}", (8, y3), _TEXT_WHITE
        )
    else:
        _blit_text(surface, font, f"app: curr_stop={sim_state.curr_stop}{inferred_suffix}", (8, y3), _TEXT_GRAY)


# ─────────────────────────── auto-input driver ────────────────────────────


def _crop_cell(frame_bgra: np.ndarray, hud_bbox: tuple[int, int, int, int], cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop a HUD cell from a BGRA frame as RGB numpy array. Pure-numpy, thread-safe.

    Used instead of pygame.image.frombuffer + Surface.blit so we don't touch pygame
    state from the background thread (the simulator owns the display thread).
    """
    hx, hy, _, _ = hud_bbox
    vx, vy, vw, vh = cell_bbox
    cell_bgra = frame_bgra[hy + vy : hy + vy + vh, hx + vx : hx + vx + vw]
    # BGRA -> RGB; .copy() ensures contiguous memory for downstream OCR
    return cell_bgra[:, :, [2, 1, 0]].copy()


@dataclass
class _Detector:
    """State machine over distance + speed + badge samples.

    Layer 2 cache (per-segment): three `*_observed` flags record whether the
    trigger condition for that event has been observed in the current segment.
    Reset on BADGE_STOPPED→(MOVING|PASSING). The flags semantically record "we
    observed the trigger condition" — whether the dispatcher acts on the
    resulting FIRE_* event is a separate concern (mismatch-skip in
    `_fire_departure` / `_fire_arrival`).

    `inferred_state()` returns the canonical Layer 3 state — what AutoDriver
    thinks the IRL game train is doing. See AUTO_INPUT.md § "Layer 3" for the
    inference truth table.

    PASSING badge handling: while the badge reads PASSING the HUD distance is to
    the passing-through station, NOT to the next stopping station — so arrival
    is only checked when badge==MOVING. Arrival uses a level test (distance ≤
    threshold) rather than a downward crossing so we still fire correctly when
    the badge transitions PASSING→MOVING with distance already under the lead.
    """

    arrival_lead_m: int = DEFAULT_LEAD_M
    prev_speed: Optional[int] = None
    prev_badge: Optional[str] = None
    departure_observed: bool = False
    arrival_observed: bool = False
    at_station_observed: bool = False

    def inferred_state(self) -> str:
        """Return the canonical Layer 3 state for the current sample.

        Pure function of `prev_badge` + Layer 2 cache. See AUTO_INPUT.md
        § "Layer 3 — AutoDriver's inferred game state" for the truth table.
        """
        badge = self.prev_badge
        if badge is None:
            return Layer3State.UNKNOWN
        if badge == "STOPPED":
            return Layer3State.STOPPING_AFTER_ARR if self.arrival_observed else Layer3State.STOPPING_FRESH
        # MOVING or PASSING
        if self.arrival_observed:
            return Layer3State.MOVING_AFTER_ARR
        if self.departure_observed:
            return Layer3State.APPROACHING_AFTER_DEP
        return Layer3State.APPROACHING_BEFORE_DEP

    def update(self, distance: Optional[int], speed: Optional[int], badge: Optional[str]) -> list[str]:
        events: list[str] = []
        # Cross-attribute reject (black-screen guard). The game sometimes blacks the
        # screen briefly to fast-forward simulated time, but ONLY while parked at a
        # platform — never mid-transit. During that window the badge cell goes uniform-
        # dark and the classifier picks whichever anchor pixel-diffs lowest (typically
        # PASSING — blue is closer to black than green); the dist cell drops out
        # consistently while speed sometimes survives showing the parked-at-platform 0.
        # Structural rule: a real STOPPED→{MOVING,PASSING} transition always shows
        # speed climbing from 0 (the game can't fake movement without rendering it),
        # so when prev_badge==STOPPED, require speed>0 to accept the transition.
        # Without this the spurious PASSING fires a phantom STOPPED→PASSING and resets
        # observed-flags as if a new segment began. See AUTO_INPUT.md § "Cross-attribute reject".
        if self.prev_badge == "STOPPED" and badge in ("MOVING", "PASSING") and (speed is None or speed == 0):
            print(
                f"          [AD] >>> CROSS-REJECT raw_badge={badge} (prev=STOPPED, speed={speed} — train hasn't moved; likely black-screen at platform)"
            )
            badge = None
        # Segment boundaries: STOPPED ↔ (MOVING | PASSING). Both MOVING and
        # PASSING signal "the train is moving" — the OCR can mis-classify
        # a normal MOVING segment as PASSING for many consecutive frames
        # (live drive on Keiyo 2026-04-27 showed the ~80s run from 千葉みなと to
        # 稲毛海岸 stuck at PASSING). If we only reset on STOPPED→MOVING, those
        # mis-classified segments inherit observed-flags from the previous
        # segment and skip both PAs entirely. Resetting on
        # STOPPED→(MOVING|PASSING) makes the detector resilient to that misread.
        # Mid-segment MOVING↔PASSING transitions remain silent — those are the
        # legitimate "we're crossing a passing-through station" markers within
        # an already-active segment.
        if badge is not None and self.prev_badge is not None and badge != self.prev_badge:
            if self.prev_badge == "STOPPED" and badge in ("MOVING", "PASSING"):
                events.append("STOPPED->MOVING")
                self.departure_observed = False
                self.arrival_observed = False
                self.at_station_observed = False
            elif self.prev_badge in ("MOVING", "PASSING") and badge == "STOPPED":
                events.append("MOVING->STOPPED")
        # Departure: speed crossing 30 km/h upward — own-train speed, badge-independent.
        if speed is not None and self.prev_speed is not None:
            if not self.departure_observed and self.prev_speed < SPEED_DEPARTURE_KMH <= speed:
                events.append("FIRE_DEPARTURE")
                self.departure_observed = True
        # Arrival: level test, gated on badge==MOVING. Skips PASSING (wrong distance ref);
        # handles PASSING→MOVING with distance already <lead via the level (not crossing) check.
        if badge == "MOVING" and distance is not None:
            if not self.arrival_observed and distance <= self.arrival_lead_m:
                events.append("FIRE_ARRIVAL")
                self.arrival_observed = True
        # At-station: level test, gated on (badge==STOPPED AND arrival_observed).
        # `arrival_observed` ensures the train *just* arrived in this segment —
        # it rules out boot (parked at start station with no preceding approach)
        # and post-jump_to_stop. Triggers the press that flips `at_station=True`
        # on the simulator (no audio — unified state machine's APPROACHING→STOPPING
        # transition is silent; pa_at_station cycling happens on subsequent presses).
        if badge == "STOPPED" and self.arrival_observed and not self.at_station_observed:
            events.append("FIRE_AT_STATION")
            self.at_station_observed = True
        if speed is not None:
            self.prev_speed = speed
        if badge is not None:
            self.prev_badge = badge
        return events


@dataclass
class AutoDriver:
    """Background-thread auto-driver. Captures HUD, runs OCR, sets sim.pending_next_pa.

    Lifecycle:
        driver = AutoDriver(sim)
        driver.start()        # spawn daemon thread
        sim.run()             # blocks main thread; auto-driver runs alongside
        driver.stop()         # signals thread to exit; joins with timeout
    """

    sim: "PASimulator"
    lead_m: int = DEFAULT_LEAD_M
    interval_s: int = SAMPLE_INTERVAL_S

    # Internal state — set by _run on thread start
    _detector: _Detector = field(init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _segment_start_stop: int = field(default=-1, init=False)

    def __post_init__(self) -> None:
        self._detector = _Detector(arrival_lead_m=self.lead_m)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AutoDriver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        print("[AutoDriver] Loading OCR templates + badge anchors...")
        templates = build_templates()
        badge_anchors = load_badge_anchors()
        missing = set("0123456789") - templates.glyphs.keys()
        if missing:
            print(f"[AutoDriver] FATAL: missing digit templates: {sorted(missing)} — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract from _ocr_calibration/.")
            return
        if not any(badge_anchors.values()):
            print("[AutoDriver] FATAL: no badge anchors loaded — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract from _ocr_calibration/.")
            return

        print("[AutoDriver] Initializing dxcam...")
        camera = dxcam.create(output_color="BGRA")
        if camera is None:
            print("[AutoDriver] dxcam.create() returned None — DXGI capture unavailable. Auto-driver disabled.")
            return
        print(f"[AutoDriver] Started. Lead {self.lead_m}m, interval {self.interval_s}s.")

        # Open per-drive blackbox log (JSONL). One file per AutoDriver lifetime;
        # each sample below appends a line + flushes for crash safety. Path is
        # also stashed on the simulator so the debug-bar Report button can find
        # the live log to render.
        log_file, log_path = _open_drive_log(self.sim)
        if log_path is not None:
            print(f"[AutoDriver] Recording drive log -> {log_path}")
            self.sim.drive_log_path = log_path

        # Track previous-cycle badge for emitting transition events into the log.
        # Distinct from `self._detector.prev_badge` — that one drives PA-fire
        # logic; this one drives the blackbox event stream.
        prev_log_badge: Optional[str] = None

        # Snapshot initial state to recognize the first segment
        self._segment_start_stop = self.sim.state.curr_stop

        try:
            while not self._stop_event.is_set():
                try:
                    frame = None
                    for _ in range(5):
                        frame = camera.grab()
                        if frame is not None:
                            break
                        if self._stop_event.wait(0.2):
                            return
                    if frame is None:
                        self._stop_event.wait(self.interval_s)
                        continue

                    d_cell = _crop_cell(frame, HUD_BBOX, DISTANCE_VALUE_BBOX)
                    s_cell = _crop_cell(frame, HUD_BBOX, SPEED_VALUE_BBOX)
                    sl_cell = _crop_cell(frame, HUD_BBOX, SPEED_LIMIT_VALUE_BBOX)
                    b_cell = _crop_cell(frame, HUD_BBOX, BADGE_BBOX)
                    badge, b_diff = classify_badge_state(b_cell, badge_anchors)
                    s_val, _, s_score = read_speed(s_cell, templates)
                    # The DISTANCE cell is shared and self-identifies via color: dark text
                    # `Nm` (distance to next stop, both transit and ~5s+ after arriving at
                    # platform) vs green text `+/-Ncm` (stopping offset, briefly after
                    # arrival). Run both readers unconditionally — their masks are
                    # mutually exclusive, only one returns non-None per frame.
                    d_val, _, d_score = read_distance(d_cell, templates)
                    offset_val, _, offset_score = read_stopping_offset(d_cell, templates)
                    # Speed limit (最高速度): line-dependent, often empty. None is normal.
                    sl_val, _, sl_score = read_speed_limit(sl_cell, templates)
                    sample_ts = time.time()

                    # Publish status to the simulator's debug panel (atomic dict swap).
                    # Single-writer (this thread), single-reader (main thread) — no lock needed.
                    self.sim.auto_input_status = {
                        "badge": badge,
                        "badge_diff": b_diff,
                        "speed": s_val,
                        "speed_score": s_score,
                        "distance": d_val,
                        "distance_score": d_score,
                        "stopping_offset_cm": offset_val,
                        "stopping_offset_score": offset_score,
                        "speed_limit": sl_val,
                        "speed_limit_score": sl_score,
                        "segment_start_stop": self._segment_start_stop,
                        "departure_observed": self._detector.departure_observed,
                        "arrival_observed": self._detector.arrival_observed,
                        "at_station_observed": self._detector.at_station_observed,
                        "inferred_state": self._detector.inferred_state(),
                        "ts": sample_ts,
                    }

                    if log_file is not None:
                        # Emit a transition event BEFORE the sample so the plot
                        # reader sees event-then-sample in chronological order.
                        kind = _badge_transition_kind(prev_log_badge, badge)
                        if kind is not None:
                            _write_event(log_file, kind, self.sim.state.curr_stop, sample_ts)

                        _write_sample(
                            log_file,
                            {
                                "_type": "sample",
                                "ts": sample_ts,
                                "speed": s_val,
                                "speed_score": s_score,
                                "distance": d_val,
                                "distance_score": d_score,
                                "stopping_offset_cm": offset_val,
                                "stopping_offset_score": offset_score,
                                "speed_limit": sl_val,
                                "speed_limit_score": sl_score,
                                "badge": badge,
                                "badge_diff": b_diff,
                                "curr_stop": self.sim.state.curr_stop,
                                "cnt_pa": self.sim.state.cnt_pa,
                                "departure_observed": self._detector.departure_observed,
                                "arrival_observed": self._detector.arrival_observed,
                                "inferred_state": self._detector.inferred_state(),
                                "segment_start_stop": self._segment_start_stop,
                            },
                        )

                    if badge is not None:
                        prev_log_badge = badge

                    ts = time.strftime("%H:%M:%S")
                    s_str = f"{s_val:>3}km/h" if s_val is not None else " --"
                    b_str = badge or "?"
                    # Cell-content priority: cm reading wins (only shows briefly after
                    # arrival); fall through to m if cm is empty.
                    if offset_val is not None:
                        dist_field = f"off={offset_val:+d}cm"
                    elif d_val is not None:
                        dist_field = f"dst={d_val:>5}m"
                    else:
                        dist_field = "dst=  ---"
                    sl_field = f"  lim={sl_val}km/h" if sl_val is not None else ""
                    print(
                        f"[AD {ts}]  badge={b_str:<7}({b_diff:5.1f})  spd={s_str}  {dist_field}{sl_field}  "
                        f"sim:stop={self.sim.state.curr_stop} cnt_pa={self.sim.state.cnt_pa}"
                    )

                    for ev in self._detector.update(d_val, s_val, badge):
                        self._handle_event(ev)

                    self._stop_event.wait(self.interval_s)
                except Exception as e:
                    print(f"[AutoDriver] Error in capture loop: {e}")
                    self._stop_event.wait(self.interval_s)
        finally:
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass

        print("[AutoDriver] Stopped.")

    def _handle_event(self, event: str) -> None:
        if event == "STOPPED->MOVING":
            self._segment_start_stop = self.sim.state.curr_stop
            print(f"          [AD] >>> BADGE STOPPED->MOVING (segment_start_stop={self._segment_start_stop}, flags reset)")
            return
        if event == "MOVING->STOPPED":
            print("          [AD] >>> BADGE MOVING->STOPPED (arrived)")
            return
        if event == "FIRE_DEPARTURE":
            self._fire_departure()
            return
        if event == "FIRE_ARRIVAL":
            self._fire_arrival()
            return
        if event == "FIRE_AT_STATION":
            self._fire_at_station()
            return

    def _fire_departure(self) -> None:
        # Departure is "advance from segment_start_stop to next stop" — auto-fire
        # only if curr_stop is still segment_start_stop. Otherwise user already advanced.
        if self.sim.state.curr_stop != self._segment_start_stop:
            print(f"          [AD] >>> SKIPPED departure fire (sim already at stop {self.sim.state.curr_stop}; user advanced manually)")
            return
        # Silent pa_at_station drain — if user lagged on at-station announcements,
        # the synthesized press below would consume one queue entry instead of
        # advancing the segment. Mark the queue as exhausted so _next_in_stopping
        # falls through to _advance_to_next_stop (plays pa[0] of next stop).
        if self.sim.state.at_station:
            pa_at_st = self.sim.stops[self.sim.state.curr_stop].get("pa_at_station", [])
            if self.sim.state.cnt_pa_at_station + 1 < len(pa_at_st):
                dropped = len(pa_at_st) - 1 - self.sim.state.cnt_pa_at_station
                self.sim.state.cnt_pa_at_station = len(pa_at_st) - 1
                print(f"          [AD] >>> Silent drain: dropped {dropped} unplayed pa_at_station entr{'y' if dropped == 1 else 'ies'}")
        self.sim.pending_next_pa = True
        print("          [AD] >>> FIRED departure (set pending_next_pa)")

    def _fire_arrival(self) -> None:
        curr = self.sim.state.curr_stop
        # After departure fired, curr_stop should be segment_start_stop + 1.
        # If it's still segment_start_stop, departure didn't fire — would be premature.
        # If it's beyond, user already fired arrival or skipped to next stop.
        if curr <= self._segment_start_stop:
            print(f"          [AD] >>> SKIPPED arrival fire (departure not yet fired; sim at stop {curr})")
            return
        if curr > self._segment_start_stop + 1:
            print(f"          [AD] >>> SKIPPED arrival fire (sim advanced past expected; at stop {curr})")
            return

        target = self.sim.stops[curr] if curr < len(self.sim.stops) else None
        if target is None:
            print(f"          [AD] >>> SKIPPED arrival fire (curr_stop {curr} out of range)")
            return

        pa_count = len(target.get("pa", []))
        if pa_count <= 1:
            name = target.get("name", "?")
            print(f"          [AD] >>> SKIPPED arrival fire (stop '{name}' has {pa_count} PA — no arrival announcement)")
            return

        if self.sim.state.cnt_pa >= pa_count - 1:
            print(f"          [AD] >>> SKIPPED arrival fire (cnt_pa={self.sim.state.cnt_pa} already at last PA; user fired manually)")
            return

        self.sim.pending_next_pa = True
        print("          [AD] >>> FIRED arrival (set pending_next_pa)")

    def _fire_at_station(self) -> None:
        # The press that flips the sim from APPROACHING into STOPPING (ただいま).
        # No audio — the unified state machine's APPROACHING→STOPPING transition
        # is silent; this press just sets `state.at_station=True`. Subsequent
        # presses cycle pa_at_station (if any) then advance.
        if self.sim.state.at_station:
            print("          [AD] >>> SKIPPED at-station fire (sim already STOPPING)")
            return
        curr = self.sim.state.curr_stop
        # Mirrors _fire_arrival's anchor — curr should be segment_start_stop+1
        # by now (arrival fire moved sim there, or it was already there).
        if curr <= self._segment_start_stop:
            print(f"          [AD] >>> SKIPPED at-station fire (sim still at segment_start={self._segment_start_stop}; arrival not advanced)")
            return
        if curr > self._segment_start_stop + 1:
            print(f"          [AD] >>> SKIPPED at-station fire (sim past expected stop; at {curr})")
            return
        target = self.sim.stops[curr] if curr < len(self.sim.stops) else None
        if target is None:
            return
        pa = target.get("pa", [])
        # cnt_pa must be at the last approach PA (or pa empty) — otherwise the
        # press would play the next approach PA instead of entering STOPPING,
        # leaving the display on "まもなく" while the train is parked.
        if pa and self.sim.state.cnt_pa != len(pa) - 1:
            print(f"          [AD] >>> SKIPPED at-station fire (cnt_pa={self.sim.state.cnt_pa}, expected={len(pa) - 1}; arrival likely missed)")
            return
        self.sim.pending_next_pa = True
        print("          [AD] >>> FIRED at-station (set pending_next_pa)")

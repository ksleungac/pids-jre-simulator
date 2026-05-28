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

Architecture pointer: auto_input/README.md "Architecture" section.

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

from .hud_layout import PROFILES
from .ocr import (
    DEFAULT_TEMPLATES_DIR,
    Templates,
    build_templates,
    classify_badge_state,
    load_badge_anchors,
    read_distance,
    read_speed,
    read_speed_limit,
    read_stopping_offset,
    seg_for_scale,
)

if TYPE_CHECKING:
    from app import PASimulator


SAMPLE_INTERVAL_S = 5
SPEED_DEPARTURE_KMH = 30
DEFAULT_LEAD_M = 900


class Layer3State:
    """Canonical names for AutoDriver's inferred view of the IRL game state.

    Renamed 2026-05-09 from trigger-fire-shape names (STOPPING_FRESH,
    APPROACHING_BEFORE_DEP, etc.) to verb-form transit vocabulary. The new
    names describe what the train is *doing*, not which detector flag has
    flipped. See auto_input/README.md § "Layer 3 — AutoDriver's inferred game state"
    for the full inference truth table.
    """

    IDLE = "IDLE"  # parked at start, no movement yet
    STOPPED = "STOPPED"  # parked at platform after arrival
    DEPARTING = "DEPARTING"  # rolling out, speed not yet >30 km/h
    CRUISING = "CRUISING"  # at full speed between stops
    ARRIVING = "ARRIVING"  # dist <900m, decelerating into platform
    UNKNOWN = "UNKNOWN"


# Plain-English panel labels — wire and panel names line up 1:1 after the
# 2026-05-09 rename, so this map is essentially title-case identity. Kept as
# a discrete map so future divergence (i18n, customization) has a hook.
_LAYER3_HUMAN = {
    Layer3State.IDLE: "Idle",
    Layer3State.STOPPED: "Stopped",
    Layer3State.DEPARTING: "Departing",
    Layer3State.CRUISING: "Cruising",
    Layer3State.ARRIVING: "Arriving",
    Layer3State.UNKNOWN: "—",
}


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

# Speed-limit OCR misread debug dump. When a grammar-valid speed_limit read scores
# below this threshold, the source cell is saved as a PNG under the dump dir for
# offline calibration. Local-only (parent _ocr_calibration/ is gitignored).
SUSPICIOUS_SPEED_LIMIT_SCORE = 0.75
MISREAD_DUMP_DIR = project_root() / "_ocr_calibration" / "_misread_dumps"


def _dump_misread_speed_limit_cell(cell: np.ndarray, sl_val: int, sl_score: float, ts: float) -> None:
    """Save a low-confidence speed-limit cell crop as PNG for offline calibration.
    Filename encodes ts (millisecond int, matches JSONL ts*1000), score, and the
    misread value. Failures are logged but do not raise — debug-only."""
    try:
        MISREAD_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        h, w, _ = cell.shape
        surf = pygame.image.frombuffer(cell.tobytes(), (w, h), "RGB")
        path = MISREAD_DUMP_DIR / f"sl_{int(ts * 1000)}_score{int(sl_score * 100)}_read{sl_val}.png"
        pygame.image.save(surf, str(path))
    except Exception as e:
        print(f"[AutoDriver] misread cell dump failed: {e}")


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
_pause_button_rect: Optional[pygame.Rect] = None

# Top-left button strip. Horizontal pill shape — icon left, label right, width
# auto-fits the label so longer labels don't overflow. Pills are short enough
# (32px) that only line 1 of the panel content sits beside them; lines 2-3
# reclaim full panel width below.
_BTN_X0 = 8
_BTN_Y0 = 4
_BTN_HEIGHT = 32
_BTN_GAP = 6

# Smaller font dedicated to button labels.
_button_font: Optional[pygame.font.Font] = None


def _get_button_font() -> pygame.font.Font:
    global _button_font
    if _button_font is None:
        _button_font = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 12)
    return _button_font


def _draw_pill_button(
    surface: pygame.Surface,
    x: int,
    y: int,
    color: tuple[int, int, int],
    icon_kind: str,
    label: str,
    paused: bool = False,
) -> pygame.Rect:
    """Horizontal pill: rounded ends, icon on the left, label on the right.
    Width sized to fit the label. `icon_kind` ∈ {"pause", "report"}; for "pause",
    `paused=True` swaps to a play triangle."""
    label_font = _get_button_font()
    label_surf = label_font.render(label, True, _TEXT_WHITE)
    icon_w = 16
    pad_x = 12
    icon_label_gap = 8
    btn_w = pad_x + icon_w + icon_label_gap + label_surf.get_width() + pad_x
    rect = pygame.Rect(x, y, btn_w, _BTN_HEIGHT)
    pygame.draw.rect(surface, color, rect, border_radius=_BTN_HEIGHT // 2)

    icon_cx = x + pad_x + icon_w // 2
    cy = y + _BTN_HEIGHT // 2
    if icon_kind == "pause":
        if paused:
            tri = [(icon_cx - 5, cy - 8), (icon_cx - 5, cy + 8), (icon_cx + 7, cy)]
            pygame.draw.polygon(surface, _TEXT_WHITE, tri)
        else:
            bar_w, bar_h = 4, 14
            pygame.draw.rect(surface, _TEXT_WHITE, (icon_cx - 5, cy - bar_h // 2, bar_w, bar_h))
            pygame.draw.rect(surface, _TEXT_WHITE, (icon_cx + 1, cy - bar_h // 2, bar_w, bar_h))
    elif icon_kind == "report":
        pygame.draw.line(surface, _TEXT_WHITE, (icon_cx, cy - 7), (icon_cx, cy + 2), 3)
        head = [(icon_cx - 5, cy - 1), (icon_cx + 5, cy - 1), (icon_cx, cy + 7)]
        pygame.draw.polygon(surface, _TEXT_WHITE, head)

    label_x = x + pad_x + icon_w + icon_label_gap
    label_y = cy - label_surf.get_height() // 2
    surface.blit(label_surf, (label_x, label_y))
    return rect


def _draw_pause_button(surface: pygame.Surface, paused: bool) -> pygame.Rect:
    """Top-left pill with icon + label. Orange when paused, slate when running."""
    global _pause_button_rect
    color = (180, 100, 50) if paused else (80, 100, 120)
    label = "Resume" if paused else "Pause"
    _pause_button_rect = _draw_pill_button(surface, _BTN_X0, _BTN_Y0, color, "pause", label, paused=paused)
    return _pause_button_rect


def _draw_report_button(surface: pygame.Surface, x: int) -> pygame.Rect:
    """Pill button drawn to the right of Pause. Renders the drive's speed-curve HTML report."""
    global _report_button_rect
    _report_button_rect = _draw_pill_button(surface, x, _BTN_Y0, (52, 116, 145), "report", "Save Speed Curve")
    return _report_button_rect


def _render_report_async(log_path: Path) -> None:
    """Background-thread report generation so the simulator UI doesn't freeze.

    `auto_input/` package and `plot_drive.py` both live at the project root, so
    the import resolves via the standard sys.path that the launching
    `main.py` set up — no per-call sys.path.insert needed (and previously
    accumulated duplicate entries on every click).
    """
    try:
        from plot_drive import render_html_report, load_jsonl

        out_path = project_root() / f"{log_path.stem}.html"
        meta, events, samples = load_jsonl(log_path)
        render_html_report(meta, events, samples, 999, out_path)
        print(f"[Drive recorder] Report saved -> {out_path}")
    except Exception as e:
        print(f"[Drive recorder] Report generation failed: {e}")


def handle_panel_click(sim, pos: tuple[int, int]) -> bool:
    """Dispatch a MOUSEBUTTONDOWN that landed inside the debug panel.

    Returns True if a button absorbed the click (caller can stop propagating).
    """
    if _pause_button_rect is not None and _pause_button_rect.collidepoint(pos):
        driver = getattr(sim, "auto_driver", None)
        if driver is not None:
            driver.paused = not driver.paused
            print(f"[AutoDriver] {'paused' if driver.paused else 'resumed'} via panel button")
        return True
    if _report_button_rect is not None and _report_button_rect.collidepoint(pos):
        log_path = getattr(sim, "drive_log_path", None)
        if log_path is None:
            print("[Drive recorder] No drive log open yet — wait for the AutoDriver to capture some samples.")
            return True
        print(f"[Drive recorder] Generating report from {log_path.name} ...")
        threading.Thread(target=_render_report_async, args=(log_path,), daemon=True).start()
        return True
    return False


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
    paused = bool(status.get("paused", False))

    # Always-on top-left button strip — Pause first, Report second. Pills size
    # to fit their labels, so we render Pause first and place Report immediately
    # to its right.
    pause_rect = _draw_pause_button(surface, paused)
    report_rect = _draw_report_button(surface, pause_rect.right + _BTN_GAP)
    line1_x = report_rect.right + 14

    # 3-row layout. Line 1 sits beside the buttons (matching their vertical
    # center); lines 2-3 reclaim full panel width below the 32px button strip.
    y1, y2, y3 = 12, 40, 60

    if not status or all(k == "paused" for k in status):
        _blit_text(surface, font, "Game Sync  ·  waiting for first capture...", (line1_x, y1), _TEXT_GRAY)
        return

    gap = 10  # px gap between chunks on the same line

    # Line 1: header + raw badge state + match-diff. Header tints orange when
    # paused so the frozen-OCR state is unmistakable at a glance.
    header_color = _COLOR_ORANGE if paused else _TEXT_WHITE
    header_label = "Game Sync — PAUSED" if paused else "Game Sync"
    badge = status.get("badge")
    badge_diff = status.get("badge_diff")
    badge_str = badge if badge else "?"
    x = line1_x
    x = _blit_text(surface, font, header_label, (x, y1), header_color) + gap + 4
    x = _blit_text(surface, font, badge_str, (x, y1), _badge_color(badge_diff)) + gap
    if badge_diff is not None:
        x = _blit_text(surface, font, f"(d={badge_diff:.1f})", (x, y1), _TEXT_GRAY) + gap

    # Auto-fire chip — visible for 3s after a successful fire so the user can
    # confirm the auto-driver is acting. Skipped fires don't surface here (they
    # only print to console); only successful pending_next_pa sets land here.
    last_fire = status.get("last_fire")
    if last_fire is not None and isinstance(last_fire, dict):
        fire_age = time.time() - last_fire.get("ts", 0)
        if fire_age < 3.0:
            chip_label = f"  ●  Auto-fired: {last_fire.get('type', '?')}"
            _blit_text(surface, font, chip_label, (x, y1), _COLOR_GREEN)

    # Line 2: OCR readings — speed, limit, distance, stopping position (split
    # into independent fields so the user can see both the in-transit distance
    # and the platform-arrival offset, even when only one is currently populated).
    s_val = status.get("speed")
    s_score = status.get("speed_score")
    d_val = status.get("distance")
    d_score = status.get("distance_score")
    offset_val = status.get("stopping_offset_cm")
    offset_score = status.get("stopping_offset_score")
    sl_val = status.get("speed_limit")
    sl_score = status.get("speed_limit_score")
    # Line 2 sits below the button strip — full panel width available.
    x = 8
    x = _blit_text(surface, font, "speed:", (x, y2), _TEXT_GRAY) + 6
    spd_str = f"{s_val:>3} km/h" if s_val is not None else " -- km/h"
    x = _blit_text(surface, font, spd_str, (x, y2), _conf_color(s_score if s_val is not None else None)) + gap
    if sl_val is not None:
        x = _blit_text(surface, font, "limit:", (x, y2), _TEXT_GRAY) + 6
        x = _blit_text(surface, font, f"{sl_val} km/h", (x, y2), _conf_color(sl_score)) + gap
    x = _blit_text(surface, font, "distance:", (x, y2), _TEXT_GRAY) + 6
    if d_val is not None:
        x = _blit_text(surface, font, f"{d_val:>5}m", (x, y2), _conf_color(d_score)) + gap
    else:
        x = _blit_text(surface, font, "  -- m", (x, y2), _TEXT_GRAY) + gap
    # Stopping position only renders when a reading is present (the cell
    # briefly populates after arrival). Brightness-pulse flash when shown so it
    # pops against the steady-state fields; nothing rendered otherwise.
    if offset_val is not None:
        x = _blit_text(surface, font, "stopping position:", (x, y2), _TEXT_GRAY) + 6
        flash_on = (pygame.time.get_ticks() // 350) % 2 == 0
        r, g, b = _conf_color(offset_score)
        offset_color: tuple[int, int, int] = (r, g, b) if flash_on else (int(r * 0.4), int(g * 0.4), int(b * 0.4))
        _blit_text(surface, font, f"{offset_val:+d} cm", (x, y2), offset_color)

    # Line 3: train state phrase + announcements played. State word leads (plain
    # English from _LAYER3_HUMAN); station name or segment is the detail.
    # Detector observation flags are intentionally NOT shown — the state word
    # already implies them (e.g. "Approaching" means departure was observed),
    # and they're available in the JSONL log for debugging.
    inferred = status.get("inferred_state", Layer3State.UNKNOWN)
    state_word = _LAYER3_HUMAN.get(inferred, "—")
    seg_start = status.get("segment_start_stop")
    if badge == "STOPPED" and 0 <= sim_state.curr_stop < len(stops):
        location = stops[sim_state.curr_stop].get("name", "?")
        line3 = f"{location}  ·  {state_word}"
    elif seg_start is not None and 0 <= seg_start < len(stops) and 0 <= sim_state.curr_stop < len(stops):
        from_name = stops[seg_start].get("name", "?")
        to_name = stops[sim_state.curr_stop].get("name", "?")
        passing = "  (passing through)" if badge == "PASSING" else ""
        line3 = f"{from_name} → {to_name}  ·  {state_word}{passing}"
    else:
        line3 = state_word
    # Played count: cnt_pa is 0-indexed and post-play (cnt_pa=0 means pa[0] has
    # been played). Displayed value is `cnt_pa+1` of total available PAs at this
    # stop. Start station (no pa) shows "—".
    pa_total = len(stops[sim_state.curr_stop].get("pa", [])) if 0 <= sim_state.curr_stop < len(stops) else 0
    played_str = f"{sim_state.cnt_pa + 1}/{pa_total}" if pa_total > 0 else "—"
    line3 += f"  ·  Played: {played_str}"
    _blit_text(surface, font, line3, (8, y3), _TEXT_WHITE)


# ─────────────────────────── auto-input driver ────────────────────────────


def _crop_cell(frame_bgra: np.ndarray, hud_bbox: tuple[int, int, int, int], cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop a HUD cell from a BGRA frame as RGB numpy array. Pure-numpy, thread-safe.

    Used instead of pygame.image.frombuffer + Surface.blit so we don't touch pygame
    DISPLAY state from the background thread (the simulator owns the display thread).
    Display-independent pygame.image calls (frombuffer + image.save with no display
    init dependency) are safe from this thread and are used by the misread dump hook.
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
    thinks the IRL game train is doing. See auto_input/README.md § "Layer 3" for the
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

        Pure function of `prev_badge` + Layer 2 cache. See auto_input/README.md
        § "Layer 3 — AutoDriver's inferred game state" for the truth table.
        """
        badge = self.prev_badge
        if badge is None:
            return Layer3State.UNKNOWN
        if badge == "STOPPED":
            return Layer3State.STOPPED if self.arrival_observed else Layer3State.IDLE
        # MOVING or PASSING
        if self.arrival_observed:
            return Layer3State.ARRIVING
        if self.departure_observed:
            return Layer3State.CRUISING
        return Layer3State.DEPARTING

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
        # observed-flags as if a new segment began. See auto_input/README.md § "Cross-attribute reject".
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
    # Toggled by the debug-panel "Pause" button. While True, the capture loop
    # skips frame.grab() / OCR / detector.update() and only updates the panel
    # status flag — last OCR readings stay frozen on screen so the user can
    # inspect them without the live stream overwriting.
    paused: bool = False

    # Internal state — set by _run on thread start
    _detector: _Detector = field(init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _segment_start_stop: int = field(default=-1, init=False)
    # Most recent successful auto-fire — surfaced on the debug panel as a
    # transient chip so the user can verify the auto-driver is acting. Updated
    # by _fire_departure / _fire_arrival / _fire_at_station on success only;
    # skipped fires don't count.
    _last_fire: Optional[dict] = field(default=None, init=False)

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
        print("[AutoDriver] Initializing dxcam...")
        camera = dxcam.create(output_color="BGRA")
        if camera is None:
            print("[AutoDriver] dxcam.create() returned None — DXGI capture unavailable. Auto-driver disabled.")
            return
        # Resolution gate. HUD bboxes scale per ResolutionProfile; templates
        # reused across resolutions via NN-resize in compare(). Probe desktop
        # dims → PROFILES.get((w,h)) → fail loud if unsupported so user sees
        # the cause instead of silent OCR garbage at wrong bbox geometry.
        # One-shot full grab gives the desktop dims; bounded retry mirrors the
        # main-loop retry pattern (dxcam can return None right after create()).
        probe = None
        for _ in range(5):
            probe = camera.grab()
            if probe is not None:
                break
            if self._stop_event.wait(0.2):
                return
        if probe is None:
            print("[AutoDriver] dxcam returned None on resolution probe — auto-driver disabled.")
            return
        ph, pw = probe.shape[:2]
        profile = PROFILES.get((pw, ph))
        if profile is None:
            supported = ", ".join(f"{w}×{h}" for w, h in sorted(PROFILES))
            print(f"[AutoDriver] FATAL: desktop resolution {pw}×{ph} not supported. " f"Supported: {supported}. Auto-driver disabled.")
            return
        seg = seg_for_scale(profile.scale)

        # Dark digit templates: always load from 1440p set. The resize-in-compare
        # approach (compare() in ocr.py) handles cross-resolution matching without
        # needing a separate 1080p dark-digit template set.
        templates = build_templates()
        missing = set("0123456789") - templates.glyphs.keys()
        if missing:
            print(f"[AutoDriver] FATAL: missing digit templates: {sorted(missing)} — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract from _ocr_calibration/.")
            return

        # Red digit templates: prefer resolution-specific set; fall back to the
        # global cache (1440p) via None so read_speed_limit uses _get_red_digit_templates().
        red_dir = (
            DEFAULT_TEMPLATES_DIR / profile.templates_subdir / "digits_red" if profile.templates_subdir else DEFAULT_TEMPLATES_DIR / "digits_red"
        )
        red_templates: Templates | None = build_templates(red_dir) if red_dir.exists() else None

        badges_dir = DEFAULT_TEMPLATES_DIR / profile.badges_subdir
        badge_anchors = load_badge_anchors(badges_dir)
        if not any(badge_anchors.values()):
            print(f"[AutoDriver] FATAL: no badge anchors at {badges_dir} — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract.")
            return
        print(
            f"[AutoDriver] Started {pw}×{ph}. Lead {self.lead_m}m, interval {self.interval_s}s. "
            f"Capture region {profile.capture_region} (top-right quadrant)."
        )

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
                    if self.paused:
                        # Mark status so panel renders the indicator. Preserve last OCR
                        # values — only the paused flag flips so the panel doesn't blank.
                        self.sim.auto_input_status = {**self.sim.auto_input_status, "paused": True}
                        self._stop_event.wait(self.interval_s)
                        continue
                    frame = None
                    for _ in range(5):
                        frame = camera.grab(region=profile.capture_region)
                        if frame is not None:
                            break
                        if self._stop_event.wait(0.2):
                            return
                    if frame is None:
                        self._stop_event.wait(self.interval_s)
                        continue

                    hud = profile.hud_bbox_in_capture
                    d_cell = _crop_cell(frame, hud, profile.distance_value_bbox)
                    s_cell = _crop_cell(frame, hud, profile.speed_value_bbox)
                    sl_cell = _crop_cell(frame, hud, profile.speed_limit_value_bbox)
                    b_cell = _crop_cell(frame, hud, profile.badge_bbox)
                    badge, b_diff = classify_badge_state(b_cell, badge_anchors)
                    s_val, _, s_score = read_speed(s_cell, templates, seg=seg)
                    # The DISTANCE cell is shared and self-identifies via color: dark text
                    # `Nm` (distance to next stop, both transit and ~5s+ after arriving at
                    # platform) vs green text `+/-Ncm` (stopping offset, briefly after
                    # arrival). Run both readers unconditionally — their masks are
                    # mutually exclusive, only one returns non-None per frame.
                    d_val, _, d_score = read_distance(d_cell, templates, seg=seg)
                    offset_val, _, offset_score = read_stopping_offset(d_cell, templates, seg=seg)
                    # Speed limit (最高速度): line-dependent, often empty. None is normal.
                    sl_val, _, sl_score = read_speed_limit(sl_cell, templates, seg=seg, red_templates=red_templates)
                    sample_ts = time.time()
                    if sl_val is not None and sl_score < SUSPICIOUS_SPEED_LIMIT_SCORE:
                        _dump_misread_speed_limit_cell(sl_cell, sl_val, sl_score, sample_ts)

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
                        "paused": False,
                        "last_fire": self._last_fire,
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
                                "cnt_pa_at_station": self.sim.state.cnt_pa_at_station,
                                "at_station": self.sim.state.at_station,
                                "departure_observed": self._detector.departure_observed,
                                "arrival_observed": self._detector.arrival_observed,
                                "at_station_observed": self._detector.at_station_observed,
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
        self._last_fire = {"ts": time.time(), "type": "departure"}
        print("          [AD] >>> FIRED departure (set pending_next_pa)")

    def _expected_next_stop(self) -> int:
        """First stopping-station index after segment_start_stop, or -1 if none.

        "Stopping station" detected via `stop.get("time") is not None` — the
        canonical DATA_FORMAT.md discriminator (passing stations have NO `time`
        field). This matches `_build_stops_meta`'s `stops_here` test in this
        same module. **Note:** the simulator's `_advance_to_next_stop` uses a
        different test (`bool(pa) or bool(pa_at_station)`) that filters by
        audio content rather than schedule presence — they agree for normal
        routes but diverge on stopping stations with empty audio (e.g. start
        station). Use `time` here because we want "where the train physically
        stops," not "where audio plays."

        Routes with passing-through stops between two stopping stops mean
        curr_stop legitimately jumps past +1 (e.g. chuo Nakano(18) → Shinjuku(21)
        skips 東中野(19) + 大久保(20)). The expected post-departure curr_stop
        is the next stopping-station index, not segment_start_stop + 1.
        """
        for k in range(self._segment_start_stop + 1, len(self.sim.stops)):
            if self.sim.stops[k].get("time") is not None:
                return k
        return -1

    def _fire_arrival(self) -> None:
        curr = self.sim.state.curr_stop
        expected = self._expected_next_stop()
        # After departure fired, curr_stop should be `expected`.
        # If it's still segment_start_stop, departure didn't fire — would be premature.
        # If it differs from expected, user manually advanced to the wrong stop.
        if curr <= self._segment_start_stop:
            print(f"          [AD] >>> SKIPPED arrival fire (departure not yet fired; sim at stop {curr})")
            return
        if curr != expected:
            print(f"          [AD] >>> SKIPPED arrival fire (sim at stop {curr}, expected {expected})")
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
        self._last_fire = {"ts": time.time(), "type": "arrival"}
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
        expected = self._expected_next_stop()
        # Mirrors _fire_arrival's anchor — curr should be `expected` by now
        # (arrival fire moved sim there, or it was already there).
        if curr <= self._segment_start_stop:
            print(f"          [AD] >>> SKIPPED at-station fire (sim still at segment_start={self._segment_start_stop}; arrival not advanced)")
            return
        if curr != expected:
            print(f"          [AD] >>> SKIPPED at-station fire (sim at stop {curr}, expected {expected})")
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
        self._last_fire = {"ts": time.time(), "type": "at-station"}
        print("          [AD] >>> FIRED at-station (set pending_next_pa)")

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

import i18n
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


# Layer 3 inferred-state → i18n key for the line-1 state word. UNKNOWN has no
# key (renders the literal em-dash placeholder). These are the user-facing
# "what the train is doing" words; the de-jargoned public phrasing + zh_HK
# translations live in data/translations_app.json under panel.state.*.
_STATE_KEY = {
    Layer3State.IDLE: "panel.state.idle",
    Layer3State.STOPPED: "panel.state.stopped",
    Layer3State.DEPARTING: "panel.state.departing",
    Layer3State.CRUISING: "panel.state.cruising",
    Layer3State.ARRIVING: "panel.state.arriving",
}

# Layer 2 badge read → i18n key for the line-2 "state:" value (the game's own
# on-screen motion indicator). Anything not in the map → panel.badge.unknown.
_BADGE_KEY = {
    "MOVING": "panel.badge.moving",
    "STOPPED": "panel.badge.stopped",
    "PASSING": "panel.badge.passing",
}

# Auto-fire type (driver-internal name) → i18n key for the auto-played chip.
# Public phrasing maps departure→"Next stop", etc. (translations_app.json).
_FIRE_KEY = {
    "departure": "panel.fire.departure",
    "arrival": "panel.fire.arrival",
    "at-station": "panel.fire.atstation",
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

# Station-name font. Chrome labels render in the per-language chrome font via
# i18n.font(); but station names come from route data as Japanese kanji, which
# the en chrome face (HelveticaNeue, Latin-only) can't render. So names always
# render in this CJK-capable face regardless of UI language — the two-font split
# on line 1. ShinGoPr6N covers JP + Traditional Chinese; zh_CN names lean on the
# chrome path only for chrome labels, not names.
_name_font: Optional[pygame.font.Font] = None


def _get_name_font() -> pygame.font.Font:
    global _name_font
    if _name_font is None:
        _name_font = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 14)
    return _name_font


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
# (24px) that only line 1 of the panel content sits beside them; line 2
# reclaims full panel width below.
_BTN_X0 = 8
_BTN_Y0 = 4
_BTN_HEIGHT = 24
_BTN_GAP = 6


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
    `paused=True` swaps to a play triangle. Label uses the per-language chrome
    font so translated button text renders in the right script."""
    label_font = i18n.font(12)
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
    label = i18n.t("panel.btn.resume") if paused else i18n.t("panel.btn.pause")
    _pause_button_rect = _draw_pill_button(surface, _BTN_X0, _BTN_Y0, color, "pause", label, paused=paused)
    return _pause_button_rect


def _draw_report_button(surface: pygame.Surface, x: int) -> pygame.Rect:
    """Pill button drawn to the right of Pause. Renders the drive's speed-curve HTML report."""
    global _report_button_rect
    _report_button_rect = _draw_pill_button(surface, x, _BTN_Y0, (52, 116, 145), "report", i18n.t("panel.btn.save_curve"))
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
    # Two fonts. CONTRACT: chrome labels render in the per-language chrome font
    # (i18n.font — HelveticaNeue/ShinGo/Noto by locale); station names render in
    # the CJK name font because the en chrome face is Latin-only and would tofu
    # the kanji. Never SysFont, never bare Path() — both route through
    # app_paths.project_root() (i18n.font internally, _get_name_font here).
    chrome = i18n.font(14)
    name_font = _get_name_font()
    surface.fill(_PANEL_BG)
    paused = bool(status.get("paused", False))

    # Always-on top-left button strip — Pause first, Report second. Pills size
    # to fit their labels, so we render Pause first and place Report immediately
    # to its right.
    pause_rect = _draw_pause_button(surface, paused)
    report_rect = _draw_report_button(surface, pause_rect.right + _BTN_GAP)
    line1_x = report_rect.right + 14

    # 2-row layout, grouped by meaning. Line 1 (beside the buttons) = the
    # driver's interpretation + action; line 2 (full panel width below the 24px
    # button strip) = the raw OCR reads. The panel is 730px wide, so width is
    # cheap and vertical height is the constraint we're optimizing.
    y1, y2 = 8, 32

    if not status or all(k == "paused" for k in status):
        _blit_text(surface, chrome, i18n.t("panel.waiting"), (line1_x, y1), _TEXT_GRAY)
        return

    gap = 10  # px gap between chunks on the same line

    # Badge is read up front: it's a raw read (rendered on line 2), but line 1's
    # segment phrasing also keys off it (STOPPED → station name, PASSING → "(Passing)"),
    # so both groups need it.
    badge = status.get("badge")
    badge_diff = status.get("badge_diff")

    # ── Line 1 (beside buttons): the driver's INTERPRETATION + action — what the
    # OCR *thinks* the game is doing (inferred state + segment), how many PAs have
    # played, and the auto-played chip. Deliberately split from the raw reads on
    # line 2 so "what we believe" and "what we measured" don't blur together.
    # Header tints orange when paused so the frozen-OCR state is unmistakable.
    header_color = _COLOR_ORANGE if paused else _TEXT_WHITE
    header_label = i18n.t("panel.header_paused") if paused else i18n.t("panel.header")
    inferred = status.get("inferred_state", Layer3State.UNKNOWN)
    state_key = _STATE_KEY.get(inferred)
    state_word = i18n.t(state_key) if state_key else "—"
    seg_start = status.get("segment_start_stop")
    # Played count: cnt_pa is 0-indexed and post-play (cnt_pa=0 means pa[0] has
    # been played). Displayed value is `cnt_pa+1` of total available PAs at this
    # stop. Start station (no pa) shows "—".
    pa_total = len(stops[sim_state.curr_stop].get("pa", [])) if 0 <= sim_state.curr_stop < len(stops) else 0
    played_str = f"{sim_state.cnt_pa + 1}/{pa_total}" if pa_total > 0 else "—"

    # Baseline-align line 1: it mixes the chrome font and the CJK name font,
    # whose ascents differ (most visibly zh_CN Noto vs ShinGo). Top-aligning both
    # at y1 makes the station names sit off from the chrome chunks. Place each
    # chunk by its own ascent against a shared baseline so the text lines up.
    # (zh_HK happens to look fine either way — its chrome font *is* ShinGo.)
    base1 = y1 + max(chrome.get_ascent(), name_font.get_ascent())
    yc = base1 - chrome.get_ascent()  # top-y for chrome-font chunks
    yn = base1 - name_font.get_ascent()  # top-y for name-font chunks

    x = line1_x
    x = _blit_text(surface, chrome, header_label, (x, yc), header_color) + gap + 4
    # Segment: station names in the CJK name font, connectors + state word in the
    # chrome font (two-font split). `·` / `→` come from the name font too — the en
    # chrome face lacks the arrow glyph.
    if badge == "STOPPED" and 0 <= sim_state.curr_stop < len(stops):
        location = stops[sim_state.curr_stop].get("name", "?")
        x = _blit_text(surface, name_font, f"{location}  ·  ", (x, yn), _TEXT_WHITE)
        x = _blit_text(surface, chrome, state_word, (x, yc), _TEXT_WHITE) + gap
    elif seg_start is not None and 0 <= seg_start < len(stops) and 0 <= sim_state.curr_stop < len(stops):
        from_name = stops[seg_start].get("name", "?")
        to_name = stops[sim_state.curr_stop].get("name", "?")
        if seg_start == sim_state.curr_stop:
            # Parked while OCR sees the game in transit (re-entry / re-aligning):
            # segment collapses to the single station — no "A → A".
            x = _blit_text(surface, name_font, f"{from_name}  ·  ", (x, yn), _TEXT_WHITE)
        else:
            x = _blit_text(surface, name_font, f"{from_name} → {to_name}  ·  ", (x, yn), _TEXT_WHITE)
        x = _blit_text(surface, chrome, state_word, (x, yc), _TEXT_WHITE) + gap
    else:
        x = _blit_text(surface, chrome, state_word, (x, yc), _TEXT_WHITE) + gap

    # Line-1 tail: the auto-played chip OR the steady-state "Played: N/M" — never
    # both. The chip is visible for 3s after a successful fire (skipped fires only
    # print to console; only pending_next_pa sets land here) and supersedes the
    # Played count for that window, because the line is width-bound and they'd
    # otherwise collide past the panel edge. ("(Passing)" was dropped from this
    # line — line 2 already shows `state: Passing`.)
    # Auto-played chip text, WITHOUT the leading dot — the ● is rendered
    # separately via the name font (see below).
    chip_text = None
    last_fire = status.get("last_fire")
    if last_fire is not None and isinstance(last_fire, dict):
        if time.time() - last_fire.get("ts", 0) < 3.0:
            fire_key = _FIRE_KEY.get(last_fire.get("type") or "")
            fire_label = i18n.t(fire_key) if fire_key else last_fire.get("type", "?")
            chip_text = f"{i18n.t('panel.autoplayed')} {fire_label}"

    # Tail precedence: re-aligning (amber) > auto-played chip (green) > Played
    # count (gray). Re-aligning means the app is parked but OCR sees the game in
    # transit and is waiting for a second agreeing probe before silent-advancing
    # — it supersedes both because it's the live transitional signal and the line
    # is width-bound. (Re-aligning and the green chip never co-occur: re-entry
    # stands down once a live fire sets pending_next_pa.)
    #
    # The ● transient-chip bullet renders via the NAME font, not chrome: the en
    # chrome face (HelveticaNeue) is Latin-only and lacks U+25CF, so a chrome ●
    # blanks in en — same reason the segment → arrow routes through the name
    # font. Baseline-align the name-font dot (yn) with the chrome label (yc).
    if status.get("reentry_pending") is not None:
        xx = _blit_text(surface, name_font, "  ●  ", (x, yn), _COLOR_ORANGE)
        _blit_text(surface, chrome, i18n.t("panel.realigning"), (xx, yc), _COLOR_ORANGE)
    elif chip_text is not None:
        xx = _blit_text(surface, name_font, "  ●  ", (x, yn), _COLOR_GREEN)
        _blit_text(surface, chrome, chip_text, (xx, yc), _COLOR_GREEN)
    else:
        _blit_text(surface, chrome, f"·  {i18n.t('panel.played')} {played_str}", (x, yc), _TEXT_GRAY)

    # ── Line 2 (full width below buttons): the raw OCR READS — the game's own
    # motion state ("state:") + match-diff first, then the numeric cells (speed /
    # limit / distance / stopping position). These are what the templates actually
    # matched this frame; line 1 is the interpretation derived from them. All
    # chrome font — no station names on this line. Distance and stopping position
    # are independent fields so the user can see the in-transit distance and the
    # platform-arrival offset even when only one is populated.
    s_val = status.get("speed")
    s_score = status.get("speed_score")
    d_val = status.get("distance")
    d_score = status.get("distance_score")
    offset_val = status.get("stopping_offset_cm")
    offset_score = status.get("stopping_offset_score")
    sl_val = status.get("speed_limit")
    sl_score = status.get("speed_limit_score")
    badge_key = _BADGE_KEY.get(badge or "")
    badge_label = i18n.t(badge_key) if badge_key else i18n.t("panel.badge.unknown")
    x = 8
    # "OCR" stays unlocalized on purpose — it's the technical term the user has
    # already seeded with end users (kept identical across en/zh_HK/zh_CN), so it
    # leads line 2 as a literal rather than an i18n key.
    x = _blit_text(surface, chrome, "OCR", (x, y2), _TEXT_WHITE) + gap + 4
    x = _blit_text(surface, chrome, i18n.t("panel.badge"), (x, y2), _TEXT_GRAY) + 6
    x = _blit_text(surface, chrome, badge_label, (x, y2), _badge_color(badge_diff)) + gap
    if badge_diff is not None:
        x = _blit_text(surface, chrome, f"(d={badge_diff:.1f})", (x, y2), _TEXT_GRAY) + gap
    x = _blit_text(surface, chrome, i18n.t("panel.speed"), (x, y2), _TEXT_GRAY) + 6
    spd_str = f"{s_val:>3} km/h" if s_val is not None else " -- km/h"
    x = _blit_text(surface, chrome, spd_str, (x, y2), _conf_color(s_score if s_val is not None else None)) + gap
    if sl_val is not None:
        x = _blit_text(surface, chrome, i18n.t("panel.limit"), (x, y2), _TEXT_GRAY) + 6
        x = _blit_text(surface, chrome, f"{sl_val} km/h", (x, y2), _conf_color(sl_score)) + gap
    x = _blit_text(surface, chrome, i18n.t("panel.distance"), (x, y2), _TEXT_GRAY) + 6
    if d_val is not None:
        x = _blit_text(surface, chrome, f"{d_val:>5}m", (x, y2), _conf_color(d_score)) + gap
    else:
        x = _blit_text(surface, chrome, "  -- m", (x, y2), _TEXT_GRAY) + gap
    # Stopping position only renders when a reading is present (the cell
    # briefly populates after arrival). Brightness-pulse flash when shown so it
    # pops against the steady-state fields; nothing rendered otherwise.
    if offset_val is not None:
        x = _blit_text(surface, chrome, i18n.t("panel.stop_offset"), (x, y2), _TEXT_GRAY) + 6
        flash_on = (pygame.time.get_ticks() // 350) % 2 == 0
        r, g, b = _conf_color(offset_score)
        offset_color: tuple[int, int, int] = (r, g, b) if flash_on else (int(r * 0.4), int(g * 0.4), int(b * 0.4))
        _blit_text(surface, chrome, f"{offset_val:+d} cm", (x, y2), offset_color)


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

    Per-segment observed-flags (`departure_observed` / `arrival_observed` /
    `at_station_observed`): record whether each trigger condition has been
    observed in the current segment, reset on BADGE_STOPPED→(MOVING|PASSING).
    These are **Layer 3 observation memory** — they feed `inferred_state()` so the
    panel reflects what the *game* is doing. They do NOT gate PA fires: fire gating
    reads Layer 1's app sub-state directly in `AutoDriver._fire_*` (the Layer 1 ↔
    Layer 2 coupling). The two roles share one flag-set but stay conceptually
    distinct — see auto_input/README.md § "State machine layering". Within
    `update()` the flags still short-circuit duplicate FIRE_* emissions per segment
    (OCR-misread debounce); the app-sub-state guard is the authoritative gate.

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
    # Re-entry consensus latch: the target ("1A"/"1B") resolved on the PREVIOUS
    # cycle, awaiting a second agreeing probe before _maybe_reentry commits the
    # silent-advance. None = no pending re-entry. Surfaced to the panel as the
    # "re-aligning…" indicator. See auto_input/README.md § "Re-entry".
    reentry_latch: Optional[str] = None

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

        # Initial segment label (display/log only); reconciled from app state
        # every cycle below — see the coupling note in the capture loop.
        self._segment_start_stop = self._segment_from()

        try:
            while not self._stop_event.is_set():
                try:
                    if self.paused:
                        # Mark status so panel renders the indicator. Preserve last OCR
                        # values — only the paused flag flips so the panel doesn't blank.
                        self.sim.auto_input_status = {**self.sim.auto_input_status, "paused": True}
                        self._stop_event.wait(self.interval_s)
                        continue
                    # Click-jump re-anchor (Layer 1 authoritative → Layer 2 belief).
                    # The user clicked a station on the lower LCD; App jumped to
                    # STOPPING@curr_stop (jump_to_stop). Mirror that into Layer 2 so
                    # subsequent fires track from the new position. Consumed before the
                    # fresh OCR read so the re-anchored prev_badge="STOPPED" is in place
                    # when detector.update() runs this cycle. Re-anchor has no failing
                    # preconditions, so consume immediately.
                    # Scope: resets OCR memory for the parked case (Layer 3
                    # STOPPED/IDLE). A click-jump mid-transit (Layer 3 driving) is
                    # then caught by _maybe_reentry below — the re-anchor zeroes the
                    # memory, re-entry silent-advances Layer 1 up to the game.
                    if self.sim.click_jump_pending:
                        self.sim.click_jump_pending = False
                        self._reanchor_to_app()
                    # Coupling (Layer 1 → Layer 2): Layer 2 is a pure function of
                    # Layer 1, computed not stored. Here we keep the displayed
                    # segment label in sync with the app's authoritative curr_stop
                    # every cycle, so the panel's "A → B" tracks any advance — auto
                    # fire, manual PageDown, or click-jump. Fire gating reads app
                    # sub-state directly in _fire_* (the other half of the coupling).
                    # The detector's per-segment observed-flags are deliberately
                    # NOT touched here: they stay OCR-driven so Layer 3 keeps
                    # observing the game, not the app. See auto_input/README.md
                    # § "State machine layering".
                    self._segment_start_stop = self._segment_from()
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
                        "reentry_pending": self._detector.reentry_latch,
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
                    # Re-entry (Layer 3 → Layer 2/1 catch-up) runs AFTER the
                    # event loop so it reads the cross-reject-guarded badge and
                    # stands down if a normal fire already succeeded this cycle.
                    self._maybe_reentry(s_val, d_val)

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
            print("          [AD] >>> BADGE STOPPED->MOVING (Layer 3 observed-flags reset)")
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

    def _maybe_reentry(self, speed: Optional[int], distance: Optional[int]) -> None:
        """Re-entry: Layer 3 → Layer 2/1 reconciliation (the catch-up path).

        Called once per cycle AFTER detector.update() + the _handle_event loop.
        Fires only when the app is parked (at_station=True ⇔ Layer 1 at 1C) but
        the game is in transit — the genuine desync (cold boot mid-drive,
        mid-transit click-jump, or OCR that missed the real events). When the app
        is already moving (1A/1B) the normal streaming flow owns it, so no-op.

        Writes ONLY a single-shot signal (`sim.pending_silent_advance`) + the
        detector's observed-flags — never AppState directly (that mutation stays
        on the main thread). The Layer 1 advance + the flag seed are one
        consistent snapshot; the coupling is read-only on Layer 1, so this does
        not cascade. See auto_input/README.md § "Re-entry (Layer 3 → Layer 2
        reconciliation)".

        Lockstep ±1: advances by one stop. There is no station-name OCR, so a
        cold boot multiple stops behind the game is NOT recoverable here — the
        user must click-jump to their platform first.

        Consensus gate: a re-entry commits only after TWO consecutive cycles
        resolve to the *same* target. Re-entry is forward-only and irreversible
        (it never retreats Layer 1), so a lone transient misread while parked
        would stick the LCD +1 ahead of reality until the user click-jumps back.
        The cost of waiting is one interval (~5s) on the genuine cases (cold
        boot, click-jump) — cheap, and the "re-aligning…" panel indicator turns
        the wait into a legible transition instead of an abrupt snap.
        """
        target = self._resolve_reentry_target(speed, distance)
        if target is None:
            # No desync this cycle (live fire landed, app moving, OCR fail, or
            # game parked) — drop any pending latch.
            self._detector.reentry_latch = None
            return
        if target != self._detector.reentry_latch:
            # First sighting, or the target changed during the wait (e.g. 1A→1B
            # as the game crossed the arrival lead) — a changed read is NOT a
            # confirmation. Latch the new target and wait one more cycle.
            self._detector.reentry_latch = target
            print(f"          [AD] >>> RE-ENTRY: re-aligning… (probe 1, target={target})")
            return
        # Two consecutive identical targets — commit the silent-advance.
        self._detector.reentry_latch = None
        if target == "1B":
            # 3D ARRIVING → land 1B (まもなく); seed dep + arr.
            self._detector.departure_observed = True
            self._detector.arrival_observed = True
            self.sim.pending_silent_advance = "1B"
            print(f"          [AD] >>> RE-ENTRY: silent advance to 1B (game ARRIVING, dist={distance})")
        else:  # "1A"
            # 3C CRUISING (or PASSING, dist unreliable) → land 1A; seed dep.
            self._detector.departure_observed = True
            self.sim.pending_silent_advance = "1A"
            print(f"          [AD] >>> RE-ENTRY: silent advance to 1A (game CRUISING/PASSING, speed={speed})")

    def _resolve_reentry_target(self, speed: Optional[int], distance: Optional[int]) -> Optional[str]:
        """Resolve THIS cycle's re-entry target — ``"1A"`` / ``"1B"`` / ``None``.

        Pure read: no flag mutation, no signal write. The consensus latch in
        `_maybe_reentry` owns the commit decision. Returns None whenever there is
        no genuine parked-while-game-in-transit desync to correct.
        """
        # A normal fire already succeeded this cycle (e.g. the live 3B→3C
        # departure crossing, which plays audio) — let it land; re-entry stands
        # down. This is the discriminator between the live departure (audio) and
        # a re-entry (silent): the arriving-while-parked case is NOT suppressed
        # because there _fire_arrival skips and pending_next_pa stays False.
        if self.sim.pending_next_pa:
            return None
        if not self.sim.state.at_station:
            return None  # app already moving (1A/1B) — normal flow owns it
        inferred = self._detector.inferred_state()
        if inferred in (Layer3State.UNKNOWN, Layer3State.IDLE, Layer3State.STOPPED):
            return None  # OCR fail / first cycle / game parked — no desync
        # Game in transit while app parked at 1C. Disambiguate via the guarded
        # badge (prev_badge, post cross-reject) + raw speed/distance —
        # inferred_state can't tell 3B from 3C (both read DEPARTING cold), so the
        # speed>=30 gate is what separates "still in the departure window" (3B,
        # let the normal crossing play it with audio) from "already cruising" (3C).
        badge = self._detector.prev_badge
        if badge == "MOVING" and distance is not None and distance <= self._detector.arrival_lead_m:
            return "1B"
        if (speed is not None and speed >= SPEED_DEPARTURE_KMH) or badge == "PASSING":
            return "1A"
        # MOVING, speed<30, dist>lead → 3B → no-op (normal SPEED_UP_30 path plays
        # the departure with audio when speed crosses 30).
        return None

    def _reanchor_to_app(self) -> None:
        """Reset OCR memory after a click-jump (parked case).

        A click-jump (jump_to_stop) puts App in STOPPING@curr_stop. The segment
        label and fire gating both derive from app state every cycle now, so the
        *only* thing left for click-jump to do is reset the detector's OCR memory
        so a stale pre-jump read can't fire a spurious event on the next cycle:

          - prev_badge="STOPPED"               (badge memory reflects platform)
          - prev_speed=None                    (drop stale speed so the very next
                                                 cycle can't satisfy the departure
                                                 crossing test prev_speed<30<=speed
                                                 on a transient parked-platform
                                                 speed misread; self-heals next read)

        The three observed-flags are also reset to a parked reading so Layer 3
        shows IDLE (`prev_badge=STOPPED` + `arrival_observed=False`) instead of a
        stale prior-segment state — cosmetic only; fire gating no longer reads them.

        Scope: parked case (the realistic desync correction). Mid-transit
        click-jump (game still driving) is a Layer-1↔Layer-3 desync handled by
        re-entry (_maybe_reentry) — see auto_input/README.md § "Re-entry".
        """
        target = self.sim.state.curr_stop
        print(f"          [AD] >>> CLICK-JUMP re-anchor: OCR memory reset for App STOPPING@{target}")
        self._detector.departure_observed = False
        self._detector.arrival_observed = False
        self._detector.at_station_observed = True
        self._detector.prev_badge = "STOPPED"
        self._detector.prev_speed = None

    def _fire_departure(self) -> None:
        # Coupling: departure is valid only at 1C (app parked, at_station=True) —
        # firing it advances the app off the platform into 1A. If the app already
        # left (at_station=False, by auto-fire or a manual PageDown), departure has
        # effectively happened — skip. The app sub-state IS the debounce.
        if not self.sim.state.at_station:
            print(f"          [AD] >>> SKIPPED departure fire (app not parked; curr_stop={self.sim.state.curr_stop}, already departed)")
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

    def _segment_from(self) -> int:
        """The stop the current leg departed from — display/log label only.

        Derived live from authoritative app state, per the coupling:
          - parked (1C, `at_station=True`)  → `curr_stop`
          - in transit (1A/1B)              → the previous stopping station

        "Stopping station" detected via `stop.get("time") is not None` — the
        canonical DATA_FORMAT.md discriminator (passing stations have NO `time`
        field), matching `_build_stops_meta`'s `stops_here` test in this module.
        Routes with passing-through stops mean the previous stopping station may
        be several indices back (e.g. chuo Shinjuku → previous stop skips 大久保 /
        東中野), so we scan backward rather than assuming `curr_stop - 1`.

        NOT used by fire gating — those read app sub-state directly. This exists
        only so the panel's "A → B" label and the JSONL stay aligned with
        `curr_stop` no matter how it changed (auto-fire, manual PageDown, click-jump).
        """
        st = self.sim.state
        if st.at_station:
            return st.curr_stop
        for k in range(st.curr_stop - 1, -1, -1):
            if self.sim.stops[k].get("time") is not None:
                return k
        return st.curr_stop

    def _fire_arrival(self) -> None:
        # Coupling: arrival is valid only while the app is approaching its target
        # (at_station=False) — that target IS curr_stop, so no segment anchor is
        # needed. If still parked (1C), departure hasn't fired — premature.
        if self.sim.state.at_station:
            print(f"          [AD] >>> SKIPPED arrival fire (app parked at stop {self.sim.state.curr_stop}; departure not fired)")
            return
        curr = self.sim.state.curr_stop
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
        #
        # Coupling: valid only at 1B (app in final approach — at_station=False AND
        # cnt_pa at the last approach PA). The two guards below enforce exactly
        # that: at_station rules out 1C (already stopping); the cnt_pa check rules
        # out 1A (still on an earlier approach PA).
        if self.sim.state.at_station:
            print("          [AD] >>> SKIPPED at-station fire (sim already STOPPING)")
            return
        curr = self.sim.state.curr_stop
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

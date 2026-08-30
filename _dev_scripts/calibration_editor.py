# SPDX-License-Identifier: MIT
"""Calibration editor v1 — direct-manipulation pixel tuning for pygame LCDs.

WIP, see docs/wip/WIP_calibration_editor.md at repo root. Wired up by preview_display.py
when run with `--edit`. Single-file prototype; if it earns its keep we extract.

Reads `_TUNEABLES_*` dicts from target modules at runtime. Three states kept
distinct: baseline (source values at launch, `_originals`), edits (`_edited_keys`
— the (dict, key) pairs the user actually changed), and live (the in-place
mutated dict the renderer reads each frame). Ctrl+S writes back ONLY edited keys
(value-swap, type-guarded to int/float/tuple/str) — every other key keeps its
source text. ESC discards the in-memory mutations; source reloads next launch.
No hidden state is persisted between sessions (the old scratch-resume that
silently leaked one element's state into source on save was removed 2026-06-16).

Interaction:
    Click any registered element on upper LCD (dest / clock / prefix /
                                   station today) → focus element, sidebar
                                   shows its tuneable dicts (region rect +
                                   per-mode internals).
    ↑/↓                          → cycle focused param row.
    ←/→                          → nudge value ±1 (or cycle candidate on
                                   the pinned `<ELEMENT>.value` row).
    Shift+←/→                    → nudge ±10.
    Ctrl+S                       → write back to source.
    V                            → cycle the active lower-LCD view. Lower
                                   elements are only clickable in their own
                                   view (the route bar and the 5-station
                                   markers share the same rect), so this is
                                   how you reach one that isn't showing.
    ESC                          → quit edit mode.
"""

from __future__ import annotations

import ast
import importlib
import json
import math
import re
from pathlib import Path
from typing import Optional

import pygame

from app_paths import project_root

# ── Registry of editable elements ──────────────────────────────────────
# Add an element here when its draw method has been refactored to a
# module-level `_TUNEABLES_*` dict and a hit-test rect exists.
#
# Schema: element_id → {
#     "rect_module": "displays.train_models.x.upper_lcd",
#     "rect_attr": "DEST_RECT",
#     "dicts": [(module_path, dict_name), ...],
#     "target": "upper" | "lower",  # which LCD the element lives on
#                                   # (drives the left-column render in
#                                   # preview_display: upper = active-mode
#                                   # stack; lower = full LCD A. Panel is
#                                   # always on the right half.)
#     "view": "full" | "eight" | "transfer",   # target="lower" ONLY
# }
#
# ── `view` — why lower elements need it ────────────────────────────────
# The lower LCD shows one of several VIEWS in the same screen region, so two
# elements in different views have overlapping hit-test rects: the route bar
# (full-route view) and the 5-station markers both own the whole lower area.
# A static rect therefore cannot disambiguate them — whichever is registered
# first swallows every click, which is why no full-route element could be
# registered at all before this dispatch existed.
#
# Resolution: each lower element declares the view it lives in, the editor
# tracks one active lower view (`_active_lower_view`, cycled with V and seeded
# from `--lower-view`), and hit-testing + handle drawing only consider elements
# whose view matches. Upper elements carry no `view` and are always live.
# `preview_display._run_edit_loop` syncs the sim's lower slot from the active
# view each frame, so pressing V actually re-renders the lower LCD.
_REGISTRY = {
    "dest": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "DEST_RECT",
        "target": "upper",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_DEST_KANJI"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_DEST_ENGLISH"),
        ],
    },
    "clock": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "CLOCK_RECT",
        "target": "upper",
        "dicts": [
            # Region-level: position + size of CLOCK_RECT itself. draw_clock
            # syncs CLOCK_RECT from this dict each frame so editor nudges
            # land immediately. Pattern pioneer for region-level tuneables.
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_CLOCK_RECT"),
            # Per-element internal layout (text y within CLOCK_RECT, font size).
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_CLOCK"),
        ],
    },
    "prefix": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "PREFIX_RECT",
        "target": "upper",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PREFIX_RECT"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PREFIX_KANJI"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PREFIX_ENGLISH"),
        ],
    },
    "station": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "STATION_RECT",
        "target": "upper",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_STATION_RECT"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_STATION_KANJI"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_STATION_ENGLISH"),
        ],
    },
    "badge": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "BADGE_RECT",
        "target": "upper",
        "dicts": [
            # Region-level: position + size of the station-code badge clip rect
            # (spans the framed square + optional code_3 band). _draw_station_
            # code_badge syncs BADGE_RECT + reads badge_x/badge_w from this dict.
            # Internal params (ring/font sizes) stay method-local — convert
            # lazily per conventions.md § UI code style when next tuned.
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_BADGE_RECT"),
        ],
    },
    "pa_hint": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "PA_HINT_RECT",
        "target": "upper",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PA_HINT_RECT"),
        ],
    },
    "transfer_panel": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.lower_lcd",
        "rect_attr": "TP_RECT",
        "target": "lower",
        # The INLINE left column of the 5-station view — not the standalone
        # TRANSFER slot. Lives in the "eight" view accordingly.
        "view": "eight",
        "dicts": [
            ("displays.train_models.e235_0.lower_lcd", "_TUNEABLES_TRANSFER_PANEL"),
        ],
        # Four draggable handles: tp0 (tp0_x/tp0_y) = panel top-left anchor
        # (header → subtitle → list flow down from it); tp1/tp2/tp3 = the three
        # control points of the panel's curved right edge (piecewise-linear by y;
        # lower rows get more width as the band opens out). Every other tp_* key
        # is a nudge-only scalar (sizes / gaps / pitch). Registered BEFORE
        # five_station so its narrower left-column TP_RECT wins the click
        # hit-test; arc/marker clicks (x ≥ 224) fall to five_station. tp1/tp2/tp3
        # may sit right of TP_RECT but are grabbable once the panel is focused.
        # NOT per-station — global params.
        "waypoints": {
            "dict": ("displays.train_models.e235_0.lower_lcd", "_TUNEABLES_TRANSFER_PANEL"),
            "prefixes": ["tp"],
            "per_station": False,
        },
    },
    "five_station": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.lower_lcd",
        "rect_attr": "ARC_RECT",
        "target": "lower",
        "view": "eight",
        "dicts": [
            ("displays.train_models.e235_0.lower_lcd", "_TUNEABLES_FIVE_STATION"),
        ],
        # Draggable handles: m<N>=circle markers (white; m0 = the station-0
        # dot), g<N>=badge+name group anchors (cyan), v<N>=the station-0
        # free-polygon vertices (red), a<N>=approaching arrow tip (yellow;
        # a0_x/a0_y only drawn in APPROACHING state). All absolute x/y pairs.
        # Grabbing an m/g handle selects station N → the panel filters to that
        # station's keys (`^[mg]N_`); v/a grabs DON'T re-select (vertices +
        # arrow are not stations — `select_prefixes` scopes the per-station
        # reselection).
        "waypoints": {
            "dict": ("displays.train_models.e235_0.lower_lcd", "_TUNEABLES_FIVE_STATION"),
            "prefixes": ["m", "g", "v", "a"],
            "per_station": True,
            "select_prefixes": ["m", "g"],
        },
        # draw_state: maps prefix or specific key → which at_station value draws it.
        # "stopping"   = drawn only when state.at_station is True
        # "approaching" = drawn only when state.at_station is False
        # Absent entries = always drawn (m, g, m0_x, m0_y, m1..m4, g* all absent).
        "draw_state": {
            "v": "stopping",  # pentagon vertex handles
            "a": "approaching",  # arrow handle + params
            "m0_dr": "stopping",  # pentagon dot radius (sidebar scalar)
            "m0_circle_r": "approaching",
            "m0_circle_inset": "approaching",
            "m0_ts": "approaching",
        },
    },
    "full_route": {
        "model": "e235_0",
        "rect_module": "displays.train_models.e235_0.lower_lcd",
        "rect_attr": "FULL_ROUTE_RECT",
        "target": "lower",
        "view": "full",
        "dicts": [
            ("displays.train_models.e235_0.lower_lcd", "_TUNEABLES_FULL_ROUTE"),
        ],
        # The route bar's track geometry, shared by the circular racetrack
        # (Yamanote) and the open horseshoe that subclasses it — so which one
        # you are looking at is decided by the loaded route, not by the editor.
        # No draggable handles: every key is a scalar the whole band derives
        # from, and there is no per-station position to grab (stops are placed
        # BY this geometry, not alongside it).
        #
        # Nudging here re-runs _build_positions via the renderer's
        # _resync_tuneables — see its CONTRACT block in e235_0/lower_lcd.py.
    },
    # ---- E233-0 (中央線快速) ----
    # Every BUILT element is registered. Only the car number is absent, and it is
    # absent from the renderer too (WIP § 8.3 — no data source). Registering IS
    # the wiring step (`docs/DISPLAY.md` § "Specifying a new display" step 6), so
    # an element that is drawn but unregistered can only be tuned by hand-editing
    # the module — which is the sandbox drift the editor exists to make
    # impossible. Six of these seven were left out while the upper band was being
    # built one element at a time; the renderer half was already done for the
    # plate, badge and clock, which sync their rects from their dicts each frame.
    "train_type": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "TRAIN_TYPE_RECT",
        "target": "upper",
        "dicts": [
            ("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_TRAIN_TYPE"),
        ],
        # No draggable handles: the block is four fixed slots and every key is a
        # scalar the grid derives from — there is no per-character position to
        # grab. `font_size` is picked up by the renderer's _sync_type_font,
        # which rebuilds the font when it changes (a size is part of the atlas
        # key, so it cannot just be read per frame).
    },
    # One entry per element, matching how the author tunes them — element by
    # element, so a nudge to the badge does not scroll past the plate's keys.
    "e233_destination": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "DESTINATION_RECT",
        "target": "upper",
        "dicts": [("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_DESTINATION")],
    },
    "e233_station_plate": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "STATION_PLATE_RECT",
        "target": "upper",
        "dicts": [("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_STATION_PLATE")],
        # The plate syncs STATION_PLATE_RECT from its own dict every frame, so a
        # size nudge moves the hit-test with the drawing.
    },
    "e233_station_badge": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "BADGE_RECT",
        "target": "upper",
        "dicts": [("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_STATION_BADGE")],
    },
    "e233_station_name": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "STATION_PLATE_RECT",
        "target": "upper",
        "dicts": [("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_STATION_NAME")],
        # Shares the PLATE's rect deliberately: the name has no box of its own —
        # it is a span INSIDE the plate (WIP § 8.5), so the plate's bounds are the
        # region to letterbox the reference into.
    },
    "e233_prefix": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "PREFIX_RECT",
        "target": "upper",
        "dicts": [("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_PREFIX")],
    },
    "e233_clock": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.upper_lcd",
        "rect_attr": "CLOCK_RECT",
        "target": "upper",
        "dicts": [("displays.train_models.e233_0.upper_lcd", "_TUNEABLES_CLOCK")],
    },
    "e233_full_route": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.lower_lcd",
        "rect_attr": "FULL_ROUTE_RECT",
        "target": "lower",
        "view": "full",
        "dicts": [
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_FULL_ROUTE"),
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_FULL_ROUTE_MARKS"),
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_FULL_ROUTE_NAMES"),
        ],
        # Three dicts rather than one: the bars' geometry, the marks that sit ON
        # them, and the name stack above them are three refinement passes, and
        # keeping them apart is what lets one be nudged without scrolling past
        # the others. Every key is read per frame, so no resync hook is needed —
        # except the two font sizes, which rebuild through the renderer's own
        # per-size font cache.
        #
        # A separate key from e235_0's `full_route`: the rects mean different
        # canvases, and the editor filters on `model`.
    },
    "e233_six_station": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.lower_lcd",
        "rect_attr": "SIX_STATION_RECT",
        "target": "lower",
        "view": "eight",
        "dicts": [
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_SIX_STATION"),
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_SIX_STATION_MARKS"),
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_SIX_STATION_NAMES"),
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_SIX_STATION_TRANSFERS"),
            ("displays.train_models.e233_0.lower_lcd", "_TUNEABLES_SIX_STATION_SKIP"),
        ],
        # Split the same three ways as the full route's, for the same reason.
        # `view: "eight"` because the slot is "the zoomed view" rather than a
        # station count — E235-0's 5-station renderer owns the same slot.
    },
    "e233_transfer": {
        "model": "e233_0",
        "rect_module": "displays.train_models.e233_0.transfer_info",
        "rect_attr": "TRANSFER_VIEW_RECT",
        "target": "lower",
        "view": "transfer",
        "dicts": [
            ("displays.train_models.e233_0.transfer_info", "_TUNEABLES_TRANSFER_VIEW"),
        ],
        # ONE dict, unlike the six-station view's five: this view has a banner
        # and a repeated row and nothing else, so there is no element to split
        # the tuneables between. Drive it at a two-entry stop (八王子, the
        # reference) for the calibrated case and at 新宿 for the column wrap.
    },
}


# ── State ──────────────────────────────────────────────────────────────

_focused_element: Optional[str] = None  # e.g. "dest"
# Which lower-LCD view is live. Gates hit-testing + handles for every element
# carrying a `view` field, and preview_display syncs the sim's lower slot from
# it each frame. Seeded from --lower-view, cycled with V. See the `view` note
# in the _REGISTRY header for why lower elements need this at all.
_active_lower_view: str = "eight"
# For per-station elements (five_station): which station the panel shows.
# Set on focus (0) and when a station's handle is grabbed. None = no filter.
_selected_station: Optional[int] = None
_focused_row: int = 0  # index into the flattened param list of focused element
_param_rows: list = []  # cached flat list of editable rows for focused element
_should_quit: bool = False
# Source-file snapshot at launch — captured BEFORE scratch-restore mutates
# dicts. Drives modified-vs-original display + R reset. Keyed by qualified
# dict name → key → original value.
_originals: dict = {}
# Sidebar scroll state — top row index visible. Auto-tracks focused row so
# selection never lives off-screen. Mousewheel + PgUp/PgDn also move it.
_scroll_offset: int = 0
# Per-element candidate cycler state. Populated by _on_click when an
# element has a "cycler" entry in _REGISTRY (dest / prefix / station today).
# Dispatch is element-agnostic through _cycle_candidate / _reset_candidate.
# element_id → dict of: "candidates": list, "idx": int, "original": any.
_candidate_state: dict = {}

# Drag state for waypoint handles (five_station m/g/v/a + transfer-panel tp). Set
# on MOUSEBUTTONDOWN over a handle; cleared on MOUSEBUTTONUP. While set,
# MOUSEMOTION updates the underlying `<prefix><idx>_x` / `_y` values.
_dragging_waypoint: Optional[tuple] = None  # (prefix, idx) of dragged handle, or None
# Grab offset (wp - mouse) captured at mousedown so dragging is relative —
# without it, the generous hit radius makes every grab snap the waypoint to
# the click point (position drifts just by clicking a handle).
_drag_grab_offset: tuple = (0, 0)
# `H` toggles handle visibility — even hollow rings sit on top of the element
# being judged; hide them for a clean look at the render. Hidden handles are
# also inert to grabs (click falls through to element focus).
_handles_visible: bool = True
_HANDLE_HIT_R = 12  # Figma-style generous hit radius (px) — grab area, NOT visual
_HANDLE_ARM = 6  # crosshair arm half-length (px) — small + open-centre
_HANDLE_ARM_DRAG = 8  # crosshair arm half-length while dragging

# Reference-image overlay (--overlay flag). Set once via set_overlay() at
# launch; rendered on top of LCD A's lower-LCD area at _OVERLAY_ALPHA when
# _overlay_visible. Default placement: letterbox-fit into ARC_RECT, center.
# Hold Alt and drag → reposition. Hold Alt + scroll → zoom. Toggle vis: `O`.
# Offset / scale / visibility persisted to gitignored `_overlay_state.json`
# so re-launches resume the alignment from the previous session.
_overlay_surf: Optional["pygame.Surface"] = None
_overlay_visible: bool = True
_OVERLAY_ALPHA = 128  # 0 = invisible, 255 = opaque
_overlay_offset_x: int = 0
_overlay_offset_y: int = 0
_overlay_scale: float = 1.0
_overlay_dragging: bool = False
_overlay_drag_mouse_start: Optional[tuple] = None
_overlay_drag_offset_start: Optional[tuple] = None

_OVERLAY_STATE_PATH = project_root() / "_overlay_state.json"
_LOCKS_PATH = project_root() / "_editor_locks.json"

# Per-element drag locks (K toggles the focused element). A locked element's
# handles render dimmed and are inert to grabs — stops an accidental drag from
# being swept into the next Ctrl+S. Persisted to _LOCKS_PATH across launches
# (a finalized element stays locked). Keyboard nudge is unaffected.
_locked_elements: set = set()

# Edit model (three states kept distinct, per the 2026-06-16 refactor):
#   baseline = source values at launch, captured in `_originals` BEFORE anything
#              else (immutable reference; what reset / "untouched" mean).
#   edits    = `_edited_keys` — the (dqn, key) pairs the user explicitly changed
#              this session. A key enters on nudge/drag, LEAVES when its value
#              returns to baseline (nudged/reset back). Nothing else adds to it.
#   live     = the in-place-mutated module dict the renderer reads each frame.
# Ctrl+S writes back ONLY keys in `_edited_keys` — every other key keeps its
# exact source text, so it CANNOT drift. No silent scratch-restore feeds the
# live state at launch, so a stale scratch can't leak into source either.
_edited_keys: set = set()  # of (dqn, key)

# Live sim reference — stored in enter_edit_mode so gating helpers can read
# state.at_station without threading sim through every internal call.
_edit_sim = None

_sidebar_font: Optional[pygame.font.Font] = None
_sidebar_header_font: Optional[pygame.font.Font] = None
_sidebar_hint_font: Optional[pygame.font.Font] = None


# ── Public API ─────────────────────────────────────────────────────────


def enter_edit_mode(sim) -> None:
    """Snapshot baseline from source, load locks, print help.

    Baseline (`_originals`) is the source file's values at launch — the live
    module dicts ARE the source at this point (no scratch merge), so baseline
    == live == source on entry. The editor never silently restores a prior
    session's scratch over the source (that was the drift vector); save writes
    only explicitly-edited keys. Quit discards in-memory mutations untouched.
    """
    global _edit_sim
    _edit_sim = sim
    _snapshot_originals()
    _load_locks()
    # Enable held-key repeats — nudge / scroll / row-cycle all feel snappier
    # when you can hold instead of mash. 400 ms initial delay, ~20 Hz repeat.
    pygame.key.set_repeat(400, 50)
    print("[calibration] Edit mode ON. Click DEST_RECT on upper LCD to focus.")
    print("[calibration] Up/Down select  Left/Right nudge  Shift+Arrow +-10  R reset  Ctrl+S save  ESC quit")
    print(
        "[calibration] M=cycle mode (kanji/furigana/english)  L=sync mode to focused dict"
        "  [=prev stop  ]=next stop  H=toggle drag handles  K=lock/unlock focused element"
    )
    # ASCII only, like the banner lines above it — a dev console on this
    # project is cp1252 and turns an em-dash into a replacement char.
    views = _lower_views()
    if views:
        print(f"[calibration] V=cycle lower view ({' / '.join(views)})  now: {_active_lower_view}")
    else:
        # Naming a view the loaded model has no element in would read as a
        # supported view that simply refuses to focus anything.
        print("[calibration] V=cycle lower view: this model has no registered lower elements yet")


def _snapshot_originals() -> None:
    """Shallow-copy every registered dict's current state into _originals."""
    global _originals
    _originals = {}
    for element_id, cfg in _REGISTRY.items():
        for mod_path, dict_name in cfg["dicts"]:
            mod = importlib.import_module(mod_path)
            d = getattr(mod, dict_name)
            qname = f"{mod_path}.{dict_name}"
            _originals[qname] = dict(d)


def should_quit() -> bool:
    return _should_quit


def set_overlay(surf) -> None:
    """Install a reference image to render over the lower LCD during edit.

    Called once by preview_display.py after pygame.display.set_mode (so
    convert_alpha() has a display). Loads persisted offset/scale/visibility
    from `_overlay_state.json` if present, so re-launch resumes alignment.
    Toggle visibility in-editor with `O`.
    """
    global _overlay_surf
    _overlay_surf = surf
    _load_overlay_state()


def _save_overlay_state() -> None:
    """Persist current overlay offset/scale/visibility to gitignored JSON."""
    if _overlay_surf is None:
        return
    try:
        _OVERLAY_STATE_PATH.write_text(
            json.dumps(
                {
                    "offset_x": _overlay_offset_x,
                    "offset_y": _overlay_offset_y,
                    "scale": _overlay_scale,
                    "visible": _overlay_visible,
                }
            )
        )
    except OSError as e:
        print(f"[overlay] WARN: state save failed: {e}")


def _load_overlay_state() -> None:
    """Restore overlay offset/scale/visibility from gitignored JSON, if present."""
    global _overlay_offset_x, _overlay_offset_y, _overlay_scale, _overlay_visible
    if not _OVERLAY_STATE_PATH.exists():
        return
    try:
        data = json.loads(_OVERLAY_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[overlay] WARN: state corrupt, starting fresh: {e}")
        return
    _overlay_offset_x = int(data.get("offset_x", 0))
    _overlay_offset_y = int(data.get("offset_y", 0))
    _overlay_scale = float(data.get("scale", 1.0))
    _overlay_visible = bool(data.get("visible", True))


def _save_locks() -> None:
    """Persist locked element ids to gitignored JSON."""
    try:
        _LOCKS_PATH.write_text(json.dumps(sorted(_locked_elements)))
    except OSError as e:
        print(f"[calibration] WARN: locks save failed: {e}")


def _load_locks() -> None:
    """Restore locked element ids from gitignored JSON, if present. Drops ids
    no longer in the registry (renamed/removed element)."""
    global _locked_elements
    if not _LOCKS_PATH.exists():
        return
    try:
        data = json.loads(_LOCKS_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[calibration] WARN: locks corrupt, starting unlocked: {e}")
        return
    _locked_elements = {e for e in data if e in _REGISTRY}
    if _locked_elements:
        print(f"[calibration] Locked (restored): {', '.join(sorted(_locked_elements))}")


def get_focused_target() -> Optional[str]:
    """Return 'upper' / 'lower' for the focused element, or None.

    Drives the left-column render in preview_display._run_edit_loop: lower-LCD
    elements show the full LCD A (upper + lower); upper-LCD elements show the
    active mode stacked above a locked-ENGLISH reference copy. The param panel
    is on the right half in both cases.
    """
    if _focused_element is None:
        return None
    cfg = _REGISTRY.get(_focused_element)
    return cfg.get("target", "upper") if cfg else None


def get_active_lower_view() -> str:
    """The lower-LCD view the editor is currently working in.

    `preview_display._run_edit_loop` reads this every frame and pins the sim's
    lower slot to it, so V-cycling re-renders the lower LCD immediately.
    """
    return _active_lower_view


def set_active_lower_view(view: str) -> None:
    """Seed the active lower view (from `--lower-view`) before the loop starts.

    Ignores a view no registered element lives in — the CLI accepts views the
    editor has nothing to tune in, and silently landing there would look like
    the editor was broken (click anything, nothing focuses).
    """
    global _active_lower_view
    if view in _lower_views():
        _active_lower_view = view


def _lower_views() -> list:
    """Views that registered lower elements actually live in, in registry order.

    Derived from _REGISTRY rather than listed, so registering an element in a
    new view makes that view reachable with no second edit — a hand-kept list
    is how a view ends up unreachable while looking supported
    (principles.md § "A second implementation of a production decision drifts").
    """
    views = []
    for cfg in _REGISTRY.values():
        v = cfg.get("view")
        if v is not None and v not in views and _element_for_active_model(cfg):
            views.append(v)
    return views


_active_model: str = None


def set_active_model(key: str) -> None:
    """Bind the editor to the loaded train model.

    Registry entries are per-model — an entry's rect is in ITS model's canvas
    coordinates, so offering an e233_0 element while an e235_0 route is loaded
    would hit-test a rectangle that means nothing on screen. Called once by the
    preview harness before the edit loop.
    """
    global _active_model
    _active_model = key


def editable_models() -> list:
    """Models the registry has at least one element for, in registry order.

    Derived rather than listed, for the same reason as `_lower_views`: a
    hardcoded set is how registering an element in a new model leaves it
    unreachable while looking supported.
    """
    out = []
    for cfg in _REGISTRY.values():
        m = cfg.get("model")
        if m is not None and m not in out:
            out.append(m)
    return out


def _element_for_active_model(cfg) -> bool:
    """True when cfg's element belongs to the loaded model.

    An entry with no `model` key is model-agnostic and always passes, so the
    filter is opt-in and an un-migrated entry cannot silently disappear.
    """
    m = cfg.get("model")
    return _active_model is None or m is None or m == _active_model


def _element_reachable(cfg) -> bool:
    """True when cfg's element is drawn on screen right now — model AND view."""
    return _element_for_active_model(cfg) and _element_in_active_view(cfg)


def _element_in_active_view(cfg) -> bool:
    """True when cfg's element is reachable right now.

    Upper elements carry no `view` and are always reachable; a lower element is
    reachable only while its view is the active one.
    """
    view = cfg.get("view")
    return view is None or view == _active_lower_view


def _cycle_lower_view(sim) -> None:
    """Advance to the next lower view, dropping focus if it leaves the screen.

    Dropping focus matters: the sidebar would otherwise keep showing (and
    nudging) an element that is no longer drawn, so edits would land invisibly.
    """
    global _active_lower_view, _focused_element, _param_rows, _focused_row, _scroll_offset
    views = _lower_views()
    if not views:
        return
    try:
        idx = views.index(_active_lower_view)
    except ValueError:
        idx = -1
    _active_lower_view = views[(idx + 1) % len(views)]
    if _focused_element is not None and not _element_reachable(_REGISTRY[_focused_element]):
        _focused_element = None
        _param_rows = []
        _focused_row = 0
        _scroll_offset = 0
    focusable = [e for e, c in _REGISTRY.items() if _element_reachable(c)]
    print(f"[calibration] Lower view: {_active_lower_view}  (elements: {', '.join(focusable) or 'none'})")


def handle_event(event, sim) -> bool:
    """Dispatch a pygame event. Returns True if absorbed."""
    global _should_quit, _dragging_waypoint, _drag_grab_offset, _handles_visible, _overlay_dragging
    global _overlay_drag_mouse_start, _overlay_drag_offset_start
    global _overlay_offset_x, _overlay_offset_y, _overlay_scale
    global _overlay_visible, _selected_station
    if event.type == pygame.QUIT:
        return False  # let caller close
    alt_held = bool(pygame.key.get_mods() & pygame.KMOD_ALT)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        # Alt+click anywhere on LCD A → grab the overlay for reposition.
        # Takes priority so the user can drag the overlay even when the
        # cursor sits on a waypoint handle.
        if alt_held and _overlay_surf is not None and _overlay_visible:
            _overlay_dragging = True
            _overlay_drag_mouse_start = event.pos
            _overlay_drag_offset_start = (_overlay_offset_x, _overlay_offset_y)
            return True
        # Waypoint drag takes priority over click-to-focus when arc focused
        # and the cursor sits on a handle (generous Figma hit radius).
        wp_idx = _arc_waypoint_at_pos(event.pos)
        if wp_idx is not None:
            _dragging_waypoint = wp_idx
            # Relative drag: remember where on the handle the grab landed so
            # the waypoint doesn't snap to the click point (QOL 2026-06-12).
            for p, idx, px, py in _arc_waypoints():
                if (p, idx) == wp_idx:
                    _drag_grab_offset = (px - event.pos[0], py - event.pos[1])
                    break
            # Grabbing a station's handle selects it → panel filters to it.
            # `select_prefixes` (when present) restricts which prefixes count as
            # a station handle — vertex/dot grabs (v/d) leave the filter alone.
            wp = _focused_waypoint_cfg() or {}
            if wp.get("per_station"):
                select_prefixes = wp.get("select_prefixes")
                if select_prefixes is None or wp_idx[0] in select_prefixes:
                    _selected_station = wp_idx[1]
                    _rebuild_param_rows()
            _focus_waypoint_row(wp_idx)
            return True
        return _on_click(event.pos, sim)
    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        if _overlay_dragging:
            _overlay_dragging = False
            _overlay_drag_mouse_start = None
            _overlay_drag_offset_start = None
            _save_overlay_state()
            return True
        if _dragging_waypoint is not None:
            _dragging_waypoint = None
            _drag_grab_offset = (0, 0)
            return True
        return False
    if event.type == pygame.MOUSEMOTION:
        if _overlay_dragging and _overlay_drag_mouse_start is not None:
            dx = event.pos[0] - _overlay_drag_mouse_start[0]
            dy = event.pos[1] - _overlay_drag_mouse_start[1]
            _overlay_offset_x = _overlay_drag_offset_start[0] + dx
            _overlay_offset_y = _overlay_drag_offset_start[1] + dy
            return True
        if _dragging_waypoint is not None:
            _apply_waypoint_drag(event.pos)
            return True
        return False
    if event.type == pygame.MOUSEWHEEL:
        # Alt + wheel zooms the overlay (preserve aspect). Otherwise scroll sidebar.
        if alt_held and _overlay_surf is not None and _overlay_visible:
            step = 1.05 if event.y > 0 else (1.0 / 1.05)
            _overlay_scale = max(0.1, min(10.0, _overlay_scale * step))
            _save_overlay_state()
            return True
        _scroll_by(-event.y * 3)
        return True
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_PAGEUP:
            _scroll_by(-_visible_row_count())
            return True
        if event.key == pygame.K_PAGEDOWN:
            _scroll_by(_visible_row_count())
            return True
        if event.key == pygame.K_ESCAPE:
            _should_quit = True
            return True
        if event.key in (pygame.K_UP, pygame.K_DOWN):
            _cycle_focused_row(-1 if event.key == pygame.K_UP else 1, sim)
            return True
        if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            shift = event.mod & pygame.KMOD_SHIFT
            delta = (-1 if event.key == pygame.K_LEFT else 1) * (10 if shift else 1)
            _nudge_focused(delta, sim)
            return True
        if event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
            commit_to_source()
            return True
        if event.key == pygame.K_r:
            _reset_focused(sim)
            return True
        if event.key == pygame.K_l:
            _maybe_switch_mode(sim)
            return True
        if event.key == pygame.K_m:
            _cycle_mode(sim)
            return True
        if event.key == pygame.K_v:
            _cycle_lower_view(sim)
            return True
        if event.key == pygame.K_LEFTBRACKET:
            _cycle_stop(sim, -1)
            return True
        if event.key == pygame.K_RIGHTBRACKET:
            _cycle_stop(sim, 1)
            return True
        if event.key == pygame.K_o:
            if _overlay_surf is None:
                print("[calibration] No overlay loaded -- pass --overlay <path> to enable.")
                return True
            _overlay_visible = not _overlay_visible
            print(f"[calibration] Overlay {'ON' if _overlay_visible else 'OFF'}")
            _save_overlay_state()
            return True
        if event.key == pygame.K_h:
            _handles_visible = not _handles_visible
            print(f"[calibration] Handles {'ON' if _handles_visible else 'OFF (H to restore; grabs disabled)'}")
            return True
        if event.key == pygame.K_k:
            if _focused_element is None:
                print("[calibration] No element focused — click one first to lock.")
                return True
            if _focused_element in _locked_elements:
                _locked_elements.discard(_focused_element)
                print(f"[calibration] Unlocked: {_focused_element}")
            else:
                _locked_elements.add(_focused_element)
                print(f"[calibration] Locked: {_focused_element} (handles inert to drag; K to unlock)")
            _save_locks()
            return True
        # Alt + = / - → zoom overlay (laptop keyboard fallback for wheel).
        # Step matches the wheel: 5% per press, clamped 0.1×..10×.
        if alt_held and event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_MINUS):
            if _overlay_surf is None or not _overlay_visible:
                return True
            step = 1.05 if event.key in (pygame.K_EQUALS, pygame.K_PLUS) else (1.0 / 1.05)
            _overlay_scale = max(0.1, min(10.0, _overlay_scale * step))
            _save_overlay_state()
            return True
    return False


def _cycle_mode(sim) -> None:
    from displays.base import DisplayMode

    modes = [DisplayMode.KANJI, DisplayMode.FURIGANA, DisplayMode.ENGLISH]
    cur = sim.upper.mode_cycler.current_mode
    try:
        idx = modes.index(cur)
    except ValueError:
        idx = 0
    new_mode = modes[(idx + 1) % len(modes)]
    sim.upper.mode_cycler.current_mode = new_mode
    print(f"[calibration] Mode = {new_mode.name}")


def _cycle_stop(sim, delta: int) -> None:
    n = len(sim.stops)
    if n == 0:
        return
    new_idx = (sim.state.curr_stop + delta) % n
    sim.jump_to_stop(new_idx)
    sim.upper.set_state(sim.state.curr_stop, sim.state.cnt_pa, at_station=sim.state.at_station)
    # ASCII-only print — Windows cp1252 stdout can't encode kanji station names.
    print(f"[calibration] Stop = {sim.state.curr_stop} / {n - 1}")
    # at_station may have flipped (STOPPING ↔ APPROACHING) — rebuild so
    # draw_state gating in the sidebar reflects the new state.
    _rebuild_param_rows()


def draw_overlay(screen) -> None:
    """Indicator on LCD (focused-param visual cue) + sidebar overlay.

    The param panel always occupies the right half of the doubled window
    (x=S_WIDTH..2*S_WIDTH, full height), so the left half stays clear for the
    tuning target: for upper-LCD elements preview_display stacks the active
    mode above a locked-ENGLISH reference copy there; for lower-LCD elements it
    shows the full LCD A (upper + lower). The old "sidebar below the upper LCD"
    layout was dropped — it butted flush against the upper LCD bottom (worse as
    the upper height grows) and squeezed the panel into a short wide band.
    """
    _ensure_fonts()
    _draw_reference_overlay(screen)
    _draw_focused_indicator(screen)
    _, h = screen.get_size()
    from displays.train_models.e235_0 import S_WIDTH as _SW

    sidebar = pygame.Surface((_SW, h), pygame.SRCALPHA)
    sidebar.fill((20, 20, 30, 240))
    _draw_sidebar_contents(sidebar)
    screen.blit(sidebar, (_SW, 0))


# ── Internals ──────────────────────────────────────────────────────────


def _ensure_fonts() -> None:
    global _sidebar_font, _sidebar_header_font, _sidebar_hint_font
    if _sidebar_font is None:
        font_path = str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf")
        _sidebar_font = pygame.font.Font(font_path, 16)
        _sidebar_header_font = pygame.font.Font(font_path, 20)
        _sidebar_hint_font = pygame.font.Font(font_path, 12)


def _rebuild_param_rows() -> None:
    """Rebuild _param_rows for the focused element, honoring the per-station
    filter when one is active. Call after focus, selected-station, or stop
    changes (stop cycle can flip at_station, which changes draw_state gating).

    Clamps _focused_row — row counts differ across stations (e.g. station 0
    carries `m0_dr` etc), so a focus index valid before the rebuild can point
    past the new list."""
    global _param_rows, _focused_row
    if _focused_element is None:
        _param_rows = []
        _focused_row = 0
        return
    cfg = _REGISTRY[_focused_element]
    _param_rows = _build_param_rows(
        cfg["dicts"],
        cfg.get("waypoints"),
        _selected_station,
        draw_state=cfg.get("draw_state", {}),
    )
    if _focused_row >= len(_param_rows):
        _focused_row = max(0, len(_param_rows) - 1)
    _ensure_focused_visible()


def _on_click(pos, sim) -> bool:
    global _focused_element, _focused_row, _param_rows, _scroll_offset, _selected_station
    # Hit-test each registered element that is reachable in the active lower
    # view — without that filter the route bar and the 5-station markers, which
    # share the whole lower LCD as their rect, would shadow each other.
    for element_id, cfg in _REGISTRY.items():
        if not _element_reachable(cfg):
            continue
        rect = _resolve_rect(cfg)
        if rect is None:
            continue
        if rect.collidepoint(pos):
            _focused_element = element_id
            # Per-station elements default to showing station 0's panel.
            wp = cfg.get("waypoints") or {}
            _selected_station = 0 if wp.get("per_station") else None
            _param_rows = _build_param_rows(
                cfg["dicts"],
                cfg.get("waypoints"),
                _selected_station,
                draw_state=cfg.get("draw_state", {}),
            )
            # Auto-switch to KANJI when focusing a lower-LCD element. The
            # EIGHT slot dispatches `japanese_eight_display` only in
            # KANJI/FURIGANA modes; ENGLISH falls through to the full-route
            # renderer. Without this switch, clicking a 5-station element in
            # ENGLISH mode would hide it behind the full-route view.
            if cfg.get("target") == "lower":
                from displays.base import DisplayMode

                if sim is not None and sim.upper.mode_cycler.current_mode == DisplayMode.ENGLISH:
                    sim.upper.mode_cycler.current_mode = DisplayMode.KANJI
            # Pinned candidate-cycler row at the top when this element has
            # cycler config in _REGISTRY (see module-bottom cycler-wiring block).
            cycler = cfg.get("cycler")
            if cycler is not None:
                candidates, current = cycler["build"](sim)
                try:
                    idx = candidates.index(current)
                except ValueError:
                    idx = 0
                _candidate_state[element_id] = {
                    "candidates": candidates,
                    "idx": idx,
                    "original": current,
                }
                _param_rows.insert(0, (f"__candidate__:{element_id}", "value", None, "candidate"))
            _focused_row = 0
            _scroll_offset = 0
            print(f"[calibration] Focused element: {element_id} ({len(_param_rows)} params)")
            return True
    # Click in sidebar area: try to focus a row. Sidebar geometry depends
    # on focused element's target (upper = below upper LCD; lower = right
    # half of doubled window). _sidebar_local_y handles both layouts.
    if _focused_element is not None:
        local_y = _sidebar_local_y(pos)
        if local_y is not None:
            row_idx = _row_at_sidebar_y(local_y)
            if row_idx is not None:
                _focused_row = row_idx
                _ensure_focused_visible()
                return True
    return False


def _sidebar_local_y(pos) -> Optional[int]:
    """Convert window-coord click pos to sidebar-local y, or None if outside.

    The param panel always occupies the right half of the doubled window
    (x∈[S_WIDTH, 2*S_WIDTH], full height), so panel-local y equals window y;
    clicks on the left half (the LCDs) return None.
    """
    from displays.train_models.e235_0 import S_WIDTH as _SW

    return pos[1] if pos[0] >= _SW else None


def _resolve_rect(cfg) -> Optional[pygame.Rect]:
    try:
        mod = importlib.import_module(cfg["rect_module"])
        return getattr(mod, cfg["rect_attr"])
    except (ImportError, AttributeError):
        return None


def _build_param_rows(dict_specs, waypoints=None, station=None, draw_state=None) -> list:
    """Flatten dicts into rows. Tuple values expand into N sub-rows.

    Each row: (dict_qualified_name, param_name, sub_idx, type_tag)
    - sub_idx is None for scalars, 0..N-1 for tuple channels.
    - type_tag in {"int", "float", "tuple", "str"} drives nudge behaviour.

    Waypoint `<prefix><N>_x` / `_y` keys are SKIPPED when the element has drag
    handles — they're repositioned by dragging, so listing them just clogs the
    sidebar. (Their handles still render; only the rows are hidden.)

    draw_state: optional dict mapping prefix-or-key → "stopping"|"approaching".
    Rows whose key (or whose leading prefix stem) is gated to a state that
    doesn't match the current at_station are hidden from the sidebar.
    """
    if draw_state is None:
        draw_state = {}
    skip_re = None
    station_re = None
    prefix_re = None
    if waypoints:
        prefixes = waypoints.get("prefixes") or [waypoints["prefix"]]
        alt = "|".join(re.escape(p) for p in prefixes)
        skip_re = re.compile(rf"^({alt})\d+_[xy]$")
        # Per-station filter: show only the selected station's keys (`^[mg]N_`).
        if station is not None:
            station_re = re.compile(rf"^({alt}){station}_")
        # Build a regex that captures the prefix stem of any registered key,
        # so we can gate full key groups by prefix (e.g. "v" gates "v0_dr" etc).
        prefix_re = re.compile(rf"^({alt})\d+")
    rows = []
    for mod_path, dict_name in dict_specs:
        mod = importlib.import_module(mod_path)
        d = getattr(mod, dict_name)
        dqn = f"{mod_path}.{dict_name}"
        for key, val in d.items():
            if skip_re and skip_re.match(key):
                continue
            if station_re and not station_re.match(key):
                continue
            # Draw-state gating: check exact key first, then prefix stem.
            if draw_state:
                if not _draw_state_allows(draw_state, key):
                    continue
                if prefix_re:
                    m = prefix_re.match(key)
                    if m and not _draw_state_allows(draw_state, m.group(1)):
                        continue
            if isinstance(val, bool):
                rows.append((dqn, key, None, "bool"))  # nudging bool is just toggle
            elif isinstance(val, int):
                rows.append((dqn, key, None, "int"))
            elif isinstance(val, float):
                rows.append((dqn, key, None, "float"))
            elif isinstance(val, tuple) and all(isinstance(v, (int, float)) for v in val):
                for i in range(len(val)):
                    rows.append((dqn, key, i, "tuple"))
            elif isinstance(val, str):
                rows.append((dqn, key, None, "str"))
            else:
                rows.append((dqn, key, None, "unsupported"))
    return rows


def _row_at_sidebar_y(local_y: int) -> Optional[int]:
    # Header occupies first ~36 px; rows start at 40, each 22 px tall.
    if local_y < 40:
        return None
    visible_idx = (local_y - 40) // 22
    idx = _scroll_offset + visible_idx
    if 0 <= idx < len(_param_rows):
        return idx
    return None


def _cycle_focused_row(delta: int, sim=None) -> None:
    global _focused_row
    if not _param_rows:
        return
    _focused_row = (_focused_row + delta) % len(_param_rows)
    _ensure_focused_visible()


# Sidebar geometry — used by visible-row math + scrollbar. Kept in sync
# manually with _draw_sidebar_contents's row_top / row_h / footer reservation.
_ROW_TOP = 40
_ROW_H = 22
_FOOTER_RESERVE = 28


def _sidebar_height() -> int:
    """Sidebar pixel height = full window height (panel occupies the right
    half, full height). Read lazily to avoid circular import at module load."""
    surf = pygame.display.get_surface()
    if surf is None:
        return 420  # safe default ≈ S_HEIGHT
    return surf.get_height()


def _visible_row_count() -> int:
    avail = _sidebar_height() - _ROW_TOP - _FOOTER_RESERVE
    return max(1, avail // _ROW_H)


def _ensure_focused_visible() -> None:
    """Auto-scroll so focused row sits inside the visible window."""
    global _scroll_offset
    vis = _visible_row_count()
    if _focused_row < _scroll_offset:
        _scroll_offset = _focused_row
    elif _focused_row >= _scroll_offset + vis:
        _scroll_offset = _focused_row - vis + 1


def _scroll_by(delta: int) -> None:
    global _scroll_offset
    vis = _visible_row_count()
    max_offset = max(0, len(_param_rows) - vis)
    _scroll_offset = max(0, min(max_offset, _scroll_offset + delta))


# ── Mode-follow-focus ──────────────────────────────────────────────────
#
# Dict-name suffix → language family inference. Drives auto-switch of the
# sim's display mode so the focused dict's keys actually affect the visible
# render. KANJI ↔ FURIGANA stays a user choice (both render via the same
# Japanese-family path); ENGLISH ↔ japanese flips automatically.


def _dict_mode_family(dict_name: str):
    if "_KANJI" in dict_name or "_FURIGANA" in dict_name:
        return "japanese"
    if "_ENGLISH" in dict_name:
        return "english"
    return None  # mode-agnostic dict


def _current_mode_family(sim):
    from displays.base import DisplayMode

    cur = sim.upper.mode_cycler.current_mode
    if cur in (DisplayMode.KANJI, DisplayMode.FURIGANA):
        return "japanese"
    if cur == DisplayMode.ENGLISH:
        return "english"
    return None


def _maybe_switch_mode(sim) -> None:
    """If focused row's dict targets a different mode family than current,
    switch the sim. KANJI default for japanese family."""
    if not _param_rows or sim is None:
        return
    from displays.base import DisplayMode

    dqn, _, _, _ = _param_rows[_focused_row]
    _, dict_name = dqn.rsplit(".", 1)
    target_family = _dict_mode_family(dict_name)
    if target_family is None:
        return
    cur_family = _current_mode_family(sim)
    if cur_family == target_family:
        return
    new_mode = DisplayMode.ENGLISH if target_family == "english" else DisplayMode.KANJI
    sim.upper.mode_cycler.current_mode = new_mode
    print(f"[calibration] Auto-switched mode to {new_mode.name}")


# ── Param-kind convention + visual indicator ───────────────────────────
#
# Key-suffix convention drives both indicator type AND param semantics:
#
#     _x                       → screen x coord            (vertical line)
#     _y                       → screen y coord            (horizontal line)
#     _w, _width               → width, paired with _x     (right-edge line)
#     _h, _height              → height, paired with _y    (bottom-edge line)
#     _color                   → RGB tuple                 (swatch in sidebar)
#     _<edge>_offset/_margin   → edge-anchored offset      (line at edge ± val)
#                                <edge> ∈ left/right/top/bottom
#
# Keys not matching this shape get no indicator (gentle pressure to rename
# per convention). Tunable still works — just no visual feedback.

_EDGE_OFFSET_SUFFIXES = (
    "_left_offset",
    "_left_margin",
    "_right_offset",
    "_right_margin",
    "_top_offset",
    "_top_margin",
    "_bottom_offset",
    "_bottom_margin",
)


def _param_kind_from_key(key: str):
    for suffix in _EDGE_OFFSET_SUFFIXES:
        if key.endswith(suffix):
            # Return edge label only — caller maps to indicator geometry.
            edge = suffix.rsplit("_", 1)[0].lstrip("_")  # _right_offset → right
            return f"edge_{edge}"
    if key.endswith("_x"):
        return "x"
    if key.endswith("_y"):
        return "y"
    if key.endswith(("_w", "_width")):
        return "width"
    if key.endswith(("_h", "_height")):
        return "height"
    if key.endswith("_color"):
        return "color"
    # Polar geometry (arc-style elements). Pair detection in
    # _paired_polar_center / _paired_polar_radius via stem stripping.
    if key.endswith("_radius"):
        return "radius"
    if key.endswith("_angle"):
        return "angle"
    return None


def _paired_polar_center(key: str, d: dict):
    """For radius/angle keys, find paired _center_x + _center_y in same dict.

    Strips the polar suffix and looks for `<stem>_center_x` / `<stem>_center_y`.
    e.g. `arc_radius` → stem `arc` → `arc_center_x` / `arc_center_y`.
    """
    for suffix in ("_radius", "_start_angle", "_end_angle", "_angle"):
        if key.endswith(suffix):
            stem = key[: -len(suffix)]
            cx_key = stem + "_center_x"
            cy_key = stem + "_center_y"
            if cx_key in d and cy_key in d:
                return cx_key, cy_key
    return None


def _paired_polar_radius(key: str, d: dict):
    """For angle keys, find the paired `_radius` key in same dict."""
    for suffix in ("_start_angle", "_end_angle", "_angle"):
        if key.endswith(suffix):
            stem = key[: -len(suffix)]
            r_key = stem + "_radius"
            if r_key in d:
                return r_key
    return None


def _paired_anchor_key(key: str, kind: str, d: dict):
    """For width/height, find paired x/y key in same dict."""
    if kind == "width":
        suffixes = [("_width", "_x"), ("_w", "_x")]
    elif kind == "height":
        suffixes = [("_height", "_y"), ("_h", "_y")]
    else:
        return None
    for src, dst in suffixes:
        if not key.endswith(src):
            continue
        stem = key[: -len(src)]
        for candidate in (stem + dst, stem.rsplit("_max", 1)[0] + dst):
            if candidate in d:
                return candidate
    return None


def _draw_reference_overlay(screen) -> None:
    """Composite the loaded reference image over LCD A's lower-LCD area.

    No-op if no overlay set or toggled off. Scales the source image to fit
    ARC_RECT preserving aspect ratio (letterboxed inside the rect). Alpha
    set per-blit via per-surface alpha (set_alpha) so the underlying LCD
    is visible through it. Renders only on LCD A (the live tuning canvas);
    LCD B side-by-side stays clean.
    """
    if _overlay_surf is None or not _overlay_visible:
        return
    arc_rect = _overlay_fit_rect()
    if arc_rect is None:
        return
    src_w, src_h = _overlay_surf.get_size()
    if src_w == 0 or src_h == 0:
        return
    # Base scale: letterbox-fit into arc_rect, preserving aspect. User's
    # _overlay_scale multiplies on top so Alt+wheel zooms about the centered
    # default. Alt+drag pans via _overlay_offset_x/_y.
    fit_scale = min(arc_rect.width / src_w, arc_rect.height / src_h)
    eff_scale = fit_scale * _overlay_scale
    dst_w = max(1, int(src_w * eff_scale))
    dst_h = max(1, int(src_h * eff_scale))
    scaled = pygame.transform.smoothscale(_overlay_surf, (dst_w, dst_h))
    scaled.set_alpha(_OVERLAY_ALPHA)
    dst_x = arc_rect.x + (arc_rect.width - dst_w) // 2 + _overlay_offset_x
    dst_y = arc_rect.y + (arc_rect.height - dst_h) // 2 + _overlay_offset_y
    screen.blit(scaled, (dst_x, dst_y))


def _overlay_fit_rect():
    """Where a reference overlay is letterboxed, for the ACTIVE model.

    e235_0 keeps fitting into its 5-station `ARC_RECT`: that is what its
    references are cropped to, and changing it would move every existing tuning
    workflow. Any model without that rect fits the whole LCD instead — which is
    what a model being built element by element needs, since its references are
    whole-screen captures and its first elements are in the UPPER band, which
    `ARC_RECT` does not even cover.

    Returns None when no model is bound, so the overlay is skipped rather than
    drawn somewhere arbitrary.
    """
    if _active_model is None:
        return None
    try:
        lower = importlib.import_module(f"displays.train_models.{_active_model}.lower_lcd")
        return getattr(lower, "ARC_RECT")
    except (ImportError, AttributeError):
        pass
    try:
        pkg = importlib.import_module(f"displays.train_models.{_active_model}")
        return pygame.Rect(0, 0, pkg.S_WIDTH, pkg.S_HEIGHT)
    except (ImportError, AttributeError):
        return None


def _draw_focused_indicator(screen) -> None:
    """Paint ruler indicators on LCD A (canonical) + mirror on LCD B
    (side-by-side cross-reference in edit mode) when the focused dict
    actually affects the ENGLISH render. Mirror uses a subsurface at
    x=S_WIDTH so the inner draw function paints at the same rect-local
    coords without any offset math.

    Dispatch by dict-name suffix:
      _KANJI / _FURIGANA   → LCD A only (LCD B is always ENGLISH)
      _ENGLISH             → both LCDs (LCD B always; LCD A when in EN mode)
      _RECT / no suffix    → both LCDs (region rect or mode-agnostic)
    """
    _draw_indicator_at(screen)
    # Skip LCD B mirror when the tuneable doesn't affect the ENGLISH render.
    if _focused_element is None or not _param_rows:
        return
    dqn, _key, _sub_idx, type_tag = _param_rows[_focused_row]
    if type_tag in ("candidate", "unsupported"):
        return
    dict_name = dqn.rsplit(".", 1)[1]
    if dict_name.endswith(("_KANJI", "_FURIGANA")):
        return
    s_width = screen.get_width() // 2
    if s_width <= 0:
        return
    try:
        lcd_b = screen.subsurface((s_width, 0, s_width, screen.get_height()))
    except (ValueError, pygame.error):
        return  # screen not wide enough for a 2nd LCD (non-edit context)
    _draw_indicator_at(lcd_b)


def _draw_indicator_at(screen) -> None:
    if _focused_element is None or not _param_rows:
        return
    # Element-specific always-on overlay: arc shows the full waypoint
    # polyline (faint dots + connecting line) so user sees the whole
    # shape even while tuning a single waypoint. Runs BEFORE the focused-
    # param highlight so the focused waypoint's bright ring lands on top.
    if _focused_waypoint_cfg() is not None:
        _draw_arc_polyline_preview(screen)
    dqn, key, sub_idx, type_tag = _param_rows[_focused_row]
    if type_tag in ("candidate", "unsupported"):
        return  # synthetic / inert rows have no canvas indicator
    cfg = _REGISTRY.get(_focused_element)
    if cfg is None:
        return
    rect = _resolve_rect(cfg)
    if rect is None:
        return
    mod_path, dict_name = dqn.rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    d = getattr(mod, dict_name)
    raw_val = d[key]
    kind = _param_kind_from_key(key)
    if kind is None or kind == "color":
        return  # color shown as sidebar swatch, no canvas indicator
    if sub_idx is not None:
        return  # tuple sub-rows of non-color: no canvas indicator v1

    val = int(raw_val) if isinstance(raw_val, (int, float)) else None
    if val is None:
        return

    color = (255, 200, 80)
    dep_color = (130, 100, 40)  # dimmer — dependent extent
    # Ruler placement: outside the rect if there's room, else just inside.
    ruler_y_above = rect.top - 5 if rect.top >= 10 else rect.top + 3
    ruler_x_left = rect.left - 5 if rect.left >= 10 else rect.left + 3

    if kind == "x":
        # Ruler: screen-0 → val at y=ruler_y_above. Anchor = screen 0 because
        # the source code uses screen-absolute x.
        _draw_h_ruler(screen, color, 0, val, ruler_y_above)
        # Dependent _w extent shown as dim ruler one row up.
        for dep_key in (key[:-2] + "_w", key[:-2] + "_width"):
            if dep_key in d and isinstance(d[dep_key], (int, float)):
                right_x = val + int(d[dep_key])
                _draw_h_ruler(screen, dep_color, val, right_x, ruler_y_above - 5)
                break
    elif kind == "y":
        _draw_v_ruler(screen, color, 0, val, ruler_x_left)
        for dep_key in (key[:-2] + "_h", key[:-2] + "_height"):
            if dep_key in d and isinstance(d[dep_key], (int, float)):
                bot_y = val + int(d[dep_key])
                _draw_v_ruler(screen, dep_color, val, bot_y, ruler_x_left - 5)
                break
    elif kind == "width":
        anchor_key = _paired_anchor_key(key, kind, d)
        if anchor_key is None:
            return
        anchor_val = int(d[anchor_key])
        # Width ruler spans anchor_x → anchor_x + val.
        _draw_h_ruler(screen, color, anchor_val, anchor_val + val, ruler_y_above)
        # Dim ruler showing anchor's own measurement (from 0) for context.
        _draw_h_ruler(screen, dep_color, 0, anchor_val, ruler_y_above - 5)
    elif kind == "height":
        anchor_key = _paired_anchor_key(key, kind, d)
        if anchor_key is None:
            return
        anchor_val = int(d[anchor_key])
        _draw_v_ruler(screen, color, anchor_val, anchor_val + val, ruler_x_left)
        _draw_v_ruler(screen, dep_color, 0, anchor_val, ruler_x_left - 5)
    elif kind.startswith("edge_"):
        edge = kind[len("edge_") :]
        if edge == "left":
            _draw_h_ruler(screen, color, rect.left, rect.left + val, ruler_y_above)
        elif edge == "right":
            _draw_h_ruler(screen, color, rect.right - val, rect.right, ruler_y_above)
        elif edge == "top":
            _draw_v_ruler(screen, color, rect.top, rect.top + val, ruler_x_left)
        elif edge == "bottom":
            _draw_v_ruler(screen, color, rect.bottom - val, rect.bottom, ruler_x_left)
    elif kind == "radius":
        # Radial line from center going east, length = val. Center may sit
        # off-canvas (e.g. arc_center_x < 0); draw clips automatically.
        center_keys = _paired_polar_center(key, d)
        if center_keys is None:
            return
        cx_key, cy_key = center_keys
        cx, cy = int(d[cx_key]), int(d[cy_key])
        _draw_polar_spoke(screen, color, cx, cy, val, angle_deg=0)
    elif kind == "angle":
        # Spoke from center at val° (degrees) of length = paired _radius.
        # Pygame y is inverted: y_end = cy - r·sin(angle) so positive degrees
        # point UP visually, matching math convention.
        center_keys = _paired_polar_center(key, d)
        r_key = _paired_polar_radius(key, d)
        if center_keys is None or r_key is None:
            return
        cx_key, cy_key = center_keys
        cx, cy = int(d[cx_key]), int(d[cy_key])
        radius = int(d[r_key])
        _draw_polar_spoke(screen, color, cx, cy, radius, angle_deg=val)


def _focused_waypoint_cfg() -> Optional[dict]:
    """Waypoint config of the focused element, or None. Drives the generic
    drag-handle machinery: `{"dict": (mod, name), "prefixes": ["m", "b"]}` →
    each `<prefix><N>_x` / `<prefix><N>_y` pair is a draggable handle."""
    cfg = _REGISTRY.get(_focused_element) if _focused_element else None
    return cfg.get("waypoints") if cfg else None


def _waypoint_prefixes(wp: dict) -> list:
    """Prefix list for a waypoint cfg (back-compat with single `prefix`)."""
    return wp.get("prefixes") or [wp["prefix"]]


def _current_at_station() -> Optional[bool]:
    """Return state.at_station from the live sim, or None if unavailable."""
    if _edit_sim is None:
        return None
    try:
        return _edit_sim.state.at_station
    except AttributeError:
        return None


def _draw_state_allows(draw_state: dict, key_or_prefix: str) -> bool:
    """Return True if the key (or prefix) should be shown given the current
    at_station state.

    draw_state maps prefix-or-key → "stopping" | "approaching". A match means
    the element is only drawn in that state. If not in the map, always allowed.
    at_station=None (sim unavailable) → allow everything (safe default).
    """
    if key_or_prefix not in draw_state:
        return True
    at_station = _current_at_station()
    if at_station is None:
        return True
    required = draw_state[key_or_prefix]
    if required == "stopping":
        return at_station
    if required == "approaching":
        return not at_station
    return True


def _arc_waypoints() -> list:
    """Return list of (prefix, idx, x, y) for every waypoint of the focused
    element, across all its prefixes.

    Empty list if the element has no waypoint config or keys missing. Used by
    hit-test + handle render. Element-agnostic (five-station markers + groups).
    """
    wp = _focused_waypoint_cfg()
    if not wp:
        return []
    try:
        mod = importlib.import_module(wp["dict"][0])
        t = getattr(mod, wp["dict"][1])
    except (ImportError, AttributeError):
        return []
    draw_state = _REGISTRY.get(_focused_element, {}).get("draw_state", {})
    out = []
    for p in _waypoint_prefixes(wp):
        if not _draw_state_allows(draw_state, p):
            continue
        i = 0
        while f"{p}{i}_x" in t and f"{p}{i}_y" in t:
            out.append((p, i, int(t[f"{p}{i}_x"]), int(t[f"{p}{i}_y"])))
            i += 1
    return out


def _arc_waypoint_at_pos(pos) -> Optional[tuple]:
    """Hit-test mouse pos against the focused element's waypoints. Returns
    (prefix, idx) or None.

    Only returns a hit when the focused element has waypoints — keeps drag
    handles inert when tuning other elements (no accidental grabs).
    """
    if _focused_waypoint_cfg() is None:
        return None
    if not _handles_visible:
        return None  # hidden handles are inert — clicks fall through to focus
    if _focused_element in _locked_elements:
        return None  # locked element's handles are inert to grabs (K to unlock)
    mx, my = pos
    r_sq = _HANDLE_HIT_R * _HANDLE_HIT_R
    for p, idx, px, py in _arc_waypoints():
        dx = px - mx
        dy = py - my
        if dx * dx + dy * dy <= r_sq:
            return (p, idx)
    return None


def _focus_waypoint_row(handle: tuple) -> None:
    """Jump sidebar focus to the dragged waypoint's `_x` row (auto-scrolls).

    QOL: numeric feedback for the waypoint you're moving stays visible
    without manual ↑/↓ navigation. `_x` chosen as the canonical pair anchor
    (the indicator paired-ruler logic also keys off `_x` rows).
    """
    global _focused_row
    p, idx = handle
    target_key = f"{p}{idx}_x"
    for row_i, (_dqn, key, _sub, _tag) in enumerate(_param_rows):
        if key == target_key:
            _focused_row = row_i
            _ensure_focused_visible()
            return


def _apply_waypoint_drag(pos) -> None:
    """Write mouse pos (plus the mousedown grab offset) into `arc_p<idx>_x`
    / `_y` for the dragged waypoint.

    Live update — the element redraws next frame. Each axis is recorded in
    `_edited_keys` via `_mark_edit`, so only dragged handles persist on Ctrl+S.
    """
    if _dragging_waypoint is None:
        return
    wp = _focused_waypoint_cfg()
    if not wp:
        return
    try:
        mod = importlib.import_module(wp["dict"][0])
        t = getattr(mod, wp["dict"][1])
    except (ImportError, AttributeError):
        return
    p, idx = _dragging_waypoint
    x_key = f"{p}{idx}_x"
    y_key = f"{p}{idx}_y"
    if x_key not in t or y_key not in t:
        return
    t[x_key] = int(pos[0] + _drag_grab_offset[0])
    t[y_key] = int(pos[1] + _drag_grab_offset[1])
    dqn = f"{wp['dict'][0]}.{wp['dict'][1]}"
    _mark_edit(dqn, x_key, t)
    _mark_edit(dqn, y_key, t)


def _draw_arc_polyline_preview(screen) -> None:
    """Small open-crosshair grab handles at each waypoint.

    Renders only when the focused element has a `waypoints` cfg (caller-gated) —
    today the five_station handles (m/g/v/a) and the transfer-panel handles (tp).
    No connector line is drawn (the element's own render shows the shape). Handles
    use a generous hit radius (_HANDLE_HIT_R) but a small, OPEN-centre crosshair
    visual so the point being aligned (and any element underneath) stays visible.
    """
    if not _handles_visible:
        return
    # All handles render as small OPEN crosshairs — least obstructive: the open
    # centre keeps the point being aligned against the overlay visible (and, for
    # m-handles, the countdown digit underneath — a filled/ring centre made
    # digit-size calibration impossible, user-flagged 2026-06-12), while the
    # thin arms cover almost nothing. The grab area (_HANDLE_HIT_R) is unchanged,
    # so the small visual doesn't make handles harder to catch.
    #
    # CONTRASTIVE: each arm is TWO-TONE — a dark casing under a bright core — so
    # it reads against ANY backdrop (a single colour can't: red vertices vanish
    # on the red marker, white m-handles on the white disks). On light surfaces
    # the dark casing carries the contrast; on dark/coloured ones the bright
    # core does. Per-prefix core colour still distinguishes the sets (m=white
    # markers/dot, b=cyan group anchors, v=red polygon vertices); dragged handle
    # grows its arms + cores blue.
    prefix_color = {"m": (245, 245, 250), "g": (90, 210, 230), "v": (255, 90, 90), "tp": (120, 230, 150)}
    drag_color = (120, 200, 255)
    casing = (15, 15, 20)  # near-black underlay → contrast on light surfaces
    gap = 2  # clear centre radius — keeps the target pixel + neighbourhood open
    locked = _focused_element in _locked_elements
    for p, idx, px, py in _arc_waypoints():
        is_dragging = (p, idx) == _dragging_waypoint
        arm = _HANDLE_ARM_DRAG if is_dragging else _HANDLE_ARM
        if locked:
            color = (90, 90, 100)  # dimmed — locked, inert to grabs
        else:
            color = drag_color if is_dragging else prefix_color.get(p, (245, 245, 250))
        # Thin yellow ring around the selected station's handles (not when locked).
        if idx == _selected_station and not locked:
            pygame.draw.circle(screen, (255, 210, 60), (px, py), arm + 2, 1)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a_pt = (px + dx * gap, py + dy * gap)
            b_pt = (px + dx * arm, py + dy * arm)
            pygame.draw.line(screen, casing, a_pt, b_pt, 3)
            pygame.draw.line(screen, color, a_pt, b_pt, 1)


def _draw_polar_spoke(screen, color, cx: int, cy: int, length: int, angle_deg: float) -> None:
    """Spoke from (cx, cy) at angle_deg, of given length, with end-cap dot.

    Math convention: 0° = east, 90° = north. Pygame y inverted internally
    (subtract sin·length so positive degrees visually go up). Center dot
    drawn separately so user sees where the anchor sits, even off-canvas.
    """
    rad = math.radians(angle_deg)
    end_x = int(cx + length * math.cos(rad))
    end_y = int(cy - length * math.sin(rad))
    pygame.draw.line(screen, color, (cx, cy), (end_x, end_y), 1)
    pygame.draw.circle(screen, color, (end_x, end_y), 4, 1)
    pygame.draw.circle(screen, color, (cx, cy), 3)


def _draw_h_ruler(screen, color, x0: int, x1: int, y: int, tick: int = 3) -> None:
    """Horizontal measurement ruler from x0 to x1 at row y, with perpendicular
    end ticks. x0 may be > x1; the function normalizes."""
    a, b = (x0, x1) if x0 <= x1 else (x1, x0)
    pygame.draw.line(screen, color, (a, y), (b, y), 1)
    pygame.draw.line(screen, color, (a, y - tick), (a, y + tick), 1)
    pygame.draw.line(screen, color, (b, y - tick), (b, y + tick), 1)


def _draw_v_ruler(screen, color, y0: int, y1: int, x: int, tick: int = 3) -> None:
    a, b = (y0, y1) if y0 <= y1 else (y1, y0)
    pygame.draw.line(screen, color, (x, a), (x, b), 1)
    pygame.draw.line(screen, color, (x - tick, a), (x + tick, a), 1)
    pygame.draw.line(screen, color, (x - tick, b), (x + tick, b), 1)


def _values_equal(a, b) -> bool:
    """Baseline equality with float tolerance. Float nudges go through
    `round(x + delta*0.1, 2)`, so nudging back to a source value must compare
    with tolerance — exact `==` would leave the key stuck in `_edited_keys`.
    Recurses into tuples (color/coord channels)."""
    if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
        return all(_values_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return a == b
    return a == b


def _mark_edit(dqn: str, key: str, d: dict) -> None:
    """Record (or clear) a single key edit by comparing the live value to the
    baseline captured at launch. A key counts as edited ONLY while it differs
    from source — nudging or resetting it back to baseline drops it, so a no-op
    round-trip never writes. This per-key set is what ``commit_to_source``
    persists; every other key keeps its source text untouched."""
    baseline = _originals.get(dqn, {})
    if key not in baseline:
        return  # no baseline to compare against → can't prove a change; never auto-write
    if _values_equal(d[key], baseline[key]):
        _edited_keys.discard((dqn, key))
    else:
        _edited_keys.add((dqn, key))


def _nudge_focused(delta: int, sim=None) -> None:
    if not _param_rows:
        return
    dqn, key, sub_idx, type_tag = _param_rows[_focused_row]
    if type_tag == "unsupported":
        return
    if type_tag == "candidate":
        _cycle_candidate(delta, sim)
        return
    mod_path, dict_name = dqn.rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    d = getattr(mod, dict_name)
    val = d[key]
    if type_tag == "int":
        d[key] = int(val) + delta
    elif type_tag == "float":
        d[key] = round(float(val) + delta * 0.1, 2)
    elif type_tag == "tuple":
        new_chan = val[sub_idx] + delta
        # Clamp RGB-style 0-255 if channel looks color-shaped (3-tuple of ints).
        if len(val) == 3 and all(isinstance(v, int) for v in val):
            new_chan = max(0, min(255, new_chan))
        new_tuple = val[:sub_idx] + (new_chan,) + val[sub_idx + 1 :]
        d[key] = new_tuple
    elif type_tag == "bool":
        d[key] = not val
    elif type_tag == "str":
        return  # string nudging not implemented
    _mark_edit(dqn, key, d)


def _reset_focused(sim=None) -> None:
    """Reset focused row to original (source-file value at launch).

    Scalar row: restores the whole value. Tuple sub-row: restores only that
    channel, leaving other channels at their current edited state — matches
    nudge granularity. No-op if already at original. Candidate row (dest
    cycler) restores to the original dest captured at focus time.
    """
    if not _param_rows:
        return
    dqn, key, sub_idx, type_tag = _param_rows[_focused_row]
    if type_tag == "candidate":
        _reset_candidate(sim)
        return
    if type_tag == "unsupported":
        return
    orig = _originals.get(dqn, {}).get(key)
    if orig is None:
        return
    mod_path, dict_name = dqn.rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    d = getattr(mod, dict_name)
    if sub_idx is None:
        if d[key] == orig:
            return
        d[key] = orig
    else:
        cur = d[key]
        if cur[sub_idx] == orig[sub_idx]:
            return
        d[key] = cur[:sub_idx] + (orig[sub_idx],) + cur[sub_idx + 1 :]
    _mark_edit(dqn, key, d)


def _build_dest_candidates(sim) -> tuple:
    """Returns (candidates, current_value) for the dest cycler."""
    stops = sim.stops
    cur_idx = sim.state.curr_stop
    seen: list = []
    for stop in stops:
        d = stop.get("dest", "")
        if d and d not in seen:
            seen.append(d)
    route_dest = getattr(sim.upper, "dest", "") or ""
    if route_dest and route_dest not in seen:
        seen.append(route_dest)
    cur_dest = stops[cur_idx].get("dest", route_dest) if 0 <= cur_idx < len(stops) else route_dest
    return seen, cur_dest


def _apply_dest_value(sim, value: str) -> None:
    cur = sim.state.curr_stop
    if 0 <= cur < len(sim.stops):
        sim.stops[cur]["dest"] = value


def _build_prefix_candidates(sim) -> tuple:
    """Returns (candidates, current_value) for the prefix cycler.

    Candidates read from the canonical _PREFIX_FURIGANA module constant in
    upper_lcd.py (also keyed by _PREFIX_ENGLISH — same KANJI keys). Source-
    of-truth dispatch: if the state machine adds a 4th prefix, this picks
    it up automatically. Never hardcode the list here.
    """
    mod = importlib.import_module("displays.train_models.e235_0.upper_lcd")
    candidates = list(mod._PREFIX_FURIGANA.keys())
    return candidates, sim.upper.prefix_text


def _apply_prefix_value(sim, value: str) -> None:
    sim.upper.prefix_text = value


def _build_station_candidates(sim) -> tuple:
    """Returns (candidates, current_value) for the station cycler.

    Walks sim.stops collecting kanji station names (dedup, order preserved).
    Apply drives sim.state.curr_stop — station_text is stop-derived, so
    cycling also changes dest/badge (same side effect as `[`/`]` keybind).
    """
    seen: list = []
    for stop in sim.stops:
        name = stop.get("name", "")
        if name and name not in seen:
            seen.append(name)
    cur = ""
    if 0 <= sim.state.curr_stop < len(sim.stops):
        cur = sim.stops[sim.state.curr_stop].get("name", "")
    return seen, cur


def _apply_station_value(sim, value: str) -> None:
    # jump_to_stop already calls UpperDisplay.set_state internally
    # (app.py:592), so no extra set_state needed here.
    for idx, stop in enumerate(sim.stops):
        if stop.get("name", "") == value:
            sim.jump_to_stop(idx)
            return


def _cycle_candidate(delta: int, sim) -> None:
    """Cycle the focused element's pinned candidate row. Element-agnostic via
    _REGISTRY[element]["cycler"]["apply"]."""
    state = _candidate_state.get(_focused_element)
    if state is None or not state["candidates"]:
        return
    cfg = _REGISTRY.get(_focused_element)
    cycler = cfg.get("cycler") if cfg else None
    if cycler is None:
        return
    n = len(state["candidates"])
    state["idx"] = (state["idx"] + (1 if delta > 0 else -1)) % n
    new_val = state["candidates"][state["idx"]]
    cycler["apply"](sim, new_val)
    # ascii() escapes non-ASCII (kanji etc) to \uXXXX so cp1252 stdout
    # on Windows doesn't crash. repr() preserves unicode visible.
    print(f"[calibration] {_focused_element} = {ascii(new_val)}  ({state['idx'] + 1}/{n})")


def _reset_candidate(sim) -> None:
    state = _candidate_state.get(_focused_element)
    if state is None or sim is None:
        return
    cfg = _REGISTRY.get(_focused_element)
    cycler = cfg.get("cycler") if cfg else None
    if cycler is None:
        return
    orig = state["original"]
    if orig in state["candidates"]:
        state["idx"] = state["candidates"].index(orig)
    cycler["apply"](sim, orig)


def _draw_sidebar_contents(surf) -> None:
    w, h = surf.get_size()
    pad_x = 16
    header_y = 8
    scrollbar_w = 6
    val_col_x = w // 2 + 40
    row_w = w - scrollbar_w  # leave gutter for scrollbar

    # Header.
    if _focused_element is None:
        header_text = "Calibration Editor — click DEST_RECT to start"
    else:
        lock_tag = "  [LOCKED — K]" if _focused_element in _locked_elements else ""
        header_text = f"Editing: {_focused_element}{lock_tag}"
    header_img = _sidebar_header_font.render(header_text, True, (240, 240, 245))
    surf.blit(header_img, (pad_x, header_y))

    # Windowed rows — only draw the slice in [_scroll_offset, _scroll_offset + vis).
    vis = _visible_row_count()
    end = min(len(_param_rows), _scroll_offset + vis)
    for i in range(_scroll_offset, end):
        dqn, key, sub_idx, type_tag = _param_rows[i]
        y = _ROW_TOP + (i - _scroll_offset) * _ROW_H
        is_focused = i == _focused_row
        if is_focused:
            pygame.draw.rect(surf, (60, 90, 140, 255), pygame.Rect(0, y, row_w, _ROW_H))

        # Synthetic candidate-cycler row (e.g. dest value picker).
        if type_tag == "candidate":
            element_id = dqn.split(":", 1)[1] if ":" in dqn else "?"
            state = _candidate_state.get(element_id, {})
            cands = state.get("candidates", [])
            cidx = state.get("idx", 0)
            cur_val = cands[cidx] if cands else ""
            orig_val = state.get("original", "")
            modified = bool(cands) and cur_val != orig_val
            label = f"{element_id.upper()}.value"
            label_img = _sidebar_font.render(label, True, (220, 220, 230))
            surf.blit(label_img, (pad_x, y + 2))
            val_text = f"{cur_val!r}  ({cidx + 1}/{len(cands)})" if cands else "(no candidates)"
            if modified:
                val_text = f"{val_text}  ← {orig_val!r}"
            if modified:
                color = (255, 220, 120) if is_focused else (230, 200, 130)
            else:
                color = (255, 255, 200) if is_focused else (200, 200, 210)
            val_img = _sidebar_font.render(val_text, True, color)
            surf.blit(val_img, (val_col_x, y + 2))
            continue

        # Resolve current value + original for display.
        mod_path, dict_name = dqn.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        d = getattr(mod, dict_name)
        val = d[key]
        orig_val = _originals.get(dqn, {}).get(key)
        if sub_idx is not None:
            display_key = f"{key}[{sub_idx}]"
            display_val = val[sub_idx]
            orig_display = orig_val[sub_idx] if orig_val is not None else None
        else:
            display_key = key
            display_val = val
            orig_display = orig_val

        # Dict-name prefix (collapsed) so user knows which dict.
        dict_short = dict_name.replace("_TUNEABLES_", "")
        label = f"{dict_short}.{display_key}"
        label_img = _sidebar_font.render(label, True, (220, 220, 230))
        surf.blit(label_img, (pad_x, y + 2))

        # Value display — show ` ← <orig>` when modified.
        modified = orig_display is not None and display_val != orig_display
        val_text = repr(display_val) if not isinstance(display_val, (int, float)) else str(display_val)
        if modified:
            orig_text = repr(orig_display) if not isinstance(orig_display, (int, float)) else str(orig_display)
            val_text = f"{val_text}  ← {orig_text}"
        if type_tag == "unsupported":
            val_text += "  (unsupported)"
        if modified:
            color = (255, 220, 120) if is_focused else (230, 200, 130)
        else:
            color = (255, 255, 200) if is_focused else (200, 200, 210)
        val_img = _sidebar_font.render(val_text, True, color)
        surf.blit(val_img, (val_col_x, y + 2))

        # Color swatch — when the parent key matches the `_color` convention,
        # show the current tuple as a filled rect next to the value. Each
        # sub-row (R/G/B) gets the same swatch since they all render one color.
        if _param_kind_from_key(key) == "color" and isinstance(val, tuple) and len(val) == 3:
            try:
                swatch_color = tuple(max(0, min(255, int(c))) for c in val)
                swatch_x = val_col_x - 24
                swatch_rect = pygame.Rect(swatch_x, y + 4, 16, _ROW_H - 8)
                pygame.draw.rect(surf, swatch_color, swatch_rect)
                pygame.draw.rect(surf, (90, 90, 100), swatch_rect, 1)  # thin border
            except (TypeError, ValueError):
                pass

    # Scrollbar — only when content overflows.
    if len(_param_rows) > vis:
        track_top = _ROW_TOP
        track_h = vis * _ROW_H
        pygame.draw.rect(surf, (50, 50, 60, 255), pygame.Rect(w - scrollbar_w, track_top, scrollbar_w, track_h))
        thumb_h = max(20, int(track_h * vis / len(_param_rows)))
        max_offset = max(1, len(_param_rows) - vis)
        thumb_y = track_top + int((track_h - thumb_h) * _scroll_offset / max_offset)
        pygame.draw.rect(surf, (140, 140, 160, 255), pygame.Rect(w - scrollbar_w, thumb_y, scrollbar_w, thumb_h))

    # Footer hint. Second line surfaces when an overlay is loaded (Alt-modified
    # gestures + O toggle exist only in that mode).
    hint = "↑/↓ select   ←/→ nudge   Shift+←/→ ±10   R reset   L sync mode   Wheel/PgUp/Dn scroll   Ctrl+S save   ESC quit"
    hint_img = _sidebar_hint_font.render(hint, True, (160, 160, 170))
    if _overlay_surf is not None:
        hint2 = "O toggle overlay   Alt+drag pan overlay   Alt+Wheel / Alt+=/- zoom overlay (aspect kept)"
        hint2_img = _sidebar_hint_font.render(hint2, True, (160, 160, 170))
        surf.blit(hint_img, (pad_x, h - 36))
        surf.blit(hint2_img, (pad_x, h - 20))
    else:
        surf.blit(hint_img, (pad_x, h - 20))


# ── Writeback ──────────────────────────────────────────────────────────


def commit_to_source() -> None:
    """Write back ONLY the keys the user edited this session — every other key
    keeps its exact source text, so an untouched key cannot drift. Type-guarded:
    only int / float / tuple-of-numeric / str values get written.

    `_edited_keys` holds (dqn, key) pairs that currently differ from baseline.
    Grouped here into module → dict → {keys}; `_swap_dict_literal` rewrites only
    those keys' value-sides."""
    if not _edited_keys:
        print("[calibration] No edits this session — nothing to write.")
        return
    # module path -> dict_name -> set(keys)
    by_module: dict[str, dict[str, set]] = {}
    for dqn, key in _edited_keys:
        mod_path, dict_name = dqn.rsplit(".", 1)
        by_module.setdefault(mod_path, {}).setdefault(dict_name, set()).add(key)

    for mod_path, dicts in by_module.items():
        rel = mod_path.replace(".", "/") + ".py"
        src_path = project_root() / rel
        if not src_path.exists():
            print(f"[calibration] WARN: source not found: {src_path}")
            continue
        text = src_path.read_text(encoding="utf-8")
        n = 0
        for dict_name, keys in dicts.items():
            mod = importlib.import_module(mod_path)
            current = getattr(mod, dict_name)
            text = _swap_dict_literal(text, dict_name, current, src_path, allowed_keys=keys)
            n += len(keys)
        src_path.write_text(text, encoding="utf-8")
        print(f"[calibration] Wrote {n} edited key(s) to {rel}")

    _edited_keys.clear()
    print("[calibration] git diff to review.")


def _swap_dict_literal(text: str, dict_name: str, new_values: dict, src_path: Path, allowed_keys=None) -> str:
    """Find `<dict_name> = {...}` at module-level, replace value-side per key.

    When ``allowed_keys`` is given, ONLY those keys are rewritten — every other
    key's source text is left byte-for-byte untouched, so an unedited key can
    never drift even if the live dict's in-memory value differs."""
    tree = ast.parse(text)
    target_node = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == dict_name
            and isinstance(node.value, ast.Dict)
        ):
            target_node = node.value
            break
    if target_node is None:
        print(f"[calibration] WARN: dict literal {dict_name} not found in {src_path.name}")
        return text

    lines = text.split("\n")
    # Walk keys in REVERSE so col-offset edits on later keys don't shift the
    # cols of earlier keys on the same line. Multi-key-per-line schemas
    # (e.g. _TUNEABLES_FIVE_STATION's `"m1_x": ..., "m1_y": ..., "m1_r": ..."`
    # rows) require this — forward iteration corrupts the file the moment a
    # value's repr length differs from the original on a multi-key line.
    # Single-key-per-line dicts are also safe under reverse since each line
    # has only one edit.
    for k_node, v_node in reversed(list(zip(target_node.keys, target_node.values))):
        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
            continue
        key = k_node.value
        if key not in new_values:
            continue
        if allowed_keys is not None and key not in allowed_keys:
            continue
        new_val = new_values[key]
        if not isinstance(new_val, (int, float, tuple, str)):
            print(f"[calibration] WARN: skip {dict_name}[{key!r}] unsupported type {type(new_val).__name__}")
            continue
        # Tuple must be all simple values.
        if isinstance(new_val, tuple) and not all(isinstance(v, (int, float, str)) for v in new_val):
            print(f"[calibration] WARN: skip {dict_name}[{key!r}] nested tuple not supported")
            continue

        new_repr = repr(new_val)
        v_lineno = v_node.lineno - 1
        v_end_lineno = v_node.end_lineno - 1
        v_col_start = v_node.col_offset
        v_end_col = v_node.end_col_offset
        if v_lineno != v_end_lineno:
            # Multi-line value; skip with warning rather than risk mangling.
            print(f"[calibration] WARN: skip {dict_name}[{key!r}] multi-line value")
            continue
        line = lines[v_lineno]
        lines[v_lineno] = line[:v_col_start] + new_repr + line[v_end_col:]
    return "\n".join(lines)


# ── Cycler config ──────────────────────────────────────────────────────
# Forward-references functions defined above. Each element with a value
# cycler gets a "cycler" entry on its _REGISTRY config:
#   "build": (sim) -> (candidates_list, current_value)
#   "apply": (sim, value) -> None
# _on_click pins a synthetic row at the top of the param list when present;
# _cycle_candidate + _reset_candidate dispatch through this config.
_REGISTRY["dest"]["cycler"] = {
    "build": _build_dest_candidates,
    "apply": _apply_dest_value,
}
_REGISTRY["prefix"]["cycler"] = {
    "build": _build_prefix_candidates,
    "apply": _apply_prefix_value,
}
_REGISTRY["station"]["cycler"] = {
    "build": _build_station_candidates,
    "apply": _apply_station_value,
}

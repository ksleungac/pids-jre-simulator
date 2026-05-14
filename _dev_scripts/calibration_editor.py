"""Calibration editor v1 — direct-manipulation pixel tuning for pygame LCDs.

WIP, see WIP_calibration_editor.md at repo root. Wired up by preview_display.py
when run with `--edit`. Single-file prototype; if it earns its keep we extract.

Reads `_TUNEABLES_*` dicts from target modules at runtime. Mutates them in
place — pygame redraws pick up new values next frame. Auto-saves to a
gitignored scratch JSON for crash safety. Ctrl+S writes back to source
(value-swap only, type-guarded to int/float/tuple/str). ESC quits without
writeback (scratch JSON persists for resume).

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
    ESC                          → quit edit mode.
"""

from __future__ import annotations

import ast
import importlib
import json
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
# }
_REGISTRY = {
    "dest": {
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "DEST_RECT",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_DEST_KANJI"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_DEST_ENGLISH"),
        ],
    },
    "clock": {
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "CLOCK_RECT",
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
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "PREFIX_RECT",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PREFIX_RECT"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PREFIX_KANJI"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_PREFIX_ENGLISH"),
        ],
    },
    "station": {
        "rect_module": "displays.train_models.e235_0.upper_lcd",
        "rect_attr": "STATION_RECT",
        "dicts": [
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_STATION_RECT"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_STATION_KANJI"),
            ("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_STATION_ENGLISH"),
        ],
    },
}


# ── State ──────────────────────────────────────────────────────────────

_focused_element: Optional[str] = None  # e.g. "dest"
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

_SCRATCH_PATH = project_root() / "_calibration_session.json"

_sidebar_font: Optional[pygame.font.Font] = None
_sidebar_header_font: Optional[pygame.font.Font] = None
_sidebar_hint_font: Optional[pygame.font.Font] = None


# ── Public API ─────────────────────────────────────────────────────────


def enter_edit_mode(sim) -> None:
    """Snapshot originals, restore values from scratch JSON if present, print help.

    Originals captured BEFORE scratch-restore so the R reset target is the
    source-file value, not a prior session's tweaks. Scratch is user-side
    state; originals are pristine-source state.
    """
    _snapshot_originals()
    _restore_from_scratch()
    # Enable held-key repeats — nudge / scroll / row-cycle all feel snappier
    # when you can hold instead of mash. 400 ms initial delay, ~20 Hz repeat.
    pygame.key.set_repeat(400, 50)
    print("[calibration] Edit mode ON. Click DEST_RECT on upper LCD to focus.")
    print("[calibration] Up/Down select  Left/Right nudge  Shift+Arrow +-10  R reset  Ctrl+S save  ESC quit")
    print("[calibration] M=cycle mode (kanji/furigana/english)  L=sync mode to focused dict  [=prev stop  ]=next stop")


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


def handle_event(event, sim) -> bool:
    """Dispatch a pygame event. Returns True if absorbed."""
    global _should_quit
    if event.type == pygame.QUIT:
        return False  # let caller close
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        return _on_click(event.pos, sim)
    if event.type == pygame.MOUSEWHEEL:
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
        if event.key == pygame.K_LEFTBRACKET:
            _cycle_stop(sim, -1)
            return True
        if event.key == pygame.K_RIGHTBRACKET:
            _cycle_stop(sim, 1)
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


def draw_overlay(screen) -> None:
    """Indicator on LCD (focused-param visual cue) + sidebar overlay on lower area."""
    _ensure_fonts()
    _draw_focused_indicator(screen)
    w, h = screen.get_size()
    from displays.train_models.e235_0 import UPPER_HEIGHT as _UH

    sidebar_top = _UH
    sidebar = pygame.Surface((w, h - sidebar_top), pygame.SRCALPHA)
    sidebar.fill((20, 20, 30, 230))  # near-opaque dark; user can still glimpse underneath
    _draw_sidebar_contents(sidebar)
    screen.blit(sidebar, (0, sidebar_top))


# ── Internals ──────────────────────────────────────────────────────────


def _ensure_fonts() -> None:
    global _sidebar_font, _sidebar_header_font, _sidebar_hint_font
    if _sidebar_font is None:
        font_path = str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf")
        _sidebar_font = pygame.font.Font(font_path, 16)
        _sidebar_header_font = pygame.font.Font(font_path, 20)
        _sidebar_hint_font = pygame.font.Font(font_path, 12)


def _on_click(pos, sim) -> bool:
    global _focused_element, _focused_row, _param_rows, _scroll_offset
    # Hit-test each registered element.
    for element_id, cfg in _REGISTRY.items():
        rect = _resolve_rect(cfg)
        if rect is None:
            continue
        if rect.collidepoint(pos):
            _focused_element = element_id
            _param_rows = _build_param_rows(cfg["dicts"])
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
    # Click in sidebar area: try to focus a row.
    from displays.train_models.e235_0 import UPPER_HEIGHT as _UH

    if pos[1] >= _UH and _focused_element is not None:
        row_idx = _row_at_sidebar_y(pos[1] - _UH)
        if row_idx is not None:
            _focused_row = row_idx
            _ensure_focused_visible()
            return True
    return False


def _resolve_rect(cfg) -> Optional[pygame.Rect]:
    try:
        mod = importlib.import_module(cfg["rect_module"])
        return getattr(mod, cfg["rect_attr"])
    except (ImportError, AttributeError):
        return None


def _build_param_rows(dict_specs) -> list:
    """Flatten dicts into rows. Tuple values expand into N sub-rows.

    Each row: (dict_qualified_name, param_name, sub_idx, type_tag)
    - sub_idx is None for scalars, 0..N-1 for tuple channels.
    - type_tag in {"int", "float", "tuple", "str"} drives nudge behaviour.
    """
    rows = []
    for mod_path, dict_name in dict_specs:
        mod = importlib.import_module(mod_path)
        d = getattr(mod, dict_name)
        dqn = f"{mod_path}.{dict_name}"
        for key, val in d.items():
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
    """Sidebar pixel height = screen height - UPPER_HEIGHT. Read lazily to
    avoid circular import at module load."""
    from displays.train_models.e235_0 import UPPER_HEIGHT as _UH

    surf = pygame.display.get_surface()
    if surf is None:
        return 360  # safe default; matches S_HEIGHT 480 - UPPER 117 ≈ 363
    return surf.get_height() - _UH


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
        d[key] = round(float(val) + delta * 1.0, 2)
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
    _save_scratch()


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
    _save_scratch()


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
        header_text = f"Editing: {_focused_element}"
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

    # Footer hint.
    hint = "↑/↓ select   ←/→ nudge   Shift+←/→ ±10   R reset   L sync mode   Wheel/PgUp/Dn scroll   Ctrl+S save   ESC quit"
    hint_img = _sidebar_hint_font.render(hint, True, (160, 160, 170))
    surf.blit(hint_img, (pad_x, h - 20))


# ── Persistence ────────────────────────────────────────────────────────


def _collect_current_values() -> dict:
    """Dump all registered dicts to a JSON-serializable shape."""
    data = {}
    for element_id, cfg in _REGISTRY.items():
        for mod_path, dict_name in cfg["dicts"]:
            mod = importlib.import_module(mod_path)
            d = getattr(mod, dict_name)
            data[f"{mod_path}.{dict_name}"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}
    return data


def _save_scratch() -> None:
    try:
        _SCRATCH_PATH.write_text(json.dumps(_collect_current_values(), indent=2))
    except OSError as e:
        print(f"[calibration] WARN: scratch save failed: {e}")


def _restore_from_scratch() -> None:
    if not _SCRATCH_PATH.exists():
        return
    try:
        data = json.loads(_SCRATCH_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[calibration] WARN: scratch corrupt, starting from source defaults: {e}")
        return
    for element_id, cfg in _REGISTRY.items():
        for mod_path, dict_name in cfg["dicts"]:
            qname = f"{mod_path}.{dict_name}"
            if qname not in data:
                continue
            mod = importlib.import_module(mod_path)
            d = getattr(mod, dict_name)
            for k, v in data[qname].items():
                if k not in d:
                    continue  # source dropped this key; skip
                # Re-tuplify lists.
                src_val = d[k]
                if isinstance(src_val, tuple) and isinstance(v, list):
                    d[k] = tuple(v)
                else:
                    d[k] = v
    print(f"[calibration] Restored values from {_SCRATCH_PATH.name}")


# ── Writeback ──────────────────────────────────────────────────────────


def commit_to_source() -> None:
    """Write current dict values back into source .py files. Type-guarded:
    only int / float / tuple-of-numeric / str values get written. Other
    types abort with a loud warning."""
    by_module: dict[str, list[str]] = {}
    for element_id, cfg in _REGISTRY.items():
        for mod_path, dict_name in cfg["dicts"]:
            by_module.setdefault(mod_path, []).append(dict_name)

    for mod_path, dict_names in by_module.items():
        rel = mod_path.replace(".", "/") + ".py"
        src_path = project_root() / rel
        if not src_path.exists():
            print(f"[calibration] WARN: source not found: {src_path}")
            continue
        text = src_path.read_text(encoding="utf-8")
        for dict_name in dict_names:
            mod = importlib.import_module(mod_path)
            current = getattr(mod, dict_name)
            text = _swap_dict_literal(text, dict_name, current, src_path)
        src_path.write_text(text, encoding="utf-8")
        print(f"[calibration] Wrote back to {rel}")

    if _SCRATCH_PATH.exists():
        _SCRATCH_PATH.unlink()
    print("[calibration] Scratch cleared. git diff to review.")


def _swap_dict_literal(text: str, dict_name: str, new_values: dict, src_path: Path) -> str:
    """Find `<dict_name> = {...}` at module-level, replace value-side per key."""
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
    # Walk keys in reverse so col-offset edits on later keys don't shift earlier ones.
    # (Actually AST gives nodes in source order; col-offset edits on the SAME line
    # would shift downstream cols. Each key→value is on its own line in our
    # dicts, so per-line replacement is safe regardless of order.)
    for k_node, v_node in zip(target_node.keys, target_node.values):
        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
            continue
        key = k_node.value
        if key not in new_values:
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

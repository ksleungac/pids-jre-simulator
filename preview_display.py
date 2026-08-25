# SPDX-License-Identifier: MIT
"""Entry point for the audio-free PIDS preview.

Thin wrapper around `PASimulator(preview=True)`. Everything that isn't CLI
plumbing — route loading, state machine, drawing, input handling — lives in
app.py and is shared with the real application, so behavior can't drift.
The full swap inventory (audio, input, mixer-init, window-position) is
documented at `PASimulator.__init__`'s ``preview`` parameter.

Usage:
  uv run preview_display.py                                     # MOCK route (audio/_mock/main)
  uv run preview_display.py --route yamanote/1208G              # real route by shorthand
  uv run preview_display.py --route chuo/916H --stop 6          # real route at a specific stop
  uv run preview_display.py --screenshot out.png --mode english --stop 2 --pa 1

  # Force the lower LCD's 8-station zoomed view (skips the 24s cycle so the
  # frame is always 8-station, useful for iterating layout at any curr_stop):
  uv run preview_display.py --route sobu/1217F --stop 7 --lower-view eight
  uv run preview_display.py --screenshot 8sta.png --route sobu/1217F --stop 7 \
      --mode kanji --lower-view eight

  # Force the full-route view permanently (skip 8-station alternation):
  uv run preview_display.py --route sobu/1217F --lower-view full

Interactive controls (forwarded to PASimulator._handle_input_preview):
  PageDown  next PA phase (advances to next stop when phases exhausted)
  PageUp    next STA melody (no-op in preview — audio is silent)
  M         cycle forced display mode (KANJI → FURIGANA → ENGLISH)
  Right     jump to next stop (bypasses PA cycle)
  Left      jump to previous stop
  ESC       quit

--route accepts: a path to route.json, a directory containing one, or a
shorthand like 'yamanote/1208G' / 'chuo/916H' (resolved under audio/).

--lower-view {full,eight,cycle} forces the lower LCD into a fixed view.
Default 'cycle' alternates full ↔ 8-station every 12s. 'eight' or 'full'
freeze the cycler on one view — handy for screenshots where you want a
deterministic frame regardless of how long the preview has been running.
"""

import argparse
import importlib
import os
import sys
import time
from pathlib import Path
from typing import Optional

import pygame

from app import PASimulator
from displays.base import DisplayMode
from displays.train_models import TRAIN_MODELS, get_train_model

DEFAULT_MOCK_ROUTE = "_mock/main"

MODE_MAP = {
    "kanji": DisplayMode.KANJI,
    "furigana": DisplayMode.FURIGANA,
    "english": DisplayMode.ENGLISH,
}


def _resolve_work_dir(spec: str) -> str:
    """Resolve a --route arg into a work_dir (directory containing route.json).

    Accepts a path to route.json, a directory, or a shorthand like
    'yamanote/1208G' / 'chuo/916H' / '_mock/main' (probed under audio/).
    """
    candidates = [
        Path(spec),
        Path(spec) / "route.json",
        Path("audio") / spec,
        Path("audio") / spec / "route.json",
    ]
    for c in candidates:
        if c.is_file() and c.name == "route.json":
            return str(c.parent)
        if c.is_dir() and (c / "route.json").is_file():
            return str(c)
    for base in (Path(spec), Path("audio") / spec):
        if base.is_dir():
            matches = sorted(base.glob("*/route.json")) or sorted(base.glob("**/route.json"))
            if matches:
                return str(matches[0].parent)
    raise FileNotFoundError(f"Could not resolve --route {spec!r} to a route.json file")


def parse_args():
    parser = argparse.ArgumentParser(description="PIDS Display Preview (upper + lower LCD, audio-free)")
    parser.add_argument("--screenshot", type=str, help="Save one frame to file and exit")
    parser.add_argument("--mode", type=str, choices=list(MODE_MAP), default=None, help="Force display mode (default: cycles automatically)")
    parser.add_argument("--stop", type=int, default=0, help="Initial station index (default: 0)")
    parser.add_argument(
        "--pa",
        type=int,
        default=None,
        help="Force PA phase: 0=次は/Next, 1=まもなく/Arriving, 2=ただいま/Now stopping (STOPPING). "
        "Default: leave STOPPING state from jump_to_stop (= 2).",
    )
    parser.add_argument(
        "--route",
        type=str,
        default=DEFAULT_MOCK_ROUTE,
        help=f"Route shorthand, path, or directory containing route.json. Default: {DEFAULT_MOCK_ROUTE!r} (audio/_mock/main/route.json).",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=list(TRAIN_MODELS),
        default="e235_1000",
        help="Train model to render with. Default 'e235_1000' (Yokosuka/Sōbu Rapid). 'e235_0' is the Yamanote variant — same upper LCD minus the train-type cell; lower LCD is interim-reused from e235_1000 pending its dedicated redesign.",
    )
    parser.add_argument(
        "--debug-grid",
        action="store_true",
        help="Tint each upper-LCD region's clear rect with a unique color so overlaps / under-clears / clipping are visible. Region keys: see _DEBUG_COLORS in the active model's upper_lcd.py (chosen via --model).",
    )
    parser.add_argument(
        "--lower-view",
        type=str,
        choices=("full", "eight", "transfer", "cycle"),
        default="cycle",
        help="Force lower-LCD view: 'full' = full-route, 'eight' = 8-station zoom, 'transfer' = transfer-info panel (requires station with transfers + at_station=True), 'cycle' = normal alternation (default).",
    )
    parser.add_argument(
        "--edit",
        action="store_true",
        help="Open the calibration editor (docs/wip/WIP_calibration_editor.md). Sim freezes; "
        "click an editable element on the LCD to focus its `_TUNEABLES_*` dict; ←/→ nudge "
        "values; Ctrl+S writes back to source. ESC to quit.",
    )
    parser.add_argument(
        "--overlay",
        type=str,
        default=None,
        help="Path to a reference image (e.g. IRL photo) to render semi-transparent "
        "over the lower LCD area during --edit mode. Toggle on/off with `O`. Useful for "
        "matching waypoint positions to the IRL artifact by direct visual alignment.",
    )
    return parser.parse_args()


def apply_state(sim, *, stop=0, pa=None, mode=None, lower_view="cycle"):
    """Put `sim` into one previewable state.

    Factored out of main() so anything that needs to visit many states — the
    font-atlas bake sweeps every route x stop x mode x view — drives the app
    through this one function instead of a copy of it. A copy is how a sweep ends
    up exercising states the real preview never produces, or missing ones it does.
    """
    sim.jump_to_stop(stop)
    if pa is not None:
        forced = max(0, min(pa, 2))
        if forced == 2:
            sim.state.at_station = True
            sim.state.cnt_pa = 0
        else:
            sim.state.at_station = False
            sim.state.cnt_pa = forced
    sim.upper.set_state(sim.state.curr_stop, sim.state.cnt_pa, at_station=sim.state.at_station)

    # Force display mode if requested
    if mode:
        sim.upper.mode_cycler.current_mode = MODE_MAP[mode]
        sim.upper.mode_cycler.enabled = False

    # Force lower-LCD view by setting the slot directly + locking the cycler.
    # Without locking, the cycler would still tick in interactive mode and
    # rotate FULL → EIGHT → TRANSFER on its normal cadence; the forced slot
    # would only persist for the boot frame.
    if lower_view != "cycle":
        slot_map = {
            "full": sim.lower._SLOT_FULL,
            "eight": sim.lower._SLOT_EIGHT,
            "transfer": sim.lower._SLOT_TRANSFER,
        }
        sim.lower._current_slot = slot_map[lower_view]
        # Lock: the scheduler owns every discrete change, so disabling it
        # freezes the slot AND the language flip in one switch.
        sim.scheduler.enabled = False


def render_frame(sim, timestamp=None):
    """Draw one complete frame — both LCDs — into sim.screen."""
    timestamp = time.time() if timestamp is None else timestamp
    sim.scheduler.tick(timestamp, sim.state)
    sim.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))
    # current_time=0.0 freezes the lower-LCD countdown at full values for a
    # readable static snapshot.
    sim.lower.draw(0.0)


def main():
    args = parse_args()

    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    if args.debug_grid:
        # Flip the chosen model's upper-LCD debug-grid toggle. Module-level
        # flag — must be set BEFORE pygame surfaces start rendering. The
        # upper_lcd module is derived from the model's registered display class.
        _upper_lcd_mod = importlib.import_module(get_train_model(args.model).upper_cls.__module__)
        _upper_lcd_mod.DEBUG_GRID = True

    work_dir = _resolve_work_dir(args.route)
    print(f"[preview] work_dir={work_dir}")

    sim = PASimulator(work_dir, preview=True, model=args.model)

    # Initial position. jump_to_stop lands in STOPPING@target (at_station=True,
    # cnt_pa=0). --pa overrides that into a different prefix state for visual
    # iteration: 0=次は, 1=まもなく, 2=ただいま (STOPPING). Omitted leaves the
    # natural STOPPING landing.
    apply_state(sim, stop=args.stop, pa=args.pa, mode=args.mode, lower_view=args.lower_view)

    if args.screenshot:
        render_frame(sim)
        pygame.display.flip()
        pygame.image.save(sim.screen, args.screenshot)
        print(f"Screenshot saved to {args.screenshot}")
        sim.cleanup()
        return

    if args.edit:
        # Which models the editor can drive is DERIVED from its registry, not
        # named here — a hardcoded list is how registering an element in a new
        # model leaves it unreachable while looking supported. The window is
        # now sized from the loaded model's registry record (see
        # _run_edit_loop), so the old e235_0-only refusal no longer applies.
        from app_paths import project_root

        sys.path.insert(0, str(project_root() / "_dev_scripts"))
        import calibration_editor  # noqa: E402

        editable = calibration_editor.editable_models()
        if args.model not in editable:
            print(f"[error] --edit has no registered elements for --model {args.model}.")
            print(f"        Models with elements: {', '.join(editable) or 'none'}.")
            print("        Register one in _dev_scripts/calibration_editor.py's _REGISTRY.")
            sys.exit(1)
        _run_edit_loop(sim, overlay_path=args.overlay, lower_view=args.lower_view)
        sim.cleanup()
        sys.exit()

    sim.run()
    sys.exit()


def _run_edit_loop(sim, overlay_path: Optional[str] = None, lower_view: str = "cycle") -> None:
    """Frozen-frame main loop for `--edit` mode. Sim state does NOT advance.

    Loads `_dev_scripts/calibration_editor.py` via sys.path hack (it's a
    dev-only tool, never imported by production code).

    Param panel always occupies the right half; the left half renders the
    tuning target, dispatched per-frame from the focused element's `target`
    field in calibration_editor._REGISTRY:

      target=upper (default) — active mode stacked above a locked-ENGLISH copy
      (cross-reference) so the panel never butts the upper LCD bottom:
        +----------------+----------------+
        |  UPPER (active)|                |
        +----------------|   PARAM PANEL  |
        |  UPPER (EN)    |   (full height)|
        +----------------|                |
        |                |                |
        +----------------+----------------+

      target=lower — full LCD A (upper + lower) on the left:
        +----------------+----------------+
        |  UPPER LCD A   |                |
        |                |   PARAM PANEL  |
        +----------------+   (full height)|
        |  LOWER LCD A   |                |
        |                |                |
        +----------------+----------------+

    Window stays 2×S_WIDTH wide in both layouts. The cycler is locked so the
    lower view never rotates under the tuning; which view is pinned comes from
    the editor (`get_active_lower_view`, seeded by `--lower-view`, cycled with
    V), because lower elements are only reachable in the view they live in.
    """
    from app_paths import project_root
    from displays.base import DisplayMode

    # Dimensions come from the LOADED model's registry record, never from a
    # fixed import. A hardcoded one sizes the window for e235_0 while the sim
    # renders something else — the layout is then silently wrong rather than
    # broken, which is the whole reason --edit used to refuse other models.
    S_WIDTH = sim._train_model.s_width
    S_HEIGHT = sim._train_model.s_height
    UPPER_HEIGHT = sim._train_model.upper_height

    sys.path.insert(0, str(project_root() / "_dev_scripts"))
    import calibration_editor  # noqa: E402

    from constants import FRAME_RATE

    # Window doubled: left half = tuning target, right half = param panel.
    # _STACK_GAP separates the two upper-mode copies (target=upper layout) so
    # the locked-ENGLISH reference sits clearly below the active mode.
    _STACK_GAP = 12
    window = pygame.display.set_mode((2 * S_WIDTH, S_HEIGHT))
    lcd_a = window.subsurface((0, 0, S_WIDTH, S_HEIGHT))
    lcd_a_upper = window.subsurface((0, 0, S_WIDTH, UPPER_HEIGHT))
    lcd_en_upper = window.subsurface((0, UPPER_HEIGHT + _STACK_GAP, S_WIDTH, UPPER_HEIGHT))

    # Reference-image overlay (--overlay <path>). Loaded after set_mode so
    # convert_alpha() has a display surface. Toggled in-editor with `O`.
    if overlay_path is not None:
        p = Path(overlay_path)
        if not p.exists():
            print(f"[error] --overlay path not found: {p}")
            sys.exit(1)
        try:
            overlay_surf = pygame.image.load(str(p)).convert_alpha()
        except (pygame.error, OSError) as e:
            print(f"[error] failed to load --overlay image: {e}")
            sys.exit(1)
        calibration_editor.set_overlay(overlay_surf)
        print(f"[overlay] loaded {p.name} {overlay_surf.get_size()}  -- press O to toggle")

    def _set_upper_screens(screen):
        sim.upper.screen = screen
        sim.upper.japanese_display.screen = screen
        sim.upper.furigana_display.screen = screen
        sim.upper.english_display.screen = screen

    def _set_lower_screens(screen):
        sim.lower.screen = screen
        sim.lower.japanese_display.screen = screen
        sim.lower.japanese_eight_display.screen = screen
        sim.lower.english_display.screen = screen
        sim.lower.transfer_display.screen = screen

    _set_upper_screens(lcd_a)
    _set_lower_screens(lcd_a)
    sim.screen = lcd_a

    # Lower-LCD slot is pinned (scheduler off) and driven by the editor's
    # active view rather than fixed here — the route bar lives in the FULL
    # view, so a hardcoded EIGHT pin made it unreachable no matter what the
    # registry said. `--lower-view` seeds the starting view; V cycles it.
    _SLOT_FOR_VIEW = {
        "full": sim.lower._SLOT_FULL,
        "eight": sim.lower._SLOT_EIGHT,
        "transfer": sim.lower._SLOT_TRANSFER,
    }
    # Registry entries are per-model; bind BEFORE seeding the view, because
    # which lower views exist is itself filtered by the active model.
    calibration_editor.set_active_model(sim._train_model.key)
    if lower_view != "cycle":
        calibration_editor.set_active_lower_view(lower_view)
    sim.scheduler.enabled = False

    calibration_editor.enter_edit_mode(sim)

    clock = pygame.time.Clock()
    running = True
    while running:
        clock.tick(FRAME_RATE)
        timestamp = time.time()
        time_text = time.strftime("%H:%M", time.localtime(timestamp))

        # Re-pin every frame: V changes the editor's active view, and the slot
        # has to follow or the newly-reachable element still isn't drawn.
        sim.lower._current_slot = _SLOT_FOR_VIEW[calibration_editor.get_active_lower_view()]

        target = calibration_editor.get_focused_target()
        if target == "lower":
            # Left half = full LCD A (upper + lower); lower LCD is the target.
            _set_upper_screens(lcd_a)
            _set_lower_screens(lcd_a)
            sim.upper.draw(time_text)
            sim.lower.draw(0.0)
        else:
            # Left half = active mode stacked above a locked-ENGLISH copy.
            # Clear the column first so the gap + below-stack area stay black
            # (the two copies only fill their own 0..UPPER_HEIGHT regions).
            window.fill((0, 0, 0), pygame.Rect(0, 0, S_WIDTH, S_HEIGHT))
            _set_upper_screens(lcd_a_upper)
            sim.upper.draw(time_text)
            original_mode = sim.upper.mode_cycler.current_mode
            _set_upper_screens(lcd_en_upper)
            sim.upper.mode_cycler.current_mode = DisplayMode.ENGLISH
            try:
                sim.upper.draw(time_text)
            finally:
                sim.upper.mode_cycler.current_mode = original_mode
                _set_upper_screens(lcd_a)

        # Overlay paints the right-half panel + focused-element indicators on
        # the FULL window (indicators reach LCD A's top-left coord system).
        calibration_editor.draw_overlay(window)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if calibration_editor.handle_event(event, sim):
                continue
            # Other events ignored — sim is frozen.

        if calibration_editor.should_quit():
            running = False


if __name__ == "__main__":
    main()

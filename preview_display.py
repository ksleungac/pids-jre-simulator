"""Entry point for the audio-free PIDS preview.

Thin wrapper around `PASimulator(preview=True)`. Everything that isn't CLI
plumbing — route loading, state machine, drawing, input handling — lives in
app.py and is shared with the real application, so behavior can't drift.
The full swap inventory (audio, input, mixer-init, window-position) is
documented at `PASimulator.__init__`'s ``preview`` parameter.

Usage:
  uv run preview_display.py                                     # MOCK route (audio/_mock/main)
  uv run preview_display.py --route yamanote                    # real route by shorthand
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
shorthand like 'yamanote' / 'chuo/916H' (resolved under audio/).

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

import pygame

import app
from app import PASimulator
from displays.base import DisplayMode

DEFAULT_MOCK_ROUTE = "_mock/main"

MODE_MAP = {
    "kanji": DisplayMode.KANJI,
    "furigana": DisplayMode.FURIGANA,
    "english": DisplayMode.ENGLISH,
}

# Train-model registry — package paths under displays.train_models. Used by
# --model to swap the display classes that app.py imports at module-load
# time. The main app stays on e235_1000 (its top-level import is
# unchanged); preview rebinds app.UpperDisplay / app.LowerDisplay /
# app.S_WIDTH / app.S_HEIGHT before instantiating PASimulator.
MODEL_PACKAGES = {
    "e235_1000": "displays.train_models.e235_1000",
    "e235_0": "displays.train_models.e235_0",
}


def _resolve_work_dir(spec: str) -> str:
    """Resolve a --route arg into a work_dir (directory containing route.json).

    Accepts a path to route.json, a directory, or a shorthand like
    'yamanote' / 'chuo/916H' / '_mock/main' (probed under audio/).
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
        choices=list(MODEL_PACKAGES),
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
    return parser.parse_args()


def main():
    args = parse_args()

    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    # Swap app.py's bound display classes if --model picked something other
    # than the default e235_1000. Rebinding works because PASimulator looks
    # up `UpperDisplay` / `LowerDisplay` via app's module globals at call
    # time, not via captured locals from import time.
    if args.model != "e235_1000":
        model_pkg = importlib.import_module(MODEL_PACKAGES[args.model])
        app.UpperDisplay = model_pkg.UpperDisplay
        app.LowerDisplay = model_pkg.LowerDisplay
        app.S_WIDTH = model_pkg.S_WIDTH
        app.S_HEIGHT = model_pkg.S_HEIGHT

    if args.debug_grid:
        # Flip the chosen model's upper-LCD debug-grid toggle. Module-level
        # flag — must be set BEFORE pygame surfaces start rendering, but
        # after the module imports cleanly.
        _upper_lcd_mod = importlib.import_module(f"{MODEL_PACKAGES[args.model]}.upper_lcd")
        _upper_lcd_mod.DEBUG_GRID = True

    work_dir = _resolve_work_dir(args.route)
    print(f"[preview] work_dir={work_dir}")

    sim = PASimulator(work_dir, preview=True)

    # Initial position. jump_to_stop lands in STOPPING@target (at_station=True,
    # cnt_pa=0). --pa overrides that into a different prefix state for visual
    # iteration: 0=次は, 1=まもなく, 2=ただいま (STOPPING). Omitted leaves the
    # natural STOPPING landing.
    sim.jump_to_stop(args.stop)
    if args.pa is not None:
        forced = max(0, min(args.pa, 2))
        if forced == 2:
            sim.state.at_station = True
            sim.state.cnt_pa = 0
        else:
            sim.state.at_station = False
            sim.state.cnt_pa = forced
    sim.upper.set_state(sim.state.curr_stop, sim.state.cnt_pa, at_station=sim.state.at_station)

    # Force display mode if requested
    if args.mode:
        sim.upper.mode_cycler.current_mode = MODE_MAP[args.mode]
        sim.upper.mode_cycler.enabled = False

    # Force lower-LCD view by setting the slot directly + locking the cycler.
    # Without locking, the cycler would still tick in interactive mode and
    # rotate FULL → EIGHT → TRANSFER on its normal cadence; the forced slot
    # would only persist for the boot frame.
    if args.lower_view != "cycle":
        slot_map = {
            "full": sim.lower._SLOT_FULL,
            "eight": sim.lower._SLOT_EIGHT,
            "transfer": sim.lower._SLOT_TRANSFER,
        }
        sim.lower._current_slot = slot_map[args.lower_view]
        sim.lower._slot_start = None
        # Lock: replace cycler tick + at-station-edge handler with no-ops.
        sim.lower._tick_cycle = lambda current_time: None
        sim.lower._handle_at_station_edge = lambda state, current_time: None

    if args.screenshot:
        timestamp = time.time()
        sim.upper.update(timestamp)
        sim.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))
        # current_time=0.0 freezes the lower-LCD countdown at full values for
        # a readable static snapshot.
        sim.lower.draw(0.0)
        pygame.display.flip()
        pygame.image.save(sim.screen, args.screenshot)
        print(f"Screenshot saved to {args.screenshot}")
        sim.cleanup()
        return

    sim.run()
    sys.exit()


if __name__ == "__main__":
    main()

"""Screenshot tool for the OOBE tutorial — mirrors preview_chrome.py.

Renders one frame of the tutorial at a chosen step and saves to PNG. Catches
layout regressions without requiring a full interactive run.

Two modes:
  - ``--no-sim`` (default for headless smoke tests): chrome only, with an LCD
    placeholder rectangle. Doesn't require audio bundle.
  - sim mode (default): boots the real PASimulator on tokaido/1865E inside
    the tutorial window for a full render with the embedded LCD.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame  # noqa: E402

import i18n  # noqa: E402
from tutorial import BG_COLOR, LCD_H, LCD_W, LCD_X, LCD_Y, STEPS, Tutorial, WINDOW_H, WINDOW_W  # noqa: E402


def render(step: int = 1, lang: str = "en", out: str = "screenshot_tutorial.png", no_sim: bool = False, pre_action: bool = False) -> None:
    pygame.init()
    if not no_sim:
        pygame.mixer.init()
    pygame.display.set_mode((WINDOW_W, WINDOW_H))
    i18n.init(lang)

    screen = pygame.display.get_surface()
    tut = Tutorial(screen)
    tut.current_step = step
    # Spoof predicate inputs so the screenshot shows [Next] in its enabled
    # state (step 5's dwell timer "elapsed", action steps "fired"). Doesn't
    # mutate any sim state — purely affects the predicate readout.
    # ``pre_action`` flips ``_action_in_step`` back off — used to capture
    # mid-step UI cues that hide once the user has acted (e.g. step 8's
    # station-card illustration).
    tut.step_entered_at = time.time() - 10
    tut._action_in_step = not pre_action

    screen.fill(BG_COLOR)

    if no_sim:
        tut.lcd_surface = screen.subsurface((LCD_X, LCD_Y, LCD_W, LCD_H))
        # No-sim mode: render a flat dark rect where the LCD would go.
        pygame.draw.rect(screen, (20, 20, 24), pygame.Rect(LCD_X, LCD_Y, LCD_W, LCD_H))
    else:
        # Boot a real sim and render one frame inside the LCD sub-surface.
        from app import PASimulator
        tut.lcd_surface = screen.subsurface((LCD_X, LCD_Y, LCD_W, LCD_H))
        sim = PASimulator(
            work_dir=tut.tutorial_route_dir(),
            tutorial=True,
            target_surface=tut.lcd_surface,
        )
        sim.jump_to_stop(tut.BOOT_STOP_IDX)
        tut.sim = sim
        # Run the target step's entry_handler so steps with deterministic
        # entry state (e.g. step 8 → STOPPING@鴨宮) preview correctly. Steps
        # without an entry_handler are no-ops here.
        STEPS[step - 1].entry_handler(tut)
        ts = time.time()
        sim.state.update_skip_progress(ts)
        sim.upper.update(ts)
        sim.upper.draw(time.strftime("%H:%M", time.localtime(ts)))
        sim.lower.draw(ts)
        # Mirror _tick_sim's final overlay step so step-specific callouts
        # appear in the screenshot.
        tut._draw_callout()

    tut._draw_progress_bar()
    tut._draw_panel()
    pygame.image.save(screen, out)
    pygame.quit()
    print(f"saved -> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("step", type=int, nargs="?", default=1)
    p.add_argument("lang", nargs="?", default="en")
    p.add_argument("--no-sim", action="store_true", help="skip sim boot, render placeholder LCD")
    p.add_argument("--pre-action", action="store_true", help="render pre-action state (e.g. step 8 station-card before first click)")
    p.add_argument("--out", default="screenshot_tutorial.png")
    args = p.parse_args()
    render(step=args.step, lang=args.lang, out=args.out, no_sim=args.no_sim, pre_action=args.pre_action)

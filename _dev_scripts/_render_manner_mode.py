# SPDX-License-Identifier: MIT
"""Throwaway: what does the E233-0 manner-mode page draw, on its own?

The page is NOT wired into `LowerDisplay` yet, so `preview_display.py` cannot
reach it and there is no other way to get a still out of it. This drives the
PRODUCTION renderer — it constructs `MannerModeDisplay` and calls `show_stops`,
nothing is re-implemented here — onto a canvas-sized surface, so the output is
directly comparable with the reference through
`_dev_scripts/compare_fonts.py --overlay`.

Delete once the page is wired and `preview_display.py --lower-view` can reach it.

    uv run _dev_scripts/_render_manner_mode.py [out.png]
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame  # noqa: E402

from displays.train_models.e233_0 import LOWER_BG, S_HEIGHT, S_WIDTH, UPPER_BG, UPPER_HEIGHT  # noqa: E402
from displays.train_models.e233_0.manner_mode import MannerModeDisplay  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "screenshot_manner_mode.png"

pygame.init()
screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
screen.fill(UPPER_BG)
pygame.draw.rect(screen, LOWER_BG, pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT))

MannerModeDisplay(screen, {}, []).show_stops(None, 0.0)
pygame.image.save(screen, out)
print(f"wrote {out}")

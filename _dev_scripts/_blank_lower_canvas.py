# SPDX-License-Identifier: MIT
"""Throwaway: render E235-0 frame with upper LCD normal + lower LCD blank white.

Backdrop for tracing the Tier-2 mask PNG (Yamanote 5-station band) in
Photoshop. Lower area is filled WHITE_BG (matches the real 5-station view
background) with NO arc/stations drawn.

  uv run _dev_scripts/_blank_lower_canvas.py [out.png] [stop]
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame  # noqa: E402

import app  # noqa: E402
from app import PASimulator  # noqa: E402
from displays.base import DisplayMode  # noqa: E402
from displays.train_models import e235_0  # noqa: E402

# Rebind app's display classes to E235-0 (same trick preview_display.py uses).
app.UpperDisplay = e235_0.UpperDisplay
app.LowerDisplay = e235_0.LowerDisplay
app.S_WIDTH = e235_0.S_WIDTH
app.S_HEIGHT = e235_0.S_HEIGHT

out = sys.argv[1] if len(sys.argv) > 1 else "_blank_lower_e235_0.png"
stop = int(sys.argv[2]) if len(sys.argv) > 2 else 0

sim = PASimulator("audio/yamanote/1208G", preview=True)
sim.jump_to_stop(stop)
sim.upper.set_state(sim.state.curr_stop, sim.state.cnt_pa, at_station=sim.state.at_station)
sim.upper.mode_cycler.current_mode = DisplayMode.KANJI
sim.upper.mode_cycler.enabled = False

# Upper LCD as usual.
timestamp = time.time()
sim.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))

# Lower LCD blank: flat WHITE_BG over the lower area, nothing else.
lower_rect = pygame.Rect(0, e235_0.UPPER_HEIGHT, e235_0.S_WIDTH, e235_0.S_HEIGHT - e235_0.UPPER_HEIGHT)
sim.screen.fill(e235_0.WHITE_BG, lower_rect)

pygame.display.flip()
pygame.image.save(sim.screen, out)
print(f"saved {out}  ({e235_0.S_WIDTH}x{e235_0.S_HEIGHT}, lower blank from y={e235_0.UPPER_HEIGHT})")
sim.cleanup()

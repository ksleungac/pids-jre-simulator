"""Ad-hoc: tile the E235-0 5-station inline transfer panel for every Yamanote
stop into one montage PNG. Headless (SDL dummy), single sim, loops all stops.

Not shipped (`_` prefix). Run: uv run _dev_scripts/_montage_panels.py
"""

import math
import os
import sys
import time
from pathlib import Path

# Project root on sys.path — this dev script lives under _dev_scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["SDL_VIDEODRIVER"] = "dummy"

import importlib

import pygame

import app
from app import PASimulator

# Rebind app's display classes to E235-0 (same mechanism as preview_display).
pkg = importlib.import_module("displays.train_models.e235_0")
app.UpperDisplay = pkg.UpperDisplay
app.LowerDisplay = pkg.LowerDisplay
app.S_WIDTH = pkg.S_WIDTH
app.S_HEIGHT = pkg.S_HEIGHT
UPPER_HEIGHT = pkg.UPPER_HEIGHT
S_HEIGHT = pkg.S_HEIGHT

sim = PASimulator("audio/yamanote", preview=True)

# Pin lower LCD to the 5-station (EIGHT) slot; lock the cycler.
sim.lower._current_slot = sim.lower._SLOT_EIGHT
sim.scheduler.enabled = False

# Left strip width: panel can extend to the curve's widest control point
# (tp3_x) plus a col-2 entry, so size the crop from the live tuneables.
_tp = importlib.import_module("displays.train_models.e235_0.lower_lcd")._TUNEABLES_TRANSFER_PANEL
CROP_W = min(pkg.S_WIDTH, max(int(_tp["tp1_x"]), int(_tp["tp2_x"]), int(_tp["tp3_x"])) + 90)
LOWER_H = S_HEIGHT - UPPER_HEIGHT
LABEL_H = 18
COLS = 6
PAD = 6

stops = sim.stops
n = len(stops)
cells = []
label_font = pygame.font.Font(None, 18)

for i in range(n):
    sim.jump_to_stop(i)
    # Approaching (次は) — panel content is state-independent; this matches refs.
    sim.state.at_station = False
    sim.state.cnt_pa = 0
    sim.upper.set_state(sim.state.curr_stop, sim.state.cnt_pa, at_station=False)
    ts = time.time()
    sim.scheduler.tick(ts, sim.state)  # no-op while scheduler.enabled is False - mirrors app.run() order
    sim.upper.draw(time.strftime("%H:%M", time.localtime(ts)))
    sim.lower.draw(0.0)
    crop = sim.screen.subsurface((0, UPPER_HEIGHT, CROP_W, LOWER_H)).copy()
    cells.append((i, stops[i].get("name", "?"), crop))

rows = math.ceil(n / COLS)
cell_w = CROP_W + PAD
cell_h = LOWER_H + LABEL_H + PAD
montage = pygame.Surface((COLS * cell_w + PAD, rows * cell_h + PAD))
montage.fill((40, 40, 48))

for idx, (stop_i, name, crop) in enumerate(cells):
    r, c = divmod(idx, COLS)
    x = PAD + c * cell_w
    y = PAD + r * cell_h
    lbl = label_font.render(f"{stop_i}: {name}", True, (230, 230, 235))
    montage.blit(lbl, (x, y))
    montage.blit(crop, (x, y + LABEL_H))

out = "_panels_montage.png"
pygame.image.save(montage, out)
print(f"Saved {out}  ({n} stops, {COLS}x{rows} grid, {montage.get_size()})")
sim.cleanup()

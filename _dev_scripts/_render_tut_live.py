"""Dev harness: headless live render of the embedded TIMS tutorial to a PNG.

Reskin-loop preview tool. Dummy SDL drivers (no window/audio) + a cursor no-op
(the dummy video driver has no cursor subsystem, so set_cursor would raise).
Boots the real walkthrough into the shell's detail region and snapshots one
frame. --step jumps to a given step so the disabled/enabled button states and
per-step panel copy can be eyeballed. Not shipped (_dev_scripts/).

    uv run _dev_scripts/_render_tut_live.py [out.png] [--lang zh_HK] [--step N]
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, ".")

import argparse  # noqa: E402

import pygame  # noqa: E402

pygame.init()
pygame.font.init()
pygame.mouse.set_cursor = lambda *a, **k: None  # dummy video driver has no cursor subsystem

import i18n  # noqa: E402
from tutorial_tims import WINDOW_SIZE, TimsTutorial  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default="_tut_live.png")
ap.add_argument("--lang", default="zh_HK")
ap.add_argument("--step", type=int, default=None, help="jump the walkthrough to step N (1..8)")
args = ap.parse_args()

i18n.init(args.lang)
screen = pygame.display.set_mode(WINDOW_SIZE)
tut = TimsTutorial(screen, live=True)
tut._ensure_walkthrough()
if args.step is not None and tut._walkthrough is not None:
    tut._walkthrough._jump_to_step(args.step)
tut.render(screen)
pygame.image.save(screen, args.out)
print(f"saved {args.out} {WINDOW_SIZE[0]}x{WINDOW_SIZE[1]} lang={args.lang} step={args.step}")

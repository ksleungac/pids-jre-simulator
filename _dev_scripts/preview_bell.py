# SPDX-License-Identifier: MIT
"""Render the departure-bell box in every state, for eyeballing against the photo.

    uv run _dev_scripts/preview_bell.py                    # the state strip
    uv run _dev_scripts/preview_bell.py --zoom 3           # bigger
    uv run _dev_scripts/preview_bell.py --compare          # + reference beside it
    uv run _dev_scripts/preview_bell.py --state ringing    # one state, large

Writes `screenshot_bell*.png` at the repo root — that is where the author opens
them from, and the root `.gitignore` already keeps `screenshot_*.png` untracked.

The strip is the point: states 1, 5, 6 and 7 of the design all draw identically
(the real box has no lamp, so ON being in is its whole display), and putting
them side by side is what shows whether in-versus-out reads at a glance.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

import departure_bell as bell  # noqa: E402

REFERENCE = Path(__file__).resolve().parent.parent / "_references" / "bell" / "sta-bell.jpg"

# Label -> state. Ordered as a conductor meets them.
STATES = {
    "ready": bell.BellState(),
    "ON pressed": bell.BellState(on_flash=True),
    "ringing": bell.BellState(on_latched=True),
    "OFF pressed": bell.BellState(on_latched=False, off_flash=True),
}


def _label_font(size: int):
    return pygame.font.Font(None, size)


def strip(zoom: int, states: dict) -> pygame.Surface:
    pad, cap_h = 16 * 1, 22
    tiles = [(name, pygame.transform.scale_by(bell.render(st), zoom)) for name, st in states.items()]
    tw, th = tiles[0][1].get_size()
    out = pygame.Surface((pad + (tw + pad) * len(tiles), pad + th + cap_h + pad))
    out.fill((18, 20, 24))
    font = _label_font(cap_h)
    for i, (name, tile) in enumerate(tiles):
        x = pad + (tw + pad) * i
        out.blit(tile, (x, pad))
        ink = font.render(name, True, (200, 205, 212))
        out.blit(ink, ink.get_rect(midtop=(x + tw // 2, pad + th + 4)))
    return out


def beside_reference(render: pygame.Surface) -> pygame.Surface:
    """Reference photo and render at the SAME height, side by side.

    Height-aligned rather than width-aligned: the box is the subject in both, so
    matching its height is what makes proportions comparable (visual-adjust
    skill, § Side-by-side composites).
    """
    ref = pygame.image.load(str(REFERENCE)).convert()
    h = render.get_height()
    rw = int(ref.get_width() * h / ref.get_height())
    ref = pygame.transform.smoothscale(ref, (rw, h))
    pad = 16
    out = pygame.Surface((pad * 3 + rw + render.get_width(), h + pad * 2))
    out.fill((18, 20, 24))
    out.blit(ref, (pad, pad))
    out.blit(render, (pad * 2 + rw, pad))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoom", type=int, default=2)
    ap.add_argument("--compare", action="store_true", help="stack the reference photo beside it")
    ap.add_argument("--state", choices=sorted(STATES), help="render one state only")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1))

    picked = {args.state: STATES[args.state]} if args.state else STATES
    img = strip(args.zoom, picked)
    if args.compare:
        img = beside_reference(img)

    out = args.out or (f"screenshot_bell_{args.state}.png" if args.state else "screenshot_bell.png")
    pygame.image.save(img, out)
    print(f"{out}  {img.get_size()[0]}x{img.get_size()[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""DEV eval — Noto Sans JP, NATIVE x1, AA OFF, sweep 12..36px. No upscaling (x2 thickens too much).
Confirms the locked rule: render native 1x at the raw display px, all the way to the ~32-36px ceiling.

  uv run _dev_scripts/_noto_size_ladder.py --screenshot _noto_size_ladder.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

FACE = project_root() / "_dev_scripts" / "_fonts_eval" / "NotoSansJP.ttf"
F = project_root() / "fonts"
WORD = "報知設定 山手線 ABC 123"
INK = (236, 241, 246)
CAP = (150, 162, 174)
BG = (26, 30, 38)
SIZES = [12, 16, 20, 24, 28, 32, 34, 36, 38, 40, 42, 44]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", default="_noto_size_ladder.png")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    capf = pygame.font.Font(str(F / "ArkPixel12pxMono-Latin.otf"), 12)

    rows = [(s, pygame.font.Font(str(FACE), s).render(WORD, False, INK)) for s in SIZES]
    pad, capw, vgap = 16, 70, 12
    W = pad * 2 + capw + max(g.get_width() for _, g in rows)
    H = pad * 2 + sum(max(g.get_height(), 14) + vgap for _, g in rows)
    surf = pygame.Surface((W, H))
    surf.fill(BG)
    y = pad
    for s, g in rows:
        surf.blit(capf.render(f"{s}px 1x", False, CAP), (pad, y + max(0, (g.get_height() - 12) // 2)))
        surf.blit(g, (pad + capw, y))
        y += max(g.get_height(), 14) + vgap

    out = str(project_root() / args.screenshot)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({W}x{H})")


if __name__ == "__main__":
    main()

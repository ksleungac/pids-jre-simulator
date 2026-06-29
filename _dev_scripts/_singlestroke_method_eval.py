"""DEV eval — demonstrate the SINGLE-STROKE + NEAREST-UPSCALE method on a NORMAL font (MS Gothic).

The method (user's framing, 2026-06-26): don't hunt a dedicated pixel font. Take a normal font, render
it AA-OFF at a small base size where strokes are ~1px ("single-stroke drawing"), then NEAREST-upscale by
an integer k for larger display sizes. Strokes stay k-px-wide in grid units → crisp pixel look at every
size, with the font's own glyph SHAPES (MS Gothic) instead of a pixel font's.

Compares, per target display height:
  - MS Gothic native AA-ON   (the "normal / thick" look we're avoiding)
  - MS Gothic native AA-OFF  (sub-grid: uneven, strokes too heavy small)
  - MS Gothic 12px master × k (pure single-stroke; least kanji detail)
  - MS Gothic 16px master × k (more strike detail; some 2px strokes)

  uv run _dev_scripts/_singlestroke_method_eval.py --screenshot _singlestroke_method.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

MSG = "C:/Windows/Fonts/msgothic.ttc"  # DEV-only system font, never shipped
WORD = "報知設定 山手線 鶯谷 ABC 123"
INK = (236, 241, 246)
CAP = (150, 162, 174)
SUB = (110, 120, 132)
BG = (26, 30, 38)


def native(size, aa):
    return pygame.font.Font(MSG, size).render(WORD, aa, INK, BG if aa else None)


def upscaled(master, k):
    g = pygame.font.Font(MSG, master).render(WORD, False, INK)  # AA OFF → 1-bit strike
    return pygame.transform.scale(g, (g.get_width() * k, g.get_height() * k))


def n_colors(surf):
    seen = set()
    for x in range(0, surf.get_width(), 2):
        for y in range(0, surf.get_height(), 2):
            seen.add(surf.get_at((x, y))[:3])
    return len(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH", default="_singlestroke_method.png")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()

    rows = []  # (caption, subcaption, surface)
    # method rows: 12px and 16px masters, upscaled k=2,3,4
    for master in (12, 16):
        strike = "BITMAP-strike" if n_colors(pygame.font.Font(MSG, master).render(WORD, True, (255, 255, 255), (0, 0, 0))) <= 2 else "outline"
        for k in (2, 3, 4):
            g = upscaled(master, k)
            rows.append((f"MSGothic {master}px master  ×{k}  → {g.get_height()}px", f"single-stroke + nearest-upscale  ({strike} master)", g))
    # contrast rows: native big AA-on / AA-off at comparable display sizes
    for size in (24, 32, 48):
        rows.append((f"MSGothic native {size}px  AA-ON", "the 'normal/thick' look we avoid", native(size, True)))
        rows.append((f"MSGothic native {size}px  AA-OFF", "sub-grid: strokes too heavy, uneven", native(size, False)))

    pad, capw, gap = 14, 360, 10
    W = capw + max(s.get_width() for *_, s in rows) + pad * 2
    H = sum(s.get_height() + gap for *_, s in rows) + pad * 2
    surf = pygame.Surface((W, H))
    surf.fill(BG)
    capfont = pygame.font.Font(MSG, 15)
    subfont = pygame.font.Font(MSG, 12)
    y = pad
    for cap, sub, s in rows:
        surf.blit(capfont.render(cap, True, CAP), (pad, y + 2))
        surf.blit(subfont.render(sub, True, SUB), (pad, y + 22))
        surf.blit(s, (capw, y + max(0, (40 - s.get_height()) // 2) if s.get_height() < 40 else y))
        # place glyph row vertically; if tall, just top-align next to caption
        y += max(s.get_height(), 44) + gap

    out = str(project_root() / args.screenshot)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({W}x{H})")


if __name__ == "__main__":
    main()

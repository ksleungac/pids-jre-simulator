"""DEV eval — Noto Sans JP TIMS numerals: wide full-width glyph DESIGN, but packed tighter than the
fat full-width em cell (user: full-width spacing too wide). Native x1, AA OFF.

Packer: render each full-width digit (U+FF10..19), measure its ink width, lay digits on a MONOSPACE
cell = max_ink_width + gap, glyph ink centered in the cell. `gap` tunes density (can be negative).
Non-digit chars (':' '.' 'k' 'm' '/' 'h') render naturally inline. Shows a gap sweep + the clock /
speed / distance samples from tims_002.

  uv run _dev_scripts/_noto_numbers.py --screenshot _noto_numbers.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

FACE = project_root() / "_dev_scripts" / "_fonts_eval" / "NotoSansJP.ttf"
F = project_root() / "fonts"
INK = (236, 241, 246)
CAP = (150, 162, 174)
HDR = (190, 200, 212)
BG = (26, 30, 38)


def ink_x(s):
    cols = [x for x in range(s.get_width()) if any(s.get_at((x, y))[0] > 40 for y in range(s.get_height()))]
    return (min(cols), max(cols)) if cols else (0, s.get_width() - 1)


def tims_number(text, size, gap, fullwidth=True):
    """DIGITS -> full-width glyph on a monospace cell (cell = max digit ink + gap, ink centered).
    EVERYTHING ELSE (separators :. and unit letters km/h) -> natural HALF-WIDTH inline."""
    fnt = pygame.font.Font(str(FACE), size)
    dig = {d: fnt.render(chr(0xFF10 + int(d)) if fullwidth else d, False, INK) for d in "0123456789"}
    iw = {d: ink_x(g) for d, g in dig.items()}
    cell = max(x1 - x0 + 1 for x0, x1 in iw.values()) + gap
    h = fnt.get_height()

    pieces = []  # (surface, width)
    for ch in text:
        if ch.isdigit():  # full-width digit on monospace cell
            cs = pygame.Surface((cell, h))
            cs.fill(BG)
            g = dig[ch]
            x0, x1 = iw[ch]
            cs.blit(g, (int(cell / 2 - (x0 + x1) / 2), 0))
            pieces.append((cs, cell))
        else:  # separator / unit letter -> natural half-width
            g = fnt.render(ch, False, INK)
            pieces.append((g, g.get_width()))
    out = pygame.Surface((sum(w for _, w in pieces), h))
    out.fill(BG)
    x = 0
    for s, w in pieces:
        out.blit(s, (x, 0))
        x += w
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", default="_noto_numbers.png")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    capf = pygame.font.Font(str(F / "ArkPixel12pxMono-Latin.otf"), 12)

    SZ = 32  # native px, AA off
    blocks = []
    blocks.append(("full-width DEFAULT (too wide)", pygame.font.Font(str(FACE), SZ).render("０９５１２３", False, INK)))
    for gap in (-2, 0, 2, 4):
        blocks.append((f"FW glyph, cell=ink{'+' if gap >= 0 else ''}{gap}", tims_number("095123", SZ, gap)))
    blocks.append(("half-width DEFAULT", pygame.font.Font(str(FACE), SZ).render("095123", False, INK)))
    blocks.append(("--- samples @ cell=ink+2 ---", None))
    blocks.append(("clock 12:03:15", tims_number("12:03:15", SZ, 2)))
    blocks.append(("speed 3km/h", tims_number("3km/h", SZ, 2)))
    blocks.append(("distance 2.1km", tims_number("2.1km", SZ, 2)))

    pad, capw, vgap = 18, 230, 14
    rows = [(lab, g) for lab, g in blocks]
    W = pad * 2 + capw + max((g.get_width() for _, g in rows if g), default=200)
    H = pad * 2 + sum((g.get_height() if g else 18) + vgap for _, g in rows)
    surf = pygame.Surface((W, H))
    surf.fill(BG)
    y = pad
    for lab, g in rows:
        col = HDR if g is None else CAP
        gy = max(0, (g.get_height() - 12) // 2) if g else 0
        surf.blit(capf.render(lab, False, col), (pad, y + gy))
        if g:
            surf.blit(g, (pad + capw, y))
        y += (g.get_height() if g else 18) + vgap

    out = str(project_root() / args.screenshot)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({W}x{H})")


if __name__ == "__main__":
    main()

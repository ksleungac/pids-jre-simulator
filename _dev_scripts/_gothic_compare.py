"""DEV eval — compare SHIPPABLE gothic fonts under the single-stroke + nearest-upscale method, against
MS Gothic (the target look, non-shippable) and Ark mono (the rejected pixel font).

Method per font: render AA-OFF at a small base size (single-stroke 1-bit), NEAREST-upscale by integer k.
Columns = method variants (16px×2, 16px×3, 12px×3). Rows = fonts. The question the image answers:
which shippable gothic, rendered this way, looks closest to MS Gothic rendered the same way?

  uv run _dev_scripts/_gothic_compare.py --screenshot _gothic_compare.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

E = project_root() / "_dev_scripts" / "_fonts_eval"
F = project_root() / "fonts"

# (label, path, coverage-note)
FONTS = [
    ("MS Gothic  (TARGET — system-only, has bitmap strikes)", "C:/Windows/Fonts/msgothic.ttc", "JP only (zh_CN tofu)"),
    ("BIZ UDGothic  (Morisawa UD, OFL, shippable)", E / "BIZUDGothic-Regular.ttf", "JP only"),
    ("Noto Sans JP  (OFL, shippable; family has SC/TC)", E / "NotoSansJP.ttf", "JP (Noto SC/TC cover zh)"),
    ("M PLUS 1 Code  (OFL, monospace — TIMS-like)", E / "MPLUS1Code.ttf", "JP only"),
    ("Ark Pixel 12 mono  (current shipped — REJECTED)", F / "ArkPixel12pxMono-zh_HK.otf", "per-locale, no strikes"),
]
WORD = "報知設定 山手線 鶯谷 ABC 123"
INK = (236, 241, 246)
CAP = (160, 172, 184)
SUB = (110, 120, 132)
BG = (26, 30, 38)
VARIANTS = [(12, 2), (16, 2), (20, 2), (24, 2)]  # (base_px, k) — AA off, k=2 cap, displays 24/32/40/48px


def upscaled(path, base, k):
    try:
        g = pygame.font.Font(str(path), base).render(WORD, False, INK)  # AA OFF
    except Exception as e:
        s = pygame.Surface((300, base * k))
        s.fill((60, 20, 20))
        return s
    return pygame.transform.scale(g, (g.get_width() * k, g.get_height() * k))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", default="_gothic_compare.png")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()

    capf = pygame.font.Font(str(F / "ArkPixel12pxMono-Latin.otf"), 13)
    subf = pygame.font.Font(str(F / "ArkPixel12pxMono-Latin.otf"), 11)

    pad, gap, vgap = 16, 26, 22
    cells = {}  # (fi, vi) -> surface
    for fi, (_, path, _) in enumerate(FONTS):
        for vi, (base, k) in enumerate(VARIANTS):
            cells[(fi, vi)] = upscaled(path, base, k)

    col_w = [max(cells[(fi, vi)].get_width() for fi in range(len(FONTS))) for vi in range(len(VARIANTS))]
    row_h = [max(cells[(fi, vi)].get_height() for vi in range(len(VARIANTS))) for fi in range(len(FONTS))]

    W = pad * 2 + sum(col_w) + gap * (len(VARIANTS) - 1)
    H = pad * 2 + sum(row_h) + (len(FONTS)) * (26 + vgap)  # +caption per row
    surf = pygame.Surface((W, H))
    surf.fill(BG)

    # column headers
    y = pad
    x = pad
    for vi, (base, k) in enumerate(VARIANTS):
        surf.blit(subf.render(f"{base}px master x{k} = {base*k}px", False, SUB), (x, y))
        x += col_w[vi] + gap
    y += 22

    for fi, (label, _, cov) in enumerate(FONTS):
        surf.blit(capf.render(label, False, CAP), (pad, y))
        surf.blit(subf.render(cov, False, SUB), (pad, y + 15))
        y += 30
        x = pad
        for vi in range(len(VARIANTS)):
            g = cells[(fi, vi)]
            surf.blit(g, (x, y))
            x += col_w[vi] + gap
        y += row_h[fi] + vgap

    out = str(project_root() / args.screenshot)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({W}x{H})")


if __name__ == "__main__":
    main()

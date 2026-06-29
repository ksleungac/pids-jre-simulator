"""DEV eval — confirm the Noto Sans family across the app's 3 locales under the single-stroke method,
and demonstrate WHY the per-locale siblings are needed (Noto Sans JP on Chinese = Han-unified / tofu).

Strings are REAL app chrome (data/translations_app.json). Method: AA OFF, base 16px, nearest x2 = 32px.

  uv run _dev_scripts/_noto_locale_check.py --screenshot _noto_locale_check.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

E = project_root() / "_dev_scripts" / "_fonts_eval"
F = project_root() / "fonts"
JP = "国府津 鴨宮 山手線 鶯谷"  # station names — ALWAYS Japanese
TC = "選擇路線 教學 自動報站 儲存駕駛記錄"  # zh_HK chrome
SC = "选择路线 教程 自动报站 保存速度曲线"  # zh_CN chrome
INK = (236, 241, 246)
CAP = (160, 172, 184)
WARN = (228, 150, 90)
BG = (26, 30, 38)
BASE, K = 16, 2

ROWS = [
    ("JP station names  ->  Noto Sans JP", JP, "NotoSansJP.ttf", CAP),
    ("zh_HK chrome  ->  Noto Sans TC   (correct)", TC, "NotoSansTC.ttf", CAP),
    ("zh_HK chrome  ->  Noto Sans JP   (WRONG: JP glyph variants)", TC, "NotoSansJP.ttf", WARN),
    ("zh_CN chrome  ->  Noto Sans SC   (correct)", SC, "NotoSansSC.ttf", CAP),
    ("zh_CN chrome  ->  Noto Sans JP   (WRONG: tofu / unified)", SC, "NotoSansJP.ttf", WARN),
]


def render(path, text):
    g = pygame.font.Font(str(E / path), BASE).render(text, False, INK)
    return pygame.transform.scale(g, (g.get_width() * K, g.get_height() * K))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", default="_noto_locale_check.png")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    capf = pygame.font.Font(str(F / "ArkPixel12pxMono-Latin.otf"), 13)

    glyphs = [(cap, render(p, t), col) for cap, t, p, col in ROWS]
    pad, vgap = 18, 16
    W = pad * 2 + max(g.get_width() for _, g, _ in glyphs)
    H = pad * 2 + sum(g.get_height() + 20 + vgap for _, g, _ in glyphs)
    surf = pygame.Surface((W, H))
    surf.fill(BG)
    y = pad
    for cap, g, col in glyphs:
        surf.blit(capf.render(cap, False, col), (pad, y))
        y += 20
        surf.blit(g, (pad, y))
        y += g.get_height() + vgap

    out = str(project_root() / args.screenshot)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({W}x{H})")


if __name__ == "__main__":
    main()

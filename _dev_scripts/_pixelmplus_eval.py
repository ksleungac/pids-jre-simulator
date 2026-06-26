"""DEV eval — PixelMplus12/10 vs the shipped Ark-12px-mono, on (a) GLYPH COVERAGE of the band's
actual JA + zh_HK strings and (b) kanji-DETAIL at crisp native, nearest-upscaled ×5 so the dot grid
is inspectable.

PixelMplus is a JAPANESE (JIS X 0208) font — the coverage probe is the decisive structural test:
the band chrome is per-locale (en / zh_HK / zh_CN), so a JA-only face can at best upgrade the JA
locale + the always-Japanese station names, NOT drop-in-replace the per-locale Ark set.

  uv run _dev_scripts/_pixelmplus_eval.py                       # coverage probe -> stdout
  uv run _dev_scripts/_pixelmplus_eval.py --screenshot _pixelmplus.png   # + detail render
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

E = project_root() / "_dev_scripts" / "_fonts_eval"
ARK = E / "ark-pixel-font-12px-monospaced-otf-v2026.05.07" / "ark-pixel-12px-monospaced-ja.otf"
ARK_HK = E / "ark-pixel-font-12px-monospaced-otf-v2026.05.07" / "ark-pixel-12px-monospaced-zh_hk.otf"
PM12 = E / "PixelMplus-20130602" / "PixelMplus-20130602" / "PixelMplus12-Regular.ttf"
PM12B = E / "PixelMplus-20130602" / "PixelMplus-20130602" / "PixelMplus12-Bold.ttf"
PM10 = E / "PixelMplus-20130602" / "PixelMplus-20130602" / "PixelMplus10-Regular.ttf"
PM10B = E / "PixelMplus-20130602" / "PixelMplus-20130602" / "PixelMplus10-Bold.ttf"

# The strings the band ACTUALLY renders (from data/translations_app.json + station names).
JA_NAMES = "報知設定 恵比寿 東京 渋谷 次は"  # always-Japanese station names + a dense word
HK_CHROME = "暫停 儲存記錄 返回主頁 重新對齊中 自動播放 自動報站 已暫停 停車位置 下一站 到站 停站"
CN_CHROME = "暂停 储存记录 返回主页 重新对齐中 自动播放 自动报站 已暂停 停车位置 闲置 出发中 即将抵达"


def _has_glyph(path, ch):
    """RENDER is truth: metrics() returns the .notdef box even when absent, so compare the rendered
    glyph to the rendered .notdef tofu. Identical pixels => missing."""
    f = pygame.font.Font(str(path), 24)
    g = f.render(ch, False, (255, 255, 255))
    notdef = f.render("", False, (255, 255, 255))  # PUA -> guaranteed .notdef
    if g.get_size() != notdef.get_size():
        return True
    a = pygame.image.tostring(g, "RGB")
    b = pygame.image.tostring(notdef, "RGB")
    return a != b


def _probe(label, path, text):
    chars = [c for c in text if c.strip()]
    missing = [c for c in chars if not _has_glyph(path, c)]
    cov = 100 * (len(chars) - len(missing)) / len(chars)
    print(f"  {label:18} {cov:5.1f}%  missing={''.join(missing) or 'none'}")


def coverage():
    print("\n== JA station names + dense word ==  [" + JA_NAMES + "]")
    _probe("Ark-12mono-ja", ARK, JA_NAMES)
    _probe("PixelMplus12", PM12, JA_NAMES)
    _probe("PixelMplus10", PM10, JA_NAMES)
    print("\n== zh_HK chrome labels ==  [" + HK_CHROME + "]")
    _probe("Ark-12mono-zh_hk", ARK_HK, HK_CHROME)
    _probe("PixelMplus12", PM12, HK_CHROME)
    _probe("PixelMplus10", PM10, HK_CHROME)
    print("\n== zh_CN chrome labels (Simplified) ==  [" + CN_CHROME + "]")
    _probe("PixelMplus12", PM12, CN_CHROME)


# ---- detail render ----
INK = (236, 241, 246)
GREEN = (54, 230, 64)
CAP = (150, 162, 174)
ZOOM = 5
WORD, STA, MIX, NUM = "報知設定", "恵比寿", "次は東京", "1750"
ROWS = [
    ("Ark-12mono  nat12", ARK, 12),
    ("PixelMplus12 R nat12", PM12, 12),
    ("PixelMplus12 B nat12", PM12B, 12),
    ("PixelMplus10 R nat10", PM10, 10),
    ("PixelMplus10 B nat10", PM10B, 10),
]
CAP_W = 230
ROW_H = 92


def _crisp(path, size, text, color):
    g = pygame.font.Font(str(path), size).render(text, False, color)  # AA OFF -> crisp dots
    return pygame.transform.scale(g, (g.get_width() * ZOOM, g.get_height() * ZOOM))  # nearest


def render(surf):
    surf.fill((26, 30, 38))
    cap = pygame.font.Font(str(ARK), 12)
    cols_x = [CAP_W, CAP_W + 290, CAP_W + 540, CAP_W + 820]
    samples = [(WORD, INK), (STA, GREEN), (MIX, INK), (NUM, INK)]
    for i, (label, path, size) in enumerate(ROWS):
        y = i * ROW_H
        pygame.draw.line(surf, (40, 48, 60), (0, y + ROW_H - 1), (surf.get_width(), y + ROW_H - 1), 1)
        surf.blit(cap.render(label, False, CAP), (12, y + ROW_H // 2 - 6))
        for (text, color), cx in zip(samples, cols_x):
            g = _crisp(path, size, text, color)
            surf.blit(g, (cx, y + (ROW_H - g.get_height()) // 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    coverage()
    if args.screenshot:
        W = CAP_W + 540 + 280
        surf = pygame.Surface((W, ROW_H * len(ROWS)))
        render(surf)
        out = str(project_root() / args.screenshot)
        pygame.image.save(surf, out)
        print(f"\nsaved {out}  ({W}x{ROW_H * len(ROWS)}, nearest ×{ZOOM})")


if __name__ == "__main__":
    main()

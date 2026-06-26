"""DEV eval — Ark 12px-grid vs 16px-grid kanji DETAIL.

Per the Motoya embedded-font page (https://www.motoyafont.jp/embedded-font/bitmap.html): real embedded
Japanese fonts are hand-designed bitmaps, a SEPARATE design per dot-grid (12/16/24/…), pure bitmap, no
anti-alias. So kanji detail is bounded by the GRID THE GLYPH WAS DESIGNED AT — not the size you render
it. Upscaling / supersampling the 12px source can't recover strokes it never had.

This puts the 12px-monospaced face we ship against the 16px-proportional face (more strokes per kanji)
on DENSE Japanese kanji, crisp (nearest) vs supersampled (smooth). Uses the `ja` variants because the
concern is the Japanese forms; zh_HK renders analogously.

  uv run _dev_scripts/_ark_detail_eval.py --screenshot _ark_detail.png
"""

import argparse
import sys

import pygame

sys.path.insert(0, ".")

from app_paths import project_root  # noqa: E402

EVAL = project_root() / "_dev_scripts" / "_fonts_eval"
F12 = EVAL / "ark-pixel-font-12px-monospaced-otf-v2026.05.07" / "ark-pixel-12px-monospaced-ja.otf"
F16 = EVAL / "ark-pixel-font-16px-proportional-otf-v2026.05.07" / "ark-pixel-16px-proportional-ja.otf"

BAND_BG = (8, 10, 14)
INK = (236, 241, 246)
GREEN = (54, 230, 64)
CAP = (150, 162, 174)
GRID = (40, 48, 60)

W = 820
ROW_H = 66
CAP_X = 12
WORD_X = 205  # dense kanji button word
NOTIF_X = 480  # dense kanji station name (green)
NUM_X = 710  # numerals

WORD = "報知設定"  # 報/知/設 are stroke-dense — the worst case for a small grid
NOTIF = "恵比寿"  # a real (dense) station name
NUM = "75"

# (caption, method, font_path, a, b)
#   UP -> a = native px, b = integer k         (render native AA-off, nearest ×k)
#   SS -> a = big native px, b = target px       (render a AA-on, smoothscale to b)
ROWS = [
    ("12mono nat 12", "UP", F12, 12, 1),
    ("12mono x2 = 24", "UP", F12, 12, 2),
    ("12mono ss 96>24", "SS", F12, 96, 24),
    ("- 16px grid (more strokes per kanji) -", "HDR", None, 0, 0),
    ("16prop nat 16", "UP", F16, 16, 1),
    ("16prop x2 = 32", "UP", F16, 16, 2),
    ("16prop ss 64>24", "SS", F16, 64, 24),
    ("16prop ss 96>32", "SS", F16, 96, 32),
]


def _font(path, size):
    return pygame.font.Font(str(path), size)


def _blit_up(surf, path, text, x, y, native, k, color):
    font = _font(path, native)
    g = font.render(text, False, color)  # AA OFF — crisp pixels
    if k != 1:
        g = pygame.transform.scale(g, (g.get_width() * k, g.get_height() * k))  # nearest
    surf.blit(g, (x, y + (ROW_H - g.get_height()) // 2))


def _blit_ss(surf, path, text, x, y, big, target, color):
    font = _font(path, big)
    g = font.render(text, True, color)  # AA ON
    if g.get_width() == 0:
        return
    s = target / font.get_height()
    g = pygame.transform.smoothscale(g, (max(1, round(g.get_width() * s)), max(1, round(g.get_height() * s))))
    surf.blit(g, (x, y + (ROW_H - g.get_height()) // 2))


def render(surf):
    surf.fill((26, 30, 38))
    cap = _font(F12, 12)
    y = 0
    for caption, method, path, a, b in ROWS:
        row = pygame.Rect(0, y, W, ROW_H)
        if method == "HDR":
            pygame.draw.rect(surf, (18, 21, 27), row)
            surf.blit(cap.render(caption, False, CAP), (CAP_X, y + (ROW_H - 12) // 2))
            y += ROW_H
            continue
        pygame.draw.rect(surf, BAND_BG, row)
        pygame.draw.line(surf, GRID, (0, y + ROW_H - 1), (W, y + ROW_H - 1), 1)
        surf.blit(cap.render(caption, False, CAP), (CAP_X, y + (ROW_H - 12) // 2))
        if method == "UP":
            _blit_up(surf, path, WORD, WORD_X, y, a, b, INK)
            _blit_up(surf, path, NOTIF, NOTIF_X, y, a, b, GREEN)
            _blit_up(surf, path, NUM, NUM_X, y, a, b, INK)
        else:
            _blit_ss(surf, path, WORD, WORD_X, y, a, b, INK)
            _blit_ss(surf, path, NOTIF, NOTIF_X, y, a, b, GREEN)
            _blit_ss(surf, path, NUM, NUM_X, y, a, b, INK)
        y += ROW_H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    h = ROW_H * len(ROWS)
    if args.screenshot:
        surf = pygame.Surface((W, h))
        render(surf)
        out = str(project_root() / args.screenshot)
        pygame.image.save(surf, out)
        print(f"saved {out}  ({W}x{h})")
    else:
        screen = pygame.display.set_mode((W, h))
        pygame.display.set_caption("Ark 12 vs 16 grid detail")
        render(screen)
        pygame.display.flip()
        running = True
        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    running = False
        pygame.quit()


if __name__ == "__main__":
    main()

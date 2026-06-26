"""DEV eval — can the SUPERSAMPLE-DOWN technique UNLOCK larger Ark Pixel chrome text while keeping it
fine (the real TIMS face is pixel-based but NOT squary — still fine, not hard blocks, not desktop-
smooth either)?

Framed in the k-multiplier model the user uses:
  * UP  (integer k >= 1)  — render at native px, antialias OFF, nearest ×k. k>1 hard-doubles every
                            pixel; bigger k = chunkier "squary" blocks. The thing we're escaping.
  * SS  (HIGH native, SUB-1 k) — render BIG (e.g. 48px) with antialias ON, then smoothscale DOWN to
                            the target (e.g. 24px = k 0.50). Anti-aliased edges → pixel shapes that
                            stay FINE at large sizes. This is "render 48, show 24".

Each SS row's caption gives the effective sub-1 k (target / big-native).

  uv run _dev_scripts/_ark_size_eval.py
  uv run _dev_scripts/_ark_size_eval.py --screenshot _ark_eval.png
"""

import argparse
import sys

import pygame

sys.path.insert(0, ".")

import i18n  # noqa: E402
from app_paths import project_root  # noqa: E402
from widgets import draw_lowres_text  # noqa: E402

BAND_BG = (8, 10, 14)
INK = (236, 241, 246)
GREEN = (54, 230, 64)
CAP_INK = (150, 162, 174)
ROW_GRID = (40, 48, 60)

W = 980
ROW_H = 62
CAP_X = 12
WORD_X = 180  # CJK button word
NOTIF_X = 470  # green katakana
NUM_X = 740  # numerals

SAMPLE_WORD = "返回主頁"
SAMPLE_NOTIF = "ジョウホウ"
SAMPLE_NUM = "75"

# (caption, method, a, b)
#   UP -> a = native px, b = integer k         (final = native*k, antialias off, nearest)
#   SS -> a = big native px, b = target px      (render a AA-on, smoothscale to b; effective k = b/a)
ROWS = [
    ("ref  12x1 = 12", "UP", 12, 1),
    ("- nearest upscale (squary) -", "HDR", 0, 0),
    ("up  12 x2 = 24", "UP", 12, 2),
    ("up  12 x4 = 48", "UP", 12, 4),
    ("- supersample k0.50 (2x) -", "HDR", 0, 0),
    ("ss  48 ->24  k0.50", "SS", 48, 24),
    ("ss  64 ->32  k0.50", "SS", 64, 32),
    ("ss  80 ->40  k0.50", "SS", 80, 40),
    ("ss  96 ->48  k0.50", "SS", 96, 48),
    ("- supersample k0.25 (4x) -", "HDR", 0, 0),
    ("ss  96 ->24  k0.25", "SS", 96, 24),
    ("ss  128->32  k0.25", "SS", 128, 32),
    ("ss  160->40  k0.25", "SS", 160, 40),
    ("ss  192->48  k0.25", "SS", 192, 48),
]


def _cap_font():
    return i18n.pixel_font_for_lang("en", 12)


def _blit_ss(surf, text, x, y, big_native, target, color):
    """High native, sub-1 k: render at `big_native` px (antialias ON), smoothscale to `target` px tall."""
    font = i18n.pixel_font_for_lang("zh_HK", big_native)
    big = font.render(text, True, color)  # AA ON — smooth outline of the pixel glyphs
    if big.get_width() == 0:
        return
    scale = target / font.get_height()
    small = pygame.transform.smoothscale(big, (max(1, round(big.get_width() * scale)), max(1, round(big.get_height() * scale))))
    surf.blit(small, (x, y + (ROW_H - small.get_height()) // 2))


def _blit_up(surf, text, x, y, native, k, color):
    """Nearest upscale / native — the widgets path (antialias OFF, integer k)."""
    font = i18n.pixel_font_for_lang("zh_HK", native)
    draw_lowres_text(surf, text, pygame.Rect(x, y, 280, ROW_H), font, color, max_k=k, line_gap=1, align="center")


def render(surf):
    surf.fill((26, 30, 38))
    cap = _cap_font()
    y = 0
    for caption, method, a, b in ROWS:
        row = pygame.Rect(0, y, W, ROW_H)
        if method == "HDR":
            pygame.draw.rect(surf, (18, 21, 27), row)
            draw_lowres_text(surf, caption, pygame.Rect(CAP_X, y, 360, ROW_H), cap, CAP_INK, max_k=1, line_gap=1, align="center")
            y += ROW_H
            continue
        pygame.draw.rect(surf, BAND_BG, row)
        pygame.draw.line(surf, ROW_GRID, (0, y + ROW_H - 1), (W, y + ROW_H - 1), 1)
        draw_lowres_text(surf, caption, pygame.Rect(CAP_X, y, WORD_X - CAP_X - 8, ROW_H), cap, CAP_INK, max_k=1, line_gap=1, align="center")
        if method == "UP":
            _blit_up(surf, SAMPLE_WORD, WORD_X, y, a, b, INK)
            _blit_up(surf, SAMPLE_NOTIF, NOTIF_X, y, a, b, GREEN)
            _blit_up(surf, SAMPLE_NUM, NUM_X, y, a, b, INK)
        else:  # SS
            _blit_ss(surf, SAMPLE_WORD, WORD_X, y, a, b, INK)
            _blit_ss(surf, SAMPLE_NOTIF, NOTIF_X, y, a, b, GREEN)
            _blit_ss(surf, SAMPLE_NUM, NUM_X, y, a, b, INK)
        y += ROW_H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    i18n.init("zh_HK")
    h = ROW_H * len(ROWS)
    if args.screenshot:
        surf = pygame.Surface((W, h))
        render(surf)
        out = str(project_root() / args.screenshot)
        pygame.image.save(surf, out)
        print(f"saved {out}  ({W}x{h})")
    else:
        screen = pygame.display.set_mode((W, h))
        pygame.display.set_caption("Ark supersample eval")
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

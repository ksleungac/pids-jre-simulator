"""DEV eval — why MS Gothic reads crisper than Ark at small size, and whether a FREE font matches it.

MS Gothic (msgothic.ttc, face 0 = fixed-pitch) ships EMBEDDED BITMAP STRIKES (EBDT/EBLC) — hand-tuned
bitmaps baked in at specific px sizes. SDL_ttf/FreeType render the strike (not the outline) when the
requested ppem matches one, which is the iconic crisp small-size console look. Ark is pure outline
(no strike), so at small native it's whatever the rasteriser produces. This puts them side by side at
real small size + a ×6 nearest zoom so the dot grid is inspectable; PixelMplus12 (free, on disk) rides
along as the candidate that would have to MATCH MS Gothic to justify a swap.

NOTE: MS Gothic is NOT shippable (non-redistributable license + JIS-only → tofus Simplified). This eval
is to SEE the target look and judge whether a free face reaches it — not to adopt MS Gothic.

  uv run _dev_scripts/_msgothic_eval.py --screenshot _msgothic.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

E = project_root() / "_dev_scripts" / "_fonts_eval"
ARK = E / "ark-pixel-font-12px-monospaced-otf-v2026.05.07" / "ark-pixel-12px-monospaced-ja.otf"
PM12 = E / "PixelMplus-20130602" / "PixelMplus-20130602" / "PixelMplus12-Regular.ttf"
MSG = "C:/Windows/Fonts/msgothic.ttc"  # face 0 = MS Gothic (fixed pitch, has bitmap strikes). DEV-only.

INK = (236, 241, 246)
GREEN = (54, 230, 64)
CAP = (150, 162, 174)
BG = (26, 30, 38)
ZOOM = 6
WORD, STA, MIX, NUM = "報知設定", "恵比寿", "次は東京", "1750"

# (label, path, native_px)
ROWS = [
    ("Ark-12mono  @12", ARK, 12),
    ("MS Gothic   @12", MSG, 12),
    ("MS Gothic   @11", MSG, 11),
    ("MS Gothic   @16", MSG, 16),
    ("PixelMplus12 @12", PM12, 12),
]
CAP_W = 200
SAMPLE_W = 360  # 1× samples block
ROW_H = 96


def _render(path, size, text, color):
    return pygame.font.Font(str(path), size).render(text, False, color)  # AA OFF


def render(surf):
    surf.fill(BG)
    cap = pygame.font.Font(str(ARK), 12)
    samples = [(WORD, INK), (STA, GREEN), (MIX, INK), (NUM, INK)]
    zoom_x = CAP_W + SAMPLE_W + 30
    for i, (label, path, size) in enumerate(ROWS):
        y = i * ROW_H
        pygame.draw.line(surf, (40, 48, 60), (0, y + ROW_H - 1), (surf.get_width(), y + ROW_H - 1), 1)
        surf.blit(cap.render(label, False, CAP), (12, y + ROW_H // 2 - 6))
        # 1x real-size samples, stacked into one strip
        sx = CAP_W
        for text, color in samples:
            g = _render(path, size, text, color)
            surf.blit(g, (sx, y + (ROW_H - g.get_height()) // 2))
            sx += g.get_width() + 14
        # x6 zoom of the dense word, for grid inspection
        gz = _render(path, size, WORD, INK)
        gz = pygame.transform.scale(gz, (gz.get_width() * ZOOM, gz.get_height() * ZOOM))
        surf.blit(gz, (zoom_x, y + (ROW_H - gz.get_height()) // 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    # report whether each render used a bitmap strike (height pinned) vs outline
    for label, path, size in ROWS:
        g = pygame.font.Font(str(path), size).render(WORD, False, INK)
        print(f"{label:18} req={size:>2}px  rendered_h={g.get_height():>2}px  w={g.get_width():>3}px")
    if args.screenshot:
        W = CAP_W + SAMPLE_W + 30 + len(WORD) * 12 * ZOOM + 40
        surf = pygame.Surface((W, ROW_H * len(ROWS)))
        render(surf)
        out = str(project_root() / args.screenshot)
        pygame.image.save(surf, out)
        print(f"\nsaved {out}  ({W}x{ROW_H * len(ROWS)}, 1× + nearest ×{ZOOM})")


if __name__ == "__main__":
    main()

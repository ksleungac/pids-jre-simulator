"""DEV eval — walk MS Gothic UP through sizes to find its EMBEDDED-BITMAP-STRIKE CEILING: the largest
size where it's still a crisp single-grid bitmap, before it falls back to (smooth) outline rendering.

Strike-vs-outline is detected objectively, no eyeballing: an embedded bitmap strike is 1-bit, so an
AA-ON render produces only TWO colours (bg + ink). An outline render at AA-ON produces anti-alias
GREYS (many colours). So `n_unique_colours <= 2` ⟺ bitmap strike. Ark (pure outline, one 12px design)
rides alongside at each size for reference — it never has a strike, so it's outline at every size,
which is exactly why it can't match MS Gothic's per-size baked detail.

  uv run _dev_scripts/_msgothic_sizes.py --screenshot _msgothic_sizes.png
"""

import argparse
import sys

import pygame

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

E = project_root() / "_dev_scripts" / "_fonts_eval"
ARK = E / "ark-pixel-font-12px-monospaced-otf-v2026.05.07" / "ark-pixel-12px-monospaced-ja.otf"
MSG = "C:/Windows/Fonts/msgothic.ttc"  # face 0 = MS Gothic (fixed pitch, bitmap strikes). DEV-only.

INK = (236, 241, 246)
CAP = (150, 162, 174)
BG = (26, 30, 38)
WORD = "報知設定"
SIZES = list(range(10, 27))  # every integer px 10..26 — sample each font size
ZOOM = 4


def _n_colors(path, size):
    """Unique colour count of an AA-ON render — 2 ⟺ 1-bit bitmap strike, >2 ⟺ outline (greys).
    MUST render onto an opaque background: AA-without-bg puts coverage in the ALPHA channel, so RGB
    stays constant and every size falsely reads as 2 colours. With a bg, AA greys land in RGB."""
    g = pygame.font.Font(str(path), size).render(WORD, True, (255, 255, 255), (0, 0, 0))
    seen = set()
    for x in range(g.get_width()):
        for y in range(g.get_height()):
            seen.add(g.get_at((x, y))[:3])
    return len(seen)


def _is_strike(path, size):
    return _n_colors(path, size) <= 2


def _crisp(path, size, zoom):
    g = pygame.font.Font(str(path), size).render(WORD, False, INK)  # AA OFF
    return pygame.transform.scale(g, (g.get_width() * zoom, g.get_height() * zoom))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()

    print("size  MSGothic            Ark-12mono")
    last_strike = None
    for s in SIZES:
        msg_strike = _is_strike(MSG, s)
        ark_strike = _is_strike(ARK, s)
        if msg_strike:
            last_strike = s
        mh = pygame.font.Font(str(MSG), s).render(WORD, False, INK).get_height()
        ah = pygame.font.Font(str(ARK), s).render(WORD, False, INK).get_height()
        print(f"{s:>3}   {'BITMAP' if msg_strike else 'outline':8} h={mh:<3} " f"  {'BITMAP' if ark_strike else 'outline':8} h={ah:<3}")
    print(f"\nMS Gothic largest bitmap strike at/below the tested set: {last_strike}px " f"(above this it renders smooth outline, not a crisp grid)")

    if args.screenshot:
        cap = pygame.font.Font(str(ARK), 12)
        col_msg = 150
        # MS Gothic only — one row per size
        rows = []
        for s in SIZES:
            gm = _crisp(MSG, s, ZOOM)
            rows.append((s, gm, gm.get_height() + 18))
        W = col_msg + max(g.get_width() for _, g, _ in rows) + 30
        H = sum(r[2] for r in rows)
        surf = pygame.Surface((W, H))
        surf.fill(BG)
        y = 0
        for s, gm, rh in rows:
            pygame.draw.line(surf, (40, 48, 60), (0, y + rh - 1), (W, y + rh - 1), 1)
            tag = "BITMAP" if _is_strike(MSG, s) else "outline"
            surf.blit(cap.render(f"{s}px", False, INK), (12, y + rh // 2 - 12))
            surf.blit(cap.render(tag, False, CAP), (12, y + rh // 2 + 2))
            surf.blit(gm, (col_msg, y + (rh - gm.get_height()) // 2))
            y += rh
        surf.blit(cap.render("MS Gothic ×4", False, CAP), (col_msg, 4))
        out = str(project_root() / args.screenshot)
        pygame.image.save(surf, out)
        print(f"saved {out}  ({W}x{H}, nearest ×{ZOOM})")


if __name__ == "__main__":
    main()

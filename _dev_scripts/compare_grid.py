# SPDX-License-Identifier: MIT
"""Stack reference + multiple candidate renders for one station into a tall grid.

Two modes, one composer:

1. **Coverage sheet** — tile any set of labelled renders into a grid. This is
   what `docs/DISPLAY.md` § "Specifying a new display" step 6 asks for with
   every element: one cell per case the element varies over, every cell
   rendered from the LIVE renderer (`preview_display.py --screenshot`), so the
   sheet cannot show superseded code.

       uv run preview_display.py --screenshot screenshot_a.png --route chuo/1654T --model e233_0 --stop 0
       uv run _dev_scripts/compare_grid.py --out sheet.png --cols 4 "高尾=screenshot_a.png" ...

2. **A/B/C font hunt** (the original) — reference at top, candidates stacked
   below. List each candidate as a (label_prefix, human_label) tuple in
   CANDIDATES; the script picks up screenshot_<label_prefix>_<station>.png for
   each and writes grid_<station>.png.

       uv run _dev_scripts/compare_grid.py            # no args = this mode
"""

import argparse
import sys
from pathlib import Path

import pygame

# Cell labels carry station names, so the summary line prints kanji. Windows
# pipes default to cp1252 and the script died on the label rather than on
# anything it was doing (`conventions.md` § Tooling).
sys.stdout.reconfigure(encoding="utf-8")

pygame.init()

STATIONS = {
    "tsudanuma": ("_references/lcd/Tsudanuma.png", "tsudanuma"),
    "kinshicho": ("_references/lcd/Kinshicho.png", "kinshicho"),
    "funabashi": ("_references/lcd/funabashi.png", "funabashi"),
    "shin_nihombashi": ("_references/lcd/Shin-Nihombashi.png", "shinNihombashi"),
}

# (screenshot_label_prefix, human_readable_label) — fill in for each
# A/B/C run. Each prefix corresponds to a `screenshot_<prefix>_<station>.png`
# rendered earlier (see compare_fonts.py header for the screenshot pattern).
# Example from the 2026-04 font hunt:
#   ("v0_medium",  "HelveticaNeue Medium 75pt"),
#   ("v1_bold",    "HelveticaNeue Bold 75pt"),
#   ("v2_bold80",  "HelveticaNeue Bold 80pt"),
CANDIDATES = []


def crop_upper_band(surf):
    rect = pygame.Rect(270, 0, surf.get_width() - 270, 117)
    return surf.subsurface(rect).copy()


def scale_to_w(s, w):
    scale = w / s.get_width()
    return pygame.transform.smoothscale(s, (w, int(s.get_height() * scale)))


def build_grid(station, ref_path, file_suffix, out_path):
    ref = pygame.image.load(ref_path)
    candidate_surfs = []
    for prefix, label in CANDIDATES:
        path = Path(f"screenshot_{prefix}_{file_suffix}.png")
        if not path.exists():
            print(f"missing {path}, skipping")
            continue
        surf = pygame.image.load(str(path))
        candidate_surfs.append((label, crop_upper_band(surf)))

    if not candidate_surfs:
        print(f"no candidates found for {station}")
        return

    target_w = max(ref.get_width(), *(s.get_width() for _, s in candidate_surfs))
    ref_s = scale_to_w(ref, target_w)
    cand_scaled = [(label, scale_to_w(s, target_w)) for label, s in candidate_surfs]

    label_h = 24
    pad = 6
    font = pygame.font.SysFont("arial", 14, bold=True)

    total_h = label_h + ref_s.get_height() + pad
    for _, s in cand_scaled:
        total_h += label_h + s.get_height() + pad

    out = pygame.Surface((target_w, total_h))
    out.fill((30, 30, 30))

    y = 0
    out.blit(font.render(f"REFERENCE  -  {station}", True, (255, 255, 0)), (4, y + 4))
    y += label_h
    out.blit(ref_s, (0, y))
    y += ref_s.get_height() + pad

    for label, s in cand_scaled:
        out.blit(font.render(label, True, (180, 220, 255)), (4, y + 4))
        y += label_h
        out.blit(s, (0, y))
        y += s.get_height() + pad

    pygame.image.save(out, out_path)
    print(f"wrote {out_path}")


def build_sheet(cells, out_path, cols=4, cell_w=None, title="", crop=None):
    """Tile labelled renders into a grid — the coverage sheet of mode 1.

    `cells` is a list of (label, path). Cells are scaled to one common width so
    frames from different models still line up; the grid is row-major.

    `crop` is an optional (x, y, w, h) taken from every cell before scaling —
    an upper-band sweep wants the band, not the whole 640x480 frame under it.
    """
    loaded = []
    for label, path in cells:
        if not Path(path).exists():
            print(f"missing {path}, skipping")
            continue
        surf = pygame.image.load(str(path))
        if crop:
            surf = surf.subsurface(pygame.Rect(*crop)).copy()
        loaded.append((label, surf))
    if not loaded:
        print("no cells to compose")
        return

    target_w = cell_w or max(s.get_width() for _, s in loaded)
    scaled = [(label, scale_to_w(s, target_w)) for label, s in loaded]
    cell_h = max(s.get_height() for _, s in scaled)

    label_h, pad = 22, 8
    font = pygame.font.SysFont("arial", 14, bold=True)
    title_h = 28 if title else 0

    rows = (len(scaled) + cols - 1) // cols
    out = pygame.Surface(
        (
            cols * target_w + (cols + 1) * pad,
            title_h + rows * (label_h + cell_h + pad) + pad,
        )
    )
    out.fill((30, 30, 30))
    if title:
        out.blit(font.render(title, True, (255, 255, 0)), (pad, 7))

    for i, (label, surf) in enumerate(scaled):
        cx = pad + (i % cols) * (target_w + pad)
        cy = title_h + pad + (i // cols) * (label_h + cell_h + pad)
        out.blit(font.render(label, True, (180, 220, 255)), (cx, cy + 3))
        out.blit(surf, (cx, cy + label_h))

    pygame.image.save(out, out_path)
    print(f"wrote {out_path}  ({len(scaled)} cells, {cols} cols)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ap = argparse.ArgumentParser(description="Tile labelled renders into a coverage sheet")
        ap.add_argument("cells", nargs="+", help='one "label=path.png" per cell, in reading order')
        ap.add_argument("--out", default="sheet.png")
        ap.add_argument("--cols", type=int, default=4)
        ap.add_argument("--cell-w", type=int, default=None, help="common cell width (default: widest input)")
        ap.add_argument("--title", default="")
        ap.add_argument("--crop", default=None, help="x,y,w,h taken from every cell (e.g. an upper band)")
        a = ap.parse_args()
        build_sheet(
            [tuple(c.split("=", 1)) for c in a.cells],
            a.out,
            cols=a.cols,
            cell_w=a.cell_w,
            title=a.title,
            crop=tuple(int(v) for v in a.crop.split(",")) if a.crop else None,
        )
    else:
        for name, (ref, suffix) in STATIONS.items():
            build_grid(name, ref, suffix, f"grid_{name}.png")

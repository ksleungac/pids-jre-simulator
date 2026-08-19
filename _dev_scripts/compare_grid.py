# SPDX-License-Identifier: MIT
"""Stack reference + multiple candidate renders for one station into a tall grid.

Useful for A/B/C comparing several font/size variants at once. List each
candidate as a (label_prefix, human_label) tuple in CANDIDATES; the script
picks up screenshot_<label_prefix>_<station>.png for each.

Usage:
    # render every variant under a distinct label first (see compare_fonts.py),
    # then edit CANDIDATES below and run:
    uv run compare_grid.py

Outputs grid_<station>.png — reference at top, each candidate stacked below
with its label, all scaled to matching width for direct visual comparison.
"""

from pathlib import Path

import pygame

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


if __name__ == "__main__":
    for name, (ref, suffix) in STATIONS.items():
        build_grid(name, ref, suffix, f"grid_{name}.png")

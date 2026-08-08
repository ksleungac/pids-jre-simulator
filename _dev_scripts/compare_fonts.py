# SPDX-License-Identifier: MIT
"""Side-by-side comparison of LCD reference photos vs. preview screenshots.

Usage:
    # 1. render screenshots (one per reference station) with whatever font/size
    #    you're testing — name them screenshot_<label>_<station>.png:
    uv run preview_display.py --screenshot screenshot_myrun_tsudanuma.png --mode english --stop 3 --pa 2
    uv run preview_display.py --screenshot screenshot_myrun_funabashi.png --mode english --stop 2 --pa 0
    uv run preview_display.py --screenshot screenshot_myrun_kinshicho.png --mode english --stop 1 --pa 2
    uv run preview_display.py --screenshot screenshot_myrun_shinNihombashi.png --mode english --stop 4 --pa 2

    # 2. build the comparison composites:
    uv run compare_fonts.py myrun

Outputs compare_<label>_<station>.png — reference photo on top, cropped
upper-LCD strip from your render below, both scaled to the same width so
letterforms align for direct visual comparison.

Reference photos live in lcd_references/. The mock route (audio/_mock/main)
contains the four named stations at the indicated --stop indices.
"""

import sys
from pathlib import Path

import pygame

pygame.init()

# (display_name, reference_image, screenshot_suffix, --stop, --pa)
STATIONS = [
    ("tokyo", "lcd_references/Tokyo.png", "tokyo", 0, 2),
    ("shin_nihombashi", "lcd_references/Shin-Nihombashi.png", "shinNihombashi", 1, 2),
    ("kinshicho", "lcd_references/Kinshicho.png", "kinshicho", 3, 2),
    ("funabashi", "lcd_references/funabashi.png", "funabashi", 7, 0),
    ("tsudanuma", "lcd_references/Tsudanuma.png", "tsudanuma", 8, 2),
]


def crop_upper_band(surf):
    """Crop the upper LCD strip to the area where the station name lives.

    The full preview is 730x420; upper LCD is the top 117px and the station
    name occupies roughly x=270..730. Crop to that so the side-by-side has
    minimal extraneous chrome.
    """
    rect = pygame.Rect(270, 0, surf.get_width() - 270, 117)
    return surf.subsurface(rect).copy()


def scale_to_h(s, h):
    scale = h / s.get_height()
    return pygame.transform.smoothscale(s, (int(s.get_width() * scale), h))


def make_compare(name, ref_path, render_path, out_path, label_suffix=""):
    ref = pygame.image.load(ref_path)
    rend = pygame.image.load(render_path)
    rend_crop = crop_upper_band(rend)

    # Scale both to the SAME HEIGHT so the upper-LCD strip lines up vertically.
    # This makes letter heights directly comparable; absolute pixel sizes (cap
    # height etc.) can be eyeballed against the reference.
    target_h = max(ref.get_height(), rend_crop.get_height())
    ref_s = scale_to_h(ref, target_h)
    rend_s = scale_to_h(rend_crop, target_h)

    pad = 8
    label_h = 22
    font = pygame.font.SysFont("arial", 14, bold=True)

    total_w = max(ref_s.get_width(), rend_s.get_width())
    total_h = label_h + ref_s.get_height() + pad + label_h + rend_s.get_height() + pad
    out = pygame.Surface((total_w, total_h))
    out.fill((40, 40, 40))

    y = 0
    out.blit(font.render(f"REFERENCE: {name}", True, (255, 255, 0)), (4, y + 3))
    y += label_h
    out.blit(ref_s, (0, y))
    y += ref_s.get_height() + pad
    out.blit(font.render(f"RENDER ({label_suffix}): {name}", True, (180, 220, 255)), (4, y + 3))
    y += label_h
    out.blit(rend_s, (0, y))

    pygame.image.save(out, out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "current"
    for display_name, ref, suffix, _, _ in STATIONS:
        rend = Path(f"screenshot_{label}_{suffix}.png")
        if not rend.exists():
            print(f"skip {display_name}: {rend} missing")
            continue
        make_compare(display_name, ref, str(rend), f"compare_{label}_{display_name}.png", label_suffix=label)

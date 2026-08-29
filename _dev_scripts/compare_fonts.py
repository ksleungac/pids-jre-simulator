# SPDX-License-Identifier: MIT
"""Side-by-side comparison of LCD reference photos vs. preview screenshots.

Two modes.

**Overlay** (``--overlay``) — the reference scaled onto the render's canvas, then
reference / ours / the two blended, stacked and zoomed. The blend is what says
whether an element sits where the reference puts it; the two alone are what say
which of them a difference belongs to. The live-nudging form of the same thing is
``preview_display.py --edit --overlay`` (docs/DISPLAY.md step 6) — this one is for
handing a still to the author.

    uv run _dev_scripts/compare_fonts.py --overlay \
        --ref _references/lcd/e233_0/full-takao-stopping-ja.png \
        --render screenshot_x.png --crop 0,149,640,331 --zoom 2 --out cmp.png

**Font hunt** (no args, the original) — usage:
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

Reference photos live in _references/lcd/. The mock route (audio/_mock/main)
contains the four named stations at the indicated --stop indices.
"""

import argparse
import sys
from pathlib import Path

import pygame

pygame.init()

# (display_name, reference_image, screenshot_suffix, --stop, --pa)
STATIONS = [
    ("tokyo", "_references/lcd/Tokyo.png", "tokyo", 0, 2),
    ("shin_nihombashi", "_references/lcd/Shin-Nihombashi.png", "shinNihombashi", 1, 2),
    ("kinshicho", "_references/lcd/Kinshicho.png", "kinshicho", 3, 2),
    ("funabashi", "_references/lcd/funabashi.png", "funabashi", 7, 0),
    ("tsudanuma", "_references/lcd/Tsudanuma.png", "tsudanuma", 8, 2),
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


def build_overlay(ref_path, render_path, out_path, crop=None, zoom=2, alpha=128):
    """Reference / ours / blended, stacked and zoomed. See the module docstring.

    The reference is scaled to the RENDER's canvas first, so every coordinate in
    the composite is a canvas coordinate — the same numbers the tuneables carry.
    """
    ref = pygame.image.load(ref_path)
    rend = pygame.image.load(render_path).convert_alpha()
    ref = pygame.transform.smoothscale(ref, rend.get_size()).convert_alpha()

    blend = rend.copy()
    ghost = ref.copy()
    ghost.set_alpha(alpha)
    blend.blit(ghost, (0, 0))

    panels = [("REFERENCE (scaled to canvas)", ref), ("OURS", rend), ("BLENDED", blend)]
    if crop:
        r = pygame.Rect(*crop)
        panels = [(t, s.subsurface(r).copy()) for t, s in panels]
    if zoom != 1:
        panels = [(t, pygame.transform.scale(s, (s.get_width() * zoom, s.get_height() * zoom))) for t, s in panels]

    label_h, pad = 22, 6
    font = pygame.font.SysFont("arial", 14, bold=True)
    w = max(s.get_width() for _, s in panels)
    h = sum(s.get_height() + label_h + pad for _, s in panels)
    out = pygame.Surface((w, h))
    out.fill((40, 40, 40))
    y = 0
    for title, surf in panels:
        out.blit(font.render(title, True, (255, 255, 0)), (4, y + 3))
        y += label_h
        out.blit(surf, (0, y))
        y += surf.get_height() + pad
    pygame.image.save(out, out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if "--overlay" in sys.argv:
        ap = argparse.ArgumentParser(description="Reference-over-render overlay triptych")
        ap.add_argument("--overlay", action="store_true")
        ap.add_argument("--ref", required=True)
        ap.add_argument("--render", required=True)
        ap.add_argument("--out", default="overlay.png")
        ap.add_argument("--crop", default=None, help="x,y,w,h in canvas coordinates")
        ap.add_argument("--zoom", type=int, default=2)
        ap.add_argument("--alpha", type=int, default=128)
        a = ap.parse_args()
        pygame.display.set_mode((1, 1))
        build_overlay(
            a.ref,
            a.render,
            a.out,
            crop=tuple(int(v) for v in a.crop.split(",")) if a.crop else None,
            zoom=a.zoom,
            alpha=a.alpha,
        )
        sys.exit(0)

    label = sys.argv[1] if len(sys.argv) > 1 else "current"
    for display_name, ref, suffix, _, _ in STATIONS:
        rend = Path(f"screenshot_{label}_{suffix}.png")
        if not rend.exists():
            print(f"skip {display_name}: {rend} missing")
            continue
        make_compare(display_name, ref, str(rend), f"compare_{label}_{display_name}.png", label_suffix=label)

# SPDX-License-Identifier: MIT
"""Throwaway: bake a white-on-transparent mask with route color (alpha-stencil)
and composite over the blank E235-0 canvas, to confirm edges resolve clean.

  uv run _dev_scripts/_bake_preview.py <mask.png> <base.png> <out.png>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pygame  # noqa: E402

mask_path, base_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
ROUTE_COLOR = (116, 193, 30)  # Yamanote green (arc_color)

pygame.init()
mask = pygame.image.load(mask_path)
w, h = mask.get_size()

# Alpha-stencil bake: solid route color everywhere, coverage = mask's alpha.
band = pygame.Surface((w, h), pygame.SRCALPHA)
band.fill((*ROUTE_COLOR, 255))
pygame.surfarray.pixels_alpha(band)[:] = pygame.surfarray.array_alpha(mask)

base = pygame.image.load(base_path)
base = base.copy()
base.blit(band, (0, 0))
pygame.image.save(base, out_path)
print(f"baked {mask_path} x {ROUTE_COLOR} over {base_path} -> {out_path}")

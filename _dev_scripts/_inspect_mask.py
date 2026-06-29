"""Throwaway: inspect a mask PNG's alpha + RGB so we can judge the bake.

  uv run _dev_scripts/_inspect_mask.py <mask.png>

Reports: alpha channel present?, alpha histogram, RGB at interior vs edge,
and a coarse ASCII alpha map (so the shape is visible without compositing).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pygame  # noqa: E402

path = sys.argv[1]
pygame.init()
raw = pygame.image.load(path)
has_alpha = bool(raw.get_flags() & pygame.SRCALPHA)
w, h = raw.get_size()
print(f"file={path}  size={w}x{h}  SRCALPHA_flag={has_alpha}")

alpha = pygame.surfarray.array_alpha(raw).astype(np.int32)  # (w,h)
rgb = pygame.surfarray.array3d(raw).astype(np.int32)  # (w,h,3)

n = alpha.size
a0 = int((alpha == 0).sum())
a255 = int((alpha == 255).sum())
amid = int(((alpha > 0) & (alpha < 255)).sum())
print(
    f"alpha: min={alpha.min()} max={alpha.max()}  "
    f"==0: {a0} ({100*a0/n:.1f}%)  ==255: {a255} ({100*a255/n:.1f}%)  "
    f"partial: {amid} ({100*amid/n:.1f}%)"
)

interior = alpha >= 250
edge = (alpha > 0) & (alpha < 250)
for name, mask in (("interior(a>=250)", interior), ("edge(0<a<250)", edge)):
    cnt = int(mask.sum())
    if cnt == 0:
        print(f"{name}: none")
        continue
    r, g, b = rgb[..., 0][mask], rgb[..., 1][mask], rgb[..., 2][mask]
    print(
        f"{name}: {cnt} px  R[{r.min()}-{r.max()} mean {r.mean():.0f}]  "
        f"G[{g.min()}-{g.max()} mean {g.mean():.0f}]  "
        f"B[{b.min()}-{b.max()} mean {b.mean():.0f}]"
    )

# Coarse ASCII alpha map (downsample by block-max so thin features survive).
cols, rows = 73, 28
bx, by = max(1, w // cols), max(1, h // rows)
ramp = " .:-=+*#%@"
print("alpha map (block-max coverage):")
for ry in range(rows):
    line = []
    for rx in range(cols):
        block = alpha[rx * bx : (rx + 1) * bx, ry * by : (ry + 1) * by]
        v = int(block.max()) if block.size else 0
        line.append(ramp[min(9, v * 10 // 256)])
    print("".join(line))

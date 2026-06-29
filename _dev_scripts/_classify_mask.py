"""Throwaway: classify mask pixels into transparent / band-white / grey-opaque /
edge, and map them, to see if grey is a distinct element or just band edge.

  uv run _dev_scripts/_classify_mask.py <mask.png>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402
import pygame  # noqa: E402

raw = pygame.image.load(sys.argv[1])
w, h = raw.get_size()
a = pygame.surfarray.array_alpha(raw).astype(np.int32)
rgb = pygame.surfarray.array3d(raw).astype(np.int32)
mn = rgb.min(axis=2)  # min channel = "darkness"

transparent = a < 30
opaque = a >= 230
edge = (~transparent) & (~opaque)
white_op = opaque & (mn >= 190)
grey_op = opaque & (mn < 190)

for name, m in (("transparent", transparent), ("edge(30-230a)", edge), ("white-opaque", white_op), ("grey-opaque", grey_op)):
    c = int(m.sum())
    extra = ""
    if c and name == "grey-opaque":
        ys, xs = np.where(m.T)  # note: arrays are (w,h)
        extra = f"  bbox x[{xs.min()}-{xs.max()}] y[{ys.min()}-{ys.max()}]  min-mean={int(mn[m].mean())}"
    print(f"{name:14s}: {c:7d}{extra}")

cols, rows = 73, 28
bx, by = max(1, w // cols), max(1, h // rows)
print("map: '#'=white-opaque  'o'=grey-opaque  '.'=edge  ' '=transparent")
for ry in range(rows):
    line = []
    for rx in range(cols):
        sl = (slice(rx * bx, (rx + 1) * bx), slice(ry * by, (ry + 1) * by))
        if grey_op[sl].any():
            line.append("o")
        elif white_op[sl].any():
            line.append("#")
        elif edge[sl].any():
            line.append(".")
        else:
            line.append(" ")
    print("".join(line))

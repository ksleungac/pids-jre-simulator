# TIER: T3 — e235_0 band-fill centerline is derived from the mask geometry
"""Locks the mask-derived fill-sweep centerline (#51).

The green fill on the e235_0 5-station view sweeps along a centerline that is
now derived DIRECTLY from the band mask PNG's own geometry — the per-row
horizontal centroid of the fill, ordered bottom → top — replacing the retired
Catmull-Rom-through-hand-placed-waypoints path. `_extract_band_centerline()` is
the pure geometric core; this test pins its invariants against the shipped mask.

Invariants (independent of the extraction impl — they read off the mask shape):
- non-empty, ordered BOTTOM → TOP (Y strictly decreasing),
- spans the band's Y-extent (first ≈ bottom row, last ≈ top row),
- X stays within the band's pixel column range,
- one point per band row (the mask is a single contiguous segment per row).

Discriminates: reverse the order, drop the fill test, or return empty and this
fails. Needs a pygame display (convert_alpha loads the PNG) → headless dummy.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame  # noqa: E402
import pygame.surfarray  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))

from displays.train_models.e235_0 import lower_lcd as L  # noqa: E402


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    pts = L._extract_band_centerline()
    check(len(pts) > 50, f"centerline should have many points (one per band row); got {len(pts)}")

    ys = [p[1] for p in pts]
    xs = [p[0] for p in pts]

    # Ordered bottom -> top: Y strictly decreasing.
    check(all(ys[i] > ys[i + 1] for i in range(len(ys) - 1)), "centerline must be ordered bottom->top (Y strictly decreasing)")

    # Spans the band Y-extent. The shipped mask band lives ~y=130..419; pin
    # loosely so a mask retouch doesn't break the test, but a wrong axis /
    # empty / reversed result does.
    check(ys[0] > 380, f"first point should be near the band BOTTOM (y>380); got y={ys[0]}")
    check(ys[-1] < 180, f"last point should be near the band TOP (y<180); got y={ys[-1]}")

    # X within the band's column range (mask is 730 wide; band ~[12,542]).
    check(all(0 <= x <= 730 for x in xs), "centerline X must stay within the mask width")
    check(min(xs) < 200 and max(xs) > 400, f"centerline X should sweep across the band (min<200,max>400); got [{min(xs):.0f},{max(xs):.0f}]")

    # Single-contiguous-segment-per-row is the load-bearing assumption: the
    # per-row centroid is a faithful medial line ONLY if each row's fill is one
    # segment. A future multi-segment mask retouch would slide the centroid into
    # the gap between segments while every check above still passes — so guard the
    # assumption directly rather than trusting the docstring.
    band = pygame.image.load(str(L._BAND_MASK_PATH)).convert_alpha()
    rgb = pygame.surfarray.array3d(band)
    a = pygame.surfarray.array_alpha(band)
    fill = (rgb.min(axis=2) >= L._BAND_FILL_MIN) & (a > 10)
    multi = 0
    for y in range(fill.shape[1]):
        idx = fill[:, y].nonzero()[0]
        if idx.size and int(idx.max() - idx.min() + 1) != int(idx.size):
            multi += 1
    check(multi == 0, f"mask must be ONE contiguous band per row (centroid == medial line); {multi} multi-segment rows")

    if failures:
        print("FAIL: e235_0 mask-derived fill centerline (#51)")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: e235_0 fill centerline is mask-derived — {len(pts)} pts, bottom(y={ys[0]:.0f})->top(y={ys[-1]:.0f}), monotonic (#51)")


if __name__ == "__main__":
    main()

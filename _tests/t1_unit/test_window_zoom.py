# SPDX-License-Identifier: MIT
# TIER: T1 — window zoom: default pick, ceiling, and drag snapping
"""Pins `window_utils.max_zoom` / `pick_default_zoom` / `snap_zoom`.

The app is a fixed-resolution pixel artifact — every element is authored at one
pixel size — so it only scales cleanly by WHOLE multiples with nearest-neighbour.
These three functions are what keep the window on a multiple: one picks the
out-of-box size, one bounds it to the screen, one snaps a drag.

They take the work area as ARGUMENTS rather than querying it, which is the only
reason a 4K or 8K case can be checked from a 1080p machine. If they ever go back
to fetching it internally, every row below silently becomes a test of this
developer's desktop instead.

Discriminators are noted per case.
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

from window_utils import max_zoom, pick_default_zoom, snap_zoom  # noqa: E402

# Drive window: LCD 730x420 + status band 68. Pinned literally — importing the
# constants would scale the expectations with any mutation of them.
CW, CH = 730, 488

# (label, work_w, work_h, expected default k, expected max k)
# Work areas are screen height minus a plausible taskbar at that DPI.
CASES = [
    ("1366x768  old laptop", 1366, 720, 1, 1),
    ("1920x1080 13in @125%", 1920, 1020, 1, 2),
    ("2560x1440 27in", 2560, 1392, 1, 2),
    ("3440x1440 ultrawide", 3440, 1392, 1, 2),
    ("3840x2160 4K", 3840, 2064, 2, 4),
    ("5120x2880 5K", 5120, 2784, 2, 5),
]


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    for label, ww, wh, want_default, want_max in CASES:
        k = pick_default_zoom(CW, CH, ww, wh)
        m = max_zoom(CW, CH, ww, wh)
        check(k == want_default, f"{label}: default zoom expected {want_default}x, got {k}x")
        check(m == want_max, f"{label}: max zoom expected {want_max}x, got {m}x")
        # Whatever is picked must actually fit, or the window opens off-screen.
        check(CW * k <= ww and CH * k <= wh, f"{label}: default {k}x ({CW*k}x{CH*k}) does not fit {ww}x{wh}")

    # --- the floor holds even when nothing fits (tiny screen) ---
    # Discriminator: drop the `max(1, ...)` / the `k = 1` seed and this returns 0.
    check(max_zoom(CW, CH, 320, 240) == 1, "max_zoom must never go below 1x even on a screen too small")
    check(pick_default_zoom(CW, CH, 320, 240) == 1, "default must never go below 1x")

    # --- 4K really does jump to 2x, and it is the height that drives it ---
    # Discriminator: this is the whole point of the feature; at 1x a 4K user gets 23% of height.
    check(pick_default_zoom(CW, CH, 3840, 2064) == 2, "4K must default to 2x, not 1x")
    check(CH * 2 / 2064 > 0.40, "sanity: 2x on 4K should land near the 40% target from above")

    # --- ties break toward the SMALLER multiple (companion app, not a greedy one) ---
    # Contrive a work area where k=1 and k=2 are equidistant from 40%: target = 1.5*CH
    # => work_h = 1.5*CH/0.40. Discriminator: use `<=` instead of `< best_d - 0.5` and this flips to 2.
    tie_h = round(1.5 * CH / 0.40)
    check(pick_default_zoom(CW, CH, 4000, tie_h) == 1, f"an exact tie must keep the smaller multiple; got {pick_default_zoom(CW, CH, 4000, tie_h)}x")

    # --- snapping a drag ---
    # Discriminator: replace round() with int() and the 1.6x case snaps down to 1 instead of 2.
    check(snap_zoom(CH, CH, 3) == 1, "dragging to exactly 1x stays 1x")
    check(snap_zoom(CH, CH * 2, 3) == 2, "dragging to exactly 2x stays 2x")
    check(snap_zoom(CH, int(CH * 1.6), 3) == 2, "1.6x rounds UP to 2x (nearest, not floor)")
    check(snap_zoom(CH, int(CH * 1.4), 3) == 1, "1.4x rounds DOWN to 1x")
    check(snap_zoom(CH, CH * 9, 3) == 3, "a drag past the ceiling clamps to max, not beyond")
    check(snap_zoom(CH, 10, 3) == 1, "a drag to almost nothing clamps to 1x, never 0")
    check(snap_zoom(CH, 0, 3) == 1, "a zero-height resize event must not produce 0x")

    if failures:
        print("FAIL: window zoom")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: window zoom (default pick, ceiling, tie-break, drag snap, floor at 1x)")


if __name__ == "__main__":
    main()

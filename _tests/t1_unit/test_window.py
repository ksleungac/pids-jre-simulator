# SPDX-License-Identifier: MIT
# TIER: T1 — the window: how big it opens, and where a click in it lands
"""What the app's window guarantees, as pure functions.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). One window,
two decisions, and they are coupled: the zoom multiple that section 1 picks is
the divide that section 2 has to undo. Splitting them across files is how the
second silently stops matching the first.

  1. HOW BIG IT OPENS   — window_utils.max_zoom / pick_default_zoom / snap_zoom
  2. WHERE A CLICK GOES — PASimulator.window_to_lcd

Both fail silently. A bad multiple opens the window off-screen, or leaves a 4K
user at 23% of their height; a bad transform sends click-to-jump to the wrong
station, and a wrong station is still a valid jump, so nothing raises (#73).

No pygame display, no fonts, no route — the transform is called unbound against
a stub, and the zoom functions take the work area as ARGUMENTS rather than
querying it, which is the only reason a 4K or 5K case can be checked from a
1080p machine. If they ever go back to fetching it internally, every row in
section 1 silently becomes a test of this developer's desktop instead.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import PASimulator  # noqa: E402
from window_utils import max_zoom, pick_default_zoom, snap_zoom  # noqa: E402

# ── 1. how big it opens ───────────────────────────────────────────────────────
# The app is a fixed-resolution pixel artifact — every element is authored at one
# pixel size — so it only scales cleanly by WHOLE multiples with nearest-neighbour.
# These three functions keep the window on a multiple: one picks the out-of-box
# size, one bounds it to the screen, one snaps a drag.
#
# Drive window: LCD 730x420 + status band 68. Pinned literally — importing the
# constants would scale the expectations with any mutation of them.
CW, CH = 730, 488

# (label, work_w, work_h, expected default k, expected max k)
# Work areas are screen height minus a plausible taskbar at that DPI.
ZOOM_CASES = [
    ("1366x768  old laptop", 1366, 720, 1, 1),
    ("1920x1080 13in @125%", 1920, 1020, 1, 2),
    ("2560x1440 27in", 2560, 1392, 1, 2),
    ("3440x1440 ultrawide", 3440, 1392, 1, 2),
    ("3840x2160 4K", 3840, 2064, 2, 4),
    ("5120x2880 5K", 5120, 2784, 2, 5),
]


def check_zoom(check):
    """Discriminators are noted per case."""
    for label, ww, wh, want_default, want_max in ZOOM_CASES:
        k = pick_default_zoom(CW, CH, ww, wh)
        m = max_zoom(CW, CH, ww, wh)
        check(k == want_default, f"{label}: default zoom expected {want_default}x, got {k}x")
        check(m == want_max, f"{label}: max zoom expected {want_max}x, got {m}x")
        # Whatever is picked must actually fit, or the window opens off-screen.
        check(
            CW * k <= ww and CH * k <= wh,
            f"{label}: default {k}x ({CW*k}x{CH*k}) does not fit {ww}x{wh}",
        )

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
    check(
        pick_default_zoom(CW, CH, 4000, tie_h) == 1,
        f"an exact tie must keep the smaller multiple; got {pick_default_zoom(CW, CH, 4000, tie_h)}x",
    )

    # --- snapping a drag ---
    # Discriminator: replace round() with int() and the 1.6x case snaps down to 1 instead of 2.
    check(snap_zoom(CH, CH, 3) == 1, "dragging to exactly 1x stays 1x")
    check(snap_zoom(CH, CH * 2, 3) == 2, "dragging to exactly 2x stays 2x")
    check(snap_zoom(CH, int(CH * 1.6), 3) == 2, "1.6x rounds UP to 2x (nearest, not floor)")
    check(snap_zoom(CH, int(CH * 1.4), 3) == 1, "1.4x rounds DOWN to 1x")
    check(snap_zoom(CH, CH * 9, 3) == 3, "a drag past the ceiling clamps to max, not beyond")
    check(snap_zoom(CH, 10, 3) == 1, "a drag to almost nothing clamps to 1x, never 0")
    check(snap_zoom(CH, 0, 3) == 1, "a zero-height resize event must not produce 0x")


# ── 2. where a click goes ─────────────────────────────────────────────────────
# `window_to_lcd` is the one place window coords become LCD coords. Click-to-jump
# and the hover cursor each used to subtract the debug-panel offset inline; two
# copies of a transform with no compiler to keep them agreeing is how click-to-jump
# ends up on the wrong station (#73).

PANEL_H = 68  # tims.band.BAND_H — pinned literally; reading the constant in would
# scale the expectations with any mutation of it and stop discriminating.


def sim(auto_input, panel_h=PANEL_H, zoom=1):
    panel = SimpleNamespace(get_height=lambda: panel_h) if auto_input else None
    s = SimpleNamespace(auto_input=auto_input, debug_surface=panel, zoom=zoom)
    s.window_to_canvas = lambda pos: PASimulator.window_to_canvas(s, pos)
    return s


def call(s, pos):
    return PASimulator.window_to_lcd(s, pos)


def check_transform(check):
    # --- OCR off: no panel, so window coords ARE LCD coords ---
    off = sim(auto_input=False)
    check(call(off, (0, 0)) == (0, 0), f"OCR off: origin maps 1:1; got {call(off, (0, 0))}")
    check(call(off, (365, 210)) == (365, 210), f"OCR off: mid maps 1:1; got {call(off, (365, 210))}")
    check(call(off, (729, 419)) == (729, 419), f"OCR off: last px maps 1:1; got {call(off, (729, 419))}")

    # --- OCR on: the band occupies the top 68px, LCD starts below it ---
    on = sim(auto_input=True)
    check(call(on, (100, PANEL_H)) == (100, 0), f"first LCD row maps to y=0; got {call(on, (100, PANEL_H))}")
    check(
        call(on, (100, PANEL_H + 210)) == (100, 210),
        f"mid LCD row; got {call(on, (100, PANEL_H + 210))}",
    )
    check(call(on, (100, PANEL_H - 1)) is None, "a click INSIDE the band must not reach the LCD")
    check(call(on, (100, 0)) is None, "a click at the very top must not reach the LCD")

    # --- x is never offset, only y ---
    check(call(on, (0, PANEL_H))[0] == 0, "x must pass through untouched")
    check(call(on, (729, PANEL_H))[0] == 729, "x must pass through untouched at the right edge")

    # --- the panel is ignored unless auto_input is on, even if a surface lingers ---
    stale = sim(auto_input=False)
    stale.debug_surface = SimpleNamespace(get_height=lambda: PANEL_H)
    check(
        call(stale, (10, 10)) == (10, 10),
        f"auto_input off must ignore a stale panel surface; got {call(stale, (10, 10))}",
    )

    # --- ZOOM: the divide comes off BEFORE the band offset, since the band is a canvas measurement.
    #     Applying them the other way round subtracts 68 window-px from a 2x window = 34 canvas-px,
    #     and every click lands 34px too low with no error anywhere.
    z2 = sim(auto_input=True, zoom=2)
    check(
        call(z2, (200, PANEL_H * 2)) == (100, 0),
        f"2x: first LCD row maps to y=0; got {call(z2, (200, PANEL_H * 2))}",
    )
    check(
        call(z2, (200, (PANEL_H + 210) * 2)) == (100, 210),
        f"2x: mid LCD row; got {call(z2, (200, (PANEL_H + 210) * 2))}",
    )
    check(call(z2, (200, PANEL_H * 2 - 2)) is None, "2x: a click still inside the band must not reach the LCD")

    z3 = sim(auto_input=False, zoom=3)
    check(call(z3, (300, 330)) == (100, 110), f"3x, no band: pure divide; got {call(z3, (300, 330))}")
    check(call(z3, (0, 0)) == (0, 0), "3x: origin stays the origin")

    # A click at the far corner of a 3x window must land inside the canvas, not one px past it.
    check(
        call(z3, (730 * 3 - 1, 420 * 3 - 1)) == (729, 419),
        f"3x: last window px maps to last canvas px; got {call(z3, (2189, 1259))}",
    )


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    check_zoom(check)
    check_transform(check)

    if failures:
        print("FAIL: window")
        print("\n".join(failures))
        sys.exit(1)
    print(
        "PASS: window (zoom default/ceiling/tie-break/drag-snap/floor; " "window->LCD band offset on y only, band clicks rejected, zoom undone first)"
    )


if __name__ == "__main__":
    main()

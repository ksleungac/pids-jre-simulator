# SPDX-License-Identifier: MIT
# TIER: T1 — the single window->LCD coordinate transform
"""Pins `PASimulator.window_to_lcd`, the one place window coords become LCD coords.

Click-to-jump and the hover cursor each used to subtract the debug-panel offset
inline. Two copies of a transform with no compiler to keep them agreeing is how
click-to-jump ends up on the wrong station — and it fails SILENTLY, since a wrong
station is still a valid jump (#73).

This locks today's behaviour before the window becomes resizable, because the zoom
divide lands in this same function. If that change breaks the offset, these fail
instead of the app quietly jumping to the wrong stop.

Called unbound against a stub — no pygame display, no fonts, no route.
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

PANEL_H = 68  # tims.band.BAND_H — pinned literally; reading the constant in would
# scale the expectations with any mutation of it and stop discriminating.


def sim(auto_input, panel_h=PANEL_H, zoom=1):
    panel = SimpleNamespace(get_height=lambda: panel_h) if auto_input else None
    s = SimpleNamespace(auto_input=auto_input, debug_surface=panel, zoom=zoom)
    s.window_to_canvas = lambda pos: PASimulator.window_to_canvas(s, pos)
    return s


def call(s, pos):
    return PASimulator.window_to_lcd(s, pos)


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # --- OCR off: no panel, so window coords ARE LCD coords ---
    off = sim(auto_input=False)
    check(call(off, (0, 0)) == (0, 0), f"OCR off: origin maps 1:1; got {call(off, (0, 0))}")
    check(call(off, (365, 210)) == (365, 210), f"OCR off: mid maps 1:1; got {call(off, (365, 210))}")
    check(call(off, (729, 419)) == (729, 419), f"OCR off: last px maps 1:1; got {call(off, (729, 419))}")

    # --- OCR on: the band occupies the top 68px, LCD starts below it ---
    on = sim(auto_input=True)
    check(call(on, (100, PANEL_H)) == (100, 0), f"first LCD row maps to y=0; got {call(on, (100, PANEL_H))}")
    check(call(on, (100, PANEL_H + 210)) == (100, 210), f"mid LCD row; got {call(on, (100, PANEL_H + 210))}")
    check(call(on, (100, PANEL_H - 1)) is None, "a click INSIDE the band must not reach the LCD")
    check(call(on, (100, 0)) is None, "a click at the very top must not reach the LCD")

    # --- x is never offset, only y ---
    check(call(on, (0, PANEL_H))[0] == 0, "x must pass through untouched")
    check(call(on, (729, PANEL_H))[0] == 729, "x must pass through untouched at the right edge")

    # --- the panel is ignored unless auto_input is on, even if a surface lingers ---
    stale = sim(auto_input=False)
    stale.debug_surface = SimpleNamespace(get_height=lambda: PANEL_H)
    check(call(stale, (10, 10)) == (10, 10), f"auto_input off must ignore a stale panel surface; got {call(stale, (10, 10))}")

    # --- ZOOM: the divide comes off BEFORE the band offset, since the band is a canvas measurement.
    #     Applying them the other way round subtracts 68 window-px from a 2x window = 34 canvas-px,
    #     and every click lands 34px too low with no error anywhere.
    z2 = sim(auto_input=True, zoom=2)
    check(call(z2, (200, PANEL_H * 2)) == (100, 0), f"2x: first LCD row maps to y=0; got {call(z2, (200, PANEL_H * 2))}")
    check(call(z2, (200, (PANEL_H + 210) * 2)) == (100, 210), f"2x: mid LCD row; got {call(z2, (200, (PANEL_H + 210) * 2))}")
    check(call(z2, (200, PANEL_H * 2 - 2)) is None, "2x: a click still inside the band must not reach the LCD")

    z3 = sim(auto_input=False, zoom=3)
    check(call(z3, (300, 330)) == (100, 110), f"3x, no band: pure divide; got {call(z3, (300, 330))}")
    check(call(z3, (0, 0)) == (0, 0), "3x: origin stays the origin")

    # A click at the far corner of a 3x window must land inside the canvas, not one px past it.
    check(call(z3, (730 * 3 - 1, 420 * 3 - 1)) == (729, 419), f"3x: last window px maps to last canvas px; got {call(z3, (2189, 1259))}")

    if failures:
        print("FAIL: window->LCD transform")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: window->LCD transform (band offset applied on y only, band clicks rejected)")


if __name__ == "__main__":
    main()

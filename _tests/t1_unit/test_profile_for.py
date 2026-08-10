# SPDX-License-Identifier: MIT
# TIER: T1 — profile_for capture geometry (viewport fit + letterbox derivation)
"""T1 — hud_layout.profile_for: the OCR capture geometry for a desktop size.

Every auto-driven frame is cropped at whatever this returns, so a wrong answer does not
degrade — it reads a different part of the screen and the badge classifies nothing. The
geometry is also unverifiable on the author's machine for any resolution their display
cannot produce, which is why it is derived rather than measured, and why the derivation
needs a test rather than a live drive per size.

The letterbox arm exists because the game fits a 16:9 viewport into a taller desktop:
measured on a 1920x1200 capture as exactly 60px of pure black top and bottom, HUD at
(1650,75) — the 1080p geometry plus the bar. Sweeping the HUD origin +/-4px through the
production badge matcher put a sharp minimum at dead centre (3.6 mean-abs-diff, against
18.7 one pixel out in x and 28.8 in y).

Every expected tuple is pinned LITERALLY rather than derived from the module: a test that
recomputes the arithmetic under test agrees with any mutation of it and stops
discriminating (`principles.md` § "Test real logic, not ceremony").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.hud_layout import PROFILES, profile_for  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def check_geometry(w: int, h: int, capture, hud, label: str) -> None:
    p = profile_for(w, h)
    if p is None:
        FAILURES.append(f"{label}: {w}x{h} was refused, expected a profile")
        return
    check(p.capture_region == capture, f"{label}: {w}x{h} capture_region expected {capture}, got {p.capture_region}")
    check(p.hud_bbox == hud, f"{label}: {w}x{h} hud_bbox expected {hud}, got {p.hud_bbox}")
    # The capture must actually contain the HUD — the invariant a bar offset applied to one
    # and not the other would break, while both still looked individually plausible.
    cl, ct, cr, cb = p.capture_region
    hx, hy, hw, hh = p.hud_bbox
    check(
        cl <= hx and ct <= hy and hx + hw <= cr and hy + hh <= cb,
        f"{label}: {w}x{h} HUD {p.hud_bbox} is not inside capture {p.capture_region}",
    )
    check(
        p.hud_bbox_in_capture == (hx - cl, hy - ct, hw, hh),
        f"{label}: {w}x{h} hud_bbox_in_capture expected {(hx - cl, hy - ct, hw, hh)}, got {p.hud_bbox_in_capture}",
    )


def main() -> int:
    # --- 16:9, zero bar. The two hand-calibrated baselines plus the two derived sizes. ---
    check_geometry(1920, 1080, (960, 0, 1920, 540), (1650, 15, 262, 360), "16:9")
    check_geometry(2560, 1440, (1280, 0, 2560, 720), (2200, 20, 350, 480), "16:9")
    check_geometry(3840, 2160, (1920, 0, 3840, 1080), (3300, 30, 525, 720), "16:9")
    check_geometry(3200, 1800, (1600, 0, 3200, 900), (2750, 25, 438, 600), "16:9 derived")

    # --- 16:10, letterboxed. 1920x1200 is the MEASURED one; the others follow the same fit. ---
    check_geometry(1920, 1200, (960, 60, 1920, 600), (1650, 75, 262, 360), "16:10 measured")
    check_geometry(2560, 1600, (1280, 80, 2560, 800), (2200, 100, 350, 480), "16:10")
    check_geometry(3840, 2400, (1920, 120, 3840, 1200), (3300, 150, 525, 720), "16:10")

    # The letterbox must move the geometry and nothing else: same desktop width, same HUD
    # size and x as the 16:9 profile of that width, y shifted by exactly the bar.
    p1080, p1200 = profile_for(1920, 1080), profile_for(1920, 1200)
    check(
        p1200.hud_bbox[0] == p1080.hud_bbox[0] and p1200.hud_bbox[2:] == p1080.hud_bbox[2:],
        f"letterbox must change only y: {p1080.hud_bbox} -> {p1200.hud_bbox}",
    )
    check(p1200.hud_bbox[1] - p1080.hud_bbox[1] == 60, f"1920x1200 bar must be 60px, got {p1200.hud_bbox[1] - p1080.hud_bbox[1]}")

    # --- Refused. Each would otherwise read at a wrong screen position. ---
    for w, h, why in (
        (3440, 1440, "21:9 — wider than 16:9, pillarboxing unmeasured"),
        (2560, 1080, "21:9 — wider than 16:9"),
        (1600, 1200, "4:3 — fitted viewport is 900p, under the 1080p floor"),
        (1280, 1024, "5:4 — fitted viewport is 720p"),
        (1366, 768, "marginally WIDER than 16:9 — 1366*9 > 768*16, so the aspect gate takes it"),
        (1280, 720, "720p — exactly 16:9 but under the floor; this is the row that isolates it"),
        # Isolates the width%16 integrality guard: 1922 is NOT wider than 16:9 and its
        # fitted viewport is 1081, so it clears both other gates and only the divisibility
        # check can refuse it. Without this row, deleting that guard leaves the suite green
        # (`principles.md` § "a check that has never been observed to fail has not been
        # shown to work") — every other refusal here fails the floor for its own reason.
        (1922, 1300, "width has no integer 16:9 height — 1922*9/16 is not whole"),
    ):
        check(profile_for(w, h) is None, f"{w}x{h} must be refused ({why}), got a profile")

    # --- The observed-record dict must agree with the derivation it claims to record. ---
    for (w, h), p in PROFILES.items():
        check(p.verified, f"PROFILES[{w}x{h}] must carry verified=True — the dict is the observed record")
        check((p.desktop_w, p.desktop_h) == (w, h), f"PROFILES[{w}x{h}] carries desktop {p.desktop_w}x{p.desktop_h}")

    for f in FAILURES:
        print(f"  {f}")
    print(f"{'FAIL' if FAILURES else 'PASS'}: profile-for ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

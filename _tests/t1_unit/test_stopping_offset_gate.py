# SPDX-License-Identifier: MIT
# TIER: T1 — stopping-offset badge gate (_accept_stopping_offset)
"""Locks `_accept_stopping_offset(offset_cm, badge)` — the badge==STOPPED gate on the
green ±cm stopping-offset read.

The game shows the ±cm offset only after MOVING→STOPPED (STOPPED badge up). The green
read is phantom-prone — scenery-green bleed through the semi-transparent HUD can
fabricate a ±cm value mid-transit — so it is trusted only when the badge groundtruth
says STOPPED. The badge is the most reliable read on the HUD (canonical, clean
pixel-diff separation), strictly more reliable than the speed/distance digit reads, so
it is the SOLE gate — deliberately NOT speed-gated, because folding the noisier speed
read into a badge that is already groundtruth would only add false-rejects. Same
badge-only rule as FIRE_AT_STATION: badge read > (distance, speed).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import _accept_stopping_offset  # noqa: E402

# (offset_cm, badge, expected)
# fmt: off
CASES = [
    # Real offset with the STOPPED badge up — accepted, sign + zero preserved.
    (40,   "STOPPED", 40),
    (-11,  "STOPPED", -11),
    (0,    "STOPPED", 0),      # stopped exactly on the mark
    # Green read while the badge says moving/passing — phantom scenery bleed, rejected.
    (40,   "MOVING",  None),
    (40,   "PASSING", None),
    (-11,  "MOVING",  None),
    # Badge unreadable (OCR dropout) — cannot confirm stopped, so reject.
    (40,   None,      None),
    # No green read at all — None regardless of badge.
    (None, "STOPPED", None),
    (None, "MOVING",  None),
    (None, None,      None),
]
# fmt: on


def main():
    failures = []
    for offset_cm, badge, expected in CASES:
        got = _accept_stopping_offset(offset_cm, badge)
        if got != expected:
            failures.append(f"  _accept_stopping_offset({offset_cm!r}, {badge!r}) = {got!r}, expected {expected!r}")

    if failures:
        print("FAIL: stopping-offset gate")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: stopping-offset gate ({len(CASES)} cases — badge==STOPPED accept, phantom + dropout reject)")


if __name__ == "__main__":
    main()

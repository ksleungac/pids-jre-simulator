# TIER: T1 — speed domain clamp + decimal-slip rectify (_rectify_speed)
"""Locks `_rectify_speed(value)` — the speed value-domain hardening.

Drivable top speed is 135 km/h; reads are accepted up to a 140 slack ceiling. The
failure this rectifies: the speed reader's decimal-point detection fails, so the
tenths digit concatenates onto the integer (72.7 → "727"). Because the game shows a
single decimal place, the overshoot is always exactly one extra trailing digit, so
`//10` recovers the integer part; a re-check against the ceiling drops genuine
garbage to None. Real speeds — including the legit 3-digit 100–135 band — are ≤140
and pass through untouched (so the T3 real-speed fixtures are unaffected).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.ocr import _rectify_speed  # noqa: E402

# (raw_value, expected)
# fmt: off
CASES = [
    (None, None),
    # In-range reads pass through unchanged.
    (0,    0),
    (72,   72),
    (99,   99),
    (100,  100),    # legit 3-digit speed
    (120,  120),
    (135,  135),    # drivable max
    (140,  140),    # ceiling inclusive
    # Decimal slip — one tenths digit appended; //10 recovers it.
    (727,  72),     # 72.7 → "727"
    (999,  99),     # 99.9 → "999"
    (1350, 135),    # 135.0 → "1350"
    (1358, 135),    # 135.8 → "1358"
    (200,  20),     # 20.0 → "200"
    (141,  14),     # 14.1 → "141" (just over ceiling)
    # Genuine garbage — still out of range after one drop → dropped to None.
    (9999, None),   # //10 = 999, still > 140
    (14000, None),  # //10 = 1400, still > 140
]
# fmt: on


def main():
    failures = []
    for value, expected in CASES:
        got = _rectify_speed(value)
        if got != expected:
            failures.append(f"  _rectify_speed({value!r}) = {got!r}, expected {expected!r}")

    if failures:
        print("FAIL: speed rectify")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: speed rectify ({len(CASES)} cases — in-range passthrough, decimal-slip recover, garbage drop)")


if __name__ == "__main__":
    main()

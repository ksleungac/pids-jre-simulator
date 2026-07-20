# TIER: T1 — distance plausibility guard (guard_distance)
"""Locks `guard_distance` — the physical-motion gate + hold-last-good on the remaining-distance read.

A degraded 1080p frame mis-segments distance into a single-frame spike (1372→3→1257), correlated
with the speed decimal-slip; the badge-reject gate misses these (badge still reads MOVING). But
distance obeys physics: between samples the train moves ≤ v·Δt. Reject a read that moves further
from the last VALID distance than MAX_DRIVABLE_SPEED_KMH·Δt (+ slack) and hold-last-good. Reset the
anchor on a reference-frame change (prev_badge != "MOVING": departure STOPPED→MOVING, or a
mid-segment PASSING→MOVING where distance legitimately jumps UP to the next stop) — accept there
unconditionally. No consensus latch; a double spike is rejected on both frames and self-heals as Δt
grows. Design consult: third-man 2026-07-21.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import DISTANCE_GUARD_SLACK_M, guard_distance  # noqa: E402
from auto_input.ocr import MAX_DRIVABLE_SPEED_KMH  # noqa: E402

DT = 3.0  # representative OCR interval (measured ~3s in drive logs)
MAXD = (MAX_DRIVABLE_SPEED_KMH / 3.6) * DT + DISTANCE_GUARD_SLACK_M  # ~162.5 m at dt=3

# (prev_badge, badge, distance, last_valid, dt) -> (value, rejected)
# fmt: off
CASES = [
    # Boot: no anchor yet → accept the first read.
    ("MOVING",  "MOVING", 1695, None, DT, (1695, False)),
    # OCR dropout (None) → pass through, not a "reject".
    ("MOVING",  "MOVING", None, 1695, DT, (None, False)),
    # Plausible approach step (well within v·Δt) → accepted.
    ("MOVING",  "MOVING", 1600, 1695, DT, (1600, False)),
    # Spike DOWN (1372→3) while steady MOVING → implausible, hold last valid.
    ("MOVING",  "MOVING",    3, 1372, DT, (1372, True)),
    # Spike UP (152→2242) → implausible, hold last valid.
    ("MOVING",  "MOVING", 2242,  152, DT, (152,  True)),
    # Reference-frame reset — departure (prior STOPPED): 3m → 1800m accepted unconditionally.
    ("STOPPED", "MOVING", 1800,    3, DT, (1800, False)),
    # Reference-frame reset — PASSING→MOVING up-jump (prior PASSING): accepted.
    ("PASSING", "MOVING", 1800,   50, DT, (1800, False)),
    # Reference-frame reset — MOVING→PASSING (current PASSING): a big change is accepted, NOT
    # rejected, even though |500-1695| >> bound (the gap the prior-only reset missed).
    ("MOVING",  "PASSING", 500, 1695, DT, (500,  False)),
    # badge=None degraded frame while prior was MOVING → STILL gated (a spike can't poison the anchor).
    ("MOVING",  None,        3, 1372, DT, (1372, True)),
    # Boundary: a change within the bound (Δ=162 ≤ ~162.5) is KEPT.
    ("MOVING",  "MOVING", 1533, 1695, DT, (1533, False)),
    # Just past the bound (Δ=170) → rejected, hold.
    ("MOVING",  "MOVING", 1525, 1695, DT, (1695, True)),
    # Long dropout: a big legit change passes because Δt scales the bound.
    ("MOVING",  "MOVING", 1000, 1695, 20.0, (1000, False)),
]
# fmt: on


def main() -> int:
    fails = []
    for prev_badge, badge, dist, last_valid, dt, expected in CASES:
        got = guard_distance(prev_badge, badge, dist, last_valid, dt)
        if got != expected:
            fails.append(f"  guard_distance({prev_badge!r}, {badge!r}, {dist}, {last_valid}, {dt}): expected {expected}, got {got}")

    # Double spike: both frames rejected + held (no consensus accept); self-heals only when a
    # plausible read near the anchor returns.
    v1, r1 = guard_distance("MOVING", "MOVING", 3, 1372, DT)  # spike 1 → hold
    v2, r2 = guard_distance("MOVING", "MOVING", 5, v1, 2 * DT)  # spike 2 vs the held anchor → still rejected
    if not (r1 and r2 and v1 == 1372 and v2 == 1372):
        fails.append(f"  double-spike: expected both rejected holding 1372, got ({v1},{r1}) ({v2},{r2})")

    if fails:
        print(f"FAIL: distance-guard ({len(fails)} case(s)):")
        print("\n".join(fails))
        return 1
    print(f"PASS: distance-guard ({len(CASES)} cases + double-spike)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: MIT
# TIER: T1 — distance plausibility guard (guard_distance)
"""Locks `guard_distance` — the physical-motion gate + hold-last-good on the remaining-distance read.

A degraded 1080p frame mis-segments distance into a single-frame spike (1372→3→1257), correlated
with the speed decimal-slip; the badge-reject gate misses these (badge still reads MOVING). But
distance obeys physics: between samples the train moves ≤ v·Δt. Reject a read that moves further
from the last VALID distance than MAX_DRIVABLE_SPEED_KMH·Δt (+ slack) and hold-last-good.

Re-anchor only on a **re-point** — the HUD switching its distance to a NEW target. Two conditions,
both required: the pair is in DISTANCE_RETARGET_PAIRS (STOPPED→STOPPED dwell refresh, PASSING→
PASSING next passed station, PASSING→MOVING to the stopping station) AND the jump is UPWARD, since
a re-point always goes from something just reached (≈0) to something farther.
No consensus latch; a double spike is rejected on both frames and self-heals as Δt grows.
Design consult: third-man 2026-07-21; re-point pairs + direction condition 2026-08-11.
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
    # NOT a re-point — departure. The dwell refresh is guaranteed to complete while the badge
    # still reads STOPPED (author-stated 2026-08-11), so by the departure edge the anchor is
    # already the next station's distance and the departure's own motion is ~3.75m against a
    # ~162m allowance. Was (1800, False) until 2026-08-11: that fixture encoded the design's
    # assumption ("accepted unconditionally"), not an observed drive.
    ("STOPPED", "MOVING", 1800,    3, DT, (3,    True)),
    # Same for a departure toward a passed-through station.
    ("STOPPED", "PASSING", 1800,   3, DT, (3,    True)),
    # Re-point — PASSING→MOVING up-jump (prior PASSING): accepted.
    ("PASSING", "MOVING", 1800,   50, DT, (1800, False)),
    # Re-point — dwell refresh, both frames STOPPED: accepted.
    ("STOPPED", "STOPPED", 1400,   3, DT, (1400, False)),
    # Re-point — consecutive passed-through stations, both frames PASSING: accepted.
    ("PASSING", "PASSING",  900, 645, DT, (900,  False)),
    # DOWNWARD jump on a reference-in-flux pair is NOT a re-point — a re-point always goes from
    # something just reached (≈0) to something farther. This is the frame after a one-frame
    # PASSING misread: it presents as PASSING→MOVING, identical by badge to a genuine one, and
    # only the direction separates them. Was accepted pre-2026-08-11 → まもなく ~400m early.
    ("PASSING", "MOVING",     5, 1330, DT, (1330, True)),
    ("PASSING", "PASSING",    5, 1330, DT, (1330, True)),
    ("STOPPED", "STOPPED",    5, 1330, DT, (1330, True)),
    # MOVING→PASSING is physically impossible (auto_input/README.md § "Only four badge
    # transitions are physically possible"), so there is no re-point for an exemption to absorb
    # → ordinary gated path. NOT a claim that the badge is unreliable; the badge outranks the
    # distance read. Was (500, False) pre-2026-08-11, which is the model that change corrected.
    ("MOVING",  "PASSING", 500, 1695, DT, (1695, True)),
    # ...and UPWARD too. This is the case that isolates the removal: a downward MOVING→PASSING is
    # gated by the direction condition whether or not PASSING is treated as reference-in-flux, so
    # only an upward one discriminates. Mutation-proven 2026-08-11 (restoring the old
    # `badge in ("STOPPED","PASSING")` must fail HERE).
    ("MOVING",  "PASSING", 1800,  50, DT, (50,   True)),
    # badge=None degraded frame while prior was MOVING → STILL gated (a spike can't poison the anchor).
    ("MOVING",  None,        3, 1372, DT, (1372, True)),
    # MOVING→STOPPED is deliberately NOT a re-point pair. The dwell refresh fires only after the
    # badge reads STOPPED, so physically it lands on STOPPED→STOPPED; a coarse SAMPLE_INTERVAL_S
    # can make it first OBSERVED here, and that timing artifact is explicitly not designed around
    # (author-stated 2026-08-11 — the lever is the interval, not the guard). Pinned so the pair
    # is not quietly added back.
    ("MOVING",  "STOPPED", 1400,  40, DT, (40,   True)),
    # prev_badge=None (set by _reanchor_to_app on a click-jump, and on the frame after a boot whose
    # first badge read failed) with an anchor already held → gated, NOT exempt. The game's distance
    # is continuous across a click-jump — only the APP moved — so there is no re-point to absorb.
    (None,      "MOVING",    3, 1372, DT, (1372, True)),
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

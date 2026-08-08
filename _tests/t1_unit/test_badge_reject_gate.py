# SPDX-License-Identifier: MIT
# TIER: T1 — badge-reject score gate (_apply_badge_reject_gate)
"""Locks `_apply_badge_reject_gate` — the cross-attribute hardening that drops
low-confidence digit reads on a badge-reject frame.

When the badge fails to classify (`badge is None` — classifier diff > BADGE_DIFF_REJECT,
a degraded frame: black-screen / mid-animation), the other digit reads are phantom-prone:
sampling the drive logs, speed/distance land at score median ~0.60 (the docs' "<0.6
random-match danger zone") vs ~0.90 when the badge reads. So when the most reliable HUD
read fails ("badge > distance, speed"), any read below BADGE_NONE_SCORE_GATE is dropped.
CONDITIONAL on badge=None, NOT a global floor — a real 0.6 read is kept whenever the
badge confirms the frame. Offset is absent (already badge-gated to STOPPED).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import BADGE_NONE_SCORE_GATE, _apply_badge_reject_gate  # noqa: E402

T = BADGE_NONE_SCORE_GATE  # 0.80

# (badge, speed, s_score, dist, d_score, limit, sl_score) -> (speed, dist, limit, gated)
# fmt: off
CASES = [
    # Badge readable → gate is a NO-OP; low scores pass through untouched (a real low read
    # is trusted when the badge confirms the frame).
    ("MOVING",  73, 0.55, 500, 0.55, 60, 0.55, (73, 500, 60, ())),
    ("STOPPED",  0, 0.60, 999, 0.60, 45, 0.60, (0, 999, 45, ())),
    # Badge=None + all reads below gate → all dropped, all named.
    (None,      73, 0.55, 500, 0.60, 60, 0.70, (None, None, None, ("speed", "distance", "speed_limit"))),
    # Badge=None + all reads above gate → all kept (a strong read on a degraded frame stays).
    (None,      73, 0.95, 500, 0.90, 60, 0.85, (73, 500, 60, ())),
    # Badge=None + mixed → only the sub-threshold reads drop.
    (None,      73, 0.55, 500, 0.95, 60, 0.70, (None, 500, None, ("speed", "speed_limit"))),
    # Badge=None + a field already None → not "gated" (nothing to drop); others still gate.
    (None,    None, 1.00, 500, 0.50, None, 1.00, (None, None, None, ("distance",))),
    # Boundary: score exactly at the gate is KEPT (strict <).
    (None,      73, T,    500, T,    60, T,    (73, 500, 60, ())),
    # Just below the boundary → dropped.
    (None,      73, T - 0.001, 500, T - 0.001, 60, T - 0.001,
                                                (None, None, None, ("speed", "distance", "speed_limit"))),
]
# fmt: on


def main() -> int:
    fails = []
    for badge, sp, ss, ds, dss, lim, ls, expected in CASES:
        got = _apply_badge_reject_gate(badge, sp, ss, ds, dss, lim, ls)
        if got != expected:
            fails.append(f"  badge={badge} sp={sp}/{ss} ds={ds}/{dss} lim={lim}/{ls}: expected {expected}, got {got}")
    if fails:
        print(f"FAIL: badge-reject-gate ({len(fails)}/{len(CASES)}):")
        print("\n".join(fails))
        return 1
    print(f"PASS: badge-reject-gate ({len(CASES)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

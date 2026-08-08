# SPDX-License-Identifier: MIT
"""Offline verification of the re-entry consensus latch — no game, no OCR.

`AutoDriver._maybe_reentry` commits a silent-advance only after TWO consecutive
cycles resolve to the SAME target ("1A"/"1B"). This drives synthetic probe
sequences through a real `_Detector` + a fake `sim` and asserts the latch
commits / re-latches / clears correctly. Pure state-machine logic — the game is
only needed for the OCR reads, which this change does not touch.

    uv run _dev_scripts/verify_reentry_consensus.py

Dev-only; does not ship.
"""

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_input.driver import AutoDriver, _Detector  # noqa: E402


def _make_driver() -> AutoDriver:
    """An AutoDriver with only the two attributes _maybe_reentry touches.

    _maybe_reentry / _resolve_reentry_target read self.sim + self._detector only,
    so we skip the heavy __init__ (camera/profile/templates) entirely.
    """
    ad = object.__new__(AutoDriver)
    ad._detector = _Detector()
    ad.sim = SimpleNamespace(
        pending_next_pa=False,
        pending_silent_advance=None,
        state=SimpleNamespace(at_station=True, curr_stop=0),
        # Landing stop has pa=2 so the 1B target is resolvable (pa=1 has no 1B).
        stops=[{"pa": ["p"]}, {"pa": ["p", "p"]}],
    )
    return ad


def _probe(ad: AutoDriver, kind: str):
    """Run one cycle resolving to `kind`, return the committed target this cycle.

    `kind` configures the detector/sim so _resolve_reentry_target yields the
    intended read; the latch (the state under test) is preserved across probes.
    Returns the silent-advance committed THIS cycle ("1A"/"1B") or None.
    """
    det = ad._detector
    ad.sim.pending_next_pa = False
    ad.sim.pending_silent_advance = None
    ad.sim.state.at_station = True
    # Flags reset each probe; the live read drives inferred_state. (Commit
    # mutates these, but the next probe's setup overwrites them — only the
    # reentry_latch must survive across probes, and nothing here touches it.)
    det.departure_observed = False
    det.arrival_observed = False

    if kind == "1A":  # game CRUISING: MOVING, speed>=30, dist>lead
        det.prev_badge = "MOVING"
        ad._maybe_reentry(speed=60, distance=2000)
    elif kind == "1B":  # game ARRIVING: MOVING, dist<=lead
        det.prev_badge = "MOVING"
        ad._maybe_reentry(speed=20, distance=300)
    elif kind == "noop_parked":  # game STOPPED/IDLE at platform
        det.prev_badge = "STOPPED"
        ad._maybe_reentry(speed=0, distance=None)
    elif kind == "live_fire":  # a normal fire landed this cycle
        det.prev_badge = "MOVING"
        ad.sim.pending_next_pa = True
        ad._maybe_reentry(speed=60, distance=2000)
    elif kind == "app_moving":  # app already at 1A/1B
        det.prev_badge = "MOVING"
        ad.sim.state.at_station = False
        ad._maybe_reentry(speed=60, distance=2000)
    else:
        raise ValueError(kind)

    return ad.sim.pending_silent_advance


# (name, [probe kinds], expected commit on the FINAL probe, expected #commits)
CASES = [
    ("same-target commits on 2nd", ["1A", "1A"], "1A", 1),
    ("single probe does NOT commit", ["1A"], None, 0),
    ("changed target re-latches, no early commit", ["1A", "1B"], None, 0),
    ("1A,1B,1B commits 1B on 3rd", ["1A", "1B", "1B"], "1B", 1),
    ("no-op breaks the streak", ["1A", "noop_parked", "1A"], None, 0),
    ("1A,noop,1A,1A commits on 4th", ["1A", "noop_parked", "1A", "1A"], "1A", 1),
    ("live fire stands re-entry down", ["1A", "live_fire", "1A"], None, 0),
    ("app moving -> no re-entry", ["app_moving", "app_moving"], None, 0),
    ("two arrivals commit 1B", ["1B", "1B"], "1B", 1),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failures = 0
    for name, seq, want_final, want_count in CASES:
        ad = _make_driver()
        commits = []
        final = None
        for kind in seq:
            final = _probe(ad, kind)
            if final is not None:
                commits.append(final)
        ok = (final == want_final) and (len(commits) == want_count)
        # Latch must be clear after a commit, and reflect the last target while waiting.
        latch = ad._detector.reentry_latch
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{mark}] {name:42} seq={seq} -> final={final} " f"commits={commits} latch={latch}")
    print()
    print("ALL PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

# TIER: T1 — at-station fire (AutoDriver._fire_at_station)
"""Locks `_fire_at_station`'s reachability contract: a STOPPED badge while the app
is in transit (1A/1B) must ALWAYS land the STOPPING transition.

The 2026-07-24 rule replaced the old cnt_pa REFUSAL ("arrival likely missed" →
skip → app stuck at 1A until click-jump) with a silent approach-PA drain: cnt_pa
is normalized to the last approach entry so the synthesized press enters STOPPING
instead of playing a leftover approach PA.

Stubs the sim with SimpleNamespace and calls the method unbound — same technique
as test_reentry_target.py.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import AutoDriver  # noqa: E402


def fire(*, at_station=False, curr_stop=0, cnt_pa=0, pa=("a", "b")):
    """Run one _fire_at_station against a stubbed sim; return the sim state."""
    sim = SimpleNamespace(
        pending_next_pa=False,
        state=SimpleNamespace(at_station=at_station, curr_stop=curr_stop, cnt_pa=cnt_pa, is_last_pa=False),
        stops=[{"name": "X", "pa": list(pa)}],
    )
    fake_self = SimpleNamespace(sim=sim, _last_fire=None)
    AutoDriver._fire_at_station(fake_self)
    return sim


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # 1. REACHABILITY (the rule): arrival missed — pa=2 but cnt_pa still 0 (app at 1A).
    #    Must drain to the last approach entry and land the press. Discriminates:
    #    restoring the old refusal leaves pending_next_pa False.
    sim = fire(cnt_pa=0, pa=("approach0", "approach1"))
    check(sim.pending_next_pa is True, "reachability: press must land despite missed arrival (was: refusal → stuck at 1A)")
    check(sim.state.cnt_pa == 1, f"reachability: cnt_pa must drain to last approach entry, got {sim.state.cnt_pa}")
    check(sim.state.is_last_pa is True, "reachability: drain must keep the is_last_pa ≡ cnt_pa>=len-1 invariant")

    # 2. Normal 1B: cnt_pa already at the last approach PA — press lands, no drain.
    sim = fire(cnt_pa=1, pa=("approach0", "approach1"))
    check(sim.pending_next_pa is True, "normal 1B: press must land")
    check(sim.state.cnt_pa == 1, "normal 1B: cnt_pa untouched")

    # 3. pa=1 stop (1A≡1B collapse): cnt_pa=0 == len(pa)-1 — press lands, no drain.
    sim = fire(cnt_pa=0, pa=("only",))
    check(sim.pending_next_pa is True, "pa=1: press must land")
    check(sim.state.cnt_pa == 0, "pa=1: cnt_pa untouched")

    # 4. App parked (1C / boot at start station): skip — the app-parked guard is what
    #    lets the detector emit FIRE_AT_STATION unconditionally on STOPPED.
    sim = fire(at_station=True, cnt_pa=0)
    check(sim.pending_next_pa is False, "parked: fire must skip (already STOPPING)")

    if failures:
        print("FAIL: at-station fire")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: at-station fire (reachability drain + normal 1B + pa=1 collapse + parked skip)")


if __name__ == "__main__":
    main()

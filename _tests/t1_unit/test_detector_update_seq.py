# TIER: T1 — detector direct read (_Detector.update sample sequences)
"""Locks `_Detector.update()` — the DIRECT-READ path: raw (distance, speed, badge)
samples in → PA-fire event names + observed-flags out.

This is the part that actually *reads the sensors and decides* (threshold crossings),
as opposed to `inferred_state()`, which only formats the flags this method sets. The
2026-07-16 re-entry bug was NOT in here (the detector handles PASSING correctly — see
cases D and G), but this is where the same class of bug *could* live, so the raw→decision
behaviors are pinned.

Stateful unit test: one `_Detector`, exercised over a call sequence, no pygame/I/O.
Cases D and G are facets of the cross-cutting `PASSING ≡ MOVING` invariant (see
_tests/README.md § "Build plan").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import _Detector  # noqa: E402


def run(samples, **detector_kw):
    """Feed (distance, speed, badge) samples through a fresh detector; collect events."""
    d = _Detector(**detector_kw)
    events = []
    for dist, speed, badge in samples:
        events.extend(d.update(dist, speed, badge))
    return d, events


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # A. Departure fires once when own-speed enters the audible band on a fresh segment.
    d, ev = run([(2000, 0, "STOPPED"), (2000, 5, "MOVING"), (2000, 35, "MOVING")])
    check(ev.count("FIRE_DEPARTURE") == 1, f"A departure: expected 1 FIRE_DEPARTURE, got {ev.count('FIRE_DEPARTURE')} ({ev})")
    check(d.departure_observed is True, "A departure: departure_observed should be True")

    # B. No re-fire when speed dips below 30 and re-crosses (the flag debounces —
    #    "current speed lies" case: a cruising train slowing mid-segment isn't departing).
    d, ev = run([(2000, 0, "STOPPED"), (2000, 5, "MOVING"), (2000, 35, "MOVING"), (2000, 25, "MOVING"), (2000, 40, "MOVING")])
    check(ev.count("FIRE_DEPARTURE") == 1, f"B debounce: expected exactly 1 FIRE_DEPARTURE across dip+recross, got {ev.count('FIRE_DEPARTURE')}")

    # C. Arrival fires once on MOVING with distance <= lead (level test).
    d, ev = run([(2000, 0, "STOPPED"), (2000, 35, "MOVING"), (800, 40, "MOVING")])
    check(ev.count("FIRE_ARRIVAL") == 1, f"C arrival: expected 1 FIRE_ARRIVAL, got {ev.count('FIRE_ARRIVAL')} ({ev})")

    # D. [PASSING facet] PASSING does NOT arrive even at distance <= lead — its
    #    distance is to the passing station, not the stopping target.
    d, ev = run([(2000, 0, "STOPPED"), (2000, 35, "MOVING"), (300, 40, "PASSING")])
    check("FIRE_ARRIVAL" not in ev, f"D passing-skip-arrival: PASSING@dist=300 must NOT fire arrival ({ev})")
    check(d.arrival_observed is False, "D passing-skip-arrival: arrival_observed should stay False")

    # E. STOPPED -> MOVING starts a new segment: resets all three observed-flags.
    d, ev = run([(2000, 5, "MOVING")], prev_badge="STOPPED", departure_observed=True, arrival_observed=True, at_station_observed=True)
    check("STOPPED->MOVING" in ev, f"E reset: expected STOPPED->MOVING event ({ev})")
    check(not d.departure_observed and not d.arrival_observed and not d.at_station_observed, "E reset: all three flags should reset to False")

    # F. Black-screen cross-reject: prev=STOPPED, moving-ish badge at speed 0 is
    #    rejected (the game can't move without rendering speed climbing from 0).
    d, ev = run([(None, 0, "PASSING")], prev_badge="STOPPED")
    check("CROSS_REJECT" in ev, f"F cross-reject: expected CROSS_REJECT ({ev})")
    check("STOPPED->MOVING" not in ev, "F cross-reject: must NOT begin a segment")
    check(d.prev_badge == "STOPPED", "F cross-reject: prev_badge should stay STOPPED (read rejected)")

    # G. [PASSING facet] Departure fires through a PASSING-badged rollout — PASSING is
    #    a moving segment, departure is speed-based and badge-independent. This is the
    #    detector's slice of the incident path, and it handles it correctly; the bug
    #    lived in the re-entry resolver (test_reentry_target.py), not here.
    d, ev = run([(2000, 0, "STOPPED"), (2000, 5, "PASSING"), (2000, 20, "PASSING"), (2000, 35, "MOVING")])
    check(
        ev.count("FIRE_DEPARTURE") == 1,
        f"G passing-departure: expected 1 FIRE_DEPARTURE through PASSING rollout, got {ev.count('FIRE_DEPARTURE')} ({ev})",
    )

    # ── Departure-as-level-test (#82). H and I are the two ways the old crossing
    #    (prev_speed < 30 <= speed) lost a departure PERMANENTLY for the segment; both
    #    fire under the level test. J pins the ceiling. Each discriminates: H/I fail if
    #    the crossing is restored, J fails if the upper bound is dropped.

    # H. Stale-high prev_speed. prev_speed only updates on a non-None read, so dropped
    #    reads through deceleration + dwell carry the pre-station cruise value into the
    #    next departure. The crossing can never satisfy prev_speed < 30 again.
    d, ev = run([(2000, 45, "MOVING")], prev_badge="STOPPED", prev_speed=78)
    check(ev.count("FIRE_DEPARTURE") == 1, f"H stale-prev-speed: departure must fire with prev_speed=78 stale, got {ev}")

    # I. Absent prev_speed — thread start, or post-click-jump (_reanchor_to_app nulls it).
    d, ev = run([(2000, 35, "MOVING")], prev_badge="STOPPED", prev_speed=None)
    check(ev.count("FIRE_DEPARTURE") == 1, f"I absent-prev-speed: departure must fire with prev_speed=None, got {ev}")

    # J. Ceiling: at or above the stale bound the PA is unrecoverable and re-entry's
    #    SILENT 1A advance owns it — the level test must NOT fire. Cold boot mid-cruise.
    d, ev = run([(2000, 86, "MOVING")])
    check("FIRE_DEPARTURE" not in ev, f"J stale-ceiling: speed 86 is re-entry territory, must not fire departure ({ev})")
    check(d.departure_observed is False, "J stale-ceiling: departure_observed should stay False")

    # K. Band edges are [30, 60). Literals DELIBERATELY hardcoded, not imported from
    #    driver — importing the constants under test would make this pass for any band
    #    (see principles.md § "Test real logic, not ceremony"). Widening the band is a
    #    behaviour change and must break this line.
    d, ev = run([(2000, 30, "MOVING")])
    check("FIRE_DEPARTURE" in ev, f"K lower-edge: speed == 30 must fire ({ev})")
    d, ev = run([(2000, 59, "MOVING")])
    check("FIRE_DEPARTURE" in ev, f"K in-band-top: speed == 59 must fire ({ev})")
    d, ev = run([(2000, 60, "MOVING")])
    check("FIRE_DEPARTURE" not in ev, f"K upper-edge: speed == 60 must NOT fire ({ev})")

    if failures:
        print("FAIL: detector update() direct-read sequences")
        print("\n".join(failures))
        sys.exit(1)
    print(
        "PASS: detector update() direct-read sequences (A departure, B debounce, C arrival, D passing-skip, "
        "E reset, F cross-reject, G passing-departure, H stale-prev-speed, I absent-prev-speed, "
        "J stale-ceiling, K band-edges)"
    )


if __name__ == "__main__":
    main()

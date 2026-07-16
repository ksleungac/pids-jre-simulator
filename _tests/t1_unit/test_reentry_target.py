# TIER: T1 — re-entry resolver (_resolve_reentry_target)
"""Locks `AutoDriver._resolve_reentry_target()` — THE 2026-07-16 bug site.

The resolver is a pure read of (prev_badge, speed, distance) + the app-parked guards,
returning the re-entry target "1A" / "1B" / None. The bug was an `or badge=="PASSING"`
clause that forced "1A" (departed) for a PASSING badge at ANY speed — so departing a
station whose next station is a pass-through silent-advanced and ATE the departure PA.

The resolver reads `self.sim.pending_next_pa`, `self.sim.state.at_station`, and
`self._detector`. We stub the sim with a SimpleNamespace and use a real `_Detector`,
then call the method unbound. (Stubbing collaborators keeps this a unit test.)

The `resolve(PASSING,s,d) == resolve(MOVING,s,None)` block is this site's facet of the
cross-cutting `PASSING ≡ MOVING` invariant (see _tests/README.md § "Build plan"):
PASSING behaves like a MOVING whose distance is unusable.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import AutoDriver, _Detector  # noqa: E402

LEAD = 900


def resolve(prev_badge, speed, distance, *, pending_next_pa=False, at_station=True, arr_obs=False, dep_obs=False, lead=LEAD):
    det = _Detector(arrival_lead_m=lead, prev_badge=prev_badge, arrival_observed=arr_obs, departure_observed=dep_obs)
    sim = SimpleNamespace(pending_next_pa=pending_next_pa, state=SimpleNamespace(at_station=at_station))
    fake_self = SimpleNamespace(sim=sim, _detector=det)
    return AutoDriver._resolve_reentry_target(fake_self, speed, distance)


# Spec grid — reachable domain is badge in {MOVING, PASSING} (STOPPED/None are filtered
# upstream by the inferred_state guard). Guards satisfied (parked, no live fire).
#   speed: None / <30 / >=30   ·   dist: None / >lead / <=lead
# Expected derived from the invariant: arrival(1B) = MOVING AND dist<=lead (checked first);
# departure(1A) = speed>=30, badge-independent; else None.
# fmt: off
GRID = [
    # badge,     speed, dist,  expected
    ("MOVING",   None,  None,  None),
    ("MOVING",   None,  2000,  None),
    ("MOVING",   None,  300,   "1B"),
    ("MOVING",   10,    None,  None),
    ("MOVING",   10,    2000,  None),
    ("MOVING",   10,    300,   "1B"),
    ("MOVING",   40,    None,  "1A"),
    ("MOVING",   40,    2000,  "1A"),
    ("MOVING",   40,    300,   "1B"),   # arrival checked BEFORE speed
    ("PASSING",  None,  None,  None),
    ("PASSING",  None,  2000,  None),
    ("PASSING",  None,  300,   None),   # PASSING never arrives (distance unusable)
    ("PASSING",  10,    None,  None),
    ("PASSING",  10,    2000,  None),
    ("PASSING",  10,    300,   None),   # <-- THE INCIDENT: was "1A" on the buggy clause
    ("PASSING",  40,    None,  "1A"),
    ("PASSING",  40,    2000,  "1A"),
    ("PASSING",  40,    300,   "1A"),   # PASSING never returns 1B
]
# fmt: on


def main():
    failures = []

    for badge, speed, dist, expected in GRID:
        got = resolve(badge, speed, dist)
        if got != expected:
            failures.append(f"  resolve(badge={badge!r}, speed={speed}, dist={dist}) = {got!r}, expected {expected!r}")

    # [PASSING facet] departure axis is badge-independent: PASSING resolves like a
    # MOVING whose distance is unusable, and PASSING never resolves to the arrival target.
    for speed in (None, 10, 40):
        for dist in (None, 2000, 300):
            pv = resolve("PASSING", speed, dist)
            mv_nodist = resolve("MOVING", speed, None)
            if pv != mv_nodist:
                failures.append(f"  PASSING != MOVING-no-dist at speed={speed}, dist={dist}: PASSING={pv!r} MOVING(None)={mv_nodist!r}")
            if pv == "1B":
                failures.append(f"  PASSING resolved to 1B at speed={speed}, dist={dist} — arrival is MOVING-only")

    # Regression anchor — the exact incident: parked, next station passes, low speed.
    if resolve("PASSING", 10, 300) is not None:
        failures.append("  REGRESSION: resolve(PASSING, speed=10, dist=300) must be None (was '1A' — ate the departure PA)")

    # Guard branches — resolver stands down regardless of badge.
    if resolve("PASSING", 40, 2000, pending_next_pa=True) is not None:
        failures.append("  guard: pending_next_pa=True must return None (a live fire owns this cycle)")
    if resolve("MOVING", 40, 2000, at_station=False) is not None:
        failures.append("  guard: at_station=False (app already moving) must return None")

    if failures:
        print("FAIL: re-entry resolver")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: re-entry resolver ({len(GRID)} grid cells + PASSING==MOVING facet + regression + guards)")


if __name__ == "__main__":
    main()

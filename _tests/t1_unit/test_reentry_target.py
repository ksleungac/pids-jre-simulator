# SPDX-License-Identifier: MIT
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


def resolve(
    prev_badge, speed, distance, *, pending_next_pa=False, at_station=True, arr_obs=False, dep_obs=False, lead=LEAD, origin_known=False, next_pa=2
):
    det = _Detector(
        arrival_lead_m=lead, prev_badge=prev_badge, arrival_observed=arr_obs, departure_observed=dep_obs, motion_origin_known=origin_known
    )
    # Parked at stop 0; the joined segment lands on stop 1 with `next_pa` approach
    # PAs (default 2 — a real 1B exists; pa=1 collapses 1A ≡ 1B, see facet below).
    stops = [{"pa": ["p"]}, {"pa": ["p"] * next_pa}]
    sim = SimpleNamespace(pending_next_pa=pending_next_pa, state=SimpleNamespace(at_station=at_station, curr_stop=0), stops=stops)
    fake_self = SimpleNamespace(sim=sim, _detector=det, _next_stopping_pa_count=lambda: AutoDriver._next_stopping_pa_count(fake_self))
    return AutoDriver._resolve_reentry_target(fake_self, speed, distance)


# Spec grid — reachable domain is badge in {MOVING, PASSING} (STOPPED/None are filtered
# upstream by the inferred_state guard). Guards satisfied (parked, no live fire).
#   speed: None / 10 (below band) / 40 (IN the audible band) / 80 (stale)
#   dist:  None / >lead / <=lead
# Expected derived from the invariant: arrival(1B) = MOVING AND dist<=lead (checked first);
# departure(1A) = speed >= 60 ONLY, badge-independent; else None.
#
# The 40 rows are #82's partition: [30, 60) belongs to the AUDIBLE level test in
# _Detector.update, so this silent fallback must decline it. Before #82 both keyed on 30
# and this resolver returned "1A" there — inheriting every departure the crossing dropped.
# 60 is hardcoded, not imported, so widening the band breaks these rows (see
# principles.md § "Test real logic, not ceremony").
# fmt: off
GRID = [
    # badge,     speed, dist,  expected
    ("MOVING",   None,  None,  None),
    ("MOVING",   None,  2000,  None),
    ("MOVING",   None,  300,   "1B"),
    ("MOVING",   10,    None,  None),
    ("MOVING",   10,    2000,  None),
    ("MOVING",   10,    300,   "1B"),
    ("MOVING",   40,    None,  None),   # in-band: audible primary owns it
    ("MOVING",   40,    2000,  None),   # in-band: audible primary owns it
    ("MOVING",   40,    300,   "1B"),   # arrival checked BEFORE speed
    ("MOVING",   80,    None,  "1A"),
    ("MOVING",   80,    2000,  "1A"),
    ("MOVING",   80,    300,   "1B"),   # arrival checked BEFORE speed
    ("PASSING",  None,  None,  None),
    ("PASSING",  None,  2000,  None),
    ("PASSING",  None,  300,   None),   # PASSING never arrives (distance unusable)
    ("PASSING",  10,    None,  None),
    ("PASSING",  10,    2000,  None),
    ("PASSING",  10,    300,   None),   # <-- 2026-07-16 INCIDENT: was "1A" on the buggy clause
    ("PASSING",  40,    None,  None),
    ("PASSING",  40,    2000,  None),
    ("PASSING",  40,    300,   None),
    ("PASSING",  80,    None,  "1A"),
    ("PASSING",  80,    2000,  "1A"),
    ("PASSING",  80,    300,   "1A"),   # PASSING never returns 1B
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
    for speed in (None, 10, 40, 80):
        for dist in (None, 2000, 300):
            pv = resolve("PASSING", speed, dist)
            mv_nodist = resolve("MOVING", speed, None)
            if pv != mv_nodist:
                failures.append(f"  PASSING != MOVING-no-dist at speed={speed}, dist={dist}: PASSING={pv!r} MOVING(None)={mv_nodist!r}")
            if pv == "1B":
                failures.append(f"  PASSING resolved to 1B at speed={speed}, dist={dist} — arrival is MOVING-only")

    # Regression anchor — the 2026-07-16 incident: parked, next station passes, low speed.
    if resolve("PASSING", 10, 300) is not None:
        failures.append("  REGRESSION: resolve(PASSING, speed=10, dist=300) must be None (was '1A' — ate the departure PA)")

    # Regression anchor — #82 strictness inversion. This silent fallback must never be
    # satisfiable where the audible primary is: [30, 60) is the primary's band, so a
    # freshly-departed train at 45 km/h resolves to no target no matter the badge.
    for badge in ("MOVING", "PASSING"):
        if resolve(badge, 45, 2000) is not None:
            failures.append(f"  REGRESSION: resolve({badge}, speed=45, dist=2000) must be None — [30,60) is the AUDIBLE primary's band")

    # Guard branches — resolver stands down regardless of badge.
    if resolve("PASSING", 80, 2000, pending_next_pa=True) is not None:
        failures.append("  guard: pending_next_pa=True must return None (a live fire owns this cycle)")
    if resolve("MOVING", 80, 2000, at_station=False) is not None:
        failures.append("  guard: at_station=False (app already moving) must return None")

    # [Provenance facet] BASE ARMING CONDITION: motion of KNOWN origin (a witnessed
    # STOPPED→(MOVING|PASSING) edge) never resolves to ANY target — the audible
    # primary owns the whole segment. Every grid cell goes None, whatever the reads.
    for badge, speed, dist, _expected in GRID:
        got = resolve(badge, speed, dist, origin_known=True)
        if got is not None:
            failures.append(
                f"  PROVENANCE: resolve({badge!r}, speed={speed}, dist={dist}, origin_known=True) = {got!r}, expected None — witnessed motion never re-enters"
            )

    # [pa=1 facet] A pa=1 landing stop has NO distinct 1B (cnt_pa = len(pa)-1 = 0 makes
    # 1A ≡ 1B one AppState, and the single announcement must never be silently skipped):
    # every 1B grid cell declines; the 1A (speed>=60) cells are unaffected. STOPPING on
    # pa=1 is reached by the at-station transition edge itself, not a re-entry landing.
    for badge, speed, dist, expected in GRID:
        got = resolve(badge, speed, dist, next_pa=1)
        if expected == "1B":
            # 1B declines and falls THROUGH to the 1A speed test — "PA=1 case
            # only re-entry to 1a" (60 hardcoded, not imported — see K-note).
            want = "1A" if (speed is not None and speed >= 60) else None
        else:
            want = expected
        if got != want:
            failures.append(f"  PA1: resolve({badge!r}, speed={speed}, dist={dist}, next_pa=1) = {got!r}, expected {want!r} — pa=1 has no 1B target")
    # Fall-through: pa=1, inside the lead, speed already stale-high → 1A (not None) —
    # "PA=1 case only re-entry to 1a".
    if resolve("MOVING", 80, 300, next_pa=1) != "1A":
        failures.append("  PA1: resolve(MOVING, speed=80, dist=300, next_pa=1) must fall through to '1A'")

    # Regression anchor — the 2026-07-23 Nambu incident: normal departure from 武蔵溝ノ口,
    # segment 703m < 900m lead, first moving frames at speed 1-3. The witnessed edge
    # must disarm re-entry entirely (the departure PA plays via the audible primary).
    if resolve("MOVING", 1, 703, origin_known=True) is not None:
        failures.append(
            "  REGRESSION: resolve(MOVING, speed=1, dist=703, origin_known=True) must be None (2026-07-23: ate the departure PA on a short segment)"
        )
    # Discrimination check for the anchor above: the SAME reads with UNKNOWN origin
    # (mid-transit join inside the lead) still resolve 1B — proves the provenance
    # gate, not some other condition, is what suppresses the incident.
    if resolve("MOVING", 1, 703, origin_known=False) != "1B":
        failures.append(
            "  DISCRIMINATION: resolve(MOVING, speed=1, dist=703, origin_known=False) must be '1B' (unknown-origin join inside the lead is re-entry's legitimate case)"
        )

    if failures:
        print("FAIL: re-entry resolver")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: re-entry resolver ({len(GRID)} grid cells + PASSING==MOVING facet + provenance facet + regressions + guards)")


if __name__ == "__main__":
    main()

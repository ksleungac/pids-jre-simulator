# TIER: T1 — inferred_state() truth table
"""Locks the canonical Layer-3 inference (`_Detector.inferred_state`) against drift.

Every cell of the (prev_badge x arrival_observed x departure_observed) grid is
asserted against the truth table in auto_input/README.md § "Layer 3 — AutoDriver's
inferred game state". The expected values are hand-derived FROM THE README table
(the spec), not read back from the code — so a future edit to inferred_state() that
disagrees with the documented table fails here.

The MOVING and PASSING rows are IDENTICAL by design: PASSING is a transient
sub-state of MOVING and never changes the inferred game state (the canonical
`PASSING ≡ MOVING` invariant). That equality is asserted separately at the end —
re-introducing a PASSING special-case (the class of the 2026-07-16 re-entry PA-drop
incident) flips a MOVING/PASSING cell and trips it.

Pure: constructs a bare `_Detector` dataclass, sets three fields, reads
inferred_state(). No pygame init, no camera, no I/O. (Importing driver.py loads
dxcam/pygame/numpy as modules but does not initialize them.)
"""

import sys
from pathlib import Path

# _tests/ is dev harness (never shipped, exempt from the production path-resolver
# ban) — Path(__file__) here is fine. Put the repo root on sys.path for the import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import Layer3State, _Detector  # noqa: E402

L = Layer3State

# Spec table — hand-derived from README § "Layer 3" truth table (NOT from the code).
#   (prev_badge, arrival_observed, departure_observed) -> expected Layer 3 state
# fmt: off
CASES = [
    (None,      False, False, L.UNKNOWN),
    (None,      False, True,  L.UNKNOWN),
    (None,      True,  False, L.UNKNOWN),
    (None,      True,  True,  L.UNKNOWN),
    ("STOPPED", False, False, L.IDLE),
    ("STOPPED", False, True,  L.IDLE),      # departure flag irrelevant while STOPPED
    ("STOPPED", True,  False, L.STOPPED),
    ("STOPPED", True,  True,  L.STOPPED),
    ("MOVING",  False, False, L.DEPARTING),
    ("MOVING",  False, True,  L.CRUISING),
    ("MOVING",  True,  False, L.ARRIVING),  # arrival wins over departure flag
    ("MOVING",  True,  True,  L.ARRIVING),
    ("PASSING", False, False, L.DEPARTING),
    ("PASSING", False, True,  L.CRUISING),
    ("PASSING", True,  False, L.ARRIVING),
    ("PASSING", True,  True,  L.ARRIVING),
]
# fmt: on


def _infer(badge, arr, dep):
    d = _Detector()
    d.prev_badge = badge
    d.arrival_observed = arr
    d.departure_observed = dep
    return d.inferred_state()


def main():
    failures = []
    for badge, arr, dep, expected in CASES:
        got = _infer(badge, arr, dep)
        if got != expected:
            failures.append(f"  inferred_state(badge={badge!r}, arr={arr}, dep={dep}) = {got!r}, expected {expected!r}")

    # Invariant: PASSING is identical to MOVING on the inferred state for every
    # (arr, dep). Its violation is the 2026-07-16 re-entry PA-drop bug class.
    for arr in (False, True):
        for dep in (False, True):
            mv = _infer("MOVING", arr, dep)
            pv = _infer("PASSING", arr, dep)
            if mv != pv:
                failures.append(f"  PASSING != MOVING at arr={arr}, dep={dep}: MOVING={mv!r} PASSING={pv!r}")

    if failures:
        print("FAIL: inferred_state truth table")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: inferred_state truth table ({len(CASES)} cells + MOVING==PASSING invariant)")


if __name__ == "__main__":
    main()

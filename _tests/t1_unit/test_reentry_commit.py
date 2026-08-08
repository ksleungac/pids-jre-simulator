# SPDX-License-Identifier: MIT
# TIER: T1 — re-entry commit shape (AutoDriver._maybe_reentry)
"""Locks the COMMIT side of re-entry — what a consensus-confirmed target actually
does to the sim. The resolver's spec grid lives in test_reentry_target.py; this
covers the 1A commit's pa-dependent split (2026-07-24 rule):

  - landing stop pa>=2 → SILENT advance (announcement stale mid-segment)
  - landing stop pa=1  → AUDIBLE catch-up ("pa=1 always play it" — the single
    announcement is never stale), via the same press as a departure fire.

Real AutoDriver via object.__new__ (skips camera __init__) + stubbed sim —
same technique as _dev_scripts/verify_reentry_consensus.py.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import AutoDriver, _Detector  # noqa: E402


def make_driver(next_pa):
    ad = object.__new__(AutoDriver)
    ad._detector = _Detector(prev_badge="MOVING")
    ad.sim = SimpleNamespace(
        pending_next_pa=False,
        pending_silent_advance=None,
        state=SimpleNamespace(at_station=True, curr_stop=0, cnt_pa_at_station=-1),
        stops=[{"pa": ["p"], "pa_at_station": []}, {"pa": ["p"] * next_pa}],
    )
    return ad


def commit_1a(next_pa):
    """Two consecutive CRUISING probes (speed 80, dist beyond lead) → commit 1A."""
    ad = make_driver(next_pa)
    first = ad._maybe_reentry(80, 2000)
    second = ad._maybe_reentry(80, 2000)
    return ad, first, second


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # pa>=2 → silent advance signal, no audible press.
    ad, first, second = commit_1a(next_pa=2)
    check(first is None and second == "1A", f"pa=2: expected commit on 2nd probe, got ({first}, {second})")
    check(ad.sim.pending_silent_advance == "1A", f"pa=2: expected silent advance '1A', got {ad.sim.pending_silent_advance!r}")
    check(ad.sim.pending_next_pa is False, "pa=2: silent commit must NOT press (no audio)")

    # pa=1 → AUDIBLE press (pending_next_pa, the departure-fire path), no silent signal.
    # Discriminates: reverting to the silent advance fails both checks below.
    ad, first, second = commit_1a(next_pa=1)
    check(first is None and second == "1A", f"pa=1: expected commit on 2nd probe, got ({first}, {second})")
    check(ad.sim.pending_next_pa is True, "pa=1: commit must press AUDIBLY (pa=1 announcement never stale)")
    check(ad.sim.pending_silent_advance is None, "pa=1: no silent-advance signal on the audible path")

    if failures:
        print("FAIL: re-entry commit shape")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: re-entry commit shape (pa>=2 silent 1A + pa=1 audible catch-up)")


if __name__ == "__main__":
    main()

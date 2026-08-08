# SPDX-License-Identifier: MIT
# TIER: T1 — e235_0 5-station view: passing-station handling (out-of-spec skip route)
"""Locks e235_0's `JapaneseFiveStationDisplay` best-effort treatment of a
PASSING station (empty ``pa``) when an out-of-spec skip route is fed into the
Yamanote model (#66).

Decision (user, 2026-07-23): passing stations STAY in their fixed slot and render
as an EMPTY ring (a countdown circle with no digit) — the 5-station view is a
"next-stops" list with no calibrated passing-marker slot, so a proper passing
chevron (as the full-route open view draws) is a deferred ultra-low-priority
item. The empty ring is the minimal best-effort.

Two invariants under test, both on pure logic callable unbound against a
SimpleNamespace stub (no pygame / fonts / display), mirroring test_eight_window:

1. `_visible_stop_indices` still INCLUDES passing stations — they appear in the
   slot, they are not skipped. (Locks the "they appear" decision.)
2. `_ahead_minutes` returns None for a passing station (→ empty ring) and adds
   NOTHING to the cumulative chain — crucially it must NOT crash when a passing
   station carries ``time: null``. Reverting the fix makes ``cumulative += None``
   raise TypeError, so this fixture discriminates.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from displays.train_models.e235_0.lower_lcd import JapaneseFiveStationDisplay  # noqa: E402


def vis_of(stops, curr, circular=False):
    fake = SimpleNamespace(stops=stops, _circular=circular)
    return JapaneseFiveStationDisplay._visible_stop_indices(fake, curr)


def ahead_of(stops, vis):
    # at_station=True → cumulative seeds at 0 and _first_stop_minutes is never
    # called, so the stub needs no bound helper.
    fake = SimpleNamespace(stops=stops)
    state = SimpleNamespace(at_station=True, is_last_pa=False, curr_stop=vis[0], departure_time=0)
    return JapaneseFiveStationDisplay._ahead_minutes(fake, state, 0.0, vis)


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # Linear out-of-spec skip route: curr(0) stop, then PASS/stop alternating,
    # with the passing stations carrying `time: null` (the latent-crash shape).
    stops = [
        {"name": "A", "pa": ["a"], "time": 0},  # 0 curr (stopping — always has pa)
        {"name": "B", "pa": [], "time": None},  # 1 PASS, time:null
        {"name": "C", "pa": ["c"], "time": 3},  # 2 stop
        {"name": "D", "pa": [], "time": None},  # 3 PASS, time:null
        {"name": "E", "pa": ["e"], "time": 2},  # 4 stop
    ]

    # (1) passing stations APPEAR — vis is curr + next 4 by index, passing incl.
    vis = vis_of(stops, 0)
    check(vis == [0, 1, 2, 3, 4], f"vis should keep passing stations: got {vis}")
    check(1 in vis and 3 in vis, f"passing stations 1,3 must appear in the slot window: {vis}")

    # (2) _ahead_minutes: passing → None (empty ring), no chain contribution, and
    #     NO CRASH on time:null. Revert the fix → `cumulative += None` → TypeError.
    mins = ahead_of(stops, vis)
    check(mins == [None, 3, None, 5], f"ahead minutes: passing→None, chain skips them; got {mins}")

    # All-stopping route (in-spec Yamanote shape): behaviour unchanged, no None.
    stops_all = [{"name": n, "pa": [n], "time": t} for n, t in zip("ABCDE", (0, 2, 3, 2, 4))]
    vis2 = vis_of(stops_all, 0)
    mins2 = ahead_of(stops_all, vis2)
    check(mins2 == [2, 5, 7, 11], f"all-stopping chain must be pure cumulative, no None; got {mins2}")

    if failures:
        print("FAIL: e235_0 5-station passing-station handling (#66)")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: e235_0 5-station passing stations render empty ring, no time-chain contribution, no time:null crash (#66)")


if __name__ == "__main__":
    main()

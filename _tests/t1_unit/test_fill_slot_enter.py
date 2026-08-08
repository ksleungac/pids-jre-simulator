# SPDX-License-Identifier: MIT
# TIER: T1 — e235_0 5-station band fill fires only on a genuine slot-enter
"""Locks the fix for the 5-station green-band false-refill (the `_INACTIVE_GAP`
second-clock bug).

Before: `JapaneseFiveStationDisplay.show_stops` self-detected "the slot became
active" from a wall-clock draw-gap (`current_time - _fill_last_seen > 0.5`). A
renderer cannot tell a draw stall (window move / alt-tab freezes the main thread
> 0.5 s) or a stopped→moving marker flip from a real re-enter, so both
false-restarted the sweep.

After: the fill restarts ONLY when the scheduler commits a genuine slot change
into the EIGHT slot. The trigger chain, all pure logic callable unbound against a
SimpleNamespace stub (no pygame / fonts / display), mirroring test_eight_window:

    ChangeScheduler.tick → LowerDisplayBase.apply_slot(slot, now)
        └ entered = slot != _current_slot          (a same-slot reveal-restart is NOT an enter)
          └ LowerDisplay._on_slot_entered(slot)    (e235_0: routes EIGHT → the fill renderer)
            └ JapaneseFiveStationDisplay.on_slot_enter(now) → _fill_start = now

The composed sequence is the discriminator: revert any link (drop the `entered`
guard, drop the EIGHT routing guard, or re-add the draw-gap self-detect) and one
of the assertions below fails.
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

from displays.lower_lcd import LowerDisplayBase  # noqa: E402
from displays.train_models.e235_0.lower_lcd import (  # noqa: E402
    JapaneseFiveStationDisplay,
    LowerDisplay as E0LowerDisplay,
)

FULL = LowerDisplayBase._SLOT_FULL
EIGHT = LowerDisplayBase._SLOT_EIGHT
TRANSFER = LowerDisplayBase._SLOT_TRANSFER


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # --- (1) apply_slot fires _on_slot_entered ONLY on a genuine slot change ---
    def apply(cur, new):
        calls = []
        fake = SimpleNamespace(_current_slot=cur, _slot_start=0.0)
        fake._on_slot_entered = lambda slot, now: calls.append((slot, now))
        LowerDisplayBase.apply_slot(fake, new, 5.0)
        return calls, fake

    calls, fake = apply(FULL, EIGHT)
    check(calls == [(EIGHT, 5.0)], f"apply FULL→EIGHT must fire _on_slot_entered once; got {calls}")
    check(fake._current_slot == EIGHT and fake._slot_start == 5.0, "apply_slot must still commit slot + restart dwell")

    calls, fake = apply(EIGHT, EIGHT)
    check(calls == [], f"apply EIGHT→EIGHT (same-slot re-anchor) must NOT fire _on_slot_entered; got {calls}")
    check(fake._slot_start == 5.0, "same-slot apply still restarts the dwell timer (reveal_slot semantics)")

    # --- (2) e235_0 _on_slot_entered routes EIGHT (and only EIGHT) to the fill ---
    def route(slot):
        got = []
        eight = SimpleNamespace(on_slot_enter=lambda now: got.append(now))
        fake = SimpleNamespace(_SLOT_EIGHT=EIGHT, japanese_eight_display=eight)
        E0LowerDisplay._on_slot_entered(fake, slot, 9.0)
        return got

    check(route(EIGHT) == [9.0], f"_on_slot_entered(EIGHT) must call the 5-station on_slot_enter; got {route(EIGHT)}")
    check(route(FULL) == [], "_on_slot_entered(FULL) must NOT touch the 5-station fill")
    check(route(TRANSFER) == [], "_on_slot_entered(TRANSFER) must NOT touch the 5-station fill")

    # --- (3) on_slot_enter sets the reveal start ---
    r = SimpleNamespace(_fill_start=None)
    JapaneseFiveStationDisplay.on_slot_enter(r, 7.5)
    check(r._fill_start == 7.5, f"on_slot_enter must stamp _fill_start; got {r._fill_start}")

    # --- (4) Composed chain: only a REAL re-enter refills (draw stall / motion
    #         flip / mode flip never reach apply_slot with an EIGHT change). ---
    eight = SimpleNamespace(_fill_start=None)
    eight.on_slot_enter = lambda now: setattr(eight, "_fill_start", now)
    mgr = SimpleNamespace(_current_slot=FULL, _slot_start=0.0, _SLOT_EIGHT=EIGHT, japanese_eight_display=eight)
    mgr._on_slot_entered = lambda slot, now: E0LowerDisplay._on_slot_entered(mgr, slot, now)

    LowerDisplayBase.apply_slot(mgr, EIGHT, 1.0)  # FULL→EIGHT: sweep starts
    check(eight._fill_start == 1.0, f"FULL→EIGHT must start the fill at 1.0; got {eight._fill_start}")

    LowerDisplayBase.apply_slot(mgr, EIGHT, 2.0)  # same-slot re-anchor: NO refill
    check(eight._fill_start == 1.0, f"a same-slot re-anchor must NOT refill (draw stall / motion flip class); got {eight._fill_start}")

    LowerDisplayBase.apply_slot(mgr, FULL, 3.0)  # leave EIGHT
    LowerDisplayBase.apply_slot(mgr, EIGHT, 4.0)  # genuine re-enter: refills
    check(eight._fill_start == 4.0, f"a genuine FULL→EIGHT re-enter must refill at 4.0; got {eight._fill_start}")

    if failures:
        print("FAIL: e235_0 5-station band fill slot-enter trigger")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: 5-station band fill fires only on a genuine slot-enter (no draw-stall / stopped→moving false-refill)")


if __name__ == "__main__":
    main()

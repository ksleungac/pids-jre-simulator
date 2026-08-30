# SPDX-License-Identifier: MIT
# TIER: T1 — lower LCD: which stations are shown, and when the view changes
"""What the lower LCD guarantees about the stations it is showing you.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). Four
decisions across three train models, all pure logic, all about the same question —
what is on screen and when does it change:

  1. e235_1000 8-STATION WINDOW + FULL-SLOT LOCK — which 8 cells, and when the
     full-route view drops out
  2. e235_0 5-STATION CONTENT — which stations appear and what each ring shows,
     including a passing station on an out-of-spec route
  3. e235_0 5-STATION BAND FILL — when the sweep restarts
  4. e233_0 FULL-ROUTE MARKER COLUMN — where the position marker sits along the
     leg it is crossing, on a route long enough to window

Every method here reads only `self.*` fields plus class constants, so they are
called UNBOUND against a `SimpleNamespace` stub — no pygame, no fonts, no display,
no route. Rendering itself stays by-eye (`_tests/README.md`); what is tested is
the logic that decides what gets rendered.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
# run_all.py runs each test via a subprocess pipe (cp1252 on Windows); the
# PASS line + failure messages carry Japanese station names. Match run_all.py's
# own guard so the non-ASCII output doesn't crash the run. See conventions.md
# § Tooling "Hook scripts that output non-ASCII must reconfigure stdout".
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
from displays.train_models.e233_0.lower_lcd import (  # noqa: E402
    JapaneseFullRouteDisplay as E233FullRoute,
)
from displays.train_models.e235_1000.lower_lcd import (  # noqa: E402
    JapaneseEightStationDisplay,
    LowerDisplay,
)

FAILURES: list[str] = []


def check(cond, msg) -> None:
    if not cond:
        FAILURES.append("  " + msg)


# ── 1. the 8-station window and the FULL-slot lock ────────────────────────────
# THE 2026-07-17 bug site.
#
# `JapaneseEightStationDisplay._get_window(cursor_pos)` and
# `LowerDisplay._should_lock_to_eight(cursor_pos)` are pure logic: given the VISUAL train
# position they return the visible 8-cell window / whether to drop the FULL slot. The bug
# keyed both on `curr_stop` (the skipped-ahead PA target) instead of `cursor_pos`. A
# departure that skips passing stations jumps curr_stop several cells ahead while cursor_pos
# lags — so the window snapped to the tail before the visible cursor arrived (pointer fell
# off the left edge → suppressed) AND the FULL slot dropped early (view locked to 8-station
# prematurely). The incident: Chūō departing 新宿 (idx 21, skip to 四ツ谷 idx 25) with 32
# stops — visually 10 stations from the end, yet locked with no arrow.
#
# THE INVARIANT (docs/DISPLAY.md § "Position-locked views always show the pointer"):
# for every valid cursor position, the returned window MUST contain cursor_pos — the
# pointer is always visible.

VC = JapaneseEightStationDisplay.VISIBLE_COUNT  # 8
LOCK = JapaneseEightStationDisplay.LOCK_THRESHOLD  # 7


def window(n, cursor):
    """Global indices of _get_window(cursor) for a route of n display-stops."""
    fake = SimpleNamespace(display_stops=[{"_i": k} for k in range(n)], VISIBLE_COUNT=VC)
    return [gi for gi, _ in JapaneseEightStationDisplay._get_window(fake, cursor)]


def locked(nstops, cursor):
    """_should_lock_to_eight for a route of nstops sim-stops at visual position cursor."""
    # LOCK_THRESHOLD is a class attr on the concrete (derived from the renderer's
    # canonical constant) since the cycler moved up to LowerDisplayBase.
    fake = SimpleNamespace(stops=[{"_i": k} for k in range(nstops)], LOCK_THRESHOLD=LowerDisplay.LOCK_THRESHOLD)
    return LowerDisplay._should_lock_to_eight(fake, cursor)


def locked_e0(nstops, cursor):
    fake = SimpleNamespace(stops=[{"_i": k} for k in range(nstops)], LOCK_THRESHOLD=E0LowerDisplay.LOCK_THRESHOLD)
    return E0LowerDisplay._should_lock_to_eight(fake, cursor)


def check_eight_window() -> None:
    # --- Short route (n <= VISIBLE_COUNT): whole list, any cursor ---
    for n in (1, 5, VC):
        for cur in range(n):
            w = window(n, cur)
            check(w == list(range(n)), f"short n={n} cur={cur}: window={w} expected 0..{n-1}")

    # --- Long route regimes (n > VISIBLE_COUNT) ---
    for n in (VC + 1, 17, 32, 46):
        last = n - 1
        # THE INVARIANT: every valid cursor position is inside the window (pointer visible).
        for cur in range(n):
            w = window(n, cur)
            check(len(w) == VC, f"n={n} cur={cur}: window has {len(w)} cells, expected {VC}")
            check(cur in w, f"POINTER LOST — n={n} cur={cur}: cursor not in window {w}")

        # cursor <= 0 -> start 0 (no negative slice); also covers leading-frame negatives.
        for cur in (0, -1, -5):
            check(window(n, cur)[0] == 0, f"n={n} cur={cur}: expected start 0, got window {window(n, cur)}")

        # sliding regime (0 < cursor <= n-VC): cursor sits at local index 1, one past cell left.
        for cur in range(1, n - VC + 1):
            w = window(n, cur)
            check(w[0] == cur - 1, f"n={n} cur={cur} sliding: window[0]={w[0]} expected {cur-1}")
            check(w[1] == cur, f"n={n} cur={cur} sliding: cursor not at local index 1 (window={w})")

        # locked regime (cursor > n-VC): window == [n-VC .. n-1], terminus always included.
        for cur in range(n - VC + 1, n):
            w = window(n, cur)
            check(w == list(range(n - VC, n)), f"n={n} cur={cur} locked: window={w} expected {list(range(n-VC, n))}")
            check(last in w, f"n={n} cur={cur} locked: terminus {last} not in window {w}")
            check(cur in w, f"n={n} cur={cur} locked: cursor not in window {w}")

    # --- _should_lock_to_eight keys on cursor_pos, monotone at the LOCK boundary ---
    for nstops in (17, 32, 46):
        for cur in range(nstops):
            expect = (nstops - cur) <= LOCK
            check(locked(nstops, cur) is expect, f"lock n={nstops} cur={cur}: got {locked(nstops, cur)} expected {expect}")

    # --- Regression anchors — the exact Chūō 新宿→四ツ谷 incident (32 stops) ---
    N = 32
    # Departing 新宿(21): curr_stop jumps to 四ツ谷(25) but cursor_pos lags at 22.
    # Was: keyed on curr_stop=25 -> locked + window [24..31] -> cursor 22 off the left edge.
    check(
        locked(N, 22) is False,
        "REGRESSION: lock(32, cursor=22) must be False — FULL stays while train is visually 10 from end (was True on curr_stop=25)",
    )
    w22 = window(N, 22)
    check(22 in w22, f"REGRESSION: window(32, cursor=22) must contain the cursor (pointer visible); got {w22}")
    check(w22[0] == 21, f"REGRESSION: window(32, cursor=22) sliding start should be 21; got {w22}")
    # Once the train is visually at 四ツ谷(25): 7 from the end -> genuinely locks, dest in view.
    check(locked(N, 25) is True, "lock(32, cursor=25) must be True — 四ツ谷 is 7 stations from 東京")
    w25 = window(N, 25)
    check(w25 == list(range(24, 32)), f"window(32, cursor=25) locked expected [24..31]; got {w25}")
    check(31 in w25 and 25 in w25, f"window(32, cursor=25) must contain terminus AND cursor; got {w25}")

    # --- E235-0 NEVER locks: no-lock is its native norm (#68/#81). Yamanote is a
    #     circular LOOP with no end for the inherited linear end-of-route heuristic
    #     to fire on, so the lock is off for EVERY route (in-spec AND out-of-spec
    #     best-effort). Discriminates: delete the _should_lock_to_eight override on
    #     e235_0's LowerDisplay and it falls back to the inherited
    #     (len(stops)-cursor) <= LOCK_THRESHOLD → True near the tail → this fails.
    for nstops in (17, 30, 46):
        for cur in range(nstops):
            check(
                locked_e0(nstops, cur) is False,
                f"E235-0 lock n={nstops} cur={cur}: got True — e235_0 must NEVER lock (native no-lock norm)",
            )
    # Tail anchor + discrimination proof: at the exact tail position where
    # e235_1000 DOES lock, e235_0 still returns False.
    check(locked_e0(32, 31) is False, "REGRESSION #68/#81: e235_0 lock(32, cursor=31) must be False — the FULL-slot lock is off on e235_0")
    check(locked(32, 31) is True, "sanity: e235_1000 DOES lock at the tail (32, cursor=31) — proves the e235_0 assertion discriminates")


# ── 2. what the 5-station view shows, passing stations included ───────────────
# e235_0's best-effort treatment of a PASSING station (empty ``pa``) when an
# out-of-spec skip route is fed into the Yamanote model (#66).
#
# Decision (user, 2026-07-23): passing stations STAY in their fixed slot and render
# as an EMPTY ring (a countdown circle with no digit) — the 5-station view is a
# "next-stops" list with no calibrated passing-marker slot, so a proper passing
# chevron (as the full-route open view draws) is a deferred ultra-low-priority
# item. The empty ring is the minimal best-effort.
#
# 1. `_visible_stop_indices` still INCLUDES passing stations — they appear in the
#    slot, they are not skipped. (Locks the "they appear" decision.)
# 2. `_ahead_minutes` returns None for a passing station (→ empty ring) and adds
#    NOTHING to the cumulative chain — crucially it must NOT crash when a passing
#    station carries ``time: null``. Reverting the fix makes ``cumulative += None``
#    raise TypeError, so this fixture discriminates.


def vis_of(stops, curr, circular=False):
    fake = SimpleNamespace(stops=stops, _circular=circular)
    return JapaneseFiveStationDisplay._visible_stop_indices(fake, curr)


def ahead_of(stops, vis):
    # at_station=True → cumulative seeds at 0 and _first_stop_minutes is never
    # called, so the stub needs no bound helper.
    fake = SimpleNamespace(stops=stops)
    state = SimpleNamespace(at_station=True, is_last_pa=False, curr_stop=vis[0], departure_time=0)
    return JapaneseFiveStationDisplay._ahead_minutes(fake, state, 0.0, vis)


def check_five_station_content() -> None:
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


# ── 3. when the 5-station band fill restarts ──────────────────────────────────
# The fix for the 5-station green-band false-refill (the `_INACTIVE_GAP`
# second-clock bug).
#
# Before: `JapaneseFiveStationDisplay.show_stops` self-detected "the slot became
# active" from a wall-clock draw-gap (`current_time - _fill_last_seen > 0.5`). A
# renderer cannot tell a draw stall (window move / alt-tab freezes the main thread
# > 0.5 s) or a stopped→moving marker flip from a real re-enter, so both
# false-restarted the sweep.
#
# After: the fill restarts ONLY when the scheduler commits a genuine slot change
# into the EIGHT slot. The trigger chain, all pure logic callable unbound:
#
#     ChangeScheduler.tick → LowerDisplayBase.apply_slot(slot, now)
#         └ entered = slot != _current_slot          (a same-slot reveal-restart is NOT an enter)
#           └ LowerDisplay._on_slot_entered(slot)    (e235_0: routes EIGHT → the fill renderer)
#             └ JapaneseFiveStationDisplay.on_slot_enter(now) → _fill_start = now
#
# The composed sequence is the discriminator: revert any link (drop the `entered`
# guard, drop the EIGHT routing guard, or re-add the draw-gap self-detect) and one
# of the assertions below fails.

FULL = LowerDisplayBase._SLOT_FULL
EIGHT = LowerDisplayBase._SLOT_EIGHT
TRANSFER = LowerDisplayBase._SLOT_TRANSFER


def check_fill_slot_enter() -> None:
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


# ── 4. e233_0 full-route: the marker's row-first test ─────────────────────────
# Every consumer of the full-route window derives its column the SAME way —
# `local = di - window_start`, then `local % per_row`. `_slot`, `_draw_bars` and
# `_row_edges` all do. `_marker_slot` decides whether to push the marker into the
# middle of the leg it is crossing, and it asked `di % per_row` instead: correct
# only while the window starts at 0, which is every Chūō frame, so it read as
# right. On a route long enough to window (Keihin's 46 cells, start 6) it
# disagreed at 4 of the 40 visible cells — suppressing the offset at two mid-row
# cells and applying it at both row-first ones, which puts the marker past that
# row's own wall.
#
# The invariant, not the arithmetic: the marker's row-first test must agree with
# `_slot`'s column for EVERY cell in the window. Restoring `di % per` fails this.


def _e233_full_route_stub(n_cells: int, cursor: int):
    """A `JapaneseFullRouteDisplay` with the REAL window/slot/pitch logic bound.

    Everything `_marker_slot` reaches reads only `self.*` and the module
    tuneables, so every production method it needs binds straight onto a
    namespace — `_box_width` included, which is a single dict read and touches no
    font. Nothing here is substituted, so what is exercised is the real decision.

    `curr` and `cursor` are separate arguments on purpose: `_window()` keys on
    `_curr()` (the PA target) while `_marker_slot` keys on `_cursor()` (the
    visual position), and a skip animation is exactly when they disagree.
    """
    stub = SimpleNamespace(
        display_stops=[{"name": f"s{i}", "pa": ["x"]} for i in range(n_cells)],
        display_offset=0,
        state=SimpleNamespace(curr_stop=cursor, cursor_pos=cursor, at_station=False),
    )
    for name in (
        "_window",
        "_per_row",
        "_rows",
        "_slot",
        "_slot0_cx",
        "_pitch",
        "_avail",
        "_row_cy",
        "_curr",
        "_cursor",
        "_box_width",
    ):
        setattr(stub, name, getattr(E233FullRoute, name).__get__(stub))
    return stub


def _marker_offset(stub, di: int) -> float:
    """How far `_marker_slot` pushes the marker off cell `di`'s plain slot centre."""
    _, marker_cx, _ = E233FullRoute._marker_slot(stub, {})
    _, slot_cx, _ = stub._slot(di)
    return abs(marker_cx - slot_cx)


def check_e233_marker_column() -> None:
    # The oracle is WIP § 9.3.6, not the arithmetic: the marker sits in the
    # middle of the leg it is crossing, EXCEPT at a row's first cell, where the
    # station behind it is on the other row and there is no leg on this row to
    # sit in. So `_marker_slot`'s x must equal the plain slot centre at a
    # row-first cell and be pushed off it everywhere else.
    #
    # 46 cells window to (6, 40) — the case that separates the two expressions.
    # 40 cells window to (0, 40), where `di` and the local column coincide and
    # the bug is invisible; it is here so a "fix" that breaks Chūō is caught.
    for n_cells in (46, 40):
        stub = _e233_full_route_stub(n_cells, cursor=0)
        for di in range(n_cells):
            stub.state.curr_stop = stub.state.cursor_pos = di
            # The window is a function of the cursor, so it must be re-read for
            # every position rather than sampled once — reading it once is how
            # this test first reported a failure that was its own bookkeeping.
            start, count = stub._window()
            per = stub._per_row()
            if not (start <= di < start + count):
                continue
            # Row-first is read OUT of `_slot`, not restated: column 0 is the
            # rightmost slot by construction, so a cell whose slot centre IS
            # `_slot0_cx()` is the one starting its row. Restating the arithmetic
            # would compare the fix against a copy of itself.
            _, slot_cx, _ = stub._slot(di)
            row_first = abs(slot_cx - stub._slot0_cx()) < 1e-9
            offset = _marker_offset(stub, di)
            if row_first:
                check(
                    offset < 1e-9,
                    f"e233_0 marker must sit ON the slot at a row-FIRST cell " f"(n={n_cells}, window start={start}, di={di}); offset {offset:.2f}px",
                )
            else:
                check(
                    offset > 0.0,
                    f"e233_0 marker must be pushed into the leg at a MID-ROW cell "
                    f"(n={n_cells}, window start={start}, di={di}, local col "
                    f"{(di - start) % per}); it sat on the slot centre",
                )

    # THE SKIP-ANIMATION CELL, which the loop above cannot construct: it pins
    # curr == cursor, so a 46-cell route never presents window (6,40) with the
    # cursor ON di 6. In production those two indices come apart — `_window()`
    # keys on `_curr()` and `_marker_slot` on `_cursor()` — so departing di 6 and
    # skipping to 7 gives start 6 with the marker still drawn at 6, which is the
    # row's FIRST cell and must take no offset. Under the old `di % per` it read
    # `6 % 20 = 6`, mid-row, and the marker went past the row's right wall.
    skip = _e233_full_route_stub(46, cursor=0)
    skip.state.curr_stop, skip.state.cursor_pos = 7, 6
    start, _ = skip._window()
    check(start == 6, f"precondition: curr_stop 7 on a 46-cell route should window at 6; got {start}")
    check(
        _marker_offset(skip, 6) < 1e-9,
        f"e233_0 marker must sit ON the slot at di=6, the row-first cell of window "
        f"(6,40), while a skip holds cursor_pos behind curr_stop; offset {_marker_offset(skip, 6):.2f}px",
    )


def main():
    check_eight_window()
    check_five_station_content()
    check_fill_slot_enter()
    check_e233_marker_column()

    if FAILURES:
        print("FAIL: lower LCD")
        print("\n".join(FAILURES))
        sys.exit(1)
    print(
        "PASS: lower LCD (8-station window short/sliding/locked + pointer-always-visible + Chūō 新宿 regression + "
        "e235_0 never-locks #68/#81; 5-station passing empty ring, no time:null crash #66; band fill only on a genuine slot-enter; "
        "e233_0 marker row-first column agrees with _slot on a windowed 46-cell route)"
    )


if __name__ == "__main__":
    main()

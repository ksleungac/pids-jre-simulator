# SPDX-License-Identifier: MIT
# TIER: T1 — 8-station window + FULL-slot lock (cursor_pos keying)
"""Locks the pointer-visibility invariant for the E235-1000 lower LCD — THE 2026-07-17
bug site.

`JapaneseEightStationDisplay._get_window(cursor_pos)` and
`LowerDisplay._should_lock_to_eight(cursor_pos)` are pure logic: given the VISUAL train
position they return the visible 8-cell window / whether to drop the FULL slot. The bug
keyed both on `curr_stop` (the skipped-ahead PA target) instead of `cursor_pos`. A
departure that skips passing stations jumps curr_stop several cells ahead while cursor_pos
lags — so the window snapped to the tail before the visible cursor arrived (pointer fell
off the left edge → suppressed) AND the FULL slot dropped early (view locked to 8-station
prematurely). The incident: Chūō departing 新宿 (idx 21, skip to 四ツ谷 idx 25) with 32
stops — visually 10 stations from the end, yet locked with no arrow.

Both methods read only `self.*` fields + class consts, so we call them unbound against a
`SimpleNamespace` stub (no pygame, no fonts, no display). See test_reentry_target.py for
the same stub-the-collaborators pattern.

THE INVARIANT under test (DISPLAY.md § "Position-locked views always show the pointer"):
for every valid cursor position, the returned window MUST contain cursor_pos — the pointer
is always visible.
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

from displays.train_models.e235_1000.lower_lcd import (  # noqa: E402
    JapaneseEightStationDisplay,
    LowerDisplay,
)
from displays.train_models.e235_0.lower_lcd import LowerDisplay as E0LowerDisplay  # noqa: E402

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


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

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
    def locked_e0(nstops, cursor):
        fake = SimpleNamespace(stops=[{"_i": k} for k in range(nstops)], LOCK_THRESHOLD=E0LowerDisplay.LOCK_THRESHOLD)
        return E0LowerDisplay._should_lock_to_eight(fake, cursor)

    for nstops in (17, 30, 46):
        for cur in range(nstops):
            check(locked_e0(nstops, cur) is False, f"E235-0 lock n={nstops} cur={cur}: got True — e235_0 must NEVER lock (native no-lock norm)")
    # Tail anchor + discrimination proof: at the exact tail position where
    # e235_1000 DOES lock, e235_0 still returns False.
    check(locked_e0(32, 31) is False, "REGRESSION #68/#81: e235_0 lock(32, cursor=31) must be False — the FULL-slot lock is off on e235_0")
    check(locked(32, 31) is True, "sanity: e235_1000 DOES lock at the tail (32, cursor=31) — proves the e235_0 assertion discriminates")

    if failures:
        print("FAIL: 8-station window / FULL-slot lock")
        print("\n".join(failures))
        sys.exit(1)
    print(
        "PASS: 8-station window + lock (short/sliding/locked regimes, pointer-always-visible invariant, Chūō 新宿 regression, e235_0 never-locks #68/#81)"
    )


if __name__ == "__main__":
    main()

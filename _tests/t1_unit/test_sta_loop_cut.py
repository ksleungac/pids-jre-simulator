# SPDX-License-Identifier: MIT
# TIER: T1 — STA loop/cut dispatch (PASimulator._next_sta)
"""The last sta track loops `[0, sta_cut)`; a press while it loops is the cut.

Models the real platform: the departure melody runs until the conductor cuts it.
Every OTHER track plays straight through once and `sta_cut` does not apply to it at
all — it is a property of the last track, not of the stop. The whole model rides on
one discriminator, `cnt_sta == len(sta) - 1`, because `cnt_sta` saturates at the last
index; on a single-track stop it never leaves 0, so every press is "the last track".

Stubs the audio layer and records the CALL, not just that `_next_sta` ran — the old
bug in this area was two calls with different effects, so a test that only counts
entries proves nothing. Calls the method unbound, same technique as
test_fire_at_station.py.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import PASimulator  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append("  " + msg)


def drive(stop: dict, presses: int, *, tail_armed=True):
    """Press Page Up `presses` times against one stop; return the call log."""
    calls: list[str] = []
    # Mirrors the audio layer: `looping` is armed only by a loop=True play and is
    # disarmed by the cut. Modelling it as "something is playing" is exactly the
    # conflation this dispatch must not make.
    live = {"sta": False, "looping": False}

    def play_sta(stop_idx, sta_idx, cut, loop=False):
        calls.append(f"play(idx={sta_idx}, cut={cut}, loop={loop})")
        live["sta"] = True
        live["looping"] = bool(loop) and tail_armed

    def cut_to_tail():
        if not tail_armed:
            calls.append("cut->unarmed")
            return False
        calls.append("cut")
        live["sta"], live["looping"] = True, False
        return True

    sim = SimpleNamespace(
        stops=[stop],
        state=SimpleNamespace(curr_stop=0, cnt_sta=0),
        audio=SimpleNamespace(
            is_sta_playing=lambda: live["sta"],
            is_sta_looping=lambda: live["looping"],
            play_sta=play_sta,
            cut_to_tail=cut_to_tail,
        ),
    )
    for _ in range(presses):
        PASimulator._next_sta(sim)
    return calls, sim.state.cnt_sta


def main() -> int:
    # 1. SINGLE TRACK — 324 of the corpus's 325 stops. Press 1 loops the melody,
    #    press 2 is the cut. cnt_sta never moves off 0.
    calls, cnt = drive({"sta": ["m"], "sta_cut": 7.7}, 2)
    check(calls == ["play(idx=0, cut=7.7, loop=True)", "cut"], f"single track: loop then cut, got {calls}")
    check(cnt == 0, f"single-track cnt_sta must stay 0, got {cnt}")

    # 2. A press AFTER the cut starts the melody looping again — not a second cut. This
    #    needs one continuous 3-press drive: `drive()` builds a fresh sim per call, so
    #    separate runs never reach the post-cut state (tail sounding, loop disarmed) and
    #    the branch would go uncovered. Discriminates a cut that forgets to clear
    #    `looping` — that would return "cut" here instead of replaying.
    calls, _ = drive({"sta": ["m"], "sta_cut": 7.7}, 3)
    check(
        calls == ["play(idx=0, cut=7.7, loop=True)", "cut", "play(idx=0, cut=7.7, loop=True)"],
        f"press after the cut must loop from the head again, got {calls}",
    )

    # 3. TWO TRACKS — saikyo 大宮, the only such stop. Its first entry is an arrival
    #    door-opening announcement: plays through once, no cut, no loop. Only the
    #    LAST entry loops, and only then does sta_cut apply.
    calls, cnt = drive({"sta": ["arrival", "melody"], "sta_cut": 7.7}, 3)
    check(
        calls == ["play(idx=0, cut=0, loop=False)", "play(idx=1, cut=7.7, loop=True)", "cut"],
        f"two tracks: announcement, then looping melody, then cut — got {calls}",
    )
    check(cnt == 1, f"cnt_sta must saturate at the last index, got {cnt}")

    # 4. A press during the NON-last track advances to the next track rather than
    #    cutting — there is no cut to take on a track that has no sta_cut.
    calls, _ = drive({"sta": ["arrival", "melody"], "sta_cut": 7.7}, 2)
    check("cut" not in calls, f"must not cut while a non-last track plays, got {calls}")

    # 5. A stop whose sta_cut is absent or out of range never arms a loop, so the cut
    #    path is unreachable there and every press simply replays. The press must not
    #    be swallowed — that is the property, not which branch delivers it.
    calls, _ = drive({"sta": ["m"], "sta_cut": 0}, 2, tail_armed=False)
    check(
        calls == ["play(idx=0, cut=0, loop=True)", "play(idx=0, cut=0, loop=True)"],
        f"unusable sta_cut must replay on every press, got {calls}",
    )
    check("cut" not in calls, f"unusable sta_cut must never reach the cut path, got {calls}")

    # 6. A stop with no melody is a no-op, both shapes the data uses.
    for empty in ({"sta": []}, {"sta": [""]}, {}):
        calls, _ = drive(empty, 2)
        check(calls == [], f"stop with no sta must be silent, got {calls} for {empty}")

    for f in FAILURES:
        print(f)
    print(f"{'FAIL' if FAILURES else 'PASS'}: sta-loop-cut ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: MIT
# TIER: T1 — STA playback: one press, one effect
"""What pressing Page Up guarantees.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). Two layers of
one behaviour, and they only make sense together — the press-edge bug was
invisible except through what the dispatch does with a second entry:

  1. HOW MANY TIMES A PRESS FIRES — PASimulator._handle_input_main
  2. WHAT EACH FIRE DOES          — PASimulator._next_sta

Both stub the audio layer and record the CALL, not merely that the method ran.
The bug in this area was two calls with different effects, so a test that only
counts entries proves nothing. Both call the method unbound against a
SimpleNamespace — no pygame display, no audio device, no route.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app as app_module  # noqa: E402
from app import PASimulator  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append("  " + msg)


# ── 1. how many times a press fires ───────────────────────────────────────────
# One physical Page Up press must fire `_next_sta` exactly ONCE, however long it
# is held.
#
# `_next_sta` picks its branch from current playback state — not playing plays from
# the head, already playing restarts at `sta_cut` (the closing-door announcement).
# The input loop polls `keyboard.is_pressed`, which is LEVEL-triggered, and Page Up
# was the one key with no repeat throttle. So a single press was polled ~every 33ms
# at 30fps and did both: poll 1 started the melody, poll 2 saw it playing and jumped
# to the cut. Loading a track measures ~155ms against keypresses of 80-200ms, which
# is why it fired on roughly half of presses rather than all of them — and why it was
# only visible after End, the one sequence where the head is what the user expects.
#
# `keyboard.is_pressed` and `pygame.time.wait` are patched at the module the handler
# resolves them through, so the frame sequence is fully scripted.


def drive_keys(frames, *, sta_playing_after_first=True):
    """Run `_handle_input_main` once per entry in `frames`.

    Each entry is the set of keys physically down that frame. Returns the list of
    calls made, in order. `sta_playing_after_first` models the real audio layer:
    once _next_sta has played something, the channel reports busy.
    """
    calls: list[str] = []
    state = {"sta_playing": False}

    fake = SimpleNamespace(
        _pageup_was_down=False,
        pending_next_pa=False,
        pending_silent_advance=None,
        audio=SimpleNamespace(
            is_pa_playing=lambda: False,
            is_playing=lambda: state["sta_playing"],
            is_sta_playing=lambda: state["sta_playing"],
            pause_sta=lambda: (calls.append("pause_sta"), state.__setitem__("sta_playing", False)),
            pause_pa=lambda: calls.append("pause_pa"),
        ),
    )

    def _next_sta():
        # Mirrors the real branch choice so the test observes WHICH play happened,
        # not merely that _next_sta was entered — the bug produced two entries with
        # different effects, and only the second one is wrong.
        calls.append("sta_from_cut" if state["sta_playing"] else "sta_from_head")
        if sta_playing_after_first:
            state["sta_playing"] = True

    fake._next_sta = _next_sta
    fake._next_pa = lambda: calls.append("pa")
    fake._silent_advance_to = lambda t: None

    orig_pressed, orig_wait = app_module.keyboard.is_pressed, app_module.pygame.time.wait
    try:
        for down in frames:
            app_module.keyboard.is_pressed = lambda k, _d=down: k in _d
            app_module.pygame.time.wait = lambda ms: None
            PASimulator._handle_input_main(fake)
    finally:
        app_module.keyboard.is_pressed, app_module.pygame.time.wait = orig_pressed, orig_wait
    return calls


def check_press_edge() -> None:
    # 1. THE BUG. One press held across four frames — a 130ms press at 30fps. Exactly
    #    one fire, and it must be from the head. Discriminates: reverting to the
    #    level-triggered `elif keyboard.is_pressed("page_up")` yields
    #    ["sta_from_head", "sta_from_cut", "sta_from_cut", "sta_from_cut"].
    calls = drive_keys([{"page_up"}] * 4)
    check(calls == ["sta_from_head"], f"held Page Up must fire once from the head, got {calls}")

    # 2. Release then press again IS a second press — the restart-at-cut semantic the
    #    feature exists for. Without the flag clearing on release this returns one call.
    calls = drive_keys([{"page_up"}, set(), {"page_up"}, {"page_up"}])
    check(calls == ["sta_from_head", "sta_from_cut"], f"re-press must restart at the cut, got {calls}")

    # 3. The reported sequence: play, End, restart. The restart must reach the head.
    #    This is the case the level-trigger broke — after End the first poll takes the
    #    from-head branch and the second immediately overrode it with the cut.
    calls = drive_keys([{"page_up"}, set(), {"end"}, set(), {"page_up"}, {"page_up"}])
    check(
        calls == ["sta_from_head", "pause_sta", "sta_from_head"],
        f"End then restart must replay from the head, got {calls}",
    )

    # 4. Page Down keeps its LEVEL trigger — held-key self-retry is what the
    #    auto-input `pending_next_pa` path relies on, so this must NOT become an edge.
    calls = drive_keys([{"page down"}] * 3)
    check(calls == ["pa", "pa", "pa"], f"Page Down must stay level-triggered, got {calls}")

    # 5. A held Page Up still blocks the End branch, exactly as the elif chain did
    #    before — the action moved to the edge, the chain did not change.
    calls = drive_keys([{"page_up"}, {"page_up", "end"}])
    check(calls == ["sta_from_head"], f"held Page Up must keep swallowing End, got {calls}")


# ── 2. what each fire does ────────────────────────────────────────────────────
# The last sta track loops `[0, sta_cut)`; a press while it loops is the cut.
#
# Models the real platform: the departure melody runs until the conductor cuts it.
# Every OTHER track plays straight through once and `sta_cut` does not apply to it at
# all — it is a property of the last track, not of the stop. The whole model rides on
# one discriminator, `cnt_sta == len(sta) - 1`, because `cnt_sta` saturates at the last
# index; on a single-track stop it never leaves 0, so every press is "the last track".


def drive_sta(stop: dict, presses: int, *, tail_armed=True):
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


def check_loop_cut() -> None:
    # 1. SINGLE TRACK — 324 of the corpus's 325 stops. Press 1 loops the melody,
    #    press 2 is the cut. cnt_sta never moves off 0.
    calls, cnt = drive_sta({"sta": ["m"], "sta_cut": 7.7}, 2)
    check(calls == ["play(idx=0, cut=7.7, loop=True)", "cut"], f"single track: loop then cut, got {calls}")
    check(cnt == 0, f"single-track cnt_sta must stay 0, got {cnt}")

    # 2. A press AFTER the cut starts the melody looping again — not a second cut. This
    #    needs one continuous 3-press drive: `drive_sta()` builds a fresh sim per call, so
    #    separate runs never reach the post-cut state (tail sounding, loop disarmed) and
    #    the branch would go uncovered. Discriminates a cut that forgets to clear
    #    `looping` — that would return "cut" here instead of replaying.
    calls, _ = drive_sta({"sta": ["m"], "sta_cut": 7.7}, 3)
    check(
        calls == ["play(idx=0, cut=7.7, loop=True)", "cut", "play(idx=0, cut=7.7, loop=True)"],
        f"press after the cut must loop from the head again, got {calls}",
    )

    # 3. TWO TRACKS — saikyo 大宮, the only such stop. Its first entry is an arrival
    #    door-opening announcement: plays through once, no cut, no loop. Only the
    #    LAST entry loops, and only then does sta_cut apply.
    calls, cnt = drive_sta({"sta": ["arrival", "melody"], "sta_cut": 7.7}, 3)
    check(
        calls == ["play(idx=0, cut=0, loop=False)", "play(idx=1, cut=7.7, loop=True)", "cut"],
        f"two tracks: announcement, then looping melody, then cut — got {calls}",
    )
    check(cnt == 1, f"cnt_sta must saturate at the last index, got {cnt}")

    # 4. A press during the NON-last track advances to the next track rather than
    #    cutting — there is no cut to take on a track that has no sta_cut.
    calls, _ = drive_sta({"sta": ["arrival", "melody"], "sta_cut": 7.7}, 2)
    check("cut" not in calls, f"must not cut while a non-last track plays, got {calls}")

    # 5. A stop whose sta_cut is absent or out of range never arms a loop, so the cut
    #    path is unreachable there and every press simply replays. The press must not
    #    be swallowed — that is the property, not which branch delivers it.
    calls, _ = drive_sta({"sta": ["m"], "sta_cut": 0}, 2, tail_armed=False)
    check(
        calls == ["play(idx=0, cut=0, loop=True)", "play(idx=0, cut=0, loop=True)"],
        f"unusable sta_cut must replay on every press, got {calls}",
    )
    check("cut" not in calls, f"unusable sta_cut must never reach the cut path, got {calls}")

    # 6. A stop with no melody is a no-op, both shapes the data uses.
    for empty in ({"sta": []}, {"sta": [""]}, {}):
        calls, _ = drive_sta(empty, 2)
        check(calls == [], f"stop with no sta must be silent, got {calls} for {empty}")


def main() -> int:
    check_press_edge()
    check_loop_cut()

    for f in FAILURES:
        print(f)
    print(f"{'FAIL' if FAILURES else 'PASS'}: sta playback (press-edge + loop/cut dispatch, {len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: MIT
# TIER: T1 — Page Up press-edge (PASimulator._handle_input_main)
"""One physical Page Up press must fire `_next_sta` exactly ONCE, however long it is held.

`_next_sta` picks its branch from current playback state — not playing plays from the
head, already playing restarts at `sta_cut` (the closing-door announcement). The input
loop polls `keyboard.is_pressed`, which is LEVEL-triggered, and Page Up was the one key
with no repeat throttle. So a single press was polled ~every 33ms at 30fps and did both:
poll 1 started the melody, poll 2 saw it playing and jumped to the cut. Loading a track
measures ~155ms against keypresses of 80-200ms, which is why it fired on roughly half of
presses rather than all of them — and why it was only visible after End, the one sequence
where the head is what the user expects.

Stubs the sim with SimpleNamespace and calls the method unbound — same technique as
test_fire_at_station.py. `keyboard.is_pressed` and `pygame.time.wait` are patched at the
module the handler resolves them through, so the frame sequence is fully scripted.
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


def drive(frames, *, sta_playing_after_first=True):
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


def main() -> int:
    # 1. THE BUG. One press held across four frames — a 130ms press at 30fps. Exactly
    #    one fire, and it must be from the head. Discriminates: reverting to the
    #    level-triggered `elif keyboard.is_pressed("page_up")` yields
    #    ["sta_from_head", "sta_from_cut", "sta_from_cut", "sta_from_cut"].
    calls = drive([{"page_up"}] * 4)
    check(calls == ["sta_from_head"], f"held Page Up must fire once from the head, got {calls}")

    # 2. Release then press again IS a second press — the restart-at-cut semantic the
    #    feature exists for. Without the flag clearing on release this returns one call.
    calls = drive([{"page_up"}, set(), {"page_up"}, {"page_up"}])
    check(calls == ["sta_from_head", "sta_from_cut"], f"re-press must restart at the cut, got {calls}")

    # 3. The reported sequence: play, End, restart. The restart must reach the head.
    #    This is the case the level-trigger broke — after End the first poll takes the
    #    from-head branch and the second immediately overrode it with the cut.
    calls = drive([{"page_up"}, set(), {"end"}, set(), {"page_up"}, {"page_up"}])
    check(
        calls == ["sta_from_head", "pause_sta", "sta_from_head"],
        f"End then restart must replay from the head, got {calls}",
    )

    # 4. Page Down keeps its LEVEL trigger — held-key self-retry is what the
    #    auto-input `pending_next_pa` path relies on, so this must NOT become an edge.
    calls = drive([{"page down"}] * 3)
    check(calls == ["pa", "pa", "pa"], f"Page Down must stay level-triggered, got {calls}")

    # 5. A held Page Up still blocks the End branch, exactly as the elif chain did
    #    before — the action moved to the edge, the chain did not change.
    calls = drive([{"page_up"}, {"page_up", "end"}])
    check(calls == ["sta_from_head"], f"held Page Up must keep swallowing End, got {calls}")

    for f in FAILURES:
        print(f)
    print(f"{'FAIL' if FAILURES else 'PASS'}: pageup-edge ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

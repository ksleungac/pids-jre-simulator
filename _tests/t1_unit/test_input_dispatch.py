# SPDX-License-Identifier: MIT
# TIER: T1 — main-loop input dispatch: what one frame does with keys and signals
"""What `PASimulator._handle_input_main` guarantees, for one frame at a time.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). The feature is
the DISPATCH — the priority chain, the audio gate, and the two single-shot signals
the AutoDriver writes from the OCR thread — not what any one action then does.
Four things arrive at this function and it decides which of them happens:

  1. THE SIGNALS   — pending_silent_advance, pending_pa_drain (OCR thread → here)
  2. PAGE DOWN     — manual press OR pending_next_pa, gated on PA not playing
  3. PAGE UP       — its own module (`test_playback.py`), because a press edge is
                     only legible against what _next_sta does with a second entry
  4. END           — pause, preferring STA when both streams are sounding

The chain is `if / elif / elif`, so ORDER is a guarantee and not an accident: a
held Page Down masks Page Up, a held Page Up masks End. Each case says what it
discriminates, because several of these branches fail by doing NOTHING, which an
entry-counting test cannot see.

Everything runs the real method unbound against a SimpleNamespace — no pygame
display, no audio device, no route — and records the CALL, not merely that the
method ran.
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


def drive(
    frames,
    *,
    pending_next_pa=False,
    silent_advance=None,
    pa_drain=False,
    at_station=False,
    pa_playing=(),
    sta_playing=(),
):
    """Run `_handle_input_main` once per entry in `frames`; return the call log.

    Each frame entry is the set of keys physically down. `pa_playing` /
    `sta_playing` are per-frame booleans (a bare False/True broadcasts), because
    the audio layer's answer CHANGES between frames in every case that matters —
    a signal deferred while a PA sounds has to fire once it stops, and that is
    two frames with different audio states.

    The flags are seeded as the OCR thread would have written them before frame 1.
    They are single-shot: the method clears them, so a second frame sees them
    already gone, which is what makes the "fires once" cases meaningful.
    """
    n = len(frames)
    pa_seq = list(pa_playing) if isinstance(pa_playing, (list, tuple)) else [pa_playing] * n
    sta_seq = list(sta_playing) if isinstance(sta_playing, (list, tuple)) else [sta_playing] * n
    pa_seq += [False] * (n - len(pa_seq))
    sta_seq += [False] * (n - len(sta_seq))

    calls: list[str] = []
    now = {"i": 0}

    fake = SimpleNamespace(
        _pageup_was_down=False,
        pending_next_pa=pending_next_pa,
        pending_silent_advance=silent_advance,
        pending_pa_drain=pa_drain,
        state=SimpleNamespace(at_station=at_station),
        audio=SimpleNamespace(
            is_pa_playing=lambda: pa_seq[now["i"]],
            is_sta_playing=lambda: sta_seq[now["i"]],
            is_playing=lambda: pa_seq[now["i"]] or sta_seq[now["i"]],
            pause_sta=lambda: calls.append("pause_sta"),
            pause_pa=lambda: calls.append("pause_pa"),
        ),
    )
    fake._next_pa = lambda: calls.append("pa")
    fake._next_sta = lambda: calls.append("sta")
    fake._silent_advance_to = lambda t: calls.append(f"silent_advance({t})")
    fake._drain_pa_at_station = lambda: calls.append("drain")

    orig_pressed, orig_wait = app_module.keyboard.is_pressed, app_module.pygame.time.wait
    try:
        for i, down in enumerate(frames):
            now["i"] = i
            app_module.keyboard.is_pressed = lambda k, _d=down: k in _d
            app_module.pygame.time.wait = lambda ms: None
            PASimulator._handle_input_main(fake)
    finally:
        app_module.keyboard.is_pressed, app_module.pygame.time.wait = orig_pressed, orig_wait
    return calls, fake


# ── 1. the PA branch and its audio gate ───────────────────────────────────────
# `critical_lessons §5`: a single-shot flag must be consumed only once its action's
# preconditions hold. Reset-before-gate loses the signal on a no-op, and the
# original symptom was the LCD stuck on まもなく.


def check_pa_branch() -> None:
    # 1. A manual press fires.
    calls, _ = drive([{"page down"}])
    check(calls == ["pa"], f"Page Down must fire a PA, got {calls}")

    # 2. The driver's flag fires through the SAME path, with no key down. This is
    #    the whole auto-input mechanism — one code path, two sources.
    calls, sim = drive([set()], pending_next_pa=True)
    check(calls == ["pa"], f"pending_next_pa must fire with no key down, got {calls}")
    check(sim.pending_next_pa is False, "a consumed pending_next_pa must be cleared")

    # 3. Single-shot: the flag fires exactly once, not on every subsequent frame.
    calls, _ = drive([set(), set(), set()], pending_next_pa=True)
    check(calls == ["pa"], f"pending_next_pa must fire once, got {calls}")

    # 4. THE §5 CASE. A PA is mid-play, so `_next_pa` would no-op. The flag must
    #    SURVIVE, and fire on the first frame the audio is free. Discriminates a
    #    reset moved above the audio gate: that yields [] — the at-station press
    #    silently dropped, which is how まもなく got stuck.
    calls, sim = drive([set(), set()], pending_next_pa=True, pa_playing=[True, False])
    check(calls == ["pa"], f"a deferred pending_next_pa must fire once free, got {calls}")
    check(sim.pending_next_pa is False, "the deferred flag must be cleared once it fires")

    # 5. Held across frames, a manual press self-retries — the level trigger is
    #    deliberate here and `pending_next_pa` depends on it (conventions.md
    #    § "A key whose action depends on state must be EDGE-triggered": Page Down
    #    is the documented exception, because its action is self-gating).
    calls, _ = drive([{"page down"}] * 3)
    check(calls == ["pa", "pa", "pa"], f"Page Down must stay level-triggered, got {calls}")

    # 6. Held while a PA sounds, it does nothing at all — the gate covers the
    #    manual source too, not just the flag.
    calls, _ = drive([{"page down"}] * 2, pa_playing=True)
    check(calls == [], f"Page Down must no-op while a PA sounds, got {calls}")


# ── 2. the AutoDriver's two single-shot signals ───────────────────────────────
# Both are written on the OCR thread and read here, so both describe a state that
# may be one or more frames old. AppState is mutated only on this thread; the
# driver writes bare flags and nothing else (auto_input/README.md).


def check_silent_advance() -> None:
    # 1. Parked app takes the advance — what the write side guaranteed. Without
    #    this case the guard below is satisfiable by never advancing at all.
    calls, _ = drive([set()], silent_advance="1A", at_station=True)
    check(calls == ["silent_advance(1A)"], f"parked app must take the re-entry advance, got {calls}")

    # 2. THE BUG (#105). The app left 1C between the write and this read — a Page
    #    Down at the platform drains the backlog and advances to 1A — so the flag
    #    describes a desync that is already resolved, and taking it advances a
    #    SECOND time and skips a stop. Discriminates: dropping the
    #    `if self.state.at_station:` guard yields ["silent_advance(1A)"].
    calls, _ = drive([set()], silent_advance="1A", at_station=False)
    check(calls == [], f"stale re-entry signal must not advance a moving app, got {calls}")

    # 3. DROPPED, not held. Re-entry is forward-only and irreversible, so a flag
    #    parked until the app happens to stop again would fire against a situation
    #    nobody resolved. A real desync is re-resolved next cycle, and the
    #    detector's two-probe consensus latch re-confirms before committing.
    calls, sim = drive([set(), set()], silent_advance="1A", at_station=False)
    check(calls == [], f"a dropped signal must not fire on a later frame, got {calls}")
    check(sim.pending_silent_advance is None, "a dropped signal must still be cleared")

    # 4. Not audio-gated, unlike the PA branch — the advance is silent by
    #    definition, so a sounding PA is no reason to defer it.
    calls, _ = drive([set()], silent_advance="1B", at_station=True, pa_playing=True)
    check(calls == ["silent_advance(1B)"], f"a silent advance must not wait on audio, got {calls}")


def check_pa_drain() -> None:
    # 1. ORDER is the guarantee. The at-station queue must read exhausted BEFORE
    #    the synthesized press, or the press spends itself on another announcement
    #    instead of departing. Discriminates a drain moved below `_next_pa`.
    calls, _ = drive([{"page down"}], pa_drain=True, at_station=True)
    check(calls == ["drain", "pa"], f"drain must precede the press, got {calls}")

    # 2. Single-shot — frame 2 presses without draining again.
    calls, sim = drive([{"page down"}] * 2, pa_drain=True, at_station=True)
    check(calls == ["drain", "pa", "pa"], f"drain must fire once, got {calls}")
    check(sim.pending_pa_drain is False, "a consumed drain request must be cleared")

    # 3. It rides the PA branch's gate, so a sounding PA defers BOTH together —
    #    they must not come apart, or the queue empties for a press that never
    #    happened and the user loses announcements with nothing advancing.
    calls, _ = drive([set(), set()], pending_next_pa=True, pa_drain=True, at_station=True, pa_playing=[True, False])
    check(calls == ["drain", "pa"], f"a deferred drain must stay paired with its press, got {calls}")

    # 4. The ordinary case: every manual press, and every auto-fire at a stop with
    #    nothing queued, drains nothing.
    calls, _ = drive([{"page down"}], at_station=True)
    check(calls == ["pa"], f"a press with no drain request must not drain, got {calls}")


# ── 3. the priority chain ─────────────────────────────────────────────────────
# `if / elif / elif`. The masking is deliberate and was preserved verbatim through
# the 2026-08-11 press-edge fix — only Page Up's ACTION moved to the edge, the
# chain did not change.


def check_chain_order() -> None:
    # 1. Page Down masks Page Up.
    calls, _ = drive([{"page down", "page_up"}])
    check(calls == ["pa"], f"Page Down must mask Page Up, got {calls}")

    # 2. Page Up masks End, on the key being DOWN rather than on its edge — a held
    #    Page Up keeps swallowing End on every frame, including frames where the
    #    edge has already been spent.
    calls, _ = drive([{"page_up"}, {"page_up", "end"}], sta_playing=True)
    check(calls == ["sta"], f"held Page Up must keep swallowing End, got {calls}")

    # 3. A PA-gated Page Down does NOT fall through to Page Up. The gate is part
    #    of the branch's condition, so a blocked press masks nothing — the frame
    #    goes to Page Up. Locks which of the two readings the elif chain has.
    calls, _ = drive([{"page down", "page_up"}], pa_playing=True)
    check(calls == ["sta"], f"a PA-blocked Page Down must not swallow Page Up, got {calls}")

    # 4. The signals sit ABOVE the chain, so they land whatever is held.
    calls, _ = drive([{"page_up"}], silent_advance="1A", at_station=True)
    check(calls == ["silent_advance(1A)", "sta"], f"signals must land above the chain, got {calls}")


# ── 4. the pause key ──────────────────────────────────────────────────────────
# End is stateful — each press decides which stream is silenced — so which one it
# picks is the guarantee, and it is gated on something actually sounding.


def check_pause() -> None:
    # 1. Both sounding: STA loses. The in-train PA carries information; the
    #    platform melody is the one people want silenced.
    calls, _ = drive([{"end"}], pa_playing=True, sta_playing=True)
    check(calls == ["pause_sta"], f"End must prefer pausing STA when both sound, got {calls}")

    # 2. PA alone: PA is paused. Discriminates a preference written as an
    #    unconditional `pause_sta`.
    calls, _ = drive([{"end"}], pa_playing=True)
    check(calls == ["pause_pa"], f"End must pause the PA when only it sounds, got {calls}")

    # 3. STA alone: STA is paused.
    calls, _ = drive([{"end"}], sta_playing=True)
    check(calls == ["pause_sta"], f"End must pause the STA when only it sounds, got {calls}")

    # 4. Silence: nothing happens. `and self.audio.is_playing()` is the guard, and
    #    without it End would pause a channel that has nothing on it every frame.
    calls, _ = drive([{"end"}] * 3)
    check(calls == [], f"End must do nothing when nothing sounds, got {calls}")


def main() -> int:
    check_pa_branch()
    check_silent_advance()
    check_pa_drain()
    check_chain_order()
    check_pause()

    for f in FAILURES:
        print(f)
    print(f"{'FAIL' if FAILURES else 'PASS'}: input dispatch (PA gate + driver signals + chain order + pause, {len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

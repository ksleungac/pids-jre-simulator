# SPDX-License-Identifier: MIT
# TIER: T1 — the departure-bell box: what it shows, where it stands, what a press does
"""What the bell box guarantees, as pure functions.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). The box is a
second window with its own geometry and its own press semantics, so it is its
own seam — the same reason `test_stream.py` is not folded into `test_window.py`.

  1. WHAT IT SHOWS   — departure_bell.BellState.of
  2. WHERE A CAP IS  — departure_bell.cap_rects / hit_test
  3. WHERE IT STANDS — bell_window.pick_zoom / place_beside, and the drag snap
  4. A REMOTE TAP    — BellWindow.tap, which shares § 2's geometry
  5. WHAT A PRESS DOES — PASimulator._bell_press

Section 5 is the one with a bug in it waiting: ON latches and OFF is momentary,
so the two caps act on OPPOSITE sides of `is_sta_looping()`. Collapsing them
into "both call `_next_sta`" is the natural simplification and it is wrong in a
way nothing raises on — ON pressed twice would cut the melody it just started.

Section 2 is load-bearing for stage 3 as well as the local window: the remote
tap resolves through the same `hit_test`, so a drift here moves both at once.

No pygame display, no window, no audio device: sections 1–4 are pure calls and
section 5 runs `_bell_press` unbound against a SimpleNamespace, the same
technique `test_playback.py` uses.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bell_window  # noqa: E402
import departure_bell as bell  # noqa: E402
import window_utils  # noqa: E402
from app import PASimulator  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append("  " + msg)


# ── 1. what it shows ──────────────────────────────────────────────────────────
# CONTRACT (departure_bell): the box owns no state — everything it draws is
# derived from audio. The one thing this can catch is the derivation being
# inverted or a field going independent, which is why the truth table is
# exhaustive over the three inputs rather than illustrative.
def check_state() -> None:
    for looping in (False, True):
        for on_flash in (False, True):
            for off_flash in (False, True):
                st = bell.BellState.of(looping, on_flash=on_flash, off_flash=off_flash)
                check(
                    st.on_latched is looping and st.on_flash is on_flash and st.off_flash is off_flash,
                    f"BellState.of({looping}, {on_flash}, {off_flash}) -> {st}",
                )

    # The latch is the melody, so it does not need a press to stay in: a state
    # built with no flash at all still draws ON pressed while the loop runs.
    check(bell.BellState.of(True).on_latched, "a running loop must show ON latched with no press")
    check(not bell.BellState.of(False).on_latched, "silence must not show ON latched")


# ── 2. where a cap is ─────────────────────────────────────────────────────────
# Canvas coordinates, shared by the local window (window px / zoom) and the
# remote tap (fraction * canvas). Both centres hit, the dead band between them
# and the plate above must NOT, or a press near a cap fires the other one.
def check_hit() -> None:
    rects = bell.cap_rects()
    check(set(rects) == {"on", "off"}, f"cap_rects must name exactly on/off, got {sorted(rects)}")
    check(rects["on"].size == rects["off"].size, f"the caps are equal on the box: {rects['on'].size} vs {rects['off'].size}")
    check(rects["on"].centerx == rects["off"].centerx, "the caps share a vertical centre line")
    check(rects["on"].bottom < rects["off"].top, "ON sits above OFF with a gap between them")

    for name, r in rects.items():
        check(bell.hit_test(r.center) == name, f"the centre of {name} must hit {name}")
        check(bell.hit_test((r.left, r.top)) == name, f"the top-left px of {name} is inside it")
        check(bell.hit_test((r.right, r.bottom)) is None, f"one px past {name}'s bottom-right is outside it")

    gap_y = (rects["on"].bottom + rects["off"].top) // 2
    check(bell.hit_test((rects["on"].centerx, gap_y)) is None, "the gap between the caps is dead")
    check(bell.hit_test((0, 0)) is None, "the canvas corner is dead")
    check(bell.hit_test((rects["on"].centerx, 0)) is None, "the plate above the caps is dead")

    # A WINDOW point is a canvas point divided by the zoom, and that is the only
    # difference between them — the same conversion serves the click and the
    # hover cursor. At 3x, a point 3x further down the window is the same cap;
    # forgetting the divide would send every press to whatever sits at 1/3 the
    # depth, which for the OFF cap is the ON cap.
    inst = bell_window.BellWindow.__new__(bell_window.BellWindow)
    for zoom in (1, 2, 3):
        inst.zoom = zoom
        for name, r in rects.items():
            win_pt = (r.centerx * zoom, r.centery * zoom)
            check(inst._cap_at(win_pt) == name, f"at {zoom}x, window point {win_pt} must be {name}, got {inst._cap_at(win_pt)}")
    inst.zoom = 3
    check(
        inst._cap_at(rects["off"].center) != "off",
        "at 3x an UN-divided OFF centre must not still read as OFF — that is the case the divide exists for",
    )


# ── 3. where it stands ────────────────────────────────────────────────────────
# The box scales by whole multiples like everything else in this app, and its
# multiple comes from the SCREEN — never from the PA window. The two are separate
# windows the user sizes separately, so the box must not inherit or follow the
# other's zoom; a case here reading a PA-window height would be the coupling
# coming back. Work areas are passed as ARGUMENTS, which is the only reason a 4K
# case can be checked from a 1080p machine (same rule as `test_window.py` § 1).
#
# Canvas pinned literally rather than imported: importing it would scale the
# expectations with any mutation of it and the row would stop discriminating.
BELL_W, BELL_H = 192, 290


def check_geometry() -> None:
    check(bell.BELL_CANVAS == (BELL_W, BELL_H), f"the box's canvas moved to {bell.BELL_CANVAS}; retune the rows below, do not import it")

    # (label, work, expected opening k). The box opens at a smaller share of the
    # screen than the PA window, but climbs the same ladder: 1x through 1440p,
    # 2x on 4K and 5K.
    for label, work, want in [
        ("1366x768  old laptop", (1366, 720), 1),
        ("1920x1080 @125%", (1920, 1020), 1),
        ("2560x1440 27in", (2560, 1392), 1),
        ("3840x2160 4K", (3840, 2064), 2),
        ("5120x2880 5K", (5120, 2784), 2),
        ("a work area shorter than the box", (1920, 250), 1),  # never below 1x
    ]:
        got = bell_window.pick_zoom(*work)
        check(got == want, f"pick_zoom {label}: want {want}x, got {got}x")

    # A drag snaps to a whole multiple, bounded by what fits the screen. The
    # affordance the PA window has, reached through the same helper rather than a
    # second implementation of it.
    kmax = window_utils.max_zoom(BELL_W, BELL_H, 1920, 1020)
    check(kmax == 3, f"1080p fits 3 whole boxes tall, got {kmax}")
    for requested, want in [(300, 1), (420, 1), (440, 2), (580, 2), (900, 3), (4000, 3), (1, 1)]:
        got = window_utils.snap_zoom(BELL_H, requested, kmax)
        check(got == want, f"snap_zoom({requested}px) want {want}x, got {got}x")

    # Beside the PA window, tops level.
    work = (1920, 1020)
    x, y = bell_window.place_beside((200, 100, 930, 588), (BELL_W, BELL_H), work)
    check((x, y) == (930 + bell_window.GAP_PX, 100), f"the box stands to the right with tops level, got {(x, y)}")

    # No room on the right -> the other side, rather than off the screen.
    x, y = bell_window.place_beside((1000, 100, 1850, 588), (BELL_W, BELL_H), work)
    check(x == 1000 - bell_window.GAP_PX - BELL_W, f"no room on the right means the left, got x={x}")

    # Clamped into the work area either way.
    x, y = bell_window.place_beside((0, 900, 1900, 1010), (BELL_W, BELL_H), work)
    check(0 <= x <= work[0] - BELL_W, f"x must stay inside the work area, got {x}")
    check(0 <= y <= work[1] - BELL_H, f"y must stay inside the work area, got {y}")


# ── 4. what a press does ──────────────────────────────────────────────────────
# The real box: ON LATCHES (pressing it again while it is in does nothing), OFF
# is MOMENTARY (it does nothing unless there is a latch to release). Page Up
# carries both meanings on one key because a keyboard has no latch to look at.
# Both caps route to `_next_sta` — one audio path — and the asymmetry is the
# only thing the box adds.
def _press(which: str, looping: bool):
    fired = []
    stub = SimpleNamespace(
        audio=SimpleNamespace(is_sta_looping=lambda: looping),
        _next_sta=lambda: fired.append("next_sta"),
    )
    PASimulator._bell_press(stub, which)
    return fired


def check_remote_tap() -> None:
    """A tap from the stream resolves through the SAME geometry as a click.

    The dock carries the window's own surface, so a point in it is a window
    point — one `_cap_at` for both, which is what stops the remote hit-rects
    drifting from what is drawn. Locked because the two surfaces are wired
    separately and nothing would raise if they diverged.
    """
    inst = bell_window.BellWindow.__new__(bell_window.BellWindow)
    inst._closed = False
    inst._flash_until = {"on": 0.0, "off": 0.0}
    rects = bell.cap_rects()

    for zoom in (1, 2):
        inst.zoom = zoom
        inst._flash_until = {"on": 0.0, "off": 0.0}
        for name, r in rects.items():
            got = inst.tap((r.centerx * zoom, r.centery * zoom), 100.0)
            check(got == name, f"a remote tap on {name} at {zoom}x must press {name}, got {got}")
            check(inst._flash_until[name] > 100.0, f"a remote tap on {name} must light the flash on the PC's box too")

    # A tap on the casting presses nothing and lights nothing.
    inst.zoom = 1
    inst._flash_until = {"on": 0.0, "off": 0.0}
    check(inst.tap((2, 2), 100.0) is None, "a remote tap on the casting must press nothing")
    check(inst._flash_until == {"on": 0.0, "off": 0.0}, "a remote tap that hit no cap must light nothing")

    # A closed box takes no taps — the dock leaves the stream with the window.
    inst._closed = True
    check(inst.tap(rects["on"].center, 100.0) is None, "a closed box must refuse a remote tap")
    check(inst.surface() is None, "a closed box publishes no surface, so the dock disappears")


def check_press() -> None:
    check(_press("on", looping=False) == ["next_sta"], "ON with nothing playing must start the melody")
    check(_press("on", looping=True) == [], "ON while the melody loops is a no-op — the cap is already in")
    check(_press("off", looping=True) == ["next_sta"], "OFF while the melody loops must cut it")
    check(_press("off", looping=False) == [], "OFF with nothing playing is a no-op — there is no latch to release")

    # A press that hit neither cap must never reach the audio, whatever the state.
    for looping in (False, True):
        check(_press("", looping) == [], f"a press on no cap must be silent (looping={looping})")


def main() -> int:
    check_state()
    check_hit()
    check_geometry()
    check_remote_tap()
    check_press()

    for f in FAILURES:
        print(f)
    print(
        f"{'FAIL' if FAILURES else 'PASS'}: departure bell (state derivation, cap hit-test, window placement, ON-latch/OFF-momentary, {len(FAILURES)} failure(s))"
    )
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

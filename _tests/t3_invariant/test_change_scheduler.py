"""T3 — ChangeScheduler invariants (lower-LCD flash fix, #78).

Drives the REAL scheduler against a REAL PASimulator (headless, silent audio)
over simulated timestamps. The oracles are independent of the implementation:
observed change TIMES and the floor between them, not a restatement of the
scheduler's own arithmetic.

Route: sobu/1217F — the only through-service route (2 frames, junction at
千葉/idx 9), so the JR-logo restart transition is exercisable, and it has both
transfer-bearing and transfer-less stops.

The auto-driver reaches the STOPPING edge through
``pending_next_pa`` → ``_handle_input`` → ``_next_pa`` (a background thread
setting a single-shot flag consumed on the main thread). ``_next_pa`` is that
shared seam, so the Preemptive cases drive it directly rather than faking OCR
or poking ``state.at_station`` by hand.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

import displays.base as base  # noqa: E402

# Pinned here rather than imported: a test that reads the constants under test
# scales its own expectations with any mutation of them and stops
# discriminating. The schedule below is the SPEC — changing the implementation
# must fail here and be an explicit edit in both places.
BEAT = 4.0  # constants.BEAT_SECONDS
CHANGE_FLOOR = 1 * BEAT  # displays.base.CHANGE_FLOOR_BEATS
SCHEDULE_BEATS = {"language": 1, "full": 3, "eight": 3, "transfer": 2, "swap_hold": 3, "logo": 1}

ROUTE = "audio/sobu/1217F"
FRAME_DT = 1.0 / 15.0  # FRAME_RATE
EPS = 1e-6
JUNCTION = 9  # 千葉 — frames[0].to_idx, where the through-service swap fires
NO_TRANSFERS = 12  # 四街道 — no transfers AND a stopping station (idx 10 東千葉 has pa=[], so _next_pa skips it)


class Rig:
    """A headless sim plus a log of every visible change the scheduler applies."""

    def __init__(self):
        from app import PASimulator

        self.sim = PASimulator(ROUTE, preview=True)
        self.t = 1000.0
        self.sim.scheduler.seed(self.t)
        self.changes = []  # (timestamp, snapshot)
        self._prev = self._snapshot()

    def _snapshot(self):
        low = self.sim.lower
        return (self.sim.upper.mode_cycler.current_mode, low._current_slot, low.transition_active)

    @property
    def slot(self):
        return self.sim.lower._current_slot

    @property
    def last_change(self):
        return self.sim.scheduler.last_change

    def step(self, dt=FRAME_DT):
        """Advance one frame exactly as app.run() does.

        The draws are included on purpose, and the snapshot is taken AFTER
        them: `draw` is contractually pure, so any renderer that ticks a timer
        of its own — the two-clock bug this design removes — shows up here as a
        change the scheduler never applied.
        """
        self.t += dt
        self.sim.state.update_skip_progress(self.t)
        self.sim.scheduler.tick(self.t, self.sim.state)
        self.sim.upper.draw("12:00")
        self.sim.lower.draw(self.t)
        cur = self._snapshot()
        if cur != self._prev:
            self.changes.append((self.t, cur))
            self._prev = cur

    def run(self, seconds):
        for _ in range(int(round(seconds / FRAME_DT))):
            self.step()

    def run_until_change(self, limit=30.0):
        """Step until the next change lands. Returns its timestamp."""
        n = len(self.changes)
        for _ in range(int(round(limit / FRAME_DT))):
            self.step()
            if len(self.changes) > n:
                return self.changes[-1][0]
        raise AssertionError(f"no change within {limit}s")

    def depart_and_arrive(self, limit=40):
        """Press PA until the train is STOPPING at the next station.

        Same call the auto-driver's pending_next_pa reaches; no frames are
        stepped, so the arrival lands between ticks like a real mid-frame
        background-thread fire.
        """
        start = self.sim.state.curr_stop
        for _ in range(limit):
            self.sim._next_pa()
            if self.sim.state.at_station and self.sim.state.curr_stop != start:
                return
        raise AssertionError("never arrived at the next station")

    def gaps(self):
        ts = [t for t, _ in self.changes]
        return [b - a for a, b in zip(ts, ts[1:])]


def main():
    pygame.init()
    pygame.display.set_mode((730, 420))
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # --- Boot seed -----------------------------------------------------
    # An unseeded timer makes the first frame compute a huge delta and
    # instant-fire, so the boot view never persists.
    r = Rig()
    r.run(3.9)  # language cadence is 4s
    check(not r.changes, f"boot seed: change fired within 3.9s of boot ({r.changes})")

    # --- The slot keeps rotating ----------------------------------------
    # Gross-breakage guard: a cadence-aligned slot (12s = 3 x 4s) comes due on
    # the very frame the language is due, so a floor that gates it wrongly can
    # stall it. (With floor 2s < cadence 4s it would stall by 2s rather than
    # forever; the permanent starvation the design note warns about needs
    # floor >= cadence. This catches the gross case; atomicity is pinned below.)
    r = Rig()
    r.run(60.0)
    slot_changes = sum(1 for (_, snap), (_, prev) in zip(r.changes[1:], r.changes) if snap[1] != prev[1])
    slot_changes += 1 if r.changes and r.changes[0][1][1] != r.sim.lower._SLOT_FULL else 0
    check(slot_changes >= 4, f"rotation: only {slot_changes} slot rotations in 60s (expected >= 4)")

    # --- Atomic batching -------------------------------------------------
    # THE property the one-tick design turns on. When both axes come due on the
    # same frame they must apply as ONE event. A scheduler that ticks them in
    # turn against a mutating last_change splits that into two changes a floor
    # apart — an extra visible mutation, and the seed of the starvation trap if
    # the floor is ever raised to the cadence.
    both = [t for (t, snap), (_, prev) in zip(r.changes[1:], r.changes) if snap[0] != prev[0] and snap[1] != prev[1]]
    check(both, "atomicity: language and slot never batched into one event across 60s (are they ticked in turn?)")

    # --- Floor, absent any Preemptive -----------------------------------
    # At floor == cadence this also pins the quantizer: TRANSFER's off-grid 6s
    # expiry must DEFER to the next allowed moment rather than land mid-interval.
    tight = [g for g in r.gaps() if g < CHANGE_FLOOR - EPS]
    check(not tight, f"floor: {len(tight)} gaps below {CHANGE_FLOOR}s in a static 60s run ({tight[:4]})")

    # --- Floor under a forced collision ----------------------------------
    # Re-anchor the floor, then make the language due on the very next frame.
    # Only the floor stands between those two changes.
    # The schedule is authored in whole beats, so the written duration is the
    # one observed. A fractional/off-grid value silently defers to the next beat
    # and the source stops describing the screen (6s once rendered as 8s).
    check(
        base.beats(base.CHANGE_FLOOR_BEATS) == CHANGE_FLOOR,
        f"floor: implementation is {base.beats(base.CHANGE_FLOOR_BEATS)}s, spec pins {CHANGE_FLOOR}s",
    )
    low0 = Rig().sim.lower
    spec = {
        "language": base.LANGUAGE_BEATS,
        "full": low0._SLOT_BEATS[low0._SLOT_FULL],
        "eight": low0._SLOT_BEATS[low0._SLOT_EIGHT],
        "transfer": low0._SLOT_BEATS[low0._SLOT_TRANSFER],
        "swap_hold": low0._SWAP_HOLD_BEATS,
        "logo": low0._TRANSITION_BEATS,
    }
    check(spec == SCHEDULE_BEATS, f"schedule drifted from spec: {spec} != {SCHEDULE_BEATS}")
    for name, n in spec.items():
        check(isinstance(n, int) and not isinstance(n, bool) and n >= 1, f"schedule: {name} is {n!r}, not a whole beat count")

    r = Rig()
    r.run(1.0)
    r.sim.scheduler.last_change = r.t
    r.sim.upper.mode_cycler.seed(r.t - 99)  # language overdue
    mode_at = lambda: r.sim.upper.mode_cycler.current_mode  # noqa: E731
    mode_before = mode_at()
    anchored_at = r.t
    r.run(CHANGE_FLOOR - 0.3)
    check(
        mode_at() == mode_before,
        f"floor collision: an overdue language flip fired {r.t - anchored_at:.2f}s after a change (floor is {CHANGE_FLOOR}s)",
    )
    r.run(0.5)  # past the floor — it must then fire, not be dropped
    check(mode_at() != mode_before, "floor collision: the deferred language flip was dropped instead of applied late")

    # --- Preemptive: the STOPPING edge beats the floor -------------------
    # The auto-driver fires at an arbitrary phase offset, so a stop routinely
    # lands a fraction of a second after a scheduled change. Transfer info must
    # show at once anyway — that bypass is by design.
    r = Rig()
    r.sim.jump_to_stop(4)  # a transfer-bearing stop, mid-route
    r.run(1.0)
    t_change = r.run_until_change()
    r.step()  # ~0.07s later — well inside the floor
    r.depart_and_arrive()
    r.step()
    check(
        r.slot == r.sim.lower._SLOT_TRANSFER,
        f"stopping edge: slot is {r.slot}, expected TRANSFER despite being {r.t - t_change:.2f}s inside the floor",
    )
    t_forced = r.last_change
    check(abs(t_forced - r.t) < EPS, "stopping edge: force-switch did not re-anchor the floor")

    # --- ...and re-anchors it -------------------------------------------
    n_before = len(r.changes)
    r.run(CHANGE_FLOOR - 0.2)
    check(
        len(r.changes) == n_before,
        f"re-anchor: {len(r.changes) - n_before} change(s) landed within {CHANGE_FLOOR}s of the force-switch",
    )

    # --- A no-op edge must NOT re-anchor ---------------------------------
    # Already on TRANSFER: nothing is visibly changing, so stamping the floor
    # would silently shove the language cadence out at every single stop.
    r = Rig()
    r.sim.jump_to_stop(4)
    r.run(1.0)  # first observation — the edge detector needs a prior frame
    r.depart_and_arrive()
    r.step()
    check(r.slot == r.sim.lower._SLOT_TRANSFER, "no-op setup: expected to be on TRANSFER")
    anchored = r.last_change
    r.depart_and_arrive()  # arrive at the NEXT transfer-bearing station
    r.step()
    check(
        r.last_change == anchored or r.slot != r.sim.lower._SLOT_TRANSFER,
        "no-op edge: re-anchored the floor while already showing TRANSFER",
    )

    # --- A station with no transfers must not re-anchor ------------------
    r = Rig()
    r.sim.jump_to_stop(NO_TRANSFERS - 1)  # 都賀 — the preceding stopping station
    r.run(1.0)
    # Re-anchor everything so nothing is scheduled-due; then only a Preemptive
    # could move anything, which is exactly what this case says must not happen.
    r.sim.lower.apply_slot(r.slot, r.t)
    r.sim.upper.mode_cycler.seed(r.t)
    r.sim.scheduler.last_change = r.t
    anchored = r.last_change
    slot_before = r.slot
    r.depart_and_arrive()
    r.step()
    check(r.sim.state.curr_stop == NO_TRANSFERS, f"setup: expected to arrive at {NO_TRANSFERS}, got {r.sim.state.curr_stop}")
    check(
        r.last_change == anchored and r.slot == slot_before,
        "transfer-less station: the edge forced a change / re-anchored with no TRANSFER slot available",
    )

    # --- Cross-stop jump while at_station stays True ---------------------
    r = Rig()
    r.sim.jump_to_stop(4)
    r.step()
    r.sim.lower.apply_slot(r.sim.lower._SLOT_FULL, r.t)
    r.sim.jump_to_stop(6)  # both transfer-bearing; at_station stays True
    r.step()
    check(r.slot == r.sim.lower._SLOT_TRANSFER, f"cross-stop jump: slot is {r.slot}, expected TRANSFER")

    # --- Nothing changes under the JR-logo restart screen -----------------
    # A slot mutating out of sight flashes the instant the logo clears.
    r = Rig()
    r.sim.jump_to_stop(JUNCTION)
    r.run(1.0)
    # Snapshot the visible pair BEFORE the fire frame. Filtering the change log
    # by `t > logo_t` instead would exclude the fire frame itself — the one frame
    # an illegal change can land on — and the assertion would name an invariant
    # it does not actually lock. (It silently stopped discriminating once the
    # floor moved to a full beat; caught by re-running the mutation.)
    pair_before = (r.sim.upper.mode_cycler.current_mode, r.slot)
    while not r.sim.lower.transition_active:
        # Captured BEFORE the step, so on exit it holds the pair as of the frame
        # just before the fire — capturing after would already include whatever
        # the fire frame did, which is precisely what must be caught.
        pair_before = (r.sim.upper.mode_cycler.current_mode, r.slot)
        r.step()
        if r.t > 1000.0 + 120:
            raise AssertionError("through-service swap never fired")
    while r.sim.lower.transition_active:
        r.step()
    # Logo-up frames may flip ONLY the transition flag; mode/slot must not move.
    under_logo = [t for t, snap in r.changes if snap[2] and (snap[0], snap[1]) != pair_before]
    check(not under_logo, f"logo: {len(under_logo)} change(s) applied while the restart screen was up ({under_logo[:3]})")

    # The reveal is a Preemptive: the new frame comes up on its DEFAULT slot, so
    # the first view of a through-service segment is deterministic and starts a
    # full dwell — not whatever the pre-swap cycle happened to leave behind
    # (which at a junction is always TRANSFER, from the stopping force-switch).
    reveal_t = r.t
    expected = r.sim.lower._available_slots(r.sim.state)[0]
    check(
        r.slot == expected,
        f"logo reveal: revealed on slot {r.slot}, expected the frame's default slot {expected}",
    )
    r.run(CHANGE_FLOOR - 0.2)
    after = [t for t, _ in r.changes if t > reveal_t + EPS]
    check(not after, f"logo reveal: a change landed within {CHANGE_FLOOR}s of the reveal ({after[:3]})")

    # The reveal must RESTART the dwell, not inherit the pre-swap remainder.
    # Slot timers are wall-clock, so the logo burns dwell invisibly; without a
    # restart the new segment's opening view expires after one floor.
    slot_at_reveal = r.slot
    r.run(8.0 - (CHANGE_FLOOR - 0.2))
    check(
        r.slot == slot_at_reveal,
        f"logo reveal: the new segment's first view was cut after <8s (slot {slot_at_reveal} -> {r.slot}); " "the reveal did not restart the dwell",
    )

    # Nothing may change in the floor before the swap fires either — the logo
    # covering a just-rotated view is the same flash, seen from the other side.
    logo_up = next((t for t, snap in r.changes if snap[2]), None)
    check(logo_up is not None, "swap: never observed the logo in the change log")
    if logo_up is not None:
        before = [t for t, _ in r.changes if logo_up - CHANGE_FLOOR < t < logo_up - EPS]
        check(not before, f"swap quiet: {len(before)} change(s) landed within {CHANGE_FLOOR}s before the logo ({before})")

    # --- Language coverage ------------------------------------------------
    # Every (slot, language) pairing must surface EVENTUALLY. There is no
    # requirement that one appearance of a slot spans all three languages — a
    # slot may show one language this time and another the next, so long as no
    # pairing is permanently buried by a locked phase relationship between the
    # slot rotation and the language cadence.
    #
    # Simulated rather than derived from arithmetic: the cadences are tuned by
    # feel, not measured, so a retune must be checked by observation. This fails
    # loudly if some future set of durations locks a pairing out.
    r = Rig()
    expected = {(slot, m) for slot in r.sim.lower._available_slots(r.sim.state) for m in r.sim.upper.mode_cycler.mode_displays}
    seen = set()
    for _ in range(int(round(180.0 / FRAME_DT))):
        r.step()
        seen.add((r.slot, r.sim.upper.mode_cycler.current_mode))
    missing = expected - seen
    check(not missing, f"coverage: {len(missing)} (slot, language) pairing(s) never appeared in 180s: {sorted(missing)}")

    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS - change scheduler invariants (floor, starvation, boot seed, preemptive bypass/re-anchor, logo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

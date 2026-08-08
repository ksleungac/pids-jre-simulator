# SPDX-License-Identifier: MIT
"""Base classes and utilities for train display system.

The view schedule is authored in BEATS, never in seconds. One beat is
``constants.BEAT_SECONDS`` (4s), and every discrete change — language flip,
slot rotation, through-service swap, restart screen — is a whole number of
beats. Authoring in seconds is what let a written 6s render as an observed 8s:
an off-grid duration silently defers to the next allowed moment, so the number
in the source stopped describing the screen. Whole beats make written ==
observed by construction. See DISPLAY.md § "Change scheduler".
"""

import time
from enum import IntEnum

# --- The schedule, in beats ------------------------------------------------
# Language cadence. One beat is DEFINED as this, so it is 1 by construction;
# named rather than inlined so the schedule below reads uniformly.
LANGUAGE_BEATS = 1
# Minimum gap between any two visible changes. At exactly one beat this is also
# the quantizer: an off-grid slot duration defers to the next beat instead of
# landing mid-interval, so the rhythm is uniform without constraining what may
# be written. It deliberately does NOT sit below the cadence — that earlier
# split existed to dodge a starvation trap (with floor == cadence the floor is
# armed continuously, so under a scheduler that ticked each axis IN TURN a
# cadence-aligned slot could only come due on a language-tick frame, see delta
# 0, and block forever). ChangeScheduler evaluates both axes against one
# frame-start snapshot and batches them, so that trap cannot occur.
# Cost, accepted: a Preemptive re-anchor dead-zones the other axis a full beat.
CHANGE_FLOOR_BEATS = 1


def beats(n: int) -> float:
    """Whole beats → seconds. The ONLY way a duration enters the schedule."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError(f"schedule durations must be a whole number of beats >= 1, got {n!r}")
    from constants import BEAT_SECONDS  # local: constants must not import displays

    return n * BEAT_SECONDS


class DisplayMode(IntEnum):
    """Display modes for Upper LCD cycling."""

    KANJI = 0
    FURIGANA = 1
    ENGLISH = 2


class ModeCycler:
    """
    Manages cycling through display modes.

    Shared utility used by all train model displays.
    """

    # CONTRACT: freeze a forced mode with `cycler.enabled = False`, NOT `paused`
    # (silently creates a new attr; un-freezes on the next interval).
    # See DISPLAY.md § "⚠️ Cycler.enabled vs Cycler.paused". Has bitten preview scripts.
    def __init__(self, mode_displays: dict, default_mode: DisplayMode = DisplayMode.ENGLISH):
        """
        Initialize mode cycler.

        Args:
            mode_displays: Dict mapping DisplayMode to display class instances
            default_mode: Starting display mode
        """
        self.mode_displays = mode_displays
        self.current_mode = default_mode
        self.last_switch_time = time.time()
        self.enabled = True

    # CONTRACT: the cycler does NOT tick itself. ChangeScheduler (below) owns
    # every discrete change; it queries `is_due` and calls `advance`. A caller
    # that advances this directly re-introduces the uncoordinated second clock
    # the scheduler exists to remove. See DISPLAY.md § "Change scheduler".
    def seed(self, current_time: float) -> None:
        """Anchor the language timer at boot (real wall-clock, never 0.0)."""
        self.last_switch_time = current_time

    def is_due(self, current_time: float) -> bool:
        """True when the language cadence (one beat) has elapsed and cycling is enabled."""
        if not self.enabled:
            return False
        return current_time - self.last_switch_time >= beats(LANGUAGE_BEATS)

    def advance(self, current_time: float) -> None:
        """Commit a language flip and restart the cadence timer."""
        self._cycle_to_next()
        self.last_switch_time = current_time

    def _cycle_to_next(self) -> None:
        """Cycle to the next available display mode."""
        modes = list(self.mode_displays.keys())
        if self.current_mode not in modes:
            self.current_mode = modes[0]
            return

        current_idx = modes.index(self.current_mode)
        self.current_mode = modes[(current_idx + 1) % len(modes)]

    def get_current_mode(self) -> DisplayMode:
        """Get current display mode."""
        return self.current_mode

    def get_current_display(self):
        """Get display instance for current mode."""
        return self.mode_displays[self.current_mode]


class ChangeScheduler:
    """The single owner of every discrete view change.

    A *change* is any discrete visible mutation: a language flip or a slot
    rotation. Continuous content — clock, countdown, skip / breath / band-fill
    animations — is not a change; it renders every frame, untouched.

    Two knobs:

    1. **Per-axis cadence** — how many beats each axis wants between changes
       (language ``LANGUAGE_BEATS``; slots ``LowerDisplayBase._SLOT_BEATS``).
    2. **Change floor** (``CHANGE_FLOOR_BEATS``) — after any change, no change
       of any kind for one beat. At exactly one beat it doubles as the
       quantizer that keeps every change on the grid.

    CONTRACT: this must be ONE atomic tick per frame, NOT a shared
    ``last_change`` consulted independently by upper and lower. Both axes are
    evaluated against the same frame-start snapshot and applied together. A
    cadence-aligned slot (12s = 3 × 4s) comes due on the very frame the
    language is also due; if the language ticked first and stamped
    ``last_change``, the slot would then see delta 0 < floor, block, and
    **never rotate again**. Atomic evaluation + batching is what makes the
    floor safe. See DISPLAY.md § "Change scheduler".

    A due-but-blocked change is not queued: due-ness is recomputed from
    timestamps every frame and applies on the first frame the floor allows.
    Single-threaded render loop, so no race and no pending flag.
    """

    def __init__(self, mode_cycler: ModeCycler, lower):
        self.mode_cycler = mode_cycler
        self.lower = lower
        self.enabled = True
        # Seed at construction so an embedder that never calls seed() (the
        # tutorial's mini render loops) still behaves — otherwise timers sit at
        # 0.0 and the first tick instant-fires. run() re-anchors at boot_t.
        self.seed(time.time())

    def seed(self, current_time: float) -> None:
        """Anchor every timer at boot to real wall-clock.

        Without this the first main-loop frame computes a huge delta against a
        zero timer and instant-fires a change, so the boot view never persists
        through its natural duration.
        """
        self.last_change = current_time
        self.mode_cycler.seed(current_time)
        self.lower.seed(current_time)

    def tick(self, current_time: float, state) -> None:
        """Advance every axis at most once, atomically.

        Must run once per frame BEFORE any drawing, and after
        ``state.update_skip_progress`` — slot membership reads ``cursor_pos``.
        """
        if not self.enabled:
            return

        # Non-view machinery first: the through-service frame swap and the
        # restart transition. `reveal` is True on the frame the JR logo clears.
        reveal = self.lower.update(state, current_time)
        # Observed every frame so the position edge detector stays continuous,
        # even while the logo suppresses changes.
        at_station_edge = self.lower.observe(state)
        if self.lower.transition_active:
            # Static logo — nothing to tick under it. A slot mutating out of
            # sight would flash the instant the logo cleared.
            return

        snapshot = self.last_change

        # --- Preemptive: intent-driven, bypasses the floor, re-anchors it. ---
        forced = self.lower.preemptive_slot(state, at_station_edge)
        if reveal and forced is None:
            forced = self.lower.reveal_slot(state)
        preemptive = forced is not None or reveal

        # Go quiet just before the through-service swap fires. Its time is known
        # from the arm, so — unlike a driver-fired stop — the collision IS
        # foreseeable, and a rotation landing a frame before the JR logo covers
        # the screen reads as a flash.
        until_swap = self.lower.seconds_until_swap(current_time)
        floor = beats(CHANGE_FLOOR_BEATS)
        swap_imminent = until_swap is not None and until_swap <= floor

        # --- Scheduled: both axes read the SAME snapshot before either applies.
        allowed = preemptive or ((current_time - snapshot) >= floor and not swap_imminent)
        language_due = allowed and self.mode_cycler.is_due(current_time)
        slot = forced
        if slot is None and allowed:
            slot = self.lower.scheduled_slot(state, current_time)

        if slot is None and not language_due and not reveal:
            return

        # --- Apply as one batched event, then stamp the floor once. ---
        if language_due:
            self.mode_cycler.advance(current_time)
        if slot is not None:
            self.lower.apply_slot(slot, current_time)
        self.last_change = current_time

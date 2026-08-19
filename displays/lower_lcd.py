# SPDX-License-Identifier: MIT
"""Cross-model Lower LCD manager — slot cycling, transfer force-switch, and
the through-service frame swap.

Parent half of the parent + per-model-concrete split (see conventions.md
§ "Display module structure"). Everything here is model-agnostic
*coordination*: which slot is on screen, when it is allowed to change, and
which through-service frame the window renders. Per-model *rendering* —
renderer construction, ``_pick_renderer``, ``draw``, the restart screen —
stays in the concrete under ``displays/train_models/{model}/lower_lcd.py``.

The split exists so a new train model gets the scheduler contract by
construction. Before it, the slot cycler lived in the E235-1000 concrete and
E235-0 only inherited it by happening to fork that class; a model written
standalone would have satisfied none of the hooks ``ChangeScheduler`` calls.

CONTRACT: this class NEVER ticks itself. ``ChangeScheduler``
(``displays/base.py``) owns every discrete change — it calls ``observe`` /
``preemptive_slot`` / ``scheduled_slot`` / ``apply_slot`` exactly once per
frame, and the concrete's ``draw`` is a pure renderer that advances no timer.
Ticking a timer inside ``draw`` re-creates the two-independent-clocks bug the
scheduler exists to kill. See docs/DISPLAY.md § "Change scheduler".

CONTRACT: concrete subclasses MUST provide
  - ``self.transfer_display`` — a ``TransferInfoDisplay``; the base forwards
    ``set_state`` to it and reads ``_resolve_transfers`` off it.
  - ``LOCK_THRESHOLD`` — remaining-stops count at which the full-route slot
    drops out. Derive it from the model's eight/five-station renderer rather
    than re-typing the number (that constant is its canonical source).
  - ``_pick_renderer(mode)`` and ``draw(current_time)``.
"""

from typing import Optional

from displays.base import beats


class LowerDisplayBase:
    """Slot cycle + through-service frame state for a Lower LCD.

    Owns no rendering. Holds the view-cycle slot, the at-station force-switch
    edge detector, and the frame-swap / restart-transition machine.
    """

    # View-cycle slots (rotated in order, with per-slot dwells IN BEATS).
    # Default 2-slot cycle is full-route 3 beats / 8-station 3 beats.
    # When the train is in the transfer-info window (see _in_transfer_window
    # — derived from cnt_pa rather than state.is_last_pa for single-PA-stop
    # correctness), TRANSFER joins as a 3rd slot at 2 beats. The 8-station lock
    # (remaining stops ≤ LOCK_THRESHOLD) drops FULL from rotation, leaving
    # EIGHT alone outside the window and EIGHT↔TRANSFER inside it. TRANSFER is
    # also dropped when the current station has no transfers to render.
    #
    # Language coverage works differently per slot, and the difference matters
    # when retuning. FULL / EIGHT dwell 3 beats = exactly the 3-language cycle,
    # so each surfaces in EVERY language during a single appearance (the default
    # out-of-window round trip is 3+3 = 6 beats, an exact multiple of the cycle,
    # so their starting language never rotates — it does not need to). TRANSFER
    # at 2 beats cannot span the cycle; what covers it is the in-window round
    # trip of 3+3+2 = 8 beats, which is NOT a multiple of 3, so its starting
    # language rotates and all three pairings surface across successive cycles.
    _SLOT_FULL = 0
    _SLOT_EIGHT = 1
    _SLOT_TRANSFER = 2
    _SLOT_BEATS = {
        _SLOT_FULL: 3,
        _SLOT_EIGHT: 3,
        _SLOT_TRANSFER: 2,
    }

    # Remaining-stops threshold for the eight-station lock. Concretes MUST set
    # this (derived from their own renderer's canonical constant).
    LOCK_THRESHOLD: Optional[int] = None

    # Through-service restart screen: the JR-logo blank shown on swap.
    _TRANSITION_BEATS = 1
    # Beats the train sits STOPPED at the junction before the reboot fires.
    # Mental model: the hold must (a) signal the train is stopped at the frame
    # boundary and (b) show the junction's exchange (transfer) info. On the
    # STOPPING edge the force-switch moves to the TRANSFER slot, so the
    # transfer page shows immediately; the hold gives it comfortable read time
    # before the reboot. Fixed timer, deliberately decoupled from the
    # view-cycle — NOT "exhaust every page" (nobody needs FULL + EIGHT shown
    # before the swap), just long enough for the above (tuned by feel).
    _SWAP_HOLD_BEATS = 3

    def __init__(self, screen, route_data, stops, mode_cycler):
        if self.LOCK_THRESHOLD is None:
            raise TypeError(f"{type(self).__name__} must define LOCK_THRESHOLD (see LowerDisplayBase CONTRACT).")

        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.mode_cycler = mode_cycler
        self._state = None

        # View-cycle state. _slot_start = wall-clock when the current slot
        # began; None until the scheduler seeds it at boot.
        self._current_slot: int = self._SLOT_FULL
        self._slot_start: Optional[float] = None
        # _prev_at_station = last-frame at_station (None until first observed —
        # boot's at_station=True must NOT fire a rising-edge force-switch).
        self._prev_at_station: Optional[bool] = None
        self._prev_curr_stop: Optional[int] = None

        # Through-service frame swap state. The displayed frame lags position:
        # at a junction the train STOPS while still showing the old frame, the
        # page cycle rotates once (all pages shown), THEN the frame flips. Owned
        # here (not in the renderers) because the fire condition reads this
        # manager's own view-cycle. Single-frame / legacy routes: _frame_count
        # <= 1 → the whole machine is inert.
        self._frames = route_data.get("frames") or []
        self._frame_count = len(self._frames) if self._frames else 1
        self._pre_len = len(route_data.get("pre_stops", []))
        self._active_frame_idx = 0
        self._swap_armed = False
        self._swap_arm_time = 0.0
        # Restart transition — on swap fire, the lower LCD blanks to the JR logo
        # for _TRANSITION_BEATS before the new frame appears (the "restart"
        # while parked at the junction). A page-jump cancels it.
        self._transition_active = False
        self._transition_start = 0.0
        self._transition_curr_stop = -1  # position at fire; any change cancels

    # ------------------------------------------------------------------
    # State binding
    # ------------------------------------------------------------------

    def set_state(self, state) -> None:
        """Bind to an AppState instance. Subsequent draws read live state."""
        self._state = state
        # Forward to subordinate renderers that need state binding too.
        self.transfer_display.set_state(state)

    @property
    def transition_active(self) -> bool:
        """True while the JR-logo restart screen is up.

        The scheduler applies no discrete change while this holds — the screen
        is a static logo, so there is nothing to tick under it, and a slot
        mutating out of sight would flash the instant the logo clears.
        """
        return self._transition_active

    # ------------------------------------------------------------------
    # Slot membership
    # ------------------------------------------------------------------

    def _should_lock_to_eight(self, cursor_pos: int) -> bool:
        """Drop the full-route view once the VISUAL train position (cursor_pos,
        not the skipped-ahead curr_stop) leaves ≤ LOCK_THRESHOLD stops to
        the end. Keying on cursor_pos means a departure that skips passing
        stations keeps FULL in rotation until the train is visually near the
        tail — not the instant curr_stop jumps to the next PA target."""
        # CONTRACT: measures remaining to len(stops), NOT dest_stop_idx. On a
        # reference-tail route (Keihin 727B: dest 磯子 @40, data runs to @45, tail
        # all time:null) this locks ~6 stops "late" vs a terminus bound and trails
        # past-terminus reference stops in the window. Whether the view SHOULD
        # bound at the terminus is an OPEN FIDELITY question needing IRL reference
        # (Sōbu, in-spec, same shape — not yet collected; #103), NOT a bug: the
        # train-STOP terminus (dest_stop_idx, app.py) is a separate settled
        # concern. Don't re-flag as len-vs-terminus drift.
        return (len(self.stops) - cursor_pos) <= self.LOCK_THRESHOLD

    def _in_transfer_window(self, state) -> bool:
        """True when transfer-info should be in the cycle rotation.

        Window = APPROACHING_FINAL (cnt_pa is at the last index of pa[])
        through STOPPING. Derived directly from cnt_pa rather than reading
        ``state.is_last_pa`` because the flag is only set inside
        ``_next_in_approaching`` (multi-PA path) — single-PA stations
        auto-fire pa[0] via ``_advance_to_next_stop`` which hardcodes
        is_last_pa = False even though pa[0] is already the last (and only)
        PA. The derived check correctly fires for both cases.
        """
        if state.at_station:
            return True
        pa_tracks = self.stops[state.curr_stop].get("pa", [])
        if not pa_tracks:
            return False
        return state.cnt_pa >= len(pa_tracks) - 1

    def _station_has_transfers(self, state) -> bool:
        """True when the current station has at least one transfer to render
        after active-line filter + view-drop are applied.

        Cheap enough to call per-frame: dict lookup + two list comps inside
        TransferInfoDisplay._resolve_transfers. If this becomes a hot spot,
        cache against (curr_stop, transfer_view) — but don't pre-optimize.
        """
        if not (0 <= state.curr_stop < len(self.stops)):
            return False
        name = self.stops[state.curr_stop].get("name", "")
        return bool(self.transfer_display._resolve_transfers(name))

    def _available_slots(self, state) -> list:
        """Slots in rotation order for the current state.

        Combinations (× transfer-available toggle):
          - not in window, not locked  → [FULL, EIGHT]
          - not in window, locked      → [EIGHT]
          - in window,    not locked   → [FULL, EIGHT, TRANSFER]
          - in window,    locked       → [EIGHT, TRANSFER]

        TRANSFER is dropped from the list when the current station has no
        transfers (or filtering wipes them out) — the cycle simply rotates
        without a blank slot.
        """
        locked = self._should_lock_to_eight(state.cursor_pos)
        in_window = self._in_transfer_window(state) and self._station_has_transfers(state)
        if locked and in_window:
            return [self._SLOT_EIGHT, self._SLOT_TRANSFER]
        if locked:
            return [self._SLOT_EIGHT]
        if in_window:
            return [self._SLOT_FULL, self._SLOT_EIGHT, self._SLOT_TRANSFER]
        return [self._SLOT_FULL, self._SLOT_EIGHT]

    # ------------------------------------------------------------------
    # Scheduler interface — query, then apply. Never self-ticking.
    # ------------------------------------------------------------------

    def seed(self, now: float) -> None:
        """Anchor the slot timer at boot (real wall-clock, never 0.0).

        Without this the first scheduled evaluation computes a huge delta
        against an unset timer and instant-rotates, so the boot view never
        persists through its natural duration.
        """
        self._slot_start = now

    def observe(self, state) -> bool:
        """Record this frame's position and report the STOPPING rising edge.

        Called exactly once per frame by the scheduler, BEFORE the slot
        queries, because it both reads and stamps the previous-frame position.

        The edge fires on at_station False→True, and also on a cross-stop jump
        while at_station stayed True (arrow-key preview, click-jump, and the
        auto-driver's click_jump_pending) so each stop shows transfer info.
        Boot's initial at_station=True is captured as the first observation
        without firing, so the cycle starts on its default slot.
        """
        if self._prev_at_station is None:
            self._prev_at_station = state.at_station
            self._prev_curr_stop = state.curr_stop
            return False
        stop_changed = state.curr_stop != self._prev_curr_stop
        rising = state.at_station and (not self._prev_at_station or stop_changed)
        self._prev_at_station = state.at_station
        self._prev_curr_stop = state.curr_stop
        return rising

    def preemptive_slot(self, state, at_station_edge: bool) -> Optional[int]:
        """Slot that must be shown IMMEDIATELY, bypassing the change floor.

        Two sources:
        - **STOPPING edge** → TRANSFER. Intent-driven: the stop must show its
          transfer info at once, so this outranks the floor. It fires at every
          stop and re-anchors the floor off the language cadence — accepted.
        - **Content-invalid** → the current slot is TRANSFER but the station
          lost its transfers (departure / filter wipeout). Holding it would
          show a blank panel, so it is never deferred. Distinct from a
          *layout*-invalid slot (e.g. FULL after the eight-lock engages),
          whose last-rendered image is still coherent — that one goes through
          ``scheduled_slot`` and the floor may defer it a beat.

        Returns None when the wanted slot is already on screen: a no-op is not
        a change, so it must not re-anchor the floor (otherwise every stop
        silently shoves the language cadence out).
        """
        slots = self._available_slots(state)
        forced = None
        if self._current_slot == self._SLOT_TRANSFER and self._SLOT_TRANSFER not in slots:
            forced = slots[0]  # content-invalid
        if at_station_edge and self._SLOT_TRANSFER in slots:
            forced = self._SLOT_TRANSFER
        return forced if forced != self._current_slot else None

    def scheduled_slot(self, state, now: float) -> Optional[int]:
        """Slot the cadence wants next, or None. Deferrable by the floor.

        Covers the layout-invalid reconcile and the per-slot duration
        rotation. Both route through ``apply_slot``, which re-stamps
        ``_slot_start`` — so a reconcile can never be followed by an instant
        rotation (the stale-timer path that cut a slot sub-second before the
        scheduler existed).
        """
        slots = self._available_slots(state)
        if self._current_slot not in slots:
            return slots[0]  # layout-invalid reconcile
        if len(slots) == 1:
            return None  # single-slot cycle: nothing to advance to
        if self._slot_start is None:
            return None  # unseeded (preview freeze) — never rotate blind
        if now - self._slot_start >= beats(self._SLOT_BEATS[self._current_slot]):
            idx = slots.index(self._current_slot)
            return slots[(idx + 1) % len(slots)]
        return None

    def reveal_slot(self, state) -> int:
        """Slot to reveal when the restart logo clears — the new frame's default.

        Returned even when it is ALREADY the current slot, because applying it
        is what restarts the dwell. Slot timers are wall-clock, so the logo burns
        dwell while the view is invisible; without the restart the new segment's
        opening view expires after one floor instead of its full dwell. The
        reveal is the start of a new segment — it gets a full dwell, not the
        remainder of the pre-swap one.
        """
        return self._available_slots(state)[0]

    def seconds_until_swap(self, now: float) -> Optional[float]:
        """Seconds until the through-service frame swap fires, or None if unarmed.

        The fire is on a fixed timer from the arm, so unlike a driver-fired stop
        it is predictable well ahead — which lets the scheduler go quiet just
        before it instead of letting a rotation flash for one frame under the
        incoming JR logo.
        """
        if not self._swap_armed:
            return None
        return (self._swap_arm_time + beats(self._SWAP_HOLD_BEATS)) - now

    def apply_slot(self, slot: int, now: float) -> None:
        """Commit a slot change and restart its dwell timer.

        A genuine slot-enter (the committed slot differs from the current one)
        notifies ``_on_slot_entered`` so a renderer with a slot-enter animation
        (the E235-0 5-station band fill) can restart it. Fired HERE — the
        scheduler's single slot-commit funnel — never from ``draw`` (a pure
        renderer: a trigger self-detected there cannot tell a draw stall or a
        stopped→moving marker flip from a real re-enter). A same-slot re-anchor
        (``reveal_slot`` restarting the dwell) is NOT an enter.
        """
        entered = slot != self._current_slot
        self._current_slot = slot
        self._slot_start = now
        if entered:
            self._on_slot_entered(slot, now)

    def _on_slot_entered(self, slot: int, now: float) -> None:
        """Hook — a NEW slot just became current (not a same-slot re-anchor).

        Base no-op; a concrete whose renderer owns a slot-enter animation
        overrides it. See docs/DISPLAY_E235.md § "E235-0 — 5-station stopping view".
        """
        pass

    def update(self, state, now: float) -> bool:
        """Advance the through-service frame machine + restart transition.

        Called once per frame by the scheduler, before the slot queries.
        Returns True when the restart logo just cleared (or was cancelled by a
        position change) — the scheduler treats that as a Preemptive re-anchor
        so the revealed frame starts a full dwell rather than flashing.
        """
        self._update_active_frame(state, now)
        if not self._transition_active:
            return False
        # Any position change (page forward, jump) cancels it — it's a brief
        # at-junction screen.
        if state.curr_stop != self._transition_curr_stop:
            self._transition_active = False
            return True
        if now - self._transition_start >= beats(self._TRANSITION_BEATS):
            self._transition_active = False
            return True
        return False

    # ------------------------------------------------------------------
    # Through-service frame swap
    # ------------------------------------------------------------------

    def _natural_frame(self, sim_curr: int) -> int:
        """Frame whose global window contains the train (first match — a
        junction belongs to the EARLIER frame). The displayed frame tracks
        this except while a fired swap holds the next frame at the junction."""
        gi = sim_curr + self._pre_len
        for i, fr in enumerate(self._frames):
            if fr["from_idx"] <= gi <= fr["to_idx"]:
                return i
        return self._frame_count - 1

    # CONTRACT: drives the through-service frame swap. Arm at STOPPING@junction,
    # hold a fixed _SWAP_HOLD_BEATS, then flip the frame. The lag is required
    # — the LCD "restarts while stopping" per IRL. See docs/DISPLAY.md § Through-
    # Service Display Frames.
    def _update_active_frame(self, state, current_time: float) -> None:
        """Advance ``_active_frame_idx`` with the arm → wait → fire rule.

        - Aligned + STOPPING at the active frame's junction → arm, record the
          arm time.
        - _SWAP_HOLD_BEATS elapsed → fire: flip to the next frame. The frame
          now leads position (shows frame N+1 while the train is still parked
          at the boundary) — held until the train departs the junction.
        - Any other divergence (jump, backward, paged through fast) → snap to
          the natural frame and disarm.
        """
        if self._frame_count <= 1:
            return
        natural = self._natural_frame(state.curr_stop)
        a = self._active_frame_idx
        gi = state.curr_stop + self._pre_len

        # Valid "fired, holding ahead": showing frame a (= natural+1) while the
        # train is still parked at the boundary station of frame `natural`.
        holding_ahead = a == natural + 1 and gi == self._frames[natural]["to_idx"]
        if holding_ahead:
            return
        if natural != a:
            # jump / backward / fast-paged past the junction — resync, disarm.
            self._active_frame_idx = natural
            self._swap_armed = False
            return

        # Aligned (displaying the train's frame): manage arm/fire at its junction.
        has_next = a < self._frame_count - 1
        at_junction = has_next and state.at_station and gi == self._frames[a]["to_idx"]
        if not at_junction:
            self._swap_armed = False
            return
        if not self._swap_armed:
            self._swap_armed = True
            self._swap_arm_time = current_time
        elif current_time - self._swap_arm_time >= beats(self._SWAP_HOLD_BEATS):
            self._active_frame_idx = a + 1  # FIRE — flip the window
            self._swap_armed = False
            self._transition_active = True  # play the JR-logo restart screen
            self._transition_start = current_time
            self._transition_curr_stop = state.curr_stop

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def hit_test(self, mx: int, my: int) -> Optional[int]:
        """Dispatch a click in LCD-local coords to the active renderer's hit_test.

        Returns sim_index for clickable cells, None for non-clickable
        (pre_stops, padding, transfer-info — no clickable elements there).
        ENGLISH mode falls back to the Japanese full-route renderer's
        hit_test — clicks DO work in ENGLISH. Past-dest filter lives in
        the caller (`PASimulator._click_target`) since `dest_stop_idx` is
        on the simulator, not the renderer.
        """
        if self._state is None:
            return None
        mode = self.mode_cycler.get_current_mode()
        renderer = self._pick_renderer(mode)
        if hasattr(renderer, "hit_test"):
            return renderer.hit_test(self._state, mx, my)
        return None

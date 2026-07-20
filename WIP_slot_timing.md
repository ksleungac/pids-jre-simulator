# WIP — Lower-LCD slot / language timing model

**Status:** LOCKED 2026-07-20 — design + `/third-man` review complete; revised same day (single 4s floor split into cadence 4s / floor 2s; language-coverage invariant added). Implementation pending.

**Tracking:** [#78](https://github.com/ksleungac/pids-jre-simulator/issues/78).

---

## EDIT-CONTRACT

- **Holds:** the target timing model (the change-scheduler), the flash classes it must kill, pinned parameters, rejected alternatives, and open items.
- **Does NOT hold:** the investigation blow-by-blow, or anything already true of shipped code (that graduates to the canonical home).
- **Rejected alternatives stay** until graduation — the record of what was already considered.
- **Graduation trigger:** when the fix ships, dissolve into `DISPLAY_E235.md` § "View cycler (LowerDisplay)" (+ `DISPLAY.md` if a cross-model invariant lands); delete this doc. Single-commit restructure.

---

## The problem

The lower LCD runs two independent clocks — language (`STATION_DISPLAY_INTERVAL = 4s`, `constants.py:36`) and slot (FULL 12s / EIGHT 12s / TRANSFER 6s, `_SLOT_DURATIONS:1777`) — with **no coordination and no notion of "how long the current config has actually been on screen."** A flash is any two changes landing within a few frames, so there is **no single culprit line**. Two observed classes:

- **Class 1 — slot cut.** A slot (the e235_0 5-station) appears then vanishes sub-second (band still gray). A Reactive slot change (reconcile snap; stale-`_slot_start` instant-rotate after the `len==1` freeze) fires the instant the slot set changes.
- **Class 2 — cross-source staccato.** The upper's language flip, then the lower's slot rotation ~0.5s later. Confirmed.

---

## The model — a change scheduler

Ground everything on **change**. A change = any *discrete* visible mutation: a language flip **or** a slot rotation. (Continuous content — clock, countdown, skip / breath / band-fill animations — is **not** a change; it renders every frame, untouched.)

Two knobs, deliberately separate:

1. **Per-axis cadence** — *unchanged from today.* The normal interval each axis *wants* to change: language 4s; a slot after its duration (12/12/6s). Just the existing durations.
2. **Global floor = 2s** — *the one new mechanism.* After **any** change event, no change of any kind for 2s — the hard anti-staccato minimum.

**The floor (2s) sits *below* the language cadence (4s).** In normal running the cadence drives timing and the floor is invisible (4 > 2); the floor only bites to keep an *off-cadence* change — one forced by a Preemptive re-anchor — ≥2s from its neighbour. So after a stop the language cadence recovers within **2s** instead of dead-zoning a full 4s. (Splitting the old single 4s into *cadence 4s + floor 2s* is exactly what buys this.)

**Atomicity is still required.** A slot whose duration is a multiple of the language cadence (FULL/EIGHT = 12s = 3×4s) still comes due *exactly on* a language tick, so those two changes coincide and must be applied together atomically — the floor value does not change that (see the CRITICAL note below).

### Enforcement — one atomic tick per frame (NOT two consumers of a shared clock)

A single `change_controller.tick(timestamp, state)` runs **once per frame, before any drawing**. It:
- reads a **frame-start snapshot** of `last_change`;
- evaluates **both** axes against that same snapshot;
- applies all due-and-floor-allowed changes **atomically** (batched into one event);
- stamps `last_change` **once**.

This moves the language tick out of `upper.update` (today `upper_lcd.py:650`); `upper.draw` / `lower.draw` become pure renderers reading `current_mode` / `_current_slot`.

> **CRITICAL — do NOT implement as "one shared `last_change` consulted by both."** A cadence-aligned slot (12s) comes due on a language-tick frame; the language tick runs first (`app.py:382 upper.update` before `:386 lower.draw`), stamps `last_change`, and the slot then sees `now − last_change = 0 < floor`, blocks, and **never rotates**. Atomic frame-start evaluation + batching is what makes it work.

**Poll, not messages/queue.** A due-but-blocked change is **not** queued: due-ness is recomputed from timestamps every frame, and the change applies on the first frame the floor allows. No pending flag. Single-threaded render loop → no race, no queue.

**Boot.** Seed `last_change` and the per-axis timers to `boot_t` (real wall-clock) — mirrors the existing boot CONTRACT (`app.py:358`); otherwise the first main-loop frame computes a huge delta and instant-fires a change.

### Three change flavors (labels, not three code paths)

- **Scheduled** — a per-axis cadence elapsed.
- **Reactive** — the current slot went invalid (dropped from `_available_slots`). Two sub-cases, and they differ:
  - **Layout-invalid** (e.g. FULL after the 8-station lock engages) — the last-rendered image is still coherent → **deferred** by the floor, then corrects. Accepted.
  - **Content-invalid** (current slot is TRANSFER and the station *lost* its transfers — departure / filter wipeout) — holding it shows a **blank/stale panel** → treated as **immediate** (Preemptive-class), never held.
- **Preemptive** — intent-driven, immediate, re-anchors the floor (stamps `last_change = now`): transfer force-switch on stopping; user page / jump; content-invalid reconcile (above); **and the through-service restart transition** (below).

**Batching.** Same-frame-due changes apply together as one event.

### Through-service restart transition (the frame swap)

Existing mechanics unchanged — arm at STOPPING@junction, hold `_SWAP_HOLD_DURATION` (12s), fire (`_active_frame_idx += 1`, 5s JR-logo blank), then the new frame. Scheduler handling: **while the logo is up the controller applies no discrete changes** (the screen is a static logo — nothing to tick under it); **at logo-clear it fires one Preemptive re-anchor** — reveal the new frame on its default slot and stamp `last_change = now`. So the first slot of the new segment holds ≥ the floor and is deterministic. Without this, `_tick_cycle` mutating `_current_slot` under the logo lets a slot flash the instant the logo clears.

### Architecture

The controller owns `last_change` + the axis state — the single shared coordinator (extends today's shared `ModeCycler`). It must honor `enabled = False` (preview / calibration freeze, `preview_display.py`).

---

## Parameters (pinned)

- **Global floor = 2s.** The hard minimum gap between any two changes — the anti-staccato guarantee. Sits *below* the language cadence (4s), so normal rotation is never gated by it; it only spaces *off-cadence* (Preemptive-adjacent) changes. 2s is ≥ the 1.5s band-fill (a slot's intro always completes) and ≫ the ~0.5s flash threshold, so a 2s gap is a readable beat, not a flash.
- **Per-axis cadence = observed IRL values:** language 4s; FULL/EIGHT 12s; TRANSFER 6s. Free parameters — the model does **not** depend on 12 = 3×4, *except* the coverage invariant below, which is stated explicitly rather than assumed.
- **Reactive hold-stale = accepted for *layout-invalid* only** (a coherent view one beat behind). **Content-invalid is NOT held** (immediate).

---

## Language coverage — no buried pairing

A language-distinct slot must surface in **every** language, not get buried in one. This holds **by construction**: FULL and EIGHT dwell **12s = one full language cycle (3 × 4s)**, so any 12s window spans all three language phases regardless of slot/language phase alignment — every (slot, language) pairing appears. TRANSFER is language-agnostic (renders identically), so its 6s dwell is fine. e235_0 is exempt — its FULL/EIGHT render kanji-only.

**Invariant:** a language-distinct slot's dwell must be ≥ the language cycle (12s). This is the *one* place the model leans on 12 = 3×4 — stated explicitly, not assumed. Caveats: (a) a future language-distinct slot *shorter* than the cycle would need an explicit coverage mechanism, not this; (b) a slot cut short by a Preemptive near a stop temporarily shows fewer languages — self-heals on its next full appearance.

---

## What it covers

- **Class 1** — killed. Nothing shows for less than the floor (2s ≥ band-fill).
- **Class 2** — killed. The floor keeps the second change ≥2s from the first.
- **Preemptive residual** — the force-switch can still cut a slot short, *by design* (stopping must show transfer immediately).

## One consequence to accept

The **Preemptive force-switch fires at *every* stop** (STOPPING → TRANSFER) and re-anchors the floor off the language cadence. With **floor = 2s**, the interrupted language flip resumes within **2s** of the stop (not a full 4s) — the cadence snaps back fast. The trade: an off-cadence change (slot-vs-language near a stop) can sit **2s apart** instead of batching — a readable beat, not a staccato.

---

## Rejected / not-this

- **Per-language minimum-dwell floor (≥2–3s at a language).** No-op — language already guarantees ≥4s by cadence.
- **Single 4s floor (== cadence).** Superseded by the cadence/floor split: a 4s floor forced every stop to dead-zone the language a full 4s; 2s halves that and still kills the (sub-0.5s) staccato.
- **Message / event queue / async scheduler.** Unnecessary — single-threaded atomic per-frame poll, no race.
- **Fixed *absolute* 4s grid (changes quantized to 0, 4, 8…).** Superseded by the rolling floor, whose real advantage is that **Preemptive re-anchors the grid to each stop** (a stop's TRANSFER gets its full dwell instead of being clipped by an absolute grid).
- **"Reactive targets the intended slot" refinement — CUT.** Under the floor the 5-station holds ≥ the floor (a legitimate approach view, not a flash), and STOPPING → transfer is already the Preemptive edge's job.
- **Explicit per-language coverage scheduler.** Not needed while every language-distinct slot's dwell ≥ the language cycle (see invariant) — the coverage falls out for free.
- **Chasing the exact Class-1 trigger with a transition log before fixing.** Deferred — the model fixes Class 1 by construction.

---

## Next steps

- [x] Design locked + `/third-man` review + floor/coverage revision (2026-07-20).
- [x] Tracking issue filed ([#78](https://github.com/ksleungac/pids-jre-simulator/issues/78)).
- [ ] Implement — the one-tick controller. Main structural work: move the language tick out of `upper.update` into the shared controller; make `upper`/`lower` pure renderers. Then a regression test on the starvation trap (a cadence-aligned 12s slot must still rotate) + the boot-init seed.

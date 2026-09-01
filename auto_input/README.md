# Auto-Input — OCR-driven PA firing from JR EAST Train Sim HUD

Companion module that automates PA-firing in the simulator by reading JR EAST Train Simulator game's HUD via screen capture. Removes need to press PageDown manually during normal driving.

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** schema reference, gotchas, invariants — implementation specifics looked up when editing the relevant submodule.
>
> **Refuses:**
> - History notes / change logs (`### 2026-03-14`, "pre-X behavior", "Key Changes from legacy …") — `git log` has this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future sections ("When X is implemented, …") — defer until needed
> - Design-discussion rationale (multi-paragraph framings of *why* a model exists) — the rule lives here; the rationale lives in `memory/YYYY-MM-DD.md`
> - Facts already in [CLAUDE.md](../CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Voice:** new reference-shaped entries (schema, OCR pipeline rules, event tables, layer specs, contracts) stay compressed — tables, `=` for definitional equivalence, no narrative padding. Rationale-shaped passages ("Mental model" framings, "Why not X" framings, narrative examples) run as ordinary prose. Both in complete sentences where they use prose at all, per [CLAUDE.md § Writing tone](../CLAUDE.md).
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](../.claude/rules/principles.md).

## Mental model

The auto-driver is an **input layer** — it observes game state via OCR on the game window, detects state transitions, and emits PA-fire events. The simulator's existing state machine (`AppState`, `_next_pa`, `state.curr_stop`) is the source of truth for *what* PA to play; the auto-driver only decides *when* to advance the queue.

This split keeps fidelity work (LCD rendering, route data, audio cuts) decoupled from input automation. The auto-driver can be disabled and the simulator behaves exactly as today, with manual PageDown control.

**Two integrations.** Both live in this repo and share OCR + state-machine implementation:

- **In-process** (`auto_input/driver.py` `AutoDriver`) — spawned from `main.py` when **OCR Auto-PA** toggle enabled on setup screen. Runs in daemon thread, sets `PASimulator.pending_next_pa = True` at fire-time, same code path as manual PageDown. Manual-press precedence implicit: the driver gates each fire on the app's sub-state (departure only when parked, etc.), so a manual PageDown that already advanced the app makes the driver skip its own fire. Includes in-window debug panel.
- **Observation-only** (`_dev_scripts/ocr_observe.py`) — standalone OCR corpus collector. Calls `sampling.read_hud` (THE production read path) and records what it saw: full-HUD PNGs, `reads.jsonl` with RAW beside GUARDED values, decimal speed + guard marks on the console. Fires nothing, touches no simulator state. It owns NO read logic by design — a diagnostic that re-derives any of the pipeline yields evidence about itself, not production. (Superseded `capture_game.py`, whose forked copy of the read path had drifted; that fork's synthetic-PageDown driving is gone with it — the in-process integration is the only firing path now.)

## Game-side ground truths (author-stated 2026-08-18)

Facts about JR EAST Train Sim itself, not about this code. None is derivable by reading the repo, and a detector, search or review that walks the state space freely spends itself on cases the game never produces. Two more live at their point of use: the four possible badge transitions (§ "Badge classification") and the direction of a distance re-point (§ "Distance plausibility guard").

| Fact | Consequence for the driver |
|---|---|
| A run **always starts parked at a platform** | Boot state is deterministic — `badge==STOPPED`, speed 0. Not "varies by scenario". |
| The speed cell **always renders one decimal** | A decimal-less speed read is ALWAYS a misread, never a real frame (`critical_lessons §7`). |
| The pause menu can **jump the train to any station**, earlier or later | This is what click-to-jump and re-entry exist for. Distance re-points by any amount in EITHER direction, and the badge changes with no physical motion. |
| **ESC dims the whole frame** behind the menu, OCR region included | Reads sometimes survive the dark mask. Unlike a black screen this persists for minutes at reduced contrast. |
| The HUD is **user-toggleable, whole or per-row** | OCR then reads nothing. Expected, understood by the user, not a defect — see § Limitations. |
| Yamanote has **TASC** (user-toggled, as IRL) | The game brakes to the stop mark itself, so stopping offsets there cluster near 0 by machine, not by driving skill. |
| Reverse is possible but **ATS cuts it off** | Bounded to a crawl; not a state worth designing for. |

The screen goes black on exactly four events: platform fast-forward · overrun reset · run start and end · a pause-menu station jump. Never mid-transit under power.

## State machine layering

Auto-driver subsystem involves three distinct state machines. They align in normal flow but diverge after manual user action — keeping them separate in vocabulary prevents wrong fix landing in wrong layer.

**Shorthand codes** — a quick-reference for discussion; the full state names below stay the canonical vocabulary in code + prose.

| Layer 1 — app sub-state | Layer 2 — driver belief | Layer 3 — inferred game |
|---|---|---|
| **1A** = `APPROACHING_EARLY` (次は) | **2A** = fresh segment, no fire | **3A** = `IDLE` |
| **1B** = `APPROACHING_FINAL` (まもなく) | **2B** = departed | **3B** = `DEPARTING` |
| **1C** = `STOPPING` (ただいま) | **2C** = arriving | **3C** = `CRUISING` |
| | **2D** = at-station | **3D** = `ARRIVING` |
| | | **3E** = `STOPPED` |

The Layer 1 ↔ Layer 2 coupling (1A⇒2B, 1B⇒2C, 1C⇒2A, so Layer 2 is derived from Layer 1) is implemented in `driver.py`. Fire-gating reads the app sub-state directly — departure only at 1C, arrival only at 1A, at-station at 1A/1B, meaning any in-transit state — and the segment label derives from `curr_stop` each cycle. The observed-flags below stay OCR-driven for Layer 3. The separate Layer-1↔Layer-3 catch-up is handled by re-entry; see "Re-entry (Layer 3 → Layer 2 reconciliation)" below. Design-discussion rationale: `memory/2026-05-30.md` (coupling) and `memory/2026-05-31.md` (re-entry).

### Layer 1 — App (sim's own state machine)

State on `AppState` (`curr_stop`, `cnt_pa`, `cnt_pa_at_station`, `at_station`). Exists whether auto-driver enabled or not. Three press-driven sub-states per stop: `APPROACHING_EARLY` → `APPROACHING_FINAL` → `STOPPING`. Spec in [docs/DISPLAY.md § Unified State Machine](../docs/DISPLAY.md); mental-model summary in [CLAUDE.md § App state machine](../CLAUDE.md). Auto-driver triggers transitions by setting `pending_next_pa=True`, same code path as manual PageDown.

### Layer 2 — AutoDriver belief

Auto-driver's belief about where the train is in its segment — **derived from Layer 1, not stored.** Fire-gating reads the app sub-state directly (departure only at 1C, arrival only at 1A, at-station at 1A/1B), so the app advance is the debounce. `_segment_start_stop` is a display/log label recomputed from `curr_stop` each cycle (`_segment_from`).

The `_Detector`'s `departure_observed` / `arrival_observed` / `at_station_observed` flags still live on this instance but now serve **Layer 3**, feeding `inferred_state()`. They are OCR-driven and reset on `STOPPED->(MOVING|PASSING)`, NOT reconciled from Layer 1 — except seeded directly on re-entry (see "Re-entry" below).

### Layer 3 — AutoDriver's inferred game state

What auto-driver thinks IRL game train is doing — expressed as one of five canonical named states + sentinel:

| Canonical name | Panel label | Game-side meaning |
|---|---|---|
| `IDLE` | Idle | At platform, no in-segment arrival was observed (boot, post-click, or arrival trigger missed by OCR). |
| `DEPARTING` | Departing | In-transit, dep-trigger not observed this segment. Usually rolling out, but ALSO a cold boot mid-cruise (no speed implication — the flag is what's unset, not the speed). |
| `CRUISING` | Cruising | In-transit at full speed, dep-trigger observed, arr-trigger not yet observed. |
| `ARRIVING` | Arriving | In-transit, dist crossed below arrival lead (~900m), decelerating to platform. |
| `STOPPED` | Stopped | At platform, arr-trigger observed in this segment. |
| `UNKNOWN` | — | OCR FAIL or insufficient context. Sentinel. |

**2026-05-09 rename.** Old wire names embedded the detector's trigger-fire shape (`STOPPING_FRESH`, `APPROACHING_BEFORE_DEP`, `APPROACHING_AFTER_DEP`, `MOVING_AFTER_ARR`, `STOPPING_AFTER_ARR`) which leaked internal logic into the state name. New names describe what the train is *doing* in plain transit verbs and line up 1:1 with the user-facing panel labels.

**Cross-layer token sharing.** Layer 1's vocabulary (`STOPPING` / `APPROACHING_EARLY` / `APPROACHING_FINAL`) is now disjoint from Layer 3 — old suffix discipline isn't needed there. **The badge read ↔ Layer 3 share one token by design:** `STOPPED` is both a **badge read** (raw OCR input — *not* Layer 2; Layer 2 is the belief flag-set) and a Layer 3 inferred-state value (output). `MOVING` and `PASSING` are badge reads only; `IDLE` / `DEPARTING` / `CRUISING` / `ARRIVING` / `UNKNOWN` appear only in Layer 3. The collision on `STOPPED` is intentional — the badge read is one input to the inference, and at the platform with `arrival_observed=True` they collapse to the same semantic. **In code and discussion, always disambiguate by field name** (`status['badge']` vs `status['inferred_state']`) rather than by raw string match. The panel disambiguates visually too: badges render in UPPERCASE, Layer 3 states in Title Case ("Stopped").

These = **inference outputs**, not direct OCR reads. Inputs:

- **Raw OCR observations**: `badge_read ∈ {STOPPED, MOVING, PASSING}`, `speed_read`, `distance_read` — single-sample reads of game HUD.
- **Layer 2 cache** (per-segment): `departure_observed`, `arrival_observed`, `at_station_observed`. Necessary because OCR alone doesn't distinguish `DEPARTING` from `CRUISING` — both show `badge∈{MOVING,PASSING}`; cache disambiguates. Flags semantically record "we observed the trigger condition this segment," not "we dispatched a fire" — fire gating reads Layer 1's app sub-state, a separate concern.

**Streaming inference truth table** (per-sample, with cache):

| `badge` | `arrival_observed` | `departure_observed` | → state |
|---|---|---|---|
| `STOPPED` | False | * | `IDLE` |
| `STOPPED` | True | * | `STOPPED` |
| `MOVING` or `PASSING` | True | * | `ARRIVING` |
| `MOVING` or `PASSING` | False | True | `CRUISING` |
| `MOVING` or `PASSING` | False | False | `DEPARTING` |
| `None` | * | * | `UNKNOWN` |

(`at_station_observed` doesn't appear — gates dispatch of FIRE_AT_STATION, not inferred state.)

**Entry-point inference** (no Layer 2 cache; toggle-ON, click reanchor): substitute `distance ≤ lead` for `arrival_observed`. `IDLE` ≡ `STOPPED` (collapsed at entry — functionally identical anchoring). `DEPARTING` lumped into `CRUISING` (brief acceleration window functionally equivalent at entry).

Inference function pluggable; future cross-attribute hardening enriches it without changing named-state vocabulary.

**Vocabulary discipline.** In design conversations and code comments:

1. **Use Layer 1 / 2 / 3 named states verbatim** — say *"AutoDriver thinks the game is in `IDLE`"*, not *"badge is STOPPED"* or any invented parallel vocabulary. Badge = one input to the inference; inferred state = what design reasons about. Vocabulary separation lets us harden inference without re-litigating design conclusions.
2. **Use arrow-flow notation for state progressions** — write `STOPPING(queue) → STOPPING(queue exhausted) → APPROACHING_EARLY`, not multi-column table. Tables fit orthogonal cross-products (Layer 3 × Layer 1 alignment table); progressions = sequence, read as arrows. Tables on transitions read as over-engineered.
3. **Don't redesign the state machine** — named states already implemented in `_Detector.update`. Design how flows interact with them, not what they should be.
4. **Discuss Layer 1 transitions against the canonical transition graph** — § "Layer 1 transition graph" below is the agreed discussion medium (2026-07-24): every proposed behavior change is located on that graph (which arrow, which guard) before code is discussed.

### Layer interaction

Normal flow:

```
Layer 3 observation → event → fire gate (Layer 1 sub-state) → pending_next_pa
                                                                  ↓
                                                       Layer 1 advance via _next_pa
                                                                  ↓
                                              Layer 2 (re-)derived from Layer 1 next cycle
```

Layer 3 (game observation) proposes a fire; the gate checks Layer 1's sub-state (departure only at 1C, arrival only at 1A, at-station at 1A/1B) and, if valid, advances Layer 1. **Layer 2 is derived from Layer 1, so it always follows Layer 1 and never drifts** — a manual PageDown that already advanced Layer 1 simply makes the gate skip the driver's own fire on the next cycle. The OCR observed-flags reset on the next `STOPPED->(MOVING|PASSING)`, for Layer 3 only.

### When layers diverge

| Cause | Effect | Reconciled by |
|---|---|---|
| Manual PageDown / auto-fire | Layer 1 advances | **Nothing to reconcile** — Layer 2 is derived from Layer 1 each cycle. Fire-gating reads the app sub-state, so a manual advance into 1A makes the driver skip its own departure; the segment label tracks `curr_stop` next cycle. |
| Click-jump on lower LCD | Layer 1 jumps to STOPPING@target | Segment label + fire-gating derive from `curr_stop` automatically. `_reanchor_to_app` additionally invalidates OCR memory (`prev_badge=None` + the three observed-flags — a cosmetic Layer-3 reset to `UNKNOWN` — and `motion_origin_known=False`, re-arming re-entry: post-jump motion is motion of unknown origin) so a stale badge read can't fire post-jump; signalled by single-shot `PASimulator.click_jump_pending`. It also nulls `prev_speed`, which since #82 protects nothing — the departure level test reads only the current speed (open risk, [#85](https://github.com/ksleungac/pids-jre-simulator/issues/85)). Parked case; mid-transit click-jump (game driving) is a Layer-1↔Layer-3 desync — see entry-point flow. |
| Toggle-ON mid-drive, mid-transit click-jump, or Layer 1 static while the game moved on | Layer 1 lags the game; the coupling has no Layer-1 change to ride | **Re-entry** — `_maybe_reentry` silent-advances Layer 1 up to the game AND seeds the observed-flags (one consistent snapshot). See "Re-entry (Layer 3 → Layer 2 reconciliation)" below. |

Layer 3 stays accurate at all times — observes the game, not the sim. Layer 1 ↔ Layer 2 reconciliation is automatic (Layer 2 derived from Layer 1); Layer 1 ↔ Layer 3 reconciliation is handled by re-entry (`_maybe_reentry`) — see below.

### Re-entry (Layer 3 → Layer 2 reconciliation)

`AutoDriver._maybe_reentry` (runs after the event loop each cycle) catches Layer 1 up when belief lags the game — cold boot mid-drive, mid-transit click-jump, missed OCR. Pulls Layer 1 + Layer 2 up to the game as **one consistent snapshot**: silent-advances the app sub-state AND seeds the observed-flags together.

**Base arming condition — motion provenance (2026-07-23/24).** Re-entry handles only **motion of UNKNOWN origin**. A witnessed `STOPPED→(MOVING|PASSING)` edge (a valid, cross-reject-passed badge read) sets `_Detector.motion_origin_known` — that motion is a normal departure the audible primary owns, and the resolver returns no target for the whole segment, whatever the speed/distance reads say. This is validated BEFORE any target resolution; the conditions below are secondary. The discriminator is history, not instantaneous reads: on a segment shorter than the arrival lead (the Yamanote norm; 武蔵溝ノ口→津田山 703m on Nambu, the incident) the 1B condition is true from the FIRST moving frame of a perfectly normal departure — only provenance separates that from a genuine mid-transit join. Unknown origin means: cold boot mid-transit (first-ever badge read is `MOVING`), or history invalidated by a click-jump (`_reanchor_to_app` sets `prev_badge=None` + clears the flag — deliberately NOT a synthetic `"STOPPED"`, which would fabricate a witnessed edge on the first post-jump `MOVING` read). Cleared on `MOVING->STOPPED`: each segment's motion must witness its own edge, so a dropout that eats the edge itself leaves re-entry legitimately armed.

Gated on **app parked** (`at_station=True` ⇔ 1C) — when the app is already moving (1A/1B) normal flow owns it. Also stands down when `pending_next_pa` is already set: a live fire succeeded this cycle (it plays with audio), so re-entry would be a silent dup. That gate is the discriminator between the live 3B→3C departure (audio) and a re-entry 3C (silent) — the arriving-while-parked case is NOT suppressed, because there `_fire_arrival` skips and `pending_next_pa` stays False.

Each cycle `_resolve_reentry_target` resolves a re-entry **target** (a pure read — no mutation), keyed on Layer 3 — all rows conditional on motion origin UNKNOWN per the base condition above:

| Layer 3 (game) | Target |
|---|---|
| any, motion origin KNOWN (witnessed edge) | none — normal departure; the audible primary owns the segment |
| 3A/3E parked, `speed < DEPARTURE_STALE_KMH`, or speed unknown | none — normal flow owns it. In `[30, 60)` the AUDIBLE `FIRE_DEPARTURE` level test already played it |
| 3C CRUISING (`speed ≥ DEPARTURE_STALE_KMH`, badge `MOVING` or `PASSING`) | 1A; commit seeds `departure_observed=True` |
| 3D ARRIVING (`badge==MOVING` AND `dist≤lead`) AND landing stop has **pa≥2** | 1B; commit seeds `departure_observed=arrival_observed=True` |

**pa=1 segments have no 1B target.** `cnt_pa = len(pa)-1 = 0` collapses 1A ≡ 1B into one AppState, and the single announcement must never be skipped by a silent landing. So on a pa=1 landing stop (`_next_stopping_pa_count`, mirroring `_advance_to_next_stop`'s landing rule) the 1B row declines and falls through to the 1A speed test. STOPPING is then reached by the at-station transition edge itself: STOPPED badge → `FIRE_AT_STATION`, unconditional per the reachability rule.

**Two-probe consensus.** A target commits only after **two consecutive cycles resolve to the same target** — the `_Detector.reentry_latch` holds the prior cycle's target; a matching read commits, any *different* target (incl. 1A→1B mid-wait) or a no-op re-bases the latch. Rationale: re-entry is forward-only and irreversible (it never retreats Layer 1), so a lone transient misread while parked would stick the LCD +1 ahead of reality until the user click-jumps back. The genuine cases (cold boot, click-jump) pay one sample interval of latency — cheap, and the wait is shown as the amber **"Re-aligning…"** panel indicator (`reentry_pending` in the status dict) instead of an abrupt snap.

Silent **because the announcement is stale** — conditional, not absolute. 1B commit = inside the approach window (まもなく already partway); 1A commit = at or above `DEPARTURE_STALE_KMH` (dep PA unrecoverable mid-segment). Below that bound the normal level test already fired the departure WITH audio, so re-entry never resolves a target there. **Exception: a pa=1 landing stop's 1A commit is AUDIBLE** — the single announcement is never stale ("pa=1 always play it"), so the commit routes through `_fire_departure`'s press (pa[0] plays, pa_at_station backlog drains) instead of `pending_silent_advance`.

**Primary/fallback strictness must not invert.** Re-entry is silent AND forward-only-irreversible, so it must never be *easier* to satisfy than the audible path it replaces — else its domain becomes residual ("whatever the primary dropped") instead of principled. Two partitions enforce it, one per axis:

- `DEPARTURE_STALE_KMH` partitions the **speed** axis: `[30, 60)` audible primary, `[60, ∞)` silent fallback (#82).
- `motion_origin_known` partitions the **provenance** axis: a witnessed edge means the primary owns the whole segment, an unknown origin means re-entry. The 2026-07-23 incident showed the speed partition alone left the 1B path satisfiable during a normal short-segment departure.

A commit emits a `reentry_1a` / `reentry_1b` drive-log event; `reentry_pending` (the latch) rides on every sample line and drives the panel's amber "Re-aligning…" chip.

Mechanism: single-shot `PASimulator.pending_silent_advance` (`"1A"|"1B"`) written by the OCR thread, consumed on the **main thread** via `_silent_advance_to` → `_advance_to_next_stop(silent=True)`. AppState is mutated only on the main thread — the bg thread writes only the signal + the detector flags (multi-field AppState writes from the bg thread would tear against the render loop).

**No feedback loop:** the Layer 1 ↔ Layer 2 coupling is read-only on Layer 1 (reads it for the segment label + fire-gate; never writes the observed-flags). Re-entry writes Layer 1 + flags as one snapshot; next cycle the coupling just re-reads (idempotent) and the seeded flags gate any re-fire.

**Lockstep ±1:** advances one stop. No station-name OCR, so a cold boot multiple stops behind the game is NOT recoverable here — click-jump to the platform first.

### Layer 1 transition graph (canonical)

The agreed discussion medium (2026-07-24): design conversations about driver behavior locate every change on this graph — which arrow, which guard — in the vocabulary above. Update it in the same change as any transition-behavior edit.

```
 ┌────────┐ ──(a)──────────────► ┌────────┐ ──(b)──────────────► ┌────────┐ ──(c)──────────────► ┌─────────┐
 │ 1C @N  │                      │   1A   │                      │   1B   │                      │ 1C @N+1 │
 │ parked │                      │  次は  │                      │ まもなく │                      │ parked  │
 └──┬──┬──┘                      └──┬──▲──┘                      └───▲────┘                      └───▲─────┘
    │  │                            │  │                             │                               │
    │  │         (d) silent 1A      │  │                             │                               │
    │  ├────────────────────────────┼──┘                             │                               │
    │  │         (e) silent 1B      │                                │                               │
    │  └────────────────────────────┼────────────────────────────────┘                               │
    │                               │                                                                │
    │                               │    (f) at-station directly from 1A                             │
    │                               └────────────────────────────────────────────────────────────────┘
    │
   (g) click-jump: user, from ANY state ────► 1C @ clicked stop
```

- **(a) `FIRE_DEPARTURE`** — audible PA · `spd ≥ 30` while parked · or manual PgDn. Upper bound `60` applies to unknown-origin motion only; on a **witnessed** edge (`motion_origin_known`) the ceiling lifts (fresh departure fires at any speed — catches a dwell whose whole `[30,60)` band was lost to an OCR dropout).
- **(b) `FIRE_ARRIVAL`** — audible PA · `MOVING ∧ dist ≤ lead` · or manual PgDn.
- **(c) `FIRE_AT_STATION`** — silent press · STOPPED badge · **ALWAYS** (reachability rule).
- **(d) RE-ENTRY → 1A** — motion origin UNKNOWN ∧ `spd ≥ 60` · 2-probe consensus. Silent for pa≥2 (announcement stale); **AUDIBLE for pa=1** — the single announcement is never stale, the commit presses like a departure fire and pa[0] plays.
- **(e) RE-ENTRY → 1B** — silent · motion origin UNKNOWN ∧ `MOVING ∧ dist ≤ lead` ∧ landing stop **pa≥2** · 2-probe consensus. The only arrow that skips 1A; pa=1 has no 1B (1A≡1B collapse) so (e) declines and (f) carries the arrival.
- **(f) same `FIRE_AT_STATION` from 1A** — STOPPED badge, **ALWAYS**; a missed arrival's `cnt_pa` is silently drained so the press lands as STOPPING. For pa=1, 1A≡1B and this IS the normal path.
- **(g) click-jump** — lands `1C @ target`; invalidates badge history (`prev_badge=None`, origin unknown) → re-entry (d)/(e) re-armed.

Arming rule over (d)/(e): a witnessed `STOPPED→(MOVING|PASSING)` edge while parked (cross-reject passed) sets `motion_origin_known` — (d) and (e) vanish for that segment; the `MOVING->STOPPED` arrival clears it, so each segment's motion must witness its own edge. Driver start mid-transit and post-(g) history are the unknown-origin cases.

From→to matrix (every reachable Layer 1 pair):

| from \ to | **1A** | **1B** | **1C** |
|---|---|---|---|
| **1C** | audible `FIRE_DEPARTURE` · manual PgDn · re-entry silent (origin unknown ∧ spd≥60) | re-entry silent ONLY (origin unknown ∧ MOVING ∧ dist≤lead ∧ landing pa≥2) — the primary never lands 1B from parked (`_fire_arrival` skips at 1C); pa=1 has no 1B at all (1A≡1B collapse) | click-jump |
| **1A** | — | audible `FIRE_ARRIVAL` · manual PgDn | at-station on STOPPED badge, **always** (reachability rule; missed-arrival `cnt_pa` silently drained) · click-jump |
| **1B** | — | — | at-station on STOPPED badge, **always** · click-jump |

Properties, by construction:

- A normal stopping pattern can never activate re-entry: the witnessed edge disarms both silent arcs.
- Re-entry achieves only 1A/1B, never 1C, and never backward — click-jump is the only backward move.
- Every state provably reaches the next stage: 1C exits via the departure band, 1A/1B exit via the STOPPED badge.

## Architecture

```
[JR EAST Train Sim window — DirectX]
              │
              │ DXGI Output Duplication (dxcam) with region=profile.capture_region
              ▼
[Primary-monitor quadrant BGRA  (1280×720 @ 1440p  |  960×540 @ 1080p)]
              │
              │ profile.hud_bbox_in_capture crop (region-relative coords)
              ▼
[HUD region  (350×480 @ 1440p  |  262×360 @ 1080p)]
              │
              │ sampling.downscale_hud — area/box resize into the ONE model
              ▼
[HUD @ 262×360, whatever the desktop was]     ← every cell bbox below is the model's
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
  [Distance][Speed][Badge]
   cell      cell  cell
       │      │      │
   OCR digits OCR  pixel-diff
   + 'm' filter +  vs anchors
                decimal-stop
       │      │      │
       ▼      ▼      ▼
   int m   int km/h  "MOVING" | "STOPPED" | "PASSING"
       │      │      │
       └──────┼──────┘
              ▼
     [PaEventDetector]
              │
              ▼
   ┌──────────────────────────────────┐
   │ Events:                          │
   │   STOPPED->MOVING                │
   │   FIRE_DEPARTURE                 │
   │   FIRE_ARRIVAL                   │
   │   MOVING->STOPPED                │
   │   FIRE_AT_STATION                │
   └──────────────────────────────────┘
              │
              ▼ for each `FIRE_*` event:
   [AutoDriver._handle_event — inspects sim.state directly]
   app not in this fire's valid sub-state?    → skip (e.g. not parked for departure / manual advance)
   target stop has only 1 PA?                 → skip (no arrival announcement)
   sim.state.cnt_pa already at last PA?       → skip (user fired manually)
   otherwise                                  → sim.pending_next_pa = True
   departure with pa_at_station still queued? → sim.pending_pa_drain  = True
              │
              ▼ (next pygame frame on main thread)
   [PASimulator._handle_input_main — pending_next_pa OR keyboard.is_pressed]
              │
              ▼
   PASimulator._drain_pa_at_station()  (only if requested — marks the queue
              │                         exhausted so the press below DEPARTS
              │                         rather than playing another entry)
              ▼
   PASimulator._next_pa() → state.curr_stop / state.cnt_pa advance
```

Both signals are bare flags, and that is the invariant rather than a detail: the
OCR thread writes only signals and its own detector flags, never `AppState`. The
drain used to be an `AppState` read-modify-write done here on the OCR thread — the
one such write in `driver.py` — which raced the main thread's own increment of the
same counter and could silently undo itself (#3, fixed 2026-08-30). Both are also
re-checked against `at_station` where they are consumed, because a flag written on
one thread and read on another can describe a platform the app has since left.

## Resolution handling

**One model at 1080p; every larger capture is downscaled into it.** A per-resolution model costs a full calibration round — capture screenshots, hand-author a `ResolutionProfile`, re-extract templates — which does not scale past the two resolutions that already exist. Shrinking the input instead means a new desktop resolution needs neither.

Per cycle: grab the capture region at the desktop's own resolution → `sampling.downscale_hud` cuts the HUD out and resizes it to 262×360 → the readers run against `DOWNSCALE_PROFILE`. A 1080p capture is already that size and comes back as a plain copy. Cost is 5.6 ms per 1440p HUD, ~0 at 1080p.

**Capture profile and read profile are separate variables** (`profile` vs `read_profile` in `AutoDriver._run`). `profile` says what to grab and where the HUD sits inside it; `read_profile` says which cell bboxes, thresholds and templates read it. Collapsing them is how a cell gets cropped at one geometry and thresholded at another.

**Resampler = area/box average** (`sampling._resize_area`), a separable filter computed from a cumulative sum, so cost is one pass regardless of the downscale factor. Correct at any ratio: an output pixel is the mean of exactly the input pixels it covers, so nothing aliases however far the image shrinks. ~10 ms per 1440p HUD, ~15 ms at 4K.

Three things learned choosing it, all measured rather than reasoned:

- **`rint` before the uint8 cast, never a bare `astype`.** The cast truncates, biasing every resampled pixel down by up to 1 LSB — a uniform field of 137 came back as 136. One level of systematic darkening is exactly the margin the binarization threshold works in ([critical_lessons.md §7](../.claude/rules/critical_lessons.md)).
- **Sharper is not better here, and neither is more faithful.** Cubic scored WORST of everything tried — its edge ringing creates halos the Otsu threshold misreads. The failure mode for this pipeline is a thin stroke falling below the threshold, not aliasing.
- **Don't tune the resampler on synthetic blur.** An area+unsharp variant beat everything on a gaussian-blur sweep (193 vs 178 across a broad parameter plateau) and then destroyed the decimal digit on **145 of 792 real driven frames**. Gaussian blur is a uniform low-pass that re-sharpening recovers from; real capture degradation is not, and the unsharp overshoot disturbs the 3–4 pixel decimal dot. Validate on real frames — see [principles.md § "Validate against the outcome, not a proxy"](../.claude/rules/principles.md).

**What the resize costs, measured.** A downscaled 1440p HUD has edge acutance 0.351, against 0.361 for a reporter's real degraded 1080p capture and 0.529 for a crisp dev one. The resize spends about one real-world degradation budget up front, and still reads 26/26 on the 1440p calibration set, because the §7-era hardening was built for exactly that softness.

Under added blur both paths hold identically to σ=1.0. From σ=1.5 the downscaled one loses two more reads, and **the whole gap is the tenths digit** — log/report only, degrading to `None` rather than to a wrong integer. Every decision-driving read (badge, speed, speed_limit, stopping_offset) tracks the native path exactly, so the cost falls on the one field that cannot affect a fire.

**Fails loud on a short grab.** numpy slices past the end silently, and downscaling a partial HUD is worse than not downscaling: the resize restores the model's dimensions, so every downstream shape check passes and the readers return confident garbage.

**Downscaling is the only read path.** The per-resolution path it replaced rode a `--legacy-ocr` debug flag, retired 2026-08-09 once three live drives (1080p / 1440p / 4K) had confirmed the downscale path. It survived only at the two hand-calibrated resolutions, and promoting 4K's geometry silently armed it at a third where its anchors no longer matched the cell. Drive logs before that date carry an `ocr_legacy` key in the meta line; nothing reads it.

### What a profile means, and what gets interpolated

**A `PROFILES` entry means that geometry has been confirmed on a live drive at least once.** It is a record of observation, not of capability; the reads themselves need nothing per-resolution.

What the three observed drives read, all through `ocr_observe` on the production path:

| | 1440p (ratio 0.75) | 4K (0.50) | 1920×1200 (1.00, letterboxed) |
|---|---|---|---|
| samples | 792 / 453 s | 941 / 566 s | 1493 / 840 s (2 drives) |
| badge / speed / distance / limit | 100 / 100 / 98.4 / 100 % | 99.1 / 99.3 / 98.2 / 99.4 % | 99.3 / 99.3 / 98.6 / 99.3 % |
| speed_score median | 0.880 | 0.883 | 0.897 |
| badge_diff median (reject at 50) | 9.8 | 10.1 | 1.2 |

Halving the ratio costs nothing measurable — scores are flat, and speed is fractionally *higher* at 4K, which is the metric that would move first if the resampler under-filtered. The 4K read-rate dip is one 4-second black-screen event at the end of that run, not a steady rate; **0 frames lost speed while the badge read fine**, so the pipeline degrades as a whole frame or not at all, never as isolated garbage. The 1440p distance figure is not a miss rate either: eleven of its thirteen nulls are the train parked with the shared cell showing `1cm`, where the metre reader correctly returns `None` (§ "Stopping offset").

Everything else follows from two measured facts.

**One: the HUD sits at the same FRACTION of the viewport at every size.** Verified to the digit across both hand-calibrated profiles — `x/W = 0.859375`, `y/H = 0.013889`, `h/H = 1/3` identical at 1440p and 1080p, and the capture region is always `(W/2, 0, W, H/2)` of the viewport. The game scales the HUD without reflow, so any other size lands on the same fractions.

**Two: the viewport is not always the desktop.** On a desktop taller than 16:9 the game fits a 16:9 viewport and letterboxes it. Measured on a 1920×1200 capture: exactly 60 px of pure black top and bottom, inner region exactly 1920×1080, HUD at `(1650, 75)` — the 1080p geometry plus the bar. Confirmed by sweeping the HUD origin ±4 px through the production badge matcher, which put a sharp minimum at dead centre (3.6 mean-abs-diff, against 18.7 one pixel out in x and 28.8 in y). `_viewport_for` fits the viewport; a 16:9 desktop falls out of the same arithmetic with a zero bar, so there is one code path rather than a letterbox special case.

| capture | handling |
|---|---|
| **In `PROFILES`** | observed; used as authored |
| **16:9, viewport ≥ 1080p, no entry** | **derived** from the fractions above (`profile_for`), announced at startup as unobserved |
| **16:10** | **derived against the letterboxed viewport.** 1920×1200 is measured; 2560×1600 / 3840×2400 are the same aspect at a different size, so the fit carries |
| **Taller still** (4:3, 3:2 …) | derived by the same arithmetic *when the width allows it* (below), but **no desktop of that aspect has ever been seen** — the letterbox fit is measured only at 16:10. Permitted rather than refused because it is one mechanism, not a per-aspect rule; announced at startup with the bar it assumed, so a wrong fit is diagnosable from the first line of output |
| **Viewport below 1080p** | **refused** — the bars carry no pixels the readers can use, so the floor is on the viewport, not the desktop |
| **Width not a multiple of 16** | **refused.** No whole-pixel 16:9 height fits, and which way the game rounds the half pixel — or whether it splits the leftover row between the bars — is unmeasured. This is what actually stops most 3:2 panels: 3240×2160 and 3000×2000 both fail here even though their aspect and viewport are fine, while 2256×1504 passes. Rounding would be inventing the answer; one screenshot at 3240×2160 would settle it |
| **Wider than 16:9** (21:9 …) | **refused.** Presumably pillarboxed by the same logic, but nobody has seen one, and a guess reads at the wrong screen position rather than degrading. One screenshot would settle it |

An interpolated profile carries `verified=False`. It reads normally — geometry is the only thing being guessed and downscaling handles the rest — and the flag changes nothing beyond the startup NOTE it prints.

**Promotion is a one-line change:** once a resolution has been driven, add `(w, h): replace(_derive(w, h), verified=True)` to `PROFILES` so the entry records that it was seen. `_derive` rather than a hand-authored literal keeps the arithmetic in one home, so a promoted profile cannot drift from what derivation would have produced.

**`ResolutionProfile`** (frozen dataclass, `auto_input/hud_layout.py`) — `capture_region`, `hud_bbox`, `hud_bbox_in_capture`, cell bboxes (`badge_bbox`, `distance_value_bbox`, `speed_value_bbox`, `speed_limit_value_bbox`), `scale`. Only `capture_region` and `hud_bbox_in_capture` do anything on a non-model profile — they say what to grab and where the HUD is inside it; the cell bboxes that read it come from `DOWNSCALE_PROFILE`. `PROFILES` maps `(desktop_w, desktop_h)` → profile. `DOWNSCALE_PROFILE` is the 1080p one with its HUD origin at `(0,0)`, since a downscaled frame IS the HUD.

**`SegConfig`** — frozen dataclass of all segmentation thresholds (`digit_min_h`, `digit_min_w`, text-band Y bounds, gap limits). `SEG_DEFAULT` = 1440p values; `seg_for_scale(s)` returns a proportionally scaled copy. All readers take an optional `seg=`. The capture loop passes `seg_for_scale(read_profile.scale)`, so in practice every read runs at the model's scale.

**Templates — one set of each, because there is one model.** `ocr_templates/digits_red/` (13–16×20 px) and `ocr_templates/badges/` (83×30) are cut at the model's scale and are what every read uses. `ocr_templates/digits/` (dark, 0–9) is cut at 1440p and NN-resized onto the candidate in `compare()`, so it is scale-free by construction — that is why it needs no model-scale twin. Nothing here is per-resolution: the second sets, and the native reads that consumed them, were deleted 2026-08-19 when downscaling became the only path.

The shapes still refused above are refused for want of a measurement, and the designed-but-unapproved replacement (a user-drawn HUD box, presets, auto-propose) is held as a direction rather than a ticket: [TODO.md](../TODO.md) § "The HUD is found on any screen shape, not just the ones measured".

## HUD layout

All bboxes = `(x, y, w, h)`. Cell bboxes = HUD-relative; HUD bbox = canonical screen-relative; capture region + HUD-in-region derived. Values below are 1440p baseline; 1080p = ×0.75 rounded. Live in `PROFILE_1920_1080` / `PROFILE_2560_1440` in `auto_input/hud_layout.py`. The flat constants below are backward-compat (consumed by `*_from_surface` dev-tool helpers + calibration extractor).

| Constant | Value | Notes |
|---|---|---|
| `HUD_BBOX` | `(2200, 20, 350, 480)` | Canonical screen-relative position. Consumed by `*_from_surface` helpers (1b dev tool) + calibration extractor |
| `DISTANCE_VALUE_BBOX` | `(120, 314, 230, 55)` | Right side of "Distance" / "残距離" row (shared with stopping-offset) |
| `SPEED_VALUE_BBOX` | `(120, 165, 230, 55)` | Right side of "Speed" / "速度" row |
| `SPEED_LIMIT_VALUE_BBOX` | `(120, 215, 230, 55)` | Right side of "Speed Limit" / "最高速度" row — red digits, line-dependent |
| `BADGE_BBOX` | `(29, 122, 111, 40)` | Green/blue pentagon — left + top scenery bleed trimmed |

Position invariant across language modes (EN/JA), game states (running/stopped/at-platform), and scenes — verified against 7 reference screenshots.

**Resolution gate.** Production AutoDriver runs a bootstrap full-frame `camera.grab()` at startup, probes `(w, h)`, and calls `profile_for(w, h)`. That returns the observed entry when there is one, and otherwise derives the geometry against the fitted 16:9 viewport. It is fatal only when the size is out of scope (§ "What a profile means, and what gets interpolated"). This prevents OCR running with wrong-resolution bboxes. Sibling to other fail-loud invariants in [critical_lessons.md](../.claude/rules/critical_lessons.md).

## Capture: dxcam (DXGI Output Duplication)

**Why not Win32 PrintWindow or BitBlt-from-desktop:** the game renders via DirectX, and the swap chain isn't visible to GDI. Both APIs return all-black frames even with `PW_RENDERFULLCONTENT` flag set. **dxcam** uses DXGI Output Duplication (the same GPU-level capture API used by Discord/OBS), reading the GPU framebuffer directly.

```python
import dxcam
from auto_input.hud_layout import profile_for
profile = profile_for(desktop_w, desktop_h)  # observed entry, else derived; None = out of scope
camera = _open_capture_camera(output_color="BGRA")  # adapter-enumerating; native BGRA
frame = camera.grab(region=profile.capture_region)  # right-half quadrant, resolution-dependent
```

Notes:
- BGRA output = DXGI's native format; choosing it avoids requiring opencv as dep
- `grab()` can return `None` (no new frame since last call) — retry with brief sleep
- Game must be **rendering** (not minimized/alt-tabbed in a state where it pauses)
- Top-right corner where HUD lives must not be covered by other windows
- **Adapter selection is enumerated, not hardcoded to device 0.** Capture opens via `_open_capture_camera` (`driver.py`), which walks every `(device_idx, output_idx)` dxcam exposes — primary output first — and returns the first whose `create()` succeeds (a successful create IS a live duplicator; `DuplicateOutput` runs inside it). A bare `dxcam.create()` addresses only adapter 0's primary output, which raises `DXGI_ERROR_UNSUPPORTED` (0x887A0004, a hard `COMError`) when the display is owned by a different adapter — the classic Microsoft-Hybrid (Optimus) case where DDA is unsupported against the discrete GPU. Enumeration finds the display's actual owner. On total failure the full traceback is printed (never muted — it is the only signal for the next machine) and the driver disables gracefully.
- **Enumeration cannot cover the process-scoped half, and that is the case seen in the wild.** DDA's hybrid restriction is about which GPU the *calling process* runs on, not which adapter index is passed to `DuplicateOutput`. So when Windows launches the app on the discrete GPU, every combo the walk tries raises `UNSUPPORTED` and it exhausts. Confirmed 2026-07-26: the #97 reporter fixed it by setting the app's Windows GPU preference to power saving, changing no adapter, no monitor and no cable. Two levers remain, neither shipped:
  - The per-app preference at `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` — value = full exe path, data `GpuPreference=1;`. It applies at next launch and overrides the vendor control panel.
  - dxcam's `backend="winrt"`. Windows.Graphics.Capture captures at the compositor, with no same-adapter constraint. It needs `dxcam[winrt]` bundled (`winrt-runtime` plus 8 namespace packages), and its `importlib.import_module` loads need explicit PyInstaller hidden-imports.

  The OCR consent panel carries a plain-language note telling the user to switch to power saving. See [#97](https://github.com/ksleungac/pids-jre-simulator/issues/97).

## OCR pipeline (digit cells)

### Stage 1 — segmentation

```
cell (RGB) → grayscale → threshold (ADAPTIVE, see below) → column-sum > 2 = "has text"
                         (text band y=15..52)
                                 │
                                 ▼
            Find runs of has-text columns separated by gaps → raw bboxes
```

**Threshold is per-cell, not a constant** (`_cell_dark_threshold`, 2026-07-22). Otsu over the text band, clamped to `[OTSU_CLAMP_LO, OTSU_CLAMP_HI]`, falling back to `DARK_THRESHOLD` when the band's dynamic range is under `OTSU_MIN_CONTRAST`.

The HUD is **semi-transparent**, so background scenery brightness moves the pixel levels under the text and a fixed global split cannot hold. Measured over 2442 live frames: a bright surface background clipped a digit's anti-aliased edge column, so the SAME `4` binarized 13px wide where a dark tunnel background gave 16px, and a clipped glyph no longer matches its own template. Adaptive: per-digit modal-width purity **89.2% → 95.1%**, clipped forms to zero, 0 regressions (6 reads changed, all recoveries).

Two non-obvious constraints, both learned the hard way:
- **The clamp is load-bearing.** Bare Otsu on a cell with NO text splits sensor noise and hallucinates digits (uniform bg 240 → `"79"`, bg 10 → `"77600"`). Empty cells are NORMAL — `read_speed_limit` gets one on every line with no posted limit.
- **`segment_chars` and `extract_glyph` must use the SAME threshold**, both derived from the whole cell. If they disagree, the bounding box and the pixels inside it are computed under different rules. That is why `extract_glyph` takes the cell rather than the crop.

Text band excludes HUD's top/bottom borders and any scenery bleed-through near cell edges.

### Stage 2 — filtering

Three filters in sequence:

1. **Digit-shape filter**: keep only bboxes with `h ≥ 22` and `7 ≤ w ≤ 30`. Drops 'm' suffix strokes (h≈10), label tail fragments, scenery blobs.
2. **Decimal-stop** (speed only): find the small decimal point (`h ≤ decimal_max_h, w ≤ decimal_max_w`) in the bottom half of the text band and stop accepting digits at its x-position. **Robust against gap variance**; replaces the gap-based heuristic that was failing on `1x.x` and `11x.x`.

   **1-column-tolerant** (2026-07-20): the search scans the raw *column-runs* rather than the finalized digit bboxes, with a 1-px row tolerance. On 1080p and softer captures the dot binarizes to a single dark column, its faint edge column falling below `DARK_THRESHOLD`, which `finalize()` cannot turn into a bbox. Before this, a 1-column dot was invisible to the search and the tenths digit slipped into the integer (19.1 → `191`) on ~40% of frames of a compressed 1080p capture. The dot detection had zero margin — 1440p renders it 3–4 columns wide, which is why the failure was 1080p-specific and hard to reproduce on a crisp screen.

   **Gap-guarded** (2026-07-22): a candidate is accepted only if it stands `DECIMAL_MIN_GAP` clear of the last DIGIT-sized run. The 1-column tolerance cuts both ways: on a degraded frame a digit SHEDS a 1-column stub (a `4` dropped a `w=1 h=3` fragment 1px past its own body), dimensionally identical to a dot, and the scan took it as the decimal and truncated `48.3` to `4`. A real decimal stands clear, measured 4–5px at 1080p, while a shed fragment abuts at 1px. The two rules are a matched pair: **never widen the dot scan without keeping the gap guard, and never drop the gap guard while the 1-column tolerance stands.** Regression oracle: `_tests/t1_unit/test_ocr_read.py` § "where the number ends", over a committed live cell.

   **Domain safety-net:** `read_speed` still passes the value through `_rectify_speed`. A read above the 140 km/h ceiling (drivable max 135 plus slack) drops one trailing digit and re-checks (`727 → 72`, `1350 → 135`); genuine garbage becomes `None`. With the 1-column-tolerant stop this is now a rarely-exercised backstop rather than the primary line of defense.
3. **Gap-stop** (safety net): stop accepting digits at first horizontal gap greater than `MAX_GAP`. Distance: 20 (anything past 'm' has bigger gap). Speed: 25 (relaxed because decimal-stop = primary boundary; 25 catches scenery blobs but lets through wide kerning like '1' to '1' which can be 18px).

### Stage 3 — template matching

Templates: 10 binary glyphs (digits 0-9) extracted from labeled reference screenshots via `KNOWN_VALUES` dict in `auto_input/ocr.py`.

Matching: each segmented bbox's binary glyph padded to size of template, then compared pixel-equality. Score = fraction of matching pixels (0.5 = random for binary). Best-scoring template wins per glyph; concatenate to integer.

Live scores observed: 0.75–1.00. Below 0.6 = danger zone (random match territory).

### Tunable constants (in `auto_input/ocr.py`)

| Constant | Value | Rationale |
|----------|-------|-----------|
| `DARK_THRESHOLD` | 70 | Excludes gray scenery; keeps near-black text |
| `COLUMN_TEXT_MIN` | 2 | Filters single-pixel column noise |
| `ROW_TEXT_MIN` | 1 | Tight row bounds |
| `TEXT_BAND_Y` | (15, 52) | Excludes borders + scenery bleed at cell edges |
| `DIGIT_MIN_H` | 22 | Distance/speed digits ≈ 30-33 px tall |
| `DIGIT_MIN_W` | 7 | Narrowest digit ('1') ≈ 8-9 px |
| `DIGIT_MAX_W` | 30 | Widest digit ≈ 23 px |
| `DECIMAL_MAX_H` | 10 | Decimal point ≈ 4-5 px tall |
| `DECIMAL_MAX_W` | 7 | Decimal point ≈ 3 px wide |
| `DECIMAL_BASELINE_FRACTION` | 0.55 | Decimal sits in bottom half of text band |
| `DISTANCE_MAX_GAP` | 20 | Inter-digit gap < 20; m-stroke gap > 20 |
| `SPEED_MAX_GAP` | 25 | Wider for narrow `1`-to-`1` kerning (~18 px) |

These are fields on `SegConfig` (frozen dataclass, `auto_input/ocr.py`). `SEG_DEFAULT` uses the 1440p values above. `seg_for_scale(s)` scales all pixel-threshold fields proportionally — pass the result as `seg=` to any OCR reader to run at a different resolution.

## Stopping offset (cm) — shared distance cell

`DISTANCE_VALUE_BBOX` cell is content-shared and self-identifies via color:

- **Dark text `Nm`** — distance to the **next station in sequence**, pass-throughs included — NOT the total to the next stopping station. Shown during transit, AND at the platform after the cm display dismisses (~5s post-arrival). While the badge reads MOVING the two coincide (no pass-through is left before the stop), which is why "next stopping station" reads correct in transit and is wrong at a platform on a rapid service. The distinction is load-bearing for the distance guard: per-station re-targeting is exactly what produces the upward re-points it exempts, and a total-to-the-stop reading would only ever count down (§ "Distance plausibility guard").
- **Green text `±Ncm`** — stopping offset from the platform's stop mark. Shown briefly after `MOVING→STOPPED` (~5s window). Sign shown only for negative (train stopped past the mark); `0` and positives omit the sign character.

Both readers run unconditionally each capture cycle. Their masks are mutually exclusive (`gray < 70` for m-distance, `(G - max(R,B)) > 30` for cm-offset), so at most one returns non-None per frame — **except across the swap itself**. As the train crawls the last metre the cell changes m→cm while the badge still reads MOVING, and for 2–3 frames the masks stop separating and BOTH readers fire on the same pixels (`dist=78` and `offset=78` together). The offset copy is discarded by its STOPPED gate; the metre copy passes through as a phantom distance that appears to go UP, which the distance guard then catches. Observed identically on native 1440p, so downscaling is not implicated. JSONL records both fields each sample; display priority gives cm precedence (transient signal of interest), falls through to m otherwise.

**Badge-gated acceptance (driver, not reader).** `read_stopping_offset` is state-agnostic, but the driver trusts its value only when the badge groundtruth says STOPPED (`_accept_stopping_offset` in `driver.py`). The green ±cm read is phantom-prone — scenery-green bleed through the semi-transparent HUD can fabricate a ±cm value mid-transit — so it is gated on `badge == "STOPPED"`.

**Badge read > (distance, speed):** the badge is the most reliable read on the HUD — canonical, with clean pixel-diff separation — and strictly more reliable than the speed/distance digit reads. So it is the SOLE gate, deliberately NOT speed-gated: folding in the noisier speed read would only add false-rejects, with no phantom protection the badge doesn't already give. Same badge-only rule as `FIRE_AT_STATION`.

Rejections emit an `offset_reject` drive-log event, paired with the same-ts sample, so a valid offset ever lost to a badge misread stays visible. The reader also domain-clamps `|offset| ≤ 500cm`, the game's stop zone; a larger magnitude is a garbage green read and becomes `None`.

Two pipeline differences in `read_stopping_offset` vs `read_distance`:
- **Color mask** as above.
- **Sign detection**: small bbox (h ≤ 12, w ≤ 18) in vertical center of text band, left of first digit, treated as leading minus. No `+` glyph template — positive case has no sign character at all.

`cm` suffix = same green color but smaller than digits, excluded by existing `DIGIT_MIN_H=22` shape filter. Digit templates reused unchanged — binarization is colour-agnostic, shape matches dark-text version.

**Overrun semantics.** The game prevents the user from physically stopping in the red-text zone — overrun → game resets the train to `0cm`, briefly shows it, then black-screens to fast-forward past to the next station. Red text is unreachable in normal play. The "no cm reading" state at STOPPED is the normal post-display-dismissal state, **not** an out-of-bound signal — interpreting overrun requires examining the surrounding badge transitions and the brief `0cm` read, not a single null cm sample.

## Speed limit (最高速度) — red digits

Cell at `SPEED_LIMIT_VALUE_BBOX`, between speed and distance rows. Red digits + dark `km/h` suffix. **Line-dependent** — many lines don't post a cab speed limit; empty cell = normal "no posted limit" state, not OCR fault. `read_speed_limit` returns `None` for those frames; speed limits always in 5/10 km/h increments when present (5, 10, …, 75, 95, 110, 120).

Reader uses `(R - max(G,B)) > RED_TEXT_DELTA` as color mask — dark `km/h` suffix excluded automatically. Three complications the reader handles:

- **Tight kerning glues digit pairs** — at 80, 90, 110 the column-density threshold never drops below `COLUMN_TEXT_MIN` between digit pairs (typically ?-`0`), so segmentation sees one over-wide run instead of two digits. `segment_red_digits` supports two split strategies:
  - **`argmin` (default)**: find deepest column-density valley and split there, recursively until each sub-bbox fits `DIGIT_MAX_W`. Precise for cases with clear inter-digit dip.
  - **`equal_width` (fallback)**: divide each over-wide run into N equal parts where N = round(width / 18). Ignores column density entirely. Robust to cases where `0`-shaped digits' natural hollows look deeper than actual digit boundary (limit_100's `0+0` merged blob).
  `read_speed_limit` runs `argmin` first; if grammar-valid AND `min_score >= ARGMIN_TRUST_SCORE` (0.85, in `ocr.py`), return immediately. Otherwise — argmin grammar-invalid OR low-confidence valid — also runs `equal_width` and prefers its grammar-valid result. Threshold gates against argmin's `0+0` misread mode where split lands inside a digit hollow and produces a confident-but-wrong grammar-valid read; equal_width's symmetric split repairs it (calibrated against 31-frame `100` corpus — low band 0.65-0.66, high band 0.92+).
- **Stroke-weight mismatch** — red font is bolder than dark-text font the original digit templates were extracted from, so dark templates alone consistently mismatch certain digit pairs (8 / 6 misread as 4). Two-tier matching: (a) red-text digit templates extracted from limit screenshots into `ocr_templates/digits_red/` (one PNG per digit, full 0–9 coverage as of 2026-05-09); (b) dark templates dilated by `SPEED_LIMIT_TEMPLATE_DILATION` (3 px) as fallback for any digit without a red template. Best-of-both score wins per glyph. Re-extract via `_dev_scripts/extract_ocr_assets.py` after adding new `_ocr_calibration/limit_*.png` reference screenshots.
- **Domain validation** — observed range in JR EAST Train Sim Real is 25–130 km/h in 5/10 km/h increments. Reader validates final integer against `VALID_SPEED_LIMITS = {25, 30, 35, …, 130}` and returns `None` on out-of-grammar reads. Catches fallout of split contamination (e.g. 110 occasionally read as 114 because `0`'s left curve bleeds into `1`'s split bbox), single-digit corruptions (90 sometimes read as 1), and any future misclassification mode that produces a non-grammar value. Better to return `None` and miss a frame than write a wrong value to JSONL.

**Debugging misreads.** Live-frame OCR misreads don't round-trip cleanly through pipeline: dxcam BGRA frame and `pygame.image.save`'d PNG of same instant can produce different `segment_red_digits` bboxes via sub-pixel column-density variance. A live `100`→`110` misread may replay to `100`→`160` on saved PNG (grammar-fail → equal_width fallback → correct), masking original mode. To collect a usable corpus, AutoDriver dumps `sl_cell` to `_ocr_calibration/_misread_dumps/sl_<ts_ms>_score<NN>_read<NNN>.png` whenever a grammar-valid `speed_limit` read scores below `SUSPICIOUS_SPEED_LIMIT_SCORE` (0.75, in `auto_input/driver.py`); `ts_ms = int(ts * 1000)` matches JSONL row.

## Badge classification (state cell)

Game shows pentagon badge in next-station row, with text inside:

| State | EN text | JA text | Color | Meaning |
|---|---|---|---|---|
| MOVING | "Next" | "次停車駅" | green | Train heading to next stopping station (badge displays target) |
| STOPPED | "Stopping at" | "停車中" | green | Train at platform |
| PASSING | "Pass" | "通過" | **blue** | Train crossing a station that won't be stopped at; badge still displays the next *stopping* station, but **HUD distance is to the passing station, not the stopping target** |

**Critical observations:**
- Pentagon shape **identical** across all three states — only text content + fill colour differ.
- MOVING and STOPPED both use same green pentagon; pixel-diff against text-content anchors discriminates them.
- PASSING's blue fill gives classifier wide separation margin: cross-state mean diff to MOVING/STOPPED ≈ 43, vs within-state ~6–10.
- **STOPPED is canonical, never transient.** Game only shows STOPPED badge when train is actually stopped within platform's stopping range OR when game has reset train to a platform. NEVER flickers STOPPED briefly during deceleration or overrun. Detector logic relies on this: single STOPPED frame sufficient to flip `at_station_observed=True`, no debouncing or N-frame consensus needed. Also rules out recurrence-shape hypothesis ("brief STOPPED reading during overrun resets atstn_obs from prior segment") — that scenario can't happen by game design.
- **Only four badge transitions are physically possible.** `STOPPED→MOVING`, `STOPPED→PASSING`, `PASSING→MOVING`, `MOVING→STOPPED`. **`MOVING→PASSING` and `PASSING→STOPPED` cannot occur** — passing stations all lie *before* the stopping station, so once the HUD targets the stop there is nothing left to pass; and a station being passed is by definition not one the train stops at. Within a segment the badge is therefore monotone: `PASSING`\* then `MOVING`.

  **This is a constraint on the GAME, not on our state machine.** Nothing in the code encodes it, so no amount of reading the code recovers it, and a detector or search that walks the badge freely will spend itself on transitions that never happen.

  Observing one of the two impossible transitions means a **misread**, not a state change, which splits how code may treat them. **Tolerating** one as a recovery is correct: `_Detector.update`'s `prev_badge in ("MOVING","PASSING") and badge=="STOPPED"` accepts the impossible `PASSING→STOPPED` as an arrival, and that is what recovers the Keiyo run where a whole MOVING segment reads PASSING and the train then genuinely stops. **Relaxing a guard** on one is a hole, because the relaxation then lands only on corrupt frames. Author-stated 2026-08-11.

### Classifier

Pixel-diff against 6 anchor templates:

```python
BADGE_ANCHOR_FILES = {
    "MOVING":  ["running_en",  "running_ja"],
    "STOPPED": ["stopping_en", "stopping_ja"],
    "PASSING": ["passing_en",  "passing_ja"],
}
```

`load_badge_anchors(badges_dir)` silently skips missing files, so a stem listed here but absent on disk costs an anchor without an error. The dict carried three stems per state until 2026-08-19, when the second (1440p) anchor dir was deleted — the extra stems were its filenames.

Per frame: crop badge cell, compute mean-abs-diff against each anchor, pick state with lowest-diff anchor. Language-agnostic — whichever anchor matches best determines state, regardless of which language user plays in.

Diff < 15 = high confidence; real reads sit there. Diff > `BADGE_DIFF_REJECT` (50) rejected at classifier — `classify_badge_state` returns `(None, diff)` so detector treats it as OCR FAIL. Black-screen / dark-cell garbage frames diff 60-110; mid-animation transient spikes at exact transitions hit >70. 50 cleanly separates real from garbage with margin on both sides. Detector's `None` tolerance preserves `prev_badge` across rejected frames, so one-cycle delay on transition detection = only cost.

## State machine — `PaEventDetector`

Lives in `auto_input/driver.py` `_Detector` — SINGLE copy since 2026-07-21 (the `capture_game.py` fork was deleted; a hand-synced duplicate silently drifted and broke). Tracks distance + speed + badge across samples, emits PA-fire event names on transitions.

### State vocabulary

State machine works in Layer 3 named-state vocabulary — see "State machine layering" above for canonical names + inference truth table. The 5 states (`IDLE`, `DEPARTING`, `CRUISING`, `ARRIVING`, `STOPPED`) + `UNKNOWN` sentinel describe autodriver's inferred view of where IRL game train is in its segment cycle. They map onto per-sample event emissions below.

**When designing flows that interact with the state machine** (entry-point, resync, click-to-jump): say *"AutoDriver thinks the game is in `IDLE`"*, not *"badge is STOPPED."* The badge is one input to the inference; the inferred state is what the design reasons about. The separation matters for hardening — and avoids design conclusions accidentally over-trusting a single OCR attribute.

### Events

| Event | Trigger | Effect |
|---|---|---|
| `STOPPED->MOVING` | badge transition | New segment begins; reset all three observed-flags; set `motion_origin_known=True` (witnessed edge — disarms re-entry for the segment, see § "Re-entry") |
| `MOVING->STOPPED` | badge transition | Train just arrived at platform (logged only — see `FIRE_AT_STATION`); clear `motion_origin_known` (the next motion must witness its own edge) |
| `FIRE_DEPARTURE` | `departure_observed=False` AND `SPEED_DEPARTURE_KMH ≤ speed` AND (`speed < DEPARTURE_STALE_KMH` OR `motion_origin_known`) | Fire departure PA, set `departure_observed=True`. Ceiling lifts on a witnessed edge — see § "Departure is a level test too" |
| `FIRE_ARRIVAL` | `badge==MOVING` AND `distance ≤ arrival_lead_m` AND `arrival_observed=False` | Fire arrival PA, set `arrival_observed=True` |
| `FIRE_AT_STATION` | `badge==STOPPED` AND `at_station_observed=False` | Fire silent press that flips sim into STOPPING (sets `state.at_station=True`); set `at_station_observed=True`. If the arrival was missed (`cnt_pa` not at the last approach PA), `_fire_at_station` silently drains to the last entry first so the press lands as the STOPPING transition |

`arrival_lead_m` = base **900m**, adjusted on the setup-screen Lead stepper (range 500–1500, ±100m).

**Long-approach bump (auto, per-stop).** Stops whose arrival PA (`pa[1]`) runs ≥ `LONG_APPROACH_PA_SEC` (40s) fire arrival `LONG_APPROACH_BUMP_M` (+400m) earlier → effective 1300m. Probed once from audio headers on thread start (`_compute_long_approach`, soundfile header read, no decode); per-cycle `_lead_for(curr_stop)` sets `arrival_lead_m` before `update()`, so both the level-test and re-entry (`_resolve_reentry_target`) sites read it. Auto-derived per route — no route.json authoring, applies to future routes. Threshold = duration 900m can't cover at cruise (~23 m/s); flat bump (not scaled) because long PA ↔ slow approach self-compensates in distance. Replaces the old manual "1200m for transfer-heavy lines" guidance — Shinjuku / Atami / major junctions now self-bump. Rationale: `memory/2026-06-11.md`.

**Per-segment observed flags** prevent double-firing within a single segment when OCR misreads transiently flip a trigger condition (e.g. speed misread as `7` between two real in-band reads would fire `FIRE_DEPARTURE` twice without the flag). All three flags (`departure_observed`, `arrival_observed`, `at_station_observed`) reset on `STOPPED->MOVING`. PASSING transitions do NOT reset flags — PASSING = transient sub-state of MOVING within a segment, not new segment.

**`at_station_observed` is NOT gated on `arrival_observed`** (gate removed 2026-07-24 — the reachability rule): a STOPPED badge while the app is in transit IS the arrival fact, and a dropout that ate the arrival must not strand the app at 1A/1B. The concerns the old gate carried are covered elsewhere: boot (parked at session start with `badge==STOPPED`) by `_fire_at_station`'s app-parked skip; post-jump refire by `_reanchor_to_app` setting `at_station_observed=True`; a missed arrival's stale `cnt_pa` by the fire-side approach-PA drain. Pa-empty stops still get the at-station fire — `_fire_at_station` accepts `pa==[]` because APPROACHING→STOPPING transition silent regardless of pa contents.

### Arrival and departure are level tests, not crossings

Arrival trigger fires whenever `badge==MOVING AND distance ≤ arrival_lead_m`, gated by per-segment `arrival_observed` flag. Does **not** require downward-crossing of threshold.

This matters because of PASSING. While badge reads PASSING, HUD distance is to the passing-through station (NOT to next stopping target). Detector ignores those samples entirely:

- **Arrival check gated on `badge==MOVING`** — PASSING-relative sample at, say, 300m to passing station doesn't trigger arrival for actual stopping station that's still 1500m away.
- **`prev_distance` no longer tracked** — level test doesn't need it. Old downward-crossing test (`prev > lead >= curr`) couldn't handle case where `PASSING→MOVING` resumed with distance already < lead (first MOVING sample's distance jumps *up* relative to PASSING-relative prev, defeating the crossing check). Level test handles it cleanly: any MOVING sample with `distance ≤ lead` fires arrival, exactly once per segment.

Speed/departure logic — speed = own-train and badge-independent.

**Departure is a level test too, bounded above ONLY for unknown-origin motion.** Fires whenever `departure_observed=False AND SPEED_DEPARTURE_KMH ≤ speed AND (speed < DEPARTURE_STALE_KMH OR motion_origin_known)` — no `prev_speed`, no crossing. A crossing (`prev_speed < 30 ≤ speed`) loses the departure **permanently for that segment** whenever `prev_speed` is absent (thread start, post-click-jump) or stale at/above 30 — `prev_speed` only updates on a non-`None` read, so dropped reads through deceleration + dwell carry the pre-station cruise value into the next departure, i.e. **degraded arrival reads break the FOLLOWING departure**. Double-fire protection is the `departure_observed` flag + the app-sub-state gate in `_fire_departure`, never the test's shape.

**The upper bound is provenance-gated (2026-07-24).** The `DEPARTURE_STALE_KMH` ceiling reserves the `≥60` case for re-entry's silent 1A (§ "Primary/fallback strictness must not invert"), but ONLY when the origin is unknown. On a **witnessed** `STOPPED→(MOVING|PASSING)` edge (`motion_origin_known`) the segment just started, so the announcement is fresh at any speed and the ceiling lifts: the departure fires audibly, transition-graph arrow (a) mimicking (d).

Without this, a platform dwell whose acceleration lands entirely inside an OCR dropout loses the departure — badge and speed both `None` through the whole `[30, 60)` band, first valid read already `≥60`. The witnessed edge has disarmed re-entry, so nothing catches it and the app strands at 1C. (The 2026-07-24 01:36 incident: 35 s of black-screen at the platform, badge recovered at 64.8 km/h.) This is a NORMAL-drive path — no click-jump, no re-entry — so the ceiling must never compromise it.

**Direction-agnostic BY DESIGN — don't "fix" it back into a crossing.** The test fires on a DECELERATING pass through the band too. `departure_observed` bounds that correctly: in a segment watched from its start the acceleration already set the flag, so the flag is False while decelerating ONLY on a mid-segment join (cold boot, toggle-ON, click-jump) — exactly where the PA has not played. Direction was only ever a proxy for "fresh segment"; the flag is the real thing. Measured over 26 recorded drives: 42 segments, 0 decelerating fires.

**What this does NOT fix — missed segment start.** If the `STOPPED->MOVING` transition is itself missed (badge dropout across the whole departure), the flags keep the PREVIOUS segment's `True`, so the departure is **suppressed** — silence, not a spurious fire. Re-entry stays legitimately armed here (the edge was never witnessed, so `motion_origin_known` stays False): Layer 1 sits at 1C until `speed ≥ 60` resolves the silent 1A, or `dist ≤ arrival_lead_m` resolves the silent 1B (pa≥2 landing stops only), or the STOPPED badge at the platform lands the at-station fire (pa=1's path). A steady in-band cruise therefore recovers later than it did when the resolver's bound was 30. Accepted trade — the alternative re-inverts the strictness. Tracked: [#84](https://github.com/ksleungac/pids-jre-simulator/issues/84).

**Manual-press precedence** is implicit in the Layer-1 fire gates: each `_fire_*` reads the app sub-state before sending its press (departure only at 1C, arrival only at 1A, at-station at 1A/1B), so a manual PageDown that already advanced the app makes the driver skip its own fire (`SKIPPED … already departed` etc.). Pressing PageDown manually always wins; the auto-driver fills in only where you didn't. (The old timestamp comparison + `SELF_PRESS_GUARD_S` self-press hook are gone — the app sub-state IS the precedence check.)

`None` values for distance/speed/badge tolerated individually — OCR FAIL frames don't reset state, so transient unreadable frames don't break segment continuity.

**Cross-attribute reject (black-screen guard).** When `prev_badge == "STOPPED"` and the new badge would transition to `MOVING` or `PASSING`, the transition is rejected (badge forced to `None`) unless `speed > 0`. The game black-screens briefly to fast-forward simulated time, but only while parked at a platform, never mid-transit. (One of four black-screen causes; § "Game-side ground truths" has the set.)

During that window the badge cell goes uniform-dark and the classifier picks whichever anchor pixel-diffs lowest, typically PASSING, since blue is closer to black than green. The distance cell drops out consistently while the speed cell sometimes survives showing the parked-at-platform `0`. The structural rule exploits that asymmetry: a real platform departure always shows speed climbing from 0, because the game can't fake movement without rendering it, so `speed == 0` or `speed is None` at a STOPPED→moving transition is the black-screen signature. Without this the spurious PASSING fires a phantom `STOPPED→PASSING` and resets the observed-flags as if a new segment began.

First concrete instance of the cross-attribute hardening philosophy (see the `auto-input` [GitHub issues](https://github.com/ksleungac/pids-jre-simulator/issues)). Rejection also lands in the JSONL drive log as a `cross_reject` event, log-only with no fire. It pairs by ts with the sample line, which keeps the raw rejected badge/diff/speed.

**Badge-reject score gate.** When the badge itself fails to classify (`badge is None` — best-anchor diff > `BADGE_DIFF_REJECT`, so the frame is degraded: black-screen or a mid-animation transient), the accompanying digit reads are phantom-prone. Sampling the drive logs on `badge=None` frames, speed/distance sit at score **median ~0.60** (the "<0.6 random-match danger zone" above) vs **~0.90** (p25 0.88) when the badge reads — a clean separation. So on a badge-reject frame, `_apply_badge_reject_gate` (driver) drops any `speed` / `distance` / `speed_limit` read below `BADGE_NONE_SCORE_GATE` (0.80) to `None`, before any decision, the log, or the band sees it. This is the "badge > (distance, speed)" principle extended to frame quality: when the most reliable HUD read fails, distrust the derived ones. **Conditional on `badge=None`, NOT a global score floor** — a genuine 0.6 read is kept whenever the badge confirms the frame; the earlier-rejected global-floor ban lacked an honest threshold, which the `badge=None` conditioning supplies. Offset is not included — it is already badge-gated to STOPPED (above), so `badge=None` rejects it upstream. A drop emits a `score_gate` drive-log event (log-only), paired by ts with the sample whose `*_score` fields still hold the rejected confidences.

**Distance plausibility guard.** Distance (`Nm` remaining) has no decimal and the badge reads MOVING on ~60% of its spike frames, so neither the decimal fix nor the badge-reject gate catches its degraded-frame failure: a single-frame mis-segmentation spike (`1372 → 3 → 1257`). But distance obeys physics — between two samples the train moves at most `v·Δt`. `guard_distance` (driver) rejects a read whose change from the last VALID distance exceeds `MAX_DRIVABLE_SPEED_KMH · Δt` (+ `DISTANCE_GUARD_SLACK_M`) and HOLDS-LAST-GOOD. The **ceiling** speed (not the current frame's, which is co-corrupted on spike frames) keeps the bound false-reject-proof; `Δt` is the actual elapsed time since the last valid read (measured ~3s), so an OCR dropout doesn't tighten it. **Re-anchor only on a re-point.** A *re-point* is the HUD switching its distance to a NEW target — the metre count then jumps by any amount and `v·Δt` cannot apply. **Two conditions, both required** (narrowed 2026-08-11):

1. **The badge pair is one of exactly three** (`DISTANCE_RETARGET_PAIRS`) — `STOPPED→STOPPED` (the dwell refresh: having arrived, the HUD re-targets the next station), `PASSING→PASSING` (cleared one passed-through station, re-targets the next), `PASSING→MOVING` (cleared the last passed-through station, re-targets the stopping station).
2. **The jump is UPWARD** — a re-point always goes from something just reached (≈0) to something farther, so a downward jump is never one. That is the spike shape (1330 → 5). Safe because the parked distance is the green ±cm stopping offset (≈0) and the refresh takes it up; no phase of normal driving moves a re-point down (author-stated 2026-08-11). A pause-menu station jump does re-point in either direction, but it arrives behind a black screen and is re-entry's job, not the guard's (§ "Game-side ground truths").

**The set is decided by what is physically possible, never by sampling timing.** A coarse `SAMPLE_INTERVAL_S` can make the dwell refresh first *observed* on a `MOVING→STOPPED` pair — no sample landed between the stop and the refresh — and that pair is then gated. Deliberately not designed around: the lever is the interval, not the guard.

Condition 2 is what makes a one-frame PASSING misread harmless. The frame *after* it presents as `PASSING→MOVING` — identical by badge to a genuine switch, so condition 1 cannot separate them — but a real one jumps up to the stopping station while the spike went down. Without it, a mis-segmented distance is accepted, re-anchored, and read by the arrival level test: まもなく ~400 m early, then every correct distance rejected for ~21 s until Δt loosens the bound.

`MOVING→PASSING` gets no exemption: it is physically impossible (§ "Only four badge transitions are physically possible"), so there is no re-point for an exemption to absorb. **That is a claim about the reference frame, not about badge reliability** — the badge stays the most trusted read and nothing here second-guesses it.

**A departure carries no re-point.** The dwell refresh completes while the badge still reads STOPPED (author-stated 2026-08-11), so by the `STOPPED→MOVING` edge the anchor already holds the next station's distance. The departure's own motion is ~3.75 m — a train's quickest ~3 km/h/s over one 3 s sample — against a ~162 m allowance. `STOPPED→MOVING` and `STOPPED→PASSING` are therefore ordinary gated frames.

A `badge=None` degraded frame while the prior badge was MOVING IS still gated, so a confident-but-garbage spike on an unreadable-badge frame can't re-anchor and poison the guard. No consensus latch: a double spike is rejected on both frames and self-heals when a plausible read near the anchor returns, since the bound loosens as `Δt` grows.

Validated on the reporter's 1080p logs: wild distance jumps 24/10 → 1/1. A reject emits a `distance_reject` drive-log event. Design consult: `/third-man`, 2026-07-21, which redirected an earlier two-frame-consensus proposal to this badge-transition reset. Follow-up of the temporal-stabilization issue (#70).

## Debug panel (in-process integration only)

When OCR Auto-PA enabled at setup screen, `PASimulator` allocates an extra `DEBUG_PANEL_HEIGHT` row above the LCD via pygame sub-surfaces. LCD code **completely unchanged** — it gets a sub-surface positioned at `(0, DEBUG_PANEL_HEIGHT)` and thinks it's drawing to a regular LCD-sized screen.

**The panel IS the shared TIMS status band** (`tims.band.render` — the same band the `tims.setup` flow draws). `DEBUG_PANEL_HEIGHT` is re-exported from `tims.band.BAND_H` (single source; the band owns its height). `app.py::_render_panel` feeds the band the live `auto_input_status` dict + stashes its returned `{home/save/pause}` hit-rects for the run-loop click handler (`_handle_band_click`: home stops PA + returns to setup, save = drive report, pause = auto-driver pause).

**Strict separation still holds:** `app.py` just hands the band a sub-surface + the status dict and knows nothing about layout / fonts / colors — only the render module moved (was `auto_input/driver.py::draw_debug_panel`, now `tims/band.py`). The old `draw_debug_panel` + `handle_panel_click` have been **removed** — the band fully supersedes them; the band preview (`_dev_scripts/preview_band_ocr.py`) now carries its own mock fixtures.

### Layout

The live panel's layout (left OCR-state column / centre speed·limit·distance readout / message strips / [pause][save][home] cluster) lives in `tims/band.py` + [docs/APP.md § Persistent status band](../docs/APP.md). It reads the status-dict fields below. The OCR-panel migration DROPPED the old confidence-colour tint (green/yellow/orange OCR-score) — too debug for the public band; the raw Layer-2 badge folds onto the state line instead.

The historical 3-line `draw_debug_panel` layout (ShinGoPr6N @ 14pt, `dep✓ arr·` flags, confidence colours) has been removed — `tims.band.render` is now the sole panel renderer.

### Width adaptivity

The band takes its width from the caller's surface (`surf.get_width()`); `PASimulator` allocates the sub-surface at `S_WIDTH` from the active train model, so the band follows future train models with different LCD widths automatically.

### Status dict (single-writer / single-reader, atomic dict assignment)

`AutoDriver` thread populates `sim.auto_input_status` after each capture:

```python
{
    "badge": "MOVING" | "STOPPED" | "PASSING" | None,
    "badge_diff": float | None,            # template-match diff (lower = better)
    "speed": int | None,                   # km/h, integer (decimal stripped) — drives the band + all decisions
    "speed_decimal": float | None,         # km/h with the tenths (e.g. 5.3) — LOG/report only, never a decision; None-tenths degrades to X.0
    "speed_score": float,                  # OCR confidence 0..1
    "distance": int | None,                # meters to next stop
    "distance_score": float,
    "stopping_offset_cm": int | None,      # cm offset at platform (briefly populated post-arrival)
    "stopping_offset_score": float,
    "speed_limit": int | None,             # km/h speed limit (line-dependent, often empty)
    "speed_limit_score": float,
    "segment_start_stop": int,             # sim.state.curr_stop snapshot at last STOPPED→MOVING
    "departure_observed": bool,
    "arrival_observed": bool,
    "at_station_observed": bool,
    "reentry_pending": str | None,         # "1A"/"1B" = a re-entry target awaiting its second
                                           # agreeing probe; drives the amber "Re-aligning…" chip
    "inferred_state": str,                 # canonical Layer 3 state name (see § "Layer 3" truth table)
    "ts": float,                           # time.time() of capture
    "paused": bool,                        # True when the user has clicked Pause (capture loop idle)
    "last_fire": dict | None,              # {"ts": float, "type": "departure"|"arrival"|"at-station"} — most recent successful auto-fire; panel renders a transient chip when ts is recent
}
```

**Paused-frame variant.** During paused cycles loop preserves prior status dict and overlays only `"paused": True` (no fresh OCR fields). Readers should treat any field that's stale-looking against `paused=True` accordingly.

CPython dict assignment is atomic. No lock needed for single writer (BG thread) + single reader (main thread).

## Sample interval

**3 seconds** (in-process driver `SAMPLE_INTERVAL_S`; user-adjustable 1–10s on the OCR setting page). Trade-off:

- **Tighter** would catch threshold crossings more precisely but burns more CPU and could flood logs with redundant identical reads
- **Wider** would miss events; at 100 km/h train moves ~83m in 3s, so wider sample could miss 900m threshold entirely

3s = good balance for both threshold detection and event cadence.

State machine robust to granularity — `prev_<X>` carries forward between samples, threshold-crossings fire on first sample after boundary crossed.

## Usage

**In-process integration** (the default path):

```bash
# Toggle OCR Auto-PA on the setup screen, adjust Lead (default 900m, ±100m
# steps) and Interval (default 3s, ±1s), then select a route with Enter.
uv run main.py
```

**Separate-process script** (diagnostic / observation):

```bash
# Watch the production read path live — no dumps, quick sanity check
uv run python _dev_scripts/ocr_observe.py --no-dump

# Collect an OCR corpus: full-HUD PNGs + reads.jsonl per sample
uv run python _dev_scripts/ocr_observe.py --interval 0.5

# Force resolution (default = auto-detect from first frame)
uv run python _dev_scripts/ocr_observe.py --res 1080p
```

Each sample dumps the WHOLE HUD region, not individual cells — so an offline sweep can
re-crop at different bboxes to test a crop-geometry hypothesis. A cell-only dump bakes the
suspect geometry into the evidence.

**Offline calibration validation** (no live game required):

```bash
uv run python _tests/t3_invariant/test_ocr_reads.py          # committed fixtures, both resolutions
uv run python _tests/t3_invariant/test_ocr_reads.py --deep   # also re-sweep local _ocr_calibration*/ when present
```

Stop with Ctrl+C. Script prints one line per sample (badge state, speed, distance, scores) plus indented `>>>` lines for state-machine events and auto/manual key activity.

## Files

| Path | Role |
|---|---|
| `auto_input/` | Package — public surface re-exports `AutoDriver`, `generate_report` from `__init__.py`. Internal submodules below. |
| `auto_input/driver.py` | **Primary** — `AutoDriver` class (in-process daemon thread) + `_Detector` state machine + `generate_report()` (drive-report trigger, called by the band Save button). All auto-input logic lives here. |
| `tims/band.py` | **Live OCR panel** — `render(surf, status, sim_state, stops)` draws the shared TIMS status band from the `auto_input_status` dict; returns `{home/save/pause}` hit-rects. `BAND_H` = the panel height (re-exported as `constants.DEBUG_PANEL_HEIGHT`). Shared with the `tims.setup` flow. |
| `auto_input/hud_layout.py` | Resolution profiles + viewport derivation (`_viewport_for` / `_derive` / `profile_for`), the `PROFILES` observed-record, and `DOWNSCALE_PROFILE` (the one 1080p model every capture is read through). The flat 1440p constants at the bottom are the backward-compat tail for the dev tools + extractor. |
| `auto_input/ocr.py` | OCR pipeline + badge classifier; runnable for offline validation (`uv run python -m auto_input.ocr`) |
| `main.py` | Reads `auto_input` / `lead_m` / `interval_s` from setup-screen config dict. Spawns `AutoDriver` when `auto_input=True` and passes same flag to `PASimulator`. |
| `tims/setup/` | OCR Auto-PA launch cluster + Lead/Interval steppers (`pa_setting.py` / `ocr_setting.py`; the retired classic `setup.py` held a toggle pill + steppers under the route list). `_handle_band_click` updates state; selected route's Enter returns config dict including auto-input fields. |
| `app.py` | `PASimulator`: allocates debug sub-surface in `_init_pygame`; `pending_next_pa` flag checked alongside keyboard in `_handle_input_main`; `auto_input_status` dict written by AutoDriver, read by `_render_panel()` which delegates to `tims.band.render`. `MOUSEBUTTONDOWN` events in the panel area go to `_handle_band_click` (band's home/save/pause rects). `drive_log_path` attribute stashes live JSONL path so the report can find it. `run()` returns `"home"`/`"quit"`; band Home → return to setup. **No panel rendering logic lives in app.py.** |
| `constants.py` | `DEBUG_PANEL_HEIGHT` — re-exported from `tims.band.BAND_H` (single source; the band owns its height). |
| `auto_input/sampling.py` | **THE per-cycle read path** — `read_hud()` (crop → 4 readers → 3 guards, in a load-bearing order) + `GuardState` / `Reading` + `downscale_hud()` (HUD → the 1080p model, § "Resolution handling"). Called by BOTH `AutoDriver` and `ocr_observe.py`, so the diagnostic cannot drift from production. Carries a `# CONTRACT:` block on the ordering. |
| `_dev_scripts/ocr_observe.py` | Standalone OCR corpus collector — calls `read_hud`, dumps full-HUD PNGs + `reads.jsonl` (RAW beside GUARDED). Observation only, fires nothing. Always reads through the downscale path, so the corpus describes what production runs. Output split per capture resolution: `_experiments/live_captures/<height>p/<timestamp>/`. |
| `_dev_scripts/test_dxcam.py` | Diagnostic — full-desktop dxcam capture + brightness check |
| `ocr_templates/digits/*.png` | **Runtime input** — 10 pre-extracted digit glyphs (~20×30 binary PNGs). Loaded by `build_templates()`. Reused at all resolutions via NN-resize. Committed. |
| `ocr_templates/digits_red/*.png` | **Runtime input** — 10 red-font digit glyphs at the model's scale (13–16×20 px). Loaded by `build_templates(red_dir)`. Committed. |
| `ocr_templates/badges/*.png` | **Runtime input** — 6 badge cell crops (83×30 RGB) at the model's scale. Loaded by `load_badge_anchors()`. Committed. |
| `_ocr_calibration/*.png` | **Local-only** 1440p source screenshots (~33 MB). Gitignored. Source for `extract_ocr_assets.py`. |
| `_ocr_calibration_1080p/*.png` | **Local-only** 1080p source screenshots. Gitignored. Source for 1080p extraction passes. |
| `_dev_scripts/extract_ocr_assets.py` | One-shot extractor: reads `_ocr_calibration*/` → writes `ocr_templates/` AND the committed T3 test fixtures under `_tests/fixtures/ocr/<res>/` (cells + quadrant frames, per each resolution's `manifest.json`). Run after re-capturing sources, then commit diff. |
| `_tests/t3_invariant/test_ocr_reads.py` | **T3 test** — asserts the production OCR pipeline reads correct values from committed HUD fixtures (badge + speed-limit + stopping-offset), both resolutions, no local calibration needed. Runs at `/build` pre-flight via `run_all.py`. `--deep` also sweeps `_ocr_calibration*/` when present. Replaced the former `validate_ocr.py`. |
| `_tests/fixtures/ocr/<res>/` | **Committed test input** — `manifest.json` (stem → type + expected value, the single ground-truth source), `cells/*.png` (full-coverage cropped cells), `frames/*.png` (capture-region quadrant crops for crop-geometry). ~KB per cell; a few quadrant frames per resolution. |
| `_recordings/drive_<line>_<diagram>_<TS>.jsonl` | **Blackbox / drive recorder log** — one file per AutoDriver lifetime. Line 0 = `_type: "meta"` (route/diagram/dest/stops + `desktop_resolution` / `ocr_profile_resolution` / `ocr_scale` for resolution self-diagnosis); **the sample line is written BEFORE `detector.update()` runs**, so its observed-flags / `at_station` reflect the state the cycle STARTED with — a fire that lands this cycle shows up on the NEXT sample. Offline analysis that forgets this reads a normal departure as a desync; subsequent lines mix `_type: "event"` — two families, **badge transitions** (arrival / departure / passing_start / passing_end) and **diagnostic markers**, log-only, each paired by ts with its sample (`cross_reject` / `score_gate` / `distance_reject` / `offset_reject` / `reentry_1a` / `reentry_1b`) — and `_type: "sample"` (one OCR sample cycle, all OCR fields + sim state including `at_station` / `cnt_pa_at_station` / `at_station_observed` / `reentry_pending` / `inferred_state` / `segment_start_stop`). Written inside `auto_input/driver.py`'s capture loop with per-line `flush()` for crash safety. Local-only / gitignored. Field additions backward-compatible (plot_drive ignores unknowns); field removals or renames require coordinated update with `plot_drive.py`. |
| `_experiments/live_captures/<height>p/<ts>/` | `ocr_observe` dumps, split per capture resolution (gitignored — `_experiments/` is artifact-only). PNGs are the NATIVE HUD crop, not the downscaled one, so a dump can be re-cropped and re-read offline at any geometry. |
| `fonts/ShinGoPr6N-Medium.otf` | Latin + CJK font used by debug panel for station names |

## Adding a new resolution

Downscaling is what makes this short. No calibration screenshots, no template extraction, no per-resolution tuning — the reads happen on the 1080p model whatever the capture size. What is still needed is **where the HUD sits in the frame**, which cannot be derived because it depends on the game's own layout.

1. Usually nothing. `profile_for` already derives every in-scope size, so a new resolution is only worth an entry once someone has *seen* it read — `(w, h): replace(_derive(w, h), verified=True)` in `PROFILES`. Nothing per-resolution is extracted — the templates are the model's, whatever the capture size.
2. Verify the HUD is actually where the profile says. One `ocr_observe` run at that resolution dumps the HUD crop; if the crop is framed correctly the reads follow.
3. Optional but recommended: capture one frame into `_tests/fixtures/ocr/<res>/` with a `manifest.json` (`resolution`, `profile_key`, `source_dir`, `cells`, `frames`) so T3 locks the new geometry. `uv run python _dev_scripts/extract_ocr_assets.py` regenerates the fixture set from the manifest. **A `frames` entry pins the cell bbox it names, and a quadrant holds every cell** — so give a second entry the optional `file` key to re-read a different cell out of a frame another entry already writes, rather than committing a duplicate of the same pixels. `cells` are model-scale only, since there is one template set.
4. `uv run python _tests/t3_invariant/test_ocr_reads.py` — must PASS before committing.

## Limitations

- **Supported resolutions**: any desktop that is 16:9 **or taller** whose fitted 16:9 viewport is 1080p or larger — the game letterboxes into that viewport and the geometry is derived against it. **Evidence tiers matter here:** 16:9 and 16:10 have both been driven; 4:3 / 3:2 are permitted by the same arithmetic but no desktop of that aspect has ever been seen, so they announce themselves at startup as derived. Reads run on the 1080p model whatever the capture size, so nothing per-resolution is extracted; a size absent from `PROFILES` is derived and announced at startup (§ "What a profile means, and what gets interpolated"). Refused, with the driver disabled, on any of three counts: a **viewport below 1080p**; a **width that is not a multiple of 16** (no whole-pixel 16:9 height fits — this is what stops 3240×2160 and 3000×2000, though 2256×1504 passes); or anything **wider than 16:9** (21:9). Each is unmeasured rather than impossible, and refusing beats guessing, because a wrong geometry reads confidently instead of degrading.
- **Primary monitor only**: capture targets the display Windows marks Primary (the primary output is tried first by `_open_capture_camera`). The game must run on the primary monitor, and the **primary monitor's own resolution** must be in scope — a game on a *secondary* monitor is never captured, because the startup probe reads the primary's resolution and disables the driver if it is out of scope. A secondary monitor's placement does not offset the capture (region coords are output-local).
- **Multi-GPU / hybrid graphics**: `_open_capture_camera` enumerates all adapters, so a primary display driven by a non-zero adapter is now found automatically. The unrecoverable case is a Microsoft-Hybrid (Optimus) system whose captured display is owned by the **discrete** GPU — DDA is unsupported against the dGPU by design, every dxgi combo raises `DXGI_ERROR_UNSUPPORTED`, and the driver disables (full traceback logged). User-side workarounds and the winrt fallback: [#97](https://github.com/ksleungac/pids-jre-simulator/issues/97).
- **Game must be visible**: HUD area (top-right) must not be covered.
- **Capture reads whatever is topmost**: alt-tabbing does NOT pause the game, so the run continues while an overlapping window feeds its own pixels to the OCR. A minimized game may also stop rendering and produce stale captures.
- **HUD can be switched off**: the game hides the HUD, or individual rows of it, on a user toggle. OCR then reads nothing — expected behaviour, not a defect.
- **Scenery bleed**: HUD background is semi-transparent; very dark scenery behind reduces match scores (still reads correctly above ~0.7).
- **No station-name OCR**: auto-driver doesn't validate which station the user is at; trusts simulator's `state.curr_stop`. If they desync, manual PageDown is the recovery.
- **Game DRM**: irrelevant to the OCR pipeline (works on legit + cracked installs identically since dxcam reads GPU output regardless of game's startup path).

Priority-ordered backlog lives in [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues) (`auto-input` label). Validation history + design rationale: `git log` + the `memory/` dailies (2026-04-26 → 2026-05-31).

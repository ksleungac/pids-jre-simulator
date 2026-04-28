# WIP — Interactive Lower LCD (click station icon to jump)

**Status**: MVP **unblocked** as of 2026-04-28 evening — STOPPING state shipped (see [memory/2026-04-28.md](memory/2026-04-28.md) "Evening — STOPPING state"). Click-to-jump now lands in STOPPING@target naturally via `jump_to_stop`. App-state behavior settled. OCR-resync subset still open on Q1/Q2.

## Feature scope

Click on a station icon in the lower LCD → jump `curr_stop` to that station. Doubles as manual OCR resync mechanism: when AutoDriver's segment-start anchor desyncs from the simulator's `curr_stop` (route reload, manual jump, OCR misfire), the user clicks the right station and AutoDriver re-anchors via the entry-point flow.

Originating TODO entry: see `TODO.md` § Display / LCD fidelity.

---

## Settled — App-state behavior (no OCR considerations)

### Decisions

1. **Hover**: pointer-hand cursor on station-cell hover. No rendering difference. When mouse is off the LCD, the display looks identical to real PIDS (fidelity preserved).
2. **Misclick**: no confirm gate. Re-click to recover.
3. **Past-dest cells**: not clickable on non-circular routes (cells past `dest_stop_idx`, e.g. Keihin 727B's 磯子→大船 reference tail). Filter sits in the click handler — `jump_to_stop` and preview ←/→ stay unchanged.
4. **Click on currently-active cell**: same effect as any other cell.
5. **Audio on click**: `audio.pause()`, do NOT invoke `_next_pa`. Lifted into `jump_to_stop` itself so preview ←/→ also pauses.
6. **Landing state — SUPERSEDED 2026-04-28 evening.** Old design: `cnt_pa = 0` reset → "次は X" (APPROACHING). New design: `at_station = True` reset → "ただいま X" (STOPPING) — matches the unified state machine's "click means I'm at platform X" semantic. `jump_to_stop` already does this; `_has_pa` predicate updated to accept stops with non-empty `pa_at_station`. Next PageDown plays `pa_at_station[0]` (or advances to next stop if empty).
7. **`pending_next_pa` flag**: not cleared on click. Acceptable corner case (very rare; AutoDriver-only).

### `cnt_pa` semantics — corrected understanding

`cnt_pa` is the **display state label**, not strictly "the PA that was just played":
- Selects the upper LCD prefix (`次は` / `まもなく` / `ただいま`).
- Selects what `_next_pa` does next (within-stop increment vs. advance branch).

The "just played" framing happens to hold during normal advance flow but does NOT hold for init or `jump_to_stop` (no PA actually played, but cnt_pa=0 still puts the display in 次は mode).

### PA list convention (verified against `audio/sobu/1217F/route.json`)

```json
"pa": ["{prev}-dep", "{this}-arr"]
```
- `pa[0] = "{prev}-dep"` — heard mid-segment after departing prev. Plays via `_next_pa` advance branch.
- `pa[1] = "{this}-arr"` — heard approaching this stop. Plays via `_next_pa` within-stop branch.
- `pa[2+]` — out-of-scope concept today. Only behavior today is upper-prefix fall-through to `ただいま`. Don't bake in a "transfer info" interpretation.

### Implementation plan

1. **`JapaneseDisplay.hit_test(x, y) -> Optional[int]`** — full-route view cell math (1-2 row layout).
2. **`JapaneseEightStationDisplay.hit_test(x, y) -> Optional[int]`** — 8-station view (single row, hit area = full vertical column: label + bar + badge).
3. **`LowerDisplay.hit_test(x, y)`** — one-liner: `return self._pick_japanese_renderer().hit_test(x, y) if self._state else None`. ENGLISH falls back to Japanese full-route already.
4. **`PASimulator._handle_lcd_click(pos)`** helper — converts window y to LCD-local (subtract `DEBUG_PANEL_HEIGHT` when `auto_input=True`), calls `hit_test`, filters past-dest, calls `jump_to_stop`.
5. **Wire in two places**:
   - `run()`'s MOUSEBUTTONDOWN handler — add `else` branch for clicks below the debug panel (current branch only handles clicks INSIDE the panel).
   - `_handle_input_preview` — add MOUSEBUTTONDOWN case (preview drains all events).

Net: 4 small additions + 2 wire-up sites. **No AutoDriver changes needed in MVP** — existing `_fire_arrival` mismatch-skip handles single-stop drift correctly.

---

## Settled — OCR state machine vocabulary

### State terminology (use these names, not flag combos)

User's named states (= the autodriver's actual logical states; transitions already implemented in `_Detector`):

1. **STOPPING at station**
2. **MOVING/PASSING (before departure PA)**
3. **MOVING/PASSING (after departure PA / before arrival PA)**
4. **MOVING (after arrival PA)**
5. **STOPPING (next station)**

PASSING variant of the cycle: `STOPPING → PASSING (before dep PA) → PASSING (after dep PA) → MOVING (after dep / before arr) → MOVING (after arr) → STOPPING`.

### Mapping to current detector flag combo (implementation only)

| State | `prev_badge` | `dep_fired` | `arr_fired` |
|---|---|---|---|
| STOPPING at station | STOPPED | * | * |
| MOVING/PASSING (before dep PA) | MOVING/PASSING | False | False |
| MOVING/PASSING (after dep PA / before arr PA) | MOVING/PASSING | True | False |
| MOVING (after arr PA) | MOVING | True | True |
| STOPPING (next station) | STOPPED | * | * |

### OCR observation vs logical state — keep separate

- **Observations** (raw OCR reads): `badge_read ∈ {STOPPED, MOVING, PASSING}`, `speed_read`, `distance_read`.
- **Logical state** (autodriver's semantic conclusion): one of the 5 named states above.

The inference function maps observations → state. Today it's badge+speed (+ maybe distance for States 3/4). Future cross-attribute hardening enriches this function without changing the entry-point interface.

**Single-PA stop confirmation**: detector emits `FIRE_ARRIVAL` for single-PA stops (sets `arrival_fired=True`); dispatcher `_fire_arrival` skips actual PA playback (line 631: `if pa_count <= 1: SKIPPED`). Debug bar shows `dep✓ arr✓` for both single- and multi-PA stops — flags track detector state, not audio playback.

### LCD note (insight from this discussion)

~~The simulator's display does NOT have a separate "STOPPING at station" state in its display logic~~ — **2026-04-28 evening: this gap is now closed.** STOPPING is a real state on `AppState.at_station`; lower LCD renders the pentagon at curr_stop's cell when set; upper LCD prefix becomes "ただいま X." States 1 (fresh STOPPING) and 5 (STOPPING after arrival) still collapse to the same display (no info distinguishes them on the LCD), so anchor logic still treats them as interchangeable.

---

## Settled — Entry-point design

### Concept

Single procedure used at:
- AutoDriver startup (replaces today's blind `_segment_start_stop = sim.state.curr_stop` at `auto_input.py:503`).
- Resync after any unexpected `curr_stop` change.

### Procedure

1. **Mute** — no events fire while in entry-point mode.
2. **Probe sliding window** — each probe yields a logical state via the inference function. Keep probing until 2 consecutive probes agree on the same logical state.
3. **Anchor** based on confirmed state + current `sim.state.curr_stop = X`:

| Detected state | `_segment_start_stop` | `dep_fired` | `arr_fired` |
|---|---|---|---|
| STOPPING at station | curr_stop (= X) | False | False |
| MOVING/PASSING (before dep PA) | X − 1 | **False** | False |
| MOVING/PASSING (after dep PA / before arr PA) | X − 1 | True | **False** |
| MOVING (after arr PA) | X − 1 | True | True |
| STOPPING (next station) | curr_stop (= X) | False | False |

4. **Exit entry point** — resume normal event flow.

### Triggers (lean yes for all three)

- Initial AutoDriver toggle ON.
- Click-jump (sim's `curr_stop` changed unexpectedly).
- Manual PageDown (same — any AppState change autodriver didn't initiate).

### Detection of "unexpected curr_stop change"

Simplest: AutoDriver tracks last-known `curr_stop`. If it differs from current and not from its own `pending_next_pa` fire, invoke entry point. (Confirm at resume.)

### Inference function (today)

| Observation | Logical state |
|---|---|
| `badge=STOPPED` | STOPPING at station |
| `badge ∈ {MOVING, PASSING}` + `spd<30` | MOVING/PASSING (before dep PA) |
| `badge ∈ {MOVING, PASSING}` + `spd≥30` | (post-dep) — State 3 or 4, see Q2 |

---

## Open questions (paused here)

### Q1 — State 2 entry's dep-PA loss: accept, or fix dispatcher?

State 2 entry sets `segment_start_stop = X − 1`, `dep_fired = False`. When speed later crosses 30, detector emits `FIRE_DEPARTURE`. Dispatcher's `_fire_departure` checks `curr == segment_start`; with `curr = X` and `segment_start = X−1` they mismatch → SKIPPED. Dep PA is lost for this segment.

Options:
- **(a)** Accept the loss. State 2 is rare and transient (~10–30s acceleration window). User manually fires dep PA. Simplest.
- **(b)** Add post-jump branch to dispatcher: `if curr == segment_start + 1 AND cnt_pa == 0`, play `pa[0]` of `curr_stop` directly (no `_next_pa` advance, since cnt_pa is already at 0). Recovers dep PA.
- **(c)** Use `cnt_pa = -1` sentinel for State 2 entries. (Reintroduces a foreign sentinel for one specific case — likely not worth it.)

Lean **(a)** for MVP simplicity; **(b)** if dep replay matters in practice.

### Q2 — State 3 vs State 4 disambiguation

With badge + speed alone, States 3 and 4 are indistinguishable (both `badge ∈ {MOVING, PASSING}`, `spd≥30`). Distance disambiguates: `dst > lead → State 3`; `dst ≤ lead → State 4`.

Options:
- Add distance to inference.
- Accept ambiguity today (default to State 3 → accept potential double-fire of arr for State 4 clicks).

### Q3 — Probe disagreement during 2-probe consensus

If probe 1 and probe 2 disagree on logical state:
- **Sliding window**: probe 3 must agree with probe 2; if so, confirm. (Lean — catches up faster if state genuinely changed mid-resync.)
- **Reset**: discard prior probe, start fresh.

### Q4 — PASSING vs MOVING during entry-point anchor

Lean **same anchor** for PASSING and MOVING in-transit states (both treated as "in transit"). The PASSING-specific gating (arrival check off when badge=PASSING) happens during normal event flow afterward, not at anchor time. Confirm.

---

## When picking up next

- Resolve Q1 (dep-PA loss accept/fix).
- Resolve Q2 (State 3/4 distance disambiguation).
- Confirm Q3 (sliding window) and Q4 (PASSING anchor).
- Decide what ships in MVP vs defers (likely: ship app-state-only first, OCR resync as follow-up).
- Then implement.

## Cross-references

- App-state convention: `app.py` `AppState`, `jump_to_stop`, `_next_pa`.
- Detector + dispatcher: `auto_input.py` `_Detector`, `AutoDriver._fire_departure`/`_fire_arrival`.
- Renderers: `displays/train_models/e235_1000/lower_lcd.py` `JapaneseDisplay` + `JapaneseEightStationDisplay`.
- Click event plumbing: `app.py` `PASimulator.run` MOUSEBUTTONDOWN handler + `_handle_input_preview`.
- Future cross-attribute hardening: `TODO.md` § Auto-input/OCR "Cross-attribute hardening, when needed."

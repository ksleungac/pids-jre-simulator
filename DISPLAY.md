# LCD Display System — Cross-Model Infrastructure

Modular per-train-model architecture for both Upper and Lower LCDs. This doc covers **cross-model** layer: factory dispatch, mode system, unified state machine, lower-LCD interface contract, recipe for adding new train models. Per-sub-series renderer specifics live in per-series docs (see [Per-series displays](#per-series-displays) below).

Train-family scope and in-spec/best-effort policy live in [CLAUDE.md](CLAUDE.md) "Mental Model" (preloaded — should already be in head). JSON shapes → [DATA_FORMAT.md](DATA_FORMAT.md). Cross-cutting code contracts live inline at code sites (font-loading at first font init in each model's `upper_lcd.py`; countdown formula at `lower_lcd.py` `draw_times`; PyInstaller path resolution at [`app_paths.py`](app_paths.py) `project_root`).

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** cross-model invariants — factory dispatch, mode-cycler contract, unified-state-machine spec, lower-LCD interface (state injection + skip animation + terminus handling) every train-model implementation must satisfy, and recipe for adding a new train model.
>
> **Refuses:**
> - Per-sub-series renderer details (E235-1000's linear bar, E235-0's circular full-route, transfer-info pipeline) — those live in [DISPLAY_E235.md](DISPLAY_E235.md) and future per-series docs
> - History notes / change logs (`### 2026-03-14`, "pre-X behavior", "Key Changes from legacy …") — `git log` has this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future sections ("When X is implemented, …") — defer until needed; GitHub Issues is the home for pending designs
> - Design-discussion rationale (multi-paragraph framings of *why* a model exists) — the rule lives here; the rationale lives in `memory/YYYY-MM-DD.md`
> - Facts already in [CLAUDE.md](CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Voice:** new reference-shaped entries (cross-model invariants, contracts, recipes, mode-system rules, state-machine spec, edge-case tables) — caveman-full voice (drop articles, fragments OK, `=` for definitional equivalence). Rationale-shaped passages (incident warnings, "Mental model:" framings, narrative examples) — stay normal voice. See [CLAUDE.md § Chat output style](CLAUDE.md).
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](.claude/rules/principles.md).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Registry Layer (displays/)                                 │
│  - get_train_model() returns a model's display classes      │
│  - DisplayMode enum (KANJI, FURIGANA, ENGLISH)              │
│  - ModeCycler (handles mode switching timing)               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Train Model Layer (displays/train_models/{model}/)         │
│  - UpperDisplay (manager)                                   │
│  - LowerDisplay (manager)                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Mode Renderer Layer                                        │
│  - upper_lcd.py: JapaneseDisplay / FuriganaDisplay /        │
│                  EnglishDisplay                             │
│  - lower_lcd.py: per-model renderers (full-route +          │
│                  zoomed view + transfer-info + ENGLISH      │
│                  placeholder)                               │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
displays/
├── __init__.py              # Package entry point: DisplayMode, ModeCycler, get_train_model
├── base.py                  # DisplayMode (IntEnum: KANJI=0, FURIGANA=1, ENGLISH=2), ModeCycler,
│                            # ChangeScheduler + the beat schedule (beats(), *_BEATS)
├── lower_lcd.py             # Parent LowerDisplayBase: slot cycle, transfer force-switch,
│                            # through-service frame swap — the scheduler's contract
│                            # (concrete renderers are per-model)
├── utils.py                 # Shared helpers: draw_station_code_badge, draw_route_disclaimer,
│                            # draw_text_given_width, draw_1col_text, draw_1col_text_plain,
│                            # arrow_points
├── transfer_info.py         # Parent TransferInfoDisplay (state binding, transfers_by_view,
│                            # variant resolution) — concrete renderers are per-model
└── train_models/
    ├── __init__.py          # Model registry: TRAIN_MODELS, get_train_model(), model_choices()
    ├── e235_1000/
    │   ├── __init__.py      # Per-model manifest: S_WIDTH, S_HEIGHT, UPPER_HEIGHT, palette;
    │   │                    # exports UpperDisplay, LowerDisplay
    │   ├── upper_lcd.py     # JapaneseDisplay, FuriganaDisplay, EnglishDisplay, UpperDisplay
    │   ├── lower_lcd.py     # JapaneseDisplay (linear full-route),
    │   │                    # JapaneseEightStationDisplay, EnglishDisplay,
    │   │                    # LowerDisplay
    │   └── transfer_info.py # E235-1000 concrete render_transfer
    └── e235_0/
        ├── __init__.py      # Per-model manifest; exports UpperDisplay, LowerDisplay
        ├── upper_lcd.py     # E235-1000 fork minus train-type cell
        └── lower_lcd.py     # CircularFullRouteDisplay (Yamanote);
                             # LowerDisplay subclass swapping FULL slot when route=山手線
```

### Naming Conventions

| Level | Pattern | Example |
|-------|---------|---------|
| Train model | Directory: `snake_case` | `e235_1000/`, `e235_0/`, future `e231_500/` |
| Display section | File: `{section}_lcd.py` | `upper_lcd.py`, `lower_lcd.py` |
| Mode renderer | Class: `{Mode}Display` | `JapaneseDisplay`, `EnglishDisplay` |
| Manager | Class: `{Section}Display` | `UpperDisplay`, `LowerDisplay` |

No redundant prefixes in class names (e.g., `JapaneseDisplay` not `E235_1000JapaneseDisplay`) — each train model has its own directory scope.

---

## Mode System

### DisplayMode + ModeCycler

`DisplayMode` (in `displays/base.py`) = IntEnum: `KANJI=0`, `FURIGANA=1`, `ENGLISH=2`. `ModeCycler` (same file) holds the current mode + its timer. It does **not** tick itself — it exposes `is_due(now)` / `advance(now)` and `ChangeScheduler` drives both (see § Change scheduler). Cadence = `LANGUAGE_BEATS` (1 beat = 4s). Cycler keeps `enabled` flag for freezing on a forced mode.

### Cycler Sharing Between Upper and Lower

**One cycler, shared.** Upper owns it; lower receives it as constructor argument:

```python
self.upper = UpperDisplay(screen, route_data, stops)
self.lower = LowerDisplay(screen, route_data, stops, self.upper.mode_cycler)
```

Keeps modes in lockstep without parallel timer (no drift, no re-tick). When upper switches to ENGLISH, lower switches with it. Default mode + `enabled` flag controlled from upper side; the cadence and the actual ticking belong to `ChangeScheduler`.

### Cycling Behavior

| Time | Mode | Prefix | Station Name |
|------|------|--------|--------------|
| 0–4s | KANJI | 次は | 東京 |
| 4–8s | FURIGANA | つぎは | とうきょう |
| 8–12s | ENGLISH | Next | Tōkyō |

**Graceful fallback:** if station lacks furigana or English data, that mode skipped in cycle.

### Stop data keys vs DisplayMode enum

Stop data = plain dict (merged from `route.json` + `data/translations.json`) — keys are **strings**: `"name"`, `"english"`, `"furigana"`. `DisplayMode` = internal **enum** tracking which mode active. Use string keys for stop lookup (`stops[i].get("english")`) — `stops[i].get(DisplayMode.ENGLISH)` silently returns `""` because enum value isn't a dict key.

Naming alignment between `"english"` (data) and `DisplayMode.ENGLISH` (state) intentional but bridging happens at manager layer (`UpperDisplay`/`LowerDisplay`), not via direct lookup.

### Mode Mapping (Lower-Specific)

Shared cycler ranges over KANJI / FURIGANA / ENGLISH. The `LowerDisplay` manager reads the active language mode from the cycler and passes it to its internal `_pick_renderer(mode)` method.

- For KANJI and FURIGANA, it dispatches to the Japanese full-route or 8-station views.
- For ENGLISH, it dispatches to the `EnglishDisplay` (or falls back to the Japanese 8-station view if a specialized English zoomed view isn't implemented). 

Because the lower display has its own internal state machine for alternating between FULL and EIGHT station views (the "slot cycler"), it uses dynamic dispatch (`_pick_renderer`) rather than a simple dictionary map.

### ⚠️ Cycler.enabled vs Cycler.paused

ModeCycler has `enabled`, **not** `paused`. To freeze a forced mode (e.g. in preview scripts), set `cycler.enabled = False`. Assigning to `paused` silently creates a new attribute that `is_due()` never checks — the forced mode will un-freeze after the cadence elapses. This has burned us before.

To freeze the language AND the lower's slot together, set `scheduler.enabled = False` — one switch for both axes (what `preview_display.py --lower-view` uses).

---

## Change scheduler

`ChangeScheduler` (`displays/base.py`) is the single owner of every discrete view change. Constructed in `app.py` beside upper/lower; ticked once per frame from the main loop, after `update_skip_progress` (slot membership reads `cursor_pos`) and before both draws.

**Change** = discrete visible mutation: language flip OR slot rotation. Continuous content (clock, countdown, skip / breath / band-fill animation) is not a change — renders every frame, untouched.

**But continuous content still needs a discrete TRIGGER owner.** A reveal/sweep that renders every frame (the E235-0 5-station band fill) restarts on a slot-enter — and that restart is a discrete event, fired from `LowerDisplayBase.apply_slot` (the sole slot-commit funnel, on a genuine `slot != _current_slot` enter), never self-detected by the renderer from a wall-clock draw-gap. Inside a pure renderer a draw stall (a window move freezes the main thread) is indistinguishable from a real re-enter, so a gap heuristic false-restarts on any stall — and coincidentally on a stopped→moving marker flip. Keeping the trigger on the scheduler side is what lets `draw()` stay pure. Per-sub-series instance: DISPLAY_E235.md § "E235-0 — 5-station stopping view".

### The schedule is authored in BEATS

1 beat = `constants.BEAT_SECONDS` (4s) = the language cadence. Every duration is a whole beat count via `displays.base.beats(n)`, which rejects anything else:

| element | beats | seconds | where |
|---|---|---|---|
| language | 1 | 4s | `base.LANGUAGE_BEATS` |
| change floor | 1 | 4s | `base.CHANGE_FLOOR_BEATS` |
| FULL / EIGHT | 3 | 12s | `LowerDisplayBase._SLOT_BEATS` |
| TRANSFER | 2 | 8s | same |
| swap hold | 3 | 12s | `_SWAP_HOLD_BEATS` |
| restart logo | 1 | 4s | `_TRANSITION_BEATS` |

**Why beats, not seconds** — an off-grid duration silently defers to the next allowed moment, so the number in the source stops describing the screen. Whole beats make written == observed by construction; rationale at `displays/base.py` module docstring.

**Language coverage** — every (slot, language) pairing must surface eventually; there is NO requirement that one appearance of a slot spans all three languages. FULL / EIGHT dwell 3 beats = exactly the 3-language cycle, so each surfaces in every language within one appearance (the default out-of-window round trip is 3+3 = 6 beats, an exact multiple of the cycle — their starting language never rotates and doesn't need to). TRANSFER at 2 beats can't span the cycle; what covers it is the in-window round trip of 3+3+2 = 8 beats, not a multiple of 3, so its starting language rotates across successive cycles.

### The floor

After any change, no change of any kind for `CHANGE_FLOOR_BEATS`. At exactly one beat it doubles as the quantizer: an off-grid slot dwell defers to the next beat rather than landing mid-interval, so the rhythm is uniform without constraining what may be written.

It deliberately does **not** sit below the cadence — safe only because evaluation is atomic. Rationale (the starvation trap a below-cadence floor was dodging) lives at the constant: `displays/base.py` `CHANGE_FLOOR_BEATS`.

> **CONTRACT — one atomic tick per frame.** Both axes evaluate against the SAME frame-start `last_change` snapshot and apply together as one batched event, stamping `last_change` once. NOT a shared `last_change` consulted independently by upper and lower — that is exactly the starvation trap above. A due-but-blocked change is never queued: due-ness recomputes from timestamps every frame and applies on the first frame the floor allows.

### Change flavors

- **Scheduled** — a per-axis cadence elapsed. Deferrable by the floor.
- **Reactive** — current slot left `_available_slots`. *Layout-invalid* (FULL after the eight-lock engages) still renders coherently → deferrable. *Content-invalid* (TRANSFER at a station that lost its transfers) would show a blank panel → treated as Preemptive, never held.
- **Preemptive** — intent-driven, immediate, bypasses the floor and re-anchors it: the STOPPING force-switch to TRANSFER (also fired by a cross-stop jump onto a transfer-bearing stop — same rising edge), content-invalid reconcile, the restart-logo reveal, and a position change that cancels the logo. The stop force-switch fires at every stop and re-anchors the language off its cadence — accepted, transfer info must show at once. Plain paging is NOT preemptive: `_advance_to_next_stop` clears `at_station`, so no edge fires and the slot rotates on cadence.

### Restart logo

While `lower.transition_active`, the scheduler applies no discrete change — the screen is a static logo, and a slot mutating out of sight would flash the instant it cleared. At logo-clear it fires one Preemptive: reveal the new frame's default slot AND restart its dwell. The restart matters even when the slot is unchanged — slot timers are wall-clock, so the logo burns dwell invisibly; without it the new segment's opening view expired after one floor instead of its full 3 beats.

The swap fire is the one Preemptive that is **predictable** (fixed timer from the arm), so the scheduler goes quiet for one floor before it via `lower.seconds_until_swap` — otherwise a rotation lands a frame before the logo covers it.

Invariants pinned by `_tests/t3_invariant/test_change_scheduler.py` (schedule-as-spec, floor, atomic batching, boot seed, Preemptive bypass + re-anchor, logo quiet + reveal, pairing coverage).

---

## Unified State Machine

Every stop follows two-sub-state cycle: APPROACHING (`at_station=False`) → STOPPING (`at_station=True`) → next stop's APPROACHING → ...

State lives on `AppState` (`at_station: bool`, `cnt_pa: int`, `cnt_pa_at_station: int`). Transitions all happen in `app.py` `_next_pa` and its helpers `_next_in_approaching` / `_next_in_stopping` / `_advance_to_next_stop`.

### Press flow per stop

| Sub-state | Press behavior | Audio |
|---|---|---|
| `at_station=False`, `cnt_pa < len(pa)-1` | Within-pa: `cnt_pa += 1`, play next | `pa[cnt_pa]` |
| `at_station=False`, pa exhausted | **Enter STOPPING**, prefix flips to "ただいま" | none |
| `at_station=True`, more `pa_at_station` left | In-STOPPING: `cnt_pa_at_station += 1`, play next | `pa_at_station[cnt_pa_at_station]` |
| `at_station=True`, `pa_at_station` exhausted | **Exit via advance**, lands in APPROACHING@next | next stop's `pa[0]` |

Press counts to fully traverse a stop (advance-into → STOPPING → advance-out): 1-PA stop = 3 presses, 2-PA stop = 4 presses, stop with N pa_at_station entries = `len(pa) + 1 + N + 1` presses.

### Boot state

`AppState.__init__` defaults to `at_station=True`, `cnt_pa_at_station=-1`. So `curr_stop=0` boots into STOPPING — train parked at start platform, no advance-into has happened. First press either plays `pa_at_station[0]` (if non-empty) or advances directly to idx 1.

### Prefix mapping

`UpperDisplay.set_state(curr_stop, cnt_pa, at_station)` resolves prefix as:

| State | Prefix (KANJI) | Furigana | English |
|---|---|---|---|
| `at_station=True` | ただいま | ただいま | Now stopping at |
| `cnt_pa == len(pa) - 1` (final approach PA) | まもなく | まもなく | Arriving at |
| otherwise (`cnt_pa < last`) | 次は | つぎは | Next |

`at_station=True` = **only** path to "ただいま" — overrides cnt_pa-based mapping. All at-platform PAs belong in `pa_at_station`, never in `pa[]`.

**Final-approach rule.** Only LAST entry in `pa[]` flips prefix to "まもなく"; intermediate approach announcements (e.g. pa[1] of a future 3-PA stop) stay on "次は."

### `jump_to_stop` semantic

Click-to-jump (preview ←/→, future click-to-jump on lower LCD) lands in STOPPING@target. Mental model: clicking a station cell means "I'm at platform X." Next press cycles `pa_at_station` or advances, matching the rest of STOPPING. Implementation in `app.py` `jump_to_stop` — sets `at_station=True`, resets `cnt_pa_at_station=-1`, plus all the existing housekeeping (skip, departure_time, cnt_sta).

`_has_pa` predicate (used by `jump_to_stop`'s passing-station roll) accepts stop with non-empty `pa` OR non-empty `pa_at_station` as valid landing target. Stops with both empty treated as passing stations and rolled past.

### Circular loop-back

Yamanote-style routes have same station name at idx 0 and idx N. Duplicate idx 0 = structural marker for circularity, not a state to visit mid-loop. `_advance_to_next_stop`'s loop-back branch jumps `idx N → idx 1` directly, plays `pa[0]` of new stop, lands in APPROACHING.

### Skip animation

Skip animation lives in `_advance_to_next_stop`. Entering STOPPING and cycling pa_at_station don't touch skip state — by the time STOPPING entered, train has already arrived (skip = whatever previous advance left it at, with skip_progress catching up to skip via `update_skip_progress`). Within-pa branch zeros skip on every press as defensive catch-up. See [Lower LCD — Cross-Model Interface § Station Skip Logic](#station-skip-logic-full-spec) below for full contract.

### Edge cases & guards

**Audio-playing guard.** `_next_pa` early-returns when `audio.is_playing()` — both manual PageDown and `pending_next_pa` from auto-driver dropped while audio plays. `jump_to_stop` does NOT honor this guard; instead calls `audio.pause()` itself before mutating state, so callers (preview ←/→, click-to-jump) get clean handoff without doing their own pause.

**`cnt_pa` is dead during STOPPING.** Naturally-entered STOPPING (via `_next_in_approaching`'s "pa exhausted" branch) leaves `cnt_pa` at `len(pa)-1`. `jump_to_stop`-entered STOPPING forces `cnt_pa=0`. Both render "ただいま X" because `at_station` overrides prefix mapping. `cnt_pa` not read again until `_advance_to_next_stop` resets it to `0` on exit.

**Terminus (non-circular).** `STOPPING@dest_stop_idx` = stable end-state — pressing PageDown falls through `_advance_to_next_stop`'s final `else: return` (neither `curr_stop < terminus_idx` nor `circular == 1` is true). Silent no-op, no state change.

**`pa=[]` with non-empty `pa_at_station`.** `_is_stopping` accepts either non-empty, so advance lands such a stop in APPROACHING with `cnt_pa=0`, then calls `audio.play_pa(curr_stop, 0)` which silently returns at `audio.py:73` (`pa_index >= len(pa_tracks)`). Display flashes "次は X" with no audio for one press until user presses again to enter STOPPING. No known route data hits this today, but `_has_pa` tolerates it.

---

## Code Style Conventions

- **Position constants inlined** as local variables in each draw method (e.g. `box_x, box_y = 15, 8`). Different train models may need different layouts; per-method positions make that explicit.
- **Fonts shared** as class members defined in `__init__` (e.g. `self.font_type_bold`). Fonts consistent within a model.
- See [conventions.md § "Tuneable-params block"](.claude/rules/conventions.md) for project-wide rule on labeled-local-variables at top of every draw method.

### Mode Renderer Design

Each mode renderer (`JapaneseDisplay`, `FuriganaDisplay`, `EnglishDisplay`) = **self-contained**: owns its fonts, layout, full set of draw methods. ~90% similarity across renderers acceptable — different train models may need to diverge freely without reaching into wrong layer. Canonical shape: `JapaneseDisplay` in `upper_lcd.py` (fonts loaded once in `__init__`, position constants inline per draw method).

### Centering Text Across Fonts

Use `surface.get_bounding_rect()` — returns tight visible-pixel bounds. **Do NOT** use `font.get_size()` / `surface.get_size()` for tight centering — those include font leading, which varies significantly per font (Frutiger's leading much larger than Helvetica's at same pt size), breaking alignment when swapping fonts.

Canonical example: `UpperDisplay._draw_station_code_badge` centers two text rows of different sizes inside small badge, reactive to any font choice.

For **horizontal centering inside fixed-width cell** (e.g. passing-station chevron in lower LCD): use `(cell_w - element_w) // 2` for true center. Don't copy magic-number approximations like `stops_w * 0.3` — that constant happens to work for full-route's narrow cells (~1 px off true center) but is ~8 px off in 8-station view's wide cells.

---

## Lower LCD — Cross-Model Interface

Contract every train model's `LowerDisplay` must satisfy. Per-sub-series renderer specifics (linear full-route, circular full-route, 8-station, transfer-info pipeline, continuity arrows, layout/centering tables, `draw_times` subtleties) live in per-series docs.

### State Injection & Skip Animation

Lower needs more per-frame state than upper (cursor_pos, skip, skip_progress, time_to_next, departure_time, frame_mode, is_last_pa). API mirrors upper's `set_state` / `update` / `draw`, but `set_state` binds AppState reference rather than copying fields. Called once at app startup; subsequent draws read live state from bound reference. `update(current_time)` = no-op (cycler shared with upper); `draw(current_time)` dispatches to whichever mode renderer cycler points at.

### Station Skip Logic (full spec)

**Single source of truth**: `state.curr_stop` = only stored "where is the train" index. Visual cursor on lower LCD derived: `state.cursor_pos = curr_stop - max(0, skip - skip_progress)`. When no skip in flight (`skip == 0`), `cursor_pos == curr_stop`.

**Skip setup happens in `app._next_pa`'s "advance to next stop" branch** (not in lower-LCD renderer):

- Records `prev_stop = curr_stop`, advances `curr_stop` past passing stations to next PA station.
- Sets `skip = curr_stop - prev_stop - 1` (number of passing stations crossed), `skip_progress = 0`, `time_to_next = stops[curr_stop].time` if `skip > 0`.
- First frame after this: `cursor_pos = curr_stop − skip` = first passing station. Cursor visibly steps onto it.

**Time-based progression**: `AppState.update_skip_progress` increments `skip_progress` at thresholds `time_to_next * i / (skip + 1)`. `cursor_pos` auto-advances because derived. No `curr_stop_disp` mutation. Called from main loop in `app.run()` *before* drawing each frame — keeps lower display pure rendering.

**Catch-up at next PA tick**: `_next_pa`'s "next PA within current stop" branch zeros `skip` / `skip_progress` / `time_to_next` on every `cnt_pa` increment. Cursor snaps to `curr_stop`. Idempotent — no-op if skip already 0.

**No leak class possible**: "advance" branch *overwrites* skip from gap (not appends), "within stop" branch unconditionally zeros it. No separate "flush" path that could leak.

**Inner circle**: drawn at `curr_stop` (PA target) via `gi == self.state.curr_stop` in `draw_marks`. During skip animation `cursor_pos` lags behind by `skip - skip_progress` — intentional: pointer (red triangle) shows animation position; inner dot shows actual PA target.

**State fields**: `skip`, `skip_progress`, `time_to_next` — three integers fully describe animation. `cursor_pos` = property on `AppState`, not stored.

**Call order in `app.run()`** — renderer stays pure-read so a future English lower won't need to re-implement skip:

```python
self.state.update_skip_progress(timestamp)
self.scheduler.tick(timestamp, self.state)   # every discrete change, atomically
self.upper.draw(...)                          # pure renderers from here
self.lower.draw(timestamp)
pygame.display.flip()
```

### Position-locked views always show the pointer

Any lower-LCD view whose window is locked to the train's position (E235-1000 8-station, E235-0 5-station / circular / open-horseshoe — every renderer that re-centres on the train) MUST render the train pointer in every frame. **Every stop-count / window / lock consideration keys on `cursor_pos` (the VISUAL train position), never `curr_stop` (the skipped-ahead PA target).** A departure that skips passing stations advances `curr_stop` several cells ahead while `cursor_pos` animates across them; keying a window or lock threshold on `curr_stop` snaps it to the tail before the visible cursor arrives, pushing the pointer out of view. Key on `cursor_pos` and the pointer stays visible throughout.

**Scope — the active frame.** The invariant applies to whichever frame is *active* (the one containing the train's position). For a through-service route the junction station is **shared** between adjacent frames, so a train parked at a junction sits at index 0 of the incoming frame — the leading-frame hold (a fired swap shows frame N+1 while still parked at the junction — see [Through-Service Display Frames](#through-service-display-frames)) therefore still renders the pointer, at the junction station. There is no active frame without a train icon.

### Terminus (`dest_stop_idx`)

Non-circular routes terminate at route-level `dest`, not at `len(stops) - 1`. Some route data (e.g. Keihin 727B) extends past operational dest for through-running reference — Keihin 727B's dest is 磯子 (index 40) but stops continue 41..45 to 大船 to capture the through-running segment.

`PASimulator.__init__` resolves `self.dest_stop_idx` once by name-matching `self.dest` against `self.stops`. `_next_pa` computes `terminus_idx = self.dest_stop_idx` (non-circular) or `len(self.stops) - 1` (circular — duplicate-name first-match would be wrong otherwise, but circular routes use loop-back branch so doesn't matter).

---

## Through-Service Display Frames

A through-service route (one physical train across multiple operational segments) partitions its station list into ordered display **frames**. Lower LCD renders only the frame holding the train; swaps at the junction with a restart screen. Plain route = one implicit frame = legacy behavior (no `frames` key — byte-identical to pre-frames). Authored schema → [DATA_FORMAT.md § frames](DATA_FORMAT.md). Per-model restart transition → [DISPLAY_E235.md](DISPLAY_E235.md).

### Active-frame windowing

Each frame = window `[from_idx … to_idx]` over combined `pre_stops + stops` (loader closure, `route_loader._resolve_frames`). The renderer reframes each frame to look EXACTLY like a standalone `pre_stops` route — so existing pixel code handles it unchanged; only WHAT list/offset is fed in changes. Lives in `_FrameWindowMixin` (mixed into both lower-LCD view classes):

- `display_stops` = frame's slice; layout recomputed against it (`_relayout`).
- `display_offset` = always-passed prefix length WITHIN the frame = `max(0, min(to_idx+1, len(pre_stops)) - from_idx)`. Frame 0 keeps the pre_stops prefix; later frames start fresh at 0.
- `_frame_sim_base` = frame's first simulated `stops[]` index = `max(0, from_idx - len(pre_stops))`. Maps sim → frame-local display index: `curr = state.curr_stop - _frame_sim_base + display_offset`.
- `_frame_global_lo` = frame's first cell global index; lets continuity compare a window's GLOBAL position against the full route.

Legacy (no `frames`): `_frames_view` None, `_frame_sim_base = 0`, `display_stops` = whole list.

### Frame selection + swap timing

Active frame = first frame whose global window contains the train (junction = shared boundary belongs to the EARLIER frame). Single resolver: `LowerDisplay._natural_frame` (on the route closure's `frames`). The manager pushes the resulting (lag-adjusted) index into the renderer via `set_active_frame`; renderers never derive their own frame.

`LowerDisplay` owns the swap (it sees the view-cycle) and pushes the lagging frame index into the active renderer via `set_active_frame`:

- **Armed** at STOPPING@junction (`at_station` + position == active frame's `to_idx`, frame has a successor).
- **Held** for a fixed `_SWAP_HOLD_BEATS` (3 beats = 12s) — decoupled from the view-cycle. The hold's purpose: signal the train is stopped at the frame boundary AND give the junction's exchange (transfer) info time to read (the STOPPING edge force-switches to the TRANSFER slot, so it shows immediately). NOT "exhaust every page."
- **Fires**: advance `_active_frame_idx`, start the restart transition. Frame now LEADS position (shows frame N+1 while train still parked at the junction) — held until the train departs.
- **Jump / backward / fast-page** → resync to the natural frame, disarm, cancel any restart.

### Continuity at a frame boundary

A non-final frame's right edge (the junction) is a continuation, NOT a terminus — but the frame slice makes the renderer read it as the route end. Continuity checks therefore compare the window's GLOBAL position against the FULL route, not the slice:

- 8-station: `route_continues = (_frame_global_lo + last_gi) < len(_full_display_stops) - 1`. Reduces to the original `last_gi < len(display_stops) - 1` for legacy.
- Full-route: `_get_stops_list_disp` sets the tail slot (slot 2 two-row / slot 0 single-row) from the SAME comparison — `_frame_global_lo + window_last < len(_full_display_stops) - 1`. Symmetric with 8-station; no draw-side override.
- **Drawing fix (8-station)**: when the train stops ON the last visible cell, `draw_times` skips that cell's 分-area, so the continuity triangle would float past the red pentagon. The 分-area bar extension is painted before the pointer (pentagon overdraws it) so the triangle always connects to the route bar.

> **Pending IRL verification**: continuity arrow at the screen-edge / row-end case (full-route chevrons + 8-station triangle) when a frame boundary lands at a row end — see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues).

---

## Adding New Train Model

1. Create `displays/train_models/{model_name}/` directory.
2. Copy and modify `upper_lcd.py` for fonts/positions (often a fork from sibling sub-series — see [conventions.md § "Display module structure"](.claude/rules/conventions.md) for copy-don't-reinvent rule when forking).
3. Implement `lower_lcd.py` with `LowerDisplay`. Subclass existing model's `LowerDisplay` and override only the slot renderer that differs (precedent: E235-0 subclasses E235-1000 and swaps only FULL slot's renderer when route is Yamanote).
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay` + per-model dimensions/palette (`S_WIDTH`, `S_HEIGHT`, `UPPER_HEIGHT`, `DARK_BG`, `WHITE_BG`).
5. Register in `displays/train_models/__init__.py` — import the package and add a `TRAIN_MODELS` entry (key = folder name = the route.json `model` value):

   ```python
   from displays.train_models import e233_0   # alongside the existing models
   TRAIN_MODELS["e233_0"] = TrainModel(
       "e233_0", "E233-0", e233_0.UpperDisplay, e233_0.LowerDisplay, e233_0.S_WIDTH, e233_0.S_HEIGHT
   )
   ```

   The model then appears automatically in the setup-screen per-route dropdown (`model_choices()`); any route defaults to it via its route.json `model` field (see [DATA_FORMAT.md § Route-Level Fields](DATA_FORMAT.md)). `app.py` instantiates the registered classes from the `model` constructor arg — no `app.py` edit needed.

6. Add per-series doc (`DISPLAY_{MODEL}.md`) for sub-series-specific renderer rules. Cross-reference from [Per-series displays](#per-series-displays) below.

Per [CLAUDE.md](CLAUDE.md) "Mental Model → Per-model IRL line scope": new model's IRL line scope determines which routes need full-fidelity behavior; everything else best-effort.

### Usage

```python
# Direct import (single train model)
from displays.train_models.e235_1000 import UpperDisplay
upper = UpperDisplay(screen, route_data, stops)
upper.set_state(curr_stop=0, cnt_pa=0, at_station=True)  # boots STOPPING at start platform
upper.draw()   # language ticking belongs to ChangeScheduler, which PASimulator owns

# Registry (multiple train models) — what app.py / setup.py use
from displays import get_train_model
model = get_train_model("e235_1000")          # TrainModel record (default if unknown)
upper = model.upper_cls(screen, route_data, stops)
lower = model.lower_cls(screen, route_data, stops, upper.mode_cycler)
```

---

## Integration with Main Application

Wired in `app.py` `PASimulator.__init__` (creates `upper` + `lower`, passes upper's `mode_cycler` to lower so modes stay in lockstep, calls `lower.set_state(self.state)`) plus `ChangeScheduler(upper.mode_cycler, lower)`) and `PASimulator.run` (per-frame call order: `state.update_skip_progress(timestamp)` → `scheduler.tick` → `upper.draw` → `lower.draw` → `pygame.display.flip()`).

---

## Testing

```bash
# Default mock route (E235-1000)
uv run preview_display.py

# E235-0 sub-series
uv run preview_display.py --model e235_0 --route yamanote

# Real route
uv run preview_display.py --route yamanote

# Force English mode
uv run preview_display.py --mode english

# Static screenshot
uv run preview_display.py --screenshot out.png --route _mock/main --mode kanji --stop 0

# Force a specific lower view
uv run preview_display.py --lower-view {full,eight,cycle}
```

**Observe:**

- Mode cycling: upper changes between KANJI / FURIGANA / ENGLISH every 4s; lower dispatches to EnglishDisplay for the full-route slot during ENGLISH mode.
- Skip animation: PageDown across passing-station gap; cursor walks forward through passing station, inner red dot stays at new PA target.
- Long-route window flip (Keihin-Tōhoku, Chuo): cursor pos stays correct as window slides.
- Centering: mock route (11 stops) renders with equal margins; multi-line routes unchanged.

Preview-mode swap inventory documented at `PASimulator.__init__`'s ``preview`` parameter in `app.py`. `jump_to_stop` semantics live in its docstring at `app.py` `PASimulator.jump_to_stop`. Mock-route stop layout → [`audio/_mock/main/README.md`](audio/_mock/main/README.md).

---

## Per-series displays

Sub-series-specific renderer details (per-class layout, continuity arrows, transfer-info pipeline, sub-series diffs) live in their own docs:

- [DISPLAY_E235.md](DISPLAY_E235.md) — E235 family (E235-0 + E235-1000)
- *Future: DISPLAY_E233.md, DISPLAY_E231.md, etc. as those models land.*

---

## Related Documentation

- [CLAUDE.md](CLAUDE.md) — project overview, module table, controls, "When Working On…" pointers
- [CLAUDE.md](CLAUDE.md) "Mental Model" — train-family scope, IRL line scope per model, best-effort policy, Hepburn convention (preloaded)
- [DATA_FORMAT.md](DATA_FORMAT.md) — `translations.json` / `train_types.json` / `stations.json` / `route.json` shapes, validation rules
- `displays/base.py` — `DisplayMode` enum, `ModeCycler`
- `app.py` `PASimulator.__init__` ``preview`` parameter — preview-mode swap inventory
- `app_paths.py` `project_root` — PyInstaller path resolution contract

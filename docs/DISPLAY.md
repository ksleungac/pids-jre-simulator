# LCD Display System — Cross-Model Infrastructure

Modular per-train-model architecture for both Upper and Lower LCDs. This doc covers the **cross-model** layer: factory dispatch, mode system, unified state machine, lower-LCD interface contract, and the recipe for adding new train models. Per-sub-series renderer specifics live in per-series docs (see [Per-series displays](#per-series-displays) below).

Train-family scope and in-spec/best-effort policy live in [CLAUDE.md](../CLAUDE.md) "Mental Model", which is preloaded. JSON shapes → [DATA_FORMAT.md](DATA_FORMAT.md). Cross-cutting code contracts live inline at code sites: font-loading at first font init in each model's `upper_lcd.py`, the countdown formula at `lower_lcd.py` `draw_times`, PyInstaller path resolution at [`app_paths.py`](../app_paths.py) `project_root`.

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
> - Facts already in [CLAUDE.md](../CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Voice:** new reference-shaped entries (cross-model invariants, contracts, recipes, mode-system rules, state-machine spec, edge-case tables) stay compressed — tables, `=` for definitional equivalence, no narrative padding. Rationale-shaped passages (incident warnings, "Mental model:" framings, narrative examples) run as ordinary prose. Both in complete sentences where they use prose at all, per [CLAUDE.md § Writing tone](../CLAUDE.md).
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](../.claude/rules/principles.md).

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

No redundant prefixes in class names (e.g. `JapaneseDisplay` rather than `E235_1000JapaneseDisplay`), since each train model has its own directory scope.

---

## Mode System

### DisplayMode + ModeCycler

`DisplayMode` (in `displays/base.py`) = IntEnum: `KANJI=0`, `FURIGANA=1`, `ENGLISH=2`. `ModeCycler` (same file) holds the current mode and its timer. It does **not** tick itself. It exposes `is_due(now)` / `advance(now)`, and `ChangeScheduler` drives both (see § Change scheduler). Cadence = `LANGUAGE_BEATS` (1 beat = 4s). The cycler keeps an `enabled` flag for freezing on a forced mode.

### Cycler Sharing Between Upper and Lower

**One cycler, shared.** Upper owns it. Lower receives it as a constructor argument:

```python
self.upper = UpperDisplay(screen, route_data, stops)
self.lower = LowerDisplay(screen, route_data, stops, self.upper.mode_cycler)
```

This keeps modes in lockstep without a parallel timer, so there is no drift and no re-tick. When upper switches to ENGLISH, lower switches with it. The default mode and the `enabled` flag are controlled from the upper side. The cadence and the ticking belong to `ChangeScheduler`.

### Cycling Behavior

| Time | Mode | Prefix | Station Name |
|------|------|--------|--------------|
| 0–4s | KANJI | 次は | 東京 |
| 4–8s | FURIGANA | つぎは | とうきょう |
| 8–12s | ENGLISH | Next | Tōkyō |

**Graceful fallback:** if a station lacks furigana or English data, that mode is skipped in the cycle.

### Stop data keys vs DisplayMode enum

Stop data = plain dict (merged from `route.json` + `data/translations.json`), keyed by **strings**: `"name"`, `"english"`, `"furigana"`. `DisplayMode` = an internal **enum** tracking which mode is active. Use string keys for stop lookup (`stops[i].get("english")`). `stops[i].get(DisplayMode.ENGLISH)` silently returns `""`, because the enum value isn't a dict key.

The naming alignment between `"english"` (data) and `DisplayMode.ENGLISH` (state) is intentional, but the bridging happens at the manager layer (`UpperDisplay` / `LowerDisplay`), not via direct lookup.

### Mode Mapping (Lower-Specific)

The shared cycler ranges over KANJI / FURIGANA / ENGLISH. The `LowerDisplay` manager reads the active language mode from the cycler and passes it to its internal `_pick_renderer(mode)` method.

- For KANJI and FURIGANA, it dispatches to the Japanese full-route or 8-station views.
- For ENGLISH, it dispatches to the `EnglishDisplay` (or falls back to the Japanese 8-station view if a specialized English zoomed view isn't implemented). 

Because the lower display has its own internal state machine for alternating between FULL and EIGHT station views (the "slot cycler"), it uses dynamic dispatch (`_pick_renderer`) rather than a simple dictionary map.

### ⚠️ Cycler.enabled vs Cycler.paused

ModeCycler has `enabled`, **not** `paused`. To freeze a forced mode (e.g. in preview scripts), set `cycler.enabled = False`. Assigning to `paused` silently creates a new attribute that `is_due()` never checks, so the forced mode un-freezes once the cadence elapses.

To freeze the language and the lower's slot together, set `scheduler.enabled = False`. That is one switch for both axes, and it is what `preview_display.py --lower-view` uses.

---

## IRL divergences (deliberate)

Where the simulator knowingly departs from a real E235. Each row is a design choice with a reason, so a fidelity finding filed against any of them is a false positive. The IRL column is author-stated, 2026-08-18.

| IRL | Simulator | Why |
|---|---|---|
| Upper's language change and lower's content change run on **independent rhythms** | One `ChangeScheduler` drives both on a shared beat under one floor | Two uncoordinated clocks produced sub-second view flashes (#78); the coupling IS that fix |
| Transfer info surfaces around the **second flip after stopping** | `at_station` rising edge force-switches to TRANSFER at once, bypassing the floor | Transfer info is why the stop matters; immediacy was chosen over fidelity |
| The route bar is a **minority** of lower-screen time — delays, お知らせ and general info each take a turn, and there are many of them | Two or three slots rotate, so the route bar dominates | The other content types do not exist here; there is nothing to rotate against |
| The display advances to the next station **when the train starts moving** | Advances when the announcement audio finishes | Manual drive has no motion signal at all; under OCR auto-drive the speed read supplies one |
| Every door has its own screen, and only the **opening side** shows the arrival content (door state, transfer info, stair / escalator position) | One screen, content keyed to the stop | No door-side data axis exists |

---

## Change scheduler

`ChangeScheduler` (`displays/base.py`) is the single owner of every discrete view change. It is constructed in `app.py` beside upper and lower, and ticked once per frame from the main loop: after `update_skip_progress` (slot membership reads `cursor_pos`), and before both draws.

**Change** = a discrete visible mutation, either a language flip or a slot rotation. Continuous content (clock, countdown, skip / breath / band-fill animation) is not a change. It renders every frame, untouched.

**Continuous content still needs a discrete trigger owner.** A reveal or sweep that renders every frame (the E235-0 5-station band fill) restarts on a slot-enter, and that restart is a discrete event. It is fired from `LowerDisplayBase.apply_slot`, the sole slot-commit funnel, on a genuine `slot != _current_slot` enter. It is never self-detected by the renderer from a wall-clock draw-gap. Inside a pure renderer, a draw stall (a window move freezes the main thread) is indistinguishable from a real re-enter, so a gap heuristic false-restarts on any stall, and also on a stopped→moving marker flip. Keeping the trigger on the scheduler side lets `draw()` stay pure. Per-sub-series instance: DISPLAY_E235.md § "E235-0 — 5-station stopping view".

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

**Why beats, not seconds.** An off-grid duration silently defers to the next allowed moment, so the number in the source stops describing the screen. Whole beats make written == observed by construction. Rationale at the `displays/base.py` module docstring.

**Language coverage.** Every (slot, language) pairing must surface eventually. There is no requirement that one appearance of a slot spans all three languages. FULL and EIGHT dwell 3 beats, which is the 3-language cycle, so each surfaces in every language within one appearance. Their default out-of-window round trip is 3+3 = 6 beats, an exact multiple of the cycle, so their starting language never rotates and does not need to. TRANSFER at 2 beats cannot span the cycle. What covers it is the in-window round trip of 3+3+2 = 8 beats, which is not a multiple of 3, so its starting language rotates across successive cycles.

### The floor

After any change, no change of any kind for `CHANGE_FLOOR_BEATS`. At one beat it doubles as the quantizer: an off-grid slot dwell defers to the next beat rather than landing mid-interval, so the rhythm is uniform without constraining what may be written.

It deliberately does **not** sit below the cadence, which is safe only because evaluation is atomic. The rationale (the starvation trap a below-cadence floor was dodging) lives at the constant, `displays/base.py` `CHANGE_FLOOR_BEATS`.

> **CONTRACT: one atomic tick per frame.** Both axes evaluate against the **same** frame-start `last_change` snapshot and apply together as one batched event, stamping `last_change` once. It is **not** a shared `last_change` consulted independently by upper and lower, which is the starvation trap above. A due-but-blocked change is never queued: due-ness recomputes from timestamps every frame and applies on the first frame the floor allows.

### Change flavors

- **Scheduled.** A per-axis cadence elapsed. Deferrable by the floor.
- **Reactive.** The current slot left `_available_slots`. *Layout-invalid* (FULL after the eight-lock engages) still renders coherently, so it is deferrable. *Content-invalid* (TRANSFER at a station that lost its transfers) would show a blank panel, so it is treated as Preemptive and never held.
- **Preemptive.** Intent-driven and immediate. It bypasses the floor and re-anchors it. The members are the STOPPING force-switch to TRANSFER (also fired by a cross-stop jump onto a transfer-bearing stop, on the same rising edge), the content-invalid reconcile, the restart-logo reveal, and a position change that cancels the logo. The stop force-switch fires at every stop and re-anchors the language off its cadence. That is accepted, because transfer info must show at once. Plain paging is **not** preemptive: `_advance_to_next_stop` clears `at_station`, so no edge fires and the slot rotates on cadence.

### The TRANSFER slot's window — and the stations it can never reach

`LowerDisplayBase._in_transfer_window` puts TRANSFER in the rotation from APPROACHING_FINAL through STOPPING, derived from `cnt_pa` rather than `is_last_pa` so a single-PA stop still qualifies. `_station_has_transfers` then drops it where the filtered list is empty, so the cycle rotates without a blank slot.

**A stop with `"pa": []` is unreachable for this view, however many transfers it has.** `_in_transfer_window` returns False outright when the stop carries no PA tracks, and a station the train runs through carries none. That is not a defect. It is what "the train does not stop here" means.

It matters when enumerating cases. `data/stations.json` will resolve transfers for such a station, so a coverage sweep built from the transfer data alone lists states the app cannot produce. On `chuo/1654T` that is 代々木 / 市ヶ谷 / 飯田橋 / 水道橋, four JB-only stations the 快速 passes. They do not fail loudly either: `jump_to_stop` rolls a passing index back to the nearest stopping station, so each renders as its **neighbour** and the sheet looks complete while carrying duplicates. Filter the enumeration on `pa` before rendering (`_dev_scripts/_e233_transfer_cases.py`).

### Restart logo

While `lower.transition_active`, the scheduler applies no discrete change. The screen is a static logo, and a slot mutating out of sight would flash the instant it cleared. At logo-clear it fires one Preemptive: reveal the new frame's default slot, and restart its dwell. The restart matters even when the slot is unchanged. Slot timers are wall-clock, so the logo burns dwell invisibly; without the restart the new segment's opening view expired after one floor instead of its full 3 beats.

The swap fire is the one Preemptive that is **predictable** (a fixed timer from the arm), so the scheduler goes quiet for one floor before it via `lower.seconds_until_swap`. Otherwise a rotation lands a frame before the logo covers it.

Invariants pinned by `_tests/t3_invariant/test_change_scheduler.py` (schedule-as-spec, floor, atomic batching, boot seed, Preemptive bypass + re-anchor, logo quiet + reveal, pairing coverage).

---

## Unified State Machine

Every stop follows a two-sub-state cycle: APPROACHING (`at_station=False`) → STOPPING (`at_station=True`) → next stop's APPROACHING → ...

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

`AppState.__init__` defaults to `at_station=True`, `cnt_pa_at_station=-1`. So `curr_stop=0` boots into STOPPING: the train is parked at the start platform and no advance-into has happened. The first press either plays `pa_at_station[0]` (if non-empty) or advances directly to idx 1.

### Prefix mapping

`UpperDisplay.set_state(curr_stop, cnt_pa, at_station)` resolves prefix as:

| State | Prefix (KANJI) | Furigana | English |
|---|---|---|---|
| `at_station=True` | ただいま | ただいま | Now stopping at |
| `cnt_pa == len(pa) - 1` (final approach PA) | まもなく | まもなく | Arriving at |
| otherwise (`cnt_pa < last`) | 次は | つぎは | Next |

`at_station=True` is the **only** path to "ただいま", and it overrides the cnt_pa-based mapping. All at-platform PAs belong in `pa_at_station`, never in `pa[]`.

**Final-approach rule.** Only the **last** entry in `pa[]` flips the prefix to "まもなく". Intermediate approach announcements (e.g. pa[1] of a future 3-PA stop) stay on "次は."

### `jump_to_stop` semantic

Click-to-jump (preview ←/→, future click-to-jump on lower LCD) lands in STOPPING@target. Mental model: clicking a station cell means "I'm at platform X." The next press cycles `pa_at_station` or advances, matching the rest of STOPPING. Implementation in `app.py` `jump_to_stop`: it sets `at_station=True`, resets `cnt_pa_at_station=-1`, and does the existing housekeeping (skip, departure_time, cnt_sta).

The `_has_pa` predicate (used by `jump_to_stop`'s passing-station roll) accepts a stop with a non-empty `pa` or a non-empty `pa_at_station` as a valid landing target. Stops with both empty are treated as passing stations and rolled past.

### Circular loop-back

Yamanote-style routes have the same station name at idx 0 and idx N. The duplicate idx 0 is a structural marker for circularity, not a state to visit mid-loop. `_advance_to_next_stop`'s loop-back branch jumps `idx N → idx 1` directly, plays `pa[0]` of the new stop, and lands in APPROACHING.

### Skip animation

Skip animation lives in `_advance_to_next_stop`. Entering STOPPING and cycling pa_at_station do not touch skip state, because by the time STOPPING is entered the train has already arrived. Skip holds whatever the previous advance left it at, with skip_progress catching up to skip via `update_skip_progress`. The within-pa branch zeros skip on every press as a defensive catch-up. See [Lower LCD — Cross-Model Interface § Station Skip Logic](#station-skip-logic-full-spec) below for the full contract.

### Edge cases & guards

**Audio-playing guard.** `_next_pa` early-returns when `audio.is_playing()`, so both a manual PageDown and a `pending_next_pa` from the auto-driver are dropped while audio plays. `jump_to_stop` does **not** honor this guard. It calls `audio.pause()` itself before mutating state, so callers (preview ←/→, click-to-jump) get a clean handoff without doing their own pause.

**`cnt_pa` is dead during STOPPING.** Naturally-entered STOPPING (via `_next_in_approaching`'s "pa exhausted" branch) leaves `cnt_pa` at `len(pa)-1`. `jump_to_stop`-entered STOPPING forces `cnt_pa=0`. Both render "ただいま X", because `at_station` overrides the prefix mapping. `cnt_pa` is not read again until `_advance_to_next_stop` resets it to `0` on exit.

**Terminus (non-circular).** `STOPPING@dest_stop_idx` is a stable end-state. Pressing PageDown falls through `_advance_to_next_stop`'s final `else: return`, because neither `curr_stop < terminus_idx` nor `circular == 1` is true. Silent no-op, no state change.

**`pa=[]` with non-empty `pa_at_station`.** `_is_stopping` accepts either one being non-empty, so an advance lands such a stop in APPROACHING with `cnt_pa=0`, then calls `audio.play_pa(curr_stop, 0)`, which silently returns at `audio.py:73` (`pa_index >= len(pa_tracks)`). The display flashes "次は X" with no audio for one press, until the user presses again to enter STOPPING. No known route data hits this today, but `_has_pa` tolerates it.

---

## Code Style Conventions

- **Position constants inlined** as local variables in each draw method (e.g. `box_x, box_y = 15, 8`). Different train models may need different layouts, and per-method positions make that explicit.
- **Fonts shared** as class members defined in `__init__` (e.g. `self.font_type_bold`). Fonts are consistent within a model.
- **ShinGo fonts resolve through `font_atlas.lcd_font(face, size, bold=, italic=, draws=…)`.** Never use a bare `pygame.font.Font` for a baked face; `lint_primitives.py` bans it. `set_bold()` / `set_italic()` on the result now **raise**, because style is part of the atlas key, so pass the kwargs instead. `draws=` declares where the text comes from: `at("audio/*/route.json:stops[].name")`, `lit("次は")`, plus `replace=` / `split=` / `wrap=` / `suffix=` for text the renderer derives. **Adding drawn text is a two-part edit**, the string and its declaration. The atlas is cooked from declarations, so coverage never depends on a state being reachable, and `lcd_font` validates every dev draw against the declaration, so an undeclared string fails on the first frame that draws it. Text layout has one implementation, `utils.compose_text_parts`, and the atlas stores its output. A font **size** is part of the key, so `/build` re-bakes every run. Design and gates: [wip/WIP_font_atlas.md](wip/WIP_font_atlas.md).
- **When a renderer derives text, declare the derivation.** Do not write a `lit()` listing the forms you have seen. `at(...)` carries `split=` / `wrap=` / `cuts=` / `prefix=` / `suffix=` so the declaration says what the **rule** can produce, rather than what the corpus happens to contain today. Pairing a derivation option with a literal for the leftover case reintroduces the enumeration the declaration removed, and it fails the same way: correct when written, silently short the day the data grows. The 6-station transfer band split a line name at `（` and drew the tail with its paren, a string no field holds, so it declared `split="（"` plus `lit("（各駅停車）")`, the one tail Chūō has. `data/lines.json` carries a second full-width-paren name, and it raised on the first frame of a Yamanote drive. In a build that ships no font software the same call is a `KeyError`. `cuts=True` takes both halves at every break position, so it cannot depend on where the rule cuts. Over-approximating costs nothing: a declaration says what **may** be drawn, while the bake stores what **is**. See [critical_lessons.md § 9](../.claude/rules/critical_lessons.md).
- See [conventions.md § "Tuneable-params block"](../.claude/rules/conventions.md) for the project-wide rule on labeled local variables at the top of every draw method.

### Mode Renderer Design

Each mode renderer (`JapaneseDisplay`, `FuriganaDisplay`, `EnglishDisplay`) is **self-contained**: it owns its fonts, its layout and its full set of draw methods. Roughly 90% similarity across renderers is acceptable, since different train models may need to diverge freely without reaching into the wrong layer. Canonical shape: `JapaneseDisplay` in `upper_lcd.py` (fonts loaded once in `__init__`, position constants inline per draw method).

### Centering Text Across Fonts

Use `surface.get_bounding_rect()`, which returns tight visible-pixel bounds. **Do not** use `font.get_size()` / `surface.get_size()` for tight centering. Those include font leading, which varies a great deal per font (Frutiger's leading is much larger than Helvetica's at the same pt size), so alignment breaks when swapping fonts.

Canonical example: `UpperDisplay._draw_station_code_badge` centers two text rows of different sizes inside a small badge, reactive to any font choice.

For **horizontal centering inside a fixed-width cell** (e.g. the passing-station chevron in the lower LCD), use `(cell_w - element_w) // 2` for true center. Don't copy magic-number approximations like `stops_w * 0.3`. That constant works for full-route's narrow cells (~1 px off true center) but is ~8 px off in the 8-station view's wide cells.

**A narrow glyph in an equal-width slot is centered, not flush left.** Text laid out on uniform slots (`utils.compose_text_parts`'s compression branch, `draw_1col_text`'s column) mixes full-width kanji with halfwidth characters: the digit in `空港第2ビル`, the `･` of a compound destination. Placing every glyph at its slot's left edge leaves the narrow one with all its slack on the right, which reads as a gap rather than as spacing. Both axes now center per character: horizontal by the slot's own slack (`(int(sep) - glyph_w) // 2`), vertical against the widest character's column width. The correction is **0 for uniform-width text**, so it moves only the mixed runs. On E235's compound destinations one glyph moves, the `･`, from 60 to 66 in its 30 px slot. It centers the glyph's **surface**; a face's own asymmetric side bearing (katakana `ビ`) is left as the typeface set it.

---

## Lower LCD — Cross-Model Interface

The contract every train model's `LowerDisplay` must satisfy. Per-sub-series renderer specifics (linear full-route, circular full-route, 8-station, transfer-info pipeline, continuity arrows, layout/centering tables, `draw_times` subtleties) live in per-series docs.

### State Injection & Skip Animation

Lower needs more per-frame state than upper (cursor_pos, skip, skip_progress, time_to_next, departure_time, frame_mode, is_last_pa). The API mirrors upper's `set_state` / `update` / `draw`, but `set_state` binds an AppState reference rather than copying fields. It is called once at app startup, and subsequent draws read live state from the bound reference. `update(current_time)` is a no-op, since the cycler is shared with upper. `draw(current_time)` dispatches to whichever mode renderer the cycler points at.

### Station Skip Logic (full spec)

**Single source of truth**: `state.curr_stop` is the only stored "where is the train" index. The visual cursor on the lower LCD is derived: `state.cursor_pos = curr_stop - max(0, skip - skip_progress)`. When no skip is in flight (`skip == 0`), `cursor_pos == curr_stop`.

**Skip setup happens in `app._next_pa`'s "advance to next stop" branch** (not in the lower-LCD renderer):

- Records `prev_stop = curr_stop`, advances `curr_stop` past passing stations to next PA station.
- Sets `skip = curr_stop - prev_stop - 1` (number of passing stations crossed), `skip_progress = 0`, `time_to_next = stops[curr_stop].time` if `skip > 0`.
- On the first frame after this, `cursor_pos = curr_stop − skip` = the first passing station. The cursor visibly steps onto it.

**Time-based progression**: `AppState.update_skip_progress` increments `skip_progress` at thresholds `time_to_next * i / (skip + 1)`. `cursor_pos` auto-advances because it is derived. There is no `curr_stop_disp` mutation. It is called from the main loop in `app.run()` *before* drawing each frame, which keeps the lower display pure rendering.

**Catch-up at next PA tick**: `_next_pa`'s "next PA within current stop" branch zeros `skip` / `skip_progress` / `time_to_next` on every `cnt_pa` increment. The cursor snaps to `curr_stop`. It is idempotent, and a no-op if skip is already 0.

**No leak class possible**: the "advance" branch *overwrites* skip from the gap rather than appending, and the "within stop" branch unconditionally zeros it. There is no separate "flush" path that could leak.

**Inner circle**: drawn at `curr_stop` (the PA target) via `gi == self.state.curr_stop` in `draw_marks`. During skip animation `cursor_pos` lags behind by `skip - skip_progress`. That is intentional: the pointer (red triangle) shows the animation position, and the inner dot shows the actual PA target.

**State fields**: `skip`, `skip_progress`, `time_to_next`. Three integers fully describe the animation. `cursor_pos` is a property on `AppState`, not stored.

**Call order in `app.run()`.** The renderer stays pure-read, so a future English lower won't need to re-implement skip:

```python
self.state.update_skip_progress(timestamp)
self.scheduler.tick(timestamp, self.state)   # every discrete change, atomically
self.upper.draw(...)                          # pure renderers from here
self.lower.draw(timestamp)
pygame.display.flip()
```

### Position-locked views always show the pointer

Any lower-LCD view whose window is locked to the train's position (E235-1000 8-station, E235-0 5-station / circular / open-horseshoe, every renderer that re-centres on the train) **must** render the train pointer in every frame. **Every stop-count, window and lock consideration keys on `cursor_pos` (the visual train position), never on `curr_stop` (the skipped-ahead PA target).** A departure that skips passing stations advances `curr_stop` several cells ahead while `cursor_pos` animates across them. Keying a window or lock threshold on `curr_stop` snaps it to the tail before the visible cursor arrives, pushing the pointer out of view. Key on `cursor_pos` and the pointer stays visible throughout.

**Scope: the active frame.** The invariant applies to whichever frame is *active*, the one containing the train's position. For a through-service route the junction station is **shared** between adjacent frames, so a train parked at a junction sits at index 0 of the incoming frame. The leading-frame hold (a fired swap shows frame N+1 while the train is still parked at the junction; see [Through-Service Display Frames](#through-service-display-frames)) therefore still renders the pointer, at the junction station. There is no active frame without a train icon.

### Terminus (`dest_stop_idx`)

Non-circular routes terminate at the route-level `dest`, not at `len(stops) - 1`. Some route data (e.g. Keihin 727B) extends past the operational dest for through-running reference: Keihin 727B's dest is 磯子 (index 40), but stops continue 41..45 to 大船 to capture the through-running segment.

`PASimulator.__init__` resolves `self.dest_stop_idx` once by name-matching `self.dest` against `self.stops`. `_next_pa` computes `terminus_idx = self.dest_stop_idx` for non-circular routes, or `len(self.stops) - 1` for circular ones. A duplicate-name first-match would be wrong there, but circular routes use the loop-back branch, so it does not matter.

---

## Through-Service Display Frames

A through-service route (one physical train across multiple operational segments) partitions its station list into ordered display **frames**. The lower LCD renders only the frame holding the train, and swaps at the junction with a restart screen. A plain route is one implicit frame, which is legacy behavior: with no `frames` key the output is byte-identical to pre-frames. Authored schema → [DATA_FORMAT.md § frames](DATA_FORMAT.md). Per-model restart transition → [DISPLAY_E235.md](DISPLAY_E235.md).

### Active-frame windowing

Each frame = the window `[from_idx … to_idx]` over the combined `pre_stops + stops` (loader closure, `route_loader._resolve_frames`). The renderer reframes each frame to look like a standalone `pre_stops` route, so existing pixel code handles it unchanged. Only the list and the offset fed in change. This lives in `_FrameWindowMixin`, mixed into both lower-LCD view classes:

- `display_stops` = the frame's slice. Layout is recomputed against it (`_relayout`).
- `display_offset` = the always-passed prefix length **within** the frame = `max(0, min(to_idx+1, len(pre_stops)) - from_idx)`. Frame 0 keeps the pre_stops prefix. Later frames start fresh at 0.
- `_frame_sim_base` = the frame's first simulated `stops[]` index = `max(0, from_idx - len(pre_stops))`. It maps sim → frame-local display index: `curr = state.curr_stop - _frame_sim_base + display_offset`.
- `_frame_global_lo` = the frame's first cell global index. It lets continuity compare a window's global position against the full route.

Legacy (no `frames`): `_frames_view` is None, `_frame_sim_base = 0`, and `display_stops` is the whole list.

### Frame selection + swap timing

Active frame = the first frame whose global window contains the train. The junction is a shared boundary and belongs to the **earlier** frame. There is a single resolver, `LowerDisplay._natural_frame`, working on the route closure's `frames`. The manager pushes the resulting (lag-adjusted) index into the renderer via `set_active_frame`. Renderers never derive their own frame.

`LowerDisplay` owns the swap (it sees the view-cycle) and pushes the lagging frame index into the active renderer via `set_active_frame`:

- **Armed** at STOPPING@junction (`at_station` + position == active frame's `to_idx`, frame has a successor).
- **Held** for a fixed `_SWAP_HOLD_BEATS` (3 beats = 12s), decoupled from the view-cycle. The hold signals that the train is stopped at the frame boundary, and gives the junction's exchange (transfer) info time to read; the STOPPING edge force-switches to the TRANSFER slot, so it shows immediately. It is **not** "exhaust every page".
- **Fires**: advance `_active_frame_idx`, start the restart transition. The frame now **leads** position, showing frame N+1 while the train is still parked at the junction, and it is held that way until the train departs.
- **Jump / backward / fast-page** → resync to the natural frame, disarm, cancel any restart.

### Continuity at a frame boundary

A non-final frame's right edge (the junction) is a continuation rather than a terminus, but the frame slice makes the renderer read it as the route end. Continuity checks therefore compare the window's **global** position against the **full** route, not the slice:

- 8-station: `route_continues = (_frame_global_lo + last_gi) < len(_full_display_stops) - 1`. Reduces to the original `last_gi < len(display_stops) - 1` for legacy.
- Full-route: `_get_stops_list_disp` sets the tail slot (slot 2 two-row / slot 0 single-row) from the same comparison, `_frame_global_lo + window_last < len(_full_display_stops) - 1`. Symmetric with 8-station, and there is no draw-side override.
- **Drawing fix (8-station)**: when the train stops ON the last visible cell, `draw_times` skips that cell's 分-area, so the continuity triangle would float past the red pentagon. The 分-area bar extension is painted before the pointer (pentagon overdraws it) so the triangle always connects to the route bar.

> **Pending IRL verification**: continuity arrow at the screen-edge / row-end case (full-route chevrons + 8-station triangle) when a frame boundary lands at a row end — see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues).

---

## Specifying a new display (spec-first workflow)

**Scope: any display work beyond small tuning.** That means a new train model, a new view on
an existing one, or a view rebuilt against fresh references. Small nudges to a calibrated
element skip this and go straight to `/calibration-editor`.

The spec is written before the code and the code follows it. Established 2026-08-22 on
E233-0; `docs/wip/WIP_e233_0_display.md` is the worked example.

### 1. One reference per view

`_references/lcd/<model>/`, named `<view>-<state>-<lang>.png`. That path is already
inventoried in `THIRD-PARTY.md` § "Reference material", so a file placed there is covered by
an existing carve-out; a new folder elsewhere is an uninventoried asset class
(`conventions.md` § Tooling).

**Note what the reference set cannot show you.** References captured at one instant share
one state, one station name and one train type, so they can agree perfectly and still say
nothing about what varies. Write that limit down next to the measurement rather than
reading the agreement as invariance (`critical_lessons.md` § 9: a check that consumes the
same enumeration the artifact came from verifies fidelity, never coverage).

### 2. Whole-display basics FIRST

In order, before any element: **aspect → upper/lower divide → background colours →
canvas**. Every later number is expressed against these, so settling them last means
redoing everything. **Font size is part of the atlas key**, so a late canvas change
re-bakes and re-tunes the whole model.

Do not assume the fork source's canvas carries over. E235 is 730 × 420 (≈16:9); E233-0
measured 4:3, which is the first thing its fork could not inherit.

### 3. Ratios before pixels, measured by script

Never estimate a ratio by eye. An off-axis or rescaled reference yields a different number
every time you look (`conventions.md` § UI code style). Threshold ink or detect colour runs
inside known rects and read the bbox.

Record ratios, not pixels: references arrive at assorted sizes and the canvas is chosen
after measuring, so a ratio survives both and a pixel survives neither. Mark every value
`[measured]` (a script produced it) or `[observed]` (read by eye, not yet trusted).

### 4. Draw the base canvas, and stop at content-independence

Ship the backgrounds, the divide and the border as the model's `__init__.py` and render it.
Draw the render **from those constants**, never from a copy, so the picture also checks
the module (`principles.md` § "A second implementation of a production decision drifts").

The base layer takes only what is **state-, view- and content-independent**. A container
for content, such as the destination plate, a badge or a code box, does not qualify until
its overflow rule is settled: fixing its geometry early answers "does it grow, or does the
text shrink" by accident, in the layer where a wrong answer is least visible.

### 5. One drill-down session per view, with the author

Its output is that view's section in the WIP doc: **element inventory · what drives each
element · text overflow · adaptive behaviour at edge conditions.**

**No view section is written ahead of its session.** A spec authored unprompted is a gap
filled autonomously, and it arrives at the next reader indistinguishable from an author
decision (`principles.md` § Implementation-completion-as-spec). Park raw observations under
an explicit not-yet-decided heading instead.

### 6. Build, then tune

Build the view against the spec, then tune it in the calibration editor against the same
reference (`/calibration-editor`, `--overlay`). New elements are wired editor-ready as they
are written, which for a new model is free, since the fork source is already wired.

**One element at a time, and the live element bounds the REPORT as well as the diff.** A
settled or parked element is not measured, not mentioned, and not re-justified. A bare
noun ("the white box", "the font") resolves to the live element, not to the ambiguity between
it and a finished one. Naming a finished element back at the author reads as correcting them
on scope they already set. 2026-08-25, three times inside the clock element: the plate's
corners were measured and led the reply when only the clock's were in play; asked why, the
answer was "it was ambiguous to me", which tells the author their instruction was unclear
when the loop had already made it clear; and a question about the clock's typeface was
answered with an unasked enumeration of four parked elements' faces. Author: *"i do element
by element with you, and i tell you to do the clock, the i mean only the clock, what the fuck
are you correcting me for"*. If a referent genuinely is ambiguous, resolve it silently and
report only the live element.

**The artifact is the production renderer, and the tool that tunes it is the calibration
editor.** `preview_display.py --edit --overlay <ref.png>` puts the reference over the live
element; the editor reads that element's `_TUNEABLES_*` from the production module, nudges them
live, and `Ctrl+S` writes only the edited keys back. **Registering the element in `_REGISTRY` is
the wiring step.** That is what makes this more than the tidier route: the thing being tuned and
the thing being shipped are the same bytes, so a sandbox cannot drift from the renderer and a
preview cannot show superseded code. Never fit an element in a separate harness. The blunt
domain test is that **if a script imports pygame, loads a font, or computes a position, it is
drawing, and drawing is the renderer's job**; a measurement script reads the reference and
prints numbers. General form:
[principles.md § "Prototype inside the code that will hold it"](../.claude/rules/principles.md).
Two consequences, both of which the author had to state on 2026-08-26 after the station-name
element was fitted in a temp-directory script and never wired in:

- **A preview or comparison renders from the LIVE code**, always. Keeping the old arm around
  while you work is your own business and your own call — *"i know sometimes you want to keep
  the old before handing out the new, you think about this youself, just that when i said i want
  overview or compare, it should just be the new one"* — but what goes to the author is the new
  one. **Old-versus-new is on their EXPLICIT request only, and they will say so directly**: it
  is for a call they cannot make without seeing both, like the train type's weight (§ 8.10 of
  `WIP_e233_0_display.md` — DeBold against Heavy / Medium / Light). *"most of the time i don't,
  if i am not sure i will say very directly and want old vs new, othertimes, if you re-read my
  word, i never said your original results are ok and worth keeping."* Their silence is not a
  reason to preserve the previous arm, and never a reason to show it. *"when i ask for a preview,
  comparison of anytime, unless i said you compare new of old, then i MUST see the latest
  algorithm, in your provision or in your mind or what i
  don't fucking care, you show the old thing to me what's the fucking point"* — a sheet of
  twelve stops went out rendered from the superseded layout, which invalidated every earlier
  picture in the same session, because the author could no longer tell which of them had come
  from where.
- **An acceptance is an instruction to land the value, not a datum.** *"when i say correct i
  fucking mean you can apply it"*, and *"when i say something looks good, without followup
  comment, or what, i mean i accept, confirmed this already"*. Apply it in the same turn and
  show the result; do not carry it forward as a finding. A confirm gate the author sets is
  scoped to the one thing they asked about — satisfying it does not put the whole element back
  into discussion.

The badge and the station name went through this loop in the same session with opposite
outcomes, which is the cheapest illustration available: the badge was measured, wired into the
renderer, rendered from the renderer, and accepted first pass.

**Pixel-tune against the reference first, then sweep the edge cases** (author, 2026-08-29:
*"ref and compare was for pixel tuning. pixel tuning first then overview"*). The two artifacts
answer different questions and the order is not interchangeable. The overlay
(`compare_fonts.py --overlay`, or `preview_display --edit --overlay` live) says whether the element
sits where the reference puts it; the coverage sheet says whether it survives the states and
routes the reference never shows. Sweeping first spends the author's attention on eighteen cells
of a geometry that is still moving, and the sheet has to be rebuilt anyway.

**Every render handed to the author is the WHOLE SCREEN**, overlay and coverage sheet alike, never
a crop to the element's band (author, 2026-08-29: *"when you show overview always show full
screen"*, then *"overlay only preview with full screen"*). Zoom instead when an element needs to
be read closely. Cropping hides what the rest of the display is doing, which is the context that
makes a change judgeable at all, and the author then has to ask for the missing half.

**The coverage sheet is produced unprompted, with the element, and it opens at full spread.**
Do not wait to be asked for a preview or a comparison, and do not start with the one stop the
reference happens to show (author, 2026-08-26: *"i want preview and compare results be
automatically prepared, not i asking, also it should at start cover most of the possible
scenarios, don't need me asking"*). Enumerate what the element actually varies over: every
name length in the corpus, every state the machine reaches, a null field, an out-of-spec route.
Render one row per case from the live code, and send it as part of landing the element. It is
also the only instrument that can catch the class below, so producing it is not politeness but
the verification step.

**One composed sheet, never a handful of screenshots** (author, 2026-08-29: *"for this kind of
things always and only use the overview for my convenient"*, and *"i like the overview displays,
this saves me so much time"*). `_dev_scripts/compare_grid.py --out sheet.png --cols N "label=file"`
tiles labelled cells; render the cells, compose, send the sheet, delete the cells. A stream of
individual files makes the author open and compare them by hand, which is the work the sheet exists
to remove. Re-send the same sheet as it is rebuilt rather than accumulating new ones.

**The cells never touch the repo root; only the composed sheet does** (author, 2026-08-30: *"for
those mid work individual sheets, don't spam by root folder, just show me composed version"*).
Render them under `_visual_iter/` (gitignored) and write the sheet to the root as
`screenshot_*.png`, which is the path the author opens. Eighty-odd cells at the root buries the
sheet among its own inputs, which is the previous bullet's complaint one level down.
`compare_grid.py --cells-file <manifest>` takes the list as a UTF-8 file for this reason: a manifest
also survives Japanese labels, which PowerShell mangles when they go through native argv.

**The axes it must cover are a standard, not a per-element judgement call** (author, 2026-08-29:
*"the edge cases covered should be a standard"*). For a lower-LCD view that is: every state the
machine reaches (each PA phase, boot at the route origin, at the terminus, mid-skip with the cursor
on a run-through station), every structural edge the layout can present (either side of a wrap or a
window swap, either side of a through-service junction), the extreme value its content can take (a
three-digit countdown, the longest name in the corpus), and **every shipped line**, since the
out-of-spec paths are only exercised by real route data. Cases missing from the sheet are the ones
that ship broken: this session's window swap, three-digit minutes and single-row layout were all
found by adding a cell, not by reading code.

**An element whose layout varies with the DATA cannot be settled against a frozen reference,
and the fit will not tell you so.** A capture constrains the parameters visible in it and leaves
every other one free. That is `principles.md` § "A parameter the score cannot see is not being
fit" one level up: there the free parameter was a coordinate the sample did not bear on, here it
is an axis of the world the harness has no representation for. E233-0's first five upper elements
are static, so one reference showed the whole of each and an exhaustive RMS fit settled it. Five
successes in a row taught nothing, because for a static element, fitting the parameters and
implementing the element are the same act. The station name is the first whose layout is a rule
over character count, and no capture in the set shows one, three or five characters, so the fit
reported a confident number for a rule it could not see. Fit what the reference constrains, drive
the real corpus across every route and stop for the rest, and say in the spec which figures came
from which. A request for "the whole display across other stations" is the author supplying the
axis the reference cannot.

### 7. Graduate

Fold the settled spec into `docs/DISPLAY_<MODEL>.md` and delete the WIP section. The WIP
doc dissolves when its stated trigger is met; until then keep its status current rather than
letting it drift (`conventions.md` § "WIP-doc → canonical-doc graduation").

---

## Adding New Train Model

Mechanics, once § "Specifying a new display" has produced a spec.

1. Create `displays/train_models/{model_name}/` directory.
2. Copy and modify `upper_lcd.py` for fonts and positions. This is often a fork from a sibling sub-series; see [conventions.md § "Display module structure"](../.claude/rules/conventions.md) for the copy-don't-reinvent rule.
3. Implement `lower_lcd.py` with `LowerDisplay`. Subclass existing model's `LowerDisplay` and override only the slot renderer that differs (precedent: E235-0 subclasses E235-1000 and swaps only FULL slot's renderer when route is Yamanote).
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay` + per-model dimensions/palette (`S_WIDTH`, `S_HEIGHT`, `UPPER_HEIGHT`, `DARK_BG`, `WHITE_BG`).
5. Register in `displays/train_models/__init__.py`: import the package and add a `TRAIN_MODELS` entry (key = folder name = the route.json `model` value):

   ```python
   from displays.train_models import e233_0   # alongside the existing models
   TRAIN_MODELS["e233_0"] = TrainModel(
       "e233_0", "E233-0", e233_0.UpperDisplay, e233_0.LowerDisplay, e233_0.S_WIDTH, e233_0.S_HEIGHT
   )
   ```

   The model then appears automatically in the setup-screen per-route dropdown (`model_choices()`), and any route defaults to it via its route.json `model` field (see [DATA_FORMAT.md § Route-Level Fields](DATA_FORMAT.md)). `app.py` instantiates the registered classes from the `model` constructor arg, so no `app.py` edit is needed.

6. Add per-series doc (`DISPLAY_{MODEL}.md`) for sub-series-specific renderer rules. Cross-reference from [Per-series displays](#per-series-displays) below.

Per [CLAUDE.md](../CLAUDE.md) "Mental Model → Per-model IRL line scope": new model's IRL line scope determines which routes need full-fidelity behavior; everything else best-effort.

### Usage

```python
# Direct import (single train model)
from displays.train_models.e235_1000 import UpperDisplay
upper = UpperDisplay(screen, route_data, stops)
upper.set_state(curr_stop=0, cnt_pa=0, at_station=True)  # boots STOPPING at start platform
upper.draw()   # language ticking belongs to ChangeScheduler, which PASimulator owns

# Registry (multiple train models) — what app.py / tims.setup use
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

Preview-mode swap inventory documented at `PASimulator.__init__`'s ``preview`` parameter in `app.py`. `jump_to_stop` semantics live in its docstring at `app.py` `PASimulator.jump_to_stop`. Mock-route stop layout → [`audio/_mock/main/README.md`](../audio/_mock/main/README.md).

---

## Per-series displays

Sub-series-specific renderer details (per-class layout, continuity arrows, transfer-info pipeline, sub-series diffs) live in their own docs:

- [DISPLAY_E235.md](DISPLAY_E235.md) — E235 family (E235-0 + E235-1000)
- *Future: DISPLAY_E233.md, DISPLAY_E231.md, etc. as those models land.*

---

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) — project overview, module table, controls, "When Working On…" pointers
- [CLAUDE.md](../CLAUDE.md) "Mental Model" — train-family scope, IRL line scope per model, best-effort policy, Hepburn convention (preloaded)
- [DATA_FORMAT.md](DATA_FORMAT.md) — `translations.json` / `train_types.json` / `stations.json` / `route.json` shapes, validation rules
- `displays/base.py` — `DisplayMode` enum, `ModeCycler`
- `app.py` `PASimulator.__init__` ``preview`` parameter — preview-mode swap inventory
- `app_paths.py` `project_root` — PyInstaller path resolution contract

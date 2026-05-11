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
> - Speculative future sections ("When X is implemented, …") — defer until needed; `TODO.md` is the home for pending designs
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
│  Factory Layer (displays/)                                  │
│  - get_train_display() returns model-specific display       │
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
├── __init__.py              # Package entry point: DisplayMode, ModeCycler, get_train_display
├── base.py                  # DisplayMode (IntEnum: KANJI=0, FURIGANA=1, ENGLISH=2), ModeCycler
├── utils.py                 # Shared helpers: draw_station_code_badge, draw_route_disclaimer,
│                            # draw_text_given_width, draw_1col_text, draw_1col_text_plain,
│                            # arrow_points
├── transfer_info.py         # Parent TransferInfoDisplay (state binding, transfers_by_view,
│                            # variant resolution) — concrete renderers are per-model
└── train_models/
    ├── __init__.py          # Factory registry: TRAIN_DISPLAYS, get_train_display()
    ├── e235_1000/
    │   ├── __init__.py      # Per-model manifest: S_WIDTH, S_HEIGHT, UPPER_HEIGHT, palette;
    │   │                    # exports UpperDisplay, LowerDisplay
    │   ├── upper_lcd.py     # JapaneseDisplay, FuriganaDisplay, EnglishDisplay, UpperDisplay
    │   ├── lower_lcd.py     # JapaneseDisplay (linear full-route),
    │   │                    # JapaneseEightStationDisplay, EnglishDisplay (placeholder),
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

`DisplayMode` (in `displays/base.py`) = IntEnum: `KANJI=0`, `FURIGANA=1`, `ENGLISH=2`. `ModeCycler` (same file) cycles through registered modes every `STATION_DISPLAY_INTERVAL` seconds (default 4s). Cycler keeps `enabled` flag for freezing on a forced mode.

### Cycler Sharing Between Upper and Lower

**One cycler, shared.** Upper owns it; lower receives it as constructor argument:

```python
self.upper = UpperDisplay(screen, route_data, stops)
self.lower = LowerDisplay(screen, route_data, stops, self.upper.mode_cycler)
```

Keeps modes in lockstep without parallel timer (no drift, no re-tick). When upper switches to ENGLISH, lower switches with it. Cycler's interval, default mode, and `enabled` flag all controlled from upper side.

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

Shared cycler ranges over KANJI / FURIGANA / ENGLISH. Lower's `mode_displays` dict maps both KANJI and FURIGANA to `japanese_display` (real PIDS doesn't furigana the route map); ENGLISH intentionally absent so `mode_displays.get(mode, self.japanese_display)` falls back to Japanese until ENGLISH renderer implemented. Result: upper cycles freely through all three; lower stays Japanese.

### ⚠️ Cycler.enabled vs Cycler.paused

ModeCycler has `enabled`, **not** `paused`. To freeze a forced mode (e.g. in preview scripts), set `cycler.enabled = False`. Assigning to `paused` silently creates a new attribute that `update()` never checks — the forced mode will un-freeze after the cycle interval elapses. This has burned us before.

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
self.upper.update(timestamp); self.upper.draw(...)
self.lower.draw(timestamp)
pygame.display.flip()
```

### Terminus (`dest_stop_idx`)

Non-circular routes terminate at route-level `dest`, not at `len(stops) - 1`. Some route data (e.g. Keihin 727B) extends past operational dest for through-running reference — Keihin 727B's dest is 磯子 (index 40) but stops continue 41..45 to 大船 to capture the through-running segment.

`PASimulator.__init__` resolves `self.dest_stop_idx` once by name-matching `self.dest` against `self.stops`. `_next_pa` computes `terminus_idx = self.dest_stop_idx` (non-circular) or `len(self.stops) - 1` (circular — duplicate-name first-match would be wrong otherwise, but circular routes use loop-back branch so doesn't matter).

---

## Adding New Train Model

1. Create `displays/train_models/{model_name}/` directory.
2. Copy and modify `upper_lcd.py` for fonts/positions (often a fork from sibling sub-series — see [conventions.md § "Display module structure"](.claude/rules/conventions.md) for copy-don't-reinvent rule when forking).
3. Implement `lower_lcd.py` with `LowerDisplay`. Subclass existing model's `LowerDisplay` and override only the slot renderer that differs (precedent: E235-0 subclasses E235-1000 and swaps only FULL slot's renderer when route is Yamanote).
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay` + per-model dimensions/palette (`S_WIDTH`, `S_HEIGHT`, `UPPER_HEIGHT`, `DARK_BG`, `WHITE_BG`).
5. Register in `displays/train_models/__init__.py`:

   ```python
   TRAIN_DISPLAYS["{model_name}"] = {ModelName}UpperDisplay
   ```

6. Add per-series doc (`DISPLAY_{MODEL}.md`) for sub-series-specific renderer rules. Cross-reference from [Per-series displays](#per-series-displays) below.

Per [CLAUDE.md](CLAUDE.md) "Mental Model → Per-model IRL line scope": new model's IRL line scope determines which routes need full-fidelity behavior; everything else best-effort.

### Usage

```python
# Direct import (single train model)
from displays.train_models.e235_1000 import UpperDisplay
upper = UpperDisplay(screen, route_data, stops)
upper.set_state(curr_stop=0, cnt_pa=0, at_station=True)  # boots STOPPING at start platform
upper.update(timestamp)
upper.draw()

# Factory (multiple train models)
from displays import get_train_display
display = get_train_display("e235_1000", screen, route_data, stops)
display.update(timestamp)
display.draw()
```

---

## Integration with Main Application

Wired in `app.py` `PASimulator.__init__` (creates `upper` + `lower`, passes upper's `mode_cycler` to lower so modes stay in lockstep, calls `lower.set_state(self.state)`) and `PASimulator.run` (per-frame call order: `state.update_skip_progress(timestamp)` → `upper.update` + `upper.draw` → `lower.draw` → `pygame.display.flip()`).

---

## Testing

```bash
# Default mock route (E235-1000)
uv run preview_display.py

# E235-0 sub-series
uv run preview_display.py --model e235_0 --route yamanote

# Real route
uv run preview_display.py --route yamanote

# Force English mode (lower stays Japanese until placeholder is filled in)
uv run preview_display.py --mode english

# Static screenshot
uv run preview_display.py --screenshot out.png --route _mock/main --mode kanji --stop 0

# Force a specific lower view
uv run preview_display.py --lower-view {full,eight,cycle}
```

**Observe:**

- Mode cycling: upper changes between KANJI / FURIGANA / ENGLISH every 4s; lower stays Japanese until ENGLISH dispatch enabled.
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

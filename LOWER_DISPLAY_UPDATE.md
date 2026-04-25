# Lower LCD Display System - Modular Architecture

**Date:** 2026-04-25

**Status:** REFACTORED — Japanese fully implemented, English placeholder

> **Companion doc:** [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md). Sections marked **🔁 Shared with UPPER** below are duplicated in both files — keep them in sync when editing.

---

## Overview

The Lower LCD displays the route map: station bars, kanji station name labels, current-position pointer, inner-circle PA target indicator, station markers (circles / arrows), travel-time numbers, and the skip-animation frame for passing stations.

Refactored from the monolithic `display.py` (now deleted) into the modular per-train-model architecture pioneered by the upper LCD. The lower's mode set is intentionally smaller than the upper's:

- **KANJI** mode → JapaneseDisplay (full implementation)
- **FURIGANA** mode → JapaneseDisplay (real PIDS does not furigana the route map)
- **ENGLISH** mode → currently disabled in the dispatch dict; falls back to JapaneseDisplay

When English is implemented, uncomment the `DisplayMode.ENGLISH` entry in `LowerDisplay.__init__` and the lower will follow the upper into English automatically (shared cycler, see below).

---

## Architecture Overview — 🔁 Shared with UPPER

```
┌─────────────────────────────────────────────────────────────┐
│  Factory Layer (displays/)                                  │
│  - get_train_display() returns model-specific display       │
│  - DisplayMode enum (KANJI, FURIGANA, ENGLISH)              │
│  - ModeCycler (handles mode switching timing)               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Train Model Layer (displays/train_models/e235_1000/)       │
│  - UpperDisplay (manager)                                   │
│  - LowerDisplay (manager)                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Mode Renderer Layer (lower_lcd.py)                         │
│  - JapaneseDisplay (KANJI / FURIGANA modes)                 │
│  - EnglishDisplay (placeholder — clears region only)        │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure — 🔁 Shared with UPPER

```
displays/
├── __init__.py              # Package entry point
├── base.py                  # DisplayMode, ModeCycler
├── utils.py                 # Shared drawing utilities
└── train_models/
    ├── __init__.py          # Factory registry
    └── e235_1000/
        ├── __init__.py      # Exports: UpperDisplay, LowerDisplay
        ├── upper_lcd.py     # Upper LCD (see UPPER_DISPLAY_UPDATE.md)
        └── lower_lcd.py     # Lower LCD: JapaneseDisplay, EnglishDisplay, LowerDisplay
```

---

## Mode Renderer Design

Each mode renderer is **self-contained** — owns its fonts, layout calculation, and full set of draw methods. Same pattern as upper. Even though Japanese-vs-English deltas in the lower are smaller than in the upper (markers/pointer/times geometry is identical, only labels and fonts vary), the renderers are kept fully separate so future train models can diverge freely without reaching into the wrong layer.

### JapaneseDisplay

Owns all the route-map rendering. Methods:

- `_calculate_layout()` — derives `per_line`, `x` (centered to actual cell count), `y`, `h_line`, `top_pad`, `circular`, `continuity` from `len(stops)`.
- `_get_line(i)` — line 1 vs line 2 for global index `i`.
- `_get_stops_list_disp(curr_stop)` — returns `(global_index, stop)` pairs in the current visible window. For long routes (> `STOPS_QUANTITY`), slides the window forward as the train approaches the end.
- `_find_dest_index(f_stops)` — global index of the destination within the visible window.
- `draw_marks(f_stops, dest_idx, cursor_pos, curr_stop)` — circles / passing-station arrows; the inner red dot at `curr_stop` marks the actual PA target (lags behind cursor during skip animation).
- `draw_ptr(f_stops, dest_idx, cursor_pos, curr_stop)` — red triangle pointer at `cursor_pos`.
- `draw_times(f_stops, dest_idx, cursor_pos, current_time, departure_time, is_last_pa)` — cumulative travel times with floor-division countdown.
- `show_stops(state, current_time)` — entry point. Reads from passed-in AppState; **does not mutate**. Skip-animation progress lives on AppState (see below).

Fonts (loaded from `fonts/` folder, locale-safe):

```python
self.font_stops  = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_SIZE)        # 25
self.font_time   = pygame.font.Font("fonts/HelveticaNeue-Bold.otf", FONT_TIME_SIZE)         # 14
self.font_minute = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_MINUTE_SIZE)  # 11
```

The lower's three font sizes are *shared across mode renderers* (and live in `constants.py`) because both Japanese and the future English use the same metrics for time/minute glyphs. Per-display-module size constants belong inline; `constants.py` carries only sizes that are actually shared across modules.

### EnglishDisplay (placeholder)

Stub. `show_stops` clears the lower-region background only — no labels, no markers. This was a deliberate choice: an empty lower region is a clear visual signal "English not implemented yet" rather than a stale Japanese render bleeding through when the upper cycles into English.

Currently *not* mapped in `LowerDisplay.mode_displays`, so the dispatch falls back to JapaneseDisplay. The class is kept around as scaffolding for when English is implemented.

---

## ModeCycler — 🔁 Shared with UPPER

The `ModeCycler` lives in `displays/base.py`. Cycles through the modes registered in its `mode_displays` dict every `STATION_DISPLAY_INTERVAL` seconds (default 4s).

### Cycler Sharing Between Upper and Lower

**One cycler, shared.** The upper owns it, the lower receives it as a constructor argument:

```python
# In app.py
self.upper = UpperDisplay(screen, route_data, stops)
self.lower = LowerDisplay(screen, route_data, stops, self.upper.mode_cycler)
```

Why: keeps upper and lower in lockstep without a parallel timer (no drift, no re-tick). When the upper switches to ENGLISH, the lower switches with it. The cycler's interval, default mode, and `enabled` flag are all controlled from the upper side.

### Mode Mapping (Lower-Specific)

The shared cycler ranges over `KANJI / FURIGANA / ENGLISH`. The lower's `mode_displays` dict maps:

```python
self.mode_displays = {
    DisplayMode.KANJI: self.japanese_display,
    DisplayMode.FURIGANA: self.japanese_display,
    # DisplayMode.ENGLISH: self.english_display,  # disabled until implemented
}
```

`LowerDisplay.draw()` does `self.mode_displays.get(mode, self.japanese_display)` — the missing-key fallback returns Japanese for ENGLISH mode. Result: upper cycles freely through all three; lower stays Japanese until the ENGLISH entry is uncommented.

---

## State Injection & Skip Animation

The lower needs significantly more per-frame state than the upper does (cursor_pos, skip, skip_progress, time_to_next, departure_time, frame_mode, is_last_pa). API mirrors upper's `set_state` / `update` / `draw`, but stores an AppState reference rather than copying fields:

```python
class LowerDisplay:
    def set_state(self, state):       # binds AppState reference
        self._state = state

    def update(self, current_time):   # cycler is shared with upper, no-op here
        pass

    def draw(self, current_time):     # dispatches to active mode's renderer
        ...
```

`set_state` is called once at app startup; subsequent draws read live state from the bound reference.

### Skip Animation — Pure Rendering, State on AppState

The lower display does **not** mutate state. The skip-progress counter — which advances the cursor through passing stations as travel time elapses — lives on `AppState.update_skip_progress(current_time)` and is called from `app.run()` *before* drawing each frame:

```python
# In app.run()
self.state.update_skip_progress(timestamp)
self.upper.update(timestamp); self.upper.draw(...)
self.lower.draw(timestamp)
pygame.display.flip()
```

`AppState.cursor_pos` is a `@property` derived as `curr_stop - max(0, skip - skip_progress)`. The renderer reads `state.cursor_pos` directly — no separate "current display index" field.

This separation matches the upper's pattern (renderers consume state, never mutate it) and means a future English lower-display will not need to re-implement the skip animation.

See `.claude/rules/notes.md` "Station Skip Logic (LowerDisplay)" for the full spec including catch-up at PA-tick, long-route window flips, and pointer suppression edge cases.

---

## Layout / Centering

`_calculate_layout()` decides the route-map bar geometry from `len(stops)`:

| Stop count | per_line | Lines | Notes |
|---|---|---|---|
| `> 17` or even | `min(14, ⌈n/2⌉)` | 2 | Most real routes |
| ≤ 17 and odd | 17 | 1 | Mock route, future short single-line variants |
| `> 28` | as above | 2 + window slide | Yamanote (30), Chuo (32), Keihin (46) |

**Centering fix (2026-04-25):** the row x-offset uses `min(per_line, num_stops)`, not `per_line` alone, so single-line routes with `num_stops < per_line` (e.g. mock at 11 stops with `per_line=17`) center to actual content width instead of leaning left under a per_line-wide bounding box. Multi-line layouts unaffected.

---

## Integration with Main Application — 🔁 Shared with UPPER

```python
from displays.train_models.e235_1000 import UpperDisplay, LowerDisplay

class PASimulator:
    def __init__(self, work_dir, route_data=None, preview=False):
        ...
        self.upper = UpperDisplay(self.screen, self.route_data, self.stops)
        # Lower shares the upper's mode_cycler — modes stay in lockstep.
        self.lower = LowerDisplay(self.screen, self.route_data, self.stops, self.upper.mode_cycler)
        self.lower.set_state(self.state)

    def run(self):
        # Initial draw
        self.upper.set_state(self.state.curr_stop, self.state.cnt_pa)
        self.upper.draw()
        self.lower.draw()
        pygame.display.flip()

        while self.running:
            timestamp = time.time()

            # Advance skip animation (state-machine logic on AppState).
            self.state.update_skip_progress(timestamp)

            self.upper.update(timestamp)
            self.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))
            self.lower.draw(timestamp)

            pygame.display.flip()
            self._handle_input()
```

### Key Changes from Legacy display.py

| Old (display.py) | New (lower_lcd.py) |
|---|---|
| `LowerDisplay(screen, route_data, app_state, stops)` | `LowerDisplay(screen, route_data, stops, mode_cycler)` + `.set_state(state)` |
| `lower.show_stops(current_time)` | `lower.draw(current_time)` |
| `_update_skip_progress` mutates `state.skip_progress` | `AppState.update_skip_progress(current_time)` (state owns the mutation) |
| `pygame.display.flip()` inside `show_stops` | Lifted into `app.run()` after both displays draw |
| One class, one mode | `JapaneseDisplay` + `EnglishDisplay` + `LowerDisplay` manager |

---

## draw_times subtleties (recurring review false positives)

Two things in `JapaneseDisplay.draw_times` that look wrong but aren't:

- **`is_first_station` flips ONCE.** The flag identifies the *first time-bearing* stop after `cursor_pos` and gives it the countdown calculation; subsequent stops use cumulative addition. After cycle 2 it's nested inside `if cursor_pos <= gi <= dest_idx and "time" in stop:` — passing stations at the cursor get correctly skipped, and the first station with `time` correctly receives the "first" treatment regardless of whether it sits at `cursor_pos` exactly.
- **The 分-marker `OR` covers all cases.** `if local_i == self.per_line - 1 or gi == dest_idx:` correctly fires for both line-break columns AND mid-line dest. Don't change to AND or pile on extra clauses — that breaks one of the two cases.

## Design Decisions

1. **Shared cycler with upper.** Keeps modes in lockstep, single source of truth for mode timing.
2. **Self-contained mode renderers.** Same pattern as upper. Some duplication is OK; flexibility for future train models is more valuable than DRY.
3. **Pure-rendering split.** Skip-progress mutation lives on AppState, not the renderer. Renderer reads, never writes.
4. **English placeholder over English-disabled-in-cycler.** Keeping ENGLISH in the shared cycler (rather than removing it) means the upper still cycles freely; the lower's local fallback handles its own incompleteness without affecting the upper.
5. **Centering uses actual cell count, not per_line.** Single-line short routes (mock) now render centered.
6. **Distribution unchanged** — same `fonts/`, `data/`, `audio/` layout as upper. See `/build` skill.

---

## Future: Element Clear-Background Convention

When the lower LCD grows past its single route-map region (e.g. the English mode is implemented and lower needs to differentiate between Japanese label box vs English label box), it'll adopt the same convention as the upper LCD: per-region `_DEBUG_COLORS` + `_bg()` helper + Region Map comment block at the top of `lower_lcd.py`. The convention itself is documented in [UPPER_DISPLAY_UPDATE.md "Element Clear-Background Convention"](UPPER_DISPLAY_UPDATE.md#element-clear-background-convention) — same rules for both displays, including the D1/D2 distinction and probing methodology. Single source of truth is the upper doc; this section is a pointer.

---

## Files

- `displays/train_models/e235_1000/lower_lcd.py` — JapaneseDisplay, EnglishDisplay (placeholder), LowerDisplay manager
- `app.py` — `AppState.update_skip_progress`, integration in `PASimulator.__init__` / `.run()`
- `constants.py` — shared lower-LCD font sizes (`FONT_STOPS_SIZE`, `FONT_TIME_SIZE`, `FONT_STOPS_MINUTE_SIZE`) and layout (`STOPS_BAR_HEIGHT`, `STOPS_WIDTH`, `STOPS_PER_LINE`)
- `displays/base.py` — DisplayMode, ModeCycler (shared infrastructure)

---

## Testing

```bash
# Default mock route
uv run preview_display.py

# Real route
uv run preview_display.py --route yamanote

# Force English mode (lower stays Japanese until placeholder is filled in)
uv run preview_display.py --mode english

# Static screenshot for visual regression
uv run preview_display.py --screenshot out.png --route _mock/main --mode kanji --stop 0
```

**Observe:**
- Mode cycling: upper changes between KANJI / FURIGANA / ENGLISH every 4s; lower stays Japanese until ENGLISH dispatch is enabled.
- Skip animation: PageDown across a passing-station gap; cursor walks forward through the passing station, inner red dot stays at the new PA target.
- Long-route window flip (Keihin-Tōhoku, Chuo): cursor pos stays correct as window slides.
- Centering: mock route (11 stops) renders with equal margins; Keiyo (17 stops) edge-to-edge; multi-line routes unchanged.

---

## Changes Log

### 2026-04-25
- Refactored from monolithic `display.py` into modular `lower_lcd.py` mirroring upper's pattern.
- New `JapaneseDisplay` self-contained renderer; `EnglishDisplay` placeholder; `LowerDisplay` manager with `set_state` / `update` / `draw`.
- Skip-progress mutation moved from renderer onto `AppState.update_skip_progress`. Renderer is now pure rendering.
- Shared `mode_cycler` with upper (constructor arg).
- `pygame.display.flip()` lifted out of renderer into `app.run()`.
- Single-line layout centering bug fixed (`min(per_line, num_stops)`).
- English mapping disabled in `mode_displays` dict; falls back to Japanese until implemented.
- Legacy `display.py` deleted.

---

## Related Documentation

- [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md) — companion doc, upper LCD architecture
- [CLAUDE.md](CLAUDE.md) — project overview
- [.claude/rules/notes.md](.claude/rules/notes.md) — Station Skip Logic spec, edge cases
- [DATA_FORMAT.md](DATA_FORMAT.md) — JSON data conventions
- `displays/base.py` — ModeCycler implementation

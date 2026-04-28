# LCD Display System

Modular per-train-model architecture for both Upper and Lower LCDs. Currently implements **E235-1000**; built to extend to other JR East series with heavy code reuse. Train-family scope and in-spec/best-effort policy live in [CLAUDE.md](CLAUDE.md) "Mental Model" (preloaded — should already be in head).

This is the canonical display doc — covers shared infrastructure, upper LCD, lower LCD, and integration. Cross-cutting code contracts live inline at their code sites (font-loading at the first font init in [`upper_lcd.py`](displays/train_models/e235_1000/upper_lcd.py); countdown formula at `lower_lcd.py` `draw_times`; PyInstaller path resolution at `upper_lcd.py` `get_base_dir`). JSON shapes are in [DATA_FORMAT.md](DATA_FORMAT.md).

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
│  Train Model Layer (displays/train_models/e235_1000/)       │
│  - UpperDisplay (manager)                                   │
│  - LowerDisplay (manager)                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Mode Renderer Layer                                        │
│  - upper_lcd.py: JapaneseDisplay / FuriganaDisplay /        │
│                  EnglishDisplay                             │
│  - lower_lcd.py: JapaneseDisplay (full) +                   │
│                  JapaneseEightStationDisplay (zoomed) +     │
│                  EnglishDisplay (placeholder)               │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
displays/
├── __init__.py              # Package entry point: DisplayMode, ModeCycler, get_train_display
├── base.py                  # DisplayMode (IntEnum: KANJI=0, FURIGANA=1, ENGLISH=2), ModeCycler
├── utils.py                 # Shared helpers: draw_station_code_badge, draw_route_disclaimer,
│                            # draw_text_given_width, draw_1col_text, arrow_points
└── train_models/
    ├── __init__.py          # Factory registry: TRAIN_DISPLAYS, get_train_display()
    └── e235_1000/
        ├── __init__.py      # Exports: UpperDisplay, LowerDisplay
        ├── upper_lcd.py     # JapaneseDisplay, FuriganaDisplay, EnglishDisplay, UpperDisplay
        └── lower_lcd.py     # JapaneseDisplay, JapaneseEightStationDisplay,
                             # EnglishDisplay (placeholder), LowerDisplay
```

### Naming Conventions

| Level | Pattern | Example |
|-------|---------|---------|
| Train model | Directory: `snake_case` | `e235_1000/`, future `e231_500/` |
| Display section | File: `{section}_lcd.py` | `upper_lcd.py`, `lower_lcd.py` |
| Mode renderer | Class: `{Mode}Display` | `JapaneseDisplay`, `EnglishDisplay` |
| Manager | Class: `{Section}Display` | `UpperDisplay`, `LowerDisplay` |

No redundant prefixes in class names (e.g., `JapaneseDisplay` not `E235_1000JapaneseDisplay`) — each train model has its own directory scope.

---

## Mode System

### DisplayMode + ModeCycler

```python
class DisplayMode(IntEnum):
    KANJI = 0      # Japanese kanji
    FURIGANA = 1   # Japanese furigana (phonetic)
    ENGLISH = 2    # English romanized (Hepburn with macrons)
```

`ModeCycler` (in `displays/base.py`) cycles through registered modes every `STATION_DISPLAY_INTERVAL` seconds (default 4s). Cycler keeps an `enabled` flag for freezing on a forced mode.

### Cycler Sharing Between Upper and Lower

**One cycler, shared.** The upper owns it; the lower receives it as a constructor argument:

```python
self.upper = UpperDisplay(screen, route_data, stops)
self.lower = LowerDisplay(screen, route_data, stops, self.upper.mode_cycler)
```

This keeps modes in lockstep without a parallel timer (no drift, no re-tick). When the upper switches to ENGLISH, the lower switches with it. The cycler's interval, default mode, and `enabled` flag are all controlled from the upper side.

### Cycling Behavior

| Time | Mode | Prefix | Station Name |
|------|------|--------|--------------|
| 0–4s | KANJI | 次は | 東京 |
| 4–8s | FURIGANA | つぎは | とうきょう |
| 8–12s | ENGLISH | Next | Tōkyō |

**Graceful fallback:** if a station lacks furigana or English data, that mode is skipped in the cycle.

### Stop data keys vs DisplayMode enum

These look interchangeable but aren't. Stop data is a plain dict (merged from `route.json` + `data/translations.json`) — keys are **strings**: `"name"`, `"english"`, `"furigana"`. `DisplayMode` is an internal **enum** tracking which mode is active. They never appear together in the same lookup.

```python
# CORRECT — string key for data lookup
station = self.stops[self.curr_stop].get("english", "")

# WRONG — enum value cannot key a stop dict
station = self.stops[self.curr_stop].get(DisplayMode.ENGLISH, "")  # always returns ""
```

Naming alignment between `"english"` (data) and `DisplayMode.ENGLISH` (state) is intentional but bridging happens at the manager layer (`UpperDisplay`/`LowerDisplay`), not via direct lookup.

### Mode Mapping (Lower-Specific)

The shared cycler ranges over KANJI / FURIGANA / ENGLISH. Lower's `mode_displays` dict maps:

```python
self.mode_displays = {
    DisplayMode.KANJI:    self.japanese_display,
    DisplayMode.FURIGANA: self.japanese_display,  # real PIDS doesn't furigana the route map
    # DisplayMode.ENGLISH: self.english_display,  # disabled until implemented
}
```

`LowerDisplay.draw()` does `self.mode_displays.get(mode, self.japanese_display)` — missing-key fallback returns Japanese for ENGLISH mode. Result: upper cycles freely through all three; lower stays Japanese until the ENGLISH entry is uncommented.

### ⚠️ Cycler.enabled vs Cycler.paused

ModeCycler has `enabled`, **not** `paused`. To freeze a forced mode (e.g. in preview scripts), set `cycler.enabled = False`. Assigning to `paused` silently creates a new attribute that `update()` never checks — the forced mode will un-freeze after the cycle interval elapses. This has burned us before.

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

`AppState.__init__` defaults to `at_station=True`, `cnt_pa_at_station=-1`. So `curr_stop=0` boots into STOPPING — the train is parked at the start platform, no advance-into has happened. First press either plays `pa_at_station[0]` (if non-empty) or advances directly to idx 1.

### Prefix mapping

`UpperDisplay.set_state(curr_stop, cnt_pa, at_station)` resolves prefix as:

| State | Prefix (KANJI) | Furigana | English |
|---|---|---|---|
| `at_station=True` | ただいま | ただいま | Now stopping at |
| `cnt_pa == len(pa) - 1` (final approach PA) | まもなく | まもなく | Arriving at |
| otherwise (`cnt_pa < last`) | 次は | つぎは | Next |

`at_station=True` is the **only** path to "ただいま" — overrides cnt_pa-based mapping. The pre-migration `cnt_pa >= 2 → ただいま` fallback was removed because it preserved a wrong-stop ambiguity (display said "ただいま X" while the audio at pa[2+] referred to the previous stop's platform). All at-platform PAs now belong in `pa_at_station`.

**Final-approach rule.** Only the LAST entry in `pa[]` flips the prefix to "まもなく"; intermediate approach announcements (e.g. pa[1] of a future 3-PA stop) stay on "次は." For today's 2-PA data (`pa = [{prev}-dep, {this}-arr]`) this is identical to the previous `cnt_pa >= 1 → まもなく` mapping — pa[1] is both the second entry and the last, so it flips to "まもなく" either way.

### `jump_to_stop` semantic

Click-to-jump (preview ←/→, future click-to-jump on lower LCD) lands in STOPPING@target. Mental model: clicking a station cell means "I'm at platform X." Next press cycles `pa_at_station` or advances, matching the rest of STOPPING. Implementation in `app.py` `jump_to_stop` — sets `at_station=True`, resets `cnt_pa_at_station=-1`, plus all the existing housekeeping (skip, departure_time, cnt_sta).

`_has_pa` predicate (used by `jump_to_stop`'s passing-station roll) accepts a stop with non-empty `pa` OR non-empty `pa_at_station` as a valid landing target. Stops with both empty are treated as passing stations and rolled past.

### Circular loop-back

Yamanote-style routes have the same station name at idx 0 and idx N. The duplicate idx 0 is a structural marker for circularity, not a state to visit mid-loop. `_advance_to_next_stop`'s loop-back branch jumps `idx N → idx 1` directly, plays `pa[0]` of the new stop, and lands in APPROACHING. (Pre-unified-model code reset to idx 0 with no audio; that 2-press hop collapsed into 1 press here.)

### Skip animation

Skip animation lives in `_advance_to_next_stop`. Entering STOPPING and cycling pa_at_station do not touch skip state — by the time STOPPING is entered, the train has already arrived (skip is whatever the previous advance left it at, with skip_progress catching up to skip via `update_skip_progress`). Within-pa branch zeros skip on every press as a defensive catch-up. See "Station Skip Logic (full spec)" under Lower LCD for the full contract.

---

## Code Style Conventions

- **Position constants are inlined** as local variables in each draw method (e.g. `box_x, box_y = 15, 8`). Different train models may need different layouts; keeping positions per-method makes that explicit.
- **Fonts are shared** as class members defined in `__init__` (e.g. `self.font_type_bold`). Fonts are consistent within a model.
- **Tuneable-params block** (project-wide convention): every UI draw method exposes its magic numbers (positions, sizes, offsets, gaps) as labeled local variables at the top. All downstream coordinates derive from those. Rationale: visual tuning means nudging these values — they must be discoverable AND reactive.

### Mode Renderer Design

Each mode renderer (`JapaneseDisplay`, `FuriganaDisplay`, `EnglishDisplay`) is **self-contained**: owns its fonts, layout, and full set of draw methods. ~90% similarity across renderers is acceptable — different train models may need to diverge freely without reaching into the wrong layer.

```python
class JapaneseDisplay:
    def __init__(self, screen, route_data, stops):
        # Fonts shared (defined once in __init__)
        self.font_type_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 26)
        self.font_type_bold.set_bold(True)
        self.font_type_bold.set_italic(True)
        self.font_dest = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
        self.font_station = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 78)
        # ...

    def draw_station(self, station_text: str) -> None:
        # Position constants inline (not shared)
        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54
        # ...
```

### Centering Text Across Fonts

Use `surface.get_bounding_rect()` — returns tight visible-pixel bounds. **Do NOT** use `font.get_size()` / `surface.get_size()` for tight centering — those include font leading, which varies significantly per font (Frutiger's leading is much larger than Helvetica's at the same pt size), breaking alignment when swapping fonts.

Canonical example: `UpperDisplay._draw_station_code_badge` centers two text rows of different sizes inside a small badge, reactive to any font choice.

For **horizontal centering inside a fixed-width cell** (e.g. passing-station chevron in the lower LCD): use `(cell_w - element_w) // 2` for true center. Don't copy magic-number approximations like `stops_w * 0.3` — that constant happens to work for the full-route's narrow cells (~1 px off true center) but is ~8 px off in the 8-station view's wide cells.

---

## Upper LCD

### Manager Class

```python
class UpperDisplay:
    def __init__(self, screen, route_data, stops):
        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.furigana_display = FuriganaDisplay(screen, route_data, stops)
        self.english_display = EnglishDisplay(screen, route_data, stops)

        self.mode_cycler = ModeCycler({
            DisplayMode.KANJI:    self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            DisplayMode.ENGLISH: self.english_display,
        }, default_mode=DisplayMode.KANJI)

        self.translations = load_json_relative("data/translations.json")
        self.train_types = load_json_relative("data/train_types.json")

    def set_state(self, curr_stop: int, cnt_pa: int, at_station: bool = False) -> None: ...
    def update(self, current_time: float = None) -> None: ...
    def draw(self, current_time_str: str = None) -> None: ...
```

### Destination Behavior

- **Always kanji** in KANJI/FURIGANA modes (no cycling to furigana — IRL behavior).
- **English mode** uses "Bound for" prefix + English destination from `translations.json`.
- **Compound destinations** use `"StationA&\nStationB"` format; `&` indicates line break point (no space before `&`).

### Stop-Level Destination Override

Used by circular routes (Yamanote) to show changing destinations. Implementation:

- Check stop-level `dest` first; fallback to route-level `dest`.
- The `dest` value is read from the current stop when drawing the upper display.
- Always displays as kanji (no furigana cycling).
- The kanji `dest` is looked up in `data/translations.json` for English mode rendering.
- Example: at 田町, show "東京・上野" instead of route-level "品川・東京".

JSON-side details (where the override field lives, how compound names are encoded) are in [DATA_FORMAT.md](DATA_FORMAT.md). Real-world motivation is in [CLAUDE.md](CLAUDE.md) "Mental Model → IRL display conventions".

### English Station Name (E235-1000)

- Font: `fonts/HelveticaNeue-Bold.otf` @ 75pt (the `.ttf` cut had macron artifacts at large sizes — gone).
- Position: `name_x = int(S_WIDTH * 0.40) + 10` (10 px right of the Japanese position to give breathing room from the JO/JY badge); `name_y = UPPER_HEIGHT - name_h` (2 px lower than Japanese to match reference).
- Each mode's `draw_station` owns a `DARK_BG` clear rect that covers its glyph box plus ~10 px below for descender overflow. **Extend the rect downward only** — extending it upward into the prefix/clock band erases the clock.
- JR PIDS uses uniform horizontal smoothscale (current `collapse=True` path) for long names — they do NOT swap to a separate condensed font cut. Don't introduce one.

### Station Code Badge

`_draw_station_code_badge()` reads `sta_code` (per-stop, from `route.json`) → renders the framed JY/03 square. Body is a thin wrapper that calls `displays.utils.draw_station_code_badge` with upper-LCD-specific params (badge_x=222, badge_w=68, badge_h=68, ring 7+7, fonts 18/22, etc.) and the optional `code_3` band. The same helper is reused by the 8-station view's per-cell mini badges (smaller box, no `code_3` band, no black ring).

If the Japanese station name has a `code_3` entry in `data/stations.json`, the outer black rect extends UPWARD into a top band showing the 3-letter Roman code (white text, e.g. AKB/TYO).

All layout knobs live in the params block at the top of the method: `code_3_band_h`, `code_3_x_offset`, `code_3_y_offset`; font size in `__init__` as `self.font_sta_code_3letter`.

**Draw order:** badge draws **last** in `UpperDisplay.draw()` (after prefix/station) so the extended top band is not clipped. The prefix `DARK_BG` rect and the badge share `x=222` — earlier ordering painted over the top of the extension.

JSON-side details (`stations.json` keying, the 22-station catalog rule) are in [DATA_FORMAT.md](DATA_FORMAT.md). Real-world rationale is in [CLAUDE.md](CLAUDE.md) "Mental Model → IRL display conventions".

### Element Clear-Background Convention

Every upper-LCD region has a declared **confinement** — a rectangle inside which everything the region draws must visually land. The clear rect is not special; it's just one of the things drawn for the region (alongside glyphs, decorations). The same containment rule applies to all of them.

#### The principle

> Anything a region draws — bg fill, glyph pixels, shapes — must visually stay inside that region's confinement.

That's it. Clear rect ⊆ confinement. Glyph visible pixels ⊆ confinement. Period.

#### Why declare confinements at all

- **Correctness**: every frame's `pygame.draw.rect` for a region's bg should respect this; otherwise it clobbers a neighbor's bg.
- **Debug visibility**: with `--debug-grid` enabled, each region's clear paints in a region-specific tint (red dest, blue prefix, etc.). Anything one region draws that lands on a *neighbor's tint* is a containment violation, surfaced visually.
- **Cross-mode parity**: the three mode renderers (Japanese / Furigana / English) share the same confinement per element. Internal content layout can differ; the boundary doesn't.

#### Two checks: D1 (cheap pre-check) and D2 (the rule)

Pygame font surfaces have **leading** — empty (transparent) pixels above the visible glyph caps. Surface_top is at `blit_y`, but visible glyph caps appear `~10–15 px below` for big fonts. This causes the two-check distinction:

- **D1 (surface containment, analytical)**: `blit_y ≥ confinement.top`. If true, no pixel — visible or transparent — is rendered above `confinement.top`. Sufficient for compliance, no probing needed.
- **D2 (visible-pixel containment, empirical)**: actual visible glyph caps land at `y ≥ confinement.top`. Requires probing or per-font knowledge of leading. Tighter — allows surfaces to extend above confinement *as long as the leading absorbs the overshoot* and no painted pixel actually crosses.

**D2 is the rule.** D1 is a useful pre-check: if it passes, you're done. If D1 fails, that's a *signal to probe*, not an automatic violation — the leading might absorb the overshoot. **Pixel-perfect tuning often requires D2** (e.g., 78pt kanji surfaces extend into the prefix's y-range, but visible caps stay at y≥35 thanks to leading; D1 would forbid the IRL-accurate font size unnecessarily).

#### Probing methodology (gotcha)

When pixel-probing a region's glyphs for containment, **isolate the region** so that neighboring regions' content can't masquerade as the target's:

- Use a scenario where the neighbor is empty or short. For station containment vs prefix, test with the short "Next" prefix (x≤280) — that leaves x=302+ purely station territory. The long "Now stopping at" prefix overlaps station's x-range, and *its* text glyphs landing at y=20-something in the prefix-text overlap zone get mistaken for station glyphs.
- Or probe at "exclusive x ranges" — for station, that's x=522–570 (between prefix right edge and clock left edge) and x=650–686 (right of clock). Any non-bg pixel in these strips at y<confinement.top must be the target region's drawing.

#### Pygame rendering gotchas (recurring review false positives)

Two facts about pygame text rendering that look like bugs to a fresh reviewer:

- **Transparent leading does NOT clobber.** `font.render(text, True, color)` (no bg arg) returns an SRCALPHA surface. Default `blit` alpha-blends; transparent leading pixels don't overwrite the destination. So a station-glyph surface starting above `band_bottom_y` is safe — the prefix text underneath survives in the leading strip.
- **`font.get_height()` is smaller than folk wisdom suggests** — roughly `pt_size × 0.92` for both HelveticaNeue-Medium and ShinGoPr6N-Medium, NOT `pt_size × 1.2`. Probed examples: 24pt → 22, 78pt → 78. **Probe via `pygame.font.Font(...).get_height()` before claiming overflow.**

#### Other rules

- All three mode renderers clear the **same** confinement for the same element. Internal layout can differ per mode; the boundary doesn't.
- Sub-text-bg parameters (e.g., `font.render(text, True, fg, bg)`) inside a region should pass `_bg("<same region>")` as `bg` so they don't punch holes in the tint when debug-grid is on.
- A region's clear rect must not extend into a neighbor's confinement. The `station` clear is clamped to `band_bottom_y=35` (top) and `UPPER_HEIGHT=117` (bottom) for this reason — same clamp pattern duplicated in all three mode renderers' `draw_station`.

#### Current state (E235-1000 upper, post-2026-04-25)

- All 4 station modes (Kanji 78pt, Furigana 78pt, English 1-line 75pt, English 2-line 42pt) comply with **D2**: visible glyph caps land at y≥35 in every mode.
- All 4 station modes' **clear rects** are clamped to `(302, 35, 384, ≤82)` — they fit inside the declared station confinement.

#### Debug-grid mode

`uv run preview_display.py --debug-grid` flips `DEBUG_GRID` in `upper_lcd.py` so every region's `_bg("<region>")` returns its assigned tint instead of `DARK_BG`. Keys live in `_DEBUG_COLORS`. Adding a new region: register key in `_DEBUG_COLORS` AND in the Region Map comment. Forgetting either keeps debug-grid silent on the new region.

#### Region map

Bounds + drawn-by + debug color for every region live as a comment block at the top of `displays/train_models/e235_1000/upper_lcd.py`, alongside `_DEBUG_COLORS`. Per-train-model — different models will have different layouts, so the map stays with the code, not in this doc.

History note: Pre-2026-04-25, the English `draw_destination` had no clear rect at all, and Japanese/Furigana cleared only their narrow 150x35 text box. Bug only surfaced when 2-line station rendering revealed a similar clobbering issue elsewhere — prompted unifying the territory definitions across modes.

---

## Lower LCD

### Mode Renderer Design (lower-specific)

- **JapaneseDisplay** — full route-map renderer. Owns layout calc, marks, pointer, times.
- **JapaneseEightStationDisplay** — 8-station zoomed view (alternates with the full-route view every 12s).
- **EnglishDisplay** — placeholder. `show_stops` clears the lower-region background only — no labels, no markers. Deliberately empty: it's a clear "English not implemented yet" signal, vs a stale Japanese render bleeding through.

JapaneseDisplay methods:

- `_calculate_layout()` — derives `per_line`, `x` (centered to actual cell count), `y`, `h_line`, `top_pad`, `circular`, `continuity` from `len(stops)`.
- `_get_line(i)` — line 1 vs line 2 for global index `i`.
- `_get_stops_list_disp(curr_stop)` — returns `(global_index, stop)` pairs in the current visible window. For long routes (> `STOPS_QUANTITY`), slides the window forward as the train approaches the end.
- `_find_dest_index(f_stops)` — global index of the destination within the visible window.
- `draw_marks(f_stops, dest_idx, cursor_pos, curr_stop)` — circles / passing-station arrows; the inner red dot at `curr_stop` marks the actual PA target.
- `draw_ptr(f_stops, dest_idx, cursor_pos, curr_stop)` — red triangle pointer at `cursor_pos`.
- `draw_times(...)` — cumulative travel times with floor-division countdown.
- `show_stops(state, current_time)` — entry point. Reads from passed-in AppState; **does not mutate**.

Fonts (loaded from `fonts/`, locale-safe):

```python
self.font_stops  = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_SIZE)        # 25
self.font_time   = pygame.font.Font("fonts/HelveticaNeue-Bold.otf", FONT_TIME_SIZE)         # 14
self.font_minute = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_MINUTE_SIZE)  # 11
```

Lower's font sizes are *shared across mode renderers* (live in `constants.py`) because both Japanese and the future English use the same metrics. Per-display-module sizes go inline; `constants.py` is for values genuinely shared across modules.

### State Injection & Skip Animation

The lower needs more per-frame state than the upper (cursor_pos, skip, skip_progress, time_to_next, departure_time, frame_mode, is_last_pa). API mirrors upper's `set_state` / `update` / `draw`, but stores an AppState reference rather than copying fields:

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

### Station Skip Logic (full spec)

**Single source of truth**: `state.curr_stop` is the only stored "where is the train" index. The visual cursor on the lower LCD is derived: `state.cursor_pos = curr_stop - max(0, skip - skip_progress)`. When no skip is in flight (`skip == 0`), `cursor_pos == curr_stop`.

**Skip setup happens in `app._next_pa`'s "advance to next stop" branch** (not in the lower-LCD renderer):

- Records `prev_stop = curr_stop`, advances `curr_stop` past passing stations to the next PA station.
- Sets `skip = curr_stop - prev_stop - 1` (number of passing stations crossed), `skip_progress = 0`, `time_to_next = stops[curr_stop].time` if `skip > 0`.
- First frame after this: `cursor_pos = curr_stop − skip` = first passing station. The cursor visibly steps onto it.

**Time-based progression**: `AppState.update_skip_progress` increments `skip_progress` at thresholds `time_to_next * i / (skip + 1)`. `cursor_pos` auto-advances because it's derived. No `curr_stop_disp` mutation. Called from the main loop in `app.run()` *before* drawing each frame — keeps the lower display pure rendering.

**Catch-up at next PA tick**: `_next_pa`'s "next PA within current stop" branch zeros `skip` / `skip_progress` / `time_to_next` on every `cnt_pa` increment. Cursor snaps to `curr_stop`. Idempotent — no-op if skip was already 0.

**No leak class possible**: the "advance" branch *overwrites* skip from the gap (not appends), and the "within stop" branch unconditionally zeros it. Single-PA-target leakage (the old bug) cannot recur — there is no separate "flush" path to remember.

**Inner circle**: drawn at `curr_stop` (PA target) via `gi == self.state.curr_stop` in `draw_marks`. During skip animation `cursor_pos` lags behind by `skip - skip_progress` — intentional: the pointer (red triangle) shows animation position; the inner dot shows the actual PA target.

**State fields**: `skip`, `skip_progress`, `time_to_next` — three integers fully describe the animation. `cursor_pos` is a property on `AppState`, not stored.

#### Skip animation runs through the renderer in pure-read mode

```python
# In app.run()
self.state.update_skip_progress(timestamp)
self.upper.update(timestamp); self.upper.draw(...)
self.lower.draw(timestamp)
pygame.display.flip()
```

The renderer never mutates state. A future English lower-display will not need to re-implement the skip animation.

### Layout / Centering

`_calculate_layout()` decides the route-map bar geometry from `len(stops)`:

| Stop count | per_line | Lines | Notes |
|---|---|---|---|
| `> 17` or even | `min(14, ⌈n/2⌉)` | 2 | Most real routes |
| ≤ 17 and odd | 17 | 1 | Mock route, future short single-line variants |
| `> 28` | as above | 2 + window slide | Yamanote (30), Chuo (32), Keihin (46) |

**Centering fix (2026-04-25):** the row x-offset uses `min(per_line, num_stops)`, not `per_line` alone, so single-line routes with `num_stops < per_line` (e.g. mock at 11 stops with `per_line=17`) center to actual content width instead of leaning left under a per_line-wide bounding box. Multi-line layouts unaffected.

### Long-Route Window Refresh

Constants: `STOPS_PER_LINE = 14`, so `STOPS_QUANTITY = 28`. Refresh only triggers for routes with **more than 28 stops**.

Hits: Keihin-Tōhoku (46), Chuo (32), Yamanote (30). Below threshold: Nambu (26), Saikyō/Takasaki (24), etc.

Trigger: when `len(stops) - curr_stop < STOPS_QUANTITY`, `_get_stops_list_disp()` returns `self.stops[len(stops) - STOPS_QUANTITY:]` (last 28 stops).

Window carries tuples `(global_idx, stop)` — draw code doesn't need a separate `window_start` parameter to compare state, the global index travels with each cell.

**`continuity[2]` sync (state-leak fix, 2026-04-26):** `_get_stops_list_disp` updates `continuity[2]` on **every call**, not just at the transition frame. Set to `0` whenever the window has slid (visible window includes the route's last stop, no more route past it); restored to `1` whenever the window is back at its original position and route has > 28 stops. The earlier "set once at `remaining == STOPS_QUANTITY - 1`" form left the flag stale at `[1,1,1]` after the user jumped further forward, causing slot-2 chevrons to render past the destination on Keihin (Ōfuna). Circular routes (Yamanote) keep `[1, 1, 1]` since the route always continues past the visible window via the loop.

### Continuity arrows (full-route view)

Continuity is a **property of certain cells** (last-on-row-1, first-on-row-2, last-visible-when-window-slid), not a separate element type. The cell loop in `JapaneseDisplay.show_stops` draws each variant inline alongside the cell so color inherits from the cell's active/passed state — no separate threshold logic, no floating shapes that drift away when the bar gray-outs.

#### Three slots

| slot | trigger | direction | shape |
|---|---|---|---|
| 0 | `local_i == per_line - 1 and continuity[0]` (last cell of row 1) | "to" — route continues to row 2 | bar → 分-area → triangle (apex right, off bar's tail) → chev1 → chev2 |
| 1 | `local_i == per_line and continuity[1]` (first cell of row 2) | "from" — route continues from row 1 | chev1 → chev2 → bar with WHITE_BG inverse-triangle notch carved INTO bar's left edge (apex right) |
| 2 | `gi == last_gi and continuity[2]` (last visible cell when window has slid) | "to" — route continues past visible window | same as slot 0 |

**Slot 0/2 vs slot 1 are visually asymmetric:** slot 0/2 has an *outward* triangle (bar tapers to a point); slot 1 has an *inward* notch (bar's left edge has a white V-shape carved in). Per IRL `lcd_references/chev.png` and `chev2.png` references.

#### Color inheritance

Color is **always `cell_color`** (`self.color` when active, `INACTIVE_COLOR` when passed). No threshold checks. The bar/triangle/chevrons all dim together as the train passes — natural mirror of the cell's own color transition.

#### Drawing order (slot 1 specifically)

Slot 1 renders in this order so the chevron tip pokes into the notch's V-shape:
1. Bar rect (extended `+cont_tri_w` to the left to compensate for notch carve, see below)
2. WHITE_BG inverse-triangle notch (overdraws bar)
3. Chevrons (overdraw the notch where chev2's tip extends into the V — the cell-color overdraw makes the tip "nestle" into the notch instead of disappearing into the white)

Slot 0/2 renders in straightforward order (bar → tail extension → triangle → chevrons), no overdraw conflicts.

#### Tip-portion uniformity (the critical geometry)

For triangle and chevron tips to look like the same pointiness — and for all three gaps (triangle→chev1, chev1→chev2 at top/bottom AND at the V-shape center) to render as a uniform 4-px white margin — set:

```
tri_w == cont_chev_w − cont_chev_stroke == 8
```

Currently `cont_tri_w = 8`, `cont_chev_w = 12`, `cont_chev_stroke = 4` → tip-portion = 8 = `tri_w`. Also matches the red cursor's tip-portion (`w − stroke = 18 − 10 = 8`) so apex slopes read consistently across the LCD. Negative `cont_chev_gap = -4` overlaps chevron BBs so the visible whitespace at the V-center is 4 px (not the bounding-box "gap" — the chevron's tip protrudes into its BB).

**If you change one of those three params, recompute the others** to keep the uniform-gap relationship. The tuneable-params block at the top of `show_stops` is the canonical place; downstream coordinates derive from it.

#### Slot 1 bar compensation

The notch carves `cont_tri_w` px into the bar's left edge. Without compensation, the visible bar would be `cont_tri_w` px narrower than other cells. The cell loop adds `cont_tri_w` to `bar_w` (and shifts `bar_x` left by the same) for slot-1 cells so the visible bar (after notch) matches the original `stops_w + left_extra + right_extra`.

### Row-end / row-head bar extension

Independent of continuity: every row-tail cell (last on row 1 OR last visible cell on row 2) gets `+row_tail_extra = 10` px on the right; every row-head cell (first on row 1 OR first on row 2) gets `+row_head_extra = 10` px on the left. Visible as bigger 東京 / 千葉 / 東千葉 / 成田空港 cells in Sōbu's display.

Three rendering surfaces must stay in sync with these constants — change one, change all three:

| File | Symbol | Constant |
|---|---|---|
| `lower_lcd.py` `JapaneseDisplay.show_stops` cell loop | `row_head_extra`, `row_tail_extra` | source of truth |
| `lower_lcd.py` `JapaneseDisplay.draw_times` 分-marker block | `cell_extra = 10` | mirror of `row_tail_extra` |
| `lower_lcd.py` `JapaneseDisplay.draw_ptr` curr_stop==0 pentagon | `head_extra = 10` | mirror of `row_head_extra` |

The `draw_times` and `draw_ptr` sites have inline comments pointing at this rule — but the magic number is duplicated. Foot-gun if changed in one place only.

### Terminus (`dest_stop_idx`)

Non-circular routes terminate at the route-level `dest`, not at `len(stops) - 1`. Some route data (e.g. Keihin 727B) extends past the operational dest for through-running reference — Keihin 727B's dest is 磯子 (index 40) but stops continue 41..45 to 大船 to capture the through-running segment.

`PASimulator.__init__` resolves `self.dest_stop_idx` once by name-matching `self.dest` against `self.stops`. `_next_pa` computes `terminus_idx = self.dest_stop_idx` (non-circular) or `len(self.stops) - 1` (circular — duplicate-name first-match would be wrong otherwise, but circular routes use the loop-back branch so it doesn't matter).

Without this, PageDown at 磯子 advanced into 新杉田 → ... → 大船, well past the operational terminus. Fixed 2026-04-26.

### draw_times subtleties (recurring review false positives)

Two things in `JapaneseDisplay.draw_times` that look wrong but aren't:

- **`is_first_station` flips ONCE.** The flag identifies the *first time-bearing* stop after `cursor_pos` and gives it the countdown calculation; subsequent stops use cumulative addition. After cycle 2 it's nested inside `if cursor_pos <= gi <= dest_idx and "time" in stop:` — passing stations at the cursor get correctly skipped, and the first station with `time` correctly receives the "first" treatment regardless of whether it sits at `cursor_pos` exactly.
- **The 分-marker `OR` covers all cases.** `if local_i == self.per_line - 1 or gi == dest_idx:` correctly fires for both line-break columns AND mid-line dest. Don't change to AND or pile on extra clauses — that breaks one of the two cases. The 8-station view's analogous condition is `local_i == len(window) - 1 or gi == dest_idx` — same semantics for its respective iteration context.

### 8-Station Zoomed-In View (`JapaneseEightStationDisplay`)

A second Japanese-mode renderer that shows the next 8 upcoming stations at ~2× cell width, alternating with the full-route view every 12s.

#### Window invariant — always exactly 8 cells

Computed in `_get_window(curr_stop, cursor_pos)`. The two args differ only during a skip animation, when `cursor_pos` lags behind `curr_stop` (cursor walks across passing stations while curr_stop already points at the next PA target).

| condition | window start | cursor's local index |
|---|---|---|
| `len(stops) ≤ VISIBLE_COUNT (=8)` | 0 | cursor_pos |
| `curr_stop == 0` | 0 | 0 (no past cell — train hasn't departed anywhere yet) |
| `curr_stop > n - VISIBLE_COUNT` (locked) | `n - 8` | `cursor_pos - (n - 8)` (cursor marches rightward) |
| otherwise (sliding) | `cursor_pos - 1` | 1 (one past cell on the cursor's left) |

`LOCK_THRESHOLD = VISIBLE_COUNT - 1 = 7`. Lock kicks in when `remaining ≤ 7` so the locked window has 1 already-passed cell + 7 ahead = 8 visible.

**Why sliding is keyed on `cursor_pos` but lock on `curr_stop`:**

- *Sliding on `cursor_pos`* keeps the "1 past cell on the cursor's left" contract honest mid-skip. If sliding were keyed on `curr_stop`, the visible cursor (at `cursor_pos < curr_stop` during a skip) would land at local index 0 with zero past context — observable as "the just-departed station vanishes the moment a passing-station skip starts." This was the bug fixed on 2026-04-26.
- *Lock on `curr_stop`* preserves destination visibility near route-end. If lock were keyed on `cursor_pos`, a brief skip animation just before the lock threshold would let the destination cell drop out of view for the duration of the animation. Lock entry is the moment "the route's tail fits in 8 cells regardless of cursor position" — that's a curr_stop fact.

**Visual side effect:** anchoring sliding on `cursor_pos` means the window shifts left by exactly one cell at the frame `cursor_pos` catches up to `curr_stop` (skip animation completes). Single-frame snap; preserves the past-cell-always-visible contract.

#### View cycler (`LowerDisplay`)

24s alternation: 12s full-route, 12s 8-station. Lives on `LowerDisplay` (NOT shared with upper's 4s language cycler — they're orthogonal concerns).

**Critical invariant** — `_tick_view_cycle(current_time)` is called from `LowerDisplay.draw()` UNCONDITIONALLY (subject only to the lock check), BEFORE language-mode dispatch. It must NOT live inside the `KANJI/FURIGANA` branch — if it does, the timer pauses while the upper is in ENGLISH (≈ 1/3 of every language cycle) and the 24s cadence drifts longer than spec'd. The renderer picker `_pick_japanese_renderer()` is a pure function of state — no time arg, no side effects.

When `_should_lock_to_eight(curr_stop)` is True, the cycler is frozen on 8-station permanently for the rest of the trip — no point cycling back to a full-route view that no longer fits.

#### Per-cell mini badge

Sized to ~half the station-circle diameter. Square (22×22), no black outer ring (route color goes to the edge), thin 2-px route-color ring around a white interior, fonts 8 pt prefix / 11 pt num, `text_gap=1`. Past-station badges keep full route color (IRL doesn't dim).

Drawing logic lives in `displays/utils.draw_station_code_badge` — shared with the upper LCD's prominent single-station badge. Lower passes `text_y_offset` to nudge the JO/number group to taste.

#### Compound-name layout (Keihin's `さいたま 新都心`)

Two columns. **Right column** reads first (`parts[0]`), **left column** reads second (`parts[1]`) — Japanese top-to-bottom right-to-left reading order. Both columns share a 3-character standard height (`baseline_vs = 3 * char_h`); a 4-char part compresses to fit, a 3-char part stays uncompressed.

- Right column **top** anchors at `label_top_y` (aligns with single-column stops' tops).
- Left column **bottom** anchors at `label_top_y + label_box_h` (aligns with single-column stops' bottoms).

The compression of `さいたま` (4 chars in 3-char height) is what visually signals it's the "raised, denser" half — DON'T relax it to `label_box_h`, you lose the asymmetry.

#### Single-character station name (Keihin's `蕨`)

Rendered via direct `font.render` + blit and **vertically centered** in the label box (not stacked from the top via `draw_1col_text` — that would pin it to the top).

#### Pointer chevron — uniform halo recipe

Two polygons: an inner filled red chevron and an outer outline chevron. For the halo to read uniformly:

```
delta = halo_width
outer_w      = inner_w      + delta
outer_stroke = inner_stroke + delta
outer_x      = inner_x      - delta // 2  # centers outer around inner
```

If `outer_w - outer_stroke ≠ inner_w - inner_stroke`, the tip-lengths differ and the halo reads as proportionally pointier or blunter than the fill. See the `arrow_points` docstring in `utils.py` for the full geometry. **Note that `arrow_points`'s `stroke` parameter is the chevron's BODY thickness — NOT a typical line stroke.** Scaling `inner_w` without `inner_stroke` makes the chevron *pointier*, not bigger. Geometrically: horizontal distance from the notch vertex to the tip = `stroke`. Body width = `stroke`. Tip-portion width = `w - stroke`.

#### Initial-stop pentagon (curr_stop=0)

Drawn instead of the chevron when `curr_stop == 0`. Its `overhang` must equal `inner_h_overshoot // 2` of the chevron pointer so heights match across stop=0 and mid-route frames.

#### Passing-station chevron centering

Use `(stops_w - arrow_w) // 2` for true horizontal centering. The full-route's `stops_w * 0.3` constant is an approximation that's only ~1 px off true center for narrow `stops_w=42` cells but ~8 px off for the 8-station view's `stops_w=82` cells. Don't copy the magic number across.

#### Continuity arrow scaffolding

`_draw_continuation_marker` is defined but **deliberately not called** from `show_stops`. The user has a known-buggy continuity-arrow helper in their full-route renderer; the 8-station version is parked here as scaffolding until the two implementations can be reconciled. `side_margin = 44` reserves the px the triangle will need when wired in. See the multi-line comment block above the method body for the wire-up instructions.

#### Layout tuneable params (top of `__init__`)

| param | value | what it controls |
|---|---|---|
| `VISIBLE_COUNT` | 8 | always-visible cell count |
| `LOCK_THRESHOLD` | 7 | lock-to-8-station condition (`remaining ≤ 7`) |
| `side_margin` | 44 | px reserved on each end of the bar (continuity-arrow headroom) |
| `label_top_pad` | 19 | gap below upper LCD before label band |
| `label_h_chars` | 4 | label box height = 4 char heights |
| `label_font_size` | 30 | ShinGoPr6N-Medium for kanji labels |
| `bar_height` | 38 | route-map bar |
| `bar_badge_gap` | 4 | between bar bottom and badge top |
| `badge_w / badge_h` | 22 / 22 | per-cell mini badge |
| `font_badge_prefix / num` | 8 pt / 11 pt | NeueFrutigerWorld-Bold |

#### Route disclaimer

`displays/utils.draw_route_disclaimer` renders the standard PIDS legalese (`のりかえ、待合せ時間は…`) bottom-right anchored, dark color matching active station-name labels. Both `JapaneseDisplay.show_stops` and `JapaneseEightStationDisplay.show_stops` call it as the last draw step.

### Shared utility gotchas (used by lower LCD)

#### `draw_1col_text` per-character horizontal centering (`utils.py`)

Each glyph in a vertical column is centered against the **widest character's column width**, not against the function's `x` arg directly.

Without this, mixed-width strings render off-axis: digit `2` and katakana `ビル` in `空港第2ビル` line up flush-left under the wider kanji.

The function takes a single `x` (left edge of the widest char's column) and computes per-char offsets internally — callers don't need to do anything special.

#### `arrow_points` chevron recipe (`utils.py`)

The `stroke` parameter is the chevron's **body thickness**, NOT a typical line stroke. To resize without changing shape: scale `w`, `h`, AND `stroke` by the same factor. Bumping only `w` makes the chevron pointier (longer tip, same body). See "Pointer chevron — uniform halo recipe" above for the inner/outer halo math, plus the full docstring in `utils.py`.

### Future: Element Clear-Background Convention

When the lower LCD grows past its single route-map region (e.g. when English mode is implemented and lower needs to differentiate Japanese label box vs English label box), it'll adopt the same convention as the upper LCD: per-region `_DEBUG_COLORS` + `_bg()` helper + Region Map comment block at the top of `lower_lcd.py`. The convention itself is documented above under "Upper LCD → Element Clear-Background Convention" — same rules for both displays, including the D1/D2 distinction and probing methodology.

---

## Integration with Main Application

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
        self.upper.set_state(self.state.curr_stop, self.state.cnt_pa, at_station=self.state.at_station)
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

### Key Changes from Legacy `display.py`

| Old | New |
|---|---|
| `LowerDisplay(screen, route_data, app_state, stops)` | `LowerDisplay(screen, route_data, stops, mode_cycler)` + `.set_state(state)` |
| `lower.show_stops(current_time)` | `lower.draw(current_time)` |
| `_update_skip_progress` mutates `state.skip_progress` | `AppState.update_skip_progress(current_time)` (state owns the mutation) |
| `pygame.display.flip()` inside `show_stops` | Lifted into `app.run()` after both displays draw |
| Old `draw_init()` / `draw_clock(timestamp)` / `draw_current_station()` | `set_state()` + `update(timestamp)` + `draw(time_str)` |
| One class, one mode | Per-mode renderers + Manager class |

---

## Adding New Train Model

1. Create `displays/train_models/{model_name}/` directory.
2. Copy and modify `upper_lcd.py` for fonts/positions.
3. Implement `lower_lcd.py` with `LowerDisplay`.
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay`.
5. Register in `displays/train_models/__init__.py`:

   ```python
   TRAIN_DISPLAYS["{model_name}"] = {ModelName}UpperDisplay
   ```

Per [CLAUDE.md](CLAUDE.md) "Mental Model → Per-model IRL line scope": the new model's IRL line scope determines which routes need full-fidelity behavior; everything else is best-effort.

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

## Distribution

See `/build` skill. Folder layout (alongside the exe at runtime):

```
your-folder/
├── JRE-PA-Simulator.exe
├── fonts/
├── data/
│   ├── translations.json
│   ├── train_types.json
│   └── stations.json
└── audio/
    ├── chuo/
    ├── yamanote/
    └── ...
```

`fonts/` and `data/` must ship; `audio/` is supplied by the user. Build details (PyInstaller flags, version metadata, junction handling) live in the `/build` skill itself.

---

## Testing

```bash
# Default mock route
uv run preview_display.py

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
- Mode cycling: upper changes between KANJI / FURIGANA / ENGLISH every 4s; lower stays Japanese until ENGLISH dispatch is enabled.
- Skip animation: PageDown across a passing-station gap; cursor walks forward through the passing station, inner red dot stays at the new PA target.
- Long-route window flip (Keihin-Tōhoku, Chuo): cursor pos stays correct as window slides.
- Centering: mock route (11 stops) renders with equal margins; multi-line routes unchanged.

Preview-mode swap inventory is documented at `PASimulator.__init__`'s ``preview`` parameter in `app.py`. `jump_to_stop` semantics live in its docstring at `app.py` `PASimulator.jump_to_stop`. Mock-route stop layout is in [`audio/_mock/main/README.md`](audio/_mock/main/README.md).

---

## Design Decisions

1. **Duplication OK.** Mode renderers may have ~90% similar code, but stay separate for flexibility. Different trains may need different layouts.
2. **No shared mode renderers across train models.** E235-1000's `JapaneseDisplay` is independent from a future E231-500's `JapaneseDisplay`.
3. **Position constants inlined; fonts shared.** Positions are method-specific; fonts are model-specific.
4. **Destination always kanji.** In KANJI/FURIGANA modes, destination doesn't cycle (IRL behavior).
5. **English suffix becomes prefix.** "Bound for" before the destination in ENGLISH mode.
6. **Centralized translations.** All displays load from `data/translations.json` and `data/train_types.json`.
7. **Shared cycler upper↔lower.** Single source of truth for mode timing.
8. **Pure-rendering split.** Skip-progress mutation lives on `AppState`, not the renderer.
9. **English placeholder over English-disabled-in-cycler.** Keeps the upper cycling freely; the lower's local fallback handles its own incompleteness.
10. **Centering uses actual cell count, not per_line.** Single-line short routes render centered.
11. **`constants.py` for cross-module values only.** Per-LCD-module sizes/positions/fonts live inline; only values genuinely consumed by ≥ 2 modules go in `constants.py`.

---

## Changes Log

### 2026-04-26
- Merged `UPPER_DISPLAY_UPDATE.md` + `LOWER_DISPLAY_UPDATE.md` into this single `DISPLAY.md`. Display-specific gotchas previously in `notes.md` (English Station Name, Centering Across Fonts, Station Code Badge, Skip Logic, Long-Route Refresh, `draw_1col_text`, `arrow_points`) folded in here as their canonical home.
- New "Mental Model" section added to [CLAUDE.md](CLAUDE.md) for train-family scope and best-effort policy (preloaded — humans don't re-derive "what this project is" each session). REALWORLD.md, briefly introduced earlier the same day, was collapsed into CLAUDE.md once the preloaded-vs-progressive split was articulated.
- **8-station window: sliding case now keyed on `cursor_pos` instead of `curr_stop`.** Fixes the "past cell vanishes mid-skip" bug — during a passing-station skip animation, `cursor_pos` lags behind `curr_stop`, so anchoring the window on `curr_stop` put the visible cursor at local index 0 with zero past context. Lock case stays keyed on `curr_stop` to preserve destination visibility during near-end skips. See "Window invariant" table above for the full rationale.
- 8-station pointer chevron: `offset_factor` 0.3 → 0.4. Body now sits ~15% in past cell, ~24% in cursor cell (was ~11% / ~28%) — slightly more centered on the cell boundary while keeping a mild bias toward the cursor cell.
- **Continuity arrows on full-route view**: 3 slots (row-1 tail "to", row-2 head "from", last-visible-when-slid "to"). Slot 0/2 = bar→triangle→2 chevrons; slot 1 = 2 chevrons + bar with WHITE_BG inverse-triangle notch carved into bar's left edge. Color inherits from cell (`self.color` when active, `INACTIVE_COLOR` when passed); no threshold checks. Tip-portion uniformity: `tri_w == cont_chev_w − cont_chev_stroke == 8` makes all three gaps render as a uniform 4-px white margin everywhere. Slot 1 bar is extended `+cont_tri_w` to the left to compensate for the notch carve. New helpers `draw_continuity_arrow` / `draw_continuity_triangle` in `displays/utils.py`.
- **Row-end / row-head bar extension**: every row-tail cell gets `+row_tail_extra = 10` px on the right; every row-head cell gets `+row_head_extra = 10` px on the left. Independent of continuity. `draw_times` 分-marker shift and `draw_ptr` curr_stop=0 pentagon left edge mirror these constants — change one, change all three (foot-gun documented in DISPLAY.md "Row-end / row-head bar extension" table).
- **`continuity[2]` state-leak fix** in `_get_stops_list_disp`: now recomputed on every call based on whether the visible window includes the route's last stop (not just at the `remaining == STOPS_QUANTITY - 1` transition frame). Caused slot-2 chevrons to render past Keihin's destination Ōfuna once the window had slid further forward.
- **Dest as terminus** in `app._next_pa`: non-circular routes terminate at `self.dest_stop_idx` (resolved at init by name-matching `self.dest`), not `len(self.stops) - 1`. Some route data extends past the operational dest for through-running reference (e.g. Keihin 727B's stops continue 41..45 from 磯子 to 大船). Fixed PageDown advancing into 新杉田 → … → 大船.

### 2026-04-25 (lower 8-station view + lower refactor)
- New `JapaneseEightStationDisplay` — 8-cell zoomed-in route map with sliding (1 past + cursor + 6 ahead) / locked (last 8 stops) windowing.
- New 24s view-cycler on `LowerDisplay` (12s full ↔ 12s 8-station). Locks permanently to 8-station once `remaining ≤ 7`. Timer hoisted to `LowerDisplay.draw()` so it doesn't drift while the upper is in ENGLISH.
- Compound-name two-column layout (right reads first, 3-char baseline) and single-char vertical centering.
- New shared helpers in `displays/utils.py`: `draw_station_code_badge` (extracted from upper, now also used for 8-station per-cell mini badges) and `draw_route_disclaimer`.
- Per-char horizontal centering fix in `utils.py` `draw_1col_text` for mixed-script names like `空港第2ビル`.
- `arrow_points` docstring extended with the chevron-with-uniform-halo recipe.
- `_draw_continuation_marker` defined but deliberately uncalled (deferred until the user's existing buggy full-route helper is reviewed).
- Lower LCD refactored from monolithic `display.py` (deleted) into modular `lower_lcd.py` with `JapaneseDisplay` + `EnglishDisplay` placeholder + `LowerDisplay` manager.
- Skip-progress mutation moved from renderer onto `AppState.update_skip_progress`. Renderer is now pure rendering.
- Shared `mode_cycler` with upper (constructor arg).
- `pygame.display.flip()` lifted out of renderer into `app.run()`.
- Single-line layout centering bug fixed (`min(per_line, num_stops)`).
- English mapping disabled in lower's `mode_displays` dict; falls back to Japanese until implemented.
- English mode re-enabled in upper (was temporarily disabled during the SysFont migration — file-path font loading verified, no fallback needed).
- `preview_display.py` got a `--lower-view {full,eight,cycle}` flag for forcing a deterministic frame.

### 2026-03-14
- **Font loading fix:** changed all `pygame.font.SysFont()` to `pygame.font.Font()` with direct file paths to fix crashes on non-English Windows systems (Chinese locale).
- **JSON loading fix:** updated `load_json_relative()` to use `sys.executable` instead of `__file__` for PyInstaller exe compatibility.
- Build command updated from `--windowed` to `--console` for error visibility.

### 2026-03-11
- Initial modular architecture implementation.
- 3-mode display cycling (KANJI → FURIGANA → ENGLISH).
- Integration with main application.

---

## Related Documentation

- [CLAUDE.md](CLAUDE.md) — project overview, module table, controls, "When Working On…" pointers
- [CLAUDE.md](CLAUDE.md) "Mental Model" — train-family scope, IRL line scope per model, best-effort policy, Hepburn convention (preloaded)
- [DATA_FORMAT.md](DATA_FORMAT.md) — `translations.json` / `train_types.json` / `stations.json` / `route.json` shapes, validation rules
- `displays/base.py` — `DisplayMode` enum, `ModeCycler`
- `app.py` `PASimulator.__init__` ``preview`` parameter — preview-mode swap inventory
- `displays/train_models/e235_1000/upper_lcd.py` `get_base_dir` — PyInstaller path resolution contract
- `displays/train_models/e235_1000/lower_lcd.py` `draw_times` — countdown formula contract

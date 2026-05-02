# LCD Display System

Modular per-train-model architecture for both Upper and Lower LCDs. Currently implements **E235-1000**; built to extend to other JR East series with heavy code reuse. Train-family scope and in-spec/best-effort policy live in [CLAUDE.md](CLAUDE.md) "Mental Model" (preloaded — should already be in head).

This is the canonical display doc — covers shared infrastructure, upper LCD, lower LCD, and integration. Cross-cutting code contracts live inline at their code sites (font-loading at the first font init in [`upper_lcd.py`](displays/train_models/e235_1000/upper_lcd.py); countdown formula at `lower_lcd.py` `draw_times`; PyInstaller path resolution at `upper_lcd.py` `get_base_dir`). JSON shapes are in [DATA_FORMAT.md](DATA_FORMAT.md).

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** schema reference, gotchas, invariants — implementation specifics looked up when editing the relevant submodule.
>
> **Refuses:**
> - History notes / change logs (`### 2026-03-14`, "pre-X behavior", "Key Changes from legacy …") — `git log` has this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future sections ("When X is implemented, …") — defer until needed
> - Design-discussion rationale (multi-paragraph framings of *why* a model exists) — the rule lives here; the rationale lives in `memory/YYYY-MM-DD.md`
> - Facts already in [CLAUDE.md](CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
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

Yamanote-style routes have the same station name at idx 0 and idx N. The duplicate idx 0 is a structural marker for circularity, not a state to visit mid-loop. `_advance_to_next_stop`'s loop-back branch jumps `idx N → idx 1` directly, plays `pa[0]` of the new stop, and lands in APPROACHING.

### Skip animation

Skip animation lives in `_advance_to_next_stop`. Entering STOPPING and cycling pa_at_station do not touch skip state — by the time STOPPING is entered, the train has already arrived (skip is whatever the previous advance left it at, with skip_progress catching up to skip via `update_skip_progress`). Within-pa branch zeros skip on every press as a defensive catch-up. See "Station Skip Logic (full spec)" under Lower LCD for the full contract.

### Edge cases & guards

**Audio-playing guard.** `_next_pa` early-returns when `audio.is_playing()` — both manual PageDown and `pending_next_pa` from auto-driver are dropped while audio plays. `jump_to_stop` does NOT honor this guard; instead it calls `audio.pause()` itself before mutating state, so callers (preview ←/→, click-to-jump) get a clean handoff without doing their own pause.

**`cnt_pa` is dead during STOPPING.** Naturally-entered STOPPING (via `_next_in_approaching`'s "pa exhausted" branch) leaves `cnt_pa` at `len(pa)-1`. `jump_to_stop`-entered STOPPING forces `cnt_pa=0`. Both render "ただいま X" because `at_station` overrides the prefix mapping. `cnt_pa` is not read again until `_advance_to_next_stop` resets it to `0` on exit.

**Terminus (non-circular).** `STOPPING@dest_stop_idx` is a stable end-state — pressing PageDown falls through `_advance_to_next_stop`'s final `else: return` (neither `curr_stop < terminus_idx` nor `circular == 1` is true). Silent no-op, no state change.

**`pa=[]` with non-empty `pa_at_station`.** `_is_stopping` accepts either non-empty, so advance lands such a stop in APPROACHING with `cnt_pa=0`, then calls `audio.play_pa(curr_stop, 0)` which silently returns at `audio.py:73` (`pa_index >= len(pa_tracks)`). Display flashes "次は X" with no audio for one press until the user presses again to enter STOPPING. No known route data hits this today, but `_has_pa` tolerates it.

---

## Code Style Conventions

- **Position constants are inlined** as local variables in each draw method (e.g. `box_x, box_y = 15, 8`). Different train models may need different layouts; keeping positions per-method makes that explicit.
- **Fonts are shared** as class members defined in `__init__` (e.g. `self.font_type_bold`). Fonts are consistent within a model.
- See [conventions.md § "Tuneable-params block"](.claude/rules/conventions.md) for the project-wide rule on labeled-local-variables at the top of every draw method.

### Mode Renderer Design

Each mode renderer (`JapaneseDisplay`, `FuriganaDisplay`, `EnglishDisplay`) is **self-contained**: owns its fonts, layout, and full set of draw methods. ~90% similarity across renderers is acceptable — different train models may need to diverge freely without reaching into the wrong layer. Canonical shape: `JapaneseDisplay` in `upper_lcd.py` (fonts loaded once in `__init__`, position constants inline per draw method).

### Centering Text Across Fonts

Use `surface.get_bounding_rect()` — returns tight visible-pixel bounds. **Do NOT** use `font.get_size()` / `surface.get_size()` for tight centering — those include font leading, which varies significantly per font (Frutiger's leading is much larger than Helvetica's at the same pt size), breaking alignment when swapping fonts.

Canonical example: `UpperDisplay._draw_station_code_badge` centers two text rows of different sizes inside a small badge, reactive to any font choice.

For **horizontal centering inside a fixed-width cell** (e.g. passing-station chevron in the lower LCD): use `(cell_w - element_w) // 2` for true center. Don't copy magic-number approximations like `stops_w * 0.3` — that constant happens to work for the full-route's narrow cells (~1 px off true center) but is ~8 px off in the 8-station view's wide cells.

---

## Upper LCD

### Destination Behavior

Convention (always-kanji / "Bound for" English / `&` compound separator) lives in [CLAUDE.md](CLAUDE.md) "Mental Model → IRL display conventions"; JSON encoding in [DATA_FORMAT.md § Compound Destinations](DATA_FORMAT.md).

### Stop-Level Destination Override

Used by circular routes (Yamanote) to show changing destinations. Implementation:

- Check stop-level `dest` first; fallback to route-level `dest`.
- The `dest` value is read from the current stop when drawing the upper display.
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

### Element confinement (clip-enforced)

Every upper-LCD region has a declared rect — manifest at the top of `displays/train_models/e235_1000/upper_lcd.py` (`TRAIN_TYPE_RECT`, `DEST_RECT`, `PREFIX_RECT`, `STATION_RECT`, `CLOCK_RECT`, `BADGE_RECT`, `PA_HINT_RECT`). Each region's draw method wraps its body in `with clip(self.screen, RECT):` (helper at `displays/utils.py:clip`). Pixels drawn outside the rect are dropped at the pygame layer — bleed into a neighbour's territory is structurally impossible, no eyeball check needed.

**Tuning a region's bounds** — change the rect at module top. The clip wrap, the bg fill, and the debug-grid tint all read from the same constant.

**Debug-grid mode** — `uv run preview_display.py --debug-grid` swaps each region's bg to a unique tint via `_bg("<region>")` returning its `_DEBUG_COLORS` entry. Useful for verifying a NEW region's manifest entry covers the intended footprint; not load-bearing for catching bleed (clip handles that).

**Cross-mode parity** — all three mode renderers (Japanese / Furigana / English) share the same confinement per element. Internal content layout can differ; the boundary doesn't.

**Region map** — bounds + drawn-by + debug color for every region live as a comment block at the top of `displays/train_models/e235_1000/upper_lcd.py`, alongside `_DEBUG_COLORS`. Per-train-model — stays with the code, not in this doc.

**Pygame rendering gotchas:**

- **Transparent leading does NOT clobber.** `font.render(text, True, color)` (no bg arg) returns an SRCALPHA surface; transparent pixels don't overwrite the destination on blit. A glyph surface whose top lands above its region's clip rect is safe — clip drops the transparent strip, the underlying bg survives.
- **`font.get_height()` is ~`pt_size × 0.92`** for HelveticaNeue-Medium and ShinGoPr6N-Medium, NOT `pt_size × 1.2`. Probed examples: 24pt → 22, 78pt → 78.
- **When passing a bg arg to `font.render()` inside a region**, use `_bg("<same region>")` not `DARK_BG` directly. Both render the same in normal mode, but `DARK_BG` punches solid-DARK_BG holes through the region's tint when debug-grid is on, defeating the visualization.

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

The lower needs more per-frame state than the upper (cursor_pos, skip, skip_progress, time_to_next, departure_time, frame_mode, is_last_pa). API mirrors upper's `set_state` / `update` / `draw`, but `set_state` binds an AppState reference rather than copying fields. Called once at app startup; subsequent draws read live state from the bound reference. `update(current_time)` is a no-op (the cycler is shared with upper); `draw(current_time)` dispatches to whichever mode renderer the cycler points at.

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

**Call order in `app.run()`** — renderer stays pure-read so a future English lower won't need to re-implement skip:

```python
self.state.update_skip_progress(timestamp)
self.upper.update(timestamp); self.upper.draw(...)
self.lower.draw(timestamp)
pygame.display.flip()
```

### Layout / Centering

`_calculate_layout()` decides the route-map bar geometry from `len(stops)`:

| Stop count | per_line | Lines | Notes |
|---|---|---|---|
| ≤ 14 | `num_stops` | 1 | Mock (11). Single row, centered |
| 15 to 28 | `⌈n/2⌉` | 2 | Keiyo (17→9+8), Sōbu/Jōban (19→10+9), Tōkaidō (21→11+10), Saikyō/Takasaki (24→12+12), Nambu (26→13+13) |
| > 28 | 14 | 2 + window flip | Yamanote (30), Chūō (32), Keihin-Tōhoku (46) |

**E235-1000 IRL is 14-per-line.** The previous "≤17 odd → single row of 17" fallback was a one-time concession to keep Keiyō (17 stops) on a single line even though that exceeds the real LCD's 14-cell-per-row layout. With the per-train-model split in place, the active model now honors its IRL grid; out-of-spec routes (Keiyō isn't an E235-1000 line) wrap to 2 rows under the best-effort policy. See [CLAUDE.md](CLAUDE.md) "Mental Model → Per-model IRL line scope".

**Centering:** the row x-offset uses `min(per_line, num_stops)`, not `per_line` alone. Under the current rule `per_line ≤ num_stops` always, so the `min()` is defensive — kept for code safety.

### Long-Route Window Refresh

Constants: `STOPS_PER_LINE = 14`, so `STOPS_QUANTITY = 28`. Refresh only triggers for routes with **more than 28 stops**.

Hits: Keihin-Tōhoku (46), Chuo (32), Yamanote (30). Below threshold: Nambu (26), Saikyō/Takasaki (24), etc.

Trigger: when `len(stops) - curr_stop < STOPS_QUANTITY`, `_get_stops_list_disp()` returns `self.stops[len(stops) - STOPS_QUANTITY:]` (last 28 stops).

Window carries tuples `(global_idx, stop)` — draw code doesn't need a separate `window_start` parameter to compare state, the global index travels with each cell.

**`continuity[2]` sync:** `_get_stops_list_disp` updates `continuity[2]` on **every call**, not just at the transition frame. Set to `0` whenever the window has slid (visible window includes the route's last stop, no more route past it); restored to `1` whenever the window is back at its original position and route has > 28 stops. The earlier "set once at `remaining == STOPS_QUANTITY - 1`" form left the flag stale at `[1,1,1]` after the user jumped further forward, causing slot-2 chevrons to render past the destination on Keihin (Ōfuna). Circular routes (Yamanote) keep `[1, 1, 1]` since the route always continues past the visible window via the loop.

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

- *Sliding on `cursor_pos`* keeps the "1 past cell on the cursor's left" contract honest mid-skip. If sliding were keyed on `curr_stop`, the visible cursor (at `cursor_pos < curr_stop` during a skip) would land at local index 0 with zero past context — observable as "the just-departed station vanishes the moment a passing-station skip starts."
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

---

## Integration with Main Application

Wired in `app.py` `PASimulator.__init__` (creates `upper` + `lower`, passes the upper's `mode_cycler` to the lower so modes stay in lockstep, calls `lower.set_state(self.state)`) and `PASimulator.run` (per-frame call order: `state.update_skip_progress(timestamp)` → `upper.update` + `upper.draw` → `lower.draw` → `pygame.display.flip()`).

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

## Related Documentation

- [CLAUDE.md](CLAUDE.md) — project overview, module table, controls, "When Working On…" pointers
- [CLAUDE.md](CLAUDE.md) "Mental Model" — train-family scope, IRL line scope per model, best-effort policy, Hepburn convention (preloaded)
- [DATA_FORMAT.md](DATA_FORMAT.md) — `translations.json` / `train_types.json` / `stations.json` / `route.json` shapes, validation rules
- `displays/base.py` — `DisplayMode` enum, `ModeCycler`
- `app.py` `PASimulator.__init__` ``preview`` parameter — preview-mode swap inventory
- `displays/train_models/e235_1000/upper_lcd.py` `get_base_dir` — PyInstaller path resolution contract
- `displays/train_models/e235_1000/lower_lcd.py` `draw_times` — countdown formula contract

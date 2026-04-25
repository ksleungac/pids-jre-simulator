# Project Notes & Reference

## Critical Implementation Notes

### Dictionary Keys vs Enum Usage
- **Data keys are strings**: Stop data uses `"english"`, `"furigana"`, `"name"` as keys
- **Internal state uses enum**: `DisplayMode.KANJI`, `DisplayMode.ENGLISH` for mode tracking
- **Correct pattern**: `self.stops[self.curr_stop].get("english", "")` NOT `DisplayMode.ENGLISH`

### Translation System
- Keys are **raw Japanese text** (東京，次は), NOT station codes
- Station lookup: `translations.json[station_name]` where station_name is kanji
- Train type lookup: `train_types.json[train_type]` where train_type is kanji
- Fallback chain for train types: `english_short` → `english` → kanji

### Hepburn Romanization
- **Macrons for long vowels**: ō (おう/おお), ū (う)
- Examples: Tōkyō (東京), Chūō (中央), Etchūjima (越中島)
- Not all vowels need macrons - only true long vowels (Ebisu stays as-is)
- Follows IRL JR East usage where applicable

### Code Style Preferences
- **Position constants**: Inline as local variables (`box_x, box_y = 15, 8`)
- **Fonts**: Shared as class members (`self.font_type_bold`)
- **Rationale**: Positions may differ per train model; fonts are consistent within a model

### Font Loading (CRITICAL for non-English Windows)
- **Problem**: `pygame.font.SysFont()` scans Windows font registry, which can fail on Chinese/Japanese locale systems
- **Error**: `TypeError: expected str, bytes or os.PathLike object, not int`
- **Solution**: Use `pygame.font.Font("fonts/filename.otf", size)` with direct file paths
- **Distribution**: `fonts/` folder must be placed alongside exe at runtime
- **Example**:
  ```python
  # WRONG - crashes on Chinese Windows
  self.font = pygame.font.SysFont("shingopr6nmedium", 35)

  # CORRECT - loads from file
  self.font = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
  ```

### JSON Loading (PyInstaller Exe Compatibility)
- **Problem**: In PyInstaller one-file exe, `__file__` points to temp extraction folder (`_MEIxxxxx`), not actual exe location
- **Solution**: Use `sys.executable` when `sys.frozen` is True
- **Pattern**:
  ```python
  def get_base_dir() -> Path:
      if getattr(sys, "frozen", False):
          return Path(sys.executable).parent  # Exe directory
      else:
          return Path(__file__).parent.parent.parent.parent  # Project root
  ```
- **Usage**: `load_json_relative("data/translations.json")` resolves to exe/data/translations.json at runtime

### Countdown System
- `TIME_SCALE = 60` means 60 real seconds = 1 travel minute
- Floor division: Time only decrements after **full minute** elapsed
- Formula: `max(1, time - floor(elapsed_minutes))`
- Last PA behavior: Forces display to "1" (arriving now)
- `departure_time` set when `curr_stop` increments (train departs)

### Station Skip Logic (LowerDisplay)
- **Single source of truth**: `state.curr_stop` is the only stored "where is the train" index. The visual cursor on the lower LCD is derived: `state.cursor_pos = curr_stop - max(0, skip - skip_progress)`. When no skip is in flight (`skip == 0`), cursor_pos == curr_stop.
- **Skip setup happens in `app._next_pa`'s "advance to next stop" branch** (not in the lower-LCD renderer):
  - Records `prev_stop = curr_stop`, advances `curr_stop` past passing stations to the next PA station.
  - Sets `skip = curr_stop - prev_stop - 1` (number of passing stations crossed), `skip_progress = 0`, `time_to_next = stops[curr_stop].time` if `skip > 0`.
  - First frame after this: cursor_pos = curr_stop − skip = first passing station. The cursor visibly steps onto it.
- **Time-based progression**: `AppState.update_skip_progress` increments `skip_progress` at thresholds `time_to_next * i / (skip + 1)`. cursor_pos auto-advances because it's derived. No `curr_stop_disp` mutation. Called from the main loop in `app.run()` *before* drawing each frame — keeps the lower display pure rendering (mirrors how the upper is structured).
- **Catch-up at next PA tick**: `_next_pa`'s "next PA within current stop" branch zeros `skip`/`skip_progress`/`time_to_next` on every cnt_pa increment. Cursor snaps to curr_stop. Idempotent — no-op if skip was already 0.
- **No leak class possible**: Because the "advance" branch *overwrites* skip from the gap (not appends), and the "within stop" branch unconditionally zeros it, single-PA-target leakage (the old bug) cannot recur. There is no separate "flush" path to remember.
- **Inner circle**: Drawn at `curr_stop` (PA target) via `gi == self.state.curr_stop` in `draw_marks`. During skip animation cursor_pos lags behind by `skip - skip_progress` — intentional: pointer (red triangle) shows animation position, inner dot shows the actual PA target.
- **State fields**: `skip`, `skip_progress`, `time_to_next` — three integers fully describe the animation. `cursor_pos` is a property on `AppState`, not stored.

### Long-Route Window Refresh
- Constants: `STOPS_PER_LINE = 14`, so `STOPS_QUANTITY = 28`. Refresh only triggers for routes with **more than 28 stops**.
- Hits: Keihin-Tōhoku (46), Chuo (32), Yamanote (30). Below threshold: Nambu (26), Saikyō/Takasaki (24), etc.
- Trigger: when `len(stops) - curr_stop < STOPS_QUANTITY`, `_get_stops_list_disp()` returns `self.stops[len(stops) - STOPS_QUANTITY:]` (last 28 stops) and sets `continuity = [1, 1, 0]` on the exact transition frame.
- Window carries tuples `(global_idx, stop)` — draw code doesn't need a separate `window_start` parameter to compare state, the global index travels with each cell.

### PA Track Numbering
- Tracks numbered sequentially across route (1, 2, 3, ...)
- When modifying: Only change affected stations, don't renumber subsequent stations
- Example: Moving track 1 from Station B to A only changes those two stations

### Windows Console Encoding
- Set `PYTHONUTF8=1` before running Python scripts with Japanese output
- File I/O uses `encoding='utf-8'` explicitly
- Console output requires environment variable or `sys.stdout.reconfigure('utf-8')`
- **PyInstaller exe**: Use `--console` flag to enable console window for error visibility

## Display Architecture Notes

### Mode Renderer Pattern
- Each renderer (JapaneseDisplay, FuriganaDisplay, EnglishDisplay) is **self-contained**
- Duplication across renderers is **intentional** for flexibility
- Different train models may need different layouts

### Destination Display
- **Always kanji** - no cycling to furigana (IRL behavior)
- Compound destinations use `"StationA&\nStationB"` format
- `&` indicates line break point (no space before `&`)

### Stop-Level Dest Override
- Used by circular routes (Yamanote) to show changing destinations
- Implementation: Check stop-level `dest` first, fallback to route-level
- Example: At 田町，show "東京・上野" instead of route-level "品川・東京"

### English Station Name (E235-1000)
- Font: `fonts/HelveticaNeue-Bold.otf` @ 75pt (the `.ttf` cut had macron artifacts at large sizes — gone)
- Position: `name_x = int(S_WIDTH * 0.40) + 10` (10px right of the Japanese position to give breathing room from the JO/JY badge), `name_y = UPPER_HEIGHT - name_h` (2px lower than Japanese to match reference)
- Each mode's `draw_station` owns a DARK_BG clear rect that covers its glyph box plus ~10px below for descender overflow. **Extend the rect downward only** — extending it upward into the prefix/clock band erases the clock.
- JR PIDS uses uniform horizontal smoothscale (current `collapse=True` path) for long names — they do NOT swap to a separate condensed font cut. Don't introduce one.

### Centering Text Across Fonts
- Use `surface.get_bounding_rect()` — returns tight visible-pixel bounds
- Do NOT use `font.get_size()` / `surface.get_size()` for tight centering — those include font leading, which varies significantly per font (e.g. Frutiger's leading is much larger than Helvetica's at the same pt size), breaking alignment when swapping fonts
- Canonical example: `UpperDisplay._draw_station_code_badge` in `displays/train_models/e235_1000/upper_lcd.py` — centers two text rows (JY/03) of different sizes inside a small badge, reactive to any font choice

### Station Code Badge (UpperDisplay)
- `_draw_station_code_badge()` reads `sta_code` (per-stop, from route.json) → renders the framed JY/03 square
- If the Japanese station name has a `code_3` entry in `data/stations.json`, the outer black rect extends UPWARD into a top band showing the 3-letter Roman code (white text, e.g. AKB/TYO)
- All layout knobs live in the params block at the top of the method: `code_3_band_h`, `code_3_x_offset`, `code_3_y_offset`; font size in `__init__` as `self.font_sta_code_3letter`
- **Draw order**: badge draws LAST in `UpperDisplay.draw()` (after prefix/station) so the extended top band is not clipped. The prefix DARK_BG rect and the badge share x=222 — earlier ordering painted over the top of the extension.

### stations.json (Station Metadata)
- Location: `data/stations.json` (project root). Keyed by raw Japanese station name — same key space as `translations.json`, separated by concern (translations = display text; stations = operational/physical facts).
- Line-independent — one entry per station even when it appears on multiple lines (e.g. 秋葉原 on both Yamanote and Keihin-Tohoku).
- **`code_3`** field (JR East 3-letter Roman code): exactly **22** stations total. Assignment rule is "3+ JR East systems converge" with two documented exceptions (浜松町, 高輪ゲートウェイ). The catalog is finite — do not hunt for codes on smaller stations; they use 2-character katakana telegraph codes (電略) which are a separate internal system and are NOT stored here.
- Missing `code_3` → badge skips the top band (plain JY/03 rendering, unchanged from pre-feature behavior).

### Adding New Train Model
1. Create `displays/train_models/{model_name}/` directory
2. Copy and modify `upper_lcd.py` for fonts/positions
3. Implement `lower_lcd.py` with `LowerDisplay`
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay`
5. Register in `displays/train_models/__init__.py`:
   ```python
   TRAIN_DISPLAYS["{model_name}"] = {ModelName}UpperDisplay
   ```

## Preview Mode (testing harness)

`PASimulator(preview=True)` runs the real app with two swaps: `_SilentAudio` replaces `AudioPlayer`, and `_handle_input_preview` (pygame events) replaces the `keyboard`-library polling. `pygame.mixer.init()` and `win32gui.SetWindowPos` are skipped. Everything else — route loading, `_next_pa`, `_next_sta`, draw loop — is shared with the real app. Bug fixes to state-machine code automatically apply to preview.

`preview_display.py` is the thin entry point (~110 lines of CLI plumbing + screenshot mode). No duplicated state machine.

### Mock route
- Path: `audio/_mock/main/route.json`. Default when `--route` is omitted. (`_` prefix on folder = preserved-but-not-shipped, applies to `_archive/` too.)
- Curated 11-stop fictional line — reference stations integrated as test stations so each does double duty (logic test + visual font reference). Covers: code_3 badge presence/absence, PA-track counts 0/1/2/3, 1-station skip to single-PA target (reproduces the single-PA skip-flush bug), 2-station skip to multi-PA target (happy path), long-name wrap (高輪ゲートウェイ), compound destination (品川・高輪ゲートウェイ).
- Stop indices used by `compare_fonts.py`: 0=東京 (Tokyo ref + multi-PA + TYO code_3), 1=新日本橋 (Shin-Nihombashi ref + 1-skip source), 3=錦糸町 (Kinshicho ref + 1-skip target → REPRO bug), 7=船橋 (Funabashi ref + 2-skip multi-PA target), 8=津田沼 (Tsudanuma ref + single-PA).
- Lives as a real `route.json` file — not in-code constants. Loads via the same path as real routes. Edit freely to experiment.

### `jump_to_stop(target, direction=-1)`
- Hard-jumps to a stop, bypassing PA cycle. Used by `--stop` CLI and ←/→ arrow keys.
- If target is a passing station (`pa == []`), rolls in `direction` to the nearest PA station. Default `-1` (backward) — lands on pre-skip state so PageDown exercises the skip logic.
- Consequence: `→` key is a no-op when the next station is passing. Cross skips via PageDown, not arrow keys.
- Resets `skip`/`skip_progress`/`time_to_next`/`departure_time` — preview starts from a clean state.

## Data Validation Rules

### sta_code Field
- Simple format only: `JC05` NOT `JC05_SJK`
- Suffixes go in `sta` field for audio files: `JC05_SJK`
- `null` for stations without official codes (e.g., Kawagoe Line)

### Required Fields Checklist
- `data/translations.json`: All station names must have entries
- `data/train_types.json`: Train types (optional, falls back to kanji)
- `sta_code` in every stop (value or `null`)
- `dest_furigana` is NOT stored in route.json — it's auto-looked-up from `translations.json[dest]` at load time
- **Passing stations** (`pa: []`): must NOT have `sta`, `sta_cut`, or `time`. Train doesn't stop → no departure melody. Countdown timing comes from the next PA station's `time`, which spans the whole skip.

### Key Format Patterns
| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Prefix][Number]` | Stations with JR codes | `JC01`, `JK47` |
| `name_駅名` | Stations without codes | `name_蘇我` |
| `[Japanese text]` | Translation keys | `東京`, `快速` |

## Known Quirks & Edge Cases

1. **First station PA**: May have `["1"]` for pre-departure announcement
2. **Stations with no PA**: Empty array `[]`, skipped automatically
3. **Circular routes**: First and last station same name (大崎 in Yamanote)
4. **Multiple PA tracks**: Yellow hint square shown when `len(pa_tracks) > 1`
5. **STA cut**: Seconds where melody stops and door chime begins
6. **Distribution**: See `/build` skill for folder structure and build details
7. **ModeCycler has `enabled`, NOT `paused`**: To freeze a forced mode (e.g. in preview scripts), set `cycler.enabled = False`. Assigning to `paused` silently creates a new attribute that `update()` never checks — the forced mode will un-freeze after the cycle interval elapses.

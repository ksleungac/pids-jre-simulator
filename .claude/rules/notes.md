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
- **Time-based progression**: Red arrow (●) advances through passing stations based on elapsed time
  - Travel time from stopping to stopping station divided into (skip + 1) segments
  - Example: Skip 2 stations, 10min travel → arrow moves at ~3.33min intervals
- **Two-phase approach**:
  - Phase 1 (`cnt_pa == 0`): Set `skip` count and `time_to_next`, reset `skip_progress`
  - Phase 2 (`cnt_pa >= 1`): Complete jump, deduct `skip_progress` from remaining (time-based may have already advanced)
- **Inner circle**: Always drawn at `curr_stop` (logical PA station), not `curr_stop_disp` (display can be at passing station)
- **State fields**: `time_to_next`, `skip_progress` (not just `skip`)

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

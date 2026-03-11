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

### Countdown System
- `TIME_SCALE = 60` means 60 real seconds = 1 travel minute
- Floor division: Time only decrements after **full minute** elapsed
- Formula: `max(1, time - floor(elapsed_minutes))`
- Last PA behavior: Forces display to "1" (arriving now)
- `departure_time` set when `curr_stop` increments (train departs)

### PA Track Numbering
- Tracks numbered sequentially across route (1, 2, 3, ...)
- When modifying: Only change affected stations, don't renumber subsequent stations
- Example: Moving track 1 from Station B to A only changes those two stations

### Windows Console Encoding
- Set `PYTHONUTF8=1` before running Python scripts with Japanese output
- File I/O uses `encoding='utf-8'` explicitly
- Console output requires environment variable or `sys.stdout.reconfigure('utf-8')`

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
- `dest_furigana` at route level only (auto-lookup from translations)

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

## Testing Notes

- User tests thoroughly before accepting changes
- Verify changes work in actual program, not just preview script
- Test with multiple routes when possible

## Reference Documents

- **DATA_FORMAT.md**: JSON field definitions, validation script
- **UPPER_DISPLAY_UPDATE.md**: Display architecture details
- **CLAUDE.md**: Quick reference (this file complements it)

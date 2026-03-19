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
- **Single-skip** (1 passing station): `curr_stop_disp` jumps directly to next station with PA, `skip = 0`
- **Multi-skip** (2+ passing stations): Two-phase approach
  - Phase 1 (`cnt_pa == 0`): Set `skip` count, keep `curr_stop_disp` at first passing station
  - Phase 2 (`cnt_pa >= 1`): Complete jump via `curr_stop_disp += skip - 1`
- **Rationale**: `draw_marks()` uses `effective_idx = i - skip` to compensate for multi-skip highlighting
- **Bug pattern**: Original code checked `len(pa_tracks) == 1` instead of `skip == 1`, breaking single-skip for stations with 2+ PA tracks

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
6. **Distribution folder structure**: EXE must be alongside `audio/`, `data/`, `fonts/` at same level (folders are siblings, not nested)

## Distribution Notes

**Executable folder structure (CRITICAL for release builds):**
```
dist-folder/
├── JRE-PA-Simulator.exe
├── fonts/
│   ├── ShinGoPr6N-Medium.otf
│   ├── ShinGoPr6N-Heavy.otf
│   ├── HelveticaNeue-Roman.otf
│   ├── HelveticaNeue-Medium.otf
│   └── HelveticaNeueBold.ttf
├── audio/
│   ├── chuo/
│   ├── yamanote/
│   └── ...
└── data/
    ├── translations.json
    └── train_types.json
```
- Paths are resolved relative to exe directory
- Folders must be direct siblings of exe, not nested in subfolders
- **Build command**: `uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm`
- **Console enabled**: For error visibility on non-English Windows systems

### Path Resolution Pattern

```python
def get_base_dir() -> Path:
    """Get base directory - works for both dev and PyInstaller exe."""
    if getattr(sys, "frozen", False):
        # Running as compiled exe - use exe directory
        return Path(sys.executable).parent
    else:
        # Running as script - go up from this file
        return Path(__file__).parent.parent.parent.parent
```

**Why this matters:**
- `__file__` points to `_MEIxxxxx` temp folder in PyInstaller one-file exe
- `sys.executable` points to the actual exe location
- Fonts, data, and audio are loaded relative to exe directory at runtime

## Testing Notes

- User tests thoroughly before accepting changes
- Verify changes work in actual program, not just preview script
- Test with multiple routes when possible

---

## Working Practices

### Document References in CLAUDE.md
**Rule:** When creating any new `.md` documentation file, immediately add a reference to it in `CLAUDE.md`.

**Why:** `CLAUDE.md` is the primary entry point - without a reference there, new documentation is invisible in future sessions.

**Pattern:**
```markdown
**Full docs:** [DATA_FORMAT.md](DATA_FORMAT.md) | [AUDIO_SPLITTING_WORKFLOW.md](AUDIO_SPLITTING_WORKFLOW.md)
```

---

## Reference Documents

- **[AUDIO_SPLITTING_WORKFLOW.md](../AUDIO_SPLITTING_WORKFLOW.md)** - PA/STA splitting guide
- **DATA_FORMAT.md**: JSON field definitions, validation script
- **UPPER_DISPLAY_UPDATE.md**: Display architecture details
- **CLAUDE.md**: Quick reference (this file complements it)

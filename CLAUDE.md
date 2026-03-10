# PA Simulator Project - CLAUDE.md

## Project Overview

**Japanese Train PA (Public Address) Simulator** - A pygame-based application that simulates train station announcements and arrival melodies with visual LCD display.

**Current Date:** 2026-03-07

**Last Update:**
- Real-time countdown for travel times on lower LCD (TIME_SCALE constant controls speed)
- Centralized translations.json for all furigana/english lookups
- Destination furigana now loaded from translations.json (removed from route.json)
- **Destination always displays as kanji** (no furigana cycling - IRL behavior)
- **Stop-level dest override** - Individual stops can override route-level dest (Yamanote line)
- **Black formatting** - Pre-commit hook auto-formats Python files before commit
- **3-mode display cycling** - Upper LCD cycles through KANJI → FURIGANA → ENGLISH (unified single cycling system)
- **English page support** - Upper LCD preview script prototypes English romanized display with proper fonts/layout
- **Modular display architecture (NEW 2026-03-07)** - Refactored to support multiple train models (E235-1000, E231-500, etc.) with separate Upper/Lower LCD implementations per model

---

## File Structure

```
pids_jre_simulator/
├── main.py              # Entry point - runs setup screen, then simulator
├── app.py               # PASimulator and AppState classes
├── audio.py             # AudioPlayer with loudness normalization (double-buffered temp files)
├── display.py           # UpperDisplay and LowerDisplay classes (legacy, being replaced)
├── constants.py         # All constants (screen, colors, fonts, timing)
├── utils.py             # Drawing utilities (draw_text, draw_text_given_width, etc.)
├── setup.py             # Route selection setup screen
├── preview_upper_lcd.py # Standalone preview for E235-1000 Upper LCD (uses new architecture)
├── old_version.py       # User's original backup (keep for reference)
├── pyproject.toml       # Project configuration (uses uv)
├── displays/            # NEW: Modular display system (2026-03-07)
│   ├── __init__.py      # Package entry - exports DisplayMode, ModeCycler, get_train_display
│   ├── base.py          # DisplayMode enum, ModeCycler class
│   └── train_models/
│       ├── __init__.py  # Factory registry
│       └── e235_1000/   # E235-1000 series implementation
│           ├── __init__.py      # Exports: UpperDisplay, LowerDisplay
│           ├── upper_lcd.py     # Upper LCD: JapaneseDisplay, FuriganaDisplay, EnglishDisplay
│           └── lower_lcd.py     # Lower LCD (placeholder)
├── data/
│   └── translations.json      # Central translation database (furigana, english, station names, destinations)
└── audio/               # Audio files organized by route
    ├── yamanote/
    ├── nanbu/4027F/
    ├── nanbu/603F/
    ├── chuo/916H/
    ├── chuo/1654T/
    ├── keihin/1275A/
    ├── keihin/727B/
    ├── saikyo/1349F/
    ├── saikyo/759K/
    ├── keiyo/
    ├── tokaido/
    └── joban/tsuchiura/
```

---

## Key Features Implemented

### 1. Setup Screen (NEW)
- Scans `audio/` directory for route.json files
- Extracts train diagram from folder structure (e.g., `nanbu/4027F/` → "4027F")
- Displays routes with consistent format:
  - Line 1: Route Name - Train Diagram
  - Line 2: Train Type | Destination ゆき
- Scrollable list with visual scrollbar indicator
- Controls: ↑↓ navigate, Enter select, ESC cancel

### 2. Audio Playback
- Loudness normalization to -15 LUFS using pyloudnorm
- Double-buffered temp files to avoid file locking issues
- Temp files stored in system temp directory, auto-cleaned on exit
- PA announcements and STA departure melodies

### 3. Visual Display
**Upper Section (dark background):**
- Train type box (italic bold)
- Destination with ゆき/方面 suffix
- Color band
- Prefix: ただいま → 次は → まもなく
- Station name with even character spacing (draw_text_given_width)
- Yellow hint square (bottom right) when station has multiple PA tracks
- Clock (top right)

**Lower Section (route map):**
- Station markers with proper spacing
- Progress indicator (pointer triangle)
- Passed/current/future station states
- Travel time with real-time countdown (see Real-Time Countdown System below)
- "分" markers at line breaks and destination

### 4. Controls
- **Page Down**: Advance to next PA (no effect while audio playing)
- **Page Up**: Play STA melody (jumps to sta_cut if already playing)
- **End**: Pause audio playback

### 5. Route Support
- Circular routes (e.g., 山手線 - loops back to start)
- Multi-diagram routes (e.g., 南武線 4027F, 603F)
- Variable color schemes per route (color, contrast_color, type_color)
- Stations with no PA announcements (skipped automatically)

### 6. Furigana Cycling (Updated 2026-03-05)
**Upper LCD cycles through 3 modes every 2 seconds:**
- **KANJI** (mode 0): Japanese kanji characters
- **FURIGANA** (mode 1): Japanese phonetic furigana
- **ENGLISH** (mode 2): English romanized with macrons (Hepburn system)
- **Destination** (left side): **Always kanji, no cycling** (IRL behavior)
- **Prefix** (center): "次は" → "つぎは" in FURIGANA mode, "Next" in ENGLISH mode
- **Station name** (right side): Cycles based on mode (kanji/furigana/english)
- **Graceful fallback**: If station lacks furigana or English data, that mode is skipped in cycle
- **Single cycling system**: Uses `DisplayMode` enum (not dual-layer approach)
- **Preview script**: `preview_upper_lcd.py` for prototyping display layouts

### 7. Stop-Level Destination Override (NEW 2026-03-04)
**Individual stops can override the route-level `dest` field:**
- Used by Yamanote line to show changing destinations around the loop
- Example: At 田町，destination shows "東京・上野" instead of route-level "品川・東京"
- Implementation: `UpperDisplay._get_current_dest()` checks stop-level `dest` first
- Compound destinations use `"Shinagawa&\nTokyo"` format for multi-line English display

### 8. Real-Time Countdown System (Updated 2026-03-04)
**Lower LCD travel times count down in real-time as the train travels:**
- **Countdown start**: When train departs (first PA of new segment, `curr_stop` increments)
- **Display formula**: `max(1, time - floor(elapsed_minutes))`
- **Full minute rule**: Time only decrements after full minute has elapsed (e.g., "3" shows for entire first minute)
- **Last PA behavior**: When on last PA of station, display forces to "1" (arriving now)
- **TIME_SCALE constant**: Controls countdown speed
  - `TIME_SCALE = 60` → Real-time (60 real seconds = 1 travel minute)
  - `TIME_SCALE = 5` → Fast (5 real seconds = 1 travel minute, for testing)
  - Lower value = faster countdown

**Implementation:**
- `AppState.departure_time`: Timestamp when train departed for current segment
- `AppState.is_last_pa`: Flag set when on last PA before arriving
- `draw_times()`: Calculates elapsed time and applies countdown logic
- Main loop calls `show_stops(current_time=timestamp)` every frame for smooth updates

### 9. Modular Display Architecture (NEW 2026-03-07)
**Refactored display system to support multiple train models with different LCD styles:**
- **Train model isolation**: Each train model (E235-1000, E231-500) has its own display classes
- **Mode renderer pattern**: JapaneseDisplay, FuriganaDisplay, EnglishDisplay are self-contained
- **Manager class**: UpperDisplay handles mode cycling and delegates rendering
- **Factory pattern**: `get_train_display("e235_1000")` returns model-specific display
- **Room for Lower LCD**: Architecture supports `lower_lcd.py` per train model
- **See UPPER_DISPLAY_UPDATE.md** for detailed architecture documentation

---

## Module Responsibilities

### `constants.py`
- `S_WIDTH=730`, `S_HEIGHT=420`
- `UPPER_HEIGHT=int(S_HEIGHT * 0.28)`
- Font configurations (shingopr6nmedium, shingopr6nheavy, helveticaneueroman)
- Colors: DARK_BG, WHITE_BG, PASSED_COLOR, CURRENT_COLOR, INACTIVE_COLOR
- Timing: FRAME_RATE=15, KEY_REPEAT_DELAY=200, AUDIO_FADE_MS=800
- **`STATION_DISPLAY_INTERVAL=4`** - Seconds between kanji/furigana cycling
- **`TIME_SCALE=60`** - Real-time countdown speed (60 real secs = 1 travel minute)

### `utils.py`
- `draw_text()` - Text with optional scaling
- `draw_text_given_width()` - Even character spacing (critical for station names)
- `draw_aapolygon()` - Antialiased polygons
- `arrow_points()` - Arrow shape generation
- `draw_1col_text()` - Vertical text
- `draw_stops_text()` - Station name rendering

### `setup.py`
- `SetupScreen` class
- `scan_routes()` - Walk audio/, extract diagram from folder name
- `draw()` - Render route list with scrolling
- `run()` - Event loop, returns config dict or None

### `audio.py`
- `AudioPlayer` class
- Double-buffered temp file management
- `play_pa()`, `play_sta()` - Playback with normalization
- `pause()`, `is_playing()` - State queries
- Auto-cleanup via atexit handler

### `display.py`
- `UpperDisplay` - Train info, station name, clock, hint square
  - **`DisplayMode` enum**: KANJI (0), FURIGANA (1), ENGLISH (2)
  - **`_get_current_dest()`** - Gets current destination, checking stop-level override first
  - **`_update_display_mode()`** - Cycles through 3 modes every 2 seconds
  - **`_draw_destination()`** - Draws destination (always kanji, no cycling)
  - **`_draw_prefix()`** - Draws prefix with 3-mode support (kanji/furigana/english)
  - **`_draw_station_name()`** - Draws station name with 3-mode support
  - **`_get_current_layout()`** - Returns layout config for current mode (KANJI/FURIGANA share same layout)
  - `draw_clock()` - Updates display mode and redraws cycling elements
  - **Layout sharing**: FURIGANA reuses KANJI layout via `.copy()` (programmatically shared, not duplicated)
- `LowerDisplay` - Route map, markers, times, pointer
- Both receive route_data, app_state, **and stops** (merged data) via dependency injection

### `app.py`
- `AppState` - curr_stop, cnt_pa, cnt_sta, curr_stop_disp, skip, frame_mode, **departure_time**, **is_last_pa**
- `PASimulator` - Main application class
- **`_load_station_db()`** - Loads `data/translations.json` from project root (central translation database)
- **`_merge_station_data()`** - Merges furigana/english into stops by looking up station name in translations.json
- **`_load_route_data()`** - Loads route.json, then looks up `dest_furigana` from translations.json using `dest` key
- `_init_pygame()`, `run()`, `_handle_input()`
- `_next_pa()` - Advance PA (blocked while playing)
- `_next_sta()` - Play STA (jumps to sta_cut if playing)

### `main.py`
- Initialize pygame
- Run setup screen
- Launch simulator with selected config
- Error handling and cleanup

---

## Known Behaviors (Verified Working)

1. **PA Playback**: Page Down advances PA, blocked while audio is playing
2. **STA Playback**: Page Up plays from start, pressing again while playing jumps to sta_cut position
3. **Pause**: End key pauses playback
4. **Upper Display Updates**: Station name and prefix update correctly on Page Down
5. **Yellow Hint Square**: Appears at bottom-right of upper section when station has >1 PA tracks
6. **Character Spacing**: Station names use even character spacing (draw_text_given_width)
7. **Route Scrolling**: Setup screen scrolls and shows scrollbar indicator
8. **Temp File Cleanup**: Uses system temp dir, auto-deleted on exit
9. **3-Mode Cycling**: Upper LCD cycles KANJI → FURIGANA → ENGLISH every 2 seconds (DisplayMode enum)
10. **Destination Always Kanji**: Destination stays as kanji, no cycling (IRL behavior)
11. **Stop-Level Dest Override**: Individual stops can override route-level dest (Yamanote line)
12. **Real-Time Countdown**: Lower LCD travel times count down in real-time from departure
13. **Last PA Forces Time to 1**: When on last PA before arriving, display shows "1" (arriving now)
14. **Full Minute Rule**: Time only decrements after full minute elapsed (e.g., "3" → "2" after 1 min)
15. **Black Formatting**: Pre-commit hook auto-formats Python files with black before commit
16. **Graceful Fallback**: If station lacks furigana/English data, that mode is skipped in cycle
17. **Layout Sharing**: FURIGANA mode reuses KANJI layout config (programmatically via .copy())

---

## Testing Checklist (For Next Session)

- [ ] Test all routes in audio/ folder
- [ ] Verify circular route behavior (山手線 loops correctly)
- [ ] Test stations with no PA announcements (skipped correctly)
- [ ] Verify STA cut position works for all stations
- [ ] Test keyboard input responsiveness
- [ ] Verify audio normalization doesn't clip
- [ ] Test route selection with multiple diagrams (南武線 4027F vs 603F)

---

## Running The Simulator

```bash
# Using uv (recommended)
uv run main.py

# Or activate venv first
.venv\Scripts\activate
python main.py
```

---

## Dependencies (from pyproject.toml)

- pygame
- soundfile
- pyloudnorm
- keyboard
- pywin32

---

## Notes for Next AI

1. **Character spacing is critical** - use draw_text_given_width for station names
2. **Playback behavior is specific** - review _next_pa() and _next_sta() logic carefully
3. **3-mode cycling system** - DisplayMode enum (KANJI=0, FURIGANA=1, ENGLISH=2), single cycling logic
4. **Translation lookup by Japanese text** - keys are raw Japanese text (e.g., `東京`), not station codes
5. **dest_furigana auto-lookup** - `dest` value in route.json is used to lookup furigana from translations.json
6. **Line-specific stations.json** - `audio/[line]/stations.json` keeps keys only (empty values) for future line-specific data
7. **Windows console encoding** - set `PYTHONUTF8=1` when running Python scripts that output Japanese characters
8. **TIME_SCALE constant** - Controls real-time countdown speed (60=real-time, lower=faster testing)
9. **Countdown timing** - Time decrements only after full minute elapsed (floor division)
10. **departure_time tracking** - Set in AppState when curr_stop increments (train departs)
11. **Destination always kanji** - Upper LCD destination does NOT cycle to furigana (IRL behavior)
12. **Stop-level dest override** - Stops can have `dest` field to override route-level destination
13. **Compound destination format** - English uses `"StationA&\nStationB"` for multi-line display
14. **Layout sharing pattern** - FURIGANA reuses KANJI layout via `.copy()` (not duplicated code)
15. **Graceful fallback** - If station lacks data for a mode, that mode is skipped in cycling
16. **Preview script for prototyping** - `preview_upper_lcd.py` for testing display changes before integrating to display.py
17. **Hepburn romanization with macrons** - English translations use ō/ū for long vowels (Tōkyō, Yūrakuchō)
18. **Modular display architecture** - New `displays/` package supports multiple train models; use `get_train_display()` factory or import directly from `displays.train_models.e235_1000`
19. **Mode renderer pattern** - Each display mode (JapaneseDisplay, FuriganaDisplay, EnglishDisplay) is self-contained with its own fonts/positions; duplication across modes is intentional for flexibility
20. **Adding new train model** - Create `displays/train_models/{model}/` with `upper_lcd.py`, `lower_lcd.py`, `__init__.py`; register in `displays/train_models/__init__.py`

**Personal working preferences** are in `.claude/rules/preferences.md` (naming conventions, collaboration style, tooling).

---

## Data Format Specification

For detailed JSON data format specifications (route.json, stations.json field definitions, conventions), see **[DATA_FORMAT.md](DATA_FORMAT.md)**.

---

## Display Architecture Documentation

For detailed documentation on the modular display architecture (train models, mode renderers, cycling system), see **[UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md)**.


# PA Simulator Project - CLAUDE.md

## Project Overview

**Japanese Train PA (Public Address) Simulator** - A pygame-based application that simulates train station announcements and arrival melodies with visual LCD display.

**Current Date:** 2026-02-28

**Last Refactor:** Fresh refactor completed with modular architecture and new setup screen feature.

---

## File Structure

```
pids_jre_simulator/
├── main.py              # Entry point - runs setup screen, then simulator
├── app.py               # PASimulator and AppState classes
├── audio.py             # AudioPlayer with loudness normalization (double-buffered temp files)
├── display.py           # UpperDisplay and LowerDisplay classes
├── constants.py         # All constants (screen, colors, fonts, timing)
├── utils.py             # Drawing utilities (draw_text, draw_text_given_width, etc.)
├── setup.py             # Route selection setup screen (NEW FEATURE)
├── old_version.py       # User's original backup (keep for reference)
├── pyproject.toml       # Project configuration (uses uv)
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
- Travel time accumulation
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

---

## Module Responsibilities

### `constants.py`
- `S_WIDTH=730`, `S_HEIGHT=420`
- `UPPER_HEIGHT=int(S_HEIGHT * 0.28)`
- Font configurations (shingopr6nmedium, shingopr6nheavy, helveticaneueroman)
- Colors: DARK_BG, WHITE_BG, PASSED_COLOR, CURRENT_COLOR, INACTIVE_COLOR
- Timing: FRAME_RATE=15, KEY_REPEAT_DELAY=200, AUDIO_FADE_MS=800

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
- `LowerDisplay` - Route map, markers, times, pointer
- Both receive route_data and app_state via dependency injection

### `app.py`
- `AppState` - curr_stop, cnt_pa, cnt_sta, curr_stop_disp, skip, frame_mode
- `PASimulator` - Main application class
- `_load_route_data()`, `_init_pygame()`, `run()`, `_handle_input()`
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

## Potential Future Enhancements (Discuss With User)

1. **Home Key**: Small window mode (partially implemented in app.py, commented out)
2. **Additional Routes**: Easy to add by creating audio/[route]/[diagram]/ folders
3. **Volume Control**: Currently no user volume control
4. **Playback Speed**: Could add variable speed playback
5. **Playlist Mode**: Queue multiple routes/trains
6. **Settings Persistence**: Remember last selected route
7. **Visual Themes**: Custom color schemes
8. **Export/Recording**: Record PA sequences

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

1. **User prefers sta naming convention** (not "departure_melody" or similar)
2. **Folder structure is important** - diagram extracted from folder name
3. **Character spacing is critical** - use draw_text_given_width for station names
4. **Playback behavior is specific** - review _next_pa() and _next_sta() logic carefully
5. **User tests thoroughly** - verify changes work before presenting

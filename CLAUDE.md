# PA Simulator Project - CLAUDE.md

## Project Overview

**Japanese Train PA (Public Address) Simulator** - A pygame-based application that simulates train station announcements and arrival melodies with visual LCD display.

**Current Date:** 2026-03-14

**Last Update:**
- v0.5.0 release: GitHub Actions auto-build workflow, bilingual README
- Executable distribution: exe must be alongside `audio/`, `data/`, `fonts/` at same level
- Modular UpperDisplay integrated from `displays/train_models/e235_1000/upper_lcd.py`
- English train type display with `data/train_types.json` (`english_short` for narrow boxes)
- Code refactor: inlined position constants, fonts shared as class members
- Hepburn romanization with macrons (中央特快 → Chūō Special Rapid)
- Session scratch log for misc interaction notes
- Filename-based PA tracks: `pa` array uses descriptive filenames (e.g., `"tokyo_dep"`) instead of sequential numbers
- Station skip logic fix: single-skip jumps immediately, multi-skip uses two-phase approach
- **Font loading fix**: Changed `pygame.font.SysFont()` to `pygame.font.Font()` with direct file paths to fix crashes on non-English Windows (Chinese locale)
- **JSON loading fix**: Uses `sys.executable` for path resolution in PyInstaller exe (avoids temp folder `_MEIxxxxx` issues)
- **English mode disabled**: Temporarily disabled until fonts verified (KANJI → FURIGANA cycling only)
- **Build command**: Changed from `--windowed` to `--console` for error visibility

---

## File Structure

```
pids_jre_simulator/
├── main.py, app.py, audio.py, display.py (LowerDisplay), constants.py, utils.py
├── displays/                          # Modular display system
│   ├── base.py                        # DisplayMode enum, ModeCycler
│   └── train_models/e235_1000/
│       ├── upper_lcd.py               # Japanese/Furigana/EnglishDisplay, UpperDisplay
│       └── lower_lcd.py               # Placeholder
├── data/
│   ├── translations.json              # Station names (furigana, english)
│   └── train_types.json               # Train type English translations
└── audio/[line]/[diagram]/route.json
```

---

## Key Features

1. **Display Cycling** (2s each): KANJI → FURIGANA (ENGLISH disabled until fonts verified)
   - Destination: always kanji (IRL behavior)
   - Prefix/Station: cycle with translations
   - Train type: cycles, uses `english_short` if available

2. **Modular Architecture**: Per-train-model displays (E235-1000, E231-500...)
   - Mode renderers: self-contained (JapaneseDisplay, etc.)
   - Manager: UpperDisplay handles cycling + delegates rendering

3. **Stop-Level Dest Override**: Circular routes (Yamanote) change destination mid-route

4. **Real-Time Countdown**: `TIME_SCALE=60` (60s = 1 travel minute), floor division

5. **Audio**: -15 LUFS normalization, double-buffered temp files

6. **Cross-Platform Font Loading**: Uses `pygame.font.Font()` with file paths (avoids Windows font registry issues on non-English systems)

7. **PyInstaller Exe Compatibility**: JSON loading uses `sys.executable` for path resolution (not `__file__`)

---

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `constants.py` | S_WIDTH=730, S_HEIGHT=420, TIME_SCALE=60, FRAME_RATE=15 |
| `utils.py` | draw_text, draw_text_given_width (even spacing), draw_aapolygon |
| `audio.py` | AudioPlayer class, play_pa/sta, pause, is_playing |
| `display.py` | LowerDisplay (legacy, still in use) |
| `displays/` | UpperDisplay (E235-1000): set_state(), update(), draw() |
| `app.py` | PASimulator, AppState, translation loading, PA/STA handling |
| `main.py` | Entry point, setup screen, error handling |

---

## Known Behaviors

1. PA: Page Down (blocked while playing)
2. STA: Page Up (jumps to sta_cut if playing)
3. Pause: End key
4. Yellow hint: Multiple PA tracks indicator
5. Destination: always kanji (no cycling)
6. Graceful fallback: Skip missing furigana/English modes
7. Countdown: Full minute rule, forces "1" on last PA
8. Black formatting: Pre-commit hook
9. Station skip: Single-skip (1 passing station) jumps directly; multi-skip (2+) uses two-phase approach
10. Font loading: Uses `pygame.font.Font()` with file paths (not `SysFont()`) to avoid Windows registry issues
11. JSON loading: Uses `sys.executable` when frozen, `__file__` when running as script
12. English mode: Currently disabled (KANJI → FURIGANA only) until fonts verified

---

## Critical Notes for Next AI

**See [.claude/rules/notes.md](.claude/rules/notes.md)** for detailed implementation patterns:
- Dictionary keys vs enum usage
- Translation lookup (raw Japanese text keys)
- Hepburn macrons (ō, ū)
- Position constants inline, fonts as class members
- WINDOWS console encoding (`PYTHONUTF8=1`)
- **Font loading**: Use `pygame.font.Font("fonts/...")` not `SysFont()` - avoids Windows font registry crashes on non-English systems
- **JSON loading**: Use `sys.executable.parent` when `sys.frozen` for PyInstaller exe path resolution

---

## Running

```bash
uv run main.py
```

---

## Distribution Folder Structure

**Executable must be placed alongside folders at same level:**

```
your-folder/
├── JRE-PA-Simulator.exe
├── fonts/
│   ├── ShinGoPr6N-Medium.otf
│   ├── ShinGoPr6N-Heavy.otf
│   ├── HelveticaNeue-Roman.otf
│   ├── HelveticaNeue-Medium.otf
│   └── HelveticaNeueBold.ttf
├── data/
│   ├── translations.json
│   └── train_types.json
└── audio/
    ├── chuo/
    ├── yamanote/
    └── ...
```

The exe loads audio/data/fonts relative to its directory - folders must be siblings, not nested.

**Build command:**
```bash
uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm
```

**Key notes:**
- `--console` enabled for error visibility on non-English Windows systems
- Fonts/data/audio not bundled inside exe - loaded from runtime directory
- Path resolution uses `sys.executable` (not `__file__`) to handle PyInstaller temp folder

---

**Full docs:** [DATA_FORMAT.md](DATA_FORMAT.md) | [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md)

**Implementation notes:** [.claude/rules/notes.md](.claude/rules/notes.md) - Detailed patterns, edge cases, validation rules

**Preferences:** [.claude/rules/preferences.md](.claude/rules/preferences.md) - User preferences, working style

**Session log:** [SCRATCH.md](SCRATCH.md) - Recent interaction notes (dated, under 200 lines)


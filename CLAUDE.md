# PA Simulator Project - CLAUDE.md

## Project Overview

**Japanese Train PA (Public Address) Simulator** - A pygame-based application that simulates train station announcements and arrival melodies with visual LCD display.

---

## Session Startup

Before doing anything else:

1. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context
2. Read [memory/MEMORY.md](memory/MEMORY.md) — long-term memory and operating principles
3. Read [preferences.md](.claude/rules/preferences.md) — user preferences and working style

Don't ask permission. Just do it.

## Red Lines

* Don't exfiltrate private data. Ever.
* Don't run destructive commands without asking.
* When in doubt, ask.

## Memory

You wake up fresh each session. These files are your continuity:

* **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
* **Long-term:** `memory/MEMORY.md` — your curated memories, like a human's long-term memory

Capture what matters. Decisions, context, things to remember. Skip the secrets unless asked to keep them.

### 🧠 MEMORY.md - Your Long-Term Memory

* You can **read, edit, and update** MEMORY.md freely in sessions
* Write significant events, thoughts, decisions, opinions, lessons learned
* This is your curated memory — the distilled essence, not raw logs
* Over time, review your daily files and update MEMORY.md with what's worth keeping

### 📝 Write It Down - No "Mental Notes"!

* **Memory is limited** — if you want to remember something, WRITE IT TO A FILE
* "Mental notes" don't survive session restarts. Files do.
* When someone says "remember this" → update `memory/YYYY-MM-DD.md` or relevant file
* When you learn a lesson → update CLAUDE.md, rules, or the relevant skill
* When you make a mistake → document it so future-you doesn't repeat it
* **Text > Brain**

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

## When Working On...

**Don't read these upfront — consult when needed:**

- **Data/JSON** → Read [DATA_FORMAT.md](DATA_FORMAT.md) first
  - Working with `data/`, translations.json, train_types.json, route.json, stations.json

- **Display/UI** → Read [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md) first
  - Working with `displays/`, UpperDisplay, LowerDisplay, mode cycling

- **Audio/Diagram** → Read [AUDIO_SPLITTING_WORKFLOW.md](AUDIO_SPLITTING_WORKFLOW.md) first
  - Working with `audio/`, PA/STA splitting, creating new diagrams

- **Code Patterns** → Read [.claude/rules/notes.md](.claude/rules/notes.md) first
  - Font loading, JSON paths, PyInstaller, station skip logic

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

**Create Release:**
```powershell
# Build exe, create zip, and publish release in one command
.\release.ps1 v0.5.0b
```
- Requires `gh` CLI authenticated with `workflow` scope
- Creates distribution zip: exe + fonts + data + empty audio folder
- Uploads both standalone exe and distribution zip to GitHub release

---

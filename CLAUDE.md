# PA Simulator Project

Japanese Train PA (Public Address) Simulator — pygame-based app simulating station announcements and arrival melodies with visual LCD display.

## Quick Start

```bash
uv run main.py
```

Build executable: use `/build` skill. Code review: use `/review-dirty` or `/review-plus-fix-relentlessly`.

## Session Startup

Before doing anything else:
1. Read `memory/YYYY-MM-DD.md` (today and yesterday) for recent context
2. Read [memory/MEMORY.md](memory/MEMORY.md) — long-term memory index
3. Read [.claude/rules/preferences.md](.claude/rules/preferences.md) — user preferences

## Memory (project-level, in-repo)

This is a separate system from any auto-memory the host may provide. It lives in `memory/` and travels with the repo.

- **Daily logs**: `memory/YYYY-MM-DD.md` — what happened, decisions, context for the day
- **Curated index**: `memory/MEMORY.md` — one-line pointers to the daily logs worth keeping

Rules:
- Write it down. "Mental notes" do not survive session restarts; files do.
- Capture WHY, not just WHAT. Git log already has what changed.
- Use `/session-recap` at the end of a session to write the day's log and update the index.

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
│   ├── train_types.json               # Train type English translations
│   └── stations.json                  # Station metadata, line-independent (3-letter codes; more fields later)
└── audio/[line]/[diagram]/route.json
```

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

## Key Features

1. **Display Cycling** (2s each): KANJI → FURIGANA → ENGLISH. Destination always kanji (IRL behavior).
2. **Modular Architecture**: Per-train-model displays (E235-1000, E231-500...). Mode renderers are self-contained.
3. **Stop-Level Dest Override**: Circular routes (Yamanote) change destination mid-route.
4. **Real-Time Countdown**: `TIME_SCALE=60` (60s = 1 travel minute), floor division, forces "1" on last PA.
5. **Audio**: -15 LUFS normalization, double-buffered temp files.
6. **Station Skip**: Time-based red arrow progression through passing stations.
7. **Station Code Badge**: JY/03 framed square + optional 3-letter code (AKB, TYO, ...) for the 22 major JR East interchange stations. Code source: `data/stations.json` keyed by Japanese name.

## Controls

| Key | Action |
|-----|--------|
| Page Down | Play PA (blocked while playing) |
| Page Up | Play STA (jumps to sta_cut if playing) |
| End | Pause |

Yellow hint square = multiple PA tracks available.

## When Working On...

**Don't read these upfront — consult when needed:**

- **Data/JSON** → Read [DATA_FORMAT.md](DATA_FORMAT.md) first
- **Display/UI** → Read [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md) first
- **Audio/Diagram** → Read [AUDIO_SPLITTING_WORKFLOW.md](AUDIO_SPLITTING_WORKFLOW.md) first
- **Code Patterns** → Read [.claude/rules/notes.md](.claude/rules/notes.md) — font loading, JSON paths, PyInstaller, station skip logic, distribution
- **Building/Releasing** → Use `/build` skill

# PA Simulator Project

Japanese Train PA (Public Address) Simulator — pygame-based app simulating station announcements and arrival melodies with visual LCD display.

## Quick Start

```bash
uv run main.py
```

Build executable (local test build): use `/build` skill. Cut a GitHub release: `.\release.ps1 v<version>` (tag first). Update READMEs / translations: use `/readme` skill. Code review: use `/review-dirty` or `/review-plus-fix-relentlessly`. Commit hygiene: use `/commit` skill.

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
├── main.py, app.py, audio.py, constants.py, utils.py
├── preview_display.py                 # Audio-free preview entry point — uses PASimulator(preview=True)
├── displays/                          # Modular display system
│   ├── base.py                        # DisplayMode enum, ModeCycler
│   └── train_models/e235_1000/
│       ├── upper_lcd.py               # Japanese/Furigana/EnglishDisplay, UpperDisplay
│       └── lower_lcd.py               # Japanese/EnglishDisplay (placeholder), LowerDisplay
├── data/
│   ├── translations.json              # Station names (furigana, english)
│   ├── train_types.json               # Train type English translations
│   └── stations.json                  # Station metadata, line-independent (3-letter codes; more fields later)
└── audio/
    ├── [line]/[diagram]/route.json    # Real routes
    └── _mock/main/route.json          # Curated edge-case catalog for preview (`_` prefix = not shipped)
```

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `constants.py` | S_WIDTH=730, S_HEIGHT=420, TIME_SCALE=60, FRAME_RATE=15 |
| `utils.py` | draw_text, draw_text_given_width (even spacing), draw_aapolygon |
| `audio.py` | AudioPlayer class, play_pa/sta, pause, is_playing |
| `displays/` | Modular per-train-model UpperDisplay + LowerDisplay (E235-1000): set_state(), update(), draw() |
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
8. **Single train-position index** (`app.py` `AppState`): `state.curr_stop` is the only stored "where is the train" index. The visual cursor `state.cursor_pos` is a derived property: `curr_stop - max(0, skip - skip_progress)`. During skip animation the cursor lags behind curr_stop and walks forward as `skip_progress` ticks up. All rendering uses global indices; rendering iterates `(global_idx, stop)` pairs from `_get_stops_list_disp()` and local column index appears only in pixel math.

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
- **Upper LCD** → Read [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md) first
- **Lower LCD** → Read [LOWER_DISPLAY_UPDATE.md](LOWER_DISPLAY_UPDATE.md) first (sections marked **🔁 Shared with UPPER** are duplicated — keep in sync)
- **Audio/Diagram** → Use `/split-audio` skill (PA + STA splitting, naming conventions, route.json updates)
- **Code Patterns** → Read [.claude/rules/notes.md](.claude/rules/notes.md) — font loading, JSON paths, PyInstaller, station skip logic, long-route refresh, preview mode
- **Testing / previewing** → `uv run preview_display.py` defaults to the mock catalog (`audio/_mock/main`). Keys: PageDown=PA, PageUp=STA, M=mode, ←/→=jump, ESC=quit. See notes.md "Preview Mode" for `jump_to_stop` backward-rounding semantics.
- **Building/Releasing** → Use `/build` skill

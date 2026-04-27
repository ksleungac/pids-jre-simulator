# PA Simulator Project

Japanese Train PA (Public Address) Simulator — pygame-based app simulating station announcements and arrival melodies with visual LCD display.

## Quick Start

```bash
uv run main.py
```

Build executable (local test build): use `/build` skill. Cut a GitHub release: `.\release.ps1 v<version>` (tag first). Update READMEs / translations: use `/readme` skill. Code review: use `/review-dirty` or `/review-plus-fix-relentlessly`. Commit hygiene: use `/commit` skill.

## Mental Model

What this project is modeling. Keep this in head — it shapes every design decision. (Implementation details live in domain docs and are read on demand.)

### Train family

JR East runs multiple train series in commuter service: E233 (sub-series 0–8000), E235 (0 and 1000), and others. Each series has its own LCD look — drawings differ slightly, but the *element set* (clock, station name, route bar, mode cycling, badges, view alternation) is mostly shared. Adding a new model is largely re-skinning, not re-architecting.

In the codebase, each train model lives under `displays/train_models/{model}/`. Heavy reuse across models is expected.

### Per-model IRL line scope (in-spec vs best-effort)

Every train series only runs on a fixed subset of JR East lines IRL — and real-world PIDS only ever displays data from those lines. The exact line↔series mappings are NOT memorized; ask or look up when scope matters for a design decision.

The simulator accepts **any** route loaded into **any** train model — including routes the active model never serves IRL (Yamanote / Chuo / Keihin-Tōhoku used as long-route stress tests, the `_mock` catalog, future user-supplied routes). Reality only constrains the in-spec subset.

| Route relative to active model | Behavior |
|---|---|
| **In-spec** (model's IRL lines) | Match real PIDS |
| **Out-of-spec** | Best-effort (floors below) |

- **Hard floor:** no crashes, no missing-key errors, no broken layouts. Cycling, skip animation, view alternation behave identically to in-spec routes.
- **Soft floor:** long names truncate, missing translations fall back, odd stop counts use existing layout regimes.
- **Not obligated:** IRL-accurate fidelity for a line the model never serves — there's no reference to match.

When a specific line or series comes up in conversation, treat it as scope context for the active model — not a request to recite mappings.

### IRL display conventions

Behaviors true on real trains and mirrored by the simulator:

- **Destination stays kanji even in furigana mode.** Only station name and prefix cycle. English mode uses "Bound for" + English destination.
- **Stop-level destination override.** Circular routes (Yamanote) change the displayed destination as the train traverses the loop.
- **Station code 3-letter Roman badge** for ~22 major interchange stations (AKB, TYO, …). Rule of thumb: "3+ JR East systems converge," with documented exceptions. Smaller stations use 2-character katakana telegraph codes (電略) — separate internal system, not modeled here.
- **Compound destinations** like 品川・東京 use a `&` separator on real PIDS for the multi-line layout.
- **English text uses modified Hepburn romanization with macrons** (Tōkyō, Chūō, Etchūjima). JSON-encoding details in [DATA_FORMAT.md](DATA_FORMAT.md).

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
├── main.py, app.py, audio.py, constants.py
├── preview_display.py                 # Audio-free preview entry point — uses PASimulator(preview=True)
├── displays/                          # Modular display system
│   ├── base.py                        # DisplayMode enum, ModeCycler
│   ├── utils.py                       # ALL drawing primitives + display-domain helpers (draw_text, draw_aapolygon, arrow_points, draw_station_code_badge, draw_route_disclaimer, draw_continuity_*)
│   └── train_models/e235_1000/
│       ├── __init__.py                # Per-model dimensions/palette: S_WIDTH, S_HEIGHT, UPPER_HEIGHT, DARK_BG, WHITE_BG (defined before class imports for partial-module safety)
│       ├── upper_lcd.py               # JapaneseDisplay + FuriganaDisplay (inherits Japanese, no override) + EnglishDisplay + UpperDisplay manager
│       └── lower_lcd.py               # JapaneseDisplay (full route) + JapaneseEightStationDisplay (8-station zoomed) + EnglishDisplay placeholder + LowerDisplay manager (24s view-cycler)
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
| `constants.py` | TRULY cross-model values only: TIME_SCALE=60, FRAME_RATE=15, audio loudness, lower-LCD route-map sizes, setup-screen palette. Per-model dimensions live with the model. |
| `displays/utils.py` | Single home for drawing primitives (`draw_text`, `draw_text_given_width`, `draw_aapolygon`, `arrow_points`, `draw_1col_text`, `draw_stops_text`) + display-domain helpers (badges, continuity arrows, disclaimer). |
| `audio.py` | AudioPlayer class, play_pa/sta, pause, is_playing |
| `displays/` | Modular per-train-model UpperDisplay + LowerDisplay (E235-1000): set_state(), update(), draw() |
| `displays/train_models/{model}/__init__.py` | Per-model manifest: dimensions, palette, exported display classes. Where each train series declares its physical LCD shape. |
| `app.py` | PASimulator, AppState, translation loading, PA/STA handling |
| `main.py` | Entry point, setup screen, error handling |

## Key Features

1. **Display Cycling** (4s each, `STATION_DISPLAY_INTERVAL`): KANJI → FURIGANA → ENGLISH. Destination always kanji (IRL behavior).
2. **Modular Architecture**: Per-train-model displays (E235-1000, E231-500...). Mode renderers are self-contained.
3. **Stop-Level Dest Override**: Circular routes (Yamanote) change destination mid-route.
4. **Real-Time Countdown**: `TIME_SCALE=60` (60s = 1 travel minute), floor division, forces "1" on last PA.
5. **Audio**: -15 LUFS normalization, double-buffered temp files.
6. **Station Skip**: Time-based red arrow progression through passing stations.
7. **Station Code Badge**: JY/03 framed square + optional 3-letter code (AKB, TYO, ...) for the ~22 major JR East interchange stations. Source: `data/stations.json`.
8. **Lower-LCD view alternation**: 24 s cycle between full-route view and 8-station zoomed view, independent of upper's 4 s language cycler.
9. **Single train-position index** (`app.py` `AppState`): `state.curr_stop` is the only stored position; `state.cursor_pos` is a derived property that lags behind during skip animation.

## Controls

| Key | Action |
|-----|--------|
| Page Down | Play PA (blocked while playing) |
| Page Up | Play STA (jumps to sta_cut if playing) |
| End | Pause |

Yellow hint square = multiple PA tracks available.

## When Working On...

**Don't read these upfront — consult when needed:**

- **Data/JSON** → [DATA_FORMAT.md](DATA_FORMAT.md) — `route.json` / `translations.json` / `stations.json` shapes, validation rules
- **LCD displays** (upper or lower) → [DISPLAY.md](DISPLAY.md) — architecture, mode rendering, skip animation, layout gotchas, draw-method subtleties
- **Real-world JR East context** → already in this doc's "Mental Model" section above (preloaded — keep it in head, don't re-read each session)
- **Audio/Diagram** → Use `/split-audio` skill (PA + STA splitting, naming conventions, route.json updates)
- **Cross-cutting code patterns** → [.claude/rules/notes.md](.claude/rules/notes.md) — font loading on Windows, PyInstaller paths, preview mode, countdown system. (Display gotchas live in DISPLAY.md, not here.)
- **Testing / previewing** → `uv run preview_display.py` defaults to the mock catalog (`audio/_mock/main`). Keys: PageDown=PA, PageUp=STA, M=mode, ←/→=jump, ESC=quit. See notes.md "Preview Mode" for `jump_to_stop` backward-rounding semantics.
- **Building/Releasing** → Use `/build` skill
- **Codebase mess sweep** → Use `/vibe-check` skill (scan for duplicated logic, dead helpers, half-finished implementations, speculative architecture, stale comments — discussion-first, item-by-item, smoke-tests every fix). Distinct from `/review-dirty` (which reviews a single change for quality).

**Editing docs?** Check the placement table in [.claude/skills/session-recap/SKILL.md](.claude/skills/session-recap/SKILL.md) before writing — `notes.md` is for cross-cutting code only, not display or data work.

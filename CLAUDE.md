# PA Simulator Project

Japanese Train PA (Public Address) Simulator — pygame-based app simulating station announcements and arrival melodies with visual LCD display.

## Session Startup

Before doing anything else, every session:

1. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context.
2. Read [memory/MEMORY.md](memory/MEMORY.md) — long-term memory index.
3. Skim [TODO.md](TODO.md) — centralized backlog grouped by area (auto-input / display / distribution / housekeeping + closed-off paths).

`principles.md`, `conventions.md`, `critical_lessons.md`, `redlines.md` auto-load as memory files — already in context, no need to re-read.

**Two unconditional rules:**

- **Memory files are informational only.** Rules / learnings / preferences do NOT live in `memory/` — they live in their canonical home (`principles.md` / `conventions.md` / `CLAUDE.md` / domain doc / inline `# CONTRACT:` / skill), written synchronously during `/session-recap`, never deferred. Codify-or-omit; no `[log-only]` middle bucket. Defer-and-distill is gone — `/distill-memory` is now a periodic safety-net audit, not a primary route.
- **Before any doc edit, check the placement table** in [.claude/skills/session-recap/SKILL.md](.claude/skills/session-recap/SKILL.md) — pick the narrowest-domain home (CLAUDE.md framing / DISPLAY.md gotcha / DATA_FORMAT.md schema / inline `# CONTRACT:` / skill).

## Run

```bash
uv run main.py
```

## Mental Model

What this project is modeling. Keep this in head — it shapes every design decision. (Implementation details live in domain docs and are read on demand.)

### Project origin & scope

**Companion app for JRE Train Sim Real** — JR East's own train simulator. The game lacks PA + departure melodies for older routes; this fills that gap. Started as audio-only; the LCD grew incrementally as a "where am I" navigation aid. **Audio is the foundation; the LCD is navigation.**

**Coverage is asymmetric by design:**
- **Lines** — only build for routes the game does NOT already ship recordings for. Newer game routes (Sobu local, Yokosuka, future ones) have built-in PA → don't duplicate. The lines in `audio/` are old routes the game hasn't touched and likely won't.
- **Diagrams** — the full-line diagram is the canonical entry per route. Other diagrams are only worth building if they have a **different stopping pattern** (rapid vs local, limited express, etc.). Same-pattern variants that only terminate earlier are not worth the work.

**Distribution is lightly public** — released on GitHub + YouTube videos circulate, some railfans use it. **Fidelity bar is high:** elements iterate against IRL reference photos until they read pixel-correct (often 15+ revs per element). "Good enough" is rejected. See `/visual-adjust` and recent memory for the iteration patterns.

### Distribution & deployment artifact

The simulator ships as a PyInstaller exe (Windows) to the public audience above. The deployment frame matters when classifying deps, placing files, or wrapping defensive code — **silent breakage in a release build is the worst-case mode**, because the dev env has everything installed but the user's exe doesn't, and the failure is invisible until a user hits it.

- **Bundled:** all `dependencies` in `pyproject.toml`; code at project root + everything under `displays/`; asset folders (`audio/`, `data/`, `fonts/`, `ocr_templates/`).
- **Not bundled:** the `dev` dep group; folders prefixed with `_` (`_dev_scripts/`, `_experiments/`, `audio/_archive/`, `audio/_mock/`, `_*_calibration/`). Per [conventions.md § "_*" prefix](.claude/rules/conventions.md), production code MUST NOT import from `_*/` paths — folder placement carries dep-classification semantics.
- **Library classification follows the call graph, not folder location or import timing.** A library reachable from any production code path is a runtime dep — eager, lazy, behind a button, behind a flag, all the same. "Lazy" is a perf choice (when it loads); "optional" is a contract choice (whether it must exist). They aren't interchangeable. See [critical_lessons.md § "Lazy import ≠ optional dep"](.claude/rules/critical_lessons.md).

Build mechanics (PyInstaller invocation, version metadata, junction handling) live in `/build` skill — that's *how to build*; this section is *what's in the artifact*.

### Direction of travel

The project is in a **mature phase** — heavy architecture done, audio pipeline mature, visual fidelity high. Future work splits into:

- **Steady state**: new train models (E235-0 Yamanote leaning next, then E231-500 / E233 series — re-skin work, not re-architecture) + display fidelity polish on the active model (ENGLISH lower-LCD still a stub, code_3 edge cases, continuity polish).
- **Two speculative side-quests, both viable, competing for the same budget:**
  - **Automation via game-window OCR** — `TSimApp.log` confirmed empty (no streaming position). OCR of the game's "next stop / remaining meters" HUD is the realistic path. Template-match against pre-extracted glyph sprites at ~5 Hz on a window-bound capture (NOT full-desktop screenshot, NOT tesseract) mitigates privacy + performance concerns. Game HUD has been stable across versions historically and unlikely to change → calibration is effectively one-time, not a recurring maintenance burden. Closes the original 3-year companion-app loop.
  - **Distribution polish** — signed Windows installer, first-run smoothness for the lightly-public audience (~1800 video plays, real users). Windows-only; the companion game doesn't run on Mac, so there's no Mac audience.
- **Not directions** (closed-off, don't re-propose): memory hooking the game's `*saf.dll` modules, decrypting SimDATA assets, audio fingerprinting, full-desktop OCR, tesseract-based OCR, scaling to lines the game already covers, Mac build (game is Windows-only).

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
- **Through-service combined frame.** Trains that physically through-run from another line (e.g. Yokosuka Line→Sōbu Rapid: 久里浜→東京→千葉) display the combined journey on one LCD frame, with pre-route stations rendered dim/passed. At major continuation junctions (e.g. Chiba for Sōbu Rapid yielding to Sōtobō / Narita Line) the frame swaps to the next line's view — modeled via `pre_stops` in route.json; frame-swap-at-junction is deferred. See [DATA_FORMAT.md § "pre_stops Array"](DATA_FORMAT.md).
- **PA and STA are independent audio sources.** PA (in-train announcement) and STA (platform departure melody) come from different speakers IRL — they overlap freely. Sim mirrors this: PA on `mixer.music`, STA on a dedicated `mixer.Channel`; pressing Page Down during STA does not block, and vice versa.

### App state machine

Each stop advances through three press-driven sub-states: **APPROACHING_EARLY** ("次は X") → **APPROACHING_FINAL** ("まもなく X", final entry in `pa[]`) → **STOPPING** ("ただいま X", at platform) → next stop's APPROACHING_EARLY. PageDown drives transitions; `jump_to_stop` lands in STOPPING@target. Full transition spec + edge cases in [DISPLAY.md § Unified State Machine](DISPLAY.md); `AppState` field semantics in the inline `# CONTRACT:` on the class in `app.py`.

**Auto-fire asymmetry:** APPROACHING entry auto-fires `pa[0]` (the prev-stop departure announcement) — a passive-listening window where the user hasn't acted yet. STOPPING has no auto-fire; every `pa_at_station` entry plays only because the user pressed. UI cues that gate on "is the user being asked to act?" must respect this asymmetry.

## Memory (project-level, in-repo)

This is a separate system from any auto-memory the host may provide. It lives in `memory/` and travels with the repo. The "informational only / codify-or-omit" rule lives in Session Startup above.

- **Daily logs**: `memory/YYYY-MM-DD.md` — narrative continuity for next-session pickup. What happened, decisions, why-context, dead ends.
- **Curated index**: `memory/MEMORY.md` — one-line pointers to the daily logs worth keeping.

Rules:
- Write it down. "Mental notes" do not survive session restarts; files do.
- Capture WHY, not just WHAT. Git log already has what changed.
- Use `/session-recap` at the end of a session to codify learnings into their canonical homes AND write the day's narrative log.

## File Structure

```
pids_jre_simulator/
├── main.py, app.py, audio.py, constants.py
├── i18n.py, language_picker.py        # App-chrome i18n (settings, locale detect, font, t()) + first-run picker
├── setup.py                           # Route selection screen (line badge, EN translation lookup, theme)
├── preview_display.py                 # Audio-free preview entry point — uses PASimulator(preview=True)
├── preview_chrome.py                  # Chrome screenshot tool for picker / setup iteration
├── displays/                          # Modular display system
│   ├── base.py                        # DisplayMode enum, ModeCycler
│   ├── utils.py                       # ALL drawing primitives + display-domain helpers (draw_text, draw_aapolygon, arrow_points, draw_station_code_badge, draw_route_disclaimer, draw_continuity_*)
│   └── train_models/e235_1000/
│       ├── __init__.py                # Per-model dimensions/palette: S_WIDTH, S_HEIGHT, UPPER_HEIGHT, DARK_BG, WHITE_BG (defined before class imports for partial-module safety)
│       ├── upper_lcd.py               # JapaneseDisplay + FuriganaDisplay (inherits Japanese, no override) + EnglishDisplay + UpperDisplay manager
│       └── lower_lcd.py               # JapaneseDisplay (full route) + JapaneseEightStationDisplay (8-station zoomed) + EnglishDisplay placeholder + LowerDisplay manager (24s view-cycler)
├── data/
│   ├── translations.json              # Station names (furigana, english) — for LCD rendering
│   ├── train_types.json               # Train type English translations
│   ├── translations_app.json          # App-chrome strings (en / zh_HK / zh_CN), separate from LCD data
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
| `i18n.py` | App-chrome i18n: settings persistence (alongside-exe), locale detection, `t()` translation lookup, per-language SysFont helper. NOT used for LCD station-name rendering. |
| `language_picker.py` / `setup.py` | First-run language picker + route-selection screen. Both consume `i18n.t()` / `i18n.font()`. |
| `main.py` | Entry point, picker → setup screen orchestration, error handling |

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
- **Audio/Diagram** → Use `/pa-make` skill (PA splitting + naming + route.json updates) or `/sta-make` skill (STA splitting + sta_cut validation + by-ear verifier)
- **Auto-input / OCR / game-window capture** → [AUTO_INPUT.md](AUTO_INPUT.md) — companion module that reads JR EAST Train Sim's HUD via dxcam to fire PAs automatically. Lives in `auto_input.py` + `ocr.py` + `hud_layout.py` (in-process integration) and `_dev_scripts/capture_game.py` (separate-process variant).
- **Cross-cutting code contracts** → live inline at their code site as `# CONTRACT:` blocks. Examples: PyInstaller path resolution at `displays/train_models/e235_1000/upper_lcd.py:get_base_dir`, countdown formula at `displays/train_models/e235_1000/lower_lcd.py:draw_times`, font-loading rule at the first font init in `upper_lcd.py`'s `JapaneseDisplay.__init__`.
- **Testing / previewing** → `uv run preview_display.py` defaults to the mock catalog (see [`audio/_mock/main/README.md`](audio/_mock/main/README.md) for stop layout). Keys: PageDown=PA, PageUp=STA, M=mode, ←/→=jump, ESC=quit. `jump_to_stop` backward-rounding semantics are documented in its docstring at `app.py` `PASimulator.jump_to_stop`. Preview-mode swap inventory (audio, input, mixer, window) is at `PASimulator.__init__`'s ``preview`` parameter.
- **Building / releasing** → `/build` skill (local test build) or `.\release.ps1 v<version>` (cut a GitHub release; tag first).
- **README / translation maintenance** → `/readme` skill.
- **Code review** → `/review-dirty` skill (single change) or `/review-plus-fix-relentlessly` (review + fix loop).
- **Commit hygiene** → `/commit` skill.
- **Codebase mess sweep** → `/vibe-check` skill (duplicated logic, dead helpers, half-finished implementations, speculative architecture, stale comments — discussion-first, item-by-item, smoke-tests every fix). Distinct from `/review-dirty` (which reviews a single change for quality).
- **Doc bloat sweep** → `/distill-docs` skill (scan DISPLAY.md / DATA_FORMAT.md / AUTO_INPUT.md for accumulated bloat the write-time `EDIT-CONTRACT` gate misses — discussion-first, item-by-item). Pairs with the `EDIT-CONTRACT` block at the top of each domain doc.

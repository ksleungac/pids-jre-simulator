# PA Simulator Project

Japanese Train PA (Public Address) Simulator — pygame-based app simulating station announcements and arrival melodies with visual LCD display.

## Session Startup

Before doing anything else, every session:

Run `uv run _harness/session_init.py` — dumps today's + yesterday's memory, MEMORY.md index, and the GitHub-Issues backlog summary (open by area · in-progress · recently closed · stale) in one shot. Read the output instead of opening files individually.

`principles.md`, `conventions.md`, `critical_lessons.md`, `redlines.md` auto-load as memory files — already in context.

**Unconditional rules:**

- **Memory files are informational only.** Rules / learnings live in their canonical home (`principles.md` / `conventions.md` / `CLAUDE.md` / domain doc / inline `# CONTRACT:` / skill), written synchronously during `/session-recap`. Codify-or-omit; no log-only middle bucket.
- **Before any doc edit, check the placement table** in [.claude/skills/session-recap/SKILL.md](.claude/skills/session-recap/SKILL.md) — pick the narrowest-domain home.
- **Write it down.** "Mental notes" don't survive session restarts. Capture WHY, not just WHAT — git log has what changed. Use `/session-recap` at session end.

## Working loop (GitHub Issues)

Backlog = **GitHub Issues** ([repo issues](https://github.com/ksleungac/pids-jre-simulator/issues)). `TODO.md` is now only a pointer + the closed-off-paths ledger. Area labels: `auto-input` · `display` · `chrome-i18n` · `distribution` · `housekeeping` · `review-finding` · `build-incident`.

- **Pick up** an issue → `gh issue edit <N> --add-label in-progress` + a stamp comment (so a concurrent session/PC sees it's taken — don't double-pick).
- **Park** it → swap `in-progress` for `deferred` + a one-line reason comment.
- **Finish** → the commit carries `Closes #<N>` (progress commits: `Refs #<N>`); pushing to `master` auto-closes. See `/commit`.
- **New work** surfaced mid-session → `gh issue create --label <area>`.

### Issue scope — an issue is an OUTCOME, not a unit of work

Test: *if I finish this, does what the user can do change?* No → it's a commit, not an issue.

| shape | when |
|---|---|
| **Plain issue** | one outcome, one sitting — most things |
| **Parent + sub-issues** | outcome spans sessions/stages. `gh issue edit <parent> --add-sub-issue <N>` (gh ≥ 2.96). Parent tracks `completed/total` natively and closes when the outcome is real; each stage closes as it lands |
| **Not an issue** | no user-visible change |

**`Closes #N` only when you did everything #N describes.** Doing less is a signal the scope was wrong — fix by splitting a stage out **under** the outcome, never by closing it and opening a peer. A peer orphans the feature: the two tickets read as unrelated and the thing the user actually wants has no home. (2026-07-20: closed #71 "window mirroring" after shipping only its display-only stage and filed stage 2 as a sibling; user — *"can you not closes the issue just for a new stage?"*. Restructured to #71 parent → #77 stage 1 / #76 stage 2.)

Sub-issues beat a long-lived `Refs`-only ticket because progress stays legible — the parent shows a completion count instead of sitting `in-progress` for weeks with its state readable only from git log.

Session start prints the open / in-progress / recently-closed / stale summary; `/session-recap` reconciles against `gh issue list` (closure is authoritative — no keyword guessing).

## Run

```bash
uv run main.py
```

After a fresh clone: `uv sync` then `uv run pre-commit install`. See [conventions.md § Tooling](.claude/rules/conventions.md).

## Mental Model

What this project is modeling. Keep in head — shapes every design decision. Implementation details live in domain docs, read on demand.

### Project origin & scope

**Companion app for JRE Train Sim Real** — JR East's own train simulator. The game lacks PA + departure melodies for older routes; this fills that gap. Started as audio-only; the LCD grew incrementally as a "where am I" navigation aid. **Audio is the foundation; the LCD is navigation.**

**Coverage is asymmetric by design:**
- **Lines** — only build for routes the game does NOT already ship recordings for. The lines in `audio/` are old routes the game hasn't touched.
- **Diagrams** — full-line diagram is canonical per route. Other diagrams only worth building for a **different stopping pattern** (rapid vs local, etc.).

**Distribution is lightly public** — GitHub + YouTube (~1800 plays), some railfans use it. **Fidelity bar is high:** elements iterate against IRL reference photos until pixel-correct. "Good enough" is rejected.

### Distribution & deployment artifact

Ships as PyInstaller exe (Windows). **Silent breakage in a release build is the worst-case mode** — dev env has everything installed but the user's exe doesn't.

- **Bundled:** all `dependencies` in `pyproject.toml`; code at project root + `displays/`; asset folders (`audio/`, `data/`, `fonts/`, `ocr_templates/`).
- **Not bundled:** `dev` dep group; `_*` folders. Production code MUST NOT import from `_*/` paths — see [conventions.md § "_*" prefix](.claude/rules/conventions.md).
- **Dep classification follows the call graph** — see [critical_lessons.md § 3](.claude/rules/critical_lessons.md).

Build mechanics live in `/build` skill.

### Direction of travel

**Mature phase** — heavy architecture done, audio pipeline mature, visual fidelity high. Future work:

- **Steady state**: new train models (E235-0 Yamanote next, then E231-500 / E233 — re-skin, not re-architecture) + display fidelity polish.
- **Two speculative side-quests competing for budget:**
  - **OCR automation** — template-match game HUD at ~5 Hz on window-bound capture. Closes the 3-year companion-app loop.
  - **Distribution polish** — signed installer, first-run smoothness.
- **Closed-off** (don't re-propose): memory hooking `*saf.dll`, decrypting SimDATA, audio fingerprinting, full-desktop OCR, tesseract, scaling to lines the game already covers, Mac build.

### Train family

JR East runs multiple train series: E233 (sub-series 0–8000), E235 (0 and 1000), etc. Each has its own LCD look — drawings differ, but the element set (clock, station name, route bar, mode cycling, badges, view alternation) is mostly shared. Adding a new model is re-skinning, not re-architecting.

Each train model lives under `displays/train_models/{model}/`.

### Per-model IRL line scope (in-spec vs best-effort)

Every train series runs on a fixed subset of JR East lines IRL. The exact mappings are NOT memorized; ask when scope matters.

The simulator accepts **any** route into **any** train model. Reality only constrains the in-spec subset:

| Route | Behavior |
|---|---|
| **In-spec** (model's IRL lines) | Match real PIDS |
| **Out-of-spec** | Best-effort: no crashes, no missing-key errors, no broken layouts. Not obligated to IRL-accurate fidelity. |

### IRL display conventions

Behaviors true on real trains, mirrored by the simulator:

- **Destination stays kanji** even in furigana mode. English uses "Bound for" + English dest.
- **Stop-level destination override.** Circular routes change destination mid-route.
- **Station code badge** — 3-letter Roman for ~22 major interchange stations. Source: `data/stations.json`.
- **Compound destinations** use `&` separator on real PIDS.
- **English uses modified Hepburn with macrons** (Tōkyō, Chūō). Encoding details in [DATA_FORMAT.md](DATA_FORMAT.md).
- **Through-service combined frame.** Modeled via `pre_stops` in route.json. See [DATA_FORMAT.md § "pre_stops Array"](DATA_FORMAT.md).
- **PA and STA are independent audio sources** — overlap freely. PA on `mixer.music`, STA on dedicated `mixer.Channel`.

### App state machine

Each stop: **APPROACHING_EARLY** → **APPROACHING_FINAL** → **STOPPING** → next stop. PageDown drives transitions; `jump_to_stop` lands in STOPPING@target. Full spec in [DISPLAY.md § Unified State Machine](DISPLAY.md).

**Auto-fire asymmetry:** APPROACHING auto-fires `pa[0]` (passive-listening window). STOPPING has no auto-fire — every `pa_at_station` entry plays only on user press.

## Chat output style

Default = caveman-full. Drop articles, fragments OK, no pleasantries / restatement / sign-offs. Technical terms preserved verbatim.

**Revert to normal grammar for:** material-consequence ambiguity, security warnings, irreversible-action confirmations, user clarification questions.

**In scope:** chat, skill prose. **Out of scope (normal voice):** code, commits, memory daily logs.

## File Structure

```
pids_jre_simulator/
├── main.py                            # Entry point, picker → setup orchestration
├── app.py                             # PASimulator, AppState, translation loading, PA/STA handling
├── audio.py                           # AudioPlayer: play_pa/sta, pause, is_playing
├── constants.py                       # Cross-model only: TIME_SCALE=60, FRAME_RATE=15, audio, setup palette
├── app_paths.py                       # Canonical project_root() — sole PyInstaller path resolver
├── i18n.py                            # App-chrome i18n: settings, locale detect, t(), font helper
├── frame_stream.py                    # Opt-in window mirroring over HTTP (--stream / --stream-lan)
├── setup.py                           # Route selection screen
├── route_loader.py                    # finalize_route: JSON → runtime closure with derived fields
├── preview_display.py                 # Audio-free preview entry (PASimulator(preview=True))
├── displays/
│   ├── base.py                        # DisplayMode enum, ModeCycler
│   ├── utils.py                       # ALL drawing primitives + display helpers
│   └── train_models/e235_1000/
│       ├── __init__.py                # Per-model dimensions/palette
│       ├── upper_lcd.py               # Japanese + Furigana + English + UpperDisplay manager
│       └── lower_lcd.py               # Japanese + 8-station + English + LowerDisplay manager (24s cycler)
├── data/
│   ├── translations.json              # Station names (furigana, english)
│   ├── train_types.json               # Train type English translations
│   ├── translations_app.json          # App-chrome strings (en / zh_HK / zh_CN)
│   └── stations.json                  # Station metadata (3-letter codes)
├── auto_input/                        # OCR-driven auto-PA (driver + ocr + hud_layout)
├── memory/                            # Daily logs + MEMORY.md curated index
└── audio/
    ├── [line]/[diagram]/route.json    # Real routes
    └── _mock/main/route.json          # Edge-case catalog for preview (not shipped)
```

## Key Features

1. **Display Cycling** (4s): KANJI → FURIGANA → ENGLISH. Destination always kanji.
2. **Lower-LCD view alternation**: 24s cycle between full-route and 8-station zoomed view.
3. **Real-Time Countdown**: `TIME_SCALE=60`, floor division, forces "1" on last PA.
4. **Station Skip**: Time-based red arrow progression through passing stations.
5. **Single train-position index**: `state.curr_stop` is stored; `state.cursor_pos` is derived (lags during skip animation).

## Controls

| Key | Action |
|-----|--------|
| Page Down | Play PA (blocked while playing) |
| Page Up | Play STA (jumps to sta_cut if playing) |
| End | Pause |

Yellow hint square = multiple PA tracks available.

## When Working On...

Consult when needed, not upfront:

- **App architecture / setup flow** → [APP.md](APP.md)
- **Data/JSON** → [DATA_FORMAT.md](DATA_FORMAT.md)
- **LCD displays** → [DISPLAY.md](DISPLAY.md) (cross-model); [DISPLAY_E235.md](DISPLAY_E235.md) (per-sub-series)
- **Audio/Diagram** → `/pa-make` or `/sta-make` skill; per-line quirks in [audio/README.md](audio/README.md)
- **Auto-input / OCR** → [auto_input/README.md](auto_input/README.md)
- **Testing / test suite + hierarchy** → [_tests/README.md](_tests/README.md)
- **Code contracts** → inline `# CONTRACT:` blocks at code sites
- **Preview** → `uv run preview_display.py` (mock route) or a real route via `--route <line>/<diagram>` (e.g. `--route sobu/1217F --stop 9`). Flags: `--screenshot out.png` (static frame, headless), `--lower-view full|eight|transfer` (freeze a view), `--mode kanji|furigana|english`, `--model e235_1000|e235_0`. Controls: PageDown=PA, PageUp=STA, M=mode, ←/→=jump, ESC=quit. Full arg list in the `preview_display.py` docstring.
- **Build/Release** → `/build` + `/release` skills
- **Review** → `/review-dirty` (single) or `/review-plus-fix-relentlessly` (loop)
- **Commit** → `/commit` skill
- **Sweeps** → `/vibe-check` (codebase mess) or `/distill-docs` (doc bloat)

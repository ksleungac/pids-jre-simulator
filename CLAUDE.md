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

Backlog = **GitHub Issues** ([repo issues](https://github.com/ksleungac/pids-jre-simulator/issues)) — **strictly defects and near-term implementation tasks, nothing else**. `TODO.md` holds the two things that are not issues: **§ Directions** (wanted, not yet scoped) and the **closed-off-paths ledger** (decided never). `_harness/session_init.py` prints the Directions headings at session start. Area labels: `auto-input` · `display` · `chrome-i18n` · `distribution` · `housekeeping` · `review-finding` · `build-incident`.

- **Only act on issues opened by `ksleungac`. An outside contributor's ticket is READ-ONLY — no comment, no close, no label, nothing.** Their tickets are a conversation with a real person, and that conversation is the author's to have; a reply posted from their account speaks as them to someone who is owed a human answer. Read those issues freely — they are evidence, and a reporter is an instrument (`critical_lessons.md §§ 7–8`) — then put what you found in chat and let the author carry it across. 2026-08-29: I posted a technically correct reply to an outside reporter explaining that their bug was already fixed and unreleased; author — *"you will only comment or handle the tickets created by ksleungac. leave the human part to me."* Supersedes the narrower 2026-08-18 form below, which barred only closing and so read as permitting everything else. Original: *"don't close other people's issue unless i say so."*
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

**Refined-ness is a SECOND gate, after outcome-ness.** A feature named in a mental-model conversation is not a ticket, even when it genuinely is an outcome the author wants — a want is not a scope. File it once there is a mechanism to build, not when it is first spoken. (2026-08-18: three issues opened off one such conversation; two closed within the hour. Author — *"unless it's really refined, don't open as an issue … don't want my gh to be flooded with issues."*) Closing one of these is **not** a closed-off path — it does not go in the `TODO.md` ledger, because the author does intend to return to it; it is unscoped, not abandoned. It goes to **`TODO.md` § Directions**, whose headings `session_init.py` prints at session start — which is the moment the author asks what to work on, and the moment a domain doc is NOT open. Each entry carries its own description, so picking one up later needs no re-explaining; that re-stating is the actual pain a ticket was standing in for. Promote = scope it, open an issue, delete the entry. Abandon = move it down into the closed-off ledger. (2026-08-18, via `/third-man`: the question is not where the text lives, it is what PUSHES it at session start — `principles.md` § "Natural adoption gates tool value".)

**`Closes #N` only when you did everything #N describes.** Doing less is a signal the scope was wrong — fix by splitting a stage out **under** the outcome, never by closing it and opening a peer. A peer orphans the outcome: the two tickets read as unrelated, so the feature has no single tracking home. (2026-07-20: closed #71 "window mirroring" after shipping only its display-only stage and filed stage 2 as a sibling; user — *"can you not closes the issue just for a new stage?"*. Restructured to #71 parent → #77 stage 1 / #76 stage 2.)

A parent with sub-issues shows progress as a `completed/total` count; a long-lived `Refs`-only ticket keeps its state only in git log.

**A "signal missed → action suppressed" bug must name a scenario where the signal is missed AND the action is still wanted.** Write the scenario before filing. If the same evidence gates both — if the read whose absence loses the signal is the read that made the action necessary — the two cannot come apart and there is no bug. Reasoning forward from "here is a signal that can be missed" produces a report with a real mechanism, a real consequence, and nothing joining them; it reads as rigorous and is empty. (2026-08-11: #84 claimed a missed `STOPPED→MOVING` suppresses the departure PA. But the `STOPPED` badge is what fires at-station and moves the app into STOPPING — no `STOPPED` read means the app never registered the arrival, so there is no departure to announce. Author's question, which is the test: *"under what case is this missed yet the departure PA still needs playing?"* — there is none.) Generalizes past OCR: any cache invalidation, dirty flag, or edge-triggered handler where the same observation both arms the state and justifies the action.

**Always write an issue as `#N "title"` — never the bare number.** Applies to every prose surface: chat, commit bodies, issue comments, recaps. A bare `#105` forces the reader to go look it up before the sentence means anything, and a list of bare numbers is unreadable. Commit trailers (`Closes #N`) are exempt — that's a machine token. 2026-08-11: user — *"don't just name the numbers only, hard to relocate, mention the issue name and number."*

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

**Scope: JR lines, Tokyo capital region.** Non-JR operators and out-of-region lines are out of scope.

**Coverage is asymmetric by design** — full picture, dates and per-line gaps in [COVERAGE.md](docs/COVERAGE.md):
- **Lines** — the catalogue is exactly the JR Kantō routes the game shipped BEFORE in-game announcements became standard. **Gaps first is a PRIORITY rule, not a permission rule** — a route the game already voices is still worth building when you want it, and the gap list is nearly exhausted. **Coverage is a fact with a DATE on it, not a property of a route**: the game has retro-fitted announcements onto an already-shipped route, so re-check before starting a build, not after.
- **Diagrams** — full-line diagram is canonical per route. Other diagrams only worth building for a **different stopping pattern** — and a diagram is the tuple *(pattern, destination, formation, day type)*, not the service label; the same label carries different patterns on Sat/Sun.

**Distribution is lightly public** — GitHub + YouTube (~1800 plays). Some of those users are **active collaborators, not passive downloaders**: they trade IM / email with the author, know the data model and the OCR pipeline, and test on their own hardware — the re-entry departure-PA bug came from a viewer's testing. So a defect that will not reproduce here is not a dead end; the reporter is an instrument (`critical_lessons.md §§7–8`). **Fidelity bar is high:** elements iterate against IRL reference photos until pixel-correct. "Good enough" is rejected.

### Distribution & deployment artifact

Ships as PyInstaller exe (Windows). **Silent breakage in a release build is the worst-case mode** — dev env has everything installed but the user's exe doesn't.

- **Bundled:** all `dependencies` in `pyproject.toml`; code at project root + `displays/`; asset folders (`audio/`, `data/`, `fonts/`, `ocr_templates/`).
- **Not bundled:** `dev` dep group; `_*` folders. Production code MUST NOT import from `_*/` paths — see [conventions.md § "_*" prefix](.claude/rules/conventions.md).
- **Dep classification follows the call graph** — see [critical_lessons.md § 3](.claude/rules/critical_lessons.md).

Build mechanics live in `/build` skill.

### Direction of travel

**Mature phase** — heavy architecture done, audio pipeline mature, visual fidelity high. Future work:

- **Steady state**: new train models (**E233-0 next** — a re-skin, and its LCD is close to E233-1000's, so one skin serves both Chūō and Keihin-Tōhoku, whose audio already ships) + display fidelity polish.
- **OCR auto-drive is the PRIMARY interface, not a side-quest.** Assume every user runs it — it was the most-requested feature and is how the app is actually used (author, 2026-08-18). Template-match game HUD at ~5 Hz on window-bound capture. **1080p is the canonical resolution and the absolute-stability target** — the multi-resolution path downscales every input to 1080p, so the crisp higher-native 1440p is not the bar; the real user's softened 1080p capture is (`auto_input/README.md`, `critical_lessons.md §7`). The one remaining user-facing gap is **unusual aspect ratios**, which is what makes resolution support outrank the rest of this list.
- **Distribution polish** — signed installer, first-run smoothness. Real, and secondary to the above.
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
| **No IRL LCD** (line's stock has no LCD PIDS at all — E233-3000, E531, E217) | There is no real PIDS to match, so there is no spec to depart from: the bar is **plausibility**, not fidelity. A *fictional* render, and a legitimate one — prefer the nearest real relative (an E233 answers "what would the E233-3000's LCD look like") over an arbitrary borrow, and a linear-native model on a linear line needs no adaptation at all. Which lines → [COVERAGE.md](docs/COVERAGE.md). |

**Best-effort = the model's OWN native norm applied to any route — never a borrowed behavior or bespoke feature propping up an out-of-spec route.** Adapt the model's own look to the route's shape (e235_0 opens its circular racetrack into a *horseshoe* for a non-loop line — native, adapted), but don't import another model's behavior (e235_0 drops e235_1000's inherited end-of-route *lock* — that lock is a linear heuristic foreign to a loop; no-lock is e235_0's native norm). And when a route shape the view wasn't built for needs a marker the view has no calibrated slot for, reuse an EXISTING calibrated primitive degenerately — a passing station in the fixed-slot 5-station view renders the countdown ring *empty* (no digit), not an invented chevron (#66; the proper chevron is deferred as ultra-low-priority #99) — never a new uncalibrated marker — the bespoke growth this section bars. *For the reviewer:* a cross-model divergence where each model expresses its own native norm is NOT sibling-drift — verify against this section before flagging; a borrowed foreign feature IS the violation. And out-of-spec renders (the horseshoe) are **transitional** — e235_1000 is the stable general model for all routes until per-line-native models land, and as those arrive out-of-spec best-effort support is *removed*, not grown. **The no-LCD row is the exception: those are permanent**, because no native model can ever land for a train that has no LCD.

### IRL display conventions

Behaviors true on real trains, mirrored by the simulator:

- **Destination stays kanji** even in furigana mode. English uses "Bound for" + English dest.
- **Stop-level destination override.** Circular routes change destination mid-route.
- **Station code badge** — 3-letter Roman for ~22 major interchange stations. Source: `data/stations.json`.
- **Compound destinations** use `&` separator on real PIDS.
- **English uses modified Hepburn with macrons** (Tōkyō, Chūō). Encoding details in [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md).
- **Through-service combined frame.** Modeled via `pre_stops` in route.json. See [docs/DATA_FORMAT.md § "pre_stops Array"](docs/DATA_FORMAT.md).
- **PA and STA are independent audio sources** — overlap freely. PA on `mixer.music`, STA on dedicated `mixer.Channel`.

### App state machine

Each stop: **APPROACHING_EARLY** → **APPROACHING_FINAL** → **STOPPING** → next stop. PageDown drives transitions; `jump_to_stop` lands in STOPPING@target. Full spec in [docs/DISPLAY.md § Unified State Machine](docs/DISPLAY.md).

**Auto-fire asymmetry:** APPROACHING auto-fires `pa[0]` (passive-listening window). STOPPING has no auto-fire — every `pa_at_station` entry plays only on user press.

## Writing tone

Factual, nerd, non-performative. Same voice the release notes use — professional and factual, never editorial. Every prose surface: chat, docs, memory, commits.

Not a brevity rule. Use as many words as the technical detail or logic needs. The cut targets performance, not length:

- No words to show you understood, signal diligence, or project a personality.
- No self-justifying scaffolding (arguing the point is right).
- No intensifier filler (*exactly*, *the very*, *the tell is*); no throat-clearing hedge (*arguably*, *somewhat*, *tends to*).
- "X, not Y" only when Y is a real wrong path worth flagging — else drop the shadow.
- Never mark compliance. The instruction shapes the output and never appears in it.

Be true. State what you know plainly; state real uncertainty just as plainly (*unverified*, *haven't checked X*). Don't inflate confidence, don't perform humility — confidence tracks truth.

Grammar is ordinary and complete — full sentences, articles intact. What gets cut is the wrapper, not the syntax: no pleasantries, no restating the request back, no sign-offs. Technical terms stay verbatim; don't paraphrase jargon into plainer words.

A file written to disk carries the same bar plus a structural one: length matches what the task needs, with no padding — no filler sections, no summary restating the section above it, no boilerplate scaffolding. Where a doc states its own size cap, the cap is a gate, not a target.

## Working narration

One sentence before the first tool call saying what you're about to do. While working, surface an update only when you find something that changes the picture or you change direction — not per step, not per file. When finished, lead with the outcome: the first sentence answers "what happened" or "what did you find", with supporting detail after it.

That opening sentence states the action, never why the action is the right one. "Let me check X" — not "let me check X rather than assume", "rather than recommend it blind", "instead of guessing". The trailing clause advertises that you know the failure mode, which is the diligence-signalling § Writing tone bars; the shadow adds nothing the reader couldn't see. This is where the tic recurs, because the sentence is written in the moment of choosing an approach.

The closing message carries the outcome and whatever you need to decide or check. Work the diff already shows doesn't get narrated back — a file list is not a report. This is the one place the "not a brevity rule" licence in § Writing tone does not reach: technical detail earns its words, restating completed work does not.

## File Structure

```
pids_jre_simulator/
├── main.py                            # Entry point, picker → setup orchestration
├── app.py                             # PASimulator, AppState, translation loading, PA/STA handling
├── audio.py                           # AudioPlayer: play_pa/sta, pause, is_playing
├── constants.py                       # Cross-model only: TIME_SCALE=60, FRAME_RATE=15, audio, setup palette
├── app_paths.py                       # Canonical project_root() — sole PyInstaller path resolver
├── font_atlas.py                      # LCD font seam: live fonts (dev) or pre-rendered atlas
│                                       #   (ship). lcd_font() + text_parts(). docs/wip/WIP_font_atlas.md
├── i18n.py                            # App-chrome i18n: settings, locale detect, t(), font helper
├── frame_stream.py                    # Window mirroring over HTTP + taps back (TIMS 設定 →
│                                       #   off/local/lan). docs/APP.md § "Window mirroring"
├── qr.py                              # Byte-mode EC-L QR encoder, versions 1-4 — the band's
│                                       #   scannable mirror address. No dependency, by design
├── route_loader.py                    # finalize_route: JSON → runtime closure with derived fields
├── preview_display.py                 # Audio-free preview entry (PASimulator(preview=True))
├── displays/
│   ├── base.py                        # DisplayMode enum, ModeCycler, ChangeScheduler + beat schedule
│   ├── lower_lcd.py                   # LowerDisplayBase: slot cycle, force-switch, frame swap
│   ├── utils.py                       # ALL drawing primitives + display helpers
│   └── train_models/e235_1000/
│       ├── __init__.py                # Per-model dimensions/palette
│       ├── upper_lcd.py               # Japanese + Furigana + English + UpperDisplay manager
│       └── lower_lcd.py               # Japanese + 8-station + English renderers + LowerDisplay
│                                       # concrete (slot cycle lives in displays/lower_lcd.py)
├── data/
│   ├── translations.json              # Station names (furigana, english)
│   ├── train_types.json               # Train type English translations
│   ├── translations_app.json          # App-chrome strings (en / zh_HK / zh_CN)
│   └── stations.json                  # Station metadata (3-letter codes)
├── auto_input/                        # OCR-driven auto-PA (driver + ocr + hud_layout)
├── tims/                              # TIMS cab-console UI package (see docs/APP.md)
│   ├── widgets.py                     # Draw primitives (bevel buttons, AA-off low-res text)
│   ├── chrome.py                      # Shared vocabulary (PALETTE, button presets, role fonts)
│   ├── band.py                        # Persistent status band (setup screens + live OCR panel)
│   └── setup/                         # Setup/OOBE flow screens (tims.setup.run = entry)
├── docs/                              # Domain docs — APP / DATA_FORMAT / DISPLAY / DISPLAY_E235
│   └── wip/                           # In-flight design docs; each carries its own delete trigger
├── memory/                            # Daily logs + MEMORY.md index (untracked; canonical =
│                                       #   origin/memory ref via _harness/publish_memory.py)
└── audio/
    ├── [line]/[diagram]/route.json    # Real routes
    └── _mock/main/route.json          # Edge-case catalog for preview (not shipped)
```

## Key Features

1. **Display Cycling** (1 beat = 4s): KANJI → FURIGANA → ENGLISH. Destination always kanji.
2. **Lower-LCD view alternation**: full-route ↔ 8-station zoomed (+ transfer when in window). One `ChangeScheduler` owns language + slot on a shared beat so no two changes collide — see [docs/DISPLAY.md § Change scheduler](docs/DISPLAY.md).
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

- **App architecture / setup flow** → [docs/APP.md](docs/APP.md)
- **Data/JSON** → [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md)
- **LCD displays** → [docs/DISPLAY.md](docs/DISPLAY.md) (cross-model); [docs/DISPLAY_E235.md](docs/DISPLAY_E235.md) (per-sub-series)
- **Audio/Diagram** → `/pa-make` or `/sta-make` skill; per-line quirks in [audio/README.md](audio/README.md)
- **Auto-input / OCR** → [auto_input/README.md](auto_input/README.md)
- **Testing / test suite + hierarchy** → [_tests/README.md](_tests/README.md)
- **Code contracts** → inline `# CONTRACT:` blocks at code sites
- **Preview** → `uv run preview_display.py` (mock route) or a real route via `--route <line>/<diagram>` (e.g. `--route sobu/1217F --stop 9`). Flags: `--screenshot out.png` (static frame, headless), `--lower-view full|eight|transfer` (freeze a view), `--mode kanji|furigana|english`, `--model e235_1000|e235_0`. Controls: PageDown=PA, PageUp=STA, M=mode, ←/→=jump, ESC=quit. Full arg list in the `preview_display.py` docstring.
- **Build/Release** → `/build` + `/release` skills
- **Review** → `/review-dirty` (single) or `/review-plus-fix-relentlessly` (loop)
- **Commit** → `/commit` skill
- **Sweeps** → `/vibe-check` (codebase mess) or `/distill-docs` (doc bloat)

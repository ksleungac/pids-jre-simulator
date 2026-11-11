# PA Simulator Project

Japanese Train PA (Public Address) Simulator — a pygame app simulating station announcements and departure melodies (STA) with a visual LCD display.

The preloaded corpus is this file plus `.claude/rules/{principles,conventions,critical_lessons,redlines}.md`. Domain rules load with their files from the path-scoped `.claude/rules/<domain>.md`; domain docs are read on demand.

## Memory loop

Ported from game-in-idea on 2026-11-09; hooks in `.claude/settings.json`, code in `_harness/memory_loop.py`.

**Session start.** The SessionStart hook runs `_harness/session_init.py`: it fast-forwards master, pulls and publishes `private/memory`, checks the harness and fonts, and prints the tool inventory, the GitHub-Issues backlog and the `TODO.md` Directions headings. It adds the loop's notes: days never recapped, a quiet session's unlogged edits, the corpus size. Act on the notes before new work. A git-sync failure means the checkout is not current; fix that before trusting anything read from it. The full output is saved in `.claude/state/session-start.txt`. With no hook output in context, run `uv run _harness/session_init.py` yourself.

**During work.** Every turn that edits project files leaves one step line in today's `memory/YYYY-MM-DD.md`, under this session's own `## Session: in progress — <topic>` block: the step and why, written after the turn's last edit. Create the file with a `# YYYY-MM-DD` heading if missing. A turn that continues a logged step updates that line. The Stop hook blocks the end of a turn until this session has edited today's log. Edit with Edit/Write so the tracker sees it; for scratch-only edits run `uv run _harness/memory_loop.py skip <path>`. Another session's in-progress block is not yours to write into.

**Session end.** `/session-recap`: codify learnings into their home (synchronously, dedup-by-re-read, author approves; "wrap up" pre-approves), compress the in-progress block into a narrative block ending in a `**Codifications:**` line, add the index entry, publish. An in-progress block never publishes, so a session ending without a recap keeps its narrative local and the next session start names the day.

**Periodic.** `/distill-memory` (log → rules escapes) every ~15 sessions or when a correction repeats; `/distill-rules` for the rules corpus; `/distill-docs` for domain docs. `/third-man` for interpretation deadlocks and recap Step 0.

**Memory stream.** `memory/` is gitignored. Its canonical store is the journal-only `private/memory` ref, written only by `_harness/publish_memory.py`: git plumbing with no branch switch, append-only, refusing to republish an edited block. Session start pulls blocks published from the other PC into the local files. `memory/MEMORY.md` is too large to preload, so session start prints its last ten entries.

### Where things live

One fact, one home. Consult this before any doc write and pick the narrowest home.

| What | Home | NOT in |
|---|---|---|
| Project framing, scope, mental model, IRL conventions, the working loop | `CLAUDE.md` | rules files, domain docs |
| Values that shape judgment, true in any domain | `.claude/rules/principles.md` | CLAUDE.md |
| Style, naming, tooling, true in any domain | `.claude/rules/conventions.md` | CLAUDE.md |
| Hard boundaries | `.claude/rules/redlines.md` | anywhere else |
| Past-mistake lessons, true in any domain | `.claude/rules/critical_lessons.md` | anywhere else |
| A rule that bites only in one domain | path-scoped `.claude/rules/<domain>.md`: `display` · `tims` · `audio` · `ocr` · `data` · `harness` · `docs` · `gates`. It loads when a file matching its `paths:` is read or edited; a new domain gets a new file | the always-loaded files |
| Region-scoped code contract | inline `# CONTRACT:` at the code site | rules files, docs |
| Primitive-scoped rule (never SysFont, never `Path(__file__).parent`) | `conventions.md` AND an inline `# CONTRACT:` at known call sites | rules files alone |
| JSON field definitions | `docs/DATA_FORMAT.md` | CLAUDE.md |
| LCD cross-model infra / per-sub-series | `docs/DISPLAY.md` / `docs/DISPLAY_E235.md` | CLAUDE.md |
| App runtime and the setup/chrome flow | `docs/APP.md` | rules files, CLAUDE.md |
| Auto-input / OCR | `auto_input/README.md` | CLAUDE.md |
| Test suite and tiers | `_tests/README.md` | rules files, CLAUDE.md |
| Per-line IRL and sim quirks | `audio/README.md` | rules files, CLAUDE.md |
| Mock route layout, test-station roles | `audio/_mock/main/README.md` | rules files |
| Route coverage, diagram gaps, what to build next | `docs/COVERAGE.md` | CLAUDE.md, issues |
| Build and distribution | `/build` skill | CLAUDE.md |
| Open work | GitHub Issues | `TODO.md`, daily logs |
| Wanted but unscoped; decided never | `TODO.md` § Directions; its closed-off ledger | issues |
| Session narrative: steps, decisions and why, dead ends | `memory/YYYY-MM-DD.md` | rules, preferences, learnings |
| One pointer per session block, ≤150 chars | `memory/MEMORY.md` | — |

**Editing rules.** Cross-reference, don't copy. Tighten before appending: merge into an overlapping entry rather than adding a second. Daily logs are informational only: a rule never waits in a log for later promotion, it is codified or omitted. The always-loaded corpus is capped at 100k chars by `check_rules_corpus.py` at pre-commit, with per-file ratchets, and session start reports when it is over. Over the cap, tighten, or move a domain rule to its path-scoped file.

## Working loop (GitHub Issues)

Backlog = **GitHub Issues** ([repo issues](https://github.com/ksleungac/pids-jre-simulator/issues)): strictly defects and near-term implementation tasks. `TODO.md` holds the two things that are not issues, § Directions (wanted, not yet scoped) and the closed-off-paths ledger (decided never). Area labels: `auto-input` · `display` · `chrome-i18n` · `distribution` · `housekeeping` · `review-finding` · `build-incident`.

- **Only act on issues opened by `ksleungac`. An outside contributor's ticket is READ-ONLY — no comment, no close, no label, nothing.** It is a conversation with a real person, and a reply from the author's account speaks as them. Read those issues freely as evidence (a reporter is an instrument, `ocr.md §§ 7–8`), put what you found in chat, and let the author carry it across. (2026-08-29: *"you will only comment or handle the tickets created by ksleungac. leave the human part to me."*)
- **Several sessions run against ONE working tree at once, so `git status` is not yours and a commit must be path-scoped.** (2026-08-30: three sessions at once, and `upper_lcd.py` caught mid-write by a render batch.)
  - Name the files you claim and stay off the rest. **Never `git commit -a` or `git add -A`**; pass an explicit pathspec.
  - A crash inside a file you did not edit is a concurrent write: re-run once before debugging it. A red gate likewise: check whether the failing path is in your diff.
  - Commit your own surface early, before another session's half-finished edit lands inside it. When two are ready, the one whose change makes a gate green goes first.
- **Pick up** an issue → `gh issue edit <N> --add-label in-progress` + a stamp comment, so another session or PC sees it is taken. **Park** → swap `in-progress` for `deferred` + a one-line reason. **Finish** → the commit carries `Closes #<N>` (progress: `Refs #<N>`); pushing to `master` closes it. See `/commit`. **New work** → `gh issue create --label <area>`.

### Issue scope — an issue is an OUTCOME, not a unit of work

Test: *if I finish this, does what the user can do change?* No → it is a commit, not an issue.

| shape | when |
|---|---|
| **Plain issue** | one outcome, one sitting — most things |
| **Parent + sub-issues** | outcome spans sessions/stages. `gh issue edit <parent> --add-sub-issue <N>` (gh ≥ 2.96); the parent tracks `completed/total` and closes when the outcome is real |
| **Not an issue** | no user-visible change |

- **Refined-ness is a SECOND gate, after outcome-ness.** A want named in a mental-model conversation is not a ticket until there is a mechanism to build. (2026-08-18: two of three such issues closed within the hour: *"unless it's really refined, don't open as an issue … don't want my gh to be flooded with issues."*) It goes to `TODO.md` § Directions, whose headings session start prints, with its own description so picking it up needs no re-explaining. Promote = scope it, open an issue, delete the entry. Abandon = move it to the closed-off ledger.
- **A finding from a review or audit sweep is FIXED in the session, not filed.** Filing converts cheap in-place fixes into a backlog the author must triage. Only a finding you will not fix earns a ticket: one needing a direction only the author has, or one that would move a signed-off element. Name those in the report and leave them unfiled unless asked. (2026-09-12: *"no new issues grown"*.)
- **`Closes #N` only when you did everything #N describes.** Doing less means the scope was wrong: split a stage out under the outcome, never close it and open a peer, which orphans the outcome. (2026-07-20: #71 "window mirroring" restructured as parent of #77 stage 1 / #76 stage 2.)
- **A "signal missed → action suppressed" bug must name a scenario where the signal is missed AND the action is still wanted.** If the read whose absence loses the signal is the read that made the action necessary, they cannot come apart and there is no bug. (2026-08-11, #84: *"under what case is this missed yet the departure PA still needs playing?"*) Applies to any cache invalidation, dirty flag or edge-triggered handler.
- **Always write an issue as `#N "title"`, never the bare number**, on every prose surface. Commit trailers are exempt. (2026-08-11)

## Run

```bash
uv run main.py
```

After a fresh clone: `uv sync`, then `uv run pre-commit install`. Then add the private remote, which carries the narrative memory ref and the licensed Morisawa faces; without it there is no memory store and the LCD cannot render:

```bash
git remote add private https://github.com/ksleungac/private-pids-jre-simulator.git
uv run _harness/sync_fonts.py          # pull the faces this machine lacks
uv run _harness/sync_fonts.py --push   # publish any face only this machine has
```

Session start fetches it and names a missing face; `publish_memory` refuses to publish without it rather than pushing anywhere public.

## Mental Model

What this project models. It shapes every design decision; implementation details live in the domain docs.

### Project origin & scope

**Companion app for JRE Train Sim Real**, JR East's own train simulator. The game lacks PA and departure melodies on older routes, and this fills the gap. It started audio-only; the LCD grew as a "where am I" aid. **Audio is the foundation; the LCD is navigation.** Scope: JR lines in the Tokyo capital region.

**Coverage is asymmetric by design** — full picture, dates and gaps in [COVERAGE.md](docs/COVERAGE.md):
- **Lines**: exactly the JR Kantō routes the game shipped BEFORE in-game announcements became standard. **Gaps first is a PRIORITY rule, not a permission rule**; a voiced route is still worth building when wanted, and the gap list is nearly exhausted. **Coverage is a fact with a DATE on it**: the game has retro-fitted announcements onto shipped routes, so re-check before starting a build.
- **Diagrams**: the full-line diagram is canonical per route. Another is worth building only for a **different stopping pattern**, and a diagram is the tuple *(pattern, destination, formation, day type)*, not the service label.

**Distribution is lightly public**: GitHub and YouTube (~1800 plays). Some users are **active collaborators**: they trade IM and email with the author, know the data model and the OCR pipeline, and test on their own hardware. A defect that will not reproduce here is not a dead end; the reporter is an instrument (`ocr.md §§7–8`). **The fidelity bar is high**: elements iterate against IRL reference photos until pixel-correct.

### Distribution & deployment artifact

Ships as a PyInstaller exe (Windows). **Silent breakage in a release build is the worst case**: the dev env has everything installed and the user's exe does not.
- **Bundled:** all `dependencies` in `pyproject.toml`; code at project root and `displays/`; `audio/`, `data/`, `fonts/`, `ocr_templates/`.
- **Not bundled:** the `dev` dep group; `_*` folders, which production code MUST NOT import from (`conventions.md` § Naming).
- Dep classification follows the call graph (`critical_lessons.md` § 3). Build mechanics: `/build`.

### Direction of travel

**Mature phase**: architecture done, audio pipeline mature, visual fidelity high.
- **Steady state**: new train models and display fidelity polish. E233-0 is a re-skin close to E233-1000, so one skin serves Chūō and Keihin-Tōhoku, whose audio already ships.
- **OCR auto-drive is the PRIMARY interface, not a side-quest.** Assume every user runs it (author, 2026-08-18). It template-matches the game HUD on window-bound capture, one sample every 3 s by default (1–10 s, user-set; `auto_input/README.md` § "Sample interval"). **1080p is the canonical resolution and the absolute-stability target**: every input is downscaled to 1080p, so the bar is the real user's softened 1080p capture (`ocr.md §7`). The remaining user-facing gap is **unusual aspect ratios**, which puts resolution support ahead of the rest of this list.
- **Distribution polish**: signed installer, first-run smoothness. Real, and secondary.
- **Closed-off** (don't re-propose): memory hooking `*saf.dll`, decrypting SimDATA, audio fingerprinting, full-desktop OCR, tesseract, lines the game already covers, Mac build.

### Train family

JR East runs several series, E233 (sub-series 0–8000) and E235 (0 and 1000) among them. Each has its own LCD look over a mostly shared element set: clock, station name, route bar, mode cycling, badges, view alternation. A new model is a re-skin under `displays/train_models/{model}/`, not a re-architecture.

### Per-model IRL line scope (in-spec vs best-effort)

Every series runs on a fixed subset of lines IRL. The mappings are not memorized; ask when scope matters. The simulator accepts any route into any model:

| Route | Behavior |
|---|---|
| **In-spec** (model's IRL lines) | Match the real PIDS |
| **Out-of-spec** | Best-effort: no crashes, no missing-key errors, no broken layouts. Not obligated to IRL fidelity |
| **No IRL LCD** (E233-3000, E531, E217) | No real PIDS to match, so the bar is **plausibility**: a legitimate fictional render. Prefer the nearest real relative; a linear-native model on a linear line needs no adaptation. Lines: [COVERAGE.md](docs/COVERAGE.md) |

**Best-effort = the model's OWN native norm applied to any route — never a borrowed behavior or bespoke feature propping up an out-of-spec route.**
- **Adapt the model's own look to the route's shape**: e235_0 opens its circular racetrack into a horseshoe for a non-loop line.
- **Don't import another model's behavior**: e235_0 drops e235_1000's end-of-route lock, a linear heuristic foreign to a loop.
- **A route shape needing a marker the view has no calibrated slot for reuses an EXISTING calibrated primitive degenerately**: a passing station in the 5-station view renders the countdown ring empty, never an invented chevron (#66; the proper chevron is deferred, #99).

*For the reviewer:* a cross-model divergence where each model expresses its own native norm is not sibling drift; a borrowed foreign feature is the violation. Out-of-spec renders are **transitional**: e235_1000 is the general model until per-line native models land, and out-of-spec support is then removed rather than grown. **No-LCD renders are permanent**, because no native model can land for a train with no LCD.

### IRL display conventions

Behaviors true on real trains, mirrored by the simulator:
- **Destination stays kanji** even in furigana mode. English uses "Bound for" + the English destination.
- **Stop-level destination override**: circular routes change destination mid-route.
- **Station code badge**: 3-letter Roman code for ~22 major interchanges, from `data/stations.json`.
- **Compound destinations** use the `&` separator.
- **English uses modified Hepburn with macrons** (Tōkyō, Chūō); encoding in [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md).
- **Through-service combined frame**, modeled via `pre_stops` in route.json ([DATA_FORMAT.md § "pre_stops Array"](docs/DATA_FORMAT.md)).
- **PA and STA are independent audio sources** and overlap freely: PA on `mixer.music`, STA on a dedicated `mixer.Channel`.

### App state machine

Each stop: **APPROACHING_EARLY** → **APPROACHING_FINAL** → **STOPPING** → next stop. PageDown drives transitions; `jump_to_stop` lands in STOPPING at the target. Spec: [docs/DISPLAY.md § Unified State Machine](docs/DISPLAY.md). **Auto-fire asymmetry:** APPROACHING auto-fires `pa[0]` (the passive-listening window); STOPPING never auto-fires, and every `pa_at_station` entry plays only on a press.

## Writing tone

Factual and non-performative, the voice of the release notes, on every prose surface: chat, docs, memory, commits. On top of the global preferences:

- Use the fewest words that carry the technical detail. Length is earned by content; a sentence explaining why the previous one was right gets deleted.
- Reach for the plain word first: "output", not "distillation deliverables". A manufactured compound means the plain word has not been found.
- Cut words that show understanding or diligence, scaffolding that argues your own point, intensifiers (*exactly*, *the tell is*) and hedges (*arguably*, *tends to*), "X, not Y" unless Y is a real wrong path, differences the reader already sees, and any mark of compliance.
- State what you know plainly, and real uncertainty just as plainly (*unverified*, *haven't checked X*).
- **Sentence architecture.** One clause stack per sentence; past ~35 words, split it. A parenthetical carrying a real qualification becomes its own clause, and one carrying an aside goes. The em dash is not the default connector.
- **Cut structure, never facts.** Splitting a sentence costs nothing; dropping the consequence that motivates a rule or the symptom that identifies it takes the wrong thing.
- Asked what something is: short plain prose, no headers, in the order asked. (2026-08-30)
- A file on disk has the length its task needs, with no filler section and no summary restating the one above. A doc's own size cap is a gate, not a target.

## Working narration

One sentence before the first tool call, stating the action and nothing about why it is right. While working, surface only a finding that changes the picture or a change of direction; skip acknowledgment turns. (2026-05-02: *"wasted me 30 seconds to read while you DO NOT save for the next session."*) The closing message leads with the outcome; a file list is not a report.

## Code map

```
main.py                 entry: picker → setup orchestration
app.py                  PASimulator, AppState, PA/STA handling, input loop
audio.py                AudioPlayer: play_pa / play_sta / pause / is_playing
app_paths.py            project_root(): the only bundled-asset path resolver
constants.py            cross-module values only (TIME_SCALE=60, FRAME_RATE=15, audio, setup palette)
route_loader.py         finalize_route: route.json → runtime closure with derived fields
font_atlas.py           LCD font seam: live fonts in dev, baked atlas in a shipped build
i18n.py                 app-chrome strings, locale detection, chrome fonts
frame_stream.py, qr.py  window mirroring over HTTP with taps back; its dependency-free QR encoder
departure_bell.py, bell_window.py   the departure-bell box
window_utils.py         always-on-top pinning, DPI awareness
update_check.py, tutorial.py, plot_drive.py (Report button)
displays/               base.py (DisplayMode, ModeCycler, ChangeScheduler) · lower_lcd.py (slot cycle,
                        force-switch, frame swap) · transfer_info.py · utils.py (all drawing primitives) ·
                        train_models/{e235_1000,e235_0,e233_0}/ (per-model upper and lower LCD)
tims/                   TIMS cab-console UI: widgets.py, chrome.py (palette, presets), band.py, setup/
auto_input/             OCR auto-drive: driver.py, ocr.py, hud_layout.py, sampling.py
data/                   translations, train types, app-chrome strings, station metadata
audio/<line>/<diagram>/route.json   real routes; audio/_mock/ holds preview fixtures
preview_display.py, preview_transfers.py, validate_data.py   dev entry points
```

## Key Features

1. **Display cycling** (1 beat = 4 s): KANJI → FURIGANA → ENGLISH; the destination stays kanji.
2. **Lower-LCD view alternation**: full-route ↔ 8-station zoomed, plus transfer when in window. One `ChangeScheduler` owns language and slot on a shared beat ([docs/DISPLAY.md § Change scheduler](docs/DISPLAY.md)).
3. **Real-time countdown**: `TIME_SCALE=60`, floor division, forces "1" on the last PA.
4. **Station skip**: time-based red-arrow progression through passing stations.
5. **Single train-position index**: `state.curr_stop` is stored; `state.cursor_pos` is derived and lags during the skip animation.

## Controls

| Key | Action |
|-----|--------|
| Page Down | Play PA (blocked while playing) |
| Page Up | Play STA (jumps to sta_cut if playing) |
| End | Pause |

Yellow hint square = more presses yield more PA at this stop. In transit it keys on `len(pa) > 1`, at the platform on `len(pa_at_station) > 0`, because `pa` is 2-by-default and `pa_at_station` empty-by-default.

## When Working On...

Consult when needed, not upfront:

- **App architecture / setup flow** → [docs/APP.md](docs/APP.md)
- **Data/JSON** → [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md)
- **LCD displays** → [docs/DISPLAY.md](docs/DISPLAY.md) (cross-model); [docs/DISPLAY_E235.md](docs/DISPLAY_E235.md) (per-sub-series)
- **Audio/Diagram** → `/pa-make` or `/sta-make`; per-line quirks in [audio/README.md](audio/README.md)
- **Auto-input / OCR** → [auto_input/README.md](auto_input/README.md)
- **Testing** → [_tests/README.md](_tests/README.md)
- **Code contracts** → inline `# CONTRACT:` blocks at code sites
- **Preview** → `uv run preview_display.py` (mock route) or a real route via `--route <line>/<diagram>` (e.g. `--route sobu/1217F --stop 9`). Flags: `--screenshot out.png` (headless still), `--lower-view <slot>` (freeze a view), `--mode kanji|furigana|english`, `--model e235_1000|e235_0|e233_0`. Controls: PageDown=PA, PageUp=STA, M=mode, ←/→=jump, ESC=quit. Full list in the `preview_display.py` docstring.
- **Build/Release** → `/build` + `/release`
- **Review** → `/review-dirty` (single) or `/review-plus-fix-relentlessly` (loop)
- **Commit** → `/commit`
- **Sweeps** → `/vibe-check` (code), `/distill-docs` (domain docs), `/distill-rules` (rules corpus), `/distill-memory` (logs → rules)

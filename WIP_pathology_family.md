# WIP — PyInstaller deployment-frame pathology family

**Status:** discussion-pending. Captured 2026-05-05 from two release-build crashes during v0.5.3 build cycle. Will be promoted to `.claude/rules/critical_lessons.md` after discussion settles the framing + scope.

## Final tally — pathology spread across production code

What started as one wrong helper turned out to be **at least 8 broken or ad-hoc path-resolution sites** across 6 files plus 1 missing-asset class in the build script:

**Wrong/broken path resolvers (no `sys.frozen` check at all — `Path(__file__).parent` resolves to `_MEIPASS` in frozen builds, files not found):**
- `auto_input.py:87` — `RECORDINGS_DIR` (write target — drive recordings would silently land in temp `_MEIPASS/_recordings`, lost on exit)
- `auto_input.py:210` — fonts path for OCR debug panel (the second crash today)
- `auto_input.py:275` — drive-recorder HTML report `out_path` (write target — reports also lost to temp)
- `ocr.py:108` — `DEFAULT_TEMPLATES_DIR` (read target — caused the "missing digit templates" crash today)
- `plot_drive.py:41` — `ROOT` for both `_recordings` reads and HTML output writes

**Wrong-semantics path resolver:**
- `i18n.py:app_root()` — returned `_MEIPASS` for frozen builds (the FIRST crash today, FileNotFoundError on `data/translations_app.json`)

**Inline-but-correct duplicate:**
- `i18n.py:settings_path()` (line 28-30) — manually inlined the `Path(sys.executable).parent if frozen else Path(__file__).parent` pattern

**Ad-hoc resolver bypassing `sys.frozen` entirely:**
- `app.py:_load_station_db` (lines 265-271) — derived "project root" by walking up from `work_dir`, no frozen check; works only by accident in frozen mode because `work_dir` happens to be alongside-exe via Step 4's audio junction

**Missing-asset class in build script:**
- `/build` Step 4 only copied `data/*.json` — not `data/line_icons/` (caused the SECOND crash today: `FileNotFoundError: data\line_icons\JS.png`)
- `/build` Step 4 also didn't copy `ocr_templates/` — caused the THIRD/FOURTH crash today when user enabled `--auto-input`

**The recurrence count is striking:** today's session surfaced FOUR distinct release-build crashes from the same pathology family within a single hour. The user's "jackpot" framing reflects that this is broader than any individual bug — the entire codebase is riddled with deployment-frame-divergence land mines, and code review processes (vibe-check, review+fix) didn't fire on any of them because nothing in the rule corpus targeted PyInstaller path semantics.

## The two incidents (initial — kept for narrative)

### Incident 1 — wrong path-root semantics
`i18n.py:app_root()` returned `Path(sys._MEIPASS)` for frozen builds. But `data/translations_app.json` is NOT bundled INTO the exe via `--add-data`; it's copied ALONGSIDE the exe by `/build` Step 4. So `_MEIPASS` (the temp extraction tree for files bundled into the exe) doesn't have it. The exe crashed on launch with `FileNotFoundError`.

Investigation surfaced **4 separate path-resolver helpers** across the codebase, each invented locally:
- `displays/utils.py:project_root` — correct semantics
- `displays/train_models/e235_1000/upper_lcd.py:get_base_dir` — correct semantics
- `i18n.py:app_root` — WRONG (`_MEIPASS`) — the crash
- `app.py:265-271` — ad-hoc derivation from `work_dir`, no `sys.frozen` check, works only by accident

A prior `/review+fix` cycle had explicitly told claude to **leave `i18n.app_root` alone** with the rationale "those `_MEIPASS` semantics are intentional for read-only bundled assets vs alongside-exe settings." That advice was wrong — the reviewer reasoned about PyInstaller bundling semantics from cached impression because **no codified rule fired** on PyInstaller path-resolution. Vibe-check + review+fix corpus had no entry that would have made the reviewer verify rather than assume.

### Incident 2 — missing shipped asset
After Incident 1 was fixed, the rebuilt exe crashed again at runtime with `FileNotFoundError: data\line_icons\JS.png`. The transfer-info renderer (shipped this week) loads icons from `data/line_icons/<slug>.png`. But `/build` Step 4's stage copy was `Copy-Item "data\*.json"` — only JSON, not the new `line_icons/` subdirectory.

The build script and program had drifted out of sync: program added a new asset class, build script didn't extend its copy glob. Same shape as Incident 1 — silent in dev (both trees are present), explodes in the release build.

## The pathology family — initial framing (subject to user discussion)

Both incidents are **deployment-frame divergence**: dev mode hides a contract violation that surfaces only in the frozen exe.

Sibling existing entries in `critical_lessons.md`:
- **2026-04-27** — "Runtime-required materials must be committed (or have a deterministic build path)." Silent no-op on missing files in release build.
- **2026-04-30** — "Lazy import ≠ optional dep — classify by call-graph reachability." Silent ImportError swallow in release build.
- **2026-05-05** (today, two incidents) — path resolution + shipped-bundle coverage are deployment-frame contracts, not dev-time correctness checks.

All three share a root: **claude reasons about code as text rather than as a deployed artifact.**

## PyInstaller mechanism distinction (the actual semantics — for the eventual rule)

- `sys._MEIPASS` — temp directory created at exe startup, populated by extracting files bundled INTO the exe via `--add-data` (or PyInstaller's automatic `package_data` collection for `--collect-data <pkg>` libs). Lifetime = the exe's run.
- `Path(sys.executable).parent` — directory containing the exe on disk. This is where `/build` Step 4 copies `data/`, `fonts/`, `audio/` next to the exe at stage time.

**This codebase does NOT use `--add-data` for project assets.** Only `--collect-data plotly` (for plotly's library-internal JS bundle). All shipped project assets are alongside-exe via Step 4 copy. Therefore `_MEIPASS` is always wrong for our project asset loads. If a future change adds `--add-data` for some asset class, that's a new contract that needs its own helper and its own CONTRACT block.

## Candidate rules (to refine in discussion)

Two interlocking rules are tempting. User pushback may shape these into one or split them differently:

**(a) Path-root resolution.** Every module that loads bundled assets MUST go through `app_paths.project_root()`. No new local `app_root()` / `get_base_dir()` / `_project_root()` helper, no inline `Path(sys.executable).parent if frozen else Path(__file__).parent`. The canonical home is `app_paths.py` at project root; that's where the CONTRACT lives.

**(b) Shipped-bundle coverage.** When the program adds a new directory or file class under `data/`, `fonts/`, or any alongside-exe asset tree, the `/build` skill's Step-4 stage copy must be extended in the same commit. Recursive copy with `_*` exclusion (matching the audio pattern) handles new subdirectories under `data/` automatically; new top-level trees still need explicit Copy-Item lines.

## Why vibe-check + review+fix didn't catch this earlier

User's exact question: *"why vibe check, review+fix doesn't catch this out, and did anywhere in my current docs/rules says about this"*

**Nowhere in current docs/rules said about this.** Grep across `.claude/rules/` shows no matches for `_MEIPASS`, `alongside-exe`, or "PyInstaller path resolution." Vibe-check's smell list (Step 2 #1-#10) covers duplicated logic, dead helpers, half-finished work, magic numbers, etc. — none specifically targets "deployment-frame divergence in path resolvers." A prior review+fix cycle defended `i18n.app_root` from cached impression rather than verifying.

**Discussion candidates:**
- Should this become a critical_lessons.md entry (sibling to 2026-04-27 + 2026-04-30)? Likely yes; question is scope — one entry covering both the path-resolution and bundle-coverage halves, or two siblings?
- Should `/vibe-check` get a new smell category for "ad-hoc path resolvers / `sys._MEIPASS` references outside `app_paths.py`"?
- Is there a meta-pattern across the three sibling lessons worth extracting (e.g. "always trace deployment-frame behavior, not just dev")?
- The recurrence shape — claude reasons about code as text rather than as deployed artifact — was already named in 2026-04-30. Today's incident is the third instance. Does the meta-rule need promotion to `principles.md` § Verify before claiming as a sibling, or is a 3rd concrete entry enough?

## Concrete fixes already applied (codified vs not)

**Code-side (committed-or-staged):**
- `app_paths.py` created at project root with single canonical `project_root()` + terse CONTRACT pointer back to this WIP doc (will move to critical_lessons.md when discussion settles).
- `displays/utils.py:project_root`, `upper_lcd.py:get_base_dir`, `i18n.py:app_root` — collapsed into thin re-exports / aliases pointing at `app_paths.project_root`.
- `app.py:265-271` ad-hoc resolver — flagged in TODO.md for replacement, NOT yet fixed.
- `i18n.py:settings_path()` (line 28-30) — inline duplicate of the same frozen branching, NOT yet fixed.
- `tutorial.py` + `setup.py` callers still reach via `i18n.app_root()` — alias chain works, NOT yet flattened.

**Skill / rule side:**
- `/build` skill Step 4 — Copy-Item updated to recursive copy of `data/` (with `_*` harness exclusion) so future subdirectories ship without skill edits. Documentation note added re: bundle-script-must-track-program-asset-reads.
- `critical_lessons.md` — NOT YET updated. Pending this discussion.
- `CLAUDE.md` + `DISPLAY.md` — still point at `upper_lcd.py:get_base_dir` as the canonical home of the PyInstaller path-resolution contract. Need to update to point at `app_paths.py:project_root` once we settle the codification.
- `/vibe-check` — NOT YET updated. Pending discussion of whether a new smell category fires here.

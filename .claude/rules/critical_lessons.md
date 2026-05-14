# Critical Lessons - DO NOT REPEAT

## ⚠️ CRITICAL: Verify Files BEFORE Destructive Operations

**Date:** 2026-03-19

### The Incident
Renamed STA files and updated route.json references without first verifying that all corresponding MP3 files existed. Result: `kita-ageo.mp3` was missing but route.json had already been modified to reference it.

### The Rule (APPLIES TO ALL DESTRUCTIVE OPERATIONS)

> **NEVER rename, delete, or overwrite files without first verifying the current state of the target directory.**

**Before ANY file operation (rename/move/delete/overwrite):**
1. **LIST** all files in the target directory using `Glob`
2. **VERIFY** what files actually exist on disk
3. **CROSS-REFERENCE** with any config files that reference them
4. **IDENTIFY** gaps or discrepancies BEFORE making changes
5. **REPORT** findings to user for confirmation
6. **THEN** proceed with minimal, verified changes

### Applies To:
- Renaming files (any extension: `.mp3`, `.json`, `.py`, etc.)
- Deleting files or directories
- Overwriting existing files
- Modifying config files that reference external files
- Moving files between directories
- Batch operations on multiple files

### Why This Matters
- **Assumptions are dangerous**: Never assume files exist or have expected names
- **Destructive operations are hard to undo**: Especially when original state is lost
- **User work can be lost**: User manually creates/fills files - AI should not破坏 this
- **Verification is cheap**: One `Glob` call prevents costly mistakes

### The Pattern (Use This Every Time)

```
BEFORE: "I'll rename these files and update the config"
AFTER:  "Let me first check what files actually exist"

1. Glob(pattern="target_dir/*")  ← ALWAYS FIRST
2. Compare with expected list
3. Report: "Found X files, missing Y, ready to proceed?"
4. Wait for confirmation
5. Then act
```

### Discussion-First Approach
**File operations are NOT routine maintenance** - they are destructive actions that require user confirmation. Always:
- Present findings first
- Explain what will be done
- Wait for explicit go-ahead
- Verify after completion

**Measure twice, cut once.**

---

## ⚠️ CRITICAL: Runtime-required materials must be committed (or have a deterministic build path)

**Date:** 2026-04-27

### The Incident
The `auto_input` OCR feature loaded its digit templates + badge anchors from `game_references/*.png` at AutoDriver startup. Those PNGs were ~33 MB of full desktop screenshots, and they were **never committed** — gitignored implicitly via being untracked, treated by the user as "dev references." The user deleted them between sessions thinking they were dev cruft. Auto-driver came up with zero templates → silent OCR failure on the live drive (warning logged, but feature unusable).

### The Rule
> **If your code reads a file at runtime, that file must either be (a) committed in the repo, or (b) deterministically regenerable from committed sources via a one-command build step. Never both "required at runtime" AND "named like dev material" AND "uncommitted."**

The anti-pattern is: a file is *required at runtime*, lives under a *dev-named folder* (`game_references/`, `references/`, `samples/`, `examples/`), and is *not in git*. Each property alone is fine. Combined, the user can't tell the file's status from its name, deletes it, and the feature breaks silently.

### Applies To
- Template files, calibration data, pre-trained models, fixtures, asset bundles
- Anything `path.exists() else continue` patterns that silently no-op when missing
- Especially: data extracted/derived from much larger sources (the size disparity is what tempts you to leave the big sources uncommitted)

### The Pattern (Use This Every Time)

When a feature needs a non-code artifact at runtime:

1. **Ask: should this artifact be committed?** Default yes.
2. **If small (< few MB total)**: commit it. Put it under a name that signals "runtime input" not "dev material" — e.g. `<feature>_templates/`, `data/<feature>/`, NOT `references/` or `samples/`.
3. **If large (> few MB)** OR derived from larger sources: commit the *derived small artifact*, leave the *source* gitignored. Add an extraction script (`_dev_scripts/extract_<feature>_assets.py` or similar) that regenerates the artifact deterministically from sources. Document the source-folder location + how to recapture it.
4. **Fail loudly** when the artifact is missing at runtime. Not `silently skip`, not `continue with degraded behavior`. Log a `FATAL` with the path expected and the regeneration command, and refuse to start.

### Why This Matters
- **Silent no-op on missing files is the worst-case behavior** — the feature looks like it loaded, then misbehaves at the worst moment (the live drive). A loud FATAL at startup would have caught this in seconds.
- **Naming carries semantics.** "References" / "samples" / "examples" all imply optional / dev-only. Use names that match status: runtime input gets a runtime-input name.
- **Two-part repos are normal** (committed binaries / data files alongside code). The mistake isn't having binary data; it's leaving that data in a "is this dev or runtime?" ambiguous state.

### Concrete fix applied (this incident)
- Source screenshots → `_ocr_calibration/` (gitignored, `_` prefix matches project local-only convention).
- Extracted templates → `ocr_templates/digits/*.png` + `ocr_templates/badges/*.png` (committed, ~50 KB total).
- Extraction script → `_dev_scripts/extract_ocr_assets.py` (one-command regeneration when sources are recaptured).
- AutoDriver now FATAL-exits with a helpful message if templates are missing.

---

## ⚠️ CRITICAL: Lazy import ≠ optional dep — classify by call-graph reachability, not file location

**Date:** 2026-04-30

### The Incident
The drive-recorder Report ↓ button (production-side: `auto_input.py`) imported `data_tools/plot_drive.py` lazily, wrapped in `try/except`. `plot_drive.py` had been placed in `data_tools/` (a folder tagged dev-only by prior memory), and `plotly` was added to the `dev` dep group. None of these decisions was independently wrong; together they meant the Report button was silently broken in any release build (where `dev` deps don't ship). The chain of inferences that led here:

- `data_tools/` was tagged dev-only → "files there are dev-only"
- New `plot_drive.py` placed in `data_tools/` because it looked tool-shaped → "this file is dev-only"
- `plotly` is used by `data_tools/plot_drive.py` → "plotly is dev-only"
- The production-side import was wrapped in `try/except` "to defer cost" — which actually **swallowed the ImportError** that would have surfaced the misclassification on day one

The deeper pathology: each step was locally defensible. The chain looked coherent. Only a global call-graph check would have revealed that a production code path imported a dev-only file pulling in a dev-only library.

### The Rule
> **Dependency classification follows call-graph reachability, not file location, neighbor classification, or import timing. If any production-reachable code path imports a library — eager, lazy, behind a button, behind a flag — that library is a runtime dep.** "Lazy" is a performance choice (controls *when* the lib loads); "optional" is a contract choice (controls *whether* the lib must be installed). They are not interchangeable.

### Applies To
- All Python deps in `pyproject.toml` (`dependencies` vs `dev`).
- All file placements under `_*/` paths (per `conventions.md` § "_*" prefix). A file imported by production code does not belong under `_*/` — promote it.
- All defensive imports. `try: import X except ImportError: ...` is only correct when X is **truly optional**, with the no-X path explicitly tested. It is NEVER a substitute for correct dep classification.

### The Pattern (Use This Every Time)

When adding a new library:
1. **Trace the call graph.** Who imports the module that uses this lib? Who imports them? Continue until you reach a production entry-point (`main.py`, `app.py`, etc.) or hit a `_*/` boundary.
2. **Any production path reaches it → `dependencies`.** Period. No exceptions for "lazy" or "optional-feeling" usage.
3. **Only dev/CI paths reach it → `dev` group.** Note why in a comment if non-obvious.
4. **Never use `try: import X except ImportError` as a substitute for classification.** Either the lib is required (then `dependencies` + fail loud at import) or it's truly optional (then test both paths exist and behave correctly).

When placing a new file:
1. **Will production code import it?** Yes → root or `displays/`. No → `_dev_scripts/` (or `_experiments/` for not-yet-stable work).
2. **Folder placement carries dep-classification semantics.** A file under `_*/` that pulls in `dependencies`-class libs is a smell — the file is closer to production than the folder admits.

### Why This Matters
- **Silent failure in release builds is the worst-case mode.** Dev env has everything installed; user's release exe doesn't. The misclassification is invisible until a user clicks the broken button.
- **Each individual decision was locally defensible.** The chain "lazy → defer → optional → dev → data_tools" was coherent at every step. Only zooming out to the call graph reveals the contradiction.
- **The cross-check costs ~30 seconds.** `grep -rn "from <suspect_path>" --include="*.py" .` (excluding `_*/` itself). Run it before classifying any new dep.
- **Sibling lesson** (2026-04-27 above): runtime-required *materials* must be committed (or have a deterministic build path). Same shape, applied to libraries instead of asset files: production reachability determines whether something must be in the deployed artifact, regardless of "feels like dev tooling."

### Concrete fix applied (this incident)
- `dxcam` + `plotly` promoted from `dev` → `dependencies` in `pyproject.toml`.
- `plot_drive.py` moved from `_dev_scripts/` (formerly `data_tools/`) → project root, matching its production-import status.
- `data_tools/` renamed → `_dev_scripts/`, matching the `_*/` convention so the dev-only status is visible in the folder name itself.
- `/vibe-check` skill: new smell category #10 ("production code imports from `_*/` paths") — mechanical check for when the convention fails.
- Codified: `CLAUDE.md` § "Distribution & deployment artifact"; `conventions.md` § "_*" prefix extended with the hard rule + pointer to this entry.

---

## ⚠️ CRITICAL: PyInstaller deployment-frame divergence — path resolution + bundle coverage

**Date:** 2026-05-05

### The Incident
The v0.5.3 build hit **four separate release-build crashes within an hour**, all from the same family:

1. **Wrong path-root semantic** — `i18n.py:app_root()` returned `Path(sys._MEIPASS)` for frozen builds. But `data/translations_app.json` is NOT bundled INTO the exe via `--add-data`; it ships ALONGSIDE the exe via `/build` Step 4 copy. So `_MEIPASS` was empty for our project. Crashed on launch.

2. **Missing shipped asset (`data/line_icons/`)** — `/build` Step 4 was `Copy-Item "data\*.json"` (only JSON). The transfer-info renderer added in this release loads PNG icons from `data/line_icons/`. Crashed at first render.

3. **Path-root semantic + missing asset, both** — `ocr.py:DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "ocr_templates"` resolved to `_MEIPASS/ocr_templates/` in frozen mode (wrong root). AND `/build` Step 4 didn't copy `ocr_templates/` at all. Double-broken; crashed on `--auto-input`.

4. **Wrong path-root in fonts** — `auto_input.py:_get_panel_font` used `Path(__file__).parent / "fonts" / ...` which resolved to `_MEIPASS/fonts/` — wrong root, even though fonts WERE copied alongside-exe. Crashed on `--auto-input`.

Investigation surfaced **8 path-resolver call sites across 6 files**: 5 broken (no `sys.frozen` check), 1 wrong-semantic (`_MEIPASS`), 1 inline-but-correct duplicate, 1 ad-hoc bypass. Plus 2 missing-asset classes in the build script.

A prior `/review+fix` cycle had explicitly told claude to **leave `i18n.app_root` alone** with the rationale *"those `_MEIPASS` semantics are intentional for read-only bundled assets vs alongside-exe settings."* That defense reasoned from generic PyInstaller mythology (Stack Overflow conflates `--add-data` and alongside-exe staging) — true *sometimes*, wrong here. **Nothing in the codified rule corpus fired** on PyInstaller path resolution; vibe-check + review+fix corpus had no entry that would have made the reviewer verify rather than assume.

### The Rule
> **Two interlocking rules — both load-bearing.**
>
> **(a) Single canonical path resolver.** Every module that loads bundled assets MUST go through `app_paths.project_root()`. No new local `app_root()` / `get_base_dir()` / `_project_root()` helper. No inline `Path(sys.executable).parent if frozen else Path(__file__).parent`. No `sys._MEIPASS` references outside `app_paths.py` (we don't use `--add-data` for project assets — only `--collect-data plotly` for plotly's library bundle). Inventing a local resolver is the smell that produced this incident.
>
> **(b) Bundle script tracks program asset reads.** When the program adds a new top-level alongside-exe asset tree (or a new asset-class within an existing tree), `/build` Step 4's stage copy must cover it. Drift between "program reads X" and "build copies X" is silent in dev (both trees present) and explodes in the release exe. The 2026-05-05 fix inverted Step 4 from include-list to exclude-list (default-ship every top-level dir, maintain only what NOT to ship) so new asset folders ship automatically.

### PyInstaller mechanism distinction (the actual semantics)

- **`sys._MEIPASS`** — temp directory created at exe startup, populated by extracting files bundled INTO the exe via `--add-data` or `--collect-data <pkg>`. Lifetime = the exe's run.
- **`Path(sys.executable).parent`** — directory containing the exe on disk. This is where `/build` Step 4 copies `data/`, `fonts/`, `audio/`, `ocr_templates/` next to the exe at stage time.

**This codebase uses `_MEIPASS` ONLY for plotly's library bundle (via `--collect-data plotly`), never for project assets.** Therefore `_MEIPASS` is the wrong answer for any project-side asset load. If a future change adds `--add-data` for some asset class, that's a new contract that needs its own helper and its own CONTRACT block.

### Applies To
- All Python modules under project root + `displays/` that load JSON, fonts, images, audio, or any other bundled asset at runtime.
- All future asset directories that get added under `data/` or as new top-level alongside-exe trees.
- The `/build` skill's Step 4 stage-copy commands.

### The Pattern (Use This Every Time)

When adding a module that loads a bundled asset:
1. **Import from `app_paths`.** `from app_paths import project_root` — never invent a local helper.
2. **Resolve via `project_root() / "<dir>" / "<file>"`.** No `Path(__file__)` math, no `sys._MEIPASS`, no `Path(sys.executable).parent` re-implementation.
3. **Fail loud at the load site** if the file is missing (`if not path.exists(): raise FileNotFoundError(...)` with the resolved path + a hint about the build/data fix). Silent no-ops are the worst-case mode.

When adding a new asset directory or file class to `data/`, `fonts/`, `audio/`, or any new alongside-exe tree:
1. **Smoke-test the release build, not just dev.** A new asset class only proves itself in the frozen exe — dev mode reads it through `Path(__file__).parent` which always works.
2. **The default-ship build script** (Step 4 inversion landed 2026-05-05) handles new top-level dirs automatically. New subdirs under `data/`, `fonts/`, `ocr_templates/` ship via the recursive copy. New top-level dirs need no skill edit unless they should be excluded.

When reviewing diffs that touch deployment-frame primitives:
- Verify against primary source (the build script's actual behavior, the library's runtime hook, official docs) — not cached impression. "Leave it alone, semantics are intentional" is a load-bearing claim; confirm before saying it.

### Why This Matters
- **Each individual misclassification was locally defensible.** "_MEIPASS is for bundled assets" sounds right; "data/*.json is what data/ contains" sounds right. Only the deployment-frame view (what does Step 4 actually copy? what does `_MEIPASS` actually contain?) makes the contradiction visible.
- **Dev mode hides every variant.** `Path(__file__).parent` always resolves to project root in dev; `data/line_icons/` is always present in dev. The release exe is the only environment that exercises the divergence.
- **Cached PyInstaller impressions are unreliable.** The ecosystem has multiple bundling mechanisms (`--add-data`, `--collect-data`, `--onefile` extraction, alongside-exe copy via stage script). A reviewer reasoning about "what `_MEIPASS` is for" without checking which mechanism THIS project uses produces wrong classifications.
- **Authoring locality compounds the risk.** Each module's author solved the path-resolution problem in isolation; nobody noticed they were all solving the same problem. The duplication wasn't visible from any single file's view — only cross-codebase grep surfaced the four siblings.
- **Sibling lessons** (2026-04-27, 2026-04-30 above): runtime-required materials must be committed; lazy import ≠ optional dep. Today's incident is the third sibling: **path resolution + shipped-bundle coverage are deployment-frame contracts, not dev-time correctness checks.** All three lessons share the same root: **claude reasons about code as text rather than as a deployed artifact.**

### Concrete fix applied (this incident)
- **`app_paths.py` created** at project root — single canonical `project_root()` helper with PyInstaller-aware branching + terse `# CONTRACT:` block pointing here.
- **5 broken/wrong path-resolvers consolidated**: `displays/utils.py:project_root`, `upper_lcd.py:get_base_dir`, `i18n.py:app_root` collapsed to thin re-exports/aliases of `app_paths.project_root`. `i18n.py:settings_path()` inline duplicate replaced with `project_root()` call. `app.py:_load_station_db` ad-hoc resolver replaced with `project_root()`.
- **3 broken-Path(__file__) sites in auto_input.py + 1 in ocr.py + 1 in plot_drive.py** all routed through `app_paths.project_root()`.
- **`/build` skill Step 4 inverted** from include-list (`Copy-Item "data\*.json"` etc.) to exclude-list (default-ship every top-level dir, maintain `$shipExclude` for what NOT to ship). New asset folders ship automatically; misses are no longer possible by omission.
- **`principles.md`**: two new entries — *"Search before authoring common utility code"* (authoring-time discipline) and *"Verify deployment-frame and external-runtime semantics from primary source"* (review-time discipline).
- **`/vibe-check`**: smell #11 (utility-helper duplication) + smell #12 (deployment-frame primitive outside canonical home) added.
- **`/review-dirty`**: Lens 1 extended with deployment-frame verification check; Lens 2 categories #11 + #12 added with cross-codebase grep pre-flight requirement.

---

## ⚠️ CRITICAL: Single-shot signal flags must be consumed AFTER successful action, not before

**Date:** 2026-05-09

### The Incident
AutoDriver fires the at-station press by setting `sim.pending_next_pa = True` from a background thread. The simulator's main loop reads:

```python
if keyboard.is_pressed("page down") or self.pending_next_pa:
    self.pending_next_pa = False  # ← reset BEFORE the action
    self._next_pa()                # ← may no-op (PA-blocks-PA)
```

`_next_pa()` short-circuits when audio is mid-play (`if self.audio.is_pa_playing(): return`). When AutoDriver fires at-station while the まもなく PA is still playing audio, the flag is reset, `_next_pa` no-ops, and the signal is **lost forever**. By the time audio finishes, no pending flag remains and the detector's `at_station_observed` is already True so it won't re-emit. User overran Yokohama on Tokaido, train physically stopped, LCD stuck on まもなく 横浜 because the at-station press never converted.

Manual press doesn't surface the bug because the held key keeps firing every frame — the press auto-retries until audio clears. Auto-fire is one-shot; one drop is forever.

### The Rule
> **A single-shot signal flag from one source to another (`pending_X = True` → consumer reads → consumer acts) must be consumed only when the action's preconditions are met. Don't reset the flag before checking the consumer's gates — if the action no-ops, the signal is silently dropped.**

The shape: producer sets a one-shot flag; consumer reads it; consumer's action has internal preconditions that may not yet be met. If you reset the flag before checking those preconditions, you've lost the signal. If you reset after a no-op return, same outcome.

### Applies To
- `sim.pending_next_pa` (this incident — fixed in `app.py:_handle_input_real`)
- Any future flag of the same shape (e.g. `pending_next_sta`, `pending_jump`, `pending_resync`).
- More broadly: any background-thread → main-thread signal where the action might decline (mutex held, audio busy, mid-animation, etc.).

### The Pattern (Use This Every Time)

When introducing a one-shot signal flag from a source that won't retry:

1. **Check action preconditions BEFORE consuming the flag.** If preconditions aren't met, leave the flag set; retry next frame.
2. **Reset the flag only on the path where the action actually runs.** Action successfully invoked → reset. Action declined (no-op return, exception) → leave set.
3. **For held-key (multi-shot) inputs**, the standard "reset and call" pattern is fine — the input keeps re-asserting. The pathology only fires for single-shot flags.

**Concrete shape for a similar flag in this codebase:**

```python
# Wrong:
if pending_X or held_input:
    pending_X = False                  # consumed before action
    do_action()                        # may no-op, signal lost

# Right (the fix landed in app.py):
if (pending_X or held_input) and action_preconditions_met():
    pending_X = False
    do_action()
# else: pending_X stays True; held_input self-retries; either way the
# signal is preserved until the next frame where preconditions are met
```

### Why This Matters
- **Silent drop is the worst-case mode.** No console log, no error — the auto-fire just doesn't happen. User sees the LCD stuck on the wrong state with no way to know why.
- **Held-key inputs masked the pathology** for months (manual press worked because of the natural retry). The bug only surfaced when an auto-fire flag interacted with a long-PA gating condition.
- **The fix is one line** at the consumer site (gate the consumption on action preconditions). The ROOT-CAUSE understanding is what protects future flags from the same shape.

### Concrete fix applied (this incident)
- **`app.py:_handle_input_real`**: gate the consumption on `not self.audio.is_pa_playing()`. The held-key path retries naturally; the one-shot pending flag now stays set until audio clears, then runs.
- **JSONL log expanded** (`auto_input.py`): `at_station`, `cnt_pa_at_station`, `at_station_observed` added to per-sample records so the same incident is debuggable from the recording alone next time. Without these fields the original investigation couldn't distinguish "detector didn't fire" from "fire dropped" from "transition silently regressed."

---

## ⚠️ CRITICAL: AST source-edit must iterate values in reverse when multiple keys can share a line

**Date:** 2026-05-14

### The Incident
The calibration editor's `commit_to_source` writeback walks a target dict's AST nodes and replaces each value-side via `line[:col_start] + new_repr + line[end_col:]`. The loop iterated **forward** through `zip(target_node.keys, target_node.values)` — with a comment that explicitly justified this as safe because "each key→value is on its own line in our dicts."

Phase 1b of the calibration editor pivoted the arc-element dict to a multi-key-per-line schema:

```python
"arc_p0_x": 540, "arc_p0_y": 441, "arc_p0_stroke": 70,
"arc_p1_x": 461, "arc_p1_y": 310, "arc_p1_stroke": 70,
...
```

The first Ctrl+S after the schema change wrote back successfully — by coincidence, the user hadn't actually nudged any values yet (focused element, immediately Ctrl+S), so `new_repr == old_repr` for every key. No col-offset shift, no corruption.

The second Ctrl+S, after real tuning, corrupted the source file:

```
"arc_p3_x": 9,   "arc_p3_y":  9992  "arc_p3_stroke": 7055  # furthest-stop end (top)
```

Reading the modified `line` with the original AST col-offsets meant the second-key replacement slice started AFTER the first replacement had already shifted the line's length. The slice ate part of one value and bled into the adjacent key's whitespace and value. Three keys collapsed into two malformed-then-unparsable tokens. Editor crashed on next Ctrl+S because `ast.parse(text)` failed on the corrupted source. User lost their tuning work.

### The Rule
> **When mutating source by AST-walking values in place, process values in REVERSE source order. Then earlier-col values keep their original col-offsets (no edits have happened to their left yet) and replacement remains correct.**

Forward iteration is safe ONLY when each AST value is alone on its line — and that property must be a hard schema invariant, not a happy accident. Multi-key-per-line dicts (alignment-formatted blocks, dense data tables, etc.) make forward iteration unsafe the moment any value's repr length differs from the original.

### Applies To
- All AST-driven source edits where multiple AST values can appear on the same line.
- All future writeback paths in dev tools (calibration editor, future codegen utilities that patch existing source).
- Generalization: any in-place string mutation guided by precomputed offsets must process offsets in DECREASING order, regardless of whether AST is involved.

### The Pattern (Use This Every Time)

```python
# Wrong:
for k_node, v_node in zip(target_node.keys, target_node.values):
    # col_offsets are from the ORIGINAL tree. After the first edit, the
    # line's length changes — subsequent edits on the same line use cols
    # that no longer correspond to the intended values.
    lines[v_node.lineno - 1] = (
        lines[v_node.lineno - 1][: v_node.col_offset]
        + new_repr
        + lines[v_node.lineno - 1][v_node.end_col_offset :]
    )

# Right (the fix landed in calibration_editor._swap_dict_literal):
for k_node, v_node in reversed(list(zip(target_node.keys, target_node.values))):
    # Rightmost edits land first; earlier-col edits then use cols that are
    # still accurate because no edit has happened to their left.
    ...
```

Always-safe alternative when reverse iteration is awkward: sort edits by `(v_lineno, v_col_offset)` descending, apply in that order.

### Why This Matters
- **Silent data corruption is the worst-case mode.** First Ctrl+S after the schema change "worked" because nothing changed. Second one corrupted, and the user only discovered it when the editor crashed on third Ctrl+S — by then the source file was already broken in git.
- **The trap is invisible until the schema invariant breaks.** "One key per line" was a true invariant for the first six elements registered (`dest`, `clock`, `prefix`, `station` upper-LCD entries). The arc element broke the invariant; the comment in the writeback code asserting one-per-line became wrong without any code-side warning.
- **The fix is one keyword** (`reversed(...)`) at the iteration site. Cost ≈ 0. Cost of writing back ad-hoc with col-offsets from a mutated string ≈ user loses minutes of tuning work and a release-pipeline corruption later.
- **Comments that "justify" subtle invariants need to assert + enforce, not narrate.** The original comment said "each key→value is on its own line in our dicts, so per-line replacement is safe regardless of order." When that invariant changed (Phase 1b schema), the comment quietly went stale. The reverse-iteration approach is unconditionally safe regardless of schema; pick the unconditional fix when available.

### Concrete fix applied (this incident)
- **`_dev_scripts/calibration_editor.py:_swap_dict_literal`**: iteration changed to `reversed(list(zip(target_node.keys, target_node.values)))`. Comment rewritten to explain the multi-key-per-line risk and why reverse is unconditionally safe.
- **Source file restored** by hand: `displays/train_models/e235_0/lower_lcd.py` line 75 reconstructed from corruption pattern + eyeballed continuation of the stroke trend. User confirmed values close enough to proceed.

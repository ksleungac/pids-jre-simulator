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

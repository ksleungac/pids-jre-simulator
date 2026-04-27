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
3. **If large (> few MB)** OR derived from larger sources: commit the *derived small artifact*, leave the *source* gitignored. Add an extraction script (`data_tools/extract_<feature>_assets.py` or similar) that regenerates the artifact deterministically from sources. Document the source-folder location + how to recapture it.
4. **Fail loudly** when the artifact is missing at runtime. Not `silently skip`, not `continue with degraded behavior`. Log a `FATAL` with the path expected and the regeneration command, and refuse to start.

### Why This Matters
- **Silent no-op on missing files is the worst-case behavior** — the feature looks like it loaded, then misbehaves at the worst moment (the live drive). A loud FATAL at startup would have caught this in seconds.
- **Naming carries semantics.** "References" / "samples" / "examples" all imply optional / dev-only. Use names that match status: runtime input gets a runtime-input name.
- **Two-part repos are normal** (committed binaries / data files alongside code). The mistake isn't having binary data; it's leaving that data in a "is this dev or runtime?" ambiguous state.

### Concrete fix applied (this incident)
- Source screenshots → `_ocr_calibration/` (gitignored, `_` prefix matches project local-only convention).
- Extracted templates → `ocr_templates/digits/*.png` + `ocr_templates/badges/*.png` (committed, ~50 KB total).
- Extraction script → `data_tools/extract_ocr_assets.py` (one-command regeneration when sources are recaptured).
- AutoDriver now FATAL-exits with a helpful message if templates are missing.

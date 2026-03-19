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

---
name: vibe-check
description: Sanity-scan the production codebase for cruft that piles up after AI-assisted feature work — duplicated logic, dead helpers, half-finished implementations, speculative architecture, stale comments. Discussion-first, item-by-item; smoke-tests every fix.
triggers:
  - /vibe-check
  - vibe check
  - vibe coding
  - sanity scan
  - scan for mess
  - codebase mess
  - cruft scan
---

## Purpose

Multiple AI sessions add features cleanly enough on their own — but each session has a limited view of the whole. Over time the codebase accumulates: duplicated helpers (someone forked `utils.py` instead of editing the original), dead abstractions (a registry/factory created for "the future" that never came), unused imports left from a different prototype, stale comments describing a structure that's been refactored away, two ways to do the same thing within one class.

This skill **finds and triages** that mess. It is intentionally NOT an autofix loop — most "dead code" needs a conversation before deleting, because in this project a meaningful fraction of "looks dead" code is actually **dormant scaffolding** (see `.claude/rules/conventions.md` "Comment dormant scaffolding explicitly") for known future work.

## When to run

- User says "scan for mess", "vibe-coding sanity check", "what's accumulated", "is the codebase getting messy".
- After a stretch of multi-session feature work, before a release, or when the user notices a smell they want investigated systematically.
- NOT for pre-commit cleanup of a single change — use `/review-dirty` for that.

## What this skill is NOT

- Not a general code review (style, naming, micro-optimizations are out of scope — `/review-dirty` covers that).
- Not an autofix loop — every finding gets discussed before any edit.
- Not a delete-all-dead-code pass — distinguishing dead vs dormant matters.

## Process

### Step 1 — Map the in-scope codebase

Build the production surface. Use the project's own boundaries:

| Always in scope | Always out of scope |
|---|---|
| `app.py`, `main.py`, `audio.py`, `constants.py`, `i18n.py`, `font_atlas.py` | `preview_display.py` (testing harness — not shipped, exclude from production reviews) |
| `displays/**/*.py` (all LCD/model code) | `old_version.py` (intentionally preserved pre-refactor monolith — keep, do not propose deleting) |
| `data_loader.py` or any other top-level production module | `compare_*.py`, `validate_*.py` (dev/CI tools) |
| | `_*` folders / files (preserved-but-not-shipped, e.g. `_archive/`, `_mock/`) |
| | Anything under `.claude/`, `memory/`, `data/`, `audio/` (not Python production code) |

Confirm the scope at the top of your report, so the user can correct it.

### Step 2 — Hunt for these specific smells

Each finding must match one of these categories. Do not flag general code style.

1. **Duplicated logic / forked helpers.** The same function defined in two files, or near-identical blocks copy-pasted across classes. Especially: when a helper got "evolved" (added a new parameter, new branch) by forking the file rather than editing in place. The fork = vibe coding signature. **Intention test — required before flagging a duplicated VALUE / FORMULA block (not just whole functions): do the sites describe the SAME thing and must move together, or do they only match textually today?** Read the USAGE at each site, don't diff the text. A value slaved to one physical object is a real dup + desync risk → unify only the shared subset. A formula that merely *coincidentally* matches — because each site derives it for an independent reason, or a sibling copy is documented to potentially DIVERGE later — is NOT a dup; a shared helper there would silently fight the divergence intent. So factor only the values whose intention is genuinely shared and leave the site-local derivations in place. (2026-07-22, #50: three full-route methods re-derived the same four track constants — `cy` / `v_outer` / `border_outer` / `straight_right` were the one drawn track's geometry, so the passed-band clip MUST track it → shared; but `straight_left` was stop-layout earmarked to reclaim the left margin later, and the inner-hole radii were single-method → left local. Unifying the whole block would have been wrong.)
2. **Dead helpers / unreachable code.** Methods defined but never called. **CRITICAL EXCEPTION:** documented dormant scaffolding (multi-line `# NOTE: deliberately NOT called from … yet` block, per project convention) is INTENTIONAL — do not flag.
3. **Half-finished implementations.** Placeholder classes that return early unconditionally, branches that obviously don't do what they claim, methods whose body contradicts the docstring.
4. **Speculative architecture.** Class hierarchies, registries, strategy patterns, or façades where only one concrete option exists and the indirection earns nothing TODAY. Distinguish from dormant scaffolding (which has explicit markers + a known future trigger).
5. **Module-level constants duplicated across files.** Same value defined in two `.py` files instead of one being the canonical source.
6. **Unused imports.** `from x import y` where `y` is never referenced.
7. **Two ways to do the same thing within one class.** Mix of `self._accessor()` and `self.attr` for the same field, mix of two helpers with overlapping responsibility.
8. **Stale comments / docstrings contradicting code.** Comment describes a structure (`mode_displays` dict, "uncomment ENGLISH entry") that doesn't exist in the current file.
9. **Trivial accessors with no derivation.** `def _bar_y(self): return self.bar_y` — added "in case it becomes dynamic later" but never did.
10. **Production code importing from `_*/` paths.** Files at project root + under `displays/` MUST NOT have `from _foo` / `import _foo` / `from _foo.bar` for any `_*/` folder (`_archive/`, `_mock/`, `_dev_scripts/`, `_experiments/`, etc.). Per `conventions.md` § "_*" prefix, those folders are dev-only and not shipped — a production import is a misclassification (either the file should be promoted out of `_*/`, OR the caller is dev-only and shouldn't be at root). **Verification:** for each `_*/` folder at the tree top, grep production code (excluding `_*/` itself) for `from <folder>` or `import <folder>`. **Sibling rule** (Step 1 scope table): `_*/` paths are out of scope for this skill's reviews — but production imports OF them ARE in scope, this category. See `.claude/rules/critical_lessons.md` § "Lazy import ≠ optional dep" for the underlying pathology.
11. **Local utility helper that should live in a shared module.** A small utility function (path resolver, JSON loader, slug parser, format helper, common regex, anything stdlib-only and < 20 lines) lives in a feature module instead of a shared utils home (`app_paths.py`, `displays/utils.py`, `constants.py`, `i18n.py`, package-local `utils.py`). Often duplicates similar helpers in other files. **Trigger heuristics:** function < 20 lines, body uses only stdlib (`pathlib`, `json`, `re`, `sys`, `os`), name like `load_*` / `resolve_*` / `parse_*` / `format_*` / `_*_root` / `_*_path` / `_*_dir`, no domain-specific imports. **Verification:** grep for similar function names cross-codebase. If multiple implementations exist → fires #1 (forked helpers) too. **Fix:** promote to a shared module + import from there. If genuinely single-feature-specific, leave but document with a one-line comment. Per `principles.md` § "Search before authoring common utility code" — authoring locality is the failure mode this catches.
12. **Deployment-frame / runtime-semantics primitive outside canonical home, without verification anchor.** A reference to `sys._MEIPASS`, `sys.frozen`, `sys.executable`, `Path(__file__)` for behavior-dependent paths, branching on `if frozen:` / `if dev:`, OR threading primitives in non-obvious patterns (locks held across yields, queue draining at sentinel times), OR file-I/O timing assumptions (write-then-read, mtime checks) — that lives outside the canonical home (`app_paths.py` for path resolution) AND has no inline `# CONTRACT:` block citing primary source. **Distinct from #11**: #11 catches duplicated *helpers*; #12 catches *code that depends on external behavior* — runtime conditions not visible from reading the file. The 2026-05-05 release-crash incident had four such sites that read as plausible locally but were wrong because the deployment-frame primitive was misapplied. **Verification:** for path resolution, confirm centralization in `app_paths.py`; for threading / I/O, confirm a comment explains the invariant. **Fix:** promote to canonical home OR add CONTRACT block citing primary source (build script for PyInstaller behavior, library hook for runtime quirks, OS docs for OS-specifics). Per `principles.md` § "Verify deployment-frame and external-runtime semantics from primary source" — defending these from memory is the failure mode this catches.
13. **Integration residue — redundant-but-wired screen / branch after a flow integration.** When a flow becomes default or a screen's job moves to a sibling feature, the now-redundant first-run screen or state-gated branch is often left reachable — invisible in dev because it only fires on absent persisted state (a populated `settings.json` masks it). Per `critical_lessons.md §6`. **Verification:** for each first-run / onboarding / OOBE screen, confirm a live entry path AND that no sibling already owns its function. The v0.6.0 language picker survived redundant beside the TIMS home's language knobs for the whole graduation arc. **Distinct from #2** (dead/unreachable) — this code IS still reachable, just no longer *needed*.

### Step 3 — Verify before reporting

Trust-but-verify the agent that does the scanning (or yourself):

- For every "this method is dead" claim, **grep the entire project** to confirm zero callers (including `preview_display.py` and other harnesses — preview's reference counts as live for "is this called").
- For every "these are duplicates" claim, **diff the two definitions** to confirm they're truly equivalent or note exactly where they diverge.
- For every "stale comment" claim, **read the code it references** to confirm the structure really is gone.

Skipping verification = false-positive findings = user loses trust in the report.

### Step 4 — Report

Group by smell category. Each finding: `file_path:line_number` + 1 sentence what + 1 sentence why-it-looks-like-cruft. Cap report under 600 words.

Use a markdown table for the final triage list:

```markdown
| # | Smell | File |
|---|---|---|
| 1 | <one-line description> | `path:line` |
```

End the report with a suggested order to address them (cheapest/safest first, biggest surgery last) and ask which to start with. Do NOT start fixing.

### Step 5 — Discussion 1-by-1

For each item the user picks:

1. **Re-read the code** in current state (don't trust the report's stale snapshot if other edits happened).
2. **Explain the smell concretely** — show the exact lines, what's duplicated/dead/wrong.
3. **Propose a treatment** — usually one of:
   - **Delete** (when truly dead and no future use)
   - **Inline** (trivial accessor / wrapper)
   - **Collapse** (forked helpers → single source)
   - **Mark as dormant scaffolding** (when it's infrastructure for known future work — add the `# NOTE: deliberately NOT called yet` block per `.claude/rules/conventions.md` "Comment dormant scaffolding"; explain *why* no caller today, *when* to wire it in)
   - **Inheritance refactor** (when two classes are clones with intent to diverge — make one inherit, override only what diverges)
   - **Migrate** (when the value belongs in a different home — e.g. per-model constants moving from global `constants.py` to model package `__init__.py`)
4. **Ask before editing** if the treatment is non-trivial (touches >1 file, changes a public signature, or the user's intent is ambiguous). For pure cleanups (drop unused import, delete dead trivial accessor), proceed and report.
5. **Smoke test** after every code change (see Step 6).

### Step 6 — Smoke test after each fix

This project has a screenshot-mode preview. After EVERY code edit, run:

```bash
uv run preview_display.py --screenshot smoke_post<N>.png --route sobu/1217F --stop 5 --mode kanji
```

Vary `--mode {kanji|furigana|english}`, `--lower-view {full|eight|cycle}`, `--stop N` to exercise the area you touched. For UI changes, **read the screenshot back** with the `Read` tool and visually confirm the layout matches expectations. Hash comparison alone is misleading — the upper LCD shows the live `HH:MM` clock, so hashes always differ between runs even when rendering is identical.

If the smoke test fails or looks wrong, stop and investigate before moving to the next item.

### Step 7 — Wrap

After the user calls "done" (or skips remaining items):

- Print a session summary: items cleaned, items marked as dormant scaffolding, items skipped, list of files touched.
- Note any smoke-test artifacts (`smoke_*.png`) in the repo root and remind the user to delete when ready (the user reviews them — don't auto-clean; same rationale as the `/visual-adjust` "never delete the latest iteration's screenshot" rule).
- Do NOT auto-commit. The user runs `/commit` themselves when ready (the project's `PreToolUse` hook on `Bash(git commit:*)` enforces this — direct commits are denied).
- Suggest `/session-recap` if the cleanup was substantial.

## Things that are NOT vibe-coding mess

Recognize these patterns and don't flag them:

- **Dead features the user knows about.** Sometimes a feature was built, decided against, and its code lingers (e.g. `PASimulator.small_size` in this project — small-window mode that never shipped). The user typically knows about these and considers them "normal dead code from development, not vibe coding." If you suspect a finding is a known-dead feature, ASK before flagging — don't waste a report slot.
- **Documented dormant scaffolding.** Multi-line `# NOTE: deliberately NOT called from … yet` markers explicitly signal "this is reserved for future X." Per `conventions.md` "Comment dormant scaffolding explicitly" — these are intentional, leave them alone.
- **Forward-looking architecture with explicit triggers.** Even without a `# NOTE:` block, infrastructure that has a clear known-future-trigger (e.g. multi-model registry waiting for a 2nd train model) may be intentional. Propose adding a dormant marker rather than deleting.
- **Two-class structures kept for divergence intent.** If two classes have identical bodies today but the user's design intent is "they will diverge later" — propose **inheritance** (subclass with no overrides) rather than collapse, so the override path stays open without the duplication tax.
- **Per-domain duplications that respect architecture.** Duplicate logic across two domain modules (e.g. `JapaneseDisplay` and `JapaneseEightStationDisplay` both walking station times) may be deliberate if the two views have meaningfully different needs. Propose extraction, but don't force it if the user pushes back.

## Gotchas encountered in practice

- **The user has parallel WIP across PCs.** Per `principles.md` "2 different PCs", they work from 2 PCs. Mid-session they may say "stop touching X, I have WIP on it." Drop that item without resistance — never argue, never delete the in-progress work.
- **`small_size`-style dead features** are normal. The user's distinction: vibe-coding mess = unnecessary forks/abstractions/duplications introduced during feature work; dead-feature code = intentional development byproduct. ASK if unsure.
- **Smoke tests need visual confirmation, not just hash equality.** The clock changes every minute → hashes always differ. For layout-affecting changes, `Read` the screenshot and eyeball it.
- **Per-model boundaries.** When deduplicating constants/helpers across `displays/train_models/{model}/` modules, respect that future train models may need their own. Per `conventions.md` "constants.py is for cross-module values only", per-model values belong in the model's package, NOT in top-level `constants.py`. Migrating constants from `constants.py` → per-model `__init__.py` is often the right direction.
- **Don't autofix unused imports without scanning callers.** `from x import draw_text` may look unused in the current file but might be re-exported via `__all__` or referenced via `from module import *`. Grep the project before deleting.
- **Façades may have a published-API contract.** A `displays/__init__.py` that re-exports `DisplayMode` etc. may be the intended public surface even if no in-tree caller uses it yet. Treat as potential dormant scaffolding — propose marker, not delete.

## Why this matters

Each individual feature delivery looks fine. The mess is invisible until it accumulates: future agents struggle to navigate, refactors break in surprising places (because two copies of a helper drift), reviewers can't tell what's load-bearing vs scaffolding. A periodic vibe-check keeps the codebase honest about which abstractions earn their keep TODAY vs which are reserved for tomorrow.

## Scope

- **Does** scan production code for the 13 specific smell categories.
- **Does** verify findings via grep before reporting.
- **Does** propose treatments item-by-item, ask before non-trivial edits, smoke-test after every fix.
- **Does not** autofix without discussion.
- **Does not** delete code the user identifies as known-dead-feature or dormant scaffolding.
- **Does not** touch areas the user has flagged as having parallel WIP.
- **Does not** auto-commit (user runs `/commit` themselves).

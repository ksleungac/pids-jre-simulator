# Conventions — naming, style, tooling

Project-local style and naming choices. These don't shape major decisions; they keep code consistent. Each entry is short — "X uses Y" or "don't do Z."

## Naming

- **Use "sta" terminology** (not "departure_melody" or similar). Audio files, JSON fields, skill names, doc text — all use `sta`.
- **Folder structure carries metadata.** Diagram is extracted from `audio/<line>/<diagram>/` (e.g., `nambu/4027F/`). Don't flatten or rename.
- **`_*` prefix = preserved-but-not-shipped staging.** Examples: `audio/_archive/` (recordings the active diagram doesn't use, kept for future glob lookup), `audio/_mock/` (preview/test fixtures), `_experiments/` (WIP not yet ready for project root), `_<feature>_calibration/` (gitignored source material that derives committed artifacts). Treatment by tools: `release.ps1` classifies `audio/_*/` + `data/_*` as harness (not shipped); `/vibe-check` excludes code under `_*/` from production reviews. Promote out of the prefix (e.g. `_experiments/ocr.py` → `ocr.py` at project root) when the artifact is ready to ship — that promotion is itself the signal "this is now part of the surface."

## Data layout

- **Centralized translations**: single `data/translations.json` for all lines, not per-line files.
- **`constants.py` is for cross-module values only.** Per-LCD-module sizes / positions / fonts live inline in that LCD module (in tuneable-params blocks or `__init__`). Each LCD type has its own module and may pick its own sizes; sharing across modules would force false uniformity. Only add to `constants.py` if a value is genuinely consumed by ≥ 2 modules (e.g., `STOPS_WIDTH` shared by future per-train lower displays, `TIME_SCALE` shared by app + display).

## Tooling

- **Black formatting via pre-commit hook** (`.venv/Scripts/python -m black`). Don't run Black manually unless the hook isn't firing.
- **`.otf` fonts only.** `.ttf` cuts (Helvetica Neue specifically) have macron/diacritic artifacts at large sizes. The `fonts/` folder should never gain a `.ttf`.
- **`old_version.py`** — keep. Intentionally retained as the pre-refactor monolithic reference even though nothing imports it. Don't propose deleting it during tidy passes.

## UI code style

- **Tuneable-params block.** Every UI draw method must expose its magic numbers (positions, sizes, offsets, gaps) as labeled local variables at the top of the method. All downstream coordinates derive from those. No scattered magic numbers. Rationale: the user fine-tunes visuals by nudging these values — they must be discoverable AND reactive (changing `badge_w` should recompute interior width, centering, text positions automatically).
- **Comment dormant scaffolding explicitly.** When a helper is defined but intentionally uncalled (e.g. `JapaneseEightStationDisplay._draw_continuation_marker`, deferred until a related buggy helper is reviewed), put a multi-line `# NOTE: deliberately NOT called from … yet` block above it explaining *why*, *when to wire it in*, and *what's reserved for it*. Without that signal, every reviewer-pass re-flags it as dead code.

## Contract Pointers in Code

When a function or class has a non-obvious contract that lives in a doc (`DISPLAY.md`, `DATA_FORMAT.md`, etc.) — and getting it wrong has caused or *clearly could cause* regressions — anchor a pointer in the code itself, at the top of the class or function body.

**Why.** "Read the doc first" instructions get bypassed when an agent has *partial* context that feels sufficient (real failure: an agent skipping `DISPLAY.md` for a lower-LCD bugfix because some preloaded content seemed to cover it). An in-code pointer is unavoidable — anyone editing the code reads the file first, so the pointer lands in their context at the moment of decision. Skipping it requires deliberate dismissal, not omission.

**Format** (terse, ~3 lines):

```python
# CONTRACT: <one-line summary>.
# See <DOC.md> § "<exact section heading>".
# <one-line context: what breaks if you skip the doc>.
```

**Bar for adding one** — non-obvious AND would clearly bite:
- ✅ Window invariants, mode-cycler timing rules, skip-animation state contracts, clear-bg confinements, "must be called unconditionally before X" ordering rules, recurring-review-false-positive sites.
- ❌ Routine functions whose behavior is obvious from the code itself, or where the contract is local and self-documenting.

**Don't substitute for the doc.** The pointer summarizes; the doc has the actual contract. Update the doc when the contract changes; keep the inline comment terse.

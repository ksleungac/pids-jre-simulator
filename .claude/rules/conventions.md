# Conventions — naming, style, tooling

Project-local style and naming choices. These don't shape major decisions; they keep code consistent. Each entry is short — "X uses Y" or "don't do Z."

## Naming

- **Use "sta" terminology** (not "departure_melody" or similar). Audio files, JSON fields, skill names, doc text — all use `sta`.
- **Folder structure carries metadata.** Diagram is extracted from `audio/<line>/<diagram>/` (e.g., `nambu/4027F/`). Don't flatten or rename.
- **`_*` prefix = preserved-but-not-shipped staging.** Examples: `audio/_archive/` (recordings the active diagram doesn't use, kept for future glob lookup), `audio/_mock/` (preview/test fixtures), `_dev_scripts/` (middlescript: audio splitters/validators, OCR-asset extractor, drive-recorder CLI, dxcam diagnostic), `_experiments/` (WIP not yet ready for project root), `_<feature>_calibration/` (gitignored source material that derives committed artifacts).
  - **Hard rule:** production code (project root + `displays/`) MUST NOT import from `_*/` paths. The presence of a production import is itself the signal that the file has graduated — promote it out (e.g. `_experiments/ocr.py` → `ocr.py` at project root, or `_dev_scripts/plot_drive.py` → `plot_drive.py` after the 2026-04-30 incident). Folder placement carries dep-classification semantics — see [critical_lessons.md § "Lazy import ≠ optional dep"](critical_lessons.md) for the full pathology.
  - **Treatment by tools:** `release.ps1` classifies `audio/_*/` + `data/_*` as harness (not shipped); `/vibe-check` excludes code under `_*/` from production-scope reviews (Step 1) AND flags production imports of `_*/` as smell #10 (Step 2).

## Data layout

- **Centralized translations**: single `data/translations.json` for all lines, not per-line files.
- **`constants.py` is for cross-module values only.** Per-LCD-module sizes / positions / fonts live inline in that LCD module (in tuneable-params blocks or `__init__`). Each LCD type has its own module and may pick its own sizes; sharing across modules would force false uniformity. Only add to `constants.py` if a value is genuinely consumed by ≥ 2 modules (e.g., `STOPS_WIDTH` shared by future per-train lower displays, `TIME_SCALE` shared by app + display).

## Tooling

- **Pre-commit hooks: Black + primitive bans.** `.pre-commit-config.yaml` wires two hooks: Black (formatter, version-pinned to match `pyproject.toml`) and `_dev_scripts/lint_primitives.py` (regex-grep for `pygame.font.SysFont`, `Path(__file__).parent`, `sys._MEIPASS`, `sys.frozen` outside `app_paths.py`). Run `pre-commit install` once per clone — installs `.git/hooks/pre-commit`. Don't run Black manually unless the hook isn't firing. Format-skip blocks wrap in `# fmt: off` / `# fmt: on` per UI code style.
- **`.otf` fonts only.** `.ttf` cuts (Helvetica Neue specifically) have macron/diacritic artifacts at large sizes. The `fonts/` folder should never gain a `.ttf`.
- **Never `pygame.font.SysFont()` in production code.** Crashes on Chinese-locale Windows (`TypeError: expected str, bytes or os.PathLike object, not int`) because SysFont scans the Windows font registry, which fails on non-EN locales — original 2026-03-14 incident, recurred 2026-05-07 after the i18n chrome refactor regressed it. All chrome + LCD fonts load via `pygame.font.Font(str(project_root() / "fonts" / fname), ...)`. Enforcement points: CONTRACT blocks at `displays/train_models/*/upper_lcd.py`, comment block + `_LANG_CHROME_FONT` mapping in `i18n.py`. Calibration tools (`compare_fonts.py`, `compare_grid.py`) and `_dev_scripts/` may keep SysFont — they don't ship.
- **All bundled-asset path resolution via `app_paths.project_root()`.** Never `Path(__file__).parent`, never `sys._MEIPASS`, never inline `if sys.frozen:` branching, never a new local `app_root()` / `get_base_dir()` / `_project_root()` helper. The 2026-05-05 release shipped four separate crashes from authoring locality (each module's author solved the path-resolution problem in isolation, one with the wrong PyInstaller semantic). See [critical_lessons.md § "PyInstaller deployment-frame divergence"](critical_lessons.md). `_MEIPASS` is reserved for plotly's library bundle (`--collect-data plotly`), never project assets. Calibration tools and `_dev_scripts/` are exempt — they don't ship.
- **`old_version.py`** — keep. Intentionally retained as the pre-refactor monolithic reference even though nothing imports it. Don't propose deleting it during tidy passes.

## Display module structure

- **Shared display logic uses parent + per-model concrete.** When a display module has logic shared across train models, factor a parent into `displays/<module>.py` + a per-model concrete subclass into `displays/train_models/{model}/<module>.py` — real inheritance from day one even with one concrete model. Per-model tuneables (canvas sizes, fonts) stay in the concrete (per [Data layout](#data-layout)); only shared logic moves up. Counter-example: `UpperDisplay` / `LowerDisplay` are concrete-only because their bodies are entirely per-model rendering. First instance: `displays/transfer_info.py` (parent) + `displays/train_models/e235_1000/transfer_info.py` (concrete).
- **Forking a sibling-model renderer: copy primitives, don't reinvent.** When intentionally duplicating a per-model renderer for a new sub-series (e.g. `e235_0/` forked from `e235_1000/` for the Yamanote re-skin), copy the existing primitive functions (pentagon draw, dot draw, chevron geometry, time-circle, etc.) verbatim into the new module — even when "I could write that in 5 lines myself" feels true. Visual-fidelity primitives encode pixel-tuned constants from prior iteration rounds (e.g. `_draw_pentagon`'s asymmetric `rect_half_w_back=21, rect_half_w_apex=20`); rolling your own loses that calibration silently and the user has to re-iterate from scratch. Distinct from "Search before authoring common utility code" in [principles.md](principles.md) — that's about cross-cutting utilities; this is about intentional per-model duplication where copy is correct.
- **WIP-doc → canonical-doc graduation.** Speculative or in-flight feature work lives in a `WIP_<topic>.md` doc with its own EDIT-CONTRACT (holds: pending designs, transitional diffs, calibration insights). When the feature stabilizes, the WIP doc dissolves into its canonical home and is deleted. Two precedents: `WIP_transfer_display.md` → `DISPLAY.md` (2026-05-05, when `render_transfer` promoted to production) and `WIP_E235_DISPLAYS.md` → new `DISPLAY_E235.md` (2026-05-07, when E235-0 lower-LCD circular renderer shipped). Trigger to graduate is named in the WIP doc itself; absorbing it into the canonical home is a single-commit restructure (no parallel-existence period).

## UI code style

- **Tuneable-params block.** Every UI draw method must expose its magic numbers (positions, sizes, offsets, gaps) as labeled local variables at the top of the method. All downstream coordinates derive from those. No scattered magic numbers. Rationale: the user fine-tunes visuals by nudging these values — they must be discoverable AND reactive (changing `badge_w` should recompute interior width, centering, text positions automatically). **Wrap the block in `# fmt: off` / `# fmt: on`** so Black preserves trailing-comment column alignment — the alignment is what makes the block scannable. Same wrapper applies to other alignment-critical sites: aligned dict-of-tuples (`_LANG_CHROME_FONT`-style), hex-range tables (CJK detection ranges), color-palette constant clusters. **Markers must be exact** — `# fmt: off` / `# fmt: on` only; trailing text on the directive line (e.g. `# fmt: off — preserve alignment`) is treated as a regular comment and Black formats through it.
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

## Domain vocabulary bindings

Some domain docs (`AUTO_INPUT.md`, `DISPLAY.md`) define canonical names + notation for non-obvious concepts. Discussions, design docs, and code edits about those domains MUST use the canonical forms — even when not editing the doc itself. The doc holds the canonical content; this section holds the binding rule that fires regardless of whether claude opened the doc.

- **AutoDriver state vocabulary.** Use the Layer 1/2/3 names defined in [AUTO_INPUT.md](../../AUTO_INPUT.md):
  - **Layer 1 (app sub-states):** `STOPPING` / `APPROACHING_EARLY` / `APPROACHING_FINAL`
  - **Layer 2 (OCR badge reads):** `STOPPED` / `MOVING` / `PASSING` / `UNKNOWN`
  - **Layer 3 (inferred game state):** `STOPPING_FRESH` / `STOPPING_AFTER_ARR` / `APPROACHING_BEFORE_DEP` / `APPROACHING_AFTER_DEP` / `MOVING_AFTER_ARR` / `UNKNOWN`

  **Notation:** prefer arrow flow (`prev → curr`) over tables when describing transitions. Tables only when ≥3 dimensions matter at once.

  **Don't redesign the state machine** without an explicit "I want to change this" framing. The taxonomy was settled across multiple sessions; ad-hoc renaming or layer-merging in chat causes doc-vs-discussion drift.

  **Why:** even with the canonical names defined in `AUTO_INPUT.md`, claude has reverted to ad-hoc vocabulary in chat and code reviews ("the badge says X", "stopped state") — surfacing as the 2026-04-29 evening Layer 3 refactor incident, where doc led code by 24h until user noticed. Canonical content alone (in a domain doc) is read-on-demand and doesn't fire when the doc isn't opened. The binding lives here so it's preloaded into every session.

  **How to apply:** any conversation, design discussion, code review, doc edit, or commit message that touches autodriver / OCR / state-machine reasoning — use the canonical names; use arrows for transitions; flag any proposed redesign explicitly.

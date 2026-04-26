# Working Preferences

## Collaboration Style
- **Discussion-first approach**: Present findings/learnings before making documentation updates
- User reviews and confirms understanding before changes are committed
- **No auto-commit**: Never commit during session-recap or other tasks unless explicitly asked
- **Discussion-first for data work specifically**: When splitting audio, importing route data, or adding any batch of files — present the parse + flag uncertainties + ask before generating splitter scripts or touching route.json. Format variance between sources is common and surprises are normal; don't assume "the format" exists.

## Data Modeling Philosophy
- **Pragmatic over perfect**: Don't build elaborate schemas/sidecars/DBs upfront. Ship route data with whatever metadata surfaces naturally; add structure when actual pain forces it. Quoting the user: "we don't need to build up a perfect schema or system by today, i just don't want information byproduct to get wasted when i needed."
- **Filename-as-store** is preferred to JSON sidecars for content that's genuinely 1:1 with a file (e.g., STA recordings carry station + platform + song id in their basename). Keeps the operational config minimal and makes re-use queryable via `ls *_<song>.mp3`. Add a metadata file only when the filename can't carry enough info, OR when the same fact needs to be looked up from multiple file basenames.
- **Variants are out of scope for now**: Pitch shifts, station-specific arrangements, closing-door-announcement differences across platforms (different staff voices, phrasing) — explicitly deferred. Each recording gets its own slug; merging into "the same song with variants" is a future problem.

## Tooling Workflow
- **Per-source ad-hoc scripts**, not maintained libraries: when format varies between batches (e.g., audio splitting where one source uses 3-timestamp format and another uses 2-timestamp), generate a fresh script per source. Don't try to unify into one master tool. Quoting the user: "the idea is to not have fixed script, my format is variable."
- **Backup before any in-place destructive modification.** Before running tools that re-encode / overwrite / delete files in place (e.g. `trim_sta_silence.py`, manual `ffmpeg -filter_complex` splices, route.json multi-value patches), snapshot the target into `audio_src/<line>/<diagram>/` (gitignored) first. Mention the safety net in the pre-flight summary so the user knows the rollback path exists. Delete backups only after the by-ear / smoke-test gate passes. Pure relocations (`mv` to `_archive/`) don't need a separate backup — the move itself is reversible.

## Naming Conventions
- Use "sta" terminology (not "departure_melody" or similar)
- Folder structure matters - diagram extracted from folder name (e.g., `nambu/4027F/`)

## Working Style
- User tests thoroughly - verify changes work before presenting
- Prefer centralized data: single `data/translations.json` for all lines (not per-line)

## Tooling
- Black formatting via pre-commit hook (`.venv/Scripts/python -m black`)
- **`.otf` fonts only** — `.ttf` cuts (Helvetica Neue specifically) have macron/diacritic artifacts at large sizes. The `fonts/` folder should never gain a `.ttf`.
- **`old_version.py`** — keep. Intentionally retained as the pre-refactor monolithic reference even though nothing imports it. Don't propose deleting it during tidy passes.

## Environment
- User works from **2 different PCs** on this project. Avoid hardcoded absolute paths in skills, docs, or notes — rely on pwd-relative commands.

## UI Layout Work
- **Tuneable-params block**: Every UI draw method must expose its magic numbers (positions, sizes, offsets, gaps) as labeled local variables at the top of the method. All downstream coordinates derive from those. No scattered magic numbers. Rationale: the user fine-tunes visuals by nudging these values — they must be discoverable AND reactive (changing `badge_w` should recompute interior width, centering, text positions automatically).
- **Reference-image driven**: Layout iteration uses reference photos as ground truth. Use `/visual-adjust` for this work. Reference images go in `real/` (older work) or `lcd_references/` (font hunt + new work); screenshots during iteration go in project root (prefix `screenshot_`) and should be cleaned up once the user approves. `compare_fonts.py` / `compare_grid.py` build height-aligned side-by-side composites for direct visual comparison — keep them.
- **Never delete the latest iteration's screenshot.** The user reviews each frame after the assistant turn ends — they need it on disk to open. Only clean up *older* `screenshot_v*` files once a *newer* one for the same scenario exists. Pattern: `rm screenshot_v<N-1>_*.png` immediately before saving `screenshot_v<N>_...`. Never end a turn with no recent screenshot present.
- **Loose iteration language**: when the user says "half" or "5–10 px more", treat it as approximate — verify with screenshots, don't over-fit to the literal number.
- **Iterate autonomously through visual imperfection**: when a clear visual issue is still present after a fix (split shapes, mismatched tip slopes, off-center elements), keep iterating without pausing to ask after each micro-change. User's words: "iterate few more version before stopping for this clear visual imperfection." Pattern: change → screenshot → compare against reference → adjust again. Present at a stable visual checkpoint, not after every nudge.
- **`constants.py` is for cross-module values only.** Per-LCD-module sizes / positions / fonts live inline in that LCD module (in tuneable-params blocks or `__init__`). Each LCD type has its own module and may pick its own sizes; sharing across modules would force false uniformity. Only add to `constants.py` if a value is genuinely consumed by ≥ 2 modules (e.g., `STOPS_WIDTH` shared by future per-train lower displays, `TIME_SCALE` shared by app + display).
- **Comment dormant scaffolding explicitly**: when a helper is defined but intentionally uncalled (e.g. `JapaneseEightStationDisplay._draw_continuation_marker`, deferred until a related buggy helper is reviewed), put a multi-line `# NOTE: deliberately NOT called from … yet` block above it explaining *why*, *when to wire it in*, and *what's reserved for it*. Without that signal, every reviewer-pass re-flags it as dead code.

## Code Review Scope
- **Exclude testing harnesses from production reviews**: `preview_display.py` is a testing tool (not shipped). When invoking `/review-dirty` or `/review+fix` for feature work, mark it out of scope in the prompt.

## Documentation Hygiene
- **`notes.md` is NOT the kitchen sink.** Before adding any new doc content during a session — not just at `/session-recap` time — consult the placement table in [.claude/skills/session-recap/SKILL.md](../skills/session-recap/SKILL.md) and pick the narrowest-domain home. Mental-model framing (project IS, IRL conventions, scope policy) → `CLAUDE.md`. Display gotcha → `DISPLAY.md`. JSON shape → `DATA_FORMAT.md`. Build/distribution → `/build` skill. Cross-cutting code pattern (font loading, PyInstaller, preview mode) → `notes.md`. When in doubt, ask before writing.
- **Preloaded mental model vs progressive implementation detail.** Things humans keep in their head when working on this project (what it models, scope, IRL framing) belong in `CLAUDE.md` so they're always loaded. Implementation details that only matter when actively editing a submodule (draw-method gotchas, JSON-field minutiae) belong in domain docs and get read on demand. The slim-CLAUDE rule applies to *implementation*, not framing.
- **Single source of truth.** Don't duplicate the same fact across docs. Cross-reference instead — e.g., `DATA_FORMAT.md` says "see CLAUDE.md § Mental Model for the convention itself" rather than re-explaining it.

## Contract Pointers in Code
When a function or class has a non-obvious contract that lives in a doc (`DISPLAY.md`, `DATA_FORMAT.md`, etc.) — and getting it wrong has caused or *clearly could cause* regressions — anchor a pointer in the code itself, at the top of the class or function body.

**Why.** "Read the doc first" instructions in `CLAUDE.md` / skills get bypassed when an agent already has *partial* context that feels sufficient (real failure mode: an agent skipping `DISPLAY.md` for a lower-LCD bugfix because `notes.md` was preloaded). An in-code pointer is unavoidable — anyone editing the code reads the file first, so the pointer lands in their context at the moment of decision. Skipping it requires deliberate dismissal, not omission.

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

---

## Project Reference

**Cross-cutting code patterns:** [.claude/rules/notes.md](notes.md) — font loading, PyInstaller, preview mode, countdown system. (Domain-specific gotchas live in their domain doc — see Documentation Hygiene above.)

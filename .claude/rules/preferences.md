# Working Preferences

## Collaboration Style
- **Discussion-first approach**: Present findings/learnings before making documentation updates
- User reviews and confirms understanding before changes are committed
- **No auto-commit**: Never commit during session-recap or other tasks unless explicitly asked
- **Discussion-first for data work specifically**: When splitting audio, importing route data, or adding any batch of files — present the parse + flag uncertainties + ask before generating splitter scripts or touching route.json. Format variance between sources is common and surprises are normal; don't assume "the format" exists.

## Data Modeling Philosophy
- **Pragmatic over perfect**: Don't build elaborate schemas/sidecars/DBs upfront. Ship route data with whatever metadata surfaces naturally; add structure when actual pain forces it. Quoting the user: "we don't need to build up a perfect schema or system by today, i just don't want information byproduct to get wasted when i needed."
- **Filename-as-store** is preferred to JSON sidecars for content that's genuinely 1:1 with a file (e.g., STA recordings carry station + platform + song id in their basename). Keeps the operational config minimal and makes re-use queryable via `ls *_<song>.mp3`. Add a metadata file only when the filename can't carry enough info, OR when the same fact needs to be looked up from multiple file basenames.
- **Variants are out of scope for now**: Pitch shifts, station-specific arrangements, door-chime differences across platforms — explicitly deferred. Each recording gets its own slug; merging into "the same song with variants" is a future problem.

## Tooling Workflow
- **Per-source ad-hoc scripts**, not maintained libraries: when format varies between batches (e.g., audio splitting where one source uses 3-timestamp format and another uses 2-timestamp), generate a fresh script per source. Don't try to unify into one master tool. Quoting the user: "the idea is to not have fixed script, my format is variable."

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
- **`constants.py` is for cross-module values only.** Per-LCD-module sizes / positions / fonts live inline in that LCD module (in tuneable-params blocks or `__init__`). Each LCD type has its own module and may pick its own sizes; sharing across modules would force false uniformity. Only add to `constants.py` if a value is genuinely consumed by ≥ 2 modules (e.g., `STOPS_WIDTH` shared by future per-train lower displays, `TIME_SCALE` shared by app + display).

## Code Review Scope
- **Exclude testing harnesses from production reviews**: `preview_display.py` is a testing tool (not shipped). When invoking `/review-dirty` or `/review+fix` for feature work, mark it out of scope in the prompt.

---

## Project Reference

**Implementation notes:** `notes.md` - Critical patterns, edge cases, validation rules, architecture details

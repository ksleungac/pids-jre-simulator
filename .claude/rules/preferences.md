# Working Preferences

## Collaboration Style
- **Discussion-first approach**: Present findings/learnings before making documentation updates
- User reviews and confirms understanding before changes are committed
- **No auto-commit**: Never commit during session-recap or other tasks unless explicitly asked

## Naming Conventions
- Use "sta" terminology (not "departure_melody" or similar)
- Folder structure matters - diagram extracted from folder name (e.g., `nanbu/4027F/`)

## Working Style
- User tests thoroughly - verify changes work before presenting
- Prefer centralized data: single `data/translations.json` for all lines (not per-line)

## Tooling
- Black formatting via pre-commit hook (`.venv/Scripts/python -m black`)

## UI Layout Work
- **Tuneable-params block**: Every UI draw method must expose its magic numbers (positions, sizes, offsets, gaps) as labeled local variables at the top of the method. All downstream coordinates derive from those. No scattered magic numbers. Rationale: the user fine-tunes visuals by nudging these values — they must be discoverable AND reactive (changing `badge_w` should recompute interior width, centering, text positions automatically).
- **Reference-image driven**: Layout iteration uses `real/` folder photos as ground truth. Use `/visual-adjust` for this work. Reference images go in `real/`, screenshots during iteration go in project root (prefix `screenshot_`) and should be cleaned up once the user approves.

## Code Review Scope
- **Exclude testing harnesses from production reviews**: `preview_upper_lcd.py` is a testing tool (not shipped). When invoking `/review-dirty` or `/review+fix` for feature work, mark it out of scope in the prompt.

---

## Project Reference

**Implementation notes:** `notes.md` - Critical patterns, edge cases, validation rules, architecture details

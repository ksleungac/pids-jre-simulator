# Working Preferences

## Collaboration Style
- **Discussion-first approach**: Present findings/learnings before making documentation updates
- User reviews and confirms understanding before changes are committed

## Naming Conventions
- Use "sta" terminology (not "departure_melody" or similar)
- Folder structure matters - diagram extracted from folder name (e.g., `nanbu/4027F/`)

## Working Style
- User tests thoroughly - verify changes work before presenting
- Prefer centralized data: single `data/translations.json` for all lines (not per-line)

## Tooling
- Black formatting via pre-commit hook (`.venv/Scripts/python -m black`)

---

## Project Reference

**Implementation notes:** `notes.md` - Critical patterns, edge cases, validation rules, architecture details

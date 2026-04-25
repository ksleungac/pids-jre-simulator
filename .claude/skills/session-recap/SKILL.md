---
name: session-recap
description: End-of-session recap to capture learnings, preferences, and update documentation
triggers:
  - /session-recap
  - session recap
  - recap session
  - update docs
---

## Purpose

At the end of a coding session, capture not just *what* changed, but *why* - including:
- New understandings about the codebase
- User preferences discovered during the session
- Behavioral patterns that should be documented
- Data format conventions established

## Process

### Step 1: Review Session Changes

First, scan what was modified:
- Check git diff for changed files
- Identify code logic changes vs. documentation changes
- Note any new constants, functions, or data entries added

### Step 2: Discuss Learnings (CRITICAL)

Before updating any documentation, present a summary:

```
## Session Learnings Summary

### Code Changes
- [List key files/functions modified]

### New Understandings
- [What behavioral patterns were discovered?]
- [What "why" decisions were made, not just "what"?]

### Preferences Learned
- [User preferences about code style, architecture, etc.]
- [Project conventions established or reinforced]

### Documentation Updates Needed
- CLAUDE.md: [sections to update]
- DATA_FORMAT.md: [sections to update]
```

### Step 3: User Review

Wait for the user to:
- Confirm the learnings are accurate
- Add context or nuance you may have missed
- Suggest additional items to document
- Correct any misunderstandings

### Step 4: Update Documentation

After user approval, update the appropriate files. **Each piece of information has ONE home — never duplicate across files.**

#### Where things live (single source of truth)

| What | Where | NOT in |
|------|-------|--------|
| Project overview, file structure, module table, key features, commands | `CLAUDE.md` | rules files |
| Implementation patterns, code gotchas, edge cases, data validation | `.claude/rules/notes.md` | CLAUDE.md |
| User preferences, collaboration style, naming conventions | `.claude/rules/preferences.md` | CLAUDE.md, MEMORY.md |
| Red lines, hard boundaries | `.claude/rules/redlines.md` | CLAUDE.md, MEMORY.md |
| Lessons from past mistakes | `.claude/rules/critical_lessons.md` | anywhere else |
| Build/distribution details, folder structure | `.claude/skills/build/SKILL.md` | CLAUDE.md, notes.md |
| JSON field definitions, data format conventions | `DATA_FORMAT.md` | CLAUDE.md |
| Upper LCD architecture, conventions, gotchas | `UPPER_DISPLAY_UPDATE.md` | CLAUDE.md, notes.md |
| Lower LCD architecture, conventions, gotchas | `LOWER_DISPLAY_UPDATE.md` | CLAUDE.md, notes.md |
| Daily session logs | `memory/YYYY-MM-DD.md` | — |
| Long-term memory index (pointers only) | `memory/MEMORY.md` | — |

#### Rules for updating

1. **Before writing, check if the info already exists** somewhere. Update in place, don't add a second copy.
2. **CLAUDE.md stays slim** — it's a quick-reference entry point with pointers, not a knowledge dump. Only add to it if the info doesn't fit in any rules/skills file.
3. **Cross-reference, don't copy** — e.g., CLAUDE.md says "See `/build` skill" rather than repeating the folder tree.
4. **MEMORY.md is an index** — one-line pointers to memory files. No content, no rules, no preferences.
5. **When in doubt about placement**: implementation detail → `notes.md`, preference → `preferences.md`, build/release → `build/SKILL.md`.
6. **Don't bloat one md.** If `notes.md` (or any single doc) is already large, distribute new content to its narrower-domain home: upper-LCD topic → `UPPER_DISPLAY_UPDATE.md`, lower-LCD topic → `LOWER_DISPLAY_UPDATE.md`, etc. `notes.md` is for cross-cutting patterns; display-specific quirks (rendering gotchas, draw-method subtleties, font metrics) belong with the display doc that already discusses those code paths. Reviewer false positives that recur within a specific module → that module's display doc, not a generic "review notes" pile.

---

## Important Notes

1. **Don't auto-update** - Always discuss learnings first. The user's context matters more than code archaeology.

2. **Capture "why" not just "what"** - Code changes show what was modified, but the conversation reveals why it was done that way.

3. **Preferences matter** - If the user expressed a preference (e.g., "hard-coding is fine", "don't over-engineer"), note it for future sessions.

4. **Be specific** - Instead of "fixed display bug", write "Destination always displays as kanji (no furigana cycling) to match IRL behavior".

5. **No duplication** - If you find yourself writing the same fact in two places, stop and pick the one canonical home from the table above.

---

## Example Output

After a session fixing the Yamanote line destination display:

```
## Session Learnings Summary

### Code Changes
- displays/train_models/e235_1000/upper_lcd.py: _get_current_dest() method added, draw_destination() modified
- data/translations.json: 13 Yamanote entries added

### New Understandings
- IRL destination display stays as kanji, doesn't cycle to furigana like stations
- Stop-level dest override needed for circular routes with midway destination switches
- Compound destinations use "Shinagawa&\nTokyo" format (& followed by newline, no space)

### Preferences Learned
- Hard-coding UI text like "次は" is acceptable (no plans for multi-lingual UI)
- Black formatting should run via pre-commit hook, not manually

### Documentation Updates Needed
- CLAUDE.md: Add stop-level dest override section, update known behaviors #10-11, add notes 15-19
- DATA_FORMAT.md: Document compound destination format, expand stop-level override examples
- UPPER_DISPLAY_UPDATE.md: Update architecture diagram if applicable
- .claude/rules/notes.md: Add new edge case if discovered
- .claude/rules/preferences.md: Update if new preferences expressed
- memory/YYYY-MM-DD.md: Log session highlights
```

Then wait for user confirmation before proceeding.

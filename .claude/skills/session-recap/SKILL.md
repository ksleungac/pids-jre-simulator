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

After user approval, update:

**CLAUDE.md:**
- Project Overview "Last Update" section
- Known Behaviors list
- Notes for Next AI section
- Module responsibilities (if applicable)

**DATA_FORMAT.md:**
- Field definitions
- Conventions section
- Examples

### Step 5: Commit

Commit with a descriptive message like:
```
docs: Update CLAUDE.md with session discoveries
```

---

## Important Notes

1. **Don't auto-update** - Always discuss learnings first. The user's context matters more than code archaeology.

2. **Capture "why" not just "what"** - Code changes show what was modified, but the conversation reveals why it was done that way.

3. **Preferences matter** - If the user expressed a preference (e.g., "hard-coding is fine", "don't over-engineer"), note it for future sessions.

4. **Be specific** - Instead of "fixed display bug", write "Destination always displays as kanji (no furigana cycling) to match IRL behavior".

---

## Example Output

After a session fixing the Yamanote line destination display:

```
## Session Learnings Summary

### Code Changes
- display.py: _get_current_dest() method added, _draw_destination() modified
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
```

Then wait for user confirmation before proceeding.

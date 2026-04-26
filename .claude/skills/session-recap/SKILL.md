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

> **The placement table below applies *always*, not just at `/session-recap` time.** Whenever you (Claude) write or edit a doc *during* a session — not just at recap — consult this table first. `notes.md` is NOT the kitchen sink. Mental-model framing → `CLAUDE.md` (preloaded). Display gotcha → `DISPLAY.md`. JSON shape → `DATA_FORMAT.md`. Cross-cutting code pattern → `notes.md`. This rule is also restated in `preferences.md` so it's loaded at session startup.

#### The preloaded vs progressive split

A core organizing principle for placement decisions:

- **Preloaded** = always in Claude's context (CLAUDE.md, the rules files, MEMORY.md). This is for things a human working on the project already has *in their head* — what the project is modeling, scope/policy, real-world conventions, working preferences, hard rules. Re-deriving them every session would be silly; humans don't context-switch back to "what is JR East" each time they touch the codebase.
- **Progressive** = read on demand when working on that submodule (DISPLAY.md, DATA_FORMAT.md, etc.). This is implementation detail — draw-method gotchas, JSON field minutiae, layout invariants. Loading these every session bloats context with noise; loading them when actually editing the submodule lands them where they're needed.

When deciding placement, ask: *would a human working on this project have this in their head, or would they look it up when they hit the relevant submodule?*

- "What does the simulator model?" → in head → CLAUDE.md
- "What's the in-spec scope for this train model?" → in head → CLAUDE.md
- "How does the 8-station view's window invariant work?" → look up → DISPLAY.md
- "What's the exact `pa` field encoding?" → look up → DATA_FORMAT.md

The slim-CLAUDE rule applies to *implementation detail*, not framing. Mental-model content can grow CLAUDE.md modestly without violating the principle — that's what CLAUDE.md is for.

#### Where things live (single source of truth)

| What | Where | NOT in |
|------|-------|--------|
| Project overview, file structure, module table, key features, controls, **mental model (project framing, train family, IRL line scope, in-spec/best-effort policy, IRL display conventions, Hepburn)** | `CLAUDE.md` | rules files, domain docs |
| Cross-cutting code patterns (font loading, PyInstaller paths, preview mode, countdown) | `.claude/rules/notes.md` | CLAUDE.md, domain docs |
| User preferences, collaboration style, naming conventions, doc-placement hygiene, contract-pointer convention | `.claude/rules/preferences.md` | CLAUDE.md, MEMORY.md |
| Red lines, hard boundaries | `.claude/rules/redlines.md` | CLAUDE.md, MEMORY.md |
| Lessons from past mistakes | `.claude/rules/critical_lessons.md` | anywhere else |
| Build/distribution details, PyInstaller invocation, version metadata, junction handling | `.claude/skills/build/SKILL.md` | CLAUDE.md, notes.md |
| JSON field definitions, validation rules, data format encoding (incl. Hepburn examples) | `DATA_FORMAT.md` | CLAUDE.md, notes.md |
| LCD architecture, mode rendering, skip animation, layout gotchas, draw-method subtleties (upper AND lower) | `DISPLAY.md` | CLAUDE.md, notes.md |
| Daily session logs | `memory/YYYY-MM-DD.md` | — |
| Long-term memory index (pointers only) | `memory/MEMORY.md` | — |

#### Rules for updating

1. **Before writing, check if the info already exists.** Update in place, don't add a second copy.
2. **CLAUDE.md stays slim on implementation, generous on framing.** Mental-model content (what we're modeling, scope, conventions) belongs there *because* it's preloaded. Implementation details still go to domain docs.
3. **Cross-reference, don't copy** — e.g., `DATA_FORMAT.md` says "see CLAUDE.md § Mental Model for the convention itself" rather than re-explaining it.
4. **MEMORY.md is an index** — one-line pointers to memory files. No content, no rules, no preferences.
5. **When in doubt about placement**: framing/IRL/scope → `CLAUDE.md` (Mental Model); display detail → `DISPLAY.md`; JSON shape → `DATA_FORMAT.md`; cross-cutting code → `notes.md`; preference → `preferences.md`; build/release → `build/SKILL.md`.
6. **Don't bloat domain docs with framing, or CLAUDE.md with implementation.** They're complementary — preloaded framing + progressive detail. Each violation drives one of the failure modes that prompted this principle.

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
- CLAUDE.md: Update "Mental Model" if a new IRL convention or scope fact came up; add to Module Responsibilities / Key Features only if structural
- DATA_FORMAT.md: Document compound destination format, expand stop-level override examples
- DISPLAY.md: Update architecture diagram if applicable, document new mode-renderer subtleties
- .claude/rules/notes.md: Add ONLY if the new fact is genuinely cross-cutting (font loading, PyInstaller, preview) — otherwise route to CLAUDE.md/DISPLAY/DATA_FORMAT
- .claude/rules/preferences.md: Update if new preferences expressed
- memory/YYYY-MM-DD.md: Log session highlights
```

Then wait for user confirmation before proceeding.

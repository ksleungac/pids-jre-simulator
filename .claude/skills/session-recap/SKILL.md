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

Capture **what was learned**, not what was changed. `git diff` / `git log` already cover the latter. The recap captures:

- New understandings about the codebase (mental-model shifts, why-decisions)
- User preferences expressed during the session
- Behavioral patterns or data conventions established

**Capture vs codify is two different operations.** Match the entry's shape to its home:

- **Rule-shaped** (articulates an implicit pattern just-named, or user uses forward-framing language: "always / never / from now on") → direct to `principles.md` / `conventions.md` / skill / inline `# CONTRACT:`. No log-only step.
- **Fact-shaped** (IRL convention, library quirk, domain truth) → direct to CLAUDE.md mental model / domain doc / inline comment. No log-only step.
- **Preference-shaped, ambiguous** (passing remark, unclear whether the user means "this once" or "always") → daily log `## Preferences (jot)` as `[log-only]`. Promote later via recurrence or explicit framing.

A future `/distill-memory` pass surfaces patterns from accumulated `[log-only]` entries — that's the safety net for the ambiguous middle, not the universal route.

## Process

### Step 1 — Discuss learnings

Skip code-change inventory (git covers it). Present this:

```
## Session Learnings Summary

### New Understandings
- [What "why" decision was made? What mental-model shift happened?]
- [What behavioral pattern was discovered?]

### Preferences expressed (ambiguous middle only)
- [log-only] topic:<noun> — "verbatim quote" — context: one-liner
- [promote-candidate] topic:<noun> — "verbatim quote" — context: one-liner

  This section is ONLY for preference-shaped entries — passing remarks
  where permanence is unclear. Rule-shaped findings (implicit-pattern
  articulations, decision-shaping rules) and fact-shaped findings (IRL
  conventions, library quirks, domain truths) go straight to their home
  under "Documentation updates" below — no log-only detour.

  Within this section: default [log-only]. Use [promote-candidate] only
  when (a) user used "always / never / from now on / in the future"
  framing this session, OR (b) the same topic has surfaced in earlier
  daily logs (grep for the topic to check).

### TODO.md sweep
- **Closed this session**: items shipped — propose `[x]` mark or removal, with a one-line "what landed."
- **New items surfaced**: design Qs deferred, follow-ups left dangling, side-quests noted in passing.
- **Rephrase needed**: items whose framing rotted because the world changed (e.g. an item gated on "X is blocked by Y" once Y ships).
- **No changes**: explicitly state this if true. Skipping the sweep silently lets TODO.md drift.

### Documentation updates
- CLAUDE.md: only if mental-model shift
- DATA_FORMAT.md / DISPLAY.md / AUTO_INPUT.md: only if schema/architecture genuinely changed
- principles.md / conventions.md: ONLY for confirmed [promote-candidate]
- TODO.md: per the sweep above (open / close / rephrase)
- memory/YYYY-MM-DD.md: everything else (prose + the tagged Preferences section)
```

### Step 2 — User reviews and confirms

Wait for user to correct, add nuance, or override [promote-candidate] tags. Don't update anything until they sign off.

### Step 3 — Update files

After approval, update only the files the user confirmed. Each piece of information has ONE home.

The daily log gets the full structured handoff (see "Daily log format" below) — `/distill-memory` reads it later to find recurring patterns across sessions.

---

## Where things live (single source of truth)

This table applies *always*, not only at recap time. Whenever you write or edit a doc *during* a session, consult it first.

| What | Where | NOT in |
|------|-------|--------|
| Project overview, file structure, module table, key features, controls, **mental model (project framing, train family, IRL line scope, in-spec/best-effort policy, IRL display conventions, Hepburn)** | `CLAUDE.md` | rules files, domain docs |
| Cross-cutting code contracts (font-loading rule, PyInstaller path resolution, countdown formula, preview-mode swap inventory) | inline `# CONTRACT:` block at the code site | rules files, domain docs (cross-reference instead) |
| Mock route stop layout, test-station roles, schema gotchas | `audio/_mock/main/README.md` | rules files, domain docs |
| Values that shape judgment (discussion-first, pragmatic-over-perfect, filename-as-store, backup-before-destructive, doc-placement strategy) | `.claude/rules/principles.md` | CLAUDE.md, MEMORY.md |
| Project-local style, naming, tooling (sta terminology, .otf only, Black, tuneable-params, Contract Pointers convention) | `.claude/rules/conventions.md` | CLAUDE.md, MEMORY.md |
| Red lines, hard boundaries | `.claude/rules/redlines.md` | CLAUDE.md, MEMORY.md |
| Lessons from past mistakes | `.claude/rules/critical_lessons.md` | anywhere else |
| Build/distribution details, PyInstaller invocation, version metadata, junction handling | `.claude/skills/build/SKILL.md` | CLAUDE.md, inline comments |
| JSON field definitions, validation rules, data format encoding | `DATA_FORMAT.md` | CLAUDE.md, inline comments |
| LCD architecture, mode rendering, skip animation, layout gotchas | `DISPLAY.md` | CLAUDE.md, inline comments |
| Daily session logs (prose + structured Preferences section) | `memory/YYYY-MM-DD.md` | — |
| Long-term memory index (one-line pointers only) | `memory/MEMORY.md` | — |
| Open work items, follow-ups, deferred design Qs (one-line each + source pointer) | `TODO.md` | daily logs (logs capture history; TODO captures forward state) |

### Preloaded vs progressive

Preloaded files (`CLAUDE.md`, `.claude/rules/*`) hold what humans keep in their head. Progressive files (`DISPLAY.md`, `DATA_FORMAT.md`, etc.) hold implementation detail read on demand. Ask: *would someone working on this project have it in their head, or look it up when they hit the relevant submodule?* The slim-CLAUDE rule applies to *implementation*, not framing — mental model can grow CLAUDE.md modestly.

---

## Rules

1. **Match the entry's shape to its home — don't universally default to log-only.**
   - **Rule-shaped** (articulates an implicit pattern, or forward-framing "always / never / from now on") → direct to `principles.md` / `conventions.md` / skill / inline `# CONTRACT:`. No log-only step.
   - **Fact-shaped** (IRL convention, library quirk, domain truth) → direct to CLAUDE.md mental model / domain doc / inline. No log-only step.
   - **Preference-shaped, ambiguous** (passing remark, unclear permanence) → daily log `## Preferences (jot)` as `[log-only]`. Promote later via recurrence (≥2 distinct sessions) OR explicit forward framing in a future session.

   Cost of over-promotion is bloat; cost of under-promotion is one extra correction next session — strongly asymmetric. The asymmetric trap applies to the ambiguous middle, not to clearly rule-shaped or fact-shaped entries.
2. **Before writing, check if the info already exists.** Update in place, don't add a second copy.
3. **Cross-reference, don't copy.** E.g., `DATA_FORMAT.md` says "see CLAUDE.md § Mental Model" rather than re-explaining.
4. **CLAUDE.md stays slim on implementation, generous on framing.** Mental-model content belongs there *because* it's preloaded. Implementation details go to domain docs.
5. **MEMORY.md is an index.** One-line pointers to memory files only. No content, no rules.
6. **Be specific.** "Fixed display bug" → "Destination always displays as kanji (no furigana cycling) to match IRL behavior."

---

## Daily log format (`memory/YYYY-MM-DD.md`)

The daily log is mostly free-form prose for context (debugging notes, why-decisions, narrative), plus **one structured section** that `/distill-memory` will parse:

```markdown
# 2026-04-28

## Session: <one-line summary>

[Free-form prose — what was tried, what worked, dead ends, why-decisions, etc.]

## Preferences (jot)

- [log-only] topic:doc-placement — "the placement table is the canonical source" — context: said while clarifying which doc owns code contracts
- [promote-candidate] topic:commit-flow — "always smoke-test before commit" — context: after silent OCR-template no-op incident; user used "always" framing
```

### Structured-section conventions

Each entry is one line, format:

```
- [<tag>] topic:<short-noun> — "<verbatim quote>" — context: <one-liner>
```

- **Tags** evolve over the rule's lifetime:
  - `[log-only]` — default; session-recap writes this for one-shot observations
  - `[promote-candidate]` — session-recap flags this for distill-review
  - `[promoted]` — `/distill-memory` (after user accepts) updates the daily-log entry to this; signals "rule now lives in principles.md / conventions.md, don't re-propose"
  - `[rejected]` — `/distill-memory` (after user declines) updates to this; signals "considered and not promoted, stop re-surfacing"
- **Topic** is a short kebab-case noun (`audio-format`, `doc-placement`, `commit-flow`, `review-scope`, `ui-iteration`). Reuse existing topics where possible — distill clusters by topic. Don't enforce a closed vocabulary, but lean toward consistency.
- **Verbatim quote** when available; paraphrase otherwise. The user's voice is what makes the principle stick.
- **Context** is one short line — what was happening when the user said it. Helps disambiguate during distill review.

### Why this format

- Bounded structured section (`## Preferences (jot)`) is easy to grep across all daily logs without parsing prose.
- One-line entries are scannable in a long-running pass.
- Tag evolution (`[log-only]` → `[promote-candidate]` → `[promoted]` / `[rejected]`) gives `/distill-memory` a way to know what's already been decided, so monthly passes don't re-propose rejected ones.
- Free-form prose stays free-form for the parts that aren't preferences (debugging narrative, mental-model notes) — those don't need structure.

---

## Example output

After a session fixing the Yamanote destination display:

```
## Session Learnings Summary

### New Understandings
- IRL destination display stays as kanji, doesn't cycle to furigana like stations
- Stop-level dest override needed for circular routes with midway destination switches
- Compound destinations use "Shinagawa&\nTokyo" (& + newline, no space)

### Preferences expressed (default: log only)
- [log-only] topic:hardcoding — "hard-coding 次は is fine" — context: said in passing during the cycler fix; no permanence framing
- [promote-candidate] topic:tooling-format — "Black should run via pre-commit, not manual" — context: project-wide rule + "should" framing; check earlier logs for prior instances

### Documentation updates
- CLAUDE.md: no change (no mental-model shift this session)
- DATA_FORMAT.md: document compound destination format
- DISPLAY.md: document stop-level dest override behavior
- principles.md / conventions.md: pending user confirmation on the Black [promote-candidate]
- memory/2026-04-28.md: prose for the Yamanote debugging + structured Preferences section with both tagged entries
```

Then wait for user confirmation before updating files.

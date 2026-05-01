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

**HARD RULE — every bullet MUST carry a destination annotation. NO EXCEPTIONS.**

A New Understanding is, by definition, something claude learned this session. The user does NOT learn it from reading the recap — only claude does, and only if it's saved to a file that future sessions will load. A bullet without a save is self-narration: it costs the user reading time, costs claude write tokens, and produces ZERO forward value because next session has no record of it.

The mental model: claude learning ≠ user learning. The user is not the audience for the New Understandings list — the audience is *future claude*. The list exists so claude can identify what to write down. If a bullet has no destination, it's a confession that claude is about to lose the learning — and outputting that confession is worse than silent loss because it wastes the user's time too.

Every bullet MUST be one of:

- `(already in X.md from this session)` — the understanding landed in a doc as part of this session's work; the bullet is a pointer for the user's review.
- `→ propose: write to X.md` — proposed for codification in Step 3 (user reviews/adjusts in Step 2).

If a candidate bullet doesn't fit either: **OMIT it entirely.** Don't write it down to "share with the user" — there is no value to share. The user does not internalize understandings by reading; claude does, and only via the save.

Example (correct):
- IRL destination display stays as kanji, doesn't cycle to furigana like stations *(already in CLAUDE.md § "IRL display conventions")*
- Implementation-completion-as-spec recurrence pattern → *propose: write to principles.md as new entry*

Example (WRONG — anti-pattern, never produce this):
- ~~IRL destination display stays as kanji~~ ← no destination annotation; if it's already in a doc, say so; if not, propose a save; if neither applies, this bullet should not exist.

This rule is the canonical source of truth. The same logic applies in spirit to "Corrections / preferences" — but that section already has destinations baked into its template, so the gap is specifically here in "New Understandings."

### Corrections / preferences this session

Per Rule 1, classify each user correction or articulated preference and propose home(s). User reviews + approves per item in Step 2; claude writes the actual rule wording in Step 3 (diff shown before file edits land).

- "verbatim quote 1" → **rule-shaped** → conventions.md (or principles.md / skill / inline `# CONTRACT:`)
- "verbatim quote 2" → **both-shaped** → DOMAIN_DOC.md (canonical content) AND conventions.md (behavioral binding)
- "verbatim quote 3" → **fact-shaped** → CLAUDE.md mental model (or domain doc / inline)
- "verbatim quote 4" → **preference, ambiguous** → daily log `[log-only]` only

If no corrections this session, state it explicitly — don't skip silently.

### TODO.md sweep
- **Closed this session**: items shipped — propose `[x]` mark or removal, with a one-line "what landed."
- **New items surfaced**: design Qs deferred, follow-ups left dangling, side-quests noted in passing.
- **Rephrase needed**: items whose framing rotted because the world changed (e.g. an item gated on "X is blocked by Y" once Y ships).
- **No changes**: explicitly state this if true. Skipping the sweep silently lets TODO.md drift.

### Documentation updates (will land after Step 2 approval)
- CLAUDE.md / domain docs: per fact-shaped + both-shaped corrections approved
- principles.md / conventions.md: per rule-shaped + both-shaped corrections approved
- TODO.md: per the sweep above (open / close / rephrase)
- memory/YYYY-MM-DD.md: free-form prose for context + structured Preferences section (one entry per correction, tagged per its disposition)
- memory/MEMORY.md: ONE one-line pointer per session-block (per Rule 5 format), no abstracts
```

### Step 2 — User reviews and confirms

Wait for user to correct, add nuance, or override [promote-candidate] tags. Don't update anything until they sign off.

### Step 3 — Update files

After approval, update only the files the user confirmed. Each piece of information has ONE home.

**Before writing to a domain doc** (`DISPLAY.md` / `DATA_FORMAT.md` / `AUTO_INPUT.md`): re-read the `EDIT-CONTRACT` block at the top of the file. Confirm the addition isn't on the refuse list (history notes / code illustrations / speculative future / design-rationale prose / cross-doc duplication). Name the section you're merging into OR replacing — if neither, the addition is appending and probably belongs elsewhere (CLAUDE.md mental model / a skill / an inline `# CONTRACT:` / today's daily log). For additions > ~10 lines, present the diff to the user before writing.

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

0. **HARD RULE — Every "New Understanding" bullet MUST have a save-destination, NO EXCEPTIONS.** A New Understanding without a destination annotation is forbidden output. The user does NOT learn from reading the recap; only claude does, and only via the save. Outputting a destination-less understanding wastes the user's time AND loses the learning. Every bullet must be `(already in X.md from this session)` OR `→ propose: write to X.md`. If neither applies, OMIT the bullet — never narrate without committing. See Step 1 for full rationale and examples.

1. **Match the entry's shape to its home — don't universally default to log-only.**
   - **Rule-shaped** (articulates an implicit pattern, or forward-framing "always / never / from now on / don't / use X not Y") → direct to `principles.md` / `conventions.md` / skill / inline `# CONTRACT:`. No log-only step.
   - **Fact-shaped** (IRL convention, library quirk, domain truth) → direct to CLAUDE.md mental model / domain doc / inline. No log-only step.
   - **Both-shaped** (correction has BOTH canonical content AND a behavioral binding about how to use it) → save in BOTH homes. Canonical content → domain doc (read on demand); behavioral binding → `principles.md` / `conventions.md` (preloaded every session). A rule that lives only in a domain doc fires only when claude opens the doc. For corrections that need to bind in chat / design / review, the preloaded home is mandatory. Concrete (2026-04-30 incident): "for autodriver discussions use Layer 1/2/3 names + arrow flow + don't redesign" → AUTO_INPUT.md gets the canonical names + arrows AND conventions.md gets the binding rule. Saving only one half is the failure mode.
   - **Preference-shaped, ambiguous** (passing remark, unclear permanence) → daily log `## Preferences (jot)` as `[log-only]`.

   **When in doubt, classify rule-shaped, not ambiguous.** A correction is rule-shaped if violating it would cause the same mistake in any future session on this project — even without explicit "always" wording. The conservative bias toward "ambiguous middle" produced recurrences. Cost asymmetry: over-promotion = bloat (prunable via `/distill-memory`); under-promotion = recurrence (paid by user, who has explicitly named it costly: "same thing happens 2 times are frustrating enough already"). The asymmetry favors over-classifying as rule-shaped at recap time. The user's Step 2 review is the safety net for false-positive promotions.
2. **Before writing, check if the info already exists or has gone stale.** Update / remove in place, don't add a second copy, don't leave outdated content standing. Each domain doc carries an `EDIT-CONTRACT` block at its top with the concrete refuse-list and merge-or-replace requirement — re-read before writing. See [principles.md § "Tighten before appending"](../../rules/principles.md).
3. **Cross-reference, don't copy.** E.g., `DATA_FORMAT.md` says "see CLAUDE.md § Mental Model" rather than re-explaining.
4. **CLAUDE.md stays slim on implementation, generous on framing.** Mental-model content belongs there *because* it's preloaded. Implementation details go to domain docs.
5. **MEMORY.md is an index, not an abstract.** Format: `- [YYYY-MM-DD time-block](file.md) — headline finding`. ~150 char cap per line. Multi-session days get one entry per session-block ("2026-04-30 AM" / "2026-04-30 PM"), not a bundled paragraph. The temptation at recap time is to write a summary of the session in the index entry — that's the wrong shape. Headlines, not summaries. The daily log behind the link holds the detail; the index entry only has to make a future reader say "yes, click this" or "no, skip."
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

## Daily log EDIT-CONTRACT

Daily logs are decision-records, not narrative dumps. Before writing a session-block to `memory/YYYY-MM-DD.md`, check the addition isn't on the refuse list. Re-read this block at write-time, same discipline as the domain-doc EDIT-CONTRACTs.

**Refuse:**
- Blow-by-blow review-cycle reports ("Cycle 1 caught X, Y, Z. Cycle 2 caught Q. Cycle 3 clean."). Git log + commit messages already cover what changed. Keep only the WHY of decisions made during review.
- "What got done" narrative — bullet list of code changes. Git diff covers it. Keep WHY decisions, not WHAT was edited.
- Full-text rehashes of design discussions. Keep the 2-3-line decision + WHY. Trim the meandering.
- Documentation enumerations ("Updated A, B, C, D, E files"). `git status` covers it. Mention only non-obvious doc moves.

**Keep:**
- WHY a decision was made (context that doesn't survive in code).
- Non-obvious context that has no other home (mental-model shifts, surprising IRL conventions discovered, unresolved threads).
- `[log-only]` / `[promote-candidate]` preferences (per Rule 1).
- Trace of incidents — what surprised us, what we fixed, what could recur. The pathology, not the play-by-play.

**Size target:** <50 lines per session-block. >100 lines is typically the failure mode — narrating git history that's already in git. The 2026-04-29 log at 538 lines is the canonical anti-example.

---

## Example output

After a session fixing the Yamanote destination display:

```
## Session Learnings Summary

### New Understandings
- IRL destination display stays as kanji, doesn't cycle to furigana like stations → *propose: write to DISPLAY.md § "Mode rendering"*
- Stop-level dest override needed for circular routes with midway destination switches → *propose: write to DISPLAY.md § "Mode rendering"*
- Compound destinations use "Shinagawa&\nTokyo" (& + newline, no space) → *propose: write to DATA_FORMAT.md § "Destination encoding"*

(Every bullet has a destination. If a candidate bullet had nothing to propose AND wasn't already saved, it would be omitted entirely — see Step 1 hard rule.)

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

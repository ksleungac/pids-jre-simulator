---
name: session-recap
description: End-of-session recap — codify learnings synchronously into their canonical homes; daily logs hold narrative continuity only.
triggers:
  - /session-recap
  - session recap
  - recap session
  - update docs
---

## Purpose

Capture **what was learned this session** and **codify it synchronously** into its canonical home. The daily log captures narrative continuity (what happened + why) for next-session pickup; **rules / learnings / preferences live in their canonical home, written this session, not deferred.**

There is **no log-only / promote-candidate intermediate state**. Every learning, correction, or preference either lands in its canonical home this recap (with dedup-by-re-read) or is omitted entirely. Defer-and-distill is gone — `/distill-memory` becomes a safety-net audit, not a primary route.

The two operations:
- **Codify** — write the rule/fact to its canonical home (`principles.md` / `conventions.md` / `CLAUDE.md` / domain doc / inline `# CONTRACT:` / skill).
- **Narrate** — write the session story to `memory/YYYY-MM-DD.md` for next-session continuity. Informational only, not for the user's review at recap time.

## Process

### Step 0 — Friction self-check (behavioral self-observation)

Before discussing learnings, claude self-assesses: *did this session involve friction?*

**Friction signals** (impression-based — claude judges from session memory; user hints accepted):
- Multiple back-and-forth rounds on a single point of program logic.
- User foul language or visible frustration.
- User explicitly says "you've been bad today" / "you're being argumentative" / similar.
- Claude was challenged and re-justified its position instead of re-reading source (defensive posture).

**If no friction → skip silently. Proceed to Step 1.** User will voice out if claude misses.

**If friction → run the loop:**

1. **Self-observation.** Claude writes a structured behavioral self-observation: patterns claude noticed about its own outputs this session, with project-specific evidence cited inline. Format is claude's call — ad-hoc file at repo root, inline section, etc. Whatever feeds cleanly into third-man.

2. **Third-man review.** Hand the self-observation to `/third-man`. Third-man's role: **fair researcher / doctor** — not always claude's fault; sometimes the "friction" is miscommunication or unclear user wording. Third-man's job:
   - Validate patterns are real (not over-pattern-matched from one instance).
   - Disambiguate against existing `principles.md § Collaboration` entries (avoid duplicates).
   - Identify which patterns are claude-side vs miscommunication-side.
   - Propose wording for codifications.

3. **Open questions back to user.** If third-man surfaces a question requiring user preference input, claude pauses and asks. Otherwise the third-man → claude consolidation continues without further user touchpoints until Step 2.

4. **Consolidate.** Claude proposes codifications to `principles.md § Collaboration` (or narrower home if applicable, e.g. auto-memory for tool-specific feedback). Each proposal subject to the dedup rule (Step 3 rule 2).

5. **Cleanup.** Self-observation file (if any) is ephemeral — deleted after consolidation lands. The codified rule is the source of truth.

**Routing into Step 1's report:** Step-0 codifications enter the **"New Understandings"** section with `→ propose:` annotations alongside other learnings — they are claude-side learnings about claude's own behavior, NOT user corrections. Do not file them under "Corrections / preferences" (which is reserved for user-articulated rules / preferences captured verbatim).

**Scope:** this step targets **behavioral patterns claude noticed about its own outputs** — patterns the user observed but did not articulate as a rule. Project-specific factual corrections (got X wrong about the codebase) continue through Step 1's "Corrections / preferences" flow.

### Step 1 — Discuss learnings

Skip code-change inventory (git covers it). Present the report below.

**Brevity is mandatory — the report is for the user's eye-scan, not a write-up.** Each bullet should fit on one line: the learning + destination annotation, nothing more. No parenthetical "(deliberate listening pause)" / "(why: X breaks if Y)" tails — the WHY belongs in the file the codification lands in, not the recap. If a bullet won't fit on one line, the WHY is leaking; trim it. Aim: ~5 words of content + the destination tag.

Same brevity rule for "Corrections / preferences": list items being codified verbatim; for omits, **collapse to a count** ("3 other passing remarks omitted") rather than enumerating each one. Enumerating omits is the same self-narration anti-pattern the New Understandings hard-rule warns against.

Present this:

```
## Session Learnings Summary

### New Understandings

**HARD RULE — every bullet MUST carry a destination annotation. NO EXCEPTIONS.**

A New Understanding is, by definition, something claude learned this session. The user does NOT learn it from reading the recap — only claude does, and only if it's saved to a file that future sessions will load. A bullet without a save is self-narration: it costs the user reading time, costs claude write tokens, and produces ZERO forward value because next session has no record of it.

Every bullet MUST be one of:
- `(already in X.md from this session)` — landed in a doc as part of this session's work; the bullet is a pointer for the user's review.
- `→ propose: write to X.md` — proposed for codification in Step 3.

If a candidate bullet doesn't fit either: **OMIT it entirely.** Don't write it down to "share with the user" — there is no value to share.

Example (correct):
- IRL destination display stays as kanji, doesn't cycle to furigana like stations *(already in CLAUDE.md § "IRL display conventions")*
- Implementation-completion-as-spec recurrence pattern → *propose: write to principles.md as new entry*

Example (WRONG — anti-pattern, never produce this):
- ~~IRL destination display stays as kanji~~ ← no destination annotation; if it's already in a doc, say so; if not, propose a save; if neither applies, this bullet should not exist.

### Corrections / preferences this session

**No log-only intermediate.** Per Rule 1, classify each user correction or articulated preference and propose its canonical home — every entry either promotes with dedup (Step 3) or is omitted. No "save now, decide later" middle bucket.

- "verbatim quote 1" → **rule-shaped** → `principles.md` (or conventions.md / skill / inline `# CONTRACT:`)
- "verbatim quote 2" → **both-shaped** → DOMAIN_DOC.md (canonical content) AND conventions.md (behavioral binding)
- "verbatim quote 3" → **fact-shaped** → CLAUDE.md mental model (or domain doc / inline)
- (N other passing remarks omitted — no rule shape, no codification)

If no corrections this session, state it explicitly — don't skip silently. If corrections exist but all were omits, state "all N corrections omitted as passing remarks" rather than enumerating each.

### TODO.md sweep
- **Closed this session**: items shipped — propose `[x]` mark or removal, with a one-line "what landed."
- **New items surfaced**: design Qs deferred, follow-ups left dangling, side-quests noted in passing.
- **Rephrase needed**: items whose framing rotted because the world changed.
- **No changes**: explicitly state this if true. Skipping the sweep silently lets TODO.md drift.

### Documentation updates (will land after Step 2 approval)
- CLAUDE.md / domain docs: per fact-shaped + both-shaped corrections approved.
- principles.md / conventions.md: per rule-shaped + both-shaped corrections approved.
- TODO.md: per the sweep above (open / close / rephrase).
- memory/YYYY-MM-DD.md: narrative continuity for next session. **Not shown to user at recap time** — daily-log content is for future-claude, not for user review.
```

### Step 2 — User reviews and confirms

Wait for user to correct, add nuance, or override classifications. Don't update anything until they sign off.

### Step 3 — Update files

After approval, update only the files the user confirmed. Each piece of information has ONE home.

**Mandatory dedup-by-re-read before writing to any target file:**

1. **Re-read the target file in full** — not from cached impression. The cached-impression failure mode is documented (e.g. claude operating from memory of what `principles.md` *probably* says vs. what it actually says).
2. **Search for overlapping entries** by topic / similar wording.
3. **If overlap exists**: merge into the existing entry (extend `Why:` / `How to apply:` lines, add new evidence) — don't create a second entry.
4. **If no overlap**: write a new entry.

The cost of one extra file read is trivial; the cost of duplicate-rule drift is high.

**For domain doc edits** (`DISPLAY.md` / `DATA_FORMAT.md` / `AUTO_INPUT.md`): re-read the `EDIT-CONTRACT` block at the top of the file first. Confirm the addition isn't on the refuse list. Name the section you're merging into OR replacing. For additions > ~10 lines, present the diff to the user before writing.

**Daily log writes silently** — not shown to user. Pure narrative + decisions + why-context. The `## Codifications this session` subsection (see Daily log format below) gives next-session-claude a pointer to what this session changed.

---

## Where things live (single source of truth)

This table applies *always*, not only at recap time. Whenever you write or edit a doc *during* a session, consult it first.

| What | Where | NOT in |
|------|-------|--------|
| Project overview, file structure, module table, key features, controls, **mental model (project framing, train family, IRL line scope, in-spec/best-effort policy, IRL display conventions, Hepburn)** | `CLAUDE.md` | rules files, domain docs |
| Cross-cutting code contracts (font-loading rule, PyInstaller path resolution, countdown formula, preview-mode swap inventory) | inline `# CONTRACT:` block at the code site | rules files, domain docs (cross-reference instead) |
| Mock route stop layout, test-station roles, schema gotchas | `audio/_mock/main/README.md` | rules files, domain docs |
| Values that shape judgment (discussion-first, pragmatic-over-perfect, filename-as-store, backup-before-destructive, doc-placement strategy, behavioral patterns from `/third-man` reviews) | `.claude/rules/principles.md` | CLAUDE.md, MEMORY.md |
| Project-local style, naming, tooling (sta terminology, .otf only, Black, tuneable-params, Contract Pointers convention) | `.claude/rules/conventions.md` | CLAUDE.md, MEMORY.md |
| Red lines, hard boundaries | `.claude/rules/redlines.md` | CLAUDE.md, MEMORY.md |
| Lessons from past mistakes | `.claude/rules/critical_lessons.md` | anywhere else |
| Build/distribution details, PyInstaller invocation, version metadata, junction handling | `.claude/skills/build/SKILL.md` | CLAUDE.md, inline comments |
| JSON field definitions, validation rules, data format encoding | `DATA_FORMAT.md` | CLAUDE.md, inline comments |
| LCD architecture, mode rendering, skip animation, layout gotchas | `DISPLAY.md` | CLAUDE.md, inline comments |
| Daily session logs (narrative continuity only) | `memory/YYYY-MM-DD.md` | rules / preferences / learnings (those went to canonical homes) |
| Long-term memory index (one-line pointers only) | `memory/MEMORY.md` | — |
| Open work items, follow-ups, deferred design Qs (one-line each + source pointer) | `TODO.md` | daily logs (logs capture history; TODO captures forward state) |

### Preloaded vs progressive

Preloaded files (`CLAUDE.md`, `.claude/rules/*`) hold what humans keep in their head. Progressive files (`DISPLAY.md`, `DATA_FORMAT.md`, etc.) hold implementation detail read on demand. Ask: *would someone working on this project have it in their head, or look it up when they hit the relevant submodule?* The slim-CLAUDE rule applies to *implementation*, not framing — mental model can grow CLAUDE.md modestly.

---

## Rules

0. **HARD RULE — every "New Understanding" bullet MUST have a save-destination, NO EXCEPTIONS.** A New Understanding without a destination annotation is forbidden output. The user does NOT learn from reading the recap; only claude does, and only via the save. Outputting a destination-less understanding wastes the user's time AND loses the learning. Every bullet must be `(already in X.md from this session)` OR `→ propose: write to X.md`. If neither applies, OMIT the bullet — never narrate without committing. See Step 1 for full rationale and examples.

1. **Match the entry's shape to its home — no log-only intermediate.**
   - **Rule-shaped** (articulates an implicit pattern, or forward-framing "always / never / from now on / don't / use X not Y") → `principles.md` / `conventions.md` / skill / inline `# CONTRACT:`. Direct promote.
   - **Fact-shaped** (IRL convention, library quirk, domain truth) → CLAUDE.md mental model / domain doc / inline. Direct promote.
   - **Both-shaped** (correction has BOTH canonical content AND a behavioral binding about how to use it) → save in BOTH homes. Canonical content → domain doc (read on demand); behavioral binding → `principles.md` / `conventions.md` (preloaded every session). A rule that lives only in a domain doc fires only when claude opens the doc. Concrete (2026-04-30 incident): "for autodriver discussions use Layer 1/2/3 names + arrow flow + don't redesign" → AUTO_INPUT.md gets the canonical names + arrows AND conventions.md gets the binding rule.
   - **Passing remark with no rule shape** → OMIT. No log-only bucket. The daily log narrates the session, not the preferences ledger.

   **When in doubt, classify rule-shaped, not omit.** A correction is rule-shaped if violating it would cause the same mistake in any future session on this project — even without explicit "always" wording. Cost asymmetry: over-promotion = bloat (auditable via `/distill-memory`); under-promotion = recurrence (paid by user, who has named it costly: "same thing happens 2 times are frustrating enough already"). The user's Step 2 review is the safety net for false-positive promotions.

2. **Mandatory dedup-by-re-read before any write.** Before writing to ANY target file: re-read it in full, search for overlapping entries by topic/wording, merge in place if overlap exists, write new entry only if no overlap. Cached-impression dedup is forbidden — that failure mode is documented (claude operating from memory of what a file says vs. what it actually says). One extra file read is trivial; duplicate-rule drift is high cost.

3. **Tighten before appending.** Each domain doc carries an `EDIT-CONTRACT` block at its top — re-read before any non-trivial addition. See [principles.md § "Tighten before appending"](../../rules/principles.md).

4. **Cross-reference, don't copy.** E.g., `DATA_FORMAT.md` says "see CLAUDE.md § Mental Model" rather than re-explaining.

5. **CLAUDE.md stays slim on implementation, generous on framing.** Mental-model content belongs there *because* it's preloaded. Implementation details go to domain docs.

6. **MEMORY.md is an index, not an abstract.** Format: `- [YYYY-MM-DD time-block](file.md) — headline finding`. ~150 char cap per line. Multi-session days get one entry per session-block ("2026-04-30 AM" / "2026-04-30 PM"), not a bundled paragraph. Headlines, not summaries.

7. **Be specific.** "Fixed display bug" → "Destination always displays as kanji (no furigana cycling) to match IRL behavior."

---

## Daily log format (`memory/YYYY-MM-DD.md`)

The daily log is **narrative continuity for next-session pickup** — what happened, decisions, why-context, dead ends. Pure prose, no structured preferences section.

Under the informational-only model:
- Daily logs do NOT capture rules, preferences, or learnings as candidates for later promotion. Those went to their canonical home in Step 3 of this same recap.
- Daily logs DO capture: session story, decisions made, debugging narrative, why-context that doesn't fit elsewhere, pointers to where rules landed.

```markdown
# 2026-04-28

## Session: <one-line summary>

[Free-form prose — what was tried, what worked, dead ends, why-decisions, narrative.]

## Codifications this session

- principles.md § "X" — added entry from <session topic>
- DATA_FORMAT.md § "Y" — added Z field documentation
- (or: "no codifications this session")
```

The `## Codifications this session` subsection is short — one line per file touched, pointing to where the rule/fact lives now. It's a forward-pointer for next-session-claude, not a duplicate of the rule.

---

## Daily log EDIT-CONTRACT

Daily logs are decision-records, not narrative dumps or preferences-ledgers. Before writing a session-block to `memory/YYYY-MM-DD.md`, check the addition isn't on the refuse list.

**Refuse:**
- Blow-by-blow review-cycle reports ("Cycle 1 caught X, Y, Z. Cycle 2 caught Q. Cycle 3 clean."). Git log + commit messages already cover what changed.
- "What got done" narrative — bullet list of code changes. Git diff covers it. Keep WHY decisions, not WHAT was edited.
- Full-text rehashes of design discussions. Keep the 2-3-line decision + WHY. Trim the meandering.
- Documentation enumerations ("Updated A, B, C, D, E files"). `git status` covers it. Mention only non-obvious doc moves.
- **Rules / preferences / learnings as standalone entries.** Under the new model, these went to their canonical home in Step 3. Daily log mentions them only in the `## Codifications this session` pointer subsection.

**Keep:**
- WHY a decision was made (context that doesn't survive in code).
- Non-obvious context that has no other home (mental-model shifts, surprising IRL conventions discovered, unresolved threads).
- Trace of incidents — what surprised us, what we fixed, what could recur. The pathology, not the play-by-play.
- Pointers to codifications landed this session (in the `## Codifications` subsection).

**Size target:** <50 lines per session-block. >100 lines is typically the failure mode — narrating git history that's already in git.

---

## Example output

After a session fixing the Yamanote destination display (no friction, smooth session):

```
## Session Learnings Summary

### New Understandings
- IRL destination display stays as kanji, doesn't cycle to furigana like stations → *propose: write to DISPLAY.md § "Mode rendering"*
- Stop-level dest override needed for circular routes with midway destination switches → *propose: write to DISPLAY.md § "Mode rendering"*
- Compound destinations use "Shinagawa&\nTokyo" (& + newline, no space) → *propose: write to DATA_FORMAT.md § "Destination encoding"*

(Every bullet has a destination. If a candidate bullet had nothing to propose AND wasn't already saved, it would be omitted entirely.)

### Corrections / preferences this session
- "hard-coding 次は is fine" → **rule-shaped** → `conventions.md § Naming`
- "Black should run via pre-commit, not manual" → **rule-shaped** → `conventions.md § Tooling`

### TODO.md sweep
- Closed: "Fix destination cycling" — shipped via this session's commits.
- No new items.

### Documentation updates (will land after Step 2 approval)
- DATA_FORMAT.md: document compound destination format.
- DISPLAY.md: document stop-level dest override behavior.
- conventions.md: add the two corrections above (after dedup-by-re-read).
- memory/2026-04-28.md: narrative for the Yamanote debugging + `## Codifications this session` pointer block.
```

Then wait for user confirmation before updating files.

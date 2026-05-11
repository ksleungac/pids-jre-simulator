---
name: distill-docs
description: Periodic audit of domain docs (DISPLAY.md, DISPLAY_E235.md, DATA_FORMAT.md, AUTO_INPUT.md, plus future per-series DISPLAY_*.md) — scan for accumulated bloat (history notes, code-snippet illustrations, speculative future sections, design-rationale prose, cross-doc duplication, cumulative staleness). Discussion-first, item-by-item; user approves each removal before any edit lands.
triggers:
  - /distill-docs
  - distill docs
  - audit docs
  - audit domain docs
  - tighten docs
  - clean up docs
  - doc bloat
---

## Purpose

Domain docs (`DISPLAY.md`, `DISPLAY_E235.md`, `DATA_FORMAT.md`, `AUTO_INPUT.md`, plus future per-series `DISPLAY_*.md` as new train models land) are written under feature-flow pressure. Even with each doc's `EDIT-CONTRACT` block at the top doing heavy lifting at write-time, three failure modes accumulate that the gate structurally can't catch:

1. **Cross-doc drift** — a fact gets stated in DISPLAY.md, then later (correctly) added to CLAUDE.md mental model, or a skill, or an inline `# CONTRACT:`. Each edit looks fine in isolation; the duplicate only shows up reading both.
2. **Cumulative staleness** — a feature commit makes half of an old section obsolete, but the editor was focused on the new content. Old content remains as background noise.
3. **Self-blindness at write-time** — the author rarely sees their own bloat. Distance helps.

This skill is the periodic sweep that pairs with the write-time `EDIT-CONTRACT` gate. With strong gates in place it runs roughly **every 1-2 months** (more often if drift accelerates), surfaces removal candidates the gate missed, and keeps domain docs tight.

NOT for one-off cleanup of a specific section — just edit in place. NOT for general doc audit ("is CLAUDE.md still accurate?") — the scope is the three production domain docs only.

## Scope

In scope:
- `DISPLAY.md`
- `DATA_FORMAT.md`
- `AUTO_INPUT.md`

Out of scope:
- `CLAUDE.md` (preloaded; mental-model framing is intentionally generous, slim-rule applies to implementation only — see [principles.md § "Preloaded mental model vs progressive implementation detail"](../../rules/principles.md))
- `.claude/rules/principles.md` (handled by `/distill-rules`, sibling skill)
- `.claude/rules/conventions.md`, `critical_lessons.md`, `redlines.md` (no dedicated audit; may fold into `/distill-rules` if bloat surfaces)
- `.claude/skills/*/SKILL.md` (updated proactively per `feedback_proactive_skill_updates`)
- `memory/*.md` (logs are append-only by design)
- `TODO.md` (sweep handled by `/session-recap`)
- `audio/_mock/main/README.md` (small + stable)

## When to run

- Every 1-2 months when the `EDIT-CONTRACT` gate is in place and working.
- When ~5+ doc-touching commits have landed since the last run.
- After a wave of session-recap activity that wrote heavily to domain docs.
- When the user notices a domain doc feels long / hard to skim / repeats things.

## Process

### Step 1 — Load each in-scope doc + record baseline

For each of the three docs, capture:
- Total line count
- Top-level (`##`) section headings
- Date markers (any `### YYYY-MM-DD`, "Pre-YYYY-MM-DD", "Key Changes from", "(history note)" — bloat-shape candidates without further reading)

Record the baseline at the top of the proposal so before/after deltas are concrete.

### Step 2 — Scan for bloat shapes

For each doc, hunt for these specific shapes (matching the EDIT-CONTRACT refuse list + the cross-cutting failure modes):

1. **History notes / change logs.** Sections titled by date, "Key Changes from legacy …", "Pre-X behavior", migration walkthroughs. `git log` is canonical; doc-side history is duplication.
2. **Code-snippet illustrations.** Multi-line Python/JSON blocks showing how a class/method *looks* rather than what its contract *is*. Schema reference (a JSON example showing required/optional fields) is in scope for the doc; "here's what `JapaneseDisplay.__init__` looks like" is not — link `file:line` instead.
3. **Speculative future sections.** "Future: …", "When X is implemented, …", design for hypothetical features that haven't shipped. Distinct from genuine schema fields marked deferred — those stay.
4. **Design-rationale prose.** Multi-paragraph framings of *why* a layered model exists, the discussion that produced a vocabulary, etc. The decision rule lives in the doc; the discussion narrative lives in `memory/`. **Exception:** rationale-shaped passages explicitly preserved by `EDIT-CONTRACT § Voice` (e.g. "Convention rationale" framings, "Mental model:" framings, incident-warning paragraphs like "burned us before") stay — the doc has reserved them for normal voice on purpose.
5. **Cross-doc duplication.** A fact also stated in `CLAUDE.md` mental model / a skill / an inline `# CONTRACT:`. Cross-reference, don't restate.
6. **Cumulative staleness.** Sections written for an earlier feature state that's been superseded but not pruned. Hardest shape to detect — needs cross-check against current code.
7. **Design-principle / lessons inflation.** Bullet lists where each entry was added at a different time, never pruned. Scan for entries that duplicate `CLAUDE.md` framing / `conventions.md` / `principles.md`.

### Step 3 — Verify before flagging

Trust-but-verify, like `/vibe-check` does for code. False-positive findings = lost user trust = harder next pass.

| Shape | Verification step |
|---|---|
| History note | Confirm equivalent info is in `git log --oneline -- <file>` (or the changelog has it; OR the section's content is genuinely past-tense ephemera) |
| Code illustration | Open the referenced file and confirm the live code matches the doc's claim. If illustration is stale, removal case is stronger (incorrect illustration > no illustration) |
| Speculative future | Grep the codebase for the speculative feature name. If zero references and no `TODO.md` entry, the speculation is fully dormant |
| Cross-doc duplication | Quote the duplicate location with `file:line` (e.g. `CLAUDE.md:67`, `displays/.../upper_lcd.py:42` for an inline contract) |
| Cumulative staleness | Read the relevant code module to confirm the doc claim is actually obsolete — not just unfamiliar |
| Principle inflation | Diff each entry against the canonical home (`principles.md` / `conventions.md`); flag only if substantively redundant |

Skip flagging if verification fails or is ambiguous — leave it for the next pass when more context exists.

### Step 4 — Present the proposal (discussion-first)

```
## Distill-docs summary — <date range since last run>

Baseline (current → after-proposal):
- DISPLAY.md: <N> lines → ~<N - X> lines
- DATA_FORMAT.md: <N> → ~<N - Y>
- AUTO_INPUT.md: <N> → ~<N - Z>

### DISPLAY.md
| # | Shape | Section / lines | Verification |
|---|---|---|---|
| 1 | history-note | "### 2026-03-14" L750-760 | git log has 7e800f3 / equivalent |
| 2 | code-illustration | L189-205 (JapaneseDisplay snippet) | upper_lcd.py:42-58 is canonical, illustration adds nothing |
| ... |

### DATA_FORMAT.md
| # | Shape | Section / lines | Verification |
|---|---|---|---|
| ... |

### AUTO_INPUT.md
| # | Shape | Section / lines | Verification |
|---|---|---|---|
| ... |

### Cross-doc duplication
| # | Fact | Locations | Canonical home |
|---|---|---|---|
| 1 | "destination always kanji" | DISPLAY.md L725, CLAUDE.md L67 | CLAUDE.md (mental model — preloaded) |
| ... |

### Total proposed removal: ~<line-count> lines across <file-count> files
```

Wait for user decisions per finding. Don't apply until the user signs off, item by item — same discipline as `/distill-memory` and `/vibe-check`. Batch-approval within one shape category is fine if the user signals it ("remove all history notes").

### Step 5 — Apply approved changes

For each approved removal:

1. Edit the doc to remove the section.
2. If the removal references content that should live elsewhere (cross-doc dedup), confirm the canonical home is intact. Add a one-line cross-reference *only* if the removal site is a natural reader-landing point that would benefit from a pointer; otherwise just remove.
3. Don't restructure mid-pass. If a doc's structure is wrong, that's a separate conversation — flag it in the wrap report.

After all approved removals, re-record the line counts so the next distill pass has a baseline:

```
DISPLAY.md: <N> lines (-<delta>)
DATA_FORMAT.md: <N> lines (-<delta>)
AUTO_INPUT.md: <N> lines (-<delta>)
```

### Step 6 — Report

```
## Distill-docs applied

- DISPLAY.md: -<X> lines, <N> sections removed/merged
- DATA_FORMAT.md: -<Y> lines, <N> sections removed/merged
- AUTO_INPUT.md: -<Z> lines, <N> sections removed/merged
- Cross-doc dedup: <N> facts unified to canonical home
- Files touched: <list>

Structural notes (deferred, not in this pass):
- <e.g. "DISPLAY.md's Lower LCD section is mixing layout + state, candidate for splitting next time">
```

Suggest committing via `/commit`. Doc-distill commits should travel as their own commit (not bundled with feature work) so the audit trail is intact.

## Things that are NOT bloat

Recognize these patterns and don't flag them:

- **Mental-model framing in CLAUDE.md** — out of scope; intentionally generous, preloaded by design.
- **The `EDIT-CONTRACT` block at the top of each doc** — the gate itself, never flag.
- **Schema reference / JSON field tables** — even if long, this is the canonical home. Don't flag for length alone; only flag if specific fields are demonstrably stale.
- **Gotcha sections / invariants / "Don'ts"** — exactly what the doc holds. Don't flag.
- **Recently-added content** (within the last ~2 weeks of git log on the file) — too soon to know if it's bloat. Let one cycle pass.
- **Small redundancies that aid skimmability** — a 1-line restatement at the top of a section that re-introduces a concept defined elsewhere is acceptable; the cost is low and locality helps the reader.
- **Cross-references** — explicit `see CLAUDE.md § X` links are *good*, even if they technically restate the topic name.
- **Voice mismatch within a doc** — rationale-shaped passages staying in normal grammar within an otherwise-caveman-voice doc is per the Voice rule in `EDIT-CONTRACT § Voice`, NOT bloat. Specifically: "Convention rationale" / "Mental model:" / "burned us before" / "why this matters" framings explicitly carved out by the Voice rule. Don't flag voice differences alone.

## Rules

1. **Discussion-first per finding.** Never delete without explicit user approval per item. Batch-approval is fine within one shape category if the user signals it.
2. **Verify before flagging.** Quote the canonical alternative location for cross-doc dedup. Quote git log for history removal. Read the code for illustration / staleness checks. Skipping verification = false positives = lost trust.
3. **Don't refactor while distilling.** This skill removes / merges; it does not restructure. If a doc's structure is genuinely wrong, flag it as a structural note in the wrap report and let the user decide whether to address it separately.
4. **Respect dormant scaffolding.** If a "Future: X" section has a clear known-future trigger (e.g. ENGLISH lower-LCD eventual implementation that's already on `TODO.md`), propose moving the reference to `TODO.md` rather than deleting outright. Same logic as `/vibe-check`'s dormant-scaffolding carve-out for code.
5. **Don't expand scope mid-pass.** This skill audits the three named domain docs. If you notice bloat in CLAUDE.md / a skill / an inline contract during the pass, note it in the wrap report; don't pull it into the current proposal.
6. **Removal-only, no rephrasing.** Don't rewrite sentences "while you're there." Each rewrite is an opportunity to introduce drift; this skill's discipline is to remove what shouldn't be there, not to improve what stays.

## Scope

- **Does** scan DISPLAY.md, DATA_FORMAT.md, AUTO_INPUT.md for the named bloat shapes.
- **Does** verify each finding via cross-doc grep / git log / code read.
- **Does** propose removals item-by-item, ask before non-trivial deletions, record before/after line counts.
- **Does not** autofix without discussion.
- **Does not** restructure (move sections around, rename headings). Removal-only.
- **Does not** rewrite prose. If a sentence reads poorly but isn't bloat-shaped, leave it.
- **Does not** audit CLAUDE.md, skills, inline contracts, memory logs — out of scope.
- **Does not** auto-commit. User runs `/commit` themselves.

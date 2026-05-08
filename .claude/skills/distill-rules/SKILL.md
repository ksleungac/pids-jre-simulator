---
name: distill-rules
description: Periodic audit of the rules corpus (currently principles.md only). Sibling to /distill-docs — same shape (discussion-first, item-by-item, EDIT-CONTRACT-gated) but with restructure + rephrase moves allowed because rule-shape evolution IS the work for rules corpus, not a drift risk. Scan for accumulated bloat (recurrence lists, sibling cross-refs, connective tissue, manufactured compounds, nested sub-rules with own incident, misplaced how-to-apply bullets, multi-paragraph incident traces).
triggers:
  - /distill-rules
  - distill rules
  - audit principles
  - audit rules
  - tighten rules
  - clean up rules
  - rules bloat
  - principles bloat
---

## Purpose

The rules corpus (`principles.md`) accumulates bloat differently from domain docs. Each session that triggers a recurrence of an existing principle appends a "Recurred YYYY-MM-DD" note; sibling cross-refs accumulate as each new entry explains itself against prior ones; sub-rules nest inside parent how-to-apply bullets when they share a domain; multi-paragraph incident narratives sit where one-line examples would suffice.

The write-time `EDIT-CONTRACT` block at the top of `principles.md` catches most of this at write-time. This skill is the periodic sweep that catches what the gate misses — cross-entry duplication, cumulative staleness, self-blindness when the author is too close to see their own bloat.

Pair this skill with the EDIT-CONTRACT, the same way `/distill-docs` pairs with the per-doc EDIT-CONTRACTs in domain docs. With strong gates in place it runs roughly **every 1-2 months** (more often if drift accelerates after `/session-recap` has been writing heavily to `principles.md`).

NOT for one-off tidying of a specific entry — just edit in place. NOT for general rule audit ("is this rule still relevant?") — that's a different conversation; this skill is bloat-shape removal + restructure under the EDIT-CONTRACT.

## Scope

In scope:
- `.claude/rules/principles.md`

Out of scope:
- `.claude/rules/conventions.md` — no `EDIT-CONTRACT` yet; folding into this skill is premature until accumulated bloat justifies it.
- `.claude/rules/critical_lessons.md` — same; entries are heavier-shape (each is a labeled incident with explicit "The Rule" / "The Pattern" structure) and bloat-pattern set differs.
- `.claude/rules/redlines.md` — small + stable.
- Domain docs (DISPLAY.md, DATA_FORMAT.md, AUTO_INPUT.md, DISPLAY_E235.md) — handled by `/distill-docs`.
- `.claude/skills/*/SKILL.md` — updated proactively per `feedback_proactive_skill_updates`.
- `CLAUDE.md`, `memory/*.md`, `TODO.md` — out of scope.

## When to run

- Every 1-2 months when the EDIT-CONTRACT gate is in place and working.
- When ~5+ `/session-recap` codifications have landed in `principles.md` since the last run.
- When the user notices an entry has accumulated nested sub-bullets, has a recurrence list, or feels like it's growing rather than staying tight.

## Process

### Step 1 — Load `principles.md` + record baseline

Capture:
- Total line count
- Entry count per `## Section` heading
- Entries with **nested sub-bullets** that look like rules-in-disguise (own trigger / own incident / own how-to-apply paragraph)
- Entries with **recurrence prose** (`Recurred YYYY-MM-DD`, "Same pathology...", "The shape recurred...")
- Entries with **sibling cross-ref tails** ("Sibling to X:", "Pairs with Y as", "Distinct from Z")
- Entries with **multi-paragraph Why** (more than one paragraph between rule statement and how-to-apply)

Record the baseline at the top of the proposal so before/after deltas are concrete.

### Step 2 — Scan for bloat shapes

Per the EDIT-CONTRACT refuse-list at the top of `principles.md`:

1. **Recurrence lists.** "Recurred 2026-X-Y across N substrates..." → each recurrence becomes an additional one-line example in the Why list.
2. **Sibling cross-reference tails.** "Sibling to X: that polices Y, this polices Z." Reader gets the difference from context.
3. **Connective tissue.** "The shape is consistent:", "This is distinct from", "Pairs with X as the recovery layer", "The user's tolerance for X is low".
4. **Manufactured compounds when plain words work.** "scope-changing options" → "options that change scope". Test: did the compound shorten the sentence? No → replace.
5. **Nested sub-rules with their own trigger + incident + how-to-apply.** If a bullet carries its own anchor + rule, promote to a peer entry.
6. **How-to-apply bullets that fit a sibling rule better.** Migrate to the sibling, don't pile up under a parent that doesn't actually own the trigger. Today's anchor case: opacity-bullet was filed under `Verify before claiming`; it's actually a `Ground reasoning in user's stated terms` rule — different trigger.
7. **Multi-paragraph incident traces in Why.** Full traces live in daily logs; `principles.md` carries one-line examples only.
8. **User-quote padding.** Keep one quote per entry only when load-bearing (captures the rule's failure shape in the user's own words). Drop the rest.
9. **Entries that should fold.** Two entries describing the same rule with different scope (e.g. parent + "X for Y specifically") → fold the variant into a sub-bullet of the parent.

### Step 3 — Verify before flagging

False-positive findings = lost user trust = harder next pass. Verify each finding against primary source.

| Shape | Verification step |
|---|---|
| Recurrence list | Each recurrence has a corresponding daily log entry. **Read the log** — don't reconstruct examples from memory. Today's anchor case: 2026-05-02 + 2026-05-03 examples drafted from memory diverged from the actual logs; verification caught it. |
| Sibling cross-ref tail | Confirm the sibling rule actually exists in the file with the framing claimed. If the cross-ref describes a relationship that's no longer accurate, removing the tail is unambiguously right. |
| Connective tissue | Read the entry with and without it. If the rule reads cleaner without, cut. |
| Manufactured compound | Apply the test: "did the compound shorten the sentence? If no, replace with plain words." |
| Nested sub-rule promotion | Does the sub-bullet have its own trigger + own incident + own how-to-apply? If yes, it's a peer rule wearing how-to-apply clothing — promote. |
| Misplaced how-to-apply bullet | Does the bullet's content actually apply to THIS rule, or to a sibling? Run the bullet's test: "would this fire on the parent rule's trigger, or on a different trigger?" If different trigger, migrate. |
| Multi-paragraph Why | Verify each example bullet's claim against the actual daily log. Don't paraphrase from memory. |
| User-quote padding | Test: does removing the quote weaken the rule? If no, drop. |
| Fold candidate | Do the two entries share a trigger, with one being a domain-specialization of the other? If yes, fold. |

Skip flagging if verification fails or is ambiguous — leave for the next pass.

### Step 4 — Present the proposal (discussion-first)

```
## Distill-rules summary — <date range since last run>

Baseline:
- principles.md: <N> lines, <M> entries across <K> sections

### Bloat findings

| # | Entry | Shape | Action | Verification |
|---|---|---|---|---|
| 1 | Verify before claiming | recurrence list (3 substrates) | Convert to 3 one-line example bullets | Daily logs 2026-05-02 + 2026-05-03 confirm substrates |
| 2 | Implementation-completion-as-spec | nested sub-rule (Scope fidelity) | Promote to peer entry | Has own trigger (codifying user feedback) + own incident (2026-05-04) |
| 3 | Ground reasoning in user's stated terms | misplaced bullet (opacity) | Migrate to ... wait, this IS the parent. Skip. | (no verification needed) |
| ... |

### Structural changes (restructures + folds)
- Fold "Discussion-first for data work specifically" into "Discussion-first" as sub-bullet (same trigger, different domain)
- Promote 3 sub-bullets under "Ground reasoning" (Scope-expansion guard / Pre-stated scope fences / Weirdness-as-signal) to peer entries

### Total proposed
- <N> entries trimmed for prose
- <M> entries promoted to peer
- <L> entries folded
- <K> bullets migrated between entries
- ~<line-count> net line change (note: line count may not drop — density is the real metric)
```

Wait for user decisions per finding. Don't apply until the user signs off, item by item — same discipline as `/distill-docs`. Batch-approval within one shape category is fine if the user signals it ("strip all sibling cross-ref tails").

### Step 4.5 — Third-man validation for non-trivial shape changes

If any finding involves a substantive shape change (rename, rule-statement rewrite, restructure of Why or how-to-apply), run `/third-man` on a representative rewritten entry from a zero-context view BEFORE applying.

The brief for the third-man:
- The rewritten entry verbatim
- Question: does this rule read cleanly to a zero-context reader (no codebase familiarity, no prior conversation)?
- Specific concerns: clarity of claim-vs-reality in examples, abstract jargon in how-to-apply bullets, identifiers that read as noise without context.

Today's anchor case: third-man caught that a how-to-apply bullet about "don't import adjacent assumptions (opacity, render order)" actually belonged to a sibling rule (`Ground reasoning in user's stated terms`), not the parent rule it was filed under (`Verify before claiming`). The migration would have been missed without the zero-context read.

Skip third-man for trivial trims (cutting connective tissue, dropping a sibling cross-ref tail). Run it for any restructure or rephrase that changes the rule's shape.

### Step 5 — Apply approved changes

EDIT-CONTRACT-first sequencing if the contract is missing or stale:

1. **If no `EDIT-CONTRACT` exists in `principles.md`**, draft it first based on the bloat patterns observed in this pass. Get user sign-off, write the contract, THEN apply trims under the contract.
2. **If the `EDIT-CONTRACT` exists but is missing patterns this pass surfaced**, propose extending the contract first. Get user sign-off, update the contract, THEN apply.
3. **If the `EDIT-CONTRACT` is current**, apply trims directly.

For each approved change:

| Action | Edit shape |
|---|---|
| Trim prose | Edit to compress the entry's Why / how-to-apply per the EDIT-CONTRACT shape (rule + Why-with-Examples-list + terse bullets). |
| Promote sub-bullet to peer | Edit to remove the sub-bullet from parent, add new peer entry positioned next to the parent (sibling cluster). |
| Fold entry into sibling | Edit to remove the dedicated entry, add the content as a sub-bullet of the target parent. |
| Migrate how-to-apply bullet | Edit to remove from source parent, add to target parent. |

Don't restructure mid-pass beyond what was approved. If a section's overall structure is wrong, that's a separate conversation — flag it in the wrap report.

After all approved changes, re-record the line count + entry count so the next distill pass has a baseline.

### Step 6 — Report

```
## Distill-rules applied

- principles.md: <N> lines (<delta>), <M> entries (<delta>)
- Trimmed: <N> entries
- Promoted to peer: <M> entries (list)
- Folded into parent: <L> entries (list)
- Bullets migrated: <K> (list source → target)
- EDIT-CONTRACT updates: <none / extended with N patterns>

Structural notes (deferred, not in this pass):
- <e.g. "Engineering rigor section's Test the change rule could split into preventive vs detective halves — flagged for future pass">
```

Suggest committing via `/commit`. Distill-rules commits should travel as their own commit (not bundled with feature work) so the audit trail is intact.

## Things that are NOT bloat

Recognize these and don't flag them:

- **Examples lists with multiple bullets.** Required by the EDIT-CONTRACT, not bloat. Multi-example coverage is the broader-pattern shape; a single deeply-traced incident is the bloat shape that this skill cuts.
- **Date parentheticals on examples** (e.g. `(2026-04-30)`). Reverse-lookup value to daily logs.
- **One load-bearing user quote per entry** (captures the rule's failure shape in the user's own words). Multiple quotes per entry is padding.
- **The `EDIT-CONTRACT` block at the top.** The gate itself, never flag.
- **Recently-added content** (within ~2 weeks of git log on the file). Too soon to know if it's bloat. Let one cycle pass.
- **Cross-references that are explicit pointers** ("see `critical_lessons.md` § X" with a specific reason). Different from the cross-ref tails this skill cuts — those are sibling-comparison narratives ("Sibling to X: that polices Y, this polices Z"); explicit pointers are reader navigation.
- **Rule statements that are 1-2 sentences with no padding.** That's the target shape, not bloat.

## Rules

1. **Discussion-first per finding.** Never trim / promote / fold / migrate without explicit user approval per item. Batch-approval is fine within one shape category if the user signals it.
2. **Verify against daily logs for examples — don't reconstruct from memory.** The 2026-05-08 anchor case: examples drafted from memory diverged from the actual log content; daily-log read caught it before the trim landed. The third-man's specific finding was that two bullets failed the claim-vs-reality test until grounded in actual log content.
3. **Third-man validation for non-trivial shape changes.** Zero-context read catches misclassified bullets, abstract jargon, and frame-mismatched how-to-apply migrations. Skip for trivial trims; run for any restructure that changes shape.
4. **Restructure + rephrase ARE allowed** (unlike `/distill-docs`). Rule-shape evolution IS the work for rules corpus — folding overlapping entries, promoting nested sub-rules to peers, compressing multi-paragraph Why to one-line examples. The discipline difference: domain docs describe stable code (restructuring risks doc/code drift); rules corpus describes evolving judgment shapes (restructuring is the audit's purpose).
5. **Promotion vs folding rule.** Sub-rule has own trigger + own incident → promote to peer. Sub-bullet is a domain instance of parent (same trigger, different scope) → fold into parent as a sub-bullet.
6. **EDIT-CONTRACT-first sequencing.** If the contract is missing or doesn't cover the patterns this pass surfaced, write/update the contract first as the gate. The contract gates the trim pass itself, not just future drift.
7. **Don't expand scope mid-pass.** Scope is `principles.md` only. If you notice bloat in `conventions.md` / `critical_lessons.md` / a skill / an inline contract during the pass, note it in the wrap report; don't pull it into the current proposal.
8. **Don't auto-commit.** User runs `/commit` themselves.

## Scope

- **Does** scan `principles.md` for the named bloat shapes against the EDIT-CONTRACT refuse-list.
- **Does** verify each finding via daily-log read / canonical-home check / sibling-rule existence check.
- **Does** propose trims, promotions, folds, migrations item-by-item, ask before each.
- **Does** run `/third-man` zero-context validation on non-trivial shape changes.
- **Does** apply EDIT-CONTRACT updates first if the contract is missing or stale.
- **Does** record before/after baselines (line count + entry count + section structure).
- **Does not** autofix without discussion.
- **Does not** restructure beyond what was item-approved (no "while I'm here, let me reorganize sections").
- **Does not** audit `conventions.md` / `critical_lessons.md` / domain docs / skills / CLAUDE.md / memory — out of scope.
- **Does not** auto-commit.

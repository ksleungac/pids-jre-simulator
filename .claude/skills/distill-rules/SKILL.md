---
name: distill-rules
description: Periodic audit of the rules corpus (principles.md, conventions.md, critical_lessons.md). Scan for accumulated bloat — recurrence lists, sibling cross-refs, connective tissue, nested sub-rules, multi-paragraph incident traces — then sweep the skills for instructions that contradict a rule. Discussion-first, item-by-item. Restructure + rephrase allowed.
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

The rules corpus (`.claude/rules/`) accumulates bloat: recurrence notes, sibling cross-refs, nested sub-rules, multi-paragraph incident narratives. Write-time EDIT-CONTRACTs catch most of it; this skill is the periodic sweep for what the gate misses.

Runs every 1-2 months. NOT for one-off tidying — just edit in place. NOT for "is this rule still relevant?" — that's a different conversation.

## Scope

In scope:
- `.claude/rules/principles.md` — EDIT-CONTRACT at top; entries are rule + why + how-to-apply
- `.claude/rules/conventions.md` — reference-shaped entries (naming, style, tooling)
- `.claude/rules/critical_lessons.md` — incident entries: rule + pattern + scope

Read but not trimmed:
- `.claude/rules/redlines.md` — small + stable, and it is a prohibition source for Step 2.5.
- `.claude/skills/*/SKILL.md` and `CLAUDE.md` — searched in Step 2.5, and edited there only where one contradicts a rule. Their own bloat is out of scope.

Out of scope:
- Domain docs — handled by `/distill-docs`.
- `memory/*.md`, `TODO.md`.

## When to run

- Every 1-2 months when the EDIT-CONTRACT gate is in place and working.
- When ~5+ `/session-recap` codifications have landed in `principles.md` since the last run.
- When the user notices an entry has accumulated nested sub-bullets, has a recurrence list, or feels like it's growing rather than staying tight.

## Process

### Step 1 — Load target files + record baseline

`uv run _dev_scripts/check_rules_corpus.py --report` prints the numeric baseline — entries, total words, worst single entry, sibling cross-ref tails — per file, against the recorded ratchet. Read it rather than hand-counting; the script is what the pre-commit hook measures, so a figure derived any other way can disagree with the gate that will judge the pass.

Then load all in-scope files under `.claude/rules/` and capture per file the shapes the script cannot see:
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

### Step 2.5 — Sweep the skills for rules they contradict

A rules file and a skill are never read side by side, so a skill can instruct the opposite of a rule for months with nothing anywhere reporting it. This is the one finding class the EDIT-CONTRACT gate and the ratchet are both structurally blind to: each measures one file against itself, and a contradiction is a fact about a pair. Reading one file at a time cannot produce it.

Work from the prohibition to the instruction, in that direction:

1. Collect every hard prohibition in `redlines.md` and every `### Never ...` entry in `principles.md`. Name the forbidden ACT, not the sentence — "offering a commit", "reading a file through a shell".
2. Grep `.claude/skills/` and `CLAUDE.md` for text instructing that act. The grep is the act's own vocabulary, not the rule's: `suggest committing|offer to commit|want me to commit` found one, `Get-Content|cat |Select-String` found the other.
3. Order the pair with `git log -1 -S'<phrase>' --format='%h %ad' --date=short` on each side. The newer passage is current; file timestamps and a passage's own claim to supersede others are both worthless here.
4. Rewrite the older to match the newer, keeping whatever live purpose it had. A skill telling you to suggest a commit still had a real point about commits travelling alone — keep that half.

This step's own text matches its own greps, as does any skill line that states the rule correctly ("don't offer to commit", "read files with Read"). A hit is a finding only when the surrounding sentence tells you to DO the forbidden act.

An **override is not a conflict.** A skill whose different rule is explained by its own task, or that names the rule it overrides, stays. `review-dirty` preferring PowerShell over bash is an override: the msys crash is a live environment fact about that skill's own work. Preferring PowerShell `Get-Content` over the Read tool was the conflict inside it.

Where history cannot order the pair, or where the newer passage would LOOSEN a prohibition, flag it and let the author decide. Two anchor cases, both found 2026-09-29: `/distill-docs` and `/distill-rules` each said "Suggest committing via `/commit`" (2026-04-29, 2026-05-08) against `principles.md § "Never prompt to commit"` (2026-06-11); both review skills said to run `ls` and `cat` in PowerShell (2026-04-24) against `redlines.md`'s built-in-tool rule (2026-08-26). Four months and two months unnoticed respectively, in the files that exist to keep the corpus honest.

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

A distill-rules commit travels on its own, not bundled with feature work, so the audit trail stays intact. Don't offer to commit — `principles.md § "Never prompt to commit"`.

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
   - **Any pass that rewrites more than a couple of entries owes a mechanical coverage proof.** Snapshot the before state, then diff three sets: every `2026-MM-DD` date, every backticked identifier, and every `^### ` entry title. Account for each drop — a date or an identifier that vanished under the 4-example cap is a deliberate cut, one that vanished because a how-to-apply bullet got compressed away is a lost rule, and the two look identical in the diff until you check. On 2026-08-31 this found five real losses across `principles.md` and `conventions.md` (a `validate_data.py` instruction, the `v<prev>..HEAD` method, the `--derivable` flag, two file names with reverse-lookup value) that reading the diff had not surfaced.
     - **Diff at the TOKEN level, not the span level.** Comparing exact backticked spans reports every reformatting as a loss, because adding a path prefix rewrites the span: `` `calibration_editor.py` `` becomes `` `_dev_scripts/calibration_editor.py` `` and the set says one identifier vanished while the file names it twice. On 2026-09-01 that gave 29 apparent losses of which 20 were this artifact. For each dropped span, ask whether its leading token still appears anywhere in the file, and only report the residue.
   - **Renaming an entry title breaks every `§ "exact title"` citation.** They are not compiler-checked and nothing greps them. After any rename, collect every heading in the corpus, collect every `§ "..."` reference across rules + skills + docs, and report the ones that no longer resolve. The same sweep found 15 dangling references that predated the pass, six of them pointing at rules under names that no longer existed.
     - **A citation that names no heading at all is the worse form, and the `§ "..."` pattern misses it.** `/distill-docs` justified a scope exclusion with "per `feedback_proactive_skill_updates`", a snake_case token appearing exactly once in the repo — on that line. It reads as a rule name and there is no rule, so the exclusion had no stated reason for a year. Sweep bare `per \`?[a-z][a-z0-9_]{12,}\`?` and `see \`?[a-z][a-z0-9_]{12,}\`?` alongside the `§` form: a single-occurrence hit is a citation of nothing. (2026-09-29.)
     - **Scope the sweep to citations that NAME a rules file**, matching `(principles|conventions|critical_lessons|redlines)(\.md)?[^\n]{0,40}?§ "..."`. A bare `§ "..."` grep returns everything, and most of it cites headings in `docs/DISPLAY.md`, `auto_input/README.md` or a WIP doc; on 2026-09-01 that was 189 hits against 42 in scope, and a real break would have sat unread in the middle of it. Normalise whitespace before matching, since a citation wraps across two comment lines in `.py` files. Two further sources of noise are expected and are not breaks: `conventions.md` states most of its rules as bullets rather than headings, so a citation into it will not resolve against a heading set; and a citation ending in `…` or `...` is a deliberate truncation.
5. **Promotion vs folding rule.** Sub-rule has own trigger + own incident → promote to peer. Sub-bullet is a domain instance of parent (same trigger, different scope) → fold into parent as a sub-bullet.
6. **EDIT-CONTRACT-first sequencing.** If the contract is missing or doesn't cover the patterns this pass surfaced, write/update the contract first as the gate. The contract gates the trim pass itself, not just future drift.
7. **Don't expand scope mid-pass.** If you notice bloat in a skill / domain doc / inline contract during the pass, note it in the wrap report; don't pull it into the current proposal. **The exception is a Step 2.5 contradiction**, which is this pass's own subject even though its edit lands in a skill — a rule nothing obeys is a defect in the rule's reach, not in someone else's file. Fix that one; leave everything else about the skill alone.
8. **Don't auto-commit.** User runs `/commit` themselves.

## Scope

- **Does** scan all in-scope rules files for bloat shapes.
- **Does** sweep the skills for instructions that contradict a rule, and rewrite the older side.
- **Does** verify each finding against primary source.
- **Does** propose changes item-by-item, wait for approval.
- **Does** apply EDIT-CONTRACT updates first if missing or stale.
- **Does** record before/after baselines.
- **Does not** autofix without discussion.
- **Does not** restructure beyond what was approved.
- **Does not** touch domain docs or memory, or trim a skill for anything but a contradiction.
- **Does not** auto-commit.

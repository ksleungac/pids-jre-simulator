---
name: distill-memory
description: Periodic safety-net audit — scan recent daily-log narrative for behavioral patterns that escaped synchronous codification, audit rules for staleness/contradiction, surface half-promoted both-shaped entries. Discussion-first; user approves each decision.
triggers:
  - /distill-memory
  - distill memory
  - distill the daily logs
  - audit rules
---

## Purpose

Under the synchronous-codification model (`/session-recap` Step 3), every learning / preference / behavioral pattern is supposed to land in its canonical home **the same session it surfaced** — no log-only intermediate. This skill is the **safety net** for cases where that didn't happen:

1. **Escapes** — patterns that recurred across sessions but never got codified, because each individual instance felt one-off at recap time.
2. **Half-promoted entries** — both-shaped corrections (per session-recap Rule 1) where only ONE half landed: canonical content in a domain doc but no behavioral binding in `principles.md` / `conventions.md`, or vice versa. The autodriver-vocabulary case (2026-04-30) is the canonical example: Layer 1/2/3 names lived in AUTO_INPUT.md but the binding rule was never added to conventions.md, so claude forgot to use them in chat.
3. **Stale rules** — preloaded rules that lived practice has rendered obsolete or contradicted. Highest bar; explicit user confirmation.
4. **Thin-support rules** — rules that landed during /session-recap on a single instance and never recurred; possible over-promotion, candidate for pruning.

This is a **logs → rules direction** audit. It does NOT promote single-instance candidates (that's `/session-recap`'s job, in-session). It does NOT audit rules without log-side evidence.

## When to run

- Every 4–6 weeks, or when daily-log accumulation feels heavy (~15+ logs since last run).
- When the user notices a correction repeating across sessions ("I keep telling you X" — but `/session-recap` should have caught it; this is the failsafe).
- After a stretch of dense work where conventions are still solidifying.

NOT for one-off discovery — that's `/session-recap` Step 0/1 territory. NOT for rule audits without log-side evidence — that's a separate operation (rules→code direction).

## Scope

- **In scope:** narrative prose + `## Codifications this session` subsections of daily logs since the last distill pass.
- **Also in scope (one-time, until cleared):** legacy `## Preferences (jot)` structured entries in pre-2026-05-02 daily logs that haven't been processed by the one-time sweep yet.
- **Out of scope:** auditing rules without log-side evidence; one-off discovery.

If a daily log lacks anything codification-related (smooth session, no codifications), skip silently.

## Process

### Step 1 — Aggregate evidence

Glob `memory/2026-*.md` (extend year as time passes), filtered to logs newer than the last distill pass. For each log, extract:

- **Codification pointers** — entries in the `## Codifications this session` subsection (where this session's rules landed).
- **Recurring topics in prose** — keywords / themes that appear across multiple session narratives (ad-hoc Grep across `memory/*.md` for likely candidates).
- **Legacy structured entries** — any `## Preferences (jot)` lines in pre-sweep logs (will dwindle to zero once the one-time sweep completes).

Group by topic/theme.

### Step 2 — Cross-check each topic against current rules

For each topic that surfaced in ≥2 sessions, search:

- `.claude/rules/*.md`
- `.claude/skills/*/SKILL.md`
- `CLAUDE.md`
- Domain docs (`DISPLAY.md`, `DATA_FORMAT.md`, `AUTO_INPUT.md`)
- Inline `# CONTRACT:` blocks (`grep -rn '# CONTRACT:' --include='*.py'`)

Classify the topic:

| Status | Meaning | Default action |
|---|---|---|
| `[in-rules-supported]` | already codified, single-shape rule (or both halves of a both-shaped rule present); recent narrative confirms it lives | no action |
| `[half-promoted]` | both-shaped topic where only ONE half landed: canonical content in a domain doc but no preloaded binding (or vice versa) | flag for user; propose adding the missing half |
| `[in-rules-thin]` | in rules, but only one weak datapoint supports it; never recurred | flag for user review (over-promotion suspect) |
| `[escape]` | ≥2 distinct sessions narrate the topic, no rule home | flag as missed-codification candidate |
| `[stale]` | rule exists but lived practice contradicts it | flag for user (stale-rule removal candidate, highest bar) |

### Step 3 — Present the audit (discussion-first)

```
## Distill audit — <date range>

In-scope logs: N (from <oldest> to <newest>)
Last distill pass: <date>

### Escapes ([escape]) — missed-codification candidates
| topic | sessions seen | proposed home | one-line rule |
|---|---|---|---|
| ... |

### Half-promoted ([half-promoted]) — discuss
| topic | half present | half missing | proposed home for missing half |
|---|---|---|---|
| ... |

### Thin support ([in-rules-thin]) — discuss
| rule | location | only datapoint |
|---|---|---|
| ... |

### Stale rules ([stale]) — discuss
| rule | location | contradicting evidence |
|---|---|---|
| ... |

### Legacy log-only entries (one-time, until cleared)
N entries across K topics in pre-sweep logs. Process per session-recap Rule 1 (rule-shaped → promote-with-dedup; passing remarks → strip from log).
```

Wait for user decisions per item. Don't apply anything until sign-off.

### Step 4 — Apply approved changes

For each approved escape promotion:

1. **Mandatory dedup-by-re-read** of the target file (per `/session-recap` Rule 2). Re-read in full, search for overlapping entries, merge in place if overlap exists.
2. Edit the target rule/doc/skill file with the new entry. Use `principles.md`'s rule + **Why** + **How to apply** format for value-shaped rules; `conventions.md`'s short-form for style/naming.
3. The log entries that surfaced the pattern stay as-is — they're narrative, not promotion candidates.

For each approved half-promotion completion:

- Re-read the target file. Add the missing half (canonical content OR binding rule) with dedup discipline.

For each approved thin-support pruning:

- Remove the rule from its file.
- Note the removal in the next daily log under `## Codifications this session`: `removed: <rule> — reason: thin support`.

For each approved stale-rule removal:

- Remove/correct the rule.
- Note in next daily log: `stale-removed: <rule> — reason: <contradicting evidence>`.

For each legacy log-only entry processed:

- Promote-with-dedup if rule-shaped, OR strip from the daily log if it's a passing remark.
- Replace the entry with a brief narrative line in the log if it has historical value, or delete the line outright.

### Step 5 — Report

```
## Distill applied

- N escape promotions: <list of topic → home>
- N half-promotions completed: <list>
- N thin pruned: <list>
- N stale removed: <list>
- N legacy log-only processed (promote / strip)
- Files touched: <list>
```

Suggest committing via `/commit` — rule edits + log retags should travel in the same commit so the audit trail is intact.

## Rules

1. **Discussion-first per item.** Never apply a promotion / pruning / stale-removal without explicit user approval for that item.
2. **Mandatory dedup-by-re-read.** Same as `/session-recap` Rule 2 — re-read target file before any write.
3. **Single source of truth.** If a topic is already in rules, leave it; don't add a second copy in a different home.
4. **Respect the placement table.** Use `/session-recap`'s table; don't invent new homes (e.g. don't create a new top-level rules file).
5. **Stale-rule removal is the highest bar.** Requires explicit user "yes, remove" — not just lack of evidence in recent logs. Some rules are load-bearing precisely because they're so internalized nobody comments on them in narrative.
6. **Don't re-propose user-rejected items.** If a previous distill pass rejected a candidate (recorded in a daily log's `## Codifications` block as `rejected: <topic>`), surface it in summary count only, not as a new candidate.

## What this skill is NOT

- **Not** a primary route for codification. `/session-recap` Step 3 is the primary route — synchronous, same-session.
- **Not** a scanner of structured `[log-only]` entries (the model that wrote them is retired; once the one-time sweep clears legacy entries, the skill scans prose only).
- **Not** a rules → code audit. That's a different direction (rules → does code follow them?), not in scope here.
- **Not** an auto-commit skill. User runs `/commit` themselves.

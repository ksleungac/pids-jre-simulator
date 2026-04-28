---
name: distill-memory
description: Periodic pass over accumulated `[log-only]` daily-log entries — group by topic, cross-check against current rules, propose promotions / rejections / stale-rule removals. Discussion-first; user approves each decision before any rule/doc edit lands.
triggers:
  - /distill-memory
  - distill memory
  - distill the daily logs
  - audit preferences
---

## Purpose

`/session-recap` writes `[log-only]` entries to `memory/YYYY-MM-DD.md`'s `## Preferences (jot)` section when an entry's permanence is unclear (ambiguous middle — see session-recap "Match the entry's shape to its home"). The log accumulates; many of those entries are genuinely one-off, but some are early sightings of a recurring pattern.

This skill is the **codify** operation that pairs with session-recap's **capture**. It runs the cross-log roll-up: groups entries by topic, cross-checks against current rules, and surfaces three kinds of action:

1. **Promote** — recurring topic with no rule home yet → land it in `principles.md` / `conventions.md` / skill / inline.
2. **Retag** — topic already lives in a rule (often added directly by session-recap as rule-shaped or fact-shaped); update old `[log-only]` entries to `[promoted: <pointer>]` so future passes don't re-propose.
3. **Reject** — considered and declined; mark `[rejected]` so future passes don't re-surface.

A fourth, rarer action: **stale-rule removal** — a rule exists but lived evidence contradicts it. Highest bar; user confirms explicitly.

## When to run

- Monthly, or when daily-log accumulation feels heavy (~10+ structured logs since last run).
- When the user notices a correction repeating across sessions ("I keep telling you X").
- After a stretch of new project area where conventions are still solidifying.

NOT for one-off discovery — that's session-recap territory. NOT for general rule audit ("is `principles.md` still right?") — that's a different skill (rules→code direction). This is **logs→rules direction only**.

## Scope cutoff

Only logs with a structured `## Preferences (jot)` section are in scope. Older prose-only daily logs (pre-2026-04-28) are history; their patterns were extracted in a one-time manual pilot and the resulting rules already live in `principles.md` / `conventions.md`.

If a daily log lacks the section, skip silently — don't try to extract from prose.

## Process

### Step 1 — Aggregate `## Preferences (jot)` entries

Glob `memory/2026-*.md` (extend year as time passes), filter to logs containing `## Preferences (jot)`. For each entry, parse:

```
- [<tag>] topic:<kebab-noun> — "<verbatim quote>" — context: <one-liner>
```

Group entries by normalized `topic:` value (lowercase kebab). Per group, tally:

- `[log-only]` count (active candidates)
- `[promote-candidate]` count (recap pre-flagged these)
- `[promoted]` count (already settled in rules; included for completeness)
- `[rejected]` count (already declined; do not re-propose)

### Step 2 — Cross-check each topic against current rules/docs

For each topic with ≥1 `[log-only]` or `[promote-candidate]` entry, search:

- `.claude/rules/*.md`
- `.claude/skills/*/SKILL.md`
- `CLAUDE.md`
- Domain docs (`DISPLAY.md`, `DATA_FORMAT.md`, `AUTO_INPUT.md`)
- Inline `# CONTRACT:` blocks (`grep -rn '# CONTRACT:' --include='*.py'`)

Classify the topic:

| Status | Meaning | Default action |
|---|---|---|
| `[in-rules-supported]` | already in rules; ≥1 log entry confirms it lives | retag old [log-only] → [promoted: <pointer>] |
| `[in-rules-thin]` | in rules, but only one weak log datapoint supports it | flag for user review (over-promotion suspect) |
| `[recurring-not-in-rules]` | ≥2 distinct sessions, no rule home | promotion candidate |
| `[one-shot]` | single appearance, no rule | leave as `[log-only]`, no action |
| `[stale]` | rule exists but evidence contradicts it | flag for user (stale-rule removal candidate) |

### Step 3 — Propose homes via the placement table

For promotion candidates, suggest a home from `/session-recap`'s placement table:

| Shape | Home |
|---|---|
| Value / judgment rule | `principles.md` |
| Naming / style / tooling rule | `conventions.md` |
| Past-incident lesson | `critical_lessons.md` |
| Decision-moment gate | relevant skill (e.g. `/commit`, `/sta-make`) |
| Code contract | inline `# CONTRACT:` block |
| Domain fact | CLAUDE.md mental model OR domain doc |

### Step 4 — Present the proposal (discussion-first)

```
## Distill summary — <date range>

In-scope logs: N (from <oldest> to <newest>)
Total preference entries: M

### Promotion candidates ([recurring-not-in-rules])
| topic | sessions | proposed home | one-line rule |
|---|---|---|---|
| ... |

### Already supported ([in-rules-supported]) — auto-retag pending
N entries across K topics already in rules. Retag [log-only] → [promoted: <pointer>] in place.

### Stale rules ([stale]) — discuss
| rule | location | contradicting evidence |
|---|---|---|
| ... |

### Thin support ([in-rules-thin]) — discuss
| rule | location | weak evidence |
|---|---|---|
| ... |

### Single-occurrence ([one-shot]) — leave as [log-only]
N topics, no action.
```

Wait for user decisions per candidate / per stale-rule / per thin rule. Don't apply anything until the user signs off, item by item.

### Step 5 — Apply approved changes

For each approved promotion:

1. Edit the target rule/doc/skill file with the new entry. Use `principles.md`'s rule + **Why** + **How to apply** format for value-shaped rules; use `conventions.md`'s short-form for style/naming.
2. Update each contributing log entry's tag from `[log-only]` (or `[promote-candidate]`) to `[promoted: <home pointer>]`. Example:
   ```
   - [promoted: conventions.md § "Naming"] topic:underscore-prefix — "..." — context: ...
   ```

For each rejection:

- Update each contributing log entry's tag to `[rejected: <one-line reason>]`. Reason is brief — "covered by existing X principle," "user decided context-specific," etc.

For each `[in-rules-supported]` retag (auto-action, no per-item approval needed once user OKs the batch):

- Update `[log-only]` → `[promoted: <existing rule pointer>]`.

For each approved stale-rule removal:

- Edit the rule file to remove/correct.
- Note the removal in the most recent daily log under a new `## Distill notes` section: `- removed: <rule> — <reason>`. Future-you needs to know it was an explicit decision, not a regression.

### Step 6 — Report

```
## Distill applied

- N promotions: <list of topic → home>
- N retags: <count, summary>
- N rejections: <list of topic — reason>
- N stale removals: <list>
- Files touched: <list>
```

Suggest committing via `/commit` — rule edits + log retags should travel in the same commit so the audit trail is intact.

## Tag lifecycle (full picture)

```
session-recap writes:
  [log-only]          — default for ambiguous middle
  [promote-candidate] — pre-flagged for distill (forward-framing OR known prior surfacing)

distill-memory transitions to:
  [promoted: <pointer>] — rule landed (or was already there); pointer to home
  [rejected: <reason>]  — considered, not promoted
```

Once an entry is `[promoted]` or `[rejected]`, future distill passes skip it. The decision is final unless the user explicitly re-opens it.

## Rules

1. **Discussion-first per item.** Never apply a promotion / rejection / stale-removal without explicit user approval for that item. Batch-approval is fine for `[in-rules-supported]` retags (mechanical), not for new promotions or stale removals (judgment calls).
2. **Single source of truth.** If a topic is already in rules, retag — don't add a second copy in a different home.
3. **Respect the placement table.** Use `/session-recap`'s table; don't invent new homes (e.g. don't create a new top-level rules file).
4. **Don't re-propose decided topics.** `[promoted]` and `[rejected]` are final. Surface them in summary counts only, not as candidates.
5. **Stale-rule removal is the highest bar.** Requires explicit user "yes, remove" — not just lack of evidence. Some rules are load-bearing precisely because they're so internalized nobody comments on them in logs.
6. **When unsure, defer.** If a `[recurring-not-in-rules]` topic feels borderline (only 2 sessions, both ambiguous in framing), leave as `[log-only]` — let one more session of evidence accumulate before promoting. Cost of premature promotion = bloat; cost of one extra distill pass = trivial.

## Scope

- **Does** scan structured `## Preferences (jot)` entries across all in-scope daily logs.
- **Does** cross-check topics against current rules/docs/skills/inline contracts.
- **Does** propose promotions, retags, rejections, stale removals — discussion-first, item by item.
- **Does** edit rule files + retag log entries after user approval.
- **Does not** scan prose sections of daily logs (out of scope; structured section only).
- **Does not** audit current rules without log-side evidence (rules→code direction is a different skill).
- **Does not** auto-commit. User runs `/commit` themselves.
- **Does not** invent new rule files or rule homes — uses the existing taxonomy.

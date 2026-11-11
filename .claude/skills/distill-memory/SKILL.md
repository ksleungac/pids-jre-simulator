---
name: distill-memory
description: Periodic safety-net audit, log → rules — find patterns in the daily logs and memory index that escaped codification, half-promoted entries, stale or thin-support rules. Discussion-first; the author approves each item. Use on /distill-memory, "distill memory", "audit the logs".
---

## Purpose

Under synchronous codification (`/session-recap` Step 3) every learning lands in its home the session it surfaced. This skill is the safety net for when that did not happen:

1. **Escapes**: a pattern narrated in ≥ 2 sessions that never reached a home, because each instance felt one-off at recap time.
2. **Half-promoted**: a both-shaped entry with only one half landed, content in a doc without a binding rule, or the reverse.
3. **Stale**: a rule lived practice now contradicts. Highest bar.
4. **Thin support**: a rule codified on one instance that never recurred.

The direction is **log → rules**. `/distill-rules` audits the rules corpus against itself and the skills; `/distill-docs` audits domain docs. Neither reads the logs, so neither can find an escape.

Ported from game-in-idea (2026-11-09).

## When to run

- Every ~15 sessions, or when `memory/MEMORY.md` has grown ~15 entries since the last pass.
- When a correction repeats ("I keep telling you X").
- After a dense stretch where conventions are still settling.

Run on a synced checkout. Session start pulls the logs from `private/memory`, so the local files are complete.

## Process

### Step 1 — Aggregate

Read `memory/MEMORY.md` and the daily logs since the last pass (look for a `distill-memory` line in a `**Codifications:**` line to find it). Group recurring topics.

### Step 2 — Cross-check each topic seen in ≥ 2 sessions

Check its home per the placement table in `CLAUDE.md` § "Memory loop": CLAUDE.md, the four always-loaded rules files, the path-scoped domain files, the domain docs, `# CONTRACT:` blocks, the skills.

| Status | Meaning | Default action |
|---|---|---|
| `[supported]` | codified (both halves if both-shaped), recent narrative agrees | none |
| `[half-promoted]` | one half landed | propose the missing half |
| `[thin]` | one weak datapoint, never recurred | flag as an over-promotion suspect |
| `[escape]` | ≥ 2 sessions narrate it, no home | flag as a missed codification |
| `[stale]` | lived practice contradicts the rule | flag for removal (highest bar) |

### Step 3 — Present (discussion-first)

```
## Distill-memory audit — <date range>

Evidence: N session blocks, M index entries. Last pass: <date or "never">

### Escapes
| topic | sessions seen | proposed home | one-line rule |

### Half-promoted
| topic | half present | half missing | proposed home |

### Thin support
| rule | home | only datapoint |

### Stale
| rule | home | contradicting evidence |
```

Wait for a decision per item. Apply nothing before sign-off.

### Step 4 — Apply

- Escape / half-promotion: dedup-by-re-read the target, then merge or add.
- Thin / stale: remove or correct, only on an explicit "yes, remove".
- Log each applied or rejected item as a step line; `/session-recap` folds them into the block's `**Codifications:**` line (`distill-memory: added …`, `removed: … — thin`, `rejected: …`).

## Rules

1. Discussion-first per item. Batch approval within one status is fine if the author signals it.
2. Dedup-by-re-read before every write.
3. One home per fact. Already codified → leave it.
4. Use the placement table; don't invent new files.
5. Stale removal needs an explicit yes. Some rules are load-bearing because nobody needs to mention them.
6. Don't re-propose an item a past `**Codifications:**` line records as rejected.

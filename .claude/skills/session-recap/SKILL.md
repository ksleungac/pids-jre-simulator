---
name: session-recap
description: End-of-session recap — codify learnings synchronously into their home (CLAUDE.md § "Memory loop" table); compress this session's in-progress block in memory/YYYY-MM-DD.md into narrative; add the index entry; publish to private/memory. Use on /session-recap, "session recap", "recap session", "update docs", "wrap up".
triggers:
  - /session-recap
  - session recap
  - recap session
  - update docs
  - wrap up
---

## Purpose

Capture what was learned this session and codify it now, into its home per the placement table in `CLAUDE.md` § "Memory loop". The daily log holds narrative continuity; rules, learnings and preferences are written to their home this recap or omitted. There is no log-only middle state: `/distill-memory` is a safety net, not a route.

Three operations:
- **Codify**: rule or fact → its home.
- **Narrate**: compress this session's `## Session: in progress — <topic>` block in `memory/<today>.md` into a narrative block.
- **Index + publish**: one `memory/MEMORY.md` entry per block, then `uv run _harness/publish_memory.py`.

## Process

### Step 0 — Friction self-check

Did this session involve friction: several rounds on one point, visible frustration, re-justifying from memory instead of re-reading the source? **No → skip to Step 1.** The author will say so if you missed it.

**Friction → run the loop:** (1) write a behavioural self-observation with evidence quoted inline; (2) hand it to `/third-man` in fair-researcher mode, since it is not always claude's fault: validate the patterns, dedup against `principles.md` § Collaboration, separate claude-side from miscommunication-side, propose wording; (3) ask the author only if third-man surfaces a preference question; (4) consolidate; (5) delete the self-observation file. Step-0 items enter the report under New Understandings with `→ propose:`.

### Step 1 — Report

Skip the code-change inventory; git has it. Before writing, grep `memory/` for this session's domain nouns: a fact older than ~2 weeks that only a daily log holds is stranded, and goes under New Understandings with a destination. A fact about how a TOOL behaves on real data never belongs only in a log; its home is the skill step that runs that tool.

**Brevity is mandatory.** One line per bullet: the learning and its destination. The why goes in the home, not the recap. Collapse omitted remarks to a count.

```
## Session Learnings Summary

### New Understandings
- <learning> (already in <home> from this session)
- <learning> → propose: write to <home>

### Corrections / preferences
- "verbatim quote" → rule-shaped → principles.md / conventions.md / domain rules file / skill / # CONTRACT:
- "verbatim quote" → fact-shaped → CLAUDE.md / domain doc / inline
- "verbatim quote" → both → domain doc (content) AND conventions.md (binding)
- (N passing remarks omitted)

### Scratch
- `_dev_scripts/_*.py` written this session: did anything marked Throwaway turn out to matter? (or: "no scratch")

### Issues (GitHub)
- Closed: … · New: … · Partly done → sub-issue under it · Deferred: … · Stale in-progress: … (or: "No changes")

### Updates (land after approval)
- <file § section>: <per item>
- memory/<today>.md: in-progress block → narrative (not shown)
- memory/MEMORY.md: one entry per block · publish
```

**Every New Understanding carries a destination**, `(already in X)` or `→ propose: write to X`. A bullet with neither has no forward value; omit it. No corrections → say so.

**Issue reconcile.** Closure is authoritative: a pushed `Closes #N` already closed it. Check `gh issue list --state closed --search "closed:>=<last-session-date>"` maps to shipped work; open new ones only per `CLAUDE.md` § "Issue scope" (an outcome, refined, and not a sweep finding you could fix); a partly delivered issue gets a sub-issue for the delivered stage, never a peer; parked work keeps `deferred` + a reason comment; an `in-progress` issue untouched for 14 days is either done or `deferred`.

### Step 2 — Approval

Wait for the author to correct or confirm. Change nothing before sign-off.

Exception: "wrap up" (or "auto wrapup", "self wrap up when done") approves the recap and the session's work. Present the report and land the updates in the same turn.

### Step 3 — Write the homes

Write only what was confirmed. **Dedup-by-re-read first:** read the target in full, not from the copy in context, merge into an overlapping entry if there is one, and add a new entry only if none overlaps. A domain doc's `EDIT-CONTRACT` is read before editing it; additions over ~10 lines are shown as a diff.

**Cross-layer alignment:** a pattern with a post-hoc smell shape and a per-diff shape gets written at all three layers (principle or convention, `/vibe-check` smell, `/review-dirty` lens) with cross-citation.

### Step 4 — Compress the session block

In `memory/<today>.md`, replace this session's in-progress block with:

```markdown
## Session: <one-line summary>

<Prose: what was tried, decisions and why, dead ends, unresolved threads. Under ~15 lines.>

**Codifications:** principles.md § "X" — new entry; CLAUDE.md — Y (or: none)
```

The heading must be unique within the day, because the publisher keys on it. A block still headed `## Session: in progress` never publishes, so this step is what releases it. A session spanning midnight recaps into the day its block is in. Leave a parallel session's in-progress block alone. Never reword a published block; add a new one.

**Refuse:** blow-by-blow review cycles, "what got done" lists, design-discussion rehash, rules as standalone entries. **Keep:** why a decision was made, context with no other home, incident traces (the pathology, not the play-by-play), the codifications line.

### Step 5 — Index and publish

1. One entry per session block in `memory/MEMORY.md`, newest first: `- [YYYY-MM-DD label](YYYY-MM-DD.md) — headline`. Labels are unique; add a short tag when a day has more than one block. **150 chars is a hard cap**: the publisher refuses a longer entry and leaves it queued. The overflow belongs in the daily log. (Measured 2026-07-25: the cap sat stated and unread at 97–100% violation for three months, which is why the refusal lives at the publish boundary.)
2. Run `uv run _harness/publish_memory.py` and report its output line. Offline, it no-ops and the local files keep the queue; the next session start publishes. Any `WARNING` line goes to the author.
3. Stop there. The recap does not commit its rules or doc edits; committing stays a manual `/commit`. game-in-idea's recap commits and pushes, and the author kept this repo manual when the loop was ported (2026-11-09).

## Shape classification

- **Rule-shaped** ("always / never / from now on", an implicit pattern) → `principles.md` / `conventions.md` / a path-scoped domain rules file / skill / `# CONTRACT:`.
- **Fact-shaped** (IRL convention, design decision, library quirk) → CLAUDE.md / domain doc / inline.
- **Both-shaped** → content in the domain doc, binding in a rules file.
- **Passing remark** → omit.

When in doubt, rule-shaped: over-promotion is bloat that `/distill-rules` can audit, under-promotion is recurrence the author pays for.

**Region-scoped vs primitive-scoped:** a rule naming a primitive callable anywhere needs `conventions.md` plus an inline `# CONTRACT:` at known call sites; a rule whose precondition is "editing this region" needs only the inline one.

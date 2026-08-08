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

Capture what was learned this session and codify synchronously into canonical home. Daily log = narrative continuity for next-session pickup. Rules / learnings / preferences live in canonical home, written this session, not deferred. Codify-or-omit; no log-only middle bucket.

Two operations: **Codify** (rule/fact → canonical home) and **Narrate** (session story → `memory/YYYY-MM-DD.md`).

## Process

### Step 0 — Friction self-check

Before discussing learnings, self-assess: did this session involve friction? (multiple rounds on single point, user frustration, defensive posture instead of re-reading source)

**No friction → skip to Step 1.**

**Friction → run loop:** (1) Write structured behavioral self-observation with project-specific evidence. (2) Hand to `/third-man` as fair researcher — validate patterns, disambiguate against existing `principles.md § Collaboration`, identify claude-side vs miscommunication-side, propose wording. (3) Ask user if third-man surfaces preference questions. (4) Consolidate codifications. (5) Delete ephemeral self-observation file. Step-0 codifications enter Step 1 report under "New Understandings" with `→ propose:` annotations.

### Step 1 — Discuss learnings

Skip code-change inventory (git covers it). **Brevity mandatory** — each bullet fits one line: learning + destination annotation. No parenthetical WHY tails (WHY belongs in the codification target, not the recap).

```
## Session Learnings Summary

### New Understandings

**Every bullet MUST carry a destination annotation — no exceptions.**
A bullet without a save produces zero forward value (next session has no record).

Every bullet = one of:
- `(already in X.md from this session)` — pointer for user review.
- `→ propose: write to X.md` — proposed for codification in Step 3.

No destination → OMIT the bullet entirely.

### Prior-session graduation check

For each learning this session, ask: **did a past daily log already contain it?** If yes, that fact was stranded — codify it now, and name the log line that held it.

Cheapest form: grep `memory/` for the session's domain nouns (a detector name, a line name, an artifact pattern) before writing the recap. A hit older than ~2 weeks with no canonical home is a stranded fact by definition — the log is the only reason you know it.

Rule of thumb: **a fact about how a TOOL behaves on real data never belongs only in a log.** Its home is the skill step that runs that tool. (2026-05-09 recorded "yamanote is normalized hot, so the detectors bracketed the music instead of the KAK"; it reached no skill, and 2026-07-26 spent a session re-deriving it on keihin.)

### Corrections / preferences this session

Classify each and propose canonical home. Every entry promotes or is omitted.
- "verbatim quote" → **rule-shaped** → `principles.md` / `conventions.md` / skill / `# CONTRACT:`
- "verbatim quote" → **fact-shaped** → CLAUDE.md / domain doc / inline
- "verbatim quote" → **both-shaped** → domain doc (canonical) AND conventions.md (binding)
- (N passing remarks omitted — collapse to count, don't enumerate)

If no corrections, state explicitly. All omits → "all N corrections omitted as passing remarks."

### Issue backlog reconcile (GitHub Issues)
Closure is authoritative — a pushed commit with `Closes #N` already closed the issue, so there's no fuzzy matching. Then:
- **Closed this session**: `gh issue list --state closed --search "closed:>=<last-session-date>"` — confirm each maps to work that shipped (GitHub already closed them; no action needed).
- **New**: deferred design Qs / dangling follow-ups surfaced this session → `gh issue create --label <area>`. Scope each as an **outcome**, not a unit of work; a multi-stage outcome gets a parent + sub-issues rather than sibling tickets — `CLAUDE.md § "Issue scope"`.
- **Partly done**: an issue whose scope you only partly delivered is NOT closed and NOT filed-around — split the delivered stage into a sub-issue under it. Closing it and opening a peer orphans the outcome.
- **Deferred**: work parked mid-flight → issue keeps a `deferred` label + a reason comment (not closed).
- **Stale**: `gh issue list --label in-progress --search "updated:<<14d-ago>"` — an `in-progress` issue gone quiet is either done (close it) or truly parked (→ `deferred`).
- **No changes**: state explicitly.

### Documentation updates (will land after Step 2 approval)
- List target files and sections.
- memory/YYYY-MM-DD.md: not shown to user at recap time.
- memory/MEMORY.md: always — one index entry per session block.
```

### Step 2 — User reviews and confirms

Wait for sign-off. Don't update anything until confirmed.

### Step 3 — Update files

After approval, update only confirmed files. Each piece of information has ONE home.

**Mandatory dedup-by-re-read:** Re-read target file in full (not cached impression) → search overlapping entries → merge if overlap, write new if not. One extra read = trivial; duplicate drift = high cost.

**Domain doc edits:** Re-read `EDIT-CONTRACT` first. Confirm not on refuse list. Name section. Additions > ~10 lines → present diff to user. Use doc's voice per EDIT-CONTRACT § Voice.

**Cross-layer alignment:** When codifying a pattern, ask "does it have smell shape (post-hoc) and per-diff shape (review-time)?" If yes, write at all three layers (authoring-time principle/convention, `/vibe-check` smell, `/review-dirty` lens) with cross-citation.

**Daily log writes silently** — narrative + decisions + why-context. See Daily log format below.

**MEMORY.md always gets an entry** — one line per session block, written immediately after the daily log. Format at bottom of this file.

**Publish narrative** — after the daily log + MEMORY.md writes, run `uv run _harness/publish_memory.py`. It appends the new blocks/entries to the dedicated `origin/memory` journal ref (works from any branch/folder; memory never rides code commits, master history stays pure code). Offline → it no-ops and the local files keep the queue; the next recap or session start publishes. Memory files are APPEND-ONLY — never reword an already-published block/entry (the publisher refuses edits with a warning).

---

## Where things live (single source of truth)

Consult this before ANY doc write, not only at recap time.

| What | Where | NOT in |
|------|-------|--------|
| Project overview, file structure, mental model (project framing, train family, IRL scope, display conventions) | `CLAUDE.md` | rules files, domain docs |
| Region-scoped code contracts (mode-cycler timing, countdown formula, clear-bg confinements, skip-animation) | inline `# CONTRACT:` at code site | rules files, domain docs |
| Primitive-scoped rules (never SysFont, never `Path(__file__).parent`, path resolution via `app_paths`) | `conventions.md` AND inline `# CONTRACT:` at known call sites | rules files alone |
| Mock route layout, test-station roles | `audio/_mock/main/README.md` | rules files |
| Per-line IRL + sim quirks | `audio/README.md` | rules files, CLAUDE.md |
| Values that shape judgment | `.claude/rules/principles.md` | CLAUDE.md |
| Style, naming, tooling | `.claude/rules/conventions.md` | CLAUDE.md |
| Red lines | `.claude/rules/redlines.md` | CLAUDE.md |
| Past-mistake lessons | `.claude/rules/critical_lessons.md` | anywhere else |
| Build/distribution | `.claude/skills/build/SKILL.md` | CLAUDE.md |
| Auto-input / OCR domain | `auto_input/README.md` | CLAUDE.md |
| JSON field definitions | `DATA_FORMAT.md` | CLAUDE.md |
| LCD cross-model infra | `DISPLAY.md` | CLAUDE.md |
| LCD per-sub-series | `DISPLAY_E235.md` | DISPLAY.md |
| App-level runtime + setup/chrome flow | `APP.md` | rules files, CLAUDE.md, DISPLAY.md |
| Test suite + tier hierarchy | `_tests/README.md` | rules files, CLAUDE.md |
| Daily session logs | `memory/YYYY-MM-DD.md` | rules files |
| Long-term memory index | `memory/MEMORY.md` | — |
| Open work items | **GitHub Issues** (`gh issue`) | `TODO.md`, daily logs |

**Region-scoped vs primitive-scoped test:** if the rule names a language/library primitive callable anywhere → primitive-scoped (needs `conventions.md` + inline CONTRACT). If precondition is "editing this code region" → region-scoped (inline-only sufficient).

---

## Shape classification

- **Rule-shaped** ("always / never / from now on") → `principles.md` / `conventions.md` / skill / `# CONTRACT:`
- **Fact-shaped** (IRL convention, library quirk) → CLAUDE.md / domain doc / inline
- **Both-shaped** (canonical content + behavioral binding) → domain doc AND conventions.md
- **Passing remark** → OMIT

When in doubt, classify rule-shaped. Cost asymmetry: over-promotion = bloat (auditable via `/distill-rules`); under-promotion = recurrence. User's Step 2 review = safety net.

---

## Daily log format (`memory/YYYY-MM-DD.md`)

```markdown
# 2026-04-28

## Session: <one-line summary>

[Prose — what was tried, decisions, dead ends, why-context.]

## Codifications this session

- principles.md § "X" — added entry from <topic>
- (or: "no codifications this session")
```

**EDIT-CONTRACT — Refuse:** blow-by-blow review cycles, "what got done" bullet lists (git covers it), full design-discussion rehash, documentation enumerations, rules/preferences as standalone entries (those went to canonical homes).

**Keep:** WHY decisions, non-obvious context with no other home, incident traces (pathology not play-by-play), codification pointers.

**Size target:** <50 lines per session-block.

**MEMORY.md format:** `- [YYYY-MM-DD time-block](file.md) — headline`. Multi-session days get one entry per block.

**150 chars is a hard cap, enforced at publish.** `publish_memory.py` REFUSES an over-cap entry with a loud warning and leaves it queued — the entry does not reach `origin/memory` until it fits. Count before writing; if the headline doesn't fit, the surplus is detail belonging in the daily log the entry links to, never a wider index line. This is the progressive-disclosure boundary: index = pointer, daily log = detail, canonical homes = rules.

Enforced mechanically because stating it did not work. Measured 2026-07-25 across all 143 entries: 0% over cap in Mar–Apr, then 97% / 100% / 100% for May / Jun / Jul, median rising 135 → 313 → 783 → 1538 while the cap sat in this file unread. Published entries are append-only, so that history stands; the gate applies from here.

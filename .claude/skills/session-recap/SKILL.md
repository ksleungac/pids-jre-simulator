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

### Corrections / preferences this session

Classify each and propose canonical home. Every entry promotes or is omitted.
- "verbatim quote" → **rule-shaped** → `principles.md` / `conventions.md` / skill / `# CONTRACT:`
- "verbatim quote" → **fact-shaped** → CLAUDE.md / domain doc / inline
- "verbatim quote" → **both-shaped** → domain doc (canonical) AND conventions.md (binding)
- (N passing remarks omitted — collapse to count, don't enumerate)

If no corrections, state explicitly. All omits → "all N corrections omitted as passing remarks."

### TODO.md sweep
Run `uv run _harness/sweep_todo.py` — pre-digested report of section counts, likely-closed items (cross-referenced against recent commits), and stale `[x]` items. Read the report instead of parsing TODO.md manually. Then:
- **Closed**: items shipped — propose `[x]` mark or removal.
- **New**: deferred design Qs, dangling follow-ups surfaced this session.
- **Rephrase**: items whose framing rotted. **No changes**: state explicitly.

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
| Daily session logs | `memory/YYYY-MM-DD.md` | rules files |
| Long-term memory index | `memory/MEMORY.md` | — |
| Open work items | `TODO.md` | daily logs |

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

**MEMORY.md format:** `- [YYYY-MM-DD time-block](file.md) — headline`. ~150 char cap. Multi-session days get one entry per block.

---
name: third-man
description: Spawn a fresh-context Opus 4.7 agent to give an independent take when Claude and the user are talking past each other on a contested logic interpretation, OR to validate behavioral self-observations from /session-recap Step 0. User-triggered or claude self-proposed at impasse.
triggers:
  - /third-man
  - third man
  - get a third take
---

## Why this exists

Sometimes Claude and the user end up battling over a logic interpretation where neither is converging. Common pattern:

- User explains a rule in their own words.
- Claude interprets it slightly off, but with confidence.
- User pushes back.
- Claude re-interprets, still slightly off.
- User runs out of patience and approves something they don't fully understand.
- Two iterations later it surfaces that the misread was a single subtle word — e.g. "match the least badge" meant *full-element width*, but Claude read it as *badge-only width*. (Real incident, 2026-04-30.)

A fresh-context Opus 4.7 agent — never having seen Claude's prior framing — can read the user's literal words against the code and surface the gap that Claude can't see *because* of their prior framing.

## When to invoke

Two pathways, both supported:

- **User-triggered.** User invokes `/third-man` when they sense the conversation is talking past itself.
- **Claude self-proposed.** When claude has restated the same contested point 3+ rounds with no convergence — or notices itself defending a position instead of re-reading source — claude proactively offers `/third-man` rather than attempting a 4th restatement. Single-line offer: *"I think we may be talking past each other; want to spawn /third-man for an independent take?"* User signs off; claude does NOT unilaterally invoke. See `principles.md § "Self-propose /third-man at impasse"`.

A third pathway is via `/session-recap` Step 0: when claude self-detects friction at recap time, claude writes a behavioral self-observation and hands it to a third-man (in fair-researcher / doctor mode) to validate patterns + dedup against existing principles.md entries before any codification lands. This is not interpretation-deadlock recovery — it's pattern validation — but uses the same brief-assembly + neutrality discipline.

## Instructions when invoked

### Step 1 — assemble the brief

Pull together the inputs the third agent needs. **Neutrality is the whole point** — bias the brief, get a useless answer.

1. **User's words, VERBATIM.** Quote the most recent ~5 user messages relevant to the contested point. No paraphrase. No "the user means…". Direct quotes, with surrounding context if a single sentence would be ambiguous.

2. **Claude's interpretation, third-person.** Write as a neutral observer would: *"Claude interpreted this as X and proposed Y."* NOT *"I think the user meant X, so I did Y."* Drop the "I" — the agent shouldn't side with you by default.

3. **Relevant file paths.** Absolute paths to the code/data at issue. Include line numbers if the contested point is local. The agent should read primary sources, not your summary.

4. **The decision at stake.** One sentence: what's about to change, or what the user is about to approve.

### Step 2 — spawn the agent

```
Agent({
  description: "Third-man independent take",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <the brief from Step 1, ending with the task block below>
})
```

**Task block to append to the brief:**

```
YOUR TASK:

1. Read the user's quoted words FIRST. Form your own reading of what they want, before anything else colors it.

2. Read the listed files to ground that reading in the actual code/data state.

3. Read Claude's interpretation last.

4. Report, in this structure:
   - **Most natural reading of user's words:** <your reading>
   - **Claude's interpretation:** <restated>
   - **Match / mismatch / third reading:** which of the three, and where the gap is if mismatched
   - **Recommended next move:** one concrete action

Keep it under 300 words. Be direct — if Claude is wrong, say so. If the user's words are genuinely ambiguous between readings, say that too.
```

### Step 3 — relay verbatim

Pass the agent's report to the user **without commentary or selective quoting**. The user reads the third take, then decides. You don't argue with the third agent's findings before the user has seen them.

If the third man says you (Claude) misread, accept that as data — don't relitigate. Course-correct in the next turn based on the new reading.

## Brief-writing failure modes to avoid

- **Leading the witness.** "The user said X (which is ambiguous)…" — don't editorialize. Quote.
- **Burying Claude's interpretation in justification.** Just state it: "Claude interpreted X as Y and was about to do Z." Don't pre-defend.
- **Filtering quotes.** Include the user's pushback messages too — those are the strongest signal that something is off.
- **Skipping file reads.** The agent NEEDS to read primary sources. If the contested point is "what does the code currently do," your verbal summary is the same lens that already misread once.

## Out of scope (for MVP)

- Self-triggering by Claude when stuck — future refinement once skill is proven.
- Iterative ping-pong between agents — single-shot only.
- Auto-applying the third man's recommendation — user is always the decision-maker.

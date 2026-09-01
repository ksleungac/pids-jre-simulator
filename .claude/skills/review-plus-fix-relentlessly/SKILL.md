---
name: review-plus-fix-relentlessly
description: Review dirty code and fix iteratively using Ralph loop pattern.
  When user say to "loop to fix dirty" or "review+fix"
triggers:
  - /review-plus-fix-relentlessly
  - loop to fix dirty
  - review+fix
---

## Ralph Loop Implementation
This skill implements a Ralph loop pattern:
1. **Reviewer Agent**: Examines dirty changes, identifies issues (no modifications)
2. **MAIN AGENT (you)**: Reads feedback and fixes issues yourself
3. **Loop**: Continues until no issues found or max cycles reached

**The fresh reviewer context IS the mechanism — do not optimize it away.** A separate agent holding no prior context and no momentum finds what the author cannot see, and no model generation substitutes for that. Guidance saying "don't use a subagent to verify your own work" is about SELF-verification (one context re-reading itself); this loop is the opposite, and the cycle count, the re-spawn, and the reviewer's independence are all load-bearing. See `principles.md § "Fresh context is the review instrument"`.

## Shell preference (IMPORTANT — Windows host)
**Prefer PowerShell over bash for every shell command in every cycle.** The Git-for-Windows bash shell on this machine crashes with `fatal error - add_item ... errno 1`, which will abort a review cycle. Use the PowerShell tool for `git status`, `git diff`, file listing, and all other shell operations. The bash code blocks below are illustrative pseudocode for the loop structure — do NOT invoke the Bash tool to run them. Translate to PowerShell or drive the loop step-by-step through tool calls.

This applies transitively: when you spawn the review-dirty subagent, that agent must also use PowerShell (its SKILL.md has the same directive baked in).

## Scope rule (IMPORTANT — only review what you have working context for)

**Only ask the reviewer about files that you (the main agent in this session) actually built, edited, or have working context for.** The dirty / untracked tree often contains unrelated work — files left behind by another Claude session, a parallel agent's WIP, the user's personal in-progress edits. You don't have the context to judge those correctly, and applying "fixes" to them based on a reviewer's surface read can corrupt someone else's in-flight work.

When you scope each cycle's review:

- **Include**: files you edited / created in this session, plus any closely-related files you touched (e.g. a doc you updated to describe code you wrote).
- **Exclude** even if dirty:
  - Untracked files you didn't create — they belong to someone else's workstream.
  - Modified files where the changes pre-date this session and weren't yours.
  - Anything in known artifact directories (`_references/lcd/`, `_recordings/`, build outputs).
  - Testing harnesses (`preview_*.py`) per project preferences.
  - Anything the user has explicitly carved out earlier in the conversation.

If the user explicitly says "review everything", surface findings on out-of-context files but **flag them as out-of-context and do NOT apply fixes** unless the user confirms file-by-file. Reviewer findings on code you don't own are still useful information, just not actionable by you alone.

Concrete rule for the reviewer prompt: enumerate the in-scope files explicitly and list out-of-scope ones with a one-line "why excluded" each. Don't pass `git diff --name-only | xargs` style "review whatever's dirty" — that conflates your work with everyone else's.

### Line-scope mode (DIRTY vs FULL) — passed through to review-dirty
The Scope rule above governs WHICH FILES. WHICH LINES within them is a separate mode, defined in `review-dirty` § "Scope mode": **DIRTY** (diff hunks, default) against **FULL / MODULE / END-TO-END** (every line of the named files, committed-but-unchanged code included). When the user says "scan the module", "end-to-end", "review the whole X", or names specific files/dirs, pass that intent through in the `review-dirty` call's `args`. Its reviewer then embeds the whole files, runs the deterministic scanners over the module (Derivation-bypass scan), and applies the lenses to every line rather than just the diff. A hardcoded literal that shipped weeks ago is unchanged history, and a DIRTY-mode loop is structurally blind to it. **A stated full scope is literal; never narrow it to the diff.**

**INTEGRATION escalation is automatic, not user-gated.** If the fix set flips a default flow, adds or removes a first-run/onboarding screen, or rewires an entry-point branch, pass that intent through so `review-dirty`'s INTEGRATION scope runs the integration-residue checklist over the flow module. The reviewer escalates even when the user didn't ask, because the stale redundant branch is invisible in both the diff AND the dev environment. (`review-dirty` § "Scope mode"; `critical_lessons §6`.)

### Fix-confidence gating on surfaces you didn't build
The Scope rule (above) excludes files you didn't touch. A sharper axis applies when the run IS in scope but you lack the DESIGN context — a release-prep / whole-code scan of features built across prior sessions, not your own diff. There, gate each finding on **fix-confidence**, not file-ownership:
- **obvious-safe** — mechanical, zero behavioral ambiguity (hard-rule violation, palette / canonical-source derivation, dead code with grep-confirmed zero callers, stale docstring/comment) → apply inline.
- **needs-context** — requires the module's design / layout-calibration / state-machine intent → do NOT fix blind. **Ask the user** (see Triage policy: a needs-context finding is exactly the class where they are the missing input). A ticket is the last resort, not the first.

A "looks safe" fix on code you don't understand is how review+fix introduces new bugs. Have the reviewer tag every finding with this flag (obvious-safe | needs-context) so triage is mechanical. (2026-07-16: user — *"your fixer does not have context for working on these tasks, might introduce new bugs, so delve to TODO for nonobvious tasks."*) The don't-fix-blind half is intact; what changed is the outlet — the 2026-07-16 quote predates the finding that the TODO/issue path silently accumulates.

### Release-prep / whole-code scope: fold in `/vibe-check`
`review-dirty`'s lenses are diff/module-oriented. For a FULL release-prep sweep ("whole code scan for release", "prepare for release"), the reviewer must ALSO apply **`vibe-check`'s smell list** — the codebase-mess lens (dead code, duplication, canonical-source drift, integration residue) that a lens-by-lens review under-weights. Fold vibe-check's smells into the reviewer brief; don't run `review-dirty` alone. NOT for dirty-diff reviews — those don't need the whole-codebase sweep. (2026-07-16: user — *"reviewer should take advantage of vibe check."*)

## Workflow when invoked:

### Step 1: Initialize loop variables
```bash
# Set up loop control
MAX_CYCLES=10
CYCLE_COUNT=0
ISSUES_FOUND=true
```

### Step 2: Main loop
```bash
while [[ $ISSUES_FOUND == "true" && $CYCLE_COUNT -lt $MAX_CYCLES ]]; do
  CYCLE_COUNT=$((CYCLE_COUNT + 1))
  echo "=== Cycle $CYCLE_COUNT/$MAX_CYCLES ==="

  # Step 2a: Call reviewer (uses /review-dirty skill)
  echo "Running code review..."
  Skill({
    skill: "review-dirty",
    args: "$ARGUMENTS --cycle=$CYCLE_COUNT"
  })

  # Collect reviewer feedback (simplified - in practice would parse actual output)
  REVIEW_FEEDBACK="$(cat .claude/.ralph-feedback.json 2>/dev/null || echo '{\"issues_found\": false}')"

  # TWO SEPARATE GATES — do not collapse them.
  #   HAS_BLOCKING decides whether the LOOP RUNS AGAIN (architectural-critical | critical only).
  #   HAS_ANY decides whether the FIX PASS RUNS THIS CYCLE (any finding at all).
  # A warning-only cycle must still run Step 2b — findings get fixed, not logged — and then stop.
  # Collapsing these is how "warnings still get fixed" became prose the loop didn't honour.
  HAS_BLOCKING=$(echo "$REVIEW_FEEDBACK" | grep -oE '"severity": *"(architectural-critical|critical)"' || echo "")
  HAS_ANY=$(echo "$REVIEW_FEEDBACK" | grep -oE '"severity": *"' || echo "")
  ISSUES_FOUND=$([ -n "$HAS_BLOCKING" ] && echo "true" || echo "")

  # Step 2b: If the reviewer returned ANY finding, YOU (main agent) fix them now
  if [[ -n "$HAS_ANY" ]]; then
    echo "Issues found. YOU (main agent) should fix them based on the feedback."

    # Read and parse the reviewer feedback
    echo "Reviewer feedback from Cycle $CYCLE_COUNT:"
    echo "$REVIEW_FEEDBACK"

    # Review the feedback and current git status:
    # git status --short

    # As the main agent, you should:
    # 1. Read the reviewer feedback carefully
    # 2. Examine the current git diff to understand what needs fixing
    # 3. Use the Edit tool to fix ONLY the issues mentioned in feedback
    # 4. Follow repository style and values from .claude/rules/principles.md + .claude/rules/conventions.md and inline `# CONTRACT:` blocks at the relevant code sites
    # 5. Test changes before considering them complete
    # 6. Stage changes (git add ...) when ready for next review cycle

    echo "After you finish fixing, stage changes and continue to next cycle."
  else
    echo "No issues found. Ralph loop complete!"
    ISSUES_FOUND=false
  fi

  # Step 2c: Triage anything you did NOT fix this cycle (runs each cycle)
  # Default is that this list is EMPTY — findings get fixed, not deferred.
  # For each one you left: route per the Triage policy section below (fix / ask the
  # user / drop). Filing an issue requires that the finding needs the USER's input.

  # Step 2d: Report cycle completion and prepare for next cycle
  if [[ $ISSUES_FOUND == "true" ]]; then
    echo "--- End of cycle $CYCLE_COUNT ---"
    echo "Ready for next review cycle..."

    # Store feedback for next iteration (if using file-based context)
    echo "$REVIEW_FEEDBACK" > .claude/.ralph-context-cycle$CYCLE_COUNT.json

    # Wait a moment before next cycle
    sleep 2
  fi
done
```

## Triage policy for deferred findings

**The default is FIX IT, in the cycle. A deferred item is an exception that has to earn itself.**

A finding you are able to act on is work, not a ticket. File an issue for one reason only: **the finding needs the USER as its input** — a design direction, a product-use-critical call, something with a real implication for how they use the thing. That is not a severity. A critical bug you can fix gets fixed, not filed; a small change that alters how the product behaves for them may genuinely need asking.

Anything you cannot fix AND that does not need the user is **dropped** — named in the cycle report, not recorded. A backlog entry nobody is going to open is worse than no entry: it costs a line in every session-start summary and reads as owed work forever. 2026-08-11: a release-prep scan filed 35 findings in one day, and 12 were still open three weeks later, untouched since the minute they were created, none of them needing the user. User — *"it should not produce deferred items unless that items need input for me, it's a big design direction, product use critical, that has actual implication to me."* Supersedes the severity-keyed routing table, and generalizes the too-narrow 2026-07-23 own-residue exception that was scoped to just your own just-landed refactor.

### Routing rule

For each finding, in order:

0. **Is it a Lens-1 finding with no `trigger`?** → drop it, one line in the cycle report. `review-dirty` § "Trace gate" forces these to `info`; a mechanism nobody can reach is not a defect, and "fixing" it means adding a guard for a case that cannot occur. Do NOT harden against an untriggerable path.
1. **Can you fix it?** → fix it now, in this cycle. Regardless of severity. This is the overwhelming majority.
2. **Can't fix it, and it needs the user's judgment** (design direction · product-use-critical · real implication for them) → **ask them in the session**. That is the outlet, not a ticket. File an issue only if they defer it, or if the session is ending with the question unanswered.
3. **Can't fix it, doesn't need the user** → drop it. One line in the cycle report saying what you saw and why you left it. No issue.

An issue that does get filed carries the `review-finding` label plus its area label (`auto-input` / `display` / `chrome-i18n` / …). The daily-log routing path (`memory/YYYY-MM-DD.md`) is **not used** — daily logs are narrative continuity only per `session-recap/SKILL.md`.

**This does not license fixing blind.** "Can you fix it" means you understand the code well enough to be right, not that an edit is available — see the fix-confidence gating above. The change is where a `needs-context` finding goes: to the user as a question, not to the backlog as a ticket.

### Dedup logic

For each finding to be filed, dedup by `<file>:<line>` + summary:

1. **Already an open issue?** — `gh issue list --state open --label review-finding --search "<file basename>"`, scan titles/bodies. Match → skip; add a comment bumping recurrence (`recurred <date>`).
2. **Otherwise (first occurrence)** → create per the format below.

### Issue format

```
gh issue create --label review-finding --label <area> \
  --title "<summary> — <file>:<line>" \
  --body "lens N, severity; rule: <citation if any>; first flagged YYYY-MM-DD — Deferred because: <why>"
```

### Lifecycle

The issue closes when the fix lands — `Closes #<N>` in the fix commit (auto-closes on push to `master`) or `gh issue close`. If the user says "not a real issue", close it (`--reason "not planned"`) or delete — matches the project's "no log-only middle bucket" rule.

### Step 3: Final summary
```bash
echo "=== Ralph Loop Completed ==="
echo "Total cycles: $CYCLE_COUNT"
echo "Maximum cycles: $MAX_CYCLES"

if [[ $CYCLE_COUNT -ge $MAX_CYCLES ]]; then
  echo "Stopped due to reaching maximum cycles ($MAX_CYCLES)"
else
  echo "Stopped because no more issues were found"
fi

# Clean up temporary files
rm -f .claude/.ralph-*.json 2>/dev/null || true
```

## Key Features:
- **Cycle Counting**: Tracks and reports review+fix iterations
- **Stop Conditions**: Stops when no blocking issues remain (`architectural-critical` or `critical`) or max cycles reached (10). `warning`/`info` findings don't block the stop — they still get fixed in-cycle where you can (see Triage policy).
- **Role Separation**: Reviewer (opus) reads only, Fixer (opus, main agent) applies fixes
- **Context Passing**: Feedback passed between agents for iterative improvement
- **Graceful Degradation**: Clean up temporary files, handle errors

## Configuration:
- **MAX_CYCLES**: 10 (configurable)
- **Reviewer Model**: opus — project favors deeper architectural reasoning over cost; required for the three-lens review structure (see `.claude/skills/review-dirty/SKILL.md`)
- **Fixer Model**: opus (better for complex fixes)
- **Timeout**: 30 minutes total for entire loop

## Notes:
- The loop is self-contained - each cycle builds on the previous
- Reviewer feedback must be structured for the fixer to parse
- Git state should be preserved (no auto-commits unless requested)
- System should handle cases with no dirty changes gracefully

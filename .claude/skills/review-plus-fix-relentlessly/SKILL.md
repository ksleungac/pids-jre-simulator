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
  - Anything in known artifact directories (`lcd_references/`, `_recordings/`, build outputs).
  - Testing harnesses (`preview_*.py`) per project preferences.
  - Anything the user has explicitly carved out earlier in the conversation.

If the user explicitly says "review everything", surface findings on out-of-context files but **flag them as out-of-context and do NOT apply fixes** unless the user confirms file-by-file. Reviewer findings on code you don't own are still useful information, just not actionable by you alone.

Concrete rule for the reviewer prompt: enumerate the in-scope files explicitly and list out-of-scope ones with a one-line "why excluded" each. Don't pass `git diff --name-only | xargs` style "review whatever's dirty" — that conflates your work with everyone else's.

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

  # Extract blocking issues — loop continues while ANY architectural-critical OR critical exists.
  # warning/info findings don't block stop (they route to deferred-findings logging in Step 2c).
  HAS_BLOCKING=$(echo "$REVIEW_FEEDBACK" | grep -oE '"severity": *"(architectural-critical|critical)"' || echo "")
  ISSUES_FOUND=$([ -n "$HAS_BLOCKING" ] && echo "true" || echo "")

  # Step 2b: If issues found, YOU (main agent) fix them
  if [[ -n "$ISSUES_FOUND" ]]; then
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

  # Step 2c: Triage deferred findings (NEW — runs each cycle)
  # If you (main agent) chose to defer any finding rather than fix it
  # (uncertain, parallel-WIP collision, scope creep, user said "not now"), route per the
  # Triage policy section below. Do NOT silently drop deferred findings.

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

When you (main agent) decide to defer a finding rather than fix it during a cycle, route it per its severity:

### Routing rules

| Severity | If user explicitly defers | If you auto-defer (uncertain / out-of-scope / parallel WIP) |
|---|---|---|
| `architectural-critical` | TODO.md `## Deferred review findings` (real obligation, must surface at startup) | TODO.md (same — these block release-quality, do not silently bury in daily log) |
| `critical` | TODO.md `## Deferred review findings` | TODO.md (same) |
| `warning` | Daily log with `[review-deferred]` tag (recurrence may promote later) | Daily log with `[review-deferred]` tag |
| `info` | Daily log with `[review-deferred]` tag | Drop (the ASK-flag was answered "not real") |

### Dedup logic

For each finding to be logged, dedup by `<file>:<line>` + issue summary:

1. **Already in today's `memory/<today>.md` under `## Deferred from /review+fix [HH:MM]`?** → skip (no within-session duplicates).
2. **Already in TODO.md `## Deferred review findings`?** → skip (no duplicate in backlog).
3. **Already in any `memory/2026-*.md` from prior days under `[review-deferred]`?** → recurrence detected. Propose promotion to TODO.md, ask user:
   - **Approved**: add to TODO.md `## Deferred review findings`; retag prior daily-log entries `[review-deferred]` → `[review-promoted: TODO.md § "Deferred review findings"]`.
   - **Declined**: append today's entry as `[review-deferred]` with new reason captured.
4. **Otherwise (first occurrence)**: append per the routing table above.

This keeps the recurrence-promotion ladder self-contained in the loop — no separate distill pass needed for review-backlog management. The loop is self-promoting.

### Daily-log entry format

Append to `memory/<today>.md` under section heading `## Deferred from /review+fix <HH:MM>` (create section if not present):

```
- [review-deferred] <file>:<line> [lens N, severity] [rule_citation if any] — <issue summary> — Deferred reason: <why>
```

### TODO.md entry format

Append to TODO.md under section `## Deferred review findings` (create section if not present, place at end before `## Closed-off paths`):

```
- [ ] **<issue summary>** — `<file>:<line>` (lens N, severity; rule: <citation if any>; first flagged YYYY-MM-DD; recurred X times across [date list]) — Deferred because: <why>
```

### Tag lifecycle (for `[review-deferred]`)

```
review-plus-fix-relentlessly writes:
  [review-deferred] — first occurrence of a deferred finding

Loop's own recurrence detection transitions to:
  [review-promoted: TODO.md § "Deferred review findings"] — promoted after recurrence
  [review-resolved] — manual retag when subsequent review confirms gone (optional, low-priority)
  [review-rejected: <reason>] — manual retag when user explicitly says "not a real issue"
```

Once an entry is `[review-promoted]`, future loop runs skip its dedup check (it lives in TODO.md now). `[review-resolved]` and `[review-rejected]` are manual retags — the loop doesn't need to enforce them, they exist so future-you knows the item was decided not just dropped.

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
- **Stop Conditions**: Stops when no blocking issues remain (`architectural-critical` or `critical`) or max cycles reached (10). `warning`/`info` findings route to deferred-findings logging (see Triage policy below) without blocking.
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

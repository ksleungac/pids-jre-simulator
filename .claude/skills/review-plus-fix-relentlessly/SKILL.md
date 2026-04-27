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

  # Extract issues_found from feedback (simplified parsing)
  ISSUES_FOUND=$(echo "$REVIEW_FEEDBACK" | grep -o '"issues_found": true' || echo "")

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
    # 4. Follow repository style and preferences from rules/notes.md
    # 5. Test changes before considering them complete
    # 6. Stage changes (git add ...) when ready for next review cycle

    echo "After you finish fixing, stage changes and continue to next cycle."
  else
    echo "No issues found. Ralph loop complete!"
    ISSUES_FOUND=false
  fi

  # Step 2c: Report cycle completion and prepare for next cycle
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
- **Stop Conditions**: Stops when no issues found or max cycles reached (10)
- **Role Separation**: Reviewer (sonnet) reads only, Fixer (opus) applies fixes
- **Context Passing**: Feedback passed between agents for iterative improvement
- **Graceful Degradation**: Clean up temporary files, handle errors

## Configuration:
- **MAX_CYCLES**: 10 (configurable)
- **Reviewer Model**: sonnet (cost-effective for review)
- **Fixer Model**: opus (better for complex fixes)
- **Timeout**: 30 minutes total for entire loop

## Notes:
- The loop is self-contained - each cycle builds on the previous
- Reviewer feedback must be structured for the fixer to parse
- Git state should be preserved (no auto-commits unless requested)
- System should handle cases with no dirty changes gracefully

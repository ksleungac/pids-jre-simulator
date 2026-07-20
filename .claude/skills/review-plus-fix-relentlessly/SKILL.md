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

### Line-scope mode (DIRTY vs FULL) — passed through to review-dirty
The Scope rule above governs WHICH FILES. WHICH LINES within them is a separate mode, defined in `review-dirty` § "Scope mode": **DIRTY** (diff hunks, default) vs **FULL / MODULE / END-TO-END** (every line of the named files, committed-but-unchanged code included). When the user says "scan the module", "end-to-end", "review the whole X", or names specific files/dirs, pass that intent through in the `review-dirty` call's `args` — so its reviewer embeds the whole files, runs the deterministic scanners over the module (Derivation-bypass scan), and applies the lenses to every line, NOT just the diff. A hardcoded literal that shipped weeks ago is unchanged history — a DIRTY-mode loop is structurally blind to it. **A stated full scope is literal; never narrow it to the diff.**

**INTEGRATION escalation is automatic, not user-gated:** if the fix set flips a default flow, adds/removes a first-run/onboarding screen, or rewires an entry-point branch, pass that intent through so `review-dirty`'s INTEGRATION scope runs the integration-residue checklist over the flow module — the reviewer escalates even when the user didn't ask, because the stale redundant branch is invisible in both the diff AND the dev environment (`review-dirty` § "Scope mode"; `critical_lessons §6`).

### Fix-confidence gating on surfaces you didn't build
The Scope rule (above) excludes files you didn't touch. A sharper axis applies when the run IS in scope but you lack the DESIGN context — a release-prep / whole-code scan of features built across prior sessions, not your own diff. There, gate each finding on **fix-confidence**, not file-ownership:
- **obvious-safe** — mechanical, zero behavioral ambiguity (hard-rule violation, palette / canonical-source derivation, dead code with grep-confirmed zero callers, stale docstring/comment) → apply inline.
- **needs-context** — requires the module's design / layout-calibration / state-machine intent → **defer to a GitHub issue** (`gh issue create --label review-finding`); do NOT fix blind.

A "looks safe" fix on code you don't understand is exactly how review+fix introduces new bugs. Have the reviewer tag every finding with this flag (obvious-safe | needs-context) so triage is mechanical. Real bugs on out-of-focus surfaces still get LOGGED (not dropped) — deferral is not dismissal. (2026-07-16: user — *"your fixer does not have context for working on these tasks, might introduce new bugs, so delve to TODO for nonobvious tasks."*)

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

When you (main agent) decide to defer a finding rather than fix it during a cycle, file it as a **GitHub issue** (`gh issue create`) regardless of severity. The daily-log routing path (`memory/YYYY-MM-DD.md`) is **not used** — daily logs are narrative continuity / metacognitive observations only per `session-recap/SKILL.md`. Code-related obligations live as forward state in the issue backlog.

### Routing rule

Every deferred finding → a GitHub issue with the `review-finding` label (plus the area label — `auto-input` / `display` / `chrome-i18n` / … — so it groups on the board).

| Severity | Files an issue? |
|---|---|
| `architectural-critical` | yes — surfaces in the session-start backlog summary |
| `critical` | yes |
| `warning` | yes |
| `info` | yes if the user explicitly defers OR you auto-defer with a real reason. **Drop** if the ASK-flag was answered "not real" (no value tracking these). |

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

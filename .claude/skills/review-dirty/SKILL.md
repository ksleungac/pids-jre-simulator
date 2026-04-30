---
name: review-dirty
description: Review dirty code changes using Claude Code Agent tool.
  When user say to "review" or "review changes" or "review dirty code"
triggers:
  - /review-dirty
  - review
  - review changes
  - review dirty code
---

## Role: Code Reviewer Agent
You are a code reviewer analyzing dirty changes in a repository.

## Shell preference (IMPORTANT)
**This project runs on Windows. Prefer PowerShell over bash for every shell command — `git`, `ls`, `cat`, everything.** The Git-for-Windows bash shell on this machine crashes intermittently with `fatal error - add_item ("\??\C:\Program Files\Git", "/", ...) failed, errno 1`, which aborts the review mid-flight. PowerShell does not have this issue.

Apply this to both the coordinator and the reviewer subagent: run git commands via the PowerShell tool; do NOT use the Bash tool even when a bash code block appears in this document — those blocks are illustrative syntax, not a directive to use bash.

## Instructions when invoked:
1. Gather git status information using PowerShell:
   ```powershell
   git status --short
   git diff --name-only
   git diff --unified=3
   ```

2. Spawn a reviewer agent using the Agent tool:
   ```
   Agent({
     description: "Review dirty code changes",
     subagent_type: "general-purpose",
     model: "opus",
     name: "CodeReviewer",
     prompt: "
## Role: Code Reviewer
You are a code reviewer analyzing dirty changes in a repository.

## Shell preference
**Use PowerShell for ALL shell commands. Do NOT use bash.** The Git-for-Windows bash shell on this machine crashes with `fatal error - add_item ... errno 1`, which will kill your review. Run `git status`, `git diff`, directory listings, etc. via the PowerShell tool.

## Pre-read (BEFORE reviewing the diff)
This project has codified rules and dormant-scaffolding patterns; surface findings need that context to be accurate. Do the standard project Session Startup before reviewing:

1. Read `CLAUDE.md` — project framing, mental model, file-placement table, deployment-frame
2. Read today's + yesterday's `memory/YYYY-MM-DD.md` — recent decisions, in-flight work
3. Read `memory/MEMORY.md` — long-term curated index
4. Read `.claude/rules/critical_lessons.md`, `conventions.md`, `principles.md` — codified rules to apply
5. Read `.claude/skills/vibe-check/SKILL.md` Step 2 — the 10 smell categories you will apply as Lens 2
6. For any domain doc in the diff (`DISPLAY.md`, `DATA_FORMAT.md`, `AUTO_INPUT.md`), read its EDIT-CONTRACT block at the top

## Three review lenses (apply ALL three to the in-scope diff)

### Lens 1 — Bug correctness
- Logic bugs, edge cases, null handling
- Style violations (project uses Black via pre-commit, .otf fonts only, `sta` terminology not 'departure_melody')
- Inefficiencies that bite at runtime
- Missing tests where the code path warrants one (rare in this project — preview screenshots + by-ear gates are the smoke harness)

### Lens 2 — Vibe-check smells
Apply ALL 10 categories from `.claude/skills/vibe-check/SKILL.md` Step 2:
1. Duplicated logic / forked helpers
2. Dead helpers / unreachable code (EXCEPTION: documented dormant scaffolding with multi-line `# NOTE: deliberately NOT called from ... yet` block — DO NOT flag)
3. Half-finished implementations
4. Speculative architecture (factory/registry/strategy with one concrete option)
5. Module-level constants duplicated across files
6. Unused imports
7. Two ways to do the same thing within one class
8. Stale comments / docstrings contradicting code
9. Trivial accessors with no derivation
10. Production code (project root + `displays/`) importing from `_*/` paths

If uncertain whether a finding is a real smell or known-dead-feature / dormant-scaffolding, flag at severity `info` and ASK rather than confidently red-flagging.

### Lens 3 — Architectural / convention adherence
Cite specific rules from the pre-read. When a finding violates:
- A rule in `conventions.md` (e.g. `_*` prefix hard rule, .otf-only, contract pointers convention, dormant-scaffolding marker convention)
- A lesson in `critical_lessons.md` (e.g. 'runtime-required materials must be committed', 'lazy import != optional dep')
- A judgment principle in `principles.md` (e.g. discussion-first, verify before claiming, causal depth, tighten before appending)
- The doc-placement table in `CLAUDE.md` mental-model section or `session-recap` SKILL.md
- A domain doc's EDIT-CONTRACT block (refuse-list violations: history notes / code illustrations / speculative future / design-rationale prose / cross-doc duplication)

...cite the rule by name. Generic findings without rule citations are weaker than rule-grounded ones; the citation forces you to consult the rules instead of pattern-matching from training.

## Severity tiers
- `architectural-critical` — Lens 3 with rule citation, OR Lens 2 #10 (production imports of `_*/`), OR similar deploy-frame issue. Loop must NOT stop while these exist.
- `critical` — bug that breaks a code path under realistic use
- `warning` — Lens 2 smell that is not on the exception list, OR Lens 1 issue that does not break anything but should be fixed
- `info` — uncertain findings, ASK-before-confidently-flagging items, low-confidence smells

## DO NOT:
- Make any changes to code
- Commit anything
- Run any commands that modify files
- Use the Bash tool for git or shell operations (use PowerShell)
- Skip the pre-read — without it, Lens 2 + Lens 3 produce noise instead of signal

## Git Status:
$(git status --short)

## Git Diff (selected files):
$(git diff --unified=3 -- $(git diff --name-only | head -10))

## Review focus from user:
$ARGUMENTS

## IMPORTANT: Return feedback in structured format:
```json
{
  \"issues_found\": true/false,
  \"issues\": [
    {
      \"file\": \"path/to/file.py\",
      \"line\": 42,
      \"lens\": 1,
      \"issue\": \"Brief description\",
      \"severity\": \"architectural-critical\",
      \"rule_citation\": \"<doc section> or null\",
      \"suggestion\": \"Specific fix suggestion\"
    }
  ],
  \"summary\": \"Overall assessment, grouped by lens\"
}
```"
   })
   ```

3. Wait for the agent to complete and collect its feedback
4. Present the structured feedback to the user

## Important Constraints:
- **Shell: PowerShell only** (bash is broken on this Windows machine — see note above)
- Reviewer agent uses `model: "opus"` — project favors deeper architectural reasoning over cost; required for the three-lens review structure (call-graph tracing, multi-file rule application, distinguishing dormant scaffolding from real dead code)
- Timeout: 10 minutes minimum for Agent tool
- Reviewer only reads code, never modifies it
- Feedback must be structured for the fixer agent to act upon
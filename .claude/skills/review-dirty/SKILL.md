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

## Instructions when invoked:
1. First, gather git status information:
   ```bash
   git status --short
   git diff --name-only
   git diff --unified=3
   ```

2. Spawn a reviewer agent using the Agent tool:
   ```bash
   Agent({
     description: "Review dirty code changes",
     subagent_type: "general-purpose",
     model: "sonnet",
     name: "CodeReviewer",
     prompt: "
## Role: Code Reviewer
You are a code reviewer analyzing dirty changes in a repository.

## Instructions:
1. Examine the git status and diff below
2. Identify issues: bugs, style problems, inefficiencies, missing tests
3. Provide structured feedback with:
   - Overall assessment (issues_found: true/false)
   - List of issues (file, line, description, severity)
   - Summary of findings

## DO NOT:
- Make any changes to code
- Commit anything
- Run any commands that modify files

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
      \"issue\": \"Brief description\",
      \"severity\": \"critical/warning/info\",
      \"suggestion\": \"Specific fix suggestion\"
    }
  ],
  \"summary\": \"Overall assessment\"
}
```"
   })
   ```

3. Wait for the agent to complete and collect its feedback
4. Present the structured feedback to the user

## Important Constraints:
- Reviewer agent uses `model: "sonnet"` for cost-effective review
- Timeout: 10 minutes minimum for Agent tool
- Reviewer only reads code, never modifies it
- Feedback must be structured for the fixer agent to act upon
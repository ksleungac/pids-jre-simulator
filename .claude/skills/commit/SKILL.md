---
name: commit
description: Commit hygiene — before creating a commit, detect and flag unrelated changes (especially stray data fixes bundled into program commits) so they can be split into their own commits.
triggers:
  - /commit
  - commit
  - commit changes
  - make a commit
---

## Purpose

Keep each commit to one logical change. Mixing related data + program changes is fine. Mixing unrelated data fixes into a program commit pollutes history and breaks `/release` note drafting.

**One clean topic → one commit.** When the whole dirty tree is a single topic — including that topic's session-recap codifications (rules, TODO; memory publishes separately, see below) — make ONE commit. Don't reflexively split feature from recap; the feature+recap split is only for when they're genuinely separate topics. (2026-06-10) User: *"next time when commits are clean about one topic, just make them 1 commit."*

## Pre-flight (4 checks before drafting commit message)

1. **Smoke test** — invoke the modified code path, observe expected output. "It compiles" doesn't count. Or: `/review-dirty` produced clean output.
2. **User verification** — surface concrete smoke-test output to the user. Wait for explicit confirmation.
3. **Branch-domain check** — `git branch --show-current`. If on a feature branch and the change is unrelated to that feature, surface the mismatch before committing.
4. **Session-recap check** — if no `memory/<today>.md` covers this session's work (locally OR published on the `origin/memory` ref — the classification report says which), propose recap-first. User can say "skip recap" to waive.

**Skip clause:** user explicitly waives ("trivial, just commit", typo fix). Applies to that commit only.

## Process

### Step 1 — Inventory + classify

Run `git status --short`. The PostToolUse hook (`_harness/classify_commit.py`) auto-injects a classification report — read it instead of classifying manually. The report covers: file buckets, branch name, session-recap existence, data+program mix warnings.

### Step 2 — Relatedness test

Identify the main change from conversation context. For each file: **"Does this need to change for the main ask to work?"**

Red flags: unrelated data edits alongside program changes, multiple unrelated data fixes bundled, files from a parallel Claude session (not in your tool history).

### Step 3 — Report + draft message

Match repo commit style (`git log --oneline -10`). Show proposed message + any flags. Wait for user choice before committing.

For bulk additions: subject names the largest change; body enumerates the rest with counts.

### Step 4 — Execute

- Stage specific files only — **never** `git add -A` / `git add .`.
- **Never stage `memory/**`** — narrative auto-publishes to the `origin/memory` journal ref via `_harness/publish_memory.py` (recap runs it; session_init retries queued blocks); master history stays pure code. A dirty memory file is unpublished queue state, not commit cargo.
- Prepend `CLAUDE_COMMIT_VIA_SKILL=1` — mandatory; the PreToolUse hook blocks `git commit` without this marker.
- Use Bash (not PowerShell) for the commit: `CLAUDE_COMMIT_VIA_SKILL=1 git commit -m "$(cat <<'EOF' ... EOF)"`.
- Include `Co-Authored-By:` trailer — read the exact model name from the session system info (e.g. `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`). Never guess; the system info is always present.
- **Link the GitHub issue** — if the change advances or finishes an issue, add a trailer beside `Co-Authored-By:`: `Closes #N` on the finishing commit (pushing to `master` auto-closes it), `Refs #N` on a progress commit. One line per issue. A ghost ID (no such issue) is a typo — verify the number before committing.
  - **Only `Closes` an issue you finished ENTIRELY.** If the commit does part of what #N describes, that is a scope problem, not a trailer problem — split the delivered part into a sub-issue under #N (`gh issue edit N --add-sub-issue <M>`) and use `Closes #M` + `Refs #N`. Never close #N and file the remainder as a sibling; that orphans the outcome. See `CLAUDE.md § "Issue scope"`. (2026-07-20 incident: `Closes #71` on a stage-1-only commit.)
  - Any bare `#N` already cross-references the issue timeline — `Refs` is convention for reading clearly, not required syntax. Only the closing keywords close, and only on the default branch.
- Verify with `git status --short` after.

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

**One clean topic → one commit.** When the whole dirty tree is a single topic — including that topic's session-recap codifications (rules, memory, TODO) — make ONE commit. Don't reflexively split feature from recap; the feature+recap split is only for when they're genuinely separate topics. (2026-06-10) User: *"next time when commits are clean about one topic, just make them 1 commit."*

## Pre-flight (4 checks before drafting commit message)

1. **Smoke test** — invoke the modified code path, observe expected output. "It compiles" doesn't count. Or: `/review-dirty` produced clean output.
2. **User verification** — surface concrete smoke-test output to the user. Wait for explicit confirmation.
3. **Branch-domain check** — `git branch --show-current`. If on a feature branch and the change is unrelated to that feature, surface the mismatch before committing.
4. **Session-recap check** — if no `memory/<today>.md` covers this session's work, propose recap-first. User can say "skip recap" to waive.

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
- Prepend `CLAUDE_COMMIT_VIA_SKILL=1` — mandatory; the PreToolUse hook blocks `git commit` without this marker.
- Use Bash (not PowerShell) for the commit: `CLAUDE_COMMIT_VIA_SKILL=1 git commit -m "$(cat <<'EOF' ... EOF)"`.
- Include `Co-Authored-By:` trailer — read the exact model name from the session system info (e.g. `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`). Never guess; the system info is always present.
- Verify with `git status --short` after.

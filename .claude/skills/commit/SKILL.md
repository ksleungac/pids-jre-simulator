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

Keep each commit to one logical change. Mixing **related** data + program changes is fine and expected (a feature that needs a new JSON file, a refactor that needs to update its fixtures). Mixing **unrelated** data fixes into a program commit is not — it pollutes the history, makes cherry-picks harder, and makes the release-notes classifier (see `/build` + `release.ps1`) unable to tell whether a commit is Program, Data, or genuinely both.

This skill runs right before the actual commit. It's a lightweight gate, not a replacement for the built-in commit flow — the built-in flow still owns staging, message drafting, and the actual `git commit` call.

## When to run

- The user has asked for a commit (`/commit`, "commit this", "let's commit").
- OR I'm about to call `git commit` as part of some other workflow.

Run this **before** drafting the commit message — the outcome may change what's in scope for the commit.

## Pre-flight (must hold before drafting the commit message)

Three checks the model owes the user before any commit:

### 1. Smoke test of the change (model's gate)

Invoke the modified code path at least once, observe expected output:

- **Backend code:** function returns X, "loaded N templates," CLI prints expected lines, etc. ("It compiles" / "type-check passed" is correctness, not feature-correctness — does not count.)
- **UI/display:** dev server started, feature exercised in window, no regression in adjacent features.
- **Data:** ran `validate_data.py` / route playback / by-ear pass for STA.
- **Or independent review:** `/review-dirty` or `/review-plus-fix-relentlessly` produced clean output.

### 2. User verification (user's gate)

Surface the smoke-test result to the user — *concrete output, not "I tested it"* (e.g. "ran auto_input, console shows 'loaded 10 digit templates + 6 badges' — does this match what you expect?"). **Wait for explicit confirmation** before drafting the commit message.

The model passes the smoke-test on whether the code does *something coherent*; only the user can judge whether the visible behavior matches the ask. Skipping this is what caused the OCR-template incident (see `.claude/rules/critical_lessons.md` § "Runtime-required materials must be committed") — code ran, model called it done, user discovered the silent no-op only later.

### 3. Has session-recap run?

If this is the last commit of a coding session (e.g. the user is about to wrap up, has said "commit this and we're done", or the session has produced a meaningful chunk of new code/docs/learnings), check whether `/session-recap` has been run. Look for: a `memory/<today>.md` daily log file mentioning this session's work, or a recent `MEMORY.md` index entry pointing at it.

If recap has NOT been run and the session has produced material worth capturing (new patterns, preferences expressed, debugging insights, doc updates), surface it:

```
Heads-up: I don't see a session-recap entry for today's work in memory/.
Want me to run /session-recap first so the daily log + memory index are in
the same commit set as the code, or skip and just commit?
```

### Skip clause (applies to all three)

The user explicitly waives a check ("trivial, just commit", typo fix, doc-only change). Default is no-skip; a waiver applies only to the commit it was given for, not session-wide.

If any check is missing and the user hasn't waived it, surface the gap *before* drafting the commit message — fixing it after the message is drafted is wasted work.

## Process

### Step 1 — Inventory changes

Run `git status --short` and `git diff --cached --name-only` (if anything is staged) plus `git diff --name-only` (unstaged modifications). Build one list: every file that would plausibly go into this commit.

### Step 2 — Classify each file

For each file, record which bucket it falls into:

| Bucket | Paths | Notes |
|--------|-------|-------|
| **Data (shipped)** | `data/*.json`, `audio/**/route.json`, `audio/**/*.mp3`, `audio/*/stations.json` | User-facing data that ships in the distribution. |
| **Data (harness)** | `audio/_*/**` | Preview/testing fixtures + archived recordings (`_mock/`, `_archive/`). Not shipped. Treat as Program for relatedness — a mock tweak alongside a code change is normal. |
| **Program — code** | `*.py` (except `preview_*`), top-level config (`pyproject.toml`, `uv.lock`, `main.py`) | |
| **Program — preview/harness** | `preview_*.py` | Testing tool, not shipped. |
| **Program — tools** | `validate_*.py`, one-off scripts at project root | Dev/CI tools. Group with the change that introduced them. |
| **Program — docs/internal** | `*.md`, `.claude/**`, `.github/**`, `memory/**`, `.gitignore` | |
| **Program — fonts** | `fonts/*` | Rare; treat as its own category if it shows up. |
| **🚫 Never commit** | `*.exe`, `dist/`, `build/`, `__pycache__/`, `_scan.py`, `_*.py` scratch scripts | Build artifacts and throwaway scripts. If present in status, they should be `.gitignore`d or deleted — not staged. Flag these separately in the report; the user almost certainly doesn't intend to commit them. |

### Step 3 — Identify the "main" change

What did the user actually ask for? Read the conversation:
- "Add English mode" → program/code is the main change; expect `displays/**`, `app.py`, maybe `data/train_types.json` if English strings live there.
- "Fix Tokaido 1865E track 2 audio" → data is the main change; expect `audio/tokaido/1865E/**`.
- "Update README" → docs is the main change; expect `README.md`.

If the user's ask is ambiguous, **ask** before proceeding — don't guess a main theme.

### Step 4 — Apply the relatedness test

For each file, ask: **"Does this file need to change for the main ask to work or make sense?"**

Green-light (no flag — commit together):
- A new feature's code + the JSON data that feature reads (e.g. station-code badge + `data/stations.json`).
- A refactor + updates to tests/fixtures/mock routes that exercise the refactored code.
- A schema change in `data/*.json` + the code that reads the new schema.
- Docs updates that describe code being added in the same commit.

Red flags (stop and ask the user):
- The main ask is a program change, and there are edits to `audio/<some_line>/<diagram>/route.json` or `.mp3` files that have no connection to what was asked.
- The main ask is a specific data fix (one station's audio), and there are also unrelated code edits in `*.py`.
- Multiple *unrelated* data fixes staged together (e.g. one Keihin-Tōhoku route.json tweak + one Yamanote typo) — each is small, but they're not the same change.
- Anything the user didn't mention and you can't explain from the conversation.
- **Files that might be from a parallel Claude session** — this workspace sometimes has a second agent working concurrently. If you see modifications to files you didn't touch (check your tool-use history), surface them as "possibly from another session" and let the user confirm before including or excluding. Never silently include; never silently delete.

### Step 5 — Report + draft commit message before committing

Check the repo's commit style first: `git log --oneline -10`. Match the convention (e.g. `feat:`, `refactor:`, `chore(data):`).

**Honesty check for bulk additions.** When the commit touches many files, the subject + body must describe what's actually there — not just the smallest file or most exciting line. A commit titled "Add stations.json" that also drops 40 audio files is misleading future-you (real incident, 2026-03-01: keiyo bulk drop sat undetected ~8 weeks before Phase B verification surfaced mixed/wrong audio content). Subject names the largest/most consequential change; body enumerates the rest with rough counts ("+17 STA files for 蘇我→東京", "+1 stations.json"). If the changeset spans truly unrelated concerns, that's a Step-4 red flag → split it.

If flags were raised, print the review **plus a draft commit message** (the user usually wants both in one round-trip, not two):

```
## Commit review

Main change (inferred): <one-line summary of what the user asked for>

Files that fit the main change:
- <file>
- <file>

Files that look unrelated:
- <file>  — <one-line why this looks unrelated>
- <file>  — <one-line why this looks unrelated>

Files from another Claude session (if applicable):
- <file>  — not touched in this session's tool history

## Proposed commit message

<type(scope)>: <subject line matching repo convention>

<body — lead with the WHY, then bullet the concrete changes.
Mention deferred items so the commit is self-contained as history.>

Options:
  (a) Commit everything together, with this message.
  (b) Commit only the related files with this message; leave the rest.
  (c) Split into N commits — tell me the split.
  (d) Adjust the message — tell me what to change.
```

Wait for the user's call. Do **not** commit until they answer.

If no flags were raised, still show the proposed commit message and ask for confirmation before running `git commit` — the user typically wants a message preview even on clean-looking commits.

### Step 6 — Execute

After the user chooses:
- Adjust the staging area accordingly (`git add <specific-files>` / `git restore --staged <file>`). **Never** `git add -A` / `git add .` — this commit skill exists specifically because blind staging is how unrelated changes sneak in.
- Run `CLAUDE_COMMIT_VIA_SKILL=1 git commit -m "$(cat <<'EOF' ... EOF)"` with the approved message. Include the `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer. The `CLAUDE_COMMIT_VIA_SKILL=1` env-var prefix is **mandatory** — the project's `PreToolUse` hook in `.claude/settings.json` denies any `git commit` that doesn't carry this marker, on the assumption it skipped the /commit gate. The env var has no functional effect on git; it's purely a marker the hook recognizes by command-prefix shape.
- Verify with `git status --short` — the unrelated files should still be unstaged/untracked. If any disappeared, investigate before running more commits.

If the user chose a multi-commit split, loop: commit the first group, verify, then re-run this skill on the remainder before the next commit.

## Gotchas encountered in practice

- **Rename + modify (`RM` status)**: `git mv` stages the rename (`R`), but if you then edit the renamed file, the edits show up as unstaged (`M`) against the NEW path. `git add <new-path>` to include them. Otherwise the commit ships with the rename but without your content changes.
- **Build artifacts in untracked**: `JRE-PA-Simulator.exe`, `dist/`, `build/` — if these appear in `git status`, they almost certainly belong in `.gitignore`, not in a commit. Suggest adding them to `.gitignore` as a separate fix rather than including them.
- **Parallel Claude sessions**: If another agent has been editing files in the same workspace, you'll see modifications to files you don't recognize. Don't stage them (not your work to commit), don't revert them (not your work to undo). Surface them to the user as "possibly from another session" and let them route.
- **Cross-platform line endings**: `warning: LF will be replaced by CRLF` is noise on Windows; commit proceeds fine.

## Why this matters

Release notes are generated from commit history (`release.ps1` classifies each commit as Program or Data by looking at touched paths). When unrelated data fixes are bundled into a program commit, the classifier sees "mixed" and has to ask the user to split it at *release* time — the exact moment when context is stale and the commit author may not remember which files were the "main" change vs. the ride-along.

Catching this at commit time means the history already reads cleanly: each commit is one thing, each line of the release notes has an obvious home, and `git log -- data/` / `git log -- audio/` give honest answers to "what data changed since v0.5.1?"

## Scope

- **Does** inspect staged + unstaged file paths, classify them, and flag unrelated mixes.
- **Does not** rewrite git history (no rebasing/amending to split past commits).
- **Does not** replace the built-in commit flow — it runs before it.
- **Does not** fire automatically without a commit request. If the user is just saving changes to disk and hasn't asked to commit, this skill is irrelevant.

---
name: release
description: Picks up after /build to publish a GitHub release. Pre-flights the staged artifacts, drafts release_notes.md from commits since the last tag, tags master, then hands the gh release create upload command to the user. Stops short of running the upload — that's user-driven.
triggers:
  - /release
  - cut release
  - publish release
  - release notes
---

## Purpose

Picks up where `/build` ended: an exe + a distribution zip exist under `dist-release/`, smoke-tested. This skill orchestrates the publish flow — pre-flight checks, release-notes drafting, and tag creation — then **hands off to the user to run the actual `gh release create` upload**.

The split: `/build` produces the artifacts, `/release` prepares the metadata and ceremony, the user runs the upload command. Keeps every step the user explicitly drives in the user's hands.

## Required input

**Version** (e.g. `0.5.3`, `v0.5.3`, `0.5.3b`).

- If the user didn't provide a version, **ask for it first**. The version must match the `/build` artifact already on disk — verify by checking that `dist-release/JRE-PA-Simulator-v<version>-distribution.zip` exists. If the file isn't there, halt and direct user to run `/build <version>` first.
- Same parsing rules as `/build`: strip leading `v`, preserve subversion letter (`a`/`b`/`c` are sub-revisions, not betas).
- Version must match an existing zip — never guess; never invent a "next" version.

## Process

### Step 1 — Confirm version

If not provided, ask: *"What version are we releasing? (must match the zip in `dist-release/`)"*. Wait for answer.

### Step 2 — Pre-flight checks

Run these as a batch and surface any failures before drafting notes. **Halt on first failure** — don't proceed to notes when the build state is wrong.

#### 2a. Build artifacts present
```powershell
$zip = "dist-release\JRE-PA-Simulator-v$VERSION-distribution.zip"
$exe = "dist\JRE-PA-Simulator.exe"
if (-not (Test-Path $zip)) { throw "Missing $zip — run /build $VERSION first." }
if (-not (Test-Path $exe)) { throw "Missing $exe — run /build $VERSION first." }
Get-Item $zip, $exe | Format-Table Name, @{N='Size(MB)';E={[math]::Round($_.Length/1MB,1)}}, LastWriteTime -AutoSize
```

Sanity-check the zip's `LastWriteTime` is recent (within the last hour, say). A stale zip from a prior version with the same filename is a real failure mode — if the user re-ran `/build` mid-session and forgot, you'd ship stale bits.

#### 2b. Embedded version matches
The `/build` skill writes `version_info.txt` with the version. Cross-check:
```powershell
Select-String -Path "version_info.txt" -Pattern "FileVersion.*'$VERSION'" -Quiet
```
If false → version_info.txt was last written by a different version. Halt; tell user to re-run `/build $VERSION`.

#### 2c. Branch + clean tree
```powershell
$branch = git branch --show-current
if ($branch -ne "master") { throw "Releases tag master; current branch is $branch." }
$dirty  = git status --porcelain
if ($dirty) { throw "Working tree is dirty:`n$dirty`nCommit or stash first; release tags a specific SHA." }
```

#### 2d. Up to date with origin
```powershell
git fetch origin master
$ahead  = git rev-list --count origin/master..master
$behind = git rev-list --count master..origin/master
if ($behind -gt 0) { throw "Local master is $behind commits behind origin. Pull first." }
# $ahead > 0 is fine — local has unpushed commits the tag will include + push.
```

#### 2e. Tag doesn't already exist
```powershell
if (git tag -l "v$VERSION") { throw "Tag v$VERSION already exists. Bump version or delete the tag (`git tag -d`, `git push origin :refs/tags/v$VERSION`)." }
```

#### 2f. GitHub auth ready
```powershell
gh auth status 2>&1
```
If not logged in → halt; tell user to `gh auth login`.

### Step 3 — Survey commits since last release

Find the previous tag and list commits in scope:
```powershell
$prevTag = (git tag -l "v*" | Sort-Object {[Version]($_ -replace '^v','' -replace '[a-z]$','')} | Select-Object -Last 1)
git log --oneline "$prevTag..master"
```

Surface this list to the user before drafting — gives them a chance to flag commits they don't want in the notes.

### Step 4 — Draft release_notes.md

**Filter criterion** (copied here verbatim from `/build` skill so the rule lives where it's applied):

> **Include a change in user-facing release notes iff the artifact it affects ships inside the distribution zip.**
>
> What ships: the exe, `fonts/`, `data/**` (excluding `data/_*`), `audio/**` (excluding `audio/_*/`), `ocr_templates/`. Anything that lands in `dist-release/JRE-PA-Simulator/` qualifies.
>
> What does **not** ship: `README*.md` (repo-only), `CLAUDE.md`, `.claude/**`, `.github/**`, `memory/**`, `pyproject.toml`, test/preview harnesses, the mock route catalog (`audio/_mock/**`). Changes to these are invisible to end users of the exe → omit.
>
> Mixed commits (one commit touches both shipped and repo-only paths): report only the shipped-facing portion.

**Format** — match the prior release. Read the previous release's notes via `gh release view v<prev>` or check past `release_notes.md` in git history (`git log --all -- release_notes.md`); the v0.5.2 layout uses `### Program` / `### Data` sections + a distribution footer.

**Structure:**
```markdown
## v<VERSION> Release

### Program

- **<headline feature>.** One-paragraph user-facing description. No internal jargon ("apply per-N text scaling tier", "Rule 4 fallback") — describe what the user sees.

- **<next program change>.** …

### Data

- **<new route / new audio>.** Line / diagram.

- **<extended data>.** …

---

**Distribution:** `JRE-PA-Simulator-v<VERSION>-distribution.zip` is self-contained — extract and run. The standalone `JRE-PA-Simulator.exe` is also attached for users who already have `fonts/`, `data/`, `audio/`, and `ocr_templates/` folders alongside it.
```

Each bullet starts with a bolded headline noun followed by `.` then the description. Terse — 1–3 sentences.

**Don't:**
- Include refactor / cleanup commits (clip-rect, helper consolidation) unless they fix a visible regression. Internal hygiene is invisible to end users.
- Cite commit hashes or PR numbers (links rot; the GitHub release page shows the diff already).
- Mention WIP docs, memory logs, daily-log entries, skill updates, or rule codifications.
- List individual data tweaks (per-station JA fix, single-station populated) unless aggregate-newsworthy. Roll up: "27 new translations" / "12 stations populated."
- Lead with implementation jargon. "GOLDEN-rule row-grouping" → "Per-station transfer-info display showing connecting lines."

**Distribution footer** — update if the bundled folder list changed since the prior release. v0.5.3 ships `ocr_templates/` for the first time → mention it in the footer.

### Step 5 — Hard stop for user review

Print the drafted `release_notes.md` and wait for explicit user approval before proceeding.

```
Drafted release_notes.md is below — review and confirm. Reply "ship it" /
"go" / "approved" to proceed; or tell me what to change. Until you do, no
tag is created and no upload is queued.
```

Don't tag, don't push, don't run gh in this step — the user owns the publish decision.

### Step 6 — Tag (after user approval)

```powershell
git tag -a "v$VERSION" -m "v$VERSION"
git push origin "v$VERSION"
git push origin master
```

Push the tag AND any unpushed master commits — the tag annotates a specific SHA, and that SHA must be on origin or `gh release create --verify-tag` will fail.

### Step 7 — Hand off to user for upload

Print the exact `gh release create` command for the user to copy-paste. **Do not run it** — release upload is the user's call.

**Format rule** — emit a SINGLE LINE with the version literal already substituted. No backticks, no backslashes, no shell variables. The user runs git ops in Git Bash; backtick-continuations (PowerShell line break) are eaten by Bash and cause only the first line to execute, creating an empty release. A single line works in PowerShell, Git Bash, and cmd identically. Substituting the literal (`v0.5.3` not `v$VERSION`) avoids variable-expansion mismatch between shells.

```
Tag v<VERSION> pushed. Run this to publish the release (works in PowerShell or Git Bash):

gh release create v<VERSION> --title "v<VERSION>" --notes-file release_notes.md --verify-tag "dist/JRE-PA-Simulator.exe" "dist-release/JRE-PA-Simulator-v<VERSION>-distribution.zip"

After it succeeds, view the release at:
https://github.com/ksleungac/pids-jre-simulator/releases/tag/v<VERSION>
```

`<VERSION>` is the literal value resolved in Step 1 — substitute before printing.

## Out of scope

- **Building**: that's `/build`. If artifacts are missing, halt; direct user.
- **Running `gh release create`**: user runs it. Skill stops at handing off the command.
- **Modifying `pyproject.toml` / source for version bump**: not needed; version is a build-time label only (per `/build` skill's stance).
- **Post-release announcements** (YouTube, Twitter, etc.): user-driven.

## Why these choices

- **Skill stops before upload, not before tag.** Tagging is reversible (`git tag -d` + `git push origin :refs/tags/...`); uploading creates a public artifact users may have downloaded by the time you notice a problem. The split puts the irreversible step in user hands.
- **Notes are drafted, not auto-generated.** `release.ps1`'s auto-generation produces commit-subject-shaped bullets that read like git log, not like user-facing notes. The skill's draft is a starting point for the user to edit; the criterion (ships-in-zip) is the filter, not the formatting.
- **Cross-check the prior release's structure.** v0.5.2's `release_notes.md` is the format reference; staying consistent across releases makes the GitHub release page predictable for the public audience.
- **No re-build.** `/build` already produced the artifacts and the user smoke-tested them. Re-building under release.ps1 wastes time AND introduces a non-zero risk of "the binary that was tested isn't the binary that ships" — the skill ships the exact bytes the user verified.

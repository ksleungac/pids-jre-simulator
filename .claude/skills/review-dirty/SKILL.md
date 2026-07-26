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

## Scope mode — DIRTY (default) vs FULL / MODULE vs INTEGRATION
Two scope axes. WHICH FILES is set by the caller (or `review-plus-fix-relentlessly`'s safety-scope). WHICH LINES within a file has a mode:

- **DIRTY** (default — "review", "review my changes"): review the diff hunks.
- **FULL / MODULE / END-TO-END** (user says "scan the module", "end-to-end", "review the whole X", or names specific files/dirs): review EVERY LINE of the named files — git status is irrelevant, committed-but-unchanged code is IN scope. A hardcoded `VERSION = "0.5.4"` sat as unchanged history for weeks while every dirty-diff review was structurally blind to it.
- **INTEGRATION** (the change **flips a default flow, inserts/removes a first-run/onboarding screen, or rewires an entry-point branch** — `--tims`→`--classic` default flip, a picker/tutorial/consent screen added or dropped, a flow-routing `if` edited): auto-escalate to FULL scope on the touched flow module(s) AND run the **integration-residue checklist** — re-walk EVERY state-gated branch (`if not settings.get(...)`, `if X not in ...`, `if not path.exists()`) and EVERY reachable screen, asking per item: *still reachable? still needed? now redundant beside a sibling feature?* A change reviewed only along its OWN axis (the flag it flips) is blind to a screen made redundant on an ORTHOGONAL axis (persisted state) — the v0.6.0 language picker survived its own graduation commit this way (`critical_lessons §6`). **A DUTY, not a user opt-in:** recognize the trigger and escalate even from a DIRTY-mode call.

In FULL mode: (1) embed the WHOLE in-scope files in the reviewer payload, not `git diff`; (2) the reviewer runs the deterministic scanners over the whole module FIRST (see Derivation-bypass scan), then the lenses over every line. **A stated full scope is LITERAL — never silently narrow it to the diff.**

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
6. For any domain doc in the diff (`DISPLAY.md`, `DATA_FORMAT.md`, `auto_input/README.md`), read its EDIT-CONTRACT block at the top

## Derivation-bypass scan — canonical-source duplication (run BEFORE the lenses)
A hardcoded literal that re-states a value which owns a single canonical source drifts silently — it is correct-at-authoring, so neither an eyeball nor a dirty-diff review catches it (a hardcoded `\"0.5.4\"` shipped while the build was 0.6.0). Two halves:

**(1) Deterministic — run the linter over the in-scope .py files** (re-checks committed code the diff never shows; read-only, safe):
```powershell
python _dev_scripts/lint_primitives.py --derivable <in-scope .py files>
python _dev_scripts/lint_primitives.py <in-scope .py files>
```

**(2) Semantic — the sub-classes a linter CANNOT reason about.** Check each in-scope file for a hardcoded literal that should instead DERIVE from a source:
- **Special-case where a general rule belongs** — a specific literal used as a filter/branch that should be a predicate (`== \"_mock\"` where `startswith(\"_\")` is meant; one route/model/station name special-cased instead of its category). → the general predicate.
- **Color literal == a palette constant** — an RGB tuple equal to a `tims.chrome` PALETTE value, typed inline instead of the constant. → the constant.
- **Dimension re-typed, not read** — one model's dimension hardcoded in SHARED code. → `surf.get_height()` or a param.
- **UI string bypassing i18n** — a user-facing chrome label as a literal. → `i18n.t(key)`.
- **Route-derived field with per-call fallback** — `stop.get(\"X\") or default` in a renderer. → filled in the `finalize_route` closure (`principles.md` § \"JSON is input grammar\").

Report each finding as a Lens-3 item (rule: `conventions.md` § Tooling \"canonical-source duplication\") with file:line · the literal · the canonical source it should derive from.

## Structural-impact scan — code-review-graph (run BEFORE the lenses, beside the Derivation-bypass scan)
A persistent code-graph yields two complementary views the diff alone cannot show: `impact` = the **blast radius** (callers / dependents of every changed symbol); `detect-changes` = **test-gaps** + per-symbol risk + the changed-symbol list. (Verified 2026-07-21: `detect-changes` does NOT emit callers — that is `impact`'s job.) Read-only: the index writes to the USER CACHE, never the repo. **Fail-open — on ANY error (`uvx` absent, offline, build fails) SKIP silently and proceed. Never block the review.**

```powershell
$env:PYTHONIOENCODING = 'utf-8'   # the rich --brief panel crashes on cp1252 stdout; JSON output is ASCII-safe

# 1. FRESHNESS GATE — `status` reporting "a graph exists" is NOT the same as "the graph is current".
$graphCommit = (uvx code-review-graph status 2>&1 | Select-String 'Built at commit:\s*(\S+)').Matches.Groups[1].Value
$headCommit  = (git rev-parse --short=12 HEAD)
if (-not $graphCommit -or $graphCommit -notlike "$headCommit*") { uvx code-review-graph build }   # ~seconds

# 2. detect-changes — the one that fits in context (~20 KB). Run it FIRST.
uvx code-review-graph detect-changes   # test-gaps + risk + changed symbols, vs the committed-baseline graph
                                       # do NOT run `update` first (it folds the diff INTO the graph and erases it)

# 3. impact — blast radius. Redirect to a file and grep it; do NOT read it raw (see size warning below).
uvx code-review-graph impact > "$env:TEMP\crg-impact.json"
```

**Two verified limitations — factor both into how far you trust the output (measured 2026-07-21):**

- **Untracked files are INVISIBLE.** The scan's changed-set comes from tracked modifications only, so a brand-new file contributes nothing: on the #78 review, `LowerDisplayBase` (a new 400-line parent class, the largest structural piece of the change) and its new T3 test each returned **zero hits across both scans**. Consequences: the blast radius silently omits new code, and the test-gap count is inflated because a new uncommitted test cannot be seen. **For every NEW file, grep for its symbols instead — the graph gives you nothing there.**
- **Staleness is silent.** `status` reports only whether a graph exists, never whether it matches HEAD. Without the freshness gate above, a graph built several commits ago is scanned against without a word. (Nothing rebuilds it automatically — no hook wires it.)

**Size warning:** `detect-changes` is ~20 KB and safe to read. `impact` on a broad change measured **1.2 MB** — never read it raw; redirect to a file and `Select-String` for the symbols you care about.

Feed the JSON into the lenses (skip this paragraph entirely if the scan was unavailable):
- **Lens 1** — walk `impact`'s caller / dependent list for each changed symbol and confirm the diff did not break them (`critical_lessons` \"test the change, not just the bug\"). `impact` is the who-calls source (`detect-changes` omits it); fall back to grep when `impact` returns nothing, which is guaranteed for new files.
- **Lens 4** — the `test-gaps` list IS the feature-has-test axis: a changed symbol with no covering test is a Lens-4 `warning`. Reconcile against the diff — an *uncommitted* new test shows as a gap because the graph baseline is the last commit, not the working tree.
- **INTEGRATION scope** — a large or flow-crossing blast radius is a mechanical trigger to auto-escalate scope (per the Scope-mode DUTY above).

## Four review lenses (apply ALL four to the in-scope code — the diff in DIRTY mode, the whole files in FULL / INTEGRATION mode)

### Lens 1 — Bug correctness
- Logic bugs, edge cases, null handling
- Style violations (project uses Black via pre-commit, .otf fonts only, `sta` terminology not 'departure_melody')
- Inefficiencies that bite at runtime
- Missing tests where the code path warrants one (rare in this project — preview screenshots + by-ear gates are the smoke harness)
- **Deployment-frame / runtime-semantics verification.** If the diff touches PyInstaller path semantics (`sys.frozen`, `sys._MEIPASS`, `sys.executable`, `Path(__file__)` for behavior-dependent paths), threading primitives, file-I/O timing assumptions, library API behavior that differs between dev and frozen, OR any code where "correctness" depends on runtime conditions not visible from reading the file — verify against primary source (the build script's actual copy logic, the library's runtime-hook source, official docs, or actual exercise of the deployed artifact). Don't accept "intentional / standard / the way it's always done" claims from memory. The 2026-05-05 release-crash trace had a prior reviewer defend `i18n.app_root`'s `_MEIPASS` usage as "intentional semantics" — wrong, because the defense reasoned from generic PyInstaller mythology rather than checking THIS project's build script (which doesn't use `--add-data`, so `_MEIPASS` is empty). Per `principles.md` § "Verify deployment-frame and external-runtime semantics from primary source."

### Lens 2 — Vibe-check smells
Apply ALL 13 categories from `.claude/skills/vibe-check/SKILL.md` Step 2:
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
11. **Local utility helper that should live in a shared module** (path resolver / JSON loader / slug parser / format helper / common regex / stdlib-only helper buried in a feature module instead of `app_paths.py` / `displays/utils.py` / `constants.py` / `i18n.py`). Per `principles.md` § "Search before authoring common utility code."
12. **Deployment-frame / runtime-semantics primitive outside canonical home, without verification anchor** (`sys._MEIPASS`, `sys.frozen`, `sys.executable`, `Path(__file__)` for behavior-dependent paths, `if frozen:` branching outside `app_paths.py`; OR threading / I/O timing patterns without a comment explaining the invariant). Per `principles.md` § "Verify deployment-frame and external-runtime semantics from primary source." Sibling to Lens 1 verification — Lens 1 fires on the diff; Lens 2 fires on the standing pattern.
13. **Integration residue — a screen / branch / flag made redundant by a sibling feature but still wired.** After a flow integration (a flow becomes default, a screen's job moves to a sibling), a now-redundant first-run screen or state-gated branch is often left reachable because it's invisible in dev (the branch only fires on absent persisted state). **FULL / INTEGRATION-scope only — a DIRTY diff is structurally blind to it** (the stale branch is unchanged history). Distinct from #2 (dead/unreachable) — this code IS still reachable, just no longer *needed*. Per `critical_lessons.md §6`. **Verification:** for each first-run / onboarding screen, confirm a live entry path AND that no sibling feature already owns its job (the v0.6.0 picker was redundant beside the TIMS home's language knobs).

**On Lens 2 categories #11 + #12 — pre-flight grep**: when reviewing a diff that introduces a small utility helper or a deployment-frame primitive, do a `grep -rn` cross-codebase pass for sibling implementations BEFORE approving. The duplication isn't visible from the diff alone — it's visible only from the codebase view.

If uncertain whether a finding is a real smell or known-dead-feature / dormant-scaffolding, still REPORT it — at severity `info`, with the question attached. Uncertainty lowers the severity; it never suppresses the finding. Triage filters, the reviewer does not.

### Lens 3 — Architectural / convention adherence
Cite specific rules from the pre-read. When a finding violates:
- A rule in `conventions.md` (e.g. `_*` prefix hard rule, .otf-only, contract pointers convention, dormant-scaffolding marker convention)
- A lesson in `critical_lessons.md` (e.g. 'runtime-required materials must be committed', 'lazy import != optional dep')
- A judgment principle in `principles.md` (e.g. discussion-first, verify before claiming, causal depth, tighten before appending)
- The doc-placement table in `CLAUDE.md` mental-model section or `session-recap` SKILL.md
- A domain doc's EDIT-CONTRACT block (refuse-list violations: history notes / code illustrations / speculative future / design-rationale prose / cross-doc duplication)

...cite the rule by name. Generic findings without rule citations are weaker than rule-grounded ones; the citation forces you to consult the rules instead of pattern-matching from training.

### Lens 4 — Test integrity
The project carries a real test suite (`_tests/`, tier map in `_tests/README.md`). Review the CHANGE against it on three axes:
- **Test-not-stale.** A test that asserts removed/renamed behavior, encodes an old spec, or whose subject the change moved — a green stale test is worse than none (false confidence). Flag any test the change silently invalidated. Cross-cutting sibling: a coherence test that agrees with a *drifted doc* (`_tests/README.md` "Coherence ≠ correctness") — assert the deepest invariant, not a derived restatement.
- **Feature-must-have-test.** A new production code path / decision function / regression-worthy bug-fix landing with NO accompanying test in the appropriate tier — pick by SCOPE: pure fn → T1, cross-module headless → T3, state-absent first-run → T4 (`_tests/README.md` "Fixture ≠ tier"). Rendering is exempt (by-eye by design). Regression-test-per-incident is the project's first-fill rule.
- **Code-must-be-testable.** Decision logic buried where it can't be exercised headlessly (inside a pygame/blocking monolith, behind a display init, tangled with I/O) — flag as untestable-as-written and NAME the extraction (a pure function the test can call, per the `resolve_language` extraction that made the first-run language path testable). Untestable logic is how a bug class stays uncovered.

Severity: a stale / false-green test → `critical` (it actively misleads); a missing test on a regression-worthy path, or untestable-as-written logic → `warning`.

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

## In-scope code:
# DIRTY mode (default) — the diff hunks:
$(git diff --unified=3 -- $(git diff --name-only | head -10))
# FULL / MODULE mode — replace the diff above with the WHOLE in-scope files
# (Get-Content each named file); committed-but-unchanged lines MUST be reviewed.

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
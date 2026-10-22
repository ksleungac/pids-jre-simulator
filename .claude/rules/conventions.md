# Conventions: naming, style, tooling

Project-local style and naming choices. These don't shape major decisions, they keep code consistent.

<!-- EDIT-CONTRACT for conventions.md

REQUIRED SHAPE per bullet:
- Bold lead: the rule itself, one clause, plain words. It must be readable alone.
- Body: the mechanism in ordinary sentences. Keep every identifier, path, constant and
  API name — the technical content is the value of this file.
- Incident: a date and one clause. One user quote only where the rule's failure shape
  lives in their words.

REFUSE-LIST (don't add; if found, strip):
- Sibling cross-ref tails ("Same family as X", "Distinct from Y", "Pairs with Z").
- Connective tissue ("the tell is", "which is what makes it", "and that is the whole point").
- Multi-paragraph incident traces. The daily log holds the trace.
- A second user quote once one is already carrying the rule.
- Restating a rule that has a narrower home; link to that home instead.

SIZE GATES:
- Each bullet ≤ 180 words. Over that, either the rule is two rules or the trace is being
  retold. The bar is deliberately looser than principles.md's: this file's value is technical
  density, and a rule plus its mechanism plus one dated incident legitimately runs long.
- A bullet with its own trigger, incident and how-to-apply is a peer, not a sub-bullet.
- Sub-bullets are for genuine facets of one rule. Three or more means it was two rules.

VOICE:
- Plain register. Em-dashes are not the default connector; a comma, colon or full stop
  usually reads better. No SHOUTING CAPS for emphasis — bold the lead, then stop.
- This file is preloaded every turn, so its prose is the style exemplar the model imitates.
  Density of technical fact is wanted; density of rhetorical framing is not.
-->

## Naming

- **`_*` prefix = preserved-but-not-shipped staging.**

  | Folder | Holds |
  |---|---|
  | `audio/_archive/` | recordings the active diagram doesn't use, kept for future glob lookup |
  | `audio/_mock/` | preview/test fixtures |
  | `_dev_scripts/` | audio splitters/validators, OCR-asset extractor, primitive-bans linter, dxcam + game-capture diagnostics |
  | `_harness/` | hook sensors, build gate, session scripts |
  | `_experiments/` | WIP not yet ready for project root |
  | `_<feature>_calibration/` | gitignored source material that derives committed artifacts |

  - **The prefix marks a DIRECTORY, so a filter for it tests the directory parts — never the basename.** Applied to every component of a path it also matches `__init__.py`, and a package init is where the registry, the canvas and the palette live. 2026-08-30: `font_atlas.code_fingerprint()` read `not any(s.startswith("_") for s in path.parts)`, which silently dropped all five `__init__.py` in `displays/` — so registering a train model, or moving a model's canvas, left the atlas fingerprint identical and a stale atlas loading happily. `parts[:-1]` is the fix and it excludes `__pycache__` unchanged, because that one really is a directory. Any glob-then-filter over this tree wants the same care: state whether you are excluding a *location* or a *file*.
  - **Hard rule:** production code (project root + `displays/`) MUST NOT import from `_*/` paths. A production import itself means the file has graduated — promote it out (e.g. `_experiments/ocr.py` → `ocr.py` at project root, or `data_tools/plot_drive.py` → `plot_drive.py` after the 2026-04-30 incident; `data_tools/` was renamed to `_dev_scripts/` in the same incident). Folder placement carries dep-classification semantics — see [critical_lessons.md § "Lazy import ≠ optional dep"](critical_lessons.md) for the full pathology.
  - **Treatment by tools:** `/build`'s staging step classifies `audio/_*/` + `data/_*` as harness (not shipped — via `$shipExclude` plus the tracked-only filter; `release.ps1` was retired in `9bfe431`); `/vibe-check` excludes code under `_*/` from production-scope reviews (Step 1) AND flags production imports of `_*/` as smell #10 (Step 2). **The route picker skips `_`-prefixed dirs in its `audio/` scan** (`tims/setup/route_select.py`: `dirs[:] = [d for d in dirs if not d.startswith("_")]`; the classic `setup.py` picker had the same skip and was retired 2026-07-30) — so an `audio/_<line>/` WIP route is hidden from the picker AND the zip. (2026-07-15: `_joban` still listed because the scanners only special-cased literal `_mock`; the general prefix skip fixed both.)
- **A one-off measurement script is `_dev_scripts/_<question>.py`, tracked, with a docstring opening `"""Throwaway:"""` or `"""Ad-hoc:"""`.** Name it for the question it answers, never for the attempt. Tracked is the point rather than an oversight: the author sees it in the diff and can object as it lands, the throwaway-or-keep call is recorded at write time in the docstring rather than remembered, and a probe that turns out to matter is already kept. `_sim_panel_layout.py` and `_e233_lower_geometry.py` were both written as one-offs and are now the instruments their domain docs cite. **The marker is a delete trigger, and the trigger has to be pulled.** Deleting is cheap and nearly reversible — the file is tracked, so `git log --diff-filter=D -- _dev_scripts/` finds it and `git show <sha>^:<path>` brings it back. What keeping costs is the one list that exists to stop you writing a duplicate: `session_init.tools()` prints every script's first docstring line each session, so a dead probe competes for attention with the instrument you actually wanted. Three tests, and one hit is enough to keep:
  - a doc, test or skill CITES it, so someone may re-check the claim it backs;
  - a re-run would answer the same question again on new input — that is an instrument, not a probe;
  - it is the only way to reach something production cannot show you. This one expires: `_render_manner_mode.py` existed because the page was unreachable from `preview_display.py`, and the fix was to make the preview reach it (the `--lower-view` map now derives from `_SLOT_*`), not to keep the script.

  Otherwise delete. A probe answers its question ONCE; revising the artifact later is a new question and usually a new probe. The 2026-09-12 audit removed six on this rule, four of them mask probes whose PNG shipped a month earlier. The other disposal is to reclassify: a probe the docs end up citing gets its docstring rewritten to open `KEEP —` naming what cites it (`_badge_fixture_sources.py`, `_badge_colour_shift.py`). And a probe that is really a TEST goes to `_tests/`, joining the module that owns the behaviour rather than staying a script nothing runs — `verify_reentry_consensus.py` held nine consensus-latch sequences the suite lacked and had executed nowhere since the day it was written. Never the OS temp dir, which is the one location invisible to both git and the session, so you cannot open your own previous attempt and write a new file instead; 2026-08-26 produced 32 files for four questions that way. `_experiments/` is not this: it stays what its `.gitignore` entry says, PoC folders that will graduate. Renders the author will see go to the repo root as `screenshot_*.png`. See [redlines.md](redlines.md) and [principles.md § "Prototype inside the code that will hold it"](principles.md).
- **Name patterns by cause, not discovery instance.** When a recurring pattern is documented in skills / docs (recording-source quirk, behavioral pattern, technique), name it by what DRIVES it (`hostile-recording pattern`, `source-driven transient`) — NOT by the first line / case where it was observed (`yamanote-style`, `keiyo lines have KAK`). Discovery-instance tagging creates false line-specificity: a reader sees "yamanote-style" and assumes pattern is Yamanote-only, missing that it applies to any recording with the same source-side property. 2026-05-12: sta-make skill tagged hostile-recording + KAK as `yamanote-style` / `keiyo lines`; user flagged that Yamanote has KAK too — both patterns are recording-source-driven, not line-specific. Skill text retagged generically; the discovery line gets a one-line origin note as illustration, not as the pattern's scope.

## Tooling

- **Pre-commit hooks: Black + primitive bans.** `.pre-commit-config.yaml` wires five:
  - Black, the formatter, version-pinned to match `pyproject.toml`.
  - `ban-production-primitives` (`_dev_scripts/lint_primitives.py`) — regex-grep for `pygame.font.SysFont`, `Path(__file__).parent`, `sys._MEIPASS`, `sys.frozen` outside `app_paths.py`, and `_*/` production imports.
  - `ban-derivable-literals` (`lint_primitives.py --derivable`) — AST scan. See the next bullet.
  - `_dev_scripts/check_fonts.py` — the `.ttf` ban.
  - `_dev_scripts/check_spdx.py` — `# SPDX-License-Identifier: MIT` in every `.py`'s first 3 lines.

  Run `pre-commit install` once per clone. Don't run Black manually unless the hook isn't firing. Format-skip blocks wrap in `# fmt: off` / `# fmt: on` per `display.md` § "Tuneable-params block".
  - **Black's `--exclude` REPLACES its default ignore list (`.venv`, `.git`, `build`…) rather than adding to it.** Use `--extend-exclude`, or just pass the file list. 2026-08-08: `black --check . --exclude '^old_version\.py$'` started walking `.venv` and had to be killed after two minutes. `git ls-files '*.py' | xargs black --check` finished in seconds, and it is the honest scope anyway — tracked files are what the hook sees.
- **Canonical-source duplication: a hardcoded literal re-stating a value that owns a single source, so the copy drifts silently.** Correct at authoring, so eyeball and dirty-diff review both miss it. A hand-typed `VERSION="0.5.4"` shipped while the build was 0.6.0, born in a `_dev_scripts/*_draft.py` and copied verbatim into production at promotion. Caught in two tiers.
  - **Mechanical facets** — version → `app_paths.display_version()`, bare bundled-asset path → `project_root()`. Caught by the `ban-derivable-literals` pre-commit hook (`lint_primitives.py --derivable`). It is AST-based, so docstrings and error strings don't false-positive, and scoped to production plus `*_draft.py`, so a placeholder is caught at birth.
  - **Semantic facets** — what a linter cannot reason about. Caught by the derivation-bypass scan in [`/review-dirty`](../skills/review-dirty/SKILL.md). Five shapes:
    - a special-case literal where a general predicate belongs, `=="_mock"` against `startswith("_")`;
    - a colour equal to a `tims.chrome` PALETTE constant;
    - a UI string bypassing `i18n.t`;
    - a route field read via per-call `stop.get() or default`;
    - a parametric model re-stating a shape an authored asset already owns. Hand-placed Catmull-Rom waypoints against the band mask PNG: derive from the asset, as `_extract_band_centerline` does (#51).
  - A literal is a violation only when a canonical source exists. A tuneables-block magic number is its own source.
  - This generalizes four scattered instance-rules: the path resolver ([critical_lessons § 4](critical_lessons.md)), fork-time re-verify (`display.md` § Display module structure), PALETTE (`tims.md` § UI code style), and the `finalize_route` closure ([data.md § "JSON is input grammar"](data.md)).
- **All bundled-asset path resolution via `app_paths.project_root()`.** Never `Path(__file__).parent`, never `sys._MEIPASS`, never inline `if sys.frozen:` branching, never a new local `app_root()` / `get_base_dir()` / `_project_root()` helper. The 2026-05-05 release shipped four separate crashes from authoring locality (each module's author solved the path-resolution problem in isolation, one with the wrong PyInstaller semantic). See [critical_lessons.md § "PyInstaller deployment-frame divergence"](critical_lessons.md). `_MEIPASS` is reserved for plotly's library bundle (`--collect-data plotly`), never project assets. Calibration tools, `_dev_scripts/`, and `_harness/` are exempt — they don't ship.
- **`old_version.py`** — keep. Intentionally retained as the pre-refactor monolithic reference even though nothing imports it. Don't propose deleting it during tidy passes.
- **Name coupling across a boundary has no compiler: dispatch on a canonical token, and every key a consumer reads needs a producer.** Nothing type-checks a string match or a `dict.get`, so both degrade to a no-op rather than an error. **Control flow keyed on prose inside a message:** `_dev_scripts/capture_game.py` dispatched with `"fire departure PA" in event`, so renaming the event strings to match production disarmed every synthetic PageDown while the script still printed the events, looking healthy and firing nothing. Dispatch on the leading token (`event.startswith("FIRE_DEPARTURE")`) and let the readable tail carry live numbers freely. **A key read but never written:** `tims/band.py` read `reentry_pending` to draw the amber "Re-aligning…" chip and the driver never published it, so a documented feature could not appear for weeks with no error anywhere. When adding a status or telemetry key, grep both directions. (Both 2026-07-21, #82. The `stale_ref_hook` cannot see either, since it greps identifiers and these are a string literal's contents and a dict key.)
- **When the deliverable IS a table / list / measurement set, render it in the chat message — tool output is not shown to the user.** Bash and script stdout render to claude, not reliably to the user, so "the table above" points at nothing they can see. Applies whenever the output IS the answer (a proposal table, a diff of current vs proposed, a classified file list); a tool call whose result only feeds claude's next step needs no echo. 2026-07-25: presented the Chūō `sta_cut` proposal as "Table above" — user: *"SHOW it TO ME?"*.
- **Editing source by GENERATING it is one escape level too many — use Edit/Write instead.** A string literal you write INTO a file has its escapes interpreted by the writer first, so `"
"` in a `python - <<'PY'` heredoc reaches the file as a real newline. 2026-08-20 that broke `validate_data.py` twice in one edit (once in a comment, once in `if "
" in rem:`), each time as a `SyntaxError: unterminated string literal` pointing at a line that looked fine in the heredoc. Bypass-permissions mode nudges toward Bash for file work; this is the case where Bash is the worse tool. If a script genuinely must emit an escape, build it as `chr(92) + "n"` rather than escaping the escape.
- **A new asset class must update `THIRD-PARTY.md` in the same change.** `LICENSE` (MIT) covers authored code + docs only; every other class — audio recordings, fonts, operator marks, reference photographs, assets derived from third-party software — is carved out and inventoried in `THIRD-PARTY.md`. An asset added with no entry silently widens what the grant *appears* to cover, and nothing mechanical catches it (a license scanner reads `LICENSE`, not the tree); the harm is a forker relying on an apparent grant. **Attribution-bearing classes are itemized** — the 3 CC BY-SA 4.0 Commons icons carry author + license + the modification made, and that itemization IS the compliance. **Everything else is disclaimed by category** with its rights holder named: a per-file inventory of unlicensed material is a target list, not a disclaimer. 2026-07-27: `data/` turned out to mix authored JSON with 37 third-party operator marks, so "this directory is mine" is not a safe classification unit — classify per file class, not per folder.

- **A guard's domain must cover everything the prose around it claims.** Enumerate the outputs, not the ones that were top of mind. 2026-08-29: a re-run guard covered a splitter's `SEGMENTS` list while its docstring promised to refuse overwriting "a file whose length no longer matches its window", and the one output built by a different code path sat outside it. It was protected only incidentally, because two other files carried hand edits and aborted the run first; re-derive those two windows and the shield vanishes with nothing to notice. A reviewer found it, not a run.
- **A BOM disables Black silently — `pyproject.toml` parse errors are an ENCODING fault, not a config one.** `black` (and `pre-commit run black`) failing with `Could not open file 'pyproject.toml': Error reading configuration file: Invalid statement (at line 1, column 1)` means a UTF-8 BOM on `pyproject.toml`, not a malformed `[tool.black]` section — `uv` tolerates the BOM, so everything else keeps working and the message points at the wrong thing. **The formatter is then OFF for every commit until someone notices.** Check bytes first: `[System.IO.File]::ReadAllBytes(p)[0..2]` = `EF BB BF`. 2026-08-11: the v0.6.3 release commit (`7edf2ff`, other machine) round-tripped `pyproject.toml` and shipped a BOM *and* a mojibake em-dash; Black had been failing on every commit since, and reformatted a file the moment it was unblocked. The next bullet's rule already forbade the round-trip — it was violated anyway, via `/release`, which is why the DIAGNOSTIC is written here: the rule did not stop it, so make the symptom cheap to decode. Sweep the tree with a 3-byte read over `git ls-files` when in doubt.
- **Never round-trip a source file through PowerShell 5.1 `Get-Content` → `Set-Content`.** `Get-Content` without `-Encoding` decodes as the system ANSI codepage, so each non-ASCII sequence (em-dash `—` = `E2 80 94`) becomes three cp1252 chars, and writing back with `-Encoding utf8` double-encodes them to mojibake and prepends a BOM (`EF BB BF`). Python still parses the file and the tests still pass, so nothing catches it but a byte check. Mutation-test a constant with the Edit tool: change it, run, change it back. When a shell round-trip is genuinely needed, use `[System.IO.File]::ReadAllText` / `WriteAllText` with an explicit `New-Object System.Text.UTF8Encoding($false)`. (2026-07-25: a mutation check on `publish_memory.py` mangled all 13 of its em-dashes and added a BOM, caught only because a PostToolUse hook echoed the file back as `â€"`.)
- **A BOM sits latent.** Python accepts one at byte 0 as an encoding marker, so a corrupted `.py` imports, tests and ships normally, and only becomes a `SyntaxError` (`invalid non-printable character U+FEFF`) once something is inserted above it. 2026-08-08: the SPDX sweep put a comment on line 1 of `_tests/t1_unit/test_start_station_labels.py` (since merged into `test_startup.py`) and broke a test that had passed for months. Any header or prologue insertion over a tree is a reason to scan for `EF BB BF` first; the whole-tree scan is one pass and found exactly two files.
- **Hook scripts that output non-ASCII must call `sys.stdout.reconfigure(encoding="utf-8")` at entry.** Windows pipes default to cp1252; Japanese characters in validator output crash the hook silently without this. Pattern used in `route_json_hook.py`, `check_harness.py`, `check_deps.py`.
  - **cp1252 has a READ side too, and it fails quietly where the write side crashes.** `subprocess.run(..., text=True)` with no `encoding=` decodes the child's bytes as the locale codepage, so `git grep` output comes back mojibake (`—` as `â€"`) rather than raising. 2026-09-01: `stale_ref_hook.py` had shipped that way, injecting corrupted matched lines as context on every rename, and the write-side rule had been codified since 2026-05-14 while this half went unnoticed for months. Pass `encoding="utf-8", errors="replace"` on any `subprocess.run` reading a tool that can emit non-ASCII, which on this repo is all of them: paths carry kanji and every doc carries em-dashes. Reconfiguring stdout does not help — that is the other end of the pipe.
- **Avoid `FOO_<digits>x<digits>` style identifiers.** Pyright (the LSP backing the user's IDE) misparses identifiers containing a digit-letter-digit run like `CAPTURE_REGION_2560x1440` — symbol resolution breaks downstream (callers report "name not defined" even though Python accepts the identifier). Use underscore between the numeric groups instead: `CAPTURE_REGION_2560_1440`. Python lexer is fine either way; this is purely a tooling workaround. 2026-05-13 incident: capture-region refactor; renamed once Pyright kept flagging the import.
- **Prefer Serena MCP over grep for semantic code questions.** `find_referencing_symbols` (who-calls / is-orphaned), `find_symbol` (locate + body + signature), `get_symbols_overview` (file structure) answer via the LSP — grep is textual and can't tell a real caller from a comment/doc mention, so "is X dead" / "where's X called" via grep needs manual filtering. Grep stays for free-text + pattern sweeps. Server in `.mcp.json` (uvx-from-git, gitignored, per-machine). 2026-06-11: user — *"use it going forward."*
- **A shell pipeline reports the LAST command's exit code, so `check | tail` always looks clean.** `black --check . | tail -5; echo $?` prints `tail`'s status, not Black's: the check ran, printed nothing that survived the pipe, and its verdict was discarded. 2026-08-21: reported a file as Black-clean that Black had rejected, and pre-commit caught it a minute later. Any gate whose output you pipe needs `set -o pipefail`, `${PIPESTATUS[0]}`, or no pipe at all. But `${PIPESTATUS[0]}` is the left-hand command, so it is the wrong remedy when the gate sits on the right: `git ls-files '*.py' | xargs black --check; echo ${PIPESTATUS[0]}` prints `git ls-files`'s status, which is 0 while Black is rejecting a file. Both shapes fired the same day, the second in the session that codified the first. Read which side the gate is on before reaching for a remedy; passing the file list as arguments rather than piping removes the question.
- **A library's startup banner goes to STDOUT, so `2>$null` does not remove it and a loose filter adopts it as data.** pygame prints `pygame 2.6.1 (SDL 2.28.4, …)` and its community line on stdout at every import, so any script that also prints results emits two lines of chrome ahead of them. Suppressing stderr looks like it handled that and does not. 2026-08-30: a corpus sweep piped its own CSV through `Where-Object { $_ -match '^\w' }`, and both banner lines start with a word character, so the driver counted 89 cases where there were 87 and the two phantom rows became failed renders with an empty `--stop`. A filter one character laxer would have rendered two junk cells into a coverage sheet instead. Filter on the output's own shape (`$_ -like '*|*'` for a delimited row), never on "looks like text". `sys.stdout.reconfigure` does nothing here, since the banner is the library's rather than yours.
- **Never `2>&1` a native exe in PowerShell 5.1, and never pair it with `$ErrorActionPreference = "Stop"`.** PS 5.1 wraps each stderr line from a native command in an `ErrorRecord` (`NativeCommandError`), so `Stop` turns the tool's first informational line into a terminating error and the command dies at exit 0. 2026-08-01: the `/build` PyInstaller step aborted on `103 INFO: PyInstaller: 6.19.0` — nothing was wrong with the build. stderr is captured for you already; just run the exe bare and check `$LASTEXITCODE`.

## Display module structure




## UI code style

- **Comment dormant scaffolding explicitly.** When a helper is defined but intentionally uncalled, put a multi-line `# NOTE: deliberately NOT called from … yet` block above it explaining *why*, *when to wire it in*, and *what's reserved for it*. Without that signal, every reviewer-pass re-flags it as dead code.

## Contract Pointers in Code

When a function or class has a non-obvious contract that lives in a doc (`docs/DISPLAY.md`, `docs/DATA_FORMAT.md`, etc.) — and getting it wrong has caused or *clearly could cause* regressions — anchor a pointer in the code itself, at the top of the class or function body.

**Why.** "Read the doc first" instructions get bypassed when an agent has *partial* context that feels sufficient (real failure: an agent skipping `docs/DISPLAY.md` for a lower-LCD bugfix because some preloaded content seemed to cover it). An in-code pointer is unavoidable — anyone editing the code reads the file first, so the pointer lands in their context at the moment of decision. Skipping it requires deliberate dismissal, not omission.

**Format** (terse, ~3 lines):

```python
# CONTRACT: <one-line summary>.
# See <DOC.md> § "<exact section heading>".
# <one-line context: what breaks if you skip the doc>.
```

**Bar for adding one** — non-obvious AND would clearly bite:
- ✅ Window invariants, mode-cycler timing rules, skip-animation state contracts, clear-bg confinements, "must be called unconditionally before X" ordering rules, recurring-review-false-positive sites.
- ❌ Routine functions whose behavior is obvious from the code itself, or where the contract is local and self-documenting.

**Don't substitute for the doc.** The pointer summarizes; the doc has the actual contract. Update the doc when the contract changes; keep the inline comment terse.


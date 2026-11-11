# Conventions: naming, style, tooling

Project-local style and naming choices that keep code consistent. Domain conventions load with their files from the path-scoped `.claude/rules/<domain>.md`. Shape rules for editing this file: `docs.md` § "Edit contracts".

## Naming

- **`_*` prefix = preserved-but-not-shipped staging.**

  | Folder | Holds |
  |---|---|
  | `audio/_archive/` | recordings the active diagram doesn't use, kept for future glob lookup |
  | `audio/_mock/` | preview/test fixtures |
  | `_dev_scripts/` | audio splitters/validators, OCR-asset extractor, primitive-bans linter, capture diagnostics |
  | `_harness/` | hook sensors, build gate, session scripts |
  | `_experiments/` | WIP not yet ready for project root |
  | `_<feature>_calibration/` | gitignored source material that derives committed artifacts |

  - **The prefix marks a DIRECTORY, so a filter for it tests the directory parts, never the basename.** Applied to every path component it also matches `__init__.py`, where the registry, canvas and palette live. 2026-08-30: `font_atlas.code_fingerprint()` dropped all five `__init__.py` in `displays/`, so registering a model left a stale atlas loading happily; `parts[:-1]` is the fix. State whether a filter excludes a *location* or a *file*.
  - **Hard rule:** production code (project root + `displays/`) MUST NOT import from `_*/` paths. A production import means the file has graduated: promote it out (`_experiments/ocr.py` → `ocr.py`; `data_tools/plot_drive.py` → `plot_drive.py` after the 2026-04-30 incident). Placement carries dep classification, see [critical_lessons.md § "Lazy import ≠ optional dep"](critical_lessons.md).
  - **Tools honour it:** `/build` treats `audio/_*/` + `data/_*` as not shipped (`$shipExclude` plus the tracked-only filter); `/vibe-check` excludes `_*/` code from production scope and flags production imports of it (smell #10); the route picker skips `_`-prefixed dirs (`tims/setup/route_select.py`), so an `audio/_<line>/` WIP route is hidden from picker and zip. (2026-07-15: `_joban` still listed while scanners special-cased only `_mock`.)
- **A one-off measurement script is `_dev_scripts/_<question>.py`, tracked, with a docstring opening `"""Throwaway:"""` or `"""Ad-hoc:"""`.** Name it for the question, never the attempt. Tracked lets the author object as it lands and records the keep-or-delete call at write time; `_sim_panel_layout.py` and `_e233_lower_geometry.py` started this way and are now cited instruments. **The marker is a delete trigger, and the trigger has to be pulled**, because `session_init.tools()` prints every script each session and a dead probe competes with the instrument you wanted. Deleting is nearly reversible (`git log --diff-filter=D -- _dev_scripts/`). Keep only on one of:
  - a doc, test or skill CITES it;
  - a re-run would answer the same question on new input, which makes it an instrument;
  - it is the only way to reach something production cannot show you. This expires: `_render_manner_mode.py` went once the preview reached the page.

  Otherwise delete (2026-09-12 removed six). A probe the docs end up citing gets its docstring rewritten to open `KEEP —` naming what cites it; a probe that is really a test joins its module under `_tests/`. Never the OS temp dir, invisible to git and to the next attempt (2026-08-26: 32 files for four questions). `_experiments/` holds PoCs that will graduate. Renders for the author go to the repo root as `screenshot_*.png`. See [redlines.md](redlines.md) and [principles.md § "Prototype inside the code that will hold it"](principles.md).
- **Name patterns by cause, not discovery instance.** A recurring pattern in skills or docs is named by what drives it (`hostile-recording pattern`, `source-driven transient`), not by the first line it showed up on (`yamanote-style`), which reads as line-specific. The discovery line becomes a one-line origin note. (2026-05-12: KAK and hostile recording were tagged `yamanote-style` / `keiyo lines`; Yamanote has KAK too.)

## Tooling

- **Pre-commit hooks: Black + primitive bans.** `.pre-commit-config.yaml` wires: Black (pinned to `pyproject.toml`); `ban-production-primitives` (`_dev_scripts/lint_primitives.py`: `pygame.font.SysFont`, `Path(__file__).parent`, `sys._MEIPASS`, `sys.frozen` outside `app_paths.py`, `_*/` production imports); `ban-derivable-literals` (`lint_primitives.py --derivable`, below); `check_fonts.py` (the `.ttf` ban); `check_spdx.py` (`# SPDX-License-Identifier: MIT` in every `.py`'s first 3 lines); `check_tracked_ignored.py`; `check_rules_corpus.py`. Run `pre-commit install` once per clone. Format-skip blocks use exact `# fmt: off` / `# fmt: on` (`display.md` § "Tuneable-params block").
  - **Black's `--exclude` REPLACES its default ignore list** (`.venv`, `.git`, `build`), so it walks `.venv`. Use `--extend-exclude`, or pass the file list: `git ls-files '*.py' | xargs black --check`. (2026-08-08)
- **Canonical-source duplication: a hardcoded literal re-stating a value that owns a single source, so the copy drifts silently.** Correct at authoring, so review misses it. (A hand-typed `VERSION="0.5.4"` shipped in a 0.6.0 build.)
  - **Mechanical facets** (version → `app_paths.display_version()`, bundled-asset path → `project_root()`): caught by `ban-derivable-literals`, AST-based and scoped to production plus `*_draft.py`.
  - **Semantic facets**: caught by `/review-dirty`'s derivation-bypass scan. A special-case literal where a predicate belongs (`=="_mock"` vs `startswith("_")`); a colour equal to a `tims.chrome` PALETTE constant; a UI string bypassing `i18n.t`; a route field read via per-call `stop.get() or default`; a parametric model re-stating a shape an authored asset owns (derive from the asset, as `_extract_band_centerline` does, #51).
  - A literal is a violation only when a canonical source exists; a tuneables-block number is its own source. Instances: the path resolver ([critical_lessons § 4](critical_lessons.md)), fork-time re-verify (`display.md`), PALETTE (`tims.md`), the `finalize_route` closure ([data.md § "JSON is input grammar"](data.md)).
- **All bundled-asset path resolution via `app_paths.project_root()`.** Never `Path(__file__).parent`, `sys._MEIPASS`, inline `if sys.frozen:`, or a new local `app_root()`-style helper. The 2026-05-05 release shipped four crashes from modules each solving this alone. `_MEIPASS` is reserved for plotly's bundle. `_dev_scripts/`, `_harness/` and calibration tools are exempt. See [critical_lessons.md § "PyInstaller deployment-frame divergence"](critical_lessons.md).
- **`old_version.py`: keep.** The pre-refactor monolithic reference, intentionally unimported. Don't propose deleting it.
- **Name coupling across a boundary has no compiler: dispatch on a canonical token, and every key a consumer reads needs a producer.** A string match or `dict.get` degrades to a no-op, not an error. Dispatch on a leading token (`event.startswith("FIRE_DEPARTURE")`), not prose inside a message: renaming event strings once disarmed every synthetic PageDown in `capture_game.py` while it still printed them. When adding a status or telemetry key, grep both directions: `tims/band.py` read `reentry_pending`, which the driver never published, so a documented chip could not appear for weeks. (2026-07-21, #82. `stale_ref_hook` sees neither.)
- **When the deliverable IS a table, list or measurement set, render it in the chat message.** Tool output is not reliably shown to the author, so "the table above" points at nothing. (2026-07-25: *"SHOW it TO ME?"*)
- **Editing source by GENERATING it is one escape level too many — use Edit/Write instead.** A literal written INTO a file has its escapes interpreted by the writer first, so a heredoc's `\n` arrives as a real newline (2026-08-20: two `SyntaxError`s in `validate_data.py` from one edit). If a script must emit an escape, build it as `chr(92) + "n"`. Gated by `no_generated_source_hook.py`.
- **A new asset class must update `THIRD-PARTY.md` in the same change.** `LICENSE` (MIT) covers authored code and docs only. Attribution-bearing classes are itemized (the three CC BY-SA 4.0 Commons icons carry author, licence and modification); everything else is disclaimed by category with its rights holder, since a per-file inventory of unlicensed material is a target list. Classify per file class, not per folder: `data/` mixes authored JSON with 37 operator marks. (2026-07-27)
- **A guard's domain must cover everything the prose around it claims.** Enumerate the outputs, not the ones top of mind. (2026-08-29: a splitter's re-run guard covered `SEGMENTS` while its docstring promised more; one output from another code path was protected only by accident.)
- **A BOM disables Black silently — `pyproject.toml` parse errors are an ENCODING fault, not a config one.** `Could not open file 'pyproject.toml' … Invalid statement (at line 1, column 1)` means a UTF-8 BOM; `uv` tolerates it, so only the formatter is off, for every commit. Check bytes first (`EF BB BF`). (2026-08-11: a `/release` round-trip on the other PC shipped one.) Sweep `git ls-files` with a 3-byte read when in doubt.
  - **A BOM sits latent in a `.py`**: Python accepts it at byte 0 until something is inserted above it, then `invalid non-printable character U+FEFF`. Scan before any header or prologue sweep. (2026-08-08)
- **Never round-trip a source file through PowerShell 5.1 `Get-Content` → `Set-Content`.** It decodes as the ANSI codepage and writes back mojibake plus a BOM; Python still parses and tests pass. Mutation-test with the Edit tool; when a shell round-trip is unavoidable, use `[System.IO.File]::ReadAllText` / `WriteAllText` with `New-Object System.Text.UTF8Encoding($false)`. (2026-07-25: all 13 em-dashes in `publish_memory.py`.)
- **cp1252 bites both directions on Windows pipes.** Write side: a script printing non-ASCII calls `sys.stdout.reconfigure(encoding="utf-8")` at entry, or a hook crashes silently on Japanese output. Read side: `subprocess.run(..., text=True)` without `encoding=` decodes the child as the locale codepage and returns mojibake without raising; pass `encoding="utf-8", errors="replace"`. (2026-09-01: `stale_ref_hook.py` injected corrupted lines for months.)
- **Avoid `FOO_<digits>x<digits>` identifiers.** Pyright misparses a digit-letter-digit run (`CAPTURE_REGION_2560x1440`) and callers report "not defined". Use `CAPTURE_REGION_2560_1440`. (2026-05-13)
- **Prefer Serena MCP over grep for semantic code questions.** `find_referencing_symbols`, `find_symbol` and `get_symbols_overview` answer through the LSP, so a comment mention is not a caller. Grep stays for free text and pattern sweeps. (2026-06-11: *"use it going forward."*)
- **A shell pipeline reports the LAST command's exit code, so `check | tail` always looks clean.** Use `set -o pipefail`, or pass the file list as arguments instead of piping. `${PIPESTATUS[0]}` is the LEFT command, wrong when the gate is on the right (`git ls-files | xargs black --check`). (2026-08-21, both shapes in one day.)
- **A library's startup banner goes to STDOUT**, so `2>$null` does not remove pygame's two banner lines and a loose filter adopts them as data. Filter on the output's own shape (`$_ -like '*|*'`), never on "looks like text". (2026-08-30: 89 cases counted for 87.)
- **Never `2>&1` a native exe in PowerShell 5.1, and never pair it with `$ErrorActionPreference = "Stop"`.** PS wraps each stderr line in an `ErrorRecord`, so a tool's first INFO line kills the command at exit 0. Run the exe bare and check `$LASTEXITCODE`. (2026-08-01: `/build`'s PyInstaller step.)

## UI code style

- **Comment dormant scaffolding explicitly.** A helper defined but deliberately uncalled gets a `# NOTE: deliberately NOT called from … yet` block saying why, when to wire it in, and what is reserved for it. Otherwise every review re-flags it as dead code.

## Contract Pointers in Code

When a function or class has a non-obvious contract that lives in a doc, and getting it wrong has caused or clearly could cause a regression, anchor a pointer at the top of its body. "Read the doc first" gets bypassed when partial context feels sufficient; a pointer in the code lands in context at the moment of the edit.

```python
# CONTRACT: <one-line summary>.
# See <DOC.md> § "<exact section heading>".
# <one-line context: what breaks if you skip the doc>.
```

**Bar:** non-obvious AND would clearly bite. Yes: window invariants, mode-cycler timing, skip-animation state, clear-bg confinements, call-ordering rules, recurring review false positives. No: behaviour obvious from the code. The pointer summarizes; the doc holds the contract and is what gets updated.

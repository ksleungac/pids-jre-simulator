# Critical Lessons — DO NOT REPEAT

Five deployment-class incidents. Each locally defensible; each broke production. The shared root: **claude reasons about code as text rather than as a deployed artifact.**

---

## 1. Verify files BEFORE destructive operations (2026-03-19)

Renamed STA files + updated route.json without verifying MP3s existed → missing file, broken config.

**Rule:** never rename/delete/overwrite without first listing what's on disk.

**Pattern:** Glob target dir → cross-reference config → report gaps → wait for confirmation → then act.

**Scope:** any file rename, move, delete, overwrite, or batch operation.

---

## 2. Runtime-required materials must be committed (2026-04-27)

OCR templates in `game_references/` never committed. User deleted them as dev cruft → silent OCR failure on live drive.

**Rule:** if code reads a file at runtime, that file must be (a) committed, or (b) deterministically regenerable from committed sources. Never both "required at runtime" AND "named like dev material" AND "uncommitted."

**Pattern:**
- Small artifacts → commit under a runtime-named path (`ocr_templates/`, not `references/`)
- Large artifacts → commit derived small artifact, gitignore source, add extraction script
- **Fail loudly** when missing — never `path.exists() else continue`

**Scope:** templates, calibration data, fixtures, anything with silent-skip-on-missing patterns.

---

## 3. Lazy import ≠ optional dep (2026-04-30)

`plot_drive.py` in dev-only `data_tools/`, lazy-imported from production Report button, `plotly` in dev deps → Report button silently broken in every release exe.

**Rule:** dep classification follows call-graph reachability, not file location or import timing. Production-reachable code path imports a library → that library is a runtime dep. "Lazy" = when it loads (perf); "optional" = whether it must exist (contract). Not interchangeable.

**Pattern:**
- Trace call graph from the import site to entry points. Any production path reaches it → `dependencies`.
- `try: import X except ImportError` is NEVER a substitute for correct classification.
- File under `_*/` that production code imports → promote out of `_*/`.

**Scope:** all `pyproject.toml` deps, all `_*/` file placements, all defensive imports.

---

## 4. PyInstaller deployment-frame divergence (2026-05-05)

4 release-build crashes in 1 hour — 5 broken path resolvers across 6 files, 2 missing asset classes in build script.

**Rule (two interlocking parts):**
- **(a)** Single canonical path resolver: `app_paths.project_root()`. No local helpers, no `Path(__file__).parent`, no `sys._MEIPASS` for project assets.
- **(b)** Build script tracks program asset reads. Drift between "program reads X" and "build copies X" is silent in dev, explodes in release exe.

**PyInstaller mechanism distinction:**
- `sys._MEIPASS` — temp dir for files bundled INTO exe via `--add-data` / `--collect-data`. This codebase uses it ONLY for plotly's library bundle, never project assets.
- `Path(sys.executable).parent` — dir containing the exe. Where `/build` Step 4 copies `data/`, `fonts/`, `audio/`, `ocr_templates/` alongside the exe.

**Pattern:**
- `from app_paths import project_root` → `project_root() / "dir" / "file"`. No alternatives.
- Fail loud if missing. Silent no-ops are the worst-case mode.
- New asset dirs ship automatically (Step 4 uses exclude-list, not include-list).

**Scope:** all modules loading JSON, fonts, images, audio at runtime; `/build` skill Step 4.

---

## 5. Single-shot signal flags: consume AFTER successful action (2026-05-09)

`pending_next_pa` reset before audio-busy check → at-station press silently dropped → LCD stuck on まもなく.

**Rule:** a single-shot flag must be consumed only when the action's preconditions are met. Reset-before-gate = signal lost on no-op.

**Pattern:**
```python
# Wrong — signal lost if action no-ops:
if pending_X or held_input:
    pending_X = False
    do_action()            # may no-op

# Right — signal preserved until action succeeds:
if (pending_X or held_input) and preconditions_met():
    pending_X = False
    do_action()
```

Held-key inputs self-retry (standard reset-and-call is fine). The pathology only fires for single-shot flags from sources that won't re-emit.

**Scope:** any background-thread → main-thread signal where the action might decline (audio busy, mutex held, mid-animation).

---

## 6. Clean-state first-run paths are invisible in dev (2026-07-15)

TIMS became the default setup flow, but the pre-TIMS `LanguagePicker` (old grey palette) still fired on genuine first-run — the `if lang not in SUPPORTED_LANGS` branch in `main.py`, reached only when `settings.json` has no `language`. Never caught for the whole TIMS-graduation arc because every dev/test machine already has a populated `settings.json` (`language` + `oobe_completed`), so that branch never executes locally. Surfaced only when a clean v0.6.0 release build was smoke-tested from a fresh staged folder — the first screen a real new user sees was stale and half-redundant (TIMS home already has language knobs).

**Rule:** any code path gated on the ABSENCE of persisted local state (`settings.json`, caches, first-run/OOBE flags, `path.exists()`-else defaults) is structurally invisible in a dev environment that already holds that state. "The exe launched" verifies the *running* frame — not the *clean-install* frame a real new user hits. Persisted state masks first-run just as surely as `sys._MEIPASS` masks the deployment frame (lessons 3–4); same root — reasoning from the developer's environment, not the user's.

**Pattern:**
- After any change to setup / onboarding / first-run / defaults, test from a DELETED-state baseline: move `settings.json` (and any first-run flag files) aside, launch, walk the flow. Or exercise the fresh staged build folder BEFORE the smoke-test launch self-pollutes it with a `settings.json`.
- Enumerate every state-gated branch (`if not settings.get(...)`, `if lang not in ...`, `if not X.exists()`) as its own test case — each is a distinct first-run screen a dev never sees.
- When a flow is redesigned (classic → TIMS), re-walk EVERY first-run screen for staleness/redundancy, not only the screens the change touched.
- `/build` smoke test is not "does it launch" — it is "does a brand-new user's first five minutes work." Delete-state first-run is a mandatory item on that checklist.

**Scope:** first-run pickers, OOBE tutorials, settings-absent defaults, cache-miss paths, license/EULA gates, anything reached only when persisted state is missing.

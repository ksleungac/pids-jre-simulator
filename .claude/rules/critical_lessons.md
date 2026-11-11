# Critical Lessons — DO NOT REPEAT

Eleven incidents; the six that apply everywhere are here. The domain ones load with their files: §§7–8 in `ocr.md`, §§9–10 in `gates.md`, §11 in `audio.md`. Each was locally defensible and each broke something real. The shared root: **claude reasons from its own frame — code as text, the dev machine, its own measurement — rather than from the artifact as the user meets it.**

---

## 1. Verify files BEFORE destructive operations (2026-03-19)

Renamed STA files and updated route.json without checking every MP3 existed; one was missing and the config broke.

**Rule:** never rename, move, delete or overwrite without first listing what is on disk. Glob the target → cross-reference whatever points at it → report gaps → wait for the go-ahead → act.

**Then back up.** Before a tool that re-encodes, overwrites or deletes in place, snapshot the target and name the rollback in the pre-flight. Delete the snapshot only after the by-ear or smoke-test gate passes. A pure relocation (`mv` to `_archive/`) needs none.

**Scope:**
- **Non-file bulk mutations count.** Print the *resolved* target list before the loop. (2026-07-20: a `Where-Object` filter matched all 34 `review-finding` issues and a `foreach { gh issue close }` closed them when only #47 was meant.)
- **In-place audio edits count, and a skill's own gate is not advisory.** A batch you cannot show as a table is a batch you have not verified, and "applied" is reported only for files re-measured after the write. (2026-07-26: 99 keihin splices with no proposal table, against the skill's "Wait for OK"; 20 of 45 were later found wrong while reported done.)

---

## 2. Runtime-required materials must be committed (2026-04-27)

OCR templates in `game_references/` were never committed; the author deleted them as dev cruft and live OCR failed silently.

**Rule:** a file the code reads at runtime is committed, or deterministically regenerable from committed sources. Never "required at runtime" AND "named like dev material" AND "uncommitted".

**Pattern:** small artifacts are committed under a runtime-named path (`ocr_templates/`, not `references/`); large ones commit a derived small artifact plus an extraction script; a missing file **fails loudly**, never `path.exists() else continue`.

---

## 3. Lazy import ≠ optional dep (2026-04-30)

`plot_drive.py` lived in dev-only `data_tools/`, was lazy-imported by the production Report button, and `plotly` sat in dev deps, so the button was broken in every release exe.

**Rule:** dep classification follows call-graph reachability, not file location or import timing. "Lazy" is when it loads; "optional" is whether it must exist.

**Corollary (2026-07-27) — a lazy import also defers the library's SIDE EFFECTS.** `dxcam` calls `SetProcessDpiAwareness(2)` at import, and `auto_input` loads only with OCR or the Report button, so the same build scaled windows differently depending on which features the user turned on. Fixed by declaring the state at entry (`window_utils.declare_dpi_awareness`).

**Pattern:**
- Trace from the import site to entry points; any production path reaches it → `dependencies`. `try: import X except ImportError` never substitutes for classification. A `_*/` file production imports gets promoted out.
- A library that mutates process-global state at import (DPI awareness, locale, signal handlers, COM apartment) is imported at a deterministic point. To find one, hook the setter and print the stack.

---

## 4. PyInstaller deployment-frame divergence (2026-05-05)

Four release-build crashes in one hour: five broken path resolvers across six files, two asset classes missing from the build script.

**Rule:** (a) one canonical resolver, `app_paths.project_root()`, with no local helpers, no `Path(__file__).parent`, no `sys._MEIPASS` for project assets. (b) The build script tracks what the program reads; drift is silent in dev and explodes in the exe.

**Mechanism:** `sys._MEIPASS` is the temp dir for files bundled INTO the exe, used here only for plotly's bundle. `Path(sys.executable).parent` is where `/build` copies `data/`, `fonts/`, `audio/`, `ocr_templates/` alongside the exe. New asset dirs ship automatically because staging uses an exclude list. Fail loud when an asset is missing.

---

## 5. Single-shot signal flags: consume AFTER successful action (2026-05-09)

`pending_next_pa` was reset before the audio-busy check, so an at-station press was dropped and the LCD stuck on まもなく.

**Rule:** consume a single-shot flag only once the action's preconditions are met.

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

Held-key inputs self-retry, so reset-and-call is fine there. **Scope:** any background-thread → main-thread signal whose action might decline (audio busy, mutex held, mid-animation).

---

## 6. Clean-state first-run paths are invisible in dev (2026-07-15)

The pre-TIMS `LanguagePicker` still fired on a genuine first run (`main.py`, reached only when `settings.json` has no `language`), and no dev machine ever executed it, because every one already had that file. A clean v0.6.0 staged build showed it.

**Rule:** any path gated on the ABSENCE of persisted state (`settings.json`, caches, first-run flags, `path.exists()`-else defaults) is invisible in a dev environment that holds the state. "The exe launched" verifies the running frame, not the clean-install frame.

**Pattern:**
- After any change to setup, onboarding, first-run or defaults, test from a deleted-state baseline: move `settings.json` aside, or walk the fresh staged build before a smoke launch pollutes it.
- Enumerate every state-gated branch as its own case. When a flow is redesigned, re-walk EVERY first-run screen, not only the touched ones.
- **Axis-blindness.** A refactor reviewed along its own axis misses a redundancy on an orthogonal one: the flip-TIMS-to-default commit gated the OOBE one line below the picker on `args.classic` and never saw the picker, which was gated on absent state. Guarded now by `review-dirty`'s INTEGRATION re-walk and `test_startup.py` / `test_clean_frame_startup.py`.
- `/build`'s smoke test is "does a brand-new user's first five minutes work", with delete-state first-run on the checklist.

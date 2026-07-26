# Critical Lessons — DO NOT REPEAT

Nine incidents. Each locally defensible; each broke something real. The shared root: **claude reasons from its own frame — code as text, the dev machine, its own measurement — rather than from the artifact as the user meets it.**

---

## 1. Verify files BEFORE destructive operations (2026-03-19)

Renamed STA files + updated route.json without verifying MP3s existed → missing file, broken config.

**Rule:** never rename/delete/overwrite without first listing what's on disk.

**Pattern:** Glob target dir → cross-reference config → report gaps → wait for confirmation → then act.

**Scope:** any file rename, move, delete, overwrite, or batch operation — including **non-file bulk mutations** (bulk `gh issue close`/`delete`, API sweeps). 2026-07-20: a PowerShell `Where-Object` filter silently matched all 34 `review-finding` issues and a `foreach { gh issue close }` mass-closed them when only #47 was intended (caught + reopened). Print the *resolved* target list and eyeball it BEFORE the destructive loop — never drive a bulk close/delete straight off an unverified filter.

**In-place audio edits count, and a skill's own gate is not advisory.** 2026-07-26 (keihin STA): spliced 29 files, then 40, then 30, with no proposal table — against a skill step reading "Surface to user before splicing… Wait for OK" verbatim, and against a sentence claude had itself added to that skill an hour earlier. A batch you cannot show as a table is a batch you have not verified. And report "applied" only for files re-measured AFTER the write — that pass was later found wrong on 20 of 45 files while already reported done, which is worse than the unshown batch.

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
- **Axis-blindness — the cognitive mechanism (why the re-walk gets skipped).** A refactor reviewed along ITS OWN axis (the flag it flips, the strings it sweeps) goes blind to a redundancy sitting on an ORTHOGONAL axis. The flip-TIMS-to-default commit even applied the identical redundancy logic to the OOBE gate ONE line below the picker (gated it on `args.classic` because "TIMS does its own OOBE") — and missed the picker (gated on absent persisted state, no `args`, so the flip never forced it into view). Same logic, adjacent screens, decided purely by which axis each gate's condition sat on. A "hardcoded-language *sweep*" in the same commit was content-scoped (find language strings) and never saw the picker (a whole screen, off that axis). → **guarded now:** `review-dirty` § "Scope mode" INTEGRATION scope auto-escalates on a flow-routing change and runs the state-gated-branch re-walk; the T1/T4 tests (`test_resolve_language.py` / `test_clean_frame_startup.py`) lock the language path.
- `/build` smoke test is not "does it launch" — it is "does a brand-new user's first five minutes work." Delete-state first-run is a mandatory item on that checklist.

**Scope:** first-run pickers, OOBE tutorials, settings-absent defaults, cache-miss paths, license/EULA gates, anything reached only when persisted state is missing.

---

## 7. Dev-quality capture masks input-degradation bugs (2026-07-20)

The 1080p speed OCR dropped the decimal on ~40% of a user's frames (19.1 → "191"), yet was invisible on every dev machine: 0 slips on crisp local calibration + a 0/69 live drive. Root: on a *softened* capture (H.264 compression, or a hair less contrast) the decimal dot binarizes to a SINGLE dark column, and `finalize()` can't form a bbox from one column, so the decimal-stop missed it; dev captures render the dot at 2 solid columns → detected. The margin between works/fails is one pixel of darkness. I nearly abandoned the (real) fix, conceding "the reader is stable," on can't-reproduce-locally + the crisp sample — until running the production OCR over the user's screen-recording reproduced it.

**Rule:** for any read from captured / rendered input (OCR, vision, screen-scrape), the dev machine's capture is CLEANER than a real user's (compression, GPU scaling, contrast, DPI). "It reads fine here" — plus a small crisp local sample — is NOT evidence the bug is absent. Same root as lessons 3–6: reasoning from the developer's environment, not the user's.

**Pattern:**
- Reproduce against the USER's captured artifact — run the production pipeline over their recording / uploaded frame; don't trust a fresh local capture to represent theirs.
- The stable target is the DEGRADED case. For this project that is **1080p at real capture quality** — the planned multi-resolution path downscales all inputs to 1080p, so 1080p is canonical and must be absolutely stable (see `WIP_ocr_multiresolution.md`), NOT the crisp dev frame or the higher-native 1440p.
- A detector resting on a feature at the binarization floor (one-pixel margin) is a bug even when it passes on dev — widen the tolerance.

**Scope:** all OCR / vision reads; anything whose correctness depends on input pixel fidelity.

---

## 8. Dev GPU topology masks capture-availability bugs (2026-07-23)

A user's `AutoDriver` thread crashed on `dxcam.create()` with `DXGI_ERROR_UNSUPPORTED`
(0x887A0004) from `IDXGIOutput1::DuplicateOutput`. Invisible on the dev machine, which has a
discrete GPU that owns the display and is dxcam's `device_idx=0` — Desktop Duplication against
an adapter's own output always succeeds there. The bug lives in the *topology*: on a Microsoft
Hybrid (Optimus) system the captured display can be owned by a different adapter than device 0,
and DDA against the discrete GPU on a hybrid system is unsupported by design. `dxcam.create()`
defaulting to `device_idx=0` was a deployment-frame assumption, exactly like the `_MEIPASS`
path (§4) and the crisp-capture assumption (§7) — reasoning from the developer's single-GPU box,
not the user's.

Two failures compounded: the assumption itself, and that the resulting `COMError` was
**unhandled** — it killed the whole thread with a raw traceback instead of degrading, because
the guard only covered `create()` *returning* None, not *raising*.

**Rule:** any capture / GPU / display-topology assumption (`device_idx=0`, "the primary output",
"one adapter", a single capture backend) is invisible on a dev box whose topology happens to make
it hold. Enumerate the real hardware set and pick the combo that works; never trust index 0.

**Pattern:**
- Screen/GPU capture: enumerate adapters × outputs (`dxcam.output_info()`), try each until one
  succeeds — don't hardcode device 0. `auto_input/driver.py::_open_capture_camera`.
- Wrap the init in try/except so a topology mismatch degrades gracefully — but **print the full
  original traceback**; muting it blinds the next report (user: *"if you mute the trace we cannot
  debug such problem next time"*).
- Residual (no working combo — e.g. dGPU-owned display on a hybrid system): a different backend
  (`winrt` / Windows.Graphics.Capture) is the only lever; note it, don't pretend enumeration covers it.

**Scope:** dxcam / DXGI Desktop Duplication, any GPU-adapter or monitor-topology-dependent code.

---

## 9. The instrument is not the artifact — the ear is (2026-07-26)

Reported 0 KAK across a line the user could hear one in on the first file, then kept building
detectors instead of taking the named file as truth. Four detectors later, the user's own hand
cut removed 388 ms where the detector had proposed 87. Separately, auto-converged 45 files onto
the skill's measured 250–400 ms gap target and turned a by-ear PASS into a FAIL — the target was
derived from one line and its fix inserts digital silence, which is audible on a recording that
has continuous ambience.

**Rule:** for audio, the deliverable is what a person hears. Every detector is a proxy for that
and fails silently. A number inside a band is not a pass, and a band derived on one line is a
default, not a gate. When the user reports hearing something the instrument does not show, the
instrument is wrong until proven otherwise — re-check the instrument, never the assertion.

Same frame error as §7 and §8: reasoning from claude's own environment rather than the user's.
Here the environment is the measurement itself.

**Pattern:**
- A user-named file is ground truth. The detector's job becomes reproducing it; one that reports
  clean on that file is disqualified, not "mostly right."
- Treat a detected window as the INNER bound — human cuts land where the artifact stops being
  audible, which is further out than any threshold.
- Before applying a documented numeric convention across a corpus, check the corpus satisfies its
  premise (here: that the file has a near-silent floor to insert into).

**Scope:** all `sta-make` / `pa-make` detectors; anything gated by a by-ear pass.

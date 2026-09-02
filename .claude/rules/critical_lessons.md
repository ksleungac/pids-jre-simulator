# Critical Lessons — DO NOT REPEAT

Eleven incidents. Each locally defensible; each broke something real, or was caught only at the last gate before it. The shared root: **claude reasons from its own frame — code as text, the dev machine, its own measurement — rather than from the artifact as the user meets it.**

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

**Corollary (2026-07-27) — a lazy import also defers the library's SIDE EFFECTS, so process-global
state becomes feature-flag-dependent.** `dxcam` calls `SetProcessDpiAwareness(2)` at import time
(`dxcam/__init__` builds a `DXFactory()` at module scope → `dxcam/core/output.py`), and
`auto_input` is imported lazily — only with OCR enabled, or on the Report button. So the app ran
DPI-unaware through setup and became aware on entering an OCR drive, and awareness is one-way, so
it never reverted: same build, same machine, two different window scalings decided by which
features the user turned on. Nothing errors; it just looks different. Fixed by declaring the state
deliberately at entry (`window_utils.declare_dpi_awareness`) instead of inheriting it by accident.

**Pattern:**
- Trace call graph from the import site to entry points. Any production path reaches it → `dependencies`.
- `try: import X except ImportError` is NEVER a substitute for correct classification.
- File under `_*/` that production code imports → promote out of `_*/`.
- A library that mutates PROCESS-global state at import (DPI awareness, locale, signal handlers,
  COM apartment) must be imported at a deterministic point, or that state silently tracks whichever
  optional feature pulled it in. Hook the setter and print the stack when you need to find one.

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
- **Axis-blindness — the cognitive mechanism (why the re-walk gets skipped).** A refactor reviewed along ITS OWN axis (the flag it flips, the strings it sweeps) goes blind to a redundancy sitting on an ORTHOGONAL axis. The flip-TIMS-to-default commit even applied the identical redundancy logic to the OOBE gate ONE line below the picker (gated it on `args.classic` because "TIMS does its own OOBE") — and missed the picker (gated on absent persisted state, no `args`, so the flip never forced it into view). Same logic, adjacent screens, decided purely by which axis each gate's condition sat on. A "hardcoded-language *sweep*" in the same commit was content-scoped (find language strings) and never saw the picker (a whole screen, off that axis). → **guarded now:** `review-dirty` § "Scope mode" INTEGRATION scope auto-escalates on a flow-routing change and runs the state-gated-branch re-walk; the T1/T4 tests (`test_startup.py` / `test_clean_frame_startup.py`) lock the language path.
- `/build` smoke test is not "does it launch" — it is "does a brand-new user's first five minutes work." Delete-state first-run is a mandatory item on that checklist.

**Scope:** first-run pickers, OOBE tutorials, settings-absent defaults, cache-miss paths, license/EULA gates, anything reached only when persisted state is missing.

---

## 7. Dev-quality capture masks input-degradation bugs (2026-07-20)

The 1080p speed OCR dropped the decimal on ~40% of a user's frames (19.1 → "191"), yet was invisible on every dev machine: 0 slips on crisp local calibration + a 0/69 live drive. Root: on a *softened* capture (H.264 compression, or a hair less contrast) the decimal dot binarizes to a SINGLE dark column, and `finalize()` can't form a bbox from one column, so the decimal-stop missed it; dev captures render the dot at 2 solid columns → detected. The margin between works/fails is one pixel of darkness. I nearly abandoned the (real) fix, conceding "the reader is stable," on can't-reproduce-locally + the crisp sample — until running the production OCR over the user's screen-recording reproduced it.

**Rule:** for any read from captured / rendered input (OCR, vision, screen-scrape), the dev machine's capture is CLEANER than a real user's (compression, GPU scaling, contrast, DPI). "It reads fine here" — plus a small crisp local sample — is NOT evidence the bug is absent. Same root as lessons 3–6: reasoning from the developer's environment, not the user's.

**Pattern:**
- Reproduce against the USER's captured artifact — run the production pipeline over their recording / uploaded frame; don't trust a fresh local capture to represent theirs.
- The stable target is the DEGRADED case. For this project that is **1080p at real capture quality** — the multi-resolution path downscales all inputs to 1080p, so 1080p is canonical and must be absolutely stable (`auto_input/README.md` § "Resolution handling"), NOT the crisp dev frame or the higher-native 1440p.
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

**Corollary (2026-07-26) — check the restriction's SCOPE before assuming enumeration covers it.**
Walking a per-call parameter cannot fix a constraint scoped to the PROCESS. DDA's hybrid rule is
about which GPU the calling process runs on, so when Windows launches the app on the dGPU every
combo the walk tries raises `UNSUPPORTED` and it exhausts. The reporter fixed it by setting the
app's Windows GPU preference to power saving — no adapter, monitor or cable changed. The fix
above is still correct; it just addresses the other half.

**Pattern:**
- Screen/GPU capture: enumerate adapters × outputs (`dxcam.output_info()`), try each until one
  succeeds — don't hardcode device 0. `auto_input/driver.py::_open_capture_camera`.
- Wrap the init in try/except so a topology mismatch degrades gracefully — but **print the full
  original traceback**; muting it blinds the next report (user: *"if you mute the trace we cannot
  debug such problem next time"*).
- Residual (no working combo — the process is on the dGPU, or the display's only owner is): the
  levers are the per-app GPU preference (`HKCU\Software\Microsoft\DirectX\UserGpuPreferences`) or a
  different backend (`winrt` / Windows.Graphics.Capture); note it, don't pretend enumeration covers it.
- A graceful-degradation path that re-prints the original traceback reads IDENTICALLY to the crash
  it replaced, so "same error" in a user report distinguishes nothing. Keep the trace, and give the
  degraded path a distinct leading line to ask the reporter to quote.

**Scope:** dxcam / DXGI Desktop Duplication, any GPU-adapter or monitor-topology-dependent code.

---

## 9. A gate built from an enumeration cannot see a gap in that enumeration (2026-07-30)

The font atlas derived its coverage by sweeping LCD state — routes × stops × modes × views × PA
phases, from tuples typed into the baker. `sobu/1217F` is a through-service whose route bar windows
per `frames`, and pinning the lower view disabled the scheduler, so `_active_frame_idx` never left 0.
Result: **no raster at any size for the 7 stations interior to frame 1** — a `KeyError` the moment a
real drive passed 千葉, on the one route that has frames.

**All three verification gates passed on it.** `--verify` re-drove the *identical* sweep, so an
unvisited state was symmetrically absent from both the bake and the check — it reported `0 raised`
while the names were provably missing. `--pixel-verify` compared two renders of the same unvisited
set. The third gate sampled 36 states. The bug was found by a fresh-context agent reading the
manifest, not by any gate.

**Rule:** a check that consumes the same enumeration the artifact was built from verifies *fidelity*,
never *coverage*. If a generator and its verifier share the list of cases, neither can report a case
missing from the list. The oracle must be independent of the generator — and the generator's inputs
must not be a hand-typed description of what production supports.

**Pattern:**
- Derive every axis from production, never from a tuple in the tool: `TRAIN_MODELS`, `_SLOT_BEATS`,
  `_frame_count`, `DisplayMode`. A hand-written axis list is `principles.md § "A second implementation
  of a production decision drifts silently"` wearing a different hat, and it fails silently the same way.
- Better: remove the enumeration from the correctness path. Coverage keyed on *declared data sources*
  rather than reachable states cannot be short a case, because there is no case list to be short of.
- Make the failure loud where it CAN be seen: the shipped build has no font files, so `--verify` now
  runs with the baked faces unreadable. The dev tree has every face, so nothing else surfaces it.
- **A gate that STAGES its own inputs holds a second copy of "what ships", and that copy is an
  enumeration too.** `--verify-shipped` staged `audio/**/route.json` while `/build` stages every
  tracked JSON under `audio/`. Adding `system.json` therefore left the gate driving a route whose
  sheet resolved to `None`, and it reported clean: staged fingerprint `0de4f187…` over 22 files
  against the bake's `f338b038…` over 23. Derive the staging list from the function production
  itself ships with, here `font_atlas.shipped_json_files()`, never from a glob typed into the gate.
  (2026-09-02.)
- Ask of any new gate: what class of defect is this structurally unable to detect? Write the answer down.

**Scope:** any bake / codegen / fixture-generation with a paired verifier; asset pipelines; snapshot
tests whose snapshot set is produced by the code under test.

---

## 10. A suite that shares one environment verifies that environment, never deployment (2026-08-01)

The font atlas had five mechanical gates and 21,978 states of pixel-identical proof, and had **never
rendered a character outside the dev tree**. It did not work there. Two bugs, stacked:

`mode()` asked *"does `fonts/` exist"* to decide *"can I load ShinGo"*. Those are the same question
only while `fonts/` is all-or-nothing — and `/build` stages a **partial** `fonts/` (the unbaked
families stay, the baked ones are deleted), which is precisely what separates them. So the staged
folder resolved LIVE, the atlas was never consulted, and every ShinGo load went at a file the build
had just deleted. Forcing ATLAS did not help: `code_fingerprint()` globs `displays/**/*.py`, which
`/build` excludes because PyInstaller bundles it into the exe, so it hashed an *empty file list* and
refused the atlas as stale. Caught before any build shipped, by a gate built to leave the frame.

**Rule:** gates inherit the frame they run in. Adding another gate in the same environment cannot
find what that environment hides, however exhaustive it is — depth in one frame is not coverage of
another. §9 is this one level down (a check consuming the generator's own enumeration verifies
fidelity, never coverage); §§3–8 are the same root in single instances. Exhaustiveness reads as
rigour and is the thing that makes the blind spot invisible.

**Pattern:**
- For anything whose behavior differs between dev and deployed, build a gate that CONSTRUCTS the
  deployed shape and runs the real code in it. `--verify-shipped` stages `fonts/`-minus-baked and
  omits `displays/`, then drives the app in a subprocess so the root is redirected before imports —
  seconds, no PyInstaller run. A simulation you can run every build beats a real build you run rarely.
- When a predicate stands in for a question (`fonts/` exists ⇒ ShinGo loadable), name both and ask
  what would separate them. A deliberate change that makes a resource PARTIAL is the classic
  separator, and it usually lives in the build script rather than the code being reasoned about.
  **ADDING A MEMBER TO AN ENUMERATION is the other one.** A gate reading `profile.verified` as
  "has a native template set here" was exactly true while the only verified profiles were the two
  hand-calibrated ones. Promoting 4K — geometry live-confirmed, templates never extracted — split
  the two questions and silently armed `--legacy-ocr` at a resolution whose badge anchors no longer
  matched the cell, so it would have started cleanly and then classified nothing. Nothing about the
  gate changed; the set it quantified over did. Ask of any promotion: which dormant predicate was
  only true because this set was smaller? (2026-08-10 — resolved by deleting the flag, not the gate.)
  **The third separator is a resource that never participates in the mechanism at all**, so the
  predicate is not merely wrong for it — it is unanswerable, permanently. The font atlas records
  only BAKED faces, and its source-literal audit asked "is this string in the records" to decide
  "would this KeyError in a build shipping no fonts". For a face that ships (Noto, Helvetica) the
  answer is structurally no and the records are structurally empty, so `优先座位` — drawn on every
  sweep of every route — was reported as never-drawn on every run, and held `/build`'s pre-flight
  red on a string that was fine. Nobody could fix it in the display code, which is the tell: when a
  gate names a file that is provably correct, suspect the gate's DOMAIN before the file. Fixed by
  recording unbaked faces into a separate sink the baker never reads, so the predicate spans the
  same set as the question. (2026-08-30.)
- **A bound written as an OFFSET from a fitted list states a fact about the SET, not about the
  member.** The overview's shape gate read `len(services) <= len(fold_foot_x) + 1`, true only
  because the one service lacking a fitted fold also happened to need no junction spur. The `+ 1`
  reads as a documented allowance and was a coincidence of the current sheet, so a second sheet
  would have drawn a spur off the end of its tuple. Ask per member which fitted value it needs and
  bound each independently; a global count cannot express a per-member fact. (2026-09-02.)
- A check whose inputs are absent in the deployed frame must be SKIPPED there explicitly, not left to
  compute a degenerate value and compare it. Ask where each check's inputs come from, per frame.
- Count the frames a suite covers, not the cases. Five gates over one frame is one frame.

**Scope:** any dev-vs-deployed divergence — frozen builds, partial asset staging, absent source
trees, first-run state, capture quality, GPU topology.

---

## 11. The instrument is not the artifact; the ear is (2026-07-26)

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

**Recurred 2026-08-08 on an ALREADY-ACCEPTED corpus, which is the worse form.** Saikyo's STA had
passed the ear under a previous session months earlier. Knowing none of that, I audited it with
derived thresholds and reported a list of defects — dead air, an incomplete loop, a mis-shared
cut — then a spectral band borrowed from keihin declared "0 of 24 files carry speech" when the
answer was 3. The ear then returned **25/25 PASS with every inherited cut unchanged**. Nothing was
ever wrong. The user: *"you, using your own scope, tell me something is broken."*

**Rule (second half):** a gate that already accepted authored content IS the standard for it.
Derived measurement can raise a question for the ear; it cannot return a verdict that the content
is wrong. And before auditing anything that already shipped, look for the prior verdict —
`audio_src/<line>/*_verify_results.json`. That tree is gitignored, so its absence proves nothing
and does not travel between machines; ask rather than assume a set is unverified. **The copy that DOES
travel is the line's `audio/README.md` section — read it before deriving any value it might already
hold.** 2026-08-22: seven `sta_cut` values were re-derived from `audio_id.structure` block boundaries for
a new Utsunomiya diagram; six landed within 80 ms of the by-ear figures and `nasushiobara` came out
**16.00 against the ear's 12.87**, because its cut sits inside a merged block — continuous ambience never
reaches the silence floor, so the instrument cannot see that boundary at all. The README said so, in the
section that also says those values "live here or nowhere". Self-caught, and only because the README was
opened later for an unrelated edit.

**Pattern:**
- A user-named file is ground truth. The detector's job becomes reproducing it; one that reports
  clean on that file is disqualified, not "mostly right."
- Treat a detected window as the INNER bound — human cuts land where the artifact stops being
  audible, which is further out than any threshold.
- Before applying a documented numeric convention across a corpus, check the corpus satisfies its
  premise (here: that the file has a near-silent floor to insert into). A band's known-positive
  must come from the corpus you are about to judge, never the one it was measured on.
- Don't rebuild the instruments. They are named in `_dev_scripts/audio_id.py` with a `--selftest`;
  re-deriving them per session is what makes these jobs hit-or-miss, and it is how the 0-of-24
  answer got produced. Four detectors in 2026-07-26, four more in 2026-08-08, same root.

**Scope:** all `sta-make` / `pa-make` detectors; anything gated by a by-ear pass; any re-audit of
content a human gate already passed.

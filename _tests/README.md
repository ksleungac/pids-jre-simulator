# `_tests/` — the test suite + coverage map

**Not shipped** (`_` prefix — dev / build-pre-flight only). This README **is the map**: it defines the tier hierarchy and, per tier, whether tests EXIST or are a known GAP. `run_all.py` is the *live* version of the same map (an empty tier prints a loud `NO TESTS (gap)`).

## Why this exists
Rendering is validated **by eye** (deliberate — preview screenshots + by-ear audio gates). But the silent-failure bugs — the ones that break a release build after a big change — live in the **pure-logic / data / deployment-frame** layer, not the pixels. As the project matured, the by-eye pass ran less often, so that class slipped through: v0.6.0 shipped three (a hardcoded version literal, a `_mock`-vs-`startswith("_")` route leak, a re-entry PA drop). Automated tiers catch that class **deterministically, every build** — they don't replace the by-eye pass, they cover the layer the eyeball never reliably caught.

## Test hierarchy
Bottom = broad / cheap / frequent. **Rendering is EXCLUDED** (by-eye by design).

| Tier | Type | Tests WHAT | Status | Home |
|---|---|---|---|---|
| **T0 Static** | lint / format | code *shape* — banned primitives, derivable literals, `.otf`, Black | ✅ EXISTS | pre-commit: `_dev_scripts/lint_primitives.py`, `check_fonts.py` |
| **T1 Unit** | unit, pure | the pure decisions of one feature; **no pygame, no I/O** | ◐ PARTIAL | `_tests/t1_unit/` |
| **T2 Contract** | schema / parity | authored *data* conforms + cross-file parity | ✅ EXISTS | `validate_data.py` (root) |
| **T3 Invariant** | integration, headless | cross-module *behavior* over real files, **no display** | ◐ PARTIAL | `_tests/t3_invariant/` |
| **T4 Clean-frame** | integration, state-absent | first-run / OOBE from a **deleted `settings.json`** | ◐ PARTIAL | `_tests/t4_clean_frame/` |
| **T5 Smoke / E2E** | smoke, frozen | the built **exe** boots + frozen-only paths (PE version, alongside-exe assets) | ⚠️ MANUAL | run against the exe post-build |
| — Rendering | *(excluded)* | pixel fidelity | — by-eye | preview screenshots + by-ear |

**Rendering is excluded from the TIERS, not from mechanical checking.** No test can assert a layout looks right — that is the eye's job, and it stays the eye's job. But a *change* to calibrated rendering code can be held to "nothing moved except what I intended", which is a different question and a mechanical one. Before editing a hand-calibrated renderer, snapshot the geometry it produces across every input production can reach — for the transfer panel that is every `(station, line_code, transfer_view)` the route corpus yields, capturing per-row positions, gaps, the placement rule taken, and a pixel hash — then re-snapshot after and diff. The diff is the deliverable: it turns "I think this is safe" into a count, and every panel that moved has to be explained or reverted. It also surfaces the changes you did **not** intend, which is the whole point (2026-08-21: a column-spacing fix silently pulled six stations off a calibrated fallback path onto a worse one; the snapshot caught it in one run and the fix was re-scoped before anything shipped). Keep the harness in the scratchpad — it is an instrument for one change, not a fixture to maintain (`principles.md` § "A rule is not a licence to expand scope"), and its oracle is the previous state, so it proves *no unintended movement*, never correctness.

**Fixture ≠ tier.** T4 is *not* a separate scope from T3 — it's the **integration tier run with the state-absent fixture** (deleted `settings.json`). The fixture axis (settings absent / present-valid / present-corrupt) is orthogonal to the scope ladder; the absent row gets its own label only because it's the one no dev machine ever exercises (`critical_lessons §6`). A startup integration test parametrizes over fixtures in one module — the absent row earns the T4 checkmark, the present rows are its T3 companions.

Gaps are intentional **for now** — the value is knowing the hierarchy *and* what's missing. Fill incrementally; a regression case is the highest-ROI first fill — but it joins a feature's module, it does not become one (next section).

## Module scope — a FEATURE, not a function and not an incident

**The tier picks the directory; the feature picks the file.** One module per feature seam, named for the behaviour it protects. A regression case joins the module that already owns that behaviour. **A new file means a new seam exists — not that a new bug was found.**

Naming a test file after the bug that prompted it is `conventions.md § Naming`'s discovery-instance trap, one artifact over: there it corrupts a pattern's name, here it decides the shape of the whole suite. Two costs, and the second is the expensive one:

- The suite reads as **a list of past bugs** rather than a statement of what the system must do. `_tests/t1_unit/` should answer "what does auto-drive guarantee?" — twelve incident-named files answer "which twelve things went wrong."
- **Coverage gaps go invisible.** A per-incident file answers *is this bug back?*; nothing answers *does the decision layer decide correctly?* The enumeration the suite is built from becomes "the incidents that happened", and a gate built from an enumeration cannot see a gap in that enumeration (`critical_lessons §9`).

A feature legitimately spans tiers — its pure decisions in T1, its stateful behaviour in T3 — and that is two modules of the same name in two directories, not two features. `test_stream.py` exists in both: T1 holds who may bind and where a tap maps to, T3 holds frames keeping up and taps reaching the event queue.

The incident still earns its keep, in the CASE and its comment — the case says what broke, dated, so nobody deletes it as redundant. It just does not get a file.

## How to add a test
1. **Pick the tier by what it tests** — a pure function → T1; a cross-module behavior asserted headlessly → T3; a path reached only when persisted state is absent → T4.
2. **Find the module that owns the behaviour and add a case to it.** Only when no module owns it does a new `_tests/t<N>_<tier>/test_<feature>.py` get created — named for the feature, never for the bug. See § "Module scope" above. A new module's first line is `# TIER: T<N> — <feature>`, above the docstring.
   - **Cover the SEAM, not the case that brought you.** Once you are writing against a seam, write what it guarantees — every branch, the ordering between them, the gate each one sits behind — not only the branch your fix touched. A single case bolted into whichever module happened to have a usable harness is the incident-shaped test § "Module scope" bars, and it arrives pre-disguised: the suite is green, the bug is locked, and the neighbouring branches are as unwatched as before. 2026-08-30: three cases for two AutoDriver signals were appended to `test_playback.py`, whose feature is STA playback. Asking what the seam actually was — `_handle_input_main`, one frame of input dispatch — produced `test_input_dispatch.py` and 20 cases, and the PA branch's audio gate, the `critical_lessons §5` case and older than either fix, turned out to have had no coverage at all. Author: *"don't just monkey patch test cases, you might generate the whole suite cases for the module of unit tests."*
3. **Plain script, no framework:** exercise the behavior, `assert`, print a one-line `PASS: <subject>` on success, and `sys.exit(1)` (after printing what failed) on failure. **No pytest** — deferred, not rejected: adopt it only when a tier fills enough that `parametrize`/fixtures would *cut* code ("add structure when pain forces it").
4. `run_all.py` auto-discovers it (`test_*.py` glob) — it joins the map automatically.

## Running
```
uv run _tests/run_all.py
```
Runs every physical test, prints one status line per tier; an empty tier prints a loud `NO TESTS (gap)`. **Exit 1 iff a test FAILS** — a gap is *visible*, not blocking. Called by `/build` pre-flight alongside `check_deps`.

## Coverage map — what each module guarantees

Status: `✅` done · `◐` partial · `⬜` buildable now · `🔒` blocked on an artifact we don't have yet.

One row per module, because one module is one feature (§ "Module scope"). A regression case lands in the row that owns the behaviour.

| module | tier | guarantees |
|---|---|---|
| `test_auto_driver.py` | T1 | the whole decision pipeline: read gates (badge-reject score gate · stopping-offset badge gate · distance plausibility guard + hold-last-good) · `inferred_state()` 16-cell truth table · `update()` direct-read stream A–N · re-entry resolve grid + commit shape · `_fire_at_station` reachability drain |
| `test_ocr_read.py` | T1 | the read itself: `profile_for` capture geometry (16:9, 16:10 letterbox, every refusal) · glyph matching under 8 measured degradations · decimal-stop vs digit-fragment · speed value domain |
| `test_lower_lcd.py` | T1 | 8-station window + FULL-slot lock (pointer-always-visible) · 5-station content incl. passing stations · band-fill slot-enter trigger |
| `test_window.py` | T1 | zoom pick / ceiling / drag-snap · the single window→LCD transform |
| `test_bell.py` | T1 | the departure-bell box: state derived from the audio · cap hit-test incl. the dead band and the window→canvas divide · its window's own whole-multiple zoom + drag snap + placement beside the PA window · a remote tap resolving through the same geometry · ON-latches / OFF-momentary press asymmetry |
| `test_playback.py` | T1 | one Page Up press fires once · STA loop/cut dispatch |
| `test_input_dispatch.py` | T1 | one frame of `_handle_input_main`: the PA branch's audio gate (a deferred `pending_next_pa` survives and fires once free) · both AutoDriver signals on the consume side — the re-entry advance's `at_station` re-check, the at-station drain's ordering ahead of the press · the `if/elif` masking order · which stream End pauses |
| `test_startup.py` | T1 | language resolution · audio-root resolution · the start-station grid |
| `test_stream.py` | T1 + T3 | who may bind + where a tap maps + which view owns a tap when a second one is docked (T1); frames keeping up + taps reaching the event queue (T3) |
| `test_publish_memory.py` | T1 | narrative merge logic — block/entry dedup, divergence union, edited-content refusal |
| `test_publish_memory_transport.py` | T3 | the journal-ref transport: bootstrap orphan commit, chained publish, master-untouched, two-folder race union, idempotent re-run. Keeps a distinct name because it is a different subject (the git transport), not the same feature one tier up |
| `test_ocr_reads.py` | T3 | the production OCR pipeline over committed real-HUD fixtures, both resolutions |
| `test_change_scheduler.py` | T3 | lower-LCD change scheduling (the flash fix, #78) |
| `test_e0_fill_centerline.py` | T3 | e235_0 band-fill centerline derived from the mask, not restated |
| `test_clean_frame_startup.py` | T4 | first-run from a deleted `settings.json` — language done; OOBE + OCR-consent walk still `⬜` |
| `test_wrap_cache.py` | T1 | the consent-body wrap cache keys on font + width (#60) |

`test_ocr_reads.py` was migrated from the former `_dev_scripts/validate_ocr.py`, which read gitignored 186 MB screenshots and never ran at build pre-flight. Its ground truth is committed real pixels plus hand labels, so it cannot be born wrong agreeing with the code; `--deep` re-sweeps the local calibration set when present, and `_dev_scripts/extract_ocr_assets.py` regenerates it.

## Cross-cutting invariants

These are not local to any module, so each module asserts its own FACET and says so at the assertion.

**`PASSING ≡ MOVING`.** Every badge-consumer must honor it, each in its own form. Sites: `inferred_state()` (identical state) · `update()` (segment-reset on `STOPPED→(MOVING|PASSING)`, arrival gated MOVING-only) · `_resolve_reentry_target()` (PASSING = MOVING with no usable distance). **A new badge-consuming function must be added to this list and its facet asserted** — the 2026-07-16 incident was one uncovered site while the others were fine, which is how per-function testing of a cross-cutting rule gives false comfort.

**`badge > distance, speed`.** The badge is the gate the noisier reads are judged against, never the thing being second-guessed. Asserted across all three read gates in `test_auto_driver.py` §1.

## Method notes

**Test the raw-reading→decision path**, not just the tidy lookup downstream. T1 catches a decision bug at its root (a function's return value); the symptom — a cross-function flag interaction eats the departure PA — is a T3 that needs a real drive.

**T3 is the highest-value tier, conditioned on realistic varied inputs.** Real recorded drives hold the edge cases nobody would think to script; the re-entry incident is the proof, since a hand-written T3 would likely have missed it too. T1 is cheaper and pinpoints which unit broke.

**Coherence ≠ correctness.** A "code matches the documented table" test is insufficient when the doc itself carries internal drift — the re-entry incident's spec and code were born wrong together (`d7320b9`), so they agreed. Test against the deepest invariant (the truth-table `MOVING≡PASSING`), never a derived restatement.

**Retiring a code path retires its test arm — and the assets that arm keeps alive.** A test that still exercises the old path looks like coverage while verifying something production no longer does. Worse, it is a *consumer*, so the assets the old path needed still have a reader and no dead-asset check fires. The pair hides each other. 2026-08-19: OCR had gone single-model months earlier, but T3 still read each fixture natively at its own resolution, which is the only reason a second full template set was still committed and shipping. Deleting the arm is what made the assets visibly dead. When a path goes, sweep for its test arm in the same change, and ask what the arm was the last reader of.

## Known gaps

- `⬜ T3` **replay harness** (`replay_drive.py`) — reads a `_recordings/*.jsonl`, replays its `sample` stream through `_Detector`, asserts invariants (**exactly one FIRE_DEPARTURE per segment**, departure never eaten, arrival once per stop). Buildable now against a synthetic JSONL; every real recording then drops in as a case for free.
- `🔒 T3` **real-drive corpus** — the recorded JSONL(s) the harness replays. First target: Saikyo ex-Shibuya (parked → PASSING@low speed → depart) — the incident sequence on real input. BLOCKED on the recording.
- `⬜ T3` **event → fire-gate → app-advance** — `FIRE_DEPARTURE` actually reaches `pending_next_pa`/`_next_pa`, respecting the app-sub-state gate + manual-press precedence.
- `◐ T3` **consensus / commit** — `_maybe_reentry` two-probe latch + app-parked gate (stateful/threaded; partly manual). The bg→main signals' CONSUME side graduated to T1 `test_input_dispatch.py` on 2026-08-30: what the main thread does with `pending_silent_advance` / `pending_pa_drain` is a pure per-frame decision and needs no thread. What stays here is the write side and the hand-off itself.
- `⬜ T3` — `version tag == display_version()` · picker enumeration excludes every `_`-prefixed route · normal-launch full-wiring (screens-skipped) headless walk
- `⬜ T3` **4K OCR fixtures** — 1080p has a committed cell + frame set under `fixtures/ocr/`, 1440p has frames; 4K has only the resolution-independent shape invariant. Its geometry was proven on a live drive (941 samples) and nothing locks it. One HUD grab into `fixtures/ocr/2160p/` with a manifest makes it a real gate — runbook in [`auto_input/README.md`](../auto_input/README.md) § "Adding a new resolution" step 3.
- **Cell fixtures pin the READER; frame fixtures pin the GEOMETRY.** A committed cell is already cropped, so it never asks a profile where that cell is — only a frame entry does. Every cell type therefore needs a frame entry or its bbox is unguarded: `speed_value_bbox` had none until 2026-08-19, and a 70 px shift of it passed the whole suite. Adding a cell type is not enough; add the frame entry too.
- **bg/main-thread atomicity** — not unit-testable; T5 / manual.

See [`conventions.md § Tooling`](../.claude/rules/conventions.md) "canonical-source duplication" for the T0/T3 defense this suite backs.

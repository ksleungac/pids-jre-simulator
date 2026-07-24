# `_tests/` — the test suite + coverage map

**Not shipped** (`_` prefix — dev / build-pre-flight only). This README **is the map**: it defines the tier hierarchy and, per tier, whether tests EXIST or are a known GAP. `run_all.py` is the *live* version of the same map (an empty tier prints a loud `NO TESTS (gap)`).

## Why this exists
Rendering is validated **by eye** (deliberate — preview screenshots + by-ear audio gates). But the silent-failure bugs — the ones that break a release build after a big change — live in the **pure-logic / data / deployment-frame** layer, not the pixels. As the project matured, the by-eye pass ran less often, so that class slipped through: v0.6.0 shipped three (a hardcoded version literal, a `_mock`-vs-`startswith("_")` route leak, a re-entry PA drop). Automated tiers catch that class **deterministically, every build** — they don't replace the by-eye pass, they cover the layer the eyeball never reliably caught.

## Test hierarchy
Bottom = broad / cheap / frequent. **Rendering is EXCLUDED** (by-eye by design).

| Tier | Type | Tests WHAT | Status | Home |
|---|---|---|---|---|
| **T0 Static** | lint / format | code *shape* — banned primitives, derivable literals, `.otf`, Black | ✅ EXISTS | pre-commit: `_dev_scripts/lint_primitives.py`, `check_fonts.py` |
| **T1 Unit** | unit, pure | one pure function's input→output; **no pygame, no I/O** | ◐ PARTIAL | `_tests/t1_unit/` |
| **T2 Contract** | schema / parity | authored *data* conforms + cross-file parity | ✅ EXISTS | `validate_data.py` (root) |
| **T3 Invariant** | integration, headless | cross-module *behavior* over real files, **no display** | ◐ PARTIAL | `_tests/t3_invariant/` |
| **T4 Clean-frame** | integration, state-absent | first-run / OOBE from a **deleted `settings.json`** | ◐ PARTIAL | `_tests/t4_clean_frame/` |
| **T5 Smoke / E2E** | smoke, frozen | the built **exe** boots + frozen-only paths (PE version, alongside-exe assets) | ⚠️ MANUAL | run against the exe post-build |
| — Rendering | *(excluded)* | pixel fidelity | — by-eye | preview screenshots + by-ear |

**Fixture ≠ tier.** T4 is *not* a separate scope from T3 — it's the **integration tier run with the state-absent fixture** (deleted `settings.json`). The fixture axis (settings absent / present-valid / present-corrupt) is orthogonal to the scope ladder; the absent row gets its own label only because it's the one no dev machine ever exercises (`critical_lessons §6`). A startup integration test parametrizes over fixtures in one module — the absent row earns the T4 checkmark, the present rows are its T3 companions.

Gaps are intentional **for now** — the value is knowing the hierarchy *and* what's missing. Fill incrementally; **regression-test-per-incident** is the highest-ROI first fill.

## How to add a test
1. **Pick the tier by what it tests** — a pure function → T1; a cross-module behavior asserted headlessly → T3; a path reached only when persisted state is absent → T4.
2. Add `_tests/t<N>_<tier>/test_<subject>.py`. First line: `# TIER: T<N> — <subject>`.
3. **Plain script, no framework:** exercise the behavior, `assert`, print a one-line `PASS: <subject>` on success, and `sys.exit(1)` (after printing what failed) on failure. **No pytest** — deferred, not rejected: adopt it only when a tier fills enough that `parametrize`/fixtures would *cut* code ("add structure when pain forces it").
4. `run_all.py` auto-discovers it (`test_*.py` glob) — it joins the map automatically.

## Running
```
uv run _tests/run_all.py
```
Runs every physical test, prints one status line per tier; an empty tier prints a loud `NO TESTS (gap)`. **Exit 1 iff a test FAILS** — a gap is *visible*, not blocking. Called by `/build` pre-flight alongside `check_deps`.

## Build plan & known gaps

Status: `✅` done · `⬜` buildable now · `🔒` blocked on an artifact we don't have yet.

### Auto-driver decision logic (2026-07-16 — re-entry PASSING incident)
Order = buildable first, blocked last. **Guiding principle: test the raw-reading→decision path** (where the bug lived), not just the tidy lookup downstream. T1 catches this bug at its **root** (the resolver's return value); the **symptom** — a cross-function flag interaction eats the departure PA — is a T3 that needs a real drive.

**Value ranking:** T3 is the highest-value tier — *conditioned on realistic, varied inputs.* Real recorded drives hold the edge cases nobody would think to script (this bug is the proof: a hand-written T3 would likely have missed it too, because the failing sequence wasn't in anyone's imagination). T1 is cheaper and **pinpoints which unit broke**; T3 proves the composed system works on real data, and its worth scales with the size of the recorded corpus. The replay **harness is buildable now** (validate against a synthetic JSONL); only the real corpus is blocked.

**Cross-cutting invariant — `PASSING ≡ MOVING`:** not local to any one function; **every badge-consumer must honor it**, each in its own form. Sites: `inferred_state()` (identical state) · `update()` (segment-reset on `STOPPED→(MOVING|PASSING)` + arrival gated MOVING-only) · `_resolve_reentry_target()` (PASSING = MOVING with no usable distance). Each T1 above tags its PASSING check as a *facet* of this one invariant. **A new badge-consuming function must be added to this list and its facet asserted** — the incident was one uncovered site while the others were fine, which is how per-function testing of a cross-cutting rule gives false comfort.

**Coherence ≠ correctness:** a "code matches the documented table" test is **insufficient** when the doc itself carries internal drift — the re-entry incident's spec (the re-entry table) and code were born wrong *together* (`d7320b9`), so they agreed. Test against the **deepest invariant** (the truth-table `MOVING≡PASSING`), never a derived restatement. And a cost note: nailing a truth-table spec by discussion is expensive — the **recorded-drive corpus (T3) is the primary regression asset** once it exists; the T1 grids are the logic-clarifying, lower-value half.

1. `✅ T1` **`test_inferred_state.py`** — `_Detector.inferred_state()`, exhaustive 16-cell truth table + `MOVING≡PASSING`. *Done 2026-07-16.* Foundation only — the display lookup, **not** the bug site.
2. `✅ T1` **`test_detector_update_seq.py`** — `_Detector.update()`, the DIRECT read (raw sample → events/flags). Cases A–N: departure level-test + no-refire debounce · arrival level-test · **PASSING skips arrival** · `STOPPED→MOVING` segment reset · black-screen cross-reject · departure-through-PASSING · band edges · **L** at-station fires on any STOPPED in transit (reachability rule) · **M** post-click-jump arrival still fires at-station · **N** witnessed-edge departure fires with no speed ceiling (the 2026-07-24 dropout-through-band incident). **Highest-value T1;** stateful (call sequence). *2026-07-16; extended 2026-07-24.*
3. `✅ T1` **`test_reentry_target.py`** — `AutoDriver._resolve_reentry_target()`, the re-entry gate. Grid + facets: `PASSING ≡ MOVING-no-dist` · never `1B` on PASSING · **provenance** (a witnessed edge → every cell None) · **pa=1** (no `1B` target, falls through to `1A`) + the 2026-07-23 short-segment regression anchor + `#82` strictness + guards. SimpleNamespace sim stub. *2026-07-16; extended 2026-07-23/24.*
3a. `✅ T1` **`test_fire_at_station.py`** — `AutoDriver._fire_at_station()`, the reachability drain. A missed arrival (`cnt_pa` not at the last approach PA) is silently drained so the press still lands STOPPING; normal 1B, pa=1 collapse, and the app-parked skip. *Done 2026-07-24.*
3b. `✅ T1` **`test_reentry_commit.py`** — `AutoDriver._maybe_reentry()` commit shape: a pa≥2 `1A` commit is silent; a pa=1 `1A` commit is AUDIBLE (the single announcement is never stale). *Done 2026-07-24.*
4a. `⬜ T3` **replay harness** (`replay_drive.py`) — reads a `_recordings/*.jsonl`, replays its `sample` stream through `_Detector`, asserts invariants (**exactly one FIRE_DEPARTURE per segment**, departure never eaten, arrival once per stop). **Buildable now** against a synthetic JSONL; every real recording then drops in as a case for free.
4b. `🔒 T3` **real-drive corpus** — the recorded JSONL(s) the harness replays. First target: Saikyo ex-Shibuya (parked → PASSING@low speed → depart) — the incident sequence, the eaten-PA symptom on real input. **BLOCKED** on the recording.
5. `⬜ T3` **event → fire-gate → app-advance** — `FIRE_DEPARTURE` actually reaches `pending_next_pa`/`_next_pa`, respecting the app-sub-state gate + manual-press precedence. GAP (detector + AutoDriver + sim).
6. `⬜ T3` **consensus / commit** — `_maybe_reentry` two-probe latch + app-parked gate + bg→main `pending_silent_advance` signal. GAP (stateful/threaded; partly manual).

**Known gaps with no owner yet** (documented so they stay visible):
- OCR pixel→symbol reads — owned by T3 `test_ocr_reads.py` (exists; full badge/limit/offset coverage incl. PASSING, both resolutions, over committed fixtures).
- bg/main-thread atomicity — not unit-testable; T5 / manual.

**Codify after green:** the *"decision fn = build the spec table, don't read it for plausibility"* review lens → `review-dirty`; wire `run_all.py` into `/build` pre-flight.

### Other incidents' first fills
- `✅ T3` — `test_ocr_reads.py` — production OCR pipeline reads correct values from committed real-HUD fixtures (`_tests/fixtures/ocr/<res>/`): full-coverage cropped cells (read logic) + capture-region quadrant frames (crop geometry), both resolutions. Migrated from the former `_dev_scripts/validate_ocr.py` (which read gitignored 186 MB screenshots and never ran at build pre-flight). Ground truth = committed real pixels + hand labels, so it can't be born-wrong-agreeing-with-code. `--deep` re-sweeps the local calibration set when present. Regenerated by `_dev_scripts/extract_ocr_assets.py`.
- `✅ T1` — `resolve_language()` saved-or-detect, screen-free (`test_resolve_language.py`) — the language-picker incident's unit-level lock
- `✅ T1+T3` — `publish_memory` narrative pipe: T1 merge logic (block/entry dedup, divergence union, edited-content refusal — mutation-proven ×3) + T3 sandboxed journal-ref transport (bootstrap orphan commit, chained publish, **master-untouched assertion**, two-folder race union, idempotent re-run) — `test_publish_memory.py` / `test_publish_memory_transport.py`
- `◐ T4` — clean-frame startup (`test_clean_frame_startup.py`): language **done** (absent/valid/corrupt fixtures + picker-removed guard); OOBE + OCR-consent full-wiring walk still `⬜` (needs the startup path made display-free)
- `⬜ T3` — `version tag == display_version()` · picker enumeration excludes every `_`-prefixed route · normal-launch full-wiring (screens-skipped) headless walk

See [`conventions.md § Tooling`](../.claude/rules/conventions.md) "canonical-source duplication" for the T0/T3 defense this suite backs.

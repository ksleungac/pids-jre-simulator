# WIP — OCR multi-resolution / 4K support

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** the in-flight Phase-2 design for scalable multi-resolution OCR support, plus the empirical findings that back it. This is a brainstorming capture, not an approved spec — the HARD-GATE still applies (no implementation until the design is approved).
>
> **Refuses:** implementation code, and any decision presented as final that the user has not approved. Open questions stay marked open.
>
> **Dissolves into:** `auto_input/README.md` (Resolution dependency / HUD layout / Recalibration sections) when the feature ships; this file is then deleted.
>
> **Status (2026-07-21):** PAUSED (design consolidation), but **"logic hardening" is actively shipping** — see § "Relationship to the logic-hardening method" for the rules landed. **1080p is the confirmed CANONICAL resolution and the absolute-stability target** (user, 2026-07-21): because the resume design downscales every input to 1080p (Finding 2), the 1080p pipeline must be rock-solid — it is what real users run through, not the crisp higher-native 1440p. Bugs that are invisible on a dev machine's crisp 1080p capture but bite a user's softened capture are the priority (see `critical_lessons.md §7`).

## Goal

Support additional screen resolutions (next target: 4K / 3840×2160) without the current per-resolution manual burden: capturing calibration screenshots, hand-authoring a `ResolutionProfile`, and re-extracting templates for each new resolution. The maintainer cannot repeat that for every resolution combination.

## Empirical findings (measured this session)

Tests run against the committed `_tests/fixtures/ocr/` cells + frames on this machine. Scratch experiments were one-off; the results below are the durable takeaways.

1. **Pure scaling of the *pipeline* works between 1080p and 1440p.** Running the 1080p fixtures with 1440p templates NN-resized: speed-limit 19/19, badge 6/6 (once the anchor is resized to the cell shape), dark digits already shared. The per-resolution 1080p template sets are therefore largely redundant with the current `compare()` NN-resize.
   - The badge classifier currently returns 0/6 with mismatched-shape anchors only because `classify_badge_state` *skips* any anchor whose shape ≠ the cell — a code limitation, not a scaling failure.

2. **The correct direction is to normalize the *input*, never the templates.** Pick one canonical internal processing resolution, keep its native templates, and downscale every captured HUD region to it. Since real targets are all ≥ 1080p (1080p / 1440p / 4K), making **1080p the canonical** means every input downscales — never upscales, never scales a template. (The maintainer's earlier "1080p doesn't work by scaling" was from scaling the *templates* down, which is the wrong direction.)

3. **Misalignment tolerance is a bounded window, not a cliff** (HUD-box perturbed, then resized to canonical; `1px ≈ 0.29%` of HUD width):

   | Cell | Shift tolerance | Scale tolerance |
   |---|---|---|
   | Badge | ±8px+ | ±4%+ |
   | Speed limit | ±8px+ | ±4%+ |
   | Stopping offset | ~±6px (breaks at ±8) | **~±1–2% (breaks at ±3%)** |

   The stopping-offset cell (smallest digits) is the **canary**, and the **scale axis** is what breaks it, not position. Consequence: if the offset reads correctly, the box is aligned — misalignment is self-announcing through the live reads.

4. **Real-world fact (maintainer):** the game HUD **"only scales, no other changes"** across resolutions — no reflow, no repositioning, aspect constant. So the internal cell layout (Distance / Speed / Badge / limit positions within the HUD) is fixed, and a single canonical internal layout is valid.

## Proposed architecture (direction, not yet approved)

One pipeline for every resolution:

> **user-drawn (or preset) HUD rect → grab that monitor's output → resize the rect to the canonical 1080p HUD → existing 1080p OCR pipeline.**

- **Collapses** the per-resolution `ResolutionProfile` / `PROFILES` / resolution-gate machinery and per-resolution template extraction into: one canonical template set + a HUD rect.
- **Multi-monitor & windowed** fall out for free: capture follows the selected rect's monitor/output (fixes the current "primary monitor only" limit — see `auto_input/README.md` Limitations).
- **Native support for common resolutions is subsumed, not voided.** A "native resolution" becomes a **shipped preset box** (four numbers) auto-applied when a common screen size is detected → zero-config for the common case. The user-select box is the universal fallback. Net maintenance is *lower* than today (one template set + tiny presets vs. per-resolution templates + calibration screenshots).

## UX direction

- A calibration step shows a **50%-opaque box** the user aligns to the real game HUD.
- **Lock the box to the HUD's fixed aspect ratio** (the HUD only scales), removing the scale-drift axis — the one that breaks the offset canary — and leaving only position + uniform size.
- **Live reads as the confirmation:** overlay the live speed / distance / badge readout (offset as canary) so the user aligns by eye and verifies by numbers, landing inside the ±2% window without needing precision. Reuses the existing status-band read rendering.
- Auto-propose a starting box (spectrum: a resolution-scaled default → a multi-scale template match on the badge pentagon to *find* the HUD).

## Open questions (unresolved — for resume)

- Canonical internal resolution: 1080p is the leaning, not locked.
- Auto-propose level to build first: cheap default box vs. landmark-match auto-detection.
- Common resolutions: silently apply the preset (zero-config) vs. always show the calibration screen with the preset pre-filled for confirmation. (First-run lessons argue for confirm.)
- **4K is reasoned, not measured** — no 4K calibration image exists. One 4K HUD grab would let the Phase-1 fixture framework (`_tests/t3_invariant/test_ocr_reads.py`) lock 4K→1080p downscale as a real test.
- How the preset boxes are stored/keyed, and how a user-selected box is persisted per setup.

## Relationship to the logic-hardening method

"Logic hardening" = OCR-read robustness rules at the reader/driver layer, independent of resolution. Shipped so far (all T1/T3-tested):

- **Speed domain rectify** (`_rectify_speed`, `ocr.py`, 2026-07-19) — a read above the 140 km/h ceiling (drivable max 135 + slack) drops one trailing digit and re-checks, recovering the decimal-slip misread (`72.7 → "727" → 72`) instead of dropping the sample. Now a rarely-exercised backstop behind the decimal-stop fix below.
- **Stopping-offset speed gate** (`_accept_stopping_offset`, `driver.py`, 2026-07-19) — the ±cm offset is accepted only at `speed == 0` (later `badge == "STOPPED"`), rejecting scenery-green phantoms; rejections log an `offset_reject` event.
- **1-column-tolerant decimal-stop** (`segment_chars`, `ocr.py`, 2026-07-20) — the decimal search scans the raw column-runs, not the finalized digit bboxes, so a decimal dot that binarized to a single dark column (the 1080p / softened-capture failure — `critical_lessons.md §7`) is still found and the tenths no longer slips into the integer. The exact-resolution reason 1080p was fragile and 1440p was not (dot 2 vs 3–4 columns). T3 speed-cell fixtures incl. a rectify-proof `5.3→5` regression cell.
- **Badge-reject score gate** (`_apply_badge_reject_gate`, `driver.py`, 2026-07-21) — when `badge is None` (classifier reject = degraded frame), drop any `speed`/`distance`/`speed_limit` read below `BADGE_NONE_SCORE_GATE` (0.80); conditional on badge-reject, so it supplies the honest threshold a global score floor lacked. Data: badge=None reads sit at score ~0.60 vs ~0.90 when the badge reads. Emits a `score_gate` event.

**Why it matters to THIS design:** hardening each read widens the pipeline's misread tolerance, which directly softens the ±2% scale-alignment cliff the user-drawn-box approach introduces (the stopping-offset canary in Finding 3). More per-read robustness ⇒ more forgiving box alignment ⇒ less precision the calibration UX must force the user to hit. Fold further hardening rules here as they land (candidates under discussion: digit-read score-gating, at-station speed gate), then re-weigh how tight the box-alignment UX actually needs to be.

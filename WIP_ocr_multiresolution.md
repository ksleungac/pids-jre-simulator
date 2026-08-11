# WIP — OCR multi-resolution / 4K support

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** the in-flight Phase-2 design for scalable multi-resolution OCR support, plus the empirical findings that back it. This is a brainstorming capture, not an approved spec — the HARD-GATE still applies (no implementation until the design is approved).
>
> **Refuses:** implementation code, and any decision presented as final that the user has not approved. Open questions stay marked open.
>
> **Dissolves into:** `auto_input/README.md` (Resolution dependency / HUD layout / Recalibration sections) when the feature ships; this file is then deleted.
>
> **Status (2026-08-09):** **downscaling is the ONLY path.** Every capture is downscaled into the one 1080p model; the per-resolution path and its `--legacy-ocr` lever were retired once three live drives had confirmed it. See § "Downscale path (shipped)". The UX half (user-drawn box, presets, auto-propose) is still unbuilt and unapproved; the HARD-GATE stands for that half only. **1080p is the model resolution and the absolute-stability target** (user, 2026-07-21): every input downscales into it, so it is what real users run through, not the crisp higher-native 1440p. Bugs invisible on a dev machine's crisp capture but biting a user's softened one are the priority (`critical_lessons.md §7`).

## Goal

Support additional screen resolutions (next target: 4K / 3840×2160) without the current per-resolution manual burden: capturing calibration screenshots, hand-authoring a `ResolutionProfile`, and re-extracting templates for each new resolution. The maintainer cannot repeat that for every resolution combination.

## Empirical findings (measured this session)

Tests run against the committed `_tests/fixtures/ocr/` cells + frames on this machine. Scratch experiments were one-off; the results below are the durable takeaways.

1. **Pure scaling of the *pipeline* works between 1080p and 1440p.** Running the 1080p fixtures with 1440p templates NN-resized: speed-limit 19/19, badge 6/6 (once the anchor is resized to the cell shape), dark digits already shared. The per-resolution 1080p template sets are therefore largely redundant with the current `compare()` NN-resize.
   - The badge classifier returns 0/6 with mismatched-shape anchors only because `classify_badge_state` *skips* any anchor whose shape ≠ the cell — a code limitation, not a scaling failure. **This dissolves under normalise-the-input rather than needing a fix**: every frame arrives at the canonical HUD size, so the badge cell always matches the canonical anchor shape. Confirmed by the PoC — badge reads 6/6 through the canonical path at both resolutions. Don't carry it forward as a task.

2. **The correct direction is to shrink the *input*, never the templates.** Build one model at a single resolution, keep its native templates, and downscale every captured HUD region into it. Since real targets are all ≥ 1080p (1080p / 1440p / 4K), making **1080p the model** means every input downscales — never upscales, never scales a template. (The maintainer's earlier "1080p doesn't work by scaling" was from scaling the *templates* down, which is the wrong direction.)

3. **Misalignment tolerance is a bounded window, not a cliff** (HUD-box perturbed, then downscaled into the model; `1px ≈ 0.29%` of HUD width):

   | Cell | Shift tolerance | Scale tolerance |
   |---|---|---|
   | Badge | ±8px+ | ±4%+ |
   | Speed limit | ±8px+ | ±4%+ |
   | Stopping offset | ~±6px (breaks at ±8) | **~±1–2% (breaks at ±3%)** |

   The stopping-offset cell (smallest digits) is the **canary**, and the **scale axis** is what breaks it, not position. Consequence: if the offset reads correctly, the box is aligned — misalignment is self-announcing through the live reads.

   **These numbers predate the 2026-07-21/22 hardening** (adaptive per-cell threshold, `compare_tolerant`, the decimal gap-guard, the distance guard — all listed below). Tolerance widens the window, so the real cliff is probably more forgiving than ±1–2% now. **Re-measure before the calibration UX is designed around it** — designing to a stale cliff forces more alignment precision on the user than the pipeline needs, and the sweep is cheap against the committed fixtures.

4. **Real-world fact (maintainer):** the game HUD **"only scales, no other changes"** across resolutions — no reflow, no repositioning, aspect constant. So the internal cell layout (Distance / Speed / Badge / limit positions within the HUD) is fixed, and a single canonical internal layout is valid.

## Proposed architecture (direction, not yet approved)

One pipeline for every resolution:

> **user-drawn (or preset) HUD rect → grab that monitor's output → downscale the rect into the 1080p model → existing 1080p OCR pipeline.**

- **Collapses** the per-resolution `ResolutionProfile` / `PROFILES` / resolution-gate machinery and per-resolution template extraction into: one template set + a HUD rect.
- **Multi-monitor & windowed** fall out for free: capture follows the selected rect's monitor/output (fixes the current "primary monitor only" limit — see `auto_input/README.md` Limitations).
- **Native support for common resolutions is subsumed, not voided.** A "native resolution" becomes a **shipped preset box** (four numbers) auto-applied when a common screen size is detected → zero-config for the common case. The user-select box is the universal fallback. Net maintenance is *lower* than today (one template set + tiny presets vs. per-resolution templates + calibration screenshots).

## Downscale path (shipped, 2026-07-26)

`sampling.downscale_hud` cuts the HUD from the captured region and resizes it to the model's
262×360; readers then run against `DOWNSCALE_PROFILE`. This is what every resolution does —
the old per-resolution path was retired 2026-08-09 (see § "Open questions").

**Geometry maps exactly.** Every 1440p cell bbox × 0.75 equals its 1080p counterpart with
zero rounding drift (badge `(29,122,111,40)` → `(22,92,83,30)`, and the same for speed /
limit / distance), and the HUD-in-capture origin `(920,20)` → `(690,15)`. Nothing needed
re-authoring; the existing 1080p profile IS the model.

**Reads are unchanged on real input.** Over all 23 local 1440p calibration screenshots (26
reads incl. tenths), through the production crop path: 26/26 either way. Same on the
committed quadrant frames at both resolutions. Locked by T3 `test_ocr_reads.py`.

**What downscaling costs, measured.** A downscaled 1440p HUD has edge acutance 0.351 vs the
reporter's real degraded 1080p capture at 0.361 and crisp dev 1080p at 0.529 — the resize
spends about one real-world degradation budget up front. It still reads 26/26, because the
§7-era hardening was built for exactly that softness. Under added synthetic blur the two
paths hold identically to σ=1.0; from σ=1.5 the downscaled one drops 2 more reads, and
**the entire gap is the tenths digit** — every decision-driving read (badge, speed,
speed_limit, stopping_offset) tracks the native path exactly, and the tenths is log/report
only and degrades to `None`, never to a wrong integer. The cost falls on the one field that
cannot affect a fire.

**Resampler: area/box average** (`sampling._resize_area`), separable, computed from a
cumulative sum so cost is one pass whatever the ratio — ~10 ms per 1440p HUD, ~15 ms at 4K.
Correct at every ratio by construction, which is what "one model for all resolutions" needs.
Chosen after measuring four candidates on READ ACCURACY (not pixel fidelity — see § "The
resampler shootout" below).

**Confirmed on live driven pixels at both resolutions** — see § "Live results".

## Live results (2026-07-26)

All three driven through `ocr_observe`, which runs the production read path.

| | 1440p (ratio 0.75) | 4K (ratio 0.50) | 1920×1200 (ratio 1.00, letterboxed) |
|---|---|---|---|
| live samples | 792 over 453 s | 941 over 566 s | 1493 over 840 s (2 drives) |
| badge / speed / distance / limit read | 100 / 100 / 98.4 / 100 % | 99.1 / 99.3 / 98.2 / 99.4 % | 99.3 / 99.3 / 98.6 / 99.3 % |
| tenths | 99.5 % | 99.3 % | 99.0 % |
| speed_score median | 0.880 | **0.883** | 0.897 |
| dist_score median | 0.875 | 0.869 | 0.892 |
| badge_diff median (reject at 50) | 9.8 | 10.1 | **1.2** |
| implausible distance jumps | 0 | 0 | see note |

**The jump row is not comparable across columns.** The 0s were measured under a rule the
2026-08-10 session could not reconstruct; re-measuring every recorded run with one consistent
rule — distance GROWING by >10 m between consecutive accepted reads — gives 2–6 per run at
*every* resolution, 1080p through 4K, including the two columns showing 0. The 1200p drives
score 3 and 4, i.e. the shared noise floor rather than a regression. The row is left as
recorded rather than overwritten, since a new instrument does not get to overturn a prior
verdict (`critical_lessons.md` §11).

**Halving the ratio costs nothing measurable.** Confidence scores are flat — speed is
fractionally *higher* at 4K — which is the metric that would move first if the resampler
under-filtered. The 4K read-rate dip is one 4-second black-screen event at the end of the
run (8 frames, badge_diff 68–134 against a threshold of 50), not a steady rate: **0 frames
lost speed while the badge read fine**, so the pipeline degrades as a whole frame or not at
all, never as isolated garbage.

This also confirms the **interpolated 4K geometry** — all four cells reading at ~99% with
1440p-equivalent scores is only possible if the bboxes are right. 4K is now a tested entry
in `PROFILES`.

**The 1440p distance figure (98.4%) is not a miss rate.** Eleven of its thirteen nulls are
the train parked with the shared cell showing `1cm`: the metre-reader correctly returns
`None` and the cm-reader returns 1. Only 2 frames (the swap instant) had neither.

**One pre-existing defect surfaced, unrelated to downscaling.** As the train crawls the last
metre the cell swaps m→cm while the badge is still MOVING, and on those 2–3 frames BOTH
readers fire on the same pixels (`dist=78` and `offset=78` together) — the colour masks stop
separating during the transition. The offset copy is correctly discarded (its gate needs
STOPPED); the metre copy passes through as a phantom distance that appears to go UP. Native
1440p reads it identically, so downscaling is not implicated. Harmless in practice — arrival
fired at 900 m, and the distance guard catches the worst frame — but it is a real artifact.

## The resampler shootout

Scored on read accuracy over the 1440p catalogue under increasing blur, then checked against
792 real frames. Totals out of 208:

| | score | verdict |
|---|---|---|
| cubic | 159 | worst — edge ringing creates halos the Otsu threshold misreads |
| area | 174 | correct at any ratio; its own low-pass costs a little under blur |
| bilinear | 178 | fine at 0.75, but samples a fixed 2×2 however far it shrinks |
| area + unsharp | **193** | best on synthetic … and **destroyed the decimal digit on 145/792 REAL frames** |

Two lessons worth keeping:

- **The failure mode is a thin stroke falling below the binarization threshold, not
  aliasing.** That is why the textbook-correct downsampler does not automatically win, and
  why the sharpening kernel loses outright.
- **Synthetic gaussian blur is a proxy and it pointed the wrong way.** Uniform low-pass is
  something re-sharpening recovers from; real capture degradation is not, and the unsharp
  overshoot disturbs the 3–4 pixel decimal dot. A broad parameter plateau made the win look
  robust — it was not. Cross-ref `principles.md § "Validate against the outcome, not a
  proxy"`.

Area ships because it is ratio-independent and, on real driven frames, indistinguishable
from bilinear: **0 differences across badge, speed, distance and limit over 792 frames.**

## UX direction

- A calibration step shows a **50%-opaque box** the user aligns to the real game HUD.
- **Lock the box to the HUD's fixed aspect ratio** (the HUD only scales), removing the scale-drift axis — the one that breaks the offset canary — and leaving only position + uniform size.
- **Live reads as the confirmation:** overlay the live speed / distance / badge readout (offset as canary) so the user aligns by eye and verifies by numbers, landing inside the ±2% window without needing precision. Reuses the existing status-band read rendering.
- Auto-propose a starting box (spectrum: a resolution-scaled default → a multi-scale template match on the badge pentagon to *find* the HUD).

## Open questions (unresolved — for resume)

- ~~Live 1440p confirmation~~ — **done**, see § "Live results".
- ~~4K measurement~~ — **done**, see § "Live results". 4K is now a tested PROFILES entry.
- ~~Resampler at the 0.5 ratio~~ — **settled**, see § "The resampler shootout". Area ships; halving the ratio cost nothing measurable.
- **Committed 4K test fixtures.** The live drive proved the geometry, but nothing under _tests/ locks it — only the resolution-independent shape invariant runs. One 4K HUD grab into _tests/fixtures/ocr/2160p/ with a manifest would make it a real regression gate the way 1440p and 1080p are.
- ~~**Non-16:9 is untested.**~~ — **half settled 2026-08-09, by exactly the screenshot this asked for.** A 1920×1200 desktop grab shows the game fits a 16:9 viewport and **letterboxes** it: 60 px of pure black top and bottom, inner region exactly 1920×1080, HUD at `(1650, 75)`. Of the three candidate hypotheses only that one reads — badge diff 3.6 against a rejection threshold of 50, where scale-by-width scored 53.7 and scale-by-height 76.9 — and a ±4 px origin sweep puts a sharp minimum at dead centre. So **taller than 16:9 is supported** and derived against the viewport (`_viewport_for`), with 16:9 falling out as the zero-bar case. **Wider than 16:9 (21:9) is still refused**: presumably pillarboxed by the same logic, but one measurement is not two claims. Still one screenshot away.
- Auto-propose level to build first: cheap default box vs. landmark-match auto-detection.
- Common resolutions: silently apply the preset (zero-config) vs. always show the calibration screen with the preset pre-filled for confirmation. (First-run lessons argue for confirm.)
- How the preset boxes are stored/keyed, and how a user-selected box is persisted per setup.
- ~~Whether `--legacy-ocr` is worth keeping~~ — **retired 2026-08-09.** Three live drives (1080p / 1440p / 4K) had confirmed the downscale path, and the lever had become a liability: it only ever worked at the two hand-calibrated resolutions, and its guard tested `verified` as a proxy for "has native templates here". Promoting 4K's geometry — live-confirmed, templates never extracted — separated those two questions and armed the flag at a resolution whose badge anchors no longer matched the cell shape, so it would have started cleanly and then classified nothing. Deleting the branch deleted the guard.

## Relationship to the logic-hardening method

"Logic hardening" = OCR-read robustness rules at the reader/driver layer, independent of resolution. Shipped so far (all T1/T3-tested):

- **Speed domain rectify** (`_rectify_speed`, `ocr.py`, 2026-07-19) — a read above the 140 km/h ceiling (drivable max 135 + slack) drops one trailing digit and re-checks, recovering the decimal-slip misread (`72.7 → "727" → 72`) instead of dropping the sample. Now a rarely-exercised backstop behind the decimal-stop fix below.
- **Stopping-offset speed gate** (`_accept_stopping_offset`, `driver.py`, 2026-07-19) — the ±cm offset is accepted only at `speed == 0` (later `badge == "STOPPED"`), rejecting scenery-green phantoms; rejections log an `offset_reject` event.
- **1-column-tolerant decimal-stop** (`segment_chars`, `ocr.py`, 2026-07-20) — the decimal search scans the raw column-runs, not the finalized digit bboxes, so a decimal dot that binarized to a single dark column (the 1080p / softened-capture failure — `critical_lessons.md §7`) is still found and the tenths no longer slips into the integer. The exact-resolution reason 1080p was fragile and 1440p was not (dot 2 vs 3–4 columns). T3 speed-cell fixtures incl. a rectify-proof `5.3→5` regression cell.
- **Badge-reject score gate** (`_apply_badge_reject_gate`, `driver.py`, 2026-07-21) — when `badge is None` (classifier reject = degraded frame), drop any `speed`/`distance`/`speed_limit` read below `BADGE_NONE_SCORE_GATE` (0.80); conditional on badge-reject, so it supplies the honest threshold a global score floor lacked. Data: badge=None reads sit at score ~0.60 vs ~0.90 when the badge reads. Emits a `score_gate` event.
- **Distance plausibility guard** (`guard_distance`, `driver.py`, 2026-07-21) — rejects a distance read that moves further than `MAX_DRIVABLE_SPEED_KMH · Δt` from the last valid one and holds-last-good; re-anchors only on a re-point (see `auto_input/README.md` § "Distance plausibility guard"). Wild jumps 24/10 → 1/1 on the reporter's 1080p logs.
- **Adaptive per-cell threshold** (`_cell_dark_threshold`, `ocr.py`, 2026-07-22) — Otsu over the text band, clamped, replacing the fixed `DARK_THRESHOLD`. The HUD is semi-transparent, so scenery brightness moves the levels under the text and one global split cannot hold. Per-digit modal-width purity 89.2% → 95.1%, clipped glyph forms to zero.
- **Degradation-tolerant glyph match** (`compare_tolerant`, `ocr.py`, 2026-07-22) — scores the template at its natural aspect windowed left/right (sub-pixel phase clips an edge column) plus dilate/erode variants (ink bleed closes a counter). Read accuracy under thinning 92.8% → 100%.
- **Decimal gap-guard** (`segment_chars`, `ocr.py`, 2026-07-22) — the matched pair to the 1-column tolerance above: a dot candidate is accepted only `DECIMAL_MIN_GAP` clear of the last digit-sized run, because a degraded digit sheds a 1-column stub dimensionally identical to a dot. Never widen the dot scan without this, never drop it while the tolerance stands.

**Why it matters to THIS design:** hardening each read widens the pipeline's misread tolerance, which directly softens the ±2% scale-alignment cliff the user-drawn-box approach introduces (the stopping-offset canary in Finding 3). More per-read robustness ⇒ more forgiving box alignment ⇒ less precision the calibration UX must force the user to hit. Fold further hardening rules here as they land (candidates under discussion: digit-read score-gating, at-station speed gate), then re-weigh how tight the box-alignment UX actually needs to be.

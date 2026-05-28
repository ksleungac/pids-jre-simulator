# WIP — Native 1080p OCR support

Feasibility scaffold for running OCR auto-input on a game window rendered at 1920×1080. Current production path is hard-pinned to 2560×1440 with a fail-loud resolution gate in `auto_input.driver._run`. This doc holds calibration insights from the 2026-05-13 probe + the pickup path to production.

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** probe findings, identified-but-deferred risks, what real 1080p production support would need.
>
> **Refuses:**
> - History notes ("we tried X but it didn't work, then tried Y") — keep only the conclusion that informs next-session work
> - Code-snippet illustrations longer than 5 lines — link to `file:line` instead
> - Facts already in [auto_input/README.md](auto_input/README.md) — cross-reference, don't restate
>
> **Voice:** caveman-full for findings (terse, fragments OK); normal voice for rationale where misreading would mislead.
>
> **Graduation:** dissolves into auto_input/README.md § "Resolution dependency" + § "Recalibration" when 1080p production path actually lands. Precedent: `WIP_transfer_display.md` → DISPLAY.md (2026-05-05).

## Premise

Game renders HUD at 100% scale at 1920×1080; 2560×1440 is proportional upscale (ratio 4:3 vertical, identical aspect). Theoretical implication: existing 1440p geometry × 0.75 = valid 1080p geometry. Templates need re-extraction at native scale; segmentation constants need proportional scaling.

## Probe results (2026-05-13)

**Scaffold:** `_dev_scripts/_probe_1080p.py` — downscales 1440p `_ocr_calibration/*.png` references to 1080p, re-extracts dark + red digit templates from downscaled cells, re-builds badge anchors, monkey-patches scaled segmentation constants, runs OCR end-to-end. 1440p production path untouched (constants restored via `try/finally`; templates/anchors don't share state with production caches).

**Score:** 2/6 references read fully-correct at 1080p (passing_jp, stopping_ja); 1440p baseline confirms 6/6.

**Patterns identified:**

- **Pipeline geometry is correct.** Scaled HUD_BBOX + cell bboxes land on the right pixels — confirmed by the 2 fully-passing refs.
- **Scaled segmentation thresholds work for typical digits.** Multi-digit reads (54, 927, 3834, 0) succeed when no `1` is present.
- **`1` digit is the dominant failure mode.** Stroke width at 0.75 scale drops to ~5 px — at the DIGIT_MIN_W floor. Two distinct failures:
  - Segmentation collapses `1` into a neighbor digit on tight kerning (`1071` segmented as 3 bboxes instead of 4).
  - Extracted `1` template (backfilled from binary-downscaled 1440p) loses discriminative pixels — matched glyphs score against narrow vertical shapes like fragments of `7`.
- **`9` red template at small scale gets confused with `8`.** Both digits have similar pixel-mass profiles at downscale; the curve discriminator collapses. Limit `90` reads as `80`.
- **Small distance values (single-digit `8m`) fall under segmentation thresholds.** `stopping_position` distance reads `None` at 1080p.
- **Downscale ≠ native render.** Bilinear-resampled 1440p screenshots are a pessimistic stand-in for real 1080p game capture. A real native 1080p render would have cleaner stroke anti-aliasing on the source side. Real probe success rate is likely higher than 2/6 once native references replace the downscaled ones.

## What real 1080p production support needs

Estimated multi-session calibration effort, not a quick toggle:

1. **Capture native 1080p references.** Run the game at 1920×1080 fullscreen; capture the same content states as the 1440p `_ocr_calibration/` set (running_en/ja/my_usage, stopping_en/ja, passing_en/ja, all `limit_*`, `stopping_position`). Save under a parallel directory — e.g. `_ocr_calibration_1080p/`.
2. **Extend `KNOWN_VALUES` / `KNOWN_LIMIT_VALUES`** in `_dev_scripts/extract_ocr_assets.py` to handle the 1080p source set; produce a `ocr_templates_1080p/` (or `ocr_templates/1080p/`) parallel tree.
3. **Resolution-aware bbox tables.** `hud_layout.py` already has the 1440p `HUD_BBOX` + derived `HUD_BBOX_IN_CAPTURE` + `CAPTURE_REGION_2560_1440`. Add `HUD_BBOX_1920_1080`, `HUD_BBOX_IN_CAPTURE_1080`, `CAPTURE_REGION_1920_1080` siblings.
4. **Resolution-aware constants.** Currently the segmentation thresholds in `auto_input/ocr.py` (DIGIT_MIN_H, DIGIT_MAX_W, decimal/sign band Y, gap thresholds) are flat module-level constants. Either parameterize each reader with a config dataclass, or maintain two constant sets keyed by resolution.
5. **Resolution-aware caches.** `_red_templates_cache` + `_dilated_dark_cache` in `auto_input/ocr.py` are flat module globals. They'd need to key by resolution OR live on a class with per-instance state. The probe monkey-patched these for one-shot test; production needs a clean abstraction.
6. **Runtime detection.** AutoDriver currently asserts `2560×1440` at startup. Replace with: probe desktop size via bootstrap full-frame grab → select 1440p or 1080p constant set → fall back to FATAL if neither. Capture-region must also switch (`CAPTURE_REGION_*` choice).
7. **`1`-segmentation tuning.** Lower COLUMN_TEXT_MIN at 1080p (currently flat at 2) and/or tighten the gap heuristic so `1`-adjacent kerning doesn't merge. May need per-resolution segment_chars parameters.
8. **`9` red template re-extraction OR fallback.** Either extract from a higher-fidelity source than the downscaled 1440p PNG, OR tune dilated-dark fallback to discriminate `9`/`8` at small scale.

## Pickup notes (for next-session claude)

When the user has captured native 1080p references and wants to wire production support:

- Read this doc + `_dev_scripts/_probe_1080p.py` first. The probe is the closest existing approximation of the 1080p pipeline; production design should converge with it, not diverge.
- Don't reuse the probe's monkey-patched approach in production. Module-level constant mutation is fine for a probe; production needs a real config abstraction (per item 4 above).
- Production design is structural — propose `/third-man` for layout ideas before writing code (per `principles.md § Self-propose /third-man at impasse OR before structural refactors`).
- The 1080p path will touch: `auto_input/driver.py`, `auto_input/hud_layout.py`, `auto_input/ocr.py`, `_dev_scripts/extract_ocr_assets.py`. Downstream syncs: auto_input/README.md § "Resolution dependency" + § "Recalibration"; build skill if any new top-level dir gets added; CLAUDE.md mental model line on resolution support.
- After production lands: dissolve this doc into auto_input/README.md and delete (per the conventions.md graduation rule).

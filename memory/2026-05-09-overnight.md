# 2026-05-09 overnight (2026-05-08 evening → 2026-05-09 early AM)

> Note: this date had a separate AM session-block (Yamanote STA refinement) by a
> different Claude session that's still dirty / uncommitted at the time this entry
> lands. Once that author commits, the two session-blocks may be consolidated into
> a single `2026-05-09.md` per the multi-session-blocks-per-file convention.

## Session: OCR auto-input hardening — black-screen guard, stopping-offset reader, speed-limit reader

Multi-thread OCR feature work continuing the auto-driver. Three independent OCR concerns shipped, plus a structural badge-bbox trim. Most substantive design + implementation landed during 2026-05-08 evening hours, with the limit_100 / limit_105 / 2-try-splitter polish + badge-bbox trim into the early hours of 2026-05-09. Bundled into one daily-log session-block because the feature surfaces share `auto_input.py` + `ocr.py` + `AUTO_INPUT.md`.

### Black-screen guard for badge classifier

User reported: train at platform, game black-screens for fast-forward, OCR badge spuriously reads PASSING (badge_diff 65–110 vs real reads <15). Without protection, the bad frame triggers `STOPPED→PASSING` transition, resets per-segment observed-flags, and corrupts subsequent state-machine reasoning.

Two complementary layers landed (codified in auto-memory `project_hardening_philosophy.md`):
- **Cross-attribute reject**: in `_Detector.update`, when `prev_badge==STOPPED AND new_badge ∈ {MOVING, PASSING} AND speed ∈ {0, None}`, force badge to None. Structural rule exploits "black-screens only happen at platforms, real departures monotonically increase speed from 0." User narrowed the scope: black-screen ONLY happens at platform, never mid-transit.
- **Confidence gate** at `classify_badge_state`: badge_diff > 50 returns `(None, diff)`. Real reads <15, garbage reads 60+ — clean separation gives the gate a wide margin. Catches session-start priming that the structural rule misses (when prev_badge=None, the structural rule doesn't fire).

Philosophy shift: original 2026-04-27 framing was "cross-attribute corroboration, NOT per-attribute confidence gates." User refined this: confidence gates are fine when the underlying classification has a naturally wide gap (badge has it; some attributes don't). Both layers collaborate; cross-attribute is primary, gates are secondary garbage-rejection.

### Stopping-offset (cm) reader

Game shows train's distance offset from platform stop mark in green text (`±Ncm`) when train arrives. Same cell as the m-distance — content-shared, color-discriminated. New reader uses green color mask (`(G-max(R,B)) > 30`), sign-via-shape detect (small horizontal bar in vertical center of text band → minus), `cm` suffix excluded by existing DIGIT_MIN_H shape filter (smaller than digits).

Initial design ran the cm reader gated on `badge==STOPPED`. Live testing showed the cm display is **transient** — appears for ~5 s after arrival, then the cell switches back to m-distance to the next station even though train still parked. User confirmed: "after a few seconds the display in the same place becomes to show the distance to the next station." Fix: drop badge-gating, run both readers unconditionally each cycle. Their masks are mutually exclusive (`gray<70` for dark m, `(G-max(R,B))>30` for green cm) so at most one returns non-None per frame.

Originally framed null cm at STOPPED as "out-of-bound" overrun. User clarified the semantic: red text never appears in practice because the game prevents stopping in red zones (overrun → game resets train to `0cm` → black-screens past to next station). So red-text reads are unreachable; null cm at STOPPED is just "display dismissed" and unrelated to overrun. Reframed in AUTO_INPUT.md.

### Speed-limit reader

This was the session's biggest iteration loop. New reader for the red speed-limit cell (最高速度 row) — separate cell at HUD-relative (120, 215, 230, 55), red digits, dark `km/h` suffix.

The bold red font is rendered with thicker strokes than the m-distance font from which the digit templates were originally extracted. Series of failure modes surfaced as the user provided more limit screenshots (75, 90, 65, 85, 80, 100, 105, 110, 120, 30, 35, 45, 55):

1. **Stroke-weight mismatch** (8 / 6 → 4 misreads): bold red `5` doesn't match thin dark `5` template. Tried template dilation (cross-kernel) — 2 px works for some cases, 3 px is the sweet spot calibrated against limits 65/75/90 (2× mismatches `6` as `4`; 4×+ over-blooms and mismatches `9` as `5`).
2. **Tight kerning glues digit pairs** (90, 80, 85): bold strokes fill the column gap so `col_has_text` never drops below threshold between adjacent digits. Segmenter sees one over-wide blob. Added column-density-valley splitter at deepest valley (column sum < 60% of run's max).
3. **Split contamination** (110): the column-density valley falls inside the right digit's curve, so the split bbox bleeds the `0`'s left curve into the `1`'s glyph. Added 2D boundary refinement: search left_end / right_start independently within ±3 px, take the (left_end, right_start) combo with highest min-score that's grammar-valid.
4. **Recursive 0+0 merge** (100): merged blob is `0+0` (two `0`s glued), and column-density argmin picks inside the first `0`'s hollow rather than the inter-digit boundary. Added recursive split (keep splitting until each sub-bbox fits DIGIT_MAX_W) — but this STILL over-segmented the `0`s into halves.

After the 100 failure, user proposed the right meta-fix: **2-try splitter** ("if you detects a failure, just switch the splitter and see what works? by confidence or something"). Implemented: argmin (precise default) → equal_width fallback (divide blob into N equal parts where N = round(width/18)). First-valid-wins semantics so the equal-width's confidently-wrong reads on cleanly-segmenting cases (e.g. limit_110) can't override argmin's correct read. Live drive validated 100/105/110 km/h all reading at 0.85+.

Also extracted dedicated red-text digit templates 0-9 from the limit screenshots into `ocr_templates/digits_red/` (via `extract_ocr_assets.py` with new `KNOWN_LIMIT_VALUES` dict). Two-tier matching: red templates first, fall back to dilated dark for any digit without a red template (currently full coverage). Best-of-both score wins per glyph. Live validation post-extraction: scores jumped from 0.6–0.7 (dilated-dark only) to 0.85–1.0 (red templates win).

Domain validation as a final safety net: `VALID_SPEED_LIMITS = {25, 30, 35, …, 130}` — reader returns None on out-of-grammar reads. Catches misread modes (single-digit `1` from corrupted 90, `144`/`170` from contamination, `45` from 8→4 mismatch). User confirmed observed-floor is 25 km/h, allowing the lower-bound tightening.

### Badge bbox trim

User: "perfection thing... can nuke >10 px on the left" + "top can also be nuked by 5px." Original BADGE_BBOX `(15, 117, 125, 45)` included scenery bleed-through outside the pentagon's bounds — translucent HUD over varying scene caused inflated within-state diffs from non-discriminating noise. Verified leftmost ~13 px were sat-zero scenery (vs sat>30 inside pentagon). Trimmed to `(29, 122, 111, 40)` — left 14 px + top 5 px scenery removed. Self-classification still passes diff=0; PASSING cross-color separation widened from ~45 to ~48-52. User confirmed live d<5 post-trim — actual margin improvement matches expectation.

### Workflow notes

User collected screenshots iteratively as failure modes surfaced. Each failure → user provides new screenshot → I diagnose → propose fix → validate. The 2-try splitter idea came from user, not me — they spotted that the appropriate response to a splitter failure is to try a different splitter, not to keep refining the same one. Worth remembering as a meta-pattern: when iterating on a single failing strategy isn't working, the user's instinct to step up to "switch strategies" is often correct earlier than I'd think to suggest it.

Limit_110's `0+0` middle bbox failure is documented but unfixed — the recursive split places the cut inside a `0`'s hollow, and equal-width fallback fixes it for limit_100 but not for the limit_110 contamination case (which has different geometry). Domain validation catches both — JSONL stays clean.

Stopping-position `0cm` ambiguity (legitimate perfect stop vs game-reset after overrun) is unresolved — both render identically as green `0cm`. Disambiguation requires context-window analysis (was there a black-screen near the MOVING→STOPPED transition? did speed jump from non-zero to 0 abruptly?). Tabled as TODO.md entry; lives in plot_drive.py's arrival-event analysis layer, not the OCR layer.

## Codifications this session

- `ocr.py` — new functions `read_stopping_offset`, `read_speed_limit`, `_try_read_speed_limit`, `segment_red_digits`, `_dilate_binary`, `_get_red_digit_templates`, `_get_dilated_dark_templates`. New constants `BADGE_DIFF_REJECT`, `RED_TEXT_DELTA`, `GREEN_TEXT_DELTA`, `SIGN_*`, `SPEED_LIMIT_TEMPLATE_DILATION`, `_TYPICAL_RED_DIGIT_WIDTH`, `VALID_SPEED_LIMITS`. Modified `classify_badge_state` (BADGE_DIFF_REJECT gate).
- `auto_input.py` — `_Detector.update` cross-attribute reject; capture loop wired with sl_cell + dual m/cm reading + speed_limit; status dict + JSONL `stopping_offset_cm` / `stopping_offset_score` / `speed_limit` / `speed_limit_score`; debug panel cm-vs-m priority + optional `lim:` row.
- `_dev_scripts/capture_game.py` — mirrors auto_input.py changes; `PaEventDetector.update` cross-attribute reject mirror; deleted broken `REFS_DIR = ... / "game_references"` (per 2026-04-27 retirement).
- `_dev_scripts/extract_ocr_assets.py` — `KNOWN_LIMIT_VALUES` dict + `extract_red_digits` function for red-text digit template extraction.
- `hud_layout.py` — added `SPEED_LIMIT_VALUE_BBOX = (120, 215, 230, 55)`; modified `BADGE_BBOX` to `(29, 122, 111, 40)`.
- `AUTO_INPUT.md` — new subsections "Cross-attribute reject (black-screen guard)", "Stopping offset (cm) — shared distance cell", "Speed limit (最高速度) — red digits"; HUD-layout table updates; Files-table updates; "Diff < 15 = high confidence" paragraph extended with BADGE_DIFF_REJECT note.
- `TODO.md` — entries updated on cross-attribute hardening (line 19, philosophy refinement noted), stopping-position data (line 26, reader/wiring shipped), speed-limit data (line 28, reader/wiring shipped + hardened); new entry on 0cm-disambiguation problem; new "Deferred review findings" entries from review+fix cycle (KNOWN_LIMIT_VALUES filename inconsistency, JSONL cross-reject visibility).
- `~/.claude/projects/D--pids-jre-simulator/memory/project_hardening_philosophy.md` — full rewrite reflecting "cross-attribute primary, confidence gates secondary" philosophy refinement.
- `ocr_templates/badges/*.png` — re-extracted at new (29, 122, 111, 40) bbox (now 111×40, was 125×45).
- `ocr_templates/digits_red/*.png` — 10 new red-text digit templates (full 0–9 coverage).

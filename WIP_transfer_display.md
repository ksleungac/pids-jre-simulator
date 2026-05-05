# WIP — Transfer-info display (lower LCD)

**Status (2026-05-05):** Small-N structural rules + `rows` data override **landed**. Verification corpus: **22/22 in-spec ✓** for row-grouping. Within-row distribution observations remain (separate class — `(N, M, K)` row counts match IRL but inter-element spacing within rows isn't always pixel-perfect).

**Row-grouping rules (settled):**
- N=2 → `(2,)` when `Σ widths ≤ W − 2·margin_x` else `(1,1)`. Calibrated 7/7 corpus.
- N=3 → `(2,1)` always. Calibrated 5/5 corpus.
- N≥4 (or any N with shinkansen prefix) → existing greedy walk + cascade dry-run. Calibrated against Tokyo / Yokohama / 新宿 / 渋谷 / 上野 / 品川 / Shinagawa.
- Optional `rows` field on `transfers_by_view[view]` → explicit IRL ground-truth override; bypasses all algorithm row-grouping. Currently unused — algorithm covers all 22 in-spec corpus stations.

**Out of scope:** 武蔵小杉 JN (E233-8000, not E235-0/1000). Per-N scaling ladder + thresholds calibrated against E235 IRL refs only; out-of-spec lines get best-effort fidelity floors per [CLAUDE.md § Per-model IRL line scope](CLAUDE.md). MKG-on-JN render uses MKG's E235-ordered transfers list (tokyu before sotetsu) — IRL E233-8000 has the opposite order; per-view ordering deferred.

**Pipeline (current):** Step 1 (per-N scaling) → Step 2 (row-grouping: rows override → shinkansen prefix → small-N structural → greedy walk + cascade dry-run) → Step 3 (blueprint widening, unchanged) → Step 4 (real-render Rules 1-4 cascade + track-back, unchanged). See sections below for each.

**Next session resume points:**
- Promote `render_transfer` to production under `displays/train_models/e235_1000/`.
- Within-row distribution polish (separate from row-grouping — see follow-up #0).
- Recalibrate Step-1 N=5 tier against more IRL refs (currently extrapolated from N=7/N=9 anchors).

---

## Algorithm

### Step 1 — per-N scaling

4-tier ladder in `preview_transfers.py:render_transfer` lines ~166-186:

| Tier | N | JA / EN | × banner JA |
|---|---|---|---|
| Sparse | ≤4 | 32 / 17 | 2.0× |
| N=5 | 5 | 29 / 15 | 1.8× |
| Mid | 6-9 | 26 / 14 | 1.6× |
| Dense | ≥10 OR ≥2 shinkansen | 22 / 11 | 1.375× |

EN derived: `round(JA × 12/23)`. `name_line_gap = -4 − (EN − 12)`. "Both shinkansen" overrides N (only fires on Tokyo JO today). IRL anchor points: Tokyo JO (N=9, both shink) = 1.32×; Ueno JY_inner (N=7) = 1.5×. N=5 tier (1.8×) extrapolated — needs more IRL refs.

### Step 2 — row-grouping

**Thresholds:**

- `margin_x = 1.6 × badge_h` (fixed per N-tier from Step 1).
- `inter_element_margin = 0.7 × margin_x` — greedy-walk comfort target for N≥4 (and row 1+ greedy capacity gate).
- `min_inter_gap = 0.5 × margin_x` — cascade Rule 2/3 floor (distribute_middles rejects gaps below this).

**Decision order in `dry_run_cascade()`:**

1. **`rows` override** — if `transfers_by_view[view].rows` is set and sums to N_total, use it directly as the row partition. Skip everything below. Cascade test fills provisional anchors per row; real-render Rules 1-4 + track-back still run within each forced row.

2. **Shinkansen prefix** — if any leading entries are shinkansen (category-sort guarantees they lead), they take row 0. Remaining entries cascade onto row 1+.

3. **Small-N structural rules:**
   - **N=2** → `(2,)` if `Σ widths ≤ W − 2·margin_x`, else `(1,1)`.
   - **N=3** → `(2,1)` always (first 2 entries → row 0, 3rd → row 1).

4. **Greedy walk + cascade dry-run** (N=1 and N≥4 fallback). L→R greedy walk fills row 0 at `inter_element_margin` spacing within canvas; remaining entries cascade onto row 1+ via Rule 1 → Rule 2 → Rule 3, with greedy capacity check as a fallback gate (entry joins current row if fits at `inter_element_margin` from rightmost-placed AND within canvas right, else opens new row). Rule 4 / track-back NEVER invoked during dry-run — those are real-render-only.

**Why the small-N rules exist.** Greedy walk's single threshold (`inter_element_margin`) couldn't simultaneously gate tight-pack capacity (秋葉原 / 成田 want IRL gaps below floor) AND force stylistic splits (新橋 fits comfortably but IRL splits anyway). Corpus-driven observation: 5/5 N=3 IRL = `(2,1)` and 7/7 N=2 IRL = `(2,)` when sum fits else `(1,1)`. The structural rules encode that pattern directly; greedy walk is reserved for N≥4 where row-0 packing is genuinely capacity-driven.

**Why the `rows` override exists.** Last-resort fall-back when neither structural rules nor cascade match IRL — a per-station data hint. Currently unused (algorithm covers all 22 in-spec corpus stations). The slot exists so that future stylistic-outlier discoveries can be encoded as data without re-tuning rules.

### Step 3 / Step 4 (unchanged)

3. **Blueprint margin widening.** Compute `effective_margin_x = max(margin_x, h_narrowest)` where `h_narrowest = min over rows of (W − Σ_row) / (n_row + 1)`. Inert when `h_narrowest ≤ margin_x`.

4. **Column-anchored positioning (real render).**
   - **Row 0 placement** under widened margin:
     - Multi-row layout (other rows below): head at `effective_margin_x`; tail right-edge at `W − effective_margin_x`; middles distribute evenly between head's right edge and tail's anchor x.
     - Single-row layout (row 0 is the only row): equal-spacing + `side_pad = (W − Σ)/14` bias when `(W − Σ)/(n+1) ≥ effective_margin_x`; else fall through to multi-row edge-pin path.
   - **Row 1+ via Rule 1/2/3 cascade + Rule 4 fallback** (with track-back). Track-back is safe here because row groups are finalized — no retroactive membership change.

### Code map

- `preview_transfers.py:render_transfer(surf, transfers, lines, debug=, rows_override=)` — params block at top defines `margin_x`, `inter_element_margin`, `min_inter_gap`.
- `dry_run_cascade()` — driver: rows-override → shinkansen prefix → small-N structural → greedy walk + cascade. Outputs `rows`.
- `cascade_test(widths, upper_anchors)` — pure-test variant of Rules 1/2/3 placement, no Rule 4. Used by dry-run + rows-override.
- `compute_row0_provisional(row_widths)` — edge-pin row 0 positions for dry-run upper-anchor purposes.
- Real-render path (Rules 1-4 + blueprint widening + track-back) consumes `rows` from dry-run; semantics unchanged from pre-GOLDEN-rule. See § "Done > Column-anchored positioning" below for full Rules 1-4 spec.

---

## Verification corpus (IRL grouping decisions)

Pre-implementation reference set for validating the GOLDEN-rule pipeline. `N` computed from `data/stations.json` (own-line filter + `transfers_by_view` drops). IRL groupings sourced from station LCD reference photos. Algorithm-output column captures GOLDEN-rule behavior post-implementation.

**Scope:** corpus is **E235-0/1000 in-spec only** (JY, JO). Per-N scaling ladder + algorithm thresholds are calibrated against IRL refs from those lines. Out-of-spec entries (e.g. 武蔵小杉 JN runs E233-8000) are kept below as best-effort comparison points but **don't drive tuning** — by [CLAUDE.md § Per-model IRL line scope](CLAUDE.md), out-of-spec routes get best-effort fidelity floors (no crashes / sane layout), not IRL match.

| # | Station | Line | View | N | IRL | Current algo | Path | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 浜松町 | JY | JY_inner | 2 | (1,1) | (1,1) ✓ | N=2 structural | drops keihin_tohoku → Monorail (422) + Ōedo (230); sum 652 > canvas 618 → fall-back |
| 2 | 渋谷 | JY | JY_inner | 8 | (3,3,2) | (3,3,2) ✓ | greedy + cascade | within-row spacing observations remain |
| 3 | 恵比寿 | JY | JY_inner | 2 | (2,) | (2,) ✓ | N=2 structural | drops saikyo_kawagoe |
| 4 | 目黒 | JY | JY_inner | 3 | (2,1) | (2,1) ✓ | N=3 structural | (was passing by greedy-coincidence pre-rule) |
| 5 | 五反田 | JY | JY_inner | 2 | (2,) | (2,) ✓ | N=2 structural | flat, no view drops |
| 6 | 大崎 | JY | JY_inner | 3 | (2,1) | (2,1) ✓ | N=3 structural | drops JA on JY_inner |
| 7 | 品川 | JY | JY_inner | 6 | (1,2,3) | (1,2,3) ✓ | shinkansen + cascade | edits keihin_tohoku→.oimachi_kamata |
| 8 | 原宿 | JY | JY_inner | 2 | (2,) | (2,) ✓ | N=2 structural | flat |
| 9 | 有楽町 | JY | JY_inner | 2 | (2,) | (2,) ✓ | N=2 structural | drops keihin_tohoku |
| 10 | 新橋 | JY | JY_inner | 3 | (2,1) | (2,1) ✓ | N=3 structural | drops {keihin_tohoku, tokaido, ueno_tokyo} |
| 11 | 新宿 | JY | JY_inner | 9 | (3,3,3) | (3,3,3) ✓ | greedy + cascade | within-row spacing observations remain |
| 12 | 日暮里 | JY | JY_inner | 3 | (2,1) | (2,1) ✓ | N=3 structural | |
| 13 | 上野 | JY | JY_inner | 7 | (1,3,3) | (1,3,3) ✓ | shinkansen + cascade | within-row anchoring observations remain |
| 14 | 秋葉原 | JY | JY_inner | 3 | (2,1) | (2,1) ✓ | N=3 structural | drops keihin_tohoku |
| 15 | 神田 | JY | JY_inner | 2 | (2,) | (2,) ✓ | N=2 structural | drops keihin_tohoku |
| 16 | 東京 | JY | JY_inner | 7 | (2,4,1) | (2,4,1) ✓ | shinkansen + cascade | drops {keihin_tohoku, chuo_rapid, ueno_tokyo} |
| 17 | 東京 | JO | JO_east | 9 | (2,4,3) | (2,4,3) ✓ | shinkansen + cascade | multi-shinkansen row 0 |
| 18 | 横浜 | JO | JO_east | 11 | (4,4,3) | (4,4,3) ✓ | greedy + cascade | |
| 19 | 武蔵小杉 | JN | JN_north | 5 | (3,2) | (2,2,1) | (out-of-spec) | E233-8000 line, not E235; best-effort fidelity per CLAUDE.md |
| 20 | 武蔵小杉 | JO | JO_north | 4 | (3,1) | (3,1) ✓ | greedy + cascade | JO_north drops shonan_shinjuku |
| 21 | 千葉 | JO | JO_east | 5 | (3,2) | (3,2) ✓ | greedy + cascade | JO_east drops sobu_local |
| 22 | 大船 | JO | JO_north | 3 | (2,1) | (2,1) ✓ | N=3 structural | JO_north drops ueno_tokyo + shonan_shinjuku |
| 23 | 成田 | JO | JO_east | 2 | (2,) | (2,) ✓ | N=2 structural | sum 612 ≤ canvas 618 → packed |

**Row-grouping: 22/22 in-spec ✓.** Within-row distribution observations (新宿, 上野, 渋谷 noted) are a separate class — row counts match IRL; inter-element spacing within rows isn't always pixel-perfect. Tracked under follow-up #0.

---

## Resume point

`preview_transfers.py` (project root) is the working prototype. Run with:

```bash
uv run preview_transfers.py --station 東京 --filter-line JO --view JO_east --out _visual_iter/<label>.png --debug
```

`--debug` prints widths + dry-run cascade trace + per-row rule taken. Tuneable params at top of `render_transfer()`.

References: `lcd_references/transfer_tokyo.png`, `lcd_references/yokohama.png`.

---

## Discussion conventions — IRL-valid render configurations

Every render referenced as an IRL comparison point MUST correspond to a real-world train's perspective. That means a specific active line (`--filter-line`) AND that line's own direction view when applicable (`--view X_<direction>`). This mirrors the app's runtime config when a train on line X reaches a station.

**Rules:**

- **Default render (no `--filter-line`) is invalid as IRL reference.** A station's transfers list without filtering is the simulator's superset; IRL only ever displays from a specific train's perspective.
- **Default `--view` to the line's own direction view.** For direction-loop / branched lines (JY, JK, JA, JO, …), use `X_<direction>` (e.g. JY_inner). For lines without direction views, omit. This is the app's intended runtime config — claude defaults to it without asking. User can override `--view` to experiment (e.g. dropping something for testing).
- **When unsure which line is active**, ASK. Don't ask about views once the line is chosen — view follows from line.

**Why this matters:** outside-IRL configurations produce layouts that exist only in the simulator. Comparing them against IRL splits gives meaningless conclusions. The inverse error — asking which view when the line's own view is the obvious default — wastes the user's attention. Both 2026-05-04 incidents (no filter at all; then auto-asking which view to assume on 目黒) trace to claude not using the app's natural default config.

---

## Done

- **Schema** — `data/lines.json` (rail-line catalog) + `transfers` field on `data/stations.json`. Icon-based badges with optional `code` for filter; `_universal` fallback when `badges` absent. Documented in `DATA_FORMAT.md`.

- **Icon assets** — 36 PNGs at 128×128 in `data/line_icons/`. Sources (33 SVGs + 2 Shinkansen variants + universal-fallback PNG) in `lcd_references/line_badges/` and `lcd_references/Shinkansen_jr*.svg`. Regen one-liner: `magick -background none <src.svg> -resize 128x128 <dst.png>`.

- **Renderer prototype** (`preview_transfers.py`) — banner with bilingual "のりかえ案内 Transfer" (dim PASSED_COLOR bg, JA centered, EN bottom-anchored 7 px), mixed-script Latin/CJK font dispatch, per-line/per-variant JA compression via `name_ja_compress` field on `lines.json` (default 1.0; set per IRL measurement), compact `・` (U+30FB → U+00B7 + 1 px side-pad), badge sized to 1.1 × JA height, margins per user spec (left = 1.6 × badge_h).

- **Column-anchored positioning — Rule 1 / Rule 2 / Rule 3 cascade + Rule 4 fallback.** Real-render's per-entry x placement (Step 4 of the pipeline). Rules 1-3 also called from dry-run via `cascade_test`; Rule 4 + track-back is real-render only.

  ### Definitions

  - `N` = number of entries in current row.
  - `M` = number of upper anchors = `len(upper_anchors)` of the row directly above.
  - `upper_anchors[k]` = the chosen x position of the k-th entry in the row directly above.
  - `widths[k]` = full entry width = badge group + gap + max(JA text width, EN text width).
  - `predecessor of entry k` = entry k-1 (the one to its immediate left in the same row).
  - `predecessor's right edge` = `predecessor.x + predecessor.width`.
  - `effective_margin_x` = `margin_x` initially; can grow if Rule 4 fires.
  - `right_edge_canvas` = `W − effective_margin_x`.

  ### Row 0 (no upper row to anchor against)

  Row 0 branches by total row count.

  **Multi-row layout (`len(rows) > 1`):** edge-pin so subsequent rows can column-align.
  - Head (entry 0) at `margin_x`.
  - Tail (entry N-1) right-edge at `right_edge_canvas` → `tail_x = right_edge_canvas - widths[N-1]`.
  - Middles (entries 1..N-2) distribute evenly between head's right edge and tail's anchor x.

  **Single-row layout (`len(rows) == 1`):** use equal-spacing when `h_equal ≥ margin_x`, with sides padded slightly larger than inters per IRL preference. Falls through to multi-row's head/tail/distribute when `h_equal < margin_x`.
  - Compute `h_equal = (W − Σ) / (n+1)` and `side_pad = max(0, (W − Σ) / single_row_side_pad_divisor)` where `single_row_side_pad_divisor = 14` (tuneable).
  - For n≥2: `side_gap = h_equal + side_pad`; `inter_gap = h_equal − 2·side_pad/(n−1)`. Total still sums to W.
  - For n=1: just center via `cursor = h_equal` (no inter to absorb side_pad).
  - Sparse rows (small Σ) → larger side_pad → more visually-anchored sides. Crowded rows (Σ → W) → side_pad → 0 → true equal-spacing.

  ### Row R > 0 — Rule 1 (column alignment, fires only when N ≤ M)

  Per-entry left-to-right sweep. Entry k attempts to anchor at `upper_anchors[k]`.

  **Asymmetric predecessor-intrusion check** is the ONLY validator:
  - Entry 0 has no predecessor → always succeeds at `upper_anchors[0]`.
  - Entry k (k ≥ 1) succeeds iff `predecessor's right edge ≤ upper_anchors[k]`. Otherwise it is **blocked**.

  **Asymmetry rationale.** Entry k overflowing rightward into entry k+1's territory is NOT entry k's concern — it doesn't block entry k. But entry k+1's anchor at `upper_anchors[k]` being intruded by entry k's text IS entry k+1's concern — it blocks entry k+1. The check is one-directional: the entry being placed cares only about whether its own predecessor intrudes into its own anchor.

  **Failure is per-entry, not row-wide.** Successful entries stay anchored. The first failure stops the sweep at index `first_failed`. Entries `[first_failed..N-1]` then proceed to Rule 2 as a segment.

  **Edge case:** Entry 0 cannot fail by construction — the predecessor check is skipped at k=0 (no predecessor exists).

  ### Row R > 0 — Rule 2 (head + tail + distribute, leftmost-fit tail anchor)

  Triggered by either:

  - **Failed-segment case** (Rule 1 attempted, partially succeeded, failed at index `f = first_failed > 0`):
    - `head_right = chosen_xs[f-1] + widths[f-1]` — i.e. the last Rule-1-successful entry's right edge. NOT reset to margin_x.
    - Tail = entry N-1 (original last entry of the row).
    - Middles = entries `[f..N-2]` (failed-segment entries strictly between head and tail).
  - **N > M case** (Rule 1 didn't fire at all):
    - Head = entry 0, anchored at `upper_anchors[0]`. `head_right = upper_anchors[0] + widths[0]`.
    - Tail = entry N-1.
    - Middles = entries `[1..N-2]`.

  **Tail anchor selection — leftmost-fit.** Iterate `upper_anchors` in order (k = 0, 1, 2, …). For each candidate `a = upper_anchors[k]`, `a` is "fitting" iff ALL of:

  - **Middle-distribution check.** If middles exist: `distribute_middles(head_right, a, middle_widths)` returns valid positions (positive gap with all middle widths fitting). If no middles: `head_right ≤ a` (the tail's predecessor — which IS the head when there are no middles — does not intrude into `a`).
  - **Canvas check.** `a + tail.width ≤ right_edge_canvas`.

  Note: the tail's own predecessor-intrusion check is enforced implicitly by the middle-distribution branch — `distribute_middles` only returns valid positions when the rightmost middle's right edge ≤ `a`. The no-middles branch checks the same condition directly (head IS the tail's predecessor).

  The **first (leftmost) `a` that fits** becomes the tail's anchor. Middles then distribute evenly between `head_right` and the tail's anchor; tail anchored at the chosen `a`.

  If no `upper_anchors[k]` fits → fall to Rule 3.

  ### Row R > 0 — Rule 3 (canvas-right fallback, Case A only)

  Rule 2's failure mode determines whether Rule 3 fires at all:

  - **Case A** — at least one upper anchor passed the predecessor-intrusion check, but the tail overflowed canvas at it (`cand + tail_w > right_edge_canvas`). The constraint was canvas, not anchors. → Rule 3 fires.
  - **Case B** — every upper anchor failed the predecessor-intrusion check. There is no usable column-anchor at all; the row genuinely needs more space than upper provides. → Rule 3 is **skipped**; fall directly to Rule 4 (equal-spacing + track-back).

  Detection: track `predecessor_clean_seen` inside Rule 2's iteration — set to True whenever a cand passed the predecessor check (regardless of canvas result).

  **Rule 3 (Case A path):**
  - `right_edge_target = W − effective_margin_x` (canvas right margin, NOT max-prior-row-rightmost).
  - `tail_x = right_edge_target − tail.width`. The tail's RIGHT edge aligns to canvas right.
  - Middles (if any) distribute evenly between `head_right` and `tail_x`.
  - If `tail_x < head_right` OR middles still don't fit → fall to Rule 4.

  **Why Case A uses canvas-right and Case B doesn't:** in Case A the column-anchor system already proved insufficient (anchors exist but tail overflows); using canvas-right is the most permissive remaining placement and visually matches IRL. In Case B (e.g. Shinagawa row 1's 東海道線), canvas-right would float the tail too far right (next to the canvas edge with a huge gap from its predecessor); equal-spacing via Rule 4 produces a balanced layout instead.

  ### Row R > 0 — Rule 4 (equal-spacing fallback + track-back)

  Triggered when Rule 3 dies — typically because rows above are narrower than this row (e.g. Shinagawa: row 0 has 1 shinkansen at width 201, row 1 has Keihin-Tōhoku-qualified at width 302 which overflows row 0's right edge).

  - Compute `h = (W − Σ widths) / (n+1)`. If `h < margin_x`: fall to last-ditch (degenerate; row would have sub-floor sides). Otherwise:
  - Place this row with **equal-spacing**: head at `h`, inter-gap `h`, tail right-edge at `W − h`. Sides == inters == `h`.
  - **Track back**: shift all rows already placed (0..R−1) by `delta = h − effective_margin_x` so their head_x aligns with the new effective margin. Anchors, right-edges, and the positions list are all updated in lockstep. Delta is often non-zero even when blueprint widening fired upstream — blueprint sets margin to `h_narrowest` (the row with the smallest h), but a different row may turn out to need an even wider gap; track-back covers the residual.
  - Set `effective_margin_x = h` for subsequent rows' cascade computations.

  ### Worked examples

  **Tokyo row 0** (shinkansen, N=2, no upper). `widths=[405, 201]`. Row 0: head at 40, tail at 690-201=489. No middles. → `[40, 489]`.

  **Tokyo row 1** (jr_east 4, N=4, M=2). `widths=[115, 143, 97, 120]`. N > M → Rule 2 (N > M case). Head at upper[0]=40, head_right=40+115=155. Middles=[143, 97]. Tail width=120. Iterate `upper_anchors=[40, 489]`:
  - upper[0]=40: distribute_middles(155, 40, [143,97]) → negative span. FAIL.
  - upper[1]=489: distribute_middles(155, 489, [143,97]) → span 334, sum 240, gap 31. Canvas 489+120=609 ≤ 690. ✓.
  - mid_xs=[186, 360], tail at 489 → `[40, 186, 360, 489]`.

  **Tokyo row 2** (3 entries, N=3, M=4). `widths=[176, 97, 126]`. N ≤ M → Rule 1. k=0: anchor at upper[0]=40. right edge=216. k=1 (keiyo): try upper[1]=186, predecessor's right edge 216 > 186 → BLOCKED. first_failed=1. Rule 2 failed-segment with head_right=216, middles=[97], tail width=126. Iterate `upper_anchors=[40, 186, 361, 489]`:
  - upper[0]=40: distribute_middles(216, 40, [97]) → negative. FAIL.
  - upper[1]=186: distribute_middles(216, 186, [97]) → negative. FAIL.
  - upper[2]=361: distribute_middles(216, 361, [97]) → span 145, gap (145-97)/2=24. Canvas 361+126=487 ≤ 690. ✓.
  - mid_xs=[240], tail at 361 → `[40, 240, 361]`.

  **Yokohama row 0** (N=4, no upper). `widths=[143, 120, 149, 157]`. Head at 40, tail at 690-157=533. Middles distribute → `[40, 210, 357, 533]`.

  **Yokohama row 1** (N=4, M=4). `widths=[98, 117, 97, 143]`. N=M → Rule 1. k=0..3 each succeed (every predecessor's right edge ≤ next upper anchor). → `[40, 210, 357, 533]`.

  **Yokohama JO row 2** (Case A worked example, N=3, M=4 with blue line at .scale(0.75) → w=267). `widths=[99, 189, 267]`. N ≤ M → Rule 1. k=0 (相鉄): anchor at 40, right=139. k=1 (みなとみらい): upper[1]=210, 139 ≤ 210 → anchor at 210, right=399. k=2 (BL): upper[2]=357, 399 > 357 → BLOCKED. first_failed=2. Rule 2 failed-segment with head_right=399, no middles, tail width=267. Iterate `upper_anchors=[40, 210, 357, 533]`:
  - upper[0..2]: head_right 399 > each → predecessor intrusion (3 fails).
  - upper[3]=533: 399 ≤ 533 → **predecessor clean** (`predecessor_clean_seen = True`); BUT canvas 533+267=800 > 690 → canvas overflow.
  - Rule 2 finds no fitting anchor. `predecessor_clean_seen = True` → **Case A**. Try Rule 3 canvas-right: `right_edge_target = W − effective_margin_x = 730 − 40 = 690`. `tail_x = 690 − 267 = 423`. head_right 399 ≤ 423 ✓. → `[40, 210, 423]`.

  **Shinagawa JY_inner blueprint widening.** Split (1,2,3) → row sums [220, 452, 406], h_per_row=[255, 92.67, 81]. `h_narrowest = min(h) = 81` (row 2). `effective_margin_x = max(40, 81) = 81`. Blueprint widens; row 0 will seed at 81 instead of 40.

  **Shinagawa JY_inner row 0** (shinkansen alone, N=1). Multi-row n=1 path → `chosen_xs=[81]` (uses effective_margin_x).

  **Shinagawa JY_inner row 1** (Case B worked example, N=2, M=1). `widths=[302, 120]` (post JY filter + JY_inner edit). N > M → Rule 2. Head at upper[0]=81, head_right=383. No middles. Iterate `upper_anchors=[81]`: head_right 383 > 81 → predecessor intrusion. Only one cand, both fail predecessor. `predecessor_clean_seen = False` → **Case B**. Skip Rule 3; fall directly to Rule 4. `h=(730−452)/3=92.67`. Place row 1 at `[93, 518]`. Track back row 0: `delta = 93 − 81 = 12`, shinkansen shifts from `[81]` to `[93]`. `effective_margin_x=93`.

  **Shinagawa JY_inner row 2** (N=3, M=2 with effective_margin_x=93). `widths=[189, 120, 97]`, upper_anchors=[93, 518], `right_edge_canvas=637`. N > M → Rule 2. Head at upper[0]=93, head_right=282. Middles=[120], tail w=97. Iterate:
  - upper[0]=93: distribute_middles(282, 93, [120]) → negative. FAIL.
  - upper[1]=518: distribute_middles(282, 518, [120]) → span 236, gap (236−120)/2=58. Canvas 518+97=615 ≤ 637. ✓.
  - mid_xs=[340], tail at 518 → `[93, 340, 518]`.

  **Yokohama JO blueprint widening (counter-example).** Split (4,4,3) → row sums [569, 455, 571], h_per_row=[32.2, 55, 39.75]. `h_narrowest = 32.2` (row 0 itself). `max(40, 32.2) = 40` → blueprint inert; standard cascade runs at default margin. Row 0 seeds at `[40, 210, 357, 533]`, row 1 column-aligns via Rule 1 (N=M=4, all anchors fit), row 2 falls to Rule 3 right-edge → `[40, 210, 407]`.

- **Through-service variant pattern — nested variants under parent slug** (replaced earlier sibling-slug approach 2026-05-02): lines whose badge set OR display name varies by zone live as variants under one parent slug in `lines.json`. UT (`ueno_tokyo`) carries variants `tokaido` (JT-only south) + `tohoku` (JU-only north); Yokosuka/Sōbu Rapid through-service merges into `yokosuka_sobu` parent with variants `yokosuka` + `sobu`; Keihin-Tōhoku at 品川 uses variant `oimachi_kamata` for the direction-qualified line name. Variants override any subset of base fields (badges, name_ja, name_en); missing fields inherit. Reference syntax in stations.json is dot-notation: `slug.variant`. Schema + resolver in `DATA_FORMAT.md` § lines.json. Why nested-not-sibling: keeps slug catalog tied to physical line identity; variants are display refinements that conceptually belong to their line.

- **Filter-line semantics**: drops any slug whose effective `badges[].code` matches active. For variants, effective badges are merged-from-base + variant-overrides. So `ueno_tokyo.tokaido` (JT-only variant) gets dropped on JT-active but not on JU-active; `ueno_tokyo` base (JT+JU) gets dropped on either.

- **`transfers_by_view` slot — `drop` + `edit` ops.** Per-station map keyed by `<line>_<direction>` (e.g. `JY_inner`, `JT_south`). `drop` removes entries by base slug; `edit` swaps a base slug to a variant ref. Drop applied first, then edit. `add` reserved for future. Populated only when IRL evidence (LCD photo or audio) shows divergence from flat-list default. Schema in `DATA_FORMAT.md` § stations.json `transfers_by_view`. Today populated: 東京 / 新橋 JY_inner drop parallel-runners; 品川 JY_inner edits `keihin_tohoku → keihin_tohoku.oimachi_kamata`.

- **Tokyo + Yokohama + Shinagawa + Shimbashi + Hamamatsuchō + Ōsaki populated** under new schema:
  - 東京: 11 entries; through-service migrated (`yokosuka` → `yokosuka_sobu.yokosuka`, `sobu_rapid` → `yokosuka_sobu.sobu`).
  - 横浜: 12 entries (was 11; gap-fix added `yokosuka_sobu.yokosuka`); UT migrated (`ueno_tokyo_jt` → `ueno_tokyo.tokaido`).
  - 品川: 7 entries with plain `keihin_tohoku` (variant override fires only on JY_inner via `transfers_by_view.JY_inner.edit`), `ueno_tokyo.tokaido`, `yokosuka_sobu.yokosuka`. JY-filter render produces 6 visible.
  - 新橋: 7 entries (JY/JK/JT/UT.tokaido + Ginza/Asakusa/Yurikamome). New line slugs added: `ginza`, `asakusa`, `yurikamome`. JY_inner drops JK/JT/UT (parallel-runners southbound).
  - 浜松町: 4 entries (JY/JK/Tokyo Monorail/Toei Asakusa via 大門 walk). New line slugs: `tokyo_monorail`, `oedo`. JY_inner drops JK. Wide entries on row 1 ordered Monorail-first (left) so Ōedo (narrow) lands on the right anchor without canvas overflow.
  - 大崎: 4 entries (JA/JS/sotetsu_through/Rinkai). New line slugs: `saikyo`, `sotetsu_through` (universal icon, "相鉄線直通 / Through service to Sōtetsu Line"), `rinkai` (icon at `data/line_icons/rinkai.png` extracted from `lcd_references/Rinkai_Line_symbol.svg`). JY_inner drops JA. IRL uses (2,1) split but current algorithm picks (1,2) — see follow-up #0.

---

## Open follow-ups (priority order)

0. **Within-row distribution polish.** Algorithm produces correct row counts (22/22 in-spec) but inter-element spacing within rows isn't always pixel-perfect IRL. Known observations: 新宿 JY_inner spacing slightly off; 赤羽 JK/JA inner spacing too wide; 千葉 JO_east row 0 cramped; 上野 JY_inner anchoring rules problem. Distinct from row-grouping class — needs visual sweep against IRL refs at fix-time, likely refinements in Step 4 cascade Rules 2/3 distribute_middles or single-row equal-spacing biasing.

1. **Promote to production.** Move `render_transfer` from `preview_transfers.py` into `displays/train_models/e235_1000/` — likely a new sibling module beside `lower_lcd.py` (the transfer view *replaces* the route bar conditionally, not an addition to it). Wire into `LowerDisplay`'s view-cycler so it triggers when `at_station=True` AND the current station has `transfers` data. Surfaces and font-loading patterns to mirror existing `lower_lcd.py` style.

2. **Stations transfer-data population — extend beyond current scope.** Currently populated (~48 stations as of 2026-05-03): all JY-loop stations with non-trivial transfers (27), 横浜, plus the rest of code_3 catalog (大宮 / 川崎 / 武蔵小杉 / 浦和 / 赤羽 / 大船) and the JO Sōbu Rapid route (新日本橋 → 成田 minus JO-only stops). Deferred: 戸塚 (Yokosuka audio data not done), 高輪ゲートウェイ (per user). Skipped: JY-only stations (目白, 新大久保, 鶯谷-JK-only edge cases), JO-only stations on Sōbu Rapid east (東千葉 / 四街道 / 物井 / 酒々井 / 空港第2ビル / 成田空港). Through-service variants added on demand using the nested-variant-under-parent pattern (see DATA_FORMAT.md § Variant resolution). Icon choice per line: mirror IRL PIDS — JR East lines + lines that IRL render with a proper badge get their own icon; lines that IRL render with universal symbol stay on `_universal`.

   **Coverage suppression is data-driven, not runtime-derived.** When IRL evidence shows a transfer dropped on a specific view (e.g. Yamanote dropped at 田端 on a Keihin-Tōhoku southbound train, because both lines parallel-run the same corridor downstream), populate `transfers_by_view["<line>_<direction>"] = {"drop": [...]}` on that station. The resolver already applies these drops after the active-line filter. Earlier plan to derive drops at runtime from a station→line-codes index over `audio/**/route.json` is dropped — per-station data sidesteps the through-service-terminus edge cases (UT Line on a JT train at 横浜) the runtime rule struggled with, and matches item 5's philosophy of accumulating raw observations first.

   **Curation priority — IRL-reference availability.** Only E233+ (except E233-3000) and E235 series carry the LCD transfer-info display; without that, no IRL reference photo can be taken from a moving train. **Has LCD ref:** Yamanote (E235-0), Yokosuka/Sōbu Rapid (E235-1000), Keihin-Tōhoku/Negishi (E233-1000), Chūō Rapid (E233-0), Jōban Local (E233-2000), Keiyō (E233-5000), Yokohama Line (E233-6000), Saikyō/Kawagoe (E233-7000), Nambu (E233-8000/8500). **No LCD ref:** Tōkaidō, Utsunomiya/Takasaki/Ueno-Tōkyō through-running (E233-3000 / E231-1000), older stock. When expanding past the code_3 catalog, prioritize stations served by ≥1 LCD-equipped line — they're verifiable. Stations served only by no-LCD lines are best-effort / defer.

3. **(deferred) Banner color tone.** Currently `PASSED_COLOR` (230, 230, 230). User: "current good."

3a. **(deferred) Per-train-model badge rendering policy.** Different E233 sub-series render certain transfer entries as color-squares instead of icons (e.g. JK E233 uses color-square for Kawagoe; JA E233 uses color-square for all JR except Shinkansen). Schema extension: add optional `color: [r, g, b]` per badge object in `lines.json` `badges` arrays — purely additive, today's renderer ignores it. Then **hardcoded per-train-model policy** (in `displays/train_models/<model>/__init__.py`, alongside dimensions/palette) drives icon-vs-color-square dispatch in the renderer. User-stated preference: don't over-engineer with a parameterized policy DSL — small hardcoded config block per model is fine. **Defer color data entry** until the policy is built — filling colors for ~40 lines now creates churn when the policy lands and each color is re-verified against IRL. User owns the policy config; this entry just tracks the schema/data side.

4. **(deferred) EN size constraint trade-off** for shinkansen row. Currently parked at EN 12 pt. Possible fixes parked.

5. **(future) Data-driven pattern analysis** once `transfers_by_view` populates across enough stations. The schema deliberately accumulates per-station per-view drops as raw observations rather than encoding suppression rules in code. Once N stations × M views are populated, pivot the `(station, view, dropped_slug)` tuples and look for clusters that suggest underlying IRL rules — upstream-coverage suppression, redundancy via active-line corridor, direction-aware suppression, etc. If a stable pattern emerges, codify it as a derivation rule with the per-station data preserved as ground-truth fallback for exceptions. Loop directions (`JY_inner` / `JY_outer`) are recorded explicitly even though the game runs one direction per route — they're the slicing dimension for this analysis later. Rough trigger threshold: ~10+ populated views with ~3+ drops each. Below that, n is too small to distinguish pattern from noise.

---

## Files touched (this work)

- `data/lines.json` (rail-line catalog, 36+ slugs)
- `data/stations.json` (~48 stations populated; many with `transfers_by_view`)
- `data/line_icons/*.png` (36 PNGs)
- `lcd_references/line_badges/*.svg`, `lcd_references/Shinkansen_jr*.svg` (icon sources)
- `lcd_references/transfer_*.png` (IRL references)
- `preview_transfers.py` (prototype renderer with GOLDEN-rule pipeline; will move to `displays/`)
- `displays/transfer_info.py` + `displays/train_models/e235_1000/transfer_info.py` (LCD hookup; see [DISPLAY.md § View cycler](DISPLAY.md))
- `DATA_FORMAT.md` (lines.json + stations.json `transfers` / `transfers_by_view` sections)

## Where the canonical layout knowledge lives

The single source of truth for IRL-derived layout decisions is the params block at the top of `preview_transfers.py:render_transfer`. Each value has a one-line comment explaining why it has that value (mostly "user spec from iteration on YYYY-MM-DD"). When promoting to production, **port the params block verbatim** — don't redo the math.

## What was NOT tested

- **Private-operator icons at runtime** — some still fall back to `_universal` placeholder.
- **Stations beyond the verification corpus** — corpus covers 21 in-spec stations; ~25+ other populated stations (大宮, 川崎, 浦和, 赤羽, JO Sōbu Rapid east stations) not yet sweeped against IRL groupings.
- **Last-ditch pack-from-margin** — Rule 4 catches the case Shinagawa would have fallen into; last-ditch never fires on real data now.

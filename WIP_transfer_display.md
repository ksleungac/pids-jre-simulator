# WIP — Transfer-info display (lower LCD)

**Status:** Algorithm locked 2026-05-03. Four layered components:
1. **Row-grouping** — capped lex-maximin over `h = (W − Σ widths)/(n+1)` (with `margin_x` floor, gap capped at `2·margin_x`) decides how many entries per row. Sort key tiebreaks by fewer-rows so few-small-entries collapse onto a single row instead of spreading vertically.
2. **Blueprint placement** — when the max-Σ row is NOT row 0 (i.e. some lower row needs more space than row 0 can seed), that row is placed first via equal-spacing as the cascade seed instead of waiting for reactive Rule 4 + track-back. When max-Σ IS row 0, behaviour is unchanged (top-down cascade with row 0 as seed).
3. **Column-anchored positioning** — Rule 1 / Rule 2 / Rule 3 cascade column-aligns non-seed rows against the adjacent already-placed row toward the seed. Row 0 (when it is the seed) has two sub-paths: single-row layout uses equal-spacing with `(W−Σ)/divisor` side-padding; multi-row layout edge-pins head/tail.
4. **Equal-spacing fallback (Rule 4)** — when cascade dies, place row equal-spaced. In standard mode (seed = row 0), tracks back earlier rows by delta. In blueprint mode (seed = max-Σ row > 0), track-back is skipped to preserve the seed.

Validated structurally against Tokyo, Yokohama, Shinagawa, Shimbashi, Hamamatsuchō, Ōsaki IRL references. Remaining work is data population + production wiring.

---

## Resume point

`preview_transfers.py` (project root) is the working prototype. Run with:

```bash
uv run preview_transfers.py --filter-line JO --out _visual_iter/v_neue_world.png
./compare_transfer.sh _visual_iter/v_neue_world.png "<label>"
```

Tuneable params live in a labeled block at the top of `render_transfer()`.

References: `lcd_references/transfer_tokyo.png`, `lcd_references/yokohama.png`.

---

## Done

- **Schema** — `data/lines.json` (rail-line catalog) + `transfers` field on `data/stations.json`. Icon-based badges with optional `code` for filter; `_universal` fallback when `badges` absent. Documented in `DATA_FORMAT.md`.

- **Icon assets** — 36 PNGs at 128×128 in `data/line_icons/`. Sources (33 SVGs + 2 Shinkansen variants + universal-fallback PNG) in `lcd_references/line_badges/` and `lcd_references/Shinkansen_jr*.svg`. Regen one-liner: `magick -background none <src.svg> -resize 128x128 <dst.png>`.

- **Renderer prototype** (`preview_transfers.py`) — banner with bilingual "のりかえ案内 Transfer" (dim PASSED_COLOR bg, JA centered, EN bottom-anchored 7 px), mixed-script Latin/CJK font dispatch, per-line/per-variant JA compression via `name_ja_compress` field on `lines.json` (default 1.0; set per IRL measurement), compact `・` (U+30FB → U+00B7 + 1 px side-pad), badge sized to 1.1 × JA height, margins per user spec (left = 1.6 × badge_h).

- **Row-grouping — capped lex-maximin.** Among splits respecting category-sort (shinkansen → jr_east → non_jr, no within-category reorder) and `max_rows = 3`, pick by 3-tuple sort key: `(capped_padded_gaps, -num_rows, uncapped_gaps)`. Larger tuple wins.
  - **Capped** = each row's gap clamped to `gap_cap = 2·margin_x`. Beyond that, more whitespace is wasted canvas, not better layout.
  - **Padded** to length `max_rows` with `gap_cap`. Lets fewer-row splits compete fairly with more-row splits (an "absent" row contributes a vacuous cap-equivalent gap).
  - **`-num_rows` tiebreak** prefers fewer rows when capped tuples tie. Without this, 3 small entries would lex-prefer (1,1,1) over single-row layout because uncapped gaps are larger when split.
  - **Uncapped** lex-maximin breaks final ties — picks the most-spread among row-count-equivalent splits.

  Per-row gap formula `h`:
  - `n=1`: `h = (W − Σ widths) / 2`.
  - `n≥2` equal-spacing case (when `(W − Σ)/(n+1) ≥ margin_x`): `h = (W − Σ)/(n+1)` (sides == inters).
  - `n≥2` stretch case (sides bottom out at `margin_x`): `h = (W − 2·margin_x − Σ)/(n − 1)`.

  No shinkansen fence, no 4-entries-per-row cap — both dropped as count-based heuristics that maximin produces naturally from widths.

  Validated splits: Tokyo (2,4,3); Yokohama (4,4,3); Shinagawa JY_inner (1,2,3); Shimbashi flat (2,2,3); Shimbashi JY_inner (3) — single row (was (1,1,1) under uncapped lex-maximin; cap+tiebreak collapses it).

- **Column-anchored positioning — Rule 1 / Rule 2 / Rule 3 cascade + Rule 4 fallback.** Each row's per-entry x positions are decided by this cascade. Rules 1–3 refactored 2026-05-02; Rule 4 added 2026-05-02; third-man verified.

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

  ### Row R > 0 — Rule 3 (right-edge fallback)

  Triggered when Rule 2's tail iteration finds no fitting upper anchor.

  - `right_edge_target = max(rightmost edge of every row above)`. (Take the maximum across all rows above this one.)
  - `tail_x = right_edge_target - tail.width`. The tail's RIGHT edge aligns to `right_edge_target`.
  - Middles (if any) distribute evenly between `head_right` (same `head_right` as Rule 2's segment) and `tail_x`.
  - `head_right` continues from Rule 2's segment context (last-Rule-1-successful right edge, or entry 0's right edge if N > M).
  - If `tail_x < head_right` (rows above are narrower than this row) OR middles still don't fit (negative span) → fall to Rule 4.

  ### Row R > 0 — Rule 4 (equal-spacing fallback + track-back)

  Triggered when Rule 3 dies — typically because rows above are narrower than this row (e.g. Shinagawa: row 0 has 1 shinkansen at width 201, row 1 has Keihin-Tōhoku-qualified at width 302 which overflows row 0's right edge).

  - Compute `h = (W − Σ widths) / (n+1)`. If `h < margin_x`: fall to last-ditch (degenerate; row would have sub-floor sides). Otherwise:
  - Place this row with **equal-spacing**: head at `h`, inter-gap `h`, tail right-edge at `W − h`. Sides == inters == `h`.
  - **Track back**: shift all rows already placed (0..R−1) by `delta = h − effective_margin_x` so their head_x aligns with the new effective margin. Anchors, right-edges, and the positions list are all updated in lockstep.
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

  **Yokohama row 2** (N=3, M=4). `widths=[99, 149, 315]`. N ≤ M → Rule 1. k=0 (相鉄): anchor at 40, right=139. k=1 (みなとみらい): upper[1]=210, 139 ≤ 210 → anchor at 210, right=359. k=2 (BL): upper[2]=357, 359 > 357 → BLOCKED. first_failed=2. Rule 2 failed-segment with head_right=359, no middles, tail width=315. Iterate `upper_anchors=[40, 210, 357, 533]`:
  - upper[0..2]: head_right 359 > each → all FAIL middle-distribution check (no-middles branch).
  - upper[3]=533: 359 ≤ 533 ✓ but canvas 533+315=848 > 690 → FAIL canvas check.
  - No upper anchor fits → Rule 3. `right_edge_target = max(row 0's rightmost = 690, row 1's rightmost = 676) = 690` (湘南新宿's right edge in row 0). The algorithm scans each row's last entry's right edge only (`row_rights_list[i][-1]`), not interior entries. tail_x = 690-315=375 ≥ head_right=359 → Rule 3 succeeds. No middles. → `[40, 210, 375]`.

  **Shinagawa JY_inner row 1** (N=2, M=1; row-grouping puts shinkansen alone on row 0). `widths=[302, 120]` (post JY filter + JY_inner edit). Row 0 has shinkansen w=201 at x=40, right edge=241. N > M → Rule 2. Head at upper[0]=40, head_right=40+302=342. No middles. Iterate `upper_anchors=[40]`: head_right 342 > 40 → FAIL. → Rule 3: `right_edge_target=241`, `tail_x=241−120=121 < head_right=342` → Rule 4. `h=(730−422)/3=103`. Place row 1 at `[103, 508]` (sides≈103, inter≈103). Track back row 0: shinkansen shifts from x=40 to x=103. `effective_margin_x=103`.

  **Shinagawa JY_inner row 2** (N=3, M=2 with effective_margin_x=103). `widths=[149, 120, 97]`, upper_anchors=[103, 508], `right_edge_canvas=627`. N > M → Rule 2. Head at upper[0]=103, head_right=252. Middles=[120], tail w=97. Iterate:
  - upper[0]=103: distribute_middles(252, 103, [120]) → negative. FAIL.
  - upper[1]=508: distribute_middles(252, 508, [120]) → span 256, gap (256−120)/2=68. Canvas 508+97=605 ≤ 627. ✓.
  - mid_xs=[320], tail at 508 → `[103, 320, 508]`.

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

0. **Two enhancement candidates queued for tomorrow's discussion:**
   - **Better row-grouping when biggest row sits below**: at 大崎 JY_inner (3 entries: JS/sotetsu_through/rinkai) IRL uses `(2,1)` split but algorithm picks `(1,2)` because uncapped lex-maximin tiebreaker prefers the first split's 124.7 over (2,1)'s 111.3. Candidate fix: category-respecting tiebreaker — `key = (capped_padded, -num_rows, -boundary_violations, uncapped)` where violations counts split points NOT at category transitions. Soft preference, not constraint (Yokohama/Tokyo splits already violate by necessity).
   - **Better Rule 1 for sparse-row-against-wider-blueprint space distribution**: Shimbashi flat under blueprint mode places rows 0/1 at `[100, 300]` (cramp left) because Rule 1 walks leftmost upper anchors. Candidate: when N<M, place head at `upper[0]`, tail at `upper[-1]`, middles distribute; skip interior anchors. Would spread rows 0/1 to `[100, 500]`.

1. **Promote to production.** Move `render_transfer` from `preview_transfers.py` into `displays/train_models/e235_1000/` — likely a new sibling module beside `lower_lcd.py` (the transfer view *replaces* the route bar conditionally, not an addition to it). Wire into `LowerDisplay`'s view-cycler so it triggers when `at_station=True` AND the current station has `transfers` data. Surfaces and font-loading patterns to mirror existing `lower_lcd.py` style.

2. **Other ~19 stations' transfer data.** Populate `transfers` arrays for the rest of `data/stations.json`'s `code_3` catalog (Tokyo + Yokohama + Shinagawa now done; ~19 remain). Through-service variants added on demand using the nested-variant-under-parent pattern (see DATA_FORMAT.md § Variant resolution). Icon choice per line: mirror IRL PIDS — JR East lines + lines that IRL render with a proper badge get their own icon; lines that IRL render with universal symbol stay on `_universal`.

   **Coverage suppression is data-driven, not runtime-derived.** When IRL evidence shows a transfer dropped on a specific view (e.g. Yamanote dropped at 田端 on a Keihin-Tōhoku southbound train, because both lines parallel-run the same corridor downstream), populate `transfers_by_view["<line>_<direction>"] = {"drop": [...]}` on that station. The resolver already applies these drops after the active-line filter. Earlier plan to derive drops at runtime from a station→line-codes index over `audio/**/route.json` is dropped — per-station data sidesteps the through-service-terminus edge cases (UT Line on a JT train at 横浜) the runtime rule struggled with, and matches item 5's philosophy of accumulating raw observations first.

3. **(deferred) Banner color tone.** Currently `PASSED_COLOR` (230, 230, 230). User: "current good."

4. **(deferred) EN size constraint trade-off** for shinkansen row. Currently parked at EN 12 pt. Possible fixes parked.

5. **(future) Data-driven pattern analysis** once `transfers_by_view` populates across enough stations. The schema deliberately accumulates per-station per-view drops as raw observations rather than encoding suppression rules in code. Once N stations × M views are populated, pivot the `(station, view, dropped_slug)` tuples and look for clusters that suggest underlying IRL rules — upstream-coverage suppression, redundancy via active-line corridor, direction-aware suppression, etc. If a stable pattern emerges, codify it as a derivation rule with the per-station data preserved as ground-truth fallback for exceptions. Loop directions (`JY_inner` / `JY_outer`) are recorded explicitly even though the game runs one direction per route — they're the slicing dimension for this analysis later. Rough trigger threshold: ~10+ populated views with ~3+ drops each. Below that, n is too small to distinguish pattern from noise.

---

## Files touched (this work)

- `data/lines.json` (rail-line catalog)
- `data/stations.json` (`東京` / `横浜` / `品川` populated; `品川` also has `transfers_by_view.JY_inner.edit`)
- `data/line_icons/*.png` (36 PNGs)
- `lcd_references/line_badges/*.svg`, `lcd_references/Shinkansen_jr*.svg` (icon sources)
- `lcd_references/transfer_tokyo.png` (IRL reference)
- `preview_transfers.py` (prototype renderer; will move to `displays/`)
- `DATA_FORMAT.md` (lines.json + stations.json `transfers` / `transfers_by_view` sections)

## Where the canonical layout knowledge lives

The single source of truth for IRL-derived layout decisions is the params block at the top of `preview_transfers.py:render_transfer`. Each value has a one-line comment explaining why it has that value (mostly "user spec from iteration on YYYY-MM-DD"). When promoting to production, **port the params block verbatim** — don't redo the math.

## What was NOT tested

- **Private-operator icons at runtime** (all 5 fall back to `_universal` placeholder).
- **Other ~19 stations' data** (only Tokyo + Yokohama + Shinagawa populated).
- **Through-service variants beyond `ueno_tokyo.tokaido` + `yokosuka_sobu.{yokosuka,sobu}` + `keihin_tohoku.oimachi_kamata`** (e.g. `ueno_tokyo.tohoku` for stations north of Tokyo — slug not yet defined; will be when a north-of-Tokyo station gets populated).
- **Last-ditch pack-from-margin** — Rule 4 catches the case Shinagawa would have fallen into; last-ditch never fires on real data now.

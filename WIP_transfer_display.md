# WIP — Transfer-info display (lower LCD)

**Status:** Algorithm locked 2026-05-02. Three layered components:
1. **Row-grouping** — lex-maximin over `h = (W − Σ widths)/(n+1)` (with `margin_x` floor) decides how many entries per row, respecting category-sort + `max_rows = 3`.
2. **Column-anchored positioning** — Rule 1 / Rule 2 / Rule 3 cascade column-aligns rows against upper-row anchors when possible.
3. **Equal-spacing fallback (Rule 4)** — when Rule 3's `right_edge_target` lands left of `head_right` (row above narrower than this row), place this row equal-spaced and track back rows above to align.

Validated structurally against Tokyo, Yokohama, Shinagawa IRL references. Remaining work is data population + private-operator icons + production wiring.

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

- **Renderer prototype** (`preview_transfers.py`) — banner with bilingual "のりかえ案内 Transfer" (dim PASSED_COLOR bg, JA centered, EN bottom-anchored 7 px), mixed-script Latin/CJK font dispatch, two-tier JA compression (0.75 for 7-char like 上野東京ライン, 0.90 for 8+ char, none for ≤6), compact `・` (U+30FB → U+00B7 + 1 px side-pad), badge sized to 1.1 × JA height, margins per user spec (left = 1.6 × badge_h).

- **Row-grouping — lex-maximin.** Among splits respecting category-sort (shinkansen → jr_east → non_jr, no within-category reorder) and `max_rows = 3`, pick the split that maximizes `min(per-row gap)`, with ties broken by lex-comparing the sorted-ascending gap vector. Per-row gap formula:
  - `n=1`: `h = (W − Σ widths) / 2`.
  - `n≥2` equal-spacing case (when `(W − Σ)/(n+1) ≥ margin_x`): `h = (W − Σ)/(n+1)` (sides == inters).
  - `n≥2` stretch case (sides bottom out at `margin_x`): `h = (W − 2·margin_x − Σ)/(n − 1)`.

  No shinkansen fence, no 4-entries-per-row cap — both dropped as count-based heuristics that maximin produces naturally from widths.

  Validated splits: Tokyo (2,4,3); Yokohama (4,4,3); Shinagawa JY_inner (1,2,3).

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

  - Head (entry 0) at `margin_x`.
  - Tail (entry N-1) right-edge at `right_edge_canvas` → `tail_x = right_edge_canvas - widths[N-1]`.
  - Middles (entries 1..N-2) distribute evenly between head's right edge and tail's anchor x.

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

- **`transfers_by_view` slot — `drop` + `edit` ops.** Per-station map keyed by `<line>_<direction>` (e.g. `JY_inner`, `JT_south`). `drop` removes entries by base slug; `edit` swaps a base slug to a variant ref. Drop applied first, then edit. `add` reserved for future. Populated only when IRL evidence (LCD photo or audio) shows divergence from flat-list default. Schema in `DATA_FORMAT.md` § stations.json `transfers_by_view`. Today populated: 品川 JY_inner edits `keihin_tohoku → keihin_tohoku.oimachi_kamata`.

- **Tokyo + Yokohama + Shinagawa populated** under new schema:
  - 東京: 11 entries; through-service migrated (`yokosuka` → `yokosuka_sobu.yokosuka`, `sobu_rapid` → `yokosuka_sobu.sobu`).
  - 横浜: 12 entries (was 11; gap-fix added `yokosuka_sobu.yokosuka`); UT migrated (`ueno_tokyo_jt` → `ueno_tokyo.tokaido`).
  - 品川: 7 entries with plain `keihin_tohoku` (variant override fires only on JY_inner via `transfers_by_view.JY_inner.edit`), `ueno_tokyo.tokaido`, `yokosuka_sobu.yokosuka`. JY-filter render produces 6 visible.

---

## Open follow-ups (priority order)

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

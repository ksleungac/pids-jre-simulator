# WIP — Transfer-info display (lower LCD)

**Status:** Algorithm refactored 2026-05-02 to per-entry Rule 1 + per-segment Rule 2 (leftmost-fit tail anchor) + Rule 3 right-edge fallback. Validated structurally against both Tokyo and Yokohama IRL references. **Algorithm shape is locked; remaining work is data population + private-operator icons + production wiring.**

---

## Resume point

`preview_transfers.py` (project root) is the working prototype. Run with:

```bash
uv run preview_transfers.py --filter-line JO --out _visual_iter/v_neue_world.png
./compare_transfer.sh _visual_iter/v_neue_world.png "<label>"
```

Tuneable params live in a labeled block at the top of `render_transfer()`.

Reference photo: `lcd_references/transfer_tokyo.png`. Yokohama reference (untested but algorithm-targeted): `lcd_references/yokohama.png`.

---

## Done

- **Schema** — `data/lines.json` (rail-line catalog) + `transfers` field on `data/stations.json`. Icon-based badges with optional `code` for filter; `_universal` fallback when `badges` absent. Documented in `DATA_FORMAT.md`.
- **Icon assets** — 36 PNGs at 128×128 in `data/line_icons/`. Sources (33 SVGs + 2 Shinkansen variants + universal-fallback PNG) in `lcd_references/line_badges/` and `lcd_references/Shinkansen_jr*.svg`. Regen one-liner: `magick -background none <src.svg> -resize 128x128 <dst.png>`.
- **Tokyo data** — `東京` populated with 11 transfers (`tohoku_shinkansen`, `tokaido_shinkansen`, `yamanote`, `keihin_tohoku`, `chuo_rapid`, `tokaido`, `ueno_tokyo`, `keiyo`, `yokosuka`, `sobu_rapid`, `marunouchi`).
- **Renderer prototype** (`preview_transfers.py`) — banner with bilingual "のりかえ案内 Transfer" (dim PASSED_COLOR bg, JA centered, EN bottom-anchored 7 px), 3-row layout with shinkansen row-fenced and 4-entries-per-row cap, mixed-script Latin/CJK font dispatch, two-tier JA compression (0.75 for 7-char like 上野東京ライン, 0.90 for 8+ char, none for ≤6), compact `・` (U+30FB → U+00B7 + 1 px side-pad), badge sized to 1.1 × JA height, margins per user spec (left = 1.6 × badge_h).
- **Column-anchored layout — Rule 1 / Rule 2 / Rule 3 cascade.** Each row's per-entry x positions are decided by this cascade. Refactored 2026-05-02 to match user spec; third-man verified.

  ### Definitions

  - `N` = number of entries in current row.
  - `M` = number of upper anchors = `len(upper_anchors)` of the row directly above.
  - `upper_anchors[k]` = the chosen x position of the k-th entry in the row directly above.
  - `widths[k]` = full entry width = badge group + gap + max(JA text width, EN text width).
  - `predecessor of entry k` = entry k-1 (the one to its immediate left in the same row).
  - `predecessor's right edge` = `predecessor.x + predecessor.width`.
  - `right_edge_canvas` = `canvas_width - margin_x` (the rightmost x any entry's right edge may reach).
  - `margin_x` = canvas left/right margin.

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
  - If middles still don't fit (negative span): last-ditch pack-from-margin with zero gap. Not expected on real data.

  ### Worked examples (post 2026-05-02 refactor)

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
  - No upper anchor fits → Rule 3. `right_edge_target = max(row 0's rightmost = 690, row 1's rightmost = 676) = 690` (湘南新宿's right edge in row 0). The algorithm scans each row's last entry's right edge only (`row_rights_list[i][-1]`), not interior entries. tail_x = 690-315=375. No middles. → `[40, 210, 375]`.

- **Through-service variant pattern — nested variants under parent slug** (replaced earlier sibling-slug approach 2026-05-02): lines whose badge set OR display name varies by zone live as variants under one parent slug in `lines.json`. UT (`ueno_tokyo`) carries variants `tokaido` (JT-only south) + `tohoku` (JU-only north); Yokosuka/Sōbu Rapid through-service merges into `yokosuka_sobu` parent with variants `yokosuka` + `sobu`; Keihin-Tōhoku at 品川 uses variant `oimachi_kamata` for the direction-qualified line name. Variants override any subset of base fields (badges, name_ja, name_en); missing fields inherit. Reference syntax in stations.json is dot-notation: `slug.variant`. Schema + resolver in `DATA_FORMAT.md` § lines.json. Why nested-not-sibling: keeps slug catalog tied to physical line identity; variants are display refinements that conceptually belong to their line.

- **Filter-line semantics**: drops any slug whose effective `badges[].code` matches active. For variants, effective badges are merged-from-base + variant-overrides. So `ueno_tokyo.tokaido` (JT-only variant) gets dropped on JT-active but not on JU-active; `ueno_tokyo` base (JT+JU) gets dropped on either.

- **`transfers_by_view` slot** — defined-but-unpopulated. Per-station drop-list keyed by `<line>_<direction>` (e.g. `JY_inner`, `JT_south`). Object form `{"drop": [...]}` reserved for future `add` / `edit` operations. Drop applied after active-line filter. Populated only when IRL evidence (LCD photo or audio) shows divergence from flat-list default. Today: empty everywhere.

- **Tokyo + Yokohama + Shinagawa populated** under new schema:
  - 東京: 11 entries; through-service migrated (`yokosuka` → `yokosuka_sobu.yokosuka`, `sobu_rapid` → `yokosuka_sobu.sobu`).
  - 横浜: 12 entries (was 11; gap-fix added `yokosuka_sobu.yokosuka`); UT migrated (`ueno_tokyo_jt` → `ueno_tokyo.tokaido`).
  - 品川: NEW — 8 entries with `keihin_tohoku.oimachi_kamata`, `ueno_tokyo.tokaido`, `yokosuka_sobu.yokosuka`. JY-filter render produces 6 visible; JO-filter regression check on Yokohama matches prior reference (11 visible, identical layout).

---

## Open follow-ups (priority order)

1. **Promote to production.** Move `render_transfer` from `preview_transfers.py` into `displays/train_models/e235_1000/` — likely a new sibling module beside `lower_lcd.py` (the transfer view *replaces* the route bar conditionally, not an addition to it). Wire into `LowerDisplay`'s view-cycler so it triggers when `at_station=True` AND the current station has `transfers` data. Surfaces and font-loading patterns to mirror existing `lower_lcd.py` style.

2. **Runtime coverage filter.** Replace the preview's `--filter-line JO` CLI hack with the rule we settled on: hide transfer T at station S on the active route if T's line stops at every station between S and the active route's next stop — including stations marked `stops_here: false` (skipped passes). **Caveat from today's discussion:** must NOT filter through-service slugs whose terminus pattern extends beyond the active line's terminus (UT Line on a JT train at Yokohama: audio happens to skip it, but the rule shouldn't be why). Implementation needs a station→line-codes index built at startup from all `audio/**/route.json` files (including `pre_stops`).

3. **Other ~19 stations' transfer data.** Populate `transfers` arrays for the rest of `data/stations.json`'s `code_3` catalog (Tokyo + Yokohama + Shinagawa now done; ~19 remain). Through-service variants added on demand using the nested-variant-under-parent pattern (see DATA_FORMAT.md § Variant resolution). Icon choice per line: mirror IRL PIDS — JR East lines + lines that IRL render with a proper badge get their own icon; lines that IRL render with universal symbol stay on `_universal`.

4. **(deferred) Banner color tone.** Currently `PASSED_COLOR` (230, 230, 230). User: "current good."

5. **(deferred) EN size constraint trade-off** for shinkansen row. Currently parked at EN 12 pt. Possible fixes parked.

6. **(future) Data-driven pattern analysis** once `transfers_by_view` populates across enough stations. The schema deliberately accumulates per-station per-view drops as raw observations rather than encoding suppression rules in code. Once N stations × M views are populated, pivot the `(station, view, dropped_slug)` tuples and look for clusters that suggest underlying IRL rules — upstream-coverage suppression, redundancy via active-line corridor, direction-aware suppression, etc. If a stable pattern emerges, codify it as a derivation rule with the per-station data preserved as ground-truth fallback for exceptions. Loop directions (`JY_inner` / `JY_outer`) are recorded explicitly even though the game runs one direction per route — they're the slicing dimension for this analysis later. Rough trigger threshold: ~10+ populated views with ~3+ drops each. Below that, n is too small to distinguish pattern from noise.

---

## Files touched (this work)

- `data/lines.json` (new — rail-line catalog, 11 entries for Tokyo's needs)
- `data/stations.json` (`東京` gained `transfers` array)
- `data/line_icons/*.png` (new — 36 PNGs)
- `lcd_references/line_badges/*.svg` (new — 33 source SVGs)
- `lcd_references/Shinkansen_jr*.svg` (new — 2 source SVGs)
- `lcd_references/transfer_tokyo.png` (the IRL reference)
- `preview_transfers.py` (new — prototype renderer, will move to `displays/`)
- `DATA_FORMAT.md` (lines.json + stations.json `transfers` sections added/updated)

## Where the canonical layout knowledge lives

The single source of truth for IRL-derived layout decisions is the params block at the top of `preview_transfers.py:render_transfer`. Each value has a one-line comment explaining why it has that value (mostly "user spec from iteration on YYYY-MM-DD"). When promoting to production, **port the params block verbatim** — don't redo the math.

## What was tested

- **Tokyo full render** (9 entries post-JO-filter, 3 rows: 2/4/3): row 0 head/tail/distribute, row 1 N>M Rule 2 (tail at upper[1]=489), row 2 Rule 1 partial (ueno_tokyo at 40) → Rule 2 leftmost-fit (tail at upper[2]=361). Matches reference photo.
- **Yokohama full render** (11 entries, 3 rows: 4-4-3): row 0 head/tail/distribute, row 1 Rule 1 N=M=4 full success, row 2 Rule 1 partial (相鉄 + みなとみらい) → Rule 2 fails (canvas overflow at upper[3]) → Rule 3 right-edge align tail. Matches reference photo.
- **Refactor regression check (2026-05-02)**: Tokyo unchanged outcome for rows 0+1; row 2 keiyo distributed at x=240 (was x=186 — predecessor intrusion now triggers Rule 2 segment). Yokohama row 2 BL moved 357→375 (Rule 3 fired post-fix).
- **Filter semantics**: any-overlap drop (`{active} ⊆ slug.codes`) — `--filter-line JO` at Tokyo drops yokosuka + sobu_rapid as before; would also drop ueno_tokyo on a JT/JU train.

## What was NOT tested

- **Private-operator icons at runtime** (all 5 fall back to `_universal` placeholder).
- **Other ~21 stations** (only Tokyo + Yokohama populated).
- **Through-service variants beyond `ueno_tokyo_jt`** (e.g. `ueno_tokyo_ju` for stations north of Tokyo — slug not yet defined; will be when a north-of-Tokyo station gets populated).
- Coverage filter logic (still preview `--filter-line` hack).
- Last-ditch pack-left fallback (never expected to fire on real data).

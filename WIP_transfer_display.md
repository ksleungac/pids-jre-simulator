# WIP — Transfer-info display (lower LCD)

**Status:** Algorithm refactored to explicit Rule 1/2/3 fallthrough and validated structurally against both Tokyo and Yokohama IRL references. Tokyo matches pixel-close; Yokohama matches row-by-row structurally but has spacing imprecision in row 3 still to tune. **Algorithm shape is locked; remaining work is data + spacing polish.**

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
- **Column-anchored layout — Rule 1/2/3 fallthrough** (refactored from earlier (K, H) double loop; H is gone, always 1 in rule 2):
  - **Row 0**: head at `margin_x`, tail's right edge at `canvas_right`, middles even-distribute.
  - **Rule 1** (Row R > 0, N ≤ M): try `positions = upper_anchors[0..N-1]`. All-or-nothing; any single overlap forfeits.
  - **Rule 2** (head + tail anchored, middles even-distribute): head at `upper[0]`, tail at `upper[K]` for K from `min(N-1, M-1)` up to `M-1`. Middles 1..N-2 always even-distribute — never greedy-anchored in this rule. First K that passes overlap check wins. Tail screen-overflow at K terminates K loop.
  - **Rule 3** (right-edge fallback): head at margin, tail right-edge-aligned to `max(rightmost-edge of upper rows)`. **N=3 single-middle case**: greedy-anchor — first upper anchor that fits between head.right and tail.left wins. N≥4 or greedy-fail: even-distribute.
  - **Last-ditch pack-left** (zero gap from margin) if even Rule 3 overlaps.
  - **Validation**: full-width inter-entry no-overlap (text from entry k can't reach entry k+1's badge) + tail no-screen-overflow.
  - Verified IRL behavior:
    - Tokyo row 1 (N=4, M=2) → Rule 2, K=1.
    - Tokyo row 2 (N=3, M=4) → Rule 2, K=2; marunouchi at upper[2] = JC's column.
    - Yokohama row 1 (N=4, M=2) → Rule 2, K=1.
    - Yokohama row 2 (N=4, M=4) → Rule 2.
    - Yokohama row 3 (N=3, M=4) → Rule 3 (BL too wide for any upper[K]); みなとみらい greedy-anchored at upper[1] = JH's column.

- **Through-service variant pattern — option (b) sibling slugs**: Lines whose badge set varies by station zone (e.g. Ueno-Tōkyō Line: JT+JU central / JT-only south / JU-only north) get sibling slugs in `lines.json`. Naming: `<base>_<badges-joined>` (e.g. `ueno_tokyo_jt`). JA/EN names duplicate intentionally — each slug self-contained. Considered option (a) per-entry override hook; rejected for less flexibility / more renderer-side machinery.

- **Filter-line semantics — match audio**: `--filter-line JT` drops any slug whose badges include JT (subset-of relation: `{active} ⊆ slug.codes`). Compound-badge through-services like `ueno_tokyo` (JT+JU) get dropped on a JT or JU train, matching audio (which skips UT entirely on JT/JU trains). Earlier "keep UT visible" rule reverted once we learned audio also skips it.

- **Yokohama data populated**: `data/lines.json` gained 9 slugs — `shonan_shinjuku` (JS), `negishi` (JK), `yokohama_line` (JH), `ueno_tokyo_jt` (JT-only variant), and 5 private operators with `_universal` icon placeholder (`keikyu`, `tokyu_toyoko`, `sotetsu`, `minatomirai`, `yokohama_subway_blue`). `data/stations.json` `横浜.transfers` populated with the 11-entry list.

---

## Open follow-ups (priority order)

1. **Yokohama row 3 spacing tweaks.** Algorithm structure is right (相鉄 / みなとみらい under JH / BL right-anchored), but visual placement of みなとみらい and BL has minor spacing mismatch vs `lcd_references/yokohama.png`. Probably tunable via existing params or minor Rule 3 refinement.

2. **Source 5 private-operator icons** (Keikyū, Tōkyū Tōyoko, Sōtetsu, Minatomirai, Yokohama Subway Blue Line). Currently rendering as `_universal` fallback. SVGs to be sourced into `lcd_references/line_badges/` then converted via the standard `magick -resize 128x128` one-liner.

3. **Promote to production.** Move `render_transfer` from `preview_transfers.py` into `displays/train_models/e235_1000/` — likely a new sibling module beside `lower_lcd.py` (the transfer view *replaces* the route bar conditionally, not an addition to it). Wire into `LowerDisplay`'s view-cycler so it triggers when `at_station=True` AND the current station has `transfers` data. Surfaces and font-loading patterns to mirror existing `lower_lcd.py` style.

4. **Runtime coverage filter.** Replace the preview's `--filter-line JO` CLI hack with the rule we settled on: hide transfer T at station S on the active route if T's line stops at every station between S and the active route's next stop — including stations marked `stops_here: false` (skipped passes). **Caveat from today's discussion:** must NOT filter through-service slugs whose terminus pattern extends beyond the active line's terminus (UT Line on a JT train at Yokohama: audio happens to skip it, but the rule shouldn't be why). Implementation needs a station→line-codes index built at startup from all `audio/**/route.json` files (including `pre_stops`).

5. **Other ~21 stations' transfer data.** Populate `transfers` arrays for the rest of `data/stations.json`'s `code_3` catalog. Most JR lines have icons ready; private operators may need icon sourcing per-station as encountered. Through-service variants (`<base>_<badges>`) added on demand using the option-(b) pattern.

6. **(deferred) Banner color tone.** Currently `PASSED_COLOR` (230, 230, 230). User: "current good."

7. **(deferred) EN size constraint trade-off** for shinkansen row. Currently parked at EN 12 pt. Possible fixes parked.

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

- **Tokyo full render** (9 entries post-JO-filter, 3 rows): all rows match reference photo (unchanged from prior validation).
- **Yokohama full render** (11 entries, 3 rows: 4-4-3): structural row-by-row match. Rule 1 doesn't apply on rows 1-2 (overlap). Rule 2 wins rows 1-2. Rule 3 fires for row 3 (BL too wide for any upper[K]); みなとみらい greedy-anchored at upper[1] = JH's column. Spacing imprecision in row 3 noted.
- **Refactor regression check**: Tokyo render unchanged after Rule 1/2/3 split; H>1 cases of the old (K, H) loop confirmed dead (never fired in production data).
- **Filter semantics**: any-overlap drop (`{active} ⊆ slug.codes`) — `--filter-line JO` at Tokyo drops yokosuka + sobu_rapid as before; would also drop ueno_tokyo on a JT/JU train.

## What was NOT tested

- **Yokohama row-3 pixel-precise spacing** (deferred — algorithm is structurally right).
- **Private-operator icons at runtime** (all 5 fall back to `_universal` placeholder).
- **Other ~21 stations** (only Tokyo + Yokohama populated).
- **Through-service variants beyond `ueno_tokyo_jt`** (e.g. `ueno_tokyo_ju` for stations north of Tokyo — slug not yet defined; will be when a north-of-Tokyo station gets populated).
- Coverage filter logic (still preview `--filter-line` hack).
- Last-ditch pack-left fallback (never expected to fire on real data).

# E235 Series — Display Doc

Per-series renderers for the E235 train family. Two sub-series ship today: **E235-1000** (Yokosuka Line, Sōbu Rapid + through-service) and **E235-0** (Yamanote Line). Cross-model infrastructure (DisplayMode, ModeCycler, Unified State Machine, Adding-New-Train-Model recipe, Lower-LCD interface contract) lives in [DISPLAY.md](DISPLAY.md). Train-family scope and per-model IRL line scope live in [CLAUDE.md](CLAUDE.md) "Mental Model" (preloaded — should already be in head).

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** schema reference, gotchas, invariants, per-sub-series renderer rules — the implementation specifics looked up when editing the relevant submodule.
>
> **Refuses:**
> - History notes / change logs (`### 2026-03-14`, "pre-X behavior", "Key Changes from legacy …") — `git log` has this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future sections ("When X is implemented, …") — defer until needed; `TODO.md` is the home for pending designs
> - Design-discussion rationale (multi-paragraph framings of *why* a model exists) — the rule lives here; the rationale lives in `memory/YYYY-MM-DD.md`
> - Facts already in [CLAUDE.md](CLAUDE.md) mental model / [DISPLAY.md](DISPLAY.md) cross-model infra / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](.claude/rules/principles.md).

---

## Sub-series catalog

| Sub-series | IRL line scope | Upper LCD | Lower LCD | Status |
|---|---|---|---|---|
| **E235-1000** | Yokosuka Line, Sōbu Rapid (incl. through-service to Sōtobō / Narita) | Shipped | Shipped (linear full-route + 8-station + transfer-info) | Stable |
| **E235-0** | Yamanote Line | Shipped — same as E235-1000 minus train-type cell | Circular full-route (Yamanote) / open-horseshoe full-route (other routes) + 5-station stopping view (owns the EIGHT slot, all routes) with inline transfer panel; horizontal transfer slot inherited from E235-1000 | Shipped |

Per [CLAUDE.md](CLAUDE.md) "Mental Model → Per-model IRL line scope": each sub-series is in-spec only for its IRL lines. Out-of-spec routes loaded into either sub-series get best-effort rendering (no crashes, no broken layouts, but no IRL-fidelity obligation).

---

## Upper LCD

### Destination Behavior

Convention (always-kanji / "Bound for" English / `&` compound separator) lives in [CLAUDE.md](CLAUDE.md) "Mental Model → IRL display conventions"; JSON encoding + sticky-override closure in [DATA_FORMAT.md § Stop-Level Destination Override](DATA_FORMAT.md). The renderer reads `stops[curr_stop]["dest"]` directly — the loader (`route_loader.finalize_route`) has already filled it on every stop at load time.

### English Station Name

- Font: `fonts/HelveticaNeue-Bold.otf` @ 75pt (the `.ttf` cut had macron artifacts at large sizes — gone).
- Position: `name_x = int(S_WIDTH * 0.40) + 10` (10 px right of the Japanese position to give breathing room from the JO/JY badge); `name_y = UPPER_HEIGHT - name_h` (2 px lower than Japanese to match reference).
- Each mode's `draw_station` owns a `DARK_BG` clear rect that covers its glyph box plus ~10 px below for descender overflow. **Extend the rect downward only** — extending it upward into the prefix/clock band erases the clock.
- JR PIDS uses uniform horizontal smoothscale (current `collapse=True` path) for long names — they do NOT swap to a separate condensed font cut. Don't introduce one.

Both sub-series share the same English-station-name treatment.

### Station Code Badge

`_draw_station_code_badge()` reads `sta_code` (per-stop, from `route.json`) → renders the framed JY/03 square. Body is a thin wrapper that calls `displays.utils.draw_station_code_badge` with upper-LCD-specific params (badge_x=222, badge_w=68, badge_h=68, ring 7+7, sizes 18/22pt, etc.) and the optional `code_3` band. **`draw_station_code_badge` is the single badge renderer** — reused by the 8-station view's per-cell mini badges (smaller box, no `code_3` band, no black ring) and the **E235-0 5-station stopping view** (`JapaneseFiveStationDisplay._draw_jy_badge` — no-black-ring variation like the mini badges, scales the upper-LCD params by `b/54`, i.e. 68px minus the 2×7px black ring, so the color ring/interior/text fill the removed ring's space; no `code_3`). The **typeface is fixed** inside the helper (Frutiger / `NeueFrutigerWorld-Bold`) — callers pass point sizes, never a font face (see conventions.md). The Wikipedia `Template:JRSN` is a simplified CSS rendering (flat colored border, generic browser font) — *lower* fidelity than this helper, not a source to mimic; it was only useful for confirming proportions.

If the Japanese station name has a `code_3` entry in `data/stations.json`, the outer black rect extends UPWARD into a top band showing the 3-letter Roman code (white text, e.g. AKB/TYO).

All layout knobs live in the params block at the top of the method: `code_3_band_h`, `code_3_x_offset`, `code_3_y_offset`, and the point sizes `prefix_size` / `num_size` / `code_3_size` (the face is fixed in the helper, not loaded here).

**Draw order:** badge draws **last** in `UpperDisplay.draw()` (after prefix/station) so the extended top band is not clipped. The prefix `DARK_BG` rect and the badge share `x=222` — earlier ordering painted over the top of the extension.

JSON-side details (`stations.json` keying, the 22-station catalog rule) are in [DATA_FORMAT.md](DATA_FORMAT.md). Real-world rationale is in [CLAUDE.md](CLAUDE.md) "Mental Model → IRL display conventions".

### Element confinement (clip-enforced)

Every upper-LCD region has a declared rect — manifest at the top of `displays/train_models/{model}/upper_lcd.py` (`TRAIN_TYPE_RECT` for E235-1000 only, `DEST_RECT`, `PREFIX_RECT`, `STATION_RECT`, `CLOCK_RECT`, `BADGE_RECT`, `PA_HINT_RECT`). Each region's draw method wraps its body in `with clip(self.screen, RECT):` (helper at `displays/utils.py:clip`). Pixels drawn outside the rect are dropped at the pygame layer — bleed into a neighbour's territory is structurally impossible, no eyeball check needed.

**Tuning a region's bounds** — change the rect at module top. The clip wrap, the bg fill, and the debug-grid tint all read from the same constant.

**Debug-grid mode** — `uv run preview_display.py --debug-grid` swaps each region's bg to a unique tint via `_bg("<region>")` returning its `_DEBUG_COLORS` entry. Useful for verifying a NEW region's manifest entry covers the intended footprint; not load-bearing for catching bleed (clip handles that).

**Cross-mode parity** — all three mode renderers (Japanese / Furigana / English) share the same confinement per element. Internal content layout can differ; the boundary doesn't.

**Region map** — bounds + drawn-by + debug color for every region live as a comment block at the top of `displays/train_models/{model}/upper_lcd.py`, alongside `_DEBUG_COLORS`. Per-train-model — stays with the code, not in this doc.

**Pygame rendering gotchas:**

- **Transparent leading does NOT clobber.** `font.render(text, True, color)` (no bg arg) returns an SRCALPHA surface; transparent pixels don't overwrite the destination on blit. A glyph surface whose top lands above its region's clip rect is safe — clip drops the transparent strip, the underlying bg survives.
- **`font.get_height()` is ~`pt_size × 0.92`** for HelveticaNeue-Medium and ShinGoPr6N-Medium, NOT `pt_size × 1.2`. Probed examples: 24pt → 22, 78pt → 78.
- **Vertically centering text in a shape: center the INK, not the render surface.** `img.get_rect(center=...)` centers the full line-height surface; the font's ascent gap above a digit exceeds its descent gap below, so the visible glyph parks low (~1.5px at a 30pt digit, scaling with size). Place by baseline + glyph metrics instead: `top = cy + (maxy + miny) / 2 - font.get_ascent()` where `maxy/miny` come from `font.metrics(s)` (ink extent above/below baseline). Exact across sizes. First bit the 5-station countdown circles (`JapaneseFiveStationDisplay._draw_numbered_circle`, 2026-06-12).
- **When passing a bg arg to `font.render()` inside a region**, use `_bg("<same region>")` not `DARK_BG` directly. Both render the same in normal mode, but `DARK_BG` punches solid-DARK_BG holes through the region's tint when debug-grid is on, defeating the visualization.

### E235-0 vs E235-1000 — diff

**Removed in E235-0:** train-type cell (`TRAIN_TYPE_RECT = pygame.Rect(15, 8, 150, 31)`). Yamanote runs a single service type IRL, so the PIDS doesn't render one. Other elements do not reflow — the 150×31 top-left area becomes plain `DARK_BG`.

Concrete code-level deltas in [`displays/train_models/e235_0/upper_lcd.py`](displays/train_models/e235_0/upper_lcd.py) vs the E235-1000 sibling:

- `TRAIN_TYPE_RECT` constant absent
- `JapaneseDisplay.draw_train_type` + `EnglishDisplay.draw_train_type` methods absent
- `_DEBUG_COLORS` dict has no `train_type` entry
- `_bg(region)` simplified — no `default=` kwarg (all regions clear to `DARK_BG`)
- `UpperDisplay.__init__` does not load `self.train_type`, `self.type_color`, or `self.train_types`
- `_get_train_type_display` method absent
- `UpperDisplay.draw` does not call `display.draw_train_type` between `_bg("upper_bg")` fill and `draw_destination`
- `font_type_bold` font load absent from both `JapaneseDisplay.__init__` and `EnglishDisplay.__init__`

Everything else (DEST / PREFIX / STATION / CLOCK / BADGE / PA_HINT / clip semantics / debug-grid mechanism / mode cycling / `set_state` semantics) is byte-identical to E235-1000's upper, modulo the per-model docstring labels.

### Clock fine-tune (applied to BOTH sub-series)

Synced 2026-05-07 across both `e235_0/upper_lcd.py` and `e235_1000/upper_lcd.py`:

- `CLOCK_RECT` x: `S_WIDTH - 160` → `S_WIDTH - 170` (clock 10px to the left)
- `clock_x` constant in both `draw_clock` methods follows the same shift
- `font_clock`: HelveticaNeue-Roman 26pt → 27pt

### Sub-series selection (preview)

`uv run preview_display.py --model e235_0` selects the E235-0 model for the preview entry point. The main app (`uv run main.py`) stays on E235-1000 — its `app.py` import is unchanged. Selection is rebind-time: preview-side patches `app.UpperDisplay / LowerDisplay / S_WIDTH / S_HEIGHT` before instantiating `PASimulator`.

When a per-route or per-line model selection becomes desirable (e.g. `route.json` carrying a `train_model` field), that's a separate plumbing change — not blocked by anything here.

---

## Lower LCD

The lower LCD's manager (`LowerDisplay`) and per-frame state contract (state injection, station-skip semantics, `cursor_pos` derivation, terminus handling) are cross-model — see [DISPLAY.md § Lower LCD — Cross-Model Interface](DISPLAY.md). This section covers per-sub-series renderers.

### Mode renderer architecture (per sub-series)

Each sub-series's `lower_lcd.py` declares its own renderer set:

**E235-1000** (`displays/train_models/e235_1000/lower_lcd.py`):
- **JapaneseDisplay** — full route-map renderer (linear bar). Owns layout calc, marks, pointer, times.
- **JapaneseEightStationDisplay** — 8-station zoomed view (alternates with the full-route view via the slot cycler).
- **EnglishDisplay** — linear full-route display. Renders Romaji station names rotated 45 degrees counter-clockwise using HelveticaNeue-Bold at 17 pt. Employs 4x supersampling with bilinear downscaling (via `rotozoom`) to eliminate pixelation and applies a horizontal squeeze compression on long station names (exceeding 110px in 1x scale) before rotation. Draws "min" instead of "分" for minute markers.

**E235-0** (`displays/train_models/e235_0/lower_lcd.py`):
- **CircularFullRouteDisplay** — Yamanote-only circular racetrack. Drives the FULL slot when `route_data["route"] == "山手線"`.
- **OpenRouteFullRouteDisplay** — the FULL slot for every **non-Yamanote** route: `CircularFullRouteDisplay` opened into a horseshoe (one end cap dropped). Subclasses it, reusing its marker primitives and overriding only the JY-keyed pieces to be stop-index keyed + linear. Replaces the old E235-1000 linear fallback; both Japanese and English modes use the same instance (kanji-only, like the circular). See [§ E235-0 — open-horseshoe full-route](#e235-0--open-horseshoe-full-route-non-yamanote).
- **JapaneseFiveStationDisplay** — owns the EIGHT slot universally (E235-0 has no 8-station view). The 5-station stopping view: hand-drawn green band + five station markers + an inline transfer panel down the left column. Same instance is wired for ENGLISH (kanji-only regardless of mode).
- **Horizontal transfer slot** — inherited unchanged from E235-1000 (the `transfer_display` concrete; distinct from the 5-station view's inline panel).

**JapaneseDisplay (E235-1000) methods:**

- `_calculate_layout()` — derives `per_line`, `x` (centered to actual cell count), `y`, `h_line`, `top_pad`, `circular`, `continuity` from `len(stops)`.
- `_get_line(i)` — line 1 vs line 2 for global index `i`.
- `_get_stops_list_disp(curr_stop)` — returns `(global_index, stop)` pairs in the current visible window. For long routes (> `STOPS_QUANTITY`), slides the window forward as the train approaches the end.
- `_find_dest_index(f_stops)` — global index of the destination within the visible window.
- `draw_marks(f_stops, dest_idx, cursor_pos, curr_stop)` — circles / passing-station arrows; the inner red dot at `curr_stop` marks the actual PA target.
- `draw_ptr(f_stops, dest_idx, cursor_pos, curr_stop)` — red triangle pointer at `cursor_pos`.
- `draw_times(...)` — cumulative travel times with floor-division countdown.
- `show_stops(state, current_time)` — entry point. Reads from passed-in AppState; **does not mutate**.

Lower-LCD fonts load in `JapaneseDisplay.__init__` (locale-safe). Sizes live in `constants.py` (`FONT_STOPS_SIZE`, `FONT_TIME_SIZE`, `FONT_STOPS_MINUTE_SIZE`) — shared across mode renderers because both Japanese and the future English use the same metrics. Per-display-module sizes go inline; `constants.py` is for values genuinely shared across modules.

---

### Through-service restart transition (E235-1000)

Frame-swap mechanics (arm / hold / fire, windowing, continuity) are cross-model — [DISPLAY.md § Through-Service Display Frames](DISPLAY.md). E235-1000 specifics:

- **Restart screen** (`LowerDisplay._draw_restart_transition`): on swap fire, the WHOLE screen blanks to `WHITE_BG` with the JR East logo centered, held `_TRANSITION_DURATION` (5 s), then the new frame renders. Full-screen (upper + lower) — relies on the app drawing lower AFTER upper (`app.py` main loop + boot draw), so the lower's fill overdraws the upper. Cancels on any position change.
- **JR logo** = `displays.utils.draw_jr_logo` — the single path in `lcd_references/JR_logo_(east).svg` (committed source) flattened to a bezier filled polygon at import (`_JR_LOGO_PATH`). No rasterized asset ships; nothing read at runtime, no `app_paths` / `/build` bundling needed. Tuneable `logo_height` + `bg_color` in the method's `# fmt: off` block; logo color = `draw_jr_logo`'s `_JR_LOGO_GREEN` default; hold = `_TRANSITION_DURATION`.
- **Frame background** = `WHITE_BG` — an LCD-model constant, NOT route-derived. The frame `line` identity is metadata only; not surfaced on this model's chrome (same physical JO service across the swap, so accent stays the route color).

---

### E235-1000 — linear full-route

#### Layout / Centering

`_calculate_layout()` decides the route-map bar geometry from `len(stops)`:

| Stop count | per_line | Lines | Notes |
|---|---|---|---|
| ≤ 14 | `num_stops` | 1 | Mock (11). Single row, centered |
| 15 to 28 | `⌈n/2⌉` | 2 | Keiyo (17→9+8), Sōbu/Jōban (19→10+9), Tōkaidō (21→11+10), Saikyō/Takasaki (24→12+12), Nambu (26→13+13) |
| > 28 | 14 | 2 + window flip | Yamanote (30), Chūō (32), Keihin-Tōhoku (46) |

**E235-1000 IRL is 14-per-line.** Out-of-spec routes (e.g. Keiyō with 17 stops, not an E235-1000 line) wrap to 2 rows under the best-effort policy. See [CLAUDE.md](CLAUDE.md) "Mental Model → Per-model IRL line scope".

**Centering:** the row x-offset uses `min(per_line, num_stops)`, not `per_line` alone. Under the current rule `per_line ≤ num_stops` always, so the `min()` is defensive — kept for code safety.

#### Long-Route Window Refresh

Constants: `STOPS_PER_LINE = 14`, so `STOPS_QUANTITY = 28`. Refresh only triggers for routes with **more than 28 stops**.

Hits: Keihin-Tōhoku (46), Chuo (32), Yamanote (30). Below threshold: Nambu (26), Saikyō/Takasaki (24), etc.

Trigger: when `len(stops) - curr_stop < STOPS_QUANTITY`, `_get_stops_list_disp()` returns `self.stops[len(stops) - STOPS_QUANTITY:]` (last 28 stops).

Window carries tuples `(global_idx, stop)` — draw code doesn't need a separate `window_start` parameter to compare state, the global index travels with each cell.

**`continuity[2]` sync:** `_get_stops_list_disp` updates `continuity[2]` on **every call**, not just at the transition frame — otherwise jumping forward leaves the flag stale and slot-2 chevrons render past the destination. Set to `0` whenever the window has slid (visible window includes the route's last stop, no more route past it); restored to `1` whenever the window is back at its original position and route has > 28 stops. Circular routes (Yamanote) keep `[1, 1, 1]` since the route always continues past the visible window via the loop.

#### Continuity arrows (full-route view)

Continuity is a **property of certain cells** (last-on-row-1, first-on-row-2, last-visible-when-window-slid), not a separate element type. The cell loop in `JapaneseDisplay.show_stops` draws each variant inline alongside the cell so color inherits from the cell's active/passed state — no separate threshold logic, no floating shapes that drift away when the bar gray-outs.

##### Three slots

| slot | trigger | direction | shape |
|---|---|---|---|
| 0 | `local_i == per_line - 1 and continuity[0]` (last cell of row 1) | "to" — route continues to row 2 | bar → 分-area → triangle (apex right, off bar's tail) → chev1 → chev2 |
| 1 | `local_i == per_line and continuity[1]` (first cell of row 2) | "from" — route continues from row 1 | chev1 → chev2 → bar with WHITE_BG inverse-triangle notch carved INTO bar's left edge (apex right) |
| 2 | `gi == last_gi and continuity[2]` (last visible cell when window has slid) | "to" — route continues past visible window | same as slot 0 |

**Slot 0/2 vs slot 1 are visually asymmetric:** slot 0/2 has an *outward* triangle (bar tapers to a point); slot 1 has an *inward* notch (bar's left edge has a white V-shape carved in). Per IRL `lcd_references/chev.png` and `chev2.png` references.

##### Color inheritance

Color is **always `cell_color`** (`self.color` when active, `INACTIVE_COLOR` when passed). No threshold checks. The bar/triangle/chevrons all dim together as the train passes — natural mirror of the cell's own color transition.

##### Drawing order (slot 1 specifically)

Slot 1 renders in this order so the chevron tip pokes into the notch's V-shape:
1. Bar rect (extended `+cont_tri_w` to the left to compensate for notch carve, see below)
2. WHITE_BG inverse-triangle notch (overdraws bar)
3. Chevrons (overdraw the notch where chev2's tip extends into the V — the cell-color overdraw makes the tip "nestle" into the notch instead of disappearing into the white)

Slot 0/2 renders in straightforward order (bar → tail extension → triangle → chevrons), no overdraw conflicts.

##### Tip-portion uniformity (the critical geometry)

For triangle and chevron tips to look like the same pointiness — and for all three gaps (triangle→chev1, chev1→chev2 at top/bottom AND at the V-shape center) to render as a uniform 4-px white margin — set:

```
tri_w == cont_chev_w − cont_chev_stroke == 8
```

Currently `cont_tri_w = 8`, `cont_chev_w = 12`, `cont_chev_stroke = 4` → tip-portion = 8 = `tri_w`. Also matches the red cursor's tip-portion (`w − stroke = 18 − 10 = 8`) so apex slopes read consistently across the LCD. Negative `cont_chev_gap = -4` overlaps chevron BBs so the visible whitespace at the V-center is 4 px (not the bounding-box "gap" — the chevron's tip protrudes into its BB).

**If you change one of those three params, recompute the others** to keep the uniform-gap relationship. The tuneable-params block at the top of `show_stops` is the canonical place; downstream coordinates derive from it.

##### Slot 1 bar compensation

The notch carves `cont_tri_w` px into the bar's left edge. Without compensation, the visible bar would be `cont_tri_w` px narrower than other cells. The cell loop adds `cont_tri_w` to `bar_w` (and shifts `bar_x` left by the same) for slot-1 cells so the visible bar (after notch) matches the original `stops_w + left_extra + right_extra`.

#### Row-end / row-head bar extension

Independent of continuity: every row-tail cell (last on row 1 OR last visible cell on row 2) gets `+row_tail_extra = 10` px on the right; every row-head cell (first on row 1 OR first on row 2) gets `+row_head_extra = 10` px on the left. Visible as bigger 東京 / 千葉 / 東千葉 / 成田空港 cells in Sōbu's display.

Three rendering surfaces must stay in sync with these constants — change one, change all three:

| File | Symbol | Constant |
|---|---|---|
| `lower_lcd.py` `JapaneseDisplay.show_stops` cell loop | `row_head_extra`, `row_tail_extra` | source of truth |
| `lower_lcd.py` `JapaneseDisplay.draw_times` 分-marker block | `cell_extra = 10` | mirror of `row_tail_extra` |
| `lower_lcd.py` `JapaneseDisplay.draw_ptr` curr_stop==0 pentagon | `head_extra = 10` | mirror of `row_head_extra` |

The `draw_times` and `draw_ptr` sites have inline comments pointing at this rule — but the magic number is duplicated. Foot-gun if changed in one place only.

#### draw_times subtleties (recurring review false positives)

Two things in `JapaneseDisplay.draw_times` that look wrong but aren't:

- **`is_first_station` flips ONCE.** The flag identifies the *first time-bearing* stop after `cursor_pos` and gives it the countdown calculation; subsequent stops use cumulative addition. After cycle 2 it's nested inside `if cursor_pos <= gi <= dest_idx and "time" in stop:` — passing stations at the cursor get correctly skipped, and the first station with `time` correctly receives the "first" treatment regardless of whether it sits at `cursor_pos` exactly.
- **The 分-marker `OR` covers all cases.** `if local_i == self.per_line - 1 or gi == dest_idx:` correctly fires for both line-break columns AND mid-line dest. Don't change to AND or pile on extra clauses — that breaks one of the two cases. The 8-station view's analogous condition is `local_i == len(window) - 1 or gi == dest_idx` — same semantics for its respective iteration context.

---

### E235-0 — circular full-route (Yamanote)

Live in [`displays/train_models/e235_0/lower_lcd.py`](displays/train_models/e235_0/lower_lcd.py). Manager subclasses `e235_1000.LowerDisplay`: the FULL-slot renderer is `CircularFullRouteDisplay` when `route_data["route"] == "山手線"`, else `OpenRouteFullRouteDisplay` (the open horseshoe — see below). The EIGHT-slot renderer is `JapaneseFiveStationDisplay` universally (all routes). The horizontal TRANSFER slot inherits unchanged from E235-1000.

**Track shape — rounded-corner rectangle (NOT a full stadium / ellipse):** each cap = top quarter-arc + vertical straight middle segment + bottom quarter-arc. Pygame's `pygame.draw.rect(border_radius=...)` draws this natively. Border-radius derives as `v − vert_seg_h/2` per outer + inner rect; outer + inner are independently parameterized (`vert_seg_h_outer = 20`, `vert_seg_h_inner = 15` → smaller inner vert_seg = larger inner border_radius = inner corner more rounded). Stroke at the apex vertical segment stays = `track_stroke_w` since the inner rect is inset by stroke_w on all sides; the corner arcs are NOT concentric (asymmetric flatness) so stroke gradient varies slightly along the arc — by design.

**Per-station screen position** keyed by `sta_code` (e.g. JY24). Bottom row = JY17 → JY30 → JY01 in inner-loop travel direction; top row = JY02 → JY16 (on screen left→right reads JY16..JY02). Missing JY codes (e.g. JY26 高輪ゲートウェイ in pre-2020 data) auto-redistribute the row's spacing across present count — no gap. Row centerline y values derived from `cy ± curve_v_radius` (matching `_draw_track`'s cy) to avoid 1px off-center on bottom-row strokes when `track_top_y + track_bottom_y` is odd.

**Four rendering states** (no dim/passed — circular loops have no terminal "behind"):

- **Pentagon** at `stops[curr_stop]`'s position when `at_station=True` (STOPPING). Asymmetric: flat back (half_w=21) + apex side 1px shorter (half_w=20) + apex extension `triangle_d=4`. Direction-aware: `face_left=True` mirrors apex to the left for top-row stops (inner-loop = R→L on top row). Drop-shadow halo via two x-shifted gray polygon copies + a fixed-size gray fill underneath; small interior light dot (radius 5) at the cell center.
  - **Breath animation**: red body uniformly scales toward `(cx, cy)` between `half_h_max = 17` (= `STOPS_BAR_HEIGHT/2 + overhang`) and `half_h_min = track_stroke_w/2 = 14` (= color-bar height). Halo + drop-shadow stay at max bbox throughout. Triangle wave (constant velocity, no rest at peaks) with period 1.2s (= 0.6s big→small + 0.6s small→big). Frame-rate independent via `pygame.time.get_ticks()`.
- **Numbered countdown circle** for the next 15 stations ahead in inner-loop direction. PASSED_COLOR full disk (the green track band peeking around the disk provides the visible "ring" effect — no route-color outline drawn explicitly) with a CURRENT_COLOR inner overlay only at curr_stop in APPROACHING (mirrors `e235_1000.draw_marks`'s `if gi == curr_stop:` gate, sized larger via `self.circle_outer_radius`). Black countdown digit on top + optional `(分)` suffix on the 15th-ahead. The `(分)` glyph anchors 2px above the color-bar bottom edge (NOT vertically centered with the circle — IRL placement). Time formula = same as `e235_1000.JapaneseDisplay.draw_times`.
- **Plain dot** for the remaining stations (the other half of the loop). Copied from `e235_1000.draw_marks` small-dot path: gray fill at radius 5 via `gfxdraw.filled_circle + aacircle`.
- **Animated approaching-arrow cascade** at curr_stop when `at_station=False` (APPROACHING). Two chevs phase-offset by sweep duration, each sweeping from last station's near-edge (A, +3px past in travel direction) to curr_stop's circle's near-edge (B, −1px before). Per chev: sweep+fade-in (1.0s, ease-out via `1-(1-sweep_t)**ease_out_power` — fast off A, decelerating into B; alpha fade-in on raw `sweep_t`, decoupled from position so the flick keeps a smooth fade) → fade-out at B (0.4s) → rest (0.4s). Cycle 1.8s. Geometry: `e235_1000` full-route chevron primitive verbatim — body 17×32 stroke 11 (tip-portion 6), halo +5 wider / −4 shorter / +6 stroke / 2px back-offset. Endpoints reactive to `self.circle_outer_radius`. Same-row only; cross-row + no-previous fall back to static chev at B. Tuneables in `_compute_chevron_animation_state`. Alpha via SRCALPHA Surface + `BLEND_RGBA_MULT` (`gfxdraw` / `draw_aapolygon` take solid colors only).

The "15 ahead" walk dedupes by sta_code, handling the route.json shape where Yamanote's traversal doubles the start station (`stops[0] = stops[-1] = 大崎/JY24`).

**Direction-of-travel chevrons** on each cap apex: white V on left cap (train descends from top → bottom across the curve), white ^ on right cap (ascends bottom → top). Inner-loop visual cue. 4px stroke, 28w × 6h (≈ full color-bar width × shallow tip), drawn over the green band via `pygame.draw.line`.

**Major-station bold names**: `MAJOR_STATION_NAMES_BOLD = {上野, 東京, 品川, 新宿, 渋谷}` — module-level hardcoded set, **not** derived from `code_3` (大崎/JY24 has code_3 = OSK but is NOT in the bold set per IRL). Names in the set render with `ShinGoPr6N-Heavy.otf`; the rest use `ShinGoPr6N-Medium.otf`. Both at 19pt.

**Vertical kanji stacking** uses the new `displays.utils.draw_1col_text_plain(font, text, x, top_y, color, screen, line_gap=0)` helper — sibling of `draw_1col_text` but without compression / distribution. Tight back-to-back stacking with optional `line_gap` extra pixels. Circular renderer passes `line_gap=1` for 1px gap between stacked chars. Long names overflow rather than squish (multi-column wrap deferred until 高輪ゲートウェイ-class names are added back to the data).

**Disclaimer**: left-bottom anchored at `x=8, y=lower_bottom - 4`. Truncated text (drops the standard `一部区間では時間を表示しません。` tail since Yamanote always shows times). 9pt.

**Out-of-spec fallback**: any non-Yamanote route loaded into E235-0 gets the open horseshoe (`OpenRouteFullRouteDisplay`) — the same racetrack with one cap dropped, NOT a linear bar. See [§ E235-0 — open-horseshoe full-route](#e235-0--open-horseshoe-full-route-non-yamanote).

**Pending iteration / known gaps:**

- Hit-test (click-to-jump on the racetrack) returns `None` for now — pentagon is animated + no clickable affordance yet.
- The breath animation only cycles in interactive preview / app mode; screenshots capture a single frame at random phase.

---

### E235-0 — open-horseshoe full-route (non-Yamanote)

Live in [`displays/train_models/e235_0/lower_lcd.py`](displays/train_models/e235_0/lower_lcd.py) `OpenRouteFullRouteDisplay`. Subclasses `CircularFullRouteDisplay`, reusing its marker primitives (dot / numbered circle / pentagon / approaching-arrow / `_chevron_frames` timeline / name) verbatim and overriding only the JY-keyed pieces to be **stop-index keyed** and linear. Drives the FULL slot for every non-Yamanote route (the circular is Yamanote-only). A best-effort *invented* look — E235-0 is Yamanote-only IRL, so there's no reference photo; floor per the per-model IRL-line-scope policy.

**Shape** — the racetrack with **one end cap dropped** = a horseshoe, not a loop. Bottom row runs L→R from the origin; folds up the right cap; top row runs R→L to the terminus. The left side is open — the two rows terminate at independent flat edges (origin + destination). `_draw_track(band_color=…)` draws the parent's closed racetrack, then whitens the left cap (two rects split at the centerline) plus the band left of each row's leftmost station.

**Layout** (`_build_positions`, keyed by stop index, NOT `sta_code`):
- Split: bottom = `stops[0 : ⌈N/2⌉]`, top = the rest. Shared pitch from the longer (bottom) row, **right-aligned at the fold** (open-left ends float; odd N staggers the two open ends by one slot).
- **No sweep / no window flip** — fit-to-rows by shrinking pitch (longest in scope is Keihin-Tōhoku 46 → 23/row). Revisit only if a real route reads too cramped.
- Direction chevron on the fold (right) cap only (`^`).

**Passed dimming** (the circular has none — a loop has no terminal "behind"):
- Boundary follows the animated `state.cursor_pos` (== `curr_stop` when not mid-skip), matching E235-1000's `gi < cursor_pos`.
- Band: `_draw_passed_band(cursor)` clip-redraws the band gray (`INACTIVE_COLOR`) over the passed portion of the folded path — bottom-left only when curr is on the bottom row; whole bottom + fold cap + top-band-right-of-boundary when curr is on the top row. Green/gray boundary at the `curr-1 ↔ curr` midpoint.
- Passed station dots + names dim to `INACTIVE_COLOR`.

**Skip / passing stations** (carried over from E235-1000's linear renderer; the Yamanote circular has none):
- Passing station = empty `pa` (carries `time: None`). Renders as a **light chevron** (`_draw_passing_chevron`, `PASSED_COLOR`, no halo) pointing in the row's travel direction — right on the bottom row, left on the top — never a numbered circle.
- Passing-station **names always dim**, even when active.
- `_ahead_indices` **skips passing stations**, so only stopping stations get a countdown number; the minute chain (`_compute_minutes_for_ahead`) sums only stopping-station `time` (a stop's `time` already spans the stations skipped to reach it). This also dodges a `None + int` crash that feeding passing stations into the cumulative would cause.
- The APPROACHING pointer cascade is **unchanged** — anchored on `curr_stop` (not `cursor_pos`); `cursor_pos` only drives the dimming.

**Pentagon / approaching arrow** — `face_left = (idx >= n_bottom)` (top row travels R→L). `_compute_chevron_animation_state` walks the previous station as `curr_stop − 1`; at the fold (curr = first top stop, a cross-row pair) it synthesizes a phantom previous one slot to the right of curr on the top row so the chevron sweeps along the top instead of across the fold. Origin (no previous) → static fallback chevron.

---

### E235-0 — 5-station stopping view (Yamanote)

Live in [`displays/train_models/e235_0/lower_lcd.py`](displays/train_models/e235_0/lower_lcd.py) `JapaneseFiveStationDisplay`. Owns the **EIGHT slot** universally on E235-0 (the manager swaps it in for every route — E235-0 has no 8-station view). The view: the green band, five station markers along it, and an inline transfer panel down the left column.

**Band — Tier-2 mask PNG.** Shape is hand-drawn white-on-transparent (`data/e235_0/five_station_band.png`, pixel-precise, not parametric), baked once with the route line color at `__init__` (`_bake_band` — alpha-stencil tint: near-white fill → line color, the grey edge outline left as-drawn, alpha untouched). A bottom-up green fill animation (`_BAND_FILL_DURATION`, sweep axis `_BAND_FILL_ANGLE`) replays on each slot-enter via a masked half-plane erase. The Catmull-Rom arc machinery is retired — see [WIP_calibration_editor.md § "Two-tier tuning model"](WIP_calibration_editor.md).

**Five markers** (positions in `_TUNEABLES_FIVE_STATION`, calibration-editor tuneable): m0 = current stop at the bottom, m1..m4 = next four going up. The next-stop walk (`_visible_stop_indices`) wraps past the doubled loop terminal with name-dedup on a **circular** route (`stops[0].name == stops[-1].name`), so approaching 大崎 the view keeps extending around the loop (大崎 → 品川 → …) instead of dead-ending; linear routes stop at the last stop. m0 is a **free-polygon** red pentagon (five hand-placed vertices v0..v4 — fixed slot + orientation, so no parametric shape model; the white dot rides m0/`m0_dr`) when STOPPING; an approaching-circle + countdown digit + animated sweep arrow (`a0_*`) when APPROACHING. m1..m4 are numbered countdown circles. Minute values = the E235-1000 `draw_times` cumulative chain (`_ahead_minutes` / `_first_stop_minutes`); the chain restarts from 0 when STOPPED (the curr→curr+1 leg is already travelled) vs seeds from the remaining-to-curr time when APPROACHING.

#### Inline transfer panel (left column)

Distinct from the horizontal TRANSFER slot — a vertical panel drawn *inside* the 5-station view (`_draw_transfer_panel`): header `{station}駅` (ShinGo Heavy) + subtitle 乗換えのご案内 (ShinGo Light) + the entry list. Reuses the parent `apply_transfer_filter`, so entry order matches the slot. Hidden entirely when the station has no transfers. Panel stays kanji in every mode (mirrors the kanji-only map).

**Grouping algorithm** (overfit to Yamanote — the only IRL line with this design):

1. **Threshold T (pair-or-stack).** Pairing engages only when `N ≥ tp_pair_min_n` (=6); below, every entry stacks one-per-row regardless of free width (IRL: 神田 / 秋葉原 / 日暮里 stay solo with room to spare). Yamanote's effective transfer counts are **1, 2, 3, 6, 7, 8, 9 — never 4 or 5**, so the 6-cutoff is unambiguous.
2. **Two columns, shared col-2 anchor.** Col-1 is left-aligned at `tp0_x`. When two entries share a row, col-2 shares ONE anchor `col2_x = px + max(col-1 width over all paired rows) + tp_col_gap`, so every row's 2nd-element badge aligns vertically.
3. **Curved right edge.** The boundary is a piecewise-linear curve through three draggable control points tp1 / tp2 / tp3 (sorted by y, extrapolated past the ends): lower rows get more width as the green band sweeps right. `_right_edge(y)` interpolates.
4. **Greedy pairing + monotone repair.** `_build` lays rows top-down, pairing consecutive non-shinkansen when the pair's own footprint fits `_right_edge(y)`. Then the repair loop computes `col2_x`, disables any paired row whose col-2 entry overflows `_right_edge(row_y)`, and rebuilds — repeated until no violators. Disabling only ever removes pairs, so it converges in ≤ N rounds.
5. **Shinkansen.** Always solo (own full-width row); the long name wraps at `･` into ≤ 2 lines against the **narrower fixed** boundary `tp_shink_wrap_x` (decoupled from the row-push curve), so the cut stays fixed (東北･山形･秋田 ｜ 北海道･上越･北陸新幹線) even when the curve is widened for pairing.

Tuneables live in `_TUNEABLES_TRANSFER_PANEL` (calibration-editor `transfer_panel` element): `tp0_x/y` = panel anchor (drag handle), tp1/tp2/tp3 = curve control points (drag handles), the rest are nudge-only scalars.

**Regression corpus** — algorithm output vs IRL row-groupings, **12/12 in-spec ✓** (verified 2026-06-16 via `_dev_scripts/_sim_panel_layout.py`, which reads the live tuneables and faithfully replicates `_build` + repair + shinkansen wrap height; cross-checked against the all-stations montage). Re-run it after any tuneable change to re-baseline.

| Station | N | Rows (members per row) | Lead-row note |
|---|---|---|---|
| 神田 / 高田馬場 (+ every N ≤ 2 stop) | ≤ 2 | all solo | threshold T |
| 大崎 / 目黒 / 新橋 / 日暮里 / 秋葉原 | 3 | (1,1,1) | threshold T |
| 品川 | 6 | (1,1,2,2) | long 京浜東北線（大井町・蒲田方面） leads solo |
| 上野 | 7 | (1,2,2,2) | solo shinkansen row 0 |
| 池袋 | 7 | (2,2,2,1) | |
| 渋谷 | 8 | (2,2,2,2) | |
| 東京 | 9 | (1,1,2,2,2,1) | two solo shinkansen rows |
| 新宿 | 9 | (2,2,2,2,1) | |

---

### 8-Station Zoomed-In View (`JapaneseEightStationDisplay`)

A second Japanese-mode renderer that shows the next 8 upcoming stations at ~2× cell width, alternating with the full-route view via the slot cycler. **E235-1000 only** — E235-0's EIGHT slot is owned by `JapaneseFiveStationDisplay` (see [§ E235-0 — 5-station stopping view](#e235-0--5-station-stopping-view-yamanote)).

#### Window invariant — always exactly 8 cells

Computed in `_get_window(curr_stop, cursor_pos)`. The two args differ only during a skip animation, when `cursor_pos` lags behind `curr_stop` (cursor walks across passing stations while curr_stop already points at the next PA target).

| condition | window start | cursor's local index |
|---|---|---|
| `len(stops) ≤ VISIBLE_COUNT (=8)` | 0 | cursor_pos |
| `curr_stop == 0` | 0 | 0 (no past cell — train hasn't departed anywhere yet) |
| `curr_stop > n - VISIBLE_COUNT` (locked) | `n - 8` | `cursor_pos - (n - 8)` (cursor marches rightward) |
| otherwise (sliding) | `cursor_pos - 1` | 1 (one past cell on the cursor's left) |

`LOCK_THRESHOLD = VISIBLE_COUNT - 1 = 7`. Lock kicks in when `remaining ≤ 7` so the locked window has 1 already-passed cell + 7 ahead = 8 visible.

**Why sliding is keyed on `cursor_pos` but lock on `curr_stop`:**

- *Sliding on `cursor_pos`* keeps the "1 past cell on the cursor's left" contract honest mid-skip. If sliding were keyed on `curr_stop`, the visible cursor (at `cursor_pos < curr_stop` during a skip) would land at local index 0 with zero past context — observable as "the just-departed station vanishes the moment a passing-station skip starts."
- *Lock on `curr_stop`* preserves destination visibility near route-end. If lock were keyed on `cursor_pos`, a brief skip animation just before the lock threshold would let the destination cell drop out of view for the duration of the animation. Lock entry is the moment "the route's tail fits in 8 cells regardless of cursor position" — that's a curr_stop fact.

**Visual side effect:** anchoring sliding on `cursor_pos` means the window shifts left by exactly one cell at the frame `cursor_pos` catches up to `curr_stop` (skip animation completes). Single-frame snap; preserves the past-cell-always-visible contract.

#### View cycler (`LowerDisplay`)

Slot rotation. Three slots with per-slot durations: `FULL` 12s / `EIGHT` 12s / `TRANSFER` 6s. Lives on `LowerDisplay` (NOT shared with upper's 4s language cycler — orthogonal concerns).

**Slot membership** is computed per-frame from state via `_available_slots`:

| in transfer window? | 8-station locked? | Slots in rotation |
|---|---|---|
| no  | no  | `[FULL, EIGHT]` |
| no  | yes | `[EIGHT]` |
| yes | no  | `[FULL, EIGHT, TRANSFER]` |
| yes | yes | `[EIGHT, TRANSFER]` |

`TRANSFER` is also dropped when the current station has no transfers (post-filter) — the cycle just rotates without a blank slot.

**Window predicate** (`_in_transfer_window`): `at_station=True` OR `cnt_pa >= len(pa)-1`. Derived from `cnt_pa` rather than `state.is_last_pa` — single-PA stations auto-fire `pa[0]` via `_advance_to_next_stop` which hardcodes `is_last_pa=False`, so the flag misses them. The `cnt_pa` check covers both single-PA and multi-PA paths.

**Two transitions matter:**

- transfer-window rising edge (passive join) — `TRANSFER` enters slot list mid-stream as the predicate flips True (last PA fired); cycle naturally rotates to it on its next turn. No timer reset.
- `at_station` rising edge (force-switch) — `_handle_at_station_edge` sets `_current_slot = TRANSFER` and resets `_slot_start`. Boot's initial `at_station=True` is captured as the first observation without firing the edge (so boot doesn't auto-jump to transfer).

**Slot reconciliation**: when `_current_slot` is no longer in the available slot list (lock kicked in mid-FULL, window closed mid-TRANSFER, station with no transfers reached mid-TRANSFER), `_tick_cycle` snaps to `slots[0]` and resets the timer.

**Critical invariant** — `_tick_cycle(current_time)` is called from `LowerDisplay.draw()` UNCONDITIONALLY, BEFORE language-mode dispatch. Nesting it in the `KANJI/FURIGANA` branch pauses the timer during `ENGLISH` (≈1/3 of every language cycle) and cadence drifts long. `_pick_renderer(mode)` is a pure function of `_current_slot` + mode (TRANSFER overrides language; otherwise Japanese slots dispatch to full/eight, ENGLISH dispatches to `english_display` for the full-route slot, falling back to `japanese_eight_display` for the 8-station zoomed slot).

#### Per-cell mini badge

Sized to ~half the station-circle diameter. Square (22×22), no black outer ring (route color goes to the edge), thin 2-px route-color ring around a white interior, fonts 8 pt prefix / 11 pt num, `text_gap=1`. Past-station badges keep full route color (IRL doesn't dim).

Drawing logic lives in `displays/utils.draw_station_code_badge` — shared with the upper LCD's prominent single-station badge. Lower passes `text_y_offset` to nudge the JO/number group to taste.

#### Compound-name layout (Keihin's `さいたま 新都心`)

Two columns. **Right column** reads first (`parts[0]`), **left column** reads second (`parts[1]`) — Japanese top-to-bottom right-to-left reading order. Both columns share a 3-character standard height (`baseline_vs = 3 * char_h`); a 4-char part compresses to fit, a 3-char part stays uncompressed.

- Right column **top** anchors at `label_top_y` (aligns with single-column stops' tops).
- Left column **bottom** anchors at `label_top_y + label_box_h` (aligns with single-column stops' bottoms).

The compression of `さいたま` (4 chars in 3-char height) is what visually signals it's the "raised, denser" half — DON'T relax it to `label_box_h`, you lose the asymmetry.

#### Single-character station name (Keihin's `蕨`)

Rendered via direct `font.render` + blit and **vertically centered** in the label box (not stacked from the top via `draw_1col_text` — that would pin it to the top).

#### Pointer chevron — uniform halo recipe

Two polygons: an inner filled red chevron and an outer outline chevron. For the halo to read uniformly:

```
delta = halo_width
outer_w      = inner_w      + delta
outer_stroke = inner_stroke + delta
outer_x      = inner_x      - delta // 2  # centers outer around inner
```

If `outer_w - outer_stroke ≠ inner_w - inner_stroke`, the tip-lengths differ and the halo reads as proportionally pointier or blunter than the fill. See [Shared utility gotchas § `arrow_points` chevron recipe](#arrow_points-chevron-recipe-utilspy) for `stroke` semantics + the `arrow_points` docstring in `utils.py` for the full geometry.

#### Initial-stop pentagon (curr_stop=0)

Drawn instead of the chevron when `curr_stop == 0`. Its `overhang` must equal `inner_h_overshoot // 2` of the chevron pointer so heights match across stop=0 and mid-route frames.

#### Passing-station chevron centering

Use `(stops_w - arrow_w) // 2` for true horizontal centering. The full-route's `stops_w * 0.3` constant is an approximation that's only ~1 px off true center for narrow `stops_w=42` cells but ~8 px off for the 8-station view's `stops_w=82` cells. Don't copy the magic number across.

#### Continuity triangle (8-station view)

When the route continues past the visible window, the last cell's bar extends into a right-pointing triangle (via `draw_continuity_triangle`). Drawn after `draw_times` so it extends past the 分 marker when present. Color matches the last cell's active/inactive state. No chevron arrows — just the triangle. The 分 marker's 3px white cap is suppressed on the last cell so the triangle attaches flush.

#### Layout tuneable params

Live as labeled locals at the top of `JapaneseEightStationDisplay.__init__` (`VISIBLE_COUNT`, `LOCK_THRESHOLD`, `side_margin`, `label_top_pad`, `label_h_chars`, `label_font_size`, `bar_height`, `bar_badge_gap`, `badge_w/h`). Adjust there — values not duplicated here to avoid drift. Badge point sizes (`prefix_size`/`num_size`) live in the per-cell badge params block; the badge **typeface is fixed** (Frutiger) inside `draw_station_code_badge` and is not a caller parameter.

#### Route disclaimer

`displays/utils.draw_route_disclaimer` renders the standard PIDS legalese (`のりかえ、待合せ時間は…`) bottom-right anchored, dark color matching active station-name labels. Both `JapaneseDisplay.show_stops` and `JapaneseEightStationDisplay.show_stops` call it as the last draw step.

---

### Shared utility gotchas (used by lower LCD)

#### `draw_1col_text` per-character horizontal centering (`utils.py`)

Each glyph in a vertical column is centered against the **widest character's column width**, not against the function's `x` arg directly.

Without this, mixed-width strings render off-axis: digit `2` and katakana `ビル` in `空港第2ビル` line up flush-left under the wider kanji.

The function takes a single `x` (left edge of the widest char's column) and computes per-char offsets internally — callers don't need to do anything special.

#### `arrow_points` chevron recipe (`utils.py`)

The `stroke` parameter is the chevron's **body thickness**, NOT a typical line stroke. To resize without changing shape: scale `w`, `h`, AND `stroke` by the same factor. Bumping only `w` makes the chevron pointier (longer tip, same body). See "Pointer chevron — uniform halo recipe" above for the inner/outer halo math, plus the full docstring in `utils.py`.

---

## Transfer Info

Lower-LCD slot showing the station's transfer-info frame (banner + per-line entries) when at a station with `transfers` data. The parent `displays/transfer_info.py:TransferInfoDisplay` handles state binding + active-line filter + `transfers_by_view` drop/edit ops + variant resolution (`resolve_entry`); the E235-1000 concrete `displays/train_models/e235_1000/transfer_info.py` provides the renderer (`render_transfer`), wired into `LowerDisplay`'s view-cycler in `lower_lcd.py`.

E235-0 inherits the E235-1000 transfer-info renderer unchanged for its horizontal TRANSFER slot (interim — visual fidelity for that slot has not been validated against IRL Yamanote refs). E235-0 *also* has a separate **inline transfer panel** inside its 5-station view, with its own grouping algorithm — see [§ Inline transfer panel](#inline-transfer-panel-left-column).

### Pipeline

1. **Per-N text scaling** — JA size from `N_total` + shinkansen-count: Sparse (≤4) 32 / N=5 29 / Mid (6-9) 26 / Dense (≥10 OR ≥2 shinkansen) 22. EN derived `round(JA × 12/23)`. `name_line_gap` scales with EN. "Both shinkansen" (Tokyo JO) forces Dense regardless of N.
2. **Row-grouping (dry-run cascade)** — decision order: `rows` data override → shinkansen prefix → small-N structural (N=2: `(2,)` if Σ widths ≤ W − 2·margin_x else `(1,1)`; N=3: always `(2,1)`) → greedy walk + cascade dry-run for N=1 and N≥4. `max_rows = 3` cap force-packs the rest onto the last allowed row.
3. **Blueprint widening** — `effective_margin_x = max(margin_x, h_narrowest)` where `h_narrowest = min over rows of (W − Σ_row) / (n_row + 1)`. Inert when no row is narrower than default margin.
4. **Real-render placement (per row)** — Rule 1 (column-align if N ≤ M; asymmetric predecessor-intrusion check) → Rule 2 (head + tail + leftmost-fit; tracks `predecessor_clean_seen` for Case A vs B) → Rule 3 (Case A only: canvas-right tail) → Rule 4 (equal-spacing + track-back of earlier rows). Anchor row uses **column-aware** placement (max width per column across non-shinkansen rows) when `slack ≥ 0`; falls back to geometric `head/tail/distribute` when `slack < 0` (品川, 横浜).

### Definitions (used in Rules 1-4 below)

- `N` = number of entries in current row.
- `M` = number of upper anchors = `len(upper_anchors)` of the row directly above.
- `upper_anchors[k]` = chosen x position of the k-th entry in the row directly above.
- `widths[k]` = full entry width (badge group + gap + max(JA, EN) text width).
- **predecessor of entry k** = entry k-1 (immediate left in the same row).
- **predecessor's right edge** = `predecessor.x + predecessor.width`.
- `effective_margin_x` = `margin_x` initially; can grow if Rule 4 fires.
- `right_edge_canvas` = `W − effective_margin_x`.

### Rule 1 — column alignment (fires only when N ≤ M)

Per-entry left-to-right sweep. Entry k attempts to anchor at `upper_anchors[k]`. **Asymmetric predecessor-intrusion check** is the only validator: entry 0 has no predecessor → always succeeds at `upper_anchors[0]`; entry k (k ≥ 1) succeeds iff `predecessor's right edge ≤ upper_anchors[k]`. Otherwise blocked.

**Asymmetry rationale.** Entry k overflowing rightward into entry k+1's territory is NOT entry k's concern — it doesn't block entry k. But entry k+1's anchor at `upper_anchors[k+1]` being intruded by entry k's text IS entry k+1's concern — it blocks entry k+1. The check is one-directional: the entry being placed cares only about whether its own predecessor intrudes into its own anchor.

**Failure is per-entry, not row-wide.** Successful entries stay anchored. The first failure stops the sweep at index `first_failed`; entries `[first_failed..N-1]` proceed to Rule 2 as a segment.

### Rule 2 — head + tail + distribute, leftmost-fit tail

Triggered by either failed-segment case (Rule 1 partial success, fails at `f = first_failed > 0`) or N>M case (Rule 1 didn't fire). In failed-segment case: `head_right = chosen_xs[f-1] + widths[f-1]` (last Rule-1-successful entry's right edge — NOT reset to margin_x); tail = entry N-1; middles = entries `[f..N-2]`. In N>M case: head = entry 0 anchored at `upper_anchors[0]`; tail = entry N-1; middles = entries `[1..N-2]`.

**Tail anchor — leftmost-fit.** Iterate `upper_anchors` in order. Cand `a` is "fitting" iff (1) middle-distribution check passes (`distribute_middles(head_right, a, middle_widths)` returns valid; if no middles, `head_right ≤ a`) AND (2) canvas check (`a + tail.width ≤ right_edge_canvas`). First fitting cand becomes tail's anchor; middles distribute evenly between `head_right` and tail's anchor. If no cand fits → Rule 3.

### Rule 3 — canvas-right fallback (Case A only)

Rule 2's failure mode determines whether Rule 3 fires:

- **Case A** — at least one upper anchor passed the predecessor-intrusion check, but tail overflowed canvas. → Rule 3 fires (canvas was the constraint, not anchors).
- **Case B** — every upper anchor failed the predecessor-intrusion check. No usable column-anchor; row genuinely needs more space than upper provides. → Rule 3 skipped; fall directly to Rule 4.

Detection via `predecessor_clean_seen` flag (set to True whenever a cand passed the predecessor check, regardless of canvas).

**Rule 3 (Case A).** `tail_x = (W − effective_margin_x) − tail.width` (tail's right edge = canvas right). Middles distribute between `head_right` and `tail_x`. If `tail_x < head_right` or middles don't fit → Rule 4.

**Why Case A uses canvas-right and Case B doesn't.** In Case A the column-anchor system already proved insufficient; canvas-right is the most permissive remaining placement and visually matches IRL. In Case B (Shinagawa row 1's 東海道線 example), canvas-right would float the tail too far right (huge gap from predecessor); equal-spacing via Rule 4 produces a balanced layout instead.

### Rule 4 — equal-spacing fallback + track-back

Triggered when Rule 3 dies. `h = (W − Σ widths) / (n+1)`. If `h < margin_x`: fall to last-ditch (degenerate; sub-floor sides). Otherwise: row placed with **equal-spacing** (head at `h`, inter-gap `h`, tail right-edge at `W − h`; sides == inters == `h`). **Track back**: shift all rows already placed (0..R−1) by `delta = h − effective_margin_x` so their head_x aligns with the new effective margin. Anchors, right-edges, and the positions list update in lockstep. Set `effective_margin_x = h` for subsequent rows. Delta is often non-zero even when blueprint widening fired upstream — blueprint sets margin to `h_narrowest` (smallest h), but a different row may turn out to need an even wider gap; track-back covers the residual.

### Shinkansen-prefix anchor row

- **0 shinkansen** → anchor row = row 0.
- **1 shinkansen** (上野) → anchor row = row 1 (column-aware override; row 0's single shinkansen can't seed column alignment).
- **2+ shinkansen** (Tokyo JY/JO) → no override; cascade Rule 2 column-aligns naturally against the shinkansen positions.

### Color-square policy

E235-1000 only: a badge with `icon: "_universal"` AND a `color: [r, g, b]` field renders as a solid color square (badge_h × badge_h) instead of the universal icon. Lines using this today: 総武本線, 外房線, 内房線, 成田線. Detection in `is_color_square(b)` inside `render_transfer`. Future train models declare their own policy in their `transfer_info.py`.

### Out-of-spec note

武蔵小杉 JN runs E233-8000, not E235-0/1000 — out of E235 in-spec. Per [CLAUDE.md "Per-model IRL line scope"](CLAUDE.md), out-of-spec routes get best-effort fidelity floors (no crashes, sane layout) rather than IRL match. Per-N scaling ladder + algorithm thresholds are calibrated against E235 IRL refs only. MKG-on-JN render uses MKG's E235-ordered transfers list (tokyu before sotetsu) — IRL E233-8000 has the opposite order; per-view ordering deferred. The algorithm picks `(2,2,1)` for the 5 entries vs IRL `(3,2)` — accepted as out-of-spec drift.

### Worked examples — Case A vs Case B

The Case A / Case B dispatch in Rule 3 is the subtlest decision in the pipeline. Two illustrative walkthroughs:

**Yokohama JO row 2 — Case A** (N=3, M=4 with blue line at .scale(0.75) → w=267). `widths=[99, 189, 267]`. Rule 1: k=0 (相鉄) anchor 40 right 139; k=1 (みなとみらい) upper[1]=210 ✓ right 399; k=2 (BL) upper[2]=357, 399 > 357 → BLOCKED. first_failed=2. Rule 2 failed-segment, head_right=399, no middles, tail=267. upper[0..2] all fail predecessor; upper[3]=533 predecessor-clean (`predecessor_clean_seen=True`) BUT canvas 533+267=800>690 → canvas overflow. No fitting cand → Case A. Rule 3: tail_x=423, head_right 399 ≤ 423 ✓. → `[40, 210, 423]`.

**Shinagawa JY_inner row 1 — Case B** (N=2, M=1). `widths=[302, 120]`. N>M → Rule 2. Head at upper[0]=81, head_right=383. Iterate `upper_anchors=[81]`: head_right 383 > 81 → predecessor intrusion. Only one cand fails → `predecessor_clean_seen=False` → Case B. Skip Rule 3; Rule 4. h=(730−452)/3=92.67. Row 1 at `[93, 518]`. Track back row 0: delta=12, shinkansen shifts `[81]→[93]`. effective_margin_x=93.

(Tokyo row 0/1/2 walk-throughs — N=2 structural, N>M Rule 2, Rule 1 → Rule 2 failed-segment respectively — covered by the rule specs above + the verification corpus below.)

### Verification corpus

Pre-implementation reference set for validating the row-grouping pipeline. `N` computed from `data/stations.json` (own-line filter + `transfers_by_view` drops). IRL groupings sourced from station LCD reference photos. **22/22 in-spec ✓** as of 2026-05-05; 武蔵小杉 JN is out-of-spec (E233-8000, not E235) and kept as a best-effort comparison point only.

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

### Where layout knobs live

The params block at the top of `render_transfer` (font sizes, margins, scaling tiers, banner spec) is the canonical home for IRL-derived tuning. Each value carries a one-line "why" comment. When changing tuning, adjust the named constant — don't redo the IRL math elsewhere.

### Discussion conventions for IRL-valid renders

Every render referenced as an IRL comparison point MUST correspond to a real-world train's perspective: a specific active line (`--filter-line`) AND that line's own direction view when applicable (`--view <line>_<direction>`). Default render (no filter) is invalid as IRL reference — it's the simulator's superset. View follows from line: don't ask "which view?" once the line is chosen. Auto-memory carries the same rule as a feedback binding.

### Known gaps / not-yet-validated

- Stations beyond the verification corpus (~25+ populated stations in 大宮, 川崎, 浦和, 赤羽, JO Sōbu Rapid east) not yet visually swept against IRL groupings.
- 赤羽 JK/JA inner spacing observation pending verification once added to corpus.
- Last-ditch `pack-from-margin` path never fires on real corpus data — Rule 4 always catches first.
- Private-operator icons at runtime still partly fall back to `_universal` placeholder for lines without dedicated icons.

---

## Related Documentation

- [DISPLAY.md](DISPLAY.md) — cross-model infrastructure: DisplayMode, ModeCycler, Unified State Machine, Adding New Train Model, Lower-LCD interface contract
- [CLAUDE.md](CLAUDE.md) — project overview, "Mental Model" framing, "When Working On…" pointers
- [DATA_FORMAT.md](DATA_FORMAT.md) — `translations.json` / `train_types.json` / `stations.json` / `route.json` shapes
- `displays/train_models/e235_1000/` — code home for E235-1000 renderers
- `displays/train_models/e235_0/` — code home for E235-0 renderers
- `displays/transfer_info.py` — parent transfer-info logic shared by all train models

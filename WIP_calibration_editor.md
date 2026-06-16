# WIP — Calibration Editor (v1)

Direct-manipulation pixel tuning for pygame LCD elements. Sidebar overlay; click an element; nudge / cycle / reset params; Ctrl+S writes back to source. Lives in `_dev_scripts/calibration_editor.py`, wired via `preview_display.py --edit`.

**Motivation.** Claude bad at pixel-tuning closed loop (image-resolution + spatial-reasoning limits). Move iteration locus off claude: user nudges in-app, sees live re-render, persists values; claude consumes final state on commit.

**Lineage.** Pattern from Claude Design auto-generated adjustment sliders (Anthropic Labs, 2026-04-17). Product doesn't fit; pattern does.

---

## Status

v1 shipped 2026-05-13 PM on `feat/calibration-editor`. Upper-LCD framework expanded to 4 elements 2026-05-14 (dest / clock / prefix / station). Phase 1b shipped 2026-05-14 evening: lower-LCD broadcast via `arc` element (5-station view green band scaffold, shape-only — stations + pentagon + minute markers deferred to Phase 2). New mechanics in Phase 1b: polyline-with-per-point-stroke geometry, waypoint + stroke param-kinds, target-driven sidebar layout dispatch, AST-writeback corruption fixed.

Phase 2 editor upgrades shipped 2026-05-15: (a) Figma-style drag handles for arc waypoints (filled circles with generous hit radius, sidebar auto-jumps to dragged waypoint's `_x` row); (b) centripetal Catmull-Rom centerline replaces straight-line polyline (passes through every waypoint, C1 continuity at junctions, endpoint phantom-neighbor reflection); (c) `arc_smoothing` tuneable for post-densification 3-tap [1,2,1]/4 averaging passes — relaxes the band away from exact waypoint pull when "nodes too strong" perception kicks in; (d) bumped 4 → 7 waypoints, p0/p6 = band end-caps + p1..p5 = 5 station slots rendered as time-circle proxies (pre-IRL stand-ins for direct station-on-band tuning); (e) `--overlay <path>` CLI flag → semi-transparent IRL reference image blit over lower LCD, Alt+drag pan / Alt+wheel-or-`=`/`-` zoom (aspect kept) / `O` toggle, offset/scale/visibility persisted to gitignored `_overlay_state.json` so re-launches resume alignment.

Graduation gate (b) partially proven by the arc; full sign-off still needs the real time-circle render (arrival-minute number, current-stop pentagon) replacing the proxies — copy the primitive from `e235_1000.lower_lcd` per conventions.md § "Forking a sibling-model renderer".

2026-06-15: `five_station` element gains draw-state gating (handles + sidebar rows hidden when the element they tune isn't drawn in the current state), approaching arrow renamed to draggable `a0` handle. Current `_TUNEABLES_FIVE_STATION` key schema: always-shown `m0_x/y`, `m1..m4_x/y/r/ts`, `g0..g4_x/y/b/ns/ni`; stopping-only `v0..v4_x/y` (pentagon vertices), `m0_dr` (dot radius); approaching-only `m0_circle_r`, `m0_circle_inset`, `m0_ts` (digit size), `a0_x/y/angle/scale/halo_w` (arrow).

2026-06-15 (later): **`transfer_panel`** registered as a second lower-LCD element — the 5-station view's inline left-column transfer list (`displays/.../e235_0/lower_lcd.py:_draw_transfer_panel`, dict `_TUNEABLES_TRANSFER_PANEL`). Rect `TP_RECT` = the left column (width ≈ panel right edge), registered **before** `five_station` so left-column clicks focus the panel while arc/marker clicks (x ≥ 224) fall through to the markers. Single draggable anchor `tp0_x`/`tp0_y` (panel top-left; header → subtitle → list flow from it); every other `tp_*` key is a nudge-only scalar (sizes / gaps / pitch / shinkansen-scale). Handle prefix `tp` (per_station=False), distinct green core.

2026-06-15 (later): **per-element drag lock** — `K` toggles a lock on the focused element. Locked handles render dimmed (no bright core) and are inert to grabs, so an accidental drag can't be swept into the next Ctrl+S; keyboard nudge of a deliberately-selected row still works (drag is the accident vector, not nudge). **Whole-element** granularity, **persisted** across launches to gitignored `_editor_locks.json` (loaded in `enter_edit_mode`; ids no longer in `_REGISTRY` are dropped on load). Sidebar header shows `[LOCKED — K]`.

---

## Architecture (locked)

| Decision | Pick |
|---|---|
| Source of truth | Module-level `_TUNEABLES_*` dicts in target `.py`; draw methods read from dict |
| Editor surface | In-pygame sidebar overlay (Lane A) — single window |
| Selection | Click LCD element → sidebar shows that element's dict params (α-first) |
| Edit mode | Frozen frame. Sim paused, audio stops |
| Persistence | **Three states kept distinct** (2026-06-16 refactor): baseline = source at launch (`_originals`); edits = `_edited_keys` per-(dict,key) set of what the user actually changed; live = the in-place-mutated module dict the renderer reads. **Ctrl+S writes back ONLY keys in `_edited_keys`** (type-guarded value-swap; `_swap_dict_literal(allowed_keys=…)` leaves every other key's source text byte-for-byte). No save → in-memory mutation discarded, source reloads next launch. Silent scratch auto-restore **removed** — it was the cross-session drift vector (one element's stale state leaking into source on the next unrelated Ctrl+S). |
| Mode-switch | Manual via `L` — sync sim mode to focused dict's family. No auto-switch on row change (disrupts flow) |
| Sidebar layout | Dispatched from focused element's `target` field on `_REGISTRY` entry: `"upper"` → sidebar below upper LCD (side-by-side LCDs above); `"lower"` → sidebar on right half of doubled window, LCD A spans full window left half (upper + lower visible). Lower-LCD focus auto-switches sim to KANJI so the `japanese_eight_display` renderer dispatches (ENGLISH would fall through to full-route). |

---

## Param-suffix convention

Key naming drives **both** semantics AND free visualization. Editor infers param-kind from suffix:

| Suffix | Kind | Indicator |
|---|---|---|
| `_x` | screen x coord | horizontal ruler from screen 0 → val + dim ruler for paired `_w` extent |
| `_y` | screen y coord | vertical ruler from screen 0 → val + dim ruler for paired `_h` extent |
| `_w`, `_width` | width, paired with `_x` | horizontal ruler from anchor_x → anchor_x + val |
| `_h`, `_height` | height, paired with `_y` | vertical ruler from anchor_y → anchor_y + val |
| `_color` | RGB tuple | 16px swatch in sidebar row |
| `_<edge>_offset`, `_<edge>_margin` | edge-anchored offset (`<edge>` ∈ left / right / top / bottom) | ruler at `rect.<edge> ± val` |
| `_p<N>_x`, `_p<N>_y` | polyline waypoint coord (paired with same-stem sibling) | highlighted ring at `(px, py)` — paired axis read from same dict |
| `_p<N>_stroke` | per-waypoint band thickness (paired with same-stem `_x`/`_y`) | horizontal bar centered at the waypoint with length = stroke |
| anything else (`_offset` without edge, `_size`, `_pad`, `_margin` without edge) | recognized but no indicator | tunable still works; no visual feedback — gentle convention pressure |

Pair detection for `_w` / `_h`: same-stem `_x` / `_y` in same dict. Fallback strips `_max` (e.g. `two_line_max_w` → `two_line_x`).

Dict-name suffix drives mode-follow-focus: `_KANJI` / `_FURIGANA` → japanese family; `_ENGLISH` → english family. Press `L` to sync sim mode to focused dict when needed.

---

## Region-level tuneability pattern

Per-element internal-layout dicts (`_TUNEABLES_DEST_KANJI` etc.) tune what's INSIDE a region. To tune the region rect itself (position + size of `CLOCK_RECT`, `DEST_RECT`, etc.), declare a sibling `_TUNEABLES_*_RECT` dict at module top and derive the rect from it:

```python
_TUNEABLES_CLOCK_RECT = {"clock_x": S_WIDTH - 170, "clock_y": 0, "clock_w": 80, "clock_h": 35}
CLOCK_RECT = pygame.Rect(_TUNEABLES_CLOCK_RECT["clock_x"], _TUNEABLES_CLOCK_RECT["clock_y"],
                         _TUNEABLES_CLOCK_RECT["clock_w"], _TUNEABLES_CLOCK_RECT["clock_h"])
```

**Key naming.** Each region rect dict uses `<element>_x` / `<element>_y` / `<element>_w` / `<element>_h` where `<element>` = rect-name minus `_RECT`, lowercased (e.g. `CLOCK_RECT` → `clock_*`, `DEST_RECT` → `dest_*`). The shared stem lets pair-detection wire `_w` ↔ `_x` and `_h` ↔ `_y` rulers automatically — bare `x`/`y`/`w`/`h` keys don't pair because pair-detection requires a same-stem `_x`/`_y` candidate (and `x` alone doesn't end with `_x`).

The draw method syncs `CLOCK_RECT` from the dict each frame via `CLOCK_RECT.update(tr["clock_x"], tr["clock_y"], tr["clock_w"], tr["clock_h"])` so editor nudges land immediately (pygame.Rect is mutable in place — editor's `getattr(mod, "CLOCK_RECT")` reads the live value). Register both dicts on the same element in `_REGISTRY` so a single click on the region surfaces region + internal tuneables together.

**Convention compliance:** the region rect drives the clip wrap AND the bg fill AND the debug-grid tint (per DISPLAY_E235.md § "Element confinement"). Don't draw a sub-sized bg rect with hand-tuned magic numbers — fill the full region rect, let clip + font ascender handle visible glyph alignment.

**Pioneers:** `CLOCK_RECT` + `PREFIX_RECT` (2026-05-14). Other region rects (`DEST_RECT`, `STATION_RECT`, `BADGE_RECT`, `PA_HINT_RECT`) convert lazily when each element next needs in-editor positioning.

---

## Per-element internal-layout dict shape (emerging convention)

Sibling to the region-rect dict above. Each region's drawable internals get a `_TUNEABLES_<ELEMENT>[_MODE]` dict at module top, where `_MODE` (`_KANJI` / `_FURIGANA` / `_ENGLISH`) is appended only when font + sizes diverge across modes.

| Region | Per-mode font diverges? | Dict shape |
|---|---|---|
| Clock | No (same font + size JA/EN) | Single `_TUNEABLES_CLOCK` |
| Prefix | Yes (ShinGo 25 vs HelveticaNeue 27) | `_TUNEABLES_PREFIX_KANJI` + `_TUNEABLES_PREFIX_ENGLISH` |
| Destination | Yes | `_TUNEABLES_DEST_KANJI` + `_TUNEABLES_DEST_ENGLISH` |

**Key conventions inside:**
- **Terse: only include what's actually tuneable.** If the text is anchored to `RECT.left` by design (single-drawable element), don't include `text_x` — anchor is implicit. Same for `text_y` if at `RECT.top`. Adding a knob signals "this could vary."
- **Position keys are RECT-relative.** `text_y: -3` means `RECT.top + (-3)`. Convention: offsets are negative-allowed nudges from the natural anchor. (Absolute screen coords belong in `_TUNEABLES_*_RECT`, not here.)
- **Font filename stays hardcoded in draw method.** Only font size is tuneable. Filename is a structural choice (script family), not a layout knob.
- **Sub-element prefix.** When a dict tunes multiple drawables (e.g. dest = box + suffix), each gets its own stem prefix (`dest_box_x`, `suffix_right_offset`). Single-drawable dicts use bare `text_x`/`text_y` since the only thing being positioned is "the text."

---

## Features landed (v1)

| Feature | Keybind |
|---|---|
| Element focus | Click element rect on LCD |
| Row select | `↑` / `↓` (key-repeat enabled) |
| Nudge value | `←` / `→`; `Shift+` for ±10 |
| Reset to original | `R` (scalar = whole value; tuple sub-row = just that channel; cycler = original dest) |
| Sync mode to focused dict | `L` (one-shot, no auto-switch) |
| Cycle dest candidate (pinned `DEST.value` row) | `←` / `→` while focused on cycler row |
| Cycle display mode (KANJI / FURIGANA / ENGLISH) | `M` |
| Cycle stop | `[` prev, `]` next |
| Scroll sidebar | mousewheel / `PgUp` / `PgDn` (auto-scroll on row select) |
| Save back to source | `Ctrl+S` (clears scratch JSON) |
| Toggle drag handles (hidden = inert to grabs) | `H` |
| Lock / unlock focused element (drag-inert; persists to `_editor_locks.json`) | `K` |
| Quit (scratch persists for resume) | `ESC` |

**Sidebar shows:**
- Modified rows display `current ← original` with warmer text color
- Color rows render an inline 16px swatch
- Scrollbar on right edge when content overflows
- Synthetic `DEST.value` cycler row pinned at top for elements that have a candidate set built (dest only today)

**Visual indicator on LCD (focused row):** figma-style rulers with end-tick caps, placed outside the focused element's rect when there's room (else just inside the boundary). Bright color for the focused param; dim color for the paired dependent extent (e.g. while tuning `_x`, the paired `_w` end-edge stays visible).

---

## Implementation notes

**Single file.** `_dev_scripts/calibration_editor.py` (~600 LOC). Sidebar rendering, hit-test, widgets, scratch JSON, writeback all inline.

**Source refactor (E235-0 dest):** both `draw_destination` methods read from module-level `_TUNEABLES_DEST_KANJI` / `_TUNEABLES_DEST_ENGLISH`. Fonts loaded lazily via cached `_font(filename, size)` factory so `font_dest_size` / `font_suffix_size` can be tuned at runtime.

**Synthetic rows.** Candidate cyclers use a sentinel `dqn` shape `"__candidate__:<element_id>"` with `type_tag = "candidate"`. `_build_param_rows` returns the normal dict-derived rows; the cycler is prepended in `_on_click` when the focused element has a build-candidates hook. `_draw_focused_indicator` early-returns on `"candidate"` / `"unsupported"` rows.

**Writeback.** AST walks the dict literal `<dict_name> = {...}` at module level, replaces each key's value-side via `ast.Constant` end-col-offset math. Type-guarded (int / float / tuple-of-numeric / str). Multi-line values skipped with warning. Tuple inside dict re-emitted via `repr()`. **Iteration is reversed** so rightmost edits land first — earlier-col cols stay accurate when multi-key-per-line schemas (Phase 1b arc polyline) put N values on one line. Forward iteration corrupts source the moment any value's repr length shifts. See [critical_lessons.md § "AST source-edit must iterate values in reverse"](.claude/rules/critical_lessons.md).

---

## Open threads

1. **More elements** registered for tuning (badge / station / route bar) — mechanical pattern: extract `# fmt: off` block → `_TUNEABLES_*` dict, declare hit-test rect, add `_REGISTRY` entry. (Clock + prefix shipped 2026-05-14.)
2. **Animation play toggle** — for chevron `sweep_duration` etc; need motion to tune.
3. **Cross-route candidate sampling** for the dest cycler — current = unique dests in loaded route only (Yamanote = 6 compounds). Walk every `audio/*/route.json` + `_mock` for short / long / katakana variety.
4. ~~**Mouse-drag handles (Phase 2 editor upgrade).**~~ Shipped 2026-05-15 (waypoints only). Figma-style grab handles render at every `arc_pN_x/_y` pair when arc focused; click-and-drag updates the underlying dict values live, band reshapes next frame, sidebar auto-jumps focus to the dragged waypoint's `_x` row. Generous 12px hit radius (grab area). Extension to other `_x`/`_y` pairs (region rects, text anchors) deferred — current scope was Phase 1b/2 arc friction. QOL 2026-06-12 (five_station tuning): `H` toggles handle visibility (hidden = inert to grabs, click falls through); mousedown records a **grab offset** so clicking a handle no longer snaps the waypoint to the click point; `_rebuild_param_rows` clamps `_focused_row` (per-station row counts differ — stale index crashed the indicator draw). **Handle redesign (later 2026-06-12):** all handles are now small **open two-tone crosshairs** (clear-centre gap + dark casing under a bright core), replacing the hollow rings. Least obstructive (the aligned point + any digit underneath stay visible) AND contrastive on any backdrop — a single colour vanishes (red vertices on the red marker, white markers on white disks), so the dark casing carries contrast on light surfaces and the bright core on dark/coloured ones. Arms 6px / 8px dragging (`_HANDLE_ARM` / `_HANDLE_ARM_DRAG`), down from the old 5/7px rings. Two prefixes added to the `five_station` element: `v0..v4` = the current-stop marker's **free-polygon vertices** (the parametric home-plate pentagon `m0_a`/`m0_sl`/`m0_ra`/`m0_pt` was dropped — a fixed-slot, fixed-orientation marker needs no shape model, so the vertices ARE the shape; the white dot rides `m0`, radius `m0_dr`); `select_prefixes: ["m","g"]` scopes per-station panel reselection so vertex grabs don't hijack the filter to a "station." **Approaching arrow drag handle (2026-06-15):** arrow keys renamed `m0_arrow_*` → `a0_x/y/angle/scale/halo_w`; prefix `a` added to `five_station` waypoints (NOT to `select_prefixes` — arrow is not a station). **Draw-state gating (2026-06-15):** `_REGISTRY["five_station"]["draw_state"]` maps prefixes/keys to `"stopping"|"approaching"`; `_arc_waypoints` skips a prefix's handles when its state doesn't match, `_build_param_rows` skips rows the same way. `_cycle_stop` calls `_rebuild_param_rows` so the sidebar re-gates when `[`/`]` flips `at_station`. `_edit_sim` global stores the sim at `enter_edit_mode` so gating reads `state.at_station` without threading `sim` through every internal call.

## Value cycler hook (generalized 2026-05-14)

Per-element value cyclers register via the `_REGISTRY[element]["cycler"]` dict, populated at module bottom of `calibration_editor.py` (forward-refs functions defined mid-file):

```python
_REGISTRY["<element>"]["cycler"] = {
    "build": <fn>,    # (sim) -> (candidates_list, current_value)
    "apply": <fn>,    # (sim, value) -> None
}
```

When `_on_click` focuses an element with cycler config, it pins a `__candidate__:<element>` row at row 0 of the param list. ←/→ on that row routes through `_cycle_candidate` (element-agnostic dispatch via cfg). `R` resets through `_reset_candidate`. Same dispatch for any future cyclable element — no per-element branching in the editor.

**Wired:**
- `dest` — candidates = unique dests in loaded route (walks `sim.stops` at click time); apply mutates `sim.stops[curr]["dest"]`.
- `prefix` — candidates = keys of `upper_lcd._PREFIX_FURIGANA` (canonical module constant enumerating the 3 state-machine prefix strings); apply mutates `sim.upper.prefix_text` (UpperDisplay's English mode translates at render time, so kanji cycle drives English render too).
- `station` — candidates = unique kanji station names from `sim.stops` (`stop["name"]`); apply jumps `sim.state.curr_stop` to the matching stop (same mechanism as `[`/`]` keybind). Side effect: dest + badge also reflect the new stop, since they're stop-derived too.

**Not wired (intentional):**
- `clock` — clock value is the current time, doesn't make sense to cycle.

**Rule — `build` reads from canonical source, never hardcoded.** Cycler candidates must derive from the project's existing source-of-truth for that element (route data, module constants, enum members). Hardcoding the list creates silent drift: if the source ever changes (new state added, value renamed), the cycler shows stale candidates with no error. If the canonical source is method-local or scattered, **promote it to a module-level constant first**, then read from there (precedent: `_PREFIX_FURIGANA` promoted out of `UpperDisplay.__init__` 2026-05-14 specifically to feed the prefix cycler).

---

## ~~Polyline-with-per-point-stroke pattern~~ (RETIRED 2026-05-30)

The 7-waypoint Catmull-Rom approach was Phase 1b/2's attempt to encode the Yamanote arc shape parametrically. **Retired** — N waypoints cannot faithfully encode the precision of a hand-drawn curve regardless of count or smoothing passes. The fundamental problem: any fixed set of control points is a lossy compression of what the user actually drew.

**Superseded by the mask PNG approach** (Tier 2, see above). Draw the shape in Photoshop at pixel precision → export white-on-transparent PNG → bake route color at `__init__` via `BLEND_RGBA_MULT`. Zero fidelity loss, color problem solved, no calibration loop.

The `_TUNEABLES_ARC` dict, `_build_catmull_rom_centerline`, and `_draw_arc` are dead code once the arc element migrates to mask PNG — remove when porting to master. The drag-handle machinery is NOT dead: it was generalized (multi-prefix waypoints, per-station panel filter) and now drives the `five_station` element's marker/group handles.

---

## Rule strength (future standard)

- **New tuneable additions:** must land in module-level `_TUNEABLES_*` dict + follow suffix convention. Hard rule going forward.
- **Existing inline `# fmt: off` tuneable blocks:** stay as-is. Convert lazily — only when next touched for tuning. No eager backfill sweep.
- **AST writeback iteration must stay reversed.** Multi-key-per-line schemas (Phase 1b polyline) only stay safe under reverse iteration. See `_dev_scripts/calibration_editor.py:_swap_dict_literal` + [critical_lessons.md § "AST source-edit must iterate values in reverse"](.claude/rules/critical_lessons.md).

---

## Two-tier tuning model (settled 2026-05-30)

**Tier 1 — simple elements** (positions, font sizes, offsets, rect bounds): `_TUNEABLES_*` + calibration editor sidebar. Universal convention; every new train model wires elements from day one.

**Tier 2 — complex geometry** (non-parametric curves, shaped bands): Photoshop → white-on-transparent mask PNG → `BLEND_RGBA_MULT` tint at runtime. Case-by-case. Route color applied at `__init__` via one bake pass — never per-frame copy.

**Yamanote arc resolution.** Catmull-Rom drag handles couldn't encode the precision of a Photoshop-drawn curve. Drag handles retired for the arc; mask PNG is the approach. The `"arc"` registry entry and Catmull-Rom band renderer are superseded; lower-LCD positional elements (station circle positions, minute number positions) get standard `_TUNEABLES_*` entries instead.

---

## Path to master — 5 pillars needed

Before the calibration editor concept merges to master as the new standard, all 5 must be in place:

1. **Code standard** — `conventions.md § UI code style` extended: every tuneable block in `_TUNEABLES_*` dict at module top, suffix convention followed, hit-test rect declared, draw methods read from dict each frame. This is what makes a display module editor-compatible.

2. **Skill** — `/calibration-editor` (or folded into a broader display-authoring skill): step-by-step for adding a new element (extract `# fmt: off` block → `_TUNEABLES_*` → register → smoke-test in `--edit`), and for wiring a brand-new train model from scratch.

3. **Editor on master** — `_dev_scripts/calibration_editor.py` + `preview_display.py --edit` / `--overlay` ported to master. Arc drag-handle machinery removed or parked. Upper-LCD 4 elements stay wired.

4. **Lint gate** — pre-commit or `lint_primitives.py` extension: flag magic numbers in draw methods that aren't in a `_TUNEABLES_*` dict. Without enforcement the convention decays silently on new model code.

5. **New-model skeleton** — minimal `_TUNEABLES_*` template for `upper_lcd.py` + `lower_lcd.py` so E233-0 (or any next model) starts editor-compatible rather than retroactively converting.

**Port strategy.** Branch is ~2 weeks behind master (harness reorg, EN display, update-check). Clean merge will conflict heavily — cherry-pick the calibration editor files individually onto master.

---

## Chosen route: E235-0 as graduation vehicle (Route A)

E235-0 is the model that proves and finalizes the calibration editor standard before it merges to master.

**Sequence:**
1. Complete E235-0 5-station view — mask PNG arc (Tier 2), station circle positions + minute number positions as `_TUNEABLES_*` entries (Tier 1)
2. Wire remaining E235-0 upper LCD elements (badge, route bar) to `_TUNEABLES_*` + register in `_REGISTRY`
3. All 5 pillars built (code standard in `conventions.md`, skill, editor port, lint gate, new-model skeleton)
4. Port editor to master — cherry-pick calibration editor files, remove dead arc Catmull-Rom machinery
5. E233-0 inherits a fully proven, already-exercised framework from day one

E235-0 remaining elements convert as they're touched (no eager sweep). E233-0 starts editor-native.

---

## Trigger to graduate

This doc deletes when all 5 pillars above are on master AND all E235-0 upper/lower LCD elements are wired via `_TUNEABLES_*` + suffix convention. Framework story lands in `conventions.md` + dedicated skill; this doc dissolves.

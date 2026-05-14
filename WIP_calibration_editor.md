# WIP — Calibration Editor (v1)

Direct-manipulation pixel tuning for pygame LCD elements. Sidebar overlay; click an element; nudge / cycle / reset params; Ctrl+S writes back to source. Lives in `_dev_scripts/calibration_editor.py`, wired via `preview_display.py --edit`.

**Motivation.** Claude bad at pixel-tuning closed loop (image-resolution + spatial-reasoning limits). Move iteration locus off claude: user nudges in-app, sees live re-render, persists values; claude consumes final state on commit.

**Lineage.** Pattern from Claude Design auto-generated adjustment sliders (Anthropic Labs, 2026-04-17). Product doesn't fit; pattern does.

---

## Status

v1 shipped 2026-05-13 PM on `feat/calibration-editor`. Upper-LCD framework expanded to 4 elements 2026-05-14 (dest / clock / prefix / station). Phase 1b shipped 2026-05-14 evening: lower-LCD broadcast via `arc` element (5-station view green band scaffold, shape-only — stations + pentagon + minute markers deferred to Phase 2). New mechanics in Phase 1b: polyline-with-per-point-stroke geometry, waypoint + stroke param-kinds, target-driven sidebar layout dispatch, AST-writeback corruption fixed. Graduation gate (b) partially proven by the arc; full sign-off still needs stations/pentagon/minutes.

---

## Architecture (locked)

| Decision | Pick |
|---|---|
| Source of truth | Module-level `_TUNEABLES_*` dicts in target `.py`; draw methods read from dict |
| Editor surface | In-pygame sidebar overlay (Lane A) — single window |
| Selection | Click LCD element → sidebar shows that element's dict params (α-first) |
| Edit mode | Frozen frame. Sim paused, audio stops |
| Persistence | Scratch JSON auto-save per change (`_calibration_session.json`, gitignored) + Ctrl+S writeback to source (type-guarded value-swap, no AST rewrite) |
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
4. **Mouse-drag handles (Phase 2 editor upgrade).** Keyboard-nudge is insufficient for multi-DOF visual targets — the 2026-05-14 arc Phase 1b session surfaced this: user could not reconcile 4 waypoints + 4 per-point strokes against an IRL ref by nudging one param at a time. Real fix = visible draggable dots on the LCD canvas. Click-and-drag a waypoint moves it, the band reshapes in real time, sidebar values update live. General-purpose — applies retroactively to any element with `_x`/`_y` pairs (dest box anchors, station rect corners, future polyline elements). Out of scope until enough Phase 1b/2 tuning friction motivates the lift.

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

## Polyline-with-per-point-stroke pattern (Phase 1b, lower-LCD)

For curved bands whose shape isn't a clean math primitive (single arc / ellipse / known equation), model the band as a polyline through N waypoints, with per-waypoint stroke.

```python
_TUNEABLES_ARC = {
    "arc_p0_x": 540, "arc_p0_y": 441, "arc_p0_stroke": 160,   # current-stop end
    "arc_p1_x": 461, "arc_p1_y": 310, "arc_p1_stroke": 120,
    "arc_p2_x": 272, "arc_p2_y": 191, "arc_p2_stroke":  85,
    "arc_p3_x":   9, "arc_p3_y":  92, "arc_p3_stroke":  55,   # furthest-stop end
    "arc_color": (116, 193, 30),
}
```

Renderer walks `_pN_x/_y/_stroke` triples in numeric order. Outer + inner band edges = waypoint ± local-normal × stroke/2 at each point. Segments between adjacent waypoints linearly interpolate both position (straight line) and thickness (trapezoid). For smoother shapes: add more waypoints. Local normal at junctions = averaged-normal bisector (simple; tight bends may pinch — softer angles softer).

**When to use vs single-primitive arc.** First instinct is the cleanest math (circle: center + radius + start/end angle = 5 numbers). Reach for polyline when:
- IRL artifact isn't a true single-radius arc (Yamanote 5-station band: shape OK but stroke varies along length — uniform stroke can't match)
- Variable thickness along the curve (per-segment width)
- Multi-radius / piecewise shapes
- Calibrating to a photo where the curve doesn't admit a clean parameterization

**Model the artifact's actual DOFs, not the cleanest math primitive.** Trying to tune a single-radius arc to an IRL band that has variable thickness wastes hours and can't converge. Polyline + per-point stroke matches the DOFs directly. The math primitive is for *rendering speed*, not the *user's mental model*.

**Phase 2 editor implication.** Multi-waypoint shapes are exactly where keyboard-nudge falls down (open thread #4): user can't reconcile N positions + N strokes against a visual target one keystroke at a time. Drag handles needed for serious tuning.

---

## Rule strength (future standard)

- **New tuneable additions:** must land in module-level `_TUNEABLES_*` dict + follow suffix convention. Hard rule going forward.
- **Existing inline `# fmt: off` tuneable blocks:** stay as-is. Convert lazily — only when next touched for tuning. No eager backfill sweep.
- **AST writeback iteration must stay reversed.** Multi-key-per-line schemas (Phase 1b polyline) only stay safe under reverse iteration. See `_dev_scripts/calibration_editor.py:_swap_dict_literal` + [critical_lessons.md § "AST source-edit must iterate values in reverse"](.claude/rules/critical_lessons.md).

---

## Trigger to graduate

This doc deletes when (a) all upper_lcd elements are customizable through `_TUNEABLES_*` + suffix convention AND (b) the pattern is broadcast-able to lower LCD without architectural change. At that point the framework story lands in `conventions.md` / a dedicated skill, the `conventions.md § UI code style` pointer goes in, and this doc dissolves.

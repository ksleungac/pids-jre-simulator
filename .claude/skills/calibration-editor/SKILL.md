---
name: calibration-editor
description: Direct-manipulation pixel-tuning for E235 LCD elements — how to launch the in-app editor, add a new tuneable element (extract magic numbers → module-level `_TUNEABLES_*` dict → register → smoke-test), and wire a brand-new train model. Use when adding/tuning LCD display elements or forking a new train model's display.
---

# Calibration Editor

Direct-manipulation pixel tuning for pygame LCD elements. Click an element on the LCD, nudge/drag its params, `Ctrl+S` writes the values back to source. The iteration locus is the user (visual judge); Claude consumes the final values on commit.

Editor code: `_dev_scripts/calibration_editor.py` (dev-only, never imported by production). Wired via `preview_display.py --edit`.

## When to use

- Tuning an existing element's position/size/colors against an IRL reference.
- **Making a new element editor-tunable** (the add-an-element runbook below).
- **Wiring a brand-new train model** — fork `e235_0` (the golden-template source) so its elements come editor-ready.

## Launch

```bash
uv run preview_display.py --edit --route yamanote --model e235_0
uv run preview_display.py --edit --overlay _references/lcd/<ref>.png   # IRL overlay (O toggles; Alt+drag pan; =/- zoom)
```

The window doubles: left half = the tuning target, right half = the param panel. Click an element → its `_TUNEABLES_*` rows appear (α-first). Edit mode freezes the sim + stops audio.

### Keybindings

| Key | Action |
|-----|--------|
| Click element | Focus it (panel shows its params) |
| `↑` / `↓` | Select row (key-repeat) |
| `←` / `→` | Nudge value (`Shift+` = ±10); on a cycler row, cycle candidate |
| drag handle | Move an `_x`/`_y` waypoint pair (records grab offset — no snap) |
| `R` | Reset focused row to source value |
| `L` | Sync sim display mode to the focused dict's family (KANJI/FURIGANA/ENGLISH) |
| `M` | Cycle display mode |
| `V` | Cycle the active lower-LCD view (see below) |
| `[` / `]` | Prev / next stop |
| `H` | Toggle drag handles (hidden = inert to grabs) |
| `K` | Lock / unlock focused element (drag-inert; persists to `_editor_locks.json`) |
| `O` | Toggle reference overlay |
| `Ctrl+S` | Write edited values back to source (only keys actually changed) |
| `ESC` | Quit |

## Lower-LCD views — every lower element is view-scoped

The lower LCD shows one of several views in the same screen region, so elements in different views have overlapping hit-test rects: the route bar (`full_route`, full-route view) and the 5-station markers (`five_station`, eight view) both claim the whole lower area. A static rect cannot tell them apart — whichever registers first swallows every click, which is why no full-route element could be registered at all until this landed (#17, 2026-08-22).

So **every `target: "lower"` entry declares the view it lives in**:

```python
"full_route": {
    "rect_module": "displays.train_models.e235_0.lower_lcd",
    "rect_attr": "FULL_ROUTE_RECT",
    "target": "lower",
    "view": "full",              # "full" | "eight" | "transfer"
    "dicts": [(..., "_TUNEABLES_FULL_ROUTE")],
},
```

The editor keeps one active lower view. Hit-testing and handle drawing only consider elements whose view matches it; upper elements carry no `view` and stay reachable throughout. `V` cycles, `--lower-view` seeds the starting view, and `preview_display._run_edit_loop` re-pins the sim's lower slot from it each frame so the view you cycle to is the one that draws. The reachable view list is derived from `_REGISTRY`, not written down — register an element in a new view and that view becomes cycleable with no second edit.

**Focus is dropped when its view leaves the screen**, so the sidebar can never nudge an element that isn't being drawn.

### If positions are precomputed, add a resync

Most elements read their dict per frame, so a nudge lands for free. An element whose dict feeds a **precomputed layout** (the route bar computes every station position at `__init__` from the track geometry) will move its own drawing and leave everything positioned off it behind. Compare a signature of the dict at the top of the draw and rebuild when it changed — `CircularFullRouteDisplay._resync_tuneables` is the pattern, and it costs production one tuple compare per frame because production never mutates the dict.

## Param-suffix convention

Key naming drives **both** semantics AND the editor's free visualization. The editor infers the param-kind from the suffix:

| Suffix | Kind | Indicator |
|---|---|---|
| `_x` | screen x | horizontal ruler 0 → val (+ dim ruler for paired `_w`) |
| `_y` | screen y | vertical ruler 0 → val (+ dim ruler for paired `_h`) |
| `_w`, `_width` | width (paired with `_x`) | ruler anchor_x → anchor_x + val |
| `_h`, `_height` | height (paired with `_y`) | ruler anchor_y → anchor_y + val |
| `_color` | RGB tuple | 16px swatch in the row |
| `_<edge>_offset` / `_<edge>_margin` (`<edge>` ∈ left/right/top/bottom) | edge-anchored offset | ruler at `rect.<edge> ± val` |
| anything else (`_size`, `_pad`, `_power`, `_dur`, `_gap`, …) | recognized scalar | no indicator — nudge still works |

Pair detection for `_w`/`_h`: same-stem `_x`/`_y` in the same dict. Dict-name suffix `_KANJI`/`_FURIGANA` → japanese family, `_ENGLISH` → english family (drives `L`).

## Add-an-element runbook

Worked example: the **badge** + **PA-hint** elements (`e235_0/upper_lcd.py`, 2026-06-23).

1. **Extract the magic numbers** into a module-level dict at the top of the LCD module. For a **region rect** (position + size of a clip rect), use a `_TUNEABLES_<ELEMENT>_RECT` dict with `<element>_x/_y/_w/_h` keys, then derive the `pygame.Rect` from it:
   ```python
   _TUNEABLES_BADGE_RECT = {"badge_x": 222, "badge_y": 50, "badge_w": 68, "badge_h": 80}
   BADGE_RECT = pygame.Rect(_TUNEABLES_BADGE_RECT["badge_x"], _TUNEABLES_BADGE_RECT["badge_y"],
                            _TUNEABLES_BADGE_RECT["badge_w"], _TUNEABLES_BADGE_RECT["badge_h"])
   ```
   For an element's **internal layout** (text offsets, font sizes within the rect), use a sibling `_TUNEABLES_<ELEMENT>[_MODE]` dict (append `_MODE` only when font/sizes diverge across modes).
   - **Values must be literals** (`ast.Constant`) — the editor's AST writeback only swaps int/float/numeric-tuple/str. Store `222`, not `S_WIDTH - 508`. Re-tunable per model anyway.
   - **Terse**: only include what's actually tuneable. If text is anchored to `RECT.left` by design, don't add a `text_x` knob.

2. **Sync the rect from the dict each frame** in the draw method so nudges land live, and read the draw's position/size from it:
   ```python
   tr = _TUNEABLES_BADGE_RECT
   BADGE_RECT.update(tr["badge_x"], tr["badge_y"], tr["badge_w"], tr["badge_h"])
   badge_x, badge_w = BADGE_RECT.x, BADGE_RECT.width
   ```
   `pygame.Rect` is mutable in place, so the editor's `getattr(mod, "BADGE_RECT")` reads the live value.

3. **Register in `_dev_scripts/calibration_editor.py` `_REGISTRY`:**
   ```python
   "badge": {
       "model": "e235_0",          # which train model this rect's coordinates mean
       "rect_module": "displays.train_models.e235_0.upper_lcd",
       "rect_attr": "BADGE_RECT",
       "target": "upper",          # "upper" | "lower" — drives the left-column render
       "dicts": [("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_BADGE_RECT")],
   },
   ```
   Draggable `_x`/`_y` waypoints + per-station filtering use the optional `waypoints` / `draw_state` keys (see `five_station` for the full shape). A `target: "lower"` entry **must** also declare `view` — see § "Lower-LCD views" below.

4. **Smoke-test:** `uv run preview_display.py --edit --route yamanote --model e235_0`, click the element, confirm its rows appear + nudging moves it. A faithful conversion renders identically before any nudge — verify with a screenshot.

## Models — the registry holds several, and every entry says which

An entry's `rect_attr` is in **its own model's canvas coordinates**, so an entry from another model hit-tests a rectangle that means nothing on the screen you are looking at. Every entry therefore carries `model`, and the editor filters on it (`set_active_model`, bound by `preview_display._run_edit_loop` from the loaded `sim._train_model.key`).

Two things are derived from that key rather than written down, for the same reason the view list is: `editable_models()` — which models `--edit` accepts — and `_lower_views()` — which views `V` cycles, since a view only another model registers in is not cycleable here. Registering the first element of a new model is enough to make `--edit --model <new>` work; there is no second place to update.

The edit window is sized from the loaded model's `TrainModel` record (`s_width` / `s_height` / `upper_height`), never from a fixed import — models genuinely differ (e235_0 is 730 × 420, e233_0 is 640 × 480), and a fixed import lays the panel out for the wrong one *silently*.

**Convert lazily** — only when an element is next touched for tuning; no eager backfill sweep. The method-local `# fmt: off` block is the *predecessor* form; a module-level `_TUNEABLES_*` dict is the editor-compatible standard (per `conventions.md § UI code style`).

## Wire-a-new-model runbook

**A re-skin** — a sub-series of a model already wired — is a fork of `e235_0` (per `conventions.md § "Forking a sibling-model renderer"`) and inherits editor-readiness. Copy the per-model module keeping its `_TUNEABLES_*` dicts + region rects, then **add** `_REGISTRY` entries pointing at the new package with the new `model` key. Add, never re-point: re-pointing the existing entries takes the model they were serving off the editor.

**A genuinely new model** — different canvas, no sibling to re-skin — arrives element by element, and its entries appear as its elements do. E233-0 is the first: 640 × 480 against E235's 730 × 420, so nothing about its geometry inherits, and its registry grew one entry (`train_type`) at the moment that element was built. That is the normal shape for a spec-first build (`docs/DISPLAY.md` § "Specifying a new display"), where the editor is step 6's tuning loop rather than something wired up front.

## Two-tier tuning model

- **Tier 1 — simple elements** (positions, sizes, offsets, rect bounds): `_TUNEABLES_*` + this editor. Default for every element.
- **Tier 2 — complex non-parametric geometry** (hand-drawn curves, shaped bands): Photoshop → white-on-transparent mask PNG → `BLEND_RGBA_MULT` route-color tint baked once at `__init__`. Case-by-case; never per-frame. (Precedent: the 5-station green band `data/e235_0/five_station_band.png`.)

## AST writeback — reverse iteration is mandatory

`Ctrl+S` walks the `<dict_name> = {...}` literal and replaces each edited key's value via `ast.Constant` end-col math. **Iteration is reversed** so rightmost edits land first — when a multi-key-per-line schema (waypoints) shifts a value's repr length, earlier-column offsets stay valid. Forward iteration corrupts source the moment any repr length changes. See `_swap_dict_literal` in `calibration_editor.py`. Only `_edited_keys` are written; every other key's source text stays byte-for-byte.

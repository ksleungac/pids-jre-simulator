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
| `[` / `]` | Prev / next stop |
| `H` | Toggle drag handles (hidden = inert to grabs) |
| `K` | Lock / unlock focused element (drag-inert; persists to `_editor_locks.json`) |
| `O` | Toggle reference overlay |
| `Ctrl+S` | Write edited values back to source (only keys actually changed) |
| `ESC` | Quit |

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
       "rect_module": "displays.train_models.e235_0.upper_lcd",
       "rect_attr": "BADGE_RECT",
       "target": "upper",          # "upper" | "lower" — drives the left-column render
       "dicts": [("displays.train_models.e235_0.upper_lcd", "_TUNEABLES_BADGE_RECT")],
   },
   ```
   Draggable `_x`/`_y` waypoints + per-station filtering use the optional `waypoints` / `draw_state` keys (see `five_station` for the full shape).

4. **Smoke-test:** `uv run preview_display.py --edit --route yamanote --model e235_0`, click the element, confirm its rows appear + nudging moves it. A faithful conversion renders identically before any nudge — verify with a screenshot.

**Convert lazily** — only when an element is next touched for tuning; no eager backfill sweep. The method-local `# fmt: off` block is the *predecessor* form; a module-level `_TUNEABLES_*` dict is the editor-compatible standard (per `conventions.md § UI code style`).

## Wire-a-new-model runbook

New models are **forks** of `e235_0` (per `conventions.md § "Forking a sibling-model renderer"`), not greenfield. Whatever `e235_0` has wired, the fork inherits editor-ready. So: copy the per-model module, keep its `_TUNEABLES_*` dicts + region rects, re-point the `_REGISTRY` entries' `rect_module`/`dicts` paths to the new model package, and tune against the new model's IRL reference. No abstract template.

## Two-tier tuning model

- **Tier 1 — simple elements** (positions, sizes, offsets, rect bounds): `_TUNEABLES_*` + this editor. Default for every element.
- **Tier 2 — complex non-parametric geometry** (hand-drawn curves, shaped bands): Photoshop → white-on-transparent mask PNG → `BLEND_RGBA_MULT` route-color tint baked once at `__init__`. Case-by-case; never per-frame. (Precedent: the 5-station green band `data/e235_0/five_station_band.png`.)

## AST writeback — reverse iteration is mandatory

`Ctrl+S` walks the `<dict_name> = {...}` literal and replaces each edited key's value via `ast.Constant` end-col math. **Iteration is reversed** so rightmost edits land first — when a multi-key-per-line schema (waypoints) shifts a value's repr length, earlier-column offsets stay valid. Forward iteration corrupts source the moment any repr length changes. See `_swap_dict_literal` in `calibration_editor.py`. Only `_edited_keys` are written; every other key's source text stays byte-for-byte.

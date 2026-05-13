# WIP — Calibration Editor (v1)

Direct-manipulation pixel tuning for pygame LCD elements. Sidebar overlay; click an element; nudge / cycle / reset params; Ctrl+S writes back to source. Lives in `_dev_scripts/calibration_editor.py`, wired via `preview_display.py --edit`.

**Motivation.** Claude bad at pixel-tuning closed loop (image-resolution + spatial-reasoning limits). Move iteration locus off claude: user nudges in-app, sees live re-render, persists values; claude consumes final state on commit.

**Lineage.** Pattern from Claude Design auto-generated adjustment sliders (Anthropic Labs, 2026-04-17). Product doesn't fit; pattern does.

---

## Status

v1 shipped 2026-05-13 PM on `feat/calibration-editor`. In active use against E235-0 dest. Not yet committed. Trigger to graduate: ships AND proves on a second element.

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
| anything else (`_offset` without edge, `_size`, `_pad`, `_margin` without edge) | recognized but no indicator | tunable still works; no visual feedback — gentle convention pressure |

Pair detection for `_w` / `_h`: same-stem `_x` / `_y` in same dict. Fallback strips `_max` (e.g. `two_line_max_w` → `two_line_x`).

Dict-name suffix drives mode-follow-focus: `_KANJI` / `_FURIGANA` → japanese family; `_ENGLISH` → english family. Press `L` to sync sim mode to focused dict when needed.

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

**Writeback.** AST walks the dict literal `<dict_name> = {...}` at module level, replaces each key's value-side via `ast.Constant` end-col-offset math. Type-guarded (int / float / tuple-of-numeric / str). Multi-line values skipped with warning. Tuple inside dict re-emitted via `repr()`.

---

## Open threads (graduate when ≥1 lands)

1. **More elements** registered for tuning (badge / station / clock / route bar) — mechanical pattern: extract `# fmt: off` block → `_TUNEABLES_*` dict, declare hit-test rect, add `_REGISTRY` entry.
2. **2D point drag handles** — drag on canvas to set `_x` + `_y` of a focused row pair instead of nudging.
3. **Animation play toggle** — for chevron `sweep_duration` etc; need motion to tune.
4. **Cross-route candidate sampling** for the dest cycler — current = unique dests in loaded route only (Yamanote = 6 compounds). Walk every `audio/*/route.json` + `_mock` for short / long / katakana variety.
5. **Generalize candidate-cycler** beyond dest — declare per-element `build_candidates` + `apply` hooks in `_REGISTRY` rather than hardcoded `_build_dest_candidates`.

---

## Trigger to graduate

This doc deletes when v1 (a) ships AND proves on a second element, OR (b) fails proof and the idea is dropped. The current v1 is in the "ships, prove on 2nd element" phase. Once a non-dest element rides the same registry + suffix convention without architectural change, the framework story lands in `conventions.md` / a dedicated skill, and this doc dissolves.

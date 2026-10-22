---
paths:
  - "data/**"
  - "audio/**/*.json"
  - "route_loader.py"
  - "validate_data.py"
  - "docs/DATA_FORMAT.md"
---

# Data rules: route.json, catalogues, the loader

Path-scoped: Claude Code loads this file when a file matching `paths:` is read or edited, not at session start. These rules moved here from `conventions.md`, `principles.md` and `critical_lessons.md` on 2026-10-22, to keep the always-loaded corpus under the combined-size limit. Same rules, narrower trigger.

## Conventions

### Data layout

- **Centralized translations**: single `data/translations.json` for all lines, not per-line files.
- **`route.json` is authored content — a UI bug gets fixed in the code, not by editing the data.** It is touchable, but it is not the reach-for when a screen behaves wrong. 2026-07-27 (#59): the TIMS picker offered Yamanote's 大崎 twice, and the two entries turned out to be non-redundant (`stops[0]` has `pa: []` as the loop origin, `stops[29]` carries `pa: ["30"]`, the closing まもなく) — deleting the trailing stop would have dropped that announcement and moved the terminus. The defect was the picker offering the terminus as a start at all. User: *"you should never touch route.json … it breaks our data"*, then *"you can touch it however usually not touched when on these kind of things."*
- **A cross-file key that differs by an INVISIBLE character fails silently — verify the join, don't eyeball it.** `data/stations.json` is keyed by station name and joined against `route.json`'s `stops[].name`; a key that does not match resolves to `{}`, which renders as "this station has no transfers" and reports nothing. 2026-08-29: 市ヶ谷 was authored `市ケ谷` — large katakana ケ (U+30B1) where the route data uses the small ヶ (U+30F6). Indistinguishable at any font size, and the author caught it by eye on a render (*"ichigaya should have transfers"*). Same trap waits in 阿佐ケ谷 / 霞ケ関 / 茅ケ崎 and every ヶ station, and in any `･`/`・`, `ー`/`—` pair. After authoring keys for a join, list the ones that MATCH mechanically rather than reading them: the miss is invisible and only the match count is trustworthy.
- **Before calling a data value wrong, read that field's `docs/DATA_FORMAT.md` entry.** A field with a documented grammar has values that look like typos and are not. 2026-08-20: `"さいたま 新都心"` was flagged as a stray space — twice — off a `' '.join(names)` readout, when `DATA_FORMAT` documents a space in `name` as a line-break instruction and uses that exact string as its example. The tell is that the evidence was a rendering of my own tool output rather than the field's definition. Author: *"yes, it is, and you should read data format before acting like that."* Cheap check, and it also stops the second flag: an unanswered first one is not a reason to re-raise.

### Tooling

- **Data-field additions must update `validate_data.py` in the same change.** A new `route.json` / data-catalog field (documented in `docs/DATA_FORMAT.md`) with no validator check makes the validator silently PASS on it — drift is invisible until a manual audit. 2026-07-15 pre-release sweep found `model` / `line_code` / color-shape / the whole `translations_app.json` (locale + `{placeholder}` parity) unchecked after the TIMS + E235-0 cycle. Full-scan = the shipped-data gate (skips `_*/`); `--route` validates any path on demand.

## Principles

#### Pragmatic over perfect
Don't build elaborate schemas upfront. Ship route data with whatever metadata surfaces naturally; add structure when pain forces it.

**How to apply:** Default to filename-as-store and minimal JSON. Add metadata files only when filename can't carry enough info.

#### Filename-as-store
Encode 1:1 metadata in the filename (e.g., STA recordings carry station + platform + song id in basename).

**How to apply:** Add a metadata file only when the same fact needs lookup from multiple basenames.

#### Variants are out of scope (for now)
Pitch shifts, station-specific arrangements — explicitly deferred. Each recording gets its own slug; merging into "the same song with variants" is a future problem.

#### JSON is input grammar; runtime is the closure
JSON files = irreducible authored content. Runtime structure = what the loader computes at load time with all derived fields filled. Renderers consume the closure via direct key access, not raw JSON with per-call fallback.

**Why:** Per-call fallback logic breaks across overrides. Examples:
- (2026-05-06) Yamanote dest-switching: renderers did `stop.get("dest") or self.route_dest` per draw, breaking sticky-override semantics.

**How to apply:**
- Loader-time computations live in `route_loader.finalize_route`. Renderers do direct key access.
- `stop.get("X") or default` in a renderer is a smell — promote the fallback into the loader.

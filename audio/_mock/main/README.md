# Mock route — `audio/_mock/main/`

Curated 11-stop fictional line. Default route when running `preview_display.py` without `--route`. The `_` prefix on `_mock/` (and `_archive/`) marks the folder as preserved-but-not-shipped — release builds skip it.

Real `route.json`, not in-code constants. Loads via the same path as real routes. Edit freely to experiment.

## Why each stop is here

Every reference station is integrated as a test station — each one does double duty (logic test + visual font reference for `compare_fonts.py` / `compare_grid.py`).

| Idx | Station | Role |
|-----|---------|------|
| 0 | 東京 | Tokyo font ref + multi-PA (`pa: ["1", "2"]`) + station-code badge (3-letter `TYO` resolved at render time via `data/stations.json` lookup, not stored in route.json) |
| 1 | 新日本橋 | Shin-Nihombashi font ref + 1-skip source (next stopping station is index 3, with passing index 2 in between) |
| 2 | 秋葉原 | Passing station (`pa: []`) |
| 3 | 錦糸町 | Kinshichō font ref + 1-skip target with single PA — historically reproduced the single-PA skip-flush bug |
| 4 | 上野 | 3-PA stop (`pa: ["1", "2", "3"]`) |
| 5 | 日暮里 | Passing station |
| 6 | 西日暮里 | Passing station |
| 7 | 船橋 | Funabashi font ref + 2-skip multi-PA target (passing 5, 6 skip cleanly into multi-PA — happy path) |
| 8 | 津田沼 | Tsudanuma font ref + single-PA |
| 9 | 高輪ゲートウェイ | Long-name wrap (`高輪ゲートウェイ` is the longest commonly-cited station name; tests truncation/two-line layout) |
| 10 | 品川 | Final stop |

Compound destination at the route level: `dest: "品川・高輪ゲートウェイ"` — exercises the `&`-style two-line layout on the upper LCD's destination panel.

## Schema notes (gotchas vs the real data)

- `code_3` (3-letter Roman badge like `TYO`, `AKB`) is **not** a `route.json` field — it lives in `data/stations.json` keyed by station name. The mock route just provides the station name; whether a 3-letter badge renders depends on whether `data/stations.json` has a `code_3` entry for that name. See [DATA_FORMAT.md § "code_3 field"](../../../DATA_FORMAT.md).
- `sta_code` (per-stop, e.g. `JO19`) is route-local and lives in `route.json`. The mock uses real-looking `sta_code` values for visual realism but they don't match any real route layout.

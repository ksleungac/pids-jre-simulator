# PA Simulator - Data Format Specification

## Overview

This document defines the JSON data formats used by the PA Simulator for route configurations and station databases.

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** schema reference, gotchas, invariants — implementation specifics looked up when editing the relevant submodule.
>
> **Refuses:**
> - History notes / change logs (`### 2026-03-14`, "pre-X behavior", "Key Changes from legacy …") — `git log` has this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future sections ("When X is implemented, …") — defer until needed
> - Design-discussion rationale (multi-paragraph framings of *why* a model exists) — the rule lives here; the rationale lives in `memory/YYYY-MM-DD.md`
> - Facts already in [CLAUDE.md](CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](.claude/rules/principles.md).

---

## File Structure

```
data/
├── translations.json        # Central translation database (furigana, english)
├── train_types.json         # Train type English translations (with optional english_short)
├── lines.json               # Rail line catalog (badges, colors, display names) for transfer entries
├── line_icons/              # PNG assets for branded line logos (Shinkansen, etc.)
└── stations.json            # Station metadata (3-letter codes, transfers; more fields over time)
audio/[line]/[diagram]/route.json   # diagram folder may be omitted for single-diagram lines
```

---

## translations.json Format (Central Translation Database)

**Location:** `data/translations.json` (project root)

### Purpose

Centralized translation lookup for **any Japanese text** used in the simulator:
- Station names (for furigana/english cycling display)
- UI text (prefixes, suffixes)
- Any other Japanese text needing translation

### Structure

```json
{
    "東京": {
        "furigana": "とうきょう",
        "english": "Tokyo"
    },
    "新宿": {
        "furigana": "しんじゅく",
        "english": "Shinjuku"
    },
    "次は": {
        "furigana": "つぎは",
        "english": "Next"
    },
    "ゆき": {
        "furigana": "ゆき",
        "english": "Bound"
    }
}
```

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Japanese text]` | Any Japanese text needing translation | `東京`, `新宿`, `次は` |

**Important:** Keys are the **raw Japanese text** (kanji/kana), not station codes. App-side lookup is direct (`translations[name]`); no fallback layer.

### Value Fields

| Field | Description |
|-------|-------------|
| `furigana` | Hiragana reading for the text |
| `english` | English translation/romanization |

### Compound Destinations (e.g., Yamanote Line)

For routes that display multiple destinations (like 品川・東京), use `&` as the separator. Whether to insert `\n` after `&` is case-by-case — match IRL: short compound dests fit on a single line and omit `\n`; longer ones break onto two lines.

```json
{
    "品川・東京": {
        "english": "Shinagawa&\nTokyo"
    },
    "東京・上野": {
        "english": "Tōkyō&Ueno"
    }
}
```

**Format:** `"StationA&StationB"` (single-line) or `"StationA&\nStationB"` (multi-line). No space around `&` in either case.

**Note:** Compound destinations typically don't need `furigana` field as they are used for English display only (not for furigana cycling on the upper LCD).

### English Translation Convention (Hepburn Romanization)

English translations use **modified Hepburn romanization with macrons** to indicate long vowels. The convention itself (preloaded mental model — Tōkyō, Chūō, why Etchūjima not Ecchūjima) is in [CLAUDE.md](CLAUDE.md) "Mental Model → IRL display conventions". This section is the JSON-encoding side.

| Long Vowel | Source | Example |
|------------|--------|---------|
| **ō** | おう, おお | 東京 → T**ō**ky**ō**, 大宮 → **Ō**miya |
| **ū** | う, うう, うう | 越中島 → Etch**ū**jima |

**Examples:**
```json
{
    "東京": { "english": "Tōkyō" },
    "大宮": { "english": "Ōmiya" },
    "大久保": { "english": "Ōkubō" },
    "十条": { "english": "Jūjō" },
    "越中島": { "english": "Etchūjima" },
    "港南台": { "english": "Kōnandai" }
}
```

### Stop-Level Destination Override

Stops can carry their own `dest` field to override the route-level value:

```json
{
    "name": "田町",
    "pa": ["3"],
    "dest": "東京・上野",
    "time": 3
}
```

**Sticky semantic.** An override sets the displayed dest from that stop onward, until the next override. Route-level `dest` is the value before any override. Used by circular routes (Yamanote) where the displayed dest cycles as the train traverses the loop.

**Loader-time closure.** `route_loader.finalize_route` walks the stops list once at load time and fills `dest` on every stop with its effective value. After load, every stop has a `dest` field; renderers read it directly with no fallback logic. JSON is input grammar — only the irreducible overrides are authored; the runtime structure is the closure.

**Yamanote example:** route-level `dest = 品川・東京`; overrides at 田町 / 神田 / 鶯谷 / 目白 / 代々木 / 恵比寿 cycle through the next-2-major-terminals window. Display semantics (kanji always; English uses translation lookup) live in [DISPLAY.md § Destination Behavior](DISPLAY.md).

---

## train_types.json Format (Train Type Translations)

**Location:** `data/train_types.json` (project root)

### Purpose

English translations for train type names (列車種別). Unlike stations, train types do **not** have furigana since they are only displayed in kanji or English.

### Structure

```json
{
    "快速": {
        "english": "Rapid"
    },
    "中央特快": {
        "english": "Chūō Special Rapid",
        "english_short": "Chūō Sp. Rapid"
    },
    "普通": {
        "english": "Local"
    },
    "内回り": {
        "english": "Inner Loop"
    },
    "外回り": {
        "english": "Outer Loop"
    }
}
```

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Japanese train type]` | Any train type name | `快速`, `普通`, `内回り`, `外回り` |

### Value Fields

| Field | Description | Required |
|-------|-------------|----------|
| `english` | Full English translation | Yes |
| `english_short` | Abbreviated version for narrow display boxes | No |

### english_short Fallback

For narrow display boxes (e.g. E235-1000 type box, 150 px), resolution order is `english_short` → `english` → kanji. `中央特快` is the only current consumer (`Chūō Sp. Rapid` fits where `Chūō Special Rapid` overflows).

English translations follow the same Hepburn-with-macrons convention as station names — see translations.json section above.

---

## lines.json Format (Rail Line Catalog)

**Location:** `data/lines.json` (project root)

### Purpose

Catalog of rail lines referenced as transfer entries on station displays. Stores brand metadata (line code, icon asset, display name) once per line, referenced by slug from `stations.json` `transfers` arrays.

### Structure

```json
{
    "yamanote": {"badges": [{"code": "JY", "icon": "JY"}], "name_ja": "山手線", "name_en": "Yamanote Line", "category": "jr_east"},
    "keihin_tohoku": {
        "badges": [{"code": "JK", "icon": "JK"}],
        "name_ja": "京浜東北線",
        "name_en": "Keihin-Tōhoku Line",
        "category": "jr_east",
        "variants": {
            "oimachi_kamata": {
                "name_ja": "京浜東北線(大井町・蒲田方面)",
                "name_en": "Keihin-Tōhoku Line (for Ōimachi/Kamata)"
            }
        }
    },
    "ueno_tokyo": {
        "badges": [{"code": "JT", "icon": "JT"}, {"code": "JU", "icon": "JU"}],
        "name_ja": "上野東京ライン",
        "name_en": "Ueno-Tōkyō Line",
        "category": "jr_east",
        "variants": {
            "tokaido": {"badges": [{"code": "JT", "icon": "JT"}]},
            "tohoku":  {"badges": [{"code": "JU", "icon": "JU"}]}
        }
    },
    "yokosuka_sobu": {
        "badges": [{"code": "JO", "icon": "JO"}],
        "category": "jr_east",
        "variants": {
            "yokosuka": {"name_ja": "横須賀線",   "name_en": "Yokosuka Line"},
            "sobu":     {"name_ja": "総武線快速", "name_en": "Sōbu Rapid Line"}
        }
    }
}
```

### Fields

| Field | Description |
|-------|-------------|
| `badges` | Optional. Array of badge objects rendered left-to-right before the line name. Each badge carries `icon` (required — slug naming a PNG asset under `data/line_icons/<slug>.png`), optionally `code` (1-2 letter line code, e.g. `JY` — used by the runtime transfer-filter rule to match against the active route's line code), and optionally `color` (`[r, g, b]` — line-brand color used by the per-train-model badge rendering policy that swaps icon for color-square on certain trains; renderer ignores when policy not active, see [DISPLAY.md § Color-square policy](DISPLAY.md)). One badge for typical JR East lines; multiple for through-running compound services (e.g. UT base = JT + JU); `icon`-only without `code` for Shinkansen / non-JR operators. **If absent** → universal fallback icon (`_universal.png`). |
| `name_ja` | Japanese display name. Required at base unless the slug is **only** referenced via variants (e.g. `yokosuka_sobu` — base never used directly). |
| `name_en` | English display name (Hepburn-with-macrons). Same required-unless-variant-only rule as `name_ja`. |
| `category` | One of `jr_east` / `shinkansen` / `non_jr`. Drives row-grouping. |
| `variants` | Optional. Map of `<variant_name> → {field overrides}`. Each variant overrides any subset of base fields; missing fields inherit from base. Used for zone-specific badge subsets (UT JT-only south, JU-only north), through-service display variants (Yokosuka vs Sōbu Rapid label on same JO physical line), and direction-qualified line names (Keihin-Tōhoku with `(大井町・蒲田方面)` suffix). Variants are referenced from `stations.json` via dot notation: `slug.variant_name`. |

### Reference resolution (variant + scale)

`stations.json` `transfers` entries can be plain `"slug"`, dotted `"slug.variant"`, or carry a trailing `.scale(N)` modifier (e.g. `"ueno_tokyo.tokaido.scale(0.75)"`). Resolver (`preview_transfers.py:resolve_entry`):

1. Strip optional trailing `.scale(N)` suffix; remember N.
2. Split remainder on first `.` → `(base_slug, variant_name)`.
3. **Dot-notation is one level only** for variants. `slug.variant.subvariant` raises ValueError.
4. **Fail loud** on missing base or unknown variant — never silently fall back. (Per `critical_lessons.md` runtime-required-artifacts rule.)
5. Merge: variant fields override base; missing fields inherit. The `variants` key is stripped from the resolved output.
6. If `.scale(N)` was present, override `name_ja_compress` with N; otherwise it defaults to 1.0 (natural width).

**When to apply `.scale(N)`** — only at busy stations whose visible entry count after view-filtering is high enough to crowd a row. Sparse stations have horizontal budget to render at natural width; over-applying compression kills legibility for no benefit. Curate per-station against the IRL reference photo.

### Notes

- **Slug keys are arbitrary IDs** — keep them stable so `stations.json` references don't churn.
- **Slug names don't carry codes** — `yokosuka_sobu` not `jo_through`. Codes are filter-machinery; names are human-readable. Variant names follow the same rule (`tokaido`/`tohoku` not `jt`/`ju`).
- **Naming asymmetry to watch**: route folder `audio/sobu/` ↔ lines slug `yokosuka_sobu`. Same physical line, different namespaces (route folder = sim-route diagram; lines slug = transfer catalog). Don't conflate when refactoring either.
- **Icon slug = filename stem** under `data/line_icons/`. Convention: JR letter codes use the bare code (`JY`, `JK`, `JT`, …); Tokyo Metro / Toei use operator-prefixed slugs (`metro_marunouchi`, `toei_asakusa`, …); descriptive for others; `_universal` for the fallback. Source SVGs live in `lcd_references/line_badges/` and regenerate via `magick -background none <src.svg> -resize 128x128 <dst.png>`.

---

## stations.json Format (Station Metadata)

**Location:** `data/stations.json` (project root)

### Purpose

Line-independent station metadata, keyed by Japanese station name. Shares the same key space as `translations.json` but separated by concern:
- `translations.json` → display text (furigana, english)
- `stations.json` → operational/physical facts (3-letter codes, transfer-line lists; future: platforms, etc.)

A station has a single entry even if it appears on multiple routes (e.g., 秋葉原 is on both Yamanote and Keihin-Tohoku — one row).

### Structure

```json
{
    "東京": {
        "code_3": "TYO",
        "transfers": [
            "tohoku_shinkansen", "tokaido_shinkansen",
            "yamanote", "keihin_tohoku", "chuo_rapid", "tokaido",
            "ueno_tokyo", "keiyo",
            "yokosuka_sobu.yokosuka", "yokosuka_sobu.sobu",
            "marunouchi"
        ]
    },
    "品川": {
        "code_3": "SGW",
        "transfers": [
            "yamanote",
            "keihin_tohoku.oimachi_kamata",
            "tokaido",
            "ueno_tokyo.tokaido",
            "yokosuka_sobu.yokosuka",
            "tokaido_shinkansen",
            "keikyu"
        ]
    },
    "秋葉原": {"code_3": "AKB"}
}
```

### Fields

| Field | Description |
|-------|-------------|
| `code_3` | JR East 3-letter station code. Only 22 stations total have one — the rule is "3+ JR East systems converge" (with 浜松町 and 高輪ゲートウェイ as explicit exceptions). Absent on all other stations. |
| `transfers` | Optional. Ordered array of slug references into `data/lines.json`. Each entry is either a plain slug `"yamanote"` or a dotted variant reference `"slug.variant"` (see `lines.json` § Variant resolution). Order matches IRL PIDS reading order (top-to-bottom, left-to-right). Include all lines reaching the station, including the user's active line — the runtime active-line filter drops slugs whose effective `badges[].code` matches the active route. |
| `transfers_by_view` | Optional. Per-station map keyed by `"<line>_<direction>"` (e.g. `"JY_inner"`, `"JT_south"`). Value is an object with optional ops: `{"drop": [base-slug names...], "edit": {base-slug: replacement-slug-ref, ...}, "rows": [int, ...]}`. `drop` and `edit` match by base slug name — `drop: ["keihin_tohoku"]` drops both plain and any `keihin_tohoku.<variant>` references; `edit: {"keihin_tohoku": "keihin_tohoku.oimachi_kamata"}` replaces whatever `keihin_tohoku`-base entry the flat list has with the variant ref. Drop applied first, then edit. `rows` is an explicit row-partition override — list of ints summing to the post-drop/edit entry count, e.g. `[2, 1]` forces the first 2 entries onto row 0 and the 3rd onto row 1. Bypasses both shinkansen-prefix detection and small-N structural rules; real-render positioning (Rules 1-4 + track-back) still runs within each forced row. Use only when algorithm row-grouping doesn't match IRL — last-resort data hint, expected to be empty for most stations. Mismatched sum → warning + algorithm fallback (no crash). `add` op reserved for future. |

### Notes

- Not every station needs an entry. Only add rows for stations with metadata to record.
- Stations without a 3-letter code simply omit the `code_3` key.
- 3-letter Roman codes (`code_3`) are distinct from 2-character katakana telegraph codes (電略) — the latter is a separate internal JR system and is not stored here.
- `transfers` populated only for stations with `code_3` in v1 scope (the 22 major interchange catalog). Other stations may gain `transfers` later as data is collected.
- **Typical category ordering** (within IRL reading order — use as a starting guess, override per IRL reference photo): Shinkansen → own JR line → JR runners (other JR East lines through the station) → private operators (Tōkyū / Keiō / Odakyū / Tōbu / Seibu / Keisei / Tsukuba Express / Yurikamome / monorails) → Tokyo Metro → Toei. Sub-order *within* a category is IRL-driven and varies per station — don't enforce it algorithmically. New stations: list candidates by category as a draft, then reorder against the reference photo.

---

## route.json Format

**Location:** `audio/[line]/[diagram]/route.json`

### Route-Level Fields

```json
{
    "route": "路線名",              // Route name (e.g., 中央線快速電車，埼京線)
    "line_code": "JY",             // Optional. Active-line badge code (JY/JK/JC/JO/JU/JT/JJ/JE/JN/JA). Drives transfer-info active-line filter — entries whose badges include this code are dropped. Absent → no filter (renders raw transfers).
    "transfer_view": "JY_inner",   // Optional. Key into each station's `transfers_by_view` map (e.g. JY_inner, JK_south, JO_east). Selects per-station drop/edit ops for this train direction. Absent → no view ops applied.
    "color": [R, G, B],            // Main route color for UI elements
    "contrast_color": [R, G, B],   // Contrast color for pointers/highlights (optional, default: [224, 54, 37] JR red)
    "type_color": [R, G, B],       // Color for train type text (optional, default: black)
    "type": "列車種別",             // Train type (e.g., 快速，普通，各駅停車)
    "dest": "終点",                 // Final destination (kanji) - furigana loaded from data/translations.json
    "pre_stops": [...]             // Optional. Through-service pre-route stations rendered as dim/passed
}
```

#### `pre_stops` Array (Through-Service Pre-Route) — Optional

Stations the train traversed **before** the simulator's active route begins — typically a different line operationally through-running into this one (e.g. Yokosuka Line's 久里浜→東京 for a Sōbu Rapid 1217F service that the simulator models from Tokyo onwards).

**Display-only.** The simulator never advances into `pre_stops` — these cells just render as already-passed history on the lower LCD route map. `stops[0]` remains the start of the simulated journey.

```json
{
    "pre_stops": [
        {"name": "横須賀",   "sta_code": "JO03"},
        {"name": "田浦",     "sta_code": "JO04"},
        ...
        {"name": "新橋",     "sta_code": "JO18"}
    ],
    "stops": [
        {"name": "東京",     "pa": [], "time": 0, "sta_code": "JO19", ...},
        ...
    ]
}
```

**Required fields:** `name` (kanji) + `sta_code` (for the per-cell mini badge in the 8-station view).

**Forbidden fields:** `pa` / `pa_at_station` / `sta` / `sta_cut` / `time` — pre-route stops are never simulated, these would be ignored. Keep them out to make intent explicit.

**Render contract** (lower LCD, full-route + 8-station views):

- Pre-route cells render in `INACTIVE_COLOR` regardless of train position — they're "always passed."
- Window logic operates on `pre_stops + stops` combined. Long combined journeys (>28 cells) flip from a first-window view to a last-window view exactly once, same final shape as native long routes — but the trigger differs: native uses **early-flip** (when `remaining < STOPS_QUANTITY`); pre_stops routes use **late-flip** (when the train would scroll off the right edge of the first window). Late-flip keeps the through-service prefix visible at boot. See `_get_stops_list_disp` in `lower_lcd.py` for the branching.
- App's `state.curr_stop` still indexes into `stops[]` (sim truth); display code shifts by `len(pre_stops)` internally.
- Translations / furigana / English not required for pre-route stations — the lower LCD shows kanji only.

### Stop-Level Fields

Each stop in the `stops` array:

```json
{
    "name": "駅名",                       // Station name (kanji)
    "pa": ["prev-dep", "this-arr"],      // Pre-arrival PA tracks (empty array = no announcement)
    "pa_at_station": ["transfer-info"],  // Optional. At-platform PA tracks played after arrival
    "sta": ["this_4_song-id"],           // STA audio filename(s) without .mp3 extension
    "sta_code": "JC01",                  // JR official station numbering code (or null)
    "sta_cut": 10,                       // STA melody: seconds where melody is cut and the closing-door announcement begins
    "time": 3                            // Travel time INCOMING from the previous PA station (minutes; 0 for first station)
}
```

**Note:** The `time` field is the scheduled **incoming** travel time — minutes from the previous PA station's departure to this stop's arrival. Display semantics (countdown formula, floor division, forced "1" on last PA, STOPPING blanking, `TIME_SCALE` constant) live at the inline `# CONTRACT:` on `displays/train_models/e235_1000/lower_lcd.py` `draw_times` per [CLAUDE.md](CLAUDE.md). State-machine interaction is in [DISPLAY.md § Unified State Machine](DISPLAY.md).

**Convention rationale:** the field is anchored on the destination station, not the source — `stops[N].time` answers "how long does it take to reach N?" (= travel from N−1 → N), not "how long until I leave N?". Verified via Tokaido 1865E: 新橋.time=2 matches IRL 東京→新橋 (~2 min), 品川.time=5 matches 新橋→品川 (~5 min). 東京.time=0 because there's no previous station.

### Field Details

#### `pa` Array (PA Announcements)

| Value | Meaning |
|-------|---------|
| `[]` | No PA announcement - train doesn't stop OR first station |
| `["tokyo-dep"]` | Single PA track using filename |
| `["tokyo-dep", "shinagawa-arr"]` | Multiple PA tracks using filenames |

**PA Track Filename Convention:**

The `pa` array contains filenames (without `.mp3` extension) that map directly to audio files in the `pa/` folder:

- Track reference `"tokyo-dep"` → `audio/[line]/[diagram]/pa/tokyo-dep.mp3`
- **Preferred convention (new lines):** descriptive `{station}-{dep|arr}` (lowercase, hyphen-separated, no macrons). Reference: `audio/sobu/1217F/`, `audio/takasaki/3922E/`. Pattern:
  - `{prev-station}-dep` = Departure announcement (recorded after departing previous station, announcing next stop). Lives in *this* stop's `pa` array.
  - `{this-station}-arr` = Arrival announcement (recorded approaching this station)
  - Compound station names use additional hyphens: `shin-koiwa-dep`, `kita-ageo-arr`
  - Terminus only has `{this}-arr`; first station has no PA at all
- **Legacy convention (existing lines):** sequential numbers (`"1"`, `"2"`, …) — used by `audio/keiyo/`, `audio/chuo/`. Don't migrate; the renderer treats both identically.

**When modifying PA tracks on a numeric-convention line:** only change the affected stations. Don't renumber subsequent stations. Example: moving track `"1"` from Station B to Station A only changes those two stations' arrays — every later station keeps its existing numbers.

**Example:**
```json
{
    "name": "品川",
    "pa": ["shimbashi-dep", "shinagawa-arr"],  // shimbashi-dep.mp3, shinagawa-arr.mp3
    "sta": ["JT03_SGW"],
    "sta_cut": 17,
    "time": 5,
    "sta_code": "JT03"
}
```

**Skipping Stations:**
Stations with empty `pa: []` are skipped automatically (train passes through without stopping). Passing stations must omit `sta`, `sta_cut`, and `time` — the train doesn't stop, so no departure melody plays and the countdown is driven by the next PA station's `time`.

```json
{
    "name": "辻堂",
    "pa": [],
    "sta_code": "JT09"
    // NO "sta" — train doesn't stop, no departure melody
    // NO "sta_cut" — melody won't play
    // NO "time" — countdown derived from next PA station
}
```

#### `pa_at_station` Array (At-Station Announcements) — Optional

Optional list of PA tracks that play **while the train is stopped at the platform**, after the pre-arrival announcements have finished. Defaults to absent / empty (typical stops have none).

Semantic split:

- **`pa`** — pre-arrival sequence (dep-from-prev, this-arr): plays while the train is moving toward this stop.
- **`pa_at_station`** — at-platform sequence (transfer info, connection notices, etc.): plays after the train has come to rest.

| Value | Meaning |
|-------|---------|
| *(field omitted)* or `[]` | No at-station PAs — default for typical 2-PA stops |
| `["transfer-info"]` | Single at-station track |
| `["transfer-info", "connection-notice"]` | Multiple at-station tracks |

**Filename convention:** same as `pa`. Slugs resolve to `pa/<slug>.mp3` — both lists share the single `pa/` folder.

**Example** (Tokaido 1865E 国府津 — junction with the Gotemba Line, with extra at-platform announcements):

```json
{
    "name": "国府津",
    "pa": ["25", "26"],
    "pa_at_station": ["27", "28"],
    "sta": ["JT14"],
    "sta_cut": 18,
    "time": 6,
    "sta_code": "JT14"
}
```

The state machine consumes both lists and surfaces a separate "STOPPING at station" display state during `pa_at_station` playback. Display-side semantics live in [DISPLAY.md](DISPLAY.md); state-machine flow lives at `app.py` `PASimulator._next_pa`.

#### `sta` Array (STA Melodies)

| Value | Meaning |
|-------|---------|
| *(field omitted)* | No STA melody — passing stations and arrival termini (the last stop, where the train doesn't depart again). An *origin* terminus DOES get `sta`, since the train departs from there. |
| `["JC01"]` | Single STA audio file |
| `["JC01", "JC01_1"]` | Multiple STA audio files (variants) |

**Note:** The `sta` field contains actual audio filenames (without `.mp3`). Two filename styles coexist (renderer treats both identically):
- **Legacy** — `sta_code` plus optional disambiguation suffix (`JC01`, `JC01_OSK`, `JK47_OMY`).
- **Slug** — `{station}_{platform}_{song-id}` (e.g. `tokyo_4_jr-sh5-1`, `kinshicho_4_gota-del-vient`). Filename is the metadata store; see `/sta-make` for the slug rules and song-id catalog.

When a station has no STA melody, **omit the field entirely** rather than setting `[]` or `[""]`.

#### `sta_code` Field (Station Numbering)

| Value | Meaning |
|-------|---------|
| `"JC01"` | Official JR East station code (used for line-specific data lookup) |
| `null` | Station has no official code (e.g., Kawagoe Line stations) |

**Format:** `[Line Prefix][Number]` (e.g., `JC01`, `JK47`, `JA08`)
- Line prefixes: JC (Chuo), JK (Keihin-Tohoku), JA (Saikyo), JE (Keiyo), JY (Yamanote), JT (Tokaido), JN (Nambu), JJ (Joban), JU (Takasaki), JO (Sōbu Rapid / Yokosuka)
- No 3-letter suffixes in `sta_code` (those go in `sta` field only)
- **Note:** `sta_code` is route-local — used by `upper_lcd.py` to render the station code badge. Line-independent station metadata lives in `data/stations.json`.

#### `sta_cut` Field

| Value | Meaning |
|-------|---------|
| `0` | No STA melody / full track plays |
| `>0` | Seconds into STA track where melody is **cut** and the closing-door announcement (station-attendant voice, "ドアが閉まります") begins. Integer or one-decimal float (e.g. `15.6`) — runtime accepts float seconds. Use the extra precision when the music→voice gap is narrow and a 1 s rounding error would land in the wrong region. |

---

## Supported Lines

All lines share the central `data/translations.json` (display text) and `data/stations.json` (operational metadata).

| Line | Code Prefix | Folder |
|------|-------------|--------|
| Chuo Main (中央線) | JC | `audio/chuo/` |
| Joban (常磐線) | JJ | `audio/joban/` |
| Keihin-Tohoku (京浜東北) | JK | `audio/keihin/` |
| Keiyo (京葉線) | JE | `audio/keiyo/` |
| Nambu (南武線) | JN | `audio/nambu/` |
| Saikyo (埼京線) | JA | `audio/saikyo/` |
| Sōbu Rapid / Yokosuka (総武快速・横須賀) | JO | `audio/sobu/` |
| Takasaki (高崎線) | JU | `audio/takasaki/` |
| Tokaido (東海道線) | JT | `audio/tokaido/` |
| Yamanote (山手線) | JY | `audio/yamanote/` |

---

## Circular Routes

First and last entries in `stops[]` share the same `name` (e.g. Yamanote: 大崎 appears twice). The simulator handles the wrap-around automatically — no special field needed.

---

## Data Validation

Run `validate_data.py` from the project root:

```bash
PYTHONUTF8=1 python validate_data.py
```

Exits 0 if clean, 1 if issues found (suitable for pre-commit / CI). Checks performed:

**Shape rules** (apply to all routes including fixtures under `audio/_*/`):

- Every stop has `pa` field (required — without it, downstream rules would silently bypass)
- Every stop has `sta_code` (value or `null`); value has no `_XX` suffix
- Passing stations (`pa: []`, non-first) have NO `sta`, NO `sta_cut`, NO `time`, NO `pa_at_station`
- First station has `time: 0`; all other non-passing stops have `time` set
- `pre_stops[]` entries have required `name` + `sta_code`; forbidden `pa` / `pa_at_station` / `sta` / `sta_cut` / `time`
- Compound translations (key contains `・`) encode `english` as `"A&\nB"` form (no space before `&`, newline immediately after)

**Cross-reference rules** (skipped for fixtures under `audio/_*/` — those use out-of-scope strings + lack real audio by design):

- Every stop `name` has an entry in `data/translations.json`
- Route-level `dest` and stop-level `dest` overrides are translated
- Route-level `type` has an entry in `data/train_types.json`
- Every file referenced by `pa` / `pa_at_station` / `sta` exists on disk (`pa/<name>.mp3`, `sta/<name>.mp3`)

**Lines + transfers** (apply at `data/` level — fixture-skip not applicable):

- `lines.json` `category` is one of `jr_east` / `shinkansen` / `non_jr`
- `lines.json` badge `icon` slugs resolve to PNGs under `data/line_icons/<icon>.png` (base + variants)
- `stations.json` `transfers[]` entries: base slug exists in `lines.json`; `slug.variant` matches a declared variant; dot-notation depth ≤ 1 (e.g. `slug.variant` OK; `slug.variant.subvariant` rejected)
- `stations.json` `transfers_by_view[VIEW]` ops:
  - `drop` entries match a base slug already in `transfers[]` (typo + stale-data guard)
  - `edit` keys match a base slug in `transfers[]`; edit values resolve in `lines.json` (base + variant if dotted)
  - `rows` array sums to `len(transfers) - len(drop)` — promotes the runtime-fallback warning to authoring-time error
- `route.json` `transfer_view`: at least one stop on the route has a `stations.json` `transfers_by_view` entry for it. Direction is route → stop → station (NOT station → route). The reverse direction would false-positive on station configs that are forward-looking or test-only (e.g. `大船`/`武蔵小杉`'s `JO_north`).

**Inventory check:**

- `stations.json` `code_3` count matches the documented 22

Issues are grouped by location (route or top-level data file). **Add new checks by editing `validate_data.py` — don't re-embed them here.**

### Things the validator can't catch (verify by eye)

- Hepburn correctness in new translations (macrons on long vowels, spelling).
- PA track mapping — that `tokyo-dep.mp3` is actually the announcement recorded *after* Tokyo and references the correct next stop. The validator only checks the file exists.
- Slug song-id correctness for `sta` files — the slug is the metadata store; the validator can't tell `kinshicho_4_gota-del-vient` from `kinshicho_4_horidei`.

---

## Windows console encoding

If `validate_data.py` (or any script printing Japanese) hits `UnicodeEncodeError: 'charmap'`, prefix with `PYTHONUTF8=1` (or `set` / `$env:` it in cmd / PowerShell). Project file I/O already passes `encoding='utf-8'`, so the issue is console output only.
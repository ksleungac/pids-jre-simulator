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
> - Facts already in [CLAUDE.md](../CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Voice:** new reference-shaped entries (schemas, field semantics, render contracts) stay compressed — tables, `=` for definitional equivalence, no narrative padding. Rationale-shaped passages (incident traces, design rationale, "why this matters" framings, anything labeled "Convention rationale" or similar) run as ordinary prose. Both in complete sentences where they use prose at all, per [CLAUDE.md § Writing tone](../CLAUDE.md).
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](../.claude/rules/principles.md).

---

## File Structure

```
data/
├── translations.json        # Central translation database (furigana, english)
├── train_types.json         # Train type English translations (with optional english_short)
├── lines.json               # Rail line catalog (badges, colors, display names) for transfer entries
├── line_icons/              # PNG assets for branded line logos (Shinkansen, etc.)
└── stations.json            # Station metadata (3-letter codes, transfers; more fields over time)
audio/[line]/{pa,sta}/              # per-line shared audio pool — every shipped line
audio/[line]/[diagram]/route.json   # route data only — no audio_root; absent means the pool
```

---

## translations.json Format (Central Translation Database)

**Location:** `data/translations.json` (project root)

### Purpose

Centralized translation lookup for **any Japanese text** used in simulator:
- Station names (furigana/english cycling display)
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

**Important:** keys are **raw Japanese text** (kanji/kana), not station codes. App-side lookup is direct (`translations[name]`). There is no fallback layer.

### Value Fields

| Field | Description |
|-------|-------------|
| `furigana` | Kana reading. Katakana is allowed where the name carries it (`くうこうだいにビル`). A **kanji is never valid**, since this is the field furigana mode renders instead of kanji. A half-converted IME entry (`よの本まち`) is well-formed JSON and silently wrong, so `validate_data.py` rejects it. |
| `english` | English translation or romanization. Must derive from `furigana`. See § English Translation Convention. |

### Compound Destinations (e.g., Yamanote Line)

Routes displaying multiple destinations (like 品川・東京) use `&` as the separator. Whether to insert `\n` after `&` is case-by-case, matching IRL. A short compound destination fits on one line, so omit `\n`. A longer one breaks onto two lines.

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

**Note:** compound destinations typically don't need a `furigana` field. They are used for English display only, not for furigana cycling on the upper LCD.

### English Translation Convention (Hepburn Romanization)

English translations use **modified Hepburn romanization with macrons** to indicate long vowels. The convention itself (preloaded mental model: Tōkyō, Chūō, why Etchūjima not Ecchūjima) lives in [CLAUDE.md](../CLAUDE.md) "Mental Model → IRL display conventions". This section covers the JSON-encoding side.

| Long Vowel | Source | Example |
|------------|--------|---------|
| **ō** | おう, おお | 東京 → T**ō**ky**ō**, 大宮 → **Ō**miya |
| **ū** | ゆう, うう | 越中島 → Etch**ū**jima, 有楽町 → Y**ū**rakuchō |

**Examples:**
```json
{
    "東京": { "english": "Tōkyō" },
    "大宮": { "english": "Ōmiya" },
    "大久保": { "english": "Ōkubo" },
    "十条": { "english": "Jūjō" },
    "越中島": { "english": "Etchūjima" },
    "港南台": { "english": "Kōnandai" }
}
```

**JR East signage form, not textbook Hepburn.** `ん` assimilates to `m` before `b` / `m` / `p`: 新橋 → Shi**m**bashi, 新町 → Shi**mm**achi, 与野本町 → Yono-Ho**mm**achi, 海浜幕張 → Kaihi**mm**akuhari, 神保原 → Ji**m**bohara.

**A hyphen marks a prefix, not a word break.** A directional or qualifier prefix takes one: Kita-Akabane, Shin-Ōkubo, Nishi-Ōi, Shim-Misato. A single place name does not: Sashiōgi, Fuchūhommachi, Hongōdai, Kemigawahama. No reading encodes this, so it is the one facet left to the eye, and the eye is not enough. **西那須野 is `Nishi-Nasuno` on JR East's own English timetable**, though 那須野 is not a station and the place-name test above would put it in the unhyphenated column beside Nishifu and Minamitama. The heuristic loses to the authority order below whenever the two disagree. Check the JR East page before trusting it. (2026-08-22: authored one-word, corrected.)

**A few `english` values are translations rather than romanizations.** 葛西臨海公園 is `Kasai-Rinkai Park` (JR East's current form; it was Kasairinkaikōen), and 成田空港 is `Narita Airport\nTerminal 1`. Each is an editorial decision, so they are listed explicitly in `validate_data.py::_TRANSLATED_NAMES` rather than pattern-matched.

**Authoring order of authority:** JR East's own English pages (`timetables.jreast.co.jp/en/…`) → ja.wikipedia's infobox ローマ字 → derivation from the reading. JR East's timetable channel strips macrons (it writes `Yurakucho`, `Osaki`), so it settles spelling and hyphenation but never macrons.

### Stop-Level Destination Override

A stop carries its own `dest` field to override the route-level value:

```json
{
    "name": "田町",
    "pa": ["3"],
    "dest": "東京・上野",
    "time": 3
}
```

**Sticky semantic.** An override sets the displayed dest from that stop onward, until the next override. The route-level `dest` is the value before any override. Circular routes (Yamanote) use this, where the displayed dest cycles as the train traverses the loop.

**Loader-time closure.** `route_loader.finalize_route` walks the stops list once at load time and fills `dest` on every stop with the effective value. After load, every stop has a `dest` field, and renderers read it directly with no fallback logic. JSON is input grammar: only the irreducible overrides are authored, and the runtime structure is the closure.

**Yamanote example:** the route-level `dest` is 品川・東京. Overrides at 田町 / 神田 / 鶯谷 / 目白 / 代々木 / 恵比寿 cycle through a next-2-major-terminals window. Display semantics (kanji always, English uses translation lookup) are in [DISPLAY_E235.md § Destination Behavior](DISPLAY_E235.md).

---

## train_types.json Format (Train Type Translations)

**Location:** `data/train_types.json` (project root)

### Purpose

English translations for train type names (列車種別). Unlike stations, train types have no furigana. They are displayed in kanji or English only.

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

For narrow display boxes (e.g. the E235-1000 type box, 150 px), the resolution order is `english_short` → `english` → kanji. `中央特快` is the only current consumer: `Chūō Sp. Rapid` fits where `Chūō Special Rapid` overflows.

English translations follow the same Hepburn-with-macrons convention as station names. See the translations.json section above.

---

## lines.json Format (Rail Line Catalog)

**Location:** `data/lines.json` (project root)

### Purpose

Catalog of rail lines referenced as transfer entries on station displays. It stores brand metadata (line code, icon asset, display name) once per line, referenced by slug from the `transfers` arrays in `stations.json`.

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
                "name_ja": "京浜東北線（大井町・蒲田方面）",
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
| `badges` | Optional. Array of badge objects rendered left-to-right before the line name. Each badge carries `icon` (required, a slug naming a PNG asset under `data/line_icons/<slug>.png`), optionally `code` (1-2 letter line code such as `JY`, which the runtime transfer-filter rule matches against the active route's line code), and optionally `color` (`[r, g, b]`, the line-brand color used by the per-train-model badge rendering policy that swaps the icon for a color square on certain trains; the renderer ignores it when that policy is not active, see [DISPLAY.md § Color-square policy](DISPLAY.md)). Typical JR East lines take one badge. Through-running compound services take several (the UT base is JT + JU). Shinkansen and non-JR operators carry `icon` without `code`. If absent, the universal fallback icon (`_universal.png`) is used. |
| `name_ja` | Japanese display name. Required at the base unless the slug is **only** referenced via variants (`yokosuka_sobu`, whose base is never used directly). |
| `name_en` | English display name (Hepburn-with-macrons). Same required-unless-variant-only rule as `name_ja`. |
| `category` | One of `jr_east` / `shinkansen` / `non_jr`. Drives row-grouping. |
| `variants` | Optional. Map of `<variant_name> → {field overrides}`. Each variant overrides any subset of base fields, and missing fields inherit from the base. Used for zone-specific badge subsets (UT JT-only south, JU-only north), through-service display variants (Yokosuka vs Sōbu Rapid label on the same JO physical line), and direction-qualified line names (Keihin-Tōhoku with the `（大井町・蒲田方面）` suffix). Variants are referenced from `stations.json` via dot notation: `slug.variant_name`. |

### Reference resolution (variant + scale)

A `transfers` entry in `stations.json` can be a plain `"slug"`, a dotted `"slug.variant"`, or carry a trailing `.scale(N)` modifier (e.g. `"ueno_tokyo.tokaido.scale(0.75)"`). Resolver (`preview_transfers.py:resolve_entry`):

1. Strip the optional trailing `.scale(N)` suffix and remember N.
2. Split the remainder on the first `.` → `(base_slug, variant_name)`.
3. Dot notation is **one level only** for variants. `slug.variant.subvariant` raises ValueError.
4. **Fail loud** on a missing base or an unknown variant. Never silently fall back. (Per the `critical_lessons.md` runtime-required-artifacts rule.)
5. Merge: variant fields override the base, and missing fields inherit. The `variants` key is stripped from the resolved output.
6. If `.scale(N)` is present, override `name_ja_compress` with N. Otherwise it defaults to 1.0 (natural width).

**When to apply `.scale(N)`:** only at busy stations whose visible entry count after view-filtering is high enough to crowd a row. Sparse stations have the horizontal budget to render at natural width, and over-applying compression kills legibility for no benefit. Curate per station against an IRL reference photo.

### Notes

- **Slug keys are arbitrary IDs.** Keep them stable so `stations.json` references don't churn.
- **Slug names don't carry codes:** `yokosuka_sobu`, not `jo_through`. Codes are filter machinery. Names are human-readable. Variant names follow the same rule (`tokaido` / `tohoku`, not `jt` / `ju`).
- **Naming asymmetry to watch**: the route folder is `audio/sobu/` while the lines slug is `yokosuka_sobu`. Same physical line, different namespaces: the route folder names a sim-route diagram, the lines slug names a transfer-catalog entry. Don't conflate them when refactoring either.
- **An icon slug is the filename stem** under `data/line_icons/`. JR letter codes use the bare code (`JY`, `JK`, `JT`, …). Tokyo Metro and Toei use operator-prefixed slugs (`metro_marunouchi`, `toei_asakusa`, …). Others are descriptive, and `_universal` is the fallback. Source SVGs live in `_references/lcd/line_badges/`. Regenerate via `magick -background none <src.svg> -resize 128x128 <dst.png>`.
- **Punctuation in `name_ja` is per-line IRL fidelity.** Match the real PIDS rather than normalizing for consistency. Width is not uniform across lines. `keihin_tohoku.oimachi_kamata` uses **full-width** brackets `（）` and dot `・` (`京浜東北線（大井町・蒲田方面）`), which is IRL-special at 品川. A "consistency" pass that half-widthed it would be wrong. Other direction suffixes use **half-width** `()`, e.g. `宇都宮線(東北線)`. Shinkansen names use the **half-width** middle dot `･` (U+FF65), matching the destination-separator convention (`東北･山形･秋田･北海道･上越･北陸新幹線`). The 5-station inline panel wraps on this codepoint (see [DISPLAY_E235.md § Inline transfer panel](DISPLAY_E235.md)).

---

## stations.json Format (Station Metadata)

**Location:** `data/stations.json` (project root)

### Purpose

Line-independent station metadata, keyed by Japanese station name. It shares the same key space as `translations.json` but is separated by concern:
- `translations.json` → display text (furigana, english)
- `stations.json` → operational/physical facts (3-letter codes, transfer-line lists; future: platforms, etc.)

A station has a single entry even if it appears on multiple routes. 秋葉原 is on both Yamanote and Keihin-Tohoku, and gets one row.

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
| `code_3` | JR East 3-letter station code. Only 22 stations have one. The rule is "3+ JR East systems converge", with 浜松町 and 高輪ゲートウェイ as explicit exceptions. Absent on all other stations. |
| `transfers` | Optional. Ordered array of slug references into `data/lines.json`. Each entry is either a plain slug `"yamanote"` or a dotted variant reference `"slug.variant"` (see `lines.json` § Variant resolution). Order matches IRL PIDS reading order, top-to-bottom and left-to-right. Include all lines reaching the station, including the user's active line: the runtime active-line filter drops slugs whose effective `badges[].code` matches the active route. |
| `transfers_by_view` | Optional. Per-station map keyed by `"<line>_<qualifier>"`, where the qualifier is whatever distinguishes one PIDS reading from another on that line code. Usually that is direction (`"JY_inner"`, `"JT_south"`), but it is **service** where two services share a code (`"JU_utsunomiya"` / `"JU_takasaki"`, which announce each other at 大宮 and so cannot share a view). The value is an object with optional ops: `{"drop": [base-slug names...], "add": [exact refs...], "edit": {base-slug: replacement-slug-ref, ...}, "rows": [int, ...]}`. `drop` and `edit` match by base slug name. `drop: ["keihin_tohoku"]` drops both the plain reference and any `keihin_tohoku.<variant>` one. `edit: {"keihin_tohoku": "keihin_tohoku.oimachi_kamata"}` replaces whatever `keihin_tohoku`-base entry the flat list has with the variant ref. Drop is applied first, then edit. **`edit` rewrites every entry of that base, and consecutive duplicates then collapse**, which is how a view merges a through-service listed as its branches. Mapping a base **to itself** looks like a no-op and is not: the key matches by base while the value is an exact ref, so `slug.a` and `slug.b` both become the bare `slug` and show as one entry under the base's own `name_ja`. 東京 lists 横須賀線 and 総武線快速 separately (a JY train shows both, a JO train shows neither), and the Chūō view collapses them: `"JC_up": {"edit": {"yokosuka_sobu": "yokosuka_sobu"}}` → `横須賀線・総武線快速`. The collapse is **consecutive-only**, so an `edit` that maps two unrelated entries onto one ref from different places in the list still yields both. Branches of one service are adjacent by construction, because `transfers[]` is in IRL reading order. **A view can merge but never split**, so the flat list always holds the finest-grained form and views coarsen it. That also fails safe, since a view with no ops shows the branches rather than a silently missing entry. Locked by `_tests/t1_unit/test_transfer_info.py`. `order` is **the view's own reading order**, a list of base slugs. Nothing else can permute: `transfers[]` is one ordered list shared by every view, and `add` / `drop` / `edit` / `rows` all preserve position, while the IRL order is a property of the PIDS being read rather than of the station. 新宿 is the case: a Chūō train names 中央・総武線 first (`"JC_up": {"order": ["sobu_local", "yamanote", "saikyo_kawagoe", "shonan_shinjuku"]}`), where the Yamanote panel leads with 山手線. The order is **leading, not total**: listed slugs come first in the order given and everything else keeps its relative position behind them, so a view states only the part it cares about (usually the JR block) and a line added to `transfers[]` later cannot silently jump to the front. It is applied last, after the merge collapse, so it sees final refs. A slug the station does not carry orders nothing and is silent at runtime, so `validate_data.py` rejects it. `rows` is an explicit row-partition override, a list of ints summing to the post-drop/edit entry count. `[2, 1]` forces the first 2 entries onto row 0 and the 3rd onto row 1. It bypasses both shinkansen-prefix detection and the small-N structural rules. Real-render positioning (Rules 1-4 + track-back) still runs within each forced row. Use it only when algorithm row-grouping doesn't match IRL. It is a last-resort data hint, expected to be empty for most stations. A mismatched sum gives a warning plus algorithm fallback, with no crash. **`add` exempts an exact ref from the active-line filter, and is the only op that runs before it**, since that filter is the only thing `add` can undo. It exists for a **sibling** service sharing the active line's code: 宇都宮線 and 高崎線 are both `JU`, so riding either drops both, yet 大宮's PA (where they diverge) announces the other one, hence `"JU_utsunomiya": {"add": ["utsunomiya_takasaki.takasaki"]}`. Matching is by **exact ref**, unlike `drop` and `edit`, because the route's own variant must still go while the sibling survives. A base slug would re-admit both. Re-admitted entries keep their position in `transfers[]`, so IRL order needs no index. A `drop` of the same base still wins, because drop runs after. Ordering is add → active-line filter → drop → edit. |

### Notes

- Not every station needs an entry. Only add rows for stations with metadata to record.
- Stations without 3-letter code omit `code_3` key.
- The 3-letter Roman codes (`code_3`) are distinct from the 2-character katakana telegraph codes (電略). The latter are a separate internal JR system and are not stored here.
- `transfers` is populated only for stations with `code_3` in v1 scope (the 22 major interchange catalog). Other stations may gain `transfers` later as data is collected.
- **Typical category ordering**, within IRL reading order. Use it as a starting guess and override per IRL reference photo: Shinkansen → own JR line → JR runners (other JR East lines through the station) → private operators (Tōkyū / Keiō / Odakyū / Tōbu / Seibu / Keisei / Tsukuba Express / Yurikamome / monorails) → Tokyo Metro → Toei. The sub-order *within* a category is IRL-driven and varies per station, so don't enforce it algorithmically. For a new station, list candidates by category as a draft, then reorder against the reference photo.
- **The flat list names a line as it is at that station, not as the operator files it.** A through-service carries different names along its length, and `transfers[]` is read by every view, so a name that is only right in one place is wrong in the others. `sobu_local` is the worked case, and it takes three forms along one line:

  | where | ref | drawn |
  |---|---|---|
  | 新宿 and west: 武蔵境 · 三鷹 · 吉祥寺 · 荻窪 · 中野 · 新宿 | `sobu_local.chuo_local` | `中央線各駅停車` |
  | east of 新宿: 代々木 · 四ツ谷 · 御茶ノ水 … | `sobu_local.chuo` | `中央・総武線（各駅停車）` |
  | on the Sōbu itself: 錦糸町 · 船橋 · 千葉 … | `sobu_local` (base) | `総武線各駅停車` |

  The boundary is geographic rather than per-view, and it sits at 新宿: *"the pattern is on the stations that is near the actual sobu line, it changes to sobu"* (author, 2026-08-29). Two references pin it from either side. `transfer-shinjuku.png` draws `中央線各駅停車` and `transfer-ocha-ja.png` draws `中央・総武線(各駅停車)`, with 新宿 itself the last station on the Chūō side.

  **Reference photographs disagree with each other on this**, showing the same line four ways across frames, so the naming is settled from the geography rather than from whichever capture is to hand. The flat list holds the finest grain and views coarsen it, the direction `transfers_by_view` § "`edit` as a merge" already sets.

---

## route.json Format

**Location:** `audio/[line]/[diagram]/route.json`

### Route-Level Fields

```json
{
    "route": "路線名",              // Route name (e.g., 中央線快速電車，埼京線)
    "audio_root": ".",             // Optional. Only the EXCEPTION is authored: absent = the per-line pool (every shipped line); "." = audio beside route.json. See § audio_root Field.
    "model": "e235_0",             // Optional. Default train-display model for this route (registry key in displays/train_models/__init__.py, e.g. e235_1000 / e235_0). Seeds the setup-screen per-route model dropdown; the user can override per session. Absent / unknown → e235_1000 (DEFAULT_MODEL_KEY).
    "line_code": "JY",             // Optional. Active-line badge code (JY/JK/JC/JO/JU/JT/JJ/JE/JN/JA). Drives the transfer-info active-line filter: entries whose badges include this code are dropped. Absent → no filter (renders raw transfers).
    "transfer_view": "JY_inner",   // Optional. Key into each station's `transfers_by_view` map (e.g. JY_inner, JK_south, JU_utsunomiya). Selects per-station drop/edit ops for this train direction. Absent → no view ops applied.
    "color": [R, G, B],            // Main route color for UI elements
    "contrast_color": [R, G, B],   // Contrast color for pointers/highlights (optional). E235 models default to [224, 54, 37] JR red when absent. E233-0 reads it only on routes OUTSIDE its own line set; see § contrast_color below.
    "type_color": [R, G, B],       // Color for train type text (optional, default: black)
    "type": "列車種別",             // Train type (e.g., 快速，普通，各駅停車)
    "dest": "終点",                 // Final destination (kanji) - furigana loaded from data/translations.json
    "direction": "上り",            // Optional. 上り/下り/南行/北行/内回り/外回り. See § remarks below.
    "remarks": "…",                // Optional. 備考 cell text, verbatim. See § remarks below.
    "pre_stops": [...],            // Optional. Through-service pre-route stations rendered as dim/passed
    "frames": [...]                // Optional. Through-service display frames. Partitions the route; the LCD swaps at junctions
}
```

#### `audio_root` Field — Optional

Folder holding this route's `pa/` and `sta/`, **relative to the route.json's own folder**.

| value | meaning |
|---|---|
| *(absent)* | `".."`, the **per-line pool**. Every shipped line. |
| `"."` | audio sits beside `route.json` (pre-pool shape). Authored only by `_mock/main` and `_joban/tsuchiura`. |

```
audio/tokaido/pa/                  <- 73 PA files, shared by both diagrams
audio/tokaido/sta/                 <- 21 STA files, shared
audio/tokaido/1865E/route.json     <- route data only
audio/tokaido/3535E/route.json
```

Only the **exception** is written down. All 14 shipped routes said `".."`, a value carrying no information, so it was dropped and the default inverted. See `principles.md § "JSON is input grammar"`: author the irreducible, derive the rest.

**Resolution lives in one place: `route_loader.resolve_audio_root(work_dir, route_data)`.** Both consumers call it: `app.py._load_route_data` (→ `self.audio_root` → `AudioPlayer`) and `validate_data.check_route`. Nothing else may join an audio path by hand. Two sites did, and the pooling migration silently broke both. The OOBE tutorial's asset pre-flight went False for every new user, and the auto-driver's long-approach probe went inert on every route.

**There is deliberately no search order.** A diagram-then-pool fallback was designed and rejected. Legacy PA slugs were diagram-local (`1654T/pa/1.mp3` and `916H/pa/1.mp3` were different announcements), so a missing file would silently resolve to the other root and play the *wrong announcement* with no error. See [critical_lessons.md §2](../.claude/rules/critical_lessons.md). One root means one resolved path and a loud failure. The resolved root depends only on the declared (or defaulted) value, never on what happens to be on disk. `_tests/t1_unit/test_startup.py` pins that property.

#### Pool filename grammar

One pool per line means filenames from every diagram share one namespace, so the name has to survive that.

| part | rule |
|---|---|
| **PA** | `{prev-station}-{dep\|arr}-{direction}[-{type}]` |
| `{prev}` on a `-dep` | the previous **stopping** station — differs from the previous array element on any diagram that skips |
| `{direction}` | from that route's own top-level `direction`: 上り→`up`, 下り→`down`, 南行/北行→`south`/`north`, 内回り/外回り→`inner`/`outer`. Mandatory, even on a one-direction line — a reverse diagram would otherwise collide. |
| `{type}` | only where a **measured** difference exists between two diagrams' takes (`audio_id.same_recording`). Bare = one file serves the line. Tokens in use: `kaisoku`, `kakueki`, `futsu`, `acty`; chūō uses a `-{diagram}` tier instead. |
| **`pa_at_station`** | `{station}-stopping[-N]-{direction}[-{type}]`, indexed when a stop has more than one (array order = play order) |
| **STA** | **verbatim — no direction token.** A melody belongs to a platform, and direction is only ever a proxy for it. Keihin (`-south`) and saikyo (`-down`) carry one because they were pooled before this rule; kept, not copied. |

One mp3 carries **one `sta_cut`**, wherever it is referenced, including twice within a single `route.json` (yamanote's loop lists 大崎 at both ends; keihin points 新子安 at 鶴見's melody). `validate_data.check_pool_sta_cut_sync` gates it.

Per-line specifics, and what has been verified by ear → [audio/README.md](../audio/README.md).

#### `pre_stops` Array (Through-Service Pre-Route) — Optional

Stations the train traversed **before** the simulator's active route begins. Typically a different line operationally through-running into this one, e.g. the Yokosuka Line's 久里浜→東京 for a Sōbu Rapid 1217F service the simulator models from Tokyo onwards.

**Display-only.** The simulator never advances into `pre_stops`; these cells render as already-passed history on the lower LCD route map. `stops[0]` remains the start of the simulated journey.

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

**Required fields:** `name` (kanji) + `sta_code` (per-cell mini badge in 8-station view).

**Forbidden fields:** `pa` / `pa_at_station` / `sta` / `sta_cut` / `time`. Pre-route stops are never simulated, so these are ignored. Keeping them out makes the intent explicit.

**Render contract** (lower LCD, full-route + 8-station views):

- Pre-route cells render `INACTIVE_COLOR` regardless of train position, so they are "always passed".
- Window logic operates on `pre_stops + stops` combined. Long combined journeys (>28 cells) flip from first-window view to last-window view exactly once, reaching the same final shape as native long routes. The trigger differs: native uses **early-flip**, when `remaining < STOPS_QUANTITY`, while pre_stops routes use **late-flip**, when the train would scroll off the right edge of the first window. Late-flip keeps the through-service prefix visible at boot. See `_get_stops_list_disp` in `lower_lcd.py` for the branching.
- The app's `state.curr_stop` still indexes into `stops[]` (sim truth); display code shifts by `len(pre_stops)` internally.
- Translations / furigana / English are loaded and displayed for pre-route stations during language cycling.

#### `frames` Array (Through-Service Display Frames) — Optional

Partitions the route's station list into ordered display **frames** for a through-service that reframes the LCD at a junction (e.g. 1217F: Sōbu Rapid 久里浜→千葉, then Narita Line 千葉→成田空港 as a self-contained route). The LCD renders only the frame holding the train's position, and swaps at the junction. **No `frames` key = one implicit frame = legacy behavior**, and none of the existing routes carry it.

```json
"frames": [
    {"from": "久里浜", "to": "千葉",     "line": "yokosuka_sobu.sobu"},
    {"from": "千葉",   "to": "成田空港", "line": "narita_line"}
]
```

| Key | Meaning |
|-----|---------|
| `from` / `to` | Station-name **text** (kanji). Window extent, inclusive. Must resolve to a `name` in the combined `pre_stops + stops` list (`from` may reference a pre_stop). |
| `line` | `lines.json` slug, optional `.variant` (dot-separated, the same resolver as `stations.json` transfers). Carries the frame's line identity (name_ja / name_en / badges / color). |

**No `dest` / `color` fields.** Destination is governed by the dest-closure above, meaning route-level `dest` plus per-stop overrides, so a junction dest-change is a per-stop `dest` on the junction stop. Background is an LCD-model constant (E235-1000 → `WHITE_BG`), not route-derived.

**Shared boundary.** The junction station is one frame's `to` and the next frame's `from`, declared in both, and the validator enforces that they abut.

**Loader closure** (`route_loader._resolve_frames`): resolves `from`/`to` → indices over `pre_stops + stops`, resolves `line` → entry, enriches each frame in place with `from_idx` / `to_idx` / `line_entry`. Fails loud on unresolved station, bad slug, non-abutting boundary, or incomplete coverage (frames must tile start→end). Renderers read the closure directly.

**Render / swap behavior** (active-frame windowing, junction swap timing, JR-logo restart transition) → [DISPLAY.md § Through-Service Display Frames](DISPLAY.md) (cross-model) + [DISPLAY_E235.md § Through-service restart transition](DISPLAY_E235.md) (E235-1000).

### Stop-Level Fields

Each stop in `stops` array:

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

#### `remarks` and `direction`

`remarks` is the TIMS 備考 cell text **verbatim**. Nothing composes it, nothing parses it, and no
code reads its content: `route_select` and `pa_setting` blit the string as authored. What goes in
it is convention plus whatever the author wants to say: a service route and its through-running
(`上野東京ライン上り　東海道線直通`), or a note about a stopping pattern that only applies on
certain days.

It used to be a kv block `{direction, via, through, note}` that a composer assembled, prefixing the
route name and appending 直通. That bought one string and cost two bugs: a 直通直通 double-suffix
that needed its own validator gate, and a cell repeating the line name that both screens already
display in their own field. Replaced 2026-08-20; the author's framing is the reason it will not come
back: *"it's not about frame type so nothing requires it to be structural"*.

**One line, ≤ 18 characters.** The character count is a **sanity bound, not the cell's capacity**.
A count cannot be that, because the cell is ~184 px of usable width at 18 px per glyph, so roughly
10 full-width Japanese characters fit where ~18 Latin ones do, and several shipped routes already
sit past the Japanese figure. Overflow is a designed case: `_marquee_cell` ping-pong-slides it. The
newline ban is the hard half, because the AA-off lowres renderer has no glyph for one and draws a
tofu box (`conventions.md` § "AA-off lowres text renderers"). Both are gated in `validate_data.py`.
A note that genuinely needs two lines needs the cell to learn stacking first; `TBL_ROW_H` is 44 px,
so there is room for it when that day comes.

**`direction` is separate because it is not a caption.** It is the diagram's actual direction, and
it is where the PA filename's `{direction}` token comes from (§ Pool filename grammar below), a
fact that has to stay machine-addressable rather than dissolve into prose. Validated against
`上り / 下り / 南行 / 北行 / 内回り / 外回り`.

**In `name`, a space means "break here".** A space inside a station name is a layout instruction, not
part of the name: the route-bar label renders the space-separated parts on two vertical lines
(`"さいたま 新都心"` → `さいたま` over `新都心`). This is the same class of in-band layout convention
as `&` / `\n` in a compound `dest` above. The consequence worth knowing is that the drawn strings are
the **parts**, which exist nowhere in the JSON, so anything enumerating renderable text from the data
has to apply the same split (`font_atlas.STATION_NAMES` declares `split=True` for exactly this).

**A single-line surface strips it rather than drawing it.** The marker instructs a break, so a
surface with nowhere to break has nothing to obey, and a drawn space there reads as a word gap,
which on a row like the status band's `A → B` segment makes one station look like two. Every
one-line renderer already does this (the E233-0 upper plate's `draw_station`, the 6-station name
column); `tims/band.py::nm` was the one that did not, until 2026-08-30.

**Note:** the `time` field is the scheduled **incoming** travel time, in minutes from the previous PA station's departure to this stop's arrival. Display semantics (countdown formula, floor division, forced "1" on last PA, STOPPING blanking, `TIME_SCALE` constant) live at an inline `# CONTRACT:` on `displays/train_models/e235_1000/lower_lcd.py` `draw_times` per [CLAUDE.md](../CLAUDE.md). State-machine interaction → [DISPLAY.md § Unified State Machine](DISPLAY.md).

**Convention rationale:** the field is anchored on the destination station rather than the source. `stops[N].time` answers "how long does it take to reach N?" (travel from N−1 → N), not "how long until I leave N?". Verified via Tokaido 1865E: 新橋.time=2 matches IRL 東京→新橋 (~2 min), 品川.time=5 matches 新橋→品川 (~5 min). 東京.time=0 because there is no previous station.

### Field Details

#### `contrast_color`

The colour a train model gives the position marker when the route's own `color` would swallow the model's native one. Authored **only on the routes that need it**: a route without the field keeps whatever the model draws natively, and filling it in everywhere would be authoring a value nobody reads.

Models consume it differently, and both readings are correct:

| Model | Reading |
|---|---|
| E235-1000 / E235-0 | The marker colour outright, on every route. Absent → `[224, 54, 37]` JR red. |
| E233-0 | Out-of-spec compatibility only. On its own lines (`_IN_SPEC_LINE_CODES`, currently `JC`) the marker keeps its two greens whatever the field says; on any other route a declared `contrast_color` becomes the marker's **dark** tone and the light one is derived from it. Absent → native greens. |

E233-0's derivation reuses the lift its own pair already carries (`−2.6°` hue, `×0.659` saturation, `×1.709` value, read off `tri_color_top` / `tri_color_bot` rather than restated), so retuning the greens carries the out-of-spec tints with them.

**The measure is hue distance, not luminance.** Saikyō's bar `(46,139,87)` scores a *better* luminance ratio against the green marker than Chūō's own bar does (1.52 against 1.25) and looks far worse, because it sits 26.5° of hue away where Chūō sits 102°. Yamanote `(116,193,30)` is the other one, at 31.7°. Those two are what the field exists for on this model.

#### `pa` Array (PA Announcements)

| Value | Meaning |
|-------|---------|
| `[]` | No PA announcement — train doesn't stop OR first station |
| `["tokyo-dep"]` | Single PA track using filename |
| `["tokyo-dep", "shinagawa-arr"]` | Multiple PA tracks using filenames |

**PA Track Filename Convention:**

`pa` array contains filenames (without `.mp3` extension) mapping directly to audio files in `pa/` folder:

- Track reference `"tokyo-dep"` → `resolve_audio_root(work_dir, route_data) / "pa" / "tokyo-dep.mp3"`, which on every shipped line is `audio/[line]/pa/tokyo-dep.mp3` (see § `audio_root` Field)
- **The convention on every shipped line:** descriptive `{station}-{dep|arr}-{direction}`, plus a train-type tier where two diagrams' announcements differ (lowercase, hyphen-separated, no macrons). Reference: `audio/sobu/pa/`, `audio/takasaki/pa/`. Grammar and per-line specifics → [audio/README.md](../audio/README.md). Pattern:
  - `{prev-station}-dep` = Departure announcement (recorded after departing previous station, announcing next stop). Lives in *this* stop's `pa` array.
  - `{this-station}-arr` = Arrival announcement (recorded approaching this station)
  - Compound station names use additional hyphens: `shin-koiwa-dep`, `kita-ageo-arr`
  - Terminus only has `{this}-arr`; first station has no PA at all
- **Numeric slugs (`"1"`, `"2"`, …) are retired on every shipped line.** The 2026-08-08 pooling converted the last of them (keiyo, yamanote, nambu, tokaido 1865E). They survive only under `audio/_joban/` and `audio/_mock/`, so the renderer's tolerance of both forms is still live rather than dead code.

**When modifying PA tracks on a numeric-convention line:** change only the affected stations, and don't renumber the ones after them. Moving track `"1"` from Station B to Station A changes only those two stations' arrays; every later station keeps its existing numbers.

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
Stations with an empty `pa: []` are skipped automatically, because the train passes through without stopping. Passing stations must omit `sta`, `sta_cut` and `time`: the train doesn't stop, so no departure melody plays, and the countdown is driven by the next PA station's `time`.

```json
{
    "name": "辻堂",
    "pa": [],
    "sta_code": "JT09"
    // NO "sta": the train doesn't stop, so no departure melody
    // NO "sta_cut": the melody won't play
    // NO "time": the countdown is derived from the next PA station
}
```

**Authoring `time` across a skip run.** The stop after passing stations carries the **whole** run, so it is never the all-stations diagram's next hop. Take that diagram's summed hops over the same stations and subtract **1 minute per passing station**, since a skip saves the dwell plus the braking and acceleration around it:

```
time = Σ(all-stations hops, previous stop → this one) − 1 × (passing stations)
```

Tōkaidō `3535E` 藤沢→茅ヶ崎 skips 辻堂: `1865E` sums 3 + 3 = 6 over one passing station, so `time: 5`.

This is a sanity rule rather than a timetable: where the game's 運転時分 table is to hand, it wins. It exists to bar two silent failures, both found in the corpus on 2026-08-21, and silent because `validate_data.py` checks `time`'s shape and never its value:

- **Copying the next hop.** Chūō `916H` 三鷹→中野 skips five stations summing to 13 minutes and was authored `2`, exactly `1654T`'s 三鷹→吉祥寺 hop. The countdown clamps at `max(1, …)`, so this shows a stuck `1分` for four minutes across five stations rather than a visibly wrong number.
- **Summing with no credit for the skip.** Tōkaidō `3535E` 藤沢→茅ヶ崎 was authored `6`, the local sum untouched, so the rapid takes exactly as long as the train that stops at 辻堂.

**Reading a real 運転時分表: `time` = previous stop's 発 → this stop's 着, and round PER HOP.** The
table's own 運転時分 column is the run from a row to the NEXT one, and it lists 停車場 — operating points
(宇都宮タ, 川口, 井堀) carry times and are not stops, so their segments fold into the following stop. A
station passed with no timing point leaves the column blank and its run is carried on the next timed
leg. **The ↓ marks in 着/発 are the stopping pattern itself** — a ↓ in 着 with a time in 発 is a timed
pass, not a stop.

Rounding has two candidate rules and they are not interchangeable. Utsunomiya `1545E` was authored as
the **difference of rounded CUMULATIVE times**, which reproduces 22 of its 23 committed values against
21 for per-hop — the better rule in isolation, and the reason its total reads 101 min against a true
100:45. But cumulative rounding makes a hop depend on everything upstream, so two diagrams sharing a
stretch legitimately disagree on it, which `check_hop_agreement` forbids: `3520M` reaches 宇都宮 46.5 min
into its run where `1545E` starts there, and cumulative yields 雀宮 = 5 against `1545E`'s 6. **Per-hop,
half-up, is the rule whenever the line has more than one diagram** — it reproduced the shared 宇都宮→小山
stretch hop-for-hop from a different table, which is what confirmed it. (2026-08-22.)

**Two diagrams covering the same stations must agree.** Within a line this is automatic (the hops are authored once and reused). Across lines it is not: Yamanote `1208G` and Keihin-Tōhoku `727B` run an identical stop sequence 田端↔品川, and three hops there had drifted apart by 2026-08-21. Where such a corridor exists, the disagreeing hop is the defect — reconcile before trusting either as the baseline for a skip run.

#### `pa_at_station` Array (At-Station Announcements) — Optional

Optional list of PA tracks that play **while train stopped at platform**, after pre-arrival announcements have finished. Defaults to absent / empty (typical stops have none).

Semantic split:

- **`pa`** — pre-arrival sequence (dep-from-prev, this-arr): plays while train moving toward this stop.
- **`pa_at_station`** — at-platform sequence (transfer info, connection notices, etc.): plays after train has come to rest.

| Value | Meaning |
|-------|---------|
| *(field omitted)* or `[]` | No at-station PAs — default for typical 2-PA stops |
| `["transfer-info"]` | Single at-station track |
| `["transfer-info", "connection-notice"]` | Multiple at-station tracks |

**Filename convention:** same as `pa`. Slugs resolve to `pa/<slug>.mp3` — both lists share single `pa/` folder.

**Example** (Tokaido 1865E 国府津 — junction with Gotemba Line, with extra at-platform announcements):

```json
{
    "name": "国府津",
    "pa": ["ninomiya-dep-down-futsu", "kozu-arr-down-futsu"],
    "pa_at_station": ["kozu-stopping-1-down-futsu", "kozu-stopping-2-down-futsu"],
    "sta": ["JT14"],
    "sta_cut": 18,
    "time": 6,
    "sta_code": "JT14"
}
```

State machine consumes both lists, surfaces separate "STOPPING at station" display state during `pa_at_station` playback. Display-side semantics → [DISPLAY.md](DISPLAY.md); state-machine flow → `app.py` `PASimulator._next_pa`.

#### `sta` Array (STA Melodies)

| Value | Meaning |
|-------|---------|
| *(field omitted)* | No STA melody — passing stations and arrival termini (last stop, where train doesn't depart again). An *origin* terminus DOES get `sta`, since train departs from there. |

**Exception — an arrival terminus MAY carry `sta` when the recording is an arrival announcement.** The slot holds platform audio, not strictly departure melodies: some stations have several STA entries, one of which plays after the train stops with the doors open. Saikyo 1349F's 川越 carries the end-of-journey announcement this way (`kawagoe-down`, `sta_cut` at the chime→voice boundary). `validate_data.py` forbids `sta` only on passing stops and `pre_stops`, and `_next_sta` has no terminus branch, so this needs no code change. Whether the user plays it is their choice. (2026-08-08, author decision.)
| `["JC01"]` | Single STA audio file |
| `["JC01", "JC01_1"]` | Multiple entries — **order is significant, see below** |

**THE LAST ENTRY IS THE DEPARTURE MELODY, and `sta_cut` is ITS property.** Since 2026-08-11 the two positions behave differently and are not interchangeable:

| position | behaviour |
|---|---|
| **last entry** | plays from the head and **loops `[0, sta_cut)`** until the user cuts it or the train departs. A further press is the conductor's cut — jump to `sta_cut`, play the tail once, stop |
| **any earlier entry** | plays straight through, once. **`sta_cut` does not apply to it at all** |

So a stop's single `sta_cut` describes only the last file, and ordering `["melody", "announcement"]` would loop the announcement at a cut measured for the melody. The corpus's only multi-entry stop is Saikyo 大宮 — `["JA26_OMY-down", "JA26_OMY_1-down"]`, an arrival door-opening announcement first, the melody last, which is the correct order and the real platform sequence.

**Ordering is an authoring rule, not a validated one.** `validate_data.py` checks that a multi-entry stop carries a `sta_cut` inside its last file — it cannot tell which file is the melody, and reversing 大宮's two entries passes it (both run 12–14 s, so the cut stays in range). Telling a melody from an announcement needs content analysis, which on this corpus has repeatedly returned confident wrong answers. Get the order right when authoring; the ear is the only gate on it.

**Note:** `sta` field contains actual audio filenames (without `.mp3`). Two filename styles coexist (renderer treats both identically):
- **Legacy** — `sta_code` plus optional disambiguation suffix (`JC01`, `JC01_OSK`, `JK47_OMY`).
- **Slug** — `{station}_{platform}_{song-id}` (e.g. `tokyo_4_jr-sh5-1`, `kinshicho_4_gota-del-vient`). Filename = metadata store; see `/sta-make` for slug rules and song-id catalog.

When a station has no STA melody, **omit field entirely** rather than setting `[]` or `[""]`.

#### `sta_code` Field (Station Numbering)

| Value | Meaning |
|-------|---------|
| `"JC01"` | Official JR East station code (used for line-specific data lookup) |
| `null` | Station has no official code (e.g., Kawagoe Line stations) |

**Format:** `[Line Prefix][Number]` (e.g., `JC01`, `JK47`, `JA08`)
- Line prefixes: JC (Chuo), JK (Keihin-Tohoku), JA (Saikyo), JE (Keiyo), JY (Yamanote), JT (Tokaido), JN (Nambu), JJ (Joban), JU (Takasaki *and* Utsunomiya — one prefix, two shipped lines, separate folders and separate pools), JO (Sōbu Rapid / Yokosuka)
- No 3-letter suffixes in `sta_code` (those go in `sta` field only)
- **Note:** `sta_code` = route-local — used by `upper_lcd.py` to render station code badge. Line-independent station metadata lives in `data/stations.json`.

#### `sta_cut` Field

| Value | Meaning |
|-------|---------|
| `0` | No STA melody / full track plays |
| `>0` | Seconds into STA track where melody is **cut** and closing-door announcement (station-attendant voice, "ドアが閉まります") begins. Integer or one-decimal float (e.g. `15.6`) — runtime accepts float seconds. Use extra precision when music→voice gap is narrow and a 1 s rounding error would land in wrong region. |

---

## Supported Lines

All lines share central `data/translations.json` (display text) and `data/stations.json` (operational metadata).

| Line | Code Prefix | Folder |
|------|-------------|--------|
| Chuo Main (中央線) | JC | `audio/chuo/` |
| Joban (常磐線) | JJ | `audio/_joban/` (WIP — not shipped) |
| Keihin-Tohoku (京浜東北) | JK | `audio/keihin/` |
| Keiyo (京葉線) | JE | `audio/keiyo/` |
| Nambu (南武線) | JN | `audio/nambu/` |
| Saikyo (埼京線) | JA | `audio/saikyo/` |
| Sōbu Rapid / Yokosuka (総武快速・横須賀) | JO | `audio/sobu/` |
| Takasaki (高崎線) | JU | `audio/takasaki/` |
| Utsunomiya (宇都宮線) | JU | `audio/utsunomiya/` |
| Tokaido (東海道線) | JT | `audio/tokaido/` |
| Yamanote (山手線) | JY | `audio/yamanote/` |

---

## Circular Routes

First and last entries in `stops[]` share same `name` (e.g. Yamanote: 大崎 appears twice). Simulator handles wrap-around automatically — no special field needed.

---

## Data Validation

Run `validate_data.py` from project root:

```bash
PYTHONUTF8=1 python validate_data.py
```

Exits 0 if clean, 1 if issues found (suitable for pre-commit / CI). Checks performed:

**Shape rules** (apply to all routes including fixtures under `audio/_*/`):

- Every stop has a `pa` field (required, because without it the downstream rules would silently bypass)
- Every stop has `sta_code` (value or `null`); value has no `_XX` suffix
- Passing stations (`pa: []`, non-first) have NO `sta`, NO `sta_cut`, NO `time`, NO `pa_at_station`
- First station has `time: 0`; all other non-passing stops have `time` set
- A stop after passing stations takes less time than the sibling diagram that stops at them, and not less than `Σ(sibling hops) − 2 × passing` (full scan only, since it needs a sibling; 13 of 31 skip segments have none and are simply not checked)
- Two diagrams sharing ≥4 consecutive hops agree on every one of them (full scan only)
- `pre_stops[]` entries have required `name` + `sta_code`; forbidden `pa` / `pa_at_station` / `sta` / `sta_cut` / `time`
- `frames[]` (if present): each entry has string `from` / `to` / `line` (shape). The semantic checks (that `from`/`to` resolve in `pre_stops+stops`, that `line` resolves in `lines.json`, and that frames abut and tile start→end) surface via the loader smoke-check, `route_loader._resolve_frames`
- Compound translations (key contains `・`) encode `english` as `"A&\nB"` form (no space before `&`, newline immediately after)

**Cross-reference rules** (skipped for fixtures under `audio/_*/`, which use out-of-scope strings and lack real audio by design):

- Every stop `name` has entry in `data/translations.json`
- Route-level `dest` and stop-level `dest` overrides translated
- Route-level `type` has entry in `data/train_types.json`
- Every file referenced by `pa` / `pa_at_station` / `sta` exists on disk (`pa/<name>.mp3`, `sta/<name>.mp3`)

**Lines + transfers** (apply at `data/` level, so the fixture-skip is not applicable):

- `lines.json` `category` is one of `jr_east` / `shinkansen` / `non_jr`
- `lines.json` badge `icon` slugs resolve to PNGs under `data/line_icons/<icon>.png` (base + variants)
- `stations.json` `transfers[]` entries: base slug exists in `lines.json`; `slug.variant` matches a declared variant; dot-notation depth ≤ 1 (e.g. `slug.variant` OK; `slug.variant.subvariant` rejected)
- `stations.json` `transfers_by_view[VIEW]` ops:
  - `drop` entries match a base slug already in `transfers[]` (typo + stale-data guard)
  - `add` entries match an **exact** ref in `transfers[]` (a base slug is rejected, since it would re-admit the route's own variant too), and are not cancelled by a `drop` of the same base in the same view (drop runs last, so that combination is dead config)
  - `edit` keys match a base slug in `transfers[]`; edit values resolve in `lines.json` (base + variant if dotted)
  - `rows` array sums to `len(transfers) - len(drop)`, which promotes a runtime-fallback warning to an authoring-time error
- `route.json` `transfer_view`: at least one stop on route has `stations.json` `transfers_by_view` entry for it. Direction = route → stop → station (NOT station → route). Reverse direction would false-positive on station configs that are forward-looking or test-only (e.g. `大船`/`武蔵小杉`'s `JO_north`).

**Inventory check:**

- `stations.json` `code_3` count matches documented 22

Issues are grouped by location (route or top-level data file). **Add new checks by editing `validate_data.py`, and don't re-embed them here.**

### Things the validator can't catch (verify by eye)

- **Hyphenation** of a station's English name. A prefix takes one, a single place name does not, and no reading encodes which it is. (Macrons and spelling *are* checked now: `check_station_translations` re-derives `english` from `furigana`.)
- PA track mapping: whether `tokyo-dep.mp3` really is the announcement recorded *after* Tokyo and references the correct next stop. The validator only checks that the file exists.
- Slug song-id correctness for `sta` files. The slug is a metadata store, and the validator cannot tell `kinshicho_4_gota-del-vient` from `kinshicho_4_horidei`.

---

## Windows console encoding

If `validate_data.py` (or any script printing Japanese) hits `UnicodeEncodeError: 'charmap'`, prefix with `PYTHONUTF8=1` (or `set` / `$env:` it in cmd / PowerShell). Project file I/O already passes `encoding='utf-8'`, so issue = console output only.

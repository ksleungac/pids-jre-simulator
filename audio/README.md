# audio/

Per-line PA + STA audio + `route.json`. Line-specific IRL/sim mental model lives here; schema → [DATA_FORMAT.md](../DATA_FORMAT.md); renderer → [DISPLAY.md](../DISPLAY.md) / [DISPLAY_E235.md](../DISPLAY_E235.md).

> **EDIT-CONTRACT** — refuses:
> - Schema content (`route.json` fields, `sta_code` grammar, filename grammar) → [DATA_FORMAT.md](../DATA_FORMAT.md)
> - Display behavior (renderer logic, mode cycling, view-cycler) → [DISPLAY.md](../DISPLAY.md) / [DISPLAY_E235.md](../DISPLAY_E235.md)
> - Recording-chain how-to (splitting / trimming / verifier) → `/pa-make` / `/sta-make` skills
> - Stale content — drop bullets when reality changes; no accumulated history
>
> Voice: compressed reference entries — tables and short complete sentences, no narrative padding. Per [CLAUDE.md § Writing tone](../CLAUDE.md).

---

## Folder convention

- `<line>/<diagram>/{pa,sta,route.json}` = standard shape. Diagram = scheduled JR EAST service ID (`1865E`, `1217F`, `3922E`, …). Multi-diagram lines hold one folder per service.
- **Yamanote = flat** (no diagram folder). Single canonical service IRL — diagram layer redundant. See [§ JY](#jy--yamanote-山手線) below.
- `_archive/<line>/<diagram>/` = preserved-not-shipped past diagrams. Dredge on glob lookup when adding new diagram on same line — old splits often reusable.
- `_mock/main/` = curated preview catalog. Details → [`_mock/main/README.md`](_mock/main/README.md).
- Filename-as-store + `_*` prefix rules → [conventions.md § Naming](../.claude/rules/conventions.md).
- **PA filename default = legacy numeric** (`1.mp3`, `2.mp3`, …). Lines using descriptive `{station}-{dep|arr}` shape (DATA_FORMAT's preferred convention for new lines) are flagged in their entry. Schema reference → [DATA_FORMAT § PA Track Filename Convention](../DATA_FORMAT.md).

---

## Per-line notes

Ordered by JR EAST line code. Standard fields omitted (= follows convention). Entries get extended only where line has something IRL-specific or sim-quirky worth recording.

### JA — Saikyo (埼京線)

- **Name:** 埼京線 / Saikyō Line
- **Diagrams:** `1349F`, `759K`

### JC — Chuo (中央線)

- **Name:** 中央線 / Chūō Line
- **Diagrams:** `1654T`, `916H`

### JE — Keiyo (京葉線)

- **Name:** 京葉線 / Keiyō Line
- **Diagrams:** `780Y_1510Y` (two consecutive service IDs concatenated into one diagram folder; physical line stays Keiyo, not actual through-running)
- **Sim quirks:** long PASSING leg 千葉みなと → 稲毛海岸 (~80s) — train crosses 千葉貨物 freight terminal. Relevant for OCR autodriver state-machine (badge stays PASSING across the freight gap).
- **Audio quirks:** Tokyo-end stations have elaborate (>20s) STA melodies IRL — music duration outliers in splitter parse are real, not segment-merge artifacts.

### JJ — Joban (常磐線)

- **Name:** 常磐線 / Jōban Line
- **Diagrams:** `tsuchiura` (station-name descriptive — folder name deviates from scheduled-ID convention)
- **Status: WIP — not shipped; moved to `audio/_joban/` (2026-07-15) so the incomplete route stays out of the release picker.** `route.json` incomplete — missing `time` on every stop, missing `sta_code` on every stop, mixed PA filename convention (Roman codes `JT1/JJ1` mixed with numerics `4/5/6`), terminus 土浦 has `sta: []` instead of field-omit. `validate_data.py` flags are expected, not real bugs. Don't auto-fix; await user pass.

### JK — Keihin-Tohoku (京浜東北線)

- **Name:** 京浜東北線 / Keihin-Tōhoku Line
- **Diagrams:** `1275A`, `727B`
- **Sim quirks:** `727B` extends `stops[41..45]` past route-level `dest` (磯子, idx 40) to 大船 — operational reference for through-running. Sim terminates at 磯子 (route-level dest), not at `len(stops) - 1`. See [DISPLAY.md § Unified State Machine](../DISPLAY.md).

### JN — Nambu (南武線)

- **Name:** 南武線 / Nambu Line
- **Diagrams:** `4027F`, `603F`

### JO — Sōbu Rapid / Yokosuka (総武線快速・横須賀線)

- **Name:** 総武線快速 / Sōbu Rapid Line (shares physical line with Yokosuka Line — `lines.json` slug `yokosuka_sobu`, variants `sobu` + `yokosuka`)
- **Diagrams:** `1217F`
- **IRL:** physical through-service 久里浜 → 東京 (Yokosuka portion) → 成田空港 (Sōbu Rapid + Narita Line continuation). LCD shows combined journey with pre-Tokyo Yokosuka portion dim/passed.
- **Sim quirks:**
  - Pre-route Yokosuka stations (横須賀 → 新橋) modeled via `pre_stops` in `route.json`; simulator's active route begins at 東京. See [DATA_FORMAT § pre_stops Array](../DATA_FORMAT.md).
  - IRL frames swap at 千葉 (Sōbu Rapid yields to Sōtobō / Narita Line views). Modeling deferred — see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues) (`display` label).
  - 千葉 has no STA melody IRL — terminus-only station for through-service inbound, `sta` + `sta_cut` omitted on that stop.
- **Audio quirks:** PA = descriptive (`{station}-{dep|arr}`).
- **Naming asymmetry:** folder `audio/sobu/` ↔ `lines.json` slug `yokosuka_sobu`. Same physical line, different namespaces. Don't conflate when refactoring either side.

### JT — Tokaido (東海道線)

- **Name:** 東海道線 / Tōkaidō Line
- **Diagrams:** `1865E`, `3535E`
- **Sim quirks:** `1865E` carries `pa_at_station` on 国府津 — junction with Gotemba Line, extra at-platform announcements. `3535E` omits it (same junction, different recording scope).
- **Audio quirks:** `3535E` PA = descriptive with **underscore** separator (`atami_arr`, `chigasaki_arr`, `fujisawa_dep`, …). Deviates from DATA_FORMAT.md § PA Track Filename Convention's hyphen-preferred shape. Don't normalize — renderer treats both identically. (`1865E` PA = default numeric.)

### JU — Takasaki (高崎線)

- **Name:** 高崎線 / Takasaki Line
- **Diagrams:** `3922E`
- **Audio quirks:** PA = descriptive (e.g. `kita-ageo-arr`).

### JY — Yamanote (山手線)

- **Name:** 山手線 / Yamanote Line
- **IRL:** circular (大崎 → 大崎), single canonical service. Both Inner Loop (内回り) and Outer Loop (外回り) covered by same `route.json` — wrap-around handled by simulator, no special field.
- **Sim quirks:**
  - Dest-cycle via sticky override at 6 stops (田町 / 神田 / 鶯谷 / 目白 / 代々木 / 恵比寿). Resolved at load time by `route_loader.finalize_route`. See [DATA_FORMAT § Stop-Level Destination Override](../DATA_FORMAT.md).
  - Circular wrap-around: `stops[0].name == stops[-1].name` (大崎 appears twice).
  - Compound dest dot = halfwidth `･` (U+FF65), not fullwidth `・` (U+30FB) — IRL PIDS form. Data canonical in halfwidth across 6 compound-dest entries (品川･東京, 東京･上野, …) + matching translations.json keys.
- **Audio quirks:** STA filename = `<sta_code>_<code_3>.mp3` when station has `code_3` (e.g. `JY01_TYO.mp3`), bare `<sta_code>.mp3` otherwise (e.g. `JY04.mp3`).
- **Layout anomaly:** flat shape — `audio/yamanote/{pa,sta,route.json}` directly, no diagram folder. Single canonical service = diagram layer redundant.

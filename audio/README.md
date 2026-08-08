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

- `<line>/{pa,sta}/` + `<line>/<diagram>/route.json` = **the shape, on every shipped line.** Diagram = scheduled JR EAST service ID (`1865E`, `1217F`, `1208G`, …); multi-diagram lines hold one folder per service, single-diagram lines still get one. `route.json` carries `"audio_root": ".."` → [DATA_FORMAT § audio_root Field](../DATA_FORMAT.md).
- `<line>/<diagram>/{pa,sta,route.json}` (audio beside route.json) = the pre-pool shape, retired 2026-08-08. Only `_joban/tsuchiura` and `_mock/main` still use it.
- `_archive/<line>/<diagram>/` = preserved-not-shipped past diagrams. Dredge on glob lookup when adding new diagram on same line — old splits often reusable.
- `_mock/main/` = curated preview catalog. Details → [`_mock/main/README.md`](_mock/main/README.md).
- Filename-as-store + `_*` prefix rules → [conventions.md § Naming](../.claude/rules/conventions.md).
- **PA filenames are descriptive on every shipped line** — `{station}-{dep|arr}-{direction}` plus a train-type tier where two diagrams' announcements differ. `{station}` on a `-dep` slug is the previous **stopping** station, which differs from the previous array element on any diagram that skips. `pa_at_station` uses `{station}-stopping[-N]-{direction}`. Numeric slugs survive only under `_joban/` and `_mock/`. Schema reference → [DATA_FORMAT § PA Track Filename Convention](../DATA_FORMAT.md).
- **STA filenames take no direction token** — a melody belongs to a platform, and direction is only ever a proxy for it. Keihin (`-south`) and saikyo (`-down`) carry one because they were pooled before that rule; they are kept, not copied.

---

## Per-line notes

Ordered by JR EAST line code. Standard fields omitted (= follows convention). Entries get extended only where line has something IRL-specific or sim-quirky worth recording.

**Every line carries an `Audio state` field — the committed record of what has actually been done to its recordings.** The by-ear gate is the only authority on audio here, and its tool writes verdicts to `audio_src/`, which is gitignored: it never reaches a fresh clone or the other PC. So a later session cannot tell "verified months ago" from "never touched", re-audits a finished corpus with derived thresholds, and reports defects that are not defects (2026-08-08, Saikyo — the ear then returned 25/25 with every cut unchanged). This field is that missing record.

State it as what was done, with the date, and say **unverified** where nothing is known — an absent verdict is not a pass. Facets worth naming: `sta_cut` placement checked by ear, KAK spliced, silences trimmed, complete melody loops confirmed, PA checked by ear. Update it in the same commit as the work, exactly like `validate_data.py`.

The whole-loop rule (keep a whole number of melody loops, trim a trailing partial — at the data's best availability, never a recut trigger) is recent and applied leniently to lines that predate it: an older line unchecked against it is recorded as such, not treated as broken.

### JA — Saikyo (埼京線)

- **Name:** 埼京線 / Saikyō Line
- **Diagrams:** `1349F` (快速 → 川越, through 川越線), `759K` (各駅停車 → 大宮)
- **Sim quirks:** `759K` extends `stops[19..23]` past route-level `dest` (大宮, idx 18) to 川越 — operational reference, no audio. Same shape as JK `727B`. `1349F` skips 北赤羽, 浮間舟渡, 戸田, 北戸田.
- **Audio quirks — this line's STA is mostly melody with NO closing-door announcement.** 18 of 24 files are melody only; `JA25` (北与野) has a full one (2番線、ドアが閉まります), `JA14`/`JA24` fragments. So `detect_sta_cut.py` reporting `music_end == voice_start` across this line is diagnosing the absent voice, not a misplaced cut — it derives `voice_start` from a level change and finds the next melody block. Cuts land in an inter-loop silence and are correct there; the whole set passed by ear 25/25 on 2026-08-08. Verify speech with `audio_id.has_speech()`, never a spectral band — a known announcement here reads hf/lf 0.002, i.e. identical to melody.
- **大宮 and 川越 carry arrival-type STA.** The `sta` slot on this line is not only departure melodies: 大宮 holds two entries, one of which plays at arrival with the doors open, and 川越 (an arrival terminus) carries the end-of-journey announcement. That makes 川越 an exception to `DATA_FORMAT.md`'s "arrival termini omit `sta`" — deliberate, author decision 2026-08-08.
- **Audio layout:** pooled — `audio/saikyo/{pa,sta}/` with `"audio_root": ".."` in both diagrams. PA slugs carry `-down` plus a `-kaisoku` / `-kakueki` tier where the two diagrams' announcements differ. The four Kawagoe-line STA files were renamed station-derived (`nisshin-down`, …) because their originals were bare numerics with no station identity — those stations have `sta_code: null`. See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Audio state:** STA — `sta_cut` verified by ear 25/25 on 2026-08-08, every value inherited unchanged; no KAK on this source (measured, and the amplitude path is valid here — peak sits 14–22 dB over the music). PA — checked by ear 2026-08-08, all pass. Silences not re-trimmed; leads 0.00–0.40 s, trails to 0.66 s, cosmetic.

### JC — Chuo (中央線)

- **Name:** 中央線 / Chūō Line
- **Diagrams:** `1654T`, `916H`
- **Audio state:** STA — trimmed through `sta-make` Phase B and verified by ear 23/23 on 2026-07-25; 国立's incomplete 2nd loop spliced; no KAK on this source. PA — lead-trimmed and verified by ear 53/53 on 2026-07-25.

### JE — Keiyo (京葉線)

- **Name:** 京葉線 / Keiyō Line
- **Diagrams:** `780Y_1510Y` (two consecutive service IDs concatenated into one diagram folder; physical line stays Keiyo, not actual through-running)
- **Sim quirks:** long PASSING leg 千葉みなと → 稲毛海岸 (~80s) — train crosses 千葉貨物 freight terminal. Relevant for OCR autodriver state-machine (badge stays PASSING across the freight gap).
- **Audio quirks:** Tokyo-end stations have elaborate (>20s) STA melodies IRL — music duration outliers in splitter parse are real, not segment-merge artifacts.
- **Terminus PA is a `-dep`, not an `-arr`.** 東京's single PA says 次は終点、東京 — the announcement made leaving 八丁堀 — so it is `hatchobori-dep-up`. Contradicts `pa-make`'s "terminus single PA = `{this}-arr`" default; read the content before assigning a role.
- **Audio layout:** pooled — `audio/keiyo/{pa,sta}/` with `"audio_root": ".."`. PA carries `-up`; STA is verbatim (no direction token). See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Audio state:** STA — **checked by ear 2026-08-08, clean.** Only 新木場 needed work: two lead splices (81 ms + 32 ms) for the documented stutter, `sta_cut` 9.3 → 9.19. Every other cut inherited unchanged. PA — unverified, no by-ear pass on record.

### JJ — Joban (常磐線)

- **Name:** 常磐線 / Jōban Line
- **Diagrams:** `tsuchiura` (station-name descriptive — folder name deviates from scheduled-ID convention)
- **Status: WIP — not shipped; moved to `audio/_joban/` (2026-07-15) so the incomplete route stays out of the release picker.** `route.json` incomplete — missing `time` on every stop, missing `sta_code` on every stop, mixed PA filename convention (Roman codes `JT1/JJ1` mixed with numerics `4/5/6`), terminus 土浦 has `sta: []` instead of field-omit. `validate_data.py` flags are expected, not real bugs. Don't auto-fix; await user pass.
- **Audio state:** n/a — unshipped WIP, outside the pooled corpus. Gets a state when the route is completed and the line ships.

### JK — Keihin-Tohoku (京浜東北線)

- **Name:** 京浜東北線 / Keihin-Tōhoku Line
- **Diagrams:** `1275A`, `727B`
- **Sim quirks:** `727B` extends `stops[41..45]` past route-level `dest` (磯子, idx 40) to 大船 — operational reference for through-running. Sim terminates at 磯子 (route-level dest), not at `len(stops) - 1`. See [DISPLAY.md § Unified State Machine](../DISPLAY.md).
- **Audio quirks — this line defeats every absolute-dB threshold in the toolchain.** The recordings carry continuous train ambience at **−15 to −37 dB** and are limited flat (PA peaks above 0 dBFS on 59 of 78 files; STA music sits at ~0 dB with under 1 dB of range). Three separate tools produced confident nonsense before this was noticed: `validate_pa.py` flags 74/78 (its −40 dB gate is *below* the noise floor, so files never trimmed are flagged too); `trim_pa_silence.py`'s `floor+12` gate lands at −3.6 to −25 dB, i.e. above ordinary speech, exactly the Step 7.4 failure mode; and `sta-make` Step 7.5's peak-amplitude KAK detector cannot fire because the KAK here is *quieter* than the music. **Use relative / spectral measures on this line, and treat any absolute-dB verdict as unverified.** Per-file loudness also splits hard by diagram — 1275A median −10.3 LUFS vs 727B −23.2 — but `audio.py` normalizes every file to −15 LUFS at playback, so that gap is inaudible in the app and only shows up in the raw-mp3 verifiers.
- **Audio layout:** pooled — `audio/keihin/{pa,sta}/` with `"audio_root": ".."` in both diagrams. PA slugs carry a direction token (`-south`) and a train-type tier only where the two diagrams keep distinct takes (`-kaisoku` / `-kakueki`). See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Audio state:** PA — trimmed and validated 2026-07-27. STA — **KAK spliced by ear 2026-08-08** across 44 files (43.1 s removed, mean 979 ms), cuts retuned in the same pass, whole-loop rule applied, verified by ear 45/45. Done by hand on the verifier's waveform; the 2026-07-27 auto-splice attempt on this line came out under-tight on 40 of 45 and was reverted — see § Audio quirks for why every threshold in the toolchain misreads this source.
- **新子安 (JK14) plays 鶴見 (JK15)'s melody.** JK14's own recording failed the by-ear gate; the stop references `JK15-south` at 鶴見's cut so it plays identically. The unused take is preserved at `audio/_archive/keihin/sta/JK14-south.mp3`. Author decision 2026-08-08.

### JN — Nambu (南武線)

- **Name:** 南武線 / Nambu Line
- **Diagrams:** `4027F`, `603F`
- **Sim quirks:** `4027F` 快速 stops at 12 of 26; `603F` 各駅停車 at all 26. 603F shares one melody across two stops — `Yagawa_Nishi-Kunitachi` serves both 矢川 and 西国立.
- **Audio quirks:** the two diagrams share **no PA at all** — 0 of 19 same-role pairs, at near-zero correlation (0.0001–0.06), i.e. wholly unrelated recordings rather than alternate takes. STA is the opposite: 23 of 23 identical. 4027F also carried `Nishifucho`, byte-identical to 603F's `Nishifu` (西府) under a second name; the pool keeps `Nishifu`.
- **Audio layout:** pooled — `audio/nambu/{pa,sta}/` with `"audio_root": ".."`. PA is `{station}-{dep|arr}-down-{kaisoku|kakueki}`; STA verbatim, keeping its capitalised English-name style (`Musashi-Kosugi`) — pooling is a move, not a rename. See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Audio state:** STA — **verified by ear 24/24 on 2026-08-08**, every file spliced (64.1 s removed, mean 2670 ms — the heaviest pass of any line). Most files carried both a lead artifact and a ~2 s incomplete trailing loop, so the whole-loop rule did most of the work here. Cuts retuned in the same pass. PA — unverified, no by-ear pass on record.

### JO — Sōbu Rapid / Yokosuka (総武線快速・横須賀線)

- **Name:** 総武線快速 / Sōbu Rapid Line (shares physical line with Yokosuka Line — `lines.json` slug `yokosuka_sobu`, variants `sobu` + `yokosuka`)
- **Diagrams:** `1217F`
- **IRL:** physical through-service 久里浜 → 東京 (Yokosuka portion) → 成田空港 (Sōbu Rapid + Narita Line continuation). LCD shows combined journey with pre-Tokyo Yokosuka portion dim/passed.
- **Sim quirks:**
  - Pre-route Yokosuka stations (横須賀 → 新橋) modeled via `pre_stops` in `route.json`; simulator's active route begins at 東京. See [DATA_FORMAT § pre_stops Array](../DATA_FORMAT.md).
  - IRL frames swap at 千葉 (Sōbu Rapid yields to Sōtobō / Narita Line views). Modeling deferred — see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues) (`display` label).
  - 千葉 has no STA melody IRL — terminus-only station for through-service inbound, `sta` + `sta_cut` omitted on that stop.
- **Audio quirks:** PA = descriptive (`{station}-{dep|arr}-down`). STA uses the rich `{station}_{platform}_{song-id}` slug and carries **no** direction token — the platform field already discriminates it, and appending one would land inside the globbable song-id field (4 stations share `gota-del-vient`, 3 share `horidei`).
- **Audio layout:** pooled — `audio/sobu/{pa,sta}/` with `"audio_root": ".."`. See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Naming asymmetry:** folder `audio/sobu/` ↔ `lines.json` slug `yokosuka_sobu`. Same physical line, different namespaces. Don't conflate when refactoring either side.
- **Audio state:** cut and split after the `sta-make` / `pa-make` skills existed, so it was produced to spec (author, 2026-08-08). No verdict file survives on this machine — `audio_src/` is gitignored — so treat it as specced-at-authoring rather than independently re-verified.

### JT — Tokaido (東海道線)

- **Name:** 東海道線 / Tōkaidō Line
- **Diagrams:** `1865E` (普通, stops everywhere), `3535E` (快速アクティー, skips 辻堂 / 大磯 / 二宮 / 鴨宮). Both 下り to 熱海.
- **Sim quirks:** `1865E` carries `pa_at_station` on 東京 (pre-departure boarding notice) and on 国府津 — junction with Gotemba Line, a dwell notice then a departure-imminent one. `3535E` omits both (same junction, different recording scope).
- **Audio quirks — the two diagrams share no PA at all.** All 31 same-role pairs are separate takes (correlation 0.08–0.79, nothing near 1.0), sourced from two independent recordings, so every PA file carries a type token. STA is the opposite: all 21 pairs are sample-identical.
- **Audio layout:** pooled — `audio/tokaido/{pa,sta}/` with `"audio_root": ".."` in both diagrams. PA is `{station}-{dep|arr}-down-{futsu|acty}`; `pa_at_station` is `{station}-stopping[-N]-down-{type}`. STA verbatim, no direction token. The old per-diagram conventions (1865E numeric, 3535E underscore-descriptive) are both gone — pooling forces one namespace. See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Audio state:** STA — **KAK on all 21 files, spliced by ear 2026-08-08** (13.9 s removed, 375–1241 ms per file, mean 662 ms); all 21 `sta_cut` retuned in the same pass; verified by ear 21/21. PA — unverified, no by-ear pass on record.
- **The KAK here is QUIETER than the melody, so the Step 7.5 amplitude path cannot see it.** A peak-ratio sweep reported zero across the line while every single file had one. Same class as JK, different cause: there the source is limited flat, here the click is simply low-level. Find it on the verifier's waveform and splice by hand; do not reach for a detector.

### JU — Takasaki (高崎線)

- **Name:** 高崎線 / Takasaki Line
- **Diagrams:** `3922E`
- **Audio quirks:** PA = descriptive (e.g. `kita-ageo-arr-down`). STA is bare station (`ageo`, `kumagaya`) with no platform and no direction token — if a 上り diagram ever lands, add the **platform** field the slug convention already defines rather than a direction token.
- **Audio layout:** pooled — `audio/takasaki/{pa,sta}/` with `"audio_root": ".."`. See [WIP_audio_pooling.md](../WIP_audio_pooling.md).
- **Audio state:** as JO — produced post-skill to spec (author, 2026-08-08), no surviving verdict file.

### JY — Yamanote (山手線)

- **Name:** 山手線 / Yamanote Line
- **IRL:** circular (大崎 → 大崎), single canonical service. Both Inner Loop (内回り) and Outer Loop (外回り) covered by same `route.json` — wrap-around handled by simulator, no special field.
- **Sim quirks:**
  - Dest-cycle via sticky override at 6 stops (田町 / 神田 / 鶯谷 / 目白 / 代々木 / 恵比寿). Resolved at load time by `route_loader.finalize_route`. See [DATA_FORMAT § Stop-Level Destination Override](../DATA_FORMAT.md).
  - Circular wrap-around: `stops[0].name == stops[-1].name` (大崎 appears twice).
  - Compound dest dot = halfwidth `･` (U+FF65), not fullwidth `・` (U+30FB) — IRL PIDS form. Data canonical in halfwidth across 6 compound-dest entries (品川･東京, 東京･上野, …) + matching translations.json keys.
- **Audio quirks:** STA filename = `<sta_code>_<code_3>.mp3` when station has `code_3` (e.g. `JY01_TYO.mp3`), bare `<sta_code>.mp3` otherwise (e.g. `JY04.mp3`).
- **Audio layout:** pooled — `audio/yamanote/{pa,sta}/` with `"audio_root": ".."` in `1208G/`. This line was flat until 2026-08-08 (its audio was already in pool position; only `route.json` moved down a level). PA carries `-inner`, the 内回り the recordings are; STA verbatim. IRL it is a single canonical service, so the diagram ID is a real service number rather than a meaningful partition.
- **Audio state:** STA — **verified by ear 30/30 on 2026-05-09**, no fails, no notes (author pass; verdicts recovered from `audio_src/yamanote/sta_verify_results.json` and committed here 2026-08-08). Predates the whole-loop rule, so that facet is unchecked — leniency applies. PA — unverified, no by-ear pass on record. The 2026-08-08 pooling renamed PA and moved `route.json`; no audio byte changed.

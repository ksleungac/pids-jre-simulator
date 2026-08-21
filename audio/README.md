# audio/

Per-line PA + STA audio + `route.json`. Line-specific IRL/sim mental model lives here; schema → [docs/DATA_FORMAT.md](../docs/DATA_FORMAT.md); renderer → [docs/DISPLAY.md](../docs/DISPLAY.md) / [docs/DISPLAY_E235.md](../docs/DISPLAY_E235.md).

> **EDIT-CONTRACT** — refuses:
> - Schema content (`route.json` fields, `sta_code` grammar, filename grammar) → [docs/DATA_FORMAT.md](../docs/DATA_FORMAT.md)
> - Display behavior (renderer logic, mode cycling, view-cycler) → [docs/DISPLAY.md](../docs/DISPLAY.md) / [docs/DISPLAY_E235.md](../docs/DISPLAY_E235.md)
> - Recording-chain how-to (splitting / trimming / verifier) → `/pa-make` / `/sta-make` skills
> - Stale content — drop bullets when reality changes; no accumulated history
>
> Voice: compressed reference entries — tables and short complete sentences, no narrative padding. Per [CLAUDE.md § Writing tone](../CLAUDE.md).

---

## Folder convention

- `<line>/{pa,sta}/` + `<line>/<diagram>/route.json` = **the shape, on every shipped line.** Diagram = scheduled JR EAST service ID (`1865E`, `1217F`, `1208G`, …); multi-diagram lines hold one folder per service, single-diagram lines still get one. `route.json` holds route data only and writes no `audio_root` — absent means the pool → [DATA_FORMAT § audio_root Field](../docs/DATA_FORMAT.md).
- `<line>/<diagram>/{pa,sta,route.json}` (audio beside route.json) = the pre-pool shape, retired 2026-08-08. Only `_joban/tsuchiura` and `_mock/main` still use it.
- **Adding a new line** — author it into the pool from the start: cut into `audio/<line>/{pa,sta}/` with the filename grammar in [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md), put `route.json` at `audio/<line>/<diagram>/`, and write no `audio_root` (absent = pooled). `/pa-make` and `/sta-make` splitter templates already target that shape. A second diagram on the same line then pays only for what is genuinely new — that is the whole point of the pool.
- **A short measured melody before `sta_cut` is not a defect.** 西国分寺 (`JC17`, 2.9 s of audio before a 6.0 s cut) was flagged during the migration and confirmed correct by the author. Don't re-raise it.
- **Cross-station melody reuse exists but is not dedupable** (~57 MB — 高尾 / 荻窪 / 西八王子 share a tune). No two different stations share an identical FILE: each STA is melody + that station's own closing announcement. Collapsing them would mean splitting the two apart and changing how STA plays — [#120](https://github.com/ksleungac/pids-jre-simulator/issues/120).
- `_archive/<line>/<diagram>/` = preserved-not-shipped past diagrams. Dredge on glob lookup when adding new diagram on same line — old splits often reusable.
- **A `_`-prefixed route cannot be previewed in atlas mode, by design.** `font_atlas` skips any path segment starting with `_` when it walks its text sources (`font_atlas.py:155`), so an unshipped route's station names are never baked and drawing one raises a declaration error that reads exactly like a regression. `preview_display.py --route _joban/tsuchiura` fails on 土浦 for this reason and always has. The picker, `/build` and the baker all exclude these routes the same way; only a hand-written sweep reaches them.
- `_mock/main/` = curated preview catalog. Details → [`_mock/main/README.md`](_mock/main/README.md).
- Filename-as-store + `_*` prefix rules → [conventions.md § Naming](../.claude/rules/conventions.md).
- **PA filenames are descriptive on every shipped line** — `{station}-{dep|arr}-{direction}` plus a train-type tier where two diagrams' announcements differ. `{station}` on a `-dep` slug is the previous **stopping** station, which differs from the previous array element on any diagram that skips. `pa_at_station` uses `{station}-stopping[-N]-{direction}`. Numeric slugs survive only under `_joban/` and `_mock/`. Schema reference → [DATA_FORMAT § PA Track Filename Convention](../docs/DATA_FORMAT.md).
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
- **大宮 and 川越 carry arrival-type STA.** The `sta` slot on this line is not only departure melodies: 大宮 holds two entries, one of which plays at arrival with the doors open, and 川越 (an arrival terminus) carries the end-of-journey announcement. That makes 川越 an exception to `docs/DATA_FORMAT.md`'s "arrival termini omit `sta`" — deliberate, author decision 2026-08-08.
- **Audio layout:** pooled — `audio/saikyo/{pa,sta}/`. PA slugs carry `-down` plus a `-kaisoku` / `-kakueki` tier where the two diagrams' announcements differ. The four Kawagoe-line STA files were renamed station-derived (`nisshin-down`, …) because their originals were bare numerics with no station identity — those stations have `sta_code: null`. Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Audio state:** STA — `sta_cut` verified by ear 25/25 on 2026-08-08, every value inherited unchanged; no KAK on this source (measured, and the amplitude path is valid here — peak sits 14–22 dB over the music). PA — checked by ear 2026-08-08, all pass. Silences not re-trimmed; leads 0.00–0.40 s, trails to 0.66 s, cosmetic.

### JC — Chuo (中央線)

- **Name:** 中央線 / Chūō Line
- **Diagrams:** `1654T` (快速), `916H` (中央特快)
- **Audio layout:** pooled — `audio/chuo/{pa,sta}/`. **This is the one line whose PA carries no direction token** (0 of 53 files, against 100 % on every other line): it was pooled 2026-07-26, before that rule existed, and retrofitting means touching every file and both `pa` arrays again. It is 上り, so a reverse (下り) Chūō diagram would collide — stamp `-up` across the 53 slugs at that point, not before. Two takes of the same announcement are kept apart by a `-{diagram}` tier (`kanda-arr-1654T` / `kanda-arr-916H`), the only line using that form; every other line's split pairs differ by train type instead.
- **Audio state:** STA — trimmed through `sta-make` Phase B and verified by ear 23/23 on 2026-07-25; 国立's incomplete 2nd loop spliced; no KAK on this source. PA — lead-trimmed and verified by ear 53/53 on 2026-07-25.

### JE — Keiyo (京葉線)

- **Name:** 京葉線 / Keiyō Line
- **Diagrams:** `780Y_1510Y` (two consecutive service IDs concatenated into one diagram folder; physical line stays Keiyo, not actual through-running)
- **Sim quirks:** long PASSING leg 千葉みなと → 稲毛海岸 (~80s) — train crosses 千葉貨物 freight terminal. Relevant for OCR autodriver state-machine (badge stays PASSING across the freight gap).
- **Audio quirks:** Tokyo-end stations have elaborate (>20s) STA melodies IRL — music duration outliers in splitter parse are real, not segment-merge artifacts.
- **Terminus PA is a `-dep`, not an `-arr`.** 東京's single PA says 次は終点、東京 — the announcement made leaving 八丁堀 — so it is `hatchobori-dep-up`. Contradicts `pa-make`'s "terminus single PA = `{this}-arr`" default; read the content before assigning a role.
- **Audio layout:** pooled — `audio/keiyo/{pa,sta}/`. PA carries `-up`; STA is verbatim (no direction token). Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Audio state:** STA — **checked by ear 2026-08-08, clean.** Only 新木場 needed work: two lead splices (81 ms + 32 ms) for the documented stutter, `sta_cut` 9.3 → 9.19. Every other cut inherited unchanged. PA — unverified, no by-ear pass on record.

### JJ — Joban (常磐線)

- **Name:** 常磐線 / Jōban Line
- **Diagrams:** `tsuchiura` (station-name descriptive — folder name deviates from scheduled-ID convention)
- **Status: WIP — not shipped; moved to `audio/_joban/` (2026-07-15) so the incomplete route stays out of the release picker.** `route.json` incomplete — missing `time` on every stop, missing `sta_code` on every stop, mixed PA filename convention (Roman codes `JT1/JJ1` mixed with numerics `4/5/6`), terminus 土浦 has `sta: []` instead of field-omit. `validate_data.py` flags are expected, not real bugs. Don't auto-fix; await user pass.
- **Audio state:** n/a — unshipped WIP, outside the pooled corpus. Gets a state when the route is completed and the line ships.

### JK — Keihin-Tohoku (京浜東北線)

- **Name:** 京浜東北線 / Keihin-Tōhoku Line
- **Diagrams:** `1275A`, `727B`
- **Sim quirks:** `727B` extends `stops[41..45]` past route-level `dest` (磯子, idx 40) to 大船 — operational reference for through-running. Sim terminates at 磯子 (route-level dest), not at `len(stops) - 1`. See [docs/DISPLAY.md § Unified State Machine](../docs/DISPLAY.md).
- **Audio quirks — this line defeats every absolute-dB threshold in the toolchain.** The recordings carry continuous train ambience at **−15 to −37 dB** and are limited flat (PA peaks above 0 dBFS on 59 of 78 files; STA music sits at ~0 dB with under 1 dB of range). Three separate tools produced confident nonsense before this was noticed: `validate_pa.py` flags 74/78 (its −40 dB gate is *below* the noise floor, so files never trimmed are flagged too); `trim_pa_silence.py`'s `floor+12` gate lands at −3.6 to −25 dB, i.e. above ordinary speech, exactly the Step 7.4 failure mode; and `sta-make` Step 7.5's peak-amplitude KAK detector cannot fire because the KAK here is *quieter* than the music. **Use relative / spectral measures on this line, and treat any absolute-dB verdict as unverified.** Per-file loudness also splits hard by diagram — 1275A median −10.3 LUFS vs 727B −23.2 — but `audio.py` normalizes every file to −15 LUFS at playback, so that gap is inaudible in the app and only shows up in the raw-mp3 verifiers.
- **Audio layout:** pooled — `audio/keihin/{pa,sta}/`. PA slugs carry a direction token (`-south`) and a train-type tier only where the two diagrams keep distinct takes (`-kaisoku` / `-kakueki`). Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Audio state:** PA — trimmed and validated 2026-07-27. STA — **KAK spliced by ear 2026-08-08** across 44 files (43.1 s removed, mean 979 ms), cuts retuned in the same pass, whole-loop rule applied, verified by ear 45/45. Done by hand on the verifier's waveform; the 2026-07-27 auto-splice attempt on this line came out under-tight on 40 of 45 and was reverted — see § Audio quirks for why every threshold in the toolchain misreads this source.
- **新子安 (JK14) plays 鶴見 (JK15)'s melody.** JK14's own recording failed the by-ear gate; the stop references `JK15-south` at 鶴見's cut so it plays identically. The unused take is preserved at `audio/_archive/keihin/sta/JK14-south.mp3`. Author decision 2026-08-08.

### JN — Nambu (南武線)

- **Name:** 南武線 / Nambu Line
- **Diagrams:** `4027F`, `603F`
- **Sim quirks:** `4027F` 快速 stops at 12 of 26; `603F` 各駅停車 at all 26. 603F shares one melody across two stops — `Yagawa_Nishi-Kunitachi` serves both 矢川 and 西国立.
- **Audio quirks:** the two diagrams share **no PA at all** — 0 of 19 same-role pairs, at near-zero correlation (0.0001–0.06), i.e. wholly unrelated recordings rather than alternate takes. STA is the opposite: 23 of 23 identical. 4027F also carried `Nishifucho`, byte-identical to 603F's `Nishifu` (西府) under a second name; the pool keeps `Nishifu`.
- **Audio layout:** pooled — `audio/nambu/{pa,sta}/`. PA is `{station}-{dep|arr}-down-{kaisoku|kakueki}`; STA verbatim, keeping its capitalised English-name style (`Musashi-Kosugi`) — pooling is a move, not a rename. Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Audio state:** STA — **verified by ear 24/24 on 2026-08-08**, every file spliced (64.1 s removed, mean 2670 ms — the heaviest pass of any line). Most files carried both a lead artifact and a ~2 s incomplete trailing loop, so the whole-loop rule did most of the work here. Cuts retuned in the same pass. PA — unverified, no by-ear pass on record.

### JO — Sōbu Rapid / Yokosuka (総武線快速・横須賀線)

- **Name:** 総武線快速 / Sōbu Rapid Line (shares physical line with Yokosuka Line — `lines.json` slug `yokosuka_sobu`, variants `sobu` + `yokosuka`)
- **Diagrams:** `1217F`
- **IRL:** physical through-service 久里浜 → 東京 (Yokosuka portion) → 成田空港 (Sōbu Rapid + Narita Line continuation). LCD shows combined journey with pre-Tokyo Yokosuka portion dim/passed.
- **Sim quirks:**
  - Pre-route Yokosuka stations (横須賀 → 新橋) modeled via `pre_stops` in `route.json`; simulator's active route begins at 東京. See [DATA_FORMAT § pre_stops Array](../docs/DATA_FORMAT.md).
  - IRL frames swap at 千葉 (Sōbu Rapid yields to Sōtobō / Narita Line views). Modeling deferred — see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues) (`display` label).
  - 千葉 has no STA melody IRL — terminus-only station for through-service inbound, `sta` + `sta_cut` omitted on that stop.
- **Audio quirks:** PA = descriptive (`{station}-{dep|arr}-down`). STA uses the rich `{station}_{platform}_{song-id}` slug and carries **no** direction token — the platform field already discriminates it, and appending one would land inside the globbable song-id field (4 stations share `gota-del-vient`, 3 share `horidei`).
- **Audio layout:** pooled — `audio/sobu/{pa,sta}/`. Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Naming asymmetry:** folder `audio/sobu/` ↔ `lines.json` slug `yokosuka_sobu`. Same physical line, different namespaces. Don't conflate when refactoring either side.
- **Audio state:** STA — **verified by ear 16/16 on 2026-08-11 against the loop spec**, 13 files spliced, 50.867 s removed, cuts retuned in the same pass. Two distinct shapes: six lead artifacts trimmed at `[0.000, ~0.8–0.94]`, and seven SURPLUS MELODY LOOPS removed — `kinshicho` −11.49 s (`sta_cut` 28.6 → 17.11), `sakura` −10.43 s, `shisui` −8.23 s, `airport-terminal-2` −5.66 s. This line's recordings run long and hold multiple complete loops, so the whole-loop trim is where its work is. Supersedes the specced-at-authoring status it carried before; being cut post-skill predicted JU's clean sheet, not this. PA — unverified, no by-ear pass on record.

### JT — Tokaido (東海道線)

- **Name:** 東海道線 / Tōkaidō Line
- **Diagrams:** `1865E` (普通, stops everywhere), `3535E` (快速アクティー, skips 辻堂 / 大磯 / 二宮 / 鴨宮). Both 下り to 熱海.
- **Sim quirks:** `1865E` carries `pa_at_station` on 東京 (pre-departure boarding notice) and on 国府津 — junction with Gotemba Line, a dwell notice then a departure-imminent one. `3535E` omits both (same junction, different recording scope).
- **Audio quirks — the two diagrams share no PA at all.** All 31 same-role pairs are separate takes (correlation 0.08–0.79, nothing near 1.0), sourced from two independent recordings, so every PA file carries a type token. STA is the opposite: all 21 pairs are sample-identical.
- **Audio layout:** pooled — `audio/tokaido/{pa,sta}/`. PA is `{station}-{dep|arr}-down-{futsu|acty}`; `pa_at_station` is `{station}-stopping[-N]-down-{type}`. STA verbatim, no direction token. The old per-diagram conventions (1865E numeric, 3535E underscore-descriptive) are both gone — pooling forces one namespace. Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Audio state:** STA — **KAK on all 21 files, spliced by ear 2026-08-08** (13.9 s removed, 375–1241 ms per file, mean 662 ms); all 21 `sta_cut` retuned in the same pass; verified by ear 21/21. PA — unverified, no by-ear pass on record.
- **The KAK here is QUIETER than the melody, so the Step 7.5 amplitude path cannot see it.** A peak-ratio sweep reported zero across the line while every single file had one. Same class as JK, different cause: there the source is limited flat, here the click is simply low-level. Find it on the verifier's waveform and splice by hand; do not reach for a detector.

### JU — Takasaki (高崎線)

- **Name:** 高崎線 / Takasaki Line
- **Diagrams:** `3922E`
- **Audio quirks:** PA = descriptive (e.g. `kita-ageo-arr-down`). STA is bare station (`ageo`, `kumagaya`) with no platform and no direction token — if a 上り diagram ever lands, add the **platform** field the slug convention already defines rather than a direction token.
- **Audio layout:** pooled — `audio/takasaki/{pa,sta}/`. Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Audio state:** STA — **checked by ear 2026-08-11 against the loop spec: clean.** No splices needed, every inherited `sta_cut` unchanged — the first line to come through a loop-spec pass with nothing to fix. Produced post-skill to spec (author, 2026-08-08), which is evidently why. PA — unverified, no by-ear pass on record.

### JU — Utsunomiya (宇都宮線)

- **Name:** 宇都宮線 / Utsunomiya Line (東北本線). Shares the JU code with 高崎線 above; separate folder, separate pool.
- **Diagrams:** `1545E` (普通 宇都宮 → 東京 上り, 上野東京ライン, through-running to 東海道線 熱海 — `dest` is 熱海 while the modelled stops end at 東京) · `3520M` (快速ラビット 黒磯 → 上野 上り). 3520M is the only diagram covering the 黒磯–宇都宮 section, and the only one that skips: 10 passing stations between 小山 and 上野.
- **Audio quirks — the PA source defeats Whisper's segment timestamps.** It is an announcement compilation (23 min for a 1 h 50 m run), and segment-level timestamps drift up to ~7 s on it, re-anchoring at long pauses; short probe clips drift the other way. **Word-level timestamps are the clock** — they agreed with the measured waveform block onsets to within 0.6 s on all five long announcements, where the segment pass was 6–7 s out. Anything built off the segment pass on this source will be wrong.
- **Live-conductor (肉声) announcements are separated, not shipped.** `1545E`'s recording carries five: per-station arrival times, car formation, the 小金井 coupling stand, 小山 platform/connection times, and the closing thanks at 東京. They are cut into `audio_src/utsunomiya/conductor/` so no PA file holds one. `3520M`'s source is far heavier — its conductor speaks at nearly every stop — and the author asked for the machine voice only, so about a third of that recording is excluded.
- **Separating the two voices is an F0 measurement, and it only works at BLOCK scale.** On this line the conductor sits at **136–145 Hz** and the automated voice at **212–225 Hz**, calibrated against `audio_src/utsunomiya/conductor/` and the shipped pool — they separate with nothing in between. Measure median F0 over an `audio_id.structure` block (announcement-sized, hundreds of voiced frames). Do **not** measure per Whisper segment (its `start` drifts on a compilation, so the window describes the wrong audio — the conductor's own time recital read 154 Hz then 249 Hz mid-sentence) and do **not** measure per word (too few frames; it chopped single sentences into three alternating verdicts). The English automated voice reads lower than the Japanese one — a short dep file that is mostly English lands near 190 Hz and looks borderline; transcribe it rather than re-tuning the threshold.
- **Audio layout:** pooled — `audio/utsunomiya/{pa,sta}/`. PA slugs are `{station}-{dep|arr}-up`. STA carries the **platform** field (`kuroiso_1`) because its source covers several platforms at one station — the case JU/Takasaki's note anticipates. Grammar → [DATA_FORMAT § Pool filename grammar](../docs/DATA_FORMAT.md).
- **Station times come from the author's own 運転時分 table, not estimates** (2026-08-20). The table lists 停車場 — operating points — so 宇都宮タ, 川口 and 井堀 appear in it and are NOT stops on this diagram; their segments fold into the following stop, and reading the table naively shifts every downstream station by one. `time` is whole minutes, so each stop's value is the difference of ROUNDED cumulative times, which keeps every displayed cumulative figure right; the run is 101 min against a true 100:45. **小山's arrival PA was 20 ms from its last English word** and was re-cut 0.5 s longer from the source — the four other segments whose boundary lands on a conductor entry have 0.59–0.80 s of room and were left alone.
- **`3520M` times come from the author's 運転時分表 too, but rounded PER HOP, not cumulatively.** Read them off the 着/発 columns (`time` = previous stop's 発 → this stop's 着) and fold the operating points — 宇都宮タ, 川口, 井堀 carry times and are not stops. The **↓ marks are the passing pattern outright**, and they agree with the on-board announcement: 10 passed stations, 23 stops. Cumulative rounding is the better rule and is what `1545E` used (it reproduces 22 of its 23 committed values against 21 for per-hop) — but it **cannot be used here**, because it makes a hop depend on everything upstream, and 3520M reaches 宇都宮 46.5 min into its run where 1545E starts there. It yields 雀宮=5 against 1545E's 6 and trips `check_hop_agreement`. Per-hop half-up is the only rule satisfying both, and it reproduces the shared 宇都宮→小山 stretch exactly.
- **This diagram is where the skip gate got its upper tolerance.** 大宮→浦和 is 7:30 NON-STOP against 1545E's 6:15 of running plus a stand at さいたま新都心 — the express is genuinely slower, which the 制限速度 column explains (60 km/h through 新都心, 9:22 morning peak). 赤羽→上野 needs it too, for a different reason: at 9:30 against 1545E's 10:00 the Rabbit really is faster, and only half-up rounding ties them at 10. So one segment is genuinely slower and one is a rounding artifact — both clear the gate, and only the first is a claim about the railway. See `validate_data.py` `TIME_SKIP_OVER_SLACK`; at 2 it admits 大宮→浦和 with ZERO margin (8 against a limit of 8), so a further +1 there would trip on data the author considers correct. The tolerance costs the gate its Tōkaidō 3535E case, noted there.
- **`hoshakuji_1` is a platform-1 recording, but this train uses platform 6** (運転時分表 線 column). The closing announcement names its platform aloud, so the file says 1番線 where the diagram is at 6 — the same mismatch `higashiwashinomiya_2` was constructed to avoid. Not repaired; flagged.
- **`3520M` PA notes.** Cut 2026-08-21 from block boundaries, so no cut crosses a voice change. Naming splits at 宇都宮: **黒磯 → 宇都宮 is bare `-up`** (the Rabbit stops at every station there, so the announcements are generic and a future 普通 diagram reuses them; nothing else covered this section), **宇都宮 → 上野 is `-up-kaisoku`** (`1545E` already owns the bare names over that stretch, and the Rabbit's own announcements differ — they carry the 「〜の次は〜に止まります」 suffix). `kuroiso-stopping-up` is the origin's at-platform announcement, wired as `pa_at_station`. **Several English announcements transcribe as nothing** on this source — the language-locked pass drops them silently, and one 25 s English 上野 arrival came back as the 「ご視聴ありがとうございました」 hallucination; re-transcribe the window alone and auto-detect finds it. The block layout is what identifies them: short-JA-dep · short-EN-dep · long-JA-arr · long-EN-arr.
- **Audio state:** PA — `3520M` **verified by ear 45/45 on 2026-08-22**, machine voice only (the conductor is excluded throughout; see the F0 note above). `1545E` **verified by ear 46/46 on 2026-08-17**, cut from word-level onsets and then hand-spliced start/end silence only; no conductor material needed removing, which is what confirmed the boundaries. STA — **collected station by station from 黒磯 southward**, one source video per station; this line has no single through-run recording, so each station is its own cut-and-verify pass. `kuroiso_1`, **verified by ear 1/1 on 2026-08-18**, two complete ~9.5 s loops kept, `sta_cut` **20.99** set by ear (music ends 20.68, voice at 21.02 — a **30 ms** pre-voice gap, deliberately far tighter than the 250–400 ms Yamanote-derived default; the ear is the gate and it passed, so do not "correct" it toward the band). 那須塩原, 西那須野 (shared by 野崎 and 片岡), 矢板, 蒲須坂, 氏家, 宝積寺 and 岡本 follow below — those seven are north of 宇都宮 and pool-ahead. **`1545E` itself is complete: all 23 non-terminus stops carry a melody, every one passed by ear on 2026-08-18**, and `西那須野`'s file serves 雀宮, 小金井 and 間々田 as well as its own station.
- **那須塩原 (`nasushiobara`) — verified by ear 1/1 on 2026-08-18.** One complete ~12.5 s loop + closing announcement, `sta_cut` **12.87** (90 ms pre-voice). The trailing **partial loop** (~3.9 s, roughly a third of a loop) was spliced out with its gap — `[12.871, 19.095]`, 6.224 s — so the whole-loop rule is satisfied. Its source warns of this shape outright: *"この駅は時間がない上、曲のテンポも遅い為、ほとんど途中切りです"* — short dwell, slow tempo, melodies usually cut partway, so a complete loop here is the good case rather than the expected one. Platform is NOT in the filename: a single Whisper read of the announcement said 9番線, unverified and not obviously fitting a station this size — omit rather than guess (the convention allows it). **Correlation cannot locate a loop boundary on this file** and that is not a defect: the repeat was already removed, and on this line's other source a real repeat reads r≈0.98 against ≤0.25 here. Do not rebuild a detector for it — the ear placed this cut.
- **西那須野 (`nishinasuno_3`) — verified by ear 1/1 on 2026-08-18.** `sta_cut` **30.93** (90 ms pre-voice). Three complete 8.40 s loops, all kept — the ~1.9 s gaps between them are the melody's own pause, not silence to splice. Platform is verified rather than guessed: the announcement says 3番線, matching the source's own chapter label. **野崎 and 片岡 share this melody** and point at this file.
- **矢板 (`yaita`) — verified by ear 1/1 on 2026-08-18.** `sta_cut` **11.53** (110 ms pre-voice). One loop kept; the 1.36 s partial restart after it was spliced out with its gap (`[11.400, 15.473]`). Its source carries two takes of two different songs (r=0.010) and no chapter list, so which of the two the tags name — 「すみれの花咲く頃」 or 「浜千鳥」 — is **not established**; the second take is the one cut. Platform NOT in the filename: the announcement reads 3番線 but nothing corroborates it, same treatment as 那須塩原.
- **蒲須坂 (`kamasusaka_1`) — verified by ear 1/1 on 2026-08-18.** `sta_cut` **10.34** (120 ms pre-voice). One loop kept; loop 2 ran 0.33 s short of the loop end and was spliced out whole (`[10.056, 20.536]`). Platform corroborated by the source's chapter list, which also makes this the only 1番線 take that is neither 非密着収録 nor 音割れ.
- **On this line an incomplete loop is removed, however nearly complete.** 蒲須坂's loop 2 was 96 % of the loop and still came out; 那須塩原 and 矢板 lost theirs at ~33 % and ~16 %. Only whole loops are kept, and 西那須野 keeps three. Saikyo's 77 %-tail precedent does not transfer here — propose removal, not retention, when a tail measures short.
- **氏家 (`ujiie_1`) — 「ムーンストーン」, `sta_cut` **9.36**, verified by ear 2026-08-18.** Its source records this melody in use for **two days**; it is pooled anyway, because the diagram is already a mosaic of eras (its PA is 2017, its STA takes span 2003–2022) and no single date is being departed from. The station's シンコペーション take is archived as `ujiie_1_syncopation` (`sta_cut` 10.25, also passed by ear).
- **宝積寺 (`hoshakuji_1`) — verified by ear 1/1 on 2026-08-18.** `sta_cut` **10.54** (80 ms pre-voice). 「風と共に」（2014年～2022年）, one loop kept. Platform and era both from the source's chapter list.
- **岡本 (`okamoto_2`) — 「メロディー」, `sta_cut` **10.0**, verified by ear 2026-08-18.** A pre-2009 take and 非密着収録, chosen over the station's own シンコペーション for variety; the ear passed it despite the recording distance. The シンコペーション（2017年～2022年）take is archived as `okamoto_2_syncopation` (`sta_cut` 20.48, both loops complete, also passed).
- **Every unused take is archived, but two of them cannot be named by song.** 那須塩原 and 矢板 each carry two takes drawn from 「浜千鳥」 and 「すみれの花咲く頃」, and their uploader gives hashtags rather than a chapter list, so which is which is unestablished — they sit as `nasushiobara_take1` / `yaita_take1`. **Correlation cannot settle it and should not be re-attempted**: two takes that chapter lists both name 「すみれの花咲く頃」 score **r=0.14** against each other, and all four unnamed takes score ~0.01 in every pairing though matching songs must exist among them. The method works only between close-mic'd recordings on similar chains (シンコペーション across 蒲須坂/西那須野 reads 0.79); across 非密着収録 and different arrangements it fails toward "different".
- **`higashiwashinomiya_2` is CONSTRUCTED, not recorded.** No 東鷲宮 source was found, so it is 小山 12番線's Water crown melody with 石橋 2番線's closing announcement grafted on at each file's own verified `sta_cut`. The graft is necessary because the announcement says its platform out loud: `oyama_12` would announce 12番線, and every genuine platform-2 file in the pool carries the right number with the wrong melody. A second variant using 野木's voice is archived as `higashiwashinomiya_2_altvoice`. **Nothing reasoning about provenance may treat this file as captured audio**; the recipe is `audio_src/utsunomiya/sta_src/build_sta_higashiwashinomiya.py`, which is gitignored, so this line is the record that travels.
- **The seven stations north of 宇都宮 were pool-ahead until `3520M` landed (2026-08-21), and it is the 黒磯-origin diagram they were waiting for** — all seven now carry an `sta` ref, so `verify_sta_listen` discovers them normally. Their `sta_cut` values were read back from this README into `3520M`'s `route.json`: they are the BY-EAR values and outrank anything `audio_id.structure` derives. `nasushiobara` is the one that proves it — its cut (12.87) sits inside a merged block because the ambience never reaches the silence floor, so a block-derived guess lands at 16.00 and is simply wrong. They were verified in its `--files` loose mode, whose results JSON holds only the last run's files — so their `sta_cut` values live here or nowhere (`audio_src/` is gitignored). Everything from 宇都宮 south keeps its value in `route.json` instead.
- **Two sources defeat the block detector entirely** — `utsunomiya_9` and `saitamashintoshin_3`. Continuous station ambience never reaches the silence floor, so `audio_id.structure` returns one merged block and cannot locate the melody→voice boundary. Whisper timestamps placed those two; don't re-derive them from blocks. **And Whisper itself returns nothing on a whole file of this kind** — `utsunomiya_9`'s full 40 s source transcribed as 0 segments with a misdetected language, which reads exactly like "this take has no closing announcement". It has one: 「9番線、ドアが閉まります」, plain on the 4.9 s tail past `sta_cut`. Run `--speech` on the voice region, never the whole file; the same failure garbles platform numbers on every station here (岡本 came back as 「あ、閉まります」 whole-file and 「2番線…」 clipped).

#### JU — Utsunomiya sources

Every file in this line's pool traces to a public YouTube recording. **Only two of these URLs were
written down while the work happened** (`split_pa_1545E.py` and one stray link inside a stored
`.description`); the rest were recovered afterwards from the author's chat log and confirmed against
the source durations each splitter recorded — `ujiie_src.mp3` is 231.71 s against a 3:52 video whose
description is byte-for-byte the chapter list in the splitter, and so on for all 28 that predate the record-it-now step. (`3520M`'s source is the 29th and was written down as it was taken.) That recovery is
why `/sta-make` and `/pa-make` now record the source at the moment it is taken.

`audio_src/` is gitignored, so this table is the only copy that travels.

| source | recordist | feeds |
|---|---|---|
| `q6Bt_iPrmMI` | East Railway Redwing | all 46 PA files (10:17–33:28 of the run) |
| `YBPhFjKe3cs` | 全国駅メロチャンネル | `kuroiso_1`; 4 archive takes (春待ち風V2 ×2, 南風の行方 ×2) |
| `q9HtUS9pkhQ` | 全国駅メロチャンネル | `nasushiobara`; `nasushiobara_take1` |
| `ZHStp0sXc2o` | ちいぼす | `nishinasuno_3` @1:21 — also serves 雀宮 / 小金井 / 間々田 / 野崎 / 片岡; `nishinasuno_3_sumire` @1:03 |
| `tUGlbdn9AW0` | 全国駅メロチャンネル | `yaita` @0:25; `yaita_take1` |
| `h1qdfSll6bo` | ちいぼす | `kamasusaka_1` @0:37; `kamasusaka_1_sumire` @0:00 |
| `V_sj9r5wboY` | ちいぼす | `ujiie_1` (ムーンストーン) @0:48; `ujiie_1_syncopation` @0:27 |
| `5wMcMh1IrlU` | ちいぼす | `hoshakuji_1` @1:08 |
| `fe0WYL8v8Ss` | ちいぼす | `okamoto_2` (メロディー) @0:00; `okamoto_2_syncopation` @0:45 |
| `2iQgX1wf1po` | ケヨポコ チャンネル short | `utsunomiya_9` — whole video |
| `OF9FenehHvU` | ちいぼす | `ishibashi_2` @1:07 |
| `HvqIqzC4eDw` | 関石ライン / Kamishi Line | `jichiidai_1` @0:00 |
| `vs01n2iUinE` | 下今市 | `oyama_12` @0:31 |
| `dZSxtLoX2GU` | Kent_K | `nogi_2` — whole video |
| `sxWkg-HLNAc` | 全国駅メロチャンネル | `koga_3` @1:27 |
| `A68uatMXvBI` | ちいぼす | `kurihashi_1` @0:18 |
| `Quknk5s51GQ` | 全国駅メロチャンネル | `kuki_3` @1:11 |
| `ApfKhHUexS4` | 70-000 SHINANO | `shinshiraoka_1` @0:57 |
| `AyQlPBwaq5M` | 全国駅メロチャンネル | `shiraoka_3` @1:01 |
| `nDYEPRI0Cgk` | 全国駅メロチャンネル | `hasuda_3` @1:00 |
| `aQyZXoj3UcE` | 全国駅メロチャンネル | `higashiomiya_2` @0:33 |
| `N5Leuabj8YE` | 全国駅メロチャンネル | `toro_2` @0:21 |
| `Pj8LyaaOUvg` | 京葉ラビット | `omiya_4` @2:05 |
| `VipyFnc27b4` | 音鉄DK | `saitamashintoshin_3` @0:52 |
| `4KQXOVQt-JE` | SAGAMI-LINE さがみせん | `urawa_3` @1:08 |
| `qMy_-n6b2N0` | 武蔵野快速 | `akabane_3` @1:24 |
| `DbH0eOyc6CM` | ハマ音鉄 | `oku_1` @0:00 |
| `Thfwh1JCPFg` | Ueno-Tokyo Line | `ueno_7` — whole video |
| `46fW6MgqNnQ` | µ'wing | all 45 of `3520M`'s PA files — whole video |
| — | — | `higashiwashinomiya_2` and its `_altvoice` are CONSTRUCTED from `oyama_12` + `ishibashi_2` / `nogi_2`; no source of their own |

Resolve an ID as `https://www.youtube.com/watch?v=<id>`. Two recordists carry most of the line:
**全国駅メロチャンネル** (9 sources) and **ちいぼす** (7); the other thirteen contributed one each.

**µ'wing asks that non-personal use of their audio be registered through a form** (linked from the
video description); personal-scope use is exempt. The repo was submitted to them on 2026-08-21 and
`3520M` comes out if they object. No other source on this line states terms of its own.

### JY — Yamanote (山手線)

- **Name:** 山手線 / Yamanote Line
- **IRL:** circular (大崎 → 大崎), single canonical service. Both Inner Loop (内回り) and Outer Loop (外回り) covered by same `route.json` — wrap-around handled by simulator, no special field.
- **Sim quirks:**
  - Dest-cycle via sticky override at 6 stops (田町 / 神田 / 鶯谷 / 目白 / 代々木 / 恵比寿). Resolved at load time by `route_loader.finalize_route`. See [DATA_FORMAT § Stop-Level Destination Override](../docs/DATA_FORMAT.md).
  - Circular wrap-around: `stops[0].name == stops[-1].name` (大崎 appears twice).
  - Compound dest dot = halfwidth `･` (U+FF65), not fullwidth `・` (U+30FB) — IRL PIDS form. Data canonical in halfwidth across 6 compound-dest entries (品川･東京, 東京･上野, …) + matching translations.json keys.
- **Audio quirks:** STA filename = `<sta_code>_<code_3>.mp3` when station has `code_3` (e.g. `JY01_TYO.mp3`), bare `<sta_code>.mp3` otherwise (e.g. `JY04.mp3`).
- **Audio layout:** pooled — `audio/yamanote/{pa,sta}/` (`route.json` in `1208G/`). This line was flat until 2026-08-08 (its audio was already in pool position; only `route.json` moved down a level). PA carries `-inner`, the 内回り the recordings are; STA verbatim. IRL it is a single canonical service, so the diagram ID is a real service number rather than a meaningful partition.
- **Audio state:** STA — **re-cut to the loop spec by ear on 2026-08-11**, 28 splices across 17 of 29 files, 9.521 s removed (7 ms – 2.31 s each), cuts retuned in the same pass. Author hand-work in the verifier's waveform; 12 files additionally re-passed explicitly, the rest are finished hand edits. The heavy ones are `JY05_UEN` (−2.31 s), `JY03_AKB` (−1.78 s, `sta_cut` 9.1 → 7.39, trailing partial loop) and head trims at `[0.000, …]` on `JY16` / `JY20_SBY` / `JY05_UEN`. **Why this pass existed:** the last sta track now LOOPS `[0, sta_cut)`, so a head artifact repeats on every pass and a trailing partial truncates every cycle — facets a one-shot play tolerated. Supersedes the 2026-05-09 pass (verified 30/30, no fails), which predated the whole-loop rule and left that facet unchecked. PA — unverified, no by-ear pass on record. The 2026-08-08 pooling renamed PA and moved `route.json`; no audio byte changed then.

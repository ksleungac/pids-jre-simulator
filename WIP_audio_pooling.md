# WIP — per-line shared audio pool

Migrating `audio/` from per-diagram audio folders to a **per-line shared pool**, so each
new diagram pays only for the announcements that are genuinely new.

**The goal is slope, not intercept.** This infrastructure exists so adding a diagram
does not bump the corpus size — *not* to compress what is already there. User:
*"the infrastructure saves size, or 'does not bump size up' when new diagram, not
necessarily to compress current chuo size"*. That distinction decides the PA rule below:
existing takes are kept, not merged, and the win comes from a new diagram referencing
pool slugs that already exist.

> **EDIT-CONTRACT** — holds: migration status per line, the transformation procedure, the
> naming rules, and the measured facts behind them. Refuses: schema reference (→
> [DATA_FORMAT.md](DATA_FORMAT.md)), per-line IRL notes (→ [audio/README.md](audio/README.md)).
>
> **Graduates when** every shipped line is migrated — single-diagram included, since pooling
> is now the only schema, no exceptions: fold the `audio_root` +
> naming rules into `DATA_FORMAT.md`, the per-line status into `audio/README.md`,
> then delete this file. **All nine shipped lines are migrated as of 2026-08-08 — the trigger is met.**

---

## Status

| line | diagrams | STA pooled | PA pooled | notes |
|---|---|---|---|---|
| chuo | 1654T, 916H | ☑ | ☑ | **Done + committed.** 23 STA + 55 PA (53 referenced); both trimmed, by-ear 23/23 + 53/53. Every pair is a genuine separate take — re-verified 2026-07-26 |
| keihin | 1275A, 727B | ☑ | ☑ | **Pooled 2026-07-26**, 192 → 123 files. 45 STA (35 identical pairs collapsed) + 78 PA (30 pairs are ONE recording, 4 more collapsed by ear). PA trimmed 2026-07-27; STA KAK spliced by ear 2026-08-08 (44 files, 43.1 s) |
| tokaido | 1865E, 3535E | ☑ | ☑ | **Done 2026-08-08.** 116 → 94 files. STA 21/21 identical; PA 0/31 shared, so every file carries a type token (`-futsu` / `-acty`) |
| nambu | 4027F, 603F | ☑ | ☑ | **Done 2026-08-08.** 110 → 86 files. STA 23/23 identical (+`Nishifucho`=`Nishifu`, one recording under two names); PA 0/19 shared at near-zero correlation, so uniform `-kaisoku` / `-kakueki` |
| saikyo | 1349F, 759K | ☑ | ☑ | **Done 2026-08-08**, 92 → 66 files, 28 → 22 MB. Legacy folders dropped. STA by-ear 25/25, PA all pass |
| sobu | 1217F | ☑ | ☑ | **Done 2026-08-08.** Single diagram, so a pure move: 28 PA gain `-down`, 16 STA verbatim (platform-bearing slugs) |
| takasaki | 3922E | ☑ | ☑ | **Done 2026-08-08.** Same shape — 30 PA gain `-down`, 16 STA verbatim |
| keiyo | 780Y_1510Y | ☑ | ☑ | **Done 2026-08-08.** 30 PA numeric → descriptive + `-up`, 17 STA verbatim. Roles confirmed from transcripts, not assumed — see below |
| yamanote | 1208G | ☑ | ☑ | **Done 2026-08-08**, the last flat line. Its audio was already in pool position, so only `route.json` moved into `1208G/`. 29 PA numeric → descriptive + `-inner`; 29 STA verbatim |

**Every shipped line is migrated, single-diagram included — pooling is the one schema going
forward** (author, 2026-08-08). A single-diagram line has nothing to dedup, so its migration
is a pure move plus the PA direction token, with no by-ear gate: the audio bytes are untouched
and the only gates that apply are "every reference resolves" and "every pooled file is
byte-identical to a snapshot original". This supersedes the earlier rule that single-diagram
lines could wait until they gained a second diagram, which would have left three lines on the
old shape permanently.

`_`-prefixed trees stay out: `_joban` is unshipped with an incomplete route.json, `_mock` is a
preview fixture.

---

## The mechanism

`route.json` gains one optional key:

```json
{ "audio_root": ".." }
```

Path **relative to the route.json's own folder**. Absent → audio sits beside `route.json`
(today's behaviour, unchanged). `".."` → the per-line pool.

Resolution lives in exactly one place: `route_loader.resolve_audio_root(work_dir, route_data)`.
Both consumers call it — `app.py._load_route_data` (→ `self.audio_root` → `AudioPlayer`) and
`validate_data.check_route`. Nothing else resolves audio paths.

**There is deliberately no search order.** A diagram-folder-then-pool fallback was designed
and rejected: legacy PA slugs are diagram-local (`1654T/pa/1.mp3` and `916H/pa/1.mp3` are
different announcements), so a missing file would silently resolve to the pool and play the
*wrong announcement* with no error — `critical_lessons.md §2`. One root means one resolved
path and a loud failure. Do not reintroduce a fallback.

---

## Naming rules

### Direction is the outermost token on PA — always, even on a one-direction line

**The pool is per LINE, and a line runs both ways.** Every PA names a different next station
and a different transfer set in the opposite direction, so a pool built without the token
silently collides the day a reverse diagram lands. Stamp it during the migration, when the
whole line is already being rewritten; retrofitting it later means touching every file and
every `pa` array a second time.

**STA is the exception — see the STA rule below.** A melody is a property of the platform, so
a slug that already records the platform needs no direction token; one that records only the
station does.

Take the token from the route's own `remarks.direction` — never pick one. JR runs three
different axes and which one a line uses is a property of that line:

| `remarks.direction` | token | lines |
|---|---|---|
| 上り | `up` | chuo, keiyo |
| 下り | `down` | sobu, nambu, saikyo, tokaido, takasaki |
| 南行 / 北行 | `south` / `north` | keihin |
| 内回り / 外回り | `inner` / `outer` | yamanote |

`south`/`north` also match the `transfer_view` vocabulary already in `data/stations.json`
(`JK_south`, `JA_north`, `JO_north`), so this is existing spelling, not a new one.

### STA — direction only when nothing else discriminates the platform

**STA takes no direction token. A melody belongs to a PLATFORM, and the platform is what the
name must pin down** — direction is only ever a proxy for it, since the opposite direction uses
the other platform. Author, 2026-08-08: *"sta no need up or down, only pa needs it, sta in sobu
and takasaki is by platform."* So pooling STA is a pure move, name unchanged.

Where a slug records the platform (`bakurocho_2_hassha-beru`, sobu) it already discriminates.
Where it doesn't (`ageo`, takasaki; `soga`, keiyo) the fix if a reverse diagram ever collides is
to add the **platform** field the slug convention already defines — not to bolt on a direction.

Appending a token also costs something concrete on the rich slugs: the trailing song-id field is
globbable (`ls *_gota-del-vient.mp3` shows every station playing that song — `sta-make § STA
filename convention`), and a token appended after it lands *inside* that field and breaks the
glob. On sobu that glob spans 4 stations for one song and 3 for another.

**Keihin (`-south`) and saikyo (`-down`) carry tokens on STA and keep them.** They were pooled
before this rule and renaming shipped data for tidiness is not worth the churn — but don't read
them as the pattern to copy.

Otherwise pooling STA is a pure move. Hyphen when the token IS appended, so `_` keeps meaning
"station code" and everything before the `-` stays the legacy name verbatim. STA takes no
train-type token — a melody is a property of the platform, not the service (measured: all 35
STA shared between keihin's 快速 and 各駅停車 diagrams are sample-identical).

Chūō's STA follow the legacy `sta_code` style. Newer lines (e.g. takasaki) use the richer
`{station}_{platform}_{song-id}` slug — **do not retrofit that during pooling.** It's an
independent change; pooling must stay a move.

### PA — rename to descriptive slugs

Legacy numeric PA slugs (`1.mp3`…) are diagram-local and collide in a shared pool, so a
pooled line must move to `{station}-{dep|arr}-{direction}`, then disambiguate variants:

| form | when |
|---|---|
| `{station}-{dep\|arr}-{dir}` | one recording of this announcement serves the whole line — including a take **shared by several diagrams** |
| `{station}-{dep\|arr}-{dir}-{type}` | content differs **by train type** — 「快速です」 vs 「中央特快です」 |
| `{station}-{dep\|arr}-{dir}-{diagram}` | anything else that must stay distinct — a different skip set within the same type, a different courtesy notice, different transfer ordering, **or the same words captured as a separate take** |

A tier token is earned by a **measured** difference, never applied pre-emptively for
symmetry: a file two diagrams share cannot carry either diagram's type, so a uniform
"tier everything" scheme is not expressible. Bare therefore reads as "one file serves the
line" — which is the signal a later diagram needs.

`{station}` on a `-dep` slug is the previous **stopping** station, not the previous array
element. Where diagrams skip differently the slugs then diverge on their own and need no
tier at all: keihin's 上野 approach is `tabata-dep-south-kaisoku` on the 快速 (which skips
西日暮里/日暮里/鶯谷) but `uguisudani-dep-south` on the 各駅停車.

**Known weakness — a `-dep` slug names the station DEPARTED, but the audio announces the
station AHEAD.** So two diagrams that leave the same station for a *different* next stop
produce the same slug for different announcements. On keihin the three such cases
(tabata, ueno, tokyo) happen to be separated anyway, because each earned a type token for
an unrelated reason — the uniqueness is accidental, not structural. The doc's own
counter-case defeats it: **1034T is 快速 exactly like 1654T** but skips 西荻窪/阿佐ヶ谷/高円寺,
so it would earn no type token and collide. Until the naming encodes the next station, a
migration must **check** this rather than assume it: no shared pool file may be referenced
from a different stop in different diagrams. Surfaced by `/third-man`, 2026-07-26.

Per `DATA_FORMAT.md`: `{prev}-dep` (announced after leaving the previous station) lives in
**this** stop's `pa` array; `{this}-arr` is the approach announcement.

The type tier cannot carry the whole load: **1034T is 快速 exactly like 1654T** but skips
西荻窪/阿佐ヶ谷/高円寺, so its departure announcements near those stations differ despite an
identical train type.

**Whether PA is shared or re-recorded is a per-line fact — measure it, never assume.**
The two lines migrated so far land on opposite answers, so neither generalises:

- **Chūō — every pair is a separate take.** Sourced per diagram from different recordings
  (user: *"yes, it is indeed different recordings, i took them from different sources"*).
  Of 25 916H files only **2** are the same audio as a 1654T file (豊田 arr, 東京 arr);
  re-measured 2026-07-26 with the overlap instrument below, **0 of the 15 pairs still
  split score above 0.45**. Both takes stay under `-{diagram}` slugs.
- **Keihin — the same recording is reused wherever content allows.** **30 of 47** shared
  events score 1.000, with 1275A's cut wholly inside 727B's (727B starts 0.13–1.86 s
  earlier), so they collapse to one file taken from **727B, the superset**. The 17 that
  differ are almost all explained by content: 9 name line+type+destination, 2 name the
  stop after next (the 快速 skip pattern), 2 say 終点 because 727B terminates at 磯子.
  Only **4** say the same words in two takes. User, before the measurement:
  *"most of them are the same, just at the large stations where the PA announces the train
  type and the destinations."*

Where a pair genuinely is two takes, keeping both is a valid end state — it costs nothing
a later diagram would not already pay. Collapsing one onto the other is a by-ear
preference: `_dev_scripts/ab_audio_ui.py` is the browser chooser (`--manifest` of
`{label, a, b}`; writes `<manifest>.choices.json`; keys `1`/`2`/`3` = keep A / B / both).
Run it **only on the pairs the instrument leaves undecided** — a difference readable in
the content (type, destination, terminus, skip set) needs no ear, and a measured 1.000
needs no ear either.

**Which cut survives is a measurement, not a preference.** Before discarding the loser,
align the pair and check what each holds that the other does not: trimming can remove a
lead later, nothing can restore audio truncated away now. Keep the cut that contains the
other (`critical_lessons.md §1`). Duration alone does not decide it — a longer file can be
longer at the wrong end.

---

## Tooling must be pool-aware

Pooling breaks a per-diagram assumption baked into the audio tools: **one mp3 now has
several referrers.** A tool that resolves `<work_dir>/route.json` cannot open a pooled
line at all (the pool has `sta/` and `pa/` but no route.json beside them), and one that
patches a single route.json silently desyncs the other diagrams — the pool's whole
invariant is that a shared file carries one value everywhere.

Two rules for any tool touching pooled audio:

- **Read**: accept either layout — `<dir>/route.json`, or `<dir>/*/route.json` merged
  into the union of referenced files.
- **Write**: patch **every** route.json referencing the file, not the first match.
  `verify_sta_listen.py` funnels both its writers through one `persist_cut()` helper so
  there is a single place that knows about pooling.

Status: **both verifiers are pool-aware** — `verify_sta_listen.py` (2026-07-25) and
`verify_pa_listen.py`, which share layout discovery through `_dev_scripts/audio_layout.py`
and dedupe entries so an mp3 with several referrers plays once. Pass the LINE folder.
`trim_sta_silence.py --route` and `trim_pa_silence.py` patch one file only; on a pooled
line run them bare and write the values separately.

## Git state

Lives on branch `feat/audio-pool`. Chūō is **done and committed** — `audio_root` support,
the pool itself, the pool-aware verifiers, the trim/`sta_cut` pass, and the drop of the
superseded per-diagram folders. `audio/chuo/{1654T,916H}/` now hold only `route.json`.

Split data from program when it lands — the commit-classification hook flags the mix.
Verifier / tooling changes are program; everything under `audio/<line>/` is data.

## Keihin — pooled 2026-07-26

Both diagrams are 南行 on the same 46-stop spine: 1275A 快速 → 大船 (skips 西日暮里, 日暮里,
鶯谷, 御徒町, 有楽町, 新橋), 727B 各駅停車 → 磯子 (stops 41–45 are operational reference past
its `dest`, so they carry no audio). 192 files → **123** (78 PA + 45 STA).

- **STA — all 35 same-named pairs are sample-identical**, `sta_cut` agrees on every shared
  code, so it was a pure move plus `-south`. 45 distinct melodies.
- **PA — 30 of the 47 shared events are ONE recording**, kept from 727B (whose cut contains
  1275A's whole, starting 0.13–1.86 s earlier). Nothing scores between 0.42 and 0.95, so
  the split needed no threshold judgment. 13 stay split on content grounds. The remaining
  **4 went to the ear and all resolved to 1275A's take** (`kannai-dep`, `negishi-arr`,
  `ishikawacho-dep`, `yamate-dep`), so 727B now plays the 快速 recording at 石川町/山手/根岸
  — verified free of type-, destination- and skip-specific wording before adopting.
- The mapping was hand-authored per § "Do this by hand"; a checker verified totality, ref
  coverage, collisions, type crossover, 次は/まもなく agreement, and that each `-dep` slug
  names the station `route.json` independently says is the previous stopping station.

Still to do: STA KAK splice + `sta_cut` re-validation (see below), then drop the legacy
folders:

```
rm -rf audio/keihin/1275A/pa audio/keihin/1275A/sta audio/keihin/727B/pa audio/keihin/727B/sta
```

Snapshot at `_audio_backup/keihin_pre_pool/` (112 MB, 192 files) until that lands.

Two PA files peak above 0 dBFS (`1275A/48` +2.7, `727B/39` +2.5 pre-pool) — pre-existing
clipping, noted for the trim pass. Whisper garbled four files (`727B/39`, `50`, `53`,
`1275A/45`); all four measure as normal-level full-length audio, so it is a transcription
artefact, not damaged content.

## Saikyo — pooled 2026-08-08

Both diagrams 下り on one 24-stop spine: 1349F 快速 → 川越 (through 川越線, skips 北赤羽,
浮間舟渡, 戸田, 北戸田), 759K 各駅停車 → 大宮 (stops 19–23 are past its `dest`, no audio).
92 files → **66** (41 PA + 25 STA).

- **STA — all 14 same-named pairs are sample-identical** and `sta_cut` already agreed on
  every one, so it was a pure move plus `-down`. The 4 Kawagoe-line files had bare numeric
  names (`20`–`23`, stations whose `sta_code` is null) carrying no station identity, which
  is the property the pooled-STA rule depends on — renamed station-derived by author
  decision. This is the one case where pooling is NOT a pure move.
- **PA — 11 of 19 shared events are ONE recording** (10 byte-identical, `ebisu-arr` two cuts
  of one take, kept 759K's superset). The 8 that split are all explained by content — type +
  destination, the 快速 skip notice, a different next station, 終点 wording — so none needed
  the ear and all took the `-kaisoku` / `-kakueki` type tier, matching keihin.
- **This line's STA carry almost no closing announcement** (see `audio/README.md § JA`), so
  `detect_sta_cut.py`'s flags here are not cut errors. Cut values were inherited unchanged
  and passed 25/25 by ear.
- 川越's terminus arrival announcement was sitting unreferenced in `1349F/sta/24.mp3` —
  now `sta: ["kawagoe-down"]`, `sta_cut: 3.8` on `stops[23]`. An arrival terminus carrying
  `sta` departs from `DATA_FORMAT.md`'s rule; the validator and `_next_sta` both accept it.
- `759K/pa/13.mp3` was unreferenced and matched no neighbour → `audio/_archive/saikyo/`.

## Tokaido — pooled 2026-08-08

1865E 普通 stops everywhere; 3535E 快速アクティー skips 辻堂, 大磯, 二宮, 鴨宮. Both 下り to 熱海.
116 → 94 files, and the two lines of this line land on opposite answers:

- **STA — all 21 same-named pairs are sample-identical**, so it was a pure move, names verbatim.
  3535E's four unreferenced melodies (the stations it skips) are byte-identical to 1865E's and
  simply vanish into the pool rather than needing an archive.
- **PA — 0 of 31 shared events is one recording.** Not a threshold call: the range runs 0.08–0.79
  with nothing near 1.0, the Chūō signature of two independent source recordings. Since no file is
  shared, every one needs a discriminator, so the whole PA set takes a **uniform type token**
  (`-futsu` / `-acty`) rather than the doc's mixed `-{type}` / `-{diagram}` split. Author decision:
  a uniform rule reads at a glance, and the doc's "earn the tier by a measured difference" caution
  is satisfied — the difference is measured, on every pair.

**`{prev}` on a `-dep` slug is the previous STOPPING station, and a skipping diagram makes that
bite.** Deriving it from the previous array element produced `tsujido-dep` / `ninomiya-dep` /
`kamonomiya-dep` on 3535E, for announcements that actually say 茅ヶ崎 / 国府津 / 小田原. Caught
because 3535E already carries hand-authored descriptive names, which makes it a free oracle:
assert the derivation reproduces all 31, and a wrong `{prev}` fails loudly. Use that check on any
line where one diagram is already descriptive.

**`pa_at_station` slug = `{station}-stopping-{dir}`** (keihin precedent), indexed `-1` / `-2` when
a stop has more than one — 国府津 carries a dwell notice (発車まで4分ほど) then a departure-imminent
one, and the array order is the play order. No new role word: `-departing` would read too close
to `-dep`. 3535E's unreferenced `opening.mp3` went to `audio/_archive/tokaido/3535E/pa/`.

## Keiyo — pooled 2026-08-08

Single diagram, so no dedup — the work was purely the numeric → descriptive PA mapping.
47 files move; 30 PA gain `-up`, 17 STA stay verbatim. Station slugs were taken from the
existing STA names, which are already descriptive, so nothing had to be romanised by hand.

**The `-dep` / `-arr` roles were read off transcripts, not assumed from the convention, and
one of them contradicts it.** `pa-make § PA filename convention` says a terminus's single PA is
`{this}-arr`; keiyo's file 30 at 東京 says 次は終点、東京 — a departure announcement made
leaving 八丁堀, so it is `hatchobori-dep-up`. Mid-route single PA (file 29 at 八丁堀) is
`etchujima-dep-up`, which does match. Spot-checked the pairing on both ends: first-of-pair is
次は (dep), second is まもなく (arr). The convention is a default; the audio decides, and a
mis-set role is permanent once the file is renamed.

## Chūō STA — trimmed + verified (2026-07-25)

Pooling was a pure move, so the STA arrived carrying whatever the original cuts had:
leading silence 0.14–1.90 s, trailing 1.4–5.6 s, against a ~0.2 s convention. The pool
had never been through `sta-make` Phase B. Running it: 19.7 → 9.6 MB, ~105 s of dead air
removed, 20 `sta_cut` values recomputed to a 250–350 ms pre-voice pad and written to both
diagrams, 23/23 passed by ear.

Findings worth keeping:

- **No KAK transients on this source.** A first measurement said 23/23, which was the
  instrument — a ±1.5 s window around `sta_cut` catches the voice attack itself. Searched
  strictly inside the music→voice silence, peaks read −33 to −47 dB. Skip Step 7.5 here.
- **`detect_sta_cut.py` flagged 13/23, and 12 were the documented zero-gap false
  positive** (`music_end == voice_start` exactly). Only 高尾 was a true EARLY.
- **国立 carried an incomplete 2nd melody loop** (1.06 s = 12 % of the loop, r = 0.98
  against the loop head) — spliced out, `sta_cut` 11.6 → 9.6. **新宿 (2 loops) and 立川
  (3 loops) are complete and were kept.** The rule + detection method now lives in
  `sta-make` § Pattern B.
- **立川 has no closing announcement at all** — three melody loops then silence. Not a
  cut-placement problem; the recording is missing content. Cut set to 21.0 by ear.
- **高尾 and 立川 sit inside melody by choice**, not in a silence gap — set by ear so the
  melody plays. Don't "correct" them back to the convention.

## Chūō PA — trimmed + verified (2026-07-25)

Lead-only trim (trailing silence is deliberately left alone — `pa-make` Step 7). 27 files
trimmed for 22.5 s, then 10 more corrected by hand; 53/53 passed by ear.

`trim_pa_silence.py`'s onset detector failed in **both** directions on this corpus and
needed a snapshot diff to catch — the full account and the mandatory post-trim check now
live in `pa-make` § Step 7.4. Short version: it ate 12.96 s of `tachikawa-dep-kaisoku`
(loud source, gate above the speech) and left a 1670 ms lead on `kanda-arr-916H` (quiet
source, a tick at 40 ms read as onset). Four loud-source `*-kaisoku` files were restored
untrimmed; trim them by hand if their leads ever matter.

## Resolution verified per diagram (2026-07-25)

Run through the production path (`load_route_from_dir` → `resolve_audio_root`), not a
reimplementation:

- Both diagrams resolve `audio_root` to the same `audio/chuo` pool.
- Every reference exists on disk — 1654T 32 PA + 23 STA, 916H 24 PA + 13 STA, 0 missing.
- **No cross-contamination**: 1654T references no `*-916H` slug, 916H references no
  `*-1654T` slug. The diagram suffix is what keeps two takes of the same announcement
  apart inside one folder, so this is the property the whole PA naming rule exists to buy.
- PA 29 exclusive / 21 exclusive / 3 shared — the 3 are the takes measured identical
  (豊田 arr, 東京 arr) plus 中野 arr collapsed by ear. STA 13 shared / 10 exclusive to
  1654T (the stations 916H skips) / 0 exclusive to 916H.

## Curating which take survives

Where two diagrams say the same words in different takes, both are kept by default and
the pair stays split (`kanda-arr-1654T` / `kanda-arr-916H`). Collapsing a pair is a
by-ear preference, not a rule: pick a take, copy it to the bare slug, repoint both
`route.json` files, delete the two variants. 中野 arr was collapsed this way onto 916H's
take. `_dev_scripts/ab_audio_ui.py --manifest _audio_backup/chuo_pa_ab.json` serves the
15 pairs still split on Chūō; none have been judged yet, and leaving them split is a
valid end state — it costs nothing a new diagram would not already pay.

## Do this by hand, not with a migration script

The Chūō migration was first attempted as one script that *derived* the slug mapping.
It got two decisions wrong in the dry run — it collapsed neither of the two genuinely
identical PA pairs (its PCM-hash identity test was too strict for files differing only
by an internal trim), and it applied a train-type suffix to the 東京 arrival because
that announcement lists 総武快速**線** as a transfer and the substring test matched.
User: *"i'd say don't use script to migrate, you use your own operation like human"* /
*"script is where you will things wrong"*.

**Decide the mapping yourself, write it out, check it, then run plain copies against
it.** Code is fine for *verification* (does every old file have a twin in the pool)
and for measurement — it is the inference that goes wrong.

Two mechanical traps also hit during the Chūō pass, both worth avoiding:

- **Shell state does not persist between tool calls** but the working directory does.
  A `cd x && VAR=y` block leaves `VAR` empty on the next call while leaving you inside
  `x`. Use absolute paths.
- **PowerShell `Set-Content -Encoding utf8` writes a BOM**, which makes `route.json`
  fail to parse. Edit JSON with the editor, never via shell redirection.

## Procedure for one line

1. **Snapshot first** — `cp -r audio/<line> _audio_backup/<line>_pre_pool`
   (`principles.md § "Backup before in-place destructive modification"`). `_audio_backup/`
   is gitignored; delete once validated.
2. **Identify identical STA** — same station across diagrams. Verify by content, not
   filename (see traps below).
3. **Identify identical PA** — transcribe and compare what is *said*. Waveform comparison
   does not work here; see traps.
4. Move the union into `audio/<line>/{pa,sta}/`, one file per distinct audio.
5. Rewrite each diagram's `pa` arrays to the new slugs; add `"audio_root": ".."`.
6. Delete the per-diagram `pa/` and `sta/` folders.
7. `PYTHONUTF8=1 uv run validate_data.py` — it cross-checks every referenced file exists
   through the same resolver, so a wrong slug fails loudly.
8. Launch the route and play a few PAs by ear before deleting the snapshot.

---

## Measurement traps

Determining "are these two files the same recording" is where a picking-up session will
lose time. Three methods failed here before one worked:

- **Byte hash — useless.** ID3 tags and re-encode padding differ on identical audio. It
  reported 9 of 13 Chūō STA pairs as different; all 13 are identical.
- **Strided cross-correlation — actively misleading.** Scanning lag on a 5 ms grid scores
  *identical* audio near zero whenever its true offset falls between grid points. It
  reported 3 pairs as "different recordings" that are sample-identical.
- **Whole-file comparison — wrong question for STA.** STA files run melody → `sta_cut` →
  closing announcement, so comparing whole files conflates the two.
- **Silence-trim + PCM hash — sound, but NOT the general test this doc once called it.**
  It was listed here as "exact identity, threshold-free". The *hash* is threshold-free;
  the silence-trim that ALIGNS the two cuts is not — it carries a gate (−60 dB), and the
  test only works when everything differing between the two files falls below it. Two cuts
  of one recording that differ by a lead of *content* never get aligned, so the hash
  reports "different" with full confidence and no diagnostic. **2026-07-26: it called all
  112 keihin PA files distinct; 30 pairs are sample-identical.** Their extra lead read −8
  to −23 dB — far above the gate. Use it to CONFIRM a positive cheaply, never to establish
  a negative.

**What works — the primary test is the overlap correlation; everything else is a shortcut:**

- *Alignment-tolerant identity* — `scipy.signal.correlate(a, b, mode="full", method="fft")`
  evaluates every lag; take the peak, then **re-score on the actual overlap** and require
  ~1.0. This is the one to reach for first. Do not assume the sign of the resulting shift:
  score both `+s` and `−s` on the overlap and keep the winner. (Getting that backwards
  makes every non-overlap region read full-scale, which looks like "both files hold unique
  content" for every pair — a plausible answer that is entirely an artefact.)
- *Exact identity* — silence-trim + PCM hash, subject to the limit above.
- *Same tune, different take* — chroma-CQT + DTW (`librosa.sequence.dtw`, cosine). Same
  melody ≈ 0.99, unrelated ≈ 0.70–0.86. Roll the chroma over 12 rotations for
  transposition invariance.
- *Same announcement, different take* — **transcribe it** (`_dev_scripts/transcribe_pa.py`,
  faster-whisper large-v3). Speech takes never correlate acoustically; only the text
  matches. This is the only method that answers the PA question.

**These live in `_dev_scripts/audio_id.py` — call them, do not rewrite them.** This
section used to end "regenerate rather than maintain them", citing
`principles.md § "Per-source ad-hoc scripts"`. That was a misapplication: the
per-source rule is about SPLITTERS, whose format genuinely varies per recording.
These instruments are source-invariant, and regenerating them is what made each
job hit-or-miss — 2026-08-08 rebuilt four from scratch and got the speech
question wrong on a corpus that had already passed the ear. Named instruments +
`--selftest` replaced that.

---

## Measured facts (don't re-derive)

- Corpus: 858 mp3, 585 MB. PA 382 MB, STA 180 MB.
- STA: 341 files, **240 distinct audios**; 62.8 MB of exact duplicates, overwhelmingly the
  same-station-across-diagram case created by copy-reuse when a second diagram was authored.
- Chūō STA: all **13** same-named pairs are sample-identical.
- Chūō PA: **13** pairs are content-identical *by wording* (12.6 MB of 916H's 32.2 MB),
  but only **2** are the same audio — the rest are separate takes, so this is not a
  dedup opportunity (see the PA naming rule). The boundary is geographic: east of 中野
  the two diagrams share a stopping pattern, so every announcement matches; west of it
  they diverge wherever the pattern is spoken.
- Station spine (`name` + `sta_code` sequence) is byte-identical across diagrams on all
  five multi-diagram lines.
- **Cross-station** melody reuse exists (~57 MB, e.g. 高尾/荻窪/西八王子 share a melody) but
  no two different stations share an identical *file*. Out of scope — this migration only
  collapses files that are already identical.
- A short measured melody before `sta_cut` is **not** a defect on its own. 西国分寺
  (`JC17`: 2.9 s of audio before a 6.0 s cut) was flagged during this pass and confirmed
  correct by the user. Don't re-raise it.

---

## Open / deferred

- **Bitrate normalisation.** Encoding ranges 75–321 kbps, all 48 kHz stereo, much of it
  mono content in a stereo container. Normalising to ~96–128 kbps mono would take 585 MB to
  roughly 250–350 MB — a larger lever than pooling, but lossy and irreversible, so it is a
  separate pass with its own backup. Not part of this work.
- Whether cross-station identical-melody files should ever be shared (would require
  splitting melody from the closing announcement, and changing how STA plays).

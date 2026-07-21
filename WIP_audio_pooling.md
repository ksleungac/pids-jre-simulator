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
> **Graduates when** every multi-diagram line is migrated: fold the `audio_root` +
> naming rules into `DATA_FORMAT.md`, the per-line status into `audio/README.md`,
> then delete this file.

---

## Status

| line | diagrams | STA pooled | PA pooled | notes |
|---|---|---|---|---|
| chuo | 1654T, 916H | ☑ | ☑ | **done + verified in-app.** Pool holds 23 STA + 55 PA. Deletions pending — see below |
| keihin | 1275A, 727B | ☐ | ☐ | 23.0 MB STA dupes — largest STA win |
| tokaido | 1865E, 3535E | ☐ | ☐ | 11.9 MB; PA already descriptive in 3535E (underscore separator) |
| nambu | 4027F, 603F | ☐ | ☐ | 7.6 MB |
| saikyo | 1349F, 759K | ☐ | ☐ | 2.0 MB |
| yamanote | *(flat)* | n/a | n/a | already one audio folder — the pool shape, pre-existing |
| sobu, takasaki, keiyo | single | n/a | n/a | nothing to share until a 2nd diagram lands |

Single-diagram lines need no migration. Migrate a line when it gains a diagram, or
opportunistically.

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

### STA — no renaming

STA filenames are already station-derived (`JC02.mp3`), so the same name means the same
station and pooling is a pure file move. `sta` arrays in `route.json` are untouched.

Chūō's STA follow the legacy `sta_code` style. Newer lines (e.g. takasaki) use the richer
`{station}_{platform}_{song-id}` slug — **do not retrofit that during pooling.** It's an
independent change; pooling must stay a move.

### PA — rename to descriptive slugs

Legacy numeric PA slugs (`1.mp3`…) are diagram-local and collide in a shared pool, so a
pooled line must move to `{station}-{dep|arr}`, then disambiguate variants:

| form | when |
|---|---|
| `{station}-{dep\|arr}` | only one recording of this announcement exists on the line |
| `{station}-{dep\|arr}-{type}` | content differs **by train type** — 「快速です」 vs 「中央特快です」 |
| `{station}-{dep\|arr}-{diagram}` | anything else that must stay distinct — a different skip set within the same type, a different courtesy notice, different transfer ordering, **or the same words captured as a separate take** |

Per `DATA_FORMAT.md`: `{prev}-dep` (announced after leaving the previous station) lives in
**this** stop's `pa` array; `{this}-arr` is the approach announcement.

The type tier cannot carry the whole load: **1034T is 快速 exactly like 1654T** but skips
西荻窪/阿佐ヶ谷/高円寺, so its departure announcements near those stations differ despite an
identical train type.

**Do not merge PA takes.** Unlike STA — which the user copy-reused, so the files are
literally identical — Chūō's PA was sourced per diagram from *different recordings*. Of
25 916H PA files only **2** are the same audio as a 1654T file (豊田 arr, 東京 arr); the
other 11 transcript-matched pairs say the same words in a different take. User:
*"yes, it is indeed different recordings, i took them from different sources"*. Both takes
are kept under `-{diagram}` slugs; a later diagram picks whichever it wants and adds no
file. `_dev_scripts/ab_audio_ui.py` is the browser chooser for making that call per pair
(`--manifest` of `{label, a, b}`; writes `<manifest>.choices.json`).

---

## Git state

Deliberately left uncommitted on `master` — the user commits once every line is pooled.
A branch was considered and deferred: a concurrent OCR session shares this working tree
and has an unpushed commit plus a staged deletion, so `git switch -c` would isolate
nothing and would mutate index state that session depends on.

The audio-pooling file set, disjoint from the OCR work:

```
app.py  audio.py  route_loader.py  validate_data.py  .gitignore
audio/chuo/1654T/route.json  audio/chuo/916H/route.json
audio/chuo/pa/  audio/chuo/sta/
WIP_audio_pooling.md
_dev_scripts/ab_audio.py  _dev_scripts/ab_audio_ui.py
```

Split data from program when it does land — the commit-classification hook flags the mix.

## Pending deletions (chuo)

Superseded files still on disk — nothing references them, `validate_data` is clean
with them present or absent. Left in place because the migration is uncommitted:

```
rm -rf audio/chuo/1654T/pa audio/chuo/1654T/sta audio/chuo/916H/pa audio/chuo/916H/sta
rm audio/chuo/pa/nakano-arr-1654T.mp3 audio/chuo/pa/nakano-arr-916H.mp3
```

The first frees ~93.5 MB (`audio/chuo` 172.8 → 79.4 MB); the second ~2.4 MB, left over
after 中野 arr was collapsed onto the 916H take by ear.

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

**What works:**

- *Exact identity* — decode to PCM, trim leading/trailing silence, hash. Threshold-free.
- *Alignment-tolerant identity* — `scipy.signal.correlate(a, b, mode="full", method="fft")`
  evaluates every lag; take the peak and normalise over the overlap.
- *Same tune, different take* — chroma-CQT + DTW (`librosa.sequence.dtw`, cosine). Same
  melody ≈ 0.99, unrelated ≈ 0.70–0.86. Roll the chroma over 12 rotations for
  transposition invariance.
- *Same announcement, different take* — **transcribe it** (`_dev_scripts/transcribe_pa.py`,
  faster-whisper large-v3). Speech takes never correlate acoustically; only the text
  matches. This is the only method that answers the PA question.

Scratch scripts for all of these were written ad-hoc per
`principles.md § "Per-source ad-hoc scripts"` — regenerate rather than maintain them.

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

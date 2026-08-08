---
name: sta-make
description: End-to-end STA (departure-melody + closing-door announcement) processing for a route — splitting source mp3s into per-segment files, trimming silences, validating sta_cut placement, and a by-ear verification gate. STA-only; for PA see pa-make.
triggers:
  - /sta-make
  - /split-sta
  - /verify-sta
  - sta workflow
  - split sta
  - trim sta
  - sta_cut
  - verify sta
  - listen sta
---

## Purpose

Take STA recordings (raw or already split) and produce simulator-ready per-segment mp3s with `sta_cut` values that land cleanly in the music→voice silence gap. Each STA is one departure: melody (varies by station/platform) → silence pad → closing-door announcement (staff voice).

## Instruments — use these, do not rebuild them

`_dev_scripts/audio_id.py`. Every question below has ONE method that works and several that return confident nonsense; re-deriving them per session is how a job goes hit-or-miss.

| question | call | notes |
|---|---|---|
| are these one recording? | `same_recording(a, b)` | FFT correlation over every lag, re-scored on the real overlap. `r ~1.0` = one recording |
| confirm an exact duplicate | `exact_identity(a, b)` | decoded-PCM hash. Confirms a positive; **never** establishes a negative |
| which cut do I keep? | `contains(a, b)` | keep the cut that contains the other — trimming is reversible, truncation is not |
| where are music / silence / the cut? | `structure(path, sta_cut)` | anchors on the silence run holding `sta_cut`. Do NOT anchor on "the first music block" — an internal melody break longer than 0.3 s makes that report a gap mid-melody |
| is there a closing announcement? | `has_speech(path)` | Whisper. The ONLY instrument that answers this |
| is that a repeated loop? | `loop_repeat(path, base, later)` | Pattern B, below |

**Calibrate before trusting it:** `uv run _dev_scripts/audio_id.py --selftest`. A check that has never been observed to fail has not been shown to work.

**Before auditing an existing route, read `audio/README.md`'s `Audio state` field for that line.** It is the committed record of what has been done and when. A set that already passed the ear is DONE; re-auditing it with derived thresholds produces a list of defects that are not defects. (2026-08-08: audited an already-verified Saikyo, reported several "problems", then the ear returned 25/25 PASS with every inherited cut unchanged.) `audio_src/<line>/*_verify_results.json` is the working file for a session in progress and is gitignored, so its absence proves nothing — the README is the record that travels.

## STA anatomy — what a raw recording actually contains

Read this before touching any detector. The shape above is the **finished** article; a raw capture has more in it, and every artifact pattern below is a piece of this one sequence:

```
music (loop 1)  →  [music (loop 2, often UNFINISHED)]  →  [silence]  →  KAK  →  silence  →  voice
        └── Pattern B removes an unfinished loop ──┘         └─ Pattern A removes this ─┘
                                                                              ↑
                                                                    sta_cut belongs HERE
```

**The melody loops until someone stops it.** A departure melody is played on a loop by a platform machine; a station attendant switches it off when the doors are about to close. So the recording ends the melody wherever the attendant happened to press — which is why a **2nd loop is usually unfinished**, and why the **KAK sits immediately after it**.

**Pattern A and Pattern B are the same physical event seen from two sides.** The attendant's switch-off produces *both* the truncated loop (Pattern B) *and* the click of the switch itself (Pattern A). A file showing one very often has the other — check for both rather than splicing one and moving on.

Which parts are optional:

| element | optional? | notes |
|---|---|---|
| music loop 2 | yes | absent if the attendant cut during loop 1; may be complete (keep — real content) or a stub (remove) |
| silence before KAK | **yes** | `music → KAK` with no gap is normal — the switch was thrown as the melody ended |
| KAK | yes | absent on clean sources; present across a whole line when the capture rig picked up the switch |
| silence after KAK | **no** | if the burst runs straight into speech it is the voice's own onset, not a KAK |
| voice | yes | some stations have no closing announcement at all (Chūō 立川: three loops then silence) |

### Keep WHOLE loops — trim a trailing partial, at the data's best availability

The melody plays on a loop and the attendant stops it wherever they stop it, so a recording holds
whatever fraction it holds. The finished article keeps a **whole number of loops** and trims the
leftover partial:

| the recording has | ship |
|---|---|
| 1.5 loops | 1 loop — splice the trailing half away |
| 2 loops | 2 loops — both are real content, keep them |
| 1 loop | 1 loop |

**Best availability, not a quality bar.** You never add music that is not in the recording, and a
file is not *failed* for what its source lacks. This is a trim decision, not a recut trigger.

**The ear decides where the boundary is.** Fractions guide, they do not rule: Saikyo's `JA24` came
in at 77 % of its base loop and the author kept it. See § Pattern B for the splice mechanics and
`audio_id.loop_repeat` for measuring a candidate repeat.

**Recent spec, applied leniently to lines that predate it** (author, 2026-08-08). Older lines were
never checked against it; record the state and move on rather than opening a pass. Apply it to new
splits and to any line being re-cut anyway.

Press **M** in `verify_sta_listen.py` to hear the whole melody `[0 → sta_cut]` — the 3 s head
playback cannot show loop structure, which is why that key exists.

**`sta_cut` belongs in the silence between KAK and voice** — after every artifact, before the first syllable. This is why **artifacts are spliced BEFORE `sta_cut` is validated** (Step 7.5 → 8 → 9): an unspliced KAK makes `detect_sta_cut.py` report `music_end == voice_start` (it flips at the click) and every LATE/EARLY verdict downstream is measured against the wrong landmark. A whole line reporting zero-gap is a **KAK diagnosis**, not a broken detector.

Two entry points — both are in scope:

- **Phase A (first-time split)**: source mp3 + hand-written timestamps exist; cut into per-segment files + write route.json.
- **Phase B (validation / refinement)**: per-segment files already exist; trim silences, validate `sta_cut`, by-ear gate, fix any failures.

For PA (announcement) processing, see the **pa-make** skill — separate workflow with its own conventions (no melody, no `sta_cut`, different filenames).

## When to run

- User points at `audio_src/<line>/<diagram>/` containing source mp3 + `sta_timestamps.txt` and asks to split → run Phase A → Phase B.
- User points at an existing `audio/<line>/<diagram>/` and asks to validate / verify / refine `sta_cut` → run Phase B only.

## Required input

- **Phase A**: source folder path; line + diagram (target: `audio/<line>/<diagram>/`); split scripts (if existing — ask before overwriting).
- **Phase B**: route folder path (`audio/<line>/<diagram>/`).

## Working files live under `audio_src/`

**All mid-products of this workflow stay under `audio_src/` (gitignored).** The repo only ever ships the operational outputs (`audio/<line>/<diagram>/sta/*.mp3` and `route.json`). Anything else — source mp3s, timestamps, splitter scripts, trim/splice backup snapshots, by-ear verifier results — is local-only.

If `audio_src/<line>/<diagram>/` doesn't exist yet (common when revisiting an existing route for Phase B only), create it on demand. Per-line/diagram subfolders mirror the operational hierarchy 1:1.

```
audio_src/                                # gitignored — local-only workspace
└── sobu/1217F/
    ├── sta_from_higashichiba.mp3         # STA source (may be partial coverage)
    ├── sta_timestamps.txt                # STA timestamps
    ├── split_sta.py                      # generated by this skill
    ├── sta.bak/                          # snapshot before trim/splice (Phase B Step 7)
    ├── route.json.bak                    # snapshot before trim/splice (Phase B Step 7)
    └── sta_verify_results.json           # by-ear verifier output (Phase B Step 11)
```

Defensive `*.bak`, `*.bak/`, `_sta_verify_*.json` globs are also gitignored so anything that escapes to project root or alongside operational audio doesn't accidentally get committed — but the convention is to put them in `audio_src/` from the start.

Cross-PC note: because `audio_src/` is gitignored, switching machines for further recuts requires manual cloud sync of the folder. If audio src work is rare, this is fine; if it becomes frequent, zip and stash.

---

## Phase A — First-time split

### Step 1 — Inspect

`ls` the source folder. Read `sta_timestamps.txt` if present. Identify which timestamp format applies (3-timestamp explicit-end vs 2-timestamp implicit-end — see Conventions). If `split_sta*.py` already exists, read it — the user may have customized. **If there is no `sta_timestamps.txt`** (just a `sta_src.mp3` with multiple concatenated segments), continue to Step 1.5 to auto-detect boundaries.

### Step 1.5 — Auto-detect segments (only when no `sta_timestamps.txt`)

When the source contains multiple stations' STA recordings concatenated end-to-end (typical structure: music → mid-gap silence → voice fragment → tiny voice-break → voice fragment → between-segment silence → next music...), segment boundaries can be auto-detected. Each segment is one `[music | mid-gap | voice]` unit.

**Algorithm.** Compute 50 ms RMS envelope. Find silence runs (< -42 dB, ≥ 0.5 s). Classify each silence by the duration of activity that follows it:

- Followed by **> 6 s** of activity (music block): **between-segments boundary** (segment END)
- Followed by **1.5–6 s** of activity (voice fragment): **mid-gap** (music → voice cut point)
- Followed by **< 1.5 s** of activity: **voice-break within voice** (skip — typical closing-door announcements have a brief pause partway through)

Each segment runs from one between-silence's END (or file start) to the next between-silence's START (or EOF). The mid-gap silence's start = `mid_cut`.

```python
import librosa, numpy as np
from pathlib import Path

SRC = Path("audio_src/<line>/<diagram>/sta_src.mp3")
y, sr = librosa.load(SRC, sr=22050, mono=True)
hop = int(sr * 0.05)
rms_db = 20 * np.log10(librosa.feature.rms(y=y, hop_length=hop)[0] + 1e-10)
times = np.arange(len(rms_db)) * 0.05

SIL_THRESH = -42  # dB
MIN_SIL = 0.5     # s

in_sil = rms_db < SIL_THRESH
runs, start = [], None
for i, s in enumerate(in_sil):
    if s and start is None: start = i
    elif not s and start is not None:
        runs.append((times[start], times[i-1])); start = None
if start is not None:
    runs.append((times[start], times[-1]))
sils = [(s, e) for s, e in runs if (e-s) >= MIN_SIL]

EOF = len(y) / sr
segments, seg_start, mid_cut = [], sils[0][1], None  # active resumes after leading silence
for i, (s, e) in enumerate(sils):
    if i == 0: continue
    next_active = (sils[i+1][0] if i+1 < len(sils) else EOF) - e
    if next_active > 6:        # BETWEEN — segment ends here
        segments.append((seg_start, mid_cut, s))
        seg_start, mid_cut = e, None
    elif next_active > 1.5:    # MID-GAP
        mid_cut = s
    # else: voice-break — skip
if mid_cut is not None:        # final segment to EOF
    segments.append((seg_start, mid_cut, EOF))

for i, (s, c, e) in enumerate(segments, 1):
    print(f"seg {i}: start={s:.2f} cut={c:.2f} end={e:.2f}  music={c-s:.2f}s voice={e-c:.2f}s")
```

**Surface to user before cutting** (Step 2 discussion still applies):

- **Segment count** vs route's stop count. Off by 1 typically means the source includes a station this train doesn't stop at (e.g., a recently-opened station — keiyo's 幕張豊砂 case) — that segment goes to `_archive`.
- **Duration outliers.** Music typically 7–15 s; voice 5–7 s. Music > 20 s may be an unusually elaborate melody (Tokyo-end of keiyo) OR two segments glued. Voice < 4 s is suspicious.
- **Source order** — first segment → last segment direction along the route. Don't assume.

Once user confirms mapping, generate `split_sta.py` using the auto-detected timestamps as `SEGMENTS`. Apply a **0.3 s pad on each side** of each segment when cutting (silence boundaries are tight to music/voice edges; pad gives `trim_sta_silence.py` lead/trail silence to normalize). Bake the pad into `sta_cut`: `sta_cut = mid_cut − (seg_start − PAD)`. Then continue to Step 4.

### Step 2 — Parse + discuss BEFORE acting

Surface to the user before generating any script or touching route.json:

- **Total segment count**
- **Platform mapping per station** (`(N)` notation), any song names provided
- **Suspicious gaps** — trailing-announcement section shorter than ~5 s is suspicious (closing-door announcements run 5–20 s normally)
- **Multi-platform stations** — if the same station has 2+ recordings, identify which the train actually uses; the rest go to `_archive`
- **Discussion-first preference**: format variance between sources is common, surprises are normal — don't assume "the format" exists

Wait for user confirmation on the parse before generating.

### Step 3 — Generate the splitter (per-source, ad-hoc)

**Splitters are per-source artifacts, not a maintained library.** Format varies between sources — one batch may use 3 timestamps per line (start/cut/end), another may use 2 (start/cut, end implicit). Each source gets its own script reflecting its own format. Don't try to unify into "the splitter".

Naming: `split_sta.py` if it's the only STA source in the folder; `split_sta_<describer>.py` if multiple (e.g., `split_sta_tokyo.py` + `split_sta_higashichiba.py`). Lives in the source folder so the audit trail of "how this batch was split" stays with the data.

**STA splitter — explicit-end format** (3 timestamps per line: start/cut/end). Add an `op` / `archive` dest tag per segment so re-runs route operational vs unused recordings to the right folder automatically:

```python
"""Split sta source into per-segment files + archive routing."""
import subprocess, sys
from pathlib import Path

SRC = Path(__file__).parent / "sta_source.mp3"
# parents[3] climbs: <diagram> → <line> → audio_src → project root
PROJECT = Path(__file__).resolve().parents[3]
OUT_OP = PROJECT / "audio" / "<line>" / "<diagram>" / "sta"
OUT_ARCHIVE = PROJECT / "audio" / "_archive" / "<line>" / "<diagram>" / "sta"

SEGMENTS = [
    # (start, cut, end, basename, dest)
    ("0:12", "1:08", "1:18", "tsuga_2_gota-del-vient", "op"),
    ("5:43", "6:08", "6:17", "narita_5_furawa-shoppu", "archive"),  # other-platform take
    # ...
]

def to_sec(ts):
    m, s = map(int, ts.split(":"))
    return m * 60 + s

for start, cut, end, name, dest in SEGMENTS:
    out_dir = OUT_ARCHIVE if dest == "archive" else OUT_OP
    out_dir.mkdir(parents=True, exist_ok=True)
    start_sec = to_sec(start)
    duration = to_sec(end) - start_sec
    sta_cut_sec = to_sec(cut) - start_sec  # → route.json sta_cut
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", str(start_sec), "-i", str(SRC),
           "-t", str(duration),
           "-c", "copy", str(out_dir / f"{name}.mp3")]
    print(f"{name}.mp3 [{dest}]  start={start}  cut={cut}  end={end}  sta_cut={sta_cut_sec}")
    subprocess.run(cmd, check=True)
```

**STA splitter — implicit-end format** (2 timestamps per line: start/cut, end = next start, last = EOF):

```python
EOF = "5:18"  # known from `ffmpeg -i sta_source.mp3 2>&1 | grep -i duration`
SEGMENTS = [
    # (start, cut, basename, dest)
    ("0:24", "0:40", "tokyo_4_jr-sh5-1", "op"),
    ("0:47", "1:07", "tokyo_3_twilight", "archive"),
    # ...
]

for i, (start, cut, name, dest) in enumerate(SEGMENTS):
    out_dir = OUT_ARCHIVE if dest == "archive" else OUT_OP
    out_dir.mkdir(parents=True, exist_ok=True)
    start_sec = to_sec(start)
    end = SEGMENTS[i + 1][0] if i + 1 < len(SEGMENTS) else EOF
    duration = to_sec(end) - start_sec
    sta_cut_sec = to_sec(cut) - start_sec
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", str(start_sec), "-i", str(SRC),
           "-t", str(duration),
           "-c", "copy", str(out_dir / f"{name}.mp3")]
    print(f"{name}.mp3 [{dest}]  start={start}  cut={cut}  end={end}  sta_cut={sta_cut_sec}")
    subprocess.run(cmd, check=True)
```

Print the `sta_cut` value during the run so it's easy to copy into route.json.

### Step 4 — Run + verify file count

Run the splitter. Verify file count matches expected segment count. List the operational + archive output folders.

### Step 5 — Update route.json

Replace placeholder `sta_cut` and `sta` fields with the splitter's output values. Replace placeholder `sta` refs with the descriptive basenames.

- **Termini**: omit `sta` and `sta_cut` fields (no departure melody at end of route). Keep `time`.
- **Stations IRL with no departure melody** (e.g. 千葉 on the Sobu line): same treatment — omit `sta` and `sta_cut`.
- **Passing stations** (`pa: []`): omit `sta`, `sta_cut`, AND `time` — train doesn't stop, countdown comes from the next PA station's `time`.

**Archive routing is handled by the splitter's per-segment `dest` tag in Step 3** — operational files land in `audio/<line>/<diagram>/sta/`, `"archive"`-tagged files land in `audio/_archive/<line>/<diagram>/sta/` (mirror layout under `_archive/`, no route.json there). The `_` prefix marks "preserved but not shipped" — `_archive/` and `_mock/` both follow this convention.

### Step 6 — Sanity check refs vs disk

```bash
PYTHONUTF8=1 python -c "
import json
from pathlib import Path
ROOT = Path('D:/pids_jre_simulator')   # absolute path — cwd persists across Bash calls
route = json.load(open(ROOT / 'audio/<line>/<diagram>/route.json', encoding='utf-8'))
sta_dir = ROOT / 'audio/<line>/<diagram>/sta'
on_disk = {p.stem for p in sta_dir.glob('*.mp3')} if sta_dir.exists() else set()
refs = {x for stop in route['stops'] for x in stop.get('sta', [])}
print(f'sta refs={len(refs)}  on_disk={len(on_disk)}')
print(f'missing: {sorted(refs - on_disk)}')
print(f'unused on disk: {sorted(on_disk - refs)}')
"
```

**Expected unused on disk: none** — unused recordings (passing-station mp3s, other-platform takes) should already be in `audio/_archive/`. If a file appears in "unused" here, it's a leftover that needs to be relocated:

```bash
mkdir -p audio/_archive/<line>/<diagram>/sta
mv audio/<line>/<diagram>/sta/{file1,file2}.mp3 audio/_archive/<line>/<diagram>/sta/
```

Continue to **Phase B**.

---

## Phase B — Validation + refinement

This phase is **always run** — for new splits and for revisits to existing routes. No route ships without a by-ear pass.

### The order: open the verifier FIRST, and do the work in it

**`verify_sta_listen.py` is the primary tool of this phase, not its final gate.** It shows the waveform, takes a drag-selection, splices it with `X`, retunes `sta_cut` on the same screen, and writes to every `route.json` referencing the file. Artifact removal and cut placement are one pass over one file, not three steps over a corpus.

The detector-first order this skill used to prescribe — detect, propose a table, apply in bulk, then listen — is demoted to background (Steps 7.5, 9, 10). It has failed on every line that has actually been examined:

| line | detector said | truth |
|---|---|---|
| keihin | no KAK (couldn't fire — source limited flat) | KAK throughout; a bulk auto-splice then came out under-tight on 40 of 45 files and was reverted |
| saikyo | 0 of 24 files carry speech | 3 do — the hf/lf band came from another capture chain |
| tokaido | 0 KAK across the line | **21 of 21** had one, quieter than the melody. Removed by eye in one sitting: 13.9 s, mean 662 ms/file |

So: back up (Step 7) → open the verifier → per file, look at the waveform, splice what you see, tune the cut, PASS → record the result (Step 13). Reach for a detector only to triage a corpus too large to eyeball, and treat whatever it says as a candidate list.

### Work the author did by hand is DONE

A file the author spliced or whose cut the author placed by ear is finished. Do not re-measure it, do not propose a correction against it, and do not report a derived threshold disagreeing with it as a finding — the ear is the gate this whole phase exists to satisfy, and it has already run.

This is the forward-looking half of `critical_lessons.md § "The instrument is not the artifact"`: that rule says the ear outranks the instrument when they conflict; this one says a finished hand edit is not a thing to re-open at all. (2026-08-08, author: *"i have confidence on things that are edited by me, so the standard workflows can change a bit."* The same day, an audit of an already-passed Saikyo produced a list of defects that were not defects.)

**Before auditing anything, read `audio/README.md`'s `Audio state` field for the line** — it is the committed record of what has been done and when. A line marked verified is not re-audited; a line marked **unverified** is where the work is.

### Step 7 — Backup before destructive ops

`trim_sta_silence.py` (next step) modifies mp3s in place (lossless lead/trail copy + lossy mid-gap re-encode) and patches route.json. **Snapshot first, into `audio_src/` so the backups stay gitignored**:

```bash
mkdir -p audio_src/<line>/<diagram>
cp -r audio/<line>/<diagram>/sta audio_src/<line>/<diagram>/sta.bak
cp audio/<line>/<diagram>/route.json audio_src/<line>/<diagram>/route.json.bak
```

Mention this safety net in your pre-flight summary so the user knows you have a rollback path. Delete `audio_src/<line>/<diagram>/sta.bak/` and `route.json.bak` only after the by-ear gate (Step 11) passes.

### Step 7.5 — Source-recording artifacts: WHAT they are (splice them in the verifier)

> **The detection machinery below is background, not the procedure.** Read the anatomy and the two
> patterns — they are what make the waveform readable — then remove the artifact by eye with the
> verifier's drag-select + `X`. Every detector in this section has now reported clean on a line
> that was full of them. Build no more of them.

Some source recordings include capture artifacts that the standard trim/validate pipeline can't clean up. Two patterns surfaced so far (across multiple lines — patterns are recording-source-driven, not line-specific):

**Pattern A — KAK transient** (physical staff-machine cut captured in audio):

**The sequence — memorise this, it is what the detector is looking for:**

```
music  →  silence (OPTIONAL)  →  KAK  →  silence  →  voice
```

**What it is: a station attendant physically switching the melody machine OFF.** The KAK *is* that switch — which is why it always lands after the music has stopped and before the closing announcement begins, never inside either. The melody does not fade; it stops dead, because power was cut mid-note.

Two consequences that decide how to find it:

- **The KAK is a position, not a level.** It is the only event in the music→voice window. Locate the window first, then take the burst inside it. Do not scan a blind `±1.5 s` around `sta_cut` — that straddles the voice attack and reports a hit on every file (Chūō: a false 23/23).
- **The silence before it is optional; the silence after it is not.** `music → KAK` with no gap is normal (the switch was thrown the instant the melody ended). `KAK → voice` with no gap is not — if the burst runs straight into speech, it is the voice's own onset, not a KAK.

Loud transient peaking near digital ceiling (-4 to -7 dB), brief (0.2–0.5 s), sits between music end and voice start.

Because the KAK's own silence boundary reads as `music_end` to a level detector, an unspliced KAK produces the **zero-gap false positive** in `detect_sta_cut.py` (`music_end == voice_start`). A whole line reporting zero-gap is therefore *evidence of KAK*, not a broken measurement — see Gotchas.

Only run this step if the user mentions it OR you spot the pattern: a single very loud short event near `sta_cut` on most files. Skip otherwise.

**Detection.** For each file, find the loudest 25 ms peak in `[sta_cut − 1.5 s, sta_cut + 1.5 s]`. If peak amplitude ≥ -15 dB (vs. typical music -20 to -25 dB), it's a KAK. Walk outward from the peak using a 25 ms peak-amplitude envelope until amplitude drops below -25 dB; that defines the splice window. Reject results with width > 1.5 s — the walk escaped into music content.

**Why raw peak amplitude, not RMS:** RMS averaging over 5–10 ms windows dilutes transient peaks down to -18 to -22 dB, indistinguishable from music. Use raw `max(|y|)` over a short window.

**Amplitude detection fails entirely on a limited/hot source — use the HF/LF ratio instead.** The method above assumes the KAK is *louder* than the music (-4 to -7 dB against music at -20 to -25 dB). On a hot source that inverts: keihin's STA is limited flat (music at ~0 dB, loudest peak in a file +2.7 dB — 0.9 dB of total range), and its KAK is **quieter than the music it interrupts** (-9 dB). No amplitude threshold can separate them, and the walk-outward step never terminates, so every candidate is rejected by `MAX_WIDTH` — a clean sheet that means "thresholds don't fit", not "no KAK". Check the corpus first: if `max_peak - music_level < ~6 dB`, skip Pattern A's amplitude path.

What survives limiting is the **spectral shape**, because a KAK is a broadband click and a melody is tonal. Take `hf = sum(|S|[f > 5 kHz])` and `lf = sum(|S|[f < 2 kHz])` from a short-hop STFT (`n_fft=512, hop=128` ≈ 5.8 ms — a KAK is ~0.15–0.5 s, so a 25 ms hop smears it):

| content | `hf/lf` |
|---|---|
| melody | 0.03–0.09 |
| closing announcement | 0.2–0.5 |
| **KAK** | **1.0–1.3** |

**These numbers are CAPTURE-CHAIN specific — they are keihin's, not the format's.** On Saikyo's platform recordings a clearly intelligible closing announcement reads **0.002**, indistinguishable from melody, so a speech-vs-melody sweep built on this band reported "0 of 24 files carry speech" when the answer was 3. Use the band only after reproducing it on a known-positive **from the same line**; for the speech question use `audio_id.has_speech()` instead, which does not depend on a band at all. (2026-08-08.)

On keihin's 大宮 melody the transition reads unambiguously — music stops dead (`lf` 146 → 37 in two frames), then `hf` jumps 13× the music median with `hf/lf` 1.31. A 20×+ separation from the melody, immune to the limiting.

**The trap: `hf/lf` explodes in quiet passages** — the denominator collapses, so silence between melody and voice reads 13–18, *higher than a real KAK*, with no click present. A detector ranking on the ratio alone picks the gap every time. Gate on absolute broadband energy as well (`hf > ~3 × hf_median_of_music_region`) so only frames carrying real HF content qualify.

**Calibrate on a known-positive before trusting any of it.** Ask the user which file has an audible KAK, probe THAT file at 5 ms resolution, and print the profile (amplitude, `hf`, `lf`, ratio) so the transient is *visible* rather than inferred. Even with the ratio + energy gate, separating melody / voice / click across a whole corpus stayed unreliable — treat the output as a **candidate list for the by-ear verifier**, not as input to an automatic splice.

**A user-named file outranks the detector — no exceptions, no second opinion.** When the user says "this file has a KAK," that file IS ground truth: the detector's job is now to REPRODUCE it, and a detector that reports clean on it is disqualified, not "mostly right." Do not build another detector to adjudicate — probe that one file at 5 ms and read the numbers. (2026-05-09 JY29_SMB, 2026-07-26 JK47_OMY-south @ 11.51 — same error, same correction, both times after claude had reported zero KAK.)

**Detector windows run ~4× tighter than a hand cut.** A burst walk stops at its threshold; a human cuts where the artifact stops being *audible*, which is further out (keihin: hand 388 ms vs detector 87 ms on STA; 0.9–2.0 s deeper on PA). Treat the detected window as the INNER bound and widen before proposing — a splice a little too wide runs into silence and is inaudible, one a little too tight leaves the click.

**Detection script template:**

```python
import librosa, numpy as np, json
from pathlib import Path

route = json.loads(Path("audio/<line>/<diagram>/route.json").read_text(encoding="utf-8"))
WIN_MS = 25; THRESH_PK_DB = -25; MIN_PEAK_DB = -15; MAX_WIDTH = 1.5; PAD = 0.03

def peak_env(y, sr, win_ms):
    win = int(sr * win_ms / 1000)
    n = len(y) // win
    return np.array([np.abs(y[i*win:(i+1)*win]).max() for i in range(n)]), win/sr

splices = []
for stop in route["stops"]:
    for name in stop.get("sta", []):
        cut = stop.get("sta_cut")
        p = Path(f"audio/<line>/<diagram>/sta/{name}.mp3")
        if cut is None or not p.exists(): continue
        y, sr = librosa.load(p, sr=22050, mono=True)
        env, dt = peak_env(y, sr, WIN_MS)
        env_db = 20 * np.log10(env + 1e-10)
        times = np.arange(len(env_db)) * dt
        mask = (times >= max(0, cut - 1.5)) & (times <= min(len(y)/sr, cut + 1.5))
        if not mask.any(): continue
        idx = np.where(mask)[0]
        peak_idx = idx[env_db[idx].argmax()]
        if env_db[peak_idx] < MIN_PEAK_DB: continue  # no KAK
        i_l, i_r = peak_idx, peak_idx
        while i_l > 0 and env_db[i_l] > THRESH_PK_DB: i_l -= 1
        while i_r < len(env_db)-1 and env_db[i_r] > THRESH_PK_DB: i_r += 1
        kak_start = max(0, times[i_l] - PAD)
        kak_end = min(len(y)/sr, times[i_r] + PAD)
        if kak_end - kak_start > MAX_WIDTH: continue  # walk escaped
        splices.append((name, round(kak_start, 3), round(kak_end, 3)))
        print(f"{name}  peak={env_db[peak_idx]:.1f}dB  splice [{kak_start:.3f}, {kak_end:.3f}]  width={kak_end-kak_start:.2f}s")
```

**Surface to user before splicing.** Show each file's proposed splice range + peak dB. Files that don't trigger the threshold get reported as "no KAK detected" — they may still be valid (just no transient), or anomalous (wrong recording entirely). Wait for OK.

**Splice + sta_cut adjustment.** Apply `ffmpeg -filter_complex` splice (same recipe as Step 12 — `atrim` + `concat`). For sta_cut adjustment per file:

- `kak_end ≤ sta_cut` → shift sta_cut down by full splice width
- `kak_start ≥ sta_cut` → no change (KAK was after the cut point)
- `kak_start < sta_cut < kak_end` → snap sta_cut to `kak_start`

Then proceed to Step 8 (trim) normally — the spliced files now have a clean music→silence→voice structure that trim_sta_silence + detect_sta_cut handle correctly.

**Pattern B — "2nd-loop snippet"** (recording captured the start of a 2nd melody loop before the staff cut):

The other half of Pattern A — the same attendant switch-off, seen as the truncated loop rather than as the click. Expect them together: if a file has an unfinished 2nd loop, look for the KAK right behind it, and vice versa. See § "STA anatomy".

Pattern: `music (1st loop) → tiny silence (~0.2 s, between-loops gap) → brief music pulse (0.1–0.7 s = start of 2nd loop) → silence (1–3 s) → voice`. The 2nd-loop pulse is real music, same melody, just truncated. If left in place, pressing PageUp during the 1st loop can land in the inter-loop silence and the simulator plays a confusing "music–silence–music(<0.5s)–silence–voice" sequence.

**Remove an INCOMPLETE trailing loop; keep a COMPLETE one.** A full second (or third) loop is real content the melody legitimately has — Chūō's 新宿 carries 2 complete loops and 立川 carries 3. Only the truncated stub is a capture artifact.

Detection — **amplitude alone cannot do this** (a mid-loop pulse looks like a voice fragment to any level detector), but **correlation against the first loop can**, and it separates cleanly enough to run over a whole line:

1. `voice_onset` = first activity block starting at/after `sta_cut` (none ⇒ the file has no announcement — melody only).
2. Music blocks = activity blocks before `voice_onset`, merged across sub-0.35 s gaps (melodies have internal breaks that are not loop boundaries). Ignore sub-0.5 s blips — a noise-floor tick at the file head otherwise becomes "block 1" and every downstream comparison is meaningless.
3. Block 1 is the base loop. Correlate each later music block against the base loop's head of equal length using `scipy.signal.correlate(..., mode="full", method="fft")` — every lag, no threshold grid (per `principles.md § "A measurement is a claim until the instrument is calibrated"`; a strided lag scan scores identical audio near zero).
4. `r ≥ 0.80` ⇒ a loop repeat. **Complete** if its duration ≥ 85 % of the base loop, else **incomplete**.

Use `audio_id.loop_repeat(path, base, later)` — steps 3–4 are what it implements.

Measured separation on Chūō: keeps landed at 100–102 % (r = 0.93–0.99), the one removal at 12 % (r = 0.98). Nothing sat near the boundary. Chroma-CQT agreed independently (0.958 vs a 0.490 voice control) — a useful second read when a waveform correlation is borderline.

**The 85 % line does not adjudicate the middle.** Saikyo's `JA24` came in at 77 % (r = 0.936) — a substantial partial loop, not a stub and not complete. Chūō's clean 12-vs-100 split is what makes the threshold look decisive; it is not. Anything between roughly 60 % and 85 % goes to the ear, not to the rule. (The user kept `JA24`.)

Surface the classified list before splicing anything (`critical_lessons.md § 1` — print the resolved target list, never drive a destructive loop off an unverified filter).

Splice rule (handles both the snippet AND the long post-snippet silence in one pass):

- `keep_until = music_1_end + 0.1 s` (just past full melody, before inter-loop silence/snippet)
- `skip_until = voice_start − 1.0 s` (leaves ~1 s of silence before voice in the new file)
- After splice, set `sta_cut = round(max(music_1_end, new_voice_start − 0.5), 1)`
  where `new_voice_start = voice_start − (skip_until − keep_until)`

Always preview after splicing — when the long post-snippet silence is genuinely long (>2 s like keiyo's tokyo-end stations), the resulting 1 s gap may still feel abrupt by-ear and the user may want to extend it. Use the verifier's interactive trim (Step 11) for fine adjustment.

### Pattern C — duplicate intro / stutter / mid-music repeat

Source recordings occasionally have a tiny stutter at the start (e.g., the first 0.1–0.3 s of music plays twice) or a fully-repeated melody (the entire melody plays twice back-to-back). These are per-file issues — don't try to detect them. Hand off to the verifier's interactive trim (Step 11) and let the user nudge start/end markers by-ear.

### Step 8 — Trim silences (in-place, modifies files)

Trims leading + trailing silence to ~0.2 s pads (lossless stream-copy) and the mid-file silence between music end and voice start to ~1 s (re-encodes, only when detection confidence is high and gap is in a sane range). With `--route`, patches route.json `sta_cut` values down by `lead_trim + mid_trim`.

```bash
PYTHONUTF8=1 uv run python _dev_scripts/trim_sta_silence.py audio/<line>/<diagram>/sta \
    --route audio/<line>/<diagram>/route.json
```

Idempotent — re-running on already-trimmed files is a no-op.

**On a pooled line, omit `--route`.** It patches a single route.json, so on a shared pool it silently desyncs the other diagrams. Run the trim bare, then re-measure the trimmed files and write `sta_cut` to every diagram in one pass (Step 10). Re-measure rather than predicting: the script skips the mid-gap trim on files where its own confidence gate declines, so predicted post-trim coordinates do not hold — on Chūō it declined 9 of 23.

### Step 9 — Validate `sta_cut` placement

Detector compares each `sta_cut` against the [`music_end`, `voice_start`] window it derives from the file. Flags EARLY (sta_cut in music) or LATE (sta_cut in voice) — both are illegal UX:

- **EARLY** (`sta_cut < music_end`): simulator briefly replays a music tail before voice — music returns when the user expected to skip past it. Jarring.
- **LATE** (`sta_cut > voice_start`): simulator clips the first syllable of the announcement. Always wrong.

```bash
PYTHONUTF8=1 uv run python _dev_scripts/detect_sta_cut.py audio/<line>/<diagram>/sta \
    --truth audio/<line>/<diagram>/route.json
```

**Expected pattern post-trim**: many stations flag EARLY by 0.6–2 s. This is **not a bug** — `trim_sta_silence.py`'s flat `total_shift = lead_trim + mid_trim` over-corrects when the original `sta_cut` sat near the original `music_end` (vs. after `voice_start`). The propose-and-apply step below fixes them.

### Step 10 — Propose corrections + apply

For each EARLY/LATE flag, **propose** the correction using the auto-set rule:

```
sta_cut = round(max(music_end, voice_start - 0.5), 1)
```

(Sits 0.5 s pre-voice when the gap allows; falls back to `voice_start` when the gap is too narrow.)

**Print the per-file structure once and read it — do not build a classifier.** A route is ~20 files; dumping each one's activity/silence timeline (start, end, duration, peak dB, with the current `sta_cut` marked) and reading it is faster and more reliable than any heuristic, and it yields the whole proposal table in one pass. Iterating detectors against files you have not looked at burns rounds and produces confident wrong numbers. (2026-07-25: three successive classifiers, all wrong, before the raw timeline made the structure obvious in one read.)

**Identifying the music→voice gap is where this goes wrong.** Two heuristics that look obvious and both fail:

- *"longest interior silence"* — correct on untrimmed files, wrong after trimming. Trim normalises the real gap to ~1.0 s while leaving the inter-announcement gaps untouched, so a 1.6–2.5 s pause between announcement clusters becomes the longest silence in the file. Four of Chūō's 23 landed 4–6 s late this way.
- *"the block before the last activity"* — the closing announcement is **several short chunks** (0.8–1.3 s) separated by real 0.1–0.8 s breaks, not one block. Anchoring on the last chunk walks backwards into the middle of the voice. Chunk brevity is normal; do not treat a 1 s voice block as suspicious.

What works: the gap is the one following the **first** sustained music block. Derive the window from the untrimmed file (where "longest interior silence" does hold), then map through the trim's reported shifts — `music_end − lead_trim`, `voice_onset − lead_trim − mid_trim` — and **verify against the trimmed audio** before writing: the span must read as silence and voice must resume at the onset. On Chūō that verification passed 20/20 and would have caught any mapping error.

Surface the diff (current → proposed, with the [`music_end`, `voice_start`] window) as a table. **Do not auto-apply** — wait for user confirmation. If detector confidence < 0.7 OR the proposal looks wrong relative to the user's hand-set value → **flag for re-listen** instead of proposing.

After user accepts, patch route.json (1-decimal precision is fine; the runtime is float-typed):

```python
import json
from pathlib import Path
p = Path("audio/<line>/<diagram>/route.json")
route = json.loads(p.read_text(encoding="utf-8"))
updates = {"ueno": 11.2, "akabane": 9.9, ...}  # sta -> new sta_cut
for stop in route["stops"]:
    for sta in stop.get("sta", []):
        if sta in updates:
            stop["sta_cut"] = updates[sta]
p.write_text(json.dumps(route, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
```

Re-run Step 9 to confirm `in gap: N/N`.

### Step 11 — By-ear verification gate (and where the actual work happens)

The detector is a feature-based heuristic; the by-ear gate is the ground truth — and per § "The
order" above, this is also where artifacts get spliced and cuts get placed, not merely where
finished work is checked. Run the GUI verifier:

```bash
PYTHONUTF8=1 uv run python _dev_scripts/verify_sta_listen.py audio/<line>/<diagram>
PYTHONUTF8=1 uv run python _dev_scripts/verify_sta_listen.py audio/<line>          # pooled line
```

**Pooled lines**: pass the LINE folder. The verifier finds `<line>/*/route.json`, merges the STA union across diagrams (ordered by the diagram referencing the most), and warns if two diagrams disagree on a shared file's `sta_cut`. Every write — interactive trim or cut nudge — lands in **all** route.json files referencing that mp3; patching one desyncs the pool. See `WIP_audio_pooling.md § Tooling must be pool-aware`.

Per station, the script:
1. Plays `[0, 3 s]` — confirms the music head is intact (no clipped attack).
2. Brief silence (~0.5 s).
3. Plays `[sta_cut − 3 s, EOF]` — gives 3 s of music tail, then the cut, then the voice. The cut transition is what you're listening for.

The window has a clickable sidebar listing all STAs with their current verdict (`✓ ✗ ·`). Click any row to jump. Pass/Fail/Replay buttons + P/F/R keys. ↑/↓ navigates linearly. Q/Esc to quit.

**Per-station notes** (✎ row above the seek bar): click or press **E** to add/edit a note (e.g. "look for double-loop at start", or a FAIL reason). Enter saves, Esc cancels. PASS auto-resolves the note (renders dim with strike-through). Notes persist in the results JSON across runs.

**Cut-marker beep**: a short 880 Hz beep fires once per playback when the tail crosses sta_cut, marking the exact transition point so it's easy to hear whether the cut lands cleanly.

**Adjusting `sta_cut` by ear** — the fastest path when the detector's placement is close but not right. **Drag the cut marker** on the seek bar (hover within ~14 px; it thickens and grows a grab handle). Releasing replays from the new position automatically, so the drag is self-verifying. `←`/`→` nudge by 0.1 s (Shift = 0.01 s) when you want exact steps. Nothing is written until `C`; `Z` discards. No audio is modified — this only moves where the simulator jumps to, unlike the trim controls below.

| Key | Action |
|---|---|
| drag marker / `←` `→` | move `sta_cut` |
| `C` | commit `sta_cut` to every route.json referencing the file |
| `Z` | discard pending cut + trim |

**Interactive trim** (for files where the propose+splice pipeline can't cleanly fix the issue — e.g., per-file stutters, duplicate intros, idiosyncratic snippets):

| Key | Action |
|---|---|
| `[` / `]` | start-trim ±0.1 s (Shift = ±0.01 s for fine) |
| `,` / `.` | end-trim ±0.1 s (Shift = ±0.01 s) |
| `R` | replay (preview the pending trim — head plays from `trim_start`, tail stops at `duration − end_trim`) |
| `T` | apply trim — splices the file lossless via ffmpeg, shifts `sta_cut` by `−start_trim`, persists to route.json |
| `Z` | reset pending trim |

The trim regions show as red overlays on the seek bar. Status line below the bar previews the new duration and new `sta_cut`. Switching stations discards pending trim. Use this for any per-file issue that doesn't fit a generic detector — keiyo's shin-kiba "0.2 s stutter at start" was an example.

**Single-station retest** when iterating on a fix:

```bash
PYTHONUTF8=1 uv run python _dev_scripts/verify_sta_listen.py audio/<line>/<diagram> --only kumagaya
```

Results merge into `audio_src/<line>/<diagram>/sta_verify_results.json` (auto-creating the dir under the gitignored `audio_src/` tree) — verdicts for stations not tested this run are preserved from the prior JSON. Read this file to pick up FAILs:

```python
import json
from pathlib import Path
results = json.loads(Path("audio_src/<line>/<diagram>/sta_verify_results.json").read_text())
fails = [it for it in results["items"] if it["verdict"] == "FAIL"]
```

### Step 12 — Investigate FAILs

For each FAIL, the detector's reported `music_end` / `voice_start` may not match reality. Probe the waveform with finer-grained RMS to see what's actually there:

```python
import librosa, numpy as np
y, sr = librosa.load("audio/<line>/<diagram>/sta/<sta>.mp3", sr=22050, mono=True)
hop = int(sr * 0.05)  # 50ms frames
rms_db = 20 * np.log10(librosa.feature.rms(y=y, hop_length=hop)[0] + 1e-10)
for i, t in enumerate(np.arange(len(rms_db)) * 0.05):
    if <window_start> <= t <= <window_end>:
        print(f"{t:>6.2f}  {rms_db[i]:>7.1f} dB")
```

Look for the silence floor (-60 dB or below) marking the real music→voice gap.

**Edge case worth knowing — "zero-gap" detector false positive** (kumagaya pattern):

- Symptom: detector reports `music_end == voice_start` with high confidence, mid-trim didn't fire, by-ear gate fails.
- Root cause: detector's `SEARCH_WINDOW_FRAMES = 12` (= 1.2 s after change-point) was too tight to reach the real silence gap. Cut-point landed mid-decay; real silence started further out.
- Fix: probe the waveform manually (above), identify the real silence boundaries, then call `trim_middle_gap` directly with explicit values:

```bash
ffmpeg -y -loglevel error -i audio/<line>/<diagram>/sta/<sta>.mp3 \
    -filter_complex "[0:a]atrim=0:<keep_until>,asetpts=PTS-STARTPTS[a1];[0:a]atrim=<skip_until>,asetpts=PTS-STARTPTS[a2];[a1][a2]concat=n=2:v=0:a=1[out]" \
    -map "[out]" -q:a 2 <sta>.tmp.mp3
mv <sta>.tmp.mp3 audio/<line>/<diagram>/sta/<sta>.mp3
```

Where `keep_until = music_end + 0.5` and `skip_until = voice_start - 0.5` (uses the same arithmetic as `trim_middle_gap`). Then update `sta_cut` to `round(max(music_end, voice_start - 0.5 - 0.5), 1)` accounting for the splice. Re-run Steps 9 + 11 to confirm.

If the file is locked when `mv` runs ("Device or resource busy"), the verifier or another player is holding it — close it and retry.

#### Hostile-recording pattern — combine fixes in ONE splice

When the source recording has multiple problems in the cut zone — sta_cut placed mid-music, residual KAK transient post-cut, no clean silence gap, voice attacks at digital ceiling — fix them all in a single ffmpeg operation. Don't iterate "fix KAK → user verifies → adjust sta_cut → user verifies → add silence pad → user verifies." That triples user verification time.

(First surfaced on Yamanote recordings — pattern is recording-source-driven, not line-specific.)

The combined operation:

1. **Cut music body before its natural sharp end** — addresses pre-cut KAK perception (the music's hard staff-cut moment can sound clicky in the verifier preview). Use `atrim=0:<music_cut>` ending slightly before the music's natural end (e.g. 100–200 ms inside the music body).
2. **Insert artificial silence** to meet the `~0.3 s pre-voice` convention. Hostile-pattern files don't have a natural silence gap wide enough; generate one with `anullsrc=channel_layout=stereo:sample_rate=22050,atrim=duration=0.30`.
3. **Skip KAK + first voice burst** — splice through to the inter-syllable quiet zone (or directly to voice content if no quiet zone exists). Use `atrim=<voice_resume>` for the second segment.
4. **Crossfade both junctions** to avoid audible click at sample-level discontinuities. Use `acrossfade=d=0.03:c1=tri:c2=tri` between music and silence (30 ms is good for music-side fade-out), and `acrossfade=d=0.02` between silence and voice (20 ms is enough since silence side is already at zero).
5. **Set sta_cut at the start of artificial silence** — gives the convention's 0.3 s pad before voice attack arrives.

Template:

```bash
ffmpeg -y -loglevel error -i audio/<line>/<diagram>/sta/<sta>.mp3 \
    -filter_complex "
        [0:a]atrim=0:<music_cut>,asetpts=PTS-STARTPTS[music];
        anullsrc=channel_layout=stereo:sample_rate=22050,atrim=duration=<silence_dur>[silence];
        [0:a]atrim=<voice_resume>,asetpts=PTS-STARTPTS[voice];
        [music][silence]acrossfade=d=0.03:c1=tri:c2=tri[ms];
        [ms][voice]acrossfade=d=0.02:c1=tri:c2=tri[out]
    " \
    -map "[out]" -q:a 2 <sta>.tmp.mp3
mv <sta>.tmp.mp3 audio/<line>/<diagram>/sta/<sta>.mp3
```

Then update `sta_cut` to `<music_cut>` (= start of inserted silence).

**Verify with the −8 dB voice-attack threshold** (not the convention's voice_start which assumes a sharp onset — hostile-pattern voices ramp in and cross −8 dB earlier than the peak). Aim for the gap from sta_cut to first window > −8 dB to be 280–340 ms. If short, increase `silence_dur` by ~100 ms and redo.

**Anti-pattern:** doing this in 2-3 ffmpeg passes (first KAK splice, then sta_cut adjustment, then silence pad). Each pass requires user verification. Combine all three into the single template above.

#### Route-level gap alignment — audit ALL stops, not just FAILs

Before declaring a route done, audit the pre-voice gap (sta_cut → first sample > −8 dB) across **every** stop, including the originally-PASSed ones. The FAIL-driven workflow only fixes the obvious ones; the PASSed files often have widely varying gaps (anything from 50 ms to 900 ms) just because their natural silence floors happen to be different lengths. That variance is audible — a PageUp on station X feels snappier than station Y on the same line.

Target: all stops within ~250–400 ms of `sta_cut → voice attack`. Two cheap fixes converge them:

**The 250–400 ms band is a Yamanote-derived default, not a gate.** It was measured on one line (2026-05-09) and does not generalise. The SHORT fix inserts `anullsrc` **digital** silence, so on a recording carrying continuous ambience (keihin: floor −15 to −37 dB) the insert is an audible dropout — 2026-07-26 it converted a by-ear PASS into a FAIL across the line. **Check the file's noise floor before inserting**; if the floor is not near-silent, move `sta_cut` only and leave the audio alone. A by-ear PASS at 30 ms outranks the band.

- **LONG (gap > 400 ms)**: route.json edit only. Set `new_sta_cut = round(voice_attack_time − 0.30, 1)`. No audio change. Files with deep silence floors before voice (`sta_cut` placed where music decay just ended) tend to land here — moving `sta_cut` later gets the simulator to start playback closer to voice.
- **SHORT (gap < 250 ms)**: insert artificial silence AT `sta_cut` position (no splice junction needed if the file is otherwise clean — typical for originally-PASSed files). Use:

```
[0:a]atrim=0:<sta_cut>,asetpts=PTS-STARTPTS[pre];
anullsrc=channel_layout=stereo:sample_rate=22050,atrim=duration=<silence_dur>[silence];
[0:a]atrim=<sta_cut>,asetpts=PTS-STARTPTS[post];
[pre][silence]concat=n=2:v=0:a=1[ps];
[ps][post]concat=n=2:v=0:a=1[out]
```

`silence_dur` ≈ `0.30 − current_gap`. No sta_cut change needed (the inserted silence pushes voice content later within the file).

Run the audit script after each fix batch. The skill is "done" when 0 stops fall outside 250–400 ms.

### Step 13 — Record the state, then clean up

**Write what was done into `audio/README.md`'s `Audio state` field for the line** — the facets that
matter are `sta_cut` checked by ear, KAK spliced (how many files, how much removed), silences
trimmed, PA checked by ear, each with the date. Say **unverified** for anything not done; an absent
verdict is not a pass.

This is the only durable record. `audio_src/<line>/sta_verify_results.json` is the working file for
a session in progress and is gitignored, so it never reaches a fresh clone or a second machine — a
later session cannot otherwise tell "verified months ago" from "never touched", and will re-audit a
finished corpus and report defects that are not defects. Update it in the same commit as the work.

After by-ear gate passes (`PASS` for all stations or user explicitly accepts FAILs):

```bash
rm -rf audio/<line>/<diagram>/sta.bak audio/<line>/<diagram>/route.json.bak
```

The `audio_src/<line>/<diagram>/sta_verify_results.json` artifact can be kept (audit trail) or removed — it gets overwritten on next run anyway, and `audio_src/` is gitignored either way.

---

## Conventions

### STA timestamps file format (`sta_timestamps.txt`)

Each line is one segment with explicit boundaries:

```
0:12 1:08(cut) to 1:18 都賀(2) gota del viento
2:41 3:01 3:06 物井(1) gota del viento
4:28 4:54 4:57 酒々井
6:19 6:47 till the end 空港第2ビル チャイム3B4
```

- Three timestamps positionally: `start`, `cut`, `end`. The `(cut)` and `to` annotations on some lines are documentation; the compact form (just three numbers) means the same thing.
- `(N)` after the station name = JR platform number where this melody plays IRL. Optional.
- Trailing string = official melody name. Optional. Can be Japanese (katakana / kanji) or English.
- "till the end" in the end slot = segment runs to EOF.

### STA filename convention

`{station}_{platform}_{song-id}.mp3`

- **Station first** (easier to scan when listing files), then platform, then song.
- **Underscore between fields**, **hyphens within a field**.
- Only `station` is required. `platform` and `song-id` are optional — drop along with the separator:
  - `narita_3_soyokaze.mp3` — all three known
  - `narita_3.mp3` — song unknown
  - `shisui_gota-del-vient.mp3` — no platform recorded (rare)
  - `shisui.mp3` — only station known
- Re-use surfaces as a glob on the trailing field: `ls *_gota-del-vient.mp3` shows every station that plays that song.
- **No metadata sidecar.** The filename IS the store. When a song is identified later, rename the file + update its `sta` ref in route.json in the same pass.
- **Variants are out of scope.** Two recordings of "the same song with slight differences" each get their own song-id slug. Differences in the trailing closing-door announcement (different staff voices, phrasing) across platforms/routes are not captured — `tsuga_2_gota-del-vient` and `monoi_1_gota-del-vient` share song identity, NOT recording identity.

### Japanese → ASCII slug rules

Hepburn romanization, macrons stripped, lowercase, hyphens for word boundaries — same rule used for station name slugs throughout the repo.

| Source | Slug |
|---|---|
| 東京 | `tokyo` |
| 越中島 | `etchujima` |
| 高輪ゲートウェイ | `takanawa-gateway` |
| スイートコール | `suito-koru` |
| フラワーショップ | `furawa-shoppu` |
| チャイム3B4 | `chaimu-3b4` |

For non-Japanese names: lowercase, spaces → hyphens, strip apostrophes/most punctuation, spell out `&` as `and`. `Don't Stop` → `dont-stop`, `Rock & Roll` → `rock-and-roll`.

### `sta_cut` field

**Seconds from the START of the file** where the melody is cut and the closing-door announcement (station-attendant voice, "ドアが閉まります" / "the doors will be closing") begins. IRL the music is *cut* — not faded — because the schedule rarely allows the full melody to play; the staff hard-cuts directly to the doors-closing voice. Computed at split time as `cut_timestamp - start_timestamp`.

#### Hard placement rule (both sides strict)

`sta_cut` MUST satisfy `music_end <= sta_cut <= voice_start` — i.e. land inside the silence gap between the music's hard cut and the voice's first frame. Both error modes are unacceptable UX (see Step 9 above).

`sta_cut` accepts integer or one-decimal float. Use the float precision when integer rounding would push outside the gap (common when the gap is < 1 s wide). The default auto-set strategy is `round(max(music_end, voice_start - 0.5), 1)`.

### Leading + trailing silence targets

Every STA file ships with **~0.2 s of silence at each end**:

- **Leading silence ~0.2 s** (true silence < −40 dB). Gives the audio attack a tiny safety pad while feeling snappy when the simulator triggers it. Anything beyond ~0.5 s feels broken.
- **Trailing silence ~0.2 s**. Mostly invisible to the user (file just stops), but critical for `detect_sta_cut.py` accuracy — the detector uses the last 3 s of the file as a "voice exemplar" for music→voice classification. Trailing silence pollutes that exemplar and degrades detection (one Sobu file's voice exemplar was 100% silence, blowing the detector by +5.8 s).

### route.json field rules at split output

- `sta`: list of basenames. Often one entry; can have multiple variants.
- `sta_cut`: number (integer or one-decimal float), seconds from start. Use float when the music→voice silence gap is narrow and integer rounding would land in music or voice instead of the silence.
- **Terminus**: omit `sta` and `sta_cut` (no departure from end-of-line). Keep `time`.
- **Stations IRL with no melody** (e.g. 千葉 on Sobu): omit `sta` and `sta_cut`. Keep `time`.
- **Passing stations** (`pa: []`): omit `sta`, `sta_cut`, AND `time`.

---

## Gotchas

- **Discussion-first.** Don't generate the splitter or update route.json until the user confirms the parse. Format variance between sources is normal — surprises happen. Same applies before running destructive trim/splice ops.
- **Backup before destructive ops.** `trim_sta_silence.py` and any `ffmpeg -filter_complex` splice modifies files in place. Snapshot the dir + route.json first; only delete backups after the by-ear gate passes.
- **CWD persists across Bash calls in this harness.** Use absolute paths in verification scripts, not relative — `Path('audio/...')` will resolve from wherever the last `cd` left you.
- **Unused-platform STA recordings** (other-platform takes for the train you're routing) belong in `audio/_archive/<line>/<diagram>/sta/`, NOT in operational `sta/`. Tag them `"archive"` in the splitter's SEGMENTS so the script routes them automatically — don't `mv` them after the fact.
- **Passing-station mp3s on disk that aren't in the route** (the train doesn't stop there) → also belong in `_archive`. Surfaces as "unused on disk" in the sanity check.
- **Trailing-announcement gap < ~5 s is suspicious** — the closing-door section between `cut` and `end` usually runs 5–20 s. If you see only 2–3 s, double-check `end` against the source.
- **Splitter scripts stay with their source folder** (`audio_src/<line>/<diagram>/`), not in a shared workflow folder. The audit trail of "how this batch was split" stays with the data. Note: the entire `audio_src/` tree is gitignored — only the cut output under `audio/<line>/<diagram>/` ships.
- **Formats vary between sources** — even within the same line/diagram, two STA recordings may use different timestamp conventions (3 timestamps vs 2). Don't try to unify; each source gets its own `split_sta_<describer>.py`.
- **Trailing digits in station romanization** (e.g., `airport-terminal-2`) are part of the station name, not platform. Filename position-parsing has no parser, so this is human-readable ambiguity only — not a bug to fix.
- **Don't create a metadata JSON sidecar.** The filename IS the metadata store. If `sta_meta.json` shows up, that's a previous experiment that should be removed.
- **Front-half placeholders are fine.** When STA source covers only part of a route (e.g., from-某-station-onward), the unsplit stops keep their placeholder `sta` refs until the rest arrives. They'll fail `validate_data.py`'s file-existence check until then — that's expected.
- **Detector zero-gap pattern → real gap is outside the search window.** When the detector returns `music_end == voice_start` with high confidence, that's NOT a genuinely tight transition — it's a false positive. Probe the waveform manually (Step 12) and run the manual mid-trim recipe.
- **A whole line reporting zero-gap can mean the recordings have no closing announcement at all.** `detect_sta_cut.py` derives `voice_start` from a level change, so on a melody-only recording it reports the next melody block — and has no way to express "there is no voice here". Saikyo is such a line: 18 of 24 files are melody only, `JA25` has a full announcement, `JA14`/`JA24` fragments. Check with `audio_id.has_speech()` before treating the flags as cut-placement errors. `sta_cut` still has a job on these files (it is where PageUp jumps to), so the values stay — they just land in an inter-loop silence rather than before a voice.
- **Source-recording transients (KAK).** Some source recordings have a loud physical-cut transient captured at the staff-machine cut moment (seen on Keiyo + Yamanote so far; recording-source-driven, not line-specific). If you spot a -4 to -7 dB peak near `sta_cut`, run Step 7.5 to splice it out before normal trim. Without splicing, the transient gets played at full volume during cut transitions — jarring UX. The detector also misclassifies the KAK's silence boundary as music_end, producing zero-gap false positives.
- **Most stations flag EARLY immediately after `trim_sta_silence.py`** — expected, propose-then-apply fixes them. Don't try to "fix" the trim script's `total_shift` math; the propose-then-apply round trip is the design.

## Documentation hook

After Phase A split / Phase B verification lands: if this work surfaced anything line-specific not already in [audio/README.md](../../../audio/README.md) — IRL melody quirk (no-melody station, elaborate-melody region), per-line filename-convention deviation, schema-corner-case usage — propose an entry. Decline if work was routine. (Recording-source patterns like KAK transient / hostile-recording are NOT line-specific; they stay in the skill's Step 7.5 + Gotchas.)

## Out of scope

- **Variant / arrangement modeling** — current scheme captures song identity, not recording identity. If/when fidelity matters, extend the convention or add a sidecar then. Don't pre-build for it.
- **Cross-route audio sharing** (e.g., 東京 STA used on Sobu AND Tokaido) — for now, duplicate the file. If it becomes painful, factor out an `audio/_shared/` later.
- **Audio normalization / loudness leveling** — out of this skill. The simulator does -15 LUFS at runtime.
- **PA processing** — see the **pa-make** skill.

## Related

- **pa-make** skill — PA workflow (separate; PA has different conventions, no `sta_cut`)
- `audio/README.md` — per-line IRL + sim quirks catalog (write-gate target above)
- `DATA_FORMAT.md` — route.json schema reference (field meanings, validation rules)
- `_dev_scripts/audio_id.py` — the named instruments (identity, structure, speech presence); `--selftest` calibrates them
- `_dev_scripts/trim_sta_silence.py` — trim leading/trailing/mid-gap silence
- `_dev_scripts/detect_sta_cut.py` — validate `sta_cut` placement
- `_dev_scripts/verify_sta_listen.py` — by-ear verification GUI
- `_dev_scripts/validate_pa.py` — PA silence-bracket validator (PA-only; lives here for proximity to other audio tools)
- `validate_data.py` — checks audio files referenced by routes exist on disk

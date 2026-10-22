---
paths:
  - "audio/**"
  - "audio_src/**"
  - "audio.py"
  - "_dev_scripts/audio_*.py"
  - "_dev_scripts/ab_audio*.py"
  - "_dev_scripts/verify_*.py"
  - "_dev_scripts/trim_*.py"
  - "_dev_scripts/detect_sta_cut.py"
  - "_dev_scripts/validate_pa.py"
  - "_dev_scripts/transcribe_pa.py"
  - "_dev_scripts/format_pa_timestamps.py"
  - "_tests/**/test_playback.py"
---

# Audio rules: PA / STA corpus, splitting, playback

Path-scoped: Claude Code loads this file when a file matching `paths:` is read or edited, not at session start. These rules moved here from `conventions.md`, `principles.md` and `critical_lessons.md` on 2026-10-22, to keep the always-loaded corpus under the combined-size limit. Same rules, narrower trigger.

## Conventions

### Naming

- **Use "sta" terminology** (not "departure_melody" or similar). Audio files, JSON fields, skill names, doc text — all use `sta`.
- **Folder structure carries metadata.** Diagram is extracted from `audio/<line>/<diagram>/` (e.g., `nambu/4027F/`). Don't flatten or rename.

### Tooling

- **ffmpeg is an external binary, not a Python dep — a second PC can lack it entirely.** The audio pipeline (`trim_sta_silence.py`, `trim_pa_silence.py`, every splice recipe in `/sta-make`, the verifiers' interactive trim) shells out to `ffmpeg`, so it appears in no `pyproject.toml` group and `check_deps.py` cannot see it. A machine without it fails with a bare `FileNotFoundError: [WinError 2]` from `subprocess`, which reads as a broken script rather than a missing tool. `_find_ffmpeg()` in the verifiers searches PATH plus the usual winget/chocolatey locations; when none hit, `uv run --with imageio-ffmpeg python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"` yields a static build with no system install — copy it to `C:/ffmpeg/bin/ffmpeg.exe` (already on the search list) to make it durable. 2026-07-25: the Chūō STA trim hit this on the second PC.
- **A native exe called from the Bash tool takes WINDOWS paths, and ffmpeg's concat demuxer answers a bad one with a short file and exit 0.** `$(pwd)` under Git Bash yields the MSYS form (`/d/pids_jre_simulator`), which ffmpeg resolves as `C:/d/…`, so a concat list built with it points at nothing. It prints `Impossible to open`, skips that entry, writes the remaining ones, and exits 0, so `set -e` does not fire and the output is a valid mp3 of the wrong length. 2026-08-12: a 48.7 s splice came out 20.6 s and only the duration check caught it. Build paths for native binaries as `D:/…` or via `cygpath -w`, and after any concat assert the output duration equals the sum of the inputs. The exit code is not the gate.
- **A concat whose duration checks out can still be wrong at the JOIN.** An mp3 frame depends on a bit reservoir that does not survive a stream-copy boundary, so the first appended frame decodes as a burst. 2026-08-20: appending 0.5 s to a PA put a +9.0 dBFS click into an otherwise −3.0 dBFS file, exactly at the seam, and the duration assertion passed because the length was right. The author heard it. When the pieces are contiguous in one source, which is the usual case when lengthening a cut, don't concat at all: widen the single `-ss/-to` window, which has no seam by construction. Reach for concat only when the pieces genuinely come from different places.
- **An undo, a snapshot, or a "have I done this yet" guard keys on a SESSION-scoped fact, never on a file existing.** A backup file's existence is a cross-session fact, because snapshots are not deleted, so `if not bak.exists(): copy()` preserves the OLDEST generation and the matching `if bak.exists(): restore()` reverts to it. On a line spliced in an earlier session that is one keystroke silently discarding that session's hand work while printing success; on Nambu it was 24 files and 64.1 s. Gate both halves on one in-memory record of "this run touched this item" (`verify_sta_listen.cut_before_splice`), so audio and metadata restore to the same moment. (2026-08-11, `_dev_scripts/verify_sta_listen.py`.)
- **Stamp a persisted verdict with the date it was given.** A results file whose items carry no date cannot distinguish a PASS from months ago from one given after today's edit, so a file spliced and not re-passed keeps a green verdict describing bytes that no longer exist, and the committed record in `audio/README.md` inherits the claim. (2026-08-11, same file as above.)
- **Comparing `pygame.Sound` buffers needs the mixer opened at the SOURCE rate.** `Sound.get_raw()` hands back the MIXER's format, so SDL resamples anything whose rate differs from what `mixer.init` was given. pygame defaults to 44100 and this corpus is 48000, so a comparison against the source array measures the resampler instead of the audio: a head-vs-itself correlation came back 0.0017 and read as a real aliasing bug. Derive the rate from the files with `sf.info(path).samplerate`, assert the fixtures agree with each other, and open the mixer there. Pinning a number puts the trap back. (2026-09-08, `_tests/t3_invariant/test_playback.py`.)

## Principles

#### Per-source ad-hoc scripts, not maintained libraries
When format varies between batches, generate a fresh script per source. Don't unify into one master tool.

**Scoped to code whose INPUT FORMAT varies — splitters, parsers, importers. It does not reach instruments.** A measurement that asks a source-invariant question ("are these two files one recording", "where are the silence runs") has one correct implementation and belongs in a maintained module with a self-test. (2026-08-08) The audio-pooling doc told the reader to regenerate its measurement recipes rather than maintain them; four got rebuilt from scratch that session and one returned a confidently wrong answer. Now `_dev_scripts/audio_id.py`. Ask which one you have: varies per source → ad-hoc; same question every time → library.

## Critical lessons

### 11. The instrument is not the artifact; the ear is (2026-07-26)

Reported 0 KAK across a line the user could hear one in on the first file, then kept building
detectors instead of taking the named file as truth. Four detectors later, the user's own hand
cut removed 388 ms where the detector had proposed 87. Separately, auto-converged 45 files onto
the skill's measured 250–400 ms gap target and turned a by-ear PASS into a FAIL — the target was
derived from one line and its fix inserts digital silence, which is audible on a recording that
has continuous ambience.

**Rule:** for audio, the deliverable is what a person hears. Every detector is a proxy for that
and fails silently. A number inside a band is not a pass, and a band derived on one line is a
default, not a gate. When the user reports hearing something the instrument does not show, the
instrument is wrong until proven otherwise — re-check the instrument, never the assertion.

Same frame error as `ocr.md` §7 and §8: reasoning from claude's own environment rather than the user's.
Here the environment is the measurement itself.

**Recurred 2026-08-08 on an ALREADY-ACCEPTED corpus, which is the worse form.** Saikyo's STA had
passed the ear under a previous session months earlier. Knowing none of that, I audited it with
derived thresholds and reported a list of defects — dead air, an incomplete loop, a mis-shared
cut — then a spectral band borrowed from keihin declared "0 of 24 files carry speech" when the
answer was 3. The ear then returned **25/25 PASS with every inherited cut unchanged**. Nothing was
ever wrong. The user: *"you, using your own scope, tell me something is broken."*

**Rule (second half):** a gate that already accepted authored content IS the standard for it.
Derived measurement can raise a question for the ear; it cannot return a verdict that the content
is wrong. And before auditing anything that already shipped, look for the prior verdict —
`audio_src/<line>/*_verify_results.json`. That tree is gitignored, so its absence proves nothing
and does not travel between machines; ask rather than assume a set is unverified. **The copy that DOES
travel is the line's `audio/README.md` section — read it before deriving any value it might already
hold.** 2026-08-22: seven `sta_cut` values were re-derived from `audio_id.structure` block boundaries for
a new Utsunomiya diagram; six landed within 80 ms of the by-ear figures and `nasushiobara` came out
**16.00 against the ear's 12.87**, because its cut sits inside a merged block — continuous ambience never
reaches the silence floor, so the instrument cannot see that boundary at all. The README said so, in the
section that also says those values "live here or nowhere". Self-caught, and only because the README was
opened later for an unrelated edit.

**Pattern:**
- A user-named file is ground truth. The detector's job becomes reproducing it; one that reports
  clean on that file is disqualified, not "mostly right."
- Treat a detected window as the INNER bound — human cuts land where the artifact stops being
  audible, which is further out than any threshold.
- Before applying a documented numeric convention across a corpus, check the corpus satisfies its
  premise (here: that the file has a near-silent floor to insert into). A band's known-positive
  must come from the corpus you are about to judge, never the one it was measured on.
- Don't rebuild the instruments. They are named in `_dev_scripts/audio_id.py` with a `--selftest`;
  re-deriving them per session is what makes these jobs hit-or-miss, and it is how the 0-of-24
  answer got produced. Four detectors in 2026-07-26, four more in 2026-08-08, same root.

**Scope:** all `sta-make` / `pa-make` detectors; anything gated by a by-ear pass; any re-audit of
content a human gate already passed.

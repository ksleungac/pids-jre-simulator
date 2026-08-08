# SPDX-License-Identifier: MIT
"""Named instruments for the audio workflows — identity, structure, speech presence.

WHY THIS EXISTS. These questions come up on every `sta-make` / `pa-make` /
pooling job, and each one has exactly one method that works and several that
return confident nonsense. Re-deriving them per session is how a job goes
hit-or-miss: 2026-08-08 rebuilt four of them from scratch and got the speech
question WRONG, on a corpus that had already passed the ear months earlier.

These are SOURCE-INVARIANT. "Are these one recording", "where are the silence
runs", "is there speech" do not vary by line, so they are maintained here.
Per-source SPLITTERS still stay ad-hoc under `audio_src/` — that is what
`principles.md § "Per-source ad-hoc scripts"` is about, and it does not reach
these.

CALIBRATE BEFORE YOU TRUST IT:  uv run _dev_scripts/audio_id.py --selftest
A gate that has never been observed to fail has not been shown to work.

    from audio_id import same_recording, exact_identity, structure, has_speech
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import correlate

SR = 22050
SILENCE_DB = -40.0  # activity floor; the repo's recordings sit well above it
_HERE = Path(__file__).resolve().parent


def load(path: Path | str, sr: int = SR) -> np.ndarray:
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def same_recording(a: Path | str, b: Path | str) -> tuple[float, float, float]:
    """(r, lag_seconds, overlap_seconds). r ~1.0 => one recording, two cuts.

    THE primary identity test. FFT correlation evaluates EVERY lag; a strided
    lag scan scores sample-identical audio near zero whenever the true offset
    falls between grid points, which is how 3 identical Chūō pairs were once
    reported "different recordings".

    Do not assume the sign of the peak lag — both +s and -s are scored on the
    real overlap and the winner kept. Getting that backwards makes every
    non-overlap region read full-scale, which looks like "both files hold
    unique content" for every pair.
    """
    x, y = load(a), load(b)
    c = correlate(x, y, mode="full", method="fft")
    lag = int(np.argmax(np.abs(c))) - (len(y) - 1)
    best = (-1.0, 0.0, 0.0)
    for s in (lag, -lag):
        if s >= 0:
            u, v = x[s:], y[: len(x) - s]
        else:
            u, v = x[: len(y) + s], y[-s:]
        n = min(len(u), len(v))
        if n < SR // 2:
            continue
        u, v = u[:n], v[:n]
        d = np.linalg.norm(u) * np.linalg.norm(v)
        r = float(np.dot(u, v) / d) if d else 0.0
        if r > best[0]:
            best = (r, s / SR, n / SR)
    return best


def exact_identity(a: Path | str, b: Path | str) -> bool:
    """True iff the DECODED samples are identical. Confirms a positive cheaply.

    NEVER use it to establish a negative: it says "different" with full
    confidence for two cuts of one recording (2026-07-26 it called all 112
    keihin PA files distinct; 30 pairs were sample-identical). Byte-hashing the
    mp3 is worse still — ID3 tags and encoder padding differ on identical audio.
    """
    return _pcm_sha(a) == _pcm_sha(b)


def _pcm_sha(p: Path | str) -> str:
    y, _ = librosa.load(str(p), sr=None, mono=False)
    return hashlib.sha256(np.ascontiguousarray(y)).hexdigest()


def contains(a: Path | str, b: Path | str) -> tuple[str | None, float, float]:
    """Which cut contains the other: ("a"|"b"|None, head_extra_s, tail_extra_s).

    Before discarding the loser of a duplicate pair, keep the cut that CONTAINS
    the other — trimming can remove a lead later, nothing restores audio
    truncated away now (`critical_lessons.md § 1`). Duration alone does not
    decide it; a longer file can be longer at the wrong end.
    """
    r, lag, _ = same_recording(a, b)
    if r < 0.95:
        return None, 0.0, 0.0
    da, db = len(load(a)) / SR, len(load(b)) / SR
    head = -lag  # >0 => b starts earlier
    tail = (db - head) - da
    if head >= -1e-3 and tail >= -1e-3:
        return "b", head, tail
    if head <= 1e-3 and tail <= 1e-3:
        return "a", -head, -tail
    return None, head, tail


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------


def structure(path: Path | str, sta_cut: float | None = None, merge_gap: float = 0.30) -> dict:
    """Activity blocks + silence runs, and the silence run holding `sta_cut`.

    ANCHOR ON sta_cut, not on "the first music block". A melody with an
    internal break longer than `merge_gap` makes first-block heuristics report
    a gap mid-melody — that produced three bogus "CUT OUTSIDE GAP" flags on
    Saikyo. Passing sta_cut asks the only non-circular question there is: does
    the authored cut sit in a silence, and what bounds it.

    Returns {duration, lead, trail, blocks, cut_silence, next_onset, peaks}.
    """
    y = load(path)
    hop = int(SR * 0.02)
    rms = 20 * np.log10(librosa.feature.rms(y=y, hop_length=hop)[0] + 1e-10)
    t = np.arange(len(rms)) * 0.02
    act = rms > SILENCE_DB

    runs, st = [], None
    for i, a in enumerate(act):
        if a and st is None:
            st = i
        elif not a and st is not None:
            runs.append((float(t[st]), float(t[i - 1])))
            st = None
    if st is not None:
        runs.append((float(t[st]), float(t[-1])))
    blocks: list[tuple[float, float]] = []
    for s0, e0 in runs:
        if blocks and s0 - blocks[-1][1] < merge_gap:
            blocks[-1] = (blocks[-1][0], e0)
        else:
            blocks.append((s0, e0))

    dur = len(y) / SR
    out = {
        "duration": dur,
        "lead": blocks[0][0] if blocks else float("nan"),
        "trail": dur - blocks[-1][1] if blocks else float("nan"),
        "blocks": blocks,
        "cut_silence": None,
        "next_onset": None,
        "peak_db": float(20 * np.log10(np.abs(y).max() + 1e-10)),
    }
    if sta_cut is not None:
        ci = int(sta_cut / 0.02)
        if 0 <= ci < len(act) and not act[ci]:
            a_i = ci
            while a_i > 0 and not act[a_i - 1]:
                a_i -= 1
            b_i = ci
            while b_i < len(act) - 1 and not act[b_i + 1]:
                b_i += 1
            out["cut_silence"] = (float(t[a_i]), float(t[b_i]))
            out["next_onset"] = float(t[min(b_i + 1, len(t) - 1)])
    return out


def loop_repeat(path: Path | str, base: tuple[float, float], later: tuple[float, float]) -> tuple[float, float]:
    """(r, fraction_of_base) for a candidate repeated melody loop.

    sta-make Pattern B: r >= 0.80 means a loop repeat; COMPLETE if it runs
    >= 85% of the base loop (keep it — real content), else a truncated stub
    (remove). Chūō separated cleanly at 12% vs 100–102%; Saikyo's JA24 landed
    at 77%, which the rule cannot adjudicate — that is an ear call, not a
    threshold call.
    """
    y = load(path)
    b0 = y[int(base[0] * SR) : int(base[1] * SR)]
    l0 = y[int(later[0] * SR) : int(later[1] * SR)]
    if len(l0) < SR // 4 or len(b0) < SR // 4:
        return 0.0, 0.0
    head = b0[: len(l0)]
    n = min(len(head), len(l0))
    u, v = head[:n], l0[:n]
    d = np.linalg.norm(u) * np.linalg.norm(v)
    return (float(np.dot(u, v) / d) if d else 0.0), (later[1] - later[0]) / (base[1] - base[0])


# --------------------------------------------------------------------------
# speech presence
# --------------------------------------------------------------------------

# Whisper emits these on non-speech audio. They are NOT content; a sweep that
# counts them reports announcements that do not exist.
_HALLUCINATIONS = (
    "ご視聴ありがとうございました",
    "Thank you for watching",
    "ご覧いただきありがとうございました",
    "おやすみなさい",
)
# transcribe_pa.py primes the model with this; it gets echoed back verbatim on
# files with no speech. Same failure class, harder to spot because it reads as
# plausible PA vocabulary. (2026-08-08: read as a real-but-garbled announcement.)
_PROMPT_ECHO = "などの案内が含まれます"


def has_speech(path: Path | str, device: str = "cuda") -> tuple[bool, str]:
    """(has_speech, transcript). Whisper is the ONLY instrument that answers this.

    Do NOT use a spectral hf/lf ratio to separate speech from melody. The band
    in `sta-make` Step 7.5 (melody 0.03-0.09, announcement 0.2-0.5) is
    CAPTURE-CHAIN SPECIFIC: on Saikyo's platform recordings a known, clearly
    intelligible announcement reads 0.002 — indistinguishable from melody — and
    a sweep built on it confidently reported "0 of 24 files have speech" when
    the true answer was 3. Calibrate any band against a known-positive from the
    SAME line before believing it.
    """
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.json"
        cmd = [sys.executable, str(_HERE / "transcribe_pa.py"), str(path), "--model", "large-v3", "--device", device, "--out", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"transcribe_pa failed: {r.stderr[-400:]}")
        data = json.loads(out.read_text(encoding="utf-8"))
    text = " ".join(s["text"].strip() for s in data.get("segments", [])).strip()
    for bad in _HALLUCINATIONS:
        text = text.replace(bad, "").strip(" 。.|")
    if _PROMPT_ECHO in text:
        text = ""
    return bool(text), text


# --------------------------------------------------------------------------
# selftest — a known-same and a known-different, from the shipped corpus
# --------------------------------------------------------------------------


def _selftest() -> int:
    root = _HERE.parent / "audio"
    same = root / "saikyo" / "sta" / "JA08_OSK-down.mp3"
    diff = root / "saikyo" / "sta" / "JA12_IKB-down.mp3"
    if not same.exists() or not diff.exists():
        print(f"SKIP: calibration pair missing under {root/'saikyo'/'sta'}")
        return 0
    ok = True

    r, lag, _ = same_recording(same, same)
    good = r > 0.999 and abs(lag) < 0.01
    ok &= good
    print(f"[{'ok ' if good else 'FAIL'}] same_recording(x, x)      r={r:.4f} lag={lag:+.3f}s   expect r~1.000")

    r2, _, _ = same_recording(same, diff)
    good = r2 < 0.5
    ok &= good
    print(f"[{'ok ' if good else 'FAIL'}] same_recording(x, y)      r={r2:.4f}                 expect r<0.5")

    good = exact_identity(same, same) and not exact_identity(same, diff)
    ok &= good
    print(f"[{'ok ' if good else 'FAIL'}] exact_identity             positive+negative")

    st = structure(same, sta_cut=9.0)
    good = st["cut_silence"] is not None and st["cut_silence"][0] < 9.0 < st["cut_silence"][1]
    ok &= good
    print(f"[{'ok ' if good else 'FAIL'}] structure(cut in silence)  cut_silence={st['cut_silence']}")

    st2 = structure(same, sta_cut=1.0)  # inside the melody — must NOT report a silence
    good = st2["cut_silence"] is None
    ok &= good
    print(f"[{'ok ' if good else 'FAIL'}] structure(cut in content)  cut_silence={st2['cut_silence']}   expect None")

    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="calibrate against a known-same and known-different pair")
    ap.add_argument("--same", nargs=2, metavar=("A", "B"), help="report same_recording + containment for two files")
    ap.add_argument("--structure", nargs="+", metavar="FILE", help="print structure; optional trailing --cut N")
    ap.add_argument("--cut", type=float, help="sta_cut for --structure")
    ap.add_argument("--speech", metavar="FILE", help="report whether a file contains speech")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if a.same:
        r, lag, ov = same_recording(*a.same)
        who, head, tail = contains(*a.same)
        print(f"r={r:.4f} lag={lag:+.3f}s overlap={ov:.2f}s")
        print(f"containing cut: {who or 'neither/undecided'}  head_extra={head:+.3f}s tail_extra={tail:+.3f}s")
        return 0
    if a.structure:
        for f in a.structure:
            st = structure(f, sta_cut=a.cut)
            print(f"{f}\n  dur={st['duration']:.2f}s lead={st['lead']:.3f}s trail={st['trail']:.3f}s peak={st['peak_db']:.1f}dB")
            print(f"  blocks={[(round(s,2),round(e,2)) for s,e in st['blocks']]}")
            if a.cut is not None:
                print(f"  cut_silence={st['cut_silence']} next_onset={st['next_onset']}")
        return 0
    if a.speech:
        yes, text = has_speech(a.speech)
        print(f"speech={yes}  {text[:200]}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

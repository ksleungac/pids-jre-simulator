"""Trim PA lead/trail to ~80ms before/after voice, using onset detection.

Voice onset = first frame where amplitude exceeds noise_floor + 12dB
AND delta over 30ms > 6dB (sharp attack, not flat noise).

    uv run python _dev_scripts/trim_pa_silence.py audio/tokaido/1865E/pa
"""

import argparse, subprocess, sys
from pathlib import Path
import librosa, numpy as np

TARGET_S = 0.080


def _find_ffmpeg() -> str:
    import shutil

    found = shutil.which("ffmpeg")
    if found:
        return found
    for c in [Path("C:/ProgramData/chocolatey/bin/ffmpeg.exe"), Path("C:/ffmpeg/bin/ffmpeg.exe")]:
        if c.exists():
            return str(c)
    return "ffmpeg"


def _ffprobe_dur(path: Path) -> float:
    r = subprocess.run(
        [
            _find_ffmpeg().replace("ffmpeg", "ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return float(r.stdout.strip() or 0)


def detect_voice_onset(rms_db: np.ndarray, noise_floor: float) -> float:
    """Return time (seconds) of voice onset, or 0.0."""
    for i in range(3, len(rms_db)):
        if rms_db[i] > noise_floor + 12 and (rms_db[i] - rms_db[i - 3]) > 6:
            return round(i * 0.01, 3)
    return 0.0


def detect_voice_end(rms_db: np.ndarray, noise_floor: float, dur: float) -> float:
    """Return time (seconds) of voice end, or duration."""
    below = 0
    for i in range(len(rms_db) - 1, -1, -1):
        if rms_db[i] < noise_floor + 6:
            below += 1
            if below >= 5:
                return round(min(dur, i * 0.01 + 0.05), 3)
        else:
            below = 0
    return dur


def trim_file(path: Path, onset: float, end: float, dur: float) -> tuple[bool, bool]:
    """Trim lead to onset-TARGET_S and trail from end+TARGET_S. Returns (did_lead, did_trail)."""
    lead_trim = max(0.0, onset - TARGET_S)
    trail_trim = max(0.0, dur - (end + TARGET_S))

    if lead_trim <= 0.01 and trail_trim <= 0.01:
        return (False, False)

    new_start = lead_trim if lead_trim > 0.01 else 0.0
    new_dur = (dur - trail_trim) - new_start if trail_trim > 0.01 else dur - new_start

    tmp = path.with_suffix(".tmp.mp3")
    cmd = [_find_ffmpeg(), "-y", "-loglevel", "error"]
    if new_start > 0.001:
        cmd += ["-ss", f"{new_start:.3f}"]
    cmd += ["-i", str(path), "-t", f"{new_dur:.3f}", "-c", "copy", str(tmp)]
    subprocess.run(cmd, check=True)
    tmp.replace(path)
    return (lead_trim > 0.01, trail_trim > 0.01)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pa_dir", type=Path, help="audio/<line>/<diagram>/pa")
    args = ap.parse_args()

    if not args.pa_dir.exists():
        print(f"not found: {args.pa_dir}", file=sys.stderr)
        return 1

    files = sorted(args.pa_dir.glob("*.mp3"), key=lambda p: p.name)
    trimmed_lead = 0
    trimmed_trail = 0
    skipped = 0

    for p in files:
        y, sr = librosa.load(str(p), sr=22050, mono=True)
        dur = len(y) / sr
        hop = int(sr * 0.01)
        rms = np.array([np.sqrt(np.mean(y[i : i + hop] ** 2)) for i in range(0, len(y) - hop, hop)])
        rms_db = 20 * np.log10(rms + 1e-10)
        # Compute noise floor from quietest segments across whole file
        # Clamp: pure-digital-silence starts give -200dB garbage
        sorted_db = np.sort(rms_db)
        noise_floor = float(np.median(sorted_db[: max(1, len(sorted_db) // 5)]))
        noise_floor = max(noise_floor, -60.0)

        onset = detect_voice_onset(rms_db, noise_floor)
        did_lead, _ = trim_file(p, onset, dur, dur)  # end=dur → no trail trim

        lead_ms = onset * 1000
        actions = []
        if did_lead:
            actions.append(f"trim_lead {(onset - TARGET_S)*1000:.0f}ms")
            trimmed_lead += 1
        else:
            actions.append(f"lead OK ({lead_ms:.0f}ms)")
            skipped += 1

        print(f"  {p.name:>8s}  noise={noise_floor:.1f}dB  onset={onset:.3f}s  dur={dur:.1f}s  ->  {', '.join(actions)}")

    print(f"\nDone. {len(files)} files: {trimmed_lead} lead-trimmed, {skipped} already-OK")

    # Run validate_pa.py as final summary gate
    print()
    subprocess.run(["uv", "run", "_dev_scripts/validate_pa.py", str(args.pa_dir)])
    return 0


if __name__ == "__main__":
    sys.exit(main())

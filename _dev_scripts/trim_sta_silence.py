# SPDX-License-Identifier: MIT
"""Trim leading + trailing + mid-file silence on STA mp3s.

- Leading and trailing silence trimmed to ~0.2 s pads (lossless stream-copy).
- Mid-file silence between music-end and voice-start trimmed to ~1.0 s
  (re-encoded — mp3 frame boundaries don't allow lossless mid-file splice).
  Only runs when detection confidence is high and the gap is in a sane range.

With --route, patches route.json sta_cut values (decremented by the total amount
shifted earlier from the file start).

    uv run _dev_scripts/trim_sta_silence.py audio/sobu/sta

Idempotent: re-running on already-trimmed files is a no-op.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from detect_sta_cut import detect

PAD = 0.2  # target leading + trailing silence pad
MID_GAP = 1.0  # target silence between music end and voice start
MIN_CONFIDENCE = 0.7  # skip mid-trim if change-point is ambiguous
MIN_GAP = 0.5  # skip mid-trim if gap is already short
MAX_GAP = 5.0  # skip mid-trim if gap is implausibly large (something weird)


def detect_silences(path: Path, threshold_db: int = -40) -> tuple[float, list[float], list[float]]:
    """Return (duration, silence_starts, silence_ends)."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", f"silencedetect=noise={threshold_db}dB:d=0.1", "-f", "null", "-"],
        capture_output=True,
        text=True,
    ).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return duration, starts, ends


def trim_ends(path: Path, lead_trim: float, new_duration: float) -> None:
    """Lossless stream-copy: trim from start (-ss) and end (-t)."""
    tmp = path.with_suffix(".tmp.mp3")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if lead_trim > 0:
        cmd += ["-ss", f"{lead_trim:.3f}"]
    cmd += ["-i", str(path), "-t", f"{new_duration - lead_trim:.3f}", "-c", "copy", str(tmp)]
    subprocess.run(cmd, check=True)
    shutil.move(str(tmp), str(path))


def trim_middle_gap(path: Path, music_end: float, voice_start: float) -> float:
    """Splice the file to leave only MID_GAP seconds of silence between music_end
    and voice_start. Returns the seconds removed (= sta_cut shift). Re-encodes."""
    keep_until = music_end + MID_GAP / 2
    skip_until = voice_start - MID_GAP / 2
    removed = skip_until - keep_until  # how much silence we drop
    if removed <= 0:
        return 0.0

    tmp = path.with_suffix(".tmp.mp3")
    # filter_complex: take [0, keep_until] then [skip_until, end], concat.
    # Both endpoints sit inside the silence window by construction → no audible
    # clip on music or voice content.
    filter_str = (
        f"[0:a]atrim=0:{keep_until:.3f},asetpts=PTS-STARTPTS[a1];"
        f"[0:a]atrim={skip_until:.3f},asetpts=PTS-STARTPTS[a2];"
        f"[a1][a2]concat=n=2:v=0:a=1[out]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-filter_complex", filter_str, "-map", "[out]", "-q:a", "2", str(tmp)],
        check=True,
    )
    shutil.move(str(tmp), str(path))
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sta_dir", type=Path, help="folder containing STA mp3s")
    ap.add_argument("--route", type=Path, help="route.json to patch sta_cut values")
    args = ap.parse_args()

    files = sorted(args.sta_dir.glob("*.mp3"))
    if not files:
        print(f"no mp3 files in {args.sta_dir}", file=sys.stderr)
        return 1

    # build {basename: lead_trim} so we can patch route.json after
    lead_trims: dict[str, float] = {}

    for f in files:
        duration, starts, ends = detect_silences(f)

        # leading silence: first silence_end if it starts at 0
        lead_trim = 0.0
        if ends and starts and starts[0] < 0.05 and ends[0] > PAD + 0.1:
            lead_trim = ends[0] - PAD

        # trailing silence: last silence runs to EOF if its end is near duration
        trail_trim = 0.0
        if ends and abs(ends[-1] - duration) < 0.1:
            trail_dur = duration - starts[-1]
            if trail_dur > PAD + 0.1:
                trail_trim = trail_dur - PAD

        actions: list[str] = []

        # 1. Lead + trail (lossless stream-copy)
        if lead_trim > 0 or trail_trim > 0:
            new_duration = duration - trail_trim
            trim_ends(f, lead_trim, new_duration)
            actions.append(f"lead -{lead_trim:.2f}s  trail -{trail_trim:.2f}s")

        # 2. Mid-file gap (re-encode, only when safe). Detect on the now-cleaned file.
        result = detect(f)
        gap = result.voice_start - result.music_end
        mid_trim = 0.0
        if result.confidence >= MIN_CONFIDENCE and MIN_GAP < gap < MAX_GAP and gap > MID_GAP + 0.1:
            mid_trim = trim_middle_gap(f, result.music_end, result.voice_start)
            actions.append(f"mid-gap {gap:.2f}s -> {MID_GAP:.1f}s  (sta_cut shift -{mid_trim:.2f}s)")

        if not actions:
            print(f"{f.name:50s} clean, skip")
        else:
            print(f"{f.name:50s} {actions[0]}")
            for a in actions[1:]:
                print(f"{'':50s} {a}")

        total_shift = lead_trim + mid_trim
        if total_shift > 0:
            lead_trims[f.stem] = total_shift

    # patch route.json sta_cut values
    # Parse + write JSON instead of regex-substituting text — handles compact
    # AND multi-line list formats, single AND multi-element sta lists. Re-emits
    # with indent=4 (matches the project convention; format may shift if input
    # was compact, but both forms are valid JSON).
    if args.route and lead_trims:
        import json

        route = json.loads(args.route.read_text(encoding="utf-8"))
        for stop in route["stops"]:
            for sta_name in stop.get("sta", []):
                if sta_name in lead_trims and stop.get("sta_cut") is not None:
                    old = stop["sta_cut"]
                    new = round(old - lead_trims[sta_name], 1)
                    if new == old:
                        continue
                    stop["sta_cut"] = new
                    print(f"  route.json: {sta_name} sta_cut {old} -> {new}")
                    break  # one shift per stop even if multi-variant sta
        args.route.write_text(json.dumps(route, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Validate PA mp3 files: each should have brief silence at start and end.

Each PA segment is one announcement bracketed by silence (the voice doesn't run
right up against the cut points in the source). If a file is missing leading or
trailing silence (below MIN_SILENCE seconds), the timestamp cut almost certainly
landed inside speech — usually the previous announcement bleeding in or the
current one being clipped at the tail.

    uv run _dev_scripts/validate_pa.py audio/sobu/pa
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MIN_SILENCE = 0.05  # seconds — less than this at either end = likely wrong cut


def detect_silences(path: Path) -> tuple[float, list[float], list[float]]:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "silencedetect=noise=-40dB:d=0.05", "-f", "null", "-"],
        capture_output=True,
        text=True,
    ).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return duration, starts, ends


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pa_dir", type=Path, help="folder containing PA mp3s")
    args = ap.parse_args()

    files = sorted(args.pa_dir.glob("*.mp3"))
    if not files:
        print(f"no mp3 files in {args.pa_dir}", file=sys.stderr)
        return 1

    print(f"{'file':40s}  {'lead':>7s}  {'trail':>7s}  status")
    print("-" * 75)
    flagged = 0
    for f in files:
        duration, starts, ends = detect_silences(f)

        # leading silence: first silence segment starts at 0
        lead = ends[0] if ends and starts and starts[0] < 0.05 else 0.0
        # trailing silence: last silence segment ends at duration
        trail = (duration - starts[-1]) if ends and abs(ends[-1] - duration) < 0.05 else 0.0

        flags = []
        if lead < MIN_SILENCE:
            flags.append("MISSING LEAD (cut into prev voice)")
        if trail < MIN_SILENCE:
            flags.append("MISSING TRAIL (cut into next voice)")
        status = " | ".join(flags) if flags else "ok"
        if flags:
            flagged += 1
        print(f"{f.name:40s}  {lead:>6.2f}s  {trail:>6.2f}s  {status}")

    print("-" * 75)
    print(f"flagged: {flagged}/{len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

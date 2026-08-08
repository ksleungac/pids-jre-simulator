# SPDX-License-Identifier: MIT
"""Format proposed PA timestamps with a safety margin.

Input via JSON (file or stdin):
    {
      "stations": [
        {"name": "新日本橋",   "voice_onsets": [742.5]},
        {"name": "馬喰町",     "voice_onsets": [784.2]},
        {"name": "新小岩",     "voice_onsets": [863.8, 908.7]},
        ...
      ]
    }

`voice_onsets` is a list of seconds (float, in original-source coordinates) at
which Whisper detected the start of each PA voice cluster for that station.
1 entry → station has 1 PA segment (e.g. terminus, or a single dep).
2 entries → 1st = {prev}-dep, 2nd = {this}-arr (per timestamps.txt convention).

Output: standard timestamps.txt format ("idx\\tname MM:SS [MM:SS]") on stdout.

Safety margin: each voice onset is floored to the nearest second BEFORE it,
guaranteeing the cut sits at or before the actual voice (≤ 1 s of leading
silence). Avoids landing inside the voice (which would clip the announcement).

Usage:
    cat proposal.json | uv run _dev_scripts/format_pa_timestamps.py
    uv run _dev_scripts/format_pa_timestamps.py proposal.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def fmt_mmss(seconds: float) -> str:
    s_floor = math.floor(seconds)  # safety margin: round DOWN, not nearest
    m, s = divmod(s_floor, 60)
    return f"{m:02d}:{s:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", nargs="?", type=Path, help="JSON file (default: stdin)")
    args = ap.parse_args()

    raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    data = json.loads(raw)

    for i, stop in enumerate(data["stations"], start=1):
        ts = " ".join(fmt_mmss(t) for t in stop["voice_onsets"])
        print(f"{i}\t{stop['name']} {ts}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Split src.mp3 into 28 PA segments for audio/sobu/1217F/pa/.

Each segment runs from its start timestamp up to the next segment's start
(last segment runs to EOF). Names follow the descriptive {prev}-dep / {this}-arr
convention so the file purpose is obvious without consulting route.json.
"""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent / "src.mp3"
OUT = Path(__file__).resolve().parents[1] / "audio" / "sobu" / "1217F" / "pa"

# (start_M:SS, output_basename)
# Segment N runs from SEGMENTS[N][0] to SEGMENTS[N+1][0]; last runs to EOF.
SEGMENTS = [
    ("12:22", "tokyo-dep"),
    ("13:04", "shin-nihombashi-dep"),
    ("13:31", "bakurocho-dep"),
    ("14:24", "kinshicho-dep"),
    ("15:08", "shin-koiwa-arr"),
    ("15:40", "shin-koiwa-dep"),
    ("16:21", "ichikawa-arr"),
    ("16:55", "ichikawa-dep"),
    ("17:37", "funabashi-arr"),
    ("18:15", "funabashi-dep"),
    ("18:40", "tsudanuma-arr"),
    ("19:17", "tsudanuma-dep"),
    ("19:24", "inage-arr"),
    ("19:54", "inage-dep"),
    ("20:43", "chiba-dep"),
    ("22:05", "tsuga-arr"),
    ("22:35", "tsuga-dep"),
    ("23:01", "yotsukaido-arr"),
    ("23:16", "yotsukaido-dep"),
    ("23:23", "monoi-arr"),
    ("23:38", "monoi-dep"),
    ("24:00", "sakura-dep"),
    ("24:17", "shisui-arr"),
    ("24:30", "shisui-dep"),
    ("24:39", "narita-arr"),
    ("25:15", "narita-dep"),
    ("26:25", "airport-terminal-2-arr"),
    ("26:42", "narita-airport-arr"),
]


def to_sec(ts: str) -> int:
    m, s = map(int, ts.split(":"))
    return m * 60 + s


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source not found: {SRC}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    for i, (start, name) in enumerate(SEGMENTS):
        start_sec = to_sec(start)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start_sec), "-i", str(SRC)]
        if i + 1 < len(SEGMENTS):
            duration = to_sec(SEGMENTS[i + 1][0]) - start_sec
            cmd += ["-t", str(duration)]
        cmd += ["-c", "copy", str(OUT / f"{name}.mp3")]
        print(f"[{i+1:2d}/{len(SEGMENTS)}] {name}.mp3 (start={start})")
        subprocess.run(cmd, check=True)

    print(f"\nDone. {len(SEGMENTS)} files written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

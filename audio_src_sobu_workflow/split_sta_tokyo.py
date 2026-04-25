"""Split src_from_tokyo.mp3 into 12 STA segments for audio/sobu/1217F/sta/.

Format for THIS source: 2 timestamps per line (start, cut). Segment end = next
line's start; last segment runs to EOF. Different from sta_from_higashichiba.mp3
(which used 3 timestamps per line). Per-source script — formats vary.

sta_cut is computed as cut - start.
"""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent / "src_from_tokyo.mp3"
PROJECT = Path(__file__).resolve().parents[1]
OUT_OP = PROJECT / "audio" / "sobu" / "1217F" / "sta"
OUT_ARCHIVE = PROJECT / "audio" / "_archive" / "sobu" / "1217F" / "sta"

# (start, cut, basename, dest) — segment N runs to SEGMENTS[N+1][0]; last runs to EOF.
# dest: "op" → operational sta/, "archive" → _archive/ (other-platform takes for 1217F).
EOF = "5:18"
SEGMENTS = [
    ("0:24", "0:40", "tokyo_4_jr-sh5-1",                  "op"),       # 1217F departs platform 4
    ("0:47", "1:07", "tokyo_3_twilight",                  "archive"),
    ("1:14", "1:34", "tokyo_2_twilight",                  "archive"),
    ("1:41", "1:53", "shin-nihombashi_2_hassha-beru",     "op"),
    ("1:59", "2:06", "bakurocho_2_hassha-beru",           "op"),
    ("2:12", "2:43", "kinshicho_4_gota-del-vient",        "op"),
    ("2:49", "3:08", "shin-koiwa_4_gota-del-vient",       "op"),
    ("3:15", "3:35", "ichikawa_4_rakuraku-tetsudo-ryoko", "op"),
    ("3:40", "4:03", "funabashi_4_horidei",               "op"),
    ("4:09", "4:30", "tsudanuma_1_horidei",               "op"),       # 1217F departs platform 1
    ("4:36", "4:48", "tsudanuma_2_horidei",               "archive"),
    ("4:54", "5:07", "inage_4_horidei",                   "op"),
]


def to_sec(ts: str) -> int:
    m, s = map(int, ts.split(":"))
    return m * 60 + s


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source not found: {SRC}", file=sys.stderr)
        return 1
    OUT_OP.mkdir(parents=True, exist_ok=True)
    OUT_ARCHIVE.mkdir(parents=True, exist_ok=True)

    print(f"{'file':<40} {'dest':>8} {'start':>6} {'cut':>6} {'end':>6} {'sta_cut':>8}")
    for i, (start, cut, name, dest) in enumerate(SEGMENTS):
        out_dir = OUT_ARCHIVE if dest == "archive" else OUT_OP
        start_sec = to_sec(start)
        end = SEGMENTS[i + 1][0] if i + 1 < len(SEGMENTS) else EOF
        duration = to_sec(end) - start_sec
        sta_cut_sec = to_sec(cut) - start_sec
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start_sec), "-i", str(SRC),
            "-t", str(duration),
            "-c", "copy", str(out_dir / f"{name}.mp3"),
        ]
        print(f"{name + '.mp3':<40} {dest:>8} {start:>6} {cut:>6} {end:>6} {sta_cut_sec:>8}")
        subprocess.run(cmd, check=True)

    print(f"\nDone. {len(SEGMENTS)} files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

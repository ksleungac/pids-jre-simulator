"""Split sta_from_higashichiba.mp3 into 8 STA segments for audio/sobu/1217F/sta/.

Format note: each segment is bounded by an explicit (start, end) — unlike PA,
the source has gaps between recordings so we can't just chain start-to-start.
The (N) suffix in filenames is the JR East platform number where the melody
plays IRL; for stations with only one recording we omit it.

sta_cut is computed as (cut_point - start), seconds from the START of the
segment — this is the offset INTO the file where melody ends and the door
chime begins.
"""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent / "sta_from_higashichiba.mp3"
PROJECT = Path(__file__).resolve().parents[1]
OUT_OP = PROJECT / "audio" / "sobu" / "1217F" / "sta"
OUT_ARCHIVE = PROJECT / "audio" / "_archive" / "sobu" / "1217F" / "sta"

# (start, cut, end, basename, dest) — dest: "op" → operational sta/, "archive" → _archive/
SEGMENTS = [
    ("0:12", "1:08", "1:18", "tsuga_2_gota-del-vient",          "op"),
    ("1:19", "1:39", "1:51", "yotsukaido_2",                    "op"),  # song still unknown
    ("2:41", "3:01", "3:06", "monoi_1_gota-del-vient",          "op"),
    ("3:39", "4:16", "4:27", "sakura_2_verde-rayo-v2",          "op"),
    ("4:28", "4:54", "4:59", "shisui_gota-del-vient",           "op"),   # end bumped 4:57 → 4:59
    ("4:59", "5:32", "5:41", "narita_3_suito-koru",             "op"),
    ("5:43", "6:08", "6:17", "narita_5_furawa-shoppu",          "archive"),  # 1217F uses platform 3
    ("6:19", "6:47", "7:06", "airport-terminal-2_chaimu-3b4",   "op"),
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
    for start, cut, end, name, dest in SEGMENTS:
        out_dir = OUT_ARCHIVE if dest == "archive" else OUT_OP
        start_sec = to_sec(start)
        end_sec = to_sec(end)
        cut_sec = to_sec(cut) - start_sec  # sta_cut is from start of segment
        duration = end_sec - start_sec
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start_sec), "-i", str(SRC),
            "-t", str(duration),
            "-c", "copy", str(out_dir / f"{name}.mp3"),
        ]
        print(f"{name + '.mp3':<40} {dest:>8} {start:>6} {cut:>6} {end:>6} {cut_sec:>8}")
        subprocess.run(cmd, check=True)

    print(f"\nDone. {len(SEGMENTS)} files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

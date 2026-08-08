# SPDX-License-Identifier: MIT
"""A/B two audio files side by side and record a by-ear verdict.

Built because measuring "are these the same recording" kept giving answers that
disagreed with the ear. Acoustic similarity can only prove two files ARE the same
audio; it cannot tell "different take of the same announcement" from "different
announcement", and every automated attempt at that distinction here was wrong at
least once. So: play them, decide, move on.

Usage
    uv run _dev_scripts/ab_audio.py --manifest _audio_backup/chuo_pa_ab.json
    uv run _dev_scripts/ab_audio.py audio/chuo/pa/kanda-arr-1654T.mp3 audio/chuo/pa/kanda-arr-916H.mp3

Manifest format — a list of pairs, optional label:
    [{"label": "神田 arr", "a": "audio/.../33.mp3", "b": "audio/.../24.mp3"}, ...]

Keys per pair:  [enter] replay both · a / b replay one · s same · d different · q quit

Verdicts are written back next to the manifest as <manifest>.verdicts.json, so an
interrupted session can be resumed and the result is reviewable afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pygame

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

GAP_S = 0.4  # silence between A and B — long enough to separate, short enough to compare


def play(path: Path, tag: str, clip: float = 0.0) -> None:
    snd = pygame.mixer.Sound(str(path))
    dur = snd.get_length()
    shown = min(dur, clip) if clip else dur
    print(f"    {tag}  {shown:5.1f}s  {path}", flush=True)
    ch = snd.play()
    deadline = time.monotonic() + shown
    while ch.get_busy() and time.monotonic() < deadline:
        time.sleep(0.05)
    ch.stop()


def play_pair(a: Path, b: Path, clip: float = 0.0) -> None:
    play(a, "A", clip)
    time.sleep(GAP_S)
    play(b, "B", clip)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help="two files to compare directly")
    ap.add_argument("--manifest", type=Path, help="JSON list of pairs to walk through")
    ap.add_argument(
        "--auto",
        action="store_true",
        help="play every pair back-to-back with no prompting — for when the session "
        "driving this script has no stdin. Call out verdicts afterwards.",
    )
    ap.add_argument("--clip", type=float, default=0.0, help="cap each clip to N seconds (0 = full)")
    args = ap.parse_args()

    pygame.mixer.init()

    if args.files:
        if len(args.files) != 2:
            print("give exactly two files, or use --manifest")
            return 2
        play_pair(*args.files)
        return 0

    if not args.manifest:
        ap.print_help()
        return 2

    pairs = json.loads(args.manifest.read_text(encoding="utf-8"))
    out_path = args.manifest.with_suffix(".verdicts.json")
    verdicts = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    if args.auto:
        print(f"playing {len(pairs)} pairs back-to-back — A then B, {GAP_S}s between.\n")
        for n, pair in enumerate(pairs, 1):
            a, b = Path(pair["a"]), Path(pair["b"])
            if not a.exists() or not b.exists():
                print(f"[{n}/{len(pairs)}] {pair.get('label')}: MISSING FILE — skipped")
                continue
            print(f"[{n}/{len(pairs)}] {pair.get('label')}")
            play_pair(a, b, args.clip)
            time.sleep(1.0)  # beat between pairs so they don't run together
        print("\ndone — call out any pair that sounded different.")
        return 0

    todo = [p for p in pairs if p.get("label", "") not in verdicts]
    print(f"{len(pairs)} pairs, {len(verdicts)} already judged, {len(todo)} to go\n")

    for n, pair in enumerate(todo, 1):
        label = pair.get("label", f"pair {n}")
        a, b = Path(pair["a"]), Path(pair["b"])
        if not a.exists() or not b.exists():
            print(f"[{n}/{len(todo)}] {label}: MISSING FILE — skipped")
            continue
        print(f"[{n}/{len(todo)}] {label}")
        play_pair(a, b)
        while True:
            key = input("    [enter]=replay  a  b  s=same  d=different  q=quit > ").strip().lower()
            if key == "":
                play_pair(a, b)
            elif key == "a":
                play(a, "A")
            elif key == "b":
                play(b, "B")
            elif key in ("s", "d"):
                verdicts[label] = "same" if key == "s" else "different"
                out_path.write_text(json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"    -> {verdicts[label]}\n")
                break
            elif key == "q":
                print(f"\nstopped. verdicts so far in {out_path}")
                return 0

    same = sum(1 for v in verdicts.values() if v == "same")
    diff = sum(1 for v in verdicts.values() if v == "different")
    print(f"\ndone — {same} same, {diff} different")
    print(f"verdicts: {out_path}")
    if diff:
        print("\nmarked different (these must NOT be collapsed):")
        for k, v in verdicts.items():
            if v == "different":
                print(f"  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

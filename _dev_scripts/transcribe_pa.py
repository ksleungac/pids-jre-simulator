# SPDX-License-Identifier: MIT
"""PoC: transcribe a PA source mp3 with Whisper to recover timestamped segments.

Idea: instead of the user manually scrubbing through src.mp3 to write
timestamps.txt, run Whisper, get text + timestamps for every utterance, then
match utterances against the route's station names to auto-generate timestamps.

This is just step 1 — get the raw transcription. Matching/cutting comes later
once we see the output quality.

Usage:
    uv run _dev_scripts/transcribe_pa.py audio_src/sobu/1217F/src_from12.mp3

Notes:
- First run downloads the model (~1.5 GB for medium). Cached after that.
- CPU is fine for PoC; ~1–3 minutes for a 27-min source on a typical laptop.
- int8 quantization keeps RAM usage modest with negligible accuracy loss.
"""

from __future__ import annotations

import argparse
import json
import os
import site
import sys
from pathlib import Path

# Force UTF-8 stdout — Japanese transcript can't be printed via cp1252 (Windows default).
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# Make CTranslate2 (faster-whisper's backend) find the bundled CUDA libs that
# uv installed via nvidia-cublas-cu12 / nvidia-cudnn-cu12. Without this, CUDA
# init fails with "cublas64_12.dll not found". Use the package's file location
# directly — site.getsitepackages() doesn't return the venv path under `uv run`.
import nvidia.cublas  # noqa: E402
import nvidia.cudnn  # noqa: E402

# nvidia.* are namespace packages — use __path__ (not __file__, which is None).
# Prepend to PATH so CTranslate2's deeper DLL loads find them (add_dll_directory
# alone wasn't sufficient — its scope didn't reach into the C extension load).
for mod in (nvidia.cublas, nvidia.cudnn):
    for pkg_root in list(mod.__path__):
        dll_dir = Path(pkg_root) / "bin"
        if dll_dir.exists():
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ["PATH"]
            os.add_dll_directory(str(dll_dir))  # type: ignore[attr-defined]

from faster_whisper import WhisperModel  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path, help="source PA mp3")
    ap.add_argument(
        "--model", default="large-v3", help="whisper model size: tiny|base|small|medium|large-v3 (default: large-v3 on GPU, medium on CPU)"
    )
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="device (default: cuda)")
    ap.add_argument("--out", type=Path, help="optional JSON output path (defaults next to script)")
    args = ap.parse_args()

    if not args.src.exists():
        print(f"ERROR: not found: {args.src}", file=sys.stderr)
        return 1

    compute_type = "float16" if args.device == "cuda" else "int8"
    print(f"Loading {args.model} on {args.device} ({compute_type})...")
    model = WhisperModel(args.model, device=args.device, compute_type=compute_type)

    print(f"Transcribing {args.src}...")
    # Generic JR-East-PA prime — biases model toward train announcement vocabulary
    # (次は…, お乗り換え, 各駅停車, etc.) without naming any specific stations or
    # lines. Route-agnostic on purpose — the same script must work for any source.
    initial_prompt = "これはJR東日本の電車内アナウンスです。次の駅、お乗り換え、お降り、各駅停車などの案内が含まれます。"
    segments, info = model.transcribe(
        str(args.src),
        word_timestamps=True,
        vad_filter=True,
        initial_prompt=initial_prompt,
        beam_size=5,  # default; bigger = slower for marginal gain
        no_speech_threshold=0.6,  # slightly stricter than default 0.6 to suppress hallucinations on quiet patches
        condition_on_previous_text=False,  # don't let earlier mistakes (homophones) bias later segments
    )

    out_data = {
        "src": str(args.src),
        "model": args.model,
        "language": info.language,
        "duration": info.duration,
        "segments": [],
    }

    for seg in segments:
        seg_data = {
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            # Word-level times are alignment-anchored and do NOT drift, unlike
            # seg.start. Cluster boundaries must be taken from here (or from an
            # audio_id.structure block onset) — see pa-make skill 0.3.0.b.
            "words": [{"s": round(w.start, 2), "e": round(w.end, 2), "w": w.word} for w in (seg.words or ())],
        }
        out_data["segments"].append(seg_data)
        print(f"[{seg.start:7.2f}s -> {seg.end:7.2f}s] {seg.text.strip()}")

    # Default output: next to the source mp3. Per-route workflow keeps every
    # artifact for one diagram in audio_src/<line>/<diagram>/.
    out_path = args.out or args.src.parent / f"{args.src.stem}_transcript.json"
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(out_data['segments'])} segments. JSON saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

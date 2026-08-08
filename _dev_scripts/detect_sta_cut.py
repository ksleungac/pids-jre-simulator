"""Detect the music→voice transition (sta_cut) in an STA mp3.

Approach: each file trains its own classifier. The first ~3 s after the leading
silence is the music exemplar; the last ~3 s is the voice exemplar (closing-door
announcement). Per-frame MFCCs are classified by distance to each exemplar's
mean. The unique flip point is the cut.

Run against the whole sobu/1217F/sta folder for validation:

    uv run _dev_scripts/detect_sta_cut.py audio/sobu/sta --truth audio/sobu/1217F/route.json

Or single file:

    uv run _dev_scripts/detect_sta_cut.py audio/sobu/sta/tsuga_2_gota-del-vient.mp3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

import librosa
import numpy as np

FRAME_MS = 100  # classification frame size
EXEMPLAR_S = 3.0  # length of music/voice training segments
SKIP_LEAD_S = 0.3  # skip leading silence pad
SMOOTH_FRAMES = 5  # majority-vote window (~0.5 s)


class DetectionResult(NamedTuple):
    music_end: float  # seconds — change-point boundary, last music frame
    voice_start: float  # seconds — first non-silence frame after music_end (= sta_cut)
    confidence: float  # [0, 1] — partition sharpness


def detect(path: Path) -> DetectionResult:
    """Detect music_end + voice_start in an STA file.

    sta_cut should be set to voice_start. The gap [music_end, voice_start] is
    the silence between the hard music-cut and the start of the closing-door
    announcement — any sta_cut value inside this window is functionally valid.
    """
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    duration = len(y) / sr

    # frame-level features. Drop MFCC[0] (log-energy) so silence isn't mis-clustered
    # with voice on energy alone; add timbral features that distinguish music from
    # speech regardless of loudness.
    hop = int(sr * FRAME_MS / 1000)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)[1:]  # drop coeff 0
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=hop)
    zcr = librosa.feature.zero_crossing_rate(y=y, hop_length=hop)
    feats = np.vstack([mfcc, centroid, contrast, zcr]).T  # (frames, F)
    # z-score so each feature contributes equally to Euclidean distance
    feats = (feats - feats.mean(axis=0)) / (feats.std(axis=0) + 1e-8)
    n_frames = feats.shape[0]
    frame_t = np.arange(n_frames) * FRAME_MS / 1000

    # exemplars: first EXEMPLAR_S after SKIP_LEAD_S = music; last EXEMPLAR_S = voice
    music_mask = (frame_t >= SKIP_LEAD_S) & (frame_t < SKIP_LEAD_S + EXEMPLAR_S)
    voice_mask = frame_t >= duration - EXEMPLAR_S
    music_mean = feats[music_mask].mean(axis=0)
    voice_mean = feats[voice_mask].mean(axis=0)

    # per-frame distance to each exemplar
    d_music = np.linalg.norm(feats - music_mean, axis=1)
    d_voice = np.linalg.norm(feats - voice_mean, axis=1)

    # change-point detection: find the single split t* that best partitions the
    # file into [music | voice]. r[i] = d_voice[i] - d_music[i] is positive for
    # music-like frames, negative for voice-like. The cumulative sum peaks at the
    # boundary — argmax of cumsum(r) is the optimal split point. Robust to brief
    # syllable pauses inside voice (which briefly look music-like) because it
    # considers the global partition cost, not local flip points.
    r = d_voice - d_music
    cumulative_r = np.cumsum(r)
    cut_frame = int(np.argmax(cumulative_r)) + 1

    # The change-point above finds where MFCC features transition from music-like
    # to voice-like — but in audio with audible music decay (reverb tail), the
    # spectral transition can lead the perceptual transition by a noticeable
    # margin. Anchor music_end / voice_start to the actual SILENCE GAP in the
    # waveform instead: search forward from cut_frame for the first contiguous
    # silence run of ≥ MIN_GAP_FRAMES; that gap's edges are the perceptual
    # music_end and voice_start.
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_db = 20 * np.log10(rms + 1e-10)
    MIN_GAP_FRAMES = 5  # 500 ms minimum to qualify as a real music→voice gap
    SEARCH_WINDOW_FRAMES = 12  # 1.2 s after cut_frame — beyond this is mid-voice
    music_end_frame = cut_frame
    voice_start_frame = cut_frame

    # Find the first silence frame within the search window after cut_frame
    silence_start = None
    for i in range(cut_frame, min(n_frames, cut_frame + SEARCH_WINDOW_FRAMES)):
        if rms_db[i] <= -40:
            silence_start = i
            break

    # If we found one, walk it to the end and qualify by length + must have content after
    if silence_start is not None:
        j = silence_start
        while j < n_frames and rms_db[j] <= -40:
            j += 1
        if j - silence_start >= MIN_GAP_FRAMES and j < n_frames:
            music_end_frame = silence_start
            voice_start_frame = j

    music_end_time = frame_t[music_end_frame] if music_end_frame < n_frames else duration
    voice_start_time = frame_t[voice_start_frame] if voice_start_frame < n_frames else duration

    # confidence = peak height relative to total signal range, in [0, 1]
    peak = cumulative_r[cut_frame - 1] if cut_frame > 0 else 0
    total_range = cumulative_r.max() - cumulative_r.min()
    confidence = float(peak / total_range) if total_range > 0 else 0.0

    return DetectionResult(
        music_end=float(music_end_time),
        voice_start=float(voice_start_time),
        confidence=confidence,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", type=Path, help="STA mp3 file or folder")
    ap.add_argument("--truth", type=Path, help="route.json for ground-truth comparison")
    args = ap.parse_args()

    files = sorted(args.target.glob("*.mp3")) if args.target.is_dir() else [args.target]

    truth: dict[str, float] = {}
    if args.truth:
        route = json.loads(args.truth.read_text(encoding="utf-8"))
        for stop in route["stops"]:
            for sta_name in stop.get("sta", []):
                if stop.get("sta_cut") is not None:
                    truth[sta_name] = stop["sta_cut"]

    # status convention: truth value vs the [music_end, voice_start] gap window.
    # Strict on both sides — neither error mode is acceptable UX:
    # - EARLY (sta_cut < music_end) → simulator briefly replays music tail before
    #   voice. Jarring (music returns when user expected to skip to voice).
    # - LATE  (sta_cut > voice_start) → simulator clips first syllable of voice.
    #   Always wrong.
    # 1-decimal sta_cut precision makes any tolerance unnecessary; if someone is
    # using integer-second sta_cut and rounds outside the gap, that's the signal
    # to bump to 1-decimal.
    print(f"{'file':50s}  {'truth':>5s}  {'music_end':>10s}  {'voice_start':>11s}  {'conf':>5s}  status")
    print("-" * 100)
    flagged = 0
    in_gap = 0
    for f in files:
        result = detect(f)
        gt = truth.get(f.stem)
        gt_str = f"{gt:>5.1f}s" if gt is not None else "   n/a"

        if gt is None:
            status = "(no truth)"
        elif gt < result.music_end:
            status = f"EARLY by {result.music_end - gt:.1f}s (in music - ILLEGAL, plays music tail before voice)"
            flagged += 1
        elif gt > result.voice_start:
            status = f"LATE by {gt - result.voice_start:.1f}s (in voice - ILLEGAL, clips first syllable)"
            flagged += 1
        else:
            status = "in gap"
            in_gap += 1

        print(f"{f.name:50s}  {gt_str:>5s}  {result.music_end:>9.2f}s  {result.voice_start:>10.2f}s  {result.confidence:>5.2f}  {status}")

    if files:
        print("-" * 100)
        print(f"in gap: {in_gap}/{len(files)}    flagged for re-listen: {flagged}/{len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

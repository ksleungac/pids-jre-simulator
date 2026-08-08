# SPDX-License-Identifier: MIT
"""Replay a screen-recording through the PRODUCTION OCR read path.

The point is degraded input. Every local corpus is captured from a live framebuffer and
is therefore CLEANER than what a reporter's machine produces — `critical_lessons.md §7`
is exactly this trap, and it has now caught us twice. A user's H.264 screen recording is
the closest thing we have to their real pixels: compression artifacts, their scaling,
their scenery, their post-processing.

Like `ocr_observe.py`, this OWNS NO READ LOGIC — frames go through `sampling.read_hud`,
the same function `AutoDriver` calls, with the same guards. Only the frame SOURCE differs
(decoded video instead of dxcam).

Requires `av` (PyAV) — present in the dev venv, NOT a production dependency. This script
lives in `_dev_scripts/` and never ships.

Usage:
  uv run python _dev_scripts/ocr_replay_video.py <video.mp4> [--every N] [--dump-suspect DIR]

  --every N          decode every Nth frame (default 6 ~= 10 Hz on 60 fps footage)
  --dump-suspect DIR write the HUD crop of any frame whose read looks implausible
  --csv PATH         write per-frame reads for offline analysis
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import av
import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_input.driver import (  # noqa: E402
    _accept_stopping_offset,
    _apply_badge_reject_gate,
    _crop_cell,
    guard_distance,
)
from auto_input.hud_layout import PROFILES  # noqa: E402
from auto_input.ocr import DEFAULT_TEMPLATES_DIR, build_templates, load_badge_anchors, seg_for_scale  # noqa: E402
from auto_input.sampling import GuardState, read_hud  # noqa: E402

MAX_PLAUSIBLE_ACCEL_KMH_S = 6.0  # commuter EMU: ~3 accel, ~4.5 emergency brake
# The HUD speed is an INTEGER, so at short dt quantization dominates the physical bound:
# at 60 fps sampled every 6 frames, dt=0.1s and a perfectly legal 1 km/h tick computes as
# 10 km/h/s. Without this slack the check flags every normal acceleration frame — it did,
# 48 times, on the first run of this harness. The bound is physics * dt PLUS one quantum.
SPEED_QUANTIZATION_SLACK_KMH = 2.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--dump-suspect", type=Path)
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args()

    pygame.init()
    container = av.open(str(args.video))
    vs = container.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    fps = float(vs.average_rate)
    profile = PROFILES.get((w, h))
    if profile is None:
        sys.exit(f"video is {w}x{h} — no ResolutionProfile. Supported: {sorted(PROFILES)}")

    templates = build_templates()
    seg = seg_for_scale(profile.scale)
    badges_dir = DEFAULT_TEMPLATES_DIR / profile.badges_subdir if profile.badges_subdir else None
    anchors = load_badge_anchors(badges_dir)
    try:
        from auto_input.ocr import _get_red_digit_templates

        red_templates = _get_red_digit_templates()
    except Exception:
        red_templates = None

    # The recording is the FULL desktop, so the HUD sits at its screen-relative origin.
    # read_hud indexes by profile.hud_bbox_in_capture, so swap that to the screen bbox —
    # same trick test_ocr_reads uses for its quadrant fixtures.
    from dataclasses import replace

    prof = replace(profile, hud_bbox_in_capture=profile.hud_bbox)

    guard = GuardState()
    prev_badge = None
    rows = []
    n = 0
    if args.dump_suspect:
        args.dump_suspect.mkdir(parents=True, exist_ok=True)

    for i, frame in enumerate(container.decode(video=0)):
        if i % args.every:
            continue
        rgb = frame.to_ndarray(format="rgb24")
        bgra = np.dstack([rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0], np.full(rgb.shape[:2], 255, np.uint8)])
        ts = i / fps
        r = read_hud(
            bgra,
            prof,
            templates,
            red_templates,
            anchors,
            seg,
            prev_badge=prev_badge,
            guard=guard,
            ts=ts,
            crop=_crop_cell,
            accept_stopping_offset=_accept_stopping_offset,
            apply_badge_reject_gate=_apply_badge_reject_gate,
            guard_distance=guard_distance,
        )
        prev_badge = r.badge if r.badge is not None else prev_badge
        rows.append((ts, r))
        n += 1

    # Plausibility pass: speed must obey physics between consecutive decoded frames.
    suspects = []
    prev = None
    for ts, r in rows:
        if r.speed is not None and prev is not None:
            dt = ts - prev[0]
            if dt > 0 and abs(r.speed - prev[1]) > MAX_PLAUSIBLE_ACCEL_KMH_S * dt + SPEED_QUANTIZATION_SLACK_KMH:
                suspects.append((ts, prev[1], r.speed, r.speed_score, r))
        if r.speed is not None:
            prev = (ts, r.speed)

    sp = [r.speed for _, r in rows if r.speed is not None]
    print(f"video      : {args.video.name}  {w}x{h} @ {fps:.2f}fps")
    print(f"decoded    : {n} frames (every {args.every})")
    print(f"speed reads: {len(sp)}/{n}   range {min(sp) if sp else '-'}-{max(sp) if sp else '-'}")
    print(f"badge      : {sum(1 for _, r in rows if r.badge is None)} unreadable / {n}")
    print(f"guards     : score_gate={sum(1 for _, r in rows if r.gated_fields)}  dist_reject={sum(1 for _, r in rows if r.distance_rejected)}")
    print(f"\nIMPLAUSIBLE speed steps (>{MAX_PLAUSIBLE_ACCEL_KMH_S} km/h/s): {len(suspects)}")
    for ts, a, b, sc, r in suspects[:25]:
        print(f"   t={ts:6.2f}s  {a:>3} -> {b:<3}  score={sc:.2f} badge={r.badge} raw={r.raw_speed}")

    if args.dump_suspect:
        hx, hy, hw, hh = profile.hud_bbox
        for i, frame in enumerate(av.open(str(args.video)).decode(video=0)):
            ts = i / fps
            if not any(abs(ts - s[0]) < 1e-9 for s in suspects):
                continue
            rgb = frame.to_ndarray(format="rgb24")[hy : hy + hh, hx : hx + hw]
            surf = pygame.image.frombuffer(np.ascontiguousarray(rgb).tobytes(), (hw, hh), "RGB")
            pygame.image.save(surf, str(args.dump_suspect / f"suspect_t{ts:07.3f}.png"))
        print(f"\ndumped {len(suspects)} suspect HUD crops -> {args.dump_suspect}")

    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(
                [
                    "ts",
                    "badge",
                    "speed",
                    "speed_decimal",
                    "speed_score",
                    "distance",
                    "distance_score",
                    "speed_limit",
                    "raw_speed",
                    "gated",
                    "dist_rejected",
                ]
            )
            for ts, r in rows:
                wr.writerow(
                    [
                        f"{ts:.3f}",
                        r.badge,
                        r.speed,
                        r.speed_decimal,
                        f"{r.speed_score:.3f}",
                        r.distance,
                        f"{r.distance_score:.3f}",
                        r.speed_limit,
                        r.raw_speed,
                        "|".join(r.gated_fields),
                        r.distance_rejected,
                    ]
                )
        print(f"csv -> {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

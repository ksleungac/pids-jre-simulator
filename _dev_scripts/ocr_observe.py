# SPDX-License-Identifier: MIT
"""OCR corpus collector — runs the PRODUCTION read path and records what it saw.

Replaces capture_game.py for OCR diagnosis. The entire point is that this script
OWNS NO READ LOGIC: it grabs a frame exactly as AutoDriver does and hands it to
`auto_input.sampling.read_hud`, the same function production calls, with the same
guards passed in. There is deliberately no local crop, no local reader, no local
threshold, and no forked detector — a diagnostic that reimplements any part of the
pipeline produces evidence about ITSELF, not about production, which is worthless
exactly when it matters (diagnosing a production misread).

What it adds over production is INFORMATION, never behaviour:
  - the full HUD region dumped per sample, so cells can be RE-CROPPED offline at
    different bboxes (the only way to test a crop-geometry hypothesis; a cell-only
    dump bakes the suspect geometry into the evidence)
  - reads.jsonl carrying RAW (pre-guard) beside GUARDED (what production decides on)
  - a console line showing the DECIMAL speed and marking every guard that fired

No synthetic keystrokes, no PA firing, no simulator coupling — it only watches.

Run:  uv run python _dev_scripts/ocr_observe.py --interval 0.5
Flags:
  --interval N   seconds between samples, fractions ok (default 1.0)
  --res 1080p|1200p|1440p|2160p   override resolution (default: auto-detect from first frame)
  --no-dump      console only, write no PNGs (quick sanity check)
  --out DIR      output dir (default _experiments/live_captures/<res>/<timestamp>/)
Stop: Ctrl+C
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

# Production read path + its guards. NOTHING here is reimplemented.
from auto_input.driver import (  # noqa: E402
    _accept_stopping_offset,
    _apply_badge_reject_gate,
    _crop_cell,
    _open_capture_camera,
    guard_distance,
)
from auto_input.hud_layout import DOWNSCALE_PROFILE, PROFILES, profile_for  # noqa: E402
from auto_input.ocr import DEFAULT_TEMPLATES_DIR, build_templates, load_badge_anchors, seg_for_scale  # noqa: E402
from auto_input.sampling import GuardState, downscale_hud, read_hud  # noqa: E402
from window_utils import declare_dpi_awareness  # noqa: E402

# DPI awareness decides what the resolution probe SEES — a DPI-unaware process reads a
# 1920x1200 desktop at 125% scaling as 1536x960, whose fitted viewport is 864 and therefore
# out of scope. A local copy of the declaration could drift from production's and silently
# select a different profile in a script whose whole contract is observing what production
# observes, so call production's (`principles.md` § "A second implementation of a production
# decision drifts silently"; dev importing production is the allowed direction).
declare_dpi_awareness()

# Derived from PROFILES, never re-typed: the --res choices ARE the driven resolutions, so a
# hand-kept copy would go stale the next time one is promoted (`conventions.md` § Tooling,
# canonical-source duplication).
_RES_FLAG_MAP = {f"{h}p": (w, h) for (w, h) in PROFILES}
DEFAULT_OUT = Path(__file__).parent.parent / "_experiments" / "live_captures"


def resolve_profile(camera, forced: str | None):
    """Same startup contract as AutoDriver: probe a full frame, resolve a profile, fail loud.

    `profile_for` returns a driven profile when one exists and derives any other desktop that
    is 16:9 or taller, whose width is a multiple of 16, and whose fitted 16:9 viewport is
    >= 1080p. None means outside that scope — all three conditions, not just the last.
    """
    if forced:
        prof = profile_for(*_RES_FLAG_MAP[forced])
        if prof is None:
            sys.exit(f"no profile for {forced}")
        return prof
    for _ in range(10):
        probe = camera.grab()
        if probe is not None:
            h, w = probe.shape[:2]
            prof = profile_for(w, h)
            if prof is None:
                sys.exit(
                    f"desktop is {w}x{h} — outside the supported scope. Needs: 16:9 or taller (never wider), "
                    f"width a multiple of 16, fitted 16:9 viewport 1080p or larger. Observed: {sorted(PROFILES)}"
                )
            if not prof.verified:
                print(
                    f"[note] {w}x{h} has not been driven — geometry derived from the 16:9 fractions "
                    f"(letterbox bar {prof.capture_region[1]}px, capture {prof.capture_region}, HUD {prof.hud_bbox})."
                )
            return prof
        time.sleep(0.2)
    sys.exit("dxcam returned no frame on the resolution probe — is the game rendering on the primary monitor?")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between samples, fractions ok (default 1.0)")
    ap.add_argument("--res", choices=sorted(_RES_FLAG_MAP), help="override resolution (default: auto-detect)")
    ap.add_argument("--no-dump", action="store_true", help="console only, write no PNGs")
    ap.add_argument("--out", type=Path, help="output dir (default _experiments/live_captures/<res>/<timestamp>/)")
    args = ap.parse_args()

    pygame.init()
    # Production's adapter/output walk, not a bare dxcam.create() — on a hybrid-GPU laptop
    # index 0 raises DXGI_ERROR_UNSUPPORTED (`critical_lessons.md` §8), so the bare call fails
    # on exactly the machines whose OCR reports most need collecting.
    camera = _open_capture_camera("BGRA")
    if camera is None:
        sys.exit("no DXGI capture combo succeeded — see the traceback above (critical_lessons §8).")
    profile = resolve_profile(camera, args.res)

    # `profile` is what to CAPTURE; DOWNSCALE_PROFILE is what READS it — production
    # downscales the HUD into the 1080p model, so this must too or the corpus describes a
    # pipeline nobody runs.
    templates = build_templates()
    seg = seg_for_scale(DOWNSCALE_PROFILE.scale)
    badges_dir = DEFAULT_TEMPLATES_DIR / "badges"
    badge_anchors = load_badge_anchors(badges_dir)
    red_dir = DEFAULT_TEMPLATES_DIR / "digits_red"
    red_templates = build_templates(red_dir) if red_dir.exists() else None

    # Split by capture resolution — cell geometry is resolution-specific and nothing IN the
    # PNGs says which. `<height>p` to match the other dirs that index CAPTURES
    # (_tests/fixtures/ocr/1440p/, the --res choices above). Templates are not among
    # them — there is one set, cut at the model's scale.
    out_dir = args.out or (DEFAULT_OUT / f"{profile.desktop_h}p" / time.strftime("%Y%m%d-%H%M%S"))
    if not args.no_dump:
        out_dir.mkdir(parents=True, exist_ok=True)
    reads_path = out_dir / "reads.jsonl"

    rx0, ry0, rx1, ry1 = profile.capture_region
    exp_w, exp_h = rx1 - rx0, ry1 - ry0
    guard = GuardState()
    prev_badge: str | None = None

    print(f"\nprofile      : {profile.desktop_w}x{profile.desktop_h} (scale={profile.scale})")
    print(f"capture      : region={profile.capture_region} -> {exp_w}x{exp_h}")
    print(f"interval     : {args.interval}s")
    print(f"output       : {'(console only)' if args.no_dump else out_dir}")
    print("read path    : auto_input.sampling.read_hud (production)")
    print("Ctrl+C to stop.\n")

    n = 0
    while True:
        try:
            frame = None
            for _ in range(5):
                frame = camera.grab(region=profile.capture_region)
                if frame is not None:
                    break
                time.sleep(0.2)
            if frame is None:
                print("[wait] dxcam returned None on all retries.")
                time.sleep(args.interval)
                continue
            h, w = frame.shape[:2]
            if (w, h) != (exp_w, exp_h):
                print(f"[warn] region {w}x{h}, expected {exp_w}x{exp_h} — skipping")
                time.sleep(args.interval)
                continue

            # Downscale into the model before reading, exactly as production does. `frame`
            # stays the native capture so the dump below keeps full-resolution pixels.
            ts = time.time()
            r = read_hud(
                downscale_hud(frame, profile),
                DOWNSCALE_PROFILE,
                templates,
                red_templates,
                badge_anchors,
                seg,
                prev_badge=prev_badge,
                guard=guard,
                ts=ts,
                crop=_crop_cell,
                accept_stopping_offset=_accept_stopping_offset,
                apply_badge_reject_gate=_apply_badge_reject_gate,
                guard_distance=guard_distance,
            )

            # DECIMAL speed: the truncation class this corpus exists to diagnose
            # (46.2 read as "4") is invisible in an integer readout — the tenths is
            # the digit that goes missing.
            spd = f"{r.speed_decimal:>6.1f}km/h" if r.speed_decimal is not None else "    --   "
            badge = f"{r.badge:<7}" if r.badge else "   ?   "
            if r.stopping_offset_cm is not None:
                dist = f"off={r.stopping_offset_cm:+5d}cm({r.stopping_offset_score:.2f})"
            elif r.distance is not None:
                dist = f"dst={r.distance:>5}m({r.distance_score:.2f})"
            else:
                dist = "dst=   ---    "
            lim = f" lim={r.speed_limit:>3}({r.speed_limit_score:.2f})" if r.speed_limit is not None else ""

            # Mark whatever a guard CHANGED — a bare guarded value can't distinguish a
            # clean read from a rejected-and-held one.
            marks = []
            if r.raw_speed != r.speed:
                marks.append(f"spd {r.raw_speed}->{r.speed}")
            if r.raw_distance != r.distance:
                marks.append(f"dst {r.raw_distance}->{r.distance}")
            if r.raw_speed_limit != r.speed_limit:
                marks.append(f"lim {r.raw_speed_limit}->{r.speed_limit}")
            if r.gated_fields:
                marks.append("SCORE_GATE:" + ",".join(r.gated_fields))
            if r.distance_rejected:
                marks.append("DIST_REJECT")
            mark = ("  [" + " | ".join(marks) + "]") if marks else ""

            print(f"[{time.strftime('%H:%M:%S')}] {badge}({r.badge_diff:5.1f}) spd={spd}({r.speed_score:.2f}) {dist}{lim}{mark}")

            if not args.no_dump:
                stem = f"{time.strftime('%Y%m%d_%H%M%S')}_{int((ts % 1) * 1000):03d}"
                sd = f"{r.speed_decimal:.1f}" if r.speed_decimal is not None else "FAIL"
                dd = str(r.distance) if r.distance is not None else "FAIL"
                name = f"hud_{stem}_s{sd}-{r.speed_score:.2f}_d{dd}-{r.distance_score:.2f}_{r.badge or 'FAIL'}"
                # WHOLE HUD region, not individual cells — lets an offline sweep re-crop at
                # different bboxes to test crop geometry.
                hx, hy, hw, hh = profile.hud_bbox_in_capture
                surf = pygame.image.frombuffer(frame.tobytes(), (w, h), "BGRA")
                hud = pygame.Surface((hw, hh))
                hud.blit(surf, (0, 0), area=pygame.Rect(hx, hy, hw, hh))
                pygame.image.save(hud, str(out_dir / f"{name}.png"))
                with reads_path.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "stem": name,
                                "ts": ts,
                                "badge": r.badge,
                                "badge_diff": r.badge_diff,
                                "speed": r.speed,
                                "speed_decimal": r.speed_decimal,
                                "speed_tenths": r.speed_tenths,
                                "speed_raw": r.speed_raw,
                                "speed_score": r.speed_score,
                                "distance": r.distance,
                                "distance_score": r.distance_score,
                                "stopping_offset_cm": r.stopping_offset_cm,
                                "stopping_offset_score": r.stopping_offset_score,
                                "speed_limit": r.speed_limit,
                                "speed_limit_score": r.speed_limit_score,
                                "raw_speed": r.raw_speed,
                                "raw_distance": r.raw_distance,
                                "raw_stopping_offset_cm": r.raw_stopping_offset_cm,
                                "raw_speed_limit": r.raw_speed_limit,
                                "gated_fields": list(r.gated_fields),
                                "distance_rejected": r.distance_rejected,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

            prev_badge = r.badge if r.badge is not None else prev_badge
            n += 1
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\nStopped. {n} samples -> {out_dir if not args.no_dump else '(no dump)'}")
            return 0


if __name__ == "__main__":
    sys.exit(main())

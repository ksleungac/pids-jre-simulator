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

REPLAY — the non-degradation gate for any change to the read path:

  uv run python _dev_scripts/ocr_observe.py --replay [DIR] [--every N]

Re-reads every dumped HUD under `_experiments/live_captures/` and diffs against the
`reads.jsonl` written beside it. No game and no dxcam: thousands of REAL frames across four
resolutions, each carrying production's own read of it, which is the honest oracle the 23
committed fixtures cannot be (six of those are byte-identical to the anchors they match,
`critical_lessons.md` §10). It is a REGRESSION baseline, not a correctness one — a change
that fixes a misread also shows up as a difference, so read the per-field breakdown and open
the frames. `--every N` subsamples, and note that anything above 1 invalidates the DISTANCE
column: that guard is cross-sample, so a sparse subsequence exercises a pipeline production
never runs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
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


def replay(root: Path, every: int) -> int:
    """Re-read every dumped HUD in `root` and diff against what was recorded at capture time.

    The corpus is the honest non-degradation gate this project otherwise lacks. The committed
    fixtures are 23 cells, six of them byte-identical to the anchors they match
    (`critical_lessons.md` §10); this is thousands of REAL frames across four resolutions,
    each carrying production's own read of it in `reads.jsonl`.

    What it is: a REGRESSION baseline. `reads.jsonl` records what the code did that day, not
    what the HUD said, so a difference is a change in behaviour and not automatically a
    defect — a change that fixes a misread shows up here as a difference too. Read the
    per-field breakdown and go look at the frames; do not treat "0 changed" as correctness
    or "n changed" as failure.

    Guard state is rebuilt per session directory in timestamp order, with the recorded `ts`,
    because the distance guard and `prev_badge` are both cross-sample. Replaying frames in
    isolation would exercise a pipeline production never runs.
    """
    from dataclasses import replace as dc_replace

    sessions = sorted(p.parent for p in root.rglob("reads.jsonl"))
    if not sessions:
        sys.exit(f"no reads.jsonl under {root}")

    templates = build_templates()
    seg = seg_for_scale(DOWNSCALE_PROFILE.scale)
    badge_anchors = load_badge_anchors(DEFAULT_TEMPLATES_DIR / "badges")
    red_dir = DEFAULT_TEMPLATES_DIR / "digits_red"
    red_templates = build_templates(red_dir) if red_dir.exists() else None

    FIELDS = ("badge", "speed", "speed_tenths", "distance", "stopping_offset_cm", "speed_limit")
    totals: dict[str, dict[str, int]] = {}
    examples: dict[str, list[str]] = {}

    for sess in sessions:
        res = sess.parent.name
        recs = [json.loads(ln) for ln in (sess / "reads.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        recs.sort(key=lambda r: r["ts"])
        recs = recs[::every]
        bucket = totals.setdefault(res, {"n": 0, "changed": 0, **{f: 0 for f in FIELDS}})
        guard = GuardState()
        prev_badge: str | None = None
        for rec in recs:
            png = sess / f"{rec['stem']}.png"
            if not png.exists():
                continue
            surf = pygame.image.load(str(png))
            w, h = surf.get_width(), surf.get_height()
            arr = pygame.surfarray.array3d(surf).transpose(1, 0, 2)
            bgra = np.dstack([arr[:, :, 2], arr[:, :, 1], arr[:, :, 0], np.full((h, w), 255, np.uint8)])
            # The dump IS the HUD region already, so the profile's HUD origin is (0,0) here.
            # Its SIZE still has to be the native one or downscale_hud lands on a wrong grid.
            prof = dc_replace(PROFILES[(1920, 1080)], hud_bbox_in_capture=(0, 0, w, h))
            r = read_hud(
                downscale_hud(bgra, prof),
                DOWNSCALE_PROFILE,
                templates,
                red_templates,
                badge_anchors,
                seg,
                prev_badge=prev_badge,
                guard=guard,
                ts=rec["ts"],
                crop=_crop_cell,
                accept_stopping_offset=_accept_stopping_offset,
                apply_badge_reject_gate=_apply_badge_reject_gate,
                guard_distance=guard_distance,
            )
            prev_badge = r.badge if r.badge is not None else prev_badge
            bucket["n"] += 1
            diffs = [f for f in FIELDS if getattr(r, f) != rec.get(f)]
            if diffs:
                bucket["changed"] += 1
                for f in diffs:
                    bucket[f] += 1
                key = f"{res}:{diffs[0]}"
                if len(examples.setdefault(key, [])) < 3:
                    examples[key].append(f"{rec['stem'][:44]} {diffs[0]}: {rec.get(diffs[0])!r} -> {getattr(r, diffs[0])!r}")

    print(f"\n=== replay of {root} ({len(sessions)} sessions, every {every}) ===")
    print(f"{'res':<8}{'frames':>8}{'changed':>9}   per-field")
    grand_n = grand_c = 0
    for res in sorted(totals):
        b = totals[res]
        grand_n += b["n"]
        grand_c += b["changed"]
        per = "  ".join(f"{f}={b[f]}" for f in FIELDS if b[f]) or "-"
        print(f"{res:<8}{b['n']:>8}{b['changed']:>9}   {per}")
    print(f"{'ALL':<8}{grand_n:>8}{grand_c:>9}")
    for key in sorted(examples):
        print(f"\n  {key}")
        for line in examples[key]:
            print(f"    {line}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between samples, fractions ok (default 1.0)")
    ap.add_argument("--res", choices=sorted(_RES_FLAG_MAP), help="override resolution (default: auto-detect)")
    ap.add_argument("--no-dump", action="store_true", help="console only, write no PNGs")
    ap.add_argument("--out", type=Path, help="output dir (default _experiments/live_captures/<res>/<timestamp>/)")
    ap.add_argument(
        "--replay",
        nargs="?",
        const=DEFAULT_OUT,
        type=Path,
        help="re-read a dumped corpus instead of capturing, and diff against its reads.jsonl "
        "(default _experiments/live_captures/). No game, no dxcam.",
    )
    ap.add_argument("--every", type=int, default=1, help="with --replay, take every Nth frame")
    args = ap.parse_args()

    pygame.init()
    if args.replay:
        return replay(args.replay, max(1, args.every))
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

            # badge_level on the console because it is the number that identifies a shifted
            # display at a glance — the thing #137 took weeks to establish from diff medians.
            lvl = f" lvl{r.badge_level:+5.0f}" if abs(r.badge_level) >= 5 else "         "
            via = "" if r.badge_via in ("raw", None) else f" via={r.badge_via}"
            print(f"[{time.strftime('%H:%M:%S')}] {badge}({r.badge_diff:5.1f}){lvl}{via} " f"spd={spd}({r.speed_score:.2f}) {dist}{lim}{mark}")

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
                                "badge_via": r.badge_via,
                                "badge_level": r.badge_level,
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

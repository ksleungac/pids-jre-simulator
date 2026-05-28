"""Offline validation of the OCR pipeline against calibration screenshots.

Tests badge classification + speed-limit reading + stopping-offset reading
using the production ResolutionProfile geometry, scaled segmentation thresholds,
and native-resolution templates. No live game capture required.

Usage:
    uv run python _dev_scripts/validate_ocr.py           # default: 1080p
    uv run python _dev_scripts/validate_ocr.py --res 1080p
    uv run python _dev_scripts/validate_ocr.py --res 1440p

All tests that have source files should PASS. Any FAIL needs investigation
before deploying to a live session at that resolution.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_input.hud_layout import PROFILES, ResolutionProfile  # noqa: E402
from auto_input.ocr import (  # noqa: E402
    DEFAULT_TEMPLATES_DIR,
    build_templates,
    classify_badge_state,
    load_badge_anchors,
    read_speed_limit,
    read_stopping_offset,
    seg_for_scale,
)

PROJECT_ROOT = Path(__file__).parent.parent

# ── Per-resolution calibration data ───────────────────────────────────────────

# (badge, speed_limit_kmh, stopping_offset_cm)
# stem -> expected value; None = file not available for that resolution
CAL_DATA: dict[str, dict] = {
    "1080p": {
        "cal_dir": "_ocr_calibration_1080p",
        "badges": {
            "running_en": "MOVING",
            "running_ja": "MOVING",
            "stopping_en": "STOPPED",
            "stopping_ja": "STOPPED",
            "passing_en": "PASSING",
            "passing_ja": "PASSING",
        },
        "limits": {
            "limit_30": 30,
            "limit_35": 35,
            "limit_40": 40,
            "limit_45": 45,
            "limit_50": 50,
            "limit_55": 55,
            "limit_65": 65,
            "limit_70": 70,
            "limit_75": 75,
            "limit_80": 80,
            "limit_85": 85,
            "limit_90": 90,
            "limit_95": 95,
            "limit_100": 100,
            "limit_105": 105,
            "limit_110": 110,
            "limit_110_2": 110,
            "limit_115": 115,
            "limit_120": 120,
        },
        "offsets": {
            "stopping_-11cm": -11,
        },
    },
    "1440p": {
        "cal_dir": "_ocr_calibration",
        "badges": {
            "running_en": "MOVING",
            "running_ja": "MOVING",
            "stopping_en": "STOPPED",
            "stopping_next_station": "STOPPED",
            "passing_en": "PASSING",
            "passing_jp": "PASSING",
        },
        "limits": {
            "limit_30": 30,
            "limit_35": 35,
            "limit_45": 45,
            "limit_55": 55,
            "limit_65": 65,
            "limit_75": 75,
            "limit_80": 80,
            "limit_85": 85,
            "limit_90": 90,
            "limit_100": 100,
            "limit_110": 110,
            "limit_120": 120,
        },
        "offsets": {
            "stopping_position": 18,
            "stopping_pos_neg": -14,
        },
    },
}

_RES_TO_PROFILE_KEY = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
}


# ── helpers ────────────────────────────────────────────────────────────────────


def _crop_cell(surf: pygame.Surface, profile: ResolutionProfile, cell_bbox: tuple) -> np.ndarray:
    hx, hy, _, _ = profile.hud_bbox
    vx, vy, vw, vh = cell_bbox
    cell_surf = pygame.Surface((vw, vh))
    cell_surf.blit(surf, (0, 0), area=pygame.Rect(hx + vx, hy + vy, vw, vh))
    arr = pygame.surfarray.array3d(cell_surf)
    return np.transpose(arr, (1, 0, 2))


# ── test runners ───────────────────────────────────────────────────────────────


def test_badges(
    cal_dir: Path,
    badge_gt: dict[str, str],
    profile: ResolutionProfile,
    anchors: dict,
) -> tuple[int, int]:
    print("\n--- Badge classification ---")
    print(f"  {'stem':24s}  {'expected':8s}  {'got':8s}  {'diff':6s}  verdict")
    print("  " + "-" * 58)
    ok = total = 0
    for stem, expected in badge_gt.items():
        p = cal_dir / f"{stem}.png"
        if not p.exists():
            print(f"  {stem:24s}  [skip]")
            continue
        total += 1
        surf = pygame.image.load(str(p))
        cell = _crop_cell(surf, profile, profile.badge_bbox)
        state, diff = classify_badge_state(cell, anchors)
        verdict = "PASS" if state == expected else "FAIL"
        if state == expected:
            ok += 1
        print(f"  {stem:24s}  {expected:8s}  {str(state):8s}  {diff:6.2f}  {verdict}")
    return ok, total


def test_speed_limits(
    cal_dir: Path,
    limit_gt: dict[str, int],
    profile: ResolutionProfile,
    seg,
    dark_templates,
    red_templates,
) -> tuple[int, int]:
    print("\n--- Speed-limit reading ---")
    print(f"  {'stem':16s}  {'expected':8s}  {'got':8s}  {'score':6s}  {'raw':8s}  verdict")
    print("  " + "-" * 62)
    ok = total = 0
    for stem, expected in limit_gt.items():
        p = cal_dir / f"{stem}.png"
        if not p.exists():
            print(f"  {stem:16s}  [skip]")
            continue
        total += 1
        surf = pygame.image.load(str(p))
        cell = _crop_cell(surf, profile, profile.speed_limit_value_bbox)
        val, raw, score = read_speed_limit(cell, dark_templates, seg=seg, red_templates=red_templates)
        verdict = "PASS" if val == expected else "FAIL"
        if val == expected:
            ok += 1
        print(f"  {stem:16s}  {expected:8d}  {str(val):8s}  {score:6.3f}  {raw:8s}  {verdict}")
    return ok, total


def test_stopping_offsets(
    cal_dir: Path,
    offset_gt: dict[str, int | None],
    profile: ResolutionProfile,
    seg,
    dark_templates,
) -> tuple[int, int]:
    print("\n--- Stopping-offset reading ---")
    print(f"  {'stem':24s}  {'expected':9s}  {'got':9s}  {'score':6s}  verdict")
    print("  " + "-" * 58)
    ok = total = 0
    for stem, expected in offset_gt.items():
        p = cal_dir / f"{stem}.png"
        if not p.exists():
            print(f"  {stem:24s}  [skip]")
            continue
        total += 1
        surf = pygame.image.load(str(p))
        cell = _crop_cell(surf, profile, profile.distance_value_bbox)
        val, _, score = read_stopping_offset(cell, dark_templates, seg=seg)
        if expected is None:
            verdict = "PASS" if val is not None else "PASS(None)"  # no crash = pass
        else:
            verdict = "PASS" if val == expected else "FAIL"
        if verdict.startswith("PASS"):
            ok += 1
        print(f"  {stem:24s}  {str(expected):9s}  {str(val):9s}  {score:6.3f}  {verdict}")
    return ok, total


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OCR pipeline offline.")
    parser.add_argument("--res", choices=["1080p", "1440p"], default="1080p", help="Resolution to validate (default: 1080p)")
    args = parser.parse_args()

    pygame.init()

    profile_key = _RES_TO_PROFILE_KEY[args.res]
    profile = PROFILES[profile_key]
    data = CAL_DATA[args.res]
    cal_dir = PROJECT_ROOT / data["cal_dir"]
    seg = seg_for_scale(profile.scale)

    print(f"Validating {args.res} OCR pipeline")
    print(f"  Profile:  {profile.desktop_w}x{profile.desktop_h}, scale={profile.scale}")
    print(f"  Cal dir:  {cal_dir.name}/  (exists={cal_dir.exists()})")

    if not cal_dir.exists():
        print(f"\nERROR: {cal_dir} not found. Provide calibration screenshots first.")
        return 1

    # Load resolution-specific assets
    badges_dir = DEFAULT_TEMPLATES_DIR / profile.badges_subdir
    anchors = load_badge_anchors(badges_dir)
    print(f"  Badges:   {sum(len(v) for v in anchors.values())} anchors from {badges_dir.relative_to(PROJECT_ROOT)}")

    red_dir = DEFAULT_TEMPLATES_DIR / profile.templates_subdir / "digits_red" if profile.templates_subdir else DEFAULT_TEMPLATES_DIR / "digits_red"
    red_templates = build_templates(red_dir) if red_dir.exists() else None
    rt_count = len(red_templates.glyphs) if red_templates else 0
    print(f"  Red tmpl: {rt_count}/10 from {red_dir.relative_to(PROJECT_ROOT)}")

    dark_templates = build_templates()

    b_ok, b_tot = test_badges(cal_dir, data["badges"], profile, anchors)
    sl_ok, sl_tot = test_speed_limits(cal_dir, data["limits"], profile, seg, dark_templates, red_templates)
    so_ok, so_tot = test_stopping_offsets(cal_dir, data["offsets"], profile, seg, dark_templates)

    total_ok = b_ok + sl_ok + so_ok
    total = b_tot + sl_tot + so_tot
    print(f"\n{'='*54}")
    print(f"  Badges:        {b_ok}/{b_tot}")
    print(f"  Speed limits:  {sl_ok}/{sl_tot}")
    print(f"  Stop offsets:  {so_ok}/{so_tot}")
    print(f"  Total:         {total_ok}/{total}  {'ALL PASS' if total_ok == total else 'FAILURES FOUND'}")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    sys.exit(main())

# TIER: T3 — OCR pipeline reads correct real-world values from committed HUD fixtures
"""Assert the production OCR pipeline reads the right value from real game HUD pixels.

Ground truth = committed real cells + hand labels (`_tests/fixtures/ocr/<res>/`),
NOT a code-derived restatement — so it can't be "born wrong agreeing with the code."
Two fixture kinds per resolution, both driven by the same `manifest.json`:

  cells/   pre-cropped cell PNGs (full coverage) -> exercises the read logic
           (segmentation + template match + grammar) at every catalogued value.
  frames/  capture-region quadrant PNGs (what production actually grabs) -> exercises
           the per-resolution crop geometry (quadrant -> HUD -> cell bbox) via the
           real production `crop_cell`.

Runs with zero local calibration screenshots. `--deep` additionally re-crops every
cell straight from the gitignored `_ocr_calibration*/` sources when present, catching
any drift between a committed fixture and a fresh crop.

Regenerate fixtures after re-capturing screenshots:
    uv run python _dev_scripts/extract_ocr_assets.py     # (also does its normal passes)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pygame

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from auto_input.hud_layout import PROFILES, ResolutionProfile  # noqa: E402
from auto_input.ocr import (  # noqa: E402
    DEFAULT_TEMPLATES_DIR,
    build_templates,
    classify_badge_state,
    crop_cell,
    load_badge_anchors,
    read_speed,
    read_speed_limit,
    read_speed_tenths,
    read_stopping_offset,
    seg_for_scale,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "ocr"


class _Assets:
    """Per-resolution OCR assets (templates/anchors/seg), built once."""

    def __init__(self, profile: ResolutionProfile) -> None:
        self.profile = profile
        self.anchors = load_badge_anchors(DEFAULT_TEMPLATES_DIR / profile.badges_subdir)
        red_dir = (
            DEFAULT_TEMPLATES_DIR / profile.templates_subdir / "digits_red" if profile.templates_subdir else DEFAULT_TEMPLATES_DIR / "digits_red"
        )
        self.red_templates = build_templates(red_dir) if red_dir.exists() else None
        self.dark_templates = build_templates()
        self.seg = seg_for_scale(profile.scale)


def _load_cell(path: Path) -> np.ndarray:
    """Load a saved cell PNG into the (H, W, 3) row-major array the readers expect."""
    arr = pygame.surfarray.array3d(pygame.image.load(str(path)))
    return np.transpose(arr, (1, 0, 2))


def _read_value(cell: np.ndarray, cell_type: str, a: _Assets):
    """Run the production reader for `cell_type` and return the parsed value."""
    if cell_type == "badge":
        return classify_badge_state(cell, a.anchors)[0]
    if cell_type == "speed":
        return read_speed(cell, a.dark_templates, seg=a.seg)[0]
    if cell_type == "speed_limit":
        return read_speed_limit(cell, a.dark_templates, seg=a.seg, red_templates=a.red_templates)[0]
    if cell_type == "stopping_offset":
        return read_stopping_offset(cell, a.dark_templates, seg=a.seg)[0]
    raise ValueError(f"unknown cell type: {cell_type}")


def _cell_bbox(profile: ResolutionProfile, cell_type: str):
    return {
        "badge": profile.badge_bbox,
        "speed": profile.speed_value_bbox,
        "speed_limit": profile.speed_limit_value_bbox,
        "stopping_offset": profile.distance_value_bbox,
    }[cell_type]


def _check(fails: list[str], label: str, got, expected) -> None:
    if got != expected:
        fails.append(f"{label}: expected {expected!r}, got {got!r}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="OCR read-correctness over committed fixtures.")
    ap.add_argument(
        "--deep",
        action="store_true",
        help="also re-crop every cell from the local gitignored _ocr_calibration*/ sources when present",
    )
    args = ap.parse_args()

    pygame.init()

    if not FIXTURES_DIR.exists():
        print(f"FAIL: fixtures dir missing: {FIXTURES_DIR}")
        return 1

    manifests = sorted(FIXTURES_DIR.glob("*/manifest.json"))
    if not manifests:
        print(f"FAIL: no manifests under {FIXTURES_DIR}")
        return 1

    fails: list[str] = []
    n_cells = n_frames = n_deep = 0

    for manifest_p in manifests:
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        res = manifest["resolution"]
        res_dir = manifest_p.parent
        profile = PROFILES[tuple(manifest["profile_key"])]
        a = _Assets(profile)

        # --- cells: committed pre-cropped cells -> read logic ---
        for e in manifest["cells"]:
            fx = res_dir / "cells" / f"{e['type']}__{e['stem']}.png"
            if not fx.exists():
                fails.append(f"{res} cell {e['type']}/{e['stem']}: fixture missing ({fx.name})")
                continue
            cell = _load_cell(fx)
            got = _read_value(cell, e["type"], a)
            _check(fails, f"{res} cell {e['type']}/{e['stem']}", got, e["expected"])
            # Speed cells may also lock the tenths digit (decimal-precision log read).
            if e["type"] == "speed" and "expected_tenths" in e:
                got_t = read_speed_tenths(cell, a.dark_templates, seg=a.seg)
                _check(fails, f"{res} cell speed-tenths/{e['stem']}", got_t, e["expected_tenths"])
            n_cells += 1

        # --- frames: capture-region quadrant -> production crop geometry ---
        # Quadrant origin == capture_region origin, so the HUD sits at
        # hud_bbox_in_capture within it; swap that in as the profile's hud origin
        # and the real crop_cell reproduces the production quadrant->HUD->cell path.
        quad_profile = replace(profile, hud_bbox=profile.hud_bbox_in_capture)
        for e in manifest["frames"]:
            fx = res_dir / "frames" / f"{e['type']}__{e['stem']}.png"
            if not fx.exists():
                fails.append(f"{res} frame {e['type']}/{e['stem']}: fixture missing ({fx.name})")
                continue
            quad = pygame.image.load(str(fx))
            cell = crop_cell(quad, quad_profile, _cell_bbox(profile, e["type"]))
            got = _read_value(cell, e["type"], a)
            _check(fails, f"{res} frame {e['type']}/{e['stem']}", got, e["expected"])
            n_frames += 1

        # --- optional deep sweep: re-crop every cell from the full source frame ---
        if args.deep:
            src_dir = ROOT / manifest["source_dir"]
            if not src_dir.exists():
                print(f"  [deep] {res}: source {src_dir.name}/ absent — skipped")
            else:
                for e in manifest["cells"]:
                    src = src_dir / f"{e['stem']}.png"
                    if not src.exists():
                        continue
                    cell = crop_cell(pygame.image.load(str(src)), profile, _cell_bbox(profile, e["type"]))
                    got = _read_value(cell, e["type"], a)
                    _check(fails, f"{res} deep {e['type']}/{e['stem']}", got, e["expected"])
                    n_deep += 1

    if fails:
        print(f"FAIL: {len(fails)} OCR read mismatch(es):")
        for f in fails:
            print(f"  - {f}")
        return 1

    deep_note = f" + {n_deep} deep" if args.deep and n_deep else ""
    print(f"PASS: ocr-reads ({n_cells} cells + {n_frames} frames{deep_note} across {len(manifests)} resolutions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

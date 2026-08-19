# SPDX-License-Identifier: MIT
# TIER: T3 — OCR pipeline reads correct real-world values from committed HUD fixtures
"""Assert the production OCR pipeline reads the right value from real game HUD pixels.

Ground truth = committed real cells + hand labels (`_tests/fixtures/ocr/<res>/`),
NOT a code-derived restatement — so it can't be "born wrong agreeing with the code."
Two fixture kinds per resolution, both driven by the same `manifest.json`:

  cells/   pre-cropped cell PNGs at the MODEL's scale -> exercises the read logic
           (segmentation + template match + grammar) at every catalogued value. Being
           pre-cropped, a cell never asks a profile where it is: it pins the READER.
           1080p only — a 1440p cell would need 1440p templates, and there is one set.
  frames/  capture-region quadrant PNGs (what production actually grabs) -> driven
           through the whole shipping path, downscale_hud -> _crop_cell -> read. This
           is the only kind that asks for a cell bbox, so it pins the GEOMETRY, and a
           cell type with no frame entry has its bbox guarded by nothing.

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
from pathlib import Path

import numpy as np
import pygame

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from auto_input.driver import _crop_cell  # noqa: E402
from auto_input.hud_layout import DOWNSCALE_PROFILE, PROFILES, ResolutionProfile  # noqa: E402
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
from auto_input.sampling import downscale_hud  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "ocr"


class _Assets:
    """The model's OCR assets — ONE set. Every capture is downscaled into the 1080p
    model before anything reads it, so there is no per-resolution set to choose."""

    def __init__(self) -> None:
        self.anchors = load_badge_anchors(DEFAULT_TEMPLATES_DIR / "badges")
        red_dir = DEFAULT_TEMPLATES_DIR / "digits_red"
        self.red_templates = build_templates(red_dir) if red_dir.exists() else None
        self.dark_templates = build_templates()
        self.seg = seg_for_scale(DOWNSCALE_PROFILE.scale)


def _load_cell(path: Path) -> np.ndarray:
    """Load a saved cell PNG into the (H, W, 3) row-major array the readers expect."""
    arr = pygame.surfarray.array3d(pygame.image.load(str(path)))
    return np.transpose(arr, (1, 0, 2))


def _load_bgra(path: Path) -> np.ndarray:
    """Load a PNG into the BGRA layout dxcam hands the driver.

    The downscale checks below run the real production functions, so they have to be fed
    production's actual pixel layout — reading them as RGB would exercise a channel order
    that never occurs live.
    """
    rgb = _load_cell(path)
    bgra = np.empty((*rgb.shape[:2], 4), np.uint8)
    bgra[:, :, 0], bgra[:, :, 1], bgra[:, :, 2] = rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0]
    bgra[:, :, 3] = 255
    return bgra


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
    n_cells = n_deep = n_model = 0
    assets = _Assets()

    # --- downscale invariants (resolution-independent) ---
    # Whatever the capture geometry, downscaling must land on the model's HUD exactly. A new
    # ResolutionProfile whose hud_bbox doesn't scale cleanly fails HERE rather than by
    # reading garbage through mis-sized cell bboxes on someone else's machine.
    #
    # 262x360 is PINNED LITERALLY, never imported. Reading the constant under test into the
    # test makes the assertion scale with any mutation of it and stop discriminating —
    # confirmed by mutation: the imported form passed a deliberate 4px width error.
    MODEL_HUD_W, MODEL_HUD_H = 262, 360
    _check(fails, "model HUD size", DOWNSCALE_PROFILE.hud_bbox_in_capture, (0, 0, MODEL_HUD_W, MODEL_HUD_H))
    for key, p in sorted(PROFILES.items()):
        rl, rt, rr, rb = p.capture_region
        blank = np.zeros((rb - rt, rr - rl, 4), np.uint8)
        got = downscale_hud(blank, p).shape[:2]
        _check(fails, f"downscale shape from {key[0]}x{key[1]}", got, (MODEL_HUD_H, MODEL_HUD_W))

    for manifest_p in manifests:
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        res = manifest["resolution"]
        res_dir = manifest_p.parent
        profile = PROFILES[tuple(manifest["profile_key"])]

        # --- cells: committed model-sized cells -> read logic ---
        for e in manifest["cells"]:
            fx = res_dir / "cells" / f"{e['type']}__{e['stem']}.png"
            if not fx.exists():
                fails.append(f"{res} cell {e['type']}/{e['stem']}: fixture missing ({fx.name})")
                continue
            cell = _load_cell(fx)
            got = _read_value(cell, e["type"], assets)
            _check(fails, f"{res} cell {e['type']}/{e['stem']}", got, e["expected"])
            # Speed cells may also lock the tenths digit (decimal-precision log read).
            if e["type"] == "speed" and "expected_tenths" in e:
                got_t = read_speed_tenths(cell, assets.dark_templates, seg=assets.seg)
                _check(fails, f"{res} cell speed-tenths/{e['stem']}", got_t, e["expected_tenths"])
            n_cells += 1

        # --- frames: the SHIPPING path, grab -> downscale_hud -> _crop_cell -> read ---
        # All production functions, and the only path there is: every desktop resolution
        # is read by the one 1080p model. This is also the only place the downscaled crop
        # geometry is pinned to real pixels.
        for e in manifest["frames"]:
            # A frame is the whole capture quadrant, so EVERY cell is in it — `type` says
            # which one this entry asserts, not what the file contains. `file` lets a second
            # entry re-read a different cell out of a frame already committed, which is how
            # a cell type gets pinned without adding a ~600 KB duplicate of the same pixels.
            fx = res_dir / "frames" / (e.get("file") or f"{e['type']}__{e['stem']}.png")
            if not fx.exists():
                fails.append(f"{res} frame {e['type']}/{e['stem']}: fixture missing ({fx.name})")
                continue
            bgra = _load_bgra(fx)
            shrunk = downscale_hud(bgra, profile)
            mcell = _crop_cell(shrunk, DOWNSCALE_PROFILE.hud_bbox_in_capture, _cell_bbox(DOWNSCALE_PROFILE, e["type"]))
            _check(fails, f"{res} downscaled {e['type']}/{e['stem']}", _read_value(mcell, e["type"], assets), e["expected"])
            n_model += 1

            # A 1080p capture already IS the model, so downscaling must return it untouched.
            # NOT a test of the early-return fast path — centre-aligned bilinear is already
            # bit-exact at 1:1 (verified by mutation), so bypassing it changes nothing. What
            # this catches is a model size that stops matching the 1080p profile, or a
            # resampler swapped for one that is not identity at 1:1 (a pre-blur, a different
            # alignment convention) — either would silently degrade the one resolution that
            # needs no correction at all.
            if (profile.desktop_w, profile.desktop_h) == (DOWNSCALE_PROFILE.desktop_w, DOWNSCALE_PROFILE.desktop_h):
                hx, hy, hw, hh = profile.hud_bbox_in_capture
                _check(fails, f"{res} downscale is a no-op copy ({e['stem']})", bool(np.array_equal(shrunk, bgra[hy : hy + hh, hx : hx + hw])), True)

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
                    got = _read_value(cell, e["type"], assets)
                    _check(fails, f"{res} deep {e['type']}/{e['stem']}", got, e["expected"])
                    n_deep += 1

    if fails:
        print(f"FAIL: {len(fails)} OCR read mismatch(es):")
        for f in fails:
            print(f"  - {f}")
        return 1

    deep_note = f" + {n_deep} deep" if args.deep and n_deep else ""
    print(f"PASS: ocr-reads ({n_cells} model cells + {n_model} downscaled frames{deep_note} across {len(manifests)} resolutions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

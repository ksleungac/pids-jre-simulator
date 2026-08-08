# SPDX-License-Identifier: MIT
"""1080p OCR feasibility probe — true 1080p pipeline.

Game renders HUD at 100% at 1080p; 1440p is proportional upscale. Downscale
1440p refs to 1080p as stand-in for real 1080p captures, then run OCR with
proportionally scaled templates + bboxes + segmentation thresholds.

Does NOT mutate the production 1440p path. Constants are monkey-patched at
runtime for this probe only.

Gitignored (underscore prefix); not for shipping.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

import auto_input.ocr as ocr_mod  # noqa: E402
from auto_input.hud_layout import (  # noqa: E402
    BADGE_BBOX,
    DISTANCE_VALUE_BBOX,
    HUD_BBOX,
    SPEED_LIMIT_VALUE_BBOX,
    SPEED_VALUE_BBOX,
)
from auto_input.ocr import (  # noqa: E402
    BADGE_ANCHOR_FILES,
    Templates,
    build_templates,
    classify_badge_state,
    extract_glyph,
    load_badge_anchors,
    read_distance,
    read_speed,
    read_speed_limit,
    read_stopping_offset,
    segment_chars,
    segment_red_digits,
)

SCALE = 0.75  # 1440 → 1080 (and 2560 → 1920)
PROJECT_ROOT = Path(__file__).parent.parent

# (badge, speed_kmh, distance_m, offset_cm, limit_kmh)
GROUND_TRUTH = {
    "running_my_usage": ("MOVING", 94, 1071, None, 95),
    "passing_jp": ("PASSING", 54, 927, None, 75),
    "stopping_ja": ("STOPPED", 0, 3834, None, 45),
    "stopping_position": ("STOPPED", 0, 8, 18, None),
    "limit_75": ("STOPPED", 0, 1962, None, 75),
    "limit_90": ("MOVING", 50, 11439, None, 90),
}


def load_full_bgra(path: Path) -> np.ndarray:
    """Load PNG as BGRA numpy array (H, W, 4)."""
    s = pygame.image.load(str(path))
    return _surface_to_bgra(s)


def _surface_to_bgra(surf: pygame.Surface) -> np.ndarray:
    w, h = surf.get_size()
    arr3 = pygame.surfarray.pixels3d(surf)  # (W,H,3) RGB
    arr3 = np.transpose(arr3, (1, 0, 2))
    bgra = np.zeros((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = arr3[:, :, 2]
    bgra[:, :, 1] = arr3[:, :, 1]
    bgra[:, :, 2] = arr3[:, :, 0]
    bgra[:, :, 3] = 255
    return bgra


def downscale_bgra(frame_bgra: np.ndarray, factor: float) -> np.ndarray:
    """Resample full frame via pygame.transform.smoothscale (bilinear)."""
    h, w = frame_bgra.shape[:2]
    new_w = int(round(w * factor))
    new_h = int(round(h * factor))
    # Convert BGRA → RGB for pygame surface (alpha not needed for screenshot data)
    rgb = frame_bgra[:, :, [2, 1, 0]].copy()
    surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
    surf_small = pygame.transform.smoothscale(surf, (new_w, new_h))
    return _surface_to_bgra(surf_small)


def downscale_binary_template(tmpl: np.ndarray, factor: float) -> np.ndarray:
    """Resample a binary 0/1 glyph by `factor`. Re-binarizes after resample."""
    h, w = tmpl.shape
    new_w = max(1, int(round(w * factor)))
    new_h = max(1, int(round(h * factor)))
    # Upscale to 0/255 for resample fidelity then re-binarize
    gray = (tmpl * 255).astype(np.uint8)
    rgb = np.stack([gray, gray, gray], axis=-1)  # (H,W,3)
    surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
    surf_small = pygame.transform.smoothscale(surf, (new_w, new_h))
    arr = pygame.surfarray.array3d(surf_small)
    arr = np.transpose(arr, (1, 0, 2)).mean(axis=2)
    return (arr > 127).astype(np.uint8)


def downscale_rgb(arr_rgb: np.ndarray, factor: float) -> np.ndarray:
    """Resample an RGB array (used for badge anchors)."""
    h, w = arr_rgb.shape[:2]
    new_w = max(1, int(round(w * factor)))
    new_h = max(1, int(round(h * factor)))
    surf = pygame.image.frombuffer(arr_rgb.tobytes(), (w, h), "RGB")
    surf_small = pygame.transform.smoothscale(surf, (new_w, new_h))
    arr = pygame.surfarray.array3d(surf_small)
    return np.transpose(arr, (1, 0, 2))


def scale_bbox(bbox: tuple, factor: float) -> tuple:
    return tuple(int(round(v * factor)) for v in bbox)


def crop_cell(frame_bgra: np.ndarray, hud_bbox: tuple, cell_bbox: tuple) -> np.ndarray:
    hx, hy, _, _ = hud_bbox
    vx, vy, vw, vh = cell_bbox
    cell_bgra = frame_bgra[hy + vy : hy + vy + vh, hx + vx : hx + vx + vw]
    return cell_bgra[:, :, [2, 1, 0]].copy()  # RGB


def run_ocr(d_cell, s_cell, sl_cell, b_cell, templates, anchors):
    badge, _b_diff = classify_badge_state(b_cell, anchors)
    s_val, _, _ = read_speed(s_cell, templates)
    d_val, _, _ = read_distance(d_cell, templates)
    o_val, _, _ = read_stopping_offset(d_cell, templates)
    sl_val, _, _ = read_speed_limit(sl_cell, templates)
    return (badge, s_val, d_val, o_val, sl_val)


DIGIT_KNOWN_VALUES = {  # source-stem -> digit-string (m stripped)
    "running_en": "2930",
    "running_ja": "2997",
    "running_my_usage": "1071",
    "stopping_en": "3834",
    "stopping_ja": "3834",
    "5 and 6": "3756",
}

LIMIT_KNOWN_VALUES = {
    "limit_30": "30",
    "limit_35": "35",
    "limit_45": "45",
    "limit_55": "55",
    "limit_65": "65",
    "limit_75": "75",
    "limit_80": "80",
    "limit_85": "85",
    "limit_90": "90",
    "limit_100": "100",
    "limit_110": "110",
    "limit_120": "120",
}


def extract_1080_digit_templates(scaled_consts: dict) -> Templates:
    """Re-extract dark digit templates from 1080p-downscaled reference cells.

    Walks DIGIT_KNOWN_VALUES, downscales each source, crops distance cell at
    1080p coords, segments digits at scaled thresholds, labels each bbox via
    the known value, and saves the first-seen glyph per digit. Returns a
    Templates object suitable for read_distance / read_speed.
    """
    # Constants must already be patched before calling (this fn reads
    # module globals via segment_chars / extract_glyph).
    glyphs: dict[str, np.ndarray] = {}
    dist_1080 = scale_bbox(DISTANCE_VALUE_BBOX, SCALE)
    hud_1080 = scale_bbox(HUD_BBOX, SCALE)
    for stem, digits_str in DIGIT_KNOWN_VALUES.items():
        p = PROJECT_ROOT / "_ocr_calibration" / f"{stem}.png"
        if not p.exists():
            continue
        f1440 = load_full_bgra(p)
        f1080 = downscale_bgra(f1440, SCALE)
        cell = crop_cell(f1080, hud_1080, dist_1080)
        bboxes = segment_chars(cell)
        if len(bboxes) != len(digits_str):
            print(f"  [skip {stem}] segmented {len(bboxes)} digits, expected {len(digits_str)}")
            continue
        for bbox, ch in zip(bboxes, digits_str):
            if ch not in glyphs:
                glyphs[ch] = extract_glyph(cell, bbox)
        print(f"  [extracted from {stem}] got digits {''.join(c for c in digits_str if c in glyphs)}")
    return Templates(glyphs=glyphs)


def extract_1080_red_templates(scaled_consts: dict) -> Templates:
    """Re-extract red speed-limit digit templates from 1080p-downscaled refs.

    Walks LIMIT_KNOWN_VALUES, segments red digits at scaled thresholds, labels
    each bbox by position in the known string. Uses same API shape as
    `_dev_scripts/extract_ocr_assets.py`'s `extract_red_digits`.
    """
    glyphs: dict[str, np.ndarray] = {}
    sl_1080 = scale_bbox(SPEED_LIMIT_VALUE_BBOX, SCALE)
    hud_1080 = scale_bbox(HUD_BBOX, SCALE)
    for stem, digits_str in LIMIT_KNOWN_VALUES.items():
        p = PROJECT_ROOT / "_ocr_calibration" / f"{stem}.png"
        if not p.exists():
            continue
        f1440 = load_full_bgra(p)
        f1080 = downscale_bgra(f1440, SCALE)
        cell = crop_cell(f1080, hud_1080, sl_1080)
        try:
            red_mask, bboxes = segment_red_digits(cell)
        except Exception as e:
            print(f"  [skip {stem}] segment failed: {e}")
            continue
        if len(bboxes) != len(digits_str):
            print(f"  [skip {stem}] segmented {len(bboxes)} red digits, expected {len(digits_str)}")
            continue
        for bbox, ch in zip(bboxes, digits_str):
            if ch not in glyphs:
                x0, y0, x1, y1 = bbox
                glyphs[ch] = red_mask[y0:y1, x0:x1].astype(np.uint8)
        got = "".join(c for c in digits_str if c in glyphs)
        print(f"  [extracted red from {stem}] got digits {got}")
    return Templates(glyphs=glyphs)


def extract_1080_badge_anchors() -> dict:
    """Build downscaled badge anchors by cropping the badge cell from each
    anchor source after the source is itself downscaled to 1080p (instead of
    binary-downscaling the existing 1440p anchor crops, which loses fidelity).
    """
    anchors: dict[str, list] = {"MOVING": [], "STOPPED": [], "PASSING": []}
    badge_1080 = scale_bbox(BADGE_BBOX, SCALE)
    hud_1080 = scale_bbox(HUD_BBOX, SCALE)
    for state, stems in BADGE_ANCHOR_FILES.items():
        for stem in stems:
            p = PROJECT_ROOT / "_ocr_calibration" / f"{stem}.png"
            if not p.exists():
                continue
            f1440 = load_full_bgra(p)
            f1080 = downscale_bgra(f1440, SCALE)
            cell = crop_cell(f1080, hud_1080, badge_1080)  # RGB (H,W,3)
            anchors[state].append(cell)
    return anchors


def main():
    # 1440p baseline (production templates + bboxes, no patching)
    templates_1440 = build_templates()
    anchors_1440 = load_badge_anchors()

    # 1080p scaled set (initial — binary-downscaled, will be REPLACED by fresh extraction)
    anchors_1080 = extract_1080_badge_anchors()

    HUD_1080 = scale_bbox(HUD_BBOX, SCALE)
    DIST_1080 = scale_bbox(DISTANCE_VALUE_BBOX, SCALE)
    SPD_1080 = scale_bbox(SPEED_VALUE_BBOX, SCALE)
    SL_1080 = scale_bbox(SPEED_LIMIT_VALUE_BBOX, SCALE)
    BADGE_1080 = scale_bbox(BADGE_BBOX, SCALE)

    print("[Setup]")
    print(f"  1440p HUD_BBOX:   {HUD_BBOX}")
    print(f"  1080p HUD_BBOX:   {HUD_1080}")
    print(f"  1440p cells:      dist={DISTANCE_VALUE_BBOX} spd={SPEED_VALUE_BBOX} sl={SPEED_LIMIT_VALUE_BBOX} badge={BADGE_BBOX}")
    print(f"  1080p cells:      dist={DIST_1080} spd={SPD_1080} sl={SL_1080} badge={BADGE_1080}")
    print(f"  1440p tmpl '0':   shape={templates_1440.glyphs['0'].shape}")
    print(f"  1440p anchor M[0]:shape={anchors_1440['MOVING'][0].shape}")
    print(f"  1080p anchor M[0]:shape={anchors_1080['MOVING'][0].shape}")

    # Save segmentation constants for restore + scale them
    original_consts = {
        "DIGIT_MIN_H": ocr_mod.DIGIT_MIN_H,
        "DIGIT_MIN_W": ocr_mod.DIGIT_MIN_W,
        "DIGIT_MAX_W": ocr_mod.DIGIT_MAX_W,
        "DECIMAL_MAX_H": ocr_mod.DECIMAL_MAX_H,
        "DECIMAL_MAX_W": ocr_mod.DECIMAL_MAX_W,
        "DISTANCE_MAX_GAP": ocr_mod.DISTANCE_MAX_GAP,
        "SPEED_MAX_GAP": ocr_mod.SPEED_MAX_GAP,
        "TEXT_BAND_Y": ocr_mod.TEXT_BAND_Y,
        "SIGN_BAND_Y": ocr_mod.SIGN_BAND_Y,
    }
    print()
    print("[Original constants]")
    for k, v in original_consts.items():
        print(f"  {k:20s} {v}")

    scaled_consts = {
        "DIGIT_MIN_H": max(1, int(round(original_consts["DIGIT_MIN_H"] * SCALE))),
        "DIGIT_MIN_W": max(1, int(round(original_consts["DIGIT_MIN_W"] * SCALE))),
        "DIGIT_MAX_W": max(1, int(round(original_consts["DIGIT_MAX_W"] * SCALE))),
        "DECIMAL_MAX_H": max(1, int(round(original_consts["DECIMAL_MAX_H"] * SCALE))),
        "DECIMAL_MAX_W": max(1, int(round(original_consts["DECIMAL_MAX_W"] * SCALE))),
        "DISTANCE_MAX_GAP": max(1, int(round(original_consts["DISTANCE_MAX_GAP"] * SCALE))),
        "SPEED_MAX_GAP": max(1, int(round(original_consts["SPEED_MAX_GAP"] * SCALE))),
        "TEXT_BAND_Y": (int(round(original_consts["TEXT_BAND_Y"][0] * SCALE)), int(round(original_consts["TEXT_BAND_Y"][1] * SCALE))),
        "SIGN_BAND_Y": (int(round(original_consts["SIGN_BAND_Y"][0] * SCALE)), int(round(original_consts["SIGN_BAND_Y"][1] * SCALE))),
    }
    print()
    print("[Scaled (1080p) constants]")
    for k, v in scaled_consts.items():
        print(f"  {k:20s} {v}")

    # First: 1440p baseline through production path (sanity)
    print()
    print("=" * 70)
    print("1440p BASELINE (production, no patching)")
    print("=" * 70)
    base_ok = 0
    for name, gt in GROUND_TRUTH.items():
        p = PROJECT_ROOT / "_ocr_calibration" / f"{name}.png"
        if not p.exists():
            continue
        f1440 = load_full_bgra(p)
        d = crop_cell(f1440, HUD_BBOX, DISTANCE_VALUE_BBOX)
        s = crop_cell(f1440, HUD_BBOX, SPEED_VALUE_BBOX)
        sl = crop_cell(f1440, HUD_BBOX, SPEED_LIMIT_VALUE_BBOX)
        b = crop_cell(f1440, HUD_BBOX, BADGE_BBOX)
        got = run_ocr(d, s, sl, b, templates_1440, anchors_1440)
        ok = got == gt
        if ok:
            base_ok += 1
        print(f"  {name:25s} {got}  {'OK' if ok else 'MISMATCH (gt=%s)' % (gt,)}")

    # Now: 1080p path
    print()
    print("=" * 70)
    print("1080p PROBE (downscaled frame + RE-EXTRACTED templates + bboxes + constants)")
    print("=" * 70)

    # Patch constants FIRST (extract_1080_* call segment_chars / segment_red_digits
    # which read these module-level globals).
    for k, v in scaled_consts.items():
        setattr(ocr_mod, k, v)

    a_ok = 0
    try:
        # Fresh re-extraction at 1080p
        print()
        print("[Re-extracting dark digit templates from 1080p sources]")
        templates_1080 = extract_1080_digit_templates(scaled_consts)
        print(f"  -> {len(templates_1080.glyphs)} digits: {sorted(templates_1080.glyphs.keys())}")
        if "0" in templates_1080.glyphs:
            print(f"  -> '0' glyph shape: {templates_1080.glyphs['0'].shape}")

        print()
        print("[Re-extracting red speed-limit templates from 1080p sources]")
        red_1080 = extract_1080_red_templates(scaled_consts)
        print(f"  -> {len(red_1080.glyphs)} red digits: {sorted(red_1080.glyphs.keys())}")

        # Backfill: missing dark digits → fall back to binary-downscaled 1440p originals
        # (shape-only fallback; less faithful than fresh extraction but unblocks the probe).
        missing_dark = sorted(set("0123456789") - templates_1080.glyphs.keys())
        if missing_dark:
            for ch in missing_dark:
                if ch in templates_1440.glyphs:
                    templates_1080.glyphs[ch] = downscale_binary_template(templates_1440.glyphs[ch], SCALE)
                    print(f"  [backfill] dark '{ch}' from binary-downscaled 1440p template: shape={templates_1080.glyphs[ch].shape}")

        # Patch red-templates cache so read_speed_limit picks up 1080p red tmpls.
        # Clear dilated-dark cache too so read_speed_limit re-dilates the fresh dark templates.
        ocr_mod._red_templates_cache = red_1080  # noqa: SLF001
        ocr_mod._dilated_dark_cache = {}  # noqa: SLF001

        print()
        for name, gt in GROUND_TRUTH.items():
            p = PROJECT_ROOT / "_ocr_calibration" / f"{name}.png"
            if not p.exists():
                continue
            f1440 = load_full_bgra(p)
            f1080 = downscale_bgra(f1440, SCALE)
            d = crop_cell(f1080, HUD_1080, DIST_1080)
            s = crop_cell(f1080, HUD_1080, SPD_1080)
            sl = crop_cell(f1080, HUD_1080, SL_1080)
            b = crop_cell(f1080, HUD_1080, BADGE_1080)
            got = run_ocr(d, s, sl, b, templates_1080, anchors_1080)
            ok = got == gt
            if ok:
                a_ok += 1
            print(f"  {name:25s} {got}  {'OK' if ok else 'MISMATCH (gt=%s)' % (gt,)}")
    finally:
        # Restore constants — never leak patched state
        for k, v in original_consts.items():
            setattr(ocr_mod, k, v)

    print()
    print(f"Summary: 1440p baseline {base_ok}/{len(GROUND_TRUTH)}; 1080p probe {a_ok}/{len(GROUND_TRUTH)}")


if __name__ == "__main__":
    pygame.init()
    main()

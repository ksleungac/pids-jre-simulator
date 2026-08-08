# SPDX-License-Identifier: MIT
"""Measure HUD bounding box in native 1080p screenshots and test badge extraction.

Scans the right edge of native 1080p refs for the HUD's white/light background,
derives HUD_BBOX_1080 (x, y, w, h), then crops the badge cell and tests
classify_badge_state against it.

Run: uv run python _dev_scripts/_measure_hud_1080p.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_input.hud_layout import BADGE_BBOX, HUD_BBOX
from auto_input.ocr import classify_badge_state, load_badge_anchors

PROJECT_ROOT = Path(__file__).parent.parent
CAL_1080 = PROJECT_ROOT / "_ocr_calibration_1080p"
CAL_1440 = PROJECT_ROOT / "_ocr_calibration"

# Known badge states for the 1080p set
BADGE_GROUND_TRUTH = {
    "running_en": "MOVING",
    "running_ja": "MOVING",
    "stopping_en": "STOPPED",
    "stopping_ja": "STOPPED",
    "passing_en": "PASSING",
    "passing_ja": "PASSING",
}


def load_rgb(path: Path) -> np.ndarray:
    """Load PNG as RGB numpy array (H, W, 3)."""
    surf = pygame.image.load(str(path))
    arr = pygame.surfarray.array3d(surf)  # (W, H, 3)
    return np.transpose(arr, (1, 0, 2))  # (H, W, 3)


def scan_hud_left_edge(img_rgb: np.ndarray) -> int:
    """Find the HUD panel's left edge pixel x.

    The HUD has a bright (whitish) semi-transparent background. Scan
    right-to-left along a row inside the HUD (y=130, inside badge area)
    looking for where brightness drops below the HUD threshold.
    Returns x of left edge.
    """
    h, w = img_rgb.shape[:2]
    # Row 130 sits inside the badge area at 1440p (badge y=122, h=40 → center y=142).
    # Scaled to 1080p → badge center ≈ y=107. Use y=120 as a safe interior row.
    scan_y = 120
    row = img_rgb[scan_y, :, :].astype(np.float32)  # (W, 3)
    brightness = row.mean(axis=1)  # per-column mean brightness

    # Debug: print brightness profile for rightmost 400 columns
    right_profile = brightness[max(0, w - 400) :]
    print(f"    brightness profile (right 400 cols, every 20): " f"{[f'{v:.0f}' for v in right_profile[::20]]}")

    # Find where brightness consistently exceeds HUD_THRESHOLD scanning left from right
    HUD_THRESHOLD = 160
    hud_x = w - 1
    for x in range(w - 1, max(0, w - 500), -1):
        if brightness[x] >= HUD_THRESHOLD:
            hud_x = x
    # Now find the left edge: scan left from hud_x
    for x in range(hud_x, max(0, w - 500), -1):
        if brightness[x] < HUD_THRESHOLD:
            return x + 1
    return hud_x


def find_hud_bbox_proportional(w: int, h: int) -> tuple[int, int, int, int]:
    """Proportional estimate: 1440p HUD_BBOX × (w/2560)."""
    scale = w / 2560
    hx = int(round(HUD_BBOX[0] * scale))
    hy = int(round(HUD_BBOX[1] * scale))
    hw = int(round(HUD_BBOX[2] * scale))
    hh = int(round(HUD_BBOX[3] * scale))
    return (hx, hy, hw, hh)


def crop_badge_cell(img_rgb: np.ndarray, hud_bbox: tuple, badge_bbox: tuple) -> np.ndarray:
    """Crop badge cell using HUD-relative badge coordinates."""
    hx, hy, _, _ = hud_bbox
    bx, by, bw, bh = badge_bbox
    return img_rgb[hy + by : hy + by + bh, hx + bx : hx + bx + bw].copy()


def scale_bbox(bbox: tuple, factor: float) -> tuple[int, int, int, int]:
    return tuple(int(round(v * factor)) for v in bbox)


def save_rgb_as_png(arr_rgb: np.ndarray, path: Path) -> None:
    """Save an RGB (H,W,3) numpy array as PNG via pygame."""
    h, w = arr_rgb.shape[:2]
    surf = pygame.image.frombuffer(arr_rgb.tobytes(), (w, h), "RGB")
    pygame.image.save(surf, str(path))


def main():
    pygame.init()

    # --- Constants ---
    # 1440p reference
    print(f"1440p HUD_BBOX:   {HUD_BBOX}  (x,y,w,h)")
    print(f"1440p BADGE_BBOX: {BADGE_BBOX}  (HUD-relative x,y,w,h)")

    # Proportional estimate (0.75×) — WIP doc says 1080p is the 100% base,
    # 1440p is 1.333× upscale, so 1080p = 0.75 × 1440p dimensions.
    SCALE = 0.75
    HUD_BBOX_1080_prop = scale_bbox(HUD_BBOX, SCALE)
    BADGE_BBOX_1080_prop = scale_bbox(BADGE_BBOX, SCALE)
    print(f"\n0.75× proportional HUD_BBOX:   {HUD_BBOX_1080_prop}")
    print(f"0.75× proportional BADGE_BBOX: {BADGE_BBOX_1080_prop}")

    # Also try: same HUD size anchored to right edge (10px margin, matching 1440p)
    # 1440p: right margin = 2560 - 2200 - 350 = 10px
    HUD_BBOX_1080_anchored = (1920 - 10 - HUD_BBOX[2], HUD_BBOX[1], HUD_BBOX[2], HUD_BBOX[3])
    print(f"Right-anchored same-size HUD:  {HUD_BBOX_1080_anchored}")

    anchors_1440 = load_badge_anchors()

    # --- Scan left edge from each screenshot for calibration ---
    print("\n--- Scanning left-edge of HUD in native 1080p screenshots ---")
    for stem in list(BADGE_GROUND_TRUTH.keys())[:2]:  # just first 2 for brevity
        p = CAL_1080 / f"{stem}.png"
        if not p.exists():
            continue
        img = load_rgb(p)
        print(f"\n  {stem}:")
        edge_x = scan_hud_left_edge(img)
        print(f"    detected left edge x={edge_x}  (prop={HUD_BBOX_1080_prop[0]}, anchored={HUD_BBOX_1080_anchored[0]})")

    # --- Crop and save badge cells for visual inspection ---
    out_dir = CAL_1080 / "_badge_crops"
    out_dir.mkdir(exist_ok=True)
    print(f"\n--- Saving badge crops to {out_dir} ---")

    anchor_map = {
        "running_en": "MOVING",
        "running_ja": "MOVING",
        "stopping_en": "STOPPED",
        "stopping_ja": "STOPPED",
        "passing_en": "PASSING",
        "passing_ja": "PASSING",
    }

    anchors_1080_prop: dict[str, list] = {"MOVING": [], "STOPPED": [], "PASSING": []}
    anchors_1080_anch: dict[str, list] = {"MOVING": [], "STOPPED": [], "PASSING": []}

    for stem, gt_state in BADGE_GROUND_TRUTH.items():
        p = CAL_1080 / f"{stem}.png"
        if not p.exists():
            continue
        img = load_rgb(p)
        cell_prop = crop_badge_cell(img, HUD_BBOX_1080_prop, BADGE_BBOX_1080_prop)
        cell_anch = crop_badge_cell(img, HUD_BBOX_1080_anchored, BADGE_BBOX)
        save_rgb_as_png(cell_prop, out_dir / f"{stem}_prop.png")
        save_rgb_as_png(cell_anch, out_dir / f"{stem}_anch.png")
        anchors_1080_prop[anchor_map[stem]].append(cell_prop)
        anchors_1080_anch[anchor_map[stem]].append(cell_anch)
        print(f"  {stem}: prop_size={cell_prop.shape[:2]} anch_size={cell_anch.shape[:2]}")

    # --- Classification test: proportional ---
    print("\n--- Badge classification — proportional (0.75×) ---")
    print(f"  {'file':22s}  {'gt':8s}  vs_1440p  vs_native")
    ok_prop_1440 = ok_prop_native = 0
    for stem, gt_state in BADGE_GROUND_TRUTH.items():
        p = CAL_1080 / f"{stem}.png"
        if not p.exists():
            continue
        img = load_rgb(p)
        cell = crop_badge_cell(img, HUD_BBOX_1080_prop, BADGE_BBOX_1080_prop)
        s1, d1 = classify_badge_state(cell, anchors_1440)
        sn, dn = classify_badge_state(cell, anchors_1080_prop)
        if s1 == gt_state:
            ok_prop_1440 += 1
        if sn == gt_state:
            ok_prop_native += 1
        print(f"  {stem:22s}  {gt_state:8s}  {str(s1):8s}({d1:4.1f})  {str(sn):8s}({dn:4.1f})")

    # --- Classification test: anchored (same size) ---
    print("\n--- Badge classification — right-anchored same-size ---")
    ok_anch_1440 = ok_anch_native = 0
    for stem, gt_state in BADGE_GROUND_TRUTH.items():
        p = CAL_1080 / f"{stem}.png"
        if not p.exists():
            continue
        img = load_rgb(p)
        cell = crop_badge_cell(img, HUD_BBOX_1080_anchored, BADGE_BBOX)
        s1, d1 = classify_badge_state(cell, anchors_1440)
        sn, dn = classify_badge_state(cell, anchors_1080_anch)
        if s1 == gt_state:
            ok_anch_1440 += 1
        if sn == gt_state:
            ok_anch_native += 1
        print(f"  {stem:22s}  {gt_state:8s}  {str(s1):8s}({d1:4.1f})  {str(sn):8s}({dn:4.1f})")

    print("\n=== Summary ===")
    print(f"  Proportional (0.75×):  vs 1440p anchors={ok_prop_1440}/6, vs native={ok_prop_native}/6")
    print(f"  Right-anchored (same): vs 1440p anchors={ok_anch_1440}/6, vs native={ok_anch_native}/6")
    print(f"\n  Badge crops saved to: {out_dir}")
    print("  Inspect *_prop.png vs *_anch.png to see which bbox is correct.")


if __name__ == "__main__":
    main()

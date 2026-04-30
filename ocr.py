"""HUD OCR + badge classifier for JR EAST Train Sim.

Three readers:
    - read_distance(cell, templates) -> int meters
    - read_speed(cell, templates) -> int km/h (decimal stripped at decimal-point bbox)
    - classify_badge_state(cell, anchors) -> "MOVING" | "STOPPED" | "PASSING"

Digit OCR pipeline:
    1. Crop value cell using HUD_BBOX + cell-relative bbox from hud_layout.py
    2. Threshold to dark; column-sum locates each char's bbox
    3. Filter to digit-shape; speed cells stop at the decimal-point bbox
    4. Pixel-match each glyph against pre-extracted digit templates 0-9
    5. Concatenate matched chars to integer

Badge classifier: pixel-diff against 6 anchor templates (Moving-EN/JA, Stopped-EN/JA,
Passing-EN/JA); lowest diff wins. Language-agnostic.

Runtime assets live under `ocr_templates/` — pre-extracted small PNGs (digit
glyphs ~20×30 binary, badge anchors 125×45 RGB). The ~33 MB of full desktop
source screenshots that were used to extract them live under `_ocr_calibration/`
(gitignored, local-only). Re-extract via `_dev_scripts/extract_ocr_assets.py`
after re-capturing source screenshots (only needed if the game HUD layout
changes).

Full domain reference: AUTO_INPUT.md.

Run validation: uv run python ocr.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygame

from hud_layout import BADGE_BBOX, DISTANCE_VALUE_BBOX, HUD_BBOX, SPEED_VALUE_BBOX

BADGE_ANCHOR_FILES: dict[str, list[str]] = {
    "MOVING": ["running_en", "running_ja"],
    "STOPPED": ["stopping_en", "stopping_next_station"],
    # PASSING is a transient sub-state of MOVING: badge displays the next *stopping*
    # station while the train crosses an intermediate passing-through station. While
    # PASSING, the HUD distance is to the passing station (NOT the next stopping
    # target), so arrival-PA logic must skip it. Blue pentagon vs MOVING/STOPPED's
    # green — cross-anchor diff ~43 vs within-state ~6, well-separated.
    "PASSING": ["passing_en", "passing_jp"],
}

# Tightened threshold: text is near-black (~0-40), HUD bg is light (~200+), scenery
# bleed-through can land in the gray zone (~80-150). Threshold of 70 keeps text but
# excludes gray scenery noise — matches the user's "boost the dark" intuition.
DARK_THRESHOLD = 70
COLUMN_TEXT_MIN = 2  # need > this many dark px in a column for "has text"
ROW_TEXT_MIN = 1
# Restrict column-scan to this y-band within the value cell. Excludes top/bottom borders and
# scenery bleed-through (HUD bg is semi-transparent, dark objects behind can register as text).
TEXT_BAND_Y: tuple[int, int] = (15, 52)
# Digit-shape filter: digits in the Distance font are ~30-33px tall, 9-23px wide.
# Drops 'm' strokes (h=10-13), label tail fragments (small), and scenery-bleed blobs (wide).
# We don't OCR the 'm' — distance is always reported in meters during transit.
DIGIT_MIN_H = 22
DIGIT_MIN_W = 7
DIGIT_MAX_W = 30
# Decimal-point shape: small dot near baseline. Used by speed OCR as a hard stop so
# the decimal-place digit (e.g. the .9 in 70.9) doesn't slip in via gap variance.
DECIMAL_MAX_H = 10
DECIMAL_MAX_W = 7
DECIMAL_BASELINE_FRACTION = 0.55  # decimal sits in bottom ~half of the text band
# Stop accepting digits at the first large horizontal gap. Inter-digit gaps span
# 3-18 px depending on which digits are adjacent (narrow '1' kerns very wide vs another '1').
# DISTANCE_MAX_GAP=20 keeps consecutive digits together; anything past the 'm' has a much
# larger gap (HUD ornaments, scenery).
# SPEED_MAX_GAP=25 is generous because the decimal-stop (handled separately when
# stop_at_decimal=True) is the primary boundary — gap-stop is a safety net for cases
# where decimal detection fails. Without 25, '1' to '1' kern (18 px in 110.X) would split.
DISTANCE_MAX_GAP = 20
SPEED_MAX_GAP = 25


def crop_cell_from_surface(surf: pygame.Surface, cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop a HUD cell from any game-window surface. cell_bbox is HUD-relative."""
    hx, hy, _, _ = HUD_BBOX
    vx, vy, vw, vh = cell_bbox
    cell = pygame.Surface((vw, vh))
    cell.blit(surf, (0, 0), area=pygame.Rect(hx + vx, hy + vy, vw, vh))
    arr = pygame.surfarray.array3d(cell)
    return np.transpose(arr, (1, 0, 2))  # pygame is column-major; convert to (H, W, 3)


def value_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop distance value cell. Backwards-compat wrapper."""
    return crop_cell_from_surface(surf, DISTANCE_VALUE_BBOX)


def speed_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop speed value cell."""
    return crop_cell_from_surface(surf, SPEED_VALUE_BBOX)


def badge_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop the next-station badge cell."""
    return crop_cell_from_surface(surf, BADGE_BBOX)


DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "ocr_templates"


def load_badge_anchors(assets_dir: Path | None = None) -> dict[str, list[np.ndarray]]:
    """Load pre-extracted badge anchor crops from ocr_templates/badges/<stem>.png.

    Each PNG is a 125×45 RGB crop of the badge cell — pixel-diff against live
    capture matches the format directly, no further extraction at runtime.
    """
    if assets_dir is None:
        assets_dir = DEFAULT_TEMPLATES_DIR / "badges"
    anchors: dict[str, list[np.ndarray]] = {state: [] for state in BADGE_ANCHOR_FILES}
    for state, stems in BADGE_ANCHOR_FILES.items():
        for stem in stems:
            path = assets_dir / f"{stem}.png"
            if not path.exists():
                continue
            surf = pygame.image.load(str(path))
            arr = pygame.surfarray.array3d(surf)
            anchors[state].append(np.transpose(arr, (1, 0, 2)))
    return anchors


def classify_badge_state(cell: np.ndarray, anchors: dict[str, list[np.ndarray]]) -> tuple[str | None, float]:
    """Pixel-diff against each anchor; return (best_state, mean_abs_diff). Lower diff = better match."""
    best_state: str | None = None
    best_diff = float("inf")
    for state, anchor_list in anchors.items():
        for anchor in anchor_list:
            if anchor.shape != cell.shape:
                continue
            diff = float(np.abs(cell.astype(int) - anchor.astype(int)).mean())
            if diff < best_diff:
                best_diff = diff
                best_state = state
    return best_state, best_diff


def load_value_cell(screenshot_path: Path) -> np.ndarray:
    """Load a screenshot from disk, crop HUD, then crop distance value cell."""
    return value_cell_from_surface(pygame.image.load(str(screenshot_path)))


def load_speed_cell(screenshot_path: Path) -> np.ndarray:
    """Load a screenshot from disk, crop HUD, then crop speed value cell."""
    return speed_cell_from_surface(pygame.image.load(str(screenshot_path)))


def segment_chars(
    cell: np.ndarray,
    max_gap: int = DISTANCE_MAX_GAP,
    stop_at_decimal: bool = False,
) -> list[tuple[int, int, int, int]]:
    """Return list of (x0, y0, x1, y1) bboxes, one per character, ordered left-to-right.

    `max_gap` controls where digit collection stops on horizontal gap.

    `stop_at_decimal=True` (used by speed OCR) finds the small decimal-point bbox in
    the bottom half of the text band and uses its x as a hard stop — robust to gap
    variance from anti-aliasing differences.
    """
    gray = cell.mean(axis=2)
    dark = gray < DARK_THRESHOLD
    band_top, band_bot = TEXT_BAND_Y
    band = dark[band_top:band_bot]

    col_has_text = band.sum(axis=0) > COLUMN_TEXT_MIN
    raw: list[tuple[int, int, int, int]] = []
    in_char = False
    x_start = 0

    def finalize(x_end: int) -> None:
        sub = band[:, x_start:x_end]
        row_has = sub.sum(axis=1) > ROW_TEXT_MIN
        ys = np.where(row_has)[0]
        if len(ys) > 0:
            raw.append((x_start, band_top + int(ys[0]), x_end, band_top + int(ys[-1]) + 1))

    for x, has in enumerate(col_has_text):
        if has and not in_char:
            x_start = x
            in_char = True
        elif not has and in_char:
            finalize(x)
            in_char = False
    if in_char:
        finalize(len(col_has_text))

    shape_filtered: list[tuple[int, int, int, int]] = []
    for bb in raw:
        w = bb[2] - bb[0]
        h = bb[3] - bb[1]
        if h >= DIGIT_MIN_H and DIGIT_MIN_W <= w <= DIGIT_MAX_W:
            shape_filtered.append(bb)

    decimal_x: int | None = None
    if stop_at_decimal:
        baseline_y = band_top + int((band_bot - band_top) * DECIMAL_BASELINE_FRACTION)
        for bb in raw:
            w = bb[2] - bb[0]
            h = bb[3] - bb[1]
            if h <= DECIMAL_MAX_H and w <= DECIMAL_MAX_W and bb[1] >= baseline_y:
                decimal_x = bb[0]
                break

    digits: list[tuple[int, int, int, int]] = []
    for bb in shape_filtered:
        if decimal_x is not None and bb[0] >= decimal_x:
            break
        if digits and bb[0] - digits[-1][2] > max_gap:
            break
        digits.append(bb)
    return digits


def extract_glyph(cell: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop a tight bbox from cell; binarize to 0/1 uint8."""
    x0, y0, x1, y1 = bbox
    sub = cell[y0:y1, x0:x1]
    gray = sub.mean(axis=2)
    return (gray < DARK_THRESHOLD).astype(np.uint8)


@dataclass
class Templates:
    glyphs: dict[str, np.ndarray]  # char -> binary glyph

    def match(self, glyph: np.ndarray) -> tuple[str, float]:
        """Return (best_char, score) where score is fraction of matching pixels."""
        best_char = "?"
        best_score = -1.0
        for ch, tmpl in self.glyphs.items():
            score = compare(glyph, tmpl)
            if score > best_score:
                best_score = score
                best_char = ch
        return best_char, best_score


def compare(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of pixels matching after centering both glyphs in a common canvas."""
    h = max(a.shape[0], b.shape[0])
    w = max(a.shape[1], b.shape[1])

    def pad(arr: np.ndarray) -> np.ndarray:
        out = np.zeros((h, w), dtype=np.uint8)
        oy = (h - arr.shape[0]) // 2
        ox = (w - arr.shape[1]) // 2
        out[oy : oy + arr.shape[0], ox : ox + arr.shape[1]] = arr
        return out

    pa, pb = pad(a), pad(b)
    return float((pa == pb).sum() / pa.size)


def build_templates(assets_dir: Path | None = None) -> Templates:
    """Load pre-extracted digit glyphs from ocr_templates/digits/<N>.png.

    Each PNG is a 0/255 grayscale image of a tight-bbox digit (~20×30 px).
    Loaded as a binary numpy array — fed directly to `Templates.match`.

    Re-extract via: uv run python _dev_scripts/extract_ocr_assets.py
    """
    if assets_dir is None:
        assets_dir = DEFAULT_TEMPLATES_DIR / "digits"
    glyphs: dict[str, np.ndarray] = {}
    for ch in "0123456789":
        path = assets_dir / f"{ch}.png"
        if not path.exists():
            continue
        surf = pygame.image.load(str(path))
        arr = pygame.surfarray.array3d(surf)
        # column-major (W,H,3) -> row-major (H,W); collapse to grayscale -> binarize
        gray = np.transpose(arr, (1, 0, 2)).mean(axis=2)
        glyphs[ch] = (gray > 127).astype(np.uint8)
    return Templates(glyphs)


def read_distance(cell: np.ndarray, templates: Templates) -> tuple[int | None, str, float]:
    """Read distance value from a distance cell. Returns (meters_int, raw_text, min_score)."""
    return _read_value(cell, templates, max_gap=DISTANCE_MAX_GAP)


def read_speed(cell: np.ndarray, templates: Templates) -> tuple[int | None, str, float]:
    """Read speed integer from a speed cell. Stops at decimal-point bbox so .X digit doesn't slip in.
    Returns (kmh_int, raw_text, min_score)."""
    return _read_value(cell, templates, max_gap=SPEED_MAX_GAP, stop_at_decimal=True)


def _read_value(
    cell: np.ndarray, templates: Templates, max_gap: int, stop_at_decimal: bool = False
) -> tuple[int | None, str, float]:
    bboxes = segment_chars(cell, max_gap=max_gap, stop_at_decimal=stop_at_decimal)
    chars: list[str] = []
    min_score = 1.0
    for bbox in bboxes:
        glyph = extract_glyph(cell, bbox)
        ch, score = templates.match(glyph)
        chars.append(ch)
        min_score = min(min_score, score)
    raw = "".join(chars)
    value = int(raw) if raw and all(c.isdigit() for c in raw) else None
    return value, raw, min_score


def main() -> int:
    """Sanity-check the runtime assets load + classifier shape-match against committed templates.

    For an end-to-end OCR validation against the original full-screen sources,
    re-capture them into `_ocr_calibration/` and run
    `uv run python _dev_scripts/extract_ocr_assets.py` (it warns + bails if any
    digit / anchor is missing, which is the actual runtime failure mode).
    """
    pygame.init()
    print(f"Loading templates from {DEFAULT_TEMPLATES_DIR}")
    templates = build_templates()
    digits_loaded = sorted(templates.glyphs.keys())
    print(f"Digit templates: {digits_loaded}  ({len(digits_loaded)}/10)")
    missing_digits = sorted(set("0123456789") - set(digits_loaded))
    if missing_digits:
        print(f"[FAIL] missing digits: {missing_digits} — re-run extract_ocr_assets.py after restoring sources.")
        return 1

    anchors = load_badge_anchors()
    anchor_count = sum(len(v) for v in anchors.values())
    print(f"Badge anchors: {anchor_count} across states {sorted(anchors.keys())}")
    expected_anchor_count = sum(len(v) for v in BADGE_ANCHOR_FILES.values())
    if anchor_count < expected_anchor_count:
        print(f"[FAIL] expected {expected_anchor_count} anchors, got {anchor_count}.")
        return 1

    # Cross-classify each anchor against all anchors — every anchor's lowest-diff match
    # must be its own state. Catches mis-extraction or wrong-state filename.
    print("\nCross-classification (anchor self-classifies as own state):")
    print(f"{'anchor':<32} {'expected':<10} {'best':<10} {'diff':<8} verdict")
    print("-" * 72)
    all_ok = True
    for state, anchor_list in anchors.items():
        for i, anchor in enumerate(anchor_list):
            best_state, diff = classify_badge_state(anchor, anchors)
            ok = best_state == state
            all_ok &= ok
            tag = f"{state}[{i}]"
            print(f"{tag:<32} {state:<10} {str(best_state):<10} {diff:<8.2f} {'PASS' if ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

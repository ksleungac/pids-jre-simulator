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

# Known distance values per screenshot — used for template extraction + validation.
# Right-most character is always 'm'; all others are digits read left-to-right.
KNOWN_VALUES: dict[str, str] = {
    "running_en": "2930m",
    "running_ja": "2997m",
    "running_my_usage": "1071m",
    "stopping_en": "3834m",
    "stopping_ja": "3834m",
    "5 and 6": "3756m",
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


def load_badge_anchors(refs_dir: Path) -> dict[str, list[np.ndarray]]:
    """Load badge anchor templates from reference screenshots."""
    anchors: dict[str, list[np.ndarray]] = {state: [] for state in BADGE_ANCHOR_FILES}
    for state, stems in BADGE_ANCHOR_FILES.items():
        for stem in stems:
            path = refs_dir / f"{stem}.png"
            if not path.exists():
                continue
            surf = pygame.image.load(str(path))
            anchors[state].append(badge_cell_from_surface(surf))
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


def expected_digits(value: str) -> str:
    """Strip 'm' suffix from a known value to get the digit string."""
    return value.rstrip("m")


def build_templates(screenshots_dir: Path) -> Templates:
    """Walk KNOWN_VALUES, segment digits, label by position, capture first-seen template per digit."""
    glyphs: dict[str, np.ndarray] = {}
    for stem, expected in KNOWN_VALUES.items():
        path = screenshots_dir / f"{stem}.png"
        if not path.exists():
            print(f"[skip] {path.name} not found")
            continue
        cell = load_value_cell(path)
        bboxes = segment_chars(cell)
        digit_str = expected_digits(expected)
        if len(bboxes) != len(digit_str):
            print(f"[warn] {stem}: segmented {len(bboxes)} digits, expected {len(digit_str)} ({digit_str})")
            continue
        for bbox, ch in zip(bboxes, digit_str):
            if ch not in glyphs:
                glyphs[ch] = extract_glyph(cell, bbox)
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
    pygame.init()
    refs_dir = Path(__file__).parent / "game_references"
    print(f"Building templates from {refs_dir}")
    templates = build_templates(refs_dir)
    print(f"Templates extracted: {sorted(templates.glyphs.keys())}")
    print()

    print(f"{'screenshot':<28} {'expected':<10} {'parsed':<10} {'raw':<10} {'min_score':<10} {'verdict':<10}")
    print("-" * 90)
    all_pass = True
    for stem, expected in KNOWN_VALUES.items():
        path = refs_dir / f"{stem}.png"
        if not path.exists():
            continue
        cell = load_value_cell(path)
        value, raw, score = read_distance(cell, templates)
        expected_int = int(expected_digits(expected))
        ok = value == expected_int
        all_pass &= ok
        print(f"{stem:<28} {expected:<10} {str(value):<10} {raw:<10} {score:<10.4f} {'PASS' if ok else 'FAIL':<10}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

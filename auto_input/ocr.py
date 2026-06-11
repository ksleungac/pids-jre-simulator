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
glyphs ~20×30 binary, badge anchors 111×40 RGB). The ~33 MB of full desktop
source screenshots that were used to extract them live under `_ocr_calibration/`
(gitignored, local-only). Re-extract via `_dev_scripts/extract_ocr_assets.py`
after re-capturing source screenshots (only needed if the game HUD layout
changes).

Full domain reference: auto_input/README.md.

Run validation: uv run python -m auto_input.ocr
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pygame

from .hud_layout import BADGE_BBOX, DISTANCE_VALUE_BBOX, HUD_BBOX, SPEED_LIMIT_VALUE_BBOX, SPEED_VALUE_BBOX, ResolutionProfile

BADGE_ANCHOR_FILES: dict[str, list[str]] = {
    "MOVING": ["running_en", "running_ja"],
    # stopping_next_station = 1440p anchor stem; stopping_ja = 1080p anchor stem.
    # load_badge_anchors skips missing files, so both coexist without branching.
    "STOPPED": ["stopping_en", "stopping_next_station", "stopping_ja"],
    # PASSING is a transient sub-state of MOVING: badge displays the next *stopping*
    # station while the train crosses an intermediate passing-through station. While
    # PASSING, the HUD distance is to the passing station (NOT the next stopping
    # target), so arrival-PA logic must skip it. Blue pentagon vs MOVING/STOPPED's
    # green — cross-anchor diff ~43 vs within-state ~6, well-separated.
    # passing_jp = 1440p anchor stem; passing_ja = 1080p anchor stem.
    "PASSING": ["passing_en", "passing_jp", "passing_ja"],
}

# Reject threshold — diff > this means no anchor is a credible match. Real reads
# sit < 15 (cross-state diffs ~6-15); black-screen / dark-cell garbage frames
# diff 60-110; mid-animation transient spikes >70. 50 cleanly separates real
# from garbage with margin on both sides. Gate lives in classify_badge_state:
# rejected frames return (None, diff) so the detector treats them as OCR FAIL.
# See auto_input/README.md § "Badge classification".
BADGE_DIFF_REJECT = 50.0

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

# Stopping-offset reader: when the train arrives at a platform (badge==STOPPED),
# the same DISTANCE cell content swaps from `1461m` (dark text) to `+/-Ncm` (green
# text — sign shown only for negative; 0/positive omit it). Game prevents stopping
# in red-text out-of-bound zones (overrun → black-screen teleport to next station),
# so red-text reads are unreachable in practice; an unreadable cm value at STOPPED
# is the out-of-bound signal.
GREEN_TEXT_DELTA = 30  # pixel is "green text" when (G - max(R,B)) > this
SIGN_MAX_H = 12  # minus glyph is a thin horizontal bar
SIGN_MAX_W = 18
SIGN_BAND_Y = (24, 42)  # vertical center of text band — minus sits here

# Speed-limit reader: 最高速度 row shows red digit value + dark "km/h" suffix. The
# red mask naturally excludes the suffix (dark text doesn't pass the red threshold).
# Empty cell (no posted limit) → no red pixels → reader returns None.
RED_TEXT_DELTA = 50  # pixel is "red text" when (R - max(G,B)) > this
# The red speed-limit font is rendered with a bolder stroke than the dark-text font
# the digit templates were extracted from. Dilating the thin templates by 3 px (cross
# kernel) closes the stroke-weight gap and lets the existing 0-9 templates match red
# digits without per-color template extraction. Validated against limits 65, 75, 90.
# Sweet-spot calibration: 2x mismatches `6` as `4` on limit 65; 4x+ over-blooms and
# mismatches `9` as `5` on limit 90. 3x clean across all three.
SPEED_LIMIT_TEMPLATE_DILATION = 3
# avg width of a red-text digit at 1440p; used by equal-width split fallback in segment_red_digits
_TYPICAL_RED_DIGIT_WIDTH = 18


@dataclass(frozen=True)
class SegConfig:
    """Per-resolution segmentation constants for the digit OCR pipeline.

    Defaults are the 1440p module-level constants above. Construct a scaled
    instance via ``seg_for_scale(0.75)`` for 1080p, or use ``SEG_DEFAULT``
    for 1440p.
    """

    # fmt: off
    text_band_y:      tuple[int, int] = TEXT_BAND_Y
    digit_min_h:      int             = DIGIT_MIN_H
    digit_min_w:      int             = DIGIT_MIN_W
    digit_max_w:      int             = DIGIT_MAX_W
    decimal_max_h:    int             = DECIMAL_MAX_H
    decimal_max_w:    int             = DECIMAL_MAX_W
    distance_max_gap: int             = DISTANCE_MAX_GAP
    speed_max_gap:    int             = SPEED_MAX_GAP
    sign_band_y:      tuple[int, int] = SIGN_BAND_Y
    sign_max_h:       int             = SIGN_MAX_H
    sign_max_w:       int             = SIGN_MAX_W
    column_text_min:       int             = COLUMN_TEXT_MIN
    red_digit_typical_w:   int             = _TYPICAL_RED_DIGIT_WIDTH
    # fmt: on


# 1440p default — pass to read_* functions at native resolution.
SEG_DEFAULT = SegConfig()


def seg_for_scale(scale: float) -> SegConfig:
    """Derive a SegConfig by proportionally scaling all 1440p pixel thresholds.

    Use ``seg_for_scale(0.75)`` for 1080p. All values floored at 1.
    """

    def sc(v: int) -> int:
        return max(1, int(round(v * scale)))

    def sc2(t: tuple[int, int]) -> tuple[int, int]:
        return (sc(t[0]), sc(t[1]))

    return SegConfig(
        text_band_y=sc2(TEXT_BAND_Y),
        digit_min_h=sc(DIGIT_MIN_H),
        digit_min_w=sc(DIGIT_MIN_W),
        digit_max_w=sc(DIGIT_MAX_W),
        decimal_max_h=sc(DECIMAL_MAX_H),
        decimal_max_w=sc(DECIMAL_MAX_W),
        distance_max_gap=sc(DISTANCE_MAX_GAP),
        speed_max_gap=sc(SPEED_MAX_GAP),
        sign_band_y=sc2(SIGN_BAND_Y),
        sign_max_h=sc(SIGN_MAX_H),
        sign_max_w=sc(SIGN_MAX_W),
        column_text_min=max(1, int(round(COLUMN_TEXT_MIN * scale))),
        red_digit_typical_w=sc(_TYPICAL_RED_DIGIT_WIDTH),
    )


def _crop_hud_cell(surf: pygame.Surface, hud_bbox: tuple[int, int, int, int], cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Shared cropper body: blit a HUD-relative cell out of a full surface."""
    hx, hy, _, _ = hud_bbox
    vx, vy, vw, vh = cell_bbox
    cell = pygame.Surface((vw, vh))
    cell.blit(surf, (0, 0), area=pygame.Rect(hx + vx, hy + vy, vw, vh))
    arr = pygame.surfarray.array3d(cell)
    return np.transpose(arr, (1, 0, 2))  # pygame is column-major; convert to (H, W, 3)


def crop_cell_from_surface(surf: pygame.Surface, cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop a HUD cell from any game-window surface. cell_bbox is HUD-relative (1440p reference HUD_BBOX)."""
    return _crop_hud_cell(surf, HUD_BBOX, cell_bbox)


def crop_cell(surf: pygame.Surface, profile: ResolutionProfile, cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Profile-aware sibling of crop_cell_from_surface: HUD origin from the profile, not the 1440p constant."""
    return _crop_hud_cell(surf, profile.hud_bbox, cell_bbox)


def value_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop distance value cell. Backwards-compat wrapper."""
    return crop_cell_from_surface(surf, DISTANCE_VALUE_BBOX)


def speed_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop speed value cell."""
    return crop_cell_from_surface(surf, SPEED_VALUE_BBOX)


def speed_limit_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop speed-limit value cell."""
    return crop_cell_from_surface(surf, SPEED_LIMIT_VALUE_BBOX)


def badge_cell_from_surface(surf: pygame.Surface) -> np.ndarray:
    """Crop the next-station badge cell."""
    return crop_cell_from_surface(surf, BADGE_BBOX)


from app_paths import project_root

DEFAULT_TEMPLATES_DIR = project_root() / "ocr_templates"


def load_badge_anchors(assets_dir: Path | None = None) -> dict[str, list[np.ndarray]]:
    """Load pre-extracted badge anchor crops from ocr_templates/badges/<stem>.png.

    Each PNG is a 111×40 RGB crop of the badge cell — pixel-diff against live
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
    """Pixel-diff against each anchor; return (best_state, mean_abs_diff). Lower diff = better match.

    Returns (None, diff) when best_diff > BADGE_DIFF_REJECT — no anchor is a credible
    match (dark-cell garbage from black-screen frames, mid-animation spikes, etc.).
    Diff value is preserved for diagnostics. See auto_input/README.md § "Badge classification".
    """
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
    if best_diff > BADGE_DIFF_REJECT:
        return None, best_diff
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
    *,
    seg: SegConfig | None = None,
) -> list[tuple[int, int, int, int]]:
    """Return list of (x0, y0, x1, y1) bboxes, one per character, ordered left-to-right.

    `max_gap` controls where digit collection stops on horizontal gap.

    `stop_at_decimal=True` (used by speed OCR) finds the small decimal-point bbox in
    the bottom half of the text band and uses its x as a hard stop — robust to gap
    variance from anti-aliasing differences.

    `seg` overrides module-level segmentation constants for non-1440p resolutions.
    Pass ``seg_for_scale(0.75)`` for 1080p; omit for 1440p (uses module defaults).
    """
    _seg = seg or SEG_DEFAULT
    gray = cell.mean(axis=2)
    dark = gray < DARK_THRESHOLD
    band_top, band_bot = _seg.text_band_y
    band = dark[band_top:band_bot]

    col_has_text = band.sum(axis=0) > _seg.column_text_min
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
        if h >= _seg.digit_min_h and _seg.digit_min_w <= w <= _seg.digit_max_w:
            shape_filtered.append(bb)

    decimal_x: int | None = None
    if stop_at_decimal:
        baseline_y = band_top + int((band_bot - band_top) * DECIMAL_BASELINE_FRACTION)
        for bb in raw:
            w = bb[2] - bb[0]
            h = bb[3] - bb[1]
            if h <= _seg.decimal_max_h and w <= _seg.decimal_max_w and bb[1] >= baseline_y:
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


def _resize_nn(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Nearest-neighbor resize for binary uint8 arrays. Pure numpy, no extra deps."""
    row_idx = np.round(np.linspace(0, arr.shape[0] - 1, target_h)).astype(int)
    col_idx = np.round(np.linspace(0, arr.shape[1] - 1, target_w)).astype(int)
    return arr[np.ix_(row_idx, col_idx)]


def compare(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of pixels matching after resizing the template (b) to the glyph (a) shape.

    Previously center-padded both arrays to a max-size canvas — worked within a
    single resolution but gave poor scores when glyph and template sizes differ
    significantly (e.g. 1080p glyph vs 1440p template). Nearest-neighbor resize
    is exact at identical sizes (no-op path) and correct across resolutions, so
    1440p templates can be used directly against 1080p glyphs without a separate
    1080p dark-digit template set.
    """
    if a.shape != b.shape:
        b = _resize_nn(b, a.shape[0], a.shape[1])
    return float((a == b).sum() / a.size)


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


def read_distance(cell: np.ndarray, templates: Templates, seg: SegConfig | None = None) -> tuple[int | None, str, float]:
    """Read distance value from a distance cell. Returns (meters_int, raw_text, min_score)."""
    _seg = seg or SEG_DEFAULT
    return _read_value(cell, templates, max_gap=_seg.distance_max_gap, seg=_seg)


def read_speed(cell: np.ndarray, templates: Templates, seg: SegConfig | None = None) -> tuple[int | None, str, float]:
    """Read speed integer from a speed cell. Stops at decimal-point bbox so .X digit doesn't slip in.
    Returns (kmh_int, raw_text, min_score)."""
    _seg = seg or SEG_DEFAULT
    return _read_value(cell, templates, max_gap=_seg.speed_max_gap, stop_at_decimal=True, seg=_seg)


def read_stopping_offset(cell: np.ndarray, templates: Templates, seg: SegConfig | None = None) -> tuple[int | None, str, float]:
    """Read green stopping-offset cm value from the (m/cm-shared) distance cell at STOPPED.

    Returns (offset_cm, raw, min_score). `offset_cm` is signed int (negative = train
    stopped past target mark) or `None` if no green text was readable. Caller may
    treat `None` at a freshly-arrived STOPPED frame as "out-of-bound" — the game
    prevents users from physically stopping in the red zone, so unreadable ≡
    overrun-teleport in practice.

    Pipeline differs from read_distance in two ways:
    - Color mask: `(G - max(R,B)) > GREEN_TEXT_DELTA` instead of `gray < DARK_THRESHOLD`.
    - Sign detection: a small bbox in the vertical center of the text band, left of
      the first digit, is treated as a leading minus. No `+` glyph (positive omitted).
    The `cm` suffix is the same green color but smaller than digits — the existing
    DIGIT_MIN_H shape filter excludes it as not-a-digit. Digit templates are reused
    (binarization is colour-agnostic; shape is identical to dark-text digits).
    """
    _seg = seg or SEG_DEFAULT
    R = cell[..., 0].astype(int)
    G = cell[..., 1].astype(int)
    B = cell[..., 2].astype(int)
    green = (G - np.maximum(R, B)) > GREEN_TEXT_DELTA

    band_top, band_bot = _seg.text_band_y
    band = green[band_top:band_bot]
    col_has_text = band.sum(axis=0) > _seg.column_text_min

    raw_bboxes: list[tuple[int, int, int, int]] = []
    in_char = False
    x_start = 0

    def finalize(x_end: int) -> None:
        sub = band[:, x_start:x_end]
        row_has = sub.sum(axis=1) > ROW_TEXT_MIN
        ys = np.where(row_has)[0]
        if len(ys) > 0:
            raw_bboxes.append((x_start, band_top + int(ys[0]), x_end, band_top + int(ys[-1]) + 1))

    for x, has in enumerate(col_has_text):
        if has and not in_char:
            x_start = x
            in_char = True
        elif not has and in_char:
            finalize(x)
            in_char = False
    if in_char:
        finalize(len(col_has_text))

    digit_bboxes: list[tuple[int, int, int, int]] = []
    sign_bbox: tuple[int, int, int, int] | None = None
    sign_y_min, sign_y_max = _seg.sign_band_y
    for bb in raw_bboxes:
        w = bb[2] - bb[0]
        h = bb[3] - bb[1]
        bb_y_mid = (bb[1] + bb[3]) // 2
        if h >= _seg.digit_min_h and _seg.digit_min_w <= w <= _seg.digit_max_w:
            digit_bboxes.append(bb)
        elif h <= _seg.sign_max_h and w <= _seg.sign_max_w and sign_y_min <= bb_y_mid <= sign_y_max:
            if sign_bbox is None or bb[0] < sign_bbox[0]:
                sign_bbox = bb

    sign = -1 if (sign_bbox is not None and digit_bboxes and sign_bbox[0] < digit_bboxes[0][0]) else 1

    chars: list[str] = []
    min_score = 1.0
    for bb in digit_bboxes:
        x0, y0, x1, y1 = bb
        glyph = green[y0:y1, x0:x1].astype(np.uint8)
        ch, score = templates.match(glyph)
        chars.append(ch)
        min_score = min(min_score, score)

    digits_str = "".join(chars)
    raw = ("-" if sign < 0 else "") + digits_str
    if not digits_str or not all(c.isdigit() for c in digits_str):
        return None, raw, min_score
    return sign * int(digits_str), raw, min_score


def _dilate_binary(arr: np.ndarray, iters: int) -> np.ndarray:
    """Cross-kernel binary dilation. Each iteration expands the True region by 1 px in 4 directions."""
    for _ in range(iters):
        out = arr.copy()
        out[1:] |= arr[:-1]
        out[:-1] |= arr[1:]
        out[:, 1:] |= arr[:, :-1]
        out[:, :-1] |= arr[:, 1:]
        arr = out
    return arr


# Speed-limit grammar: posted limits are always in 5/10 km/h increments. Observed
# range in JR EAST Train Sim Real is 25–130 — no lines drop below 25 km/h in normal
# operation per user. Out-of-grammar reads (e.g. `1` from a 90 misread, `84` from
# an 8-as-4 misread, `5` from a single-digit misread of `50`) are returned as None
# at the reader boundary so junk values don't pollute the JSONL.
VALID_SPEED_LIMITS: frozenset[int] = frozenset(range(25, 131, 5))


# Score threshold below which a grammar-valid argmin read is distrusted and equal_width
# is also tried. Calibrated on 31-frame chuo `100` corpus: low-confidence band is
# 0.65-0.66 (always wrong-or-uncertain), high-confidence band is 0.92+ (always correct).
ARGMIN_TRUST_SCORE = 0.85


def segment_red_digits(
    cell: np.ndarray, split_strategy: str = "argmin", *, seg: SegConfig | None = None
) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """Color-mask + segment + glued-digit split + shape filter for the red speed-limit cell.

    Returns `(red_mask, digit_bboxes)`. `red_mask` is the full-cell binary mask of
    red-text pixels; `digit_bboxes` are `(x0, y0, x1, y1)` tuples ordered left-to-right
    that pass the digit-shape filter.

    The bold red font kerns some digit pairs (notably 9-0, 8-0, 1-0) tightly enough
    that column-has-text never drops below threshold between them, merging into one
    over-wide run.

    Two split strategies:
      - "argmin" (default): split over-wide runs at the deepest column-density valley.
        Works when adjacent digits have a clear inter-digit kerning dip. Fails when a
        digit's natural hollow (e.g. `0`'s interior) is deeper than the boundary —
        e.g. limit_100's `0+0` merged blob has its splits land inside the `0`s.
      - "equal_width": split into N equal-width parts where N = round(width /
        _TYPICAL_RED_DIGIT_WIDTH). Ignores column-density entirely. Robust to hollow-
        as-boundary confusion; less precise when digits actually have very different
        widths (a `1` is 10 wide, a `0` is 22 wide).
    `read_speed_limit` runs "argmin" first, falls back to "equal_width" if grammar
    validation rejects the result.

    Used by `read_speed_limit` and by the red-template extractor in
    `_dev_scripts/extract_ocr_assets.py`.
    """
    _seg = seg or SEG_DEFAULT
    R = cell[..., 0].astype(int)
    G = cell[..., 1].astype(int)
    B = cell[..., 2].astype(int)
    red = (R - np.maximum(G, B)) > RED_TEXT_DELTA

    band_top, band_bot = _seg.text_band_y
    band = red[band_top:band_bot]
    col_has_text = band.sum(axis=0) > _seg.column_text_min

    raw_bboxes: list[tuple[int, int, int, int]] = []
    in_char = False
    x_start = 0

    def finalize(x_end: int) -> None:
        sub = band[:, x_start:x_end]
        row_has = sub.sum(axis=1) > ROW_TEXT_MIN
        ys = np.where(row_has)[0]
        if len(ys) > 0:
            raw_bboxes.append((x_start, band_top + int(ys[0]), x_end, band_top + int(ys[-1]) + 1))

    for x, has in enumerate(col_has_text):
        if has and not in_char:
            x_start = x
            in_char = True
        elif not has and in_char:
            finalize(x)
            in_char = False
    if in_char:
        finalize(len(col_has_text))

    def _finalize_y(sx0: int, sx1: int) -> tuple[int, int, int, int] | None:
        sub = band[:, sx0:sx1]
        row_has = sub.sum(axis=1) > ROW_TEXT_MIN
        ys = np.where(row_has)[0]
        if len(ys) == 0:
            return None
        return (sx0, band_top + int(ys[0]), sx1, band_top + int(ys[-1]) + 1)

    split_bboxes: list[tuple[int, int, int, int]] = []
    if split_strategy == "equal_width":
        # Divide each over-wide run into N equal parts (N = round(W / typical-digit-width)).
        # Ignores column density — robust to hollow-as-boundary confusion.
        for bb in raw_bboxes:
            x0, _, x1, _ = bb
            w = x1 - x0
            if w <= _seg.digit_max_w:
                split_bboxes.append(bb)
                continue
            n = max(2, round(w / _seg.red_digit_typical_w))
            for i in range(n):
                sx0 = x0 + (w * i) // n
                sx1 = x0 + (w * (i + 1)) // n
                fbb = _finalize_y(sx0, sx1)
                if fbb is not None:
                    split_bboxes.append(fbb)
    else:
        # Recursive split at deepest column-density valley until each sub-bbox fits
        # digit_max_w or no clear valley remains.
        queue: list[tuple[int, int, int, int]] = list(raw_bboxes)
        while queue:
            bb = queue.pop(0)
            x0, _, x1, _ = bb
            if x1 - x0 <= _seg.digit_max_w:
                split_bboxes.append(bb)
                continue
            col_sums = band[:, x0:x1].sum(axis=0)
            edge_pad = 3
            inner = col_sums[edge_pad : len(col_sums) - edge_pad]
            if len(inner) == 0:
                split_bboxes.append(bb)
                continue
            min_idx = int(np.argmin(inner))
            if inner[min_idx] >= 0.6 * col_sums.max():
                split_bboxes.append(bb)
                continue
            split_x = x0 + edge_pad + min_idx
            for sx0, sx1 in [(x0, split_x), (split_x, x1)]:
                fbb = _finalize_y(sx0, sx1)
                if fbb is not None:
                    queue.append(fbb)

    digit_bboxes = [bb for bb in split_bboxes if bb[3] - bb[1] >= _seg.digit_min_h and _seg.digit_min_w <= bb[2] - bb[0] <= _seg.digit_max_w]
    return red, digit_bboxes


# Lazy-loaded cache for red-text digit templates (extracted from limit screenshots
# via _dev_scripts/extract_ocr_assets.py and saved under ocr_templates/digits_red/).
# Coverage may be partial — the matcher in read_speed_limit falls back to dilated
# dark templates when a digit isn't covered.
_red_templates_cache: Templates | None = None


def _get_red_digit_templates() -> Templates:
    """Lazy-load red-text digit templates. Empty Templates returned if dir absent."""
    global _red_templates_cache
    if _red_templates_cache is None:
        red_dir = DEFAULT_TEMPLATES_DIR / "digits_red"
        _red_templates_cache = build_templates(red_dir) if red_dir.exists() else Templates(glyphs={})
    return _red_templates_cache


# Cache dilated dark templates per source-Templates identity. The dilation is a pure
# function of (templates, SPEED_LIMIT_TEMPLATE_DILATION); both are stable at runtime.
# Mirrors the _red_templates_cache pattern above.
_dilated_dark_cache: dict[int, Templates] = {}


def _get_dilated_dark_templates(templates: Templates) -> Templates:
    """Lazy-build dilated-dark templates for speed-limit matching, keyed by id(templates)."""
    key = id(templates)
    cached = _dilated_dark_cache.get(key)
    if cached is None:
        cached = Templates(glyphs={ch: _dilate_binary(t, SPEED_LIMIT_TEMPLATE_DILATION) for ch, t in templates.glyphs.items()})
        _dilated_dark_cache[key] = cached
    return cached


def read_speed_limit(
    cell: np.ndarray, templates: Templates, seg: SegConfig | None = None, red_templates: Templates | None = None
) -> tuple[int | None, str, float]:
    """Read red speed-limit (最高速度) value in km/h. Returns (kmh|None, raw, min_score).

    `None` is a valid result, not a failure: speed-limit is line-dependent — some lines
    post it in the cab, others don't. An empty cell is the normal "no posted limit"
    state, not an OCR fault. The dark `km/h` suffix is excluded by the red color mask.

    Two-tier matching: each segmented glyph is scored against (a) red-text digit
    templates extracted from limit screenshots if available, and (b) the existing
    dark-text templates dilated by SPEED_LIMIT_TEMPLATE_DILATION. Best-of-both wins
    per glyph — red templates dominate for covered digits, dilated dark covers any
    gaps.

    Score-gated two-try splitter: argmin runs first. If grammar-valid AND
    min_score >= ARGMIN_TRUST_SCORE, return immediately. Otherwise also try
    equal_width and prefer its grammar-valid result. Closes the limit_100 misread
    mode where argmin's `0+0` split lands asymmetrically inside a digit's hollow,
    producing low-confidence wrong reads (live capture saw `110` @ 0.65; saved-PNG
    replay sees `160` @ 0.66 — both repaired by equal_width's symmetric split
    returning `100` @ 0.92). Cases without a merged blob (e.g. real limit_110 has
    three separate bboxes) clear the threshold via argmin alone, or — if rendering
    variance dips score below threshold — produce identical bboxes between
    strategies, so the fallback agrees rather than breaking a clean read.

    Boundary refinement: for any consecutive pair of bboxes that touch (came from a
    glued-digit split in `segment_red_digits`), the split column is locally re-searched
    via a 2D neighborhood (left_end and right_start independently within ±3 px of the
    baseline boundary, with left_end ≤ right_start so the search can also drop the
    boundary column entirely). Each (left_end, right_start) candidate generates a
    digit pair; the cartesian product across pairs is filtered by grammar validation,
    with the highest min-score grammar-valid combo winning. Fixes contamination cases
    like limit_110 where the column-density valley falls inside the right digit's
    curve and bleeds it into the left digit's bbox.

    Domain validation: out-of-grammar reads (not in 5/10 km/h increments, > 130) are
    returned as None — common misread modes (8→4 mismatch giving `45`, contaminated
    splits giving `170`, single-digit reads giving `1`) all fail this check.
    """
    red_t = red_templates if red_templates is not None else _get_red_digit_templates()
    dilated_t = _get_dilated_dark_templates(templates)

    argmin_attempt = _try_read_speed_limit(cell, "argmin", red_t, dilated_t, seg=seg)
    a_val, a_raw, a_score = argmin_attempt
    if a_val is not None and a_score >= ARGMIN_TRUST_SCORE:
        return a_val, a_raw, a_score

    eqw_attempt = _try_read_speed_limit(cell, "equal_width", red_t, dilated_t, seg=seg)
    e_val, e_raw, e_score = eqw_attempt
    if e_val is not None:
        return e_val, e_raw, e_score

    # Neither path produced a confident grammar-valid read. Fall back to argmin's
    # result (grammar-valid at low score, or raw fallback).
    return argmin_attempt


def _try_read_speed_limit(
    cell: np.ndarray,
    split_strategy: str,
    red_t: Templates,
    dilated_t: Templates,
    *,
    seg: SegConfig | None = None,
) -> tuple[int | None, str, float]:
    """Single-strategy attempt at reading the speed-limit cell.
    Returns (value, raw, min_score). Caller drives the 2-try retry."""
    _seg = seg or SEG_DEFAULT
    red, digit_bboxes = segment_red_digits(cell, split_strategy=split_strategy, seg=_seg)
    band_top, band_bot = _seg.text_band_y
    band = red[band_top:band_bot]

    def best_match(glyph: np.ndarray) -> tuple[str, float]:
        red_ch, red_score = red_t.match(glyph) if red_t.glyphs else ("?", -1.0)
        dark_ch, dark_score = dilated_t.match(glyph)
        return (red_ch, red_score) if red_score >= dark_score else (dark_ch, dark_score)

    def extract_glyph_at(x0: int, x1: int) -> np.ndarray | None:
        sub = band[:, x0:x1]
        row_has = sub.sum(axis=1) > ROW_TEXT_MIN
        ys = np.where(row_has)[0]
        if len(ys) == 0:
            return None
        y0 = band_top + int(ys[0])
        y1 = band_top + int(ys[-1]) + 1
        return red[y0:y1, x0:x1].astype(np.uint8)

    # Generate per-segment candidates. Single bboxes yield one candidate; touching
    # pairs (split-derived) yield a 2D-search neighborhood of (left_end, right_start)
    # boundary positions with left_end ≤ right_start (allowing a gap between halves
    # when the digits' strokes overlap, e.g. limit_110 where 0's left curve crosses
    # 1's right edge). Cartesian product over segments × candidates is then filtered
    # by domain validation; the grammar-passing combo wins, even if a few hundredths
    # below an invalid one. Lets `110` beat `160` when scores are 0.65 vs 0.66.
    segments_candidates: list[list[tuple[str, float]]] = []
    i = 0
    while i < len(digit_bboxes):
        if i + 1 < len(digit_bboxes) and digit_bboxes[i][2] == digit_bboxes[i + 1][0]:
            x0L = digit_bboxes[i][0]
            x1R = digit_bboxes[i + 1][2]
            base_split = digit_bboxes[i][2]
            cands: list[tuple[str, float]] = []
            for left_end_d in range(-3, 4):
                for right_start_d in range(left_end_d, 4):
                    le = base_split + left_end_d
                    rs = base_split + right_start_d
                    if le <= x0L + DIGIT_MIN_W or rs >= x1R - DIGIT_MIN_W:
                        continue
                    gL = extract_glyph_at(x0L, le)
                    gR = extract_glyph_at(rs, x1R)
                    if gL is None or gR is None:
                        continue
                    chL, sL = best_match(gL)
                    chR, sR = best_match(gR)
                    cands.append((chL + chR, min(sL, sR)))
            if not cands:
                # Fallback: use baseline split as-is.
                for bb in (digit_bboxes[i], digit_bboxes[i + 1]):
                    x0, y0, x1, y1 = bb
                    glyph = red[y0:y1, x0:x1].astype(np.uint8)
                    ch, score = best_match(glyph)
                    cands.append((ch, score))
                segments_candidates.append([cands[0]])
                segments_candidates.append([cands[1]])
            else:
                segments_candidates.append(cands)
            i += 2
        else:
            x0, y0, x1, y1 = digit_bboxes[i]
            glyph = red[y0:y1, x0:x1].astype(np.uint8)
            ch, score = best_match(glyph)
            segments_candidates.append([(ch, score)])
            i += 1

    if not segments_candidates:
        return None, "", 1.0

    # Cartesian product → pick highest-scoring grammar-valid combo; fall through to
    # highest-scoring overall if none are valid (so domain validation still fires).
    best_valid: tuple[float, str, int] | None = None
    best_any: tuple[float, str] | None = None
    for combo in product(*segments_candidates):
        raw = "".join(ch for ch, _ in combo)
        score = min(s for _, s in combo)
        if best_any is None or score > best_any[0]:
            best_any = (score, raw)
        if not raw or not all(c.isdigit() for c in raw):
            continue
        value = int(raw)
        if value in VALID_SPEED_LIMITS and (best_valid is None or score > best_valid[0]):
            best_valid = (score, raw, value)

    if best_valid is not None:
        return best_valid[2], best_valid[1], best_valid[0]
    if best_any is not None:
        return None, best_any[1], best_any[0]
    return None, "", 1.0


def _read_value(
    cell: np.ndarray, templates: Templates, max_gap: int, stop_at_decimal: bool = False, seg: SegConfig | None = None
) -> tuple[int | None, str, float]:
    bboxes = segment_chars(cell, max_gap=max_gap, stop_at_decimal=stop_at_decimal, seg=seg)
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
    # Each state must have ≥1 anchor. BADGE_ANCHOR_FILES lists per-state stems including
    # resolution-specific names (some won't exist in every dir — that's expected).
    missing_states = [s for s, lst in anchors.items() if not lst]
    if missing_states:
        print(f"[FAIL] states with no anchors: {missing_states} — re-run extract_ocr_assets.py.")
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

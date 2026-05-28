"""Extract OCR runtime assets from local-only source screenshots.

Five-pass extraction:
    1. **Digit glyphs (dark, 1440p)** — for each KNOWN_VALUES screenshot, segment
       the distance cell, label each glyph by position, save first-seen as a tight
       binary PNG at `ocr_templates/digits/<N>.png`.
    2. **Digit glyphs (red, 1440p)** — same for KNOWN_LIMIT_VALUES speed-limit
       cells, saved at `ocr_templates/digits_red/<N>.png`.
    3. **Badge anchors (1440p)** — crop BADGE_BBOX from each BADGE_ANCHOR_FILES
       screenshot, save as `ocr_templates/badges/<stem>.png`.
    4. **Badge anchors (1080p)** — crop 1080p-profile badge cell from each
       BADGE_ANCHOR_FILES_1080P screenshot, save as
       `ocr_templates/1080p/badges/<stem>.png`.
    5. **Digit glyphs (red, 1080p)** — same as pass 2 but using 1080p profile
       crop + 0.75× segmentation, saved at `ocr_templates/1080p/digits_red/<N>.png`.

1440p source screenshots: `_ocr_calibration/` (gitignored, ~33 MB full-desktop caps).
1080p source screenshots: `_ocr_calibration_1080p/` (gitignored, native 1080p caps).
The committed runtime assets under `ocr_templates/` are a few KB total.

Run after re-capturing reference screenshots (e.g. game HUD layout changed):
    uv run python _dev_scripts/extract_ocr_assets.py

Then commit the diff under `ocr_templates/`. Domain reference: auto_input/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_input.hud_layout import PROFILE_1920_1080  # noqa: E402
from auto_input.ocr import (  # noqa: E402
    BADGE_ANCHOR_FILES,
    SegConfig,
    badge_cell_from_surface,
    extract_glyph,
    load_value_cell,
    seg_for_scale,
    segment_chars,
    segment_red_digits,
    speed_limit_cell_from_surface,
)

# Known distance values per source screenshot — labels used to assign each
# segmented glyph the right digit. Right-most char is always 'm'; everything
# before it is a digit read left-to-right. Lives here (not in ocr.py) because
# it's only consumed at extraction time.
KNOWN_VALUES: dict[str, str] = {
    "running_en": "2930m",
    "running_ja": "2997m",
    "running_my_usage": "1071m",
    "stopping_en": "3834m",
    "stopping_ja": "3834m",
    "5 and 6": "3756m",
}

# Speed-limit screenshots: red-text digit cell. Filename → posted limit value as
# a digit string. The reader's `segment_red_digits` returns the bboxes; we save
# first-seen of each digit to ocr_templates/digits_red/<N>.png. Dark-text templates
# alone don't reliably match the bolder red font (8→4 / 6→4 confusion); dedicated
# red templates close the gap.
KNOWN_LIMIT_VALUES: dict[str, str] = {
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

SOURCES_DIR = Path(__file__).parent.parent / "_ocr_calibration"
SOURCES_DIR_1080P = Path(__file__).parent.parent / "_ocr_calibration_1080p"
OUT_DIR = Path(__file__).parent.parent / "ocr_templates"

# 1080p badge sources use different stems from the 1440p set:
#   stopping_ja (vs stopping_next_station at 1440p)
#   passing_ja  (vs passing_jp at 1440p)
BADGE_ANCHOR_FILES_1080P: dict[str, list[str]] = {
    "MOVING": ["running_en", "running_ja"],
    "STOPPED": ["stopping_en", "stopping_ja"],
    "PASSING": ["passing_en", "passing_ja"],
}

# 1080p speed-limit sources. Superset of KNOWN_LIMIT_VALUES (extra: 40, 50, 70, 95, 115).
# limit_110_2 is a backup shot of 110 — only used if limit_110 fails to segment.
KNOWN_LIMIT_VALUES_1080P: dict[str, str] = {
    # fmt: off
    "limit_30":    "30",
    "limit_35":    "35",
    "limit_40":    "40",
    "limit_45":    "45",
    "limit_50":    "50",
    "limit_55":    "55",
    "limit_65":    "65",
    "limit_70":    "70",
    "limit_75":    "75",
    "limit_80":    "80",
    "limit_85":    "85",
    "limit_90":    "90",
    "limit_95":    "95",
    "limit_100":   "100",
    "limit_105":   "105",
    "limit_110":   "110",
    "limit_110_2": "110",
    "limit_115":   "115",
    "limit_120":   "120",
    # fmt: on
}


def save_binary_glyph(glyph: np.ndarray, path: Path) -> None:
    """Save a binary 0/1 numpy array as a 0/255 grayscale PNG at native shape."""
    arr = (glyph * 255).astype(np.uint8)
    rgb = np.stack([arr, arr, arr], axis=-1)
    surf = pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))
    pygame.image.save(surf, str(path))


def save_anchor_crop(cell: np.ndarray, path: Path) -> None:
    """Save a (H, W, 3) RGB numpy array as a PNG at native shape."""
    rgb = np.transpose(cell, (1, 0, 2))  # back to pygame column-major
    surf = pygame.surfarray.make_surface(rgb)
    pygame.image.save(surf, str(path))


def _crop_cell_for_profile(surf: pygame.Surface, profile: object, cell_bbox: tuple) -> np.ndarray:
    """Crop an arbitrary HUD cell from a full-desktop surface using a ResolutionProfile.

    `cell_bbox` is HUD-relative (x, y, w, h), matching a ResolutionProfile cell field.
    """
    hx, hy, _, _ = profile.hud_bbox  # type: ignore[union-attr]
    vx, vy, vw, vh = cell_bbox
    cell = pygame.Surface((vw, vh))
    cell.blit(surf, (0, 0), area=pygame.Rect(hx + vx, hy + vy, vw, vh))
    arr = pygame.surfarray.array3d(cell)
    return np.transpose(arr, (1, 0, 2))


def _crop_badge_for_profile(surf: pygame.Surface, profile: object) -> np.ndarray:
    """Crop badge cell from a full-desktop surface using a ResolutionProfile."""
    return _crop_cell_for_profile(surf, profile, profile.badge_bbox)  # type: ignore[union-attr]


def extract_digits(sources_dir: Path, digits_dir: Path) -> dict[str, str]:
    """Walk KNOWN_VALUES, segment + save first-seen glyph per digit. Return digit->source-stem map."""
    glyphs: dict[str, np.ndarray] = {}
    digit_source: dict[str, str] = {}
    for stem, expected in KNOWN_VALUES.items():
        path = sources_dir / f"{stem}.png"
        if not path.exists():
            print(f"[skip] {stem}.png — not in {sources_dir.name}/")
            continue
        cell = load_value_cell(path)
        bboxes = segment_chars(cell)
        digit_str = expected.rstrip("m")
        if len(bboxes) != len(digit_str):
            print(f"[warn] {stem}: segmented {len(bboxes)} digits, expected {len(digit_str)} ({digit_str}) — skipping")
            continue
        for bbox, ch in zip(bboxes, digit_str):
            if ch not in glyphs:
                glyphs[ch] = extract_glyph(cell, bbox)
                digit_source[ch] = stem

    digits_dir.mkdir(parents=True, exist_ok=True)
    for ch, glyph in glyphs.items():
        out = digits_dir / f"{ch}.png"
        save_binary_glyph(glyph, out)
        print(f"[digit {ch}] {glyph.shape[1]}×{glyph.shape[0]} from {digit_source[ch]} -> {out.relative_to(OUT_DIR.parent)}")

    missing = sorted(set("0123456789") - glyphs.keys())
    if missing:
        print(f"\n[WARN] missing digits: {missing} — recapture a source screenshot containing them and re-run.")
    return digit_source


def extract_red_digits(
    sources_dir: Path,
    red_digits_dir: Path,
    known_limit_values: dict[str, str] | None = None,
    crop_fn=None,  # (pygame.Surface) -> np.ndarray; None = speed_limit_cell_from_surface
    seg: SegConfig | None = None,
) -> None:
    """Walk known_limit_values, segment each limit screenshot's red-text cell,
    label each glyph by position, save first-seen as a tight binary PNG."""
    if known_limit_values is None:
        known_limit_values = KNOWN_LIMIT_VALUES
    if crop_fn is None:
        crop_fn = speed_limit_cell_from_surface
    glyphs: dict[str, np.ndarray] = {}
    digit_source: dict[str, str] = {}
    for stem, expected in known_limit_values.items():
        path = sources_dir / f"{stem}.png"
        if not path.exists():
            print(f"[skip] {stem}.png — not in {sources_dir.name}/")
            continue
        cell = crop_fn(pygame.image.load(str(path)))
        red_mask, bboxes = segment_red_digits(cell, seg=seg)
        if len(bboxes) != len(expected):
            print(f"[warn] {stem}: segmented {len(bboxes)} digits, expected {len(expected)} ({expected}) — skipping")
            continue
        for bbox, ch in zip(bboxes, expected):
            if ch not in glyphs:
                x0, y0, x1, y1 = bbox
                glyphs[ch] = red_mask[y0:y1, x0:x1].astype(np.uint8)
                digit_source[ch] = stem

    red_digits_dir.mkdir(parents=True, exist_ok=True)
    for ch, glyph in glyphs.items():
        out = red_digits_dir / f"{ch}.png"
        save_binary_glyph(glyph, out)
        print(f"[red digit {ch}] {glyph.shape[1]}×{glyph.shape[0]} from {digit_source[ch]} -> {out.relative_to(OUT_DIR.parent)}")

    missing = sorted(set("0123456789") - glyphs.keys())
    if missing:
        print(f"\n[INFO] no red template yet for: {missing} — read_speed_limit falls back to dilated dark templates for those.")


def extract_badges(
    sources_dir: Path,
    badges_dir: Path,
    badge_anchor_files: dict[str, list[str]] | None = None,
    profile: object | None = None,
) -> None:
    """Crop badge cell from each anchor source; save as PNG.

    `badge_anchor_files` defaults to the 1440p BADGE_ANCHOR_FILES dict.
    `profile` selects per-resolution crop geometry; None uses the 1440p
    ``badge_cell_from_surface`` helper (hardcoded HUD_BBOX + BADGE_BBOX).
    """
    if badge_anchor_files is None:
        badge_anchor_files = BADGE_ANCHOR_FILES
    badges_dir.mkdir(parents=True, exist_ok=True)
    for state, stems in badge_anchor_files.items():
        for stem in stems:
            path = sources_dir / f"{stem}.png"
            if not path.exists():
                print(f"[skip] {stem}.png ({state}) — not in {sources_dir.name}/")
                continue
            surf = pygame.image.load(str(path))
            cell = _crop_badge_for_profile(surf, profile) if profile is not None else badge_cell_from_surface(surf)
            out = badges_dir / f"{stem}.png"
            save_anchor_crop(cell, out)
            print(f"[badge {state}/{stem}] {cell.shape[1]}×{cell.shape[0]} -> {out.relative_to(OUT_DIR.parent)}")


def main() -> int:
    pygame.init()
    if not SOURCES_DIR.exists():
        print(f"ERROR: {SOURCES_DIR} not found.")
        print("Re-capture reference screenshots into that folder before running this script.")
        print("See auto_input/README.md § Recalibration for the full list of expected files.")
        return 1

    print(f"Extracting from {SOURCES_DIR.name}/ -> {OUT_DIR.name}/\n")
    print("--- digit glyphs (dark) ---")
    extract_digits(SOURCES_DIR, OUT_DIR / "digits")
    print("\n--- digit glyphs (red, speed-limit) ---")
    extract_red_digits(SOURCES_DIR, OUT_DIR / "digits_red")
    print("\n--- badge anchors (1440p) ---")
    extract_badges(SOURCES_DIR, OUT_DIR / "badges")
    print("\n--- badge anchors (1080p) ---")
    if SOURCES_DIR_1080P.exists():
        extract_badges(
            SOURCES_DIR_1080P,
            OUT_DIR / "1080p" / "badges",
            badge_anchor_files=BADGE_ANCHOR_FILES_1080P,
            profile=PROFILE_1920_1080,
        )
    else:
        print(f"[skip] {SOURCES_DIR_1080P.name}/ not found — 1080p badges not extracted.")
    print("\n--- digit glyphs (red, 1080p speed-limit) ---")
    if SOURCES_DIR_1080P.exists():
        seg_1080 = seg_for_scale(0.75)
        extract_red_digits(
            SOURCES_DIR_1080P,
            OUT_DIR / "1080p" / "digits_red",
            known_limit_values=KNOWN_LIMIT_VALUES_1080P,
            crop_fn=lambda surf: _crop_cell_for_profile(surf, PROFILE_1920_1080, PROFILE_1920_1080.speed_limit_value_bbox),
            seg=seg_1080,
        )
    else:
        print(f"[skip] {SOURCES_DIR_1080P.name}/ not found — 1080p red digits not extracted.")
    print(f"\nDone. Commit the diff under {OUT_DIR.name}/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

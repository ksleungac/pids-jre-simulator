"""Extract OCR runtime assets from local-only source screenshots.

Two-pass extraction:
    1. **Digit glyphs** — for each KNOWN_VALUES screenshot, segment the distance
       cell, label each glyph by position, save first-seen as a tight binary PNG
       at `ocr_templates/digits/<N>.png`.
    2. **Badge anchors** — for each BADGE_ANCHOR_FILES screenshot, crop the
       BADGE_BBOX cell and save as `ocr_templates/badges/<stem>.png`.

Source screenshots live under `_ocr_calibration/` (gitignored — local-only,
~33 MB of full 2560×1440 desktop captures, only present when re-extracting).
The committed runtime assets under `ocr_templates/` are a few KB total.

Run after re-capturing reference screenshots (e.g. game HUD layout changed):
    uv run python data_tools/extract_ocr_assets.py

Then commit the diff under `ocr_templates/`. Domain reference: AUTO_INPUT.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from ocr import (  # noqa: E402
    BADGE_ANCHOR_FILES,
    badge_cell_from_surface,
    extract_glyph,
    load_value_cell,
    segment_chars,
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

SOURCES_DIR = Path(__file__).parent.parent / "_ocr_calibration"
OUT_DIR = Path(__file__).parent.parent / "ocr_templates"


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


def extract_badges(sources_dir: Path, badges_dir: Path) -> None:
    """Crop BADGE_BBOX from each anchor source; save as PNG."""
    badges_dir.mkdir(parents=True, exist_ok=True)
    for state, stems in BADGE_ANCHOR_FILES.items():
        for stem in stems:
            path = sources_dir / f"{stem}.png"
            if not path.exists():
                print(f"[skip] {stem}.png ({state}) — not in {sources_dir.name}/")
                continue
            surf = pygame.image.load(str(path))
            cell = badge_cell_from_surface(surf)
            out = badges_dir / f"{stem}.png"
            save_anchor_crop(cell, out)
            print(f"[badge {state}/{stem}] {cell.shape[1]}×{cell.shape[0]} -> {out.relative_to(OUT_DIR.parent)}")


def main() -> int:
    pygame.init()
    if not SOURCES_DIR.exists():
        print(f"ERROR: {SOURCES_DIR} not found.")
        print("Re-capture reference screenshots into that folder before running this script.")
        print("See AUTO_INPUT.md § Recalibration for the full list of expected files.")
        return 1

    print(f"Extracting from {SOURCES_DIR.name}/ -> {OUT_DIR.name}/\n")
    print("--- digit glyphs ---")
    extract_digits(SOURCES_DIR, OUT_DIR / "digits")
    print("\n--- badge anchors ---")
    extract_badges(SOURCES_DIR, OUT_DIR / "badges")
    print(f"\nDone. Commit the diff under {OUT_DIR.name}/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

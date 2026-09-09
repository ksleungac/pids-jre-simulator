# SPDX-License-Identifier: MIT
"""Which 1080p calibration frames carry a badge that was never an anchor?

KEEP — written 2026-09-09 as a one-off and cited the same day in `auto_input/README.md`
§ "Badge classification" as the survey behind the ±2 mean-RGB claim. Anyone re-checking that
claim, or re-labelling the badge fixtures by eye, runs this.


The six committed badge fixtures are byte-identical to the six anchors they are matched
against, so T3's badge assertions score a structural 0.00 (`critical_lessons.md` §10,
2026-08-19; named again in #143). A fixture from a DIFFERENT capture is the repair, and
`_ocr_calibration_1080p/` is local-only, so this survey only runs on the machine holding it.

Crops the badge cell from every 1080p calibration frame with production geometry, runs the
production classifier, and writes a labelled contact sheet the eye can label from. Output:
`screenshot_badge_sources.png` at repo root, plus a table on stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from app_paths import project_root  # noqa: E402
from auto_input.hud_layout import PROFILE_1920_1080  # noqa: E402
from auto_input.ocr import (  # noqa: E402
    BADGE_ANCHOR_FILES,
    classify_badge_state,
    crop_cell,
    load_badge_anchors,
)

SRC = project_root() / "_ocr_calibration_1080p"
OUT = project_root() / "screenshot_badge_sources.png"
ZOOM = 4
ROW_PAD = 6
LABEL_W = 430


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dir",
        type=Path,
        default=SRC,
        help="folder of 1920x1080 frames to survey (default: _ocr_calibration_1080p/). Used to "
        "run a transcode CONTROL: the same frames pushed through the 1080p->720p->1080p chain "
        "the reporter's YouTube upload went through, so blur can be told apart from levels.",
    )
    args = ap.parse_args()
    src = args.dir
    pygame.init()
    anchors = load_badge_anchors()
    anchor_stems = {s for stems in BADGE_ANCHOR_FILES.values() for s in stems}
    font = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Medium.otf"), 18)

    rows: list[tuple[str, np.ndarray, str]] = []
    print(f"{'frame':<26} {'anchor?':<8} {'state':<9} {'diff':>7}  {'via':<5} {'mean RGB':<21} vs nearest anchor")
    for path in sorted(src.glob("*.png")):
        stem = path.stem
        surf = pygame.image.load(str(path))
        if surf.get_width() != 1920 or surf.get_height() != 1080:
            print(f"{stem:<26} SKIP — {surf.get_width()}x{surf.get_height()}, not a 1080p desktop capture")
            continue
        cell = crop_cell(surf, PROFILE_1920_1080, PROFILE_1920_1080.badge_bbox)
        state, diff, via, _level = classify_badge_state(cell, anchors)
        is_anchor = stem in anchor_stems
        # Level check: the mean RGB of this cell against the nearest same-state anchor's.
        # A capture-side level lift (#137 / #140) shows up here as a positive delta on all
        # three channels while the classifier's own diff stays modest.
        mean = cell.reshape(-1, 3).mean(axis=0)
        delta = ""
        if state:
            near = min(anchors[state], key=lambda a: np.abs(cell.astype(int) - a.astype(int)).mean())
            d = mean - near.reshape(-1, 3).mean(axis=0)
            delta = f"  Δ {d[0]:+6.1f} {d[1]:+6.1f} {d[2]:+6.1f}"
        rgb = f"{mean[0]:6.1f} {mean[1]:6.1f} {mean[2]:6.1f}"
        print(f"{stem:<26} {'ANCHOR' if is_anchor else '-':<8} {str(state):<9} {diff:>7.2f}  {str(via):<5} {rgb}{delta}")
        rows.append((stem, cell, f"{'ANCHOR ' if is_anchor else ''}{state} diff={diff:.1f} via={via}"))

    if not rows:
        print("no rows")
        return 1

    ch, cw = rows[0][1].shape[:2]
    sheet_w = LABEL_W + cw * ZOOM
    sheet_h = (ch * ZOOM + ROW_PAD) * len(rows) + ROW_PAD
    sheet = pygame.Surface((sheet_w, sheet_h))
    sheet.fill((24, 24, 28))
    y = ROW_PAD
    for stem, cell, note in rows:
        surf = pygame.surfarray.make_surface(np.transpose(cell, (1, 0, 2)))
        big = pygame.transform.scale(surf, (cw * ZOOM, ch * ZOOM))
        sheet.blit(big, (LABEL_W, y))
        sheet.blit(font.render(stem, True, (240, 240, 240)), (8, y + 4))
        sheet.blit(font.render(note, True, (150, 170, 200)), (8, y + 26))
        y += ch * ZOOM + ROW_PAD
    pygame.image.save(sheet, str(OUT))
    print(f"\n-> {OUT}  ({sheet_w}x{sheet_h}, cell {cw}x{ch} at x{ZOOM})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

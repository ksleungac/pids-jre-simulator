# SPDX-License-Identifier: MIT
# TIER: T1 — glyph matching robustness (compare_tolerant / Templates.match)
"""Locks matching against the two capture degradations measured live at 1080p.

**Sub-pixel clipping.** The HUD number sits at a fractional x that jitters frame to
frame, so a digit's edge column sometimes falls under DARK_THRESHOLD and the glyph
binarizes 2-3 px narrower. Measured 2026-07-22: the same `4` scored 0.957 starting at
x=43 (w=16) and 0.746 starting at x=44 (w=13) — one pixel of start offset. Bare
`compare` squashes a full-width template onto the clipped glyph and misaligns it.

**Ink bleed / thinning.** A softer or sharper frame thickens or erodes strokes.

Oracle is the TEMPLATE SET degraded synthetically — self-contained, no fixture needed,
and each degradation is the real mechanism rather than a guess. Discriminating: drop the
morphology variants from compare_tolerant and `thin` fails; drop the window variants and
`thicken` fails. (Measured on 724 live glyphs, bare compare reads 92.8% of thinned
glyphs correctly; window-only reads 90.5% of thickened ones.)

NOTE margin is NOT asserted here, deliberately. Tolerance lifts runner-up scores along
with the winner, so the top-2 margin COMPRESSES even as accuracy improves — margin looks
like the stability metric and isn't. Accuracy under degradation is. See compare_tolerant.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from auto_input import ocr as O  # noqa: E402


def thicken(g):
    return O._dilate_binary(g.copy(), 1)


def thin(g):
    return O._erode1(g)


def clip_left(g):
    return g[:, 1:] if g.shape[1] > 6 else g


def clip_right(g):
    return g[:, :-1] if g.shape[1] > 6 else g


def scale(g, f):
    """Resample to a different size — the cross-resolution path (1440p tmpl vs 1080p glyph)."""
    return O._resize_nn(g, max(4, int(g.shape[0] * f)), max(3, int(g.shape[1] * f)))


def main():
    failures = []
    templates = O.build_templates()
    degradations = {
        "identity": lambda g: g,
        "thicken": thicken,
        "thin": thin,
        "clip-left": clip_left,
        "clip-right": clip_right,
        "scale-0.75": lambda g: scale(g, 0.75),
        "scale-0.75+thin": lambda g: thin(scale(g, 0.75)),
        "scale-0.75+thicken": lambda g: thicken(scale(g, 0.75)),
    }

    for name, fn in degradations.items():
        wrong = []
        for digit, tmpl in templates.glyphs.items():
            got, _ = templates.match(np.ascontiguousarray(fn(tmpl)))
            if got != digit:
                wrong.append(f"{digit}->{got}")
        if wrong:
            failures.append(f"  {name}: misread {len(wrong)}/10 — {', '.join(wrong)}")

    # The live clipped-4 case, end to end through the production reader.
    fx = ROOT / "_tests" / "fixtures" / "ocr" / "1080p" / "cells" / "speed__fragment_stub_48.png"
    if fx.exists():
        import pygame

        pygame.init()
        cell = pygame.surfarray.array3d(pygame.image.load(str(fx))).swapaxes(0, 1)
        seg = O.seg_for_scale(0.75)
        boxes = O.segment_chars(cell, max_gap=seg.speed_max_gap, stop_at_decimal=True, seg=seg)
        if boxes:
            g = O.extract_glyph(cell, boxes[0])
            ch, score = templates.match(g)
            if ch != "4":
                failures.append(f"  live clipped-4: matched '{ch}', expected '4'")
            if score < 0.85:
                failures.append(f"  live clipped-4: score {score:.3f} < 0.85 (bare compare scored it 0.699)")

    if failures:
        print("FAIL: glyph matching robustness")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: glyph matching robustness ({len(degradations)} degradations x 10 digits + live clipped-4)")


if __name__ == "__main__":
    main()

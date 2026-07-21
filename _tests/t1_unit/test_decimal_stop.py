# TIER: T1 — decimal-stop discrimination (segment_chars stop_at_decimal)
"""Locks the decimal-point scan against DIGIT-FRAGMENT false positives.

THE 2026-07-22 incident: on a degraded 1080p frame a `4` shed a 1-column, 3-row stub
1 px past its own body. That stub is dimensionally identical to a decimal point (short,
narrow, sitting low), so the scan took it as the decimal and cut the read after the first
digit — 48.3 became `4`, an 83 km/h/s apparent deceleration. Root cause was the 1-column
tolerance added 2026-07-20 to catch a faint dot (19.1 -> 191): widening the scan to accept
single-column runs is exactly what admits single-column stubs. `DECIMAL_MIN_GAP` is the
counterweight — a real decimal stands clear of its digit, a shed fragment abuts it.

Oracle is a COMMITTED CELL from the live misread (`speed__fragment_stub_48.png`), not a
synthetic construction — the failure depended on binarization detail no hand-built fixture
would reproduce.

The cell reads `48.3` — VERIFIED by rendering the glyphs (glyph 2 has two closed counters:
an `8`), NOT inferred from a neighbouring frame's filename. Inferring it is exactly how an
earlier version of this docstring claimed `47.7` and invented a non-existent "bled 7 reads
as 8" defect, which was then filed as an issue and written into the README before anyone
looked at the pixels. So `48` is the CORRECT post-fix read and the assertion is exact.
"""

import sys
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from auto_input import ocr as O  # noqa: E402

FIXTURES = ROOT / "_tests" / "fixtures" / "ocr"


def load_cell(res: str, stem: str):
    p = FIXTURES / res / "cells" / f"speed__{stem}.png"
    if not p.exists():
        return None
    return pygame.surfarray.array3d(pygame.image.load(str(p))).swapaxes(0, 1)


def main():
    pygame.init()
    failures = []
    templates = O.build_templates()

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # A. THE regression: the shed stub must NOT be taken as the decimal.
    seg = O.seg_for_scale(0.75)
    cell = load_cell("1080p", "fragment_stub_48")
    if cell is None:
        failures.append("  A: fixture speed__fragment_stub_48.png missing")
    else:
        boxes = O.segment_chars(cell, max_gap=seg.speed_max_gap, stop_at_decimal=True, seg=seg)
        val, raw, _ = O.read_speed(cell, templates, seg=seg)
        check(len(boxes) == 2, f"A stub-not-decimal: expected 2 digit boxes, got {len(boxes)} ({boxes})")
        check(val != 4, f"A stub-not-decimal: read truncated to {val} — the stub was taken as the decimal")
        check(val == 48, f"A stub-not-decimal: expected 48 (cell reads 48.3), got {val} (raw '{raw}')")

    # B. Real decimals must STILL be found — the guard must not blind the scan.
    #    Every committed speed cell keeps its own correct read.
    for res, scale in (("1440p", 1.0), ("1080p", 0.75)):
        s = O.seg_for_scale(scale)
        import json

        mf = json.loads((FIXTURES / res / "manifest.json").read_text(encoding="utf-8"))
        for c in mf["cells"]:
            if c["type"] != "speed":
                continue
            cl = load_cell(res, c["stem"])
            if cl is None:
                continue
            got, _, _ = O.read_speed(cl, templates, seg=s)
            check(got == c["expected"], f"B decimal-still-found: {res}/{c['stem']} read {got}, expected {c['expected']}")

    if failures:
        print("FAIL: decimal-stop discrimination")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: decimal-stop discrimination (A stub-not-decimal, B real decimals still found across both resolutions)")


if __name__ == "__main__":
    main()

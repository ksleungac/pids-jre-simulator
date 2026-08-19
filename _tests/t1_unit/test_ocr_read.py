# SPDX-License-Identifier: MIT
# TIER: T1 — the OCR reader: from a desktop size to a trusted number
"""What reading the game's HUD guarantees, at every step of the read.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). The four
sections are the pipeline in order, and each one's failure is invisible to the
next — a wrong answer at any stage is still a well-formed number:

  1. WHERE TO LOOK        — hud_layout.profile_for (capture geometry)
  2. WHICH GLYPH IT IS    — compare_tolerant / Templates.match, under degradation
  3. WHERE THE NUMBER ENDS — segment_chars stop_at_decimal (decimal vs digit fragment)
  4. IS THE VALUE POSSIBLE — _rectify_speed (value domain)

The reader's own environment is the thing that breaks it: a real user's capture is
softer than any produced here (`critical_lessons §7`), and the author's machine
cannot produce most of the resolutions section 1 covers. So sections 1 and 4 are
pure arithmetic pinned to literals, section 2 degrades the templates by the
mechanisms measured live, and section 3's oracle is a COMMITTED CELL from an
actual misread.

The decision layer that consumes these reads is T1 `test_auto_driver.py`; the
end-to-end read of committed HUD fixtures is T3 `test_ocr_reads.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pygame

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from auto_input import ocr as O  # noqa: E402
from auto_input.hud_layout import PROFILES, profile_for  # noqa: E402
from auto_input.ocr import _rectify_speed  # noqa: E402

FIXTURES = ROOT / "_tests" / "fixtures" / "ocr"

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append("  " + msg)


# ── 1. where to look ──────────────────────────────────────────────────────────
# Every auto-driven frame is cropped at whatever `profile_for` returns, so a wrong
# answer does not degrade — it reads a different part of the screen and the badge
# classifies nothing. The geometry is also unverifiable on the author's machine for
# any resolution their display cannot produce, which is why it is derived rather
# than measured, and why the derivation needs a test rather than a live drive per size.
#
# The letterbox arm exists because the game fits a 16:9 viewport into a taller desktop:
# measured on a 1920x1200 capture as exactly 60px of pure black top and bottom, HUD at
# (1650,75) — the 1080p geometry plus the bar. Sweeping the HUD origin +/-4px through the
# production badge matcher put a sharp minimum at dead centre (3.6 mean-abs-diff, against
# 18.7 one pixel out in x and 28.8 in y).
#
# Every expected tuple is pinned LITERALLY rather than derived from the module: a test that
# recomputes the arithmetic under test agrees with any mutation of it and stops
# discriminating (`principles.md` § "Test real logic, not ceremony").


# Mutation-proven x5: bar dropped · floor applied to the desktop instead of the fitted
# viewport · aspect gate `>=` instead of `>` · bar doubled · width%16 integrality guard
# removed. The author's box cannot produce most of these resolutions, so the derivation
# is the only thing testable at all — which is why the mutation list is recorded rather
# than left implicit (`principles.md` § "Discrimination decays").


def check_geometry(w: int, h: int, capture, hud, label: str) -> None:
    p = profile_for(w, h)
    if p is None:
        FAILURES.append(f"  {label}: {w}x{h} was refused, expected a profile")
        return
    check(p.capture_region == capture, f"{label}: {w}x{h} capture_region expected {capture}, got {p.capture_region}")
    check(p.hud_bbox == hud, f"{label}: {w}x{h} hud_bbox expected {hud}, got {p.hud_bbox}")
    # The capture must actually contain the HUD — the invariant a bar offset applied to one
    # and not the other would break, while both still looked individually plausible.
    cl, ct, cr, cb = p.capture_region
    hx, hy, hw, hh = p.hud_bbox
    check(
        cl <= hx and ct <= hy and hx + hw <= cr and hy + hh <= cb,
        f"{label}: {w}x{h} HUD {p.hud_bbox} is not inside capture {p.capture_region}",
    )
    check(
        p.hud_bbox_in_capture == (hx - cl, hy - ct, hw, hh),
        f"{label}: {w}x{h} hud_bbox_in_capture expected {(hx - cl, hy - ct, hw, hh)}, got {p.hud_bbox_in_capture}",
    )


def check_capture_geometry() -> None:
    # --- 16:9, zero bar. The two hand-calibrated baselines plus the two derived sizes. ---
    check_geometry(1920, 1080, (960, 0, 1920, 540), (1650, 15, 262, 360), "16:9")
    check_geometry(2560, 1440, (1280, 0, 2560, 720), (2200, 20, 350, 480), "16:9")
    check_geometry(3840, 2160, (1920, 0, 3840, 1080), (3300, 30, 525, 720), "16:9")
    check_geometry(3200, 1800, (1600, 0, 3200, 900), (2750, 25, 438, 600), "16:9 derived")

    # --- 16:10, letterboxed. 1920x1200 is the MEASURED one; the others follow the same fit. ---
    check_geometry(1920, 1200, (960, 60, 1920, 600), (1650, 75, 262, 360), "16:10 measured")
    check_geometry(2560, 1600, (1280, 80, 2560, 800), (2200, 100, 350, 480), "16:10")
    check_geometry(3840, 2400, (1920, 120, 3840, 1200), (3300, 150, 525, 720), "16:10")

    # The letterbox must move the geometry and nothing else: same desktop width, same HUD
    # size and x as the 16:9 profile of that width, y shifted by exactly the bar.
    p1080, p1200 = profile_for(1920, 1080), profile_for(1920, 1200)
    check(
        p1200.hud_bbox[0] == p1080.hud_bbox[0] and p1200.hud_bbox[2:] == p1080.hud_bbox[2:],
        f"letterbox must change only y: {p1080.hud_bbox} -> {p1200.hud_bbox}",
    )
    check(
        p1200.hud_bbox[1] - p1080.hud_bbox[1] == 60,
        f"1920x1200 bar must be 60px, got {p1200.hud_bbox[1] - p1080.hud_bbox[1]}",
    )

    # --- Refused. Each would otherwise read at a wrong screen position. ---
    for w, h, why in (
        (3440, 1440, "21:9 — wider than 16:9, pillarboxing unmeasured"),
        (2560, 1080, "21:9 — wider than 16:9"),
        (1600, 1200, "4:3 — fitted viewport is 900p, under the 1080p floor"),
        (1280, 1024, "5:4 — fitted viewport is 720p"),
        (1366, 768, "marginally WIDER than 16:9 — 1366*9 > 768*16, so the aspect gate takes it"),
        (1280, 720, "720p — exactly 16:9 but under the floor; this is the row that isolates it"),
        # Isolates the width%16 integrality guard: 1922 is NOT wider than 16:9 and its
        # fitted viewport is 1081, so it clears both other gates and only the divisibility
        # check can refuse it. Without this row, deleting that guard leaves the suite green
        # (`principles.md` § "a check that has never been observed to fail has not been
        # shown to work") — every other refusal here fails the floor for its own reason.
        (1922, 1300, "width has no integer 16:9 height — 1922*9/16 is not whole"),
    ):
        check(profile_for(w, h) is None, f"{w}x{h} must be refused ({why}), got a profile")

    # --- The observed-record dict must agree with the derivation it claims to record. ---
    for (w, h), p in PROFILES.items():
        check(p.verified, f"PROFILES[{w}x{h}] must carry verified=True — the dict is the observed record")
        check((p.desktop_w, p.desktop_h) == (w, h), f"PROFILES[{w}x{h}] carries desktop {p.desktop_w}x{p.desktop_h}")


# ── 2. which glyph it is ──────────────────────────────────────────────────────
# Matching against the two capture degradations measured live at 1080p.
#
# **Sub-pixel clipping.** The HUD number sits at a fractional x that jitters frame to
# frame, so a digit's edge column sometimes falls under DARK_THRESHOLD and the glyph
# binarizes 2-3 px narrower. Measured 2026-07-22: the same `4` scored 0.957 starting at
# x=43 (w=16) and 0.746 starting at x=44 (w=13) — one pixel of start offset. Bare
# `compare` squashes a full-width template onto the clipped glyph and misaligns it.
#
# **Ink bleed / thinning.** A softer or sharper frame thickens or erodes strokes.
#
# Oracle is the TEMPLATE SET degraded synthetically — self-contained, no fixture needed,
# and each degradation is the real mechanism rather than a guess. Discriminating: drop the
# morphology variants from compare_tolerant and `thin` fails; drop the window variants and
# `thicken` fails. (Measured on 724 live glyphs, bare compare reads 92.8% of thinned
# glyphs correctly; window-only reads 90.5% of thickened ones.)
#
# NOTE margin is NOT asserted here, deliberately. Tolerance lifts runner-up scores along
# with the winner, so the top-2 margin COMPRESSES even as accuracy improves — margin looks
# like the stability metric and isn't. Accuracy under degradation is. See compare_tolerant.


def thicken(g):
    return O._dilate_binary(g.copy(), 1)


def thin(g):
    return O._erode1(g)


def clip_left(g):
    return g[:, 1:] if g.shape[1] > 6 else g


def clip_right(g):
    return g[:, :-1] if g.shape[1] > 6 else g


def rescale(g, f):
    """Resample to a different size — the cross-resolution path (1440p tmpl vs 1080p glyph)."""
    return O._resize_nn(g, max(4, int(g.shape[0] * f)), max(3, int(g.shape[1] * f)))


DEGRADATIONS = {
    "identity": lambda g: g,
    "thicken": thicken,
    "thin": thin,
    "clip-left": clip_left,
    "clip-right": clip_right,
    "scale-0.75": lambda g: rescale(g, 0.75),
    "scale-0.75+thin": lambda g: thin(rescale(g, 0.75)),
    "scale-0.75+thicken": lambda g: thicken(rescale(g, 0.75)),
}


def load_cell(res: str, stem: str):
    p = FIXTURES / res / "cells" / f"speed__{stem}.png"
    if not p.exists():
        return None
    return pygame.surfarray.array3d(pygame.image.load(str(p))).swapaxes(0, 1)


def check_glyph_matching(templates) -> None:
    for name, fn in DEGRADATIONS.items():
        wrong = []
        for digit, tmpl in templates.glyphs.items():
            got, _ = templates.match(np.ascontiguousarray(fn(tmpl)))
            if got != digit:
                wrong.append(f"{digit}->{got}")
        if wrong:
            FAILURES.append(f"  {name}: misread {len(wrong)}/10 — {', '.join(wrong)}")

    # The live clipped-4 case, end to end through the production reader.
    cell = load_cell("1080p", "fragment_stub_48")
    if cell is not None:
        seg = O.seg_for_scale(0.75)
        boxes = O.segment_chars(cell, max_gap=seg.speed_max_gap, stop_at_decimal=True, seg=seg)
        if boxes:
            g = O.extract_glyph(cell, boxes[0])
            ch, score = templates.match(g)
            check(ch == "4", f"live clipped-4: matched '{ch}', expected '4'")
            check(score >= 0.85, f"live clipped-4: score {score:.3f} < 0.85 (bare compare scored it 0.699)")


# ── 3. where the number ends ──────────────────────────────────────────────────
# The decimal-point scan against DIGIT-FRAGMENT false positives.
#
# THE 2026-07-22 incident: on a degraded 1080p frame a `4` shed a 1-column, 3-row stub
# 1 px past its own body. That stub is dimensionally identical to a decimal point (short,
# narrow, sitting low), so the scan took it as the decimal and cut the read after the first
# digit — 48.3 became `4`, an 83 km/h/s apparent deceleration. Root cause was the 1-column
# tolerance added 2026-07-20 to catch a faint dot (19.1 -> 191): widening the scan to accept
# single-column runs is exactly what admits single-column stubs. `DECIMAL_MIN_GAP` is the
# counterweight — a real decimal stands clear of its digit, a shed fragment abuts it.
#
# Oracle is a COMMITTED CELL from the live misread (`speed__fragment_stub_48.png`), not a
# synthetic construction — the failure depended on binarization detail no hand-built fixture
# would reproduce.
#
# The cell reads `48.3` — VERIFIED by rendering the glyphs (glyph 2 has two closed counters:
# an `8`), NOT inferred from a neighbouring frame's filename. Inferring it is exactly how an
# earlier version of this docstring claimed `47.7` and invented a non-existent "bled 7 reads
# as 8" defect, which was then filed as an issue and written into the README before anyone
# looked at the pixels. So `48` is the CORRECT post-fix read and the assertion is exact.


def check_decimal_stop(templates) -> None:
    # A. THE regression: the shed stub must NOT be taken as the decimal.
    seg = O.seg_for_scale(0.75)
    cell = load_cell("1080p", "fragment_stub_48")
    if cell is None:
        FAILURES.append("  A: fixture speed__fragment_stub_48.png missing")
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
        mf = json.loads((FIXTURES / res / "manifest.json").read_text(encoding="utf-8"))
        for c in mf["cells"]:
            if c["type"] != "speed":
                continue
            cl = load_cell(res, c["stem"])
            if cl is None:
                continue
            got, _, _ = O.read_speed(cl, templates, seg=s)
            check(got == c["expected"], f"B decimal-still-found: {res}/{c['stem']} read {got}, expected {c['expected']}")


# ── 4. is the value possible ──────────────────────────────────────────────────
# `_rectify_speed(value)` — the speed value-domain hardening.
#
# Drivable top speed is 135 km/h; reads are accepted up to a 140 slack ceiling. The
# failure this rectifies: the speed reader's decimal-point detection fails, so the
# tenths digit concatenates onto the integer (72.7 → "727"). Because the game shows a
# single decimal place, the overshoot is always exactly one extra trailing digit, so
# `//10` recovers the integer part; a re-check against the ceiling drops genuine
# garbage to None. Real speeds — including the legit 3-digit 100–135 band — are ≤140
# and pass through untouched (so the T3 real-speed fixtures are unaffected).

# (raw_value, expected)
# fmt: off
RECTIFY_CASES = [
    (None, None),
    # In-range reads pass through unchanged.
    (0,    0),
    (72,   72),
    (99,   99),
    (100,  100),    # legit 3-digit speed
    (120,  120),
    (135,  135),    # drivable max
    (140,  140),    # ceiling inclusive
    # Decimal slip — one tenths digit appended; //10 recovers it.
    (727,  72),     # 72.7 → "727"
    (999,  99),     # 99.9 → "999"
    (1350, 135),    # 135.0 → "1350"
    (1358, 135),    # 135.8 → "1358"
    (200,  20),     # 20.0 → "200"
    (141,  14),     # 14.1 → "141" (just over ceiling)
    # Genuine garbage — still out of range after one drop → dropped to None.
    (9999, None),   # //10 = 999, still > 140
    (14000, None),  # //10 = 1400, still > 140
]
# fmt: on


def check_rectify() -> None:
    for value, expected in RECTIFY_CASES:
        got = _rectify_speed(value)
        check(got == expected, f"_rectify_speed({value!r}) = {got!r}, expected {expected!r}")


def main() -> int:
    pygame.init()
    templates = O.build_templates()

    check_capture_geometry()
    check_glyph_matching(templates)
    check_decimal_stop(templates)
    check_rectify()

    if FAILURES:
        print("FAIL: OCR read")
        print("\n".join(FAILURES))
        return 1
    print(
        f"PASS: OCR read (capture geometry 16:9 + 16:10 letterbox + 8 refusals; "
        f"{len(DEGRADATIONS)} glyph degradations x 10 digits + live clipped-4; "
        f"stub-not-decimal + decimals still found both resolutions; "
        f"{len(RECTIFY_CASES)} speed-domain cases)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

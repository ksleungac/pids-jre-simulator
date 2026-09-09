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


# ── 5. is the badge still readable when the LEVELS move ──────────────────────
# `classify_badge_state` compares absolute RGB, so a capture whose levels are lifted
# scores far past BADGE_DIFF_REJECT while the badge is perfectly legible and every digit
# reader on the same frame is unaffected. That is #137's signature: badge read 6-45 % at
# a diff median of 70-80, against a documented 9.8, with speed at 87-99 % on the same
# frames. The shape-only second pass exists for exactly that, and this section pins the
# three things that make it safe to have.
#
# The oracle CANNOT be `_tests/fixtures/ocr/*/cells/badge__*.png`: all six are
# byte-identical to the six anchors they are matched against, so they score 0.00 and are
# the artifact compared to itself (critical_lessons.md §10). Shifted anchors are honest
# here for the same reason a shifted anchor is honest anywhere — the transform is the
# subject, not the pixels.


def _srgb_to_lin(v):
    v = v / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(v):
    v = np.clip(v, 0.0, 1.0)
    return 255.0 * np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def hdr_paperwhite(a, paper):
    """SDR content composited at a paper-white above 80 nits, then tonemapped back down.

    Windows scales SDR content into the scRGB swap chain by paper-white/80; anything
    downstream treating the result as ordinary SDR sees a lifted curve with a compressed
    top end. Done in LINEAR light because that is where the scaling happens — an offset on
    encoded values is a different curve and puts the shadows somewhere else.
    """
    lin = _srgb_to_lin(a.astype(float)) * (paper / 80.0)
    return _lin_to_srgb(lin / (1.0 + lin))  # Reinhard shoulder, the tonemap back


def channel_cast(a, rg, gg, bg):
    """Per-channel gain — a colour cast, which no single offset or gain can express."""
    return np.clip(a.astype(float) * np.array([rg, gg, bg]), 0, 255)


def reshade_grade(a, lift, gain, gamma, sat):
    """Lift / gain / gamma plus a saturation push — the shape of a common ReShade preset.

    ReShade grades inside the game's swap chain, so the desktop composites the graded
    frame and DDA hands dxcam the graded frame: the OCR never sees the game's own pixels.
    Saturation is in here because it is channel-relative, which a per-array affine
    normalisation is not guaranteed to survive.
    """
    v = np.clip(a.astype(float) * gain + lift, 0, 255)
    v = 255.0 * np.power(v / 255.0, gamma)
    grey = v.mean(axis=2, keepdims=True)
    return np.clip(grey + (v - grey) * sat, 0, 255)


# The first six are analytic: they name a magnitude, which is how the reporter's badge_diff
# medians were read. The last four are the shapes a real pipeline applies, and neither is an
# affine on encoded values. Every `raw_owns` flag below is MEASURED per subject rather than
# assumed — `_dev_scripts/_badge_colour_shift.py` prints the min/max the flag has to hold for.
BADGE_SHIFTS = {
    # name: (transform, must the RAW pass still own it?)
    "unshifted": (lambda a: a, True),
    "offset +40": (lambda a: np.clip(a.astype(float) + 40, 0, 255), True),
    "offset +90": (lambda a: np.clip(a.astype(float) + 90, 0, 255), False),
    "offset +120": (lambda a: np.clip(a.astype(float) + 120, 0, 255), False),
    "gain x2.0": (lambda a: np.clip(a.astype(float) * 2.0, 0, 255), False),
    "gamma 0.25": (lambda a: 255.0 * np.power(np.clip(a.astype(float), 0, 255) / 255.0, 0.25), False),
    # HDR at 240 nits paper-white is the Windows default and raw absorbs it with room to
    # spare; at 400 it is still raw's, at 42.7-47.8. That second one is the useful pin —
    # the raw pass survives an HDR desktop, so HDR alone is not what blinded #137.
    "hdr paper 240": (lambda a: hdr_paperwhite(a, 240.0), True),
    "hdr paper 400": (lambda a: hdr_paperwhite(a, 400.0), True),
    # An ordinary preset lands at 46.7-49.0 — inside the reject by one point. Pinned to say
    # how little headroom raw has left, so a change that eats that point is visible here
    # rather than on a user's drive.
    "reshade mild": (lambda a: reshade_grade(a, 18.0, 1.25, 0.9, 1.35), True),
    "reshade strong": (lambda a: reshade_grade(a, 40.0, 1.5, 0.8, 1.6), False),
    # PER-CHANNEL casts. These are the axis the flattened NCC could not survive — ravelling
    # RGB into one vector cancels `a*v + b` only when `a` is common to all three. A cool
    # cast turned green MOVING/STOPPED into blue and they matched PASSING, 2 of 6 correct.
    # `_badge_ncc_distance` correlates LUMINANCE for this reason, so these must stay 6/6.
    # Both are past what any display applies; they are here as the shape, not the magnitude.
    # warm and cool STRADDLE the reject at these gains (49.2-61.6 and 47.5-62.2 across the
    # seven subjects), so neither pass owns them and `raw_owns=None` asserts the outcome
    # only. Pinning either way would be a guess, and moving the gains until they stopped
    # straddling would delete the most realistic rung on the axis.
    "warm cast": (lambda a: channel_cast(a, 2.2, 1.0, 0.4), None),
    "cool cast": (lambda a: channel_cast(a, 0.4, 1.0, 2.2), None),
    "green pull": (lambda a: channel_cast(a, 1.0, 3.5, 1.0), True),
}

# The one committed badge cell that was never an anchor: cut from a reporter's capture, so
# it starts at the ~12 of ordinary mismatch a real read carries instead of a shifted
# anchor's 0. Every shift above runs over it as well, which is what stops this section from
# being entirely the artifact compared to itself.
NONANCHOR_BADGE = ROOT / "_tests" / "fixtures" / "ocr" / "1080p" / "cells" / "badge__reporter_slip_lowspeed.png"


def badge_garbage(shape):
    rng = np.random.default_rng(0)
    return {
        "black": np.zeros(shape, np.uint8),
        "white": np.full(shape, 255, np.uint8),
        "uniform 128": np.full(shape, 128, np.uint8),
        "uniform noise": rng.integers(0, 256, shape, dtype=np.uint8),
        "dark noise": rng.integers(0, 60, shape, dtype=np.uint8),
        "h-gradient": np.tile(np.linspace(0, 255, shape[1], dtype=np.uint8)[None, :, None], (shape[0], 1, 3)),
    }


# ── 6. the ink/background split, and where its clamp stops working ───────────
# `_cell_dark_threshold`'s clamp is ABSOLUTE (`[55, 100]`), so it is a bound in levels on a
# quantity that scales with the capture. This section pins both halves: the split it gets
# right, and the CEILING it hits — as current behaviour, dated, so the gap is visible rather
# than latent, the same way the flat-grey badge case is pinned in § 5.
#
# The oracle is synthetic, not a fixture: the claim is about the arithmetic across ink/bg
# pairs, and a fixture pins one pair. A relative clamp that satisfies the commented-out
# ideal below was built on 2026-09-09 and reverted — it passed here and on the synthetic
# shift ramp, and cost 341 of 1962 real 1440p frames their speed decimal. Do not re-land it
# without replaying `ocr_observe.py --replay`; see the constants' own comment and #89.


def check_dark_threshold() -> None:
    seg = O.seg_for_scale(1.0)
    shape = (55, 230, 3)

    def synth(ink: int, bg: int) -> np.ndarray:
        """A cell with real text-like structure at a stated ink/background pair."""
        cell = np.full(shape, bg, np.uint8)
        cell[18:48, 20:60] = ink
        cell[18:48, 80:120] = ink
        return cell

    # Where the clamp does not bind, the split lands between ink and background.
    for ink, bg in ((20, 200), (0, 90), (60, 140)):
        thr = O._cell_dark_threshold(synth(ink, bg), seg)
        check(ink < thr < bg, f"dark threshold for ink={ink} bg={bg} was {thr:.1f}, must sit strictly between")

    # KNOWN GAP, pinned as current behaviour. A bright capture's ink sits above the ceiling,
    # so the threshold stops separating and every glyph reads as background — this is the
    # mechanism behind #89's silent digit drops. When this assertion flips, the ceiling has
    # been fixed and the corpus replay is what must sign it off.
    for ink, bg in ((110, 255), (150, 255)):
        thr = O._cell_dark_threshold(synth(ink, bg), seg)
        check(thr == float(O.OTSU_CLAMP_HI), f"known gap: ink={ink} bg={bg} should pin at the ceiling, got {thr:.1f}")

    # A near-uniform band has no split to find; the contrast guard must take it, not Otsu.
    for bg in (10, 160, 240):
        thr = O._cell_dark_threshold(np.full(shape, bg, np.uint8), seg)
        check(thr == float(O.DARK_THRESHOLD), f"uniform {bg} must fall back to DARK_THRESHOLD, got {thr:.1f}")


def check_badge_levels() -> None:
    anchors = O.load_badge_anchors(ROOT / "ocr_templates" / "badges")
    n = sum(len(v) for v in anchors.values())
    check(n == 6, f"expected 6 badge anchors on disk, got {n}")
    if n == 0:
        return

    subjects = [(st, a) for st, arrs in anchors.items() for a in arrs]
    check(NONANCHOR_BADGE.exists(), f"non-anchor badge fixture missing: {NONANCHOR_BADGE.name}")
    if NONANCHOR_BADGE.exists():
        arr = pygame.surfarray.array3d(pygame.image.load(str(NONANCHOR_BADGE))).swapaxes(0, 1)
        subjects.append(("MOVING", arr))

    for name, (fn, raw_owns) in BADGE_SHIFTS.items():
        for true_state, a in subjects:
            cell = fn(a).astype(np.uint8)
            state, diff, via, level = O.classify_badge_state(cell, anchors)
            check(state == true_state, f"badge {name}: {true_state} classified as {state}")
            # NON-DEGRADATION. Anything the raw pass owns today it must still own, and
            # the fallback must not be reached. This is the whole safety argument for
            # the change: it is a property of the ORDER, so it holds without needing
            # real shifted cells to measure against.
            if raw_owns is None:
                # The transform straddles the reject across subjects, so which pass answers
                # is a property of the subject rather than of the transform. Only the
                # outcome is assertable: a state came back, and `diff` is still the raw one.
                check(via in ("raw", "ncc"), f"badge {name}: refused outright, via={via} diff={diff:.1f}")
            elif raw_owns:
                check(via == "raw", f"badge {name}: must stay on the raw pass, went via {via}")
                check(diff <= O.BADGE_DIFF_REJECT, f"badge {name}: raw diff {diff:.1f} over reject")
            else:
                check(via == "ncc", f"badge {name}: raw should have refused; via={via} diff={diff:.1f}")
                # `diff` stays the RAW number whichever pass answered, so an old drive
                # log's badge_diff still means the same thing after this change.
                check(diff > O.BADGE_DIFF_REJECT, f"badge {name}: reported diff {diff:.1f} should be the raw one")

    # The fallback must not RESCUE anything the raw pass refused, or every frame raw
    # rejects lands on a looser test — `principles.md § "A fallback must be stricter than
    # the path it replaces"`. Stated as "raw's refusals stay refused" rather than "all
    # garbage is refused", because the latter is FALSE today and not of this change's
    # making: raw accepts a flat mid-grey cell at 44.2, under its own 50. That weakness is
    # pinned below rather than quietly fixed — fixing it would change what production does
    # on frames it currently classifies, which is the one thing this change must not do.
    shape = next(iter(anchors.values()))[0].shape
    for name, g in badge_garbage(shape).items():
        state, diff, via, _level = O.classify_badge_state(g, anchors)
        if diff > O.BADGE_DIFF_REJECT:
            check(
                state is None and via is None,
                f"badge garbage {name}: raw refused (diff {diff:.1f}) but fallback rescued it as {state}",
            )
        else:
            check(via == "raw", f"badge garbage {name}: raw accepted at {diff:.1f}, so via must be raw, got {via}")

    # The one input raw accepts and should not. Pinned as CURRENT BEHAVIOUR so the gap is
    # visible and dated rather than latent; the shape-only metric scores it 100.0, so
    # whenever the raw pass is retired this assertion is what flips.
    flat = np.full(shape, 128, np.uint8)
    _state, flat_diff, flat_via, _flat_level = O.classify_badge_state(flat, anchors)
    check(flat_via == "raw", "known gap: a flat mid-grey cell is accepted by the RAW pass (2026-09-08)")
    check(
        flat_diff < O.BADGE_DIFF_REJECT,
        f"known gap: flat-grey raw diff was {flat_diff:.1f}, expected under {O.BADGE_DIFF_REJECT}",
    )
    worst_ncc = min(O._badge_ncc_distance(flat, a) for arrs in anchors.values() for a in arrs)
    check(worst_ncc > O.BADGE_NCC_REJECT, f"the shape-only metric must refuse flat grey; scored {worst_ncc:.1f}")


def main() -> int:
    pygame.init()
    templates = O.build_templates()

    check_capture_geometry()
    check_glyph_matching(templates)
    check_decimal_stop(templates)
    check_rectify()
    check_dark_threshold()
    check_badge_levels()

    if FAILURES:
        print("FAIL: OCR read")
        print("\n".join(FAILURES))
        return 1
    print(
        f"PASS: OCR read (capture geometry 16:9 + 16:10 letterbox + 8 refusals; "
        f"{len(DEGRADATIONS)} glyph degradations x 10 digits + live clipped-4; "
        f"stub-not-decimal + decimals still found both resolutions; "
        f"{len(RECTIFY_CASES)} speed-domain cases; "
        f"dark-threshold split over 3 ink/bg pairs + 2 pinned ceiling gaps + 3 uniform; "
        f"badge levels {len(BADGE_SHIFTS)} shifts x 7 subjects (6 anchors + 1 non-anchor cell) "
        f"+ 6 garbage refusals)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

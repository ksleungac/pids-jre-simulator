"""HUD region constants for JR EAST Train Simulator.

Single source of truth for cell positions. Cell coordinates are HUD-relative
(within the 350x480 HUD crop), not screen-relative — this way only HUD_BBOX
needs to change for other resolutions.

Resolution support
------------------
Two profiles are defined: 2560×1440 (production baseline) and 1920×1080.
The ``PROFILES`` dict maps ``(desktop_w, desktop_h)`` to a ``ResolutionProfile``
that carries all per-resolution bbox constants + template directory fragments.

``AutoDriver`` uses ``PROFILES`` to select the correct profile at startup via a
full-frame resolution probe. The existing flat module-level constants (``HUD_BBOX``,
``BADGE_BBOX``, etc.) remain unchanged for backward compatibility with the
``*_from_surface`` helpers in ``ocr.py`` (1b dev-tool path) and the calibration
extractor in ``_dev_scripts/extract_ocr_assets.py`` — both are 1440p-only tools.

``DOWNSCALE_PROFILE`` is the alternative to all of that (PoC, ``main.py --downscale-ocr``):
one 1080p model that every larger capture is downscaled into, so a new resolution needs no
profile and no templates. See ``sampling.downscale_hud``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ResolutionProfile:
    """All per-resolution HUD constants needed by AutoDriver.

    Bbox tuples: capture_region is (left, top, right, bottom) for dxcam.
    All others are (x, y, w, h). Cell bboxes (badge_bbox, *_value_bbox) are
    HUD-relative (origin = top-left corner of hud_bbox_in_capture).
    """

    desktop_w: int
    desktop_h: int
    # dxcam capture region — restricts per-frame capture to the quadrant
    # containing the HUD (~75% less work than full-desktop grab).
    capture_region: tuple[int, int, int, int]
    # Full HUD bounding box in desktop coordinates.
    hud_bbox: tuple[int, int, int, int]
    # HUD bbox translated into capture_region-relative coordinates.
    # Derived from hud_bbox - capture_region origin; never authored separately.
    hud_bbox_in_capture: tuple[int, int, int, int]
    # HUD-relative cell bboxes — match the corresponding flat module constants
    # at 1440p; scaled by 0.75 at 1080p.
    badge_bbox: tuple[int, int, int, int]
    distance_value_bbox: tuple[int, int, int, int]
    speed_value_bbox: tuple[int, int, int, int]
    speed_limit_value_bbox: tuple[int, int, int, int]
    # Subdirectory under ocr_templates/ for digit glyph PNGs.
    # Empty string = root ocr_templates/digits/ (1440p).
    # "1080p" = ocr_templates/1080p/digits/ (1080p).
    templates_subdir: str
    # Subdirectory under ocr_templates/ for badge anchor PNGs.
    badges_subdir: str
    # Scale relative to 1440p. Used by seg_for_scale() in ocr.py to derive
    # per-resolution segmentation thresholds.
    scale: float
    # True = this geometry has been confirmed on a live drive at least once.
    # False = interpolated from the 16:9 fractions by profile_for(). Interpolated
    # geometry is expected to be right (the HUD scales without reflow) but nobody
    # has watched it read, so it is announced at startup and bars --legacy-ocr,
    # which would need a native template set that only a tested resolution has.
    verified: bool = True


# ─── 2560×1440 profile (production baseline) ──────────────────────────────────

# fmt: off
_HUD_BBOX_2560_1440         = (2200,  20, 350, 480)
_HUD_BBOX_2560_1440_REF_H   = 1440   # the height every interpolated profile scales FROM
_CAPTURE_REGION_2560_1440   = (1280,   0, 2560, 720)
_HUD_IN_CAPTURE_2560_1440   = (
    _HUD_BBOX_2560_1440[0] - _CAPTURE_REGION_2560_1440[0],
    _HUD_BBOX_2560_1440[1] - _CAPTURE_REGION_2560_1440[1],
    _HUD_BBOX_2560_1440[2],
    _HUD_BBOX_2560_1440[3],
)

PROFILE_2560_1440 = ResolutionProfile(
    desktop_w                = 2560,
    desktop_h                = 1440,
    capture_region           = _CAPTURE_REGION_2560_1440,
    hud_bbox                 = _HUD_BBOX_2560_1440,
    hud_bbox_in_capture      = _HUD_IN_CAPTURE_2560_1440,
    badge_bbox               = ( 29, 122, 111,  40),
    distance_value_bbox      = (120, 314, 230,  55),
    speed_value_bbox         = (120, 165, 230,  55),
    speed_limit_value_bbox   = (120, 215, 230,  55),
    templates_subdir         = "",
    badges_subdir            = "badges",
    scale                    = 1.0,
)
# fmt: on


# ─── 1920×1080 profile (0.75× proportional scale) ─────────────────────────────


def _scale_bbox(bbox: tuple[int, int, int, int], s: float) -> tuple[int, int, int, int]:
    return tuple(int(round(v * s)) for v in bbox)  # type: ignore[return-value]


_S = 0.75
_HUD_BBOX_1920_1080 = _scale_bbox(_HUD_BBOX_2560_1440, _S)
# Capture right half of 1920×1080 desktop (same proportional fraction as 1440p).
_CAPTURE_REGION_1920_1080 = (960, 0, 1920, 540)
_HUD_IN_CAPTURE_1920_1080 = (
    _HUD_BBOX_1920_1080[0] - _CAPTURE_REGION_1920_1080[0],
    _HUD_BBOX_1920_1080[1] - _CAPTURE_REGION_1920_1080[1],
    _HUD_BBOX_1920_1080[2],
    _HUD_BBOX_1920_1080[3],
)

# fmt: off
PROFILE_1920_1080 = ResolutionProfile(
    desktop_w                = 1920,
    desktop_h                = 1080,
    capture_region           = _CAPTURE_REGION_1920_1080,
    hud_bbox                 = _HUD_BBOX_1920_1080,
    hud_bbox_in_capture      = _HUD_IN_CAPTURE_1920_1080,
    badge_bbox               = _scale_bbox(( 29, 122, 111,  40), _S),
    distance_value_bbox      = _scale_bbox((120, 314, 230,  55), _S),
    speed_value_bbox         = _scale_bbox((120, 165, 230,  55), _S),
    speed_limit_value_bbox   = _scale_bbox((120, 215, 230,  55), _S),
    templates_subdir         = "1080p",
    badges_subdir            = "1080p/badges",
    scale                    = _S,
)
# fmt: on

# ─── Interpolating a profile for any 16:9 resolution ──────────────────────────
# The two measured profiles agree to the digit on where the HUD sits as a FRACTION of the
# screen — x/W = 0.859375, y/H = 0.013889, h/H = 1/3 — and both capture regions are exactly
# (W/2, 0, W, H/2). The game scales the HUD without reflow, so any other 16:9 size lands on
# the same fractions and its geometry can be derived rather than measured.
#
# Scope, deliberately narrow: 16:9 only, 1080p or larger. A different aspect ratio may well
# move the HUD and nobody has checked, so guessing there would be inventing a fact. Below
# 1080p is out of scope while every real target is >= 1080p.
_MIN_INTERPOLATED_H = 1080


def _interpolate_profile(desktop_w: int, desktop_h: int) -> ResolutionProfile:
    """Derive a profile from the 16:9 fractions. Caller checks scope first."""
    s = desktop_h / _HUD_BBOX_2560_1440_REF_H
    hud = _scale_bbox(_HUD_BBOX_2560_1440, s)
    capture = (desktop_w // 2, 0, desktop_w, desktop_h // 2)
    return ResolutionProfile(
        desktop_w=desktop_w,
        desktop_h=desktop_h,
        capture_region=capture,
        hud_bbox=hud,
        hud_bbox_in_capture=(hud[0] - capture[0], hud[1] - capture[1], hud[2], hud[3]),
        badge_bbox=_scale_bbox((29, 122, 111, 40), s),
        distance_value_bbox=_scale_bbox((120, 314, 230, 55), s),
        speed_value_bbox=_scale_bbox((120, 165, 230, 55), s),
        speed_limit_value_bbox=_scale_bbox((120, 215, 230, 55), s),
        # Unused on the downscale path (the 1080p model owns the cell bboxes and templates).
        # A resolution with no native template set also has --legacy-ocr barred, via verified.
        templates_subdir="",
        badges_subdir="badges",
        scale=s,
        verified=False,
    )


# Geometries CONFIRMED ON A LIVE DRIVE. Absence is not a capability limit — any other 16:9
# desktop >= 1080p is interpolated. Add an entry once a resolution has actually been driven,
# so the dict stays a record of what was tested rather than what is possible.
#
# 4K is the interpolated geometry marked as tested — it derives to capture (1920,0,3840,1080)
# and HUD (3300,30,525,720), so this entry adds no new numbers, only the claim that someone
# watched it read. `replace` rather than a hand-authored literal so the arithmetic has exactly
# one home and a promoted profile can never drift from what interpolation would have produced.
PROFILES: dict[tuple[int, int], ResolutionProfile] = {
    (3840, 2160): replace(_interpolate_profile(3840, 2160), verified=True),
    (2560, 1440): PROFILE_2560_1440,
    (1920, 1080): PROFILE_1920_1080,
}


def profile_for(desktop_w: int, desktop_h: int) -> ResolutionProfile | None:
    """The profile for a desktop size: the tested one if it exists, else interpolated.

    Returns None when the size is outside the interpolation scope — the caller should treat
    that as fatal rather than reading with wrong geometry. See auto_input/README.md
    § "What a profile means, and what gets interpolated".
    """
    tested = PROFILES.get((desktop_w, desktop_h))
    if tested is not None:
        return tested
    if desktop_w * 9 != desktop_h * 16 or desktop_h < _MIN_INTERPOLATED_H:
        return None
    return _interpolate_profile(desktop_w, desktop_h)


# ─── The one 1080p model every resolution downscales into ─────────────────────
# Per-resolution profiles cost a calibration round each: capture screenshots, hand-author
# a ResolutionProfile, re-extract templates. Instead build ONE model at 1080p and downscale
# every larger capture into it — one template set, one SegConfig, any desktop resolution.
#
# 1080p because every real target is >= 1080p, so the resize is always a DOWNSCALE.
# Upscaling would invent detail; rescaling a TEMPLATE was the earlier wrong direction.
#
# hud_bbox_in_capture is (0, 0, w, h) because a downscaled frame IS the HUD — there is no
# surrounding capture region left to offset from. Cell bboxes are HUD-relative already, so
# they carry over from the 1080p profile untouched.
DOWNSCALE_PROFILE = replace(
    PROFILE_1920_1080,
    hud_bbox_in_capture=(0, 0, PROFILE_1920_1080.hud_bbox_in_capture[2], PROFILE_1920_1080.hud_bbox_in_capture[3]),
)


# ─── Flat constants (1440p) — backward compat ─────────────────────────────────
# Consumed by crop_cell_from_surface / *_from_surface helpers in ocr.py (1b
# dev-tool path) and extract_ocr_assets.py. These are 1440p-only tools; do not
# update them when adding new resolution profiles.

# dxcam capture region (left, top, right, bottom) — matches dxcam.grab(region=)
# signature. Top-right quadrant of 2560×1440 desktop; HUD lives entirely inside
# this quadrant. Restricting capture to this region cuts dxcam's per-frame work
# by ~75% versus full-desktop grabs. Production OCR path uses this; 1b dev tool
# (`_dev_scripts/ocr_observe.py`) uses the same region grab as production against the
# canonical HUD_BBOX coordinates below.
CAPTURE_REGION_2560_1440 = _CAPTURE_REGION_2560_1440

# Full HUD bounding box on the 2560x1440 game window (x, y, w, h) — canonical
# desktop-coordinate reference. Used by the *_from_surface helpers (1b path) and
# the calibration extractor.
HUD_BBOX = _HUD_BBOX_2560_1440

# HUD bbox translated into CAPTURE_REGION_2560_1440-relative coordinates.
# Production path (`auto_input/driver.py:_crop_cell`) consumes this against the
# region-grabbed frame. Derived, not authored — change CAPTURE_REGION or
# HUD_BBOX and this updates automatically.
HUD_BBOX_IN_CAPTURE = _HUD_IN_CAPTURE_2560_1440

# Cells within the HUD crop (HUD-relative coordinates)
# Value cells contain the right-aligned numeric+unit text only (label excluded).
DISTANCE_VALUE_BBOX = (120, 314, 230, 55)
SPEED_VALUE_BBOX = (120, 165, 230, 55)
# Speed-limit (最高速度) row — red digits + dark "km/h" suffix. Sits between speed
# and distance rows. Reader uses red color mask; suffix is dark so excluded by the mask.
SPEED_LIMIT_VALUE_BBOX = (120, 215, 230, 55)
# Badge area (Next/次停車駅 vs Stopping at/停車中). Same green pentagon shape across states;
# only the text inside differs. Classified via pixel-diff against anchor templates.
# Left + top edges trimmed off the original cell's scenery bleed-through zone (translucent
# HUD bg over varying scene): the leftmost ~13 px and top ~5 px were pure noise outside
# the pentagon's body. The trim point sits where the pentagon's left curve / top edge
# begins, keeping all text content in-frame.
BADGE_BBOX = (29, 122, 111, 40)

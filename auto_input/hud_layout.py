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
"""

from __future__ import annotations

from dataclasses import dataclass


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


# ─── 2560×1440 profile (production baseline) ──────────────────────────────────

# fmt: off
_HUD_BBOX_2560_1440         = (2200,  20, 350, 480)
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

# All supported resolutions. AutoDriver probes desktop size at startup and
# looks up here; FATAL if not found.
PROFILES: dict[tuple[int, int], ResolutionProfile] = {
    (2560, 1440): PROFILE_2560_1440,
    (1920, 1080): PROFILE_1920_1080,
}


# ─── Flat constants (1440p) — backward compat ─────────────────────────────────
# Consumed by crop_cell_from_surface / *_from_surface helpers in ocr.py (1b
# dev-tool path) and extract_ocr_assets.py. These are 1440p-only tools; do not
# update them when adding new resolution profiles.

# dxcam capture region (left, top, right, bottom) — matches dxcam.grab(region=)
# signature. Top-right quadrant of 2560×1440 desktop; HUD lives entirely inside
# this quadrant. Restricting capture to this region cuts dxcam's per-frame work
# by ~75% versus full-desktop grabs. Production OCR path uses this; 1b dev tool
# (`_dev_scripts/capture_game.py`) still uses full-desktop grabs against the
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

# SPDX-License-Identifier: MIT
"""E235-0 series Lower LCD display implementation.

Provides a circular full-route renderer (Yamanote racetrack layout) and a
`LowerDisplay` manager that swaps the full-route slot's renderer for the
circular variant on Yamanote routes. The 8-station-zoom slot is replaced by
the E235-0-specific 5-station stopping view (`JapaneseFiveStationDisplay`)
universally; only the transfer-info slot inherits unchanged from E235-1000.

Dispatch is route-keyed: ``route_data["route"] == "山手線"`` → circular
racetrack (`CircularFullRouteDisplay`); else → `OpenRouteFullRouteDisplay`,
the same racetrack opened into a horseshoe (one cap dropped) — a best-effort
E235-0 look for out-of-spec routes, replacing the old E235-1000 linear
fallback.

Geometry: stadium / racetrack — two horizontal rows joined by semicircular
end caps. Circular (Yamanote): bottom row holds JY17..JY30+JY01 (left→right
in inner-loop travel direction); top row holds JY02..JY16 (right→left in
travel direction); station screen positions are keyed by ``sta_code``, so
missing stations (e.g. JY26 高輪ゲートウェイ in pre-2020 data) auto-redistribute
the row's spacing without leaving a gap. Open (non-Yamanote): one cap dropped,
positions keyed by stop index, split ⌈N/2⌉ bottom / rest top, right-aligned at
the fold; the open-left side terminates at two flat edges (origin + terminus).

Per-station rendering states: pentagon (current stop), numbered countdown
(next 15 ahead in travel direction), or plain dot. The circular has no
dim/passed treatment (a loop has no terminal "behind"); the open variant adds
it — stations before the current stop dim to INACTIVE_COLOR.
"""

import json
import math
from collections import namedtuple
from typing import Dict, List, Optional, Tuple
import pygame
import pygame.gfxdraw
import pygame.surfarray

import font_atlas
from font_atlas import (
    STATION_NAMES,
    STATION_NAMES_EKI,
    at,
    lit,
)

# The route-map disclaimer. One constant so the `draws=` declarations name the
# same string the renderers draw, instead of a fourth hand-typed copy.
_DISCLAIMER = "のりかえ、待合せ時間は含まれません。電車により多少時間が異なります。"
from app_paths import project_root
from constants import (
    CURRENT_COLOR,
    INACTIVE_COLOR,
    PASSED_COLOR,
    STOPS_BAR_HEIGHT,
    STOPS_WIDTH,
    TIME_SCALE,
)
from displays.train_models.e235_0 import (
    S_WIDTH,
    S_HEIGHT,
    UPPER_HEIGHT,
    DARK_BG,
    WHITE_BG,
)
from displays.utils import (
    arrow_points,
    draw_1col_text_plain,
    draw_aapolygon,
    draw_station_code_badge,
    draw_text_given_width,
)
from displays.train_models.e235_1000.lower_lcd import (
    LowerDisplay as E235_1000_LowerDisplay,
)
from displays.transfer_info import apply_transfer_filter, resolve_entry
from displays.train_models.e235_1000.transfer_info import load_icon

# Lower-LCD bounding rect — clips/fills the 5-station view and anchors the
# bottom disclaimer; the calibration editor also uses it as the hit-test rect
# for clicks on the lower LCD. Spans the whole lower-LCD area. (The `ARC_`
# prefix is historical — the retired Catmull-Rom arc geometry it once bounded
# was replaced by the hand-drawn mask PNG + mask-derived fill centerline.)
ARC_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)

# Hit-test rect for the inline transfer panel (left column). A sub-region of
# ARC_RECT — the calibration editor checks it BEFORE `five_station` so clicks
# in the left column focus the panel, while clicks on the arc/markers (x ≥ this
# width, where m4 starts at x=225) fall through to the marker element. This is
# only the click-to-FOCUS region; the panel's curved right edge (tp1/tp2/tp3) may
# extend right of it, but those handles are grabbable once the panel is focused.
TP_RECT = pygame.Rect(0, UPPER_HEIGHT, 224, S_HEIGHT - UPPER_HEIGHT)

# Hit-test rect for the full-route track (the route bar). Same extent as
# ARC_RECT — both elements own the whole lower LCD — but they never collide,
# because they live in DIFFERENT lower-LCD views and the calibration editor
# filters hit-testing by the active view (`view` field in its _REGISTRY; press
# V to cycle). Before that dispatch existed, a full-route element could not be
# registered at all: a static rect would have swallowed every 5-station click.
FULL_ROUTE_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)


# =============================================================================
# Five-station band — Tier-2 mask PNG (docs/wip/WIP_calibration_editor.md § "Two-tier
# tuning model"). The band shape is hand-drawn white-on-transparent in
# Photoshop (pixel-precise, not parametric) and shipped under data/. At
# __init__ it is tinted with the route line color via an alpha-stencil bake:
# the mask's ALPHA is the only coverage source; RGB is forced white then
# multiplied by the color, so anti-aliased / non-255 edge pixels can't darken
# the result. This supersedes the Catmull-Rom arc machinery above (retired —
# removed at the master-port together with the calibration-editor drag handles).
# =============================================================================

_BAND_MASK_PATH = project_root() / "data" / "e235_0" / "five_station_band.png"

# Pixels whose min RGB channel is >= this are treated as the band's white FILL
# and recolored to the route line color. Anything below (e.g. the hand-drawn
# grey outline hugging the band edge) is left at its drawn RGB — rendered as-is.
_BAND_FILL_MIN = 190

# Five-station band fill animation — replays every time the EIGHT slot becomes
# active. The green sweeps along the band's CURVED centerline (bottom → top),
# with the leading front cut perpendicular to the local tangent, so its edge
# stays diagonal to the curve at every height (not one global sweep angle). See
# _build_fill_centerline + the reveal loop in show_stops.
_BAND_FILL_DURATION = 1.5  # seconds for the green to sweep bottom → top
# Timing curve: progress = raw_t ** _BAND_FILL_EASE_POWER. 1.0 = linear; > 1 =
# ease-in (slow start, ACCELERATES toward the top); < 1 = ease-out (fast start,
# eases into the top).
_BAND_FILL_EASE_POWER = 2.0
_BAND_GRAY = (200, 200, 200)  # gray base color shown behind the rising green
# Soft-edge width (px of arc length, trailing behind the moving front) over which
# the green alpha ramps 0 → 255, so the leading edge reads smooth, not a hard
# cut. 0 = hard edge; larger = softer / longer fade.
_BAND_FILL_FEATHER = 18
# Half-width (px) of the reveal corridor stamped along the centerline. Must
# exceed the band's widest half-thickness so the green reaches both edges;
# over-coverage is harmless (clipped by the band PNG's own alpha).
_BAND_FILL_HALF_WIDTH = 100


def _bake_band(color) -> pygame.Surface:
    """Tint the band mask's white FILL with `color`, preserving everything else.

    Only near-white opaque pixels (the fill) are recolored to the route line
    color; any other drawn pixels — notably the grey outline along the band's
    outer edge — keep their original RGB so they render as-drawn. The alpha
    channel (coverage / anti-aliasing) is never touched, so edges stay smooth.
    One bake; the surface is blitted as-is each frame.
    """
    band = pygame.image.load(str(_BAND_MASK_PATH)).convert_alpha()
    rgb = pygame.surfarray.pixels3d(band)  # live (w,h,3) view; locks surface
    is_fill = rgb.min(axis=2) >= _BAND_FILL_MIN
    rgb[is_fill] = color
    del rgb  # unlock before blitting
    return band


def _extract_band_centerline() -> List[Tuple[float, float]]:
    """Medial centerline of the band mask — one point per pixel row, the
    horizontal centroid of the band's FILL in that row, ordered bottom → top
    (the sweep direction). The mask is a SINGLE contiguous band per row
    (verified: zero multi-segment rows over the shipped PNG), so a per-row
    centroid is a faithful medial line — no parametric waypoints, no Catmull-Rom.

    Loads the RAW mask (near-white fill, same test as ``_bake_band``): the baked
    band is tinted, so its fill is no longer near-white — hence the fresh load.
    ndarray methods only (``.nonzero()`` / ``.mean()``) — surfarray returns real
    ndarrays, so no numpy import is needed (matches ``_bake_band``'s style)."""
    band = pygame.image.load(str(_BAND_MASK_PATH)).convert_alpha()
    rgb = pygame.surfarray.array3d(band)  # (w, h, 3)
    alpha = pygame.surfarray.array_alpha(band)  # (w, h)
    fill = (rgb.min(axis=2) >= _BAND_FILL_MIN) & (alpha > 10)
    h = fill.shape[1]
    pts: List[Tuple[float, float]] = []
    for y in range(h - 1, -1, -1):  # bottom → top
        xs = fill[:, y].nonzero()[0]
        if xs.size:
            pts.append((float(xs.mean()), float(y)))
    return pts


# =============================================================================
# Five-station marker positions (Tier-1 — calibration-editor tuneable). Markers
# sit ALONG the band: m0 = current stop (bottom), m1..m4 = next four stops going
# up. `_x`/`_y` pairs follow the editor suffix convention so they drag in the
# sidebar. Names sit left of each marker. See docs/wip/WIP_calibration_editor.md.
# =============================================================================

# Each station is its own object: a circle marker `m<k>_*` (x/y draggable, r =
# radius) + a badge+name group `g<k>_*` (x/y draggable anchor, b = badge size
# (square), ns = name font px, ni = name inset). Every per-station key matches
# `^[mg]<k>_`, which the calibration editor uses to show one station at a time.
# Badge sub-fonts derive from b; the minute digit derives from r (no extra knobs).
# fmt: off
_TUNEABLES_FIVE_STATION = {
    # station 0 — current stop (red stopping marker). FREE POLYGON: the
    # marker is drawn at one fixed slot + fixed orientation (only ever at
    # k==0; the 5-station view re-centres on the current stop), so there is NO
    # parametric shape model — the five vertices v0..v4 ARE the shape,
    # hand-placed against _references/lcd/E2350.png via the editor's drag
    # handles. Order = polygon winding: v0=apex, v1=shoulder R, v2=back R,
    # v3=back L, v4=shoulder L. m0_x/m0_y = the white dot centre (its own drag
    # handle) AND the index-0 anchor the m-prefix handle scan needs to reach
    # m1..m4; m0_dr = dot radius (px). Breath scales the polygon about its
    # centroid; halo is a uniform edge-normal offset. To reshape: drag the
    # v-handles — no knobs, no math.
    "m0_x": 459, "m0_y": 358, "m0_dr": 9,
    "v0_x": 444, "v0_y": 333, "v1_x": 475, "v1_y": 335, "v2_x": 498, "v2_y": 371,
    "v3_x": 447, "v3_y": 396, "v4_x": 428, "v4_y": 356,
    "g0_x": 526, "g0_y": 350, "g0_b": 42, "g0_ns": 42, "g0_ni": 46,
    # station 1 — m<N>_ts = countdown digit point size. Deliberately
    # PER-STATION params, NOT a radius-derived formula — tuned by eye and
    # kept explicit per user call (2026-06-12). Don't fold into a scale law
    # unless the user asks.
    "m1_x": 410, "m1_y": 293, "m1_r": 21, "m1_ts": 31,
    "g1_x": 481, "g1_y": 288, "g1_b": 38, "g1_ns": 40, "g1_ni": 44,
    # station 2
    "m2_x": 355, "m2_y": 243, "m2_r": 19, "m2_ts": 28,
    "g2_x": 416, "g2_y": 229, "g2_b": 34, "g2_ns": 38, "g2_ni": 35,
    # station 3
    "m3_x": 293, "m3_y": 200, "m3_r": 17, "m3_ts": 26,
    "g3_x": 339, "g3_y": 180, "g3_b": 29, "g3_ns": 32, "g3_ni": 32,
    # station 4 — farthest ahead
    "m4_x": 225, "m4_y": 167, "m4_r": 15, "m4_ts": 20,
    "g4_x": 262, "g4_y": 146, "g4_b": 25, "g4_ns": 28, "g4_ni": 28,
    # approaching-state marker (state.at_station == False) at slot 0
    "m0_circle_r":    22,   # approaching-circle outer radius
    "m0_circle_inset": 2,   # inner dark-yellow disk inset (matches full-route inner_disk_inset)
    "m0_ts":          34,   # m0 minutes-digit point size
    # approaching arrow — prefix "a", index 0: a0_x/a0_y are the drag handle pair.
    "a0_x":           479,  # arrow tip x (near m0_x)
    "a0_y":           398,  # arrow tip y (below the circle)
    "a0_angle":         -118,  # arrow heading, degrees (rotate toward m0)
    "a0_scale":       1.5,  # arrow size multiplier vs full-route original
    "a0_halo_w":        1,  # uniform halo thickness (px) on every side of arrow
    # approaching arrow sweep animation — single-chevron cycle: travel A→B, fade, rest, repeat.
    "a0_sweep_dist":   19,  # px the tip travels along heading from A to B
    "a0_sweep_dur":   0.7,  # seconds for A→B travel (= full-route sweep_duration_s)
    "a0_fade_dur":    0.4,  # seconds to fade out at B (= full-route fade_out_s)
    "a0_rest_gap":    0.2,  # seconds of invisible gap before restart (= full-route rest_s)
    # approaching arrow sweep EASE curve (the "fast→slow" motion) — tunable so
    # the feel can be nudged in the editor (prefix "a" → approaching-gated).
    "a0_ease_out_power":   2.0,  # sweep position: >1 = decelerating (fast at A, slow at B); 1 = linear
    "a0_fade_in_full_at":  0.5,  # alpha reaches 1.0 when raw sweep_t hits this fraction (decoupled from position)
    "a0_fade_out_power":   2.0,  # fade-out alpha = 1 - fade_t**this (>1 = slow drop early, fast late)
    "a0_fade_stagger":    0.3,  # fade-out lead: white halo fades over [0, 1-stagger] of fade_dur, red body over [stagger, 1] (0 = together)
}
# fmt: on


# =============================================================================
# Inline transfer panel — left column of the 5-station view. IRL the panel is
# always shown when the target station has transfers (NOT the horizontal
# transfer SLOT — that one stays inherited from e235_1000). Data path reuses
# the parent filter (apply_transfer_filter) so the entry ORDER matches the
# slot. Fonts smaller than the slot; no list-level compression (knob reserved).
# Shinkansen take one row but wrap their long name at `・` into two lines shrunk
# to fit the row pitch. See docs/DISPLAY_E235.md § "Transfer Info".
# =============================================================================
# fmt: off
_TUNEABLES_TRANSFER_PANEL = {
    "tp0_x":          10,   # panel anchor x (left margin) — DRAG handle (pairs with tp0_y)
    "tp0_y":         205,   # panel anchor y (header top) — DRAG handle (pairs with tp0_x)
    "tp1_x":         303,   # right-edge CURVE pt1 (top) x — DRAG handle (pairs tp1_y)
    "tp1_y":         251,   # right-edge curve pt1 (top) y — DRAG handle (pairs tp1_x)
    "tp2_x":         367,   # right-edge CURVE pt2 (mid) x — DRAG handle (pairs tp2_y)
    "tp2_y":         310,   # right-edge curve pt2 (mid) y — DRAG handle (pairs tp2_x)
    "tp3_x":         417,   # right-edge CURVE pt3 (bot) x — DRAG (wider: more room low)
    "tp3_y":         396,   # right-edge curve pt3 (bot) y — DRAG handle (pairs tp3_x)
    "tp_header_size": 16,   # {station}駅 — ShinGo Heavy (most bold)
    "tp_sub_gap":      2,   # gap header-bottom → subtitle-top
    "tp_sub_size":    16,   # 乗換えのご案内 — ShinGo Light (thin)
    "tp_list_gap":    8,   # gap subtitle-bottom → first row-top
    "tp_row_pitch":   24,   # fixed vertical step per entry (push-down; no compression)
    "tp_compress":   1.0,   # list-level vertical compression (1.0 = none; reserved for overflow)
    "tp_badge":       19,   # line badge square size (px) — smaller than slot
    "tp_badge_gap":    3,   # gap badge group → name
    "tp_name_size":   16,   # line name — ShinGo Medium (= slot face, smaller size)
    "tp_inter_badge":  2,   # gap between stacked badges within one entry
    "tp_col_gap":     10,   # gap between the two columns when 2 entries share a row
    "tp_wrap_lgap":    2,   # gap between the two wrapped lines (both full size, no shrink)
    "tp_pair_min_n":   6,   # pair only when ≥ this many transfers; fewer → all solo
    "tp_shink_wrap_x": 233, # shinkansen 2-line wrap right edge (NARROWER than curve; fixed cut at 北海道|上越)
}
# fmt: on


# =============================================================================
# Canonical Yamanote JY-code ordering for racetrack screen layout.
#
# Bottom row holds JY17 (新宿) through JY30 (有楽町) and wraps to JY01 (東京)
# at the right corner — 15 canonical slots, displayed left→right in the
# inner-loop travel direction.
#
# Top row holds JY02 (神田) through JY16 (新大久保) — 15 canonical slots,
# displayed left→right on screen as JY16, JY15, ..., JY02 (i.e. the inner-loop
# travel direction is right→left visually as the train comes around the
# right curve and traverses the top row back to the left curve).
#
# Missing JY codes (e.g. JY26 in pre-高輪ゲートウェイ data) are filtered out
# at __init__; remaining stations re-space evenly within their row.
# =============================================================================

JY_BOTTOM_LR_SCREEN: List[int] = [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 1]
JY_TOP_LR_SCREEN: List[int] = [16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2]


# Station names rendered with Heavy weight (bold-style) on the racetrack.
# IRL Yamanote PIDS bolds a specific subset of major interchange stations —
# NOT derived from code_3 (大崎/JY24 has code_3=OSK but is NOT bolded). User-
# approved hardcoded set; extend by adding entries below.
MAJOR_STATION_NAMES_BOLD: set[str] = {"上野", "東京", "品川", "新宿", "渋谷", "池袋"}


def _parse_jy_code(sta_code: str) -> Optional[int]:
    """Parse 'JY24' → 24. Returns None if not a JY code."""
    if not sta_code or not sta_code.startswith("JY"):
        return None
    try:
        return int(sta_code[2:])
    except ValueError:
        return None


# =============================================================================
# Circular Full-Route Display (Yamanote racetrack)
# =============================================================================


# =============================================================================
# Full-route track geometry — the route bar's cross-method layout params.
# Read by BOTH _build_positions (where the stops sit) and _draw_track (where
# the band is drawn), so a shape edit lands once for the circular racetrack AND
# the open horseshoe that subclasses it.
#
# Editor-tunable: focus with the lower view on `full` (press V to cycle views).
# Because positions are PRECOMPUTED at __init__ rather than read per frame,
# show_stops re-applies + rebuilds when the dict changes — see
# _resync_tuneables. Production never edits the dict, so the signature compare
# is the whole per-frame cost.
#
# `curve_v_radius` is deliberately NOT a key: it is derived from the two row
# centerlines, and a key would let the two disagree (conventions.md § Tooling,
# "Canonical-source duplication").
# =============================================================================
# fmt: off
_TUNEABLES_FULL_ROUTE = {
    # Vertical — track row centerlines, relative to y_top (= UPPER_HEIGHT).
    "track_top_y":         120,  # y of top-row track centerline
    "track_bottom_y":      187,  # y of bottom-row track centerline

    # Horizontal — straight section runs track_left_pad → S_WIDTH - track_right_pad
    "track_left_pad":       15,  # x of left curve apex (leftmost track edge)
    "track_right_pad":      15,  # mirrored from the right edge

    # Band geometry — consumed by _draw_track AND _build_positions.
    "track_stroke_w":       28,  # thickness of the green band
    # Cap shape: rounded-corner rectangle (NOT a full ellipse). Each cap has
    # quarter-arc top + bottom corners plus a vertical straight segment at the
    # apex. OUTER and INNER rects take independent vert_seg lengths — a smaller
    # inner vert_seg means a larger inner border_radius, so the inner edge
    # bulges further toward the apex. Stroke at the apex vertical segment stays
    # = stroke_w (the rect inset is uniform horizontally); the corner arcs are
    # not concentric, so stroke width varies slightly along the arc.
    "vert_seg_h_outer":     20,  # outer-rect vertical straight at apex
    "vert_seg_h_inner":     15,  # inner-rect vertical straight at apex (smaller = curvier)

    # Numbered-circle outer radius — shared by _draw_numbered_circle (its own
    # size) and _draw_approaching_arrow (chevron tip anchors at the circle's
    # left edge + tip_into_circle).
    "circle_outer_radius":  12,
}
# fmt: on


class CircularFullRouteDisplay:
    """E235-0 racetrack-style full-route display (Yamanote-only).

    Drives the full-route slot when the active route is 山手線. Layout is
    fixed: each station's screen position is precomputed at __init__ from
    its ``sta_code``; the pentagon moves to ``stops[curr_stop]``'s position.
    Stations within the next 15 ahead (inner-loop direction, deduped by
    sta_code) render as numbered countdown circles; the rest render as
    plain dots.
    """

    NUMBERED_AHEAD_COUNT = 15

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.color = route_data.get("color", [116, 193, 30])
        self.contrast_color = route_data.get("contrast_color", [224, 54, 37])

        # =====================================================================
        # Cross-method layout params — referenced by both _build_positions and
        # the draw methods. Per-method tuneables (pentagon shape, dot/circle
        # sizes, name clearance) live as locals in their respective draw
        # methods per conventions.md § "Tuneable-params block".
        # =====================================================================
        self.y_top = UPPER_HEIGHT  # absolute y where lower LCD area starts
        self.lower_h = S_HEIGHT - self.y_top

        # Track geometry comes from _TUNEABLES_FULL_ROUTE (module top) so the
        # calibration editor can drive it. See that dict's header for what each
        # key means and why curve_v_radius is derived rather than stored.
        self._apply_full_route_tuneables()

        # =====================================================================
        # Fonts (shared across multiple draw methods)
        # =====================================================================
        # Major station names use Heavy weight; the rest use Medium. The
        # bold set is hardcoded at module scope (MAJOR_STATION_NAMES_BOLD) —
        # not derived from code_3 since IRL Yamanote PIDS bolds a narrower set.
        self.font_station = font_atlas.lcd_font("ShinGoPr6N-Medium.otf", 19, draws=STATION_NAMES)
        self.font_station_bold = font_atlas.lcd_font("ShinGoPr6N-Heavy.otf", 19, draws=STATION_NAMES)
        self.font_circle = font_atlas.lcd_font("HelveticaNeue-Bold.otf", 15)
        self.font_minute = font_atlas.lcd_font("ShinGoPr6N-Medium.otf", 10, draws=lit("分", "(分)"))
        self.font_disclaimer = font_atlas.lcd_font("ShinGoPr6N-Medium.otf", 9, draws=lit(_DISCLAIMER))

        # =====================================================================
        # Build per-sta_code position table (screen coordinates)
        # =====================================================================
        self.positions: Dict[int, Tuple[int, int]] = {}
        self._build_positions()

    # -------------------------------------------------------------------------
    # Layout — sta_code → (x, y) precomputation
    # -------------------------------------------------------------------------

    def _apply_full_route_tuneables(self) -> None:
        """Copy `_TUNEABLES_FULL_ROUTE` onto self, deriving what is derivable.

        Every draw method and both `_build_positions` implementations read these
        off `self`, so this is the single place the dict crosses into the
        renderer. `curve_v_radius` is DERIVED here rather than stored, so the
        two row centerlines and the cap radius cannot disagree.

        Also stamps `_tuneables_sig` — the signature `_resync_tuneables`
        compares against.
        """
        t = _TUNEABLES_FULL_ROUTE
        self.track_top_y = t["track_top_y"]
        self.track_bottom_y = t["track_bottom_y"]
        self.track_left_pad = t["track_left_pad"]
        self.track_right_pad = t["track_right_pad"]
        self.track_stroke_w = t["track_stroke_w"]
        self.vert_seg_h_outer = t["vert_seg_h_outer"]
        self.vert_seg_h_inner = t["vert_seg_h_inner"]
        self.circle_outer_radius = t["circle_outer_radius"]
        # Derived — see the docstring. _build_positions takes row centerlines
        # from cy ± curve_v_radius (matching _draw_track) so a 1-pixel asymmetry
        # from an odd sum doesn't bite the bottom row's stroke alignment.
        self.curve_v_radius = (self.track_bottom_y - self.track_top_y) // 2
        self._tuneables_sig = tuple(sorted(t.items()))

    def _resync_tuneables(self) -> None:
        """Re-apply the tuneables + rebuild positions when the dict changed.

        # CONTRACT: station positions are PRECOMPUTED at __init__, not read per
        # frame — so a calibration-editor nudge to track geometry would move the
        # drawn band and leave the stops behind it. Both `show_stops`
        # implementations call this first. Production never mutates the dict, so
        # the cost there is one tuple compare per frame and nothing else.
        """
        sig = tuple(sorted(_TUNEABLES_FULL_ROUTE.items()))
        if sig != self._tuneables_sig:
            self._apply_full_route_tuneables()
            self._build_positions()

    _BandGeom = namedtuple("_BandGeom", "cy v_outer border_outer")

    def _band_geometry(self) -> "_BandGeom":
        """The track-band constants shared by ``_build_positions`` (stops sit on
        the drawn track) and ``_draw_track`` (draws it). One source so a
        track-shape edit lands once — editing the formula in a single site would
        desync the stops from the track. Returns RAW values: ``_draw_track``
        keeps its own ``max(1, …)`` clamp for the ``border_radius`` draw arg, and
        each caller keeps its OWN local derivations (``straight_left`` /
        ``straight_w`` = stop layout; ``v_inner`` / ``border_inner`` = inner
        white hole). Only the genuinely-shared three live here.
        ``OpenRouteFullRouteDisplay`` extends this with ``straight_right`` (its
        passed-band clips also key off the band)."""
        v_outer = self.curve_v_radius + self.track_stroke_w // 2
        border_outer = v_outer - self.vert_seg_h_outer // 2
        return self._BandGeom(
            cy=self.y_top + (self.track_top_y + self.track_bottom_y) // 2,
            v_outer=v_outer,
            border_outer=border_outer,
        )

    def _build_positions(self) -> None:
        """Compute screen position for each station present in stops[].

        Bottom row distributes evenly along the straight section between the
        two end-curves; top row mirrors. Curves themselves carry no station
        positions — only the straight sections do.
        """
        present_jy: set[int] = set()
        for s in self.stops:
            jy = _parse_jy_code(s.get("sta_code", ""))
            if jy is not None:
                present_jy.add(jy)

        bottom_present = [j for j in JY_BOTTOM_LR_SCREEN if j in present_jy]
        top_present = [j for j in JY_TOP_LR_SCREEN if j in present_jy]

        # Straight section x-range — between the cap corner-arc boundaries.
        # The OUTER corner arc has radius = v_outer - vert_seg_h_outer/2; it
        # spans inward from each rect edge by that radius. Stations sit only
        # in the straight section between the corners; arc regions carry no
        # station positions.
        g = self._band_geometry()
        border_outer = g.border_outer
        straight_left = self.track_left_pad + border_outer
        straight_right = S_WIDTH - self.track_right_pad - border_outer
        straight_w = straight_right - straight_left

        # Row centerline y values — derived from cy ± curve_v_radius to match
        # _draw_track's cy (avoids odd-sum 1-pixel offset on the bottom row).
        cy = g.cy
        top_row_y = cy - self.curve_v_radius
        bot_row_y = cy + self.curve_v_radius

        # Both rows share a canonical item spacing derived from the row with
        # MORE stations (so the longer row spans the full straight section).
        # The shorter row reuses that spacing; its leftover slack splits
        # evenly on both ends — matches IRL Yamanote behavior when JY26
        # 高輪ゲートウェイ is absent (bottom row 14 < top row 15).
        # ``self.slot_w`` is also consumed by chevron-animation cross-row
        # synthesis (phantom-prev placement past the curve).
        n_canonical = max(len(top_present), len(bottom_present), 1)
        self.slot_w = straight_w / n_canonical

        # Bottom row positions
        if bottom_present:
            used_w = len(bottom_present) * self.slot_w
            row_left = straight_left + (straight_w - used_w) / 2
            for i, jy in enumerate(bottom_present):
                x = row_left + self.slot_w * (i + 0.5)
                self.positions[jy] = (int(x), bot_row_y)

        # Top row positions
        if top_present:
            used_w = len(top_present) * self.slot_w
            row_left = straight_left + (straight_w - used_w) / 2
            for i, jy in enumerate(top_present):
                x = row_left + self.slot_w * (i + 0.5)
                self.positions[jy] = (int(x), top_row_y)

    # -------------------------------------------------------------------------
    # State helpers — "next 15 ahead" with sta_code dedup
    # -------------------------------------------------------------------------

    def _ahead_indices(self, curr_stop: int, include_curr: bool = False) -> List[Tuple[int, int]]:
        """Return up to NUMBERED_AHEAD_COUNT (stop_index, jy_code) tuples for
        the next stations ahead of ``curr_stop`` in inner-loop direction.

        ``include_curr=True`` prepends ``curr_stop`` itself as the first entry —
        used when APPROACHING (train hasn't arrived yet, so curr_stop is part
        of the upcoming countdown set). Total output stays capped at
        NUMBERED_AHEAD_COUNT either way.

        Walks ``stops[]`` forward with modulo wrap, skipping any sta_code
        already seen. The wrap handles the data shape where Yamanote's
        route.json doubles the start station at the end (stops[0] and
        stops[-1] are both 大崎 = JY24); without dedup, the duplicate would
        try to render twice at the same screen position.
        """
        if not (0 <= curr_stop < len(self.stops)):
            return []

        seen: set[int] = set()
        ahead: List[Tuple[int, int]] = []
        curr_jy = _parse_jy_code(self.stops[curr_stop].get("sta_code", ""))
        if curr_jy is not None:
            if include_curr:
                ahead.append((curr_stop, curr_jy))
            seen.add(curr_jy)

        n = len(self.stops)
        # 2n cap is a guard against infinite loops if data is malformed.
        for offset in range(1, 2 * n + 1):
            idx = (curr_stop + offset) % n
            jy = _parse_jy_code(self.stops[idx].get("sta_code", ""))
            if jy is None or jy in seen:
                continue
            ahead.append((idx, jy))
            seen.add(jy)
            if len(ahead) >= self.NUMBERED_AHEAD_COUNT:
                break
        return ahead

    # -------------------------------------------------------------------------
    # Track drawing
    # -------------------------------------------------------------------------

    def _draw_track(self) -> None:
        """Draw the racetrack: rounded-corner rectangle (NOT a full stadium).

        Each cap is a rectangle-with-rounded-corners shape: quarter-arc top +
        bottom corners + a vertical straight segment in the middle of the
        apex. Pygame's `border_radius=` draws this natively; concentric
        outer/inner rounded rects (inset by stroke_w on all sides) produce
        uniform stroke at every angle on the corner.

        Geometry derivation:
          border_outer = v_outer - vert_seg_h/2
          border_inner = v_inner - vert_seg_h/2 = border_outer - stroke_w
        So inner border_radius is automatically right when both rects are
        offset by stroke_w on every side.
        """
        g = self._band_geometry()
        # fmt: off
        # --- Track draw params (adjust freely) ---
        v_outer      = g.v_outer
        v_inner      = max(1, self.curve_v_radius - self.track_stroke_w // 2)
        border_outer = max(1, g.border_outer)  # clamp for border_radius (draw arg, not a coordinate)
        border_inner = max(1, v_inner - self.vert_seg_h_inner // 2)
        # -----------------------------------------
        # fmt: on

        cy = g.cy

        # Outer green rounded-corner rectangle
        outer_rect = pygame.Rect(
            self.track_left_pad,
            cy - v_outer,
            S_WIDTH - self.track_left_pad - self.track_right_pad,
            2 * v_outer,
        )
        pygame.draw.rect(self.screen, self.color, outer_rect, border_radius=border_outer)

        # Inner white rounded-corner rectangle (inset by stroke_w on all sides)
        inner_rect = pygame.Rect(
            self.track_left_pad + self.track_stroke_w,
            cy - v_inner,
            S_WIDTH - self.track_left_pad - self.track_right_pad - 2 * self.track_stroke_w,
            2 * v_inner,
        )
        pygame.draw.rect(self.screen, WHITE_BG, inner_rect, border_radius=border_inner)

    # -------------------------------------------------------------------------
    # Per-station markers
    # -------------------------------------------------------------------------

    def _draw_approaching_arrow(self, tip_x: float, tip_y: float, face_left: bool, alpha: float = 1.0) -> None:
        """Chevron arrow at a given tip apex (tip_x, tip_y) with optional fade alpha.

        Geometry copied verbatim from e235_1000.JapaneseDisplay.draw_ptr's
        full-route chevron path (NOT the 8-station uniform-halo recipe).
        Absolute deltas: halo wider by 5, shorter by 4, thicker stroke by 6,
        offset 2px back of body. Body sized for racetrack readability.

        ``face_left=True`` produces a left-pointing chevron with apex at
        (tip_x, tip_y); ``face_left=False`` produces a right-pointing one.
        ``alpha < 1.0`` renders via a SRCALPHA Surface so the chevron can fade
        in/out at animation endpoints — gfxdraw / draw_aapolygon themselves
        only take solid colors.
        """
        # fmt: off
        # --- Arrow params (adjust freely) ---
        # tip-portion = w_body - stroke_body sets the tip angle (pointiness).
        w_body            = 17                     # racetrack-tuned (narrower than sibling's 18)
        h_body            = STOPS_BAR_HEIGHT + 2   # = 32 (overhangs 2px past green band each side)
        stroke_body       = 11                     # tip-portion = 6
        # Halo absolute deltas (from e235_1000 full-route chevron, NOT 8-station).
        halo_w_extra      = 5                      # halo wider than body
        halo_h_under      = 4                      # halo shorter than body
        halo_stroke_extra = 6                      # halo stroke thicker than body
        halo_back_extra   = 2                      # halo extends past body's back by this much
        # ------------------------------------
        # fmt: on
        w_halo = w_body + halo_w_extra
        h_halo = h_body - halo_h_under
        stroke_halo = stroke_body + halo_stroke_extra
        halo_apex_extra = halo_w_extra - halo_back_extra  # = 3 (halo extends past body apex)

        # Build right-pointing geometry first; mirror per-bbox if face_left.
        # body apex = (body_x + w_body, body_y + h_body/2). Set body_x so apex.x = tip_x.
        body_x = tip_x - w_body
        body_y = tip_y - h_body / 2
        # halo apex extends `halo_apex_extra` past body apex; halo bbox right = body_x + w_body + halo_apex_extra.
        halo_x = body_x + w_body + halo_apex_extra - w_halo  # = body_x - halo_back_extra
        halo_y = tip_y - h_halo / 2

        body_pts = arrow_points(int(body_x), int(body_y), w_body, h_body, stroke_body)
        halo_pts = arrow_points(int(halo_x), int(halo_y), w_halo, h_halo, stroke_halo)

        if face_left:
            # Mirror each polygon around its own bbox horizontal center so the
            # apex flips from right edge to left edge. Apex of mirrored body
            # lands at body_x → set body_x = tip_x for left-pointing.
            body_x = tip_x
            halo_x = body_x - halo_apex_extra
            body_pts = arrow_points(int(body_x), int(body_y), w_body, h_body, stroke_body)
            halo_pts = arrow_points(int(halo_x), int(halo_y), w_halo, h_halo, stroke_halo)
            body_center_x = body_x + w_body / 2
            halo_center_x = halo_x + w_halo / 2
            body_pts = [(2 * body_center_x - px, py) for (px, py) in body_pts]
            halo_pts = [(2 * halo_center_x - px, py) for (px, py) in halo_pts]

        if alpha >= 1.0:
            draw_aapolygon(self.screen, PASSED_COLOR, halo_pts, 5)
            draw_aapolygon(self.screen, self.contrast_color, body_pts)
            return

        # Faded path — render to SRCALPHA surface, scale alpha via BLEND_RGBA_MULT, blit.
        all_pts = halo_pts + body_pts
        min_x = int(min(p[0] for p in all_pts)) - 2
        min_y = int(min(p[1] for p in all_pts)) - 2
        max_x = int(max(p[0] for p in all_pts)) + 2
        max_y = int(max(p[1] for p in all_pts)) + 2
        surf_w = max_x - min_x + 1
        surf_h = max_y - min_y + 1
        if surf_w <= 0 or surf_h <= 0:
            return
        surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        local_halo = [(px - min_x, py - min_y) for (px, py) in halo_pts]
        local_body = [(px - min_x, py - min_y) for (px, py) in body_pts]
        draw_aapolygon(surf, PASSED_COLOR, local_halo, 5)
        draw_aapolygon(surf, self.contrast_color, local_body)
        a = max(0, min(255, int(alpha * 255)))
        surf.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(surf, (min_x, min_y))

    def _compute_chevron_animation_state(self, curr_stop: int) -> Optional[List[Tuple[float, float, bool, float]]]:
        """Compute the chevron animation frames for the current frame.

        Returns:
          - ``list`` of ``(tip_x, tip_y, face_left, alpha)`` tuples (0..2
            entries) when the animation is in scope. Empty list = legitimate
            "rest gap" frame where no chev is visible — caller draws nothing.
          - ``None`` when the animation is out-of-scope (no valid previous
            station, cross-row transition) — caller falls back to a static
            chev at curr_stop's near-circle position.

        The None-vs-empty distinction matters: an empty frame during the
        rest gap must NOT trigger the static fallback (would flash a
        full-alpha chev at B mid-rest).

        Animation: two chevs phase-offset by ``phase_offset_s = sweep +
        fade_out + rest_s``, each cycling ``cycle_period_s = 2 *
        phase_offset_s``. Per chev: fade-in at A → eased sweep A→B →
        fade-out at B → idle. ``rest_s`` directly controls the empty gap
        between any two chevs being visible.
        """
        if not (0 <= curr_stop < len(self.stops)):
            return None

        curr_jy = _parse_jy_code(self.stops[curr_stop].get("sta_code", ""))
        if curr_jy is None or curr_jy not in self.positions:
            return None

        # Walk backward in stops[] with sta_code dedup to find the previous
        # station's jy. Mirrors _ahead_indices but in the reverse direction.
        last_jy = None
        seen = {curr_jy}
        n = len(self.stops)
        for offset in range(1, 2 * n + 1):
            idx = (curr_stop - offset) % n
            jy = _parse_jy_code(self.stops[idx].get("sta_code", ""))
            if jy is None or jy in seen:
                continue
            last_jy = jy
            break

        if last_jy is None or last_jy not in self.positions:
            return None

        # Cross-row transitions: chev does NOT animate across the curve. When
        # curr is the first station past a curve (e.g. JY02 right after the
        # right curve, or JY17 right after the left curve), synthesize a
        # phantom prev one slot_w away on the SAME row in the direction
        # opposite travel (top row travels R→L → phantom to the RIGHT of
        # curr; bottom row travels L→R → phantom to the LEFT of curr). The
        # animation then sweeps from phantom toward curr like any normal
        # same-row segment.
        curr_on_top = curr_jy in JY_TOP_LR_SCREEN
        last_on_top = last_jy in JY_TOP_LR_SCREEN
        curr_pos = self.positions[curr_jy]
        if curr_on_top != last_on_top:
            phantom_dx = self.slot_w if curr_on_top else -self.slot_w
            last_pos = (curr_pos[0] + phantom_dx, curr_pos[1])
        else:
            last_pos = self.positions[last_jy]

        return self._chevron_frames(last_pos, curr_pos)

    def _chevron_frames(self, last_pos: Tuple[float, float], curr_pos: Tuple[float, float]) -> List[Tuple[float, float, bool, float]]:
        """Compute the two phase-offset chevron frames for a same-row segment
        from ``last_pos`` (station A) toward ``curr_pos`` (station B).

        Pure timing/geometry — agnostic to how A and B were resolved (JY-code
        walk for the circular loop, index walk for the open route). Returns
        0..2 ``(tip_x, tip_y, face_left, alpha)`` tuples; an empty list is a
        legitimate rest-gap frame (caller draws nothing, NOT the static
        fallback).
        """
        # fmt: off
        # --- Animation params (adjust freely) ---
        # Per-chev timeline within cycle_period_s:
        #   0 → sweep_duration_s:               sweep + fade-in (A → B)
        #   sweep → sweep+fade_out_s:           fade-out at B
        #   sweep+fade_out → cycle_period_s:    idle (invisible)
        # Two chevs phase-offset by sweep+fade_out+rest, so chev2 only spawns at
        # A AFTER chev1's full lifecycle (sweep + fade-out) completes AND a
        # rest_s gap of "no visible chev" elapses. cycle = 2 * phase_offset =
        # 2 * (sweep + fade_out + rest). rest_s directly controls the empty gap.
        sweep_duration_s  = 1.0
        fade_out_s        = 0.4
        rest_s            = 0.3   # empty gap (NO chev visible) between one chev's fade-out end and the other's spawn at A
        endpoint_gap_A    = 3     # px gap between chev tip and last station's circle near edge (= start position)
        endpoint_gap_B    = 1     # px gap between chev tip and curr_stop's circle near edge (= end position)
        ease_out_power    = 2     # sweep position eased via 1-(1-sweep_t)**ease_out_power (>1 = decelerating: fast at A, slow at B)
        fade_in_full_at   = 0.5   # alpha hits 1.0 when raw sweep_t reaches this fraction (0.5 = midpoint); decoupled from position so ease-out flick keeps a smooth fade-in
        fade_out_power    = 2     # fade-out alpha = 1 - fade_t**fade_out_power (>1 = accelerating: slow drop early, fast drop late)
        # ----------------------------------------
        # fmt: on
        phase_offset_s = sweep_duration_s + fade_out_s + rest_s
        cycle_period_s = 2 * phase_offset_s

        dx = 1 if curr_pos[0] > last_pos[0] else -1
        tip_x_A = last_pos[0] + dx * (self.circle_outer_radius + endpoint_gap_A)
        tip_x_B = curr_pos[0] - dx * (self.circle_outer_radius + endpoint_gap_B)
        tip_y = curr_pos[1]
        face_left = dx < 0

        t_now = pygame.time.get_ticks() / 1000.0
        chevs: List[Tuple[float, float, bool, float]] = []
        for chev_t_offset in (0.0, phase_offset_s):
            t_chev = (t_now - chev_t_offset) % cycle_period_s
            if t_chev < sweep_duration_s:
                sweep_t = t_chev / sweep_duration_s
                eased = 1 - (1 - sweep_t) ** ease_out_power
                tip_x = tip_x_A + (tip_x_B - tip_x_A) * eased
                alpha = min(1.0, sweep_t / fade_in_full_at)
            elif t_chev < sweep_duration_s + fade_out_s:
                fade_t = (t_chev - sweep_duration_s) / fade_out_s
                alpha = 1.0 - fade_t**fade_out_power
                tip_x = tip_x_B
            else:
                continue  # rest phase — chev not visible this frame
            chevs.append((tip_x, tip_y, face_left, alpha))
        return chevs

    def _draw_direction_arrows(self) -> None:
        """Draw inner-loop direction chevrons on each cap's apex.

        Inner-loop travel direction:
          - Left cap: train comes around from top row down to bottom row → DOWN chevron (V).
          - Right cap: train goes from bottom row up to top row → UP chevron (^).
        Chevron sits centered on the vertical apex segment, drawn in WHITE_BG
        on top of the green band.
        """
        # fmt: off
        # --- Arrow params (adjust freely) ---
        # arrow_w spans the full color-bar width so the chevron reaches the
        # inner edges of the band. Smaller arrow_h = flatter, less pointy
        # chevron (higher w/h ratio = obtuse-angle V).
        arrow_w = 28   # chevron horizontal extent (= track_stroke_w, full band)
        arrow_h = 6    # chevron vertical extent (top-to-tip depth) — flatter is less pointy
        stroke  = 4
        # -------------------------------------
        # fmt: on

        cy = self.y_top + (self.track_top_y + self.track_bottom_y) // 2
        left_band_cx = self.track_left_pad + self.track_stroke_w // 2
        right_band_cx = S_WIDTH - self.track_right_pad - self.track_stroke_w // 2

        self._draw_chevron(left_band_cx, cy, arrow_w, arrow_h, stroke, point_down=True)
        self._draw_chevron(right_band_cx, cy, arrow_w, arrow_h, stroke, point_down=False)

    def _draw_chevron(self, cx: int, cy: int, w: int, h: int, stroke: int, point_down: bool) -> None:
        """Draw a vertical chevron (V down or ^ up) centered on (cx, cy)."""
        half_w = w // 2
        half_h = h // 2
        if point_down:
            left = (cx - half_w, cy - half_h)
            tip = (cx, cy + half_h)
            right = (cx + half_w, cy - half_h)
        else:
            left = (cx - half_w, cy + half_h)
            tip = (cx, cy - half_h)
            right = (cx + half_w, cy + half_h)
        pygame.draw.line(self.screen, WHITE_BG, left, tip, stroke)
        pygame.draw.line(self.screen, WHITE_BG, tip, right, stroke)

    def _draw_dot(self, pos: Tuple[int, int], color=PASSED_COLOR) -> None:
        """Plain dot for stations beyond the 15-ahead countdown window.

        Copied from e235_1000.JapaneseDisplay.draw_marks's small_dot path.
        ``color`` defaults to PASSED_COLOR (circular's only dot state); the
        open-route variant passes INACTIVE_COLOR to dim passed stations.
        """
        # fmt: off
        # --- Dot params (adjust freely) ---
        radius = 5  # matches e235_1000 small_dot_radius
        # ----------------------------------
        # fmt: on
        cx, cy = int(pos[0]), int(pos[1])
        pygame.gfxdraw.filled_circle(self.screen, cx, cy, radius, color)
        pygame.gfxdraw.aacircle(self.screen, cx, cy, radius, color)

    def _draw_numbered_circle(self, pos: Tuple[int, int], minutes: int, with_minute_suffix: bool = False, is_current: bool = False) -> None:
        """Numbered countdown circle — verbatim primitive from
        e235_1000.draw_marks's active-range marker, sized larger via
        ``self.circle_outer_radius``.

        Two layers + digit:
          - Outer PASSED_COLOR full disk (every upcoming station). The visible
            ring effect comes from the green track band peeking around the
            disk — NOT from drawing a route-color ring explicitly.
          - Inner CURRENT_COLOR overlay only when ``is_current=True`` —
            mirrors e235_1000's ``if gi == curr_stop:`` gate.
          - Black countdown digit on top + optional ``(分)`` suffix at the
            farthest-ahead position (e235_0 specific — e235_1000 renders the
            digit as a separate text label above the bar).
        """
        # fmt: off
        # --- Numbered circle params (adjust freely) ---
        # `outer_radius` lives on self (self.circle_outer_radius) — shared with
        # _draw_approaching_arrow's tip placement.
        inner_disk_inset    = 2    # inner CURRENT_COLOR overlay inset (curr_stop only; matches e235_1000)
        suffix_x_gap        = 0    # gap between circle right edge and (分) suffix
        suffix_bottom_pad   = 2    # gap between (分) bottom and color bar bottom edge
        # ----------------------------------------------
        # fmt: on
        outer_radius = self.circle_outer_radius

        cx, cy = int(pos[0]), int(pos[1])
        # Outer disk — every upcoming station. Green band shows around it.
        pygame.gfxdraw.filled_circle(self.screen, cx, cy, outer_radius, PASSED_COLOR)
        pygame.gfxdraw.aacircle(self.screen, cx, cy, outer_radius, PASSED_COLOR)
        # Inner CURRENT_COLOR overlay — curr_stop only
        if is_current:
            inner_disk_r = outer_radius - inner_disk_inset
            pygame.gfxdraw.filled_circle(self.screen, cx, cy, inner_disk_r, CURRENT_COLOR)
            pygame.gfxdraw.aacircle(self.screen, cx, cy, inner_disk_r, CURRENT_COLOR)

        # box-center (get_rect(center)) is DELIBERATE — tabular countdown digits are
        # designed centered within their advance box, so this IS the optical center.
        # Ink-centering (baseline / glyph metrics, like the 5-station renderer) was
        # tried in #33 and reverted: it strips that designed balance and pulls
        # asymmetric glyphs (5 / 7) left. Do NOT "fix" this to ink-centering.
        img = self.font_circle.render(str(minutes), True, DARK_BG)
        self.screen.blit(img, img.get_rect(center=(cx, cy)))
        if with_minute_suffix:
            suffix_img = self.font_minute.render("(分)", True, DARK_BG)
            # (分) baseline lowered to sit `suffix_bottom_pad` px above the
            # color bar's bottom edge — IRL placement, NOT vertically centered
            # with the circle.
            bar_bottom_y = cy + self.track_stroke_w // 2
            suffix_y = bar_bottom_y - suffix_bottom_pad - suffix_img.get_height()
            self.screen.blit(suffix_img, (cx + outer_radius + suffix_x_gap, suffix_y))

    def _draw_pentagon(self, pos: Tuple[int, int], face_left: bool = False) -> None:
        """Red pentagon at current stop with uniform-scale breathing animation.

        Geometry: asymmetric pentagon — flat back at half-width=rect_half_w_back
        (= STOPS_WIDTH/2 = 21), apex side at half-width=rect_half_w_apex (4px
        shorter), apex extends triangle_d-px further. Direction-aware:
        ``face_left=True`` mirrors the apex to the left for top-row stops.

        Animation: red body shrinks/grows uniformly in BOTH axes around the
        center (cx, cy); halo + drop-shadow stay at max size (fixed bbox).
        At smallest, red height = track_stroke_w (= color bar height); width
        scales by the same factor. Triangle wave (constant velocity, no rest
        at extremes), period 2s; derived from pygame.time.get_ticks() for
        frame-rate independence.
        """
        # fmt: off
        # --- Pentagon static params (adjust freely) ---
        overhang             = 2                          # vertical overhang past row centerline (max state)
        rect_half_w_back     = STOPS_WIDTH / 2            # = 21 (flat back side from center)
        rect_half_w_apex     = STOPS_WIDTH / 2 - 1        # = 20 (apex side from center; 1px shorter)
        triangle_d           = 4                          # apex extension past rect's apex side
        inner_dot_r          = 5                          # interior light dot radius
        halo_offset          = 3                          # halo drop-shadow x-shift
        # --- Pentagon animation params (adjust freely) ---
        breath_period_s      = 1.2                        # full big→small→big cycle (0.6s single travel)
        # --------------------------------------------------
        # fmt: on
        cx, cy = pos

        half_h_max = STOPS_BAR_HEIGHT / 2 + overhang  # = 17 (red at max, fully extended)
        half_h_min = self.track_stroke_w / 2  # = 14 (red at min, height = color bar)
        scale_min = half_h_min / half_h_max  # ≈ 0.824

        # Triangle wave: 1 at cycle=0 (max), 0 at half cycle (min), back to 1.
        # Constant |velocity| — instant reversal at extremes, NO rest/lingering
        # at peaks (vs cosine, which has zero velocity at peaks).
        t_seconds = pygame.time.get_ticks() / 1000.0
        cycle = (t_seconds / breath_period_s) % 1.0
        phase = 1 - 2 * cycle if cycle < 0.5 else 2 * cycle - 1
        scale = scale_min + (1.0 - scale_min) * phase

        # Direction-aware geometry — pentagon at max size; red gets uniformly scaled.
        if face_left:
            rect_right_x = cx + rect_half_w_back
            rect_left_x = cx - rect_half_w_apex
            apex_x = rect_left_x - triangle_d
            max_points = [
                (rect_right_x, cy - half_h_max),
                (rect_right_x, cy + half_h_max),
                (rect_left_x, cy + half_h_max),
                (apex_x, cy),
                (rect_left_x, cy - half_h_max),
            ]
        else:
            rect_left_x = cx - rect_half_w_back
            rect_right_x = cx + rect_half_w_apex
            apex_x = rect_right_x + triangle_d
            max_points = [
                (rect_left_x, cy - half_h_max),
                (rect_left_x, cy + half_h_max),
                (rect_right_x, cy + half_h_max),
                (apex_x, cy),
                (rect_right_x, cy - half_h_max),
            ]

        # Uniformly scale max_points toward (cx, cy) for the breathing red body.
        red_points = [(cx + (px - cx) * scale, cy + (py - cy) * scale) for (px, py) in max_points]

        # Halo: drop-shadow x-shifted copies + filled fixed-size halo. The
        # fixed-size halo fill is what becomes visible (gray) around the red
        # body when red shrinks below max.
        draw_aapolygon(self.screen, PASSED_COLOR, [(i - halo_offset, j) for (i, j) in max_points])
        draw_aapolygon(self.screen, PASSED_COLOR, [(i + halo_offset, j) for (i, j) in max_points])
        draw_aapolygon(self.screen, PASSED_COLOR, max_points)
        # Red body (uniformly scaled)
        draw_aapolygon(self.screen, self.contrast_color, red_points)
        # Interior light dot — at center, constant size
        pygame.gfxdraw.filled_circle(self.screen, int(cx), int(cy), inner_dot_r, PASSED_COLOR)
        pygame.gfxdraw.aacircle(self.screen, int(cx), int(cy), inner_dot_r, PASSED_COLOR)

    # -------------------------------------------------------------------------
    # Station name labels (vertical text)
    # -------------------------------------------------------------------------

    def _draw_station_name(self, name: str, pos: Tuple[int, int], on_top_row: bool, is_major: bool = False, color=DARK_BG) -> None:
        """Draw vertical Japanese station name above (top row) or below (bottom row) its track position.

        Uses ``draw_1col_text_plain`` — tight back-to-back stacking, no
        compression, no distribution. Long names overflow rather than squish
        (multi-column wrap deferred until 高輪ゲートウェイ-class names land).

        ``is_major`` switches to the Heavy-weight font; the major-station set
        is the hardcoded module-level ``MAJOR_STATION_NAMES_BOLD`` (NOT
        derived from ``code_3``, since IRL Yamanote bolds a narrower set —
        e.g. 大崎 has code_3=OSK but is NOT bolded).

        ``color`` defaults to DARK_BG (active); the open-route variant passes
        INACTIVE_COLOR for passed stations.
        """
        if not name:
            return

        # fmt: off
        # --- Name layout params (adjust freely) ---
        # `clearance` = gap from station-position centerline to nearest name char.
        # = track_stroke_w/2 + 8 → 8px margin between the green color bar's
        # edge and the name (per IRL ref, applied symmetrically top + bottom).
        clearance = self.track_stroke_w // 2 + 8
        line_gap = 1   # extra px between vertically-stacked chars
        # ------------------------------------------
        # fmt: on

        font = self.font_station_bold if is_major else self.font_station
        line_pitch = font.get_height() + line_gap
        col_w = max(font.size(c)[0] for c in name)
        # Column left x = station-pos x - col_w/2 (so column is centered on station x)
        col_left_x = pos[0] - col_w // 2

        if on_top_row:
            bottom_y = pos[1] - clearance
            top_y = bottom_y - line_pitch * len(name)
            top_y = max(top_y, self.y_top + 2)  # cap at top of lower LCD area (overflow rather than truncate)
        else:
            top_y = pos[1] + clearance

        draw_1col_text_plain(font, name, col_left_x, top_y, color, self.screen, line_gap=line_gap)

    # -------------------------------------------------------------------------
    # Time formula — mirrors e235_1000 JapaneseDisplay.draw_times semantics
    # -------------------------------------------------------------------------

    def _compute_minutes_for_ahead(
        self,
        ahead: List[Tuple[int, int]],
        state,
        current_time: float,
    ) -> List[int]:
        """Compute countdown minutes for each ahead-station, mirroring the
        E235-1000 lower full-route bar's draw_times semantics.

        First station from cursor: ``max(1, stop["time"] - int(elapsed))``
        if moving, or ``stop["time"]`` static if at_station, or ``1`` if
        is_last_pa. Subsequent stations: cumulative addition of static
        ``stop["time"]`` values.
        """
        if not ahead:
            return []

        elapsed_minutes = 0.0
        if current_time > 0 and state.departure_time > 0:
            elapsed_minutes = (current_time - state.departure_time) / TIME_SCALE

        minutes_list: List[int] = []
        cumulative = 0
        for i, (stop_idx, _jy) in enumerate(ahead):
            stop = self.stops[stop_idx]
            t = stop.get("time", 0)
            if i == 0:
                if state.at_station:
                    cumulative = t
                elif state.is_last_pa:
                    cumulative = 1
                else:
                    cumulative = max(1, t - int(elapsed_minutes))
            else:
                cumulative += t
            minutes_list.append(int(cumulative))
        return minutes_list

    # -------------------------------------------------------------------------
    # Main draw entry point — matches the slot manager's expected interface
    # -------------------------------------------------------------------------

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the circular full-route view.

        Order:
          1. White background
          2. Green racetrack outline
          3. Plain dots for all present stations (baseline state)
          4. Numbered countdown circles for next 15 ahead (overpaints dots)
          5. Pentagon for current stop (overpaints whatever was at that pos)
          6. Station names (vertical text, top + bottom rows)
          7. Disclaimer at bottom
        """
        self._resync_tuneables()
        # 1. Background
        pygame.draw.rect(
            self.screen,
            WHITE_BG,
            pygame.Rect(0, self.y_top, S_WIDTH, self.lower_h),
        )

        # 2. Track
        self._draw_track()

        # 2.5 Direction-of-travel chevrons on each cap apex
        self._draw_direction_arrows()

        # 3. Plain dots — baseline render for every present station.
        # Numbered circles + pentagon paint over the dots they replace.
        for jy, pos in self.positions.items():
            self._draw_dot(pos)

        # 4. Numbered countdown circles for next 15 ahead.
        # Include curr_stop when APPROACHING (train hasn't arrived yet, so its
        # time-to-arrival belongs in the countdown set; chevron in step 5
        # paints over the circle).
        include_curr = not state.at_station
        ahead = self._ahead_indices(state.curr_stop, include_curr=include_curr)
        minutes_list = self._compute_minutes_for_ahead(ahead, state, current_time)
        for i, ((stop_idx, jy), minutes) in enumerate(zip(ahead, minutes_list)):
            pos = self.positions.get(jy)
            if pos is None:
                continue
            with_suffix = i == len(ahead) - 1
            is_current = stop_idx == state.curr_stop
            self._draw_numbered_circle(pos, minutes, with_minute_suffix=with_suffix, is_current=is_current)

        # 5. Train indicator at current stop — pentagon (STOPPING) or chevron
        # (APPROACHING). face_left when on top row (inner-loop = R→L).
        if 0 <= state.curr_stop < len(self.stops):
            curr_jy = _parse_jy_code(self.stops[state.curr_stop].get("sta_code", ""))
            if curr_jy is not None:
                pos = self.positions.get(curr_jy)
                if pos is not None:
                    on_top = curr_jy in JY_TOP_LR_SCREEN
                    if state.at_station:
                        self._draw_pentagon(pos, face_left=on_top)
                    else:
                        # APPROACHING — animated cascade between last and curr.
                        # None = out-of-scope (cross-row, no-previous) → static
                        # fallback. Empty list = in-scope but rest-gap frame →
                        # draw nothing (don't flash a static chev mid-rest).
                        chevs = self._compute_chevron_animation_state(state.curr_stop)
                        if chevs is None:
                            dx_curr = -1 if on_top else 1
                            tip_x_static = pos[0] - dx_curr * (self.circle_outer_radius + 1)
                            self._draw_approaching_arrow(tip_x_static, pos[1], face_left=on_top)
                        else:
                            for tip_x, tip_y, face_left, alpha in chevs:
                                self._draw_approaching_arrow(tip_x, tip_y, face_left, alpha)

        # 6. Station names (vertical text)
        for s in self.stops:
            jy = _parse_jy_code(s.get("sta_code", ""))
            if jy is None:
                continue
            pos = self.positions.get(jy)
            if pos is None:
                continue
            on_top = jy in JY_TOP_LR_SCREEN
            name = s.get("name", "")
            is_major = name in MAJOR_STATION_NAMES_BOLD
            self._draw_station_name(name, pos, on_top_row=on_top, is_major=is_major)

        # 7. Disclaimer — left-bottom-anchored to lower-LCD area.
        # Yamanote IRL omits the "一部区間では時間を表示しません。" tail of the standard disclaimer
        # (Yamanote always shows times — no "some sections don't display times" caveat).
        # fmt: off
        # --- Disclaimer params (adjust freely) ---
        disclaimer_text = _DISCLAIMER
        left_x      = 8   # left margin from screen edge
        bottom_pad  = 4   # gap between disclaimer baseline and bottom of lower LCD
        # -----------------------------------------
        # fmt: on
        img = self.font_disclaimer.render(disclaimer_text, True, DARK_BG)
        blit_y = self.y_top + self.lower_h - bottom_pad - img.get_height()
        self.screen.blit(img, (left_x, blit_y))

    # NOTE: deliberately NOT implemented yet — interface stub returning None.
    # Wire up when click-jump for the circular full-route lands. Reserved for:
    # hit-testing each station's pentagon/numbered-circle/dot at its
    # `self.positions[jy]` screen coord (use `self.circle_outer_radius` as the
    # pick radius for circle/dot; pentagon hit-box is its bounding rect).
    # Sibling reference: e235_1000.JapaneseDisplay.hit_test (linear bar). This model's layout is a
    # curved racetrack, not a linear cell grid, so hit-testing is NEAREST-STATION within a radius:
    # each station's screen dot lives in self.positions (coords in the same LCD-local space as the
    # click, per __init__ y_top = UPPER_HEIGHT — the caller already subtracted the debug band).
    _HIT_RADIUS = 40  # px — nearest station beyond this → miss (click landed on empty track / disclaimer)

    def _pos_for_stop(self, idx: int) -> Optional[Tuple[int, int]]:
        """Screen position of stop `idx`. Circular keys self.positions by JY code; OpenRoute
        (index-keyed positions) overrides this."""
        jy = _parse_jy_code(self.stops[idx].get("sta_code", ""))
        return self.positions.get(jy) if jy is not None else None

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Map an LCD-local click to a stop index (click-to-jump): the nearest station dot within
        _HIT_RADIUS, else None. Past-dest filtering lives in the caller (PASimulator) — circular
        routes skip it, so every stop is clickable."""
        best_idx, best_d2 = None, None
        for idx in range(len(self.stops)):
            pos = self._pos_for_stop(idx)
            if pos is None:
                continue
            dx, dy = mx - pos[0], my - pos[1]
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2:
                best_idx, best_d2 = idx, d2
        if best_idx is None or best_d2 > self._HIT_RADIUS**2:
            return None
        return best_idx


# =============================================================================
# Open-route full-route display (non-Yamanote best-effort)
# =============================================================================


class OpenRouteFullRouteDisplay(CircularFullRouteDisplay):
    """E235-0 full-route renderer for NON-Yamanote (linear) routes.

    The Yamanote-style racetrack with **one cap removed** — a horseshoe, not a
    loop. Bottom row runs L→R from the origin; folds up the right cap; top row
    runs R→L to the terminus. The left side is open: the two rows terminate at
    independent flat edges (route origin + destination).

    E235-0 is Yamanote-only IRL, so this is a best-effort *invented* look for
    out-of-spec routes loaded into E235-0 (no IRL reference) — replacing the
    old E235-1000 linear fallback. Per CLAUDE.md "Per-model IRL line scope".

    Reuses the parent's marker primitives (dot / numbered circle / pentagon /
    approaching arrow / chevron timeline / name / minute chain) verbatim;
    overrides only the JY-keyed pieces (layout, track shape, ahead/prev walk,
    direction arrow) to be **stop-index keyed** and linear. Adds passed-station
    dimming (gi < curr_stop → INACTIVE_COLOR), which the circular lacks.

    Layout decisions (see docs/wip/WIP_calibration_editor.md / docs/DISPLAY_E235.md):
      - Split: bottom = stops[0 : ⌈N/2⌉], top = the rest.
      - No sweep — fit-to-rows by shrinking pitch (longest route in scope is
        Keihin-Tōhoku at 46 → 23/row; revisit if cramped).
    """

    _OpenBandGeom = namedtuple("_OpenBandGeom", "cy v_outer border_outer straight_right")

    def _band_geometry(self) -> "_OpenBandGeom":
        """Extends the parent's shared band geometry (``cy`` / ``v_outer`` /
        ``border_outer``) with ``straight_right`` — the open route's
        ``_build_positions`` and ``_draw_passed_band`` (its gray clips must align
        to the fold cap) both key off it. The shared three come from ``super()``
        so a track-shape edit lands once for BOTH the circular and open
        renderers; only ``straight_right`` (open-route-specific) is added here.
        Callers keep their OWN local derivations (``straight_left`` /
        ``straight_w`` = stop layout, may reclaim the left margin later;
        ``v_inner`` / ``border_inner`` = the inner white hole)."""
        base = super()._band_geometry()
        return self._OpenBandGeom(
            cy=base.cy,
            v_outer=base.v_outer,
            border_outer=base.border_outer,
            straight_right=S_WIDTH - self.track_right_pad - base.border_outer,
        )

    def _build_positions(self) -> None:
        """Index-keyed two-row layout, right-aligned at the fold (right cap).

        ``self.positions`` is keyed by **stop index** here (the parent keys it
        by JY code). Pitch comes from the longer (bottom) row so it fills the
        straight section; the shorter top row reuses the pitch and right-aligns
        at the fold, its open-left end floating.
        """
        n = len(self.stops)
        n_bottom = (n + 1) // 2  # ceil — bottom row gets the larger/equal half
        n_top = n - n_bottom

        # Straight-section x-range — same derivation as the parent's circular
        # layout (inside both cap corner-arcs). The open-left side has no cap to
        # clear, but keeping the range symmetric with the circular keeps pitch
        # parallel; the dead left margin is reclaimed only if cramped (future).
        g = self._band_geometry()
        straight_left = self.track_left_pad + g.border_outer  # LOCAL: open-left layout, may reclaim margin later
        straight_right = g.straight_right
        straight_w = straight_right - straight_left

        cy = g.cy
        top_row_y = cy - self.curve_v_radius
        bot_row_y = cy + self.curve_v_radius

        self.slot_w = straight_w / max(n_bottom, 1)
        x_fold = straight_right - self.slot_w / 2  # rightmost slot center (= fold)

        self.positions = {}
        # Bottom row: indices 0..n_bottom-1, L→R. index 0 = origin (bottom-left),
        # index n_bottom-1 = at the fold (bottom-right).
        for i in range(n_bottom):
            x = x_fold - (n_bottom - 1 - i) * self.slot_w
            self.positions[i] = (int(x), bot_row_y)
        # Top row: indices n_bottom..n-1, R→L. first top stop folds up at the
        # fold (top-right); last stop = terminus (top-left, open end).
        for k in range(n_top):
            x = x_fold - k * self.slot_w
            self.positions[n_bottom + k] = (int(x), top_row_y)

        # Flat band edges for the open (left) side — half a slot left of each
        # row's leftmost station. _draw_track whitens left of these.
        self._open_edge_bottom = int(self.positions[0][0] - self.slot_w / 2) if n_bottom else straight_left
        self._open_edge_top = int(self.positions[n - 1][0] - self.slot_w / 2) if n_top else self._open_edge_bottom

    def _draw_track(self, band_color=None) -> None:
        """Draw the parent's closed racetrack, then open the left side.

        Whitens the left cap (split at the centerline) plus the band left of
        each row's leftmost station, leaving two flat terminal edges. The right
        cap stays as the fold.

        ``band_color`` defaults to the route color; ``_draw_passed_band`` calls
        this under a clip with INACTIVE_COLOR to re-stroke the passed segment
        gray while preserving the exact band geometry (inner white hole, open
        ends, rounded cap).
        """
        color = band_color if band_color is not None else self.color
        g = self._band_geometry()
        cy, v_outer = g.cy, g.v_outer
        border_outer = max(1, g.border_outer)  # clamp for border_radius (draw arg, not a coordinate)
        v_inner = max(1, self.curve_v_radius - self.track_stroke_w // 2)  # LOCAL: inner white hole
        border_inner = max(1, v_inner - self.vert_seg_h_inner // 2)

        outer_rect = pygame.Rect(
            self.track_left_pad,
            cy - v_outer,
            S_WIDTH - self.track_left_pad - self.track_right_pad,
            2 * v_outer,
        )
        pygame.draw.rect(self.screen, color, outer_rect, border_radius=border_outer)
        inner_rect = pygame.Rect(
            self.track_left_pad + self.track_stroke_w,
            cy - v_inner,
            S_WIDTH - self.track_left_pad - self.track_right_pad - 2 * self.track_stroke_w,
            2 * v_inner,
        )
        pygame.draw.rect(self.screen, WHITE_BG, inner_rect, border_radius=border_inner)

        # Open the left side. Two white rects split at cy: top half trims the
        # top band to _open_edge_top, bottom half trims the bottom band to
        # _open_edge_bottom; together they erase the left cap.
        pad = 2
        pygame.draw.rect(
            self.screen,
            WHITE_BG,
            pygame.Rect(0, cy - v_outer - pad, self._open_edge_top, v_outer + pad),
        )
        pygame.draw.rect(
            self.screen,
            WHITE_BG,
            pygame.Rect(0, cy, self._open_edge_bottom, v_outer + pad),
        )

    def _draw_passed_band(self, curr: int) -> None:
        """Re-stroke the band gray (INACTIVE_COLOR) for the passed portion —
        the route bar dims behind the train, matching E235-1000's per-cell
        ``gi < cursor_pos`` graying. Done by clip-redrawing _draw_track(gray)
        over the passed regions of the folded path; the green band is drawn
        first (full) by the caller.

        The green/gray boundary sits at the midpoint between stop ``curr-1`` and
        ``curr`` (so the current cell stays green and everything behind it grays
        — same boundary semantics as the per-cell linear bar).
        """
        if curr <= 0:
            return  # at the origin nothing is behind the train
        n = len(self.stops)
        n_bottom = (n + 1) // 2
        g = self._band_geometry()
        cy, v_outer, straight_right = g.cy, g.v_outer, g.straight_right
        pad = 3

        clips: List[pygame.Rect] = []
        if curr < n_bottom:
            # Curr on the bottom row — only the bottom band left of the
            # curr-1↔curr midpoint is passed.
            bx = int((self.positions[curr - 1][0] + self.positions[curr][0]) / 2)
            clips.append(pygame.Rect(0, cy, bx, v_outer + pad))  # bottom band, lower half
        else:
            # Curr on the top row — the whole bottom band + the fold cap are
            # passed, plus the top band to the RIGHT of the boundary (top row
            # travels R→L, so "behind" is rightward).
            clips.append(pygame.Rect(0, cy, S_WIDTH, v_outer + pad))  # whole bottom band
            cap_left = int(straight_right)
            clips.append(pygame.Rect(cap_left, cy - v_outer - pad, S_WIDTH - cap_left + pad, 2 * (v_outer + pad)))  # fold cap
            if curr == n_bottom:
                btx = self.positions[curr][0]  # first top stop: only the cap crossing is passed
            else:
                btx = int((self.positions[curr - 1][0] + self.positions[curr][0]) / 2)
            clips.append(pygame.Rect(int(btx), cy - v_outer - pad, S_WIDTH - int(btx) + pad, v_outer + pad))  # top band right of boundary

        for r in clips:
            self.screen.set_clip(r)
            self._draw_track(band_color=INACTIVE_COLOR)
        self.screen.set_clip(None)

    def _draw_direction_arrows(self) -> None:
        """Only the fold (right) cap carries a direction chevron — the open
        (left) side has no cap. Travel folds bottom→top on the right → ^."""
        # fmt: off
        arrow_w = 28
        arrow_h = 6
        stroke  = 4
        # fmt: on
        cy = self.y_top + (self.track_top_y + self.track_bottom_y) // 2
        right_band_cx = S_WIDTH - self.track_right_pad - self.track_stroke_w // 2
        self._draw_chevron(right_band_cx, cy, arrow_w, arrow_h, stroke, point_down=False)

    def _ahead_indices(self, curr_stop: int, include_curr: bool = False) -> List[Tuple[int, int]]:
        """Linear next-N **stopping** stations ahead — passing stations (empty
        ``pa``) are skipped so they get no countdown number (they render as
        chevrons instead, like E235-1000). ``curr_stop`` is itself a stopping
        station (a PA target); it's prepended when ``include_curr`` (APPROACHING).

        Skipping passing stations also keeps the minute chain safe: passing
        stations carry ``time: None``, which would crash the inherited
        cumulative sum. The 2nd tuple slot is the parent's jy code, unused here
        — filled with the stop index to keep _compute_minutes_for_ahead happy.
        """
        n = len(self.stops)
        if not (0 <= curr_stop < n):
            return []
        result: List[Tuple[int, int]] = []
        if include_curr:
            result.append((curr_stop, curr_stop))
        for idx in range(curr_stop + 1, n):
            if not self.stops[idx].get("pa"):
                continue  # passing station — no number, no time
            result.append((idx, idx))
            if len(result) >= self.NUMBERED_AHEAD_COUNT:
                break
        return result

    def _compute_chevron_animation_state(self, curr_stop: int) -> Optional[List[Tuple[float, float, bool, float]]]:
        """Linear variant: previous station is curr_stop-1. At the origin (no
        previous) → None (static fallback). At the fold (curr = first top stop,
        a cross-row pair) synthesize a phantom previous one slot to the RIGHT on
        curr's row (top travels R→L) so the chev sweeps along the top row rather
        than across the fold — mirrors the parent's cross-row phantom."""
        n = len(self.stops)
        if not (0 <= curr_stop < n):
            return None
        curr_pos = self.positions.get(curr_stop)
        if curr_pos is None:
            return None
        prev = curr_stop - 1
        if prev < 0:
            return None
        prev_pos = self.positions.get(prev)
        if prev_pos is None:
            return None
        n_bottom = (n + 1) // 2
        if (curr_stop >= n_bottom) != (prev >= n_bottom):
            last_pos = (curr_pos[0] + self.slot_w, curr_pos[1])
        else:
            last_pos = prev_pos
        return self._chevron_frames(last_pos, curr_pos)

    def _draw_passing_chevron(self, pos: Tuple[int, int], face_left: bool) -> None:
        """Light chevron marker for a passing station (empty ``pa``) — the
        train runs through without stopping. Carried over from E235-1000's
        ``draw_marks`` passing-arrow (PASSED_COLOR, no halo). Points in the
        row's travel direction: bottom row L→R (right), top row R→L (left)."""
        # fmt: off
        w      = 14                       # chevron width (= e235_1000 passing_arrow_w)
        h      = self.track_stroke_w - 8  # fits inside the color bar with margin
        stroke = 6                        # body thickness (= e235_1000 passing_arrow_stroke)
        # fmt: on
        cx, cy = int(pos[0]), int(pos[1])
        x = int(cx - w / 2)
        y = int(cy - h / 2)
        pts = arrow_points(x, y, w, h, stroke)
        if face_left:
            mid = x + w / 2
            pts = [(2 * mid - px, py) for (px, py) in pts]
        draw_aapolygon(self.screen, PASSED_COLOR, pts)

    def _pos_for_stop(self, idx: int) -> Optional[Tuple[int, int]]:
        """OpenRoute keys self.positions by stop index (not JY code) — override the parent's
        JY lookup so nearest-station hit_test (inherited) resolves correctly."""
        return self.positions.get(idx)

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the open horseshoe. Same draw order as the circular parent,
        plus the carried-over skip semantics: the gray/dim boundary follows the
        animated ``cursor_pos`` (lags curr_stop during a skip), passing stations
        (empty ``pa``) render as chevrons not numbered circles, and passing-
        station names always dim. The pointer cascade is unchanged (anchored on
        curr_stop)."""
        self._resync_tuneables()
        n = len(self.stops)
        n_bottom = (n + 1) // 2
        curr = state.curr_stop
        cursor = state.cursor_pos  # animated; == curr when not mid-skip

        # 1. Background
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(0, self.y_top, S_WIDTH, self.lower_h))
        # 2. Track (open) — green full, then gray the passed portion behind the
        # cursor, then the fold-cap direction chevron.
        self._draw_track()
        self._draw_passed_band(cursor)
        self._draw_direction_arrows()
        # 3. Baseline per-station markers. passed (gi < cursor) → dim dot;
        # active passing station → light chevron; active stopping station →
        # light dot (numbered circles + pointer overpaint as needed).
        for idx, pos in self.positions.items():
            if idx < cursor:
                self._draw_dot(pos, color=INACTIVE_COLOR)
            elif not self.stops[idx].get("pa"):
                self._draw_passing_chevron(pos, face_left=(idx >= n_bottom))
            else:
                self._draw_dot(pos, color=PASSED_COLOR)
        # 4. Numbered countdown circles for next 15 STOPPING stations ahead
        # (include curr when APPROACHING; passing stations skipped).
        include_curr = not state.at_station
        ahead = self._ahead_indices(curr, include_curr=include_curr)
        minutes_list = self._compute_minutes_for_ahead(ahead, state, current_time)
        for i, ((stop_idx, _jy), minutes) in enumerate(zip(ahead, minutes_list)):
            pos = self.positions.get(stop_idx)
            if pos is None:
                continue
            with_suffix = i == len(ahead) - 1
            self._draw_numbered_circle(pos, minutes, with_minute_suffix=with_suffix, is_current=(stop_idx == curr))
        # 5. Train indicator at curr — pentagon (STOPPING) / animated chevron (APPROACHING).
        if 0 <= curr < n:
            pos = self.positions.get(curr)
            if pos is not None:
                on_top = curr >= n_bottom
                if state.at_station:
                    self._draw_pentagon(pos, face_left=on_top)
                else:
                    chevs = self._compute_chevron_animation_state(curr)
                    if chevs is None:
                        dx_curr = -1 if on_top else 1
                        tip_x_static = pos[0] - dx_curr * (self.circle_outer_radius + 1)
                        self._draw_approaching_arrow(tip_x_static, pos[1], face_left=on_top)
                    else:
                        for tip_x, tip_y, face_left, alpha in chevs:
                            self._draw_approaching_arrow(tip_x, tip_y, face_left, alpha)
        # 6. Station names — dim (INACTIVE_COLOR) when passed (gi < cursor) OR a
        # passing station (always dim, per E235-1000); else active DARK_BG.
        for idx, pos in self.positions.items():
            name = self.stops[idx].get("name", "")
            is_passing = not self.stops[idx].get("pa")
            self._draw_station_name(
                name,
                pos,
                on_top_row=(idx >= n_bottom),
                is_major=name in MAJOR_STATION_NAMES_BOLD,
                color=INACTIVE_COLOR if (idx < cursor or is_passing) else DARK_BG,
            )
        # 7. Disclaimer — left-bottom-anchored (standard text; non-Yamanote may
        # have non-time sections, so the full disclaimer is kept).
        # fmt: off
        disclaimer_text = _DISCLAIMER
        left_x      = 8
        bottom_pad  = 4
        # fmt: on
        img = self.font_disclaimer.render(disclaimer_text, True, DARK_BG)
        blit_y = self.y_top + self.lower_h - bottom_pad - img.get_height()
        self.screen.blit(img, (left_x, blit_y))


# =============================================================================
# Japanese 5-Station Display (E235-0 EIGHT-slot replacement, Phase 1)
# =============================================================================


class JapaneseFiveStationDisplay:
    """Universal EIGHT-slot replacement for E235-0 — 5-station stopping view.

    Renders the hand-drawn green band (Tier-2 mask PNG, baked with the route
    color in `_bake_band`) plus five station markers along it (Tier-1
    `_TUNEABLES_FIVE_STATION` positions): the current stop as a red pentagon
    at the bottom, the next four stops as numbered countdown circles going up.
    Station kanji names sit to the left of each marker. The marker primitives
    (`_draw_numbered_circle`, `_draw_pentagon`) are copied from this module's
    `CircularFullRouteDisplay` per conventions.md § "Forking a sibling-model
    renderer: copy primitives, don't reinvent".

    Same interface as JapaneseEightStationDisplay (the class it replaces):
    `show_stops(state, current_time)` + `hit_test`.
    """

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.color = route_data.get("color", [116, 193, 30])
        self.contrast_color = route_data.get("contrast_color", [224, 54, 37])
        # Circular route (Yamanote): stops[0] and stops[-1] are the same station
        # (the doubled loop terminal). When circular, the 5-station view's
        # next-stop walk wraps past the terminal instead of dead-ending. Same
        # idiom as e235_1000.JapaneseDisplay / CircularFullRouteDisplay.
        self._circular = bool(stops) and stops[0].get("name") == stops[-1].get("name")
        # Bake the band mask once with the route line color (Yamanote green by
        # default). See _bake_band / docs/wip/WIP_calibration_editor.md § "Two-tier".
        self._band = _bake_band(self.color)
        # Gray base band — shown below the rising green during the fill animation.
        self._band_gray = _bake_band(_BAND_GRAY)
        # Precompute the band centerline (the arc-length path the green fill
        # sweeps along; its leading front follows this curve). See
        # _build_fill_centerline.
        self._build_fill_centerline()
        # Reusable scratch mask for the fill reveal — cleared + restamped each
        # animation frame (avoids a per-frame full-screen surface allocation).
        self._fill_reveal = pygame.Surface((S_WIDTH, S_HEIGHT), pygame.SRCALPHA)

        # Fill animation state. _fill_start = current_time when the current reveal
        # began (None = not entered yet → static full band). Restarted ONLY by
        # on_slot_enter (the manager's slot-enter hook), never self-detected: the
        # renderer cannot tell a draw stall or a stopped→moving marker flip from a
        # real re-enter, which is exactly the second-clock bug this replaced.
        self._fill_start: Optional[float] = None

        # Inline transfer panel — data path mirrors the parent
        # TransferInfoDisplay so the filtered entry ORDER matches the
        # horizontal slot. Pure-function reuse (apply_transfer_filter /
        # resolve_entry) per displays/transfer_info.py; load lines+stations
        # once here. line_code / transfer_view optional (out-of-spec routes
        # render unfiltered — soft floor per CLAUDE.md scope table).
        root = project_root()
        self._tp_lines = json.loads((root / "data" / "lines.json").read_text(encoding="utf-8"))
        self._tp_stations = json.loads((root / "data" / "stations.json").read_text(encoding="utf-8"))
        self._tp_line_code = route_data.get("line_code")
        self._tp_transfer_view = route_data.get("transfer_view")
        self._tp_icon_cache: dict = {}

    def _build_fill_centerline(self) -> None:
        """Precompute the band centerline the green fill sweeps along.

        Derived DIRECTLY from the band mask's own geometry — the per-row
        horizontal centroid of the fill, bottom → top (see
        ``_extract_band_centerline``). The fill is parameterised by ARC LENGTH
        along this curve and cuts its front perpendicular to the local tangent,
        so the leading edge stays diagonal to the band at every height. Stores
        per-sample point / cumulative arc length / unit-normal arrays + total
        length, all read each frame in show_stops. Precomputed once at __init__.
        """
        pts = _extract_band_centerline()
        # Cumulative arc length per sample.
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
        # Unit normal per sample (perpendicular to the local tangent).
        n = len(pts)
        normals: List[Tuple[float, float]] = []
        for i in range(n):
            if i == 0:
                tx, ty = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            elif i == n - 1:
                tx, ty = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
            else:
                tx, ty = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
            mag = math.hypot(tx, ty) or 1.0
            normals.append((-ty / mag, tx / mag))
        self._fill_path = pts
        self._fill_cum = cum
        self._fill_normal = normals
        self._fill_len = cum[-1] if cum else 0.0

    def _font(self, name: str, size: float, draws=None):
        """Resolve a font by filename + size. Caching lives in `font_atlas`.

        # CONTRACT: every font in this module resolves here or through
        # font_atlas.lcd_font() directly — never a bare pygame.font.Font().
        # ShinGo is served from the baked atlas in a build shipping no font
        # files; a bare construct works in dev and raises there.
        # See docs/wip/WIP_font_atlas.md.
        """
        return font_atlas.lcd_font(name, size, draws=draws)

    def on_slot_enter(self, current_time: float) -> None:
        """Manager hook — the EIGHT (5-station) slot just genuinely became
        visible; restart the bottom-up green band reveal from here. The manager
        (``LowerDisplay._on_slot_entered`` → ``apply_slot``) is the SOLE trigger;
        the renderer never self-detects re-entry (see ``__init__``)."""
        self._fill_start = current_time

    # -------------------------------------------------------------------------
    # Main draw entry point
    # -------------------------------------------------------------------------

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Fill bg white, blit the tinted band, then draw the 5 station markers.

        Marker 0 = current stop (red pentagon when STOPPING); markers 1..4 =
        next four stops as numbered countdown circles. Names sit left of each.
        """
        self.screen.fill(WHITE_BG, ARC_RECT)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(ARC_RECT)
        try:
            # --- Band fill animation (bottom-up green reveal on slot-enter) ---
            # _fill_start is set by on_slot_enter (the manager's slot-enter hook);
            # this method only RENDERS the reveal, it never triggers it — a draw
            # stall or a stopped→moving marker flip must not restart the sweep.
            if current_time <= 0:
                progress = 1.0  # static/frozen frame (screenshot, --edit) → show full band
            elif self._fill_start is None:
                progress = 1.0
            else:
                raw_t = min(1.0, max(0.0, (current_time - self._fill_start) / _BAND_FILL_DURATION))
                progress = raw_t**_BAND_FILL_EASE_POWER  # ease-in: accelerates toward the top

            if progress >= 1.0:
                # Animation complete — blit green band, no gray needed.
                self.screen.blit(self._band, (0, 0))
            else:
                # Gray base covers the whole band; the green reveal is stamped
                # over it below (the detailed block owns the sweep description).
                self.screen.blit(self._band_gray, (0, 0))

                # --- Masked reveal (feathered front, follows the band curve) ---
                # Parameterised by ARC LENGTH along the precomputed centerline
                # (self._fill_*, built in _build_fill_centerline). Reveal is
                # stamped as per-segment corridor quads, each perpendicular to
                # the local tangent — so the leading front stays DIAGONAL to the
                # curve at every height, not one global angle. Green alpha ramps
                # 0 → 255 across _BAND_FILL_FEATHER px of arc length trailing the
                # front, for a smooth edge. The reveal mask is multiplied into a
                # copy of the green band via BLEND_RGBA_MULT (scales only the
                # band's alpha; RGB green stays). pygame.draw.polygon writes the
                # color's alpha directly (no blend) — same as the old hard erase.
                pts = self._fill_path
                cum = self._fill_cum
                nrm = self._fill_normal
                w = _BAND_FILL_HALF_WIDTH
                feather = max(1.0, float(_BAND_FILL_FEATHER))
                front_s = progress * self._fill_len
                solid = front_s - feather  # ≤ solid: full green; (solid, front_s]: ramp; > front_s: hidden

                reveal = self._fill_reveal
                reveal.fill((0, 0, 0, 0))  # clear last frame's stamp
                prev = None
                for i in range(len(pts)):
                    if cum[i] > front_s:
                        break
                    if cum[i] <= solid:
                        a = 255
                    else:
                        a = max(0, min(255, int(round(255 * (1.0 - (cum[i] - solid) / feather)))))
                    if prev is not None:
                        (ax, ay), (bx, by) = pts[prev], pts[i]
                        (nax, nay), (nbx, nby) = nrm[prev], nrm[i]
                        pygame.draw.polygon(
                            reveal,
                            (255, 255, 255, a),
                            [
                                (ax + nax * w, ay + nay * w),
                                (ax - nax * w, ay - nay * w),
                                (bx - nbx * w, by - nby * w),
                                (bx + nbx * w, by + nby * w),
                            ],
                        )
                    prev = i

                band_copy = self._band.copy()
                band_copy.blit(reveal, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(band_copy, (0, 0))
            # --- end band fill animation ---

            t = _TUNEABLES_FIVE_STATION
            curr = state.curr_stop
            # Index sequence for the up-to-5 markers (curr + 4 ahead; wraps past
            # the loop terminal on a circular route). Drives both the markers and
            # the cumulative minutes so they stay aligned.
            vis = self._visible_stop_indices(curr)
            minutes = self._ahead_minutes(state, current_time, vis)
            for k, idx in enumerate(vis):
                pos = (t[f"m{k}_x"], t[f"m{k}_y"])
                stop = self.stops[idx]
                gpos = (t[f"g{k}_x"], t[f"g{k}_y"])  # badge+name group anchor
                # Marker on the band first, then the badge + name group.
                if k == 0:
                    if state.at_station:
                        verts = [(t[f"v{j}_x"], t[f"v{j}_y"]) for j in range(5)]
                        self._draw_pentagon(verts, (t["m0_x"], t["m0_y"]), t["m0_dr"])
                    else:
                        cx, cy = int(t["m0_x"]), int(t["m0_y"])
                        r = int(t["m0_circle_r"])
                        # Outer disk in PASSED_COLOR, inner overlay in CURRENT_COLOR —
                        # mirrors CircularFullRouteDisplay._draw_numbered_circle is_current=True branch.
                        pygame.gfxdraw.filled_circle(self.screen, cx, cy, r, PASSED_COLOR)
                        pygame.gfxdraw.aacircle(self.screen, cx, cy, r, PASSED_COLOR)
                        inner_r = r - int(t["m0_circle_inset"])
                        pygame.gfxdraw.filled_circle(self.screen, cx, cy, inner_r, CURRENT_COLOR)
                        pygame.gfxdraw.aacircle(self.screen, cx, cy, inner_r, CURRENT_COLOR)
                        # Minutes to current target station — the first-station
                        # value of the E235-1000-aligned cumulative chain.
                        cur_min = self._first_stop_minutes(state, current_time)
                        digit_font = self._font("HelveticaNeue-Bold.otf", t["m0_ts"])
                        img = digit_font.render(str(cur_min), True, DARK_BG)
                        glyphs = [g for g in digit_font.metrics(str(cur_min)) if g]
                        maxy = max(g[3] for g in glyphs)
                        miny = min(g[2] for g in glyphs)
                        top = cy + (maxy + miny) / 2.0 - digit_font.get_ascent()
                        self.screen.blit(img, (cx - img.get_width() / 2.0, top))
                        arr_x, arr_y, arr_halo_a, arr_body_a = self._compute_five_station_arrow_animation()
                        self._draw_five_station_approaching_arrow(
                            arr_x,
                            arr_y,
                            t["a0_angle"],
                            t["a0_scale"],
                            t["a0_halo_w"],
                            halo_alpha=arr_halo_a,
                            body_alpha=arr_body_a,
                        )
                elif k - 1 < len(minutes):
                    # Digit size = per-station tuneable m<N>_ts (eyeball pass;
                    # radius→size law to be derived from the tuned values).
                    radius = t[f"m{k}_r"]
                    m = minutes[k - 1]
                    # Passing station (out-of-spec skip route) → m is None → empty
                    # ring, no digit, no font needed.
                    digit_font = self._font("HelveticaNeue-Bold.otf", t[f"m{k}_ts"]) if m is not None else None
                    self._draw_numbered_circle(pos, m, radius, digit_font)
                self._draw_jy_badge(stop, gpos, t[f"g{k}_b"])
                self._draw_station_name(stop.get("name", ""), gpos, t[f"g{k}_ns"], t[f"g{k}_ni"])

            # Inline transfer panel — left column (target station's transfers).
            self._draw_transfer_panel(state)
        finally:
            self.screen.set_clip(old_clip)

        # Small JR disclaimer line at the screen's bottom-left — copied from
        # CircularFullRouteDisplay. Drawn after the clip restore so it sits
        # unclipped at the very bottom of the lower LCD.
        # fmt: off
        disc_text  = _DISCLAIMER
        disc_x     = ARC_RECT.left + 8   # left margin from screen edge
        disc_pad_b = 4                   # gap from the bottom edge
        disc_size  = 9                   # ShinGoPr6N point size (matches full-route)
        # fmt: on
        disc_font = self._font("ShinGoPr6N-Medium.otf", disc_size, draws=lit(_DISCLAIMER))
        disc_img = disc_font.render(disc_text, True, DARK_BG)
        disc_y = ARC_RECT.bottom - disc_pad_b - disc_img.get_height()
        self.screen.blit(disc_img, (disc_x, disc_y))

    def _first_stop_minutes(self, state, current_time: float) -> int:
        """Minute value for the current-target station (the chain's first stop),
        valid for ANY state — mirrors E235-1000 draw_times: static incoming
        `time` when stopped, the `is_last_pa` floor of 1, else the countdown of
        the current segment. NOTE: all current callers are gated to APPROACHING
        (the m0 digit and the `_ahead_minutes` base both run only when
        `not at_station`), so the `at_station` branch isn't reached today; it's
        kept so the helper stays correct if a stopped-state caller is ever added.
        """
        t = self.stops[state.curr_stop].get("time", 0)
        if state.at_station:
            return t
        if getattr(state, "is_last_pa", False):
            return 1
        elapsed = 0
        if current_time > 0 and state.departure_time > 0:
            elapsed = int((current_time - state.departure_time) / TIME_SCALE)
        return max(1, t - elapsed)

    def _visible_stop_indices(self, curr: int) -> List[int]:
        """Indices of the up-to-5 stops the view shows: ``curr`` first, then the
        next four ahead. On a CIRCULAR route (``self._circular`` — the doubled
        loop terminal, stops[0].name == stops[-1].name) the walk wraps with
        modulo + name-dedup so the view keeps extending past the terminal (大崎)
        instead of dead-ending; the duplicate terminal entry is skipped. On a
        linear route it simply stops at the last stop. Mirrors
        CircularFullRouteDisplay._ahead_indices (sta_code dedup there → name
        dedup here, matching this class's circular-flag idiom)."""
        n = len(self.stops)
        if not (0 <= curr < n):
            return []
        out = [curr]
        if self._circular:
            seen = {self.stops[curr].get("name")}
            for offset in range(1, 2 * n):
                idx = (curr + offset) % n
                name = self.stops[idx].get("name")
                if name in seen:
                    continue
                out.append(idx)
                seen.add(name)
                if len(out) >= 5:
                    break
        else:
            for k in range(1, 5):
                idx = curr + k
                if idx >= n:
                    break
                out.append(idx)
        return out

    def _ahead_minutes(self, state, current_time: float, vis: List[int]) -> List[Optional[int]]:
        """Cumulative arrival minutes for the visible stops ahead of curr
        (E235-1000 draw_times accumulation). ``vis`` is the index sequence from
        ``_visible_stop_indices`` (curr first, then up to four ahead, wrapping on
        a circular route); minutes are computed for ``vis[1:]`` so they stay
        index-aligned with the markers drawn in show_stops. Base depends on
        state:
        - APPROACHING curr_stop: base = remaining time to curr_stop
          (``_first_stop_minutes``); first-ahead = base + its leg, etc.
        - STOPPED at curr_stop: that leg is already travelled, so the chain
          restarts from 0 — seeding with ``_first_stop_minutes`` would
          double-count the completed leg.
        Each visible stop's own ``time`` is the leg from its predecessor; this
        holds across the circular wrap because the doubled terminal shares the
        same leg (大崎→品川 is identical whether 大崎 is stops[0] or stops[-1])."""
        mins: List[Optional[int]] = []
        cumulative = 0 if state.at_station else self._first_stop_minutes(state, current_time)
        for idx in vis[1:]:
            # Passing station (empty `pa`) on an out-of-spec skip route: it takes
            # no countdown number and contributes nothing to the cumulative chain
            # — its `time` may be null, which would crash the sum. Marked None so
            # the draw loop renders an empty ring in the slot. Best-effort only; a
            # proper passing chevron (as the full-route open view draws) is a
            # deferred ultra-low-priority follow-up — the 5-station view's fixed
            # slots have no calibrated passing-marker treatment.
            if not self.stops[idx].get("pa"):
                mins.append(None)
                continue
            cumulative += self.stops[idx].get("time", 0)
            mins.append(int(cumulative))
        return mins

    # -------------------------------------------------------------------------
    # Inline transfer panel (left column)
    # -------------------------------------------------------------------------

    def _draw_transfer_panel(self, state) -> None:
        """Left-column transfer list for the target station (IRL inline panel).

        Reuses the parent transfer filter (``apply_transfer_filter``) so the
        entry order matches the horizontal transfer slot. Hidden entirely when
        the station has no transfers. Shinkansen entries occupy one row but
        wrap their long name at ``・`` into two lines shrunk to the row pitch.
        Panel stays Japanese in every mode (mirrors the kanji-only 5-station
        map). See docs/DISPLAY_E235.md § "Transfer Info".
        """
        if state is None:
            return
        idx = state.curr_stop
        if not (0 <= idx < len(self.stops)):
            return
        station_name = self.stops[idx].get("name", "")
        sd = self._tp_stations.get(station_name, {})
        refs = apply_transfer_filter(
            list(sd.get("transfers", [])),
            self._tp_line_code,
            self._tp_transfer_view,
            sd,
            self._tp_lines,
        )
        if not refs:
            return  # no transfers → hide whole panel (header + subtitle + list)

        t = _TUNEABLES_TRANSFER_PANEL
        px = int(t["tp0_x"])

        # Header: {station}駅 — ShinGo Heavy (most bold).
        header_font = self._font("ShinGoPr6N-Heavy.otf", t["tp_header_size"], draws=STATION_NAMES_EKI)
        header_img = header_font.render(station_name + "駅", True, DARK_BG)
        hy = int(t["tp0_y"])
        self.screen.blit(header_img, (px, hy))

        # Subtitle: 乗換えのご案内 — ShinGo Light (thin).
        sub_font = self._font("ShinGoPr6N-Light.otf", t["tp_sub_size"], draws=lit("乗換えのご案内"))
        sub_img = sub_font.render("乗換えのご案内", True, DARK_BG)
        sy = hy + header_img.get_height() + int(t["tp_sub_gap"])
        self.screen.blit(sub_img, (px, sy))

        # Entry rows — responsive packing. A shinkansen takes its OWN full-width
        # row and wraps its long name to ≤2 full-size lines (badge beside line 1).
        # Every other entry NEVER wraps (single line); two share a row when both
        # fit a half-column — short pairs share a row (IRL layout, and halves
        # vertical use so dense stations fit). A non-shinkansen too wide to share
        # takes a full row alone, still single line. At most 2 entries per row.
        name_font = self._font(
            "ShinGoPr6N-Medium.otf",
            t["tp_name_size"],
            # Shinkansen names wrap to <=2 lines at `･`, keeping
            # the separator on the leading line (see the wrap
            # note in _draw_transfer_panel).
            draws=at("data/lines.json:*.name_ja", wrap="･"),
        )
        line_h = name_font.get_height()
        badge_h = int(t["tp_badge"])
        badge_gap = int(t["tp_badge_gap"])
        inter_badge = int(t["tp_inter_badge"])
        wrap_lgap = int(t["tp_wrap_lgap"])
        col_gap = int(t["tp_col_gap"])
        pitch = t["tp_row_pitch"] * t["tp_compress"]
        row_gap = max(0, pitch - max(line_h, badge_h))  # inter-row gap implied by pitch

        # Right edge is a CURVE, not a vertical line: the green band sweeps right
        # as it descends, so lower rows get more width. The boundary is a
        # piecewise-linear curve through the draggable handles tp1/tp2/tp3 (sorted
        # by y); _right_edge(row_y) interpolates between the bracketing pair and
        # extrapolates along the end segments past the outermost handles. Left
        # edge stays vertical at px (tp0_x). See docs/DISPLAY_E235.md § "Transfer Info".
        _curve_pts = sorted(
            (
                (int(t["tp1_y"]), int(t["tp1_x"])),
                (int(t["tp2_y"]), int(t["tp2_x"])),
                (int(t["tp3_y"]), int(t["tp3_x"])),
            )
        )

        def _right_edge(yy):
            pts = _curve_pts
            if yy <= pts[0][0]:
                (y0, x0), (y1, x1) = pts[0], pts[1]
            elif yy >= pts[-1][0]:
                (y0, x0), (y1, x1) = pts[-2], pts[-1]
            else:
                (y0, x0), (y1, x1) = pts[0], pts[1]
                for k in range(len(pts) - 1):
                    if pts[k][0] <= yy <= pts[k + 1][0]:
                        (y0, x0), (y1, x1) = pts[k], pts[k + 1]
                        break
            if y1 == y0:
                return float(x0)
            return x0 + (x1 - x0) * (yy - y0) / (y1 - y0)

        def _icons(e):
            return [load_icon(b["icon"], badge_h, self._tp_icon_cache) for b in (e.get("badges") or [{"icon": "_universal"}])]

        def _is_shink(e):
            return e.get("category") == "shinkansen"

        def _entry_w(e):
            ics = _icons(e)
            bw = sum(ic.get_width() for ic in ics) + inter_badge * (len(ics) - 1)
            return bw + badge_gap + name_font.size(e["name_ja"])[0]

        def _entry_lines(e, ex):
            """Lines for entry ``e`` drawn at column-x ``ex``. Only shinkansen
            wrap (to ≤2 lines at ``･``); every other entry is a single line
            (never wraps, per spec). Shinkansen wrap against the NARROWER fixed
            boundary ``tp_shink_wrap_x`` (decoupled from the row-push curve), so
            the cut stays fixed (東北･山形･秋田 | 北海道…) even when the curve is
            widened for pairing."""
            ics = _icons(e)
            bw = sum(ic.get_width() for ic in ics) + inter_badge * (len(ics) - 1)
            text_x = ex + bw + badge_gap
            if _is_shink(e):
                avail = int(t["tp_shink_wrap_x"]) - text_x
                if name_font.size(e["name_ja"])[0] > avail:
                    return [ln for ln in self._wrap_two_lines(e["name_ja"], name_font, avail) if ln]
            return [e["name_ja"]]

        def _content_h(lines):
            return len(lines) * line_h + (len(lines) - 1) * wrap_lgap

        def _draw_entry(e, ex, top_y):
            """Badge group + name at column-x ``ex``, first line top at ``top_y``."""
            ics = _icons(e)
            bw = sum(ic.get_width() for ic in ics) + inter_badge * (len(ics) - 1)
            text_x = ex + bw + badge_gap
            lines = _entry_lines(e, ex)
            # Badge group vertically centered on the FIRST line.
            by = int(round(top_y + line_h / 2.0 - badge_h / 2.0))
            bx = ex
            for j, ic in enumerate(ics):
                self.screen.blit(ic, (bx, by))
                bx += ic.get_width()
                if j < len(ics) - 1:
                    bx += inter_badge
            ty = top_y
            for ln in lines:
                self.screen.blit(name_font.render(ln, True, DARK_BG), (text_x, int(round(ty))))
                ty += line_h + wrap_lgap

        # Grouping (col-1 left at px; col-2 shares one anchor so 2nd badges align)
        # + curved boundary + monotone repair. Algorithm + stability proof in
        # docs/DISPLAY_E235.md § "Transfer Info" → "Inline panel (5-station view)".
        resolved = [resolve_entry(ref, self._tp_lines) for ref in refs]
        list_y0 = sy + sub_img.get_height() + int(t["tp_list_gap"])
        # Threshold T (overfit Yamanote): pairing engages only when the station
        # has ≥ tp_pair_min_n transfers. Fewer → every entry stacks one-per-row,
        # regardless of free width (IRL: 秋葉原/神田/日暮里 etc. stay solo even
        # with room). Yamanote's effective transfer counts are 1,2,3,6,7,8,9 —
        # never 4 or 5 — so the gap makes the 6-cutoff unambiguous. See
        # docs/DISPLAY_E235.md § "Transfer Info".
        pairing_on = len(resolved) >= int(t["tp_pair_min_n"])

        def _build(disabled):
            """Lay rows top-down. Shinkansen → solo full-width row (may wrap).
            Non-shinkansen → pair consecutive when pairing is on AND the pair's
            own footprint fits the boundary at that row; else solo. Returns list
            of row dicts."""
            rows = []
            yy = list_y0
            j = 0
            while j < len(resolved):
                e = resolved[j]
                nxt = resolved[j + 1] if j + 1 < len(resolved) else None
                if (
                    pairing_on
                    and j not in disabled
                    and nxt is not None
                    and not _is_shink(e)
                    and not _is_shink(nxt)
                    and _entry_w(e) + col_gap + _entry_w(nxt) <= _right_edge(yy) - px
                ):
                    members = [e, nxt]
                    j += 2
                else:
                    members = [e]
                    j += 1
                # Row height: only a solo shinkansen wraps; pairs/solos are 1 line.
                if len(members) == 1 and _is_shink(members[0]):
                    ch = _content_h(_entry_lines(members[0], px))
                else:
                    ch = line_h
                row_h = max(badge_h, ch)
                rows.append({"members": members, "y": yy, "i": j - len(members), "row_h": row_h})
                yy += row_h + row_gap
            return rows

        disabled: set = set()
        col2_x = None
        rows: list = []
        for _ in range(len(resolved) + 1):
            rows = _build(disabled)
            paired = [r for r in rows if len(r["members"]) == 2]
            if not paired:
                col2_x = None
                break
            col2_x = px + max(_entry_w(r["members"][0]) for r in paired) + col_gap
            violators = [r for r in paired if col2_x + _entry_w(r["members"][1]) > _right_edge(r["y"])]
            if not violators:
                break
            for r in violators:
                disabled.add(r["i"])

        for r in rows:
            yy = r["y"]
            members = r["members"]
            _draw_entry(members[0], px, yy)
            if len(members) == 2:
                _draw_entry(members[1], col2_x, yy)

    def _wrap_two_lines(self, name: str, font, avail_w: int) -> Tuple[str, str]:
        """Greedy-to-width split into (line1, line2).

        ``･``-delimited (shinkansen — half-width middle dot U+FF65, matching the
        dest separator convention): the longest run of segments whose joined
        width INCLUDING a trailing ``･`` fits ``avail_w`` stays on line 1 with
        that ``･`` kept (the dot is not dropped at the break); the rest go to
        line 2. ``avail_w`` here is the NARROWER shinkansen wrap budget
        (``tp_shink_wrap_x``), not the row-push curve — IRL the cut is fixed
        (東北･山形･秋田 | 北海道･上越･北陸新幹線) and must not shift when the curve
        widens for pairing. No ``･``: break at the longest char prefix that fits.
        Always returns two strings (line 2 may overrun a too-wide remainder)."""
        dot = "･"  # U+FF65 halfwidth katakana middle dot (shinkansen separator)
        if dot in name:
            segs = name.split(dot)
            k = 1  # at least the first segment stays on line 1
            for i in range(1, len(segs)):
                if font.size(dot.join(segs[:i]) + dot)[0] <= avail_w:
                    k = i
                else:
                    break
            return dot.join(segs[:k]) + dot, dot.join(segs[k:])
        for i in range(len(name) - 1, 0, -1):
            if font.size(name[:i])[0] <= avail_w:
                return name[:i], name[i:]
        return name, ""

    # -------------------------------------------------------------------------
    # Marker primitives — copied from CircularFullRouteDisplay (same model).
    # -------------------------------------------------------------------------

    def _draw_numbered_circle(self, pos: Tuple[int, int], minutes: Optional[int], radius: float, font: Optional[pygame.font.Font] = None) -> None:
        """White countdown disk + dark minute digit. Green band shows as the
        ring around the disk (no explicit ring drawn). ``minutes=None`` → an
        empty ring with no digit: the 5-station view's best-effort marker for a
        passing (out-of-spec skip) station, which has no calibrated chevron slot
        here (a proper passing chevron is a deferred ultra-low-priority item)."""
        # fmt: off
        # --- Numbered circle params (adjust freely) ---
        disk_color = (245, 245, 250)   # near-white disk; green band peeks as ring
        # ----------------------------------------------
        # fmt: on
        cx, cy = int(pos[0]), int(pos[1])
        r = int(radius)
        pygame.gfxdraw.filled_circle(self.screen, cx, cy, r, disk_color)
        pygame.gfxdraw.aacircle(self.screen, cx, cy, r, disk_color)
        if minutes is None:
            return  # passing station — empty ring, no number
        # Centre the digit's INK on (cx, cy), not its rendered surface box: the
        # surface is a full font line-height tall and the font's ascent gap
        # above a digit exceeds its descent gap below, so box-centring parks the
        # digit low (~1.5px at the largest circle). Place by baseline + glyph
        # metrics instead — exact across all four circle sizes.
        img = font.render(str(minutes), True, DARK_BG)
        glyphs = [g for g in font.metrics(str(minutes)) if g]
        maxy = max(g[3] for g in glyphs)  # ink extent above baseline (cap height)
        miny = min(g[2] for g in glyphs)  # below baseline (~0 for digits)
        top = cy + (maxy + miny) / 2.0 - font.get_ascent()
        self.screen.blit(img, (cx - img.get_width() / 2.0, top))

    def _compute_five_station_arrow_animation(self) -> Tuple[float, float, float, float]:
        """Compute sweep animation state for the 5-station approaching arrow.

        Single-chevron cycle: travel A→B over sweep_dur, fade out over fade_dur,
        rest for rest_gap, repeat. Timing from pygame.time.get_ticks() so it
        animates even when current_time is frozen (editor / screenshot mode).

        Returns (tip_x, tip_y, halo_alpha, body_alpha) for the current frame.
          - During sweep:     tip lerps A→B (ease-out); both alphas 0→1 together.
          - During fade-out:  tip stays at B; the white halo fades first and the
                              red body a bit later — halo over [0, 1-stagger] of
                              fade_dur, body over [stagger, 1] (a0_fade_stagger).
          - During rest:      returns A with both alphas 0 (invisible, parked at
                              A, ready for the next cycle).
        """
        t = _TUNEABLES_FIVE_STATION
        a0_x = t["a0_x"]
        a0_y = t["a0_y"]
        angle_deg = t["a0_angle"]
        sweep_dist = t["a0_sweep_dist"]
        sweep_dur = t["a0_sweep_dur"]
        fade_dur = t["a0_fade_dur"]
        rest_gap = t["a0_rest_gap"]

        # B = A advanced along the arrow's heading by sweep_dist.
        # Heading unit vector: the base right-pointing arrow rotated by angle_deg
        # (CCW in math coords, which equals the rotation applied in _draw_five_station_approaching_arrow).
        rad = math.radians(angle_deg)
        hx = math.cos(rad)
        hy = math.sin(rad)
        tip_x_A = a0_x
        tip_y_A = a0_y
        tip_x_B = a0_x + hx * sweep_dist
        tip_y_B = a0_y + hy * sweep_dist

        cycle_period = sweep_dur + fade_dur + rest_gap
        t_now = pygame.time.get_ticks() / 1000.0
        t_cycle = t_now % cycle_period

        # Ease-curve shape — now tunable via _TUNEABLES_FIVE_STATION (editor).
        ease_out_power = t["a0_ease_out_power"]  # sweep position: fast at A, slow at B (decelerating)
        fade_in_full_at = t["a0_fade_in_full_at"]  # alpha hits 1.0 when raw sweep_t reaches this fraction
        fade_out_power = t["a0_fade_out_power"]  # fade-out: 1 - t^power
        stagger = max(0.0, min(0.95, t["a0_fade_stagger"]))  # body-fade lead behind halo

        if t_cycle < sweep_dur:
            sweep_t = t_cycle / sweep_dur
            eased = 1 - (1 - sweep_t) ** ease_out_power
            tip_x = tip_x_A + (tip_x_B - tip_x_A) * eased
            tip_y = tip_y_A + (tip_y_B - tip_y_A) * eased
            a = min(1.0, sweep_t / fade_in_full_at)  # fade-in: halo + body together
            return tip_x, tip_y, a, a
        if t_cycle < sweep_dur + fade_dur:
            fade_t = (t_cycle - sweep_dur) / fade_dur
            span = 1.0 - stagger  # each element's fade occupies this fraction of fade_dur
            # Halo leads: fades over [0, 1-stagger]. Body lags: fades over [stagger, 1].
            halo_ft = min(1.0, fade_t / span) if span > 0 else 1.0
            body_ft = min(1.0, max(0.0, (fade_t - stagger) / span)) if span > 0 else 1.0
            halo_alpha = 1.0 - halo_ft**fade_out_power
            body_alpha = 1.0 - body_ft**fade_out_power
            return tip_x_B, tip_y_B, halo_alpha, body_alpha
        # Rest phase — arrow invisible, position parked at A.
        return tip_x_A, tip_y_A, 0.0, 0.0

    def _draw_five_station_approaching_arrow(
        self,
        tip_x: float,
        tip_y: float,
        angle_deg: float,
        scale: float,
        halo_px: float = 1.0,
        halo_alpha: float = 1.0,
        body_alpha: float = 1.0,
    ) -> None:
        """Approaching arrow for the 5-station view's slot-0 (APPROACHING state).

        Geometry copied verbatim from CircularFullRouteDisplay._draw_approaching_arrow
        (same file, ~line 562), then extended with rotation + uniform scale:

        - ``scale``     multiplies all dimension params before polygon build.
        - ``angle_deg`` rotates every point about ``tip`` after polygon build
          (positive = CCW). The 5-station band runs diagonally so the arrow must
          point up-along-the-band at an arbitrary angle, not just left/right.
        - ``halo_alpha`` / ``body_alpha``  independent 0→1 fades for the white
          halo and the red body, enabling the staggered fade-out (halo first,
          body a bit later). When either is < 1.0 the faded path renders the halo
          and the body onto SEPARATE SRCALPHA surfaces — each scaled by its own
          alpha via BLEND_RGBA_MULT, halo blitted behind — so they can fade out
          of step. Both 1.0 → the opaque fast path (single direct draw).

        The full-route original uses ``face_left`` for right→left mirroring; here
        we always build right-pointing geometry first then apply the rotation —
        the same final orientation is reachable via ``angle_deg``.
        """
        # fmt: off
        # --- Arrow params (scaled from full-route original) ---
        w_body      = 17 * scale                      # full-route: 17
        h_body      = (STOPS_BAR_HEIGHT + 2) * scale  # full-route: 32
        stroke_body = 11 * scale                      # full-route: 11
        halo_w      = halo_px * scale                 # uniform halo thickness, every side
        # -----------------------------------------------------
        # fmt: on
        # Build right-pointing geometry (apex at tip_x, tip_y).
        body_x = tip_x - w_body
        body_y = tip_y - h_body / 2
        body_pts = arrow_points(int(body_x), int(body_y), int(w_body), int(h_body), int(stroke_body))

        # Rotate about tip by angle_deg (CCW positive, screen-coord-aware). The
        # 5-station band runs diagonally, so the arrow points up-along-the-band.
        if angle_deg != 0:
            rad = math.radians(angle_deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            body_pts = [
                (tip_x + (px - tip_x) * cos_a - (py - tip_y) * sin_a, tip_y + (px - tip_x) * sin_a + (py - tip_y) * cos_a) for px, py in body_pts
            ]

        # Collect all stamp offsets for the uniform halo + the body.
        # Stamp ring: body shape offset in 12 directions → union = body dilated
        # by a disk of radius halo_w → equal halo thickness on every edge.
        halo_stamps = 12
        stamp_offsets = [
            (halo_w * math.cos(2 * math.pi * k / halo_stamps), halo_w * math.sin(2 * math.pi * k / halo_stamps)) for k in range(halo_stamps)
        ]

        if halo_alpha >= 1.0 and body_alpha >= 1.0:
            for ox, oy in stamp_offsets:
                draw_aapolygon(self.screen, PASSED_COLOR, [(px + ox, py + oy) for px, py in body_pts])
            draw_aapolygon(self.screen, self.contrast_color, body_pts)
            return

        # Faded path — halo and body on SEPARATE SRCALPHA surfaces so each fades
        # on its own alpha (staggered fade-out: halo first, body a bit later).
        # Halo blitted first (behind); the body overdraws its interior, so only
        # the visible outer ring fades. Bbox spans the dilated halo extent.
        all_pts = [(px + ox, py + oy) for ox, oy in stamp_offsets for px, py in body_pts] + body_pts
        min_x = int(min(p[0] for p in all_pts)) - 2
        min_y = int(min(p[1] for p in all_pts)) - 2
        max_x = int(max(p[0] for p in all_pts)) + 2
        max_y = int(max(p[1] for p in all_pts)) + 2
        surf_w = max_x - min_x + 1
        surf_h = max_y - min_y + 1
        if surf_w <= 0 or surf_h <= 0:
            return
        local_body = [(px - min_x, py - min_y) for px, py in body_pts]

        halo_surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        for ox, oy in stamp_offsets:
            draw_aapolygon(halo_surf, PASSED_COLOR, [(px - min_x + ox, py - min_y + oy) for px, py in body_pts])
        ha = max(0, min(255, int(halo_alpha * 255)))
        halo_surf.fill((255, 255, 255, ha), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(halo_surf, (min_x, min_y))

        body_surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        draw_aapolygon(body_surf, self.contrast_color, local_body)
        ba = max(0, min(255, int(body_alpha * 255)))
        body_surf.fill((255, 255, 255, ba), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(body_surf, (min_x, min_y))

    @staticmethod
    def _offset_convex_poly(points, d: float):
        """Uniform outward offset of a convex polygon: every edge moves `d` px
        along its outward normal, corners re-intersected (miter join). Gives a
        constant-width halo regardless of shape asymmetry or rotation — a
        uniform SCALE can't (offset would vary with each edge's distance from
        center), and an x-shift smear can't (width varies with edge direction).
        """
        n = len(points)
        ccx = sum(p[0] for p in points) / n
        ccy = sum(p[1] for p in points) / n
        edges = []
        for i in range(n):
            (x0, y0), (x1, y1) = points[i], points[(i + 1) % n]
            ex, ey = x1 - x0, y1 - y0
            length = math.hypot(ex, ey) or 1.0
            nx, ny = ey / length, -ex / length
            # Flip the normal if it points toward the centroid.
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if (mx + nx - ccx) ** 2 + (my + ny - ccy) ** 2 < (mx - ccx) ** 2 + (my - ccy) ** 2:
                nx, ny = -nx, -ny
            edges.append((x0 + nx * d, y0 + ny * d, ex, ey))
        out = []
        for i in range(n):
            # Intersect offset edge i-1 with offset edge i (lines, param form).
            ax, ay, aex, aey = edges[i - 1]
            bx, by, bex, bey = edges[i]
            den = aex * bey - aey * bex
            if abs(den) < 1e-9:  # parallel edges — fall back to edge start
                out.append((bx, by))
                continue
            s = ((bx - ax) * bey - (by - ay) * bex) / den
            out.append((ax + aex * s, ay + aey * s))
        return out

    def _draw_pentagon(
        self,
        vertices: List[Tuple[int, int]],
        dot: Tuple[int, int],
        dot_r: int,
    ) -> None:
        """Red stopping marker — a freely-placed polygon, with uniform-scale
        breathing animation + pulsing glow + a white dot.

        No parametric shape model: this marker is only ever drawn at one fixed
        slot and one fixed orientation (k==0 in the 5-station view, which
        re-centres on the current stop), so the `vertices` ARE the shape —
        hand-placed against _references/lcd/E2350.png via the calibration
        editor's drag handles (keys v0..v4). `dot` is the white dot centre
        (handle d0) and `dot_r` its radius (m0_dr). The earlier home-plate +
        knobs (heading / side-length / right-tilt / cap) model was dropped: it
        couldn't represent the photographed shape, and a free polygon makes
        any pentagon reachable — see conventions / the 2026-06-12 third-man.

        Breath scales the polygon about its centroid; the halo is a true
        uniform edge-normal offset via `_offset_convex_poly`; the dot does NOT
        breathe (stays put while the red body pulses). Glow + breath pattern
        share the CircularFullRouteDisplay pentagon's feel.
        """
        # fmt: off
        # --- Pentagon static params (adjust freely) ---
        halo_w           = 3      # uniform white halo width (px, edge-normal)
        breath_period_s  = 1.2
        breath_min_scale = 0.82   # body shrinks to this of max
        glow_reach_mult  = 1.8    # peak glow radius = polygon reach × this
        glow_alpha       = 70     # peak glow opacity
        # ----------------------------------------------
        # fmt: on
        n = len(vertices)
        ccx = sum(v[0] for v in vertices) / n
        ccy = sum(v[1] for v in vertices) / n
        reach = max(math.hypot(v[0] - ccx, v[1] - ccy) for v in vertices)

        t_seconds = pygame.time.get_ticks() / 1000.0
        cycle = (t_seconds / breath_period_s) % 1.0
        phase = 1 - 2 * cycle if cycle < 0.5 else 2 * cycle - 1
        scale = breath_min_scale + (1.0 - breath_min_scale) * phase

        # Pulsing red glow halo behind the marker — fades out as it expands,
        # synced to the breath phase (brightest when the body is largest).
        glow_r = int(reach * glow_reach_mult * (0.6 + 0.4 * phase))
        a = int(glow_alpha * phase)
        if a > 0 and glow_r > 0:
            glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            pygame.gfxdraw.filled_circle(glow, glow_r, glow_r, glow_r, (*self.contrast_color, a))
            self.screen.blit(glow, (int(ccx) - glow_r, int(ccy) - glow_r))

        max_points = list(vertices)
        red_points = [(ccx + (px - ccx) * scale, ccy + (py - ccy) * scale) for (px, py) in max_points]

        # White halo = max outline dilated by halo_w (uniform width on every
        # edge at any rotation). Filled, so it also backs the breathing red.
        draw_aapolygon(self.screen, PASSED_COLOR, self._offset_convex_poly(max_points, halo_w))
        draw_aapolygon(self.screen, self.contrast_color, red_points)
        dot_x, dot_y = int(dot[0]), int(dot[1])
        inner_dot_r = max(2, int(dot_r))
        pygame.gfxdraw.filled_circle(self.screen, dot_x, dot_y, inner_dot_r, PASSED_COLOR)
        pygame.gfxdraw.aacircle(self.screen, dot_x, dot_y, inner_dot_r, PASSED_COLOR)

    def _draw_jy_badge(self, stop: Dict, gpos: Tuple[int, int], size: float) -> None:
        """Station-number badge (e.g. JY29), left-center anchored at the group
        anchor. Square, side `size`.

        Uses the shared `draw_station_code_badge` with the upper-LCD param
        set, but as the NO-black-ring variation (IRL the 5-station badges
        have the route-color frame running to the badge edge, same as the
        e235_1000 8-station mini-badge). Scale reference is 54px — the upper
        badge's 68px minus its 2x7px black ring — so at the same tuned size
        the color ring / interior / text grow to fill the removed ring's
        space. Frutiger face fixed in the helper. No code_3 band: the IRL
        Yamanote stopping-view badges are number-only.
        """
        sta_code = stop.get("sta_code")
        if not sta_code:
            return
        b = int(size)
        bx = int(gpos[0])
        by = int(gpos[1]) - b // 2
        s = b / 54.0  # scale from the upper-LCD badge minus its black ring (68 - 2*7)
        draw_station_code_badge(
            self.screen,
            bx,
            by,
            b,
            b,
            sta_code,
            self.color,
            prefix_size=18 * s,
            num_size=22 * s,
            ring_black=0,
            ring_color=max(1, round(7 * s)),
            outer_radius=max(1, round(6 * s)),
            color_radius=max(1, round(6 * s)),
            text_gap=max(1, round(3 * s)),
            prefix_x_offset=1,
        )

    def _draw_station_name(self, name: str, gpos: Tuple[int, int], name_size: float, inset: float) -> None:
        """Horizontal kanji station name at `name_size` px, inset `inset` from the
        group anchor, vertically CENTER-ALIGNED with the badge (both centered on
        gpos_y). Fixed 3-char width: 2-char middle-padded, 4+ compressed.
        """
        if not name:
            return
        font = self._font("ShinGoPr6N-Medium.otf", name_size, draws=(STATION_NAMES, lit("永")))
        width = font.size("永")[0] * 3
        nx = int(gpos[0]) + int(inset)
        ny = int(gpos[1]) - font.get_height() // 2  # center on gpos_y == badge center
        draw_text_given_width(nx, ny, width, font, name, DARK_BG, self.screen)

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Map an LCD-local click to a stop index (click-to-jump). The view shows up to 5 fixed slots
        (curr + 4 ahead, from _visible_stop_indices); each slot's clickable box spans its marker +
        badge + station name. `vis[k]` IS the stop index (self.stops space == sim-index space), so the
        matched slot returns directly. Nearest slot-centre wins when boxes overlap (wide names)."""
        if state is None:
            return None
        vis = self._visible_stop_indices(state.curr_stop)
        t = _TUNEABLES_FIVE_STATION
        MARKER_R = 22  # nominal marker reach (largest is m0_circle_r=22); pads the box on the marker side
        best_idx, best_d2 = None, None
        for k, idx in enumerate(vis):
            mx0, my0 = t[f"m{k}_x"], t[f"m{k}_y"]
            gx, gy = t[f"g{k}_x"], t[f"g{k}_y"]
            name_font = self._font("ShinGoPr6N-Medium.otf", t[f"g{k}_ns"], draws=(STATION_NAMES, lit("永")))
            name_w = name_font.size("永")[0] * 3  # fixed 3-char name width — matches _draw_station_name
            name_h = name_font.get_height()
            left = min(mx0 - MARKER_R, gx)
            right = gx + t[f"g{k}_ni"] + name_w
            top = min(my0 - MARKER_R, gy - name_h // 2)
            bot = max(my0 + MARKER_R, gy + name_h // 2)
            if left <= mx <= right and top <= my <= bot:
                cx, cy = (left + right) / 2, (top + bot) / 2  # slot centre → disambiguate overlaps
                d2 = (mx - cx) ** 2 + (my - cy) ** 2
                if best_d2 is None or d2 < best_d2:
                    best_idx, best_d2 = idx, d2
        return best_idx


# =============================================================================
# E235-0 Lower LCD manager — subclasses E235-1000 to swap full-route renderer
# =============================================================================


class LowerDisplay(E235_1000_LowerDisplay):
    """E235-0 Lower LCD manager.

    Inherits the slot cycler (FULL/EIGHT/TRANSFER) — which lives in
    ``LowerDisplayBase``, two levels up — via the E235-1000 concrete, whose
    ``draw`` / ``_draw_restart_transition`` it also reuses. Overrides:

    - **FULL slot**: route-keyed — 山手線 → circular racetrack
      (`CircularFullRouteDisplay`); any other (non-Yamanote) route →
      `OpenRouteFullRouteDisplay`, the same racetrack opened into a horseshoe
      (one cap dropped). No E235-1000 linear fallback — both are E235-0 looks.

    - **EIGHT slot**: swapped to `JapaneseFiveStationDisplay` universally
      (no dispatch — all routes get the curve, including non-Yamanote
      best-effort uses).

    TRANSFER slot inherits unchanged.
    """

    def __init__(self, screen, route_data, stops, mode_cycler):
        super().__init__(screen, route_data, stops, mode_cycler)
        # FULL slot — both branches are E235-0 racetrack renderers (Yamanote =
        # closed loop, else = open horseshoe), replacing the inherited e235_1000
        # linear. english_display points at the SAME instance: both render kanji
        # station names regardless of mode — IRL the route map stays kanji even
        # under English chrome, and the horseshoe inherits that convention.
        if route_data.get("route") == "山手線":
            self.japanese_display = CircularFullRouteDisplay(screen, route_data, stops)
        else:
            self.japanese_display = OpenRouteFullRouteDisplay(screen, route_data, stops)
        self.english_display = self.japanese_display
        # Swap EIGHT slot renderer universally (Phase 1: arc-only scaffold).
        # E235-0 has NO 8-station view — the 5-station view owns the EIGHT slot in
        # ALL modes. Point english_eight_display at the SAME instance (not a new
        # one): the fill state (`_fill_start`) must stay consistent across modes
        # within the EIGHT slot — a language flip does not re-enter the slot, so it
        # must not reset the sweep, and both modes must render the same progress.
        # One shared instance guarantees that. (5-station renders kanji names
        # regardless of mode — IRL Yamanote stopping view is kanji-only.)
        self.japanese_eight_display = JapaneseFiveStationDisplay(screen, route_data, stops)
        self.english_eight_display = self.japanese_eight_display
        # Transfer slot is the e235_1000 concrete reused here; align its lower-LCD
        # top with THIS model's UPPER_HEIGHT (ARC_RECT.top = 130, not 1000's 117)
        # so the upper LCD is the same height across all three slots.
        self.transfer_display.upper_height = ARC_RECT.top

    # E235-0's native norm is NO end-of-route lock. `_should_lock_to_eight` is a
    # LINEAR end-of-route heuristic inherited from E235-1000 (it drops the FULL
    # slot once the train is within LOCK_THRESHOLD stops of the route tail).
    # Yamanote — this model's in-spec route — is a circular LOOP with no end for
    # that heuristic to fire on, so no-lock IS E235-0's real default, not a
    # special case. Keeping the borrowed lock for out-of-spec (best-effort)
    # routes would ADD a non-native E235-1000 behavior — the opposite of
    # best-effort, which is "the model's own native norm applied to whatever
    # route is loaded, not a borrowed feature." So the lock is off for EVERY
    # route here; the inherited LOCK_THRESHOLD (7) is never consulted (kept only
    # to satisfy the LowerDisplayBase non-None CONTRACT — see displays/lower_lcd.py).
    def _should_lock_to_eight(self, cursor_pos: int) -> bool:
        return False

    def _on_slot_entered(self, slot: int, now: float) -> None:
        """Restart the 5-station band fill when its slot (EIGHT) is entered.

        The fill replays on each genuine slot-enter (docs/DISPLAY_E235.md § "E235-0 —
        5-station stopping view"). ``english_eight_display`` is the SAME instance,
        so one call covers both modes. Only a real slot change reaches here — a
        draw stall or a stopped→moving marker flip keeps EIGHT current (no
        ``apply_slot``), so neither refills the band."""
        if slot == self._SLOT_EIGHT:
            self.japanese_eight_display.on_slot_enter(now)

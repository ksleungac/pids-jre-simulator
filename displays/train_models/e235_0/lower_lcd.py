"""E235-0 series Lower LCD display implementation.

Today: provides a circular full-route renderer (Yamanote racetrack layout)
and a `LowerDisplay` manager that swaps the full-route slot's renderer for
the circular variant on Yamanote routes. Other slots (8-station zoom,
transfer-info) inherit unchanged from E235-1000 — interim until the
E235-0-specific 5-station view lands.

Dispatch is route-keyed: ``route_data["route"] == "山手線"`` → circular;
else → E235-1000's linear full-route renderer (best-effort fallback for
out-of-spec routes loaded into E235-0).

Geometry: stadium / racetrack — two horizontal rows joined by semicircular
end caps. Bottom row holds JY17..JY30+JY01 (left→right in inner-loop
travel direction); top row holds JY02..JY16 (right→left in travel
direction). Station screen positions are keyed by ``sta_code``, so missing
stations (e.g. JY26 高輪ゲートウェイ in pre-2020 data) auto-redistribute
the row's spacing across the present count without leaving a gap.

Per-station rendering states: pentagon (current stop), numbered countdown
(next 15 ahead in inner-loop direction), or plain dot (rest of loop).
No dim/passed treatment — circular loops have no terminal "behind".
"""

from typing import Dict, List, Optional, Tuple
import pygame
import pygame.gfxdraw

from constants import (
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
from displays.utils import arrow_points, draw_1col_text_plain, draw_aapolygon
from displays.train_models.e235_1000.lower_lcd import (
    LowerDisplay as E235_1000_LowerDisplay,
)


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
MAJOR_STATION_NAMES_BOLD: set[str] = {"上野", "東京", "品川", "新宿", "渋谷"}


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

        # Cached window for hit_test parity (deferred — pentagon is static for now).
        self._last_curr_stop: int = -1

        # =====================================================================
        # Cross-method layout params — referenced by both _build_positions and
        # the draw methods. Per-method tuneables (pentagon shape, dot/circle
        # sizes, name clearance) live as locals in their respective draw
        # methods per conventions.md § "Tuneable-params block".
        # =====================================================================
        self.y_top = UPPER_HEIGHT  # absolute y where lower LCD area starts
        self.lower_h = S_HEIGHT - self.y_top

        # Vertical layout — track row centerlines (relative to y_top).
        # _build_positions derives row centerline y from cy ± curve_v_radius
        # (matching _draw_track) so a 1-pixel asymmetry from odd sums doesn't
        # bite the bottom row's stroke alignment.
        self.track_top_y          = 120    # y of top-row track centerline
        self.track_bottom_y       = 187    # y of bottom-row track centerline

        # Horizontal layout — straight section runs from track_left_pad to S_WIDTH - track_right_pad
        self.track_left_pad       = 15     # x of left curve apex (leftmost track edge)
        self.track_right_pad      = 15     # mirrored from right edge

        # Track band geometry — used by _draw_track AND _build_positions
        self.track_stroke_w       = 28     # thickness of green band
        # Cap shape: rounded-corner rectangle (NOT a full ellipse). Each cap has
        # quarter-arc top + bottom corners + a vertical straight segment in the
        # middle of the apex. The OUTER and INNER rounded rects use independent
        # vert_seg lengths — smaller inner vert_seg = larger inner border_radius
        # = inner corner more rounded (bulges toward apex). Stroke at the apex
        # vertical segment stays = stroke_w (rect inset is uniform horizontally);
        # the corner arcs themselves are not concentric so the stroke gradient
        # varies slightly along the arc.
        self.curve_v_radius       = (self.track_bottom_y - self.track_top_y) // 2
        self.vert_seg_h_outer     = 20     # outer-rect vertical straight at apex
        self.vert_seg_h_inner     = 15     # inner-rect vertical straight at apex (smaller = more curvy inner)

        # =====================================================================
        # Fonts (shared across multiple draw methods)
        # =====================================================================
        # Major station names use Heavy weight; the rest use Medium. The
        # bold set is hardcoded at module scope (MAJOR_STATION_NAMES_BOLD) —
        # not derived from code_3 since IRL Yamanote PIDS bolds a narrower set.
        self.font_station = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 19)
        self.font_station_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 19)
        self.font_circle = pygame.font.Font("fonts/HelveticaNeue-Bold.otf", 15)
        self.font_minute = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 10)
        self.font_disclaimer = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 9)

        # =====================================================================
        # Build per-sta_code position table (screen coordinates)
        # =====================================================================
        self.positions: Dict[int, Tuple[int, int]] = {}
        self._build_positions()

    # -------------------------------------------------------------------------
    # Layout — sta_code → (x, y) precomputation
    # -------------------------------------------------------------------------

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
        v_outer = self.curve_v_radius + self.track_stroke_w // 2
        border_outer = v_outer - self.vert_seg_h_outer // 2
        straight_left = self.track_left_pad + border_outer
        straight_right = S_WIDTH - self.track_right_pad - border_outer
        straight_w = straight_right - straight_left

        # Row centerline y values — derived from cy ± curve_v_radius to match
        # _draw_track's cy (avoids odd-sum 1-pixel offset on the bottom row).
        cy = self.y_top + (self.track_top_y + self.track_bottom_y) // 2
        top_row_y = cy - self.curve_v_radius
        bot_row_y = cy + self.curve_v_radius

        # Bottom row positions
        if bottom_present:
            n = len(bottom_present)
            for i, jy in enumerate(bottom_present):
                x = straight_left + int(straight_w * (i + 0.5) / n) if n > 1 else (straight_left + straight_right) // 2
                self.positions[jy] = (x, bot_row_y)

        # Top row positions
        if top_present:
            n = len(top_present)
            for i, jy in enumerate(top_present):
                x = straight_left + int(straight_w * (i + 0.5) / n) if n > 1 else (straight_left + straight_right) // 2
                self.positions[jy] = (x, top_row_y)

    # -------------------------------------------------------------------------
    # State helpers — "next 15 ahead" with sta_code dedup
    # -------------------------------------------------------------------------

    def _ahead_indices(self, curr_stop: int) -> List[Tuple[int, int]]:
        """Return up to NUMBERED_AHEAD_COUNT (stop_index, jy_code) tuples for
        the next stations ahead of ``curr_stop`` in inner-loop direction.

        Walks ``stops[]`` forward with modulo wrap, skipping any sta_code
        already seen. The wrap handles the data shape where Yamanote's
        route.json doubles the start station at the end (stops[0] and
        stops[-1] are both 大崎 = JY24); without dedup, the duplicate would
        try to render twice at the same screen position.
        """
        if not (0 <= curr_stop < len(self.stops)):
            return []

        seen: set[int] = set()
        curr_jy = _parse_jy_code(self.stops[curr_stop].get("sta_code", ""))
        if curr_jy is not None:
            seen.add(curr_jy)

        ahead: List[Tuple[int, int]] = []
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
        # --- Track draw params (adjust freely) ---
        v_outer = self.curve_v_radius + self.track_stroke_w // 2
        v_inner = max(1, self.curve_v_radius - self.track_stroke_w // 2)
        border_outer = max(1, v_outer - self.vert_seg_h_outer // 2)
        border_inner = max(1, v_inner - self.vert_seg_h_inner // 2)
        # -----------------------------------------

        cy = self.y_top + (self.track_top_y + self.track_bottom_y) // 2

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

    def _draw_approaching_arrow(self, pos: Tuple[int, int], face_left: bool = False) -> None:
        """Chevron arrow at the train's target stop while APPROACHING.

        Geometry copied from e235_1000.JapaneseDisplay.draw_ptr's chevron path:
        gray halo (wider, thinner notch) under a red body (taller, pointier
        notch). Direction-aware: ``face_left=True`` mirrors the chevron to
        point LEFT for top-row stops (inner-loop = R→L on top row).
        """
        # --- Arrow params (mirrors e235_1000.draw_ptr chevron) ---
        w_body       = 18
        h_body       = STOPS_BAR_HEIGHT + 4   # = 34
        stroke_body  = 10
        w_halo       = 23
        h_halo       = STOPS_BAR_HEIGHT       # = 30
        stroke_halo  = 16
        tip_offset   = 4                      # tip lies tip_offset px past station center on apex side
        halo_x_extra = 2                      # halo sits 2px more "behind" than body (matches e235_1000's `-2`)
        # ---------------------------------------------------------
        cx, cy = pos
        body_y = int(cy - h_body / 2)
        halo_y = int(cy - h_halo / 2)

        # Build right-pointing chevron points; mirror around cx for left-pointing.
        body_x = int(cx - (w_body - tip_offset))
        halo_x = int(cx - (w_halo - tip_offset) - halo_x_extra)
        body_pts_r = arrow_points(body_x, body_y, w_body, h_body, stroke_body)
        halo_pts_r = arrow_points(halo_x, halo_y, w_halo, h_halo, stroke_halo)

        if face_left:
            body_pts = [(2 * cx - px, py) for (px, py) in body_pts_r]
            halo_pts = [(2 * cx - px, py) for (px, py) in halo_pts_r]
        else:
            body_pts = body_pts_r
            halo_pts = halo_pts_r

        draw_aapolygon(self.screen, PASSED_COLOR, halo_pts, 5)
        draw_aapolygon(self.screen, self.contrast_color, body_pts)

    def _draw_direction_arrows(self) -> None:
        """Draw inner-loop direction chevrons on each cap's apex.

        Inner-loop travel direction:
          - Left cap: train comes around from top row down to bottom row → DOWN chevron (V).
          - Right cap: train goes from bottom row up to top row → UP chevron (^).
        Chevron sits centered on the vertical apex segment, drawn in WHITE_BG
        on top of the green band.
        """
        # --- Arrow params (adjust freely) ---
        # arrow_w spans the full color-bar width so the chevron reaches the
        # inner edges of the band. Smaller arrow_h = flatter, less pointy
        # chevron (higher w/h ratio = obtuse-angle V).
        arrow_w = 28   # chevron horizontal extent (= track_stroke_w, full band)
        arrow_h = 6    # chevron vertical extent (top-to-tip depth) — flatter is less pointy
        stroke  = 4
        # -------------------------------------

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
            left   = (cx - half_w, cy - half_h)
            tip    = (cx,          cy + half_h)
            right  = (cx + half_w, cy - half_h)
        else:
            left   = (cx - half_w, cy + half_h)
            tip    = (cx,          cy - half_h)
            right  = (cx + half_w, cy + half_h)
        pygame.draw.line(self.screen, WHITE_BG, left, tip, stroke)
        pygame.draw.line(self.screen, WHITE_BG, tip, right, stroke)

    def _draw_dot(self, pos: Tuple[int, int]) -> None:
        """Plain dot for stations beyond the 15-ahead countdown window.

        Copied from e235_1000.JapaneseDisplay.draw_marks's small_dot path.
        """
        # --- Dot params (adjust freely) ---
        radius = 5  # matches e235_1000 small_dot_radius
        # ----------------------------------
        cx, cy = int(pos[0]), int(pos[1])
        pygame.gfxdraw.filled_circle(self.screen, cx, cy, radius, PASSED_COLOR)
        pygame.gfxdraw.aacircle(self.screen, cx, cy, radius, PASSED_COLOR)

    def _draw_numbered_circle(self, pos: Tuple[int, int], minutes: int, with_minute_suffix: bool = False) -> None:
        """White-interior + route-color outline circle with countdown minutes.

        IRL Yamanote countdown circles use a white interior with thin route-color
        outline + black countdown text — distinct from e235_1000's gray active-ring
        style (which sits on a green active-range bar). Uses gfxdraw for AA edges.
        """
        # --- Numbered circle params (adjust freely) ---
        outer_radius        = 12   # outer route-color ring radius
        inner_inset         = 1    # inset from outer (= visible ring thickness)
        suffix_x_gap        = 0    # gap between circle right edge and (分) suffix
        suffix_bottom_pad   = 2    # gap between (分) bottom and color bar bottom edge
        # ----------------------------------------------
        cx, cy = int(pos[0]), int(pos[1])
        pygame.gfxdraw.filled_circle(self.screen, cx, cy, outer_radius, self.color)
        pygame.gfxdraw.aacircle(self.screen, cx, cy, outer_radius, self.color)
        inner_r = outer_radius - inner_inset
        pygame.gfxdraw.filled_circle(self.screen, cx, cy, inner_r, WHITE_BG)
        pygame.gfxdraw.aacircle(self.screen, cx, cy, inner_r, WHITE_BG)

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
        cx, cy = pos

        half_h_max = STOPS_BAR_HEIGHT / 2 + overhang      # = 17 (red at max, fully extended)
        half_h_min = self.track_stroke_w / 2              # = 14 (red at min, height = color bar)
        scale_min = half_h_min / half_h_max               # ≈ 0.824

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
            rect_left_x  = cx - rect_half_w_apex
            apex_x       = rect_left_x - triangle_d
            max_points = [
                (rect_right_x, cy - half_h_max),
                (rect_right_x, cy + half_h_max),
                (rect_left_x,  cy + half_h_max),
                (apex_x,       cy),
                (rect_left_x,  cy - half_h_max),
            ]
        else:
            rect_left_x  = cx - rect_half_w_back
            rect_right_x = cx + rect_half_w_apex
            apex_x       = rect_right_x + triangle_d
            max_points = [
                (rect_left_x,  cy - half_h_max),
                (rect_left_x,  cy + half_h_max),
                (rect_right_x, cy + half_h_max),
                (apex_x,       cy),
                (rect_right_x, cy - half_h_max),
            ]

        # Uniformly scale max_points toward (cx, cy) for the breathing red body.
        red_points = [
            (cx + (px - cx) * scale, cy + (py - cy) * scale)
            for (px, py) in max_points
        ]

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

    def _draw_station_name(self, name: str, pos: Tuple[int, int], on_top_row: bool, is_major: bool = False) -> None:
        """Draw vertical Japanese station name above (top row) or below (bottom row) its track position.

        Uses ``draw_1col_text_plain`` — tight back-to-back stacking, no
        compression, no distribution. Long names overflow rather than squish
        (multi-column wrap deferred until 高輪ゲートウェイ-class names land).

        ``is_major`` switches to the Heavy-weight font; the major-station set
        is the hardcoded module-level ``MAJOR_STATION_NAMES_BOLD`` (NOT
        derived from ``code_3``, since IRL Yamanote bolds a narrower set —
        e.g. 大崎 has code_3=OSK but is NOT bolded).
        """
        if not name:
            return

        # --- Name layout params (adjust freely) ---
        # `clearance` = gap from station-position centerline to nearest name char.
        # = track_stroke_w/2 + 8 → 8px margin between the green color bar's
        # edge and the name (per IRL ref, applied symmetrically top + bottom).
        clearance = self.track_stroke_w // 2 + 8
        line_gap = 1   # extra px between vertically-stacked chars
        # ------------------------------------------

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

        draw_1col_text_plain(font, name, col_left_x, top_y, DARK_BG, self.screen, line_gap=line_gap)

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

        # 4. Numbered countdown circles for next 15 ahead
        ahead = self._ahead_indices(state.curr_stop)
        minutes_list = self._compute_minutes_for_ahead(ahead, state, current_time)
        for i, ((stop_idx, jy), minutes) in enumerate(zip(ahead, minutes_list)):
            pos = self.positions.get(jy)
            if pos is None:
                continue
            with_suffix = (i == len(ahead) - 1)
            self._draw_numbered_circle(pos, minutes, with_minute_suffix=with_suffix)

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
                        self._draw_approaching_arrow(pos, face_left=on_top)

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
        # --- Disclaimer params (adjust freely) ---
        disclaimer_text = "のりかえ、待合せ時間は含まれません。電車により多少時間が異なります。"
        left_x      = 8   # left margin from screen edge
        bottom_pad  = 4   # gap between disclaimer baseline and bottom of lower LCD
        # -----------------------------------------
        img = self.font_disclaimer.render(disclaimer_text, True, DARK_BG)
        blit_y = self.y_top + self.lower_h - bottom_pad - img.get_height()
        self.screen.blit(img, (left_x, blit_y))

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Click hit-test. Deferred — return None for now (pentagon is static)."""
        return None


# =============================================================================
# E235-0 Lower LCD manager — subclasses E235-1000 to swap full-route renderer
# =============================================================================


class LowerDisplay(E235_1000_LowerDisplay):
    """E235-0 Lower LCD manager.

    Inherits the slot cycler (FULL/EIGHT/TRANSFER) from E235-1000. Overrides
    only the FULL slot's renderer when the active route is 山手線, swapping
    in the circular racetrack display. EIGHT (8-station zoom) and TRANSFER
    inherit unchanged — interim until the E235-0-specific 5-station view
    lands and replaces the EIGHT slot universally.

    Out-of-spec routes (any non-Yamanote loaded into E235-0) get the
    E235-1000 linear full-route renderer as a best-effort fallback,
    consistent with the project's per-model IRL-line-scope policy.
    """

    def __init__(self, screen, route_data, stops, mode_cycler):
        super().__init__(screen, route_data, stops, mode_cycler)
        # Swap full-route renderer for circular when route is Yamanote.
        if route_data.get("route") == "山手線":
            self.japanese_display = CircularFullRouteDisplay(screen, route_data, stops)

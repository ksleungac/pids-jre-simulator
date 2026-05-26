"""E235-1000 series Lower LCD display implementation.

Contains all display modes (Japanese, English) for the E235-1000 series
Lower LCD (route map, station markers, travel times, skip animation).

Modes share `ModeCycler` with the Upper LCD — when both modes are
implemented for the lower, switching the upper into ENGLISH will pull the
lower along in lockstep.

English mode is fully implemented for the full-route slot, rendering Romaji
station names rotated 45 degrees counter-clockwise with high-quality
supersampled bilinear anti-aliasing and horizontal squeeze compression for
long station names to prevent overlapping.
"""

import math
from typing import Dict, List, Optional, Tuple
import pygame
import pygame.gfxdraw

from app_paths import project_root
from constants import (
    PASSED_COLOR,
    CURRENT_COLOR,
    INACTIVE_COLOR,
    FONT_STOPS_SIZE,
    FONT_TIME_SIZE,
    FONT_STOPS_MINUTE_SIZE,
    STOPS_BAR_HEIGHT,
    STOPS_WIDTH,
    STOPS_PER_LINE,
    TIME_SCALE,
)
from displays.train_models.e235_1000 import (
    S_WIDTH,
    S_HEIGHT,
    UPPER_HEIGHT,
    DARK_BG,
    WHITE_BG,
)
from displays.train_models.e235_1000.transfer_info import TransferInfoDisplay
from displays.base import DisplayMode
from displays.utils import (
    draw_aapolygon,
    arrow_points,
    draw_stops_text,
    draw_1col_text,
    draw_station_code_badge,
    draw_route_disclaimer,
    draw_continuity_arrow,
    draw_continuity_triangle,
    EN_ROUTE_DISCLAIMER,
)

# =============================================================================
# Japanese Display (KANJI / FURIGANA modes — kanji station labels)
# =============================================================================


class JapaneseDisplay:
    """Lower LCD Japanese rendering for E235-1000.

    Drives the route-map view: station bars, kanji labels, markers, pointer,
    travel times, and the skip animation frame. Used for both KANJI and
    FURIGANA modes — the real PIDS does not furigana the route map.
    """

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        # Optional through-service pre-route prefix (e.g. Yokosuka→Tokyo before
        # Sōbu/1217F's Tokyo→Narita). Display-only — sim never indexes into it.
        # Pre-route cells render dim/passed regardless of train position.
        self.pre_stops = route_data.get("pre_stops", [])
        self.display_stops = self.pre_stops + self.stops
        self.display_offset = len(self.pre_stops)
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.contrast_color = route_data.get("contrast_color", [224, 54, 37])

        self._calculate_layout()

        # Cached window from last show_stops call — read by hit_test so click
        # geometry matches what was rendered, and so hit_test never re-mutates
        # `continuity[2]` via _get_stops_list_disp's side effect.
        self._last_window: Optional[List[Tuple[int, Dict]]] = None

        self.font_stops = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), FONT_STOPS_SIZE)
        self.font_time = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), FONT_TIME_SIZE)
        self.font_minute = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), FONT_STOPS_MINUTE_SIZE)
        self.font_disclaimer = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 10)
        # Hardcoded bar-extension width computed from the canonical ShinGo font.
        # EnglishDisplay overrides font_minute (Helvetica) but NOT this — the
        # route-map bar extension must stay the same pixel width IRL.
        self._minute_w, _ = self.font_minute.size("分")

    @property
    def disclaimer_text(self) -> str:
        return "のりかえ、待合せ時間は含まれません。電車により多少時間が異なります。一部区間では時間を表示しません。"

    def _calculate_layout(self) -> None:
        """Calculate station display layout based on route length.

        Layout sizes against ``self.display_stops`` (pre_stops + stops) so a
        through-service pre-route extends the visible journey naturally.
        Circular detection stays on ``self.stops`` — pre_stops can't make a
        non-circular route circular.
        """
        num_stops = len(self.display_stops)

        if num_stops <= STOPS_PER_LINE:
            self.per_line = num_stops
        else:
            self.per_line = min(STOPS_PER_LINE, math.ceil(num_stops / 2))

        self.stops_w = STOPS_WIDTH
        # Center to actual cell count drawn. For multi-line routes this equals
        # per_line (no change); for single-line routes with num_stops < per_line
        # (e.g. _mock/main at 11 stops) this recenters instead of leaving the row
        # left-leaning under a per_line-wide centered region.
        effective_cells = min(self.per_line, num_stops)
        self.x = (S_WIDTH - self.stops_w * effective_cells) // 2
        self.y = int(S_HEIGHT * 0.28)
        self.bar_height = STOPS_BAR_HEIGHT
        self.STOPS_QUANTITY = self.per_line * 2

        self.h_line = 105 if num_stops > self.per_line else 150
        self.top_pad = 40

        self.circular = 1 if self.stops and self.stops[0].get("name") == self.stops[-1].get("name") else 0
        self.continuity = [0, 0, 0]

        if self.circular == 1 or num_stops > 28:
            self.continuity = [1, 1, 1]
        elif num_stops > self.per_line:
            self.continuity = [1, 1, 0]

    def _get_line(self, i: int) -> int:
        """Get which line (1 or 2) a station index belongs to."""
        return 1 if i < self.per_line else 2

    # CONTRACT: continuity[2] must be recomputed on every call — not just at the
    # `remaining == STOPS_QUANTITY - 1` transition frame. See DISPLAY.md §
    # "Long-Route Window Refresh". Stale leak rendered slot-2 chevrons past Ōfuna.
    def _get_stops_list_disp(self, curr_stop: int) -> List[Tuple[int, Dict]]:
        """Get the list of (global_index, stop) pairs currently visible.

        ``curr_stop`` is the **display index** (sim's curr_stop + display_offset).
        Every rendered cell carries its display-space global index so drawing
        code can compare directly against display-shifted ``curr_stop`` /
        ``cursor_pos`` without juggling a second "local" index space.

        Operates on ``self.display_stops`` (pre_stops + stops) so a
        through-service pre-route extends the visible journey naturally.

        Side effect: keeps ``self.continuity[2]`` in sync with whether the
        currently visible window reaches the route's last stop. Without this,
        the slot-2 chevrons would render past the destination on long routes
        once the window slides (e.g. Keihin Ofuna).
        """
        if len(self.display_stops) <= self.STOPS_QUANTITY:
            return list(enumerate(self.display_stops))

        window_start = 0
        f_stops = self.display_stops[: self.STOPS_QUANTITY]

        # Flip rule: native long routes use early-flip ("remaining < QUANTITY"
        # so the user sees the end approaching). Pre-stops routes use late-flip
        # — keep window at start (so the through-service prefix remains visible)
        # until the train is forced off the right edge of the first window.
        # Without this distinction, sobu/1217F (37 cells, train enters at
        # display idx 18) would flip at boot — hiding Kurihama..Tokyo from view.
        if self.pre_stops:
            should_flip = curr_stop > self.STOPS_QUANTITY - 1
        else:
            remaining = len(self.display_stops) - curr_stop
            should_flip = 0 < remaining < self.STOPS_QUANTITY

        if should_flip:
            # Window has slid — visible window now includes the route's last
            # stop. Suppress slot 2 (no continuity past dest) for non-circular
            # routes.
            window_start = len(self.display_stops) - self.STOPS_QUANTITY
            f_stops = self.display_stops[window_start:]
            if self.circular != 1:
                self.continuity[2] = 0
        elif self.circular != 1 and len(self.display_stops) > 28:
            # Window hasn't slid yet (or user jumped back to an earlier stop):
            # there IS more route past the visible window. Restore slot 2.
            self.continuity[2] = 1

        return [(window_start + i, stop) for i, stop in enumerate(f_stops)]

    def _find_dest_index(self, f_stops: List[Tuple[int, Dict]], effective_dest: str) -> int:
        """Return the global index of the destination within the visible window.

        Takes the *effective* destination — caller resolves stop-level overrides
        (Yamanote's mid-loop dest cycling) before passing in. Falls back to the
        last visible global index if the destination isn't in the current window.
        """
        for gi, stop in f_stops:
            if stop.get("name", "") == effective_dest:
                return gi
        return f_stops[-1][0] if f_stops else 0

    def draw_ptr(self, f_stops: List[Tuple[int, Dict]], dest_idx: int, cursor_pos: int, curr_stop: int, at_station: bool = False) -> None:
        """Draw the pointer/marker indicating current position.

        Two pointer shapes:
          - **Pentagon** (red filled, with small light dot inside) at
            ``curr_stop``'s cell when ``at_station=True`` OR ``curr_stop == 0``.
            The STOPPING marker — train is parked at this platform.
          - **Chevron** (red arrow + halo) at ``cursor_pos`` when in
            APPROACHING. The directional pointer that leads through skip
            animation.

        ``curr_stop == 0`` is included with the pentagon path defensively —
        the chevron geometry has no left neighbor to anchor against at idx 0,
        so the boot fallback uses the same shape.
        """
        x = self.x
        y = self.y
        if not f_stops:
            return
        window_start = f_stops[0][0]
        ptr_color = self.contrast_color

        # `curr_stop == display_offset` is the boot fallback (active route's
        # first cell, no left neighbor for chevron geometry on routes without
        # pre_stops). Routes with pre_stops have left neighbors at boot, but
        # at_station=True at boot still selects pentagon — same end result.
        use_pentagon = at_station or curr_stop == self.display_offset

        # Pentagon anchors at curr_stop (the platform we're at). Chevron
        # anchors at cursor_pos (which can lag during skip animation).
        anchor = curr_stop if use_pentagon else cursor_pos
        local_disp = anchor - window_start
        # During a long-route window flip, a multi-station skip animation
        # can leave cursor_pos behind in the cut-off zone. Suppress the
        # pointer rather than rendering it at a wrong column — the inner
        # red dot at curr_stop still shows the actual train position.
        if local_disp < 0 or local_disp >= len(f_stops):
            return
        ptr = (local_disp % self.per_line) * self.stops_w
        line_num = self._get_line(local_disp)
        l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)

        if use_pentagon:
            # fmt: off
            # --- Pentagon params (adjust freely) ---
            overhang = 2
            head_extra = 10           # left bar-extension at row-head positions
            shift_x = -3              # nudge entire pentagon horizontally (negative = left;
                                      # tunes how far the apex pokes into the next cell)
            rect_right_offset = 0     # rectangle's right edge offset from cell's right (before shift_x)
            triangle_depth = 8        # apex extends this far past the rectangle's right edge —
                                      # controls pointiness (independent of rectangle width)
            dot_radius = 5            # interior light dot
            halo_offset = 3           # gray halo offset (drop-shadow style)
            # ----------------------------------------
            # fmt: on

            cell_left = x + ptr
            cell_right = cell_left + self.stops_w
            # Row-head cells widen the bar by row_head_extra to the LEFT.
            # The pentagon mirrors that so its left edge sits flush.
            is_row_head = (local_disp % self.per_line) == 0
            left_extra = head_extra if is_row_head else 0
            left_x = cell_left - left_extra + shift_x

            rect_right_x = cell_right + rect_right_offset + shift_x
            apex_x = rect_right_x + triangle_depth

            points = [
                (left_x, l_y - overhang),
                (left_x, l_y + self.bar_height + overhang),
                (rect_right_x, l_y + self.bar_height + overhang),
                (apex_x, l_y + self.bar_height / 2),
                (rect_right_x, l_y - overhang),
            ]
            # Halo is two x-shifted copies of the polygon (one each side),
            # both drawn before the body. The left copy's right edge + apex
            # tuck inside the body and only its left edge pokes out; the
            # right copy mirrors that on the apex side. Top/bottom remain
            # flush — extend overhang if a top/bottom outline is wanted.
            draw_aapolygon(self.screen, PASSED_COLOR, [(i - halo_offset, j) for (i, j) in points])
            draw_aapolygon(self.screen, PASSED_COLOR, [(i + halo_offset, j) for (i, j) in points])
            draw_aapolygon(self.screen, ptr_color, points)

            # Small light dot — centered on cell (not on rectangle), so the
            # marker stays where the cell's natural decoration would be.
            cell_cx = int(cell_left + self.stops_w // 2)
            cell_cy = int(l_y + self.bar_height / 2)
            pygame.gfxdraw.filled_circle(self.screen, cell_cx, cell_cy, dot_radius, PASSED_COLOR)
            pygame.gfxdraw.aacircle(self.screen, cell_cx, cell_cy, dot_radius, PASSED_COLOR)
        else:
            w = 18
            offset = int(w * 0.8)
            draw_aapolygon(
                self.screen,
                PASSED_COLOR,
                arrow_points(int(x + ptr - offset - 2), int(l_y), 23, self.bar_height, 16),
                5,
            )
            draw_aapolygon(
                self.screen,
                ptr_color,
                arrow_points(int(x + ptr - offset), int(l_y - 2), w, self.bar_height + 4, 10),
            )

    # CONTRACT: inner red dot at `curr_stop` (PA target); pointer at `cursor_pos`
    # (lags during skip — intentional). See DISPLAY.md § "Station Skip Logic (full spec)".
    # DON'T "fix" the divergence to make them match.
    def draw_marks(self, f_stops: List[Tuple[int, Dict]], dest_idx: int, cursor_pos: int, curr_stop: int) -> None:
        """Draw station markers (circles and arrows).

        Cell decorations: passing-station chevron (no pa), small light dot for
        passed cells (gi < cursor_pos), or active-cell ring with optional inner
        red disk at curr_stop. The STOPPING-cell decoration (pentagon + small
        dot) is drawn by ``draw_ptr`` — pentagon overdraws whatever this method
        paints at the curr_stop cell, so no special-case skip is needed here.
        """
        if not f_stops:
            return
        x = self.x
        y = self.y
        window_start = f_stops[0][0]

        # --- Mark sizing (adjust freely) ---
        small_dot_radius = 5  # passed-style + boot pentagon interior
        active_ring_radius = 11  # outer ring on active stops
        inner_disk_inset = 2  # active_ring_radius - inner = visible ring thickness
        passing_arrow_w = 14  # passing-station chevron width
        passing_arrow_stroke = 6  # chevron body thickness
        # ------------------------------------

        for gi, stop in f_stops:
            local_i = gi - window_start
            ptr = (local_i % self.per_line) * self.stops_w
            line_num = self._get_line(local_i)
            l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)
            offset = self.stops_w // 2
            center_x = int(x + ptr + offset)
            center_y = int(l_y + self.bar_height / 2)

            in_active_range = cursor_pos <= gi <= dest_idx

            if in_active_range:
                if gi == self.display_offset and cursor_pos == self.display_offset:
                    # Boot pentagon at the active route's start cell — pentagon
                    # (drawn in draw_ptr) paints over this cell. Skip drawing
                    # here entirely. For routes without pre_stops, display_offset
                    # is 0 so this matches the original "idx 0 boot" semantic.
                    continue
                if not stop.get("pa", []):
                    arrow_offset = int(self.stops_w * 0.3)
                    draw_aapolygon(
                        self.screen,
                        PASSED_COLOR,
                        arrow_points(
                            int(x + ptr + arrow_offset),
                            int(l_y + 4),
                            passing_arrow_w,
                            self.bar_height - 8,
                            passing_arrow_stroke,
                        ),
                    )
                else:
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, active_ring_radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, active_ring_radius, PASSED_COLOR)

                    # Inner red dot marks the actual PA target — stays at
                    # curr_stop even while the cursor lags during a skip.
                    # (When at_station=True, the pentagon overdraws this — fine.)
                    if gi == curr_stop:
                        inner_radius = active_ring_radius - inner_disk_inset
                        pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, inner_radius, CURRENT_COLOR)
                        pygame.gfxdraw.aacircle(self.screen, center_x, center_y, inner_radius, CURRENT_COLOR)
            else:
                pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, small_dot_radius, PASSED_COLOR)
                pygame.gfxdraw.aacircle(self.screen, center_x, center_y, small_dot_radius, PASSED_COLOR)

    def draw_times(
        self,
        f_stops: List[Tuple[int, Dict]],
        dest_idx: int,
        cursor_pos: int,
        current_time: float,
        departure_time: float,
        is_last_pa: bool,
        at_station: bool = False,
        curr_stop: int = 0,
    ) -> None:
        """Draw travel times between stations.

        CONTRACT (countdown formula). For the *first* time-cell from the
        cursor, the displayed minutes count down in real time:
        ``remaining = max(1, stop["time"] - int(elapsed_minutes))`` where
        ``elapsed_minutes = (now - departure_time) / TIME_SCALE``. Subsequent
        cells are cumulative additions of static ``stop["time"]`` values
        (they don't tick — only the first cell does).

        - ``TIME_SCALE = 60`` means 60 real seconds = 1 travel minute (real-
          time mode). See constants.py for the scale knob.
        - ``int(elapsed_minutes)`` is intentional integer truncation, so the
          display only decrements after a *full* travel-minute has elapsed.
        - ``max(1, ...)`` clamps to 1 — the display never shows 0.
        - ``is_last_pa`` shortcuts the formula to a hard 1 (arriving now).
        - ``departure_time = 0.0`` is the uninitialized sentinel (set on stop
          advance in app.py); the ``if current_time > 0 and departure_time > 0``
          guard freezes ``elapsed_minutes`` at 0 until the first real advance,
          which is why preview mode boots into a frozen countdown.
        """
        if not f_stops:
            return
        x = self.x
        y = self.y
        window_start = f_stops[0][0]
        cumulative_time = 0

        elapsed_minutes = 0
        if current_time > 0 and departure_time > 0:
            elapsed_seconds = current_time - departure_time
            elapsed_minutes = elapsed_seconds / TIME_SCALE

        is_first_station = True

        for gi, stop in f_stops:
            if gi == 0 and cursor_pos == 0:
                continue
            if at_station and gi == curr_stop:
                # We're at the platform — the time number here would represent
                # incoming travel that already finished (= 0 useful). Skip the
                # whole render block. Subsequent cells render as if cursor were
                # one cell to the right (cumulative starts fresh from the next
                # leg out, no carry-over of stops[curr_stop]["time"]).
                continue

            local_i = gi - window_start
            ptr = (local_i % self.per_line) * self.stops_w
            line_num = self._get_line(local_i)
            l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)

            # Active range: cursor_pos..dest_idx (matches draw_marks). Without
            # the dest_idx upper bound, circular routes (Yamanote) with a
            # mid-window stop-level dest override would render time labels in
            # the inactive bars past dest_idx — visible bug on those routes.
            if cursor_pos <= gi <= dest_idx and "time" in stop:
                t_w, t_h = self.font_time.size("0")

                if is_first_station:
                    if at_station:
                        # First rendered cell after STOPPING@curr_stop: show
                        # static stops[gi]["time"] (= leg from platform to here).
                        # No countdown (we haven't departed; departure_time is
                        # stale from the previous segment).
                        cumulative_time = stop["time"]
                    elif is_last_pa:
                        cumulative_time = 1
                    else:
                        elapsed_full_minutes = int(elapsed_minutes)
                        remaining_time = max(1, stop["time"] - elapsed_full_minutes)
                        cumulative_time = remaining_time
                    is_first_station = False
                else:
                    cumulative_time += stop["time"]

                time_str = str(int(cumulative_time))
                time_x = int(x + ptr + (self.stops_w - t_w * len(time_str)) / 2)
                time_y = int(l_y + (self.bar_height - t_h) / 2)
                time_img = self.font_time.render(time_str, True, DARK_BG)
                self.screen.blit(time_img, (time_x, time_y))

                # 分-marker only renders alongside a time number — passing stations
                # (no `time` key) at line-end / dest must not get a stranded 分.
                if local_i == self.per_line - 1 or gi == dest_idx:
                    self.draw_minute_marker(local_i, gi, f_stops[-1][0], ptr, l_y, dest_idx)

    def draw_minute_marker(self, local_i: int, gi: int, last_gi: int, ptr: int, l_y: int, dest_idx: int) -> None:
        marker_text = getattr(self, "minute_marker_text", "分")
        # Bar extension width is hardcoded to the Japanese "分" glyph width —
        # never use marker_text (e.g. English "min") for this, or the route-map
        # bar will extend further right in English than IRL.
        minute_w = self._minute_w
        _, text_h = self.font_minute.size(marker_text)
        minute_y = int(l_y + (self.bar_height - text_h) / 2)

        # Row-end cells widen the bar by `row_tail_extra` (see
        # show_stops). Shift the 分 marker right by the same amount
        # so it stays at the right edge of the widened bar. Mid-row
        # dest cells (Yamanote stop-level dest override) get no
        # widening, so no shift either.
        is_row_end = local_i == self.per_line - 1 or gi == last_gi
        cell_extra = 10 if is_row_end else 0  # mirror show_stops `row_tail_extra`
        minute_x = int(self.x + ptr + self.stops_w + cell_extra)

        # White separator caps the bar's right edge when there's no
        # continuity tail. Suppress when this cell flows into the
        # continuity chevrons — bar should be visually continuous.
        is_continuity_tail = (local_i == self.per_line - 1 and self.continuity[0]) or (gi == last_gi and self.continuity[2])

        pygame.draw.rect(
            self.screen,
            self.color,
            pygame.Rect(minute_x, int(l_y), minute_w, self.bar_height),
        )
        if not is_continuity_tail:
            pygame.draw.rect(
                self.screen,
                WHITE_BG,
                pygame.Rect(minute_x + minute_w - 3, int(l_y), 3, self.bar_height),
            )

        # marker character keeps its original position (no cell_extra shift) —
        # only the marker bg rect follows the widened bar's right edge.
        minute_img = self.font_minute.render(marker_text, True, WHITE_BG)
        offset = getattr(self, "minute_marker_offset", self.stops_w * 0.85)
        self.screen.blit(minute_img, (int(self.x + ptr + offset), minute_y))

    def draw_station_name(self, stop, text_color: Tuple[int, int, int], x: int, y: int) -> None:
        draw_stops_text(
            self.font_stops,
            stop.get("name", ""),
            text_color,
            x,
            y,
            self.stops_w,
            self.screen,
        )

    # CONTRACT: row_head_extra / row_tail_extra magic numbers MUST stay in sync
    # with draw_ptr's pentagon `head_extra` and draw_times' 分-marker `cell_extra`.
    # See DISPLAY_E235.md § "Row-end / row-head bar extension" — change one, change all.
    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the full lower LCD frame for this mode.

        Args:
            state: AppState instance — read-only here. Skip-progress mutation
                lives on AppState itself (see ``AppState.update_skip_progress``)
                and runs in the app loop before this method is called.
            current_time: Wall-clock timestamp for countdown calculation.
        """
        # Display indices = sim indices + display_offset (= len(pre_stops)).
        # Renderers operate in display-index space throughout.
        curr_stop = state.curr_stop + self.display_offset
        cursor_pos = state.cursor_pos + self.display_offset

        f_stops = self._get_stops_list_disp(curr_stop)
        self._last_window = f_stops
        x = self.x
        y = self.y
        window_start = f_stops[0][0] if f_stops else 0

        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(0, int(y), S_WIDTH, S_HEIGHT - int(y)))

        if state.frame_mode == 0:
            return

        # Resolve effective destination — stop-level override beats route-level
        # (matches UpperDisplay._get_current_dest). Yamanote's mid-loop dest
        # cycling depends on this to keep the active bar range correct. Reads
        # against sim's stops[] (not display_stops) since stop-level dest
        # overrides only live on active stops. Loader fills dest on every
        # stop via sticky closure (route_loader); direct read, no fallback.
        sim_curr_stop = state.curr_stop
        if 0 <= sim_curr_stop < len(self.stops):
            effective_dest = self.stops[sim_curr_stop]["dest"]
        else:
            effective_dest = self.dest

        dest_idx = self._find_dest_index(f_stops, effective_dest)

        # fmt: off
        # --- Continuity-tail params (adjust freely) ---
        # Last-in-row cells get a +row_tail_extra width bump (applies to row 1's
        # last cell AND row 2's last visible cell, independent of continuity).
        # Continuity adds chevrons on top of that when self.continuity[0]/[2] is
        # set: bar (+row_tail_extra) → 分-area → triangle (bar's tapered tail)
        # → gap → chevron 1 → gap → chevron 2. All in cell_color (active = route
        # color, passed = INACTIVE_COLOR).
        row_tail_extra = 10      # extra px on the bar cell at row-end positions (extends RIGHT)
        row_head_extra = 10      # extra px on the bar cell at row-head positions (extends LEFT)
        cont_tri_w = 8           # bar-tail triangle width (apex right) — matches red cursor's tip slope
        cont_chev_n = 2          # number of chevrons after the triangle
        cont_chev_w = 12         # chevron horizontal extent
        cont_chev_stroke = 4     # chevron body thickness — tip-portion = w−stroke = 8 = tri_w,
                                 # so triangle and chevron tips have the same slope (uniform pointiness).
        cont_chev_gap = -4       # negative = chevron BBs OVERLAP. Combined with tip-portion = tri_w,
        # this makes ALL three gaps (triangle→chev1, chev1→chev2, body+center)
        # render as a uniform 4-px white margin.
        # -----------------------------------------------
        # fmt: on

        minute_w = self._minute_w  # Layout always uses fixed "分" width
        last_gi = f_stops[-1][0] if f_stops else -1

        for gi, stop in f_stops:
            local_i = gi - window_start
            ptr = (local_i % self.per_line) * self.stops_w
            line_num = self._get_line(local_i)
            l_y = int(y + self.h_line * line_num + self.top_pad * (line_num - 1))

            is_active = gi >= cursor_pos and gi <= dest_idx
            cell_color = self.color if is_active else INACTIVE_COLOR

            is_row1_head = local_i == 0
            is_row2_head = local_i == self.per_line
            is_row1_tail = local_i == self.per_line - 1
            is_row2_tail = gi == last_gi
            is_slot0 = is_row1_tail and self.continuity[0]
            is_slot1 = is_row2_head and self.continuity[1]
            is_slot2 = is_row2_tail and self.continuity[2]

            # Bar extension applies to ALL row-end and row-head cells
            # (independent of continuity). Continuity adds chevron tail / 'from'
            # indicator on top.
            left_extra = row_head_extra if (is_row1_head or is_row2_head) else 0
            right_extra = row_tail_extra if (is_row1_tail or is_row2_tail) else 0
            bar_x = x + ptr - left_extra
            bar_w = self.stops_w + left_extra + right_extra

            # Slot 1 cells extend the bar an extra cont_tri_w to the LEFT so
            # the inward notch carve doesn't shrink the bar's visible width.
            # Slot 0/2 add the equivalent on the right via the tail extension.
            slot1_left_compensate = cont_tri_w if is_slot1 else 0
            bar_x_eff = bar_x - slot1_left_compensate
            bar_w_eff = bar_w + slot1_left_compensate

            pygame.draw.rect(
                self.screen,
                cell_color,
                pygame.Rect(int(bar_x_eff), l_y, bar_w_eff, self.bar_height),
            )

            # Slot 1 'from' indicator — line-2's first cell.
            # Layout (left → right): chev1 → chev2 → bar with notched left edge.
            # Drawing order: bar → notch (white over bar) → chevrons (cell_color
            # over notch) so chev2's tip pokes into the notch's V-shape, exactly
            # mirroring slot 0/2's chev1 nestling against the outward triangle's
            # tip. All gaps render as uniform 4 px.
            if is_slot1:
                # White notch carved into the bar's (extended) left edge.
                notch_points = [
                    (bar_x_eff, l_y),
                    (bar_x_eff, l_y + self.bar_height),
                    (bar_x_eff + cont_tri_w, l_y + self.bar_height // 2),
                ]
                draw_aapolygon(self.screen, WHITE_BG, notch_points)

                # Chevrons. chev2_x derived for 4-px uniform gap at top/bottom AND
                # at the V-center: bar_x_eff − (chev2_x + stroke) = 4 → chev2_x =
                # bar_x_eff − 8. Tip pokes 4 px past bar_x_eff (into notch zone),
                # gets overdrawn in cell_color → visually nestles into the V.
                chev_step = cont_chev_w + cont_chev_gap
                chev2_x = bar_x_eff - cont_chev_stroke - 4  # 4 = visible top gap
                chev1_x = chev2_x - chev_step
                # Chevrons sit on the segment LEADING INTO this cell — they
                # should dim once the train has arrived (cursor_pos >= gi),
                # even though the cell itself is still active. Slots 0/2 don't
                # need this because their chevrons trail off their own cell
                # which naturally flips inactive when cursor passes.
                chev_color = self.color if (cursor_pos < gi and gi <= dest_idx) else INACTIVE_COLOR
                draw_continuity_arrow(
                    self.screen,
                    int(chev1_x),
                    l_y,
                    self.bar_height,
                    chev_color,
                    n_chevrons=cont_chev_n,
                    chevron_w=cont_chev_w,
                    chevron_stroke=cont_chev_stroke,
                    chevron_gap=cont_chev_gap,
                )

            text_color = (0, 0, 0) if (is_active and (stop.get("pa", []) or gi == self.display_offset)) else INACTIVE_COLOR

            # Slot 0 / 2 'to' indicator — extended bar tail + 分-area + triangle + chevrons.
            # Slot 0: last cell of line 1; slot 2: last visible cell when window
            # has slid.
            if is_slot0 or is_slot2:
                tail_x = x + ptr + self.stops_w + right_extra
                # 分-area extension in cell_color. When the cell is passed,
                # draw_times skips this cell so we paint the extension here to
                # keep the bar continuous; when active, draw_times overdraws
                # in route color (no visual difference).
                pygame.draw.rect(
                    self.screen,
                    cell_color,
                    pygame.Rect(int(tail_x), l_y, minute_w, self.bar_height),
                )
                # Triangle — bar's tapered tail (continuous with the bar).
                tri_x = tail_x + minute_w
                draw_continuity_triangle(
                    self.screen,
                    int(tri_x),
                    l_y,
                    self.bar_height,
                    cell_color,
                    tri_w=cont_tri_w,
                )
                # Chevrons — `chev_x` placed so the triangle→chev1 gap matches
                # the chev1→chev2 gap (uniform 4-px white margin everywhere).
                chev_x = tri_x + cont_tri_w + cont_chev_gap
                draw_continuity_arrow(
                    self.screen,
                    int(chev_x),
                    l_y,
                    self.bar_height,
                    cell_color,
                    n_chevrons=cont_chev_n,
                    chevron_w=cont_chev_w,
                    chevron_stroke=cont_chev_stroke,
                    chevron_gap=cont_chev_gap,
                )

            self.draw_station_name(
                stop,
                text_color,
                int(x + ptr),
                int(l_y - 7),
            )

        self.draw_marks(f_stops, dest_idx, cursor_pos, curr_stop)
        self.draw_ptr(f_stops, dest_idx, cursor_pos, curr_stop, state.at_station)
        self.draw_times(f_stops, dest_idx, cursor_pos, current_time, state.departure_time, state.is_last_pa, state.at_station, curr_stop)

        draw_route_disclaimer(self.screen, self.font_disclaimer, S_WIDTH - 8, S_HEIGHT - 4, (0, 0, 0), self.disclaimer_text)

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Map LCD-local (mx, my) to a sim_index for click-to-jump.

        Returns None for clicks outside any cell, or for pre_stops cells
        (visible-but-not-clickable through-service prefix). Reads the
        last-rendered window so click geometry matches what's on screen.
        Past-dest filtering (`sim_idx > dest_stop_idx`) lives in the caller —
        that index is on `PASimulator`, not the renderer.
        """
        f_stops = self._last_window
        if not f_stops or state is None:
            return None
        window_start = f_stops[0][0]

        is_multi_row = len(f_stops) > self.per_line
        if is_multi_row:
            row1_bottom = self.y + self.h_line + self.bar_height
            row2_top = self.y + 2 * self.h_line + self.top_pad
            mid_split = (row1_bottom + row2_top) // 2
            row1_band = (self.y, mid_split)
            row2_band = (mid_split, row2_top + self.bar_height + 30)
        else:
            row1_band = (self.y, self.y + self.h_line + self.bar_height + 30)
            row2_band = None

        for gi, _ in f_stops:
            local_i = gi - window_start
            line_num = self._get_line(local_i)
            cell_x = self.x + (local_i % self.per_line) * self.stops_w
            band = row1_band if line_num == 1 else row2_band
            if band is None:
                continue
            band_top, band_bot = band
            if cell_x <= mx < cell_x + self.stops_w and band_top <= my < band_bot:
                sim_idx = gi - self.display_offset
                if sim_idx < 0:
                    return None
                return sim_idx
        return None


# =============================================================================
# Japanese Display — 8-station zoomed-in view
# =============================================================================


class JapaneseEightStationDisplay:
    """Lower LCD Japanese 8-station zoomed-in view for E235-1000.

    Sliding-window route map showing the next 8 stations from curr_stop
    with larger cells than the full-route view. Window logic:

    - remaining > 8 → window = [curr_stop : curr_stop+8]; pointer locked
      to leftmost cell. Window jumps forward as curr_stop advances.
    - remaining ≤ 8 → window locks to last 8 stops (or all if total < 8);
      pointer marches rightward inside this fixed window.

    Vertical-kanji compression baseline: 4-character height. Names with
    ≤4 kanji render uncompressed (stacked from the top); 5+ compress
    proportionally to fit a 4-char-tall vertical band.

    Per-cell station code badge (mini JO/JY framed square) is drawn under
    each bar using `sta_code` from route.json.
    """

    VISIBLE_COUNT = 8
    # Lock the window when only this many (or fewer) stations remain ahead.
    # Set to VISIBLE_COUNT - 1 = 7 so the locked window has room for one
    # already-passed cell on the train's left, providing context as the
    # cursor marches across the remaining route.
    LOCK_THRESHOLD = 7

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        # Optional through-service pre-route prefix; see JapaneseDisplay above.
        self.pre_stops = route_data.get("pre_stops", [])
        self.display_stops = self.pre_stops + self.stops
        self.display_offset = len(self.pre_stops)
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.contrast_color = route_data.get("contrast_color", [224, 54, 37])

        # fmt: off
        # --- Layout params (adjust freely) ---
        # Top of the lower-LCD region (just below upper LCD)
        self.top_y = UPPER_HEIGHT
        # Side margin — reserves space at the bar's left and right ends for
        # future continuity arrows (route-continues indicators).
        self.side_margin = 44
        # Cell geometry — 8 cells distributed across the inner width.
        self.cells = min(self.VISIBLE_COUNT, len(self.display_stops))
        inner_w = S_WIDTH - 2 * self.side_margin
        self.stops_w = inner_w // self.VISIBLE_COUNT
        self.x = (S_WIDTH - self.stops_w * self.cells) // 2
        # Vertical band layout (top → bottom): top_pad → kanji label →
        # gap → bar → gap → badge → bottom_pad
        self.label_top_pad = 19  # 14 + 5px nudge to clear the upper LCD bottom edge
        self.label_h_chars = 4  # 4-char-baseline (no compress for ≤4 chars)
        self.label_font_size = 30  # bigger than full-route's 25 (cells are 2× wider)
        self.label_bar_gap = 10
        self.bar_height = 38
        self.bar_badge_gap = 4  # gap between bar bottom and badge top
        # Badge sized to roughly half the station circle (r=15, diameter 30).
        # Square shape mirrors the upper-LCD badge ratio (which is 1:1).
        self.badge_w = 22
        self.badge_h = 22
        # ------------------------------------
        # fmt: on

        self.font_stops = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), self.label_font_size)
        self.font_time = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), FONT_TIME_SIZE + 7)
        self.font_minute = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), FONT_STOPS_MINUTE_SIZE + 3)
        # Badge fonts.
        self.font_badge_prefix = pygame.font.Font(str(project_root() / "fonts" / "NeueFrutigerWorld-Bold.otf"), 8)
        self.font_badge_num = pygame.font.Font(str(project_root() / "fonts" / "NeueFrutigerWorld-Bold.otf"), 11)
        self.font_disclaimer = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 10)
        # Hardcoded bar-extension width from the canonical ShinGo "分" glyph.
        # Subclasses override font_minute but NOT this — bar width stays fixed.
        self._minute_w, _ = self.font_minute.size("分")

        # Derived band geometry (top_y of each row)
        _, t_h = self.font_stops.size("東")
        self._char_h = t_h
        self.label_top_y = self.top_y + self.label_top_pad
        self.label_box_h = self.label_h_chars * t_h
        self.bar_y = self.label_top_y + self.label_box_h + self.label_bar_gap
        self.badge_y = self.bar_y + self.bar_height + self.bar_badge_gap

        self.circular = 1 if self.stops and self.stops[0].get("name") == self.stops[-1].get("name") else 0

        # Cached window from last show_stops call — read by hit_test.
        self._last_window: Optional[List[Tuple[int, Dict]]] = None

    @property
    def disclaimer_text(self) -> str:
        return "のりかえ、待合せ時間は含まれません。電車により多少時間が異なります。一部区間では時間を表示しません。"

    def _label_text(self, stop: Dict) -> str:
        """Return the station name text for labels. Subclasses override for English."""
        return stop.get("name", "")

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    # CONTRACT: window invariant — exactly 8 cells, three regimes (short / sliding / locked).
    # See DISPLAY_E235.md § "Window invariant — always exactly 8 cells" for the
    # cursor-local-index table. Past regressions came from editing without consulting it.
    def _get_window(self, curr_stop: int, cursor_pos: int) -> List[Tuple[int, Dict]]:
        """Return (global_index, stop) pairs for the visible 8-cell window.

        Always 8 cells: 1 already-passed cell + cursor + 6 ahead.

        - len(stops) ≤ VISIBLE_COUNT → return everything (short-route case).
        - curr_stop == 0 → no past cell available; window = [0..7].
        - curr_stop > n-VISIBLE_COUNT → locked (keyed on curr_stop, not
          cursor_pos, so the destination cell stays visible during a near-end
          skip animation); window = [n-8 .. n-1]. Cursor marches rightward.
        - otherwise → sliding, anchored on cursor_pos (NOT curr_stop) so the
          visible cursor always has 1 past cell to its left even mid-skip
          (when cursor_pos lags behind curr_stop). window = [cursor_pos-1 ..
          cursor_pos+6]. Cursor sits at local index 1.

        Anchoring sliding on cursor_pos means the window slides forward by
        one cell at the moment cursor_pos catches up to curr_stop after a
        skip animation — visible single-frame shift, but preserves the
        "1 past cell always visible" contract per the docstring.
        """
        # Operates in display-index space against display_stops (pre + active).
        # `curr_stop` and `cursor_pos` are display-shifted by the caller.
        n = len(self.display_stops)
        if n <= self.VISIBLE_COUNT:
            return list(enumerate(self.display_stops))

        if curr_stop == 0:
            start = 0
        elif curr_stop > n - self.VISIBLE_COUNT:
            start = n - self.VISIBLE_COUNT
        else:
            start = cursor_pos - 1
        return [(start + i, s) for i, s in enumerate(self.display_stops[start : start + self.VISIBLE_COUNT])]

    def _find_dest_index(self, window: List[Tuple[int, Dict]], effective_dest: str) -> int:
        """Global index of the effective destination within the visible window."""
        for gi, stop in window:
            if stop.get("name", "") == effective_dest:
                return gi
        return window[-1][0] if window else 0

    # ------------------------------------------------------------------
    # Vertical kanji label
    # ------------------------------------------------------------------

    def _draw_label(self, text: str, cell_x: int, color: Tuple[int, int, int]) -> None:
        """Stack kanji vertically inside the label band.

        Three cases mirror the full-route renderer's conventions:

        1. Compound name with a space separator (Keihin's
           "さいたま 新都心" case) — render two columns side-by-side, with
           the FIRST half on the right and the SECOND half on the left
           (Japanese top-to-bottom right-to-left reading order).

        2. Single-character name (Keihin's "蕨", "鶯谷"-area entries) —
           center the lone glyph vertically in the label box rather than
           pinning it to the top.

        3. Default — top+bottom aligned vertical stack via
           `draw_1col_text`. 2-char names occupy the same vertical extent
           as 4-char names; names with > `label_h_chars` chars compress
           to fit.
        """
        if not text:
            return

        bottom_y = self.label_top_y + self.label_box_h

        # Case 1: compound name (two columns, right-then-left reading order).
        # IRL convention (see lcd_references/zoom_keihin_saitama.png):
        #   - Both columns share a 3-character standard height. A 3-char
        #     part renders uncompressed; a 4-char part (e.g. さいたま vs
        #     the 3-char 新都心) auto-compresses to fit via `draw_1col_text`.
        #     The compression is what visually signals that さいたま is the
        #     "raised, denser" half of the compound.
        #   - Right column (parts[0]) is TOP-anchored at `label_top_y` so it
        #     lines up with single-column stops' tops.
        #   - Left column (parts[1]) is BOTTOM-anchored at the label box's
        #     bottom so it lines up with single-column stops' bottoms.
        parts = text.split()
        if len(parts) >= 2:
            c_w, _ = self.font_stops.size(parts[0][0] if parts[0] else "東")
            col_gap = 2  # px between the two columns
            total_w = c_w * 2 + col_gap
            block_left_x = cell_x + (self.stops_w - total_w) // 2
            baseline_vs = 3 * self._char_h  # 3-char standard height
            # Right top at label_top_y → bottom = label_top_y + baseline_vs.
            right_bottom_y = self.label_top_y + baseline_vs
            # Left bottom at label box bottom (= aligns with single-col bottoms).
            left_bottom_y = self.label_top_y + self.label_box_h
            # Right column reads FIRST (parts[0]); left column reads SECOND.
            draw_1col_text(self.font_stops, parts[1], int(block_left_x), int(left_bottom_y), baseline_vs, color, self.screen)
            draw_1col_text(self.font_stops, parts[0], int(block_left_x + c_w + col_gap), int(right_bottom_y), baseline_vs, color, self.screen)
            return

        # Case 2: single-character name — vertically center in the label box
        if len(text) == 1:
            char_w, char_h = self.font_stops.size(text)
            char_x = cell_x + (self.stops_w - char_w) // 2
            char_y = self.label_top_y + (self.label_box_h - char_h) // 2
            img = self.font_stops.render(text, True, color)
            self.screen.blit(img, (int(char_x), int(char_y)))
            return

        # Case 3: default — top+bottom aligned vertical stack
        c_w, _ = self.font_stops.size(text[0])
        glyph_x = cell_x + (self.stops_w - c_w) // 2
        # `draw_1col_text` interprets `y` as the BOTTOM of the band:
        # it positions chars from `y - vert_space` (top) downward.
        draw_1col_text(self.font_stops, text, int(glyph_x), int(bottom_y), self.label_box_h, color, self.screen)

    # ------------------------------------------------------------------
    # Bar / pointer / marks / times
    # ------------------------------------------------------------------

    def draw_marks(
        self,
        window: List[Tuple[int, Dict]],
        dest_idx: int,
        cursor_pos: int,
        curr_stop: int,
    ) -> None:
        """Draw station markers (circles for PA stations, arrows for passing)."""
        if not window:
            return
        x = self.x
        y = self.bar_y
        window_start = window[0][0]

        for gi, stop in window:
            local_i = gi - window_start
            ptr = local_i * self.stops_w
            offset = self.stops_w // 2
            center_x = int(x + ptr + offset)
            center_y = int(y + self.bar_height / 2)

            if gi >= cursor_pos and gi <= dest_idx:
                if gi == self.display_offset and cursor_pos == self.display_offset:
                    # Boot at active route's first cell — pentagon (drawn in
                    # draw_ptr) overdraws; small dot underneath for parity.
                    radius = 6
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                elif not stop.get("pa", []):
                    # Passing-station chevron — horizontally centered in the cell so
                    # it aligns with the vertical kanji label above (which is
                    # centered too). Old `stops_w * 0.35` constant left it ~4px shy
                    # of center for our 84-px-wide cells.
                    arrow_w = 18
                    arrow_pad_y = 5
                    arrow_x = int(x + ptr + (self.stops_w - arrow_w) // 2)
                    draw_aapolygon(
                        self.screen,
                        PASSED_COLOR,
                        arrow_points(
                            arrow_x,
                            int(y + arrow_pad_y),
                            arrow_w,
                            self.bar_height - 2 * arrow_pad_y,
                            8,
                        ),
                    )
                else:
                    radius = 15
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)

                    if gi == curr_stop:
                        # Inner olive disc — sized as outer-radius minus a thin
                        # white halo (was -3, bumped to -2 per reference).
                        inner_r = radius - 2
                        pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, inner_r, CURRENT_COLOR)
                        pygame.gfxdraw.aacircle(self.screen, center_x, center_y, inner_r, CURRENT_COLOR)
            else:
                radius = 6
                pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)

    def draw_ptr(
        self,
        window: List[Tuple[int, Dict]],
        cursor_pos: int,
        curr_stop: int,
        at_station: bool = False,
    ) -> None:
        """Red triangle/pentagon pointer at cursor_pos (or curr_stop in STOPPING).

        Mirrors the full-route view's two-shape dispatch: pentagon when
        ``at_station`` OR ``curr_stop == 0``, chevron otherwise.
        """
        if not window:
            return
        x = self.x
        y = self.bar_y
        window_start = window[0][0]

        # Boot fallback: pentagon at active route's first cell. For routes
        # without pre_stops, display_offset=0 so this matches the original
        # `curr_stop == 0` semantic. With pre_stops, at_station=True at boot
        # already selects pentagon — same end result.
        use_pentagon = at_station or curr_stop == self.display_offset
        anchor = curr_stop if use_pentagon else cursor_pos
        local_disp = anchor - window_start
        # During a multi-station skip animation, cursor_pos can lag before
        # window_start (or past window end) — suppress rather than rendering
        # at a wrong column. The inner red dot at curr_stop still shows the
        # actual train position. Mirrors the full-route pointer's guard.
        if local_disp < 0 or local_disp >= len(window):
            return
        ptr_x = local_disp * self.stops_w
        ptr_color = self.contrast_color

        if not use_pentagon:
            # fmt: off
            # --- Pointer params (adjust freely) ---
            # See `arrow_points` docstring for what `stroke` actually controls
            # (chevron BODY thickness — NOT line stroke).
            inner_w = 32
            inner_stroke = 20  # ratio 0.625 — less pointy than full-route's 0.545
            inner_h_overshoot = 2  # protrudes 1px above and 1px below the bar
            # Outer outline params — sized so the OUTER's tip-length matches the
            # INNER's tip-length, otherwise the white halo reads thicker (more
            # pointy) at the chevron's tip than along its body. Setting
            # outer_stroke = inner_stroke + (outer_w - inner_w) keeps both tips
            # at the same horizontal length: outer_w - outer_stroke == inner_w
            # - inner_stroke. The outline sits centered around the inner so the
            # halo is uniform (3 px on each side for a 6-px width delta).
            outer_w_delta = 6  # outer is this much wider than inner overall
            outer_w = inner_w + outer_w_delta
            outer_stroke = inner_stroke + outer_w_delta
            outer_x_offset = -outer_w_delta // 2  # center outer around inner
            offset_factor = 0.4  # 0.5 = body centered on cell boundary; lower = more into cursor cell
            # ---------------------------------------
            # fmt: on
            offset = int(inner_w * offset_factor)
            inner_y_off = -inner_h_overshoot // 2
            inner_h = self.bar_height + inner_h_overshoot
            draw_aapolygon(
                self.screen,
                PASSED_COLOR,
                arrow_points(int(x + ptr_x - offset + outer_x_offset), int(y), outer_w, self.bar_height, outer_stroke),
                5,
            )
            draw_aapolygon(
                self.screen,
                ptr_color,
                arrow_points(int(x + ptr_x - offset), int(y + inner_y_off), inner_w, inner_h, inner_stroke),
            )
        else:
            # STOPPING pentagon — drawn at curr_stop's cell. Generalized from
            # the original boot-state pentagon at curr_stop=0 (when the
            # chevron has no left neighbor to anchor against).
            # fmt: off
            # --- Pentagon params (adjust freely) ---
            overhang = 1            # protrudes above/below bar (matches chevron's inner_h_overshoot // 2)
            shift_x = -3            # nudge left (matches full-route convention)
            rect_right_offset = 0   # rectangle's right edge offset from cell border
            triangle_depth = 10     # apex extends past rect_right_x by this much
            dot_radius = 6          # interior light dot (matches passed-style dot at curr_stop=0)
            halo_offset = 3         # gray drop-shadow offset
            # ---------------------------------------
            # fmt: on

            cell_left = x + ptr_x
            cell_right = cell_left + self.stops_w
            left_x = cell_left + shift_x
            rect_right_x = cell_right + rect_right_offset + shift_x
            apex_x = rect_right_x + triangle_depth

            points = [
                (left_x, y - overhang),
                (left_x, y + self.bar_height + overhang),
                (rect_right_x, y + self.bar_height + overhang),
                (apex_x, y + self.bar_height / 2),
                (rect_right_x, y - overhang),
            ]
            # Halo: two x-shifted copies (mirrors full-route view) so left
            # edge gets an outline matching the right apex's drop-shadow.
            draw_aapolygon(self.screen, PASSED_COLOR, [(i - halo_offset, j) for (i, j) in points])
            draw_aapolygon(self.screen, PASSED_COLOR, [(i + halo_offset, j) for (i, j) in points])
            draw_aapolygon(self.screen, ptr_color, points)

            # Small light dot inside pentagon — drawn AFTER the pentagon
            # so it's visible on top of the red fill.
            cell_cx = int(cell_left + self.stops_w // 2)
            cell_cy = int(y + self.bar_height / 2)
            pygame.gfxdraw.filled_circle(self.screen, cell_cx, cell_cy, dot_radius, PASSED_COLOR)
            pygame.gfxdraw.aacircle(self.screen, cell_cx, cell_cy, dot_radius, PASSED_COLOR)

    def draw_times(
        self,
        window: List[Tuple[int, Dict]],
        dest_idx: int,
        cursor_pos: int,
        current_time: float,
        departure_time: float,
        is_last_pa: bool,
        at_station: bool = False,
        curr_stop: int = 0,
    ) -> None:
        """Cumulative travel times — same algorithm as full-route view.

        STOPPING behavior: skip rendering at gi=curr_stop (we're at the
        platform — incoming time is no longer meaningful), and shift the
        cumulative so the next cell shows time-from-platform-to-itself
        (= stops[curr_stop+1]["time"]) instead of carrying the now-stale
        leg into curr_stop.
        """
        if not window:
            return
        x = self.x
        y = self.bar_y
        window_start = window[0][0]
        cumulative_time = 0

        elapsed_minutes = 0
        if current_time > 0 and departure_time > 0:
            elapsed_seconds = current_time - departure_time
            elapsed_minutes = elapsed_seconds / TIME_SCALE

        is_first_station = True

        for gi, stop in window:
            if gi == 0 and cursor_pos == 0:
                continue
            if at_station and gi == curr_stop:
                continue
            # Hide the time on the leftmost cell when it IS cursor_pos —
            # the pointer occupies that space (reference convention). In the
            # locked-window case where cursor_pos has marched past the
            # leftmost, the cursor_pos cell still shows its countdown.
            if gi == window_start and gi == cursor_pos:
                continue

            local_i = gi - window_start
            ptr = local_i * self.stops_w

            if cursor_pos <= gi <= dest_idx and "time" in stop:
                t_w, t_h = self.font_time.size("0")

                if is_first_station:
                    if at_station:
                        # First rendered cell after STOPPING — static time.
                        cumulative_time = stop["time"]
                    elif is_last_pa:
                        cumulative_time = 1
                    else:
                        elapsed_full_minutes = int(elapsed_minutes)
                        remaining_time = max(1, stop["time"] - elapsed_full_minutes)
                        cumulative_time = remaining_time
                    is_first_station = False
                else:
                    cumulative_time += stop["time"]

                time_str = str(int(cumulative_time))
                time_x = int(x + ptr + (self.stops_w - t_w * len(time_str)) / 2)
                time_y = int(y + (self.bar_height - t_h) / 2)
                time_img = self.font_time.render(time_str, True, DARK_BG)
                self.screen.blit(time_img, (time_x, time_y))

                # 分-marker — line-end (rightmost cell) or mid-window dest
                if local_i == len(window) - 1 or gi == dest_idx:
                    marker_text = getattr(self, "minute_marker_text", "分")
                    minute_w = self._minute_w
                    _, text_h = self.font_minute.size(marker_text)
                    minute_y = int(y + (self.bar_height - text_h) / 2)

                    pygame.draw.rect(
                        self.screen,
                        self.color,
                        pygame.Rect(int(x + ptr + self.stops_w), int(y), minute_w, self.bar_height),
                    )
                    pygame.draw.rect(
                        self.screen,
                        WHITE_BG,
                        pygame.Rect(int(x + ptr + self.stops_w + minute_w - 3), int(y), 3, self.bar_height),
                    )

                    minute_img = self.font_minute.render(marker_text, True, WHITE_BG)
                    offset = getattr(self, "minute_marker_offset", self.stops_w * 0.85)
                    self.screen.blit(minute_img, (int(x + ptr + offset), minute_y))

    # ------------------------------------------------------------------
    # Continuation triangle (rightmost-cell-is-not-terminal indicator)
    # ------------------------------------------------------------------
    # NOTE: deliberately NOT called from `show_stops` yet. The user has an
    # existing continuity-arrow helper in their full-route renderer that's
    # known-buggy; this 8-station version is parked here as scaffolding
    # until that helper is reviewed and the two implementations can be
    # reconciled. Wire `self._draw_continuation_marker(window)` at the end
    # of `show_stops`'s Pass 2 (after `draw_times`) once the design is
    # finalised. Side margin (`self.side_margin = 44`) reserves the px the
    # triangle will need on the right-hand end of the bar.
    #
    # PRE_STOPS NOTE: when wiring this in, the early-return guard below
    # currently compares against `len(self.stops)` (sim space). With pre_stops,
    # `last_gi` comes from the window in DISPLAY space, so the comparison must
    # be against `len(self.display_stops) - 1` instead — otherwise the marker
    # silently never renders on pre_stops routes.

    def _draw_continuation_marker(self, window: List[Tuple[int, Dict]]) -> None:
        """Small right-pointing triangle past the 分 marker.

        Drawn when the rightmost visible station is not the route's terminal —
        signals "the route continues beyond this view." Colored in the route
        color so it reads as a natural extension of the bar.
        """
        if not window:
            return
        last_gi = window[-1][0]
        if last_gi >= len(self.stops) - 1:
            return

        # fmt: off
        # --- Continuation marker params (adjust freely) ---
        triangle_w = 8
        triangle_pad_x = 4  # gap after the 分 marker
        triangle_pad_y = 6  # vertical inset within bar height
        # ---------------------------------------------------
        # fmt: on

        bar_right = self.x + self.cells * self.stops_w
        minute_w = self._minute_w
        # marker extends `minute_w` past bar_right (see draw_times).
        tip_left_x = bar_right + minute_w + triangle_pad_x
        cy = self.bar_y + self.bar_height // 2
        points = [
            (tip_left_x, self.bar_y + triangle_pad_y),
            (tip_left_x + triangle_w, cy),
            (tip_left_x, self.bar_y + self.bar_height - triangle_pad_y),
        ]
        draw_aapolygon(self.screen, self.color, points)

    # ------------------------------------------------------------------
    # Per-cell station code badge
    # ------------------------------------------------------------------

    def _draw_badge(self, stop: Dict, cell_x: int) -> None:
        """Mini JO/JY framed square below the station's bar.

        Delegates to the shared `draw_station_code_badge` helper (also used
        by the upper LCD). Per-cell sizing here is smaller; no `code_3` band
        — 3-letter codes only ever surface in the upper LCD's prominent
        single-station badge, never in the route-map row.

        Past-station badges are NOT dimmed — IRL the badge keeps full route
        color regardless of whether the train has passed it.
        """
        sta_code = stop.get("sta_code")
        if not sta_code:
            return

        # fmt: off
        # --- Mini-badge params (adjust freely) ---
        badge_w = self.badge_w
        badge_h = self.badge_h
        # Reference shows NO black outer ring on the per-cell badges — the
        # route-color frame goes all the way to the badge edge. The shared
        # `draw_station_code_badge` helper still draws a black rect under the
        # color rect, but with `ring_black=0` the color rect covers it
        # entirely (same size and position).
        ring_black = 0
        ring_color = 2  # route-color frame width (slightly thicker now that there's no black layer)
        outer_radius = 2  # tighter corner rounding (was 3)
        color_radius = 2
        text_gap = 1  # gap between letters row and number row
        text_y_offset = 0  # vertically centered in the interior
        prefix_x_offset = 0  # center prefix (upper biases right by 1, not desirable here)
        # ------------------------------------------
        # fmt: on

        badge_x = cell_x + (self.stops_w - badge_w) // 2
        draw_station_code_badge(
            self.screen,
            badge_x,
            self.badge_y,
            badge_w,
            badge_h,
            sta_code,
            self.color,
            self.font_badge_prefix,
            self.font_badge_num,
            ring_black=ring_black,
            ring_color=ring_color,
            outer_radius=outer_radius,
            color_radius=color_radius,
            text_gap=text_gap,
            text_y_offset=text_y_offset,
            prefix_x_offset=prefix_x_offset,
        )

    # ------------------------------------------------------------------
    # Frame entry point
    # ------------------------------------------------------------------

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the full lower LCD frame for the 8-station view."""
        # Clear lower-LCD region
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(0, self.top_y, S_WIDTH, S_HEIGHT - self.top_y))

        if state.frame_mode == 0:
            return

        # Display indices = sim indices + display_offset (= len(pre_stops)).
        curr_stop = state.curr_stop + self.display_offset
        cursor_pos = state.cursor_pos + self.display_offset
        window = self._get_window(curr_stop, cursor_pos)
        self._last_window = window

        # Loader fills dest on every stop via sticky closure (route_loader);
        # direct read, no fallback. pre_stops can't override dest.
        sim_curr_stop = state.curr_stop
        if 0 <= sim_curr_stop < len(self.stops):
            effective_dest = self.stops[sim_curr_stop]["dest"]
        else:
            effective_dest = self.dest
        dest_idx = self._find_dest_index(window, effective_dest)
        window_start = window[0][0] if window else 0

        # Pass 1: bars + labels + badges (per-cell rendering)
        for gi, stop in window:
            local_i = gi - window_start
            cell_x = self.x + local_i * self.stops_w
            l_y = self.bar_y

            is_active = gi >= cursor_pos and gi <= dest_idx

            # Bar background
            if is_active:
                pygame.draw.rect(
                    self.screen,
                    self.color,
                    pygame.Rect(cell_x, l_y, self.stops_w, self.bar_height),
                )
            else:
                pygame.draw.rect(
                    self.screen,
                    INACTIVE_COLOR,
                    pygame.Rect(cell_x, l_y, self.stops_w, self.bar_height),
                )

            # Vertical kanji label — black on active range, dim grey otherwise
            label_color = (0, 0, 0) if is_active else INACTIVE_COLOR
            self._draw_label(self._label_text(stop), cell_x, label_color)

            # Per-cell station code badge
            self._draw_badge(stop, cell_x)

        # Pass 2: marks, pointer, times (overlays on top of bars)
        self.draw_marks(window, dest_idx, cursor_pos, curr_stop)
        self.draw_ptr(window, cursor_pos, curr_stop, state.at_station)
        self.draw_times(window, dest_idx, cursor_pos, current_time, state.departure_time, state.is_last_pa, state.at_station, curr_stop)

        draw_route_disclaimer(self.screen, self.font_disclaimer, S_WIDTH - 8, S_HEIGHT - 4, (0, 0, 0), self.disclaimer_text)

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Map LCD-local (mx, my) to a sim_index for click-to-jump.

        Hit area is the full vertical column (label + bar + badge). Returns
        None for clicks outside any cell or for pre_stops cells. Past-dest
        filtering lives in the caller.
        """
        window = self._last_window
        if not window or state is None:
            return None
        window_start = window[0][0]
        band_top = self.label_top_y
        band_bot = self.badge_y + self.badge_h + 5
        if not (band_top <= my < band_bot):
            return None
        for gi, _ in window:
            local_i = gi - window_start
            cell_x = self.x + local_i * self.stops_w
            if cell_x <= mx < cell_x + self.stops_w:
                sim_idx = gi - self.display_offset
                if sim_idx < 0:
                    return None
                return sim_idx
        return None


# =============================================================================
# English Display (ENGLISH mode — full-route Romaji)
# =============================================================================


class EnglishDisplay(JapaneseDisplay):
    """Lower LCD English rendering for E235-1000.

    Inherits from JapaneseDisplay and overrides fonts, station name drawing
    (with 45-degree counter-clockwise rotated Romaji names), and the travel time
    minute marker ("min").
    """

    def __init__(self, screen, route_data, stops):
        super().__init__(screen, route_data, stops)
        # CONTRACT: load fonts from file paths only — never `pygame.font.SysFont()`.
        # See conventions.md § "Never pygame.font.SysFont() in production code".
        self.font_stops = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), 17)
        # 4x supersampled font to eliminate pixelation and jaggedness on rotated text
        self.font_stops_supersampled = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), 17 * 4)
        self.font_minute = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), FONT_STOPS_MINUTE_SIZE)
        self.font_disclaimer = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Medium.otf"), 9)

    @property
    def minute_marker_text(self) -> str:
        return "min"

    @property
    def minute_marker_offset(self) -> float:
        return self.stops_w - 6

    @property
    def disclaimer_text(self) -> str:
        return EN_ROUTE_DISCLAIMER

    def draw_station_name(self, stop, text_color: Tuple[int, int, int], x: int, y: int) -> None:
        # Get English name, fallback to Japanese name if not translated
        english_name = stop.get("english", stop.get("name", ""))
        if not english_name:
            return

        # Normalize newlines (could be literal \n or escaped \\n)
        english_name = english_name.replace("\\n", "\n")
        lines = english_name.split("\n")

        # --- Tuneable layout params (adjust freely) ---
        angle = 45.0
        target_x_offset = self.stops_w // 2  # center on cell
        target_y_offset = 4  # 3px above bar top (closer to bar, lowered by 3px from y + 1)
        line_separation = 13.0  # perpendicular separation in px for 2-line stations
        scale_factor = 4.0  # 4x supersampling scale factor
        # -----------------------------------------------

        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        base_tx = x + target_x_offset
        base_ty = y + target_y_offset

        def draw_line(text: str, tx: float, ty: float):
            # Render using the 4x larger supersampled font for high-definition anti-aliasing
            text_surf = self.font_stops_supersampled.render(text, True, text_color)

            W, H = text_surf.get_size()
            max_w_super = 110.0 * scale_factor  # 110px threshold in 1x space to prevent neighbor overlapping
            if W > max_w_super:
                # Horizontally compress long station names to avoid overlapping with neighbors
                text_surf = pygame.transform.smoothscale(text_surf, (int(max_w_super), H))
                W, H = text_surf.get_size()

            # rotozoom does bilinear filtering when scaling down (scale = 1/4 = 0.25)
            rotated_surf = pygame.transform.rotozoom(text_surf, angle, 1.0 / scale_factor)
            W_rot, H_rot = rotated_surf.get_size()

            # Vector from center of the scaled-down original surface to its bottom-left corner
            dx, dy = -W / (2.0 * scale_factor), H / (2.0 * scale_factor)

            # Rotate vector (taking screen Y inversion into account)
            dx_rot = dx * cos_a + dy * sin_a
            dy_rot = -dx * sin_a + dy * cos_a

            # Locate top-left of rotated surface to blit
            blit_x = int(tx - (W_rot / 2.0 + dx_rot))
            blit_y = int(ty - (H_rot / 2.0 + dy_rot))
            self.screen.blit(rotated_surf, (blit_x, blit_y))

        if len(lines) == 1:
            draw_line(lines[0], base_tx, base_ty)
        else:
            # 2-line stacking: Line 1 shifted up-left (-perp), Line 2 shifted down-right (+perp)
            # Perpendicular vector pointing down-right is (sin_a, cos_a)
            half_sep = line_separation / 2.0

            tx1 = base_tx - half_sep * sin_a
            ty1 = base_ty - half_sep * cos_a

            tx2 = base_tx + half_sep * sin_a
            ty2 = base_ty + half_sep * cos_a

            draw_line(lines[0], tx1, ty1)
            draw_line(lines[1], tx2, ty2)


class EnglishEightStationDisplay(JapaneseEightStationDisplay):
    """Lower LCD English 8-station zoomed-in view for E235-1000.

    Inherits from JapaneseEightStationDisplay and overrides fonts, station
    label drawing (45° rotated Romaji), disclaimer, and minute marker.
    """

    def __init__(self, screen, route_data, stops):
        super().__init__(screen, route_data, stops)
        self.font_stops = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), 22)
        self.font_stops_supersampled = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), 22 * 4)
        self.font_minute = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Bold.otf"), FONT_STOPS_MINUTE_SIZE + 3)
        self.font_disclaimer = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Medium.otf"), 9)

    @property
    def minute_marker_text(self) -> str:
        return "min"

    @property
    def minute_marker_offset(self) -> float:
        return self.stops_w - 6

    @property
    def disclaimer_text(self) -> str:
        return EN_ROUTE_DISCLAIMER

    def _label_text(self, stop: Dict) -> str:
        return stop.get("english", stop.get("name", ""))

    def _draw_label(self, text: str, cell_x: int, color: Tuple[int, int, int]) -> None:
        """Render 45° counter-clockwise rotated Romaji in the label band."""
        if not text:
            return

        rad = math.radians(45.0)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        scale_factor = 4.0

        bottom_y = self.label_top_y + self.label_box_h
        base_tx = cell_x + self.stops_w // 2
        base_ty = self.bar_y - 5  # 5px above the colored bar

        def draw_line(st: str, tx: float, ty: float):
            text_surf = self.font_stops_supersampled.render(st, True, color)
            W, H = text_surf.get_size()
            max_w_super = 144.0 * scale_factor
            if W > max_w_super:
                text_surf = pygame.transform.smoothscale(text_surf, (int(max_w_super), H))
                W, H = text_surf.get_size()
            rotated_surf = pygame.transform.rotozoom(text_surf, 45.0, 1.0 / scale_factor)
            W_rot, H_rot = rotated_surf.get_size()
            dx, dy = -W / (2.0 * scale_factor), H / (2.0 * scale_factor)
            dx_rot = dx * cos_a + dy * sin_a
            dy_rot = -dx * sin_a + dy * cos_a
            blit_x = int(tx - (W_rot / 2.0 + dx_rot))
            blit_y = int(ty - (H_rot / 2.0 + dy_rot))
            self.screen.blit(rotated_surf, (blit_x, blit_y))

        # Normalize escaped newlines from JSON
        text = text.replace("\\n", "\n")
        lines = text.split("\n")

        if len(lines) == 1:
            draw_line(lines[0], base_tx, base_ty)
        else:
            half_sep = 13.0 / 2.0
            tx1 = base_tx - half_sep * sin_a
            ty1 = base_ty - half_sep * cos_a
            tx2 = base_tx + half_sep * sin_a
            ty2 = base_ty + half_sep * cos_a
            draw_line(lines[0], tx1, ty1)
            draw_line(lines[1], tx2, ty2)


# =============================================================================
# Lower Display Manager
# =============================================================================


class LowerDisplay:
    """E235-1000 Lower LCD manager.

    Mirrors the UpperDisplay manager pattern: holds the per-mode renderers,
    delegates drawing to whichever is active, and exposes
    set_state / update / draw to the application.

    The mode cycler is **shared** with the UpperDisplay — passed in from
    outside — so upper and lower stay in lockstep without a parallel timer.
    KANJI and FURIGANA both map to JapaneseDisplay (real PIDS doesn't
    furigana the route map).
    """

    # View-cycle slots (rotated in order, with per-slot durations).
    # Default 2-slot cycle is full-route 12s / 8-station 12s (24s total).
    # When the train is in the transfer-info window (see _in_transfer_window
    # — derived from cnt_pa rather than state.is_last_pa for single-PA-stop
    # correctness), TRANSFER joins as a 3rd slot at 6s. The 8-station lock
    # (remaining stops ≤ 7) drops FULL from rotation, leaving EIGHT alone
    # outside the window and EIGHT↔TRANSFER inside it. TRANSFER is also
    # dropped when the current station has no transfers to render.
    _SLOT_FULL = 0
    _SLOT_EIGHT = 1
    _SLOT_TRANSFER = 2
    _SLOT_DURATIONS = {
        _SLOT_FULL: 12.0,
        _SLOT_EIGHT: 12.0,
        _SLOT_TRANSFER: 6.0,
    }

    def __init__(self, screen, route_data, stops, mode_cycler):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.japanese_eight_display = JapaneseEightStationDisplay(screen, route_data, stops)
        self.english_display = EnglishDisplay(screen, route_data, stops)
        self.english_eight_display = EnglishEightStationDisplay(screen, route_data, stops)
        self.transfer_display = TransferInfoDisplay(screen, route_data, stops)

        self.mode_cycler = mode_cycler
        self._state = None

        # View-cycle state. _slot_start = wall-clock when current slot began;
        # _prev_at_station = last-frame at_station (None until first observed —
        # boot's at_station=True must NOT fire a rising-edge force-switch).
        self._current_slot: int = self._SLOT_FULL
        self._slot_start: float | None = None
        self._prev_at_station: bool | None = None

    def set_state(self, state) -> None:
        """Bind to an AppState instance. Subsequent draws read live state."""
        self._state = state
        # Forward to subordinate renderers that need state binding too.
        self.transfer_display.set_state(state)

    # NOTE: deliberately a no-op TODAY, but kept as scaffolding for a future
    # split where the lower LCD owns its own mode cycler (e.g. lower cycles on
    # a different cadence than upper, or freezes during certain states).
    #
    # Why no-op now: the cycler is SHARED with UpperDisplay (passed in via
    # __init__) and ticked there. Calling cycler.update() here too would
    # double-tick → KANJI→FURIGANA→ENGLISH cadence drops from 4 s to ~2 s.
    # The view cycle is ticked inside `draw()` instead — it depends on live
    # curr_stop (for the 8-station lock condition) and is cheaper to fold in.
    #
    # When to wire it in: if/when lower stops sharing upper.mode_cycler,
    # construct an own ModeCycler in __init__ and tick it here.
    def update(self, current_time: float = None) -> None:
        pass

    def _should_lock_to_eight(self, curr_stop: int) -> bool:
        """When remaining stops ≤ LOCK_THRESHOLD (=7), drop the full-route view permanently."""
        return (len(self.stops) - curr_stop) <= JapaneseEightStationDisplay.LOCK_THRESHOLD

    def _in_transfer_window(self, state) -> bool:
        """True when transfer-info should be in the cycle rotation.

        Window = APPROACHING_FINAL (cnt_pa is at the last index of pa[])
        through STOPPING. Derived directly from cnt_pa rather than reading
        ``state.is_last_pa`` because the flag is only set inside
        ``_next_in_approaching`` (multi-PA path) — single-PA stations
        auto-fire pa[0] via ``_advance_to_next_stop`` which hardcodes
        is_last_pa = False even though pa[0] is already the last (and only)
        PA. The derived check correctly fires for both cases.
        """
        if state.at_station:
            return True
        pa_tracks = self.stops[state.curr_stop].get("pa", [])
        if not pa_tracks:
            return False
        return state.cnt_pa >= len(pa_tracks) - 1

    def _station_has_transfers(self, state) -> bool:
        """True when the current station has at least one transfer to render
        after active-line filter + view-drop are applied.

        Cheap enough to call per-frame: dict lookup + two list comps inside
        TransferInfoDisplay._resolve_transfers. If this becomes a hot spot,
        cache against (curr_stop, transfer_view) — but don't pre-optimize.
        """
        if not (0 <= state.curr_stop < len(self.stops)):
            return False
        name = self.stops[state.curr_stop].get("name", "")
        return bool(self.transfer_display._resolve_transfers(name))

    def _available_slots(self, state) -> list:
        """Slots in rotation order for the current state.

        Combinations (× transfer-available toggle):
          - not in window, not locked  → [FULL, EIGHT]
          - not in window, locked      → [EIGHT]
          - in window,    not locked   → [FULL, EIGHT, TRANSFER]
          - in window,    locked       → [EIGHT, TRANSFER]

        TRANSFER is dropped from the list when the current station has no
        transfers (or filtering wipes them out) — the cycle simply rotates
        without a blank slot.
        """
        locked = self._should_lock_to_eight(state.curr_stop)
        in_window = self._in_transfer_window(state) and self._station_has_transfers(state)
        if locked and in_window:
            return [self._SLOT_EIGHT, self._SLOT_TRANSFER]
        if locked:
            return [self._SLOT_EIGHT]
        if in_window:
            return [self._SLOT_FULL, self._SLOT_EIGHT, self._SLOT_TRANSFER]
        return [self._SLOT_FULL, self._SLOT_EIGHT]

    # CONTRACT: must be called BEFORE language-mode dispatch (not inside the
    # KANJI/FURIGANA branch). Nesting in the language branch pauses the timer
    # during ENGLISH; cycle cadence drifts long. See DISPLAY_E235.md § "View cycler".
    def _tick_cycle(self, current_time: float) -> None:
        """Advance the slot cycle. Reconciles slot membership and per-slot durations."""
        slots = self._available_slots(self._state)
        # Reconcile: if current slot dropped out (lock kicked in, or window
        # closed mid-TRANSFER), snap to the first available slot and reset timer.
        if self._current_slot not in slots:
            self._current_slot = slots[0]
            self._slot_start = current_time
            return
        # Single-slot cycle (locked, no window): nothing to advance.
        if len(slots) == 1:
            return
        # Initialize timer on first observation.
        if self._slot_start is None:
            self._slot_start = current_time
            return
        if current_time - self._slot_start >= self._SLOT_DURATIONS[self._current_slot]:
            idx = slots.index(self._current_slot)
            self._current_slot = slots[(idx + 1) % len(slots)]
            self._slot_start = current_time

    def _handle_at_station_edge(self, state, current_time: float) -> None:
        """STOPPING entry: force-switch to TRANSFER (if available), reset timer.

        Only fires on the at_station False→True transition. Boot's initial
        at_station=True is captured as the first observation without firing
        the edge, so the cycle starts on its default slot rather than
        force-jumping to transfer.
        """
        if self._prev_at_station is None:
            self._prev_at_station = state.at_station
            return
        if state.at_station and not self._prev_at_station:
            slots = self._available_slots(state)
            if self._SLOT_TRANSFER in slots:
                self._current_slot = self._SLOT_TRANSFER
                self._slot_start = current_time
        self._prev_at_station = state.at_station

    def _pick_renderer(self, mode):
        """Pick the renderer for the current slot + language mode.

        TRANSFER slot wins over language (transfer-info is dual-language —
        renders identically regardless of upper's KANJI/FURIGANA/ENGLISH).
        Other slots fall through to the existing language dispatch:
        Japanese → full-route or 8-station per slot; ENGLISH → dispatches
        to english_display for full-route, english_eight_display for 8-station.
        """
        # CONTRACT: _pick_renderer is a pure function of _current_slot + mode.
        # See DISPLAY_E235.md § "View cycler (LowerDisplay)".
        if self._current_slot == self._SLOT_TRANSFER:
            return self.transfer_display
        if mode in (DisplayMode.KANJI, DisplayMode.FURIGANA):
            return self.japanese_eight_display if self._current_slot == self._SLOT_EIGHT else self.japanese_display
        # ENGLISH mode
        if self._current_slot == self._SLOT_FULL:
            return self.english_display
        return self.english_eight_display

    def draw(self, current_time: float = 0.0) -> None:
        """Dispatch to the active slot's renderer.

        Per-frame: detect at_station rising edge → maybe force-switch to
        TRANSFER. Tick cycle. Pick renderer for (slot, language). Draw.

        Cycle ticks regardless of language mode so cadence doesn't drift
        while the upper is in ENGLISH (which would otherwise pause the
        timer for ~1/3 of every upper-mode cycle).
        """
        if self._state is None:
            return

        self._handle_at_station_edge(self._state, current_time)
        self._tick_cycle(current_time)

        mode = self.mode_cycler.get_current_mode()
        renderer = self._pick_renderer(mode)
        renderer.show_stops(self._state, current_time)

    def hit_test(self, mx: int, my: int) -> Optional[int]:
        """Dispatch a click in LCD-local coords to the active renderer's hit_test.

        Returns sim_index for clickable cells, None for non-clickable
        (pre_stops, padding, transfer-info — no clickable elements there).
        ENGLISH mode falls back to the Japanese full-route renderer's
        hit_test — clicks DO work in ENGLISH. Past-dest filter lives in
        the caller (`PASimulator._click_target`) since `dest_stop_idx` is
        on the simulator, not the renderer.
        """
        if self._state is None:
            return None
        mode = self.mode_cycler.get_current_mode()
        renderer = self._pick_renderer(mode)
        if hasattr(renderer, "hit_test"):
            return renderer.hit_test(self._state, mx, my)
        return None

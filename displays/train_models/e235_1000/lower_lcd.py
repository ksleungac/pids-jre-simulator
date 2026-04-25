"""E235-1000 series Lower LCD display implementation.

Contains all display modes (Japanese, English) for the E235-1000 series
Lower LCD (route map, station markers, travel times, skip animation).

Modes share `ModeCycler` with the Upper LCD — when both modes are
implemented for the lower, switching the upper into ENGLISH will pull the
lower along in lockstep.

**English mode is currently disabled** in the lower's mode_displays dict
(EnglishDisplay is unimplemented — only a placeholder class exists). Until
it's filled in, the lower stays in JapaneseDisplay regardless of the
shared cycler's state — the upper still cycles freely through all three
upper-display modes. To re-enable: uncomment the ENGLISH entry in
`LowerDisplay.__init__` once `EnglishDisplay.show_stops` is implemented.
"""

import math
from typing import Dict, List, Tuple
import pygame
import pygame.gfxdraw

from constants import (
    S_WIDTH,
    S_HEIGHT,
    WHITE_BG,
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
    DARK_BG,
)
from utils import (
    draw_aapolygon,
    arrow_points,
    draw_stops_text,
)
from displays.base import DisplayMode


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
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.contrast_color = route_data.get("contrast_color", [224, 54, 37])

        self._calculate_layout()

        self.font_stops = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_SIZE)
        self.font_time = pygame.font.Font("fonts/HelveticaNeue-Bold.otf", FONT_TIME_SIZE)
        self.font_minute = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_MINUTE_SIZE)

    def _calculate_layout(self) -> None:
        """Calculate station display layout based on route length."""
        num_stops = len(self.stops)

        if num_stops > 17 or num_stops % 2 == 0:
            self.per_line = min(STOPS_PER_LINE, math.ceil(num_stops / 2))
        else:
            self.per_line = 17

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

    def _get_stops_list_disp(self, curr_stop: int) -> List[Tuple[int, Dict]]:
        """Get the list of (global_index, stop) pairs currently visible.

        Every rendered cell carries its global index into ``self.stops`` so
        drawing code can compare directly against ``curr_stop`` / ``cursor_pos``
        without juggling a second "local" index space.
        """
        if len(self.stops) <= self.STOPS_QUANTITY:
            return list(enumerate(self.stops))

        window_start = 0
        f_stops = self.stops[: self.STOPS_QUANTITY]

        remaining = len(self.stops) - curr_stop
        if 0 < remaining < self.STOPS_QUANTITY:
            window_start = len(self.stops) - self.STOPS_QUANTITY
            f_stops = self.stops[window_start:]
            if remaining == self.STOPS_QUANTITY - 1 and self.circular != 1:
                self.continuity = [1, 1, 0]

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

    def draw_ptr(self, f_stops: List[Tuple[int, Dict]], dest_idx: int, cursor_pos: int, curr_stop: int) -> None:
        """Draw the pointer/triangle indicating current position."""
        x = self.x
        y = self.y
        if not f_stops:
            return
        window_start = f_stops[0][0]
        ptr_color = self.contrast_color
        local_disp = cursor_pos - window_start
        # During a long-route window flip, a multi-station skip animation
        # can leave cursor_pos behind in the cut-off zone. Suppress the
        # pointer rather than rendering it at a wrong column — the inner
        # red dot at curr_stop still shows the actual train position.
        if local_disp < 0 or local_disp >= len(f_stops):
            return
        ptr = (local_disp % self.per_line) * self.stops_w
        line_num = self._get_line(local_disp)
        l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)

        if curr_stop != 0:
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
        else:
            overhang = 2
            points = [
                (x, l_y - overhang),
                (x, l_y + self.bar_height + overhang),
                (x + self.stops_w - 10, l_y + self.bar_height + overhang),
                (x + self.stops_w - 2, l_y + self.bar_height / 2),
                (x + self.stops_w - 10, l_y - overhang),
            ]
            draw_aapolygon(self.screen, PASSED_COLOR, [(i + 3, j) for (i, j) in points])
            draw_aapolygon(self.screen, ptr_color, points)

    def draw_marks(self, f_stops: List[Tuple[int, Dict]], dest_idx: int, cursor_pos: int, curr_stop: int) -> None:
        """Draw station markers (circles and arrows)."""
        if not f_stops:
            return
        x = self.x
        y = self.y
        window_start = f_stops[0][0]

        for gi, stop in f_stops:
            local_i = gi - window_start
            ptr = (local_i % self.per_line) * self.stops_w
            line_num = self._get_line(local_i)
            l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)
            offset = self.stops_w // 2
            center_x = int(x + ptr + offset)
            center_y = int(l_y + self.bar_height / 2)

            if gi >= cursor_pos and gi <= dest_idx:
                if gi == 0 and cursor_pos == 0:
                    radius = 5
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                elif not stop.get("pa", []):
                    arrow_offset = int(self.stops_w * 0.3)
                    draw_aapolygon(
                        self.screen,
                        PASSED_COLOR,
                        arrow_points(
                            int(x + ptr + arrow_offset),
                            int(l_y + 4),
                            14,
                            self.bar_height - 8,
                            6,
                        ),
                    )
                else:
                    radius = 11
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)

                    # Inner red dot marks the actual PA target — stays at
                    # curr_stop even while the cursor lags during a skip.
                    if gi == curr_stop:
                        pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius - 2, CURRENT_COLOR)
                        pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius - 2, CURRENT_COLOR)
            else:
                radius = 5
                pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)

    def draw_times(
        self,
        f_stops: List[Tuple[int, Dict]],
        dest_idx: int,
        cursor_pos: int,
        current_time: float,
        departure_time: float,
        is_last_pa: bool,
    ) -> None:
        """Draw travel times between stations."""
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
                    if is_last_pa:
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
                    minute_w, minute_h = self.font_minute.size("分")
                    minute_y = int(l_y + (self.bar_height - minute_h) / 2)

                    pygame.draw.rect(
                        self.screen,
                        self.color,
                        pygame.Rect(
                            int(x + ptr + self.stops_w),
                            int(l_y),
                            minute_w,
                            self.bar_height,
                        ),
                    )
                    pygame.draw.rect(
                        self.screen,
                        WHITE_BG,
                        pygame.Rect(
                            int(x + ptr + self.stops_w + minute_w - 3),
                            int(l_y),
                            3,
                            self.bar_height,
                        ),
                    )

                    minute_img = self.font_minute.render("分", True, WHITE_BG)
                    self.screen.blit(minute_img, (int(x + ptr + self.stops_w * 0.85), minute_y))

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the full lower LCD frame for this mode.

        Args:
            state: AppState instance — read-only here. Skip-progress mutation
                lives on AppState itself (see ``AppState.update_skip_progress``)
                and runs in the app loop before this method is called.
            current_time: Wall-clock timestamp for countdown calculation.
        """
        f_stops = self._get_stops_list_disp(state.curr_stop)
        x = self.x
        y = self.y
        window_start = f_stops[0][0] if f_stops else 0

        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(0, int(y), S_WIDTH, S_HEIGHT - int(y)))

        if state.frame_mode == 0:
            return

        # Resolve effective destination — stop-level override beats route-level
        # (matches UpperDisplay._get_current_dest). Yamanote's mid-loop dest
        # cycling depends on this to keep the active bar range correct.
        curr_stop = state.curr_stop
        stop_dest = self.stops[curr_stop].get("dest") if 0 <= curr_stop < len(self.stops) else None
        effective_dest = stop_dest or self.dest

        dest_idx = self._find_dest_index(f_stops, effective_dest)
        cursor_pos = state.cursor_pos

        for gi, stop in f_stops:
            local_i = gi - window_start
            ptr = (local_i % self.per_line) * self.stops_w
            line_num = self._get_line(local_i)
            l_y = int(y + self.h_line * line_num + self.top_pad * (line_num - 1))

            is_passed = gi >= cursor_pos and gi <= dest_idx

            if is_passed:
                pygame.draw.rect(
                    self.screen,
                    self.color,
                    pygame.Rect(int(x + ptr), l_y, self.stops_w, self.bar_height),
                )
                text_color = INACTIVE_COLOR if (not stop.get("pa", []) and gi != 0) else (0, 0, 0)
            else:
                pygame.draw.rect(
                    self.screen,
                    INACTIVE_COLOR,
                    pygame.Rect(int(x + ptr), l_y, self.stops_w, self.bar_height),
                )
                text_color = INACTIVE_COLOR

            draw_stops_text(
                self.font_stops,
                stop.get("name", ""),
                text_color,
                int(x + ptr),
                int(l_y - 7),
                self.stops_w,
                self.screen,
            )

        self.draw_marks(f_stops, dest_idx, cursor_pos, curr_stop)
        self.draw_ptr(f_stops, dest_idx, cursor_pos, curr_stop)
        self.draw_times(f_stops, dest_idx, cursor_pos, current_time, state.departure_time, state.is_last_pa)


# =============================================================================
# English Display (ENGLISH mode — placeholder)
# =============================================================================


class EnglishDisplay:
    """Lower LCD English rendering for E235-1000 (placeholder).

    Not yet implemented. Clears the lower-region background so cycling into
    ENGLISH mode shows a clean blank frame instead of stale Japanese
    rendering. Real implementation will mirror JapaneseDisplay's structure
    with romaji station labels and Latin-script fonts.
    """

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.y = int(S_HEIGHT * 0.28)

    def show_stops(self, state, current_time: float = 0.0) -> None:
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(0, self.y, S_WIDTH, S_HEIGHT - self.y))


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

    def __init__(self, screen, route_data, stops, mode_cycler):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.english_display = EnglishDisplay(screen, route_data, stops)

        # ENGLISH intentionally not mapped while EnglishDisplay is a stub —
        # `draw()`'s `.get(mode, self.japanese_display)` falls back so the
        # lower stays Japanese even when the shared cycler is in ENGLISH.
        # Re-enable by uncommenting the ENGLISH entry once implemented.
        self.mode_displays = {
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.japanese_display,
            # DisplayMode.ENGLISH: self.english_display,
        }
        self.mode_cycler = mode_cycler

        self._state = None

    def set_state(self, state) -> None:
        """Bind to an AppState instance. Subsequent draws read live state."""
        self._state = state

    def update(self, current_time: float = None) -> None:
        """Mode cycling is driven by the upper (shared cycler), so no-op here."""
        pass

    def draw(self, current_time: float = 0.0) -> None:
        """Dispatch to the active mode's renderer."""
        if self._state is None:
            return
        mode = self.mode_cycler.get_current_mode()
        display = self.mode_displays.get(mode, self.japanese_display)
        display.show_stops(self._state, current_time)

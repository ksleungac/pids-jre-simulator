"""Display handling for PA Simulator - Lower LCD section."""

import math
from typing import Dict, List, Any
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


class LowerDisplay:
    """Handles the lower portion of the LCD (route map, station markers)."""

    def __init__(
        self,
        screen: pygame.Surface,
        route_data: Dict,
        app_state: Any,
        stops: List[Dict],
    ):
        """Initialize the lower display.

        Args:
            screen: Pygame surface to draw on
            route_data: Route configuration dictionary
            app_state: Application state object
            stops: List of stop dictionaries (with merged station data)
        """
        self.screen = screen
        self.route_data = route_data
        self.state = app_state
        self.stops = stops
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.contrast_color = route_data.get("contrast_color", [224, 54, 37])

        # Calculate layout
        self._calculate_layout()

        # Fonts - load from fonts/ folder
        self.font_stops = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_SIZE)
        self.font_time = pygame.font.Font("fonts/HelveticaNeueBold.ttf", FONT_TIME_SIZE)
        self.font_minute = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", FONT_STOPS_MINUTE_SIZE)

    def _calculate_layout(self) -> None:
        """Calculate station display layout based on route length."""
        num_stops = len(self.stops)

        # Determine stations per line
        if num_stops > 17 or num_stops % 2 == 0:
            self.per_line = min(STOPS_PER_LINE, math.ceil(num_stops / 2))
        else:
            self.per_line = 17

        self.stops_w = STOPS_WIDTH
        self.x = (S_WIDTH - self.stops_w * self.per_line) // 2
        self.y = int(S_HEIGHT * 0.28)
        self.bar_height = STOPS_BAR_HEIGHT
        self.STOPS_QUANTITY = self.per_line * 2

        # Calculate line height based on number of stations
        self.h_line = 105 if num_stops > self.per_line else 150
        self.top_pad = 40

        # Determine continuity (for circular routes or long routes)
        self.circular = 1 if self.stops and self.stops[0].get("name") == self.stops[-1].get("name") else 0
        self.continuity = [0, 0, 0]

        if self.circular == 1 or num_stops > 28:
            self.continuity = [1, 1, 1]
        elif num_stops > self.per_line:
            self.continuity = [1, 1, 0]

        self.timer = 0
        # Note: skip is tracked in self.state.skip for consistency

    def _get_line(self, i: int) -> int:
        """Get which line (1 or 2) a station index belongs to.

        Args:
            i: Station index

        Returns:
            1 for first line, 2 for second line
        """
        return 1 if i < self.per_line else 2

    def _get_stops_list_disp(self) -> List[Dict]:
        """Get the list of stops to display based on current position.

        Returns:
            List of stop dictionaries to display
        """
        if len(self.stops) <= self.STOPS_QUANTITY:
            return self.stops

        f_stops = self.stops[: self.STOPS_QUANTITY]

        # If approaching end of route, show last STOPS_QUANTITY stations
        # Guard against negative indexing edge case
        remaining = len(self.stops) - self.state.curr_stop
        if 0 < remaining < self.STOPS_QUANTITY:
            f_stops = self.stops[len(self.stops) - self.STOPS_QUANTITY :]
            self._refresh_curr_stop_disp()

        return f_stops

    def _refresh_curr_stop_disp(self) -> None:
        """Refresh current stop display position when scrolling."""
        if len(self.stops) - self.state.curr_stop == self.STOPS_QUANTITY - 1:
            if self.circular != 1:
                self.continuity = [1, 1, 0]
            self.state.curr_stop_disp = 1

    def _find_dest_index(self, f_stops: List[Dict]) -> int:
        """Find the index of the destination station.

        Args:
            f_stops: List of displayed stops

        Returns:
            Index of destination station, or last index if not found
        """
        try:
            return [s.get("name", "") for s in f_stops].index(self.dest)
        except ValueError:
            return len(f_stops) - 1

    def _update_skip_progress(self, current_time: float, f_stops: List[Dict]) -> None:
        """Update curr_stop_disp through passing stations based on elapsed time.

        Args:
            current_time: Current timestamp
            f_stops: List of displayed stops
        """
        skip = self.state.skip
        if skip == 0:
            return

        # Calculate elapsed time since departure
        if current_time > 0 and self.state.departure_time > 0:
            elapsed_seconds = current_time - self.state.departure_time
            elapsed_minutes = elapsed_seconds / TIME_SCALE
        else:
            return

        time_to_next = self.state.time_to_next
        if time_to_next <= 0:
            return

        # Progress through passing stations based on time
        # Skip stations divide the time into (skip + 1) segments
        # At skip=1: 50% time -> progress to first passing
        # At skip=2: 33% time -> first passing, 67% time -> second passing
        for i in range(1, skip + 1):
            # Threshold: time_to_next * i / (skip + 1)
            threshold = time_to_next * i / (skip + 1)
            if elapsed_minutes >= threshold and self.state.skip_progress < i:
                self.state.curr_stop_disp += 1
                self.state.skip_progress = i

    def draw_ptr(self, f_stops: List[Dict], dest_idx: int) -> None:
        """Draw the pointer/triangle indicating current position.

        Args:
            f_stops: List of displayed stops
            dest_idx: Index of destination station
        """
        x = self.x
        y = self.y
        ptr_color = self.contrast_color
        ptr = (self.state.curr_stop_disp % self.per_line) * self.stops_w
        line_num = self._get_line(self.state.curr_stop_disp)
        l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)

        if self.state.curr_stop != 0:
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

    def draw_marks(self, f_stops: List[Dict], dest_idx: int) -> None:
        """Draw station markers (circles and arrows).

        Args:
            f_stops: List of displayed stops
            dest_idx: Index of destination station
        """
        x = self.x
        y = self.y

        for i, stop in enumerate(f_stops):
            ptr = (i % self.per_line) * self.stops_w
            line_num = self._get_line(i)
            l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)
            offset = self.stops_w // 2
            center_x = int(x + ptr + offset)
            center_y = int(l_y + self.bar_height / 2)

            if i >= self.state.curr_stop_disp and i <= dest_idx:
                if i == 0 and self.state.curr_stop_disp == 0:
                    # Starting station - small circle
                    radius = 5
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                elif not stop.get("pa", []):
                    # Station with no PA - arrow
                    w = 20
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
                    # Regular station - large circle
                    radius = 11
                    pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                    pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)

                    # Current station - inner circle
                    if i == self.state.curr_stop:
                        pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius - 2, CURRENT_COLOR)
                        pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius - 2, CURRENT_COLOR)
            else:
                # Passed or future station - small circle
                radius = 5
                pygame.gfxdraw.filled_circle(self.screen, center_x, center_y, radius, PASSED_COLOR)
                pygame.gfxdraw.aacircle(self.screen, center_x, center_y, radius, PASSED_COLOR)

    def draw_times(self, f_stops: List[Dict], dest_idx: int, current_time: float = 0.0) -> None:
        """Draw travel times between stations.

        Args:
            f_stops: List of displayed stops
            dest_idx: Index of destination station
            current_time: Current timestamp for real-time countdown calculation
        """
        x = self.x
        y = self.y
        cumulative_time = 0

        # Calculate elapsed time since departure (in minutes based on TIME_SCALE)
        elapsed_minutes = 0
        if current_time > 0 and self.state.departure_time > 0:
            elapsed_seconds = current_time - self.state.departure_time
            elapsed_minutes = elapsed_seconds / TIME_SCALE

        # Get is_last_pa from state
        is_last_pa = self.state.is_last_pa

        # Track if we've processed the first station ahead
        is_first_station = True

        for i, stop in enumerate(f_stops):
            if i == 0 and self.state.curr_stop_disp == 0:
                continue

            ptr = (i % self.per_line) * self.stops_w
            line_num = self._get_line(i)
            l_y = y + self.h_line * line_num + self.top_pad * (line_num - 1)

            if i >= self.state.curr_stop_disp:
                t_w, t_h = self.font_time.size("0")

                # Add travel time
                if "time" in stop:
                    if is_first_station:
                        # First station ahead - apply countdown or last PA logic
                        if is_last_pa:
                            # On last PA ("arriving now"), show 1 minute
                            cumulative_time = 1
                        else:
                            # Countdown based on elapsed time, but only decrement when full minute passes
                            # Use floor to ensure we show full time until that minute elapsed
                            elapsed_full_minutes = int(elapsed_minutes)
                            remaining_time = max(1, stop["time"] - elapsed_full_minutes)
                            cumulative_time = remaining_time
                        is_first_station = False
                    else:
                        # Subsequent stations - add full time to cumulative
                        cumulative_time += stop["time"]

                    time_str = str(int(cumulative_time))
                    time_x = int(x + ptr + (self.stops_w - t_w * len(time_str)) / 2)
                    time_y = int(l_y + (self.bar_height - t_h) / 2)
                    time_img = self.font_time.render(time_str, True, DARK_BG)
                    self.screen.blit(time_img, (time_x, time_y))

                # Draw "分" marker at line breaks and destination
                if i == self.per_line - 1 or i == dest_idx:
                    minute_w, minute_h = self.font_minute.size("分")
                    minute_y = int(l_y + (self.bar_height - minute_h) / 2)

                    # Background rectangle
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

    def show_stops(self, current_time: float = 0.0) -> None:
        """Draw station list, markers, pointer, and travel times.

        Args:
            current_time: Current timestamp for real-time countdown calculation
        """
        f_stops = self._get_stops_list_disp()
        x = self.x
        y = self.y

        # Clear background
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(0, int(y), S_WIDTH, S_HEIGHT - int(y)))

        if self.state.frame_mode == 0:
            return

        dest_idx = self._find_dest_index(f_stops)

        # Time-based skip progression: move through passing stations based on elapsed time
        self._update_skip_progress(current_time, f_stops)

        # Draw station bars
        for i, stop in enumerate(f_stops):
            ptr = (i % self.per_line) * self.stops_w
            line_num = self._get_line(i)
            l_y = int(y + self.h_line * line_num + self.top_pad * (line_num - 1))

            is_passed = i >= self.state.curr_stop_disp and i <= dest_idx

            if is_passed:
                pygame.draw.rect(
                    self.screen,
                    self.color,
                    pygame.Rect(int(x + ptr), l_y, self.stops_w, self.bar_height),
                )
                text_color = INACTIVE_COLOR if (not stop.get("pa", []) and i != 0) else (0, 0, 0)
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

        # Draw markers, pointer, and times
        self.draw_marks(f_stops, dest_idx)
        self.draw_ptr(f_stops, dest_idx)
        self.draw_times(f_stops, dest_idx, current_time)

        pygame.display.flip()

    def increment_current_stop_display(self) -> None:
        """Update which stop is highlighted."""
        f_stops = self._get_stops_list_disp()

        if not f_stops:
            return

        dest_idx = self._find_dest_index(f_stops)

        if self.state.curr_stop_disp >= dest_idx or self.state.curr_stop_disp + 1 >= len(f_stops):
            return

        # If we're in the middle of a skip, complete it on 2nd PA
        if self.state.skip > 0 and self.state.cnt_pa >= 1:
            # Deduct time-based advancement from skip (may have already progressed)
            remaining = self.state.skip - self.state.skip_progress
            self.state.curr_stop_disp += remaining
            self.state.skip = 0
            self.state.time_to_next = 0
            self.state.skip_progress = 0
            return

        # First PA at a new station (cnt_pa == 0): advance to next station
        if self.state.cnt_pa == 0:
            self.state.curr_stop_disp += 1

            # Check if we landed on a passing station (no PA)
            current = f_stops[self.state.curr_stop_disp]
            if not current.get("pa", []):
                # Count how many stations to skip
                i = self.state.curr_stop_disp
                while i < len(f_stops) and not f_stops[i].get("pa", []):
                    i += 1
                self.state.skip = i - self.state.curr_stop_disp
                # Get time to next stopping station (from target station with PA)
                target_stop = f_stops[i]
                self.state.time_to_next = target_stop.get("time", 0)
                # Reset skip progress for time-based animation
                self.state.skip_progress = 0
                # Keep curr_stop_disp at first passing station, complete on 2nd PA

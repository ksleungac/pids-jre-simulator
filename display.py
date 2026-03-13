"""Display handling for PA Simulator - Upper and Lower LCD sections."""

import pygame
import pygame.gfxdraw
import math
import time
from typing import Dict, List, Any, Tuple, Optional

from constants import (
    S_WIDTH,
    S_HEIGHT,
    UPPER_HEIGHT,
    DARK_BG,
    WHITE_BG,
    PASSED_COLOR,
    CURRENT_COLOR,
    INACTIVE_COLOR,
    FONT_STOPS_NAME,
    FONT_STOPS_SIZE,
    FONT_STOPS_BOLD_NAME,
    FONT_CLOCK_NAME,
    FONT_CLOCK_SIZE,
    FONT_TIME_NAME,
    FONT_TIME_SIZE,
    FONT_STOPS_SMALL_SIZE,
    FONT_STOPS_MINUTE_SIZE,
    FONT_TYPE_SIZE,
    FONT_TYPE_BOLD_SIZE,
    FONT_DEST_SIZE,
    FONT_PREFIX_SIZE,
    FONT_STATION_SIZE,
    STOPS_BAR_HEIGHT,
    STOPS_WIDTH,
    STOPS_PER_LINE,
    STATION_DISPLAY_INTERVAL,
    TIME_SCALE,
)
from utils import (
    draw_text,
    draw_text_given_width,
    draw_aapolygon,
    arrow_points,
    draw_stops_text,
)


class UpperDisplay:
    """Handles the upper portion of the LCD (train info, current station)."""

    def __init__(
        self,
        screen: pygame.Surface,
        route_data: Dict,
        app_state: Any,
        stops: List[Dict],
    ):
        """Initialize the upper display.

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

        # Extract route data with defaults
        self.route_name = route_data.get("route", "Unknown")
        self.train_type = route_data.get("type", "")
        self.dest = route_data.get("dest", "")
        self.dest_furigana = route_data.get("dest_furigana", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.type_color = route_data.get("type_color", [0, 0, 0])

        # Layout
        self.x = 0
        self.y = 0
        self.h = UPPER_HEIGHT

        # Colors
        self.dark_bg = DARK_BG
        self.white_bg = WHITE_BG

        # Fonts
        self.font_type_bold = pygame.font.SysFont(FONT_STOPS_BOLD_NAME, FONT_TYPE_BOLD_SIZE, bold=True, italic=True)
        self.font_dest = pygame.font.SysFont(FONT_STOPS_NAME, FONT_DEST_SIZE)
        self.font_prefix = pygame.font.SysFont(FONT_STOPS_NAME, FONT_PREFIX_SIZE)
        self.font_station = pygame.font.SysFont(FONT_STOPS_NAME, FONT_STATION_SIZE)
        self.font_clock = pygame.font.SysFont(FONT_CLOCK_NAME, FONT_CLOCK_SIZE)
        self.font_suffix = pygame.font.SysFont(FONT_STOPS_NAME, 18)

        # Unified display cycling (kanji <-> furigana for all elements together)
        self.display_mode = 0  # 0 = kanji, 1 = furigana
        self.last_switch_time = time.time()
        self.prefix_text = "ただいま"  # Default, updated in draw_current_station

    def draw_init(self) -> None:
        """Draw initial state (train type, destination banner)."""
        # Draw dark background
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(0, 0, S_WIDTH, self.h))

        # Train type box
        box_w = 150
        pygame.draw.rect(self.screen, self.white_bg, pygame.Rect(15, 5, box_w, 31), 0, 2)
        if len(self.train_type) > 2:
            draw_text_given_width(
                15,
                7,
                box_w,
                self.font_type_bold,
                self.train_type,
                self.type_color,
                self.screen,
                collapse=True,
            )
        else:
            draw_text_given_width(
                15,
                7,
                box_w,
                self.font_type_bold,
                self.train_type,
                self.type_color,
                self.screen,
            )

        # Color band
        pygame.draw.rect(self.screen, self.color, pygame.Rect(int(S_WIDTH * 0.25), 0, 30, self.h - 7))

        # Destination with cycling (draw AFTER color band so suffix isn't covered)
        self._draw_destination()

        # Prefix ("ただいま") - set initial state
        self.prefix_text = "ただいま"
        self._draw_prefix()

        # Station name
        self._draw_station_name()

        # Hint square (indicates multiple PA announcements)
        # Positioned at bottom right of upper section, aligned with bottom edge
        if self.stops and len(self.stops[self.state.curr_stop].get("pa", [])) > 1:
            pygame.draw.rect(
                self.screen,
                (247, 225, 158),
                pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20),
            )
        else:
            pygame.draw.rect(
                self.screen,
                self.dark_bg,
                pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20),
            )

        pygame.display.flip()

    def _update_display_mode(self) -> None:
        """Update display mode (kanji/furigana) based on timer.

        Switches all elements between kanji and furigana every STATION_DISPLAY_INTERVAL seconds.
        Only cycles if furigana data is available for current station.
        """
        current_time = time.time()

        # Check if furigana is available for current station
        if self.state.curr_stop < len(self.stops):
            has_furigana = "furigana" in self.stops[self.state.curr_stop]
        else:
            has_furigana = False

        # Only cycle if furigana data exists
        if has_furigana:
            if current_time - self.last_switch_time >= STATION_DISPLAY_INTERVAL:
                self.display_mode = 1 - self.display_mode  # Toggle 0 <-> 1
                self.last_switch_time = current_time

    def _get_current_dest(self) -> str:
        """Get the current destination, checking for stop-level override.

        Returns:
            Destination text from stop if available, otherwise route-level destination
        """
        if self.stops and self.state.curr_stop < len(self.stops):
            stop_dest = self.stops[self.state.curr_stop].get("dest")
            if stop_dest:
                return stop_dest
        return self.dest

    def _draw_destination(self) -> None:
        """Draw the destination (always kanji, no furigana cycling)."""
        # Get destination, checking for stop-level override
        dest_text = self._get_current_dest()

        # Clear destination area first (fill with dark background)
        box_w = 150
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(15, 50, box_w, 35))

        # Draw destination text
        draw_text_given_width(15, 50, box_w, self.font_dest, dest_text, self.white_bg, self.screen)

        # Draw "ゆき" or "方面" suffix (render directly, no smoothscale)
        suffix = "方面" if self.route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - 10
        suffix_y = self.h - t_h - 5
        suffix_img = self.font_suffix.render(suffix, True, self.white_bg, self.dark_bg)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def _draw_prefix(self) -> None:
        """Draw the prefix with cycling for '次は' -> 'つぎは'."""
        prefix_x = int(S_WIDTH * 0.25) + 40
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(prefix_x, 5, 130, 30))

        # Select display text based on unified display mode (only "次は" has furigana)
        if self.display_mode == 1 and self.prefix_text == "次は":
            prefix_render = "つぎは"
        else:
            prefix_render = self.prefix_text

        prefix_img = self.font_prefix.render(prefix_render, True, self.white_bg)
        self.screen.blit(prefix_img, (prefix_x, 5))

    def _draw_station_name(self) -> None:
        """Draw the current station name with even character spacing.

        Displays either kanji or furigana based on unified display_mode.
        """
        if not self.stops or self.state.curr_stop >= len(self.stops):
            return

        # Get station name based on display mode
        if self.display_mode == 1 and "furigana" in self.stops[self.state.curr_stop]:
            name = self.stops[self.state.curr_stop].get("furigana", "").replace(" ", "")
        else:
            name = self.stops[self.state.curr_stop].get("name", "").replace(" ", "")

        if not name:
            return

        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54

        # Calculate text height for positioning
        _, name_h = self.font_station.size(name)

        name_y = self.h - name_h - 5

        # Clear background
        pygame.draw.rect(
            self.screen,
            self.dark_bg,
            pygame.Rect(name_x, name_y, max_width, name_h + 5),
        )

        # Use draw_text_given_width for even character spacing
        draw_text_given_width(
            name_x,
            name_y,
            int(max_width),
            self.font_station,
            name,
            self.white_bg,
            self.screen,
        )

    def draw_current_station(self) -> None:
        """Update current station name and prefix (次は/まもなく)."""
        # Update prefix text based on PA count
        if self.state.cnt_pa == 0:
            self.prefix_text = "次は"
        elif self.state.cnt_pa == 1:
            self.prefix_text = "まもなく"
        else:
            self.prefix_text = "ただいま"

        # Reset prefix display mode when prefix changes
        self.prefix_display_mode = 0
        self.last_prefix_switch = time.time()

        # Draw prefix (with cycling for "次は")
        self._draw_prefix()

        # Update station name
        self._draw_station_name()

        # Draw hint square (indicates multiple PA announcements)
        if self.stops and len(self.stops[self.state.curr_stop].get("pa", [])) > 1:
            pygame.draw.rect(
                self.screen,
                (247, 225, 158),
                pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20),
            )
        else:
            pygame.draw.rect(
                self.screen,
                self.dark_bg,
                pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20),
            )

        pygame.display.flip()

    def draw_clock(self, timestamp: float) -> None:
        """Draw current time in top-right corner.

        Args:
            timestamp: Unix timestamp
        """
        # Update display mode (kanji/furigana cycling)
        self._update_display_mode()

        curr_time = time.strftime("%H:%M", time.localtime(timestamp))

        clock_x = S_WIDTH - 160
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(clock_x, 5, 80, 25))
        clock_img = self.font_clock.render(curr_time, True, self.white_bg)
        self.screen.blit(clock_img, (clock_x, 0))

        # Redraw prefix, destination and station name (in case mode switched)
        self._draw_prefix()
        self._draw_destination()
        self._draw_station_name()

        # Redraw hint square to ensure it persists
        # Positioned at bottom right of upper section, aligned with bottom edge
        if self.stops and len(self.stops[self.state.curr_stop].get("pa", [])) > 1:
            pygame.draw.rect(
                self.screen,
                (247, 225, 158),
                pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20),
            )
        else:
            pygame.draw.rect(
                self.screen,
                self.dark_bg,
                pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20),
            )

        pygame.display.flip()


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

        # Fonts
        self.font_stops = pygame.font.SysFont(FONT_STOPS_NAME, FONT_STOPS_SIZE)
        self.font_time = pygame.font.SysFont(FONT_TIME_NAME, FONT_TIME_SIZE)
        self.font_minute = pygame.font.SysFont(FONT_STOPS_NAME, FONT_STOPS_MINUTE_SIZE)

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
                    # Use state.skip with guard against negative index
                    effective_idx = i - self.state.skip
                    if i == self.state.curr_stop_disp or effective_idx == self.state.curr_stop_disp:
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

        # Check if next station has no PA
        next_stop = f_stops[self.state.curr_stop_disp + 1]
        if not next_stop.get("pa", []):
            self.state.curr_stop_disp += 1

            if self.state.cnt_pa == 0:
                i = self.state.curr_stop_disp
                while i < len(f_stops) and not f_stops[i].get("pa", []):
                    i += 1
                self.state.skip = i - self.state.curr_stop_disp

                if self.state.skip == 1:
                    # Single skip: jump directly to next station with PA
                    self.state.curr_stop_disp += self.state.skip
                    self.state.skip = 0
                else:
                    # Multi-skip: keep curr_stop_disp at first passing station,
                    # use effective_idx compensation in draw_marks.
                    # Second PA call will complete the skip via line 738.
                    pass
            elif self.state.cnt_pa >= 1:
                self.state.curr_stop_disp += self.state.skip - 1
                self.state.skip = 0
            return

        if self.state.cnt_pa == 0:
            self.state.curr_stop_disp += 1
        else:
            self.state.skip = 0

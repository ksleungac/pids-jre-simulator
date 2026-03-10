"""E235-1000 series Upper LCD display implementation.

Contains all display modes (Japanese, Furigana, English) for the
E235-1000 series Upper LCD.
"""

import pygame
import pygame.gfxdraw
import json
import time
from pathlib import Path

from displays.base import DisplayMode, ModeCycler
from displays.utils import draw_text, draw_text_given_width


# =============================================================================
# Constants (E235-1000 specific - shared across all modes)
# =============================================================================

S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)  # 117px

# Colors
DARK_BG = [25, 25, 25]
WHITE_BG = [230, 230, 230]


# =============================================================================
# JSON Loading
# =============================================================================

def load_json_relative(filename: str) -> dict:
    """Load JSON file relative to project root."""
    # Go up 4 levels: e235_1000/ -> train_models/ -> displays/ -> project root
    path = Path(__file__).parent.parent.parent.parent / filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARNING] JSON file not found: {path}")
        return {}


# =============================================================================
# Japanese Display (KANJI mode)
# =============================================================================

class JapaneseDisplay:
    """Upper LCD Japanese (KANJI) rendering for E235-1000."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # E235-1000 specific fonts
        self.font_type_bold = pygame.font.SysFont("shingopr6nheavy", 26, bold=True, italic=True)
        self.font_dest = pygame.font.SysFont("shingopr6nmedium", 35)
        self.font_prefix = pygame.font.SysFont("shingopr6nmedium", 25)
        self.font_station = pygame.font.SysFont("shingopr6nmedium", 78)
        self.font_clock = pygame.font.SysFont("helveticaneueroman", 26)
        self.font_suffix = pygame.font.SysFont("shingopr6nmedium", 18)

        # E235-1000 specific positions
        self.dest_box_x = 15
        self.dest_box_y = 50
        self.dest_box_w = 150
        self.dest_box_h = 35
        self.suffix_x_offset = 10
        self.suffix_y_offset = 5

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_w = 150
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(15, 8, box_w, 31), 0, 2)
        if len(train_type) > 2:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix (ゆき/方面)."""
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(self.dest_box_x, self.dest_box_y, self.dest_box_w, self.dest_box_h))
        draw_text_given_width(
            self.dest_box_x, self.dest_box_y, self.dest_box_w,
            self.font_dest, dest_text, WHITE_BG, self.screen,
            collapse=False, script="japanese"
        )

        suffix = "方面" if route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - self.suffix_x_offset
        suffix_y = UPPER_HEIGHT - t_h - self.suffix_y_offset
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, DARK_BG)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (次は/まもなく/ただいま)."""
        prefix_x = int(S_WIDTH * 0.25) + 40
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(prefix_x, 5, 300, 30))
        prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, 5))

    def draw_station(self, station_text: str) -> None:
        """Draw station name with even character spacing."""
        if not station_text:
            return

        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54

        _, name_h = self.font_station.size(station_text)
        name_y = UPPER_HEIGHT - name_h - 5

        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(name_x, name_y, max_width, name_h + 5))

        draw_text_given_width(
            name_x, name_y, int(max_width),
            self.font_station, station_text, WHITE_BG, self.screen,
            collapse=False, script="japanese"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x = S_WIDTH - 160
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(clock_x, 5, 80, 25))
        clock_img = self.font_clock.render(time_text, True, WHITE_BG)
        self.screen.blit(clock_img, (clock_x, 0))


# =============================================================================
# Furigana Display (FURIGANA mode)
# =============================================================================

class FuriganaDisplay:
    """
    Upper LCD Furigana rendering for E235-1000.

    By default, behaves the same as JapaneseDisplay.
    Override methods to customize furigana-specific behavior.
    """

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # E235-1000 specific fonts (same as Japanese for now)
        self.font_type_bold = pygame.font.SysFont("shingopr6nheavy", 26, bold=True, italic=True)
        self.font_dest = pygame.font.SysFont("shingopr6nmedium", 35)
        self.font_prefix = pygame.font.SysFont("shingopr6nmedium", 25)
        self.font_station = pygame.font.SysFont("shingopr6nmedium", 78)
        self.font_clock = pygame.font.SysFont("helveticaneueroman", 26)
        self.font_suffix = pygame.font.SysFont("shingopr6nmedium", 18)

        # E235-1000 specific positions (same as Japanese)
        self.dest_box_x = 15
        self.dest_box_y = 50
        self.dest_box_w = 150
        self.dest_box_h = 35
        self.suffix_x_offset = 10
        self.suffix_y_offset = 5

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_w = 150
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(15, 8, box_w, 31), 0, 2)
        if len(train_type) > 2:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix - same as Japanese (kanji stays kanji)."""
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(self.dest_box_x, self.dest_box_y, self.dest_box_w, self.dest_box_h))
        draw_text_given_width(
            self.dest_box_x, self.dest_box_y, self.dest_box_w,
            self.font_dest, dest_text, WHITE_BG, self.screen,
            collapse=False, script="japanese"
        )

        suffix = "方面" if route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - self.suffix_x_offset
        suffix_y = UPPER_HEIGHT - t_h - self.suffix_y_offset
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, DARK_BG)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (already converted to furigana by UpperDisplay manager)."""
        prefix_x = int(S_WIDTH * 0.25) + 40
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(prefix_x, 5, 300, 30))
        prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, 5))

    def draw_station(self, station_text: str) -> None:
        """Draw station name in furigana."""
        if not station_text:
            return

        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54

        _, name_h = self.font_station.size(station_text)
        name_y = UPPER_HEIGHT - name_h - 5

        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(name_x, name_y, max_width, name_h + 5))

        draw_text_given_width(
            name_x, name_y, int(max_width),
            self.font_station, station_text, WHITE_BG, self.screen,
            collapse=False, script="japanese"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x = S_WIDTH - 160
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(clock_x, 5, 80, 25))
        clock_img = self.font_clock.render(time_text, True, WHITE_BG)
        self.screen.blit(clock_img, (clock_x, 0))


# =============================================================================
# English Display (ENGLISH mode)
# =============================================================================

class EnglishDisplay:
    """Upper LCD English rendering for E235-1000."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # E235-1000 specific English fonts
        self.font_type_bold = pygame.font.SysFont("shingopr6nheavy", 26, bold=True, italic=True)
        self.font_dest = pygame.font.SysFont("helveticaneuemedium", 33)
        self.font_prefix = pygame.font.SysFont("helveticaneuemedium", 27)
        self.font_main_prefix = pygame.font.SysFont("helveticaneuemedium", 27)
        self.font_station = pygame.font.SysFont("helveticaneuebold", 115)
        self.font_clock = pygame.font.SysFont("helveticaneueroman", 26)
        self.font_suffix = pygame.font.SysFont("helveticaneuemedium", 27)

        # E235-1000 specific English positions
        self.dest_box_x = 15
        self.dest_box_y = 50
        self.dest_box_w = 150
        self.dest_box_h = 35
        self.suffix_x_offset = -20
        self.suffix_y_offset = 30

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_w = 150
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(15, 8, box_w, 31), 0, 2)
        if len(train_type) > 2:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with prefix ('Bound for')."""
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(self.dest_box_x, self.dest_box_y, self.dest_box_w, self.dest_box_h))

        if "\n" in dest_text:
            lines = dest_text.split("\n")
            line_height = self.font_dest.get_height()
            total_height = line_height * len(lines)
            start_y = self.dest_box_y + (self.dest_box_h - total_height) // 2
            for i, line in enumerate(lines):
                y_pos = start_y + i * line_height
                draw_text_given_width(
                    self.dest_box_x, y_pos, self.dest_box_w,
                    self.font_dest, line, WHITE_BG, self.screen,
                    collapse=True, script="latin"
                )
        else:
            draw_text_given_width(
                self.dest_box_x, self.dest_box_y, self.dest_box_w,
                self.font_dest, dest_text, WHITE_BG, self.screen,
                collapse=True, script="latin"
            )

        suffix = "Bound for"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w + self.suffix_x_offset
        suffix_y = UPPER_HEIGHT - t_h - self.suffix_y_offset
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, DARK_BG)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw English prefix (already translated by UpperDisplay manager)."""
        prefix_x = int(S_WIDTH * 0.25) + 40
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(prefix_x, 5, 300, 30))
        prefix_img = self.font_main_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, 5))

    def draw_station(self, station_text: str) -> None:
        """Draw station name in English (Latin script, collapsed)."""
        if not station_text:
            return

        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54

        _, name_h = self.font_station.size(station_text)
        name_y = UPPER_HEIGHT - name_h - 2

        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(name_x, name_y, max_width, name_h + 2))

        draw_text_given_width(
            name_x, name_y, int(max_width),
            self.font_station, station_text, WHITE_BG, self.screen,
            collapse=True, script="latin"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x = S_WIDTH - 160
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(clock_x, 5, 80, 25))
        clock_img = self.font_clock.render(time_text, True, WHITE_BG)
        self.screen.blit(clock_img, (clock_x, 0))


# =============================================================================
# Upper Display Manager
# =============================================================================

class UpperDisplay:
    """
    E235-1000 Upper LCD manager.

    Handles mode cycling and delegates rendering to mode-specific displays.
    """

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.prefix_text = "ただいま"
        self.curr_stop = 0
        self.cnt_pa = 0

        # Extract route data
        self.route_name = route_data.get("route", "Unknown")
        self.train_type = route_data.get("type", "")
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.type_color = route_data.get("type_color", [0, 0, 0])

        # Create mode-specific displays
        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.furigana_display = FuriganaDisplay(screen, route_data, stops)
        self.english_display = EnglishDisplay(screen, route_data, stops)

        # Initialize mode cycler
        self.mode_displays = {
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            DisplayMode.ENGLISH: self.english_display,
        }
        self.mode_cycler = ModeCycler(self.mode_displays, default_mode=DisplayMode.ENGLISH)

        # Load translations (station names, destinations)
        self.translations = load_json_relative("data/translations.json")

        # Prefix mappings (inline - no need for separate JSON file)
        self.prefix_furigana = {
            "次は": "つぎは",
            "まもなく": "まもなく",
            "ただいま": "ただいま",
        }
        self.prefix_english = {
            "次は": "Next",
            "まもなく": "Arriving at",
            "ただいま": "Now stopping at",
        }

    def _get_current_dest(self) -> str:
        """Get current destination with stop-level override support."""
        if self.stops and self.curr_stop < len(self.stops):
            stop_dest = self.stops[self.curr_stop].get("dest")
            if stop_dest:
                return stop_dest
        return self.dest

    def _get_destination_display(self) -> str:
        """Get destination text based on current display mode."""
        dest_key = self._get_current_dest()
        mode = self.mode_cycler.get_current_mode()

        if mode == DisplayMode.ENGLISH:
            translation = self.translations.get(dest_key, {})
            english_dest = translation.get("english", "")
            if english_dest:
                return english_dest
            return dest_key

        return dest_key

    def _get_prefix_display(self) -> str:
        """Get prefix text based on current display mode."""
        mode = self.mode_cycler.get_current_mode()

        if mode == DisplayMode.ENGLISH:
            return self.prefix_english.get(self.prefix_text, self.prefix_text)

        if mode == DisplayMode.FURIGANA:
            return self.prefix_furigana.get(self.prefix_text, self.prefix_text)

        return self.prefix_text

    def _get_station_display(self) -> str:
        """Get station name based on current display mode."""
        if not self.stops or self.curr_stop >= len(self.stops):
            return ""

        mode = self.mode_cycler.get_current_mode()

        if mode == DisplayMode.ENGLISH:
            return self.stops[self.curr_stop].get(DisplayMode.ENGLISH, "")
        elif mode == DisplayMode.FURIGANA:
            return self.stops[self.curr_stop].get("furigana", "").replace(" ", "")
        else:
            return self.stops[self.curr_stop].get("name", "").replace(" ", "")

    def set_state(self, curr_stop: int, cnt_pa: int) -> None:
        """Update display state (current stop and PA count)."""
        self.curr_stop = curr_stop
        self.cnt_pa = cnt_pa

        if cnt_pa == 0:
            self.prefix_text = "次は"
        elif cnt_pa == 1:
            self.prefix_text = "まもなく"
        else:
            self.prefix_text = "ただいま"

    def update(self, current_time: float = None) -> None:
        """Update mode cycling."""
        self.mode_cycler.update(current_time)

    def draw(self, current_time_str: str = None) -> None:
        """Draw the upper display with current mode's renderer."""
        if current_time_str is None:
            current_time_str = time.strftime("%H:%M", time.localtime())

        display = self.mode_cycler.get_current_display()

        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(0, 0, S_WIDTH, UPPER_HEIGHT))
        pygame.draw.rect(self.screen, self.color, pygame.Rect(int(S_WIDTH * 0.25), 0, 30, UPPER_HEIGHT - 7))

        display.draw_train_type(self.train_type, self.type_color)

        dest_text = self._get_destination_display()
        display.draw_destination(dest_text, self.route_name)

        display.draw_clock(current_time_str)

        prefix_text = self._get_prefix_display()
        display.draw_prefix(prefix_text)

        station_text = self._get_station_display()
        display.draw_station(station_text)

        if self.stops and self.curr_stop < len(self.stops):
            pa_tracks = self.stops[self.curr_stop].get("pa", [])
            if len(pa_tracks) > 1:
                pygame.draw.rect(self.screen, (247, 225, 158), pygame.Rect(S_WIDTH - 20, UPPER_HEIGHT - 20, 20, 20))
            else:
                pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(S_WIDTH - 20, UPPER_HEIGHT - 20, 20, 20))

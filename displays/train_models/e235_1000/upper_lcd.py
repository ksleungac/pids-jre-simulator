"""E235-1000 series Upper LCD display implementation.

Contains all display modes (Japanese, Furigana, English) for the
E235-1000 series Upper LCD.
"""

import pygame
import pygame.gfxdraw
import json
import re
import time
import sys
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
BADGE_TEXT = (15, 15, 15)  # intentionally darker than DARK_BG for text-on-white contrast


# =============================================================================
# JSON Loading
# =============================================================================


def get_base_dir() -> Path:
    """Get base directory - works for both dev and PyInstaller exe."""
    if getattr(sys, "frozen", False):
        # Running as compiled exe - use exe directory
        return Path(sys.executable).parent
    else:
        # Running as script - go up 4 levels from this file
        return Path(__file__).parent.parent.parent.parent


def load_json_relative(filename: str) -> dict:
    """Load JSON file relative to project root."""
    path = get_base_dir() / filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
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

        # E235-1000 specific fonts (shared across methods) - load from fonts/ folder
        self.font_type_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 26)
        self.font_type_bold.set_bold(True)
        self.font_type_bold.set_italic(True)
        self.font_dest = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
        self.font_prefix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 25)
        self.font_station = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 78)
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 26)
        self.font_suffix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 18)

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_x, box_y, box_w, box_h = 15, 8, 150, 31
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
        text_x, text_y = 15, 10
        if len(train_type) > 2:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix (ゆき/方面)."""
        dest_box_x, dest_box_y, dest_box_w, dest_box_h = 15, 50, 150, 35
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(dest_box_x, dest_box_y, dest_box_w, dest_box_h))
        draw_text_given_width(dest_box_x, dest_box_y, dest_box_w, self.font_dest, dest_text, WHITE_BG, self.screen, collapse=False, script="japanese")

        suffix = "方面" if route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - 10
        suffix_y = UPPER_HEIGHT - t_h - 5
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, DARK_BG)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (次は/まもなく/ただいま)."""
        prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
        prefix_w, prefix_h = 300, 30
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(prefix_x, prefix_y, prefix_w, prefix_h))
        prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, prefix_y))

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
            name_x, name_y, int(max_width), self.font_station, station_text, WHITE_BG, self.screen, collapse=False, script="japanese"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x, clock_w, clock_h = S_WIDTH - 160, 80, 25
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(clock_x, 5, clock_w, clock_h))
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

        # E235-1000 specific fonts (shared across methods) - load from fonts/ folder
        self.font_type_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 26)
        self.font_type_bold.set_bold(True)
        self.font_type_bold.set_italic(True)
        self.font_dest = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
        self.font_prefix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 25)
        self.font_station = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 78)
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 26)
        self.font_suffix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 18)

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_x, box_y, box_w, box_h = 15, 8, 150, 31
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
        text_x, text_y = 15, 10
        if len(train_type) > 2:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix - same as Japanese (kanji stays kanji)."""
        dest_box_x, dest_box_y, dest_box_w, dest_box_h = 15, 50, 150, 35
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(dest_box_x, dest_box_y, dest_box_w, dest_box_h))
        draw_text_given_width(dest_box_x, dest_box_y, dest_box_w, self.font_dest, dest_text, WHITE_BG, self.screen, collapse=False, script="japanese")

        suffix = "方面" if route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - 10
        suffix_y = UPPER_HEIGHT - t_h - 5
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, DARK_BG)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (already converted to furigana by UpperDisplay manager)."""
        prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
        prefix_w, prefix_h = 300, 30
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(prefix_x, prefix_y, prefix_w, prefix_h))
        prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, prefix_y))

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
            name_x, name_y, int(max_width), self.font_station, station_text, WHITE_BG, self.screen, collapse=False, script="japanese"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x, clock_w, clock_h = S_WIDTH - 160, 80, 25
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(clock_x, 5, clock_w, clock_h))
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

        # E235-1000 specific English fonts (shared across methods) - load from fonts/ folder
        self.font_type_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 26)
        self.font_type_bold.set_bold(True)
        self.font_type_bold.set_italic(True)
        self.font_dest = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 25)
        self.font_prefix = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 27)
        self.font_main_prefix = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 27)
        self.font_station = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 75)
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 26)
        self.font_suffix = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 20)

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_x, box_y, box_w, box_h = 15, 8, 150, 31
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
        draw_text_given_width(box_x, 10, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True, script="latin")

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with 'for' label above."""
        dest_box_x, dest_box_w = 15, 150
        for_y = 50
        dest_y = 67

        # Draw "for" label
        for_img = self.font_suffix.render("for", True, (182, 182, 199), DARK_BG)
        self.screen.blit(for_img, (5, for_y))

        # Draw destination name
        _, for_h = self.font_suffix.size("for")
        if "\n" in dest_text:
            lines = dest_text.split("\n")
            line_height = self.font_dest.get_height()
            for i, line in enumerate(lines):
                y_pos = dest_y + i * line_height
                draw_text_given_width(
                    dest_box_x + 10, y_pos, dest_box_w - 10, self.font_dest, line, WHITE_BG, self.screen, collapse=True, script="latin"
                )
        else:
            # Single line: vertically center between "for" bottom and UPPER_HEIGHT
            dest_h = self.font_dest.get_height()
            zone_top = for_y + for_h
            single_y = zone_top + (UPPER_HEIGHT - zone_top - dest_h) // 2 - 5
            draw_text_given_width(
                dest_box_x + 10, single_y, dest_box_w - 10, self.font_dest, dest_text, WHITE_BG, self.screen, collapse=True, script="latin"
            )

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw English prefix (already translated by UpperDisplay manager)."""
        prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
        prefix_w, prefix_h = 300, 30
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(prefix_x, prefix_y, prefix_w, prefix_h))
        prefix_img = self.font_main_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, prefix_y))

    def draw_station(self, station_text: str) -> None:
        """Draw station name in English (Latin script, collapsed)."""
        if not station_text:
            return

        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54

        _, name_h = self.font_station.size(station_text)
        # Bottom-aligned with small margin
        name_y = UPPER_HEIGHT - name_h - 2

        draw_text_given_width(name_x, name_y, int(max_width), self.font_station, station_text, WHITE_BG, self.screen, collapse=True, script="latin")

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x, clock_w, clock_h = S_WIDTH - 160, 80, 25
        pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(clock_x, 5, clock_w, clock_h))
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

        self.mode_displays = {
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            DisplayMode.ENGLISH: self.english_display,
        }
        self.mode_cycler = ModeCycler(self.mode_displays, default_mode=DisplayMode.KANJI)

        # Station code badge fonts — sizes tunable here; layout auto-adjusts in _draw_station_code_badge
        self.font_sta_code_prefix = pygame.font.Font("fonts/NeueFrutigerWorld-Bold.otf", 18)
        self.font_sta_code_num = pygame.font.Font("fonts/NeueFrutigerWorld-Bold.otf", 22)
        self.font_sta_code_3letter = pygame.font.Font("fonts/NeueFrutigerWorld-Bold.otf", 20)

        # Load translations (station names, destinations)
        self.translations = load_json_relative("data/translations.json")

        # Load train type translations
        self.train_types = load_json_relative("data/train_types.json")

        # Load station metadata (3-letter codes, future fields)
        self.stations = load_json_relative("data/stations.json")

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

    def _get_train_type_display(self) -> str:
        """Get train type text based on current display mode."""
        mode = self.mode_cycler.get_current_mode()

        if mode == DisplayMode.ENGLISH:
            translation = self.train_types.get(self.train_type, {})
            # Check for short version first (for narrow box), then full english
            english_type = translation.get("english_short", "")
            if not english_type:
                english_type = translation.get("english", "")
            if english_type:
                return english_type
            return self.train_type

        return self.train_type

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
            return self.stops[self.curr_stop].get("english", "")
        elif mode == DisplayMode.FURIGANA:
            return self.stops[self.curr_stop].get("furigana", "").replace(" ", "")
        else:
            return self.stops[self.curr_stop].get("name", "").replace(" ", "")

    def _draw_station_code_badge(self) -> None:
        """Draw station code badge (e.g. JO01, JY03) between color ribbon and station name.

        If the station has a `code_3` entry in data/stations.json (3-letter Roman code,
        e.g. AKB, SJK, TYO), the outer black rect extends upward to form a top band
        showing the code above the framed JY/03 square.
        """
        if not self.stops or self.curr_stop >= len(self.stops):
            return
        sta_code = self.stops[self.curr_stop].get("sta_code")
        if not sta_code:
            return
        m = re.match(r"([A-Za-z]+)(\d+)", sta_code)
        if not m:
            return
        letters = m.group(1).upper()
        number = m.group(2)

        station_name = self.stops[self.curr_stop].get("name", "")
        code_3 = self.stations.get(station_name, {}).get("code_3", "")

        # --- Badge params (adjust freely) ---
        badge_x = 222  # left edge
        badge_w = 68  # total width
        badge_h = 68  # total height (framed JY/03 portion only)
        ring_black = 7  # outer black ring thickness
        ring_color = 7  # route color ring thickness (green bottom aligns with color ribbon)
        outer_radius = 8  # corner rounding of outer black frame
        color_radius = 4  # corner rounding of color ring
        interior_radius = (
            0  # corner rounding of white interior (0 = square corners; raise if you shrink rings and see white corners poke past the color ring)
        )
        text_gap = 3  # px between prefix row bottom and number row top (visible-pixel gap)
        prefix_x_offset = 1  # nudge prefix row right of center (real badge is slightly right-biased)
        # --- code_3 band params (only used when station has a 3-letter code) ---
        code_3_band_h = 12  # height of the top band added above the framed badge (smaller = black rect starts lower)
        code_3_x_offset = 0  # nudge code_3 text horizontally (0 = centered on badge)
        code_3_y_offset = 4  # nudge code_3 text vertically within band (positive = lower, closer to green ring)
        # Font size lives in __init__ as self.font_sta_code_3letter — increase pt if the text should be bigger.
        # -------------------------------------

        badge_y = UPPER_HEIGHT - badge_h
        inset = ring_black + ring_color

        # Interior bounds (derived — don't edit these)
        interior_x = badge_x + inset
        interior_y = badge_y + inset
        interior_w = badge_w - 2 * inset
        interior_h = badge_h - 2 * inset
        center_x = interior_x + interior_w // 2

        # Outer black rect extends upward when code_3 is present
        if code_3:
            outer_y = badge_y - code_3_band_h
            outer_h = badge_h + code_3_band_h
        else:
            outer_y = badge_y
            outer_h = badge_h

        pygame.draw.rect(self.screen, (0, 0, 0), pygame.Rect(badge_x, outer_y, badge_w, outer_h), 0, outer_radius)
        pygame.draw.rect(
            self.screen,
            self.color,
            pygame.Rect(badge_x + ring_black, badge_y + ring_black, badge_w - 2 * ring_black, badge_h - 2 * ring_black),
            0,
            color_radius,
        )
        pygame.draw.rect(self.screen, WHITE_BG, pygame.Rect(interior_x, interior_y, interior_w, interior_h), 0, interior_radius)

        letter_surf = self.font_sta_code_prefix.render(letters, True, BADGE_TEXT)
        num_surf = self.font_sta_code_num.render(number, True, BADGE_TEXT)
        l_rect = letter_surf.get_bounding_rect()
        n_rect = num_surf.get_bounding_rect()

        total_h = l_rect.height + text_gap + n_rect.height
        start_y = interior_y + (interior_h - total_h) // 2

        self.screen.blit(letter_surf, (center_x + prefix_x_offset - l_rect.width // 2 - l_rect.x, start_y - l_rect.y))
        num_y = start_y + l_rect.height + text_gap
        self.screen.blit(num_surf, (center_x - n_rect.width // 2 - n_rect.x, num_y - n_rect.y))

        # code_3 row — white text centered in the top band
        if code_3:
            code_3_surf = self.font_sta_code_3letter.render(code_3, True, WHITE_BG)
            c_rect = code_3_surf.get_bounding_rect()
            band_center_x = badge_x + badge_w // 2
            band_center_y = outer_y + code_3_band_h // 2
            code_3_x = band_center_x + code_3_x_offset - c_rect.width // 2 - c_rect.x
            code_3_y = band_center_y + code_3_y_offset - c_rect.height // 2 - c_rect.y
            self.screen.blit(code_3_surf, (code_3_x, code_3_y))

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

        train_type_text = self._get_train_type_display()
        display.draw_train_type(train_type_text, self.type_color)

        dest_text = self._get_destination_display()
        display.draw_destination(dest_text, self.route_name)

        display.draw_clock(current_time_str)

        prefix_text = self._get_prefix_display()
        display.draw_prefix(prefix_text)

        station_text = self._get_station_display()
        display.draw_station(station_text)

        # Badge drawn last so the extended code_3 band renders on top of
        # overlapping prefix/station DARK_BG rects.
        self._draw_station_code_badge()

        if self.stops and self.curr_stop < len(self.stops):
            pa_tracks = self.stops[self.curr_stop].get("pa", [])
            if len(pa_tracks) > 1:
                pygame.draw.rect(self.screen, (247, 225, 158), pygame.Rect(S_WIDTH - 20, UPPER_HEIGHT - 20, 20, 20))
            else:
                pygame.draw.rect(self.screen, DARK_BG, pygame.Rect(S_WIDTH - 20, UPPER_HEIGHT - 20, 20, 20))

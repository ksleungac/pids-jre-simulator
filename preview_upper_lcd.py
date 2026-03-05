"""Standalone preview script for Upper LCD drawing logic.

This script extracts the UpperDisplay drawing logic for prototyping
the English page feature. Modify this script to test new layouts,
then the changes will be integrated back into display.py.

Current Layout Zones (Upper LCD, height = 117px):
┌─────────────────────────────────────────────────────────────┐
│ [Train Type]  15:30                                         │  Top zone (0-35px)
│ [Dest ゆき]   ║                                              │  Middle zone (35-50px) - color band
│             ──┴──                                            │
│            Prefix    Station Name                            │  Bottom zone (50-117px)
└─────────────────────────────────────────────────────────────┘
"""

import pygame
import pygame.gfxdraw
import time
import sys
from enum import IntEnum


class DisplayMode(IntEnum):
    """Display modes for Upper LCD - cycles through all 3 modes."""

    KANJI = 0  # Japanese kanji
    FURIGANA = 1  # Japanese furigana (phonetic)
    ENGLISH = 2  # English romanized


# =============================================================================
# Constants (copied from constants.py for standalone operation)
# =============================================================================

S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)  # 117px

# Colors
DARK_BG = [25, 25, 25]
WHITE_BG = [230, 230, 230]
PASSED_COLOR = [230, 230, 230]
CURRENT_COLOR = [175, 150, 6]
INACTIVE_COLOR = [110, 110, 110]

# Font configurations
FONT_STOPS_NAME = "shingopr6nmedium"
FONT_STOPS_BOLD_NAME = "shingopr6nheavy"
FONT_CLOCK_NAME = "helveticaneueroman"
FONT_TIME_NAME = "helveticaneue"
FONT_ENGLISH_NAME = "helveticaneuemedium"
FONT_ENGLISH_STOPS_NAME = "helveticaneuebold"

# Font sizes
FONT_TYPE_BOLD_SIZE = 26
FONT_DEST_SIZE = 35
FONT_PREFIX_SIZE = 25
FONT_STATION_SIZE = 78
FONT_CLOCK_SIZE = 26
FONT_SUFFIX_SIZE = 18

# Timing
STATION_DISPLAY_INTERVAL = 2  # Seconds between kanji/furigana cycling

# =============================================================================
# Mock Data (for preview - modify to test different scenarios)
# =============================================================================

MOCK_ROUTE_DATA = {
    "route": "山手線",
    "type": "快速",
    "dest": "東京",
    "dest_furigana": "とうきょう",
    "color": [0, 128, 0],  # Green for Yamanote
    "type_color": [0, 0, 0],
}

MOCK_STOPS = [
    {
        "name": "東京",
        "furigana": "とうきょう",
        DisplayMode.ENGLISH: "Tōkyō",
    },
    {
        "name": "有楽町",
        "furigana": "ゆうらくちょう",
        DisplayMode.ENGLISH: "Yūrakuchō",
    },
    {
        "name": "新橋",
        "furigana": "しんばし",
        DisplayMode.ENGLISH: "Shimbashi",
    },
    {
        "name": "品川",
        "furigana": "しながわ",
        DisplayMode.ENGLISH: "Shinagawa",
    },
    {
        "name": "高輪ゲートウェイ",
        "furigana": "たかなわげーとうぇい",
        DisplayMode.ENGLISH: "Takanawa Gateway",
    },
]

MOCK_STATE = {
    "curr_stop": 0,
    "cnt_pa": 0,  # 0 = "次は", 1 = "まもなく", 2+ = "ただいま"
}

# =============================================================================
# Utility Functions (copied from utils.py)
# =============================================================================


def draw_text(
    text: str,
    font: pygame.font.Font,
    color: tuple,
    x: int,
    y: int,
    bg: tuple = None,
    h_ratio: float = 1.0,
    v_ratio: float = 1.0,
) -> pygame.Surface:
    """Draw text with optional scaling."""
    if bg is None:
        img = font.render(text, True, color).convert_alpha()
        txt_w, txt_h = img.get_size()
        if h_ratio != 1.0 or v_ratio != 1.0:
            img = pygame.transform.smoothscale(img, (int(txt_w * h_ratio), int(txt_h * v_ratio)))
    else:
        img = font.render(text, True, color, bg)
    return img


def draw_text_given_width(
    x: int,
    y: int,
    width: int,
    font: pygame.font.Font,
    text: str,
    color: tuple,
    screen: pygame.Surface,
    collapse: bool = False,
    script: str = "japanese",
) -> None:
    """Draw text constrained to a specific width, compressing if needed.

    Args:
        x, y: Position
        width: Maximum width for the text
        font: Pygame font object
        text: Text to draw
        color: RGB color tuple
        screen: Pygame surface to draw on
        collapse: If True, render as single centered text (for Latin scripts)
        script: 'latin' for proportional fonts (preserves kerning),
                'japanese' for monospaced square characters
    """
    t_w, t_h = font.size(text)
    t_w_s = t_w // len(text) if len(text) > 0 else 0

    if script == "latin":
        # Latin script: render full string centered, scale if needed
        # This preserves kerning between characters
        if t_w > width:
            h_ratio = width / t_w
            img = draw_text(text, font, color, x + (width - t_w) // 2, y, h_ratio=h_ratio)
        else:
            img = draw_text(text, font, color, x + (width - t_w) // 2, y)
        screen.blit(img, (x + (width - t_w) // 2, y))
    elif collapse:
        # Collapse mode for Japanese: render full text centered
        img = draw_text(text, font, color, x + (width - t_w) // 2, y)
        screen.blit(img, (x + (width - t_w) // 2, y))
    elif t_w > width:
        # Japanese text too wide - compress character by character
        sep = width / len(text)
        hr = width / (len(text) * t_w_s) if t_w_s > 0 else 1.0
        for i, char in enumerate(text):
            x_coord = x + sep * i
            img = draw_text(char, font, color, int(x_coord), y, h_ratio=hr)
            screen.blit(img, (int(x_coord), y))
    else:
        # Japanese text fits - add even spacing between characters
        sep = (width - t_w) // (len(text) + 1)
        exp = 7 if len(text) == 2 else 0
        for i, char in enumerate(text):
            x_coord = x + sep * (i + 1) + i * t_w_s + (exp if i > 0 else -exp)
            img = draw_text(char, font, color, int(x_coord), y)
            screen.blit(img, (int(x_coord), y))


# =============================================================================
# UpperDisplay Preview Class
# =============================================================================


class UpperDisplayPreview:
    """Preview version of UpperDisplay for prototyping English page feature."""

    def __init__(self, screen: pygame.Surface, route_data: dict, app_state: dict, stops: list):
        """Initialize the preview display.

        Args:
            screen: Pygame surface to draw on
            route_data: Route configuration dictionary
            app_state: Application state dictionary
            stops: List of stop dictionaries (with furigana/english)
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
        self.font_suffix = pygame.font.SysFont(FONT_STOPS_NAME, FONT_SUFFIX_SIZE)
        # NEW: English fonts for prototyping
        self.font_english_prefix = pygame.font.SysFont(FONT_ENGLISH_NAME, 27)
        self.font_english_station = pygame.font.SysFont(FONT_ENGLISH_STOPS_NAME, 110)

        # Layout configurations per display mode
        # KANJI and FURIGANA share the same layout (both Japanese)
        # Programmatically create FURIGANA layout from KANJI base
        kanji_base = {
            "_draw_prefix.font": self.font_prefix,
            "_draw_prefix.y": 5,
            "_draw_prefix.script": "japanese",
            "_draw_station_name.font": self.font_station,
            "_draw_station_name.y_offset": 5,
            "_draw_station_name.collapse": False,
            "_draw_station_name.script": "japanese",
        }
        self.layouts = {
            DisplayMode.KANJI: kanji_base,
            DisplayMode.FURIGANA: kanji_base.copy(),  # Reuse KANJI layout for furigana
            DisplayMode.ENGLISH: {
                "_draw_prefix.font": self.font_english_prefix,
                "_draw_prefix.y": 5,
                "_draw_prefix.script": "latin",
                "_draw_station_name.font": self.font_english_station,
                "_draw_station_name.y_offset": 5,
                "_draw_station_name.collapse": True,
                "_draw_station_name.script": "latin",
            },
        }

        # Display mode - cycles through KANJI -> FURIGANA -> ENGLISH -> KANJI
        self.display_mode = DisplayMode.ENGLISH  # Default to English for prototyping
        self.last_switch_time = time.time()
        self.prefix_text = "ただいま"
        self.cycling_enabled = True  # Enable cycling through all 3 modes

    def _get_current_layout(self) -> dict:
        """Get layout configuration for current display mode."""
        return self.layouts[self.display_mode]

    def _update_display_mode(self) -> None:
        """Update display mode based on timer.

        Cycles through all 3 modes: KANJI -> FURIGANA -> ENGLISH -> KANJI

        Note: Set self.cycling_enabled = False to disable automatic switching.
        """
        if not self.cycling_enabled:
            return

        current_time = time.time()

        # Check what's available for current station
        if self.state["curr_stop"] < len(self.stops):
            has_furigana = "furigana" in self.stops[self.state["curr_stop"]]
            has_english = DisplayMode.ENGLISH in self.stops[self.state["curr_stop"]]
        else:
            has_furigana = False
            has_english = False

        # Determine which modes are available
        available_modes = [DisplayMode.KANJI]  # KANJI always available
        if has_furigana:
            available_modes.append(DisplayMode.FURIGANA)
        if has_english:
            available_modes.append(DisplayMode.ENGLISH)

        # Cycle to next mode
        if current_time - self.last_switch_time >= STATION_DISPLAY_INTERVAL:
            current_idx = available_modes.index(self.display_mode) if self.display_mode in available_modes else 0
            next_idx = (current_idx + 1) % len(available_modes)
            self.display_mode = available_modes[next_idx]
            self.last_switch_time = current_time
            print(f"[DEBUG] Display mode switched to: {self.display_mode.name}")

    def _get_current_dest(self) -> str:
        """Get the current destination, checking for stop-level override."""
        if self.stops and self.state["curr_stop"] < len(self.stops):
            stop_dest = self.stops[self.state["curr_stop"]].get("dest")
            if stop_dest:
                return stop_dest
        return self.dest

    def _get_destination_display(self) -> str:
        """Get destination text based on display mode.

        NOTE: Currently destination stays as kanji (no cycling).
        This can be modified when implementing English page feature.
        """
        return self._get_current_dest()

    def _get_prefix_display(self) -> str:
        """Get prefix text based on display mode.

        KANJI: Shows kanji prefix (e.g., '次は')
        FURIGANA: Shows furigana prefix (e.g., 'つぎは')
        ENGLISH: Shows English translation (e.g., 'Next')
        """
        # English translations
        if self.display_mode == DisplayMode.ENGLISH:
            if self.prefix_text == "次は":
                return "Next"
            if self.prefix_text == "ただいま":
                return "Now stopping at"
            if self.prefix_text == "まもなく":
                return "Arriving at"

        # FURIGANA mode - convert specific kanji to furigana
        if self.display_mode == DisplayMode.FURIGANA:
            if self.prefix_text == "次は":
                return "つぎは"
            # Other prefixes stay as-is (no furigana data)

        # KANJI mode (or unknown prefix)
        return self.prefix_text

    def _get_station_display(self) -> str:
        """Get station name based on display mode."""
        if not self.stops or self.state["curr_stop"] >= len(self.stops):
            return ""

        if self.display_mode == DisplayMode.ENGLISH:
            return self.stops[self.state["curr_stop"]].get(DisplayMode.ENGLISH, "")
        elif self.display_mode == DisplayMode.FURIGANA:
            return self.stops[self.state["curr_stop"]].get("furigana", "").replace(" ", "")
        else:  # KANJI
            return self.stops[self.state["curr_stop"]].get("name", "").replace(" ", "")

    # =============================================================================
    # Helper Methods - Single Source of Truth for Each Zone
    # =============================================================================

    def _draw_train_type(self) -> None:
        """Draw train type box (top-left)."""
        box_w = 150
        pygame.draw.rect(self.screen, self.white_bg, pygame.Rect(15, 8, box_w, 31), 0, 2)
        if len(self.train_type) > 2:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, self.train_type, self.type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(15, 10, box_w, self.font_type_bold, self.train_type, self.type_color, self.screen)

    def _draw_destination(self) -> None:
        """Draw destination banner (left side, below train type)."""
        box_w = 150
        dest_text = self._get_destination_display()
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(15, 50, box_w, 35))
        draw_text_given_width(15, 50, box_w, self.font_dest, dest_text, self.white_bg, self.screen)

        # Suffix ("ゆき" or "方面")
        suffix = "方面" if self.route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - 10
        suffix_y = self.h - t_h - 5
        suffix_img = self.font_suffix.render(suffix, True, self.white_bg, self.dark_bg)
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def _draw_clock(self) -> None:
        """Draw clock (top-right)."""
        curr_time = time.strftime("%H:%M", time.localtime())
        clock_x = S_WIDTH - 160
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(clock_x, 5, 80, 25))
        clock_img = self.font_clock.render(curr_time, True, self.white_bg)
        self.screen.blit(clock_img, (clock_x, 0))

    def _draw_prefix(self) -> None:
        """Draw prefix with cycling logic (center, after color band).

        Uses layout configuration from self.layouts based on display mode.
        """
        layout = self._get_current_layout()
        prefix_x = int(S_WIDTH * 0.25) + 40
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(prefix_x, 5, 300, 30))
        prefix_render = self._get_prefix_display()
        prefix_img = layout["_draw_prefix.font"].render(prefix_render, True, self.white_bg)
        self.screen.blit(prefix_img, (prefix_x, layout["_draw_prefix.y"]))

    def _draw_station_name(self) -> None:
        """Draw the current station name with even character spacing.

        Uses layout configuration from self.layouts based on display mode:
        - KANJI/FURIGANA: Japanese (shingopr6nmedium, size 78)
        - ENGLISH: English romanized (helveticaneuebold, size 110)
        """
        layout = self._get_current_layout()
        name = self._get_station_display()
        if not name:
            return

        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54

        # Calculate text height for positioning using layout config
        font = layout["_draw_station_name.font"]
        _, name_h = font.size(name)
        name_y = self.h - name_h - layout["_draw_station_name.y_offset"]

        # Clear background
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(name_x, name_y, max_width, name_h + 5))

        # Use draw_text_given_width for even character spacing
        draw_text_given_width(
            name_x,
            name_y,
            int(max_width),
            font,
            name,
            self.white_bg,
            self.screen,
            collapse=layout["_draw_station_name.collapse"],
            script=layout["_draw_station_name.script"],
        )

    def _draw_hint_square(self) -> None:
        """Draw hint square (bottom-right of upper section)."""
        if self.stops and len(self.stops[self.state["curr_stop"]].get("pa", [])) > 1:
            pygame.draw.rect(self.screen, (247, 225, 158), pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20))
        else:
            pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(S_WIDTH - 20, self.h - 20, 20, 20))

    # =============================================================================
    # Public Draw Methods - Compose Helpers
    # =============================================================================

    def draw_init(self) -> None:
        """Draw initial state (all elements)."""
        # Draw dark background
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(0, 0, S_WIDTH, self.h))

        # =====================================================================
        # ONLY INLINE: Color Band (never changes, static)
        # =====================================================================
        pygame.draw.rect(self.screen, self.color, pygame.Rect(int(S_WIDTH * 0.25), 0, 30, self.h - 7))

        # =====================================================================
        # ALL OTHER ZONES: Use helper methods (single source of truth)
        # =====================================================================
        self._draw_train_type()
        self._draw_destination()
        self._draw_clock()
        self._draw_prefix()
        self._draw_station_name()
        self._draw_hint_square()

        pygame.display.flip()

    def draw_current_station(self) -> None:
        """Update current station name and prefix."""
        # Update prefix text based on PA count
        if self.state["cnt_pa"] == 0:
            self.prefix_text = "次は"
        elif self.state["cnt_pa"] == 1:
            self.prefix_text = "まもなく"
        else:
            self.prefix_text = "ただいま"

        # Use helpers - single source of truth
        self._draw_prefix()
        self._draw_station_name()
        self._draw_hint_square()

        pygame.display.flip()

    def draw_clock(self, timestamp: float) -> None:
        """Draw current time and update display mode cycling."""
        # Update display mode (KANJI -> FURIGANA -> ENGLISH cycling)
        self._update_display_mode()

        # Clock may have changed - redraw
        self._draw_clock()

        # Redraw elements that may have changed due to mode switch
        self._draw_destination()
        self._draw_prefix()
        self._draw_station_name()
        self._draw_hint_square()

        pygame.display.flip()


# =============================================================================
# Main Preview Loop
# =============================================================================


def main():
    """Run the preview loop for testing Upper LCD display."""
    pygame.init()
    screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
    pygame.display.set_caption("Upper LCD Preview - Press: PageDown=next station, PageUp=next PA, ESC=quit")
    clock = pygame.time.Clock()

    # Initialize display
    display = UpperDisplayPreview(screen, MOCK_ROUTE_DATA, MOCK_STATE, MOCK_STOPS)
    display.draw_init()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_PAGEDOWN:
                    # Next station
                    MOCK_STATE["curr_stop"] = (MOCK_STATE["curr_stop"] + 1) % len(MOCK_STOPS)
                    MOCK_STATE["cnt_pa"] = 0
                    print(f"[DEBUG] Station: {MOCK_STOPS[MOCK_STATE['curr_stop']]['name']}")
                    display.draw_init()
                elif event.key == pygame.K_PAGEUP:
                    # Next PA
                    MOCK_STATE["cnt_pa"] = (MOCK_STATE["cnt_pa"] + 1) % 3
                    prefixes = ["次は", "まもなく", "ただいま"]
                    print(f"[DEBUG] PA: {prefixes[MOCK_STATE['cnt_pa']]}")
                    display.draw_current_station()

        # Update clock (triggers display mode cycling)
        display.draw_clock(time.time())

        clock.tick(15)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

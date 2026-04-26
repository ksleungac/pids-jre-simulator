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
# Region Map — E235-1000 upper LCD layout (descriptive)
#
# CONTRACT: every region must visually confine its drawing (clear bg + glyphs)
# to its declared confinement rect below. See DISPLAY.md § "Element Clear-
# Background Convention" — has D1/D2 distinction, probing methodology, and the
# 2026-04-25 bug history (English draw_destination had no clear rect; bled).
#
# Coordinates are within the upper LCD area (y=0..UPPER_HEIGHT=117).
# "Debug" tints come from _DEBUG_COLORS below — `--debug-grid` paints them so
# violations (a region's drawing landing on a neighbor's tint) are visible.
#
# Region       Confinement (x, y, w, h)   Drawn by                    Debug
# ----------   ------------------------   -------------------------   --------
# upper_bg     (0, 0, 730, 117)           UpperDisplay.draw           gray
# ribbon       (182, 0, 30, 110)          UpperDisplay.draw           — (route color)
# train_type   (15, 8, 150, 31)           *Display.draw_train_type    — (WHITE_BG)
# dest         (0, 50, 180, 67)           *Display.draw_destination   red    (incl. suffix area)
# prefix       (222, 5, 300, 30)          *Display.draw_prefix        blue
# clock        (570, 5, 80, 25)           *Display.draw_clock         yellow
# station      (302, 35, 384, 82)         *Display.draw_station       purple (clear clamped; glyph surfaces
#                                                                              may extend above via font leading,
#                                                                              but visible caps stay at y≥35 —
#                                                                              verified by probe across all 4 modes)
# pa_hint      (710, 97, 20, 20)          UpperDisplay.draw           orange (yellow when len(pa)>1)
# badge        (222, 49, 68, 68)          _draw_station_code_badge    — (route color, optional code_3 band extends up)
# =============================================================================


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
# Debug grid — makes region clear-rects visible by tinting their backgrounds.
# Each draw method paints its DARK_BG clear via _bg("<region>") so flipping
# DEBUG_GRID swaps every region's bg to a unique tint. Use to:
#   - Spot clear-rect overlaps (one region's tint bleeds into another's bounds)
#   - Spot under-cleared zones (dark untinted patches inside a region that
#     should be fully painted)
#   - Spot clipping (text/glyphs cut off at the boundary of a tinted region)
# The dict literal also serves as the lightweight region manifest for upper
# E235-1000 — keys here are the region names referenced in draw methods.
# =============================================================================

DEBUG_GRID: bool = False  # flipped by preview_display.py --debug-grid

_DEBUG_COLORS = {
    "upper_bg":   (80, 80, 80),    # neutral gray — baseline "no region claimed this pixel"
    "dest":       (180, 40, 40),   # bright red
    "prefix":     (40, 80, 200),   # bright blue
    "clock":      (200, 170, 30),  # bright yellow
    "station":    (140, 40, 170),  # bright magenta/purple
    "pa_hint":    (220, 110, 0),   # bright orange
    # Note: train_type is intentionally absent — its WHITE_BG box is already
    # visually distinct from every other region's tint, so keep it WHITE_BG in
    # debug mode too. The _bg("train_type", default=WHITE_BG) call resolves
    # to WHITE_BG in both modes via the default-fallback path.
}


def _bg(region: str, default=None):
    """Return the region's normal background color, or its debug tint when DEBUG_GRID is on.

    Most regions clear to DARK_BG normally — pass no `default` and it'll use
    DARK_BG. Some regions clear to a different baseline (e.g. train_type uses
    WHITE_BG); pass `default=WHITE_BG` for those so normal-mode appearance is
    preserved. Region keys must match _DEBUG_COLORS — adding a new region
    means adding it here too, which keeps the manifest in sync with the draw
    code by construction.
    """
    if default is None:
        default = DARK_BG
    if DEBUG_GRID:
        return _DEBUG_COLORS.get(region, default)
    return default


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
        pygame.draw.rect(self.screen, _bg("train_type", default=WHITE_BG), pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
        text_x, text_y = 15, 10
        if len(train_type) > 2:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix (ゆき/方面)."""
        # Region clear — covers the full dest territory (text box + suffix
        # below). Convention: every changeable element clears its full
        # territory, not just its current glyph footprint.
        pygame.draw.rect(self.screen, _bg("dest"), pygame.Rect(0, 50, 180, UPPER_HEIGHT - 50))

        dest_box_x, dest_box_y, dest_box_w = 15, 50, 150
        draw_text_given_width(dest_box_x, dest_box_y, dest_box_w, self.font_dest, dest_text, WHITE_BG, self.screen, collapse=False, script="japanese")

        suffix = "方面" if route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - 10
        suffix_y = UPPER_HEIGHT - t_h - 5
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, _bg("dest"))
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (次は/まもなく/ただいま)."""
        prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
        prefix_w, prefix_h = 300, 30
        pygame.draw.rect(self.screen, _bg("prefix"), pygame.Rect(prefix_x, prefix_y, prefix_w, prefix_h))
        prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, prefix_y))

    def draw_station(self, station_text: str) -> None:
        """Draw station name with even character spacing."""
        if not station_text:
            return

        name_x = int(S_WIDTH * 0.40) + 10
        max_width = S_WIDTH * 0.54 - 10
        band_bottom_y = 35  # station's clear rect must not extend above this y (prefix/clock band)

        _, name_h = self.font_station.size(station_text)
        name_y = UPPER_HEIGHT - name_h - 5  # -5 leaves a small bottom margin

        # Clear rect clamped to station's confinement on both ends. Glyphs blit at
        # name_y may have a surface that extends above; the leading absorbs it so
        # no visible pixel actually lands above band_bottom_y (verified by probe).
        # The +5 below mirrors the -5 in name_y so clear_bot lands exactly at
        # UPPER_HEIGHT after the min(...) clamp — covers any descender residue.
        clear_top = max(name_y, band_bottom_y)
        clear_bot = min(name_y + name_h + 5, UPPER_HEIGHT)
        if clear_bot > clear_top:
            pygame.draw.rect(self.screen, _bg("station"), pygame.Rect(name_x, clear_top, max_width, clear_bot - clear_top))

        draw_text_given_width(
            name_x, name_y, int(max_width), self.font_station, station_text, WHITE_BG, self.screen, collapse=False, script="japanese"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x, clock_w, clock_h = S_WIDTH - 160, 80, 25
        pygame.draw.rect(self.screen, _bg("clock"), pygame.Rect(clock_x, 5, clock_w, clock_h))
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
        pygame.draw.rect(self.screen, _bg("train_type", default=WHITE_BG), pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
        text_x, text_y = 15, 10
        if len(train_type) > 2:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
        else:
            draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix - same as Japanese (kanji stays kanji)."""
        # Region clear — see JapaneseDisplay.draw_destination for the convention.
        pygame.draw.rect(self.screen, _bg("dest"), pygame.Rect(0, 50, 180, UPPER_HEIGHT - 50))

        dest_box_x, dest_box_y, dest_box_w = 15, 50, 150
        draw_text_given_width(dest_box_x, dest_box_y, dest_box_w, self.font_dest, dest_text, WHITE_BG, self.screen, collapse=False, script="japanese")

        suffix = "方面" if route_name == "山手線" else "ゆき"
        t_w, t_h = self.font_suffix.size(suffix)
        suffix_x = int(S_WIDTH * 0.25) - t_w - 10
        suffix_y = UPPER_HEIGHT - t_h - 5
        suffix_img = self.font_suffix.render(suffix, True, WHITE_BG, _bg("dest"))
        self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (already converted to furigana by UpperDisplay manager)."""
        prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
        prefix_w, prefix_h = 300, 30
        pygame.draw.rect(self.screen, _bg("prefix"), pygame.Rect(prefix_x, prefix_y, prefix_w, prefix_h))
        prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, prefix_y))

    def draw_station(self, station_text: str) -> None:
        """Draw station name in furigana."""
        if not station_text:
            return

        name_x = int(S_WIDTH * 0.40) + 10
        max_width = S_WIDTH * 0.54 - 10
        band_bottom_y = 35  # station's clear rect must not extend above this y (prefix/clock band)

        _, name_h = self.font_station.size(station_text)
        name_y = UPPER_HEIGHT - name_h - 5  # -5 leaves a small bottom margin (see JapaneseDisplay.draw_station)

        # Clear rect clamped to station's confinement on both ends — see JapaneseDisplay.draw_station
        # for full notes on the band_bottom clamp and the +5/-5 pairing.
        clear_top = max(name_y, band_bottom_y)
        clear_bot = min(name_y + name_h + 5, UPPER_HEIGHT)
        if clear_bot > clear_top:
            pygame.draw.rect(self.screen, _bg("station"), pygame.Rect(name_x, clear_top, max_width, clear_bot - clear_top))

        draw_text_given_width(
            name_x, name_y, int(max_width), self.font_station, station_text, WHITE_BG, self.screen, collapse=False, script="japanese"
        )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x, clock_w, clock_h = S_WIDTH - 160, 80, 25
        pygame.draw.rect(self.screen, _bg("clock"), pygame.Rect(clock_x, 5, clock_w, clock_h))
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
        self.font_dest = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 24)
        self.font_main_prefix = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 27)
        self.font_station = pygame.font.Font("fonts/HelveticaNeue-Bold.otf", 75)
        # Used when station_text contains "\n" — see draw_station's 2-line branch.
        # Smaller pt so two lines fit in the ~82px station area without colliding
        # with the prefix band. Tune in concert with line_gap below.
        self.font_station_2line = pygame.font.Font("fonts/HelveticaNeue-Bold.otf", 42)
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 26)
        self.font_suffix = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 20)

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        box_x, box_y, box_w, box_h = 15, 8, 150, 31
        pygame.draw.rect(self.screen, _bg("train_type", default=WHITE_BG), pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
        draw_text_given_width(box_x, 10, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True, script="latin")

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with 'for' label above."""
        dest_box_x, dest_box_w = 15, 150
        for_y = 50

        # Region clear — covers the whole left dest column ("for" label + 1- or
        # 2-line dest text). x stops at 180 (just left of the ribbon at x=182).
        # Larger than the actual glyph footprint on purpose so debug-grid mode
        # shows the dest territory clearly.
        pygame.draw.rect(self.screen, _bg("dest"), pygame.Rect(0, for_y, 180, UPPER_HEIGHT - for_y))

        # Draw "for" label
        for_img = self.font_suffix.render("for", True, (182, 182, 199), _bg("dest"))
        self.screen.blit(for_img, (5, for_y))

        # Draw destination name
        _, for_h = self.font_suffix.size("for")
        if "\n" in dest_text:
            # 2-line: lines left-aligned with "for" (x=5), breathing room below
            # "for". Uses full-height pitch (font.get_height()) for natural
            # inter-line spacing — *not* ascent-pitch (that's the station
            # renderer's tighter stacking). Inter-line gap matters here because
            # line 1 may contain descenders ("p" of "Airport", "g" of "Shinagawa")
            # that would collide with line 2's caps under ascent-pitch.
            two_line_x       = 5                  # align with "for" left edge
            two_line_top_pad = 5                  # gap between "for" visible bottom and line 1 top
            two_line_max_w   = 175                # extends to right edge of dest region (~180)
            visible_for_bottom = for_y + self.font_suffix.get_ascent()
            top_y = visible_for_bottom + two_line_top_pad
            line_pitch = self.font_dest.get_height()  # full-height pitch — natural inter-line gap
            lines = dest_text.split("\n")
            for i, line in enumerate(lines):
                y_pos = top_y + i * line_pitch
                img = self.font_dest.render(line, True, WHITE_BG)
                w = img.get_width()
                if w > two_line_max_w:
                    img = pygame.transform.smoothscale(img, (two_line_max_w, img.get_height()))
                self.screen.blit(img, (two_line_x, y_pos))
        else:
            # Single line: vertically center between "for" bottom and UPPER_HEIGHT
            text_x = dest_box_x + 10
            text_max_w = dest_box_w - 10
            dest_h = self.font_dest.get_height()
            zone_top = for_y + for_h
            single_y = zone_top + (UPPER_HEIGHT - zone_top - dest_h) // 2 - 5
            draw_text_given_width(
                text_x, single_y, text_max_w, self.font_dest, dest_text, WHITE_BG, self.screen, collapse=True, script="latin"
            )

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw English prefix (already translated by UpperDisplay manager)."""
        prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
        prefix_w, prefix_h = 300, 30
        pygame.draw.rect(self.screen, _bg("prefix"), pygame.Rect(prefix_x, prefix_y, prefix_w, prefix_h))
        prefix_img = self.font_main_prefix.render(prefix_text, True, WHITE_BG)
        self.screen.blit(prefix_img, (prefix_x, prefix_y))

    def draw_station(self, station_text: str) -> None:
        """Draw station name in English (Latin script).

        Single-line: bottom-aligned, horizontally width-fit (smoothscale).
        Two-line (when station_text contains "\\n"): smaller font, line 1
        left-aligned, line 2 right-aligned, both bottom-aligned. Mirrors the
        JR East PIDS treatment for stations like 成田空港 ("Narita Airport /
        Terminal 1") and 空港第2ビル ("Narita Airport / Terminal 2·3").
        """
        if not station_text:
            return

        # --- Station layout params ---
        name_x             = int(S_WIDTH * 0.40) + 10
        max_width          = int(S_WIDTH * 0.54 - 10)
        clear_pad_y        = 10   # extra px below glyph box for descender + mode-cycle scrub
        band_bottom_y      = 35   # bottom edge of the prefix/clock band — clear rect must not extend above this y
                                  # (otherwise it clobbers "Now stopping at" / clock when station glyphs reach high)
        # 2-line (used when station_text contains "\n"):
        line_pitch_offset  = 0    # px adjustment to ascent-based pitch (-ve = even tighter, +ve = looser)
        # -----------------------------

        def _clear_rect(top_y_, bottom_y_):
            """Clear between top_y_ and bottom_y_, clamped on BOTH ends so the
            station's territory stays inside the upper LCD bounds and below the
            prefix/clock band. Glyphs extending above the clamped top rely on
            the full-upper clear at the start of UpperDisplay.draw() — no stale
            residue. Bottom clamp prevents leaking into the lower display area
            (which would overpaint anyway, but containment > defensive overlap)."""
            t = max(top_y_, band_bottom_y)
            b = min(bottom_y_, UPPER_HEIGHT)
            h = b - t
            if h > 0:
                pygame.draw.rect(self.screen, _bg("station"), pygame.Rect(name_x, t, max_width, h))

        if "\n" in station_text:
            line1, line2 = station_text.split("\n", 1)
            font = self.font_station_2line
            font_h = font.get_height()
            # Line pitch = ascent: line 2's top sits at line 1's baseline → tight
            # stacking with no descender gap. Tune via line_pitch_offset.
            line_pitch = font.get_ascent() + line_pitch_offset
            total_h = line_pitch + font_h
            top_y = UPPER_HEIGHT - total_h

            _clear_rect(top_y, top_y + total_h + clear_pad_y)

            # Line 1: left-aligned at name_x. Compress horizontally if natural
            # width exceeds max_width — same defensive smoothscale the dest
            # 2-line branch uses, so future long translations don't spill past
            # the station area.
            l1_img = font.render(line1, True, WHITE_BG)
            l1_w = l1_img.get_width()
            if l1_w > max_width:
                l1_img = pygame.transform.smoothscale(l1_img, (max_width, l1_img.get_height()))
                l1_w = max_width
            self.screen.blit(l1_img, (name_x, top_y))

            # Line 2: right-aligned at the right edge of the station area.
            # Same width-clamp as line 1 — without it, a long translation
            # would push the right-aligned blit x below name_x and spill
            # leftward past the badge.
            l2_img = font.render(line2, True, WHITE_BG)
            l2_w = l2_img.get_width()
            if l2_w > max_width:
                l2_img = pygame.transform.smoothscale(l2_img, (max_width, l2_img.get_height()))
                l2_w = max_width
            l2_y = top_y + line_pitch
            self.screen.blit(l2_img, (name_x + max_width - l2_w, l2_y))
            return

        _, name_h = self.font_station.size(station_text)
        # Bottom-aligned, nudged down ~2px to match reference vertical placement
        name_y = UPPER_HEIGHT - name_h

        _clear_rect(name_y, name_y + name_h + clear_pad_y)

        draw_text_given_width(name_x, name_y, max_width, self.font_station, station_text, WHITE_BG, self.screen, collapse=True, script="latin")

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        clock_x, clock_w, clock_h = S_WIDTH - 160, 80, 25
        pygame.draw.rect(self.screen, _bg("clock"), pygame.Rect(clock_x, 5, clock_w, clock_h))
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

        pygame.draw.rect(self.screen, _bg("upper_bg"), pygame.Rect(0, 0, S_WIDTH, UPPER_HEIGHT))
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
                pygame.draw.rect(self.screen, _bg("pa_hint"), pygame.Rect(S_WIDTH - 20, UPPER_HEIGHT - 20, 20, 20))

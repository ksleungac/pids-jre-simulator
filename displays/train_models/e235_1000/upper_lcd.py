"""E235-1000 series Upper LCD display implementation.

Contains all display modes (Japanese, Furigana, English) for the
E235-1000 series Upper LCD.
"""

import pygame
import time

from app_paths import load_json_relative
from displays.base import DisplayMode, ModeCycler
from displays.utils import clip, draw_text_given_width, draw_station_code_badge

# =============================================================================
# Region Map — E235-1000 upper LCD layout (descriptive)
#
# CONTRACT: each region's draw method clips to its rect (see manifest below
# this comment block: TRAIN_TYPE_RECT, DEST_RECT, PREFIX_RECT, STATION_RECT,
# CLOCK_RECT, BADGE_RECT, PA_HINT_RECT). The clip is a hard guarantee — pixels
# drawn outside the rect are dropped by pygame. See DISPLAY_E235.md § "Element
# confinement (clip-enforced)" for the rationale and gotchas.
#
# Coordinates are within the upper LCD area (y=0..UPPER_HEIGHT=117).
# "Debug" tints come from _DEBUG_COLORS below — `--debug-grid` paints them so
# a new region's declared rect can be visually verified to cover its
# intended footprint.
#
# Bounds + drawn-by + debug-tint for each region:
#
# Region       Drawn by                    Rect constant       Debug tint
# ----------   -------------------------   -----------------   --------------
# upper_bg     UpperDisplay.draw           (full LCD area)     gray
# ribbon       UpperDisplay.draw           (route color band)  — (route color)
# train_type   *Display.draw_train_type    TRAIN_TYPE_RECT     — (WHITE_BG)
# dest         *Display.draw_destination   DEST_RECT           red
# prefix       *Display.draw_prefix        PREFIX_RECT         blue
# clock        *Display.draw_clock         CLOCK_RECT          yellow
# station      *Display.draw_station       STATION_RECT        purple
# pa_hint      UpperDisplay.draw           PA_HINT_RECT        orange (blinks yellow @ 1 Hz)
# badge        _draw_station_code_badge    BADGE_RECT          — (route color; rect spans optional code_3 top band)
# =============================================================================


# =============================================================================
# Per-model dimensions / palette — single source of truth lives in this
# model's package __init__.py (so lower_lcd.py and app.py read the same
# values without one LCD module being "the boss" over the other).
# =============================================================================

from displays.train_models.e235_1000 import (
    S_WIDTH,
    S_HEIGHT,
    UPPER_HEIGHT,
    DARK_BG,
    WHITE_BG,
)


# =============================================================================
# Region rect manifest — single source of truth for each region's bounds.
#
# Each draw method clips to its region's rect via ``with clip(screen, RECT):``,
# so any glyph or shape drawn inside cannot escape into a neighbour's territory
# (pygame drops out-of-clip pixels at the surface level — hard guarantee, no
# eyeball check needed). The same rects also drive the debug-grid tints and
# the per-region bg fills.
#
# When tuning a region's bounds, change the rect here only. The clip wrap, the
# bg fill, and the debug-grid tint all read from the same constant.
# =============================================================================

TRAIN_TYPE_RECT = pygame.Rect(15, 8, 150, 31)
DEST_RECT       = pygame.Rect(0, 50, 180, UPPER_HEIGHT - 50)
PREFIX_RECT     = pygame.Rect(222, 5, 300, 30)
STATION_RECT    = pygame.Rect(302, 35, 384, 82)
# Clock blits at y=0 (surface ascender absorbs the y=0..5 strip); the rect
# spans y=0..35 so clip never amputates the visible glyph caps.
CLOCK_RECT      = pygame.Rect(S_WIDTH - 170, 0, 80, 35)
# Badge spans both the framed 68×68 square AND the optional code_3 top band
# (12 px upward extension when present). Sized to the maximum (with-band)
# extent so clip never amputates the band when code_3 is set.
BADGE_RECT      = pygame.Rect(222, UPPER_HEIGHT - 68 - 12, 68, 68 + 12)
PA_HINT_RECT    = pygame.Rect(S_WIDTH - 20, UPPER_HEIGHT - 20, 20, 20)


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
# Japanese Display (KANJI mode)
# =============================================================================


class JapaneseDisplay:
    """Upper LCD Japanese (KANJI) rendering for E235-1000."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # CONTRACT: load fonts from file paths only — never `pygame.font.SysFont()`.
        # SysFont scans the Windows font registry, which fails on Chinese/Japanese
        # locale Windows with `TypeError: expected str, bytes or os.PathLike object,
        # not int`. All fonts in this project ship in fonts/ and load via Font(path).
        # E235-1000 specific fonts (shared across methods) - load from fonts/ folder
        self.font_type_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 26)
        self.font_type_bold.set_bold(True)
        self.font_type_bold.set_italic(True)
        self.font_dest = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
        self.font_prefix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 25)
        self.font_station = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 78)
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 27)
        self.font_suffix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 18)

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        with clip(self.screen, TRAIN_TYPE_RECT):
            box_x, box_y, box_w, box_h = 15, 8, 150, 31
            pygame.draw.rect(self.screen, _bg("train_type", default=WHITE_BG), pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
            text_x, text_y = 15, 10
            if len(train_type) > 2:
                draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True)
            else:
                draw_text_given_width(text_x, text_y, box_w, self.font_type_bold, train_type, type_color, self.screen)

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix (ゆき/方面)."""
        with clip(self.screen, DEST_RECT):
            # Per-region bg fill (DARK_BG / debug-grid tint).
            pygame.draw.rect(self.screen, _bg("dest"), DEST_RECT)

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
        with clip(self.screen, PREFIX_RECT):
            pygame.draw.rect(self.screen, _bg("prefix"), PREFIX_RECT)
            prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
            prefix_img = self.font_prefix.render(prefix_text, True, WHITE_BG)
            self.screen.blit(prefix_img, (prefix_x, prefix_y))

    def draw_station(self, station_text: str) -> None:
        """Draw station name with even character spacing."""
        if not station_text:
            return

        with clip(self.screen, STATION_RECT):
            name_x = int(S_WIDTH * 0.40) + 10
            max_width = S_WIDTH * 0.54 - 10

            _, name_h = self.font_station.size(station_text)
            name_y = UPPER_HEIGHT - name_h - 5  # -5 leaves a small bottom margin

            # Clip handles the confinement guarantee — any glyph pixel that
            # would land above STATION_RECT.top (y=35) is dropped at the
            # pygame layer. The bg fill below is sized to the full STATION_RECT
            # so the debug-grid tint shows the entire territory.
            pygame.draw.rect(self.screen, _bg("station"), STATION_RECT)

            draw_text_given_width(
                name_x, name_y, int(max_width), self.font_station, station_text, WHITE_BG, self.screen, collapse=False, script="japanese"
            )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        with clip(self.screen, CLOCK_RECT):
            clock_x, clock_w, clock_h = S_WIDTH - 170, 80, 25
            pygame.draw.rect(self.screen, _bg("clock"), pygame.Rect(clock_x, 5, clock_w, clock_h))
            clock_img = self.font_clock.render(time_text, True, WHITE_BG)
            self.screen.blit(clock_img, (clock_x, 0))


# =============================================================================
# Furigana Display (FURIGANA mode)
# =============================================================================


class FuriganaDisplay(JapaneseDisplay):
    """Upper LCD Furigana rendering for E235-1000.

    Inherits all draw methods from JapaneseDisplay — no rendering divergence
    today. Furigana-specific text translation happens upstream in
    UpperDisplay._get_*_display() before draw methods are called, so the
    glyph-rendering code is identical between KANJI and FURIGANA modes.

    Override individual draw_* methods here if/when furigana display
    actually diverges (e.g. ruby-text layout, different font, smaller pt
    for longer kana strings).
    """


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
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 27)
        self.font_suffix = pygame.font.Font("fonts/HelveticaNeue-Medium.otf", 20)

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Draw train type box."""
        with clip(self.screen, TRAIN_TYPE_RECT):
            box_x, box_y, box_w, box_h = 15, 8, 150, 31
            pygame.draw.rect(self.screen, _bg("train_type", default=WHITE_BG), pygame.Rect(box_x, box_y, box_w, box_h), 0, 2)
            draw_text_given_width(box_x, 10, box_w, self.font_type_bold, train_type, type_color, self.screen, collapse=True, script="latin")

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with 'for' label above."""
        with clip(self.screen, DEST_RECT):
            dest_box_x, dest_box_w = 15, 150
            for_y = 50

            # Per-region bg fill (DARK_BG / debug-grid tint).
            pygame.draw.rect(self.screen, _bg("dest"), DEST_RECT)

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
        with clip(self.screen, PREFIX_RECT):
            pygame.draw.rect(self.screen, _bg("prefix"), PREFIX_RECT)
            prefix_x, prefix_y = int(S_WIDTH * 0.25) + 40, 5
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

        with clip(self.screen, STATION_RECT):
            # --- Station layout params ---
            name_x             = int(S_WIDTH * 0.40) + 10
            max_width          = int(S_WIDTH * 0.54 - 10)
            # 2-line (used when station_text contains "\n"):
            line_pitch_offset  = 0    # px adjustment to ascent-based pitch (-ve = even tighter, +ve = looser)
            # -----------------------------

            # Single bg fill for the whole station territory. Clip enforces the
            # confinement guarantee — any glyph pixel that would land above
            # STATION_RECT.top (y=35) is dropped at the pygame layer, so the
            # earlier clamped-clear-rect dance is no longer needed.
            pygame.draw.rect(self.screen, _bg("station"), STATION_RECT)

            if "\n" in station_text:
                line1, line2 = station_text.split("\n", 1)
                font = self.font_station_2line
                font_h = font.get_height()
                # Line pitch = ascent: line 2's top sits at line 1's baseline → tight
                # stacking with no descender gap. Tune via line_pitch_offset.
                line_pitch = font.get_ascent() + line_pitch_offset
                total_h = line_pitch + font_h
                top_y = UPPER_HEIGHT - total_h

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

            draw_text_given_width(name_x, name_y, max_width, self.font_station, station_text, WHITE_BG, self.screen, collapse=True, script="latin")

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        with clip(self.screen, CLOCK_RECT):
            clock_x, clock_w, clock_h = S_WIDTH - 170, 80, 25
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

    def __init__(self, screen, route_data, stops, audio=None):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        # Live audio ref (optional). Used by the yellow PA hint to suppress
        # flashing while pa[0] (prev-stop dep) is still auto-playing in
        # APPROACHING_EARLY — the user can't act yet, so flashing is noise.
        self.audio = audio
        self.prefix_text = "ただいま"
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_pa_at_station = -1
        self.at_station = True  # boots in STOPPING (matches AppState default)

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
        """Get current destination. Loader fills ``dest`` on every stop via
        sticky-override closure (``route_loader.finalize_route``); this is
        a direct read, no fallback logic. Route-level ``self.dest`` is the
        backstop only for ``curr_stop`` out of range."""
        if self.stops and 0 <= self.curr_stop < len(self.stops):
            return self.stops[self.curr_stop]["dest"]
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

        Drawing logic lives in `displays.utils.draw_station_code_badge` —
        shared with the lower-LCD 8-station view's per-cell badges.
        """
        if not self.stops or self.curr_stop >= len(self.stops):
            return
        sta_code = self.stops[self.curr_stop].get("sta_code")
        if not sta_code:
            return

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

        # Clip to BADGE_RECT — covers the framed 68×68 square AND the optional
        # code_3 12-px top band (rect is sized to the maximum extent at module
        # top so the band is never amputated when present).
        with clip(self.screen, BADGE_RECT):
            draw_station_code_badge(
                self.screen,
                badge_x,
                badge_y,
                badge_w,
                badge_h,
                sta_code,
                self.color,
                self.font_sta_code_prefix,
                self.font_sta_code_num,
                code_3=code_3,
                font_code_3=self.font_sta_code_3letter,
                ring_black=ring_black,
                ring_color=ring_color,
                outer_radius=outer_radius,
                color_radius=color_radius,
                interior_radius=interior_radius,
                text_gap=text_gap,
                prefix_x_offset=prefix_x_offset,
                code_3_band_h=code_3_band_h,
                code_3_x_offset=code_3_x_offset,
                code_3_y_offset=code_3_y_offset,
            )

    def set_state(self, curr_stop: int, cnt_pa: int, at_station: bool = False, cnt_pa_at_station: int = -1) -> None:
        """Update display state (current stop, PA count, STOPPING flag).

        Prefix mapping:
            at_station=True              -> "ただいま" (at the platform)
            cnt_pa == len(pa) - 1        -> "まもなく" (final approach PA played)
            otherwise (cnt_pa < last)    -> "次は"     (heading toward this stop)

        The "final approach PA" rule generalizes cleanly to 3+ approach PAs:
        only the LAST entry in pa[] flips the prefix to まもなく; intermediate
        approach announcements stay on 次は. For today's 2-PA data
        (pa = [{prev}-dep, {this}-arr]) this is identical to the previous
        ``cnt_pa >= 1 → まもなく`` mapping.

        ``at_station=True`` is the ONLY path to "ただいま" — the old
        ``cnt_pa >= 2`` fallback was a pre-migration hack for at-platform
        announcements that have since moved to ``pa_at_station``. Reviving it
        would re-introduce the wrong-stop ambiguity (display says "ただいま X"
        but the pa[2+] audio actually refers to the previous stop's platform).
        """
        self.curr_stop = curr_stop
        self.cnt_pa = cnt_pa
        self.at_station = at_station
        self.cnt_pa_at_station = cnt_pa_at_station

        pa = self.stops[curr_stop].get("pa", []) if 0 <= curr_stop < len(self.stops) else []
        is_final_approach_pa = len(pa) >= 1 and cnt_pa == len(pa) - 1

        if at_station:
            self.prefix_text = "ただいま"
        elif is_final_approach_pa:
            self.prefix_text = "まもなく"
        else:
            self.prefix_text = "次は"

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
            stop = self.stops[self.curr_stop]
            # Yellow hint = "more press(es) yields more PA at this stop." Square
            # blinks at 1 Hz while extras remain unplayed; once the last extra
            # has been started (acknowledged), the square disappears entirely.
            #   APPROACHING: extras are pa[1..] (pa[0] auto-fires). Flash while
            #     cnt_pa < len(pa)-1.
            #   STOPPING: extras are pa_at_station[0..] (cnt starts at -1).
            #     Flash while cnt_pa_at_station < len(pa_at_station)-1.
            if self.at_station:
                pa_at_st = stop.get("pa_at_station", [])
                show_yellow = len(pa_at_st) > 0 and self.cnt_pa_at_station < len(pa_at_st) - 1
            else:
                pa_list = stop.get("pa", [])
                # APPROACHING_EARLY only: suppress flash while audio is still
                # auto/just-played. Floor passes to the user only when the
                # current PA finishes, so flashing earlier is misleading nag.
                audio_busy = self.audio is not None and self.audio.is_pa_playing()
                show_yellow = (
                    len(pa_list) > 1
                    and self.cnt_pa < len(pa_list) - 1
                    and not audio_busy
                )
            if show_yellow:
                on = (pygame.time.get_ticks() // 500) % 2 == 0
                color = (247, 225, 158) if on else _bg("pa_hint")
            else:
                color = _bg("pa_hint")
            with clip(self.screen, PA_HINT_RECT):
                pygame.draw.rect(self.screen, color, PA_HINT_RECT)

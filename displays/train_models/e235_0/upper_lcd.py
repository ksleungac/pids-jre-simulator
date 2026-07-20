"""E235-0 series Upper LCD display implementation.

Contains all display modes (Japanese, Furigana, English) for the
E235-0 series Upper LCD. Forked from E235-1000 with the train-type
cell removed — Yamanote runs a single service type, so IRL PIDS
doesn't render one. The 150×31 top-left area that previously held
the train-type box is now plain DARK_BG; no other elements reflow.
"""

import pygame
import time

from app_paths import load_json_relative, project_root
from displays.base import DisplayMode, ModeCycler
from displays.utils import clip, draw_text_given_width, draw_station_code_badge

# =============================================================================
# Region Map — E235-0 upper LCD layout (descriptive)
#
# CONTRACT: each region's draw method clips to its rect (see manifest below
# this comment block: DEST_RECT, PREFIX_RECT, STATION_RECT, CLOCK_RECT,
# BADGE_RECT, PA_HINT_RECT). The clip is a hard guarantee — pixels drawn
# outside the rect are dropped by pygame. See DISPLAY_E235.md § "Element
# confinement (clip-enforced)" for the rationale and gotchas.
#
# Coordinates are within the upper LCD area (y=0..UPPER_HEIGHT=130).
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
# dest         *Display.draw_destination   DEST_RECT           red
# prefix       *Display.draw_prefix        PREFIX_RECT         blue
# clock        *Display.draw_clock         CLOCK_RECT          yellow
# station      *Display.draw_station       STATION_RECT        purple
# pa_hint      UpperDisplay.draw           PA_HINT_RECT        orange (blinks yellow @ 1 Hz)
# badge        _draw_station_code_badge    BADGE_RECT          — (route color; rect spans optional code_3 top band)
# =============================================================================


# =============================================================================
# Per-model dimensions / palette — single source of truth lives in this
# model's package __init__.py (so app.py reads the same values without one
# LCD module being "the boss" over the other).
# =============================================================================

from displays.train_models.e235_0 import (
    S_WIDTH,
    UPPER_HEIGHT,
    DARK_BG,
    WHITE_BG,
)

# Cached pygame.font.Font factory. Used by draw methods that pull their font
# size from a tuneable dict — pygame.font.Font constructs are not free at 15
# FPS so cache by (filename, size). Lazy: never called at module load (pygame
# may not be initialized yet); only inside draw methods.
_font_cache: dict = {}


def _font(filename: str, size: int) -> pygame.font.Font:
    key = (filename, size)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.Font(str(project_root() / "fonts" / filename), size)
    return _font_cache[key]


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

DEST_RECT = pygame.Rect(0, 50, 180, UPPER_HEIGHT - 50)
# Prefix rect derived from tuneable — see Region rect tuneability pattern in
# WIP_calibration_editor.md. draw_prefix syncs PREFIX_RECT from this dict
# each frame.
_TUNEABLES_PREFIX_RECT = {
    "prefix_x": 220,
    "prefix_y": 3,
    "prefix_w": 220,
    "prefix_h": 28,
}
PREFIX_RECT = pygame.Rect(
    _TUNEABLES_PREFIX_RECT["prefix_x"],
    _TUNEABLES_PREFIX_RECT["prefix_y"],
    _TUNEABLES_PREFIX_RECT["prefix_w"],
    _TUNEABLES_PREFIX_RECT["prefix_h"],
)
_TUNEABLES_STATION_RECT = {
    "station_x": 302,
    "station_y": 41,
    "station_w": 384,
    "station_h": 91,
}
STATION_RECT = pygame.Rect(
    _TUNEABLES_STATION_RECT["station_x"],
    _TUNEABLES_STATION_RECT["station_y"],
    _TUNEABLES_STATION_RECT["station_w"],
    _TUNEABLES_STATION_RECT["station_h"],
)
# Clock blits at `CLOCK_RECT.top + text_y` (text_y may be negative — see
# _TUNEABLES_CLOCK); the rect's height absorbs the surface ascender so clip
# never amputates the visible glyph caps.
#
# Region rect derived from tuneable so the calibration editor can nudge
# position/size in-app. draw_clock syncs CLOCK_RECT from this dict each frame.
# Pattern pioneer for region-level tuneability — broadcast to PREFIX_RECT /
# STATION_RECT 2026-05-14; BADGE_RECT / PA_HINT_RECT 2026-06-23.
# See WIP_calibration_editor.md § "Region-level tuneability pattern".
_TUNEABLES_CLOCK_RECT = {
    "clock_x": 573,
    "clock_y": 0,
    "clock_w": 75,
    "clock_h": 28,
}
CLOCK_RECT = pygame.Rect(
    _TUNEABLES_CLOCK_RECT["clock_x"],
    _TUNEABLES_CLOCK_RECT["clock_y"],
    _TUNEABLES_CLOCK_RECT["clock_w"],
    _TUNEABLES_CLOCK_RECT["clock_h"],
)
# Badge spans both the framed 68×68 square AND the optional code_3 top band
# (12 px upward extension when present). Sized to the maximum (with-band)
# extent so clip never amputates the band when code_3 is set. Region rect
# derived from tuneable; _draw_station_code_badge syncs BADGE_RECT each frame
# and reads badge_x/badge_w from it (framed square height = badge_h minus the
# code_3 band). See § "Region-level tuneability pattern".
_TUNEABLES_BADGE_RECT = {
    "badge_x": 222,
    "badge_y": 50,
    "badge_w": 68,
    "badge_h": 80,
}
BADGE_RECT = pygame.Rect(
    _TUNEABLES_BADGE_RECT["badge_x"],
    _TUNEABLES_BADGE_RECT["badge_y"],
    _TUNEABLES_BADGE_RECT["badge_w"],
    _TUNEABLES_BADGE_RECT["badge_h"],
)
# PA-hint square (yellow blink = more PA available). draw() syncs each frame.
_TUNEABLES_PA_HINT_RECT = {
    "pa_hint_x": 710,
    "pa_hint_y": 110,
    "pa_hint_w": 20,
    "pa_hint_h": 20,
}
PA_HINT_RECT = pygame.Rect(
    _TUNEABLES_PA_HINT_RECT["pa_hint_x"],
    _TUNEABLES_PA_HINT_RECT["pa_hint_y"],
    _TUNEABLES_PA_HINT_RECT["pa_hint_w"],
    _TUNEABLES_PA_HINT_RECT["pa_hint_h"],
)


# =============================================================================
# Debug grid — makes region clear-rects visible by tinting their backgrounds.
# Each draw method paints its DARK_BG clear via _bg("<region>") so flipping
# DEBUG_GRID swaps every region's bg to a unique tint. Use to:
#   - Spot clear-rect overlaps (one region's tint bleeds into another's bounds)
#   - Spot under-cleared zones (dark untinted patches inside a region that
#     should be fully painted)
#   - Spot clipping (text/glyphs cut off at the boundary of a tinted region)
# The dict literal also serves as the lightweight region manifest for upper
# E235-0 — keys here are the region names referenced in draw methods.
# =============================================================================

DEBUG_GRID: bool = False  # flipped by preview_display.py --debug-grid

_DEBUG_COLORS = {
    "upper_bg": (80, 80, 80),  # neutral gray — baseline "no region claimed this pixel"
    "dest": (180, 40, 40),  # bright red
    "prefix": (40, 80, 200),  # bright blue
    "clock": (200, 170, 30),  # bright yellow
    "station": (140, 40, 170),  # bright magenta/purple
    "pa_hint": (220, 110, 0),  # bright orange
}


def _bg(region: str):
    """Return the region's normal background color, or its debug tint when DEBUG_GRID is on.

    All regions in E235-0 clear to DARK_BG — the train-type cell (which used
    WHITE_BG in E235-1000) is omitted. Region keys must match _DEBUG_COLORS;
    adding a new region means adding it here too, keeping the manifest in sync
    with the draw code by construction.
    """
    if DEBUG_GRID:
        return _DEBUG_COLORS.get(region, DARK_BG)
    return DARK_BG


# =============================================================================
# Japanese Display (KANJI mode)
# =============================================================================


# Tuneable params for KANJI destination rendering. Read by
# JapaneseDisplay.draw_destination at render time; mutated by the calibration
# editor (see WIP_calibration_editor.md). Inherited unchanged by FuriganaDisplay.
_TUNEABLES_DEST_KANJI = {
    "dest_box_x": 6,
    "dest_box_y": 62,
    "dest_box_w": 167,
    "suffix_right_offset": 10,
    "suffix_bottom_margin": 5,
    "font_dest_size": 35,
    "font_suffix_size": 18,
}


# Tuneable params for clock rendering. Shared across all modes (JA / FU / EN)
# since clock visuals don't depend on language family. Read by both
# JapaneseDisplay.draw_clock and EnglishDisplay.draw_clock.
_TUNEABLES_CLOCK = {
    "text_y": -3,
    "font_size": 31,
}


# Tuneable params for KANJI prefix rendering. Read by
# JapaneseDisplay.draw_prefix. Inherited unchanged by FuriganaDisplay.
_TUNEABLES_PREFIX_KANJI = {
    "text_y": 0,
    "font_size": 26,
}


# Tuneable params for KANJI station rendering. Read by
# JapaneseDisplay.draw_station. Inherited unchanged by FuriganaDisplay.
_TUNEABLES_STATION_KANJI = {
    "text_bottom_margin": 5,
    "font_size": 84,
}


# Prefix translations — canonical enumeration of the 3 state-machine prefix
# strings (set in UpperDisplay.set_state per app state). Module-level so the
# calibration editor reads candidates directly from here, not duplicated.
# Keys are the KANJI prefix strings; values are mode-specific translations.
_PREFIX_FURIGANA = {
    "次は": "つぎは",
    "まもなく": "まもなく",
    "ただいま": "ただいま",
}
_PREFIX_ENGLISH = {
    "次は": "Next",
    "まもなく": "Arriving at",
    "ただいま": "Now stopping at",
}


class JapaneseDisplay:
    """Upper LCD Japanese (KANJI) rendering for E235-0."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # CONTRACT: load fonts from file paths only — never `pygame.font.SysFont()`.
        # SysFont scans the Windows font registry, which fails on Chinese/Japanese
        # locale Windows with `TypeError: expected str, bytes or os.PathLike object,
        # not int`. All fonts in this project ship in fonts/ and load via Font(path).
        # font_prefix / font_station / font_dest / font_suffix / font_clock
        # loaded lazily via _font() in their respective draw methods so sizes
        # can be tuned via _TUNEABLES_PREFIX_KANJI / _TUNEABLES_STATION_KANJI /
        # _TUNEABLES_DEST_KANJI / _TUNEABLES_CLOCK at runtime.

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with suffix (ゆき/方面)."""
        t = _TUNEABLES_DEST_KANJI
        font_dest = _font("ShinGoPr6N-Medium.otf", t["font_dest_size"])
        font_suffix = _font("ShinGoPr6N-Medium.otf", t["font_suffix_size"])
        with clip(self.screen, DEST_RECT):
            # Per-region bg fill (DARK_BG / debug-grid tint).
            pygame.draw.rect(self.screen, _bg("dest"), DEST_RECT)

            draw_text_given_width(
                t["dest_box_x"], t["dest_box_y"], t["dest_box_w"], font_dest, dest_text, WHITE_BG, self.screen, collapse=False, script="japanese"
            )

            suffix = "方面" if route_name == "山手線" else "ゆき"
            t_w, t_h = font_suffix.size(suffix)
            suffix_x = int(S_WIDTH * 0.25) - t_w - t["suffix_right_offset"]
            suffix_y = UPPER_HEIGHT - t_h - t["suffix_bottom_margin"]
            suffix_img = font_suffix.render(suffix, True, WHITE_BG, _bg("dest"))
            self.screen.blit(suffix_img, (suffix_x, suffix_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw prefix (次は/まもなく/ただいま)."""
        tr = _TUNEABLES_PREFIX_RECT
        PREFIX_RECT.update(tr["prefix_x"], tr["prefix_y"], tr["prefix_w"], tr["prefix_h"])
        t = _TUNEABLES_PREFIX_KANJI
        font_prefix = _font("ShinGoPr6N-Medium.otf", t["font_size"])
        with clip(self.screen, PREFIX_RECT):
            pygame.draw.rect(self.screen, _bg("prefix"), PREFIX_RECT)
            prefix_img = font_prefix.render(prefix_text, True, WHITE_BG)
            self.screen.blit(prefix_img, (PREFIX_RECT.left, PREFIX_RECT.top + t["text_y"]))

    def draw_station(self, station_text: str) -> None:
        """Draw station name with even character spacing."""
        if not station_text:
            return

        tr = _TUNEABLES_STATION_RECT
        STATION_RECT.update(tr["station_x"], tr["station_y"], tr["station_w"], tr["station_h"])
        t = _TUNEABLES_STATION_KANJI
        font_station = _font("ShinGoPr6N-Medium.otf", t["font_size"])
        with clip(self.screen, STATION_RECT):
            _, name_h = font_station.size(station_text)
            name_y = STATION_RECT.bottom - name_h - t["text_bottom_margin"]

            # Clip handles the confinement guarantee — any glyph pixel that
            # would land above STATION_RECT.top is dropped at the pygame
            # layer. The bg fill is sized to the full STATION_RECT so the
            # debug-grid tint shows the entire territory.
            pygame.draw.rect(self.screen, _bg("station"), STATION_RECT)

            draw_text_given_width(
                STATION_RECT.left,
                name_y,
                STATION_RECT.width,
                font_station,
                station_text,
                WHITE_BG,
                self.screen,
                collapse=False,
                script="japanese",
            )

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        tr = _TUNEABLES_CLOCK_RECT
        CLOCK_RECT.update(tr["clock_x"], tr["clock_y"], tr["clock_w"], tr["clock_h"])
        t = _TUNEABLES_CLOCK
        font_clock = _font("HelveticaNeue-Roman.otf", t["font_size"])
        with clip(self.screen, CLOCK_RECT):
            pygame.draw.rect(self.screen, _bg("clock"), CLOCK_RECT)
            clock_img = font_clock.render(time_text, True, WHITE_BG)
            self.screen.blit(clock_img, (CLOCK_RECT.left, CLOCK_RECT.top + t["text_y"]))


# =============================================================================
# Furigana Display (FURIGANA mode)
# =============================================================================


class FuriganaDisplay(JapaneseDisplay):
    """Upper LCD Furigana rendering for E235-0.

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


# Tuneable params for ENGLISH destination rendering. Read by
# EnglishDisplay.draw_destination at render time; mutated by the calibration
# editor (see WIP_calibration_editor.md).
_TUNEABLES_DEST_ENGLISH = {
    "for_x": 10,
    "for_y": 50,
    "for_color": (182, 182, 199),
    "two_line_x": 10,
    "two_line_top_pad": 5,
    "two_line_max_w": 170,
    "single_x": 10,
    "single_max_w": 170,
    "single_y_offset": 10,
    "font_dest_size": 24,
    "font_suffix_size": 20,
}


# Tuneable params for ENGLISH prefix rendering. Read by EnglishDisplay.draw_prefix.
_TUNEABLES_PREFIX_ENGLISH = {
    "text_y": 0,
    "font_size": 28,
}


# Tuneable params for ENGLISH station rendering. Read by EnglishDisplay.draw_station.
# `line_pitch_offset` only fires when station_text contains \n (2-line variant).
_TUNEABLES_STATION_ENGLISH = {
    "text_bottom_margin": 0,
    "line_pitch_offset": 0,
    "font_size": 75,
    "font_2line_size": 42,
}


class EnglishDisplay:
    """Upper LCD English rendering for E235-0."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # font_prefix / font_station / font_station_2line / font_dest /
        # font_suffix / font_clock loaded lazily via _font() in their
        # respective draw methods so sizes can be tuned via
        # _TUNEABLES_PREFIX_ENGLISH / _TUNEABLES_STATION_ENGLISH /
        # _TUNEABLES_DEST_ENGLISH / _TUNEABLES_CLOCK at runtime.

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """Draw destination with 'for' label above."""
        t = _TUNEABLES_DEST_ENGLISH
        font_dest = _font("HelveticaNeue-Medium.otf", t["font_dest_size"])
        font_suffix = _font("HelveticaNeue-Medium.otf", t["font_suffix_size"])
        with clip(self.screen, DEST_RECT):
            for_y = t["for_y"]

            # Per-region bg fill (DARK_BG / debug-grid tint).
            pygame.draw.rect(self.screen, _bg("dest"), DEST_RECT)

            # Draw "for" label
            for_img = font_suffix.render("for", True, t["for_color"], _bg("dest"))
            self.screen.blit(for_img, (t["for_x"], for_y))

            # Draw destination name
            _, for_h = font_suffix.size("for")
            if "\n" in dest_text:
                # 2-line: lines left-aligned with "for", breathing room below
                # "for". Uses full-height pitch (font.get_height()) for natural
                # inter-line spacing — *not* ascent-pitch (that's the station
                # renderer's tighter stacking). Inter-line gap matters here because
                # line 1 may contain descenders ("p" of "Airport", "g" of "Shinagawa")
                # that would collide with line 2's caps under ascent-pitch.
                visible_for_bottom = for_y + font_suffix.get_ascent()
                top_y = visible_for_bottom + t["two_line_top_pad"]
                line_pitch = font_dest.get_height()  # full-height pitch — natural inter-line gap
                lines = dest_text.split("\n")
                for i, line in enumerate(lines):
                    y_pos = top_y + i * line_pitch
                    img = font_dest.render(line, True, WHITE_BG)
                    w = img.get_width()
                    if w > t["two_line_max_w"]:
                        img = pygame.transform.smoothscale(img, (t["two_line_max_w"], img.get_height()))
                    self.screen.blit(img, (t["two_line_x"], y_pos))
            else:
                # Single line: LEFT-aligned (mirrors the 2-line branch so single-
                # and 2-line renders share a left edge). Vertically centered
                # between "for" bottom and UPPER_HEIGHT, minus single_y_offset.
                # Smoothscale fallback if natural width exceeds the dest region —
                # same defensive shrink the 2-line branch uses.
                dest_h = font_dest.get_height()
                zone_top = for_y + for_h
                single_y = zone_top + (UPPER_HEIGHT - zone_top - dest_h) // 2 - t["single_y_offset"]
                img = font_dest.render(dest_text, True, WHITE_BG)
                w = img.get_width()
                if w > t["single_max_w"]:
                    img = pygame.transform.smoothscale(img, (t["single_max_w"], img.get_height()))
                self.screen.blit(img, (t["single_x"], single_y))

    def draw_prefix(self, prefix_text: str) -> None:
        """Draw English prefix (already translated by UpperDisplay manager)."""
        tr = _TUNEABLES_PREFIX_RECT
        PREFIX_RECT.update(tr["prefix_x"], tr["prefix_y"], tr["prefix_w"], tr["prefix_h"])
        t = _TUNEABLES_PREFIX_ENGLISH
        font_prefix = _font("HelveticaNeue-Medium.otf", t["font_size"])
        with clip(self.screen, PREFIX_RECT):
            pygame.draw.rect(self.screen, _bg("prefix"), PREFIX_RECT)
            prefix_img = font_prefix.render(prefix_text, True, WHITE_BG)
            self.screen.blit(prefix_img, (PREFIX_RECT.left, PREFIX_RECT.top + t["text_y"]))

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

        tr = _TUNEABLES_STATION_RECT
        STATION_RECT.update(tr["station_x"], tr["station_y"], tr["station_w"], tr["station_h"])
        t = _TUNEABLES_STATION_ENGLISH
        font_station = _font("HelveticaNeue-Bold.otf", t["font_size"])
        font_station_2line = _font("HelveticaNeue-Bold.otf", t["font_2line_size"])
        name_x = STATION_RECT.left
        max_width = STATION_RECT.width
        with clip(self.screen, STATION_RECT):
            # Single bg fill for the whole station territory. Clip enforces the
            # confinement guarantee — any glyph pixel that would land above
            # STATION_RECT.top is dropped at the pygame layer.
            pygame.draw.rect(self.screen, _bg("station"), STATION_RECT)

            if "\n" in station_text:
                line1, line2 = station_text.split("\n", 1)
                font = font_station_2line
                font_h = font.get_height()
                # Line pitch = ascent: line 2's top sits at line 1's baseline → tight
                # stacking with no descender gap. Tune via line_pitch_offset.
                line_pitch = font.get_ascent() + t["line_pitch_offset"]
                total_h = line_pitch + font_h
                top_y = STATION_RECT.bottom - total_h - t["text_bottom_margin"]

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

            _, name_h = font_station.size(station_text)
            name_y = STATION_RECT.bottom - name_h - t["text_bottom_margin"]

            draw_text_given_width(name_x, name_y, max_width, font_station, station_text, WHITE_BG, self.screen, collapse=True, script="latin")

    def draw_clock(self, time_text: str) -> None:
        """Draw clock."""
        tr = _TUNEABLES_CLOCK_RECT
        CLOCK_RECT.update(tr["clock_x"], tr["clock_y"], tr["clock_w"], tr["clock_h"])
        t = _TUNEABLES_CLOCK
        font_clock = _font("HelveticaNeue-Roman.otf", t["font_size"])
        with clip(self.screen, CLOCK_RECT):
            pygame.draw.rect(self.screen, _bg("clock"), CLOCK_RECT)
            clock_img = font_clock.render(time_text, True, WHITE_BG)
            self.screen.blit(clock_img, (CLOCK_RECT.left, CLOCK_RECT.top + t["text_y"]))


# =============================================================================
# Upper Display Manager
# =============================================================================


class UpperDisplay:
    """
    E235-0 Upper LCD manager.

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
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])

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

        # Badge typeface is fixed inside draw_station_code_badge (Frutiger);
        # point sizes live in the _draw_station_code_badge params block.

        # Load translations (station names, destinations)
        self.translations = load_json_relative("data/translations.json")

        # Load station metadata (3-letter codes, future fields)
        self.stations = load_json_relative("data/stations.json")

        # Prefix translations live in module-level _PREFIX_FURIGANA /
        # _PREFIX_ENGLISH constants (above) — single source of truth so the
        # calibration editor's prefix cycler reads canonical candidates.

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

    def _get_prefix_display(self) -> str:
        """Get prefix text based on current display mode."""
        mode = self.mode_cycler.get_current_mode()

        if mode == DisplayMode.ENGLISH:
            return _PREFIX_ENGLISH.get(self.prefix_text, self.prefix_text)

        if mode == DisplayMode.FURIGANA:
            return _PREFIX_FURIGANA.get(self.prefix_text, self.prefix_text)

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
        """Draw station code badge (e.g. JY03) between color ribbon and station name.

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

        tr = _TUNEABLES_BADGE_RECT
        BADGE_RECT.update(tr["badge_x"], tr["badge_y"], tr["badge_w"], tr["badge_h"])

        # fmt: off
        # --- Badge params (adjust freely; badge_x / badge_w / badge_h come from
        #     _TUNEABLES_BADGE_RECT below — nudge badge position/size in editor) ---
        prefix_size = 18  # "JY" letters pt (face fixed to Frutiger in draw_station_code_badge)
        num_size = 22  # station-number pt
        code_3_size = 20  # 3-letter interchange-code pt
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
        # -------------------------------------
        # fmt: on

        badge_x = BADGE_RECT.x  # synced from _TUNEABLES_BADGE_RECT
        badge_w = BADGE_RECT.width
        badge_h = BADGE_RECT.height - code_3_band_h  # framed square = rect minus code_3 band
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
                prefix_size=prefix_size,
                num_size=num_size,
                code_3=code_3,
                code_3_size=code_3_size,
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
                show_yellow = len(pa_list) > 1 and self.cnt_pa < len(pa_list) - 1 and not audio_busy
            if show_yellow:
                on = (pygame.time.get_ticks() // 500) % 2 == 0
                color = (247, 225, 158) if on else _bg("pa_hint")
            else:
                color = _bg("pa_hint")
            tr = _TUNEABLES_PA_HINT_RECT
            PA_HINT_RECT.update(tr["pa_hint_x"], tr["pa_hint_y"], tr["pa_hint_w"], tr["pa_hint_h"])
            with clip(self.screen, PA_HINT_RECT):
                pygame.draw.rect(self.screen, color, PA_HINT_RECT)

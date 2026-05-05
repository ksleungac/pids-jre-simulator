"""Shared rendering utilities for display system.

Contains both generic pygame primitives (text, polygons, chevron-arrow
geometry, vertical column text) and display-domain helpers (badges,
continuity indicators, route-map disclaimer). Single home for the
display package — every train-model module imports from here.
"""

import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple

import pygame


BADGE_TEXT = (15, 15, 15)  # dark — text sits on white interior
WHITE_BG = (230, 230, 230)


# CONTRACT: Resolve the repo root for asset loading in dev AND PyInstaller frozen builds.
# In a frozen exe, __file__ points under sys._MEIPASS (NOT next to the user's exe where
# bundled data/audio/fonts live), so we must branch on sys.frozen — see
# displays/train_models/e235_1000/upper_lcd.py:get_base_dir for the original incident
# and CLAUDE.md § "Distribution & deployment artifact" for why silent-fail is the worst case.
def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # displays/utils.py → repo root (2-parent climb).
    return Path(__file__).resolve().parent.parent


# =============================================================================
# Generic pygame primitives
# =============================================================================


@contextmanager
def clip(surface: pygame.Surface, rect):
    """Restrict drawing to ``rect`` for the duration of the with-block.

    Pixels drawn outside ``rect`` are silently dropped at the pygame layer —
    a hard guarantee that a region's draw cannot bleed into a neighbouring
    region's territory. Pairs with the per-region rect manifest at the top
    of each train-model's LCD module.

    Restores the previous clip rect on exit (nested clips work correctly).
    """
    old = surface.get_clip()
    surface.set_clip(rect)
    try:
        yield
    finally:
        surface.set_clip(old)


def draw_aapolygon(
    surface: pygame.Surface,
    color: Tuple[int, int, int],
    points: List[Tuple[float, float]],
    scale: int = 2,
    width: int = 0,
) -> None:
    """Draw antialiased polygon using supersampling.

    Args:
        surface: Pygame surface to draw on
        color: RGB color tuple
        points: List of (x, y) tuples defining the polygon
        scale: Supersampling scale factor
        width: Line width (0 for filled polygon)
    """
    x_coords = tuple(int(x) for x, _ in points)
    y_coords = tuple(int(y) for _, y in points)
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    w = x_max - x_min + 1
    h = y_max - y_min + 1

    s = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA, surface)
    s.fill((255, 255, 255, 0))
    s_points = [((int(x) - x_min) * scale, (int(y) - y_min) * scale) for x, y in points]
    pygame.draw.polygon(s, color, s_points, width)
    s2 = pygame.transform.smoothscale(s, (w, h))
    surface.blit(s2, (x_min, y_min))


def arrow_points(x: int, y: int, w: int, h: int, stroke: int) -> Tuple[Tuple[float, float], ...]:
    """Generate a 6-point chevron-arrow polygon (right-pointing).

    The result describes a horizontally-pointing chevron: a thick "<" with
    the tip at (x + w, y + h/2) and a notch carved into its left edge at
    (x + w - stroke, y + h/2). The notch makes the shape readable as an
    arrow rather than a triangle — the deeper the notch, the more the
    chevron looks like an arrowhead-with-tail.

    Geometry knobs:
        w  — total width (left edge to tip).
        h  — total height (top edge to bottom edge).
        stroke — chevron BODY THICKNESS, **not** a typical line stroke.
            Geometrically, `stroke` is the horizontal distance from the
            outer-left edge of the body to where the slanted side begins
            (and equivalently from the notch vertex to the tip).
            - stroke == w / 2: notch is exactly centered → "fat" chevron,
              equal-width body and tip portions.
            - stroke ~ w * 0.55: full-route-pointer ratio; body slightly
              wider than the tip portion.
            - small stroke (e.g. w * 0.3): pointier, longer-tip arrow.
            - stroke == w: degenerates to a thin line (no inside).
            - stroke == 0: pure right-pointing triangle (no notch).

    Scaling tips: to make the chevron larger WITHOUT changing its shape,
    scale `w`, `h`, and `stroke` by the same factor. Bumping only `w`
    makes the tip protrude → the chevron looks pointier even though it
    got "bigger".

    **Drawing a chevron with a uniform halo (filled inner + outline outer).**
    Common pattern: render an inner filled chevron in the foreground color,
    then a slightly larger outer chevron as an outline (`draw_aapolygon`
    with `width > 0`) for a halo behind it. For the halo to read as the
    same thickness along the body AND the tip, the outer's tip-length
    must equal the inner's tip-length, i.e.
        outer_w - outer_stroke == inner_w - inner_stroke
    The simplest way to achieve this — and to keep the halo uniform on
    every side — is:
        delta = halo width  # halo thickness in px
        outer_w      = inner_w      + delta
        outer_stroke = inner_stroke + delta
        outer_x      = inner_x - delta // 2  # centers outer around inner
    A common pitfall: scaling `outer_w` by some delta but using a fixed
    `outer_stroke` (or scaling stroke by a different delta). The body
    halo will look right but the tip halo will read as a different
    thickness — visible as the outline being more or less pointy than
    the inner fill.

    Args:
        x, y: Top-left of the chevron's bounding box.
        w, h: Bounding-box width and height.
        stroke: Body thickness — see notes above.

    Returns:
        Tuple of 6 (x, y) points suitable for `draw_aapolygon` (filled
        polygon when `width=0`, outline-only chevron when `width>0`).
    """
    return ((x, y), (x + w - stroke, y + h / 2), (x, y + h), (x + stroke, y + h), (x + w, y + h / 2), (x + stroke, y))


def draw_1col_text(
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    vert_space: int,
    text_color: Tuple[int, int, int],
    screen: pygame.Surface,
) -> None:
    """Draw text vertically (one column).

    Per-character horizontal centering: narrow glyphs (digits, katakana like
    ビル) are centered relative to the widest character's column width so
    mixed strings like "空港第2ビル" don't have stragglers off to the left.

    Args:
        font: Pygame font object
        text: Text to draw vertically
        x: X position (left edge of the column for the WIDEST char)
        y: Y position (bottom of the column)
        vert_space: Vertical space to fill
        text_color: RGB color tuple
        screen: Pygame surface to draw on
    """
    _, t_h = font.size(text)
    length = len(text)

    if length <= 0:
        return

    # Handle division by zero
    vert_dist = (vert_space - t_h) / (length - 1) if length > 1 else 20
    vr = 1.0

    if length * t_h > vert_space:
        vr = vert_space / (length * t_h)
        vert_dist = vert_dist + (t_h - (t_h * vr)) / (length - 1) if length > 1 else vert_dist

    char_widths = [font.size(c)[0] for c in text]
    col_w = max(char_widths)

    for k, s in enumerate(text):
        y_pos = y - vert_space + vert_dist * k
        char_w = char_widths[k]
        x_pos = x + (col_w - char_w) // 2
        img = draw_text(s, font, text_color, int(x_pos), int(y_pos), v_ratio=vr)
        screen.blit(img, (int(x_pos), int(y_pos)))


def draw_stops_text(
    font: pygame.font.Font,
    stop_text: str,
    text_color: Tuple[int, int, int],
    x: int,
    y: int,
    stops_w: int,
    screen: pygame.Surface,
) -> None:
    """Draw station name text with support for multi-line stations.

    Args:
        font: Pygame font object
        stop_text: Station name (may contain space for line break)
        text_color: RGB color tuple
        x: X position
        y: Y position
        stops_w: Width of the station box
        screen: Pygame surface to draw on
    """
    t = stop_text.split()
    _, t_h = font.size(stop_text)
    w = stops_w

    if len(t) > 1:
        r_col_offset = 10
        offset = (w - t_h * 2) / 2
        draw_1col_text(font, t[0], int(x + offset + t_h), int(y - 6), 74, text_color, screen)
        draw_1col_text(font, t[1], int(x + offset), y, 80 - r_col_offset, text_color, screen)
    else:
        offset = (w - t_h) / 2
        if len(t[0]) == 1:
            draw_1col_text(font, t[0], int(x + offset), y, 48, text_color, screen)
        else:
            draw_1col_text(font, t[0], int(x + offset), y, 80, text_color, screen)


# =============================================================================
# Display-domain helpers
# =============================================================================


def draw_continuity_arrow(
    screen: pygame.Surface,
    x: int,
    y: int,
    h: int,
    color,
    *,
    n_chevrons: int = 3,
    chevron_w: int = 7,
    chevron_stroke: int = 4,
    chevron_gap: int = 0,
) -> int:
    """Stack of right-pointing chevrons signaling "route continues."

    Used at slots 0 / 2 (line-tail "to" indicator) and slot 1 (line-head
    "from" indicator) when the route has stops outside the visible display
    area. Chevrons render at the full bar height `h`. Returns total width
    consumed so callers can chain.
    """
    step = chevron_w + chevron_gap
    for i in range(n_chevrons):
        cx = x + i * step
        draw_aapolygon(
            screen,
            color,
            arrow_points(int(cx), int(y), chevron_w, h, chevron_stroke),
        )
    return n_chevrons * chevron_w + (n_chevrons - 1) * chevron_gap


def draw_continuity_triangle(
    screen: pygame.Surface,
    x: int,
    y: int,
    h: int,
    color,
    *,
    tri_w: int = 12,
) -> int:
    """Right-pointing triangle for slots 0 / 2 — bar tail (route continues).

    Used as the bar's tapered RIGHT tail (apex right, base on the left at the
    bar's right edge). (x, y) is the top-left of the triangle's bounding rect.
    Returns `tri_w`. (Slot 1's left-head notch is drawn inline in lower_lcd.py
    as a WHITE_BG triangle carved INTO the bar; it doesn't go through this
    helper.)
    """
    points = [
        (x, y),
        (x, y + h),
        (x + tri_w, y + h // 2),
    ]
    draw_aapolygon(screen, color, points)
    return tri_w


# Boilerplate route-map disclaimer — same text on both full-route and
# 8-station views, anchored bottom-right. Source: real PIDS reference.
ROUTE_DISCLAIMER = "のりかえ、待合せ時間は含まれません。電車により多少時間が異なります。一部区間では時間を表示しません。"


def draw_route_disclaimer(
    screen: pygame.Surface,
    font: pygame.font.Font,
    right_x: int,
    bottom_y: int,
    color,
) -> None:
    """Render the route-map disclaimer right- and bottom-anchored to (right_x, bottom_y)."""
    img = font.render(ROUTE_DISCLAIMER, True, color)
    w, h = img.get_size()
    screen.blit(img, (right_x - w, bottom_y - h))


def draw_station_code_badge(
    screen: pygame.Surface,
    x: int,
    y: int,
    w: int,
    h: int,
    sta_code: str,
    color,
    font_prefix: pygame.font.Font,
    font_num: pygame.font.Font,
    *,
    code_3: str = "",
    font_code_3: pygame.font.Font = None,
    text_color = BADGE_TEXT,
    ring_black: int = 7,
    ring_color: int = 7,
    outer_radius: int = 8,
    color_radius: int = 4,
    interior_radius: int = 0,
    text_gap: int = 3,
    text_y_offset: int = 0,
    prefix_x_offset: int = 1,
    code_3_band_h: int = 12,
    code_3_x_offset: int = 0,
    code_3_y_offset: int = 4,
) -> None:
    """Draw the framed station-code badge (e.g. JO25, JY03, or line-only "JO").

    The (x, y, w, h) rect describes the **framed JY/03 portion only** — the
    optional `code_3` 3-letter top band, when present, is drawn above the
    framed square (the outer black rect extends upward by `code_3_band_h`).

    Layered as: outer black → route-color ring → white interior → letters
    centered horizontally with `prefix_x_offset` nudge → number row below
    separated by `text_gap` (visible-pixel gap, measured via
    `get_bounding_rect`).

    `sta_code` may be letters+digits (`JY03`) or letters-only (`JY` — used
    by the route selection screen as a line marker without station number,
    in which case the letters are vertically centered with no number row).

    Returns silently if `sta_code` cannot be parsed into letters [+ digits].
    Used by upper-LCD (large badge with optional code_3 band), the lower-LCD
    8-station view (smaller per-cell badge, no code_3 band), and the setup
    screen (line-marker mode, letters only).
    """
    m = re.match(r"([A-Za-z]+)(\d*)", sta_code or "")
    if not m:
        return
    letters = m.group(1).upper()
    number = m.group(2)  # may be empty (line-marker mode)

    inset = ring_black + ring_color
    interior_x = x + inset
    interior_y = y + inset
    interior_w = w - 2 * inset
    interior_h = h - 2 * inset
    center_x = interior_x + interior_w // 2

    if code_3:
        outer_y = y - code_3_band_h
        outer_h = h + code_3_band_h
    else:
        outer_y = y
        outer_h = h

    pygame.draw.rect(screen, (0, 0, 0), pygame.Rect(x, outer_y, w, outer_h), 0, outer_radius)
    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(x + ring_black, y + ring_black, w - 2 * ring_black, h - 2 * ring_black),
        0,
        color_radius,
    )
    pygame.draw.rect(screen, WHITE_BG, pygame.Rect(interior_x, interior_y, interior_w, interior_h), 0, interior_radius)

    letter_surf = font_prefix.render(letters, True, text_color)
    l_rect = letter_surf.get_bounding_rect()

    if number:
        num_surf = font_num.render(number, True, text_color)
        n_rect = num_surf.get_bounding_rect()
        total_h = l_rect.height + text_gap + n_rect.height
    else:
        total_h = l_rect.height

    start_y = interior_y + (interior_h - total_h) // 2 + text_y_offset
    screen.blit(letter_surf, (center_x + prefix_x_offset - l_rect.width // 2 - l_rect.x, start_y - l_rect.y))

    if number:
        num_y = start_y + l_rect.height + text_gap
        screen.blit(num_surf, (center_x - n_rect.width // 2 - n_rect.x, num_y - n_rect.y))

    if code_3 and font_code_3 is not None:
        code_3_surf = font_code_3.render(code_3, True, WHITE_BG)
        c_rect = code_3_surf.get_bounding_rect()
        band_center_x = x + w // 2
        band_center_y = outer_y + code_3_band_h // 2
        code_3_x = band_center_x + code_3_x_offset - c_rect.width // 2 - c_rect.x
        code_3_y = band_center_y + code_3_y_offset - c_rect.height // 2 - c_rect.y
        screen.blit(code_3_surf, (code_3_x, code_3_y))


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
        if t_w > width:
            h_ratio = width / t_w
            img = draw_text(text, font, color, x, y, h_ratio=h_ratio)
            scaled_w = int(t_w * h_ratio)
            screen.blit(img, (x + (width - scaled_w) // 2, y))
        else:
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
    elif collapse:
        # Collapse mode for Japanese: render full text centered
        img = draw_text(text, font, color, x + (width - t_w) // 2, y)
        screen.blit(img, (x + (width - t_w) // 2, y))
    else:
        # Japanese text fits - add even spacing between characters
        sep = (width - t_w) // (len(text) + 1)
        exp = 7 if len(text) == 2 else 0
        for i, char in enumerate(text):
            x_coord = x + sep * (i + 1) + i * t_w_s + (exp if i > 0 else -exp)
            img = draw_text(char, font, color, int(x_coord), y)
            screen.blit(img, (int(x_coord), y))

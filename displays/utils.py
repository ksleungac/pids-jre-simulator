"""Shared rendering utilities for display system.

These utilities are used by all train model displays.
"""

import re

import pygame

from utils import arrow_points, draw_aapolygon


BADGE_TEXT = (15, 15, 15)  # dark — text sits on white interior
WHITE_BG = (230, 230, 230)


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
    """Draw the framed station-code badge (e.g. JO25, JY03).

    The (x, y, w, h) rect describes the **framed JY/03 portion only** — the
    optional `code_3` 3-letter top band, when present, is drawn above the
    framed square (the outer black rect extends upward by `code_3_band_h`).

    Layered as: outer black → route-color ring → white interior → letters
    centered horizontally with `prefix_x_offset` nudge → number row below
    separated by `text_gap` (visible-pixel gap, measured via
    `get_bounding_rect`).

    Returns silently if `sta_code` cannot be parsed into letters+digits.
    Used by both upper-LCD (large badge with optional code_3 band) and the
    lower-LCD 8-station view (smaller per-cell badge, no code_3 band).
    """
    m = re.match(r"([A-Za-z]+)(\d+)", sta_code or "")
    if not m:
        return
    letters = m.group(1).upper()
    number = m.group(2)

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
    num_surf = font_num.render(number, True, text_color)
    l_rect = letter_surf.get_bounding_rect()
    n_rect = num_surf.get_bounding_rect()

    total_h = l_rect.height + text_gap + n_rect.height
    start_y = interior_y + (interior_h - total_h) // 2 + text_y_offset

    screen.blit(letter_surf, (center_x + prefix_x_offset - l_rect.width // 2 - l_rect.x, start_y - l_rect.y))
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

"""Utility functions for drawing text and shapes."""

import pygame
import pygame.gfxdraw
from typing import Tuple, List


def draw_text(
    text: str,
    font: pygame.font.Font,
    color: Tuple[int, int, int],
    x: int,
    y: int,
    bg: Tuple[int, int, int] = None,
    h_ratio: float = 1.0,
    v_ratio: float = 1.0
) -> pygame.Surface:
    """Draw text with optional scaling.

    Args:
        text: Text to draw
        font: Pygame font object
        color: RGB color tuple
        x: X position
        y: Y position
        bg: Optional background color (if None, uses transparent background)
        h_ratio: Horizontal scaling ratio
        v_ratio: Vertical scaling ratio

    Returns:
        The blitted surface
    """
    if bg is None:
        img = font.render(text, True, color).convert_alpha()
        txt_w, txt_h = img.get_size()
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
    color: Tuple[int, int, int],
    screen: pygame.Surface,
    collapse: bool = False
) -> None:
    """Draw text constrained to a specific width, compressing if needed.

    Args:
        x: X position
        y: Y position
        width: Maximum width for the text
        font: Pygame font object
        text: Text to draw
        color: RGB color tuple
        screen: Pygame surface to draw on
        collapse: If True, center the text without character spacing
    """
    t_w, t_h = font.size(text)
    t_w_s = t_w // len(text) if len(text) > 0 else 0

    if t_w > width:
        sep = width / len(text)
        hr = width / (len(text) * t_w_s) if t_w_s > 0 else 1.0
        for i, char in enumerate(text):
            x_coord = x + sep * i
            img = draw_text(char, font, color, int(x_coord), y, h_ratio=hr)
            screen.blit(img, (int(x_coord), y))
    else:
        sep = (width - t_w) // (len(text) + 1)
        exp = 7 if len(text) == 2 else 0
        if collapse:
            img = draw_text(text, font, color, x + (width - t_w) // 2, y)
            screen.blit(img, (x + (width - t_w) // 2, y))
        else:
            for i, char in enumerate(text):
                x_coord = x + sep * (i + 1) + i * t_w_s + (exp if i > 0 else -exp)
                img = draw_text(char, font, color, int(x_coord), y)
                screen.blit(img, (int(x_coord), y))


def draw_aapolygon(
    surface: pygame.Surface,
    color: Tuple[int, int, int],
    points: List[Tuple[float, float]],
    scale: int = 2,
    width: int = 0
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
    """Generate arrow polygon points.

    Args:
        x: X position
        y: Y position
        w: Width
        h: Height
        stroke: Stroke width

    Returns:
        Tuple of (x, y) points defining the arrow shape
    """
    return (
        (x, y),
        (x + w - stroke, y + h / 2),
        (x, y + h),
        (x + stroke, y + h),
        (x + w, y + h / 2),
        (x + stroke, y)
    )


def draw_1col_text(
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    vert_space: int,
    text_color: Tuple[int, int, int],
    screen: pygame.Surface
) -> None:
    """Draw text vertically (one column).

    Args:
        font: Pygame font object
        text: Text to draw vertically
        x: X position
        y: Y position
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

    for k, s in enumerate(text):
        y_pos = y - vert_space + vert_dist * k
        img = draw_text(s, font, text_color, x, int(y_pos), v_ratio=vr)
        screen.blit(img, (x, int(y_pos)))


def draw_stops_text(
    font: pygame.font.Font,
    stop_text: str,
    text_color: Tuple[int, int, int],
    x: int,
    y: int,
    stops_w: int,
    screen: pygame.Surface
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

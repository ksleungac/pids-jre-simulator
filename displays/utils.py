"""Shared rendering utilities for display system.

These utilities are used by all train model displays.
"""

import pygame


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

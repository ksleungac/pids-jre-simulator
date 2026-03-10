"""Train display system.

Provides display rendering for different train models with support for
multiple display modes (KANJI, FURIGANA, ENGLISH).

Usage:
    from displays import get_train_display, DisplayMode
    from displays.utils import draw_text, draw_text_given_width

    display = get_train_display("e235_1000", screen, route_data, stops)
    display.update(current_time)
    display.draw()
"""

from displays.base import DisplayMode, ModeCycler
from displays.utils import draw_text, draw_text_given_width
from displays.train_models import get_train_display

__all__ = [
    "DisplayMode",
    "ModeCycler",
    "get_train_display",
    "draw_text",
    "draw_text_given_width",
]

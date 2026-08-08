# SPDX-License-Identifier: MIT
"""Train display system.

Provides display rendering for different train models with support for
multiple display modes (KANJI, FURIGANA, ENGLISH). Top-level façade for the
multi-model registry — see ``displays/train_models/__init__.py``.

Usage:

    from displays import get_train_model, DisplayMode

    model = get_train_model("e235_1000")          # TrainModel record
    upper = model.upper_cls(screen, route_data, stops)
    lower = model.lower_cls(screen, route_data, stops, upper.mode_cycler)
"""

from displays.base import DisplayMode, ModeCycler
from displays.utils import draw_text, draw_text_given_width
from displays.train_models import get_train_model, model_choices, resolve_model_key

__all__ = [
    "DisplayMode",
    "ModeCycler",
    "get_train_model",
    "model_choices",
    "resolve_model_key",
    "draw_text",
    "draw_text_given_width",
]

# SPDX-License-Identifier: MIT
"""E235-1000 series display implementations.

Provides UpperDisplay and LowerDisplay for the E235-1000 train model,
plus the model's per-LCD-pair dimensions and palette. Per-model values
live here (not in the top-level ``constants.py``) because each train
series has its own physical LCD aspect ratio and tint — see CLAUDE.md
"Mental Model" for the family-level scope policy.

The constants are defined BEFORE the class imports below so that
``upper_lcd`` / ``lower_lcd`` can ``from displays.train_models.e235_1000
import S_WIDTH, ...`` without hitting a partial-module circular import.
"""

# Per-model screen dimensions (E235-1000 LCD pair, real-display aspect ratio)
S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)  # 117px

# Per-model palette
DARK_BG = [25, 25, 25]
WHITE_BG = [230, 230, 230]

from displays.train_models.e235_1000.upper_lcd import UpperDisplay
from displays.train_models.e235_1000.lower_lcd import LowerDisplay

__all__ = [
    "UpperDisplay",
    "LowerDisplay",
    "S_WIDTH",
    "S_HEIGHT",
    "UPPER_HEIGHT",
    "DARK_BG",
    "WHITE_BG",
]

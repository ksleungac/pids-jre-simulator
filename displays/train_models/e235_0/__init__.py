"""E235-0 series display implementations.

Provides UpperDisplay + LowerDisplay for the E235-0 train model (Yamanote
Line). The upper LCD differs from E235-1000 only by omitting the train-type
cell (Yamanote runs a single service type, so IRL PIDS doesn't render one).
The lower LCD swaps in a circular racetrack full-route renderer when the
active route is 山手線; out-of-spec routes get E235-1000's linear full-route
renderer as best-effort fallback. The 8-station-zoom + transfer-info slots
currently inherit from E235-1000 (interim until the E235-0-specific
5-station view lands). See DISPLAY_E235.md for the canonical doc.

Per-model dimensions + palette mirror E235-1000's. The constants are
defined BEFORE the class imports below so the LCD modules can
``from displays.train_models.e235_0 import S_WIDTH, ...`` without hitting
a partial-module circular import.
"""

# Per-model screen dimensions (E235-0 LCD pair, real-display aspect ratio)
S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)  # 117px

# Per-model palette
DARK_BG = [25, 25, 25]
WHITE_BG = [230, 230, 230]

from displays.train_models.e235_0.upper_lcd import UpperDisplay
from displays.train_models.e235_0.lower_lcd import LowerDisplay

__all__ = [
    "UpperDisplay",
    "LowerDisplay",
    "S_WIDTH",
    "S_HEIGHT",
    "UPPER_HEIGHT",
    "DARK_BG",
    "WHITE_BG",
]

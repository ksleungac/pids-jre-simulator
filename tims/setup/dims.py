# SPDX-License-Identifier: MIT
"""tims setup window dimensions + background — the setup flow's own-window size.

Split out of the status band (``tims/band.py`` takes its width from the caller's
surface; SCREEN_W/H is the SETUP window size, never a band concept). Every
``tims.setup`` screen imports these.
"""

from .. import chrome

# setup is its OWN window — taller than the 420 LCD-sized one the retired classic screen used;
# height is a free knob. 610 keeps the 2/3-height buttons clear of the top-corner
# lang strip.
SCREEN_W, SCREEN_H = 730, 610
BG_COLOR = chrome.BG  # slate screen background (mirror the SetupScreen bg)

"""setup_tims window dimensions + background — the setup flow's own-window size.

Split out of the status band when it graduated to root (``status_band.py`` takes
its width from the caller's surface; SCREEN_W/H is the SETUP window size, never a
band concept). Every setup_tims screen imports these.
"""

import tims_chrome

# setup is its OWN window — taller than the 420 LCD-sized one (main.py SETUP_SIZE);
# height is a free knob. 610 keeps the 2/3-height buttons clear of the top-corner
# lang strip.
SCREEN_W, SCREEN_H = 730, 610
BG_COLOR = tims_chrome.BG  # slate screen background (mirror the SetupScreen bg)

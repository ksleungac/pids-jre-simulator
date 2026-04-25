"""Constants for PA Simulator - Screen dimensions, colors, and shared sizes.

Per-display sizes (font sizes, box positions) live inline in each LCD
module's draw methods, not here — every LCD type owns its own module and
can pick different sizes. Only constants shared by *multiple* modules
(or by app/audio) belong here.
"""

# Screen dimensions
S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)

# Background colors
DARK_BG = [25, 25, 25]
WHITE_BG = [230, 230, 230]
LIGHT_GRAY = [240, 240, 240]

# Station display colors (lower LCD route map)
PASSED_COLOR = [230, 230, 230]
CURRENT_COLOR = [175, 150, 6]
INACTIVE_COLOR = [110, 110, 110]

# Lower LCD font sizes (shared across lower-LCD mode renderers)
FONT_STOPS_SIZE = 25
FONT_TIME_SIZE = 14
FONT_STOPS_MINUTE_SIZE = 11

# Lower LCD layout
STOPS_BAR_HEIGHT = 30
STOPS_WIDTH = 42
STOPS_PER_LINE = 14

# Timing
FRAME_RATE = 15
KEY_REPEAT_DELAY = 200
SETUP_KEY_REPEAT_DELAY = 300  # Initial delay before key repeat starts (milliseconds)
SETUP_KEY_REPEAT_INTERVAL = 30  # Interval between repeated key events (milliseconds)
AUDIO_FADE_MS = 800
TARGET_LOUDNESS = -15.0
STATION_DISPLAY_INTERVAL = 4  # Seconds between kanji/furigana cycling

# Time scale for countdown: 1 second of real time = this many minutes of travel time
# Higher value = faster countdown (for testing)
# Quick reference:
#   TIME_SCALE = 1    → 1 real sec = 1 travel min (5 min journey = 5 real secs) [FAST]
#   TIME_SCALE = 5    → 1 real sec = 5 travel min (5 min journey = 1 real sec)
#   TIME_SCALE = 10   → 1 real sec = 10 travel min (10 min journey = 1 real sec)
#   TIME_SCALE = 60   → 60 real secs = 1 travel min (real-time, 5 min journey = 5 mins)
TIME_SCALE = 60  # Real-time countdown

# Small window mode
SMALL_WIDTH = 400
SMALL_HEIGHT = 200
SMALL_Y = 100

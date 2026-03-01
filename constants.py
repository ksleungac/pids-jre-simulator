"""Constants for PA Simulator - Screen dimensions, colors, and fonts."""

# Screen dimensions
S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)

# Colors (defaults, can be overridden by route.json)
DEFAULT_COLOR = [255, 255, 255]
DEFAULT_CONTRAST_COLOR = [224, 54, 37]
DEFAULT_TYPE_COLOR = [0, 0, 0]

# Background colors
DARK_BG = [25, 25, 25]
WHITE_BG = [230, 230, 230]
LIGHT_GRAY = [240, 240, 240]
SELECTED_COLOR = [230, 230, 230]

# Station display colors
PASSED_COLOR = [230, 230, 230]
CURRENT_COLOR = [175, 150, 6]
INACTIVE_COLOR = [110, 110, 110]

# Font configurations
FONT_STOPS_NAME = 'shingopr6nmedium'
FONT_STOPS_SIZE = 25
FONT_STOPS_BOLD_NAME = 'shingopr6nheavy'
FONT_CLOCK_NAME = 'helveticaneueroman'
FONT_TIME_NAME = 'helveticaneue'

# Font sizes
FONT_CLOCK_SIZE = 26
FONT_TIME_SIZE = 14
FONT_STOPS_SMALL_SIZE = 17
FONT_STOPS_MINUTE_SIZE = 11
FONT_TYPE_SIZE = 26
FONT_TYPE_BOLD_SIZE = 26
FONT_DEST_SIZE = 35
FONT_PREFIX_SIZE = 25
FONT_STATION_SIZE = 78

# Layout constants
STOPS_BAR_HEIGHT = 30
STOPS_WIDTH = 42
STOPS_PER_LINE = 14

# Window positions
WINDOW_X = S_WIDTH
WINDOW_Y = S_HEIGHT

# Timing
FRAME_RATE = 15
KEY_REPEAT_DELAY = 200
AUDIO_FADE_MS = 800
TARGET_LOUDNESS = -15.0
STATION_DISPLAY_INTERVAL = 4  # Seconds between kanji/furigana cycling

# Audio
TEMP_AUDIO_FILE = './temp_audio.mp3'

# Small window mode
SMALL_WIDTH = 400
SMALL_HEIGHT = 200
SMALL_Y = 100

# PA Simulator - Fresh Refactor Plan

## Context

This is a **Japanese Train PA (Public Address) Simulator** - a pygame-based application that simulates train station announcements and arrival melodies.

**Current state:**
- `old_version.py` - User's original working code (monolithic, ~560 lines)
- `pa_v3/` - User's own refactoring attempt (good module structure idea), later passed to another AI that produced broken code
- Project uses **uv** for dependency management (pyproject.toml exists)

**Project features:**
- Station announcements (PA - "pa" folder) with audio normalization
- Departure melodies (STA - "sta" folder) - played when trains depart
- Visual LCD display with:
  - Upper section: Train type, destination, current station name, clock
  - Lower section: Route map with station markers, progress indicator, travel times
- Keyboard controls (Page Down, Page Up, End to pause)
- Support for circular routes (like Yamanote Line)
- Configurable colors per route via JSON

## User Decision

User wants a **fresh refactor + new feature**:
1. **Refactor**: Clean, modular code with short file names (`main.py`, `audio.py`, `display.py`, etc.)
2. **New Feature**: Setup screen to select routes and train numbers (not just hardcoded path input)
3. Fix all the bugs from the broken pa_v3 refactoring
4. Keep `sta` naming convention (user is used to it)

## New Feature: Setup Screen

Instead of typing a path, the user can:
1. See a list of available routes (by scanning `audio/` subfolders for `route.json` files)
2. Select a route from a menu
3. If multiple train diagrams exist for a route, select the train number/diagram
4. Launch the simulator with the selected configuration

## Architecture Design

### Module Structure (flat, alongside old_version.py)

```
pids_jre_simulator/
├── old_version.py              # User's original backup
├── main.py                     # NEW: Entry point + setup screen
├── app.py                      # NEW: Main application class
├── audio.py                    # NEW: Audio handling with normalization
├── display.py                  # NEW: LCD display (UpperDisplay, LowerDisplay)
├── constants.py                # NEW: Screen size, colors, fonts
├── utils.py                    # NEW: Drawing/text utilities
└── setup.py                    # NEW: Route selection setup screen
```

### Module Responsibilities

#### `constants.py`
```python
# Screen dimensions
S_WIDTH = 730
S_HEIGHT = 420
UPPER_HEIGHT = int(S_HEIGHT * 0.28)

# Colors (defaults, can be overridden by route.json)
DEFAULT_COLOR = [255, 255, 255]
DEFAULT_CONTRAST_COLOR = [224, 54, 37]
DEFAULT_TYPE_COLOR = [0, 0, 0]

# Font configurations
FONT_STOPS_NAME = 'shingopr6nmedium'
FONT_STOPS_SIZE = 25
FONT_STOPS_BOLD_NAME = 'shingopr6nheavy'
FONT_CLOCK_NAME = 'helveticaneueroman'

# Layout constants
STOPS_BAR_HEIGHT = 30
STOPS_WIDTH = 42
STOPS_PER_LINE = 14
```

#### `setup.py` - NEW: Route Selection Screen
```python
import os
import json
import pygame


class SetupScreen:
    """Handles route and train selection before starting the simulator."""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.routes = []  # List of available routes
        self.selected_route = None
        self.selected_train = None

    def scan_routes(self, base_dir: str = "audio") -> list:
        """Scan for available routes by finding route.json files.

        Groups routes by name, then by train diagram.
        Only shows what's available in route.json files.
        """
        self.routes = []
        for root, dirs, files in os.walk(base_dir):
            if "route.json" in files:
                route_path = os.path.join(root, "route.json")
                try:
                    with open(route_path, encoding="utf-8") as f:
                        route_data = json.load(f)
                        self.routes.append({
                            "path": root,
                            "name": route_data.get("route", "Unknown"),
                            "diagram": route_data.get("diagram", ""),
                            "type": route_data.get("type", ""),  # e.g., 内回り/外回り
                            "dest": route_data.get("dest", ""),
                        })
                except Exception as e:
                    print(f"Error loading {route_path}: {e}")

        # Group by route name, then by diagram
        self.routes.sort(key=lambda r: (r["name"], r["diagram"], r["type"]))
        return self.routes

    def draw(self, selected_idx: int) -> None:
        """Draw the setup screen with route list."""
        # Clear screen
        # Draw title
        # Draw list of routes grouped by name
        # Highlight selected item
        # Show instructions (↑↓ to navigate, Enter to select)
        pygame.display.flip()

    def run(self) -> dict | None:
        """Run the setup screen loop. Returns configuration or None if cancelled.

        Returns:
            dict with {"work_dir": path, "route_data": data} when confirmed
            None if user cancels (ESC)
        """
        self.scan_routes()
        selected_idx = 0
        running = True

        while running:
            self.draw(selected_idx)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    elif event.key == pygame.K_UP:
                        selected_idx = max(0, selected_idx - 1)
                    elif event.key == pygame.K_DOWN:
                        selected_idx = min(len(self.routes) - 1, selected_idx + 1)
                    elif event.key == pygame.K_RETURN:
                        if self.routes:
                            selected = self.routes[selected_idx]
                            # Load full route data
                            with open(os.path.join(selected["path"], "route.json"), encoding="utf-8") as f:
                                route_data = json.load(f)
                            return {"work_dir": selected["path"], "route_data": route_data}

        return None
```

#### `audio.py`
```python
import os
import pygame.mixer as mixer
import soundfile as sf
import pyloudnorm as pyln


class AudioPlayer:
    """Handles PA announcements and departure melodies with loudness normalization."""

    def __init__(self, work_dir: str, stops: list):
        self.pa_dir = os.path.join(work_dir, 'pa')
        self.sta_dir = os.path.join(work_dir, 'sta')  # Station departure melodies
        self.stops = stops
        mixer.init()

    def play_pa(self, stop_index: int, pa_index: int) -> None:
        """Load and play PA announcement with loudness normalization."""
        track_path = os.path.join(self.pa_dir, self.stops[stop_index]['pa'][pa_index] + '.mp3')
        self._load_and_play(track_path)

    def play_sta(self, stop_index: int, sta_index: int, cut_position: float = 0) -> None:
        """Load and play departure melody (sta = station melody)."""
        track_path = os.path.join(self.sta_dir, self.stops[stop_index]['sta'][sta_index] + '.mp3')
        self._load_and_play(track_path, cut_position=cut_position)

    def pause(self) -> None:
        """Pause current playback."""
        mixer.music.pause()

    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return mixer.music.get_busy()

    def _load_and_play(self, track_path: str, cut_position: float = 0) -> None:
        """Internal method to normalize and play audio."""
        try:
            data, rate = sf.read(track_path)
            meter = pyln.Meter(rate)
            loudness = meter.integrated_loudness(data)
            normalized = pyln.normalize.loudness(data, loudness, -15.0)
            sf.write('./temp_audio.mp3', normalized, rate)

            mixer.music.unload()
            if os.path.exists('./temp_audio.mp3'):
                mixer.music.load('./temp_audio.mp3')
                mixer.music.play(fade_ms=800)
        except Exception as e:
            print(f"Audio playback error: {e}")
```

#### `display.py`
```python
import pygame
import pygame.gfxdraw
from typing import List, Dict, Any


class UpperDisplay:
    """Handles the upper portion of the LCD (train info, current station)."""

    def __init__(self, screen: pygame.Surface, route_data: Dict, app_state: 'AppState'):
        self.screen = screen
        self.route_data = route_data
        self.state = app_state
        self.x = 0
        self.y = 0
        self.h = int(route_data['screen_height'] * 0.28)
        self.dark_bg = [25, 25, 25]
        self.white_bg = [230, 230, 230]

    def draw_init(self) -> None:
        """Draw initial state (train type, destination banner)."""
        # Draw dark background
        pygame.draw.rect(self.screen, self.dark_bg, pygame.Rect(0, 0, self.screen.get_width(), self.h))
        # Draw train type box, destination, color band, prefix, station name
        pygame.display.flip()

    def draw_current_station(self) -> None:
        """Update current station name and prefix (次は/まもなく)."""
        pygame.display.flip()

    def draw_clock(self, timestamp: float) -> None:
        """Draw current time in top-right corner."""
        curr_time = time.strftime('%H:%M', time.localtime(timestamp))
        pygame.display.flip()


class LowerDisplay:
    """Handles the lower portion of the LCD (route map, station markers)."""

    def __init__(self, screen: pygame.Surface, route_data: Dict, app_state: 'AppState'):
        self.screen = screen
        self.route_data = route_data
        self.state = app_state
        self.stops = route_data['stops']
        self._calculate_layout()

    def _calculate_layout(self) -> None:
        """Calculate station display layout based on route length."""
        num_stops = len(self.stops)
        self.per_line = min(14, math.ceil(num_stops / 2)) if num_stops > 17 or num_stops % 2 == 0 else 17
        self.stops_w = 42
        self.x = (self.screen.get_width() - self.stops_w * self.per_line) // 2
        self.y = int(self.screen.get_height() * 0.28)
        self.bar_height = 30

    def show_stops(self) -> None:
        """Draw station list, markers, pointer, and travel times."""
        pygame.display.flip()

    def increment_current_stop_display(self) -> None:
        """Update which stop is highlighted."""
        pass
```

#### `app.py`
```python
import pygame
from win32 import win32gui
import keyboard
import json
import time

from constants import *
from audio import AudioPlayer
from display import UpperDisplay, LowerDisplay
from utils import draw_text


class AppState:
    """Holds the current state of the application."""

    def __init__(self):
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_sta = 0
        self.circular = 0
        self.curr_stop_disp = 0
        self.skip = 0


class PASimulator:
    """Main application class managing game loop and state."""

    def __init__(self, work_dir: str, route_data: dict):
        self.work_dir = work_dir
        self.route_data = route_data
        self._load_route_data()
        self._init_pygame()

        self.state = AppState()
        self.state.circular = 1 if self.stops[0]['name'] == self.stops[-1]['name'] else 0

        self.audio = AudioPlayer(work_dir, self.stops)
        self.upper = UpperDisplay(self.screen, self.route_data, self.state)
        self.lower = LowerDisplay(self.screen, self.route_data, self.state)
        self.frame_mode = 1
        self.running = True

    def _load_route_data(self) -> None:
        """Load route.json configuration."""
        self.stops = self.route_data['stops']
        self.route_name = self.route_data['route']
        self.train_type = self.route_data['type']
        self.color = self.route_data.get('color', [255, 255, 255])
        self.contrast_color = self.route_data.get('contrast_color', [224, 54, 37])
        self.type_color = self.route_data.get('type_color', [0, 0, 0])
        self.dest = self.route_data.get('dest', 'undefined')

    def _init_pygame(self) -> None:
        """Initialize pygame display."""
        pygame.init()
        pygame.mixer.init()
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
        self.font = pygame.font.SysFont('shingopr6nmedium', 25)
        info = pygame.display.get_wm_info()
        win32gui.SetWindowPos(info['window'], -1, S_WIDTH, S_HEIGHT, 0, 0, 1)

    def run(self) -> None:
        """Main game loop."""
        self.upper.draw_init()
        self.lower.show_stops()
        while self.running:
            self.clock.tick(15)
            self._handle_input()
            self._draw()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
        pygame.quit()

    def _handle_input(self) -> None:
        """Process keyboard input."""
        if keyboard.is_pressed('page down'):
            self._next_pa()
            pygame.time.wait(200)
        elif keyboard.is_pressed('page_up'):
            self._next_sta()
        elif keyboard.is_pressed('end') and self.audio.is_playing():
            self.audio.pause()

    def _next_pa(self) -> None:
        """Advance to next PA announcement."""
        self.state.cnt_pa += 1
        if self.state.cnt_pa >= len(self.stops[self.state.curr_stop]['pa']):
            if self.state.curr_stop < len(self.stops) - 1:
                self.state.curr_stop += 1
                self.state.cnt_pa = 0
                self.lower.increment_current_stop_display()
                while len(self.stops[self.state.curr_stop]['pa']) == 0:
                    self.state.curr_stop += 1
            elif self.state.circular == 1:
                self.state.curr_stop = 0
                self.state.cnt_pa = 0
                self.state.curr_stop_disp = 0
            else:
                self.state.cnt_pa -= 1
            self.state.cnt_sta = 0
            self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
            self.lower.show_stops()
            return
        self.lower.increment_current_stop_display()
        self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
        self.lower.show_stops()

    def _next_sta(self) -> None:
        """Play next station melody."""
        if len(self.stops[self.state.curr_stop]['sta']) <= 0:
            return
        self.audio.play_sta(self.state.curr_stop, self.state.cnt_sta)
        if self.state.cnt_sta < len(self.stops[self.state.curr_stop]['sta']) - 1:
            self.state.cnt_sta += 1

    def _draw(self) -> None:
        """Draw all display elements."""
        timestamp = time.time()
        self.upper.draw_clock(timestamp)
```

#### `utils.py`
```python
import pygame


def draw_text(text: str, font: pygame.font.Font, color: tuple,
              x: int, y: int, bg: tuple = None,
              h_ratio: float = 1.0, v_ratio: float = 1.0) -> None:
    """Draw text with optional scaling."""
    if bg is None:
        img = font.render(text, True, color).convert_alpha()
        txt_w, txt_h = img.get_size()
        img = pygame.transform.smoothscale(img, (txt_w * h_ratio, txt_h * v_ratio))
    else:
        img = font.render(text, True, color, bg)
    screen.blit(img, (x, y))


def draw_text_given_width(x: int, y: int, width: int, font: pygame.font.Font,
                          text: str, color: tuple, collapse: bool = False) -> None:
    """Draw text constrained to a specific width, compressing if needed."""
    t_w, t_h = font.size(text)
    t_w_s = t_w // len(text)
    if t_w > width:
        sep = width / len(text)
        hr = width / (len(text) * t_w_s)
        for i, char in enumerate(text):
            x_coord = x + sep * i
            draw_text(char, font, color, x_coord, y, h_ratio=hr)
    else:
        sep = (width - t_w) // (len(text) + 1)
        exp = 7 if len(text) == 2 else 0
        if collapse:
            draw_text(text, font, color, x + (width - t_w) // 2, y)
        else:
            for i, char in enumerate(text):
                x_coord = x + sep * (i + 1) + i * t_w_s + (exp if i > 0 else -exp)
                draw_text(char, font, color, x_coord, y)


def draw_aapolygon(surface: pygame.Surface, color: tuple,
                   points: list, scale: int = 2, width: int = 0) -> None:
    """Draw antialiased polygon using supersampling."""
    x_coords = tuple(x for x, _ in points)
    y_coords = tuple(y for _, y in points)
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    w = x_max - x_min + 1
    h = y_max - y_min + 1
    s = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA, surface)
    s.fill((255, 255, 255, 0))
    s_points = [((x - x_min) * scale, (y - y_min) * scale) for x, y in points]
    pygame.draw.polygon(s, color, s_points, width)
    s2 = pygame.transform.smoothscale(s, (w, h))
    surface.blit(s2, (x_min, y_min))


def arrow_points(x: int, y: int, w: int, h: int, stroke: int) -> tuple:
    """Generate arrow polygon points."""
    return ((x, y), (x + w - stroke, y + h / 2), (x, y + h),
            (x + stroke, y + h), (x + w, y + h / 2), (x + stroke, y))
```

#### `main.py`
```python
"""PA Simulator - Entry Point"""

import sys
from setup import SetupScreen
from app import PASimulator


def main():
    # Run setup screen first to select route
    setup = SetupScreen()
    config = setup.run()

    if config is None:
        print("No route selected. Exiting.")
        return

    # Start simulator with selected configuration
    sim = PASimulator(config["work_dir"], config["route_data"])
    sim.run()


if __name__ == "__main__":
    main()
```

## Key Improvements Over old_version.py

1. **Separation of Concerns**: Each module has a single, clear responsibility
2. **Type Hints**: Full type annotations for better IDE support
3. **Constants in One Place**: No magic numbers scattered throughout
4. **Proper OOP**: Classes with clear interfaces and encapsulation
5. **Error Handling**: Proper try/except for file operations
6. **Testability**: Modules can be tested independently
7. **Maintainability**: Easy to find and modify specific functionality
8. **Documentation**: Docstrings for all public classes and functions
9. **Fixed Bugs**: The broken pa_v3 code is completely rewritten
10. **New Feature**: Setup screen for route selection

## Implementation Order

1. **Create `constants.py`** - Extract all constants from old_version.py
2. **Create `utils.py`** - Drawing utilities (tested, working code)
3. **Create `audio.py`** - AudioPlayer with proper `__init__` and loud_norm
4. **Create `setup.py`** - Route selection screen (NEW FEATURE)
5. **Create `display.py`** - UpperDisplay and LowerDisplay classes
6. **Create `app.py`** - PASimulator and AppState classes
7. **Create `main.py`** - Entry point with setup flow
8. **Test** route selection with yamanote route
9. **Test** full simulator playback

## Verification

1. Run `uv run python main.py`
2. Select route from setup screen (↑↓ navigate, Enter confirm, ESC cancel)
3. Test all keyboard controls:
   - Page Down: Advance PA
   - Page Up: Play station melody
   - End: Pause audio
4. Verify visual display matches old_version.py behavior
5. Verify audio plays and normalizes correctly

## Files to Keep

- `old_version.py` - User's original backup (keep indefinitely)
- `pa_v3/` - User's reference (can delete later if desired)

## Potential Errors & Issues to Fix During Refactor

### Critical Issues in old_version.py:

1. **Bare `except:` clause (line 65)** - Catches all exceptions including `KeyboardInterrupt`, `SystemExit`. Should use `except ValueError:`.

2. **Bare `except:` clause (line 128, 200, 240, 280)** - Same issue, should specify exception type.

3. **Inconsistent file naming** - Uses `new_file.mp3` (line 464-469, 486-490) which could conflict if multiple instances run.

4. **`sta_cut` not used properly** - `next_sta()` tries to use `stops[state_control.curr_stop]["sta_cut"]` (line 483) but this key might not exist in all route.json files (e.g., some stations don't have `time` or `sta_cut`).

5. **Division by zero risk** - `vert_dist = (vert_space-t_h) / (length-1)` (line 444) will fail if `length == 1`.

6. **Index out of bounds risk** - Line 145: `stops[state_control.cnt_pa]==1` accesses with `cnt_pa` which could exceed list bounds.

7. **Undefined `draw_text` at import time** - `draw_util` is imported with `*` but `draw_text` function is defined later in the same file (line 494), causing potential circular dependency.

8. **Global state dependencies** - Classes like `LOWER` and `UPPER` depend on global variables (`stops`, `screen`, `color`, etc.) making them hard to test.

9. **`state_control` used before initialization** - `pis = LOWER()` (line 398) is created before `state_control = LCD_state()` (line 397), but `LOWER.__init__` references `state_control.curr_stop` (line 104) which works because of Python's lazy evaluation, but it's fragile.

10. **Magic numbers throughout** - Values like `224,54,37`, `730`, `420`, `0.28`, etc. should be constants.

11. **Font not error-handled** - If 'shingopr6nmedium' font is not installed, pygame will use default font silently.

12. **`route["color"] is not None` check (line 28)** - Could fail if "color" key doesn't exist. Should use `route.get("color")`.

13. **Semicolon-separated statements (line 81)** - `self.curr_stop = 0; self.cnt_pa = 0; pis.curr_stop_disp = 0` is valid but against Python style conventions.

14. **`draw_stops_text` depends on global `pis`** - Line 427 uses `pis.stops_w` instead of receiving it as a parameter.

15. **File path uses backslashes in comment (line 17)** - `E:\shit\Keiyo` - the `\s` and `\K` could be interpreted as escape sequences (though in this case it works).

### Route.json Data Variations Found:

| Field | Always Present | Optional | Notes |
|-------|---------------|----------|-------|
| `route` | Yes | No | Route name (e.g., "京浜東北・根岸線", "山手線") |
| `color` | Yes | No | RGB array for main color |
| `contrast_color` | No | Yes | Only in some routes (e.g., 中央線) |
| `type_color` | No | Yes | Only in some routes (e.g., 南武線，中央線) |
| `type` | Yes | No | Train type (e.g., "快速", "各駅停車", "内回り") |
| `dest` | Yes | No | Destination |
| `diagram` | No | Yes | Train diagram/fleet number (e.g., "4027F", "1275A") |
| `stops` | Yes | No | Array of station objects |

**Stop object fields:**
| Field | Always Present | Optional | Notes |
|-------|---------------|----------|-------|
| `name` | Yes | No | Station name |
| `pa` | Yes | No | Array of PA track numbers (can be empty `[]`) |
| `sta` | Yes | No | Array of STA track names (can have `[""]` empty string) |
| `sta_cut` | No | Yes | Cut position in seconds (missing in some stops) |
| `time` | No | Yes | Travel time to next station in minutes (missing in last stop) |
| `dest` | No | Yes | Destination change mid-route (e.g., 田町，神田) |

### Issues to Address in New Code:

1. Use `temp_audio.mp3` or unique temp file names to avoid conflicts
2. Add proper error handling for missing keys in route.json using `.get()` with defaults
3. Add proper exception types (not bare `except:`)
4. Use constants for all magic numbers
5. Make classes receive dependencies via constructor injection
6. Add font availability checks
7. Use `route.get("key", default)` pattern consistently
8. Fix the `sta_cut` optional key handling - default to 0 if missing
9. Handle empty `pa` arrays (stations with no announcement)
10. Handle empty `sta` arrays with empty string `[""]` (like 立川 in 南武線)
11. Support `diagram` field for train selection in setup screen
12. Support `type_color` for custom train type text color

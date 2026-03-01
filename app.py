"""Main application class for PA Simulator."""

import os
import json
import pygame
from win32 import win32gui
import keyboard
import time
from typing import Dict, Any, Optional

from constants import S_WIDTH, S_HEIGHT, FRAME_RATE, KEY_REPEAT_DELAY
from audio import AudioPlayer
from display import UpperDisplay, LowerDisplay
from utils import draw_text


class AppState:
    """Holds the current state of the application."""

    def __init__(self):
        """Initialize application state."""
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_sta = 0
        self.circular = 0
        self.curr_stop_disp = 0
        self.skip = 0
        self.frame_mode = 1


class PASimulator:
    """Main application class managing game loop and state."""

    def __init__(self, work_dir: str, route_data: Optional[Dict] = None):
        """Initialize the PA Simulator.

        Args:
            work_dir: Directory containing the route.json and audio folders
            route_data: Optional pre-loaded route data dictionary
        """
        self.work_dir = work_dir
        self.route_data = route_data
        self._load_route_data()
        self._init_pygame()

        # Initialize state
        self.state = AppState()
        self.state.circular = 1 if (self.stops and self.stops[0].get('name') == self.stops[-1].get('name')) else 0

        # Initialize components
        self.audio = AudioPlayer(work_dir, self.stops)
        self.upper = UpperDisplay(self.screen, self.route_data, self.state, self.stops)
        self.lower = LowerDisplay(self.screen, self.route_data, self.state, self.stops)

        self.running = True

    def _load_route_data(self) -> None:
        """Load route.json configuration and merge with stations.json data."""
        if self.route_data is None:
            json_path = os.path.join(self.work_dir, 'route.json')
            with open(json_path, encoding='utf-8') as f:
                self.route_data = json.load(f)

        # Load stations.json if available (provides furigana, english names, etc.)
        self.station_db = self._load_station_db()

        # Merge station database into stops
        self.stops = self._merge_station_data()
        self.route_name = self.route_data.get('route', 'Unknown')
        self.train_type = self.route_data.get('type', '')
        self.dest = self.route_data.get('dest', '')
        self.color = self.route_data.get('color', [255, 255, 255])
        self.contrast_color = self.route_data.get('contrast_color', [224, 54, 37])
        self.type_color = self.route_data.get('type_color', [0, 0, 0])

    def _load_station_db(self) -> Dict:
        """Load stations.json database from the route's line directory.

        Searches for stations.json in:
        1. work_dir itself (e.g., audio/keiyo/stations.json)
        2. Parent directory of work_dir (e.g., audio/chuo/stations.json when work_dir is audio/chuo/1654T/)

        Returns empty dict if not found.
        """
        # First check work_dir itself (for routes like keiyo where route.json is in the line folder)
        station_db_path = os.path.join(self.work_dir.rstrip(os.sep), 'stations.json')
        if os.path.exists(station_db_path):
            with open(station_db_path, encoding='utf-8') as f:
                return json.load(f)

        # Then check parent directory (for routes like chuo/1654T where route.json is in a subfolder)
        line_dir = os.path.dirname(self.work_dir.rstrip(os.sep))
        station_db_path = os.path.join(line_dir, 'stations.json')
        if os.path.exists(station_db_path):
            with open(station_db_path, encoding='utf-8') as f:
                return json.load(f)

        return {}

    def _merge_station_data(self) -> list:
        """Merge station database info into stops based on sta_code or station name.

        Adds furigana and english fields from station_db to each stop.
        Lookup priority:
        1. sta_code (e.g., "JC01", "JK47")
        2. name-based key (e.g., "name_蘇我") for stations without official codes
        """
        stops = self.route_data.get('stops', [])
        merged = []

        for stop in stops:
            stop_copy = stop.copy()
            sta_code = stop.get('sta_code')
            station_name = stop.get('name', '')

            station_info = None

            # Try sta_code lookup first
            if sta_code and sta_code in self.station_db:
                station_info = self.station_db[sta_code]
            # Fallback to name-based lookup
            elif station_name:
                name_key = f"name_{station_name}"
                if name_key in self.station_db:
                    station_info = self.station_db[name_key]

            # Merge station info if found
            if station_info:
                if 'furigana' not in stop_copy and 'furigana' in station_info:
                    stop_copy['furigana'] = station_info['furigana']
                if 'english' not in stop_copy and 'english' in station_info:
                    stop_copy['english'] = station_info['english']

            merged.append(stop_copy)

        return merged

    def _init_pygame(self) -> None:
        """Initialize pygame display."""
        pygame.init()
        pygame.mixer.init()
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
        pygame.display.set_caption('PA Simulator')

        # Set window position
        try:
            info = pygame.display.get_wm_info()
            win32gui.SetWindowPos(info['window'], -1, S_WIDTH, S_HEIGHT, 0, 0, 1)
        except Exception as e:
            print(f"Warning: Could not set window position: {e}")

    def run(self) -> None:
        """Main game loop."""
        # Draw initial state
        self.upper.draw_init()
        self.lower.show_stops()

        while self.running:
            self.clock.tick(FRAME_RATE)
            timestamp = time.time()

            # Draw clock
            self.upper.draw_clock(timestamp)

            # Handle input
            self._handle_input()

            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

        self.cleanup()

    def _handle_input(self) -> None:
        """Process keyboard input."""
        try:
            if keyboard.is_pressed('page down'):
                self._next_pa()
                pygame.time.wait(KEY_REPEAT_DELAY)
            elif keyboard.is_pressed('page_up'):
                self._next_sta()
            elif keyboard.is_pressed('end') and self.audio.is_playing():
                self.audio.pause()
        except Exception as e:
            print(f"Input error: {e}")

    def _next_pa(self) -> None:
        """Advance to next PA announcement."""
        # Don't advance if audio is already playing
        if self.audio.is_playing():
            return

        if not self.stops:
            return

        current_stop_data = self.stops[self.state.curr_stop]
        pa_tracks = current_stop_data.get('pa', [])

        # Check if we've exhausted PA announcements for this stop
        if self.state.cnt_pa >= len(pa_tracks) - 1:
            # Move to next stop
            if self.state.curr_stop < len(self.stops) - 1:
                self.state.curr_stop += 1
                self.state.cnt_pa = 0
                self.lower.increment_current_stop_display()

                # Skip stations with no PA
                while (self.state.curr_stop < len(self.stops) and
                       not self.stops[self.state.curr_stop].get('pa', [])):
                    self.state.curr_stop += 1

                # Check if we went past the end
                if self.state.curr_stop >= len(self.stops):
                    self.state.curr_stop = len(self.stops) - 1
                    self.state.cnt_pa = max(0, len(pa_tracks) - 1)
                    return
            elif self.state.circular == 1:
                # Loop back to start for circular routes
                self.state.curr_stop = 0
                self.state.cnt_pa = 0
                self.state.curr_stop_disp = 0
            else:
                # End of route
                self.state.cnt_pa = max(0, len(pa_tracks) - 1)
                return

            self.state.cnt_sta = 0
            self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
            self.upper.draw_current_station()
            self.lower.show_stops()
        else:
            # Next PA within current stop
            self.state.cnt_pa += 1
            self.lower.increment_current_stop_display()
            self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
            self.upper.draw_current_station()
            self.lower.show_stops()

    def _next_sta(self) -> None:
        """Play next station melody.

        Behavior:
        - If not playing: Play from start
        - If already playing: Restart from sta_cut position (like a preview skip)
        """
        if not self.stops:
            return

        current_stop_data = self.stops[self.state.curr_stop]
        sta_tracks = current_stop_data.get('sta', [])

        # Handle empty station melody list
        if not sta_tracks or sta_tracks == ['']:
            return

        # Get cut position (default to 0 if not specified)
        cut_position = current_stop_data.get('sta_cut', 0)

        # If already playing, restart from cut position
        if self.audio.is_playing():
            self.audio.play_sta(self.state.curr_stop, self.state.cnt_sta, cut_position)
            return

        # Otherwise, play from start
        self.audio.play_sta(self.state.curr_stop, self.state.cnt_sta, 0)

        if self.state.cnt_sta < len(sta_tracks) - 1:
            self.state.cnt_sta += 1

    def cleanup(self) -> None:
        """Clean up resources."""
        if hasattr(self, 'audio'):
            self.audio.cleanup()
        pygame.quit()

    def small_size(self) -> None:
        """Switch to small window mode."""
        from constants import SMALL_WIDTH, SMALL_HEIGHT, SMALL_Y, LIGHT_GRAY

        pygame.display.set_mode((SMALL_WIDTH, SMALL_HEIGHT))
        try:
            info = pygame.display.get_wm_info()
            win32gui.SetWindowPos(info['window'], -1, 400, SMALL_Y, 0, 0, 1)
        except Exception:
            pass

        self.screen.fill(LIGHT_GRAY)

        # Draw mini display
        pygame.draw.rect(self.screen, (240, 240, 240), pygame.Rect(0, 0, SMALL_WIDTH, 120))
        pygame.draw.rect(self.screen, self.color, pygame.Rect(20, 10, 10, 55))

        font_n = pygame.font.SysFont('shingopr6nmedium', 20)
        draw_text = lambda t, f, c, x, y: self.screen.blit(f.render(t, True, c), (x, y))

        draw_text(self.route_name, font_n, (0, 0, 0), 40, 10)
        draw_text(self.train_type, font_n, (0, 0, 0), 40, 45)

        dest_text = self.dest
        dest_width, _ = font_n.size(dest_text)
        draw_text(dest_text, font_n, (0, 0, 0), SMALL_WIDTH - dest_width - 55, 27)

        suffix = "方面" if self.route_name == "山手線" else "行"
        draw_text(suffix, font_n, (0, 0, 0), SMALL_WIDTH - 55, 27)

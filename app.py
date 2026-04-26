"""Main application class for PA Simulator."""

import os
import json
import pygame
from win32 import win32gui
import keyboard
import time
from typing import Dict, Any, Optional

from constants import S_WIDTH, S_HEIGHT, FRAME_RATE, KEY_REPEAT_DELAY, TIME_SCALE
from audio import AudioPlayer
from displays.train_models.e235_1000 import UpperDisplay, LowerDisplay
from utils import draw_text


class AppState:
    """Holds the current state of the application."""

    def __init__(self):
        """Initialize application state."""
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_sta = 0
        self.circular = 0
        self.skip = 0
        self.frame_mode = 1
        self.departure_time = 0.0  # Timestamp when train departed for current segment
        self.is_last_pa = False  # Whether current PA is the last one before arriving
        # Time-based skip progression. cursor_pos derives from these.
        self.time_to_next = 0  # Time from current to next stopping station
        self.skip_progress = 0  # Passing-station ticks completed (0..skip)

    @property
    def cursor_pos(self) -> int:
        """Visual cursor position on the lower-LCD route map.

        Equals ``curr_stop`` except during skip animation, when the cursor
        lags behind by ``skip - skip_progress`` and walks forward as time
        passes (or a PA-within-stop tick fires) until it catches up.
        """
        return self.curr_stop - max(0, self.skip - self.skip_progress)

    # CONTRACT: skip-animation state owner — renderer stays pure.
    # See DISPLAY.md § "Station Skip Logic (full spec)".
    # Wrong: mutating skip from the renderer. Right: bump skip_progress here; cursor_pos auto-derives.
    def update_skip_progress(self, current_time: float) -> None:
        """Advance ``skip_progress`` through passing stations based on elapsed time.

        ``cursor_pos`` derives from ``curr_stop - (skip - skip_progress)`` —
        bumping ``skip_progress`` here is what pulls the visual cursor forward.

        Called from the main loop before each frame's draw. State-machine
        logic; lives on AppState rather than the renderer so the lower
        display can stay pure rendering (mirrors the upper).
        """
        if self.skip == 0:
            return

        # departure_time == 0.0 is the uninitialized sentinel (no skip in flight).
        # current_time is always a real time.time() timestamp from the run loop;
        # no need to guard for current_time <= 0.
        if self.departure_time <= 0:
            return

        if self.time_to_next <= 0:
            return

        elapsed_minutes = (current_time - self.departure_time) / TIME_SCALE

        # Skip stations divide the travel time into (skip + 1) segments.
        # skip=1: 50% mark -> progress to first passing.
        # skip=2: 33% / 67% marks -> first / second passing.
        for i in range(1, self.skip + 1):
            threshold = self.time_to_next * i / (self.skip + 1)
            if elapsed_minutes >= threshold and self.skip_progress < i:
                self.skip_progress = i


class _SilentAudio:
    """No-op audio used in preview mode.

    Drops in for AudioPlayer so preview can step through PA/state logic
    instantly without playing sound, while `_next_pa` / `_next_sta` stay
    unchanged (they only call audio through this interface).
    """

    def play_pa(self, *args, **kwargs) -> None: ...
    def play_sta(self, *args, **kwargs) -> None: ...
    def pause(self) -> None: ...
    def is_playing(self) -> bool:
        return False

    def cleanup(self) -> None: ...


class PASimulator:
    """Main application class managing game loop and state."""

    def __init__(self, work_dir: str, route_data: Optional[Dict] = None, preview: bool = False):
        """Initialize the PA Simulator.

        Args:
            work_dir: Directory containing the route.json and audio folders
            route_data: Optional pre-loaded route data dictionary
            preview: If True, run with silent audio and pygame-event input
                (used by preview_display.py — skips mixer init and win32gui
                positioning, and routes key input through pygame events instead
                of the global `keyboard` library).
        """
        self.preview = preview
        self.work_dir = work_dir
        self.route_data = route_data
        self._load_route_data()
        self._init_pygame()

        # Initialize state
        self.state = AppState()
        self.state.circular = 1 if (self.stops and self.stops[0].get("name") == self.stops[-1].get("name")) else 0

        # Initialize components
        self.audio = _SilentAudio() if preview else AudioPlayer(work_dir, self.stops)
        self.upper = UpperDisplay(self.screen, self.route_data, self.stops)
        # Lower shares the upper's mode_cycler — modes stay in lockstep, no
        # parallel timer. set_state below binds the state reference; lower
        # reads cursor_pos / skip / etc. live from it each frame.
        self.lower = LowerDisplay(self.screen, self.route_data, self.stops, self.upper.mode_cycler)
        self.lower.set_state(self.state)

        self.running = True

    def _load_route_data(self) -> None:
        """Load route.json configuration and merge with data/translations.json."""
        if self.route_data is None:
            json_path = os.path.join(self.work_dir, "route.json")
            with open(json_path, encoding="utf-8") as f:
                self.route_data = json.load(f)

        # Load translations.json (furigana, english names) for stop merging
        self.station_db = self._load_station_db()

        # Merge station database into stops
        self.stops = self._merge_station_data()
        self.route_name = self.route_data.get("route", "Unknown")
        self.train_type = self.route_data.get("type", "")
        self.dest = self.route_data.get("dest", "")

        # Lookup destination furigana from translations (fallback to route.json if present)
        self.dest_furigana = self.route_data.get("dest_furigana", "")
        if not self.dest_furigana and self.dest and self.dest in self.station_db:
            self.dest_furigana = self.station_db[self.dest].get("furigana", "")

        # Add dest_furigana to route_data so UpperDisplay can access it
        self.route_data["dest_furigana"] = self.dest_furigana

        self.color = self.route_data.get("color", [255, 255, 255])
        self.contrast_color = self.route_data.get("contrast_color", [224, 54, 37])
        self.type_color = self.route_data.get("type_color", [0, 0, 0])

    def _load_station_db(self) -> Dict:
        """Load central translations.json from data/ directory.

        Loads from project root: data/translations.json
        This file contains furigana/english translations keyed by Japanese station name.

        Returns empty dict if not found.
        """
        # Get project root by going up from work_dir (e.g., audio/chuo/1654T -> project root)
        project_root = os.path.dirname(os.path.dirname(self.work_dir.rstrip(os.sep)))

        # Handle case where work_dir is directly under audio/ (e.g., audio/keiyo)
        if os.path.basename(project_root) == "audio":
            project_root = os.path.dirname(project_root)

        translations_path = os.path.join(project_root, "data", "translations.json")

        if os.path.exists(translations_path):
            with open(translations_path, encoding="utf-8") as f:
                return json.load(f)

        return {}

    def _merge_station_data(self) -> list:
        """Merge translation data into stops from central translations.json.

        Lookup is by station name (Japanese kanji/kana).
        Adds furigana and english fields to each stop.
        """
        stops = self.route_data.get("stops", [])
        merged = []

        for stop in stops:
            stop_copy = stop.copy()
            station_name = stop.get("name", "")

            # Lookup by station name in central translations
            if station_name and station_name in self.station_db:
                translation = self.station_db[station_name]
                if "furigana" not in stop_copy and "furigana" in translation:
                    stop_copy["furigana"] = translation["furigana"]
                if "english" not in stop_copy and "english" in translation:
                    stop_copy["english"] = translation["english"]

            merged.append(stop_copy)

        return merged

    def _init_pygame(self) -> None:
        """Initialize pygame display."""
        pygame.init()
        if not self.preview:
            pygame.mixer.init()
        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
        pygame.display.set_caption("PIDS Preview  —  PageDown=PA  PageUp=Mode  ←/→=Jump  ESC=Quit" if self.preview else "PA Simulator")

        if not self.preview:
            # Set window position (real app only; preview uses default placement)
            try:
                info = pygame.display.get_wm_info()
                win32gui.SetWindowPos(info["window"], -1, S_WIDTH, S_HEIGHT, 0, 0, 1)
            except Exception as e:
                print(f"Warning: Could not set window position: {e}")

    def run(self) -> None:
        """Main game loop."""
        # Draw initial state
        self.upper.set_state(self.state.curr_stop, self.state.cnt_pa)
        self.upper.draw()
        self.lower.draw()
        pygame.display.flip()

        while self.running:
            self.clock.tick(FRAME_RATE)
            timestamp = time.time()

            # Advance skip animation (was inside LowerDisplay; moved here so
            # the display layer stays pure-rendering, mirroring upper).
            self.state.update_skip_progress(timestamp)

            # Update and draw upper display
            self.upper.update(timestamp)
            self.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))

            # Draw lower display with current time for real-time countdown
            self.lower.draw(timestamp)

            pygame.display.flip()

            # Handle input
            self._handle_input()

            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

        self.cleanup()

    def _handle_input(self) -> None:
        """Dispatch input handling based on mode."""
        if self.preview:
            self._handle_input_preview()
        else:
            self._handle_input_main()

    def _handle_input_main(self) -> None:
        """Real app: global keyboard polling via `keyboard` library."""
        try:
            if keyboard.is_pressed("page down"):
                self._next_pa()
                pygame.time.wait(KEY_REPEAT_DELAY)
            elif keyboard.is_pressed("page_up"):
                self._next_sta()
            elif keyboard.is_pressed("end") and self.audio.is_playing():
                self.audio.pause()
        except Exception as e:
            print(f"Input error: {e}")

    def _handle_input_preview(self) -> None:
        """Preview: focus-based pygame events. Also drains the event queue
        (including QUIT), so run()'s own event loop sees nothing and is a no-op
        in preview mode."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_PAGEDOWN:
                    self._next_pa()
                elif event.key == pygame.K_PAGEUP:
                    self._next_sta()
                elif event.key == pygame.K_RIGHT:
                    self.jump_to_stop(self.state.curr_stop + 1)
                elif event.key == pygame.K_LEFT:
                    self.jump_to_stop(self.state.curr_stop - 1)
                elif event.key == pygame.K_m:
                    self._cycle_display_mode()

    def _cycle_display_mode(self) -> None:
        """Cycle the upper display's forced mode (preview helper, bound to M)."""
        from displays.base import DisplayMode

        order = [DisplayMode.KANJI, DisplayMode.FURIGANA, DisplayMode.ENGLISH]
        cur = self.upper.mode_cycler.current_mode
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.upper.mode_cycler.current_mode = nxt
        self.upper.mode_cycler.enabled = False

    def jump_to_stop(self, target: int, direction: int = -1) -> None:
        """Hard-jump to a stop index, bypassing PA/audio cycle.

        If ``target`` lands on a passing station (``pa == []``), rolls in
        ``direction`` (-1 backward default, +1 forward) to the nearest station
        the train would actually stop at. Passing stations are not valid
        resting states in the real app — ``_next_pa``'s while-loop skips them
        on every transition — so the preview should not land there either.

        Default is backward so the preview always lands on the stop just
        *before* any upcoming skip: a pre-skip state from which PageDown
        exercises the skip logic. Consequence: the → arrow becomes a no-op
        when the next station is passing — use PageDown to cross the skip.

        Resets animation state so countdown and skip-progress start fresh
        (``departure_time=0`` keeps the lower-LCD countdown frozen until the
        next real PA advance).
        """
        if not self.stops:
            return
        target = max(0, min(target, len(self.stops) - 1))

        def _has_pa(i: int) -> bool:
            return bool(self.stops[i].get("pa"))

        # Special case: target=0 IS the initial-boarding state. Most real routes
        # have `pa: []` at stop 0 because no announcement has played yet (the
        # train is sitting at the start). Don't roll away from it — that's
        # exactly the state the user wants to preview. The lower LCD's special
        # "yellow flag" rendering at curr_stop=0 is meant for this.
        if target == 0:
            pass
        elif not _has_pa(target):
            step = 1 if direction >= 0 else -1
            scan = target
            while 0 <= scan < len(self.stops) and not _has_pa(scan):
                scan += step
            if 0 <= scan < len(self.stops):
                target = scan
            else:
                # Hit the boundary without finding PA — fall back the other way.
                scan = target
                step = -step
                while 0 <= scan < len(self.stops) and not _has_pa(scan):
                    scan += step
                if 0 <= scan < len(self.stops):
                    target = scan
                # else: no stop with PA anywhere — stay on clamped target.

        self.state.curr_stop = target
        self.state.cnt_pa = 0
        self.state.cnt_sta = 0
        self.state.skip = 0
        self.state.skip_progress = 0
        self.state.time_to_next = 0
        self.state.is_last_pa = False
        self.state.departure_time = 0.0
        self.upper.set_state(target, 0)

    # CONTRACT: two branches (advance overwrites skip; within-stop zeroes it)
    # together prevent single-PA-target leakage. See DISPLAY.md §
    # "Station Skip Logic (full spec)" before restructuring either branch.
    def _next_pa(self) -> None:
        """Advance to next PA announcement."""
        # Don't advance if audio is already playing
        if self.audio.is_playing():
            return

        if not self.stops:
            return

        current_stop_data = self.stops[self.state.curr_stop]
        pa_tracks = current_stop_data.get("pa", [])

        # Check if we've exhausted PA announcements for this stop
        if self.state.cnt_pa >= len(pa_tracks) - 1:
            # Move to next stop
            if self.state.curr_stop < len(self.stops) - 1:
                prev_stop = self.state.curr_stop
                self.state.curr_stop += 1
                # Skip stations with no PA — land curr_stop on the next PA station.
                while self.state.curr_stop < len(self.stops) and not self.stops[self.state.curr_stop].get("pa", []):
                    self.state.curr_stop += 1

                if self.state.curr_stop >= len(self.stops):
                    self.state.curr_stop = len(self.stops) - 1
                    self.state.cnt_pa = max(0, len(pa_tracks) - 1)
                    return

                # Set up the skip animation. cursor_pos starts at
                # (curr_stop - skip), so it appears on the first passing
                # station and walks forward as skip_progress ticks up.
                self.state.skip = self.state.curr_stop - prev_stop - 1
                self.state.skip_progress = 0
                self.state.time_to_next = self.stops[self.state.curr_stop].get("time", 0) if self.state.skip > 0 else 0
                self.state.cnt_pa = 0
                self.state.is_last_pa = False
                self.state.departure_time = time.time()
            elif self.state.circular == 1:
                # Loop back to start for circular routes
                self.state.curr_stop = 0
                self.state.cnt_pa = 0
                self.state.is_last_pa = False
                self.state.skip = 0
                self.state.skip_progress = 0
                self.state.time_to_next = 0
                self.state.departure_time = time.time()
            else:
                # End of route
                self.state.cnt_pa = max(0, len(pa_tracks) - 1)
                return

            self.state.cnt_sta = 0
            self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
            self.upper.set_state(self.state.curr_stop, self.state.cnt_pa)
            self.upper.draw()
        else:
            # Next PA within current stop. Catches the cursor up if a skip
            # animation was still mid-flight (e.g., user clicked PageDown
            # faster than the time threshold).
            self.state.cnt_pa += 1
            self.state.is_last_pa = self.state.cnt_pa >= len(pa_tracks) - 1
            self.state.skip = 0
            self.state.skip_progress = 0
            self.state.time_to_next = 0
            self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
            self.upper.set_state(self.state.curr_stop, self.state.cnt_pa)
            self.upper.draw()

    def _next_sta(self) -> None:
        """Play next station melody.

        Behavior:
        - If not playing: Play from start
        - If already playing: Restart from sta_cut position (like a preview skip)
        """
        if not self.stops:
            return

        current_stop_data = self.stops[self.state.curr_stop]
        sta_tracks = current_stop_data.get("sta", [])

        # Handle empty station melody list
        if not sta_tracks or sta_tracks == [""]:
            return

        # Get cut position (default to 0 if not specified)
        cut_position = current_stop_data.get("sta_cut", 0)

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
        if hasattr(self, "audio"):
            self.audio.cleanup()
        pygame.quit()

    def small_size(self) -> None:
        """Switch to small window mode."""
        from constants import SMALL_WIDTH, SMALL_HEIGHT, SMALL_Y, LIGHT_GRAY

        pygame.display.set_mode((SMALL_WIDTH, SMALL_HEIGHT))
        try:
            info = pygame.display.get_wm_info()
            win32gui.SetWindowPos(info["window"], -1, 400, SMALL_Y, 0, 0, 1)
        except Exception:
            pass

        self.screen.fill(LIGHT_GRAY)

        # Draw mini display
        pygame.draw.rect(self.screen, (240, 240, 240), pygame.Rect(0, 0, SMALL_WIDTH, 120))
        pygame.draw.rect(self.screen, self.color, pygame.Rect(20, 10, 10, 55))

        font_n = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 20)
        draw_text = lambda t, f, c, x, y: self.screen.blit(f.render(t, True, c), (x, y))

        draw_text(self.route_name, font_n, (0, 0, 0), 40, 10)
        draw_text(self.train_type, font_n, (0, 0, 0), 40, 45)

        dest_text = self.dest
        dest_width, _ = font_n.size(dest_text)
        draw_text(dest_text, font_n, (0, 0, 0), SMALL_WIDTH - dest_width - 55, 27)

        suffix = "方面" if self.route_name == "山手線" else "行"
        draw_text(suffix, font_n, (0, 0, 0), SMALL_WIDTH - 55, 27)

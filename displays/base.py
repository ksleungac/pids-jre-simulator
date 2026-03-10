"""Base classes and utilities for train display system."""

import time
from enum import IntEnum


class DisplayMode(IntEnum):
    """Display modes for Upper LCD cycling."""
    KANJI = 0
    FURIGANA = 1
    ENGLISH = 2


class ModeCycler:
    """
    Manages cycling through display modes.

    Shared utility used by all train model displays.
    """

    def __init__(self, mode_displays: dict, default_mode: DisplayMode = DisplayMode.ENGLISH):
        """
        Initialize mode cycler.

        Args:
            mode_displays: Dict mapping DisplayMode to display class instances
            default_mode: Starting display mode
        """
        self.mode_displays = mode_displays
        self.current_mode = default_mode
        self.last_switch_time = time.time()
        self.enabled = True

    def update(self, current_time: float = None) -> None:
        """
        Update cycling state and switch mode if interval elapsed.

        Args:
            current_time: Current timestamp (uses time.time() if None)
        """
        if not self.enabled:
            return

        if current_time is None:
            current_time = time.time()

        # Import here to avoid circular dependency
        from constants import STATION_DISPLAY_INTERVAL

        if current_time - self.last_switch_time >= STATION_DISPLAY_INTERVAL:
            self._cycle_to_next()
            self.last_switch_time = current_time

    def _cycle_to_next(self) -> None:
        """Cycle to the next available display mode."""
        modes = list(self.mode_displays.keys())
        if self.current_mode not in modes:
            self.current_mode = modes[0]
            return

        current_idx = modes.index(self.current_mode)
        self.current_mode = modes[(current_idx + 1) % len(modes)]

    def get_current_mode(self) -> DisplayMode:
        """Get current display mode."""
        return self.current_mode

    def get_current_display(self):
        """Get display instance for current mode."""
        return self.mode_displays[self.current_mode]

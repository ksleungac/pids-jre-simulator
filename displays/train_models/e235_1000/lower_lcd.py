"""E235-1000 series Lower LCD display implementation.

Placeholder for future Lower LCD implementation.
Will contain all display modes (Japanese, Furigana, English) for the
E235-1000 series Lower LCD (route map, station markers, travel times).
"""

from displays.base import DisplayMode


class LowerDisplay:
    """E235-1000 Lower LCD manager (placeholder)."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

    def update(self, current_time: float = None) -> None:
        """Update Lower LCD state."""
        pass

    def draw(self) -> None:
        """Draw the Lower LCD."""
        pass

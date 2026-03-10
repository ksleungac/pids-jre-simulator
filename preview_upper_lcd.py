"""Standalone preview script for Upper LCD drawing logic.

This script uses the new display system architecture (displays/)
for testing the E235-1000 series Upper LCD with 3-mode cycling.

Current Layout Zones (Upper LCD, height = 117px):
┌─────────────────────────────────────────────────────────────┐
│ [Train Type]  15:30                                         │  Top zone (0-35px)
│ [Dest ゆき]   ║                                              │  Middle zone (35-50px) - color band
│             ──┴──                                            │
│            Prefix    Station Name                            │  Bottom zone (50-117px)
└─────────────────────────────────────────────────────────────┘
"""

import pygame
import time
import sys

from displays.train_models.e235_1000 import UpperDisplay
from displays.base import DisplayMode
from displays.train_models.e235_1000.upper_lcd import S_WIDTH, S_HEIGHT, UPPER_HEIGHT


# =============================================================================
# Mock Data (for preview - modify to test different scenarios)
# =============================================================================

MOCK_ROUTE_DATA = {
    "route": "山手線",
    "type": "快速",
    "dest": "池袋・新宿",
    "dest_furigana": "とうきょう",
    "color": [0, 128, 0],  # Green for Yamanote
    "type_color": [0, 0, 0],
}

MOCK_STOPS = [
    {
        "name": "東京",
        "furigana": "とうきょう",
        DisplayMode.ENGLISH: "Tōkyō",
    },
    {
        "name": "有楽町",
        "furigana": "ゆうらくちょう",
        DisplayMode.ENGLISH: "Yūrakuchō",
    },
    {
        "name": "新橋",
        "furigana": "しんばし",
        DisplayMode.ENGLISH: "Shimbashi",
    },
    {
        "name": "品川",
        "furigana": "しながわ",
        DisplayMode.ENGLISH: "Shinagawa",
    },
    {
        "name": "高輪ゲートウェイ",
        "furigana": "たかなわげーとうぇい",
        DisplayMode.ENGLISH: "Takanawa Gateway",
    },
]

MOCK_STATE = {
    "curr_stop": 0,
    "cnt_pa": 0,  # 0 = "次は", 1 = "まもなく", 2+ = "ただいま"
}


# =============================================================================
# Main Preview Loop
# =============================================================================


def main():
    """Run the preview loop for testing Upper LCD display."""
    pygame.init()
    screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
    pygame.display.set_caption("Upper LCD Preview (E235-1000) - Press: PageDown=next station, PageUp=next PA, ESC=quit")
    clock = pygame.time.Clock()

    # Initialize display using new architecture
    display = UpperDisplay(screen, MOCK_ROUTE_DATA, MOCK_STOPS)
    display.set_state(MOCK_STATE["curr_stop"], MOCK_STATE["cnt_pa"])

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_PAGEDOWN:
                    # Next station
                    MOCK_STATE["curr_stop"] = (MOCK_STATE["curr_stop"] + 1) % len(MOCK_STOPS)
                    MOCK_STATE["cnt_pa"] = 0
                    display.set_state(MOCK_STATE["curr_stop"], MOCK_STATE["cnt_pa"])
                    print(f"[DEBUG] Station: {MOCK_STOPS[MOCK_STATE['curr_stop']]['name']}")
                elif event.key == pygame.K_PAGEUP:
                    # Next PA
                    MOCK_STATE["cnt_pa"] = (MOCK_STATE["cnt_pa"] + 1) % 3
                    display.set_state(MOCK_STATE["curr_stop"], MOCK_STATE["cnt_pa"])
                    prefixes = ["次は", "まもなく", "ただいま"]
                    print(f"[DEBUG] PA: {prefixes[MOCK_STATE['cnt_pa']]}")

        # Update display (handles mode cycling internally)
        display.update()

        # Draw display
        display.draw()

        pygame.display.flip()
        clock.tick(15)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

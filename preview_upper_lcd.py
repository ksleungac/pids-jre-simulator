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

Usage:
  uv run preview_upper_lcd.py                          # Interactive mode
  uv run preview_upper_lcd.py --screenshot out.png     # Save screenshot and exit
  uv run preview_upper_lcd.py --screenshot out.png --mode english --stop 2 --pa 1
"""

import argparse
import os
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
    "dest": "君津",
    "dest_furigana": "とうきょう",
    "color": [0, 128, 0],  # Green for Yamanote
    "type_color": [150, 40, 0],
}

MOCK_STOPS = [
    {
        "name": "東京",
        "furigana": "とうきょう",
        "english": "Tōkyō",
    },
    {
        "name": "有楽町",
        "furigana": "ゆうらくちょう",
        "english": "Yūrakuchō",
    },
    {
        "name": "新橋",
        "furigana": "しんばし",
        "english": "Shimbashi",
    },
    {
        "name": "品川",
        "furigana": "しながわ",
        "english": "Shinagawa",
    },
    {
        "name": "高輪ゲートウェイ",
        "furigana": "たかなわげーとうぇい",
        "english": "Takanawa Gateway",
    },
    {
        "name": "久里浜",
        "furigana": "くりはま",
        "english": "Kurihama",
    },
]

MOCK_STATE = {
    "curr_stop": 0,
    "cnt_pa": 0,  # 0 = "次は", 1 = "まもなく", 2+ = "ただいま"
}


# =============================================================================
# Main Preview Loop
# =============================================================================


def parse_args():
    parser = argparse.ArgumentParser(description="Upper LCD Preview (E235-1000)")
    parser.add_argument("--screenshot", type=str, help="Save screenshot to file and exit")
    parser.add_argument("--mode", type=str, choices=["kanji", "furigana", "english"], default=None, help="Force display mode (default: cycles)")
    parser.add_argument("--stop", type=int, default=0, help="Station index (default: 0)")
    parser.add_argument("--pa", type=int, default=0, help="PA count: 0=次は, 1=まもなく, 2=ただいま (default: 0)")
    return parser.parse_args()


def main():
    """Run the preview loop for testing Upper LCD display."""
    args = parse_args()

    # Use dummy video driver for headless screenshot mode
    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    pygame.init()
    screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
    pygame.display.set_caption("Upper LCD Preview (E235-1000) - Press: PageDown=next station, PageUp=next PA, ESC=quit")
    clock = pygame.time.Clock()

    # Initialize display using new architecture
    display = UpperDisplay(screen, MOCK_ROUTE_DATA, MOCK_STOPS)

    # Force mode if specified (temporarily enable all modes including English)
    mode_map = {"kanji": DisplayMode.KANJI, "furigana": DisplayMode.FURIGANA, "english": DisplayMode.ENGLISH}
    if args.mode:
        forced_mode = mode_map[args.mode]
        # Enable all modes so forced mode works even if normally disabled
        display.mode_displays[DisplayMode.ENGLISH] = display.english_display
        display.mode_cycler.current_mode = forced_mode
        display.mode_cycler.paused = True

    stop_idx = min(args.stop, len(MOCK_STOPS) - 1)
    pa_count = args.pa
    display.set_state(stop_idx, pa_count)

    if args.screenshot:
        # Render one frame and save
        display.update()
        display.draw()
        pygame.image.save(screen, args.screenshot)
        print(f"Screenshot saved to {args.screenshot}")
        pygame.quit()
        return

    MOCK_STATE["curr_stop"] = stop_idx
    MOCK_STATE["cnt_pa"] = pa_count

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

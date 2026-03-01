"""PA Simulator - Entry Point

A Japanese Train PA (Public Address) Simulator with pygame-based
visual display and audio playback with loudness normalization.
"""

import os
import sys
import pygame

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

from setup import SetupScreen
from app import PASimulator


def main():
    """Main entry point for the PA Simulator."""
    # Initialize pygame for the setup screen
    pygame.init()
    pygame.mixer.init()

    # Get the directory where the executable is located (for PyInstaller)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        # Running as script
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Create screen for setup
    screen = pygame.display.set_mode((730, 420))
    pygame.display.set_caption('PA Simulator - Route Selection')

    # Run setup screen to select route (scan from exe directory)
    setup = SetupScreen(screen)
    audio_dir = os.path.join(BASE_DIR, "audio")
    setup.scan_routes(audio_dir)
    config = setup.run()

    if config is None:
        print("No route selected. Exiting.")
        pygame.quit()
        return

    # Clean up setup screen
    pygame.display.quit()

    # Start simulator with selected configuration
    try:
        sim = PASimulator(config["work_dir"], config["route_data"])
        sim.run()
    except Exception as e:
        print(f"Error running simulator: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()

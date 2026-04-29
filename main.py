"""PA Simulator - Entry Point

A Japanese Train PA (Public Address) Simulator with pygame-based
visual display and audio playback with loudness normalization.
"""

import os
import sys
import pygame

# Suppress pygame welcome message
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import i18n
from language_picker import LanguagePicker
from setup import SetupScreen
from app import PASimulator


def main():
    """Main entry point for the PA Simulator."""
    # Initialize pygame for the setup screen
    pygame.init()
    pygame.mixer.init()

    # Get the directory where the executable is located
    BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

    # Create screen for setup (also reused by the first-run language picker)
    screen = pygame.display.set_mode((730, 420))
    pygame.display.set_caption("PA Simulator")

    # First-run language picker. Settings file absent or missing 'language' →
    # show picker; otherwise skip straight to setup with the saved language.
    settings = i18n.load_settings()
    lang = settings.get("language")
    if lang not in i18n.SUPPORTED_LANGS:
        i18n.init(i18n.detect_default_lang())  # so picker chrome can render
        chosen = LanguagePicker(screen).run()
        if chosen is None:
            print("Language selection cancelled. Exiting.")
            pygame.quit()
            return
        lang = chosen
        settings["language"] = lang
        i18n.save_settings(settings)
    i18n.init(lang)

    # Run setup screen to select route + OCR Auto-PA toggle/lead/interval
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
    auto_input = config.get("auto_input", False)
    driver = None
    try:
        sim = PASimulator(config["work_dir"], config["route_data"], auto_input=auto_input)
        if auto_input:
            from auto_input import AutoDriver

            driver = AutoDriver(sim, lead_m=config.get("lead_m", 900), interval_s=config.get("interval_s", 5))
            driver.start()
        sim.run()
    except Exception as e:
        print(f"Error running simulator: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if driver is not None:
            driver.stop()
        pygame.quit()


if __name__ == "__main__":
    main()

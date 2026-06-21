"""PA Simulator - Entry Point

A Japanese Train PA (Public Address) Simulator with pygame-based
visual display and audio playback with loudness normalization.
"""

import os
import pygame

# Suppress pygame welcome message
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import i18n
import update_check
from language_picker import LanguagePicker
from setup import SetupScreen
from app import PASimulator


def _run_tutorial(screen_size: tuple[int, int]) -> bool:
    """Resize the display to the tutorial's 1100×500 window, run it, then
    restore the setup-sized display. Returns True if the tutorial actually
    ran end-to-end (Done was pressed); False on Skip / window-close / asset
    failure.

    Sized window is owned by the tutorial — we set_mode here, hand the
    display surface off, and restore the original size on return. Mixer +
    pygame stay alive across the transition; no full quit happens.
    """
    from tutorial import Tutorial, WINDOW_H, WINDOW_W

    pygame.display.set_mode((WINDOW_W, WINDOW_H))
    try:
        tut = Tutorial(pygame.display.get_surface())
        completed = tut.run()
    finally:
        # Restore the setup screen's size so SetupScreen draws into the right surface.
        pygame.display.set_mode(screen_size)
    return completed


def main():
    """Main entry point for the PA Simulator."""
    # Initialize pygame for the setup screen
    pygame.init()
    pygame.mixer.init()

    # Kick off the fail-silent update check early so its 3s network window
    # overlaps the picker/setup screens; the setup screen polls the result.
    update_check.check_async()

    # Repo root (dev) / alongside-exe (frozen) — single canonical helper.
    from app_paths import project_root

    BASE_DIR = str(project_root())

    # Create screen for setup (also reused by the first-run language picker)
    SETUP_SIZE = (730, 420)
    screen = pygame.display.set_mode(SETUP_SIZE)
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

    # First-run OOBE tutorial. Runs once after the language picker, before
    # setup. Set ``oobe_completed=True`` regardless of how the tutorial
    # finished (Done / Skip / asset-missing) so we don't re-prompt on next
    # launch — a "replay" affordance lives on the setup screen.
    if not settings.get("oobe_completed"):
        _run_tutorial(SETUP_SIZE)
        settings["oobe_completed"] = True
        i18n.save_settings(settings)

    # Run setup screen to select route. The "? Tutorial" replay button shows
    # only when oobe_completed=True (it's a re-run affordance, not a first-run
    # gate). Loop in case the user clicks it: run tutorial, return to setup.
    # OCR Auto-PA toggle is always available on the setup screen. It stays
    # opt-in: enabling goes through the pill, which fires the consent
    # disclaimer and persists to settings["auto_input"]. Default OFF — OCR
    # never starts without the user's explicit consent.
    setup = SetupScreen(
        screen,
        show_tutorial_button=settings.get("oobe_completed", False),
    )
    audio_dir = os.path.join(BASE_DIR, "audio")
    setup.scan_routes(audio_dir)

    while True:
        config = setup.run()
        if config is None:
            print("No route selected. Exiting.")
            pygame.quit()
            return
        action = config.get("action")
        if action == "run_tutorial":
            _run_tutorial(SETUP_SIZE)
            continue  # re-show setup
        if action == "select":
            break
        # Unknown action: defensive bail.
        print(f"Unknown setup action: {action!r}. Exiting.")
        pygame.quit()
        return

    # Clean up setup screen
    pygame.display.quit()

    # Start simulator with selected configuration
    auto_input = config.get("auto_input", False)
    driver = None
    try:
        sim = PASimulator(config["work_dir"], config["route_data"], auto_input=auto_input, model=config.get("model"))
        if auto_input:
            from auto_input import AutoDriver

            driver = AutoDriver(sim, lead_m=config.get("lead_m", 900), interval_s=config.get("interval_s", 5))
            sim.auto_driver = driver  # exposes pause toggle to debug-panel click handler
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

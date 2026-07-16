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
from setup import SetupScreen
from app import PASimulator

SETUP_SIZE = (730, 420)  # classic setup / OOBE tutorial window
TIMS_SIZE = (730, 610)  # TIMS-console setup flow window (taller)


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


def _run_setup(args, settings, base_dir):
    """Show the setup flow (TIMS or classic) and return a launch config, or None to exit. Owns its own
    display creation so it can be re-entered after a drive returns Home (band Home button)."""
    if not args.classic:
        # TIMS-console setup flow (setup_tims), own-window 730×610 — now the DEFAULT flow.
        from setup_tims import run as run_tims

        pygame.display.set_mode(TIMS_SIZE)
        pygame.display.set_caption("PA Simulator")
        return run_tims(pygame.display.get_surface())
    # Classic setup screen. The "? Tutorial" replay button shows only when oobe_completed=True (a re-run
    # affordance, not a first-run gate). Loop in case the user clicks it: run tutorial, return to setup.
    screen = pygame.display.set_mode(SETUP_SIZE)
    pygame.display.set_caption("PA Simulator")
    setup = SetupScreen(screen, show_tutorial_button=settings.get("oobe_completed", False))
    setup.scan_routes(os.path.join(base_dir, "audio"))
    while True:
        config = setup.run()
        if config is None:
            return None
        action = config.get("action")
        if action == "run_tutorial":
            _run_tutorial(SETUP_SIZE)
            continue
        if action == "select":
            return config
        print(f"Unknown setup action: {action!r}. Exiting.")
        return None


def _run_drive(config):
    """Construct + run the simulator for one drive. Returns "home" (band Home → return to the setup
    screen) or "quit" (window close / ESC → full app exit). Stops the auto-driver thread on the way out."""
    auto_input = config.get("auto_input", False)
    driver = None
    action = "quit"
    try:
        sim = PASimulator(config["work_dir"], config["route_data"], auto_input=auto_input, model=config.get("model"))
        start_idx = config.get("start_idx")
        if start_idx:  # setup_tims start-station selection → land there (classic setup has no start_idx)
            sim.jump_to_stop(start_idx)
        if auto_input:
            from auto_input import AutoDriver

            driver = AutoDriver(sim, lead_m=config.get("lead_m", 900), interval_s=config.get("interval_s", 3))
            sim.auto_driver = driver  # exposes pause toggle to the band click handler
            driver.start()
        action = sim.run() or "quit"
    except Exception as e:
        print(f"Error running simulator: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if driver is not None:
            driver.stop()
    return action


def main():
    """Main entry point for the PA Simulator."""
    import argparse

    parser = argparse.ArgumentParser(description="Japanese Train PA Simulator")
    parser.add_argument(
        "--classic",
        action="store_true",
        help="Launch the classic setup screen instead of the default TIMS-console setup flow (setup_tims)",
    )
    args = parser.parse_args()

    # Initialize pygame for the setup screen
    pygame.init()
    pygame.mixer.init()

    # Pin every window created from here on (setup flow, tutorials, sim) always-on-top — the app is a
    # companion overlay for the game. One seam wraps set_mode so no screen has to remember to re-pin.
    import window_utils

    window_utils.install_topmost_hook()

    # Kick off the fail-silent update check early so its 3s network window
    # overlaps the setup screens; the setup screen polls the result.
    update_check.check_async()

    # Repo root (dev) / alongside-exe (frozen) — single canonical helper.
    from app_paths import project_root

    BASE_DIR = str(project_root())

    # No premature window here — the setup flow (_run_setup) and the classic OOBE tutorial each create
    # their own correctly-sized window, so creating one now would only flash a blank frame before the
    # handoff. (Used to exist for the removed first-run LanguagePicker — critical_lessons §6.)

    # Language resolution — NO standalone first-run picker. Use the saved choice, else the OS-locale
    # default; the TIMS home's language knobs own runtime switching AND persist the choice. Persist the
    # detected default on genuine first-run so settings.json is initialized deterministically. (Removing
    # the pre-TIMS grey LanguagePicker: it was stale + redundant beside the home knobs — critical_lessons §6.)
    settings = i18n.load_settings()
    lang = i18n.resolve_language(settings)  # saved-or-detect; pure + screen-free (no first-run picker)
    if settings.get("language") != lang:  # genuine first-run (absent) or corrupt value → persist deterministically
        settings["language"] = lang
        i18n.save_settings(settings)
    i18n.init(lang)

    # First-run OOBE tutorial (CLASSIC setup only). Runs once after language resolution, before setup.
    # Set ``oobe_completed=True`` regardless of how the tutorial finished (Done / Skip / asset-missing)
    # so we don't re-prompt on next launch — a "replay" affordance lives on the setup screen.
    # The TIMS flow (default) does its OWN OOBE: the 教學 card flashes until the first visit (home._mark_oobe_done
    # persists the flag), so skip the forced fullscreen tutorial there — only the classic path runs it.
    if args.classic and not settings.get("oobe_completed"):
        _run_tutorial(SETUP_SIZE)
        settings["oobe_completed"] = True
        i18n.save_settings(settings)

    # Setup ↔ drive loop. A drive's band Home button returns here to re-pick a route (run() → "home");
    # window close / ESC ends the drive with "quit" and exits. OCR Auto-PA stays opt-in inside setup.
    while True:
        config = _run_setup(args, settings, BASE_DIR)
        if config is None:
            print("No route selected. Exiting.")
            pygame.quit()
            return
        # Tear down the setup window before the drive builds its own (taller, panel-carved) window.
        pygame.display.quit()
        action = _run_drive(config)
        if action != "home":
            break  # "quit" → full exit; anything else is defensive
        # "home": pygame / fonts / mixer are still alive (drive did display.quit only) → re-show setup.
    pygame.quit()


if __name__ == "__main__":
    main()

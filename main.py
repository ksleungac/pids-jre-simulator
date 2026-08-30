# SPDX-License-Identifier: MIT
"""PA Simulator - Entry Point

A Japanese Train PA (Public Address) Simulator with pygame-based
visual display and audio playback with loudness normalization.
"""

import os
import sys

# CONTRACT: console encoding is declared HERE, at the process entry, before anything prints.
# A Windows console defaults to cp1252, which has no mapping for the arrows, ellipses and
# em-dashes our diagnostics use — so `print` RAISES rather than mojibaking, and a raise inside
# a worker kills that whole thread while the app window carries on looking healthy (#136: the
# AutoDriver died on one `→`, taking OCR auto-drive down for the session). Doing it at the
# entry rather than inside the thread keeps this process-global state declared at a
# deterministic point — `critical_lessons.md § 3`'s corollary.
# A windowed build has no stdout at all, so both halves are optional by construction.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import pygame

# Suppress pygame welcome message
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import i18n
import update_check
from app import PASimulator

TIMS_SIZE = (730, 610)  # TIMS-console setup flow window


def _run_setup():
    """Show the TIMS setup flow and return a launch config, or None to exit.

    Owns its own display creation so it can be re-entered after a drive returns
    Home (band Home button). The pre-TIMS classic `SetupScreen` and its forced
    first-run fullscreen tutorial were retired 2026-07-30 — TIMS is the only flow,
    and it does its own OOBE (the 教學 card flashes until visited,
    `tims.setup.home._mark_oobe_done` persisting `oobe_completed`).
    """
    from tims.setup import run as run_tims

    pygame.display.set_mode(TIMS_SIZE)
    pygame.display.set_caption("PA Simulator")
    return run_tims(pygame.display.get_surface())


def _run_drive(config):
    """Construct + run the simulator for one drive. Returns "home" (band Home → return to the setup
    screen) or "quit" (window close / ESC → full app exit). Stops the auto-driver thread on the way out."""
    auto_input = config.get("auto_input", False)
    driver = None
    action = "quit"
    try:
        sim = PASimulator(config["work_dir"], config["route_data"], auto_input=auto_input, model=config.get("model"))
        start_idx = config.get("start_idx")
        if start_idx is not None:  # tims setup start-station selection → land there; idx 0 is a valid target
            sim.jump_to_stop(start_idx)
        if auto_input:
            from auto_input import AutoDriver

            driver = AutoDriver(
                sim,
                lead_m=config.get("lead_m", 900),
                interval_s=config.get("interval_s", 3),
            )
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
    import frame_stream

    # DPI awareness FIRST — before pygame creates any window, and before anything can import dxcam
    # (which declares it as an import side effect, so the app used to be unaware for setup and aware
    # for an OCR drive). Must precede pygame.init(); awareness is one-way and only takes effect for
    # windows created after it. See window_utils.declare_dpi_awareness.
    import window_utils

    window_utils.declare_dpi_awareness()

    # Initialize pygame for the setup screen
    pygame.init()
    pygame.mixer.init()

    # Pin every window created from here on (setup flow, tutorials, sim) always-on-top — the app is a
    # companion overlay for the game. One seam wraps set_mode so no screen has to remember to re-pin.
    window_utils.install_topmost_hook()

    # The band's hover QR draws on top of whatever the screen painted, so it hangs off flip/update
    # rather than off band.render — same one-seam reason as the pin above.
    from tims import band as _band

    _band.install_overlay_hook()

    # Window mirroring (off by default). Owned HERE rather than by PASimulator: the setup<->drive
    # loop below rebuilds a sim per drive, so a sim-owned server would hit a bind failure on drive #2.
    # Living above the loop also means the stream spans setup, tutorial and drive without dropping.
    # The mode + port come from the TIMS 設定 page. Read straight from settings (not via i18n.init,
    # which happens further down) — load_settings is a plain JSON read and does not care about the
    # language having been resolved yet.
    _stream_settings = i18n.load_settings()
    stream_host = frame_stream.resolve_bind_host(_stream_settings.get("stream_mode"))
    if stream_host is not None:
        # Both values go through frame_stream's cleaners — settings.json is hand-editable and is
        # read here BEFORE any window exists, so a bad value must degrade, never raise.
        urls = frame_stream.start(stream_host, frame_stream.clean_port(_stream_settings.get("stream_port")))
        if urls:
            # Several candidates when a VPN or virtual adapter is present — the default route is
            # often the tunnel, not the Wi-Fi the phone is on. The band shows them too, clickable.
            print("[stream] mirroring this window at:")
            for u in urls:
                print(f"[stream]     {u}")

    # Kick off the fail-silent update check early so its 3s network window
    # overlaps the setup screens; the setup screen polls the result.
    update_check.check_async()

    # No premature window here — the setup flow (_run_setup) creates its own correctly-sized window, so
    # creating one now would only flash a blank frame before the handoff. (Used to exist for the removed
    # first-run LanguagePicker — critical_lessons §6.)

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

    # No forced first-run tutorial: TIMS owns OOBE itself — the 教學 card flashes until the first visit
    # and `tims.setup.home._mark_oobe_done` persists `oobe_completed`. The classic path's fullscreen
    # gate was retired with it (2026-07-30); the settings key stays, TIMS reads it.

    # Setup ↔ drive loop. A drive's band Home button returns here to re-pick a route (run() → "home");
    # window close / ESC ends the drive with "quit" and exits. OCR Auto-PA stays opt-in inside setup.
    while True:
        config = _run_setup()
        if config is None:
            print("No route selected. Exiting.")
            frame_stream.stop()
            pygame.quit()
            return
        # Tear down the setup window before the drive builds its own (taller, panel-carved) window.
        pygame.display.quit()
        action = _run_drive(config)
        if action != "home":
            break  # "quit" → full exit; anything else is defensive
        # "home": pygame / fonts / mixer are still alive (drive did display.quit only) → re-show setup.
    frame_stream.stop()
    pygame.quit()


if __name__ == "__main__":
    main()

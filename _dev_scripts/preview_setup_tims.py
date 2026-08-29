# SPDX-License-Identifier: MIT
"""Dev preview launcher for the tims.setup package (home menu + sub-screens).

The screens live in the production package `tims/setup/`; this launcher is the dev-only
preview entry that used to be each draft's `__main__`. Production never imports `_dev_scripts/`
— this imports the OTHER way (dev → production), which is allowed.

  uv run _dev_scripts/preview_setup_tims.py                          # home menu (click-navigates to all)
  uv run _dev_scripts/preview_setup_tims.py --screen pa             # PA-setting page (案内設定)
  uv run _dev_scripts/preview_setup_tims.py --screen route          # route / station / run-pattern picker
  uv run _dev_scripts/preview_setup_tims.py --screen home --screenshot home.png   # static render
  uv run _dev_scripts/preview_setup_tims.py --screen stream                       # 設定 (remote control)

Mirroring follows the SAVED setting, same as the app — turn it on in the 設定 screen and the band's
green address rows appear here too.
"""

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252; the debug prints carry → / kanji

sys.path.insert(0, ".")

import frame_stream  # noqa: E402
import i18n  # noqa: E402
from tims import band  # noqa: E402
from tims.setup import home, pa_setting, route_select, model_select, ocr_setting, stream_setting, tutorial_select, tutorial_basic  # noqa: E402

_SCREENS = {
    "home": home,
    "pa": pa_setting,
    "route": route_select,
    "model": model_select,
    "tutorial": tutorial_select,
    "basic": tutorial_basic,
    "stream": stream_setting,
}
# ocr_setting hosts two sub-views selected by a `view` arg (consent gate vs the steppers settings).
_OCR_VIEWS = {"consent": "consent", "ocrset": "settings"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", choices=list(_SCREENS) + list(_OCR_VIEWS), default="home", help="which screen to preview (default: home)")
    ap.add_argument("--screenshot", metavar="PATH", help="static render to PATH instead of interactive")
    args = ap.parse_args()

    # The band draws its mirror-address rows only while the server is really up, so the preview
    # starts it exactly as main.py does — from the SAVED setting, with no flag of its own. A dev-only
    # override here would be a second way to answer a question the 設定 page now owns, and the point
    # of previewing is to see what the app does.
    # Order is not load-bearing — both hooks are idempotent independent of it (band keeps a module
    # flag, and the present hook walks the wrapper chain rather than reading only its top). Kept
    # here simply to match main.py.
    band.install_overlay_hook()
    s = i18n.load_settings()
    host = frame_stream.resolve_bind_host(s.get("stream_mode"))
    if host is not None:
        for u in frame_stream.start(host, frame_stream.clean_port(s.get("stream_port"))) or []:
            print(f"[stream] {u}")

    if args.screen in _OCR_VIEWS:
        view = _OCR_VIEWS[args.screen]
        if args.screenshot:
            ocr_setting.save_screenshot(args.screenshot, view)
        else:
            ocr_setting.run_interactive(view)
        return
    mod = _SCREENS[args.screen]
    if args.screenshot:
        mod.save_screenshot(args.screenshot)
    else:
        mod.run_interactive()


if __name__ == "__main__":
    main()

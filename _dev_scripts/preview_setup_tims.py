"""Dev preview launcher for the setup_tims package (home menu + sub-screens).

The screens live in the production package `setup_tims/`; this launcher is the dev-only
preview entry that used to be each draft's `__main__`. Production never imports `_dev_scripts/`
— this imports the OTHER way (dev → production), which is allowed.

  uv run _dev_scripts/preview_setup_tims.py                          # home menu (click-navigates to all)
  uv run _dev_scripts/preview_setup_tims.py --screen pa             # PA-setting page (案内設定)
  uv run _dev_scripts/preview_setup_tims.py --screen route          # route / station / run-pattern picker
  uv run _dev_scripts/preview_setup_tims.py --screen home --screenshot home.png   # static render
"""

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252; the debug prints carry → / kanji

sys.path.insert(0, ".")

from setup_tims import home, pa_setting, route_select, model_select, ocr_setting  # noqa: E402

_SCREENS = {"home": home, "pa": pa_setting, "route": route_select, "model": model_select}
# ocr_setting hosts two sub-views selected by a `view` arg (consent gate vs the steppers settings).
_OCR_VIEWS = {"consent": "consent", "ocrset": "settings"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", choices=list(_SCREENS) + list(_OCR_VIEWS), default="home", help="which screen to preview (default: home)")
    ap.add_argument("--screenshot", metavar="PATH", help="static render to PATH instead of interactive")
    args = ap.parse_args()
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

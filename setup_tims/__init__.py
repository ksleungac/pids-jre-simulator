"""setup_tims — the TIMS-console setup flow.

Home menu (報站設定 / 教學 / 設定 / 行車記錄) → 案内設定 (C07AA) PA-setting page →
route grid (C07AB) → start-station grid (C07AC) → run-pattern table (C07AF), all
under a persistent OCR status band. Promoted from the `_dev_scripts/*_draft.py`
sketches.

The persistent status band + its shared chrome now live at project ROOT
(``status_band.py`` / ``tims_chrome.py``), shared with the live in-drive OCR panel
(``app.py``). This package keeps only its own window dims (``dims.py``) + screens.

Modules:
  dims.py         setup-window dims (SCREEN_W/H, BG_COLOR)
  home.py         page-1 menu (action cards / language knobs / version tag)
  pa_setting.py   案内設定 (C07AA) PA-setting page
  route_select.py route / start-station / run-pattern picker (C07AB/AC/AF)

Production entry: ``run(screen) -> config | None`` (re-exported from ``home``) runs the home menu on an
existing display and returns a launch-config dict shaped like ``setup.SetupScreen.run()`` (action /
work_dir / route_data / model / start_idx) when the user commits a route and 起動s, else None. main.py
calls it by default (``--classic`` opts back into the legacy setup). Preview the screens standalone via
``_dev_scripts/preview_setup_tims.py``.
"""

from status_band import BAND_H  # noqa: F401
from .dims import BG_COLOR, SCREEN_H, SCREEN_W  # noqa: F401
from .home import run  # noqa: F401

"""setup_tims — the TIMS-console setup flow.

Home menu (報站設定 / 教學 / 設定 / 行車記錄) → 案内設定 (C07AA) PA-setting page →
route grid (C07AB) → start-station grid (C07AC) → run-pattern table (C07AF), all
under a persistent OCR status band. Promoted from the `_dev_scripts/*_draft.py`
sketches.

Modules:
  band.py         persistent OCR status band + shared screen dims (SCREEN_W/H, BAND_H, BG_COLOR)
  chrome.py       shared chrome primitives (title row)
  home.py         page-1 menu (action cards / language knobs / version tag)
  pa_setting.py   案内設定 (C07AA) PA-setting page
  route_select.py route / start-station / run-pattern picker (C07AB/AC/AF)

Production entry: ``run(screen) -> config | None`` (re-exported from ``home``) runs the home menu on an
existing display and returns a launch-config dict shaped like ``setup.SetupScreen.run()`` (action /
work_dir / route_data / model / start_idx) when the user commits a route and 起動s, else None. main.py
calls it behind ``--tims``. Preview the screens standalone via ``_dev_scripts/preview_setup_tims.py``.
"""

from .band import BAND_H, BG_COLOR, SCREEN_H, SCREEN_W  # noqa: F401
from .home import run  # noqa: F401

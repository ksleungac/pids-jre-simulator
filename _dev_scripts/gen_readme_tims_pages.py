# SPDX-License-Identifier: MIT
"""Regenerate the two TIMS README screenshots that the standard preview harness
can't reach in a single CLI call:
  - docs/assets/08-tims-pa-setting.png   — PA-setting page in the READY state (a route
    must be committed so the launch cluster unlocks; save_screenshot renders the
    locked state).
  - docs/assets/09-tims-diagram-select.png — the C07AF diagram-choice page ALONE
    (route_select.save_screenshot stacks all three picker screens into one PNG).

    uv run _dev_scripts/gen_readme_tims_pages.py

Dev-only; does not ship. Writes straight into docs/assets/ (tracked README images)."""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "hide")
sys.path.insert(0, ".")

import pygame  # noqa: E402

import i18n  # noqa: E402
import tims.band as band  # noqa: E402
from app_paths import project_root  # noqa: E402
from tims.setup import pa_setting, route_select  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

LANG = "zh_HK"  # develop/preview locale (chrome is i18n; route/station names stay Japanese)
pygame.init()
pygame.font.init()
i18n.init(LANG)
pa_setting.ACTIVE_LANG = LANG
route_select.ACTIVE_LANG = LANG
band.ACTIVE_LANG = LANG

groups = route_select.grouped_routes(route_select.load_routes())


def _find(name, fallback=0):
    for i, (n, _) in enumerate(groups):
        if n == name:
            return i
    print(f"  (route {name!r} not found; using group index {fallback})")
    return fallback


# ── 08: READY PA-setting — commit the Yamanote route so the launch cluster arms ──
name, variants = groups[_find("山手線")]
v0 = variants[0]
stations = [v0["stops"][i] for i in v0["stop_idxs"]]
pa_setting._apply_selection({"route": v0, "start_name": stations[0], "pattern_no": 1})
surf = pygame.Surface((pa_setting.SCREEN_W, pa_setting.SCREEN_H))
pa_setting.render(surf)
out8 = str(project_root() / "assets" / "08-tims-pa-setting.png")
pygame.image.save(surf, out8)
print(f"saved {out8}  (committed: {name})")

# ── 09: DIAGRAM-choice (C07AF) alone — multi-variant line so both tables fill ──
cname, cvars = groups[_find("中央線快速", _find("京浜東北線", 0))]
cv0 = cvars[0]
cstations = [cv0["stops"][i] for i in cv0["stop_idxs"]]
btn_font = i18n.pixel_font_for_lang(LANG, route_select.BTN_NATIVE)
s = pygame.Surface((route_select.SCREEN_W, route_select.SCREEN_H))
route_select._render_diagram(s, cname, cstations[0], cv0["end"], cvars, selected_idx=0, flash_on=True, btn_font=btn_font)
out9 = str(project_root() / "assets" / "09-tims-diagram-select.png")
pygame.image.save(s, out9)
print(f"saved {out9}  (line: {cname}, {len(cvars)} variants)")

pygame.quit()

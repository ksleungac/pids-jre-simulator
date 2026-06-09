"""Offline render of the auto-input debug panel — no game, no OCR.

`draw_debug_panel` is a pure render (status dict in, surface out), so we can
exercise any panel state by hand-building the status dict. Used to eyeball the
re-aligning (re-entry consensus) indicator and its precedence vs the auto-played
chip / Played count, across all three locales, without the live game.

    uv run _dev_scripts/preview_panel.py

Writes PNGs to _experiments/panel_preview/. Dev-only; does not ship.
"""

import os
import sys
import time
from types import SimpleNamespace

# Headless SDL — no real window needed to render onto a Surface + save PNG.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n  # noqa: E402
from app_paths import project_root  # noqa: E402
from auto_input import draw_debug_panel  # noqa: E402
from constants import DEBUG_PANEL_HEIGHT  # noqa: E402

S_WIDTH = 730

# Fake route — kanji names exercise the CJK name-font path on line 1.
STOPS = [
    {"name": "渋谷", "pa": []},
    {"name": "原宿", "pa": ["x"]},
    {"name": "代々木", "pa": ["x"]},
    {"name": "新宿", "pa": ["x", "y"]},
    {"name": "新大久保", "pa": ["x"]},
    {"name": "高田馬場", "pa": ["x", "y", "z"]},
]

# App parked at 高田馬場 (1C) while OCR sees the game cruising — the desync that
# re-entry corrects. segment_start == curr_stop because the app is parked.
SIM_STATE = SimpleNamespace(curr_stop=5, cnt_pa=0, at_station=True)

_BASE_OCR = {
    "badge": "MOVING",
    "badge_diff": 8.0,
    "speed": 62,
    "speed_score": 0.97,
    "distance": 1180,
    "distance_score": 0.95,
    "stopping_offset_cm": None,
    "stopping_offset_score": None,
    "speed_limit": 95,
    "speed_limit_score": 0.96,
    "segment_start_stop": 5,
    "departure_observed": False,
    "arrival_observed": False,
    "at_station_observed": True,
    "inferred_state": "CRUISING",
    "paused": False,
}

# Three states to compare the line-1 tail precedence:
#   realigning — re-entry latched, awaiting 2nd agreeing probe (amber)
#   played     — steady state, no pending re-entry (gray Played count)
SCENARIOS = {
    "realigning": {**_BASE_OCR, "reentry_pending": "1A"},
    "played": {**_BASE_OCR, "reentry_pending": None},
    "autoplayed": {
        **_BASE_OCR,
        "reentry_pending": None,
        "last_fire": {"type": "departure", "ts": time.time()},
    },
}

LOCALES = ["en", "zh_HK", "zh_CN"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    pygame.init()
    pygame.display.set_mode((S_WIDTH, DEBUG_PANEL_HEIGHT))

    out_dir = project_root() / "_experiments" / "panel_preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    pad = 6
    for scen, status in SCENARIOS.items():
        # Stack the three locales vertically into one image, labeled by filename.
        stacked = pygame.Surface((S_WIDTH, (DEBUG_PANEL_HEIGHT + pad) * len(LOCALES) - pad))
        stacked.fill((0, 0, 0))
        for i, loc in enumerate(LOCALES):
            i18n.init(loc)
            panel = pygame.Surface((S_WIDTH, DEBUG_PANEL_HEIGHT))
            draw_debug_panel(panel, status, SIM_STATE, STOPS)
            stacked.blit(panel, (0, i * (DEBUG_PANEL_HEIGHT + pad)))
        path = out_dir / f"panel_{scen}.png"
        pygame.image.save(stacked, str(path))
        print(f"wrote {path}  (locales top→bottom: {', '.join(LOCALES)})")

    pygame.quit()


if __name__ == "__main__":
    main()

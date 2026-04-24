"""Standalone preview for the Upper LCD renderer (E235-1000 series).

Usage:
  uv run preview_upper_lcd.py                                     # interactive (MOCK data)
  uv run preview_upper_lcd.py --route yamanote --stop 8 --pa 0    # interactive (real route)
  uv run preview_upper_lcd.py --screenshot out.png --mode english --stop 2 --pa 1

Controls (interactive):
  PageDown  next station       PageUp  next PA phase       ESC  quit

--route accepts: a path to route.json, a directory containing one, or a shorthand
like 'yamanote' / 'chuo/916H' (resolved under audio/).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pygame

from displays.base import DisplayMode
from displays.train_models.e235_1000 import UpperDisplay
from displays.train_models.e235_1000.upper_lcd import S_WIDTH, S_HEIGHT

# =============================================================================
# Mock data (used when --route is not given)
# =============================================================================

MOCK_ROUTE_DATA = {
    "route": "山手線",
    "type": "快速",
    "dest": "君津",
    "dest_furigana": "とうきょう",
    "color": [0, 128, 0],
    "type_color": [150, 40, 0],
}

# Mix of stations that have code_3 in data/stations.json (東京, 新橋, 品川,
# 高輪ゲートウェイ) and stations that do not (有楽町, 久里浜) — good coverage
# for verifying both badge layouts in one run.
MOCK_STOPS = [
    {"name": "東京", "furigana": "とうきょう", "english": "Tōkyō", "sta_code": "JY03"},
    {"name": "有楽町", "furigana": "ゆうらくちょう", "english": "Yūrakuchō", "sta_code": "JY02"},
    {"name": "新橋", "furigana": "しんばし", "english": "Shimbashi", "sta_code": "JK29"},
    {"name": "品川", "furigana": "しながわ", "english": "Shinagawa", "sta_code": "JO25"},
    {"name": "高輪ゲートウェイ", "furigana": "たかなわげーとうぇい", "english": "Takanawa Gateway", "sta_code": "JY26"},
    {"name": "久里浜", "furigana": "くりはま", "english": "Kurihama", "sta_code": "JO01"},
]


# =============================================================================
# Real route loading
# =============================================================================

MODE_MAP = {"kanji": DisplayMode.KANJI, "furigana": DisplayMode.FURIGANA, "english": DisplayMode.ENGLISH}
PA_PREFIX_LABELS = ["次は", "まもなく", "ただいま"]


def _resolve_route_path(spec: str) -> Path:
    """Resolve a --route arg into an actual route.json path.

    Accepts: a path, a directory containing route.json, or a shorthand like
    'yamanote' / 'chuo/916H' (probed under audio/).
    """
    candidates = [
        Path(spec),
        Path(spec) / "route.json",
        Path("audio") / spec,
        Path("audio") / spec / "route.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    for base in (Path(spec), Path("audio") / spec):
        if base.is_dir():
            matches = sorted(base.glob("*/route.json")) or sorted(base.glob("**/route.json"))
            if matches:
                return matches[0]
    raise FileNotFoundError(f"Could not resolve --route {spec!r} to a route.json file")


def load_real_route(spec: str):
    """Load a real route.json and merge data/translations.json into each stop.

    Thin subset of app.py's route loading — only what the Upper LCD needs.
    """
    route_path = _resolve_route_path(spec)
    with open(route_path, encoding="utf-8") as f:
        route_data = json.load(f)

    trans_path = Path("data/translations.json")
    translations = json.loads(trans_path.read_text(encoding="utf-8")) if trans_path.is_file() else {}

    stops = []
    for stop in route_data.get("stops", []):
        merged = dict(stop)
        name = stop.get("name", "")
        if name in translations:
            merged.setdefault("furigana", translations[name].get("furigana", ""))
            merged.setdefault("english", translations[name].get("english", ""))
        stops.append(merged)

    print(f"[preview] Loaded {route_path}: route={route_data.get('route')!r}, {len(stops)} stops")
    return route_data, stops


# =============================================================================
# Main
# =============================================================================


def parse_args():
    parser = argparse.ArgumentParser(description="Upper LCD Preview (E235-1000)")
    parser.add_argument("--screenshot", type=str, help="Save one frame to file and exit")
    parser.add_argument("--mode", type=str, choices=list(MODE_MAP), default=None, help="Force display mode (default: cycles automatically)")
    parser.add_argument("--stop", type=int, default=0, help="Initial station index (default: 0)")
    parser.add_argument("--pa", type=int, default=0, help="PA phase: 0=次は/Next, 1=まもなく/Arriving, 2=ただいま/Now stopping (default: 0)")
    parser.add_argument(
        "--route",
        type=str,
        default=None,
        help="Load a real route.json instead of MOCK_STOPS. " "Accepts a path, a directory, or a shorthand (e.g. 'yamanote', 'chuo/916H').",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    pygame.init()
    screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
    pygame.display.set_caption("Upper LCD Preview (E235-1000) - PageDown=next station, PageUp=next PA, ESC=quit")
    clock = pygame.time.Clock()

    route_data, stops = load_real_route(args.route) if args.route else (MOCK_ROUTE_DATA, MOCK_STOPS)
    display = UpperDisplay(screen, route_data, stops)

    if args.mode:
        display.mode_cycler.current_mode = MODE_MAP[args.mode]
        display.mode_cycler.enabled = False

    curr_stop = max(0, min(args.stop, len(stops) - 1))
    cnt_pa = args.pa
    display.set_state(curr_stop, cnt_pa)

    if args.screenshot:
        display.update()
        display.draw()
        pygame.image.save(screen, args.screenshot)
        print(f"Screenshot saved to {args.screenshot}")
        pygame.quit()
        return

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_PAGEDOWN:
                    curr_stop = (curr_stop + 1) % len(stops)
                    cnt_pa = 0
                    display.set_state(curr_stop, cnt_pa)
                    print(f"[DEBUG] Station: {stops[curr_stop]['name']}")
                elif event.key == pygame.K_PAGEUP:
                    cnt_pa = (cnt_pa + 1) % 3
                    display.set_state(curr_stop, cnt_pa)
                    print(f"[DEBUG] PA: {PA_PREFIX_LABELS[cnt_pa]}")

        display.update()
        display.draw()
        pygame.display.flip()
        clock.tick(15)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

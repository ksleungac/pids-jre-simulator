"""Preview utility for app chrome (setup screen + OCR disclaimer).

Mirrors `preview_display.py` for the LCD: renders one frame to a PNG so visual
iteration on chrome (theme, layout, fonts) doesn't require launching the full
app interactively. Especially useful when iterating on OOBE screens later.

Usage:
    uv run preview_chrome.py setup  --lang zh_HK --selected 3 --out preview_setup.png
    uv run preview_chrome.py setup  --lang en --auto-input on   # OCR pill ON
"""

import argparse
import os
import sys

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame

import i18n
from setup import SetupScreen


def render_setup(
    screen: pygame.Surface,
    lang: str,
    selected: int,
    audio_dir: str,
    auto_input: bool,
) -> None:
    """Render the route selection screen with the given selection + OCR state."""
    i18n.init(lang)
    setup = SetupScreen(screen)
    setup.scan_routes(audio_dir)
    if not setup.routes:
        print(f"No routes found under {audio_dir!r}; nothing to render.")
        sys.exit(2)
    setup.selected_idx = max(0, min(selected, len(setup.routes) - 1))
    setup.auto_input_enabled = auto_input
    setup.draw(setup.selected_idx)


def render_ocr_disclaimer(screen: pygame.Surface, lang: str, scroll_pct: int = 0) -> None:
    """Render the OCR disclaimer at a given scroll position (0–100%).

    Two-pass: first pass derives max_scroll, second pass renders at target."""
    i18n.init(lang)
    setup = SetupScreen(screen)
    screen.fill((42, 46, 58))
    _, _, max_scroll = setup._draw_ocr_disclaimer_panel(screen, scroll_y=0)
    scroll_y = int(max_scroll * max(0, min(100, scroll_pct)) / 100)
    screen.fill((42, 46, 58))
    setup._draw_ocr_disclaimer_panel(screen, scroll_y=scroll_y)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview chrome (setup / disclaimer) → PNG.")
    parser.add_argument("screen", choices=["setup", "disclaimer"])
    parser.add_argument("--lang", choices=i18n.SUPPORTED_LANGS, default="en")
    parser.add_argument("--selected", type=int, default=0, help="Selected row idx (setup only)")
    parser.add_argument("--audio-dir", default="audio")
    parser.add_argument("--auto-input", choices=["on", "off"], default="off", help="OCR Auto-PA pill state (setup only)")
    parser.add_argument("--scroll", type=int, default=0, metavar="PCT", help="Scroll position 0-100%% (disclaimer only)")
    parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        metavar="MS",
        help="Lock pygame.time.get_ticks() to this value (disclaimer only, for animation frame capture)",
    )
    parser.add_argument("--out", default="screenshot_chrome.png")
    args = parser.parse_args()

    pygame.init()
    pygame.mixer.init()
    win_w, win_h = (720, 560) if args.screen == "disclaimer" else (730, 420)
    surf = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption(f"Preview: {args.screen} · {args.lang}")

    if args.screen == "disclaimer":
        if args.ticks is not None:
            _fixed = args.ticks
            pygame.time.get_ticks = lambda: _fixed
        render_ocr_disclaimer(surf, args.lang, args.scroll)
    else:
        render_setup(surf, args.lang, args.selected, args.audio_dir, args.auto_input == "on")

    pygame.image.save(surf, args.out)
    print(f"saved: {args.out}")
    pygame.quit()


if __name__ == "__main__":
    main()

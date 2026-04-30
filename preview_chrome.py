"""Preview utility for app chrome (language picker + setup screen).

Mirrors `preview_display.py` for the LCD: renders one frame to a PNG so visual
iteration on chrome (theme, layout, fonts) doesn't require launching the full
app interactively. Especially useful when iterating on OOBE screens later.

Usage:
    uv run preview_chrome.py picker --lang en --out preview_picker_en.png
    uv run preview_chrome.py setup  --lang zh_HK --selected 3 --out preview_setup.png
    uv run preview_chrome.py setup  --lang en --auto-input on   # OCR pill ON
"""

import argparse
import os
import sys

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame

import i18n
from language_picker import LanguagePicker
from setup import SetupScreen


def render_picker(screen: pygame.Surface, lang: str, hover_idx: int | None) -> None:
    """Render the language picker. `hover_idx` overrides the auto-detect default."""
    i18n.init(lang)
    picker = LanguagePicker(screen)
    if hover_idx is not None:
        picker._on_select(hover_idx)
    picker.draw()


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview chrome (picker / setup) → PNG.")
    parser.add_argument("screen", choices=["picker", "setup"])
    parser.add_argument("--lang", choices=i18n.SUPPORTED_LANGS, default="en")
    parser.add_argument("--selected", type=int, default=0, help="Selected row idx (setup only)")
    parser.add_argument("--hover", type=int, default=None, help="Hovered row idx (picker only; 0=en, 1=zh_HK, 2=zh_CN)")
    parser.add_argument("--audio-dir", default="audio")
    parser.add_argument("--auto-input", choices=["on", "off"], default="off", help="OCR Auto-PA pill state (setup only)")
    parser.add_argument("--out", default="screenshot_chrome.png")
    args = parser.parse_args()

    pygame.init()
    pygame.mixer.init()
    surf = pygame.display.set_mode((730, 420))
    pygame.display.set_caption(f"Preview: {args.screen} · {args.lang}")

    if args.screen == "picker":
        render_picker(surf, args.lang, args.hover)
    else:
        render_setup(surf, args.lang, args.selected, args.audio_dir, args.auto_input == "on")

    pygame.image.save(surf, args.out)
    print(f"saved: {args.out}")
    pygame.quit()


if __name__ == "__main__":
    main()

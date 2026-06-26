"""Preview entry for the GREEN TIMS tutorial shell (tutorial_tims.py).

Interactive:   uv run preview_tutorial_tims.py            (click tabs, ESC to quit)
Headless:      uv run preview_tutorial_tims.py --screenshot out.png [--lang zh_HK] [--live]

Headless renders a single frame to a Surface (no window) so the layout can be smoke-tested without a
display loop. By default the 'normal' tab shows the layout block-out (no sim boot). Pass --live to
boot the real embedded walkthrough into the detail region for a full-integration screenshot — run it
under dummy SDL drivers headlessly: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy.
"""

import argparse
import sys

import pygame

import i18n
from tutorial_tims import WINDOW_SIZE, TimsTutorial


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH", help="render one frame headless and save to PATH")
    ap.add_argument("--lang", default="zh_HK", help="chrome language (en / zh_HK / zh_CN)")
    ap.add_argument("--live", action="store_true", help="boot the real embedded walkthrough (else 'normal' tab shows the block-out)")
    args = ap.parse_args()

    pygame.init()
    pygame.font.init()
    i18n.init(args.lang)

    if args.screenshot:
        # --live boots the LCD sim, whose renderer calls Surface.convert_alpha()
        # → needs a real display surface (set_mode), which works headless under
        # SDL_VIDEODRIVER=dummy. Layout-only needs no display.
        surf = pygame.display.set_mode(WINDOW_SIZE) if args.live else pygame.Surface(WINDOW_SIZE)
        TimsTutorial(surf, live=args.live).render(surf)
        pygame.image.save(surf, args.screenshot)
        print(f"saved {args.screenshot}  {WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}  live={args.live}")
        return

    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("TIMS tutorial (green build)")
    TimsTutorial(screen).run()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()

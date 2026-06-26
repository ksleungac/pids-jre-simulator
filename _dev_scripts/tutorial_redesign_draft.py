"""DRAFT mock — tutorial-screen redesign. NOT production; a layout sketch for the visual judge.
Window-in-window master-detail: a LEFT column of vertically-stacked TIMS buttons (one per feature
tutorial — 'normal usage' + 'OCR auto-PA'), and a RIGHT detail region hosting that tutorial.

Path (a): the 'normal usage' tutorial reuses the EXISTING interactive walkthrough (live LCD 730×420
+ progress strip + step side-panel), so the right region is the current ~1100×500 tutorial layout and
the tab column slots to its left → a wide window. This mock shows that at real proportions; the inner
tutorial chrome (progress / LCD / side panel) is blocked out as placeholders — reskinning it to TIMS
fonts + buttons is the next pass.

    uv run _dev_scripts/tutorial_redesign_draft.py
"""

import sys

import pygame

sys.path.insert(0, ".")

import i18n  # noqa: E402
from app_paths import project_root  # noqa: E402
from displays.train_models.e235_1000 import S_HEIGHT, S_WIDTH  # noqa: E402
from widgets import (  # noqa: E402
    _TUNEABLES_TIMS_BUTTON,
    draw_lowres_text,
    draw_tims_button,
)

ARK_NATIVE = 12


def pixel_font(lang):
    return i18n.pixel_font_for_lang(lang, ARK_NATIVE)


# fmt: off
# ── layout tuneables ──────────────────────────────────────────────────────────
MARGIN          = 16
BG_COLOR        = (62, 68, 80)

HEADER_TEXT     = "教學"           # screen title, top-left
HEADER_K        = 3
HEADER_COLOR    = (224, 232, 238)
HEADER_H        = 48

# left menu — vertically-stacked TIMS buttons, 4 chars on ONE line
TAB_W           = 150
TAB_H           = 70
TAB_GAP         = 8
TAB_K           = 2
ACTIVE_TAB      = 0
INACTIVE_SCRIM  = (40, 44, 54, 150)  # dims unselected tabs ("unlit"; yellow stays = PRESSED only)
MENU_GAP        = 16              # gap between the tab column and the detail region

# right detail region — the existing interactive tutorial, at real proportions
LCD_W, LCD_H    = S_WIDTH, S_HEIGHT   # 730 × 420 live-sim LCD
PROGRESS_H      = 64                   # top progress strip
SIDE_W          = 370                  # step text + Back/Next panel
REGION_SLACK_H  = 16                   # bottom breathing room under the LCD
REGION_W        = LCD_W + SIDE_W                      # 1100
REGION_H        = PROGRESS_H + LCD_H + REGION_SLACK_H # 500

# inner placeholder palette (mirrors current tutorial chrome; reskinned next pass)
PROGRESS_BG     = (44, 49, 60)
PANEL_BG        = (54, 60, 72)
LCD_BG          = (25, 25, 25)
PLACE_COLOR     = (150, 162, 178)

# recessed-frame border around the whole detail region ("window in window")
PANEL_BORDER_HI = (90, 100, 118)
PANEL_BORDER_LO = (14, 20, 30)
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

ACTIVE_LANG = "zh_HK"

BODY_TOP = MARGIN + HEADER_H + 8
REGION_X = MARGIN + TAB_W + MENU_GAP
SCREEN_W = REGION_X + REGION_W + MARGIN
SCREEN_H = BODY_TOP + REGION_H + MARGIN

# (key, label) per feature tutorial; 4-char CJK self-name on one line. Placeholder translations.
TABS = [
    ("normal", "基本操作"),  # normal usage
    ("ocr", "自動廣播"),  # OCR auto-PA
]

_TAB_TUNEABLES = {**_TUNEABLES_TIMS_BUTTON, "text_align": "center", "text_pad": 12, "text_max_k": TAB_K}


def _recessed_border(surf, rect):
    """Inverted bevel hint (light far edges, dark near edges) so the region reads as recessed."""
    pygame.draw.line(surf, PANEL_BORDER_LO, rect.topleft, (rect.right - 1, rect.top), 2)
    pygame.draw.line(surf, PANEL_BORDER_LO, rect.topleft, (rect.left, rect.bottom - 1), 2)
    pygame.draw.line(surf, PANEL_BORDER_HI, (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1), 2)
    pygame.draw.line(surf, PANEL_BORDER_HI, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom - 1), 2)


def _placeholder(surf, rect, fill, label, font):
    pygame.draw.rect(surf, fill, rect)
    draw_lowres_text(surf, label, pygame.Rect(rect.x, rect.centery - 16, rect.w, 32), font, PLACE_COLOR, max_k=2, align="center")


def main():
    pygame.init()
    pygame.font.init()

    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    surf.fill(BG_COLOR)
    font = pixel_font(ACTIVE_LANG)

    # ── header ────────────────────────────────────────────────────────────────
    draw_lowres_text(surf, HEADER_TEXT, pygame.Rect(MARGIN, MARGIN, 200, HEADER_H), font, HEADER_COLOR, max_k=HEADER_K, align="center")

    # ── left menu: vertically-stacked tabs ──────────────────────────────────────
    for i, (key, label) in enumerate(TABS):
        rect = pygame.Rect(MARGIN, BODY_TOP + i * (TAB_H + TAB_GAP), TAB_W, TAB_H)
        draw_tims_button(surf, rect, label, font=font, t=_TAB_TUNEABLES, state="normal")
        if i != ACTIVE_TAB:  # inactive = unlit (dim scrim)
            scrim = pygame.Surface((TAB_W, TAB_H), pygame.SRCALPHA)
            pygame.draw.rect(scrim, INACTIVE_SCRIM, scrim.get_rect(), border_radius=5)
            surf.blit(scrim, rect.topleft)

    # ── right detail region: existing interactive tutorial at real proportions ──
    rx, ry = REGION_X, BODY_TOP
    # progress strip (full region width)
    _placeholder(surf, pygame.Rect(rx, ry, REGION_W, PROGRESS_H), PROGRESS_BG, "進度列 progress stepper", font)
    # LCD (live sim) + step side-panel
    _placeholder(surf, pygame.Rect(rx, ry + PROGRESS_H, LCD_W, LCD_H), LCD_BG, "LCD 即時模擬 (live sim 730×420)", font)
    _placeholder(surf, pygame.Rect(rx + LCD_W, ry + PROGRESS_H, SIDE_W, REGION_H - PROGRESS_H), PANEL_BG, "步驟說明\n+ Back / Next", font)
    _recessed_border(surf, pygame.Rect(rx, ry, REGION_W, REGION_H))

    out = str(project_root() / "tutorial_draft.png")
    pygame.image.save(surf, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H})")


if __name__ == "__main__":
    main()

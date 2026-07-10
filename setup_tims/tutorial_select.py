"""Tutorial-selection page (教學選擇), reached from the home menu's 教學 action card. A simple
menu screen: a centered column of TIMS bevel buttons, one per feature tutorial. Clicking a button
enters that tutorial DIRECTLY — there is no 設定 confirm (unlike the route/station selection grids);
only a 返回 button (bottom-left) + the persistent band Home / ESC return to the menu.

Mirrors the model_select (番台選択) interaction model — click commits — rather than the route grid's
select→設定 pattern, because a tutorial menu navigates on click, it doesn't build up a config.

Today it lists ONE tutorial: OCR auto-PA (opens ocr_setting's read-only consent/how-it-works
walkthrough). More tutorials slot into TUTORIALS as they graduate (e.g. the normal-usage walkthrough).

Preview:  uv run _dev_scripts/preview_setup_tims.py --screen tutorial
"""

import pygame

import i18n
from app_paths import project_root
from widgets import draw_tims_button, press_transition, tims_button_size

import status_band as band
import tims_chrome as chrome
from .dims import BG_COLOR, SCREEN_H, SCREEN_W

ACTIVE_LANG = "zh_HK"  # UI language (carried in from the home menu; chrome is i18n)
SCREEN_CODE = "C07AD"  # placeholder register code (droppable, kept for TIMS fidelity — like the siblings)

# fmt: off
# ── layout tuneables (all derived coords flow from these) ─────────────────────
BTN_NATIVE   = 22          # tutorial-button label px (AA-off native)
BTN_W        = 320         # wide menu button (holds "OCR自動報站" comfortably)
BTN_H        = 64          # menu-button height
BTN_GAP      = 16          # vertical gap between stacked buttons
GRID_TOP     = 150         # first button top y (below band + title row)

BAR_NATIVE        = 22     # 返回 label px
BAR_Y_FROM_BOTTOM = 70     # 返回 TOP sits this far up from the screen bottom
BACK_X            = 68     # 返回 left edge (mirrors route_select's bottom bar)
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# (key, i18n label key). key drives the opener dispatch in run_on; more tutorials append here as they
# graduate. Each renders as one centered menu button; clicking enters that tutorial directly.
TUTORIALS = [
    ("basic", "setup_tims.tutorial.basic"),
    ("ocr", "setup_tims.tutorial.ocr"),
]

_BTN_T = chrome.BTN_LABEL  # center-natural crammed label (the page-button role)
_BAR_T = chrome.BTN_BAR  # bottom-bar 2-char (返回) — justify-split, matches the other pages


def _open_tutorial(screen, key):
    """Dispatch into the chosen tutorial's own view. The OCR view runs on the SAME band-size window; the
    basic-usage view needs a TALLER window (vertical LCD+panel fit) so it re-sizes the display — the
    caller restores this page's own window afterwards. Returns "home" if the view was left via band Home
    (jump straight home, past this menu), else None (back to this menu)."""
    if key == "ocr":
        from . import ocr_setting

        ocr_setting.ACTIVE_LANG = ACTIVE_LANG  # carry the UI language into the consent/tutorial view
        return ocr_setting.run_consent(screen, read_only=True)  # read-only how-it-works walkthrough (no accept gate)
    elif key == "basic":
        from . import tutorial_basic

        tutorial_basic.ACTIVE_LANG = ACTIVE_LANG
        sub = pygame.display.set_mode((tutorial_basic.SCREEN_W, tutorial_basic.SCREEN_H))  # taller vertical-fit window
        pygame.display.set_caption("TIMS tutorial — basic usage")
        return tutorial_basic.run_on(sub)
    return None


def render(surf):
    """Draw the tutorial-selection page; return {"buttons": [(key, rect)...], "back", "home"}."""
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(surf)  # persistent black status band across the top
    chrome.title_row(surf, SCREEN_CODE, i18n.t("setup_tims.tutorial_select.heading"), ACTIVE_LANG)

    # centered column of tutorial buttons
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)
    x0 = (SCREEN_W - BTN_W) // 2
    hits = []
    for i, (key, label_key) in enumerate(TUTORIALS):
        rect = pygame.Rect(x0, GRID_TOP + i * (BTN_H + BTN_GAP), BTN_W, BTN_H)
        draw_tims_button(surf, rect, i18n.t(label_key), font=btn_font, t=_BTN_T, state="normal")
        hits.append((key, rect))

    # 返回 (back) bottom-left — returns to the home menu (same as band Home / ESC)
    bar_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BAR_NATIVE)
    bw, bh = tims_button_size(i18n.t("setup_tims.back"), bar_font, _BAR_T)
    back_rect = pygame.Rect(BACK_X, SCREEN_H - BAR_Y_FROM_BOTTOM, bw, bh)
    draw_tims_button(surf, back_rect, i18n.t("setup_tims.back"), font=bar_font, t=_BAR_T, state="normal")

    return {"buttons": hits, "back": back_rect, "home": band_hits["home"]}


def run_on(screen):
    """Run the tutorial-selection page until the user returns to the menu (返回 / band Home / ESC). A
    tutorial click enters that tutorial, then loops back here. Returns None (nothing to bubble up — the
    tutorials are terminal views, not config builders)."""
    global ACTIVE_LANG
    clock = pygame.time.Clock()
    below_band = pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H)  # load-beat scope (band persists)

    while True:
        hits = render(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))  # let the outer loop see it too
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None  # back to the home menu
            if event.type == pygame.KEYDOWN and event.key == pygame.K_l:  # dev: cycle locale (title is i18n)
                ACTIVE_LANG = _LANGS[(_LANGS.index(ACTIVE_LANG) + 1) % len(_LANGS)]
                band.ACTIVE_LANG = ACTIVE_LANG
                i18n.set_language(ACTIVE_LANG)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                bar_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BAR_NATIVE)
                if hits["home"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=i18n.pixel_font_for_lang(band.ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE),
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=render,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return None
                if hits["back"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["back"],
                        label=i18n.t("setup_tims.back"),
                        font=bar_font,
                        t=_BAR_T,
                        redraw=render,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return None
                for key, rect in hits["buttons"]:
                    if rect.collidepoint(event.pos):
                        # navigational: press beat (yellow) → load beat → enter the tutorial view
                        press_transition(
                            screen,
                            rect=rect,
                            label=i18n.t(dict(TUTORIALS)[key]),
                            font=i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE),
                            t=_BTN_T,
                            redraw=render,
                            blank_color=BG_COLOR,
                            blank_ms=450,
                            blank_rect=below_band,
                        )
                        signal = _open_tutorial(screen, key)
                        if signal == "home":
                            return None  # tutorial's band Home = jump straight home, PAST this menu
                        # a tutorial view may have re-sized the display (basic-usage is a taller
                        # window) — restore THIS page's own band-size window before looping back.
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                        pygame.display.set_caption("TIMS tutorial select")
                        break


_LANGS = ("en", "zh_HK", "zh_CN")


def run_interactive():
    global ACTIVE_LANG
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("tutorial select (draft)")
    run_on(screen)
    pygame.quit()


def save_screenshot(path):
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    render(surf)
    out = str(project_root() / path)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H})")

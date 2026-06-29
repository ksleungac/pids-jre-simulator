"""Train-model picker (番台選択-style), reached from the C07AA PA-setting page's 列車型號 button (the IRL
番線 slot, repurposed). Mirrors the real TIMS 番台選択 screen (tims_bandai_choice.png): a 2-column grid of
glossy bevel buttons, the active model LIT (white) like the IRL selected 番台, the rest normal, and the
not-yet-built roadmap models GRAYED (dim scrim — they show but aren't selectable, per the reference).

Each button is two staggered lines: the train SERIES (主型號, e.g. E235系) on line 1 hugging LEFT, the
SUB-SERIES (番台, e.g. 1000番台) on line 2 hugging RIGHT, chars spaced out. Built models come from the
train-model registry (model_choices); grayed ones from a small roadmap list.

Preview:   uv run _dev_scripts/preview_setup_tims.py --screen model
"""

import pygame

import i18n
from app_paths import project_root
from displays.train_models import DEFAULT_MODEL_KEY, model_choices
from widgets import _TUNEABLES_TIMS_BUTTON, draw_lowres_text, draw_tims_button, press_transition

from . import band, chrome

ACTIVE_LANG = "zh_HK"

SCREEN_W, SCREEN_H = band.SCREEN_W, band.SCREEN_H
BG_COLOR = band.BG_COLOR
SCREEN_CODE = "X00AA"  # mirrors the IRL 番台選択 register code (droppable, kept for fidelity)

# Roadmap models NOT yet in the registry — shown GRAYED so the family reads complete (per the reference,
# where unavailable 番台 are dimmed, not hidden). Ordered ABOVE the built models (E231 → E233 → E235, by
# series number). (series, sub-series). Trim / extend freely — drop a sub-series once it's registered.
_GRAYED = [
    ("E231", "500"),
    ("E233", "0"),
    ("E233", "1000"),
    ("E233", "5000"),
]

# fmt: off
# ── grid layout tuneables (all derived coords flow from these) ────────────────
MODEL_NATIVE   = 18          # button text render px (AA-off native)
BTN_W          = 168         # button width
BTN_H          = 70          # button height (2 staggered lines)
COL_GAP        = 22          # horizontal gap between the 2 columns
ROW_GAP        = 16          # vertical gap between rows
GRID_TOP       = 150         # grid top y (below band + title row)
STAGGER_SPAN   = 0.62        # each line spans this fraction of the face width (justify spreads chars in it)
LINE_INK       = (236, 241, 246)   # white-ish text on a normal (blue) button
LINE_INK_SEL   = (24, 34, 46)      # dark ink on the LIT (white) current button
LINE_INK_GRAY  = (78, 85, 93)      # muted dark-gray text on a grayed (silver) unbuilt button
FLASH_MS       = 500         # current-model blink half-period (lit ↔ normal)
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

_BTN_T = _TUNEABLES_TIMS_BUTTON
# Grayed (not-yet-built) model = a flat SILVER button (desaturated face/bevel), NOT a dark scrim over the
# blue (that read as 'shadowed', not 'disabled'). Same geometry as _BTN_T; only the colors go gray.
# fmt: off
_GRAY_T = {
    **_TUNEABLES_TIMS_BUTTON,
    "bezel_hi_color":    (198, 205, 212),  # light silver crest
    "bezel_lo_color":    (96, 103, 111),   # gray shadow
    "face_top_color":    (150, 157, 165),  # silver-gray face
    "face_bottom_color": (132, 139, 147),
}
# fmt: on


def _model_font():
    return i18n.pixel_font_for_lang("en", MODEL_NATIVE)  # "en"=NotoSansJP — E235系 / 番台 are fixed, locale-independent


def _entries():
    """Unified grid list ordered by series number: grayed roadmap models (E231 → E233…) FIRST, then the
    built/selectable models (E235, from the registry) LAST. Each entry: {key, line1 (series, e.g.
    'E235系'), line2 (sub-series, e.g. '1000番台'), enabled}."""
    out = []
    for series, sub in _GRAYED:
        out.append({"key": None, "line1": f"{series}系", "line2": f"{sub}番台", "enabled": False})
    for key, label in model_choices():
        series, _, sub = label.partition("-")  # "E235-1000" → "E235" / "1000"
        out.append({"key": key, "line1": f"{series}系", "line2": f"{sub}番台", "enabled": True})
    return out


def _draw_model_button(surf, rect, entry, *, lit):
    """Bevel shell + two STAGGERED lines (series hugs left / 番台 hugs right, chars spaced via justify).
    enabled + lit → LIT (white, dark ink) blink phase of the current model; enabled → normal blue;
    NOT enabled → a flat SILVER (grayed) button with muted text — a roadmap model, not selectable."""
    if not entry["enabled"]:
        t, state, ink = _GRAY_T, "normal", LINE_INK_GRAY
    elif lit:
        t, state, ink = _BTN_T, "waiting", LINE_INK_SEL
    else:
        t, state, ink = _BTN_T, "normal", LINE_INK
    draw_tims_button(surf, rect, label="", t=t, state=state)

    ob, lip, shd = t["outer_border_w"], t["bezel_lip_w"], t["bezel_shadow_w"]
    bezel = rect.inflate(-2 * ob, -2 * ob)
    face = pygame.Rect(bezel.x + lip, bezel.y + lip, bezel.w - lip - shd, bezel.h - lip - shd)
    span = int(face.width * STAGGER_SPAN)
    half = face.height // 2
    top_rect = pygame.Rect(face.left, face.top, span, half)  # line 1 hugs LEFT
    bot_rect = pygame.Rect(face.right - span, face.centery, span, half)  # line 2 hugs RIGHT

    font = _model_font()
    draw_lowres_text(surf, entry["line1"], top_rect, font, ink, max_k=1, line_gap=0, align="justify")
    draw_lowres_text(surf, entry["line2"], bot_rect, font, ink, max_k=1, line_gap=0, align="justify")


def render(surf, current_key, flash_on=False):
    """Draw the model picker; returns {"buttons": [(key, rect)...], "home": rect}. No confirm/back button
    (per the reference): clicking a model commits it, band Home / ESC return. The current model
    (current_key) BLINKS lit↔normal via flash_on; grayed (unbuilt) entries are excluded from the hits."""
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band._render_topband(surf)
    chrome.title_row(surf, SCREEN_CODE, i18n.t("setup_tims.model_select.heading"), ACTIVE_LANG)

    entries = _entries()
    cols = 2
    grid_w = cols * BTN_W + (cols - 1) * COL_GAP
    x0 = (SCREEN_W - grid_w) // 2
    hits = []
    for i, e in enumerate(entries):
        r, c = divmod(i, cols)
        rect = pygame.Rect(x0 + c * (BTN_W + COL_GAP), GRID_TOP + r * (BTN_H + ROW_GAP), BTN_W, BTN_H)
        lit = e["enabled"] and e["key"] == current_key and flash_on
        _draw_model_button(surf, rect, e, lit=lit)
        if e["enabled"]:
            hits.append((e["key"], rect))

    return {"buttons": hits, "home": band_hits["home"]}


def run_on(screen, current_key):
    """Run the model picker until the user selects a model, backs out, or goes Home. Returns the chosen
    model KEY (selectable button pressed), None (戻る / ESC — keep the current model), or "home" (band Home)."""
    global ACTIVE_LANG
    clock = pygame.time.Clock()
    below_band = pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H)

    def frame(s):
        flash = (pygame.time.get_ticks() // FLASH_MS) % 2 == 0
        return render(s, current_key, flash_on=flash)

    while True:
        hits = frame(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return "home"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None  # back one level (→ C07AA), model unchanged
            if event.type == pygame.KEYDOWN and event.key == pygame.K_l:  # dev: cycle locale (title is i18n)
                ACTIVE_LANG = _LANGS[(_LANGS.index(ACTIVE_LANG) + 1) % len(_LANGS)]
                band.ACTIVE_LANG = ACTIVE_LANG
                i18n.set_language(ACTIVE_LANG)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits["home"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=i18n.pixel_font_for_lang(band.ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE),
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return "home"
                for key, rect in hits["buttons"]:
                    if rect.collidepoint(event.pos):
                        press_transition(
                            screen,
                            rect=rect,
                            label="",
                            font=_model_font(),
                            t=_BTN_T,
                            redraw=frame,
                            blank_color=BG_COLOR,
                            blank_ms=0,
                        )
                        return key


_LANGS = ("en", "zh_HK", "zh_CN")


def save_screenshot(path, current_key=None):
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    render(surf, current_key or DEFAULT_MODEL_KEY, flash_on=True)
    out = str(project_root() / path)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H})")

"""Shared TIMS-screen chrome — the bits every setup_tims page draws identically.

Currently the title row (fat screen-code + cyan heading, bottom-aligned on one
baseline) + its tuneables. Each page (案内設定 C07AA / route grid C07AB / start
station C07AC / run-pattern C07AF) drew this recipe verbatim before; it lives
here once so the chrome reads identical across pages and tunes in one place.
"""

import pygame

import i18n
from widgets import draw_lowres_text, draw_lowres_text_fat, lowres_text_size


def blit_lowres(surf, text, x, y, font, color, k, *, right=False):
    """Draw low-res (AA-off) pixel text flush at (x, y); right=True right-anchors at x. Shared across
    the setup_tims screens (band readout / table cells / recap rows / marquee / page indicator) — the
    one low-res text-blit primitive, not a per-screen private helper."""
    w, h = lowres_text_size(text, font, k, 0)
    tmp = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    draw_lowres_text(tmp, text, pygame.Rect(0, 0, w, h), font, color, max_k=k, line_gap=0, align="center")
    surf.blit(tmp, (x - w if right else x, y))


# fmt: off
# ── title row: screen-code + cyan heading. The HEADING is x-stretched ('fat' = WIDE, not bold);
#    the code renders at NATURAL width (XSCALE 1.0) and CODE_HEIGHT_FRAC × the heading's rendered
#    height, bottom-aligned to the same baseline. (Code px is derived, not fixed — see title_row.)
TITLE_X          = 16
TITLE_Y          = 73             # hugs the black top band (BAND_H 68) with a 5px margin
TITLE_NATIVE     = 24             # cyan heading px (4px shorter than the pre-redesign size)
TITLE_XSCALE     = 1.36           # heading x-stretch
TITLE_COLOR      = (84, 214, 226) # TIMS cyan heading
CODE_HEIGHT_FRAC = 0.8            # code rendered height = this × the heading's rendered height
CODE_XSCALE      = 1.0            # screen-code at NATURAL width (no stretch — not fat)
CODE_COLOR       = (210, 218, 228)# near-white code
CODE_GAP_FRAC    = 0.8            # code↔heading gap = this × a heading full-width char
# fmt: on


def title_row(surf, code, heading, lang):
    """Draw the screen-code (smaller, fatter stretch) + cyan heading, both x-stretched and
    bottom-aligned on one baseline, at (TITLE_X, TITLE_Y). ``code`` is the Latin screen code
    (C07AA…); ``heading`` is the already-localized title string; ``lang`` picks the heading face."""
    title_font = i18n.pixel_font_for_lang(lang, TITLE_NATIVE)
    _, title_h = lowres_text_size(heading, title_font, 1, 0)
    # Derive the code px so its rendered height ≈ CODE_HEIGHT_FRAC × the heading height. Lowres height
    # is ~linear in px, so measure the code once at a reference px and scale to the target height.
    ref_font = i18n.pixel_font_for_lang("en", TITLE_NATIVE)
    _, ref_code_h = lowres_text_size(code, ref_font, 1, 0)
    code_px = max(1, round(TITLE_NATIVE * CODE_HEIGHT_FRAC * title_h / max(1, ref_code_h)))
    code_font = i18n.pixel_font_for_lang("en", code_px)  # latin face for the code, height-matched
    code_w0, code_h = lowres_text_size(code, code_font, 1, 0)
    code_sw = max(1, round(code_w0 * CODE_XSCALE))
    code_y = TITLE_Y + (title_h - code_h)  # bottom-align the code to the heading's ink bottom
    draw_lowres_text_fat(surf, code, (TITLE_X, code_y), code_font, CODE_COLOR, xscale=CODE_XSCALE, k=1, line_gap=0)
    draw_lowres_text_fat(
        surf,
        heading,
        (TITLE_X + code_sw + round(CODE_GAP_FRAC * title_font.size("国")[0]), TITLE_Y),
        title_font,
        TITLE_COLOR,
        xscale=TITLE_XSCALE,
        k=1,
        line_gap=0,
    )

# SPDX-License-Identifier: MIT
"""Shared TIMS chrome — the design tokens + bits every TIMS surface draws identically.

Lives in the ``tims`` package (peer of ``tims/widgets.py``) because it's shared by
BOTH the ``tims.setup`` flow AND the live in-drive status band (``tims/band.py``,
rendered from core ``app.py``). ``tims/widgets.py`` holds the PRIMITIVES (how to draw a
button / low-res text); this holds the STYLE VOCABULARY (which palette, which
button role, which font px). Promoted from ``setup_tims/chrome.py`` when the band
graduated into the live OCR panel.

Holds the title row (fat screen-code + cyan heading, bottom-aligned on one
baseline) + its tuneables, the shared PALETTE, button role-presets, and the
low-res text blit.
"""

import pygame

import i18n
from .widgets import _TUNEABLES_TIMS_BUTTON, draw_lowres_text, draw_lowres_text_fat, lowres_text_size

# fmt: off
# ── TIMS palette — the SINGLE SOURCE for chrome colors (design tokens). Screens reference these
#    instead of re-declaring literals, which had DRIFTED: near-black as (8,10,14) vs (10,13,18); bright
#    ink as (236,241,246) vs (232,238,245); light-slate as (150,162,176) vs (150,164,178). Only shared
#    color VALUES live here — layout geometry (positions/sizes) stays per-module (conventions § Data layout).
BG          = (62, 68, 80)      # screen background (slate)
PANEL_BG    = (8, 10, 14)       # near-black panel / table / band-strip interior
FRAME       = (120, 132, 144)   # slate frame / border / separator
GRID        = (150, 162, 176)   # lighter slate — gridlines / thin accents / L-notch frame
INK         = (236, 241, 246)   # bright white text
DIM         = (150, 162, 174)   # dimmer secondary text
CYAN        = (84, 214, 226)    # TIMS cyan heading (title_row)
CODE_INK    = (210, 218, 228)   # near-white screen code / page indicator
AMBER       = (232, 184, 64)    # caution / caption
GREEN       = (54, 230, 64)     # dot-matrix notification green

# ── TIMS button presets — ONE draw_tims_button primitive, named ROLE variants (plain dicts, so the
#    per-screen `{**PRESET, "text_align": …}` spread still works). Hoisted from per-screen copies that
#    had duplicated verbatim (route_select._BAR_T ≡ ocr_setting._FOOT_T, etc.). One-off / model-specific
#    dicts (lang knobs, grayed tiles, slot-grid boxes) stay local — only the recurring roles live here.
_B = _TUNEABLES_TIMS_BUTTON
BTN_BAR    = {**_B, "text_align": "justify", "v_pad": 14, "text_max_k": 1, "nominal_k": 1, "line_gap": 3}  # bottom-bar 2-char (返回/設定/取消/明白)
BTN_LABEL  = {**_B, "text_align": "center", "v_pad": 0, "text_max_k": 1, "line_gap": 3}                    # crammed page buttons (natural, 1-by-1)
BTN_ACTION = {**_B, "text_align": "center", "text_pad": 12, "text_max_k": 1}                               # home action cards
BTN_STEP   = {**_B, "text_align": "center", "v_pad": 4, "text_max_k": 1, "min_w": 0}                       # steppers / number chips

# ── disabled / unavailable = SILVER overlay (conventions § "disabled = silver palette, NOT a dark scrim").
#    Spread over ANY base/role tuneable: {**_TUNEABLES_TIMS_BUTTON, **DISABLED} / {**BTN_BAR, **DISABLED}.
#    ONE canonical silver, graduated from model_select._GRAY_T once the grey spread past one screen (roadmap
#    tiles + consent-OK-locked + tutorial-disabled + launch-locked + inert band buttons). Overrides only the
#    NORMAL-state face/bevel/ink — callers draw state="normal".
DISABLED = {
    "bezel_hi_color":    (198, 205, 212),  # light silver crest
    "bezel_lo_color":    (96, 103, 111),   # gray shadow
    "face_top_color":    (150, 157, 165),  # silver-gray face
    "face_bottom_color": (132, 139, 147),
    "text_color":        (78, 85, 93),     # muted dark-gray ink on the silver face
}

# ── standard chrome font px by ROLE (recurring sizes only; genuine per-screen one-offs stay local)
FONT_PX = {"title": 24, "heading": 16, "body": 16, "cap": 13, "button": 20}
# fmt: on


def blit_lowres(surf, text, x, y, font, color, k, *, right=False):
    """Draw low-res (AA-off) pixel text flush at (x, y); right=True right-anchors at x. Shared across
    the tims.setup screens (band readout / table cells / recap rows / marquee / page indicator) — the
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
TITLE_COLOR      = CYAN           # TIMS cyan heading (palette CYAN)
CODE_HEIGHT_FRAC = 0.8            # code rendered height = this × the heading's rendered height
CODE_XSCALE      = 1.0            # screen-code at NATURAL width (no stretch — not fat)
CODE_COLOR       = CODE_INK       # near-white code (palette CODE_INK)
CODE_GAP_FRAC    = 0.8            # code↔heading gap = this × a heading full-width char
# fmt: on


_WRAP_CACHE = {}  # (font, max_w, text) -> [line, ...]; see wrap_lines
_WRAP_CACHE_MAX = 512  # inputs are a fixed string set x 3 locales; the cap is a runaway backstop


def wrap_lines(text, font, max_w):
    """Greedy pixel wrap (CJK char-by-char; blank line preserved). Caller owns the paragraph split.

    A Latin run backtracks to its last space so a word is never cut mid-run ("Windo / ws"),
    while CJK keeps breaking at the column edge — the same rule the classic panel's wrap_text
    uses. A single Latin word wider than the column still hard-breaks rather than overflowing.

    Lives here rather than in a screen because two screens now wrap text (the OCR consent body and
    the remote-terminal page's caution line), and the second one reaching into the first's privates
    is the smell that says a helper has outgrown its module (`principles.md` § "Search before
    authoring", vibe-check #11).

    MEMOIZED. The consent view rebuilds its whole body every frame, and this loop measures
    `font.size()` once per CHARACTER — 1737 calls per build, 48% of the frame cost, all of it
    re-deriving identical breaks (#60). The result depends only on (text, font, max_w), so it is
    cached on exactly those. The font object IS the key, which both keys per-locale correctly and
    holds a reference so its id can never be reused by a later font. Callers must treat the
    returned list as read-only — it is the cached instance, not a copy.
    """
    key = (font, max_w, text)
    cached = _WRAP_CACHE.get(key)
    if cached is not None:
        return cached

    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if font.size(cur + ch)[0] <= max_w or not cur:
                cur += ch
                continue
            if ch == " ":
                lines.append(cur)
                cur = ""
                continue
            sp = cur.rfind(" ")
            tail = cur[sp + 1 :] if sp >= 0 else ""
            # Backtrack only when the carried tail is Latin: a CJK continuation has no word
            # boundary worth preserving, and moving it would just ragged the column for nothing.
            if sp > 0 and tail and ord(tail[0]) < 0x3000:
                lines.append(cur[:sp])
                cur = tail + ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)

    if len(_WRAP_CACHE) >= _WRAP_CACHE_MAX:
        _WRAP_CACHE.clear()
    _WRAP_CACHE[key] = lines
    return lines


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

"""TIMS-style tutorial screen (GREEN build — blue/green).

A new window-in-window tutorial: a LEFT column of vertically-stacked TIMS tab buttons (one per
feature tutorial), and a RIGHT recessed detail region that hosts the selected tutorial. Pressing a
tab switches which tutorial the region shows; the active tab reads LIT, the others UNLIT (yellow
stays reserved for the momentary PRESSED state — never a selected indicator).

Built ALONGSIDE the existing `tutorial.py` (BLUE), which stays the live OOBE path until this is wired
into the home menu and switched over. NOTE: deliberately NOT imported by main.py / setup.py yet — it
is the in-flight green build. Wiring + switch (and the Tutorial-card flash that replaces the forced
first-run launch) come after the detail region embeds the real walkthrough. See
WIP_setup_redesign.md § "Tutorial screen".

Chrome = the graduated `widgets.py` primitives + `i18n.pixel_font_for_lang` (per-locale Ark pixel
face). Reuses no font/path resolution of its own.

    uv run preview_tutorial_tims.py
"""

from __future__ import annotations

import pygame

import i18n
from tutorial import WINDOW_H, WINDOW_W
from widgets import (
    _TUNEABLES_TIMS_BUTTON,
    draw_lowres_text,
    draw_tims_button,
    lowres_text_size,
    press_transition,
)

ARK_NATIVE = 12  # native render grid for the pixel face (upscaled by k)

# fmt: off
# ── layout tuneables (the approved draft proportions) ─────────────────────────
MARGIN          = 16
BG_COLOR        = (62, 68, 80)

HEADER_KEY      = "tutorial2.title"   # i18n; falls back to the key (caption only)
HEADER_FALLBACK = "教學"
HEADER_K        = 2                    # k=2 ceiling convention (no large pixel text)
HEADER_COLOR    = (224, 232, 238)
HEADER_H        = 48

# back-to-home button — square, top-right, 4-char CJK wrapped 2x2. Exits back to the home menu
# (same as ESC). Content-SIZED to the 2x2 label (like the language knobs) so the pixel text fills at
# k=HOME_K instead of shrinking in a fixed box; the derived size drives the top-band height below.
HOME_KEY         = "tutorial2.home"
HOME_FALLBACK    = "返回\n主頁"         # 2x2 — return to home page
HOME_K           = 2                   # pixel multiplier (small-size aesthetic — never balloon)
HOME_LINE_GAP    = 0                   # tight 2x2 (rows touch), like the language knobs
HOME_TEXT_MARGIN = 6                   # gap between the tight 2x2 block and the bevel

# left menu — vertically-stacked TIMS buttons, 4 chars on ONE line
TAB_W           = 130
TAB_H           = 70
TAB_GAP         = 8
TAB_K           = 2
INACTIVE_SCRIM  = (40, 44, 54, 150)   # dims unselected tabs ("unlit")
MENU_GAP        = 16                   # gap between tab column and detail region

# right detail region = the embedded tutorial's OWN window (single source: tutorial.WINDOW_W/H — the
# same constants main.py sizes the standalone tutorial with, so narrowing the panel there flows here).
REGION_W        = WINDOW_W
REGION_H        = WINDOW_H

# detail placeholder palette (until the live walkthrough embeds)
PANEL_FILL      = (28, 32, 40)
PLACE_COLOR     = (150, 162, 178)
PANEL_BORDER_HI = (90, 100, 118)      # bottom/right (recessed)
PANEL_BORDER_LO = (14, 20, 30)        # top/left shadow (recessed)
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on


def _home_btn_size():
    """Content-derived square side for the 2x2 home label, mirroring the language-knob recipe:
    square the 2x2 footprint (at k=HOME_K), + margin + bevel. Mono Ark metrics are locale-independent,
    so measure once at zh_HK. Guarantees the label fills at k=HOME_K rather than dropping to a tiny k
    in a too-big fixed box."""
    pygame.font.init()
    font = i18n.pixel_font_for_lang("zh_HK", ARK_NATIVE)
    sw, sh = lowres_text_size(HOME_FALLBACK, font, HOME_K, HOME_LINE_GAP)
    b = _TUNEABLES_TIMS_BUTTON
    bevel = 2 * b["outer_border_w"] + b["bezel_lip_w"] + b["bezel_shadow_w"]
    return max(sw, sh) + 2 * HOME_TEXT_MARGIN + bevel


HOME_BTN_SIZE = _home_btn_size()

# Derived window size (the detail region drives it). Top band = taller of header / home button so
# the square home button clears the detail region below.
TOP_BAND_H = max(HEADER_H, HOME_BTN_SIZE)
BODY_TOP = MARGIN + TOP_BAND_H + 8
REGION_X = MARGIN + TAB_W + MENU_GAP
SCREEN_W = REGION_X + REGION_W + MARGIN
SCREEN_H = BODY_TOP + REGION_H + MARGIN
WINDOW_SIZE = (SCREEN_W, SCREEN_H)

# (key, i18n_label_key, fallback_label) per feature tutorial. 4-char CJK on one line. The fallback is
# used until translations_app.json gains the keys (wiring step); keeps the green build runnable now.
TABS = [
    ("normal", "tutorial2.tab.normal", "基本操作"),  # normal usage  → embeds the live walkthrough
    ("ocr", "tutorial2.tab.ocr", "自動廣播"),  # OCR auto-PA   → new walkthrough (later)
]

_TAB_TUNEABLES = {**_TUNEABLES_TIMS_BUTTON, "text_align": "center", "text_pad": 12, "text_max_k": TAB_K}

# Home button: tight-centered 2x2 label (the language-knob recipe — content-sized square, k=HOME_K).
_HOME_TUNEABLES = {**_TUNEABLES_TIMS_BUTTON, "text_align": "center", "text_pad": HOME_TEXT_MARGIN, "line_gap": HOME_LINE_GAP, "text_max_k": HOME_K}


def _t(key: str, fallback: str) -> str:
    """i18n lookup with an explicit fallback (t() returns the key itself when missing — we want a
    readable label while the translations file hasn't gained these keys yet)."""
    val = i18n.t(key)
    return fallback if val == key else val


class TimsTutorial:
    """Window-in-window tutorial shell. Owns tab state + the detail-region dispatch.

    Caller passes the display surface (so the home menu can hand off into it). The detail region
    currently renders reskinned placeholders; the 'normal usage' view embeds the live interactive
    walkthrough in a later increment.
    """

    def __init__(self, screen: pygame.Surface, live: bool = True):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.active_tab = 0
        self.running = True
        # live=True: the 'normal' tab embeds the real interactive walkthrough
        # (boots a sim). live=False: it shows the layout block-out placeholder —
        # used by headless layout smoke-tests so they don't boot audio.
        self.live = live
        # Fixed layout → tab hit-rects can be built once.
        self._tab_rects = [pygame.Rect(MARGIN, BODY_TOP + i * (TAB_H + TAB_GAP), TAB_W, TAB_H) for i in range(len(TABS))]
        self._region = pygame.Rect(REGION_X, BODY_TOP, REGION_W, REGION_H)
        # back-to-home button — square, top-right corner of the top band.
        self._home_rect = pygame.Rect(SCREEN_W - MARGIN - HOME_BTN_SIZE, MARGIN, HOME_BTN_SIZE, HOME_BTN_SIZE)
        # Embedded walkthrough (the 'normal' tab). Lazily booted on first show so
        # the sim only spins up when the user opens that tab. _failed latches a
        # boot failure (missing assets / no audio) → fall back to placeholder.
        self._walkthrough = None  # type: ignore[assignment]
        self._walkthrough_failed = False

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            while self.running:
                self.clock.tick(15)
                self._handle_events()
                self.render(self.screen)
                pygame.display.flip()
        finally:
            if self._walkthrough is not None:
                self._walkthrough.embed_teardown()

    def _ensure_walkthrough(self) -> bool:
        """Boot the embedded interactive walkthrough into the detail region on
        first need. Returns True once it's live, False if it can't boot (caller
        shows the placeholder). Idempotent; latches failure so we don't re-try
        every frame."""
        if self._walkthrough is not None:
            return True
        if self._walkthrough_failed:
            return False
        from tutorial import Tutorial  # local: heavy (boots a sim); only on first 'normal' open

        region_surf = self.screen.subsurface(self._region)
        tut = Tutorial(region_surf)
        tut.set_embedded(origin=self._region.topleft)
        if not tut.embed_setup():
            self._walkthrough_failed = True
            return False
        self._walkthrough = tut
        return True

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._home_rect.collidepoint(event.pos):
                    # decisive nav back to the home menu: yellow press beat → blank loading beat → exit.
                    font = i18n.pixel_font_for_lang(i18n.current_lang(), ARK_NATIVE)
                    press_transition(
                        self.screen,
                        rect=self._home_rect,
                        label=_t(HOME_KEY, HOME_FALLBACK),
                        font=font,
                        t=_HOME_TUNEABLES,
                        redraw=self.render,
                        blank_color=BG_COLOR,
                    )
                    self.running = False
                    continue
                if self._hit_tab(event.pos):
                    continue  # tab switch consumed the click
            # Everything else (PgDn/PgUp/End keys, clicks inside the detail
            # region) forwards to the live walkthrough when the normal tab is up.
            if TABS[self.active_tab][0] == "normal" and self._walkthrough is not None:
                self._walkthrough.process_event(event)

    def _hit_tab(self, pos: tuple[int, int]) -> bool:
        for i, rect in enumerate(self._tab_rects):
            if rect.collidepoint(pos):
                self.active_tab = i
                return True
        return False

    # ── drawing ───────────────────────────────────────────────────────────────
    def render(self, surface: pygame.Surface) -> None:
        """Draw one frame. Separated from run() so it can be exercised headlessly."""
        surface.fill(BG_COLOR)
        font = i18n.pixel_font_for_lang(i18n.current_lang(), ARK_NATIVE)

        # header
        draw_lowres_text(
            surface, _t(HEADER_KEY, HEADER_FALLBACK), pygame.Rect(MARGIN, MARGIN, 200, HEADER_H), font, HEADER_COLOR, max_k=HEADER_K, align="center"
        )

        # back-to-home button, top-right
        draw_tims_button(surface, self._home_rect, _t(HOME_KEY, HOME_FALLBACK), font=font, t=_HOME_TUNEABLES, state="normal")

        # left tab column — active LIT, others UNLIT (dim scrim; yellow = PRESSED only)
        for i, (key, lk, fb) in enumerate(TABS):
            rect = self._tab_rects[i]
            draw_tims_button(surface, rect, _t(lk, fb), font=font, t=_TAB_TUNEABLES, state="normal")
            if i != self.active_tab:
                scrim = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                pygame.draw.rect(scrim, INACTIVE_SCRIM, scrim.get_rect(), border_radius=5)
                surface.blit(scrim, rect.topleft)

        # right detail region
        self._render_detail(surface, font)

    def _render_detail(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        region = self._region
        key = TABS[self.active_tab][0]

        # 'normal' tab → embed the live interactive walkthrough (renders its own
        # chrome + sim into the region sub-surface). Frame it with the recessed
        # border on top so the window-in-window inset reads.
        if key == "normal" and self.live and self._ensure_walkthrough():
            self._walkthrough.render_frame()
            self._recessed_border(surface, region)
            return

        # Otherwise (OCR tab, or walkthrough unavailable) → reskinned placeholder.
        pygame.draw.rect(surface, PANEL_FILL, region, border_radius=4)
        self._recessed_border(surface, region)
        label = _t(TABS[self.active_tab][1], TABS[self.active_tab][2])
        caption = label + ("  —  即時演練嵌入此處" if key == "normal" else "  —  教學內容")
        draw_lowres_text(surface, caption, pygame.Rect(region.x + 20, region.y + 20, region.w - 40, 40), font, PLACE_COLOR, max_k=2, align="center")

    @staticmethod
    def _recessed_border(surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Inverted bevel hint (light far edges, dark near edges) → reads as a recessed inset."""
        pygame.draw.line(surface, PANEL_BORDER_LO, rect.topleft, (rect.right - 1, rect.top), 2)
        pygame.draw.line(surface, PANEL_BORDER_LO, rect.topleft, (rect.left, rect.bottom - 1), 2)
        pygame.draw.line(surface, PANEL_BORDER_HI, (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1), 2)
        pygame.draw.line(surface, PANEL_BORDER_HI, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom - 1), 2)

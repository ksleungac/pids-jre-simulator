# SPDX-License-Identifier: MIT
"""Basic-usage tutorial — VERTICAL-FIT, framed inside the TIMS page. INTERACTIVE.

The legacy `tutorial.py` walkthrough is a WIDE window (LCD 730 left + 300px step panel right +
progress strip on top). To live inside the 730-wide TIMS band window it reflows VERTICALLY:
band → title header → live LCD (native 730×420, unscaled) → labeled progress strip → step panel.

`tutorial.py` is LEFT INTACT. `BasicTutorial` SUBCLASSES `Tutorial` and inherits the ENTIRE step
machine unchanged — event dispatch, press-cycle, progress-jump, click-to-jump, predicates, ActionFlow,
skip handlers, the per-step text getters. It overrides ONLY the layout-bearing methods (LCD placement,
LCD click-mapping, per-frame draw, progress bar, panel, callout) so the same logic renders vertically.
Hit-testing follows automatically because the overridden draws populate the same `_phase_rects` /
`_btn_rects` the inherited handlers read.

The audio seek bar is relocated into the title-row header (right of the title) to reclaim vertical
space. Still simplified vs the wide panel (refine later): no action-history block; the "press this
button" prompt is conveyed by FLASHING the button, not a text line.

Preview:  uv run _dev_scripts/preview_setup_tims.py --screen basic
"""

import time

import pygame

import i18n
from app import PASimulator
from displays.train_models.e235_1000 import S_HEIGHT, S_WIDTH
from ..widgets import draw_tims_button, lowres_text_size, press_transition, tims_button_size

from .. import band
from .. import chrome
from .dims import BG_COLOR
from tutorial import PHASE_KEYS, STEPS, Tutorial, _fmt_time, _font_cjk, _font_helv, _render_mixed

ACTIVE_LANG = "zh_HK"
SCREEN_CODE = "C07AE"  # placeholder register code (droppable — like the other tims setup screens)

# fmt: off
# ── vertical-fit layout tuneables (all derived coords flow from these) ─────────
SCREEN_W        = S_WIDTH              # 730 — band width; LCD is exactly this wide so it fits unscaled
LCD_W, LCD_H    = S_WIDTH, S_HEIGHT    # 730×420 native (NO rescale → click-to-jump math survives)

# Layout, top→bottom: band → title header → live LCD → LABELED progress strip → step panel. The
# progress strip sits BETWEEN the LCD and the instructions (full width, so 8 phase labels fit).
LCD_TOP         = 100                  # LCD top — gap title→LCD equals the band→title gap (both 5px, symmetric header)
PROG_GAP_TOP    = 4                    # gap LCD → progress strip
PROG_STRIP_H    = 62                   # labeled progress strip height (dots + up to 2 wrapped label lines)
PANEL_GAP       = 0                    # progress strip + panel are FLUSH (one continuous near-black block)
PANEL_H         = 150                  # step-panel height (heading + body; action conveyed by button flash)
BOTTOM_MARGIN   = 0                    # panel runs to the window bottom (no slate strip)

LCD_Y           = LCD_TOP
PROG_Y          = LCD_Y + LCD_H + PROG_GAP_TOP
PANEL_Y         = PROG_Y + PROG_STRIP_H + PANEL_GAP
SCREEN_H        = PANEL_Y + PANEL_H + BOTTOM_MARGIN

# progress strip (full-width, below the LCD): dots + phase labels
PROG_PAD_X      = 24                   # strip side padding
PROG_DOT_R      = 7                    # phase-dot radius
PROG_LABEL_PX   = 15                   # phase-label px (8 across 730)
PROG_LABEL_GAP  = 8                    # min px between adjacent labels → wrap threshold (col spacing − this)
PROG_LINE_GAP   = 2                    # gap between a label's two wrapped lines (EN wraps; CJK stays 1 line)
DOT_DONE        = chrome.CYAN          # completed / current dot — the shared TIMS cyan (was (54,214,226), R-drifted from CYAN)
DOT_FUTURE      = (108, 118, 134)      # not-yet-reached
LINE_DONE       = (54, 160, 172)       # completed connector
LINE_FUTURE     = (92, 100, 116)       # future connector

# step panel
PANEL_PAD       = 18                   # panel inner padding
HEAD_PX         = 20                   # heading px (phase name — cyan)
BODY_PX         = 17                   # body/action px
BODY_GAP        = 5                    # extra px between wrapped body lines
BLANK_GAP       = 7                    # vertical gap for an explicit blank line (\n\n in a body)
RECAP_SEP       = " · "                 # middot join for the FLATTENED recap reference list (wraps at spaces)
BTN_NATIVE      = 16                   # panel-button label px (smaller than the 20px page-button size)
BTN_H           = 36                   # panel-button height (shorter)
BTN_GAP         = 8                    # gap between stacked panel buttons
BTN_H_PAD       = 13                   # side padding inside the button (≈4-char label + this each side)
BTN_EDGE_MARGIN = 10                   # button column hugs the screen right edge (small gap)
BTN_GUTTER      = 14                   # gap between the body-text column and the button column
BEAT_PRESSED_MS = 100                  # button yellow-flash hold (press feedback)
BEAT_BLANK_MS   = 280                  # step-change loading beat (panel blanked)
LOAD_BEAT_MS    = 300                  # page-entry loading beat (content region emptied to slate)
NEXT_FLASH_MS   = 450                  # Next-button 'proceed' flash half-period (lit↔normal)
HOME_BEAT_MS    = 450                  # band-Home exit beat (matches the select page's nav beat)

# audio seek bar — lives in the title-row header (right of the title), space being tight. Visible ONLY
# while audio plays (mirrors the wide layout's gate). Bar + elapsed/total labels on ONE line, centered
# in the 32px header band (band bottom → LCD top), right-anchored.
SEEK_W            = 200                 # bar width
SEEK_H            = 6                   # bar height
SEEK_LABEL_PX     = 13                  # elapsed/total label px (AA-off)
SEEK_LABEL_GAP    = 7                   # gap bar↔label
SEEK_RIGHT_MARGIN = 16                  # right edge inset (matches title left inset)
SEEK_BG_COLOR     = (44, 50, 62)        # unfilled bar track
SEEK_FILL_COLOR   = chrome.CYAN         # filled progress — TIMS cyan (green dropped)
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# Panel buttons: warehouse center-natural preset, tightened side padding → width = worst-case label
# (measured in the active locale) + BTN_H_PAD each side, so the group shares one narrow size.
# nominal_k=1: BTN_LABEL inherits nominal_k=2 from the base (sizes the box for DOUBLE-size text) but
# draws at k=1 — that mismatch is what made the boxes ~2× too wide; size + draw both at native k=1.
# Thinner outline + bevel: the base bevel (~8.8px) reads heavy on these small 36px buttons.
_BTN_T = {
    **chrome.BTN_LABEL,
    "h_pad": BTN_H_PAD,
    "nominal_k": 1,
    "outer_border_w": 1,
    "bezel_lip_w": 2.0,
    "bezel_shadow_w": 1.2,
    "corner_radius": 4,
    "face_corner_radius": 3,
}


class BasicTutorial(Tutorial):
    """Vertical-fit host for the interactive walkthrough. Inherits Tutorial's step machine; overrides
    only layout: where the LCD sits, how a click maps to it, and how each frame + progress + panel draw."""

    def __init__(self, screen, lang=ACTIVE_LANG):
        super().__init__(screen)
        self._lang = lang
        self._home_rect = None  # band Home hit-rect (set each frame)
        self._exit_to_home = False  # True when the user left via band Home → jump PAST the menu, straight home

    # ── layout overrides ──────────────────────────────────────────────────────
    def embed_setup(self):
        """Boot the sim with the LCD subsurface at the VERTICAL LCD_Y (Tutorial's own embed_setup places
        it at the wide-layout origin). Everything else — jump-to-boot-stop, step-1 snapshot — is the same."""
        ok, _ = self.assets_ok()
        if not ok:
            return False
        self.lcd_surface = self.screen.subsurface((0, LCD_Y, LCD_W, LCD_H))
        try:
            self.sim = PASimulator(work_dir=self.tutorial_route_dir(), tutorial=True, target_surface=self.lcd_surface)
        except Exception as e:  # no-audio build / missing assets
            print(f"[tutorial_basic] sim boot failed: {e}")
            return False
        self.sim.jump_to_stop(self.BOOT_STOP_IDX)
        self._enter_step(1)
        self._load_beat()  # page-entry loading beat, before the first full frame paints
        return True

    def _lcd_click_target(self, pos):
        """Map a window click to a sim-stop index using the VERTICAL LCD offset (Tutorial's version
        subtracts the wide-layout LCD_X/LCD_Y module constants)."""
        if self.sim is None:
            return None
        x, y = pos
        lx, ly = x, y - LCD_Y
        if lx < 0 or ly < 0 or lx >= LCD_W or ly >= LCD_H:
            return None
        return self.sim._click_target(lx, ly)

    def _draw_callout(self):
        """Pulse the current step's LCD callout region at the VERTICAL LCD offset (cyan, not the wide
        layout's green — TIMS drops green)."""
        rect = self._step().callout_rect
        if rect is None:
            return
        if self.current_step == 7 and self._step7_clicked:
            return
        x, y, w, h = rect
        self._draw_pulsing_outline(pygame.Rect(x, LCD_Y + y, w, h), chrome.CYAN, outline_w=3)

    def _panel_step_beat(self, btn_rect, label):
        """Yellow press-beat for a panel button (Back / Next / Skip): flash the pressed button bright
        yellow, then a short loading beat blanking ONLY the step panel (the region that changes between
        steps) before the new step renders. Overrides Tutorial's beat, which blanks the wide-layout
        panel rect — wrong region here."""
        btn_font = i18n.pixel_font_for_lang(self._lang, BTN_NATIVE)
        press_transition(
            self.screen,
            rect=btn_rect,
            label=label,
            font=btn_font,
            t=_BTN_T,
            redraw=lambda _s: self.render_frame(),
            blank_color=BG_COLOR,
            blank_rect=pygame.Rect(0, PANEL_Y, SCREEN_W, PANEL_H),
            pressed_ms=BEAT_PRESSED_MS,
            blank_ms=BEAT_BLANK_MS,
        )

    def _skip_tutorial(self):
        """Give the Skip button the same yellow press-beat as Back/Next before jumping to the recap
        (Tutorial's _handle_panel_click calls _skip_tutorial WITHOUT a beat, unlike Back/Next)."""
        r = self._btn_rects.get("skip_tutorial")
        if r is not None:
            self._panel_step_beat(r, i18n.t("tutorial.btn.skip_tutorial"))
        super()._skip_tutorial()

    def _load_beat(self):
        """Page-entry loading beat: band up top, the LCD/progress/panel region emptied to slate, held a
        beat — the entry transition every tims.setup page shows. The tutorial_select → basic switch
        resizes the window (taller), which swallows the caller's beat, so the view emits its own."""
        surf = self.screen
        surf.fill(BG_COLOR)
        band.ACTIVE_LANG = self._lang
        band.render(surf)  # band persists across the beat
        pygame.draw.rect(surf, chrome.PANEL_BG, pygame.Rect(0, band.BAND_H, SCREEN_W, LCD_Y - band.BAND_H))
        chrome.title_row(surf, SCREEN_CODE, i18n.t("setup_tims.tutorial.basic"), self._lang)
        pygame.display.flip()
        pygame.time.delay(LOAD_BEAT_MS)

    def process_event(self, event):
        """Band Home → leave the tutorial (back to the menu). Everything else is the inherited dispatch
        (ESC/QUIT, PgDn/PgUp/End, progress-jump, panel buttons, LCD click)."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and band.click_stream(event.pos):
            return  # band mirror address → opened in the PC's browser; the tutorial stays put
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self._home_rect and self._home_rect.collidepoint(event.pos):
            # band Home → yellow flash + loading beat (content emptied to slate), THEN leave to the menu —
            # same nav beat the tutorial_select page shows on its own band Home.
            press_transition(
                self.screen,
                rect=self._home_rect,
                label=i18n.t("setup_tims.band.home"),
                font=i18n.pixel_font_for_lang(band.ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE),
                t=band._BAND_BTN_TUNEABLES,
                redraw=lambda _s: self.render_frame(),
                blank_color=BG_COLOR,
                blank_ms=HOME_BEAT_MS,
                blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
            )
            self._exit_to_home = True  # band Home = straight home, not back one level to the menu
            self.running = False
            return
        super().process_event(event)

    # ── per-frame render (vertical) ───────────────────────────────────────────
    def render_frame(self):
        surf = self.screen
        surf.fill(BG_COLOR)
        band.ACTIVE_LANG = self._lang
        self._home_rect = band.render(surf)["home"]  # persistent OCR status band across the top
        # near-black header (continuous with the band + LCD), then title
        pygame.draw.rect(surf, chrome.PANEL_BG, pygame.Rect(0, band.BAND_H, SCREEN_W, LCD_Y - band.BAND_H))
        chrome.title_row(surf, SCREEN_CODE, i18n.t("setup_tims.tutorial.basic"), self._lang)
        self._draw_seek_bar()  # audio progress — right side of the title header (playing only)
        # live LCD (mirror Tutorial._tick_sim's draw order), into the subsurface at LCD_Y
        ts = time.time()
        self.sim.state.update_skip_progress(ts)
        self.sim.scheduler.tick(ts, self.sim.state)
        self.sim.upper.draw(time.strftime("%H:%M", time.localtime(ts)))
        self.sim.lower.draw(ts)
        self._draw_callout()
        self._draw_progress_v()
        self._draw_panel_v()
        self._update_hover_cursor()

    def _draw_seek_bar(self):
        """Audio-position seek bar in the title-row header (right of the title). Drawn only while audio
        plays — a slim cyan-fill track flanked by elapsed / total time labels, all on one line, vertically
        centered in the 32px band-bottom→LCD-top header. Mirrors the wide layout's seek bar, relocated to
        reclaim vertical space."""
        if self.sim is None or not self.sim.audio.is_playing():
            return
        pos, dur = self.sim.audio.position(), self.sim.audio.duration()
        if pos is None or not dur or dur <= 0:
            return
        lf = i18n.pixel_font_for_lang("en", SEEK_LABEL_PX)
        center_y = (band.BAND_H + LCD_Y) // 2
        elapsed_s, total_s = _fmt_time(pos), _fmt_time(dur)
        ew, eh = lowres_text_size(elapsed_s, lf, 1, 0)
        tw, _ = lowres_text_size(total_s, lf, 1, 0)
        right_x = SCREEN_W - SEEK_RIGHT_MARGIN
        bar_right = right_x - tw - SEEK_LABEL_GAP
        bar_left = bar_right - SEEK_W
        elapsed_x = bar_left - SEEK_LABEL_GAP - ew
        label_y = center_y - eh // 2
        bar_y = center_y - SEEK_H // 2
        chrome.blit_lowres(self.screen, elapsed_s, elapsed_x, label_y, lf, chrome.DIM, 1)
        track = pygame.Rect(bar_left, bar_y, SEEK_W, SEEK_H)
        pygame.draw.rect(self.screen, SEEK_BG_COLOR, track, border_radius=3)
        fill_w = int(SEEK_W * max(0.0, min(1.0, pos / dur)))
        if fill_w > 0:
            pygame.draw.rect(self.screen, SEEK_FILL_COLOR, pygame.Rect(bar_left, bar_y, fill_w, SEEK_H), border_radius=3)
        chrome.blit_lowres(self.screen, total_s, right_x, label_y, lf, chrome.DIM, 1, right=True)

    @staticmethod
    def _wrap_phase_label(lbl, font, max_w):
        """Wrap a phase label to <=2 lines that each fit max_w. Breaks on spaces AND hyphens (so
        'Pre-departure' can split); a single unsplittable token (a short CJK label) stays on one line.
        EN labels ('Departure melody', 'Stopped at next station') overflow the ~97px column at one line
        and wrap; the compact CJK labels pass straight through."""
        if lowres_text_size(lbl, font, 1, 0)[0] <= max_w:
            return [lbl]
        atoms = []
        for word in lbl.split(" "):
            parts = word.split("-")
            for j, p in enumerate(parts):
                atoms.append(p + ("-" if j < len(parts) - 1 else ""))
        if len(atoms) == 1:
            return [lbl]  # unsplittable (e.g. a long CJK run) — leave as one line

        def _join(seq):
            s = ""
            for a in seq:
                if s and not s.endswith("-"):  # no space after a hyphen break (keeps 'Pre-departure')
                    s += " "
                s += a
            return s

        best = None  # 2-line split that minimizes the wider line
        for cut in range(1, len(atoms)):
            l1, l2 = _join(atoms[:cut]), _join(atoms[cut:])
            w = max(lowres_text_size(l1, font, 1, 0)[0], lowres_text_size(l2, font, 1, 0)[0])
            if best is None or w < best[0]:
                best = (w, [l1, l2])
        return best[1]

    def _draw_progress_v(self):
        """Full-width labeled progress strip between the LCD and the panel; populates self._phase_rects
        (one click column per phase) so the inherited progress-jump handler works unchanged."""
        surf = self.screen
        pygame.draw.rect(surf, chrome.PANEL_BG, pygame.Rect(0, PROG_Y, SCREEN_W, PROG_STRIP_H))
        n = len(PHASE_KEYS)
        lf = i18n.pixel_font_for_lang(self._lang, PROG_LABEL_PX)
        xs = [PROG_PAD_X + (SCREEN_W - 2 * PROG_PAD_X) * i // (n - 1) for i in range(n)]
        spacing = (SCREEN_W - 2 * PROG_PAD_X) // (n - 1)
        dot_y = PROG_Y + 13
        active = self._active_phase_idx()  # -1 on the recap step (no dot lit)
        for i in range(n - 1):
            done = i < active
            pygame.draw.line(surf, LINE_DONE if done else LINE_FUTURE, (xs[i], dot_y), (xs[i + 1], dot_y), 3)
        self._phase_rects = []
        for i, key in enumerate(PHASE_KEYS):
            done = active >= 0 and i <= active
            pygame.draw.circle(surf, DOT_DONE if done else DOT_FUTURE, (xs[i], dot_y), PROG_DOT_R)
            if i == active:
                pygame.draw.circle(surf, chrome.INK, (xs[i], dot_y), PROG_DOT_R + 3, 2)
            color = chrome.INK if done else chrome.DIM
            lines = self._wrap_phase_label(i18n.t(key), lf, spacing - PROG_LABEL_GAP)
            line_h = lowres_text_size("Ag", lf, 1, 0)[1]
            ly0 = dot_y + PROG_DOT_R + 5
            for li, line in enumerate(lines):
                lw = lowres_text_size(line, lf, 1, 0)[0]
                lx = min(max(xs[i] - lw // 2, 2), SCREEN_W - lw - 2)
                chrome.blit_lowres(surf, line, lx, ly0 + li * (line_h + PROG_LINE_GAP), lf, color, 1)
            col_left = max(0, xs[i] - spacing // 2)
            col_right = min(SCREEN_W, xs[i] + spacing // 2)
            self._phase_rects.append(pygame.Rect(col_left, PROG_Y, col_right - col_left, PROG_STRIP_H))

    def _draw_panel_v(self):
        """Step panel below the progress strip: phase heading (cyan) + body + (key/click guidance when
        the step isn't yet satisfied). Buttons hug the right edge; populates self._btn_rects with the
        keys the inherited panel-click handler expects (back / next / skip_tutorial). The Next button
        FLASHES white when the step is complete (self.predicate_satisfied) — that flash is the 'proceed'
        prompt, replacing a 'press Next' text line."""
        surf = self.screen
        pygame.draw.rect(surf, chrome.PANEL_BG, pygame.Rect(0, PANEL_Y, SCREEN_W, PANEL_H))
        pygame.draw.line(surf, chrome.FRAME, (0, PANEL_Y), (SCREEN_W, PANEL_Y), 1)

        # button column (worst-case width sets where the body wraps)
        btn_font = i18n.pixel_font_for_lang(self._lang, BTN_NATIVE)
        last = self.current_step == len(STEPS)
        ready = self.predicate_satisfied
        specs = [("back", i18n.t("tutorial.btn.back"), self.current_step > 1)]
        specs.append(("next", i18n.t("tutorial.btn.done") if last else i18n.t("tutorial.btn.next"), ready))
        if not last:
            specs.append(("skip_tutorial", i18n.t("tutorial.btn.skip_tutorial"), True))
        bw = max(tims_button_size(lbl, btn_font, _BTN_T)[0] for _, lbl, _ in specs)
        bx = SCREEN_W - BTN_EDGE_MARGIN - bw
        by = PANEL_Y + PANEL_PAD
        flash_on = (pygame.time.get_ticks() // NEXT_FLASH_MS) % 2 == 0
        self._btn_rects = {}
        for key, label, enabled in specs:
            r = pygame.Rect(bx, by, bw, BTN_H)
            # disabled → SILVER palette (conventions § "disabled = silver, not a dark scrim")
            btn_t = _BTN_T if enabled else {**_BTN_T, **chrome.DISABLED}
            state = "waiting" if (key == "next" and enabled and flash_on) else "normal"
            draw_tims_button(surf, r, label, font=btn_font, t=btn_t, state=state)
            self._btn_rects[key] = r
            by += BTN_H + BTN_GAP

        # text column (heading + body + optional key/click guidance)
        x = PANEL_PAD
        y = PANEL_Y + PANEL_PAD
        text_w = bx - BTN_GUTTER - x
        head_f = i18n.pixel_font_for_lang(self._lang, HEAD_PX)
        chrome.blit_lowres(surf, self._step_header_text(), x, y, head_f, chrome.CYAN, 1)
        y += lowres_text_size("永", head_f, 1, 0)[1] + 8

        latin_f = _font_helv(BODY_PX)
        cjk_f = _font_cjk(BODY_PX)
        body = self._step_body_text()
        if last:  # FLATTEN recap: the one-per-line keycap list → intro + a middot-joined wrapping paragraph
            ls = body.split("\n")
            items = [ln for ln in ls[1:] if ln.strip()]
            body = ls[0] + "\n" + RECAP_SEP.join(items)
        paras = [(body, chrome.INK)]
        if not ready:  # still doing the step → show the key/click guidance (button prompts are the flash)
            action = self._step_action_text()
            if action and "[[btn:" not in action:
                paras.append((action, chrome.AMBER))
        for para, color in paras:
            # split on hard newlines FIRST (\n is markup, not a glyph — feeding it to the wrapper renders
            # it as a tofu box); each hard line then soft-wraps to the column width. \n\n → a blank gap.
            for hard_line in para.split("\n"):
                if not hard_line.strip():
                    y += BLANK_GAP
                    continue
                for line in self._wrap_lines(hard_line, latin_f, cjk_f, text_w):
                    if last:  # flattened recap: drop a separator that wrapped to a line start
                        line = line.lstrip("· ")
                    img = _render_mixed(line, latin_f, cjk_f, color)
                    surf.blit(img, (x, y))
                    y += img.get_height() + BODY_GAP
            y += 4


def run_on(screen):
    """Run the interactive vertical-fit tutorial on ``screen`` until the user finishes / skips / ESCs /
    band-Home. Returns None (a terminal view — nothing to bubble up). Falls back to a message if the
    sim can't boot (no-audio build)."""
    tut = BasicTutorial(screen, ACTIVE_LANG)
    tut.run()  # inherited loop: embed_setup() → render_frame()/flip/_handle_events() → teardown
    return "home" if tut._exit_to_home else None  # band Home propagates past the menu; ESC/Done/Skip → menu


def run_interactive():
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("basic-usage tutorial (vertical-fit)")
    run_on(screen)
    pygame.quit()


def save_screenshot(path, step=1):
    from app_paths import project_root

    pygame.init()
    pygame.font.init()
    pygame.mouse.set_cursor = lambda *a, **k: None  # dummy video driver has no cursor subsystem
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    tut = BasicTutorial(screen, ACTIVE_LANG)
    if tut.embed_setup():
        if step != 1:
            tut._jump_to_step(step)
        tut.render_frame()
    out = str(project_root() / path)
    pygame.image.save(screen, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H}) step={step}")

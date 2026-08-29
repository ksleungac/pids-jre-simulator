# SPDX-License-Identifier: MIT
"""Application settings (設定), TIMS-styled. One section today: the remote terminal.

# CONTRACT: this page holds APPLICATION settings, not feature settings.
# A setting that belongs to one feature lives where that feature is used — the OCR lead/interval
# steppers are on the PA page beside 自動放送始発起動, and the train model is picked there too.
# That is deliberate and stays (author, 2026-08-29: "OCR settings already has its access path down
# the tims, this settings i thought was for other settings than OCR or PA"). Do not migrate them
# here; a second page editing the same settings.json keys is the drift this note exists to prevent.
#
# So the page is titled 設定 and each group gets a section heading. Growth path: when the groups
# outgrow one screen, the sections become the entries of a second-level menu, with nothing moved.

Mirroring used to be reachable only as a launch flag (`--stream` / `--stream-lan`), which meant
the feature existed and nobody could find it. This section is the switch, and it is what the band's
green mirror-address row (`tims/band.py`) exists to pay off.

Two controls:
  * ACCESS — a three-position picker, one cell lit. It is exactly ``frame_stream.MODES``: off /
    this PC / network. Not two checkboxes: the three are mutually exclusive, and the middle one is
    the whole point of having three — a loopback socket is unreachable from the network, so it
    needs no Windows firewall grant, while the network position does.
  * PORT — a stepper over a narrow range. The realistic need is "8541 is taken, give me another",
    which ±1 serves; a wide range would only make the stepper useless.

Working-copy semantics, the same as the OCR settings page it is modelled on: both controls edit an
in-memory copy, 設定 commits, and 返回 / ESC / band Home revert to the entry snapshot.

Preview:  uv run _dev_scripts/preview_setup_tims.py --screen stream
"""

import pygame

import frame_stream
import i18n
from ..widgets import draw_lowres_number, draw_tims_button, lowres_text_size, press_transition, tims_button_size

from .. import band
from .. import chrome
from . import dims

ACTIVE_LANG = "zh_HK"  # develop/preview in zh_HK (chrome is i18n)

# fmt: off
# ── layout tuneables ──────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = dims.SCREEN_W, dims.SCREEN_H
BG_COLOR           = dims.BG_COLOR

SETTINGS_CODE      = "C07AJ"               # screen code, alongside ocr_setting's C07AG / C07AH

PANEL_X            = 24                    # matches the OCR pages' inset, so the footers line up
FOOTER_H           = 60
TITLE_NATIVE       = 20                    # row-label px (the OCR settings page's label size)
FOOT_NATIVE        = 20                    # footer button px — 2-char bar buttons
NOTE_NATIVE        = 15                    # caution / caption px
LINE_GAP_PX        = 4

# Section heading. Cyan at the ROW-LABEL size read as merely coloured text — a heading has to
# outrank the labels under it, so it is larger AND carries a hairline rule across the content
# width. The rule is what actually makes it a section: one more line of cyan does not.
SECTION_NATIVE     = 24                    # > TITLE_NATIVE (20), < the title row's own size
SECTION_RULE_COLOR = chrome.FRAME
SECTION_RULE_GAP   = 7                     # heading ink bottom -> its rule
TITLE_ROW_H        = 40                    # what chrome.title_row occupies below the band
TITLE_GAP          = 30                    # title row -> the first section heading
HEAD_GAP           = 24                    # section rule -> that section's first row
ROW_GAP            = 20                    # between rows within a section

# Label left x, shared by every row AND by the section rule — so the content block, the section
# rule and the footer buttons all sit on ONE left edge, and the rule's margins are symmetric
# (PANEL_X either side). It was 90, inherited from the OCR page whose rows carry no rule to expose
# the indent; here the rule ran 90 -> 706 and the whole block visibly hung right.
ROW_X              = PANEL_X
# Where a row's control starts. 190 rather than the OCR page's 210 because THREE cells have to fit
# on one row: measured, the widest locale's access row is 414px, which lands 12px inside the right
# margin from here and would overflow from 210. The labels were shortened for the same reason —
# en `Network` alone is 205px at this face, so `Off / PC / LAN` is what makes the row fit in every
# locale (conventions.md § UI code style, fixed-column multi-locale label strips).
CONTROL_X          = ROW_X + 190
ROW_H              = 44                    # control height; both rows use it so they read as a group
MODE_GAP           = 8                     # gap between the three access cells
NOTE_GAP           = 9                     # a row -> its own caption underneath
PORT_VALUE_W       = 120                   # port readout box (the OCR stepper's value box width)
STEP_W             = 44                    # − / ＋ button width
STEP_GAP           = 8
STEP_VALUE_NATIVE  = 26                    # fat TIMS numerals in the value box

INK                = chrome.INK
DIM                = chrome.DIM
AMBER              = chrome.AMBER          # the firewall caution — same role as the OCR page's resolution note
PANEL_BG           = chrome.PANEL_BG
PANEL_BORDER       = chrome.FRAME

# The RANGE is frame_stream's — it declares itself the sole owner because `main.py` binds the
# persisted value long before this page could clamp it. Only the step is this page's own knob.
PORT_MIN, PORT_MAX = frame_stream.PORT_MIN, frame_stream.PORT_MAX
PORT_STEP = 1
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

_MODE_KEYS = {m: f"setup_tims.stream.mode.{m}" for m in frame_stream.MODES}
_FOOT_T = {**chrome.BTN_BAR, "v_pad": 9}  # the OCR pages' footer button, so 返回/設定 match across pages
# Page-button preset, centred label — but content-sized. BTN_LABEL inherits the primitive's `min_w`,
# which is meant for a lone page button; three of them across one row overflowed the screen and the
# 區域網絡 cell fell off the right edge. `min_w: 0` is the same escape BTN_STEP takes for the same reason.
_MODE_T = {**chrome.BTN_LABEL, "min_w": 0}
_STEP_T = chrome.BTN_STEP

# Working copy + the entry snapshot 返回 reverts to. None = not entered yet (see run_settings).
_mode = frame_stream.DEFAULT_MODE
_port = frame_stream.DEFAULT_PORT
_entry_mode = None
_entry_port = None


def _load_state():
    global _mode, _port
    s = i18n.load_settings()
    # Both through frame_stream's cleaners — one implementation of "a persisted value becomes a
    # usable one", so this page cannot clamp differently from what `main.py` will actually bind.
    _mode = frame_stream.clean_mode(s.get("stream_mode"))
    _port = frame_stream.clean_port(s.get("stream_port"))


def _save_state():
    """Persist the working copy AND make it true immediately.

    Applying here rather than at next launch is what lets the band's address row appear the moment
    you press 設定 — the row is the whole payoff of turning this on, and a setting whose effect you
    cannot see is indistinguishable from one that did not save. A failed bind is loud on its own
    (`frame_stream.start` prints it), and leaves mirroring off, which the band then shows honestly
    by drawing no row at all.
    """
    s = i18n.load_settings()
    s["stream_mode"], s["stream_port"] = _mode, _port
    i18n.save_settings(s)
    frame_stream.apply_mode(_mode, _port)


def _mode_cell_size(font):
    """One size for all three access cells — the worst-case label sets it and the shorter ones centre
    inside (`conventions.md` § UI code style: grouped buttons share size AND design). Measured in the
    ACTIVE locale's face, because the labels differ in width per locale."""
    w = max(tims_button_size(i18n.t(k), font, _MODE_T)[0] for k in _MODE_KEYS.values())
    return w, ROW_H


def _section(surf, text, y):
    """Draw a section heading at ``y`` plus its hairline rule; return the y the section's first row
    starts at. One helper because every group added to this page needs the identical pair, and two
    hand-placed copies would drift the moment one is nudged."""
    f = i18n.pixel_font_for_lang(ACTIVE_LANG, SECTION_NATIVE)
    h = lowres_text_size(text, f, 1, 0)[1]
    chrome.blit_lowres(surf, text, ROW_X, y, f, chrome.CYAN, 1)
    ry = y + h + SECTION_RULE_GAP
    pygame.draw.line(surf, SECTION_RULE_COLOR, (ROW_X, ry), (SCREEN_W - PANEL_X, ry))
    return ry + HEAD_GAP


def render_settings(screen):
    """Draw the remote-terminal settings view; return hit-rects."""
    screen.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(screen)
    # The PAGE is 設定 (the home card's own label — one name for the door and the room); the
    # remote terminal is a SECTION on it. See the contract at the top of this module.
    chrome.title_row(screen, SETTINGS_CODE, i18n.t("setup_tims.action.settings"), ACTIVE_LANG)

    label_font = i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE)
    mode_font = i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE)
    note_font = i18n.pixel_font_for_lang(ACTIVE_LANG, NOTE_NATIVE)

    # Section heading + its rule. A second group added below gets the same pair and reads as a peer.
    y = _section(screen, i18n.t("setup_tims.stream.heading"), band.BAND_H + TITLE_ROW_H + TITLE_GAP)

    # ── ACCESS: three cells, one LIT. Steady yellow ("pressed") rather than a flash, because a
    #    separate 設定 button carries the proceed cue — the route/diagram pickers' idiom exactly.
    lh = lowres_text_size(i18n.t("setup_tims.stream.mode_label"), label_font, 1, 0)[1]
    chrome.blit_lowres(screen, i18n.t("setup_tims.stream.mode_label"), ROW_X, y + (ROW_H - lh) // 2, label_font, INK, 1)
    cw, ch = _mode_cell_size(mode_font)
    mode_rects = {}
    for i, m in enumerate(frame_stream.MODES):
        rect = pygame.Rect(CONTROL_X + i * (cw + MODE_GAP), y, cw, ch)
        draw_tims_button(screen, rect, i18n.t(_MODE_KEYS[m]), font=mode_font, t=_MODE_T, state="pressed" if m == _mode else "normal")
        mode_rects[m] = rect

    # Firewall caution, under the cells. AMBER = "this one costs you something", the same weight the
    # OCR page gives its resolution line. ONE line by request — the longer version explained what
    # network access lets other devices do, which is a tutorial's job, not a settings row's.
    ny = y + ROW_H + NOTE_GAP
    note_w = SCREEN_W - CONTROL_X - PANEL_X
    for line in chrome.wrap_lines(i18n.t("setup_tims.stream.firewall_note"), note_font, note_w):
        if line:
            chrome.blit_lowres(screen, line, CONTROL_X, ny, note_font, AMBER, 1)
        ny += lowres_text_size("永", note_font, 1, 0)[1] + LINE_GAP_PX

    # ── PORT: [−] value [＋], the OCR settings page's stepper shape, redrawn here rather than
    #    imported because that one is private to its module and carries its own label column.
    py = ny + ROW_GAP
    plh = lowres_text_size(i18n.t("setup_tims.stream.port_label"), label_font, 1, 0)[1]
    chrome.blit_lowres(screen, i18n.t("setup_tims.stream.port_label"), ROW_X, py + (ROW_H - plh) // 2, label_font, INK, 1)
    minus_rect = pygame.Rect(CONTROL_X, py, STEP_W, ROW_H)
    value_box = pygame.Rect(minus_rect.right + STEP_GAP, py, PORT_VALUE_W, ROW_H)
    plus_rect = pygame.Rect(value_box.right + STEP_GAP, py, STEP_W, ROW_H)
    can_dec, can_inc = _port > PORT_MIN, _port < PORT_MAX
    draw_tims_button(screen, minus_rect, "−", font=label_font, t=_STEP_T if can_dec else {**_STEP_T, **chrome.DISABLED})
    draw_tims_button(screen, plus_rect, "＋", font=label_font, t=_STEP_T if can_inc else {**_STEP_T, **chrome.DISABLED})
    pygame.draw.rect(screen, PANEL_BG, value_box)
    pygame.draw.rect(screen, PANEL_BORDER, value_box, 1)
    num_font = i18n.pixel_font_for_lang("en", STEP_VALUE_NATIVE)
    nw = draw_lowres_number(pygame.Surface((1, 1)), str(_port), (0, 0), num_font, INK, k=1)[0]
    draw_lowres_number(screen, str(_port), (value_box.centerx - nw // 2, value_box.centery - num_font.get_height() // 2), num_font, INK, k=1)

    # ── footer: 返回 (revert) bottom-left, 設定 (commit) bottom-right — a grouped pair, one size.
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE)
    back_label, set_label = i18n.t("setup_tims.back"), i18n.t("setup_tims.set")
    bw = max(tims_button_size(back_label, btn_font, _FOOT_T)[0], tims_button_size(set_label, btn_font, _FOOT_T)[0])
    bh = tims_button_size(set_label, btn_font, _FOOT_T)[1]
    fy = SCREEN_H - FOOTER_H
    back_rect = pygame.Rect(PANEL_X, fy, bw, bh)
    set_rect = pygame.Rect(SCREEN_W - PANEL_X - bw, fy, bw, bh)
    changed = _entry_mode is not None and (_mode != _entry_mode or _port != _entry_port)
    set_state = "waiting" if (changed and (pygame.time.get_ticks() // 450) % 2 == 0) else "normal"
    draw_tims_button(screen, back_rect, back_label, font=btn_font, t=_FOOT_T)
    draw_tims_button(screen, set_rect, set_label, font=btn_font, t=_FOOT_T, state=set_state)
    return {
        "home": band_hits["home"],
        "back": back_rect,
        "set": set_rect,
        "modes": mode_rects,
        "port_minus": minus_rect,
        "port_plus": plus_rect,
    }


def _tap(screen, rect, label, t):
    """Momentary yellow press for an in-place control (mode cell, stepper): no loading beat, because
    nothing navigates — the value changes on this page."""
    press_transition(
        screen,
        rect=rect,
        label=label,
        font=i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE),
        t=t,
        redraw=lambda s: render_settings(s),
        blank_color=BG_COLOR,
        blank_ms=0,
        pressed_ms=80,
    )


def _leave(screen, rect, label):
    """The yellow press + loading beat every navigating button on this page shares (返回 / 設定 / Home)."""
    press_transition(
        screen,
        rect=rect,
        label=label,
        font=i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE),
        t=_FOOT_T,
        redraw=lambda s: render_settings(s),
        blank_color=BG_COLOR,
        blank_ms=450,
        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
    )


def run_settings(screen):
    """Run the page until 設定 / 返回 / Home. Working-copy semantics: the controls edit an in-memory
    copy and ONLY 設定 persists. Returns "home" on band Home (the caller bubbles it to the menu),
    None otherwise."""
    global _mode, _port, _entry_mode, _entry_port
    _load_state()
    _entry_mode, _entry_port = _mode, _port  # snapshot for 返回 = revert
    clock = pygame.time.Clock()
    while True:
        hits = render_settings(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                _mode, _port = _entry_mode, _entry_port
                return None
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                _mode, _port = _entry_mode, _entry_port  # ESC = cancel → revert
                return None
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if band.click_stream(event.pos):  # band mirror address → open it in the PC's browser
                    continue
                if hits["home"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE),
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=lambda s: render_settings(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    _mode, _port = _entry_mode, _entry_port  # Home discards unconfirmed edits
                    return "home"
                elif hits["set"].collidepoint(event.pos):
                    _leave(screen, hits["set"], i18n.t("setup_tims.set"))
                    _save_state()
                    return None
                elif hits["back"].collidepoint(event.pos):
                    _leave(screen, hits["back"], i18n.t("setup_tims.back"))
                    _mode, _port = _entry_mode, _entry_port
                    return None
                elif hits["port_minus"].collidepoint(event.pos):
                    if _port > PORT_MIN:  # silver at the bound → no tap, no change
                        _tap(screen, hits["port_minus"], "−", _STEP_T)
                        _port = max(PORT_MIN, _port - PORT_STEP)
                elif hits["port_plus"].collidepoint(event.pos):
                    if _port < PORT_MAX:
                        _tap(screen, hits["port_plus"], "＋", _STEP_T)
                        _port = min(PORT_MAX, _port + PORT_STEP)
                else:
                    for m, rect in hits["modes"].items():
                        if rect.collidepoint(event.pos) and m != _mode:
                            _tap(screen, rect, i18n.t(_MODE_KEYS[m]), _MODE_T)
                            _mode = m  # the cell now draws steady yellow; 設定 starts flashing
                            break


# ── dev preview ──────────────────────────────────────────────────────────────────
def run_interactive():
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("TIMS remote-terminal settings (draft)")
    run_settings(screen)
    pygame.quit()


def save_screenshot(path):
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))  # set_mode so blits work headless
    _load_state()
    render_settings(screen)
    from app_paths import project_root

    out = str(project_root() / path)
    pygame.image.save(screen, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H})")

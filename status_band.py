"""Persistent TIMS status band — the near-black top strip.

Two callers, one module (lives at project root so both import DOWN into it):
  * the ``setup_tims`` screens render it as persistent chrome across the setup flow
    (``status=None`` → the placeholder no-readings mode);
  * the live in-drive app (``app.py::PASimulator._render_panel``) renders it as the
    OCR debug panel, feeding a live ``auto_input.driver`` status dict.

It IS the OCR debug panel — promoted from ``setup_tims/band.py`` when the live
wiring landed. Width is taken from the caller's surface (``surf.get_width()``); the
setup-window dims (SCREEN_W/H) live in ``setup_tims/dims.py`` — never a band concept.

  * LEFT         — OCR state, SMALL k=1: segment · inferred·played · BADGE.
  * CENTER       — readout cell: speed limit / speed / distance(m), WIDE numerals.
  * CENTER-RIGHT — two dim message strips (re-aligning / fire / stopping / paused), yellow flash.
  * RIGHT        — control cluster [pause][save][home], uniform squares; home always rightmost.
"""

import time

import pygame

import i18n
import tims_chrome as chrome  # shared palette + low-res text blit (chrome.blit_lowres)
from widgets import (
    _TUNEABLES_TIMS_BUTTON,
    HINT_CYAN_COLOR,
    HINT_INK_COLOR,
    draw_tims_button,
    lowres_text_size,
    press_transition,
)

# TIMS band face = Noto Sans, per-locale, AA-OFF at native px, NO upscale (WIP § Font decision).
# Resolved via i18n.pixel_font_for_lang. Left-column px are per-line (NOTIF_/STATE_NATIVE); the
# message-strip px lives in the MSG block below (MSG_NATIVE).

# fmt: off
# ── band layout tuneables (all derived coords flow from these) ────────────────
ACTIVE_LANG        = "zh_HK"           # UI language shown on the band (synced from the active screen)

# persistent TIMS status band (top strip, full width). Height reconciled with the live window carve
# (constants.DEBUG_PANEL_HEIGHT is DERIVED from BAND_H). The readout cell is a PLACEHOLDER swapped for
# live OCR fields ("might not be clock") — don't chase TIMS-clock fidelity. Rightmost button = ALWAYS home.
BAND_H             = 68                # shorter band (rows sit on an 8 / 26 / 44 grid)
BAND_COLOR         = chrome.PANEL_BG       # near-black strip

# LEFT column — green notification + OCR state (segment + inferred state), stacked, SMALL. Station
# names ONLY ever surface here, so k=1 keeps the dense left column from crowding the band (the real
# TIMS left column is small dense text — a k=2 segment would dominate the strip).
LEFT_X             = 12
NOTIF_TEXT         = "ツウコク　ジョウホウ"  # green notif — tims_002 通告情報, full-width gap. INTENDED fixed-JP (a real TIMS system label, like station names) — NOT an i18n miss; don't localize (user 2026-07-11)
NOTIF_NATIVE       = 11                # green notif px — SMALLER (least-important line)
NOTIF_COLOR        = chrome.GREEN     # TIMS dot-matrix green
STATE_NATIVE       = 16                # OCR state + badge px — LARGER (primary band info)
STATE_INK          = chrome.INK
STATE_SUB          = chrome.DIM   # dimmer secondary line

# CENTER readout cell — speed limit / speed / distance (OCR placeholders), right-aligned between
# separators. The LIMIT is PLAIN at rest (no highlight); cyan is the CHANGE CUE only — when the limit
# value just changed it BLINKS cyan↔plain for LIMIT_FLASH_WINDOW seconds, then settles back to plain.
# If SPEED exceeds the LIMIT the limit block flashes RED (over-speed warning). Both the change-flash
# and over-speed are driven off live OCR deltas (driver stamps limit_change_ts, like last_fire).
CELL_X             = 222               # readout cell left edge — right of the (now wider) folded left column
CELL_W             = 120
CELL_PAD           = 3
SEP_COLOR          = chrome.FRAME   # vertical separators flanking the cell
SEP_W              = 2
CELL_INK           = chrome.INK   # the number ink (bright)
CELL_UNIT_INK      = (130, 144, 156)   # unit (km/h, m) ink — DIMMER than the number, not so bright
READOUT_NUM_H       = 18            # number rendered HEIGHT (px). SUPERSAMPLED (drawn big AA-on, scaled
                                    # DOWN) so this in-between size reads SMOOTH, not blocky — the pixel
                                    # face is crisp only at 12/24, so a size between them must be either
                                    # sub-grid (blocky, heavy strokes) or supersampled (this). Strokes
                                    # stay proportional ("pixel but not squary").
READOUT_NUM_SS_NATIVE = 18          # readout number load px — AA-off native (supersample retired)
READOUT_UNIT_K      = 1             # unit stays crisp pixel (draw_lowres) at its own native grid
READOUT_UNIT_NATIVE = 15            # unit native (≈15px) — larger; bottom-aligned to the number baseline (grows upward), rendered dim
READOUT_DIGIT_XSCALE = 1.3          # WIDE TIMS numerals: widen each digit, independent of the gap
READOUT_DIGIT_GAP    = 2            # px between digits at the rendered size
READOUT_UNIT_GAP     = 2            # gap between the number and its unit (km/h, m) — tight, unit sits close
READOUT_UNIT_CELL_GAP = 1           # px BETWEEN the fat full-width unit glyphs (proportional advance); ≤1 keeps them touching/near-touching
LIMIT_UNIT         = "km/h"           # units for the '--' no-readings display (live values carry their own)
SPEED_UNIT         = "km/h"
DIST_UNIT          = "m"              # distance is ALWAYS metres (OCR reads m; finer than rounded km)
LIMIT_Y            = 18                # BAND ROW BASELINES — shared by readout AND left state column (rows line up); ink bottom-aligns here
SPEED_Y            = 39
DIST_Y             = 60
LIMIT_LABEL        = "制限"            # 2-char row label AHEAD of the limit number = "this is the speed limit"
                                       # (the game HUD labels it 最高速度; band cell dropped labels — this restores
                                       # a short one). The label IS the identity cue → the number stays plain
                                       # (no red ink). Fixed-JP (a HUD label, like NOTIF_TEXT) — not localized.
LIMIT_LABEL_COLOR  = (150, 164, 178)   # dim slate — a quiet annotation; the bright number stays the focus
LIMIT_LABEL_NATIVE = 16                # label px (AA-off native) — max that clears a 3-digit limit (100–130); a
                                       # 3-digit "120 km/h" number starts ~x262, label at LIMIT_LABEL_X ends ~x257
LIMIT_LABEL_X      = CELL_X + 3        # label left edge (just inside the cell's left separator at CELL_X)
LIMIT_PAD_X        = 3                 # cyan limit block inset (x) — tight (hugs ink)
LIMIT_PAD_Y        = 1
LIMIT_FLASH_MS     = 400               # half-period of the change blink (cyan↔plain)
LIMIT_FLASH_WINDOW = 2.5               # seconds the change-blink runs after a limit change, then plain
OVER_LIMIT_BG      = (190, 30, 34)     # over-speed warning: the LIMIT block flashes this red (not the cell)
OVER_LIMIT_INK     = (245, 240, 240)   # light ink on the red block (dark cyan-ink would vanish on red)
OVER_LIMIT_FLASH_MS = 350              # half-period of the red over-limit block flash

# MESSAGE strips (center-right) — the original TIMS "two dim bars" look, restored where the OCR
# state used to sit. Houses the OCR fire event (top) + stopping-position reading (bottom).
MSG_X              = 350               # strips left edge (right of the readout cell, which ends ~342)
MSG_GAP_R          = 10                # gap before the control-button cluster (strips end here)
STRIP_H            = 24
STRIP_GAP          = 5
STRIP_Y1           = 10                # strips nearer the band top (+ taller STRIP_H) → more reading space
STRIP_RADIUS       = 0                 # SHARP corners — no rounding (user: strips are sharp, not smooth)
STRIP_COLOR        = (34, 46, 58)      # dim slate — TIMS message-strip fill
MSG_K              = 1
MSG_NATIVE         = 17                # message-strip text px (AA-off native) — bumped from 13; strip is 24px tall
MSG_FLASH_MS       = 450               # message-display flash half-period (bright yellow, auto-clears)
MSG_PAD_X          = 6                 # text inset inside a strip

BAND_BTN_GAP       = 6                 # gap between the right-edge control buttons (pause/save/home)
HOME_MARGIN        = 4                 # rightmost band button = "return to home" — small margin = cluster hugs the corner
HOME_TEXT_MARGIN   = 5                 # gap between the label block and the bevel — sets the control-square size (−1 → box 2px smaller)
BAND_BTN_BOX_K     = 1                 # box hugs the native label (AA-off, no upscale) + HOME_TEXT_MARGIN
BAND_BTN_BOX_NATIVE  = 17              # px the SQUARE is sized to — FROZEN (bumping the label px must NOT grow the box)
BAND_BTN_TEXT_NATIVE = 20              # band-button LABEL render px — bigger than the box-sizing px → text grows, box stays
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# Band buttons (labels in translations_app.json — keys setup_tims.band.home / .pause / .save): rightmost
# = return-to-home (persistent across screens); left of it the migrated OCR-panel controls — pause the
# auto-driver + save the driving record. Same TIMS button primitive, uniform squares.
_BAND_BTN_TUNEABLES = {
    **_TUNEABLES_TIMS_BUTTON,
    "text_align": "center",
    "text_pad": 0,  # margin lives in the CONTENT-SIZED box (HOME_TEXT_MARGIN), not here — an
    # internal pad on top of the box margin double-counts and starves k to 1
    "text_max_k": 1,  # SMALL band-button text (k=1 native pixel) — matches the k=1 left column /
    # message strips. Box stays sized to BAND_BTN_BOX_K so the SQUARE keeps its
    # size; only the label shrinks (font smaller, NOT the button)
    "line_gap": 3,  # true visual gap between the 2 rows (ink-based line stacking)
}

_digit_cell_cache: dict = {}


def _tims_digit_cell(font, gap):
    """Cached full-width TIMS digit metrics for `font`: (cell_w, {d: ink_bbox}, ink_top, ink_bot). Each
    digit is the FAT full-width glyph (U+FF10..19); the monospace cell = widest digit ink + `gap`, ink
    centered. ink_top/ink_bot = vertical ink extent shared across digits (baseline align)."""
    key = (id(font), gap)
    v = _digit_cell_cache.get(key)
    if v is None:
        boxes = {}
        maxw = 0
        tops, bots = [], []
        for d in "0123456789":
            bb = font.render(chr(0xFF10 + int(d)), False, (255, 255, 255)).get_bounding_rect()
            boxes[d] = bb
            if bb.w:
                maxw = max(maxw, bb.w)
            if bb.h:
                tops.append(bb.y)
                bots.append(bb.y + bb.h)
        top = min(tops) if tops else 0
        bot = max(bots) if bots else font.get_height()
        v = (maxw + gap, boxes, top, bot)
        _digit_cell_cache[key] = v
    return v


def _number_ink(text, font, gap):
    """(ink_top, ink_bot, width) of a FAT full-width TIMS numeral run (see _draw_number_ss). Digits sit
    on a monospace cell (widest digit ink + gap); separators/units render natural half-width inline.
    ink_top/ink_bot = vertical ink extent (baseline-align + highlight-block hug); width = run width."""
    cell, boxes, dtop, dbot = _tims_digit_cell(font, gap)
    tops, bots = [], []
    w = 0
    for ch in text:
        if ch.isdigit():
            w += cell
            tops.append(dtop)
            bots.append(dbot)
        else:
            bb = font.render(ch, False, (255, 255, 255)).get_bounding_rect()
            w += font.size(ch)[0]
            if bb.h:
                tops.append(bb.y)
                bots.append(bb.y + bb.h)
    top = min(tops) if tops else 0
    bot = max(bots) if bots else font.get_height()
    return top, bot, w


def _draw_number_ss(surf, text, pos, font, color, target_h, xscale, gap):
    """FAT TIMS numeral run, AA-OFF: each DIGIT is the full-width glyph (U+FF10..19) centered on a
    monospace cell (widest digit ink + `gap`) — the 全角 TIMS look; separators/unit letters render
    natural HALF-width inline. `target_h`/`xscale` unused (kept for caller compat). `pos` = top-left of
    the full-height run; digit ink keeps the font's natural baseline (caller bottom-aligns via pos.y)."""
    cell, boxes, _dt, _db = _tims_digit_cell(font, gap)
    x = int(pos[0])
    y0 = pos[1]
    for ch in text:
        if ch.isdigit():
            bb = boxes[ch]
            g = font.render(chr(0xFF10 + int(ch)), False, color)  # AA OFF, full-width fat glyph
            surf.blit(g, (x + (cell - bb.w) // 2 - bb.x, y0))  # ink centered in the monospace cell
            x += cell
        else:
            surf.blit(font.render(ch, False, color), (x, y0))  # separator / unit letter, natural half-width
            x += font.size(ch)[0]


def _fullwidth(ch: str) -> str:
    """ASCII printable → its FAT full-width (全角) form (`k`→`ｋ`) — same family as the full-width
    digits. Exception: `/` stays natural — the full-width `／` is ~2× wider than the letters and
    would balloon the monospace cell; the narrow natural slash reads better between them."""
    if ch == "/":
        return ch
    o = ord(ch)
    return chr(o + 0xFEE0) if 0x21 <= o <= 0x7E else ch


_unit_cell_cache: dict = {}


def _unit_ss_metrics(unit, font, gap):
    """Metrics for the FAT full-width unit run, rendered PROPORTIONALLY (each glyph advances by its
    own ink width + `gap`, so `gap=0` makes the glyphs TOUCH — the dense CJK look). A uniform cell
    floats the narrow glyphs (`/`), which reads as bad spacing; proportional keeps the fat glyphs
    butting. Returns (ink_top, ink_bot, total_w)."""
    key = (id(font), gap, unit)
    v = _unit_cell_cache.get(key)
    if v is None:
        tops, bots = [], []
        total = 0
        for i, ch in enumerate(unit):
            bb = font.render(_fullwidth(ch), False, (255, 255, 255)).get_bounding_rect()
            total += bb.w + (gap if i < len(unit) - 1 else 0)  # gap BETWEEN glyphs, not after the last
            if bb.h:
                tops.append(bb.y)
                bots.append(bb.y + bb.h)
        top = min(tops) if tops else 0
        bot = max(bots) if bots else font.get_height()
        v = (top, bot, total)
        _unit_cell_cache[key] = v
    return v


def _draw_unit_ss(surf, unit, pos, font, color, gap):
    """Draw `unit` (km/h / m) in FAT full-width forms, glyphs advancing by their own width + `gap`
    (gap=0 → touching). Matches the digits' fat look at the unit font size. `pos` = top-left of the
    run; caller bottom-aligns via pos.y (ink bottom lands on the baseline)."""
    x = int(pos[0])
    y0 = pos[1]
    for ch in unit:
        f = _fullwidth(ch)
        bb = font.render(f, False, (255, 255, 255)).get_bounding_rect()
        surf.blit(font.render(f, False, color), (x - bb.x, y0))  # ink flush at x
        x += bb.w + gap


def _blit_readout(
    surf, number, unit, rx, baseline, num_font, unit_font, color, unit_color, *, highlight=False, hl_color=HINT_CYAN_COLOR, hl_ink=HINT_INK_COLOR
):
    """One readout value, ink BOTTOM-ALIGNED to `baseline` and right-anchored at `rx`: an AA-off TIMS
    numeral run (_draw_number_ss) + a SMALLER, DIMMER unit rendered on the SAME monospace + full-width
    model (_draw_unit_ss), both sitting on the SAME baseline.
    `highlight` paints a block that HUGS the ink (not the font's full leading box, which sat too tall
    and too high) — the speed-limit's always-on cyan cue, its change blink, or the red over-speed flash."""
    n_top, n_bot, nw = _number_ink(number, num_font, READOUT_DIGIT_GAP)
    u_top, u_bot, uw = _unit_ss_metrics(unit, unit_font, READOUT_UNIT_CELL_GAP)
    total_w = nw + READOUT_UNIT_GAP + uw
    x0 = rx - total_w
    num_ink = hl_ink if highlight else color
    unit_ink = hl_ink if highlight else unit_color
    num_y = baseline - n_bot  # full-height glyph cell shifted so the digit ink bottom lands on baseline
    unit_y = baseline - u_bot  # unit ink bottom on the same baseline (bottom-aligned with the number)
    if highlight:
        block_top = min(num_y + n_top, unit_y + u_top)
        block = pygame.Rect(x0, block_top, total_w, baseline - block_top)
        pygame.draw.rect(surf, hl_color, block.inflate(2 * LIMIT_PAD_X, 2 * LIMIT_PAD_Y), border_radius=3)
    _draw_number_ss(surf, number, (x0, num_y), num_font, num_ink, READOUT_NUM_H, READOUT_DIGIT_XSCALE, READOUT_DIGIT_GAP)
    _draw_unit_ss(surf, unit, (x0 + nw + READOUT_UNIT_GAP, unit_y), unit_font, unit_ink, READOUT_UNIT_CELL_GAP)


_MSG_YELLOW = (250, 228, 70)  # TIMS message-display yellow (strips flash this, then auto-clear)
_SAVE_KEYS = {  # Save-button confirmation → top message strip (phase set on sim.last_save by the driver)
    "generating": "panel.save.generating",
    "saved": "panel.save.saved",
    "failed": "panel.save.failed",
    "nolog": "panel.save.nolog",
}
SAVE_NOTICE_WINDOW = 3.0  # seconds a terminal save phase (saved/failed/nolog) shows; "generating" holds
SAVE_GENERATING_MAX = 20.0  # failsafe: drop a stuck "generating" after this (thread died before flipping)


def _save_message(save_notice):
    """Resolve `sim.last_save` {ts, phase} → a localized strip message, or None when stale/absent.
    'generating' holds up to SAVE_GENERATING_MAX (async render can outlast the terminal window);
    terminal phases (saved/failed/nolog) show for SAVE_NOTICE_WINDOW then clear."""
    if not save_notice:
        return None
    phase = save_notice.get("phase")
    key = _SAVE_KEYS.get(phase)
    if not key:
        return None
    age = time.time() - save_notice.get("ts", 0)
    window = SAVE_GENERATING_MAX if phase == "generating" else SAVE_NOTICE_WINDOW
    return i18n.t(key) if age < window else None


# Layer-2 badge folds onto the state line in STATE_SUB (dim) — decision: NO confidence colour on it.

# The band reads the SAME i18n strings the live OCR debug panel uses (auto_input/driver.py:
# _STATE_KEY / _FIRE_KEY → data/translations_app.json `panel.*`). Mirrored here (local const, not
# imported — keeps the band off the heavy cv2/numpy driver module). i18n.t() resolves to the active
# UI language (zh_HK in the preview).
#   The Layer-2 BADGE is the deliberate exception: shown as its RAW canonical token (STOPPED / MOVING
#   / PASSING), NOT localized. It's the raw OCR template-match read, and a localized badge collides
#   visually with the (also-localized) inferred state right above it (badge 行駛 vs state 行駛中; or
#   both 停止). Raw keeps the measured(Layer-2)-vs-inferred(Layer-3) split legible — same rationale the
#   panel keeps "OCR" unlocalized.
_STATE_KEYS = {
    "IDLE": "panel.state.idle",
    "STOPPED": "panel.state.stopped",
    "DEPARTING": "panel.state.departing",
    "CRUISING": "panel.state.cruising",
    "ARRIVING": "panel.state.arriving",
}
_FIRE_KEYS = {
    "departure": "panel.fire.departure",
    "arrival": "panel.fire.arrival",
    "at-station": "panel.fire.atstation",
}


# NOTE: the live-status branch below (status != None) is exercised by the live in-drive app
# (app.py::_render_panel feeds the auto_input.driver status dict). The setup_tims callers pass
# status=None → only the placeholder branch runs there. Don't flag either branch as dead.
def _band_vals(status, sim_state, stops):
    """Map a live OCR `status` dict (auto_input.driver shape) onto the band's display fields. `status`
    None → standalone placeholders (home-menu preview). Encodes the OCR-panel migration decisions:
    badge grouped with the state (left column), NO confidence colour, events → the yellow strips."""
    if not status:
        # Setup stage: OCR is NOT running yet → the NO-READINGS state. Only the green notif hint shows;
        # no segment, no speed / limit / distance readings (dim '--'), no fire/stop messages, no cyan or
        # yellow flashing. Applies to EVERY setup_tims screen (all pre-OCR). The live-status branch below
        # drives the real readings once auto_input feeds a status dict.
        return {
            "left": [
                (NOTIF_TEXT, NOTIF_COLOR, NOTIF_NATIVE, "name"),
            ],
            "limit": ("--", LIMIT_UNIT),
            "speed": ("--", SPEED_UNIT),
            "dist": ("--", DIST_UNIT),
            "limit_changed": False,
            "over_limit": False,
            "msgs": [],
            "paused": False,
            "no_readings": True,
        }
    curr = sim_state.curr_stop if sim_state else 0
    n = len(stops or [])

    def nm(i):
        return stops[i].get("name", "?") if 0 <= i < n else "?"

    badge = status.get("badge")
    seg_start = status.get("segment_start_stop")
    if badge == "STOPPED" or seg_start is None or seg_start == curr:
        seg = nm(curr)
    else:
        seg = f"{nm(seg_start)} → {nm(curr)}"
    sk = _STATE_KEYS.get(status.get("inferred_state"))
    word = i18n.t(sk) if sk else "—"
    badge_disp = badge or ""  # RAW Layer-2 token (STOPPED/MOVING/PASSING) — see note at _STATE_KEYS
    pa_total = len(stops[curr].get("pa", [])) if (stops and 0 <= curr < n) else 0
    played = f"{sim_state.cnt_pa + 1}/{pa_total}" if (sim_state and pa_total) else "—"
    # messages (yellow strips) — the SAME i18n strings the live OCR debug panel renders:
    # re-aligning, auto-played fire (panel.autoplayed + panel.fire.*), stopping position, paused-frozen.
    msgs = []
    if status.get("reentry_pending") is not None:
        msgs.append(i18n.t("panel.realigning"))
    lf = status.get("last_fire")
    if isinstance(lf, dict) and time.time() - lf.get("ts", 0) < 3.0:
        fk = _FIRE_KEYS.get(lf.get("type") or "")
        fire_label = i18n.t(fk) if fk else (lf.get("type") or "?")
        msgs.append(f"{i18n.t('panel.autoplayed')} {fire_label}")
    off = status.get("stopping_offset_cm")
    if off is not None:
        msgs.append(f"{i18n.t('panel.stop_offset')} {off:+d} cm")
    if status.get("paused"):
        msgs.append(i18n.t("panel.header_paused"))
    sl, sp, ds = status.get("speed_limit"), status.get("speed"), status.get("distance")
    over = sp is not None and sl is not None and sl > 0 and sp > sl
    badge_tail = f" · {badge_disp}" if badge_disp else ""
    return {
        # row0 green notif (persistent), row1 segment, row2 state · played · BADGE (folded onto the line)
        "left": [
            (NOTIF_TEXT, NOTIF_COLOR, NOTIF_NATIVE, "name"),
            (seg, STATE_INK, STATE_NATIVE, "name"),
            (f"{word} · {played}{badge_tail}", STATE_SUB, STATE_NATIVE, "chrome"),
        ],
        "limit": (str(sl) if sl is not None else "--", "km/h"),
        "speed": (str(sp) if sp is not None else "--", "km/h"),
        "dist": (str(ds) if ds is not None else "--", "m"),
        # cyan change-cue: driver stamps limit_change_ts on a value→value change (mirrors last_fire);
        # blink for LIMIT_FLASH_WINDOW s after, then plain. None reads don't stamp (OCR-dropout safe).
        "limit_changed": (lct := status.get("limit_change_ts") or 0) > 0 and time.time() - lct < LIMIT_FLASH_WINDOW,
        "over_limit": over,
        "msgs": msgs,
        "paused": bool(status.get("paused")),
    }


def render(surf, status=None, sim_state=None, stops=None, *, save_notice=None, force_flash_on=False, home_inert=False):
    """Persistent TIMS status band across the top. Drives off a live OCR `status` dict (auto_input
    shape: badge / inferred_state / segment_start_stop / speed / speed_limit / distance /
    stopping_offset_cm / last_fire / reentry_pending / paused, + `sim_state.curr_stop/cnt_pa` + `stops`
    names) when given; else standalone placeholders. Band width = `surf.get_width()`.
      * LEFT         — OCR state, SMALL k=1: segment · inferred·played · BADGE (Layer-2, grouped here).
      * CENTER       — readout cell: speed limit / speed / distance(m), WIDE numerals. Limit flashes
                       cyan on CHANGE (placeholder mode only for now).
      * CENTER-RIGHT — two dim message strips = TIMS message displays: re-aligning / fire / stopping /
                       paused, in BRIGHT YELLOW that FLASHES + auto-clears (absent when no event).
      * RIGHT        — control cluster [pause][save][home], uniform squares. Pause lights yellow when
                       paused. Home always rightmost.
    `force_flash_on` pins the limit-flash + message-strip blink to their ON phase (for a STATIC
    montage render — otherwise both depend on `get_ticks` and a frozen frame may catch them dark).
    Returns {"home"/"save"/"pause": rect} hit-rects."""
    width = surf.get_width()
    vals = _band_vals(status, sim_state, stops)
    save_msg = _save_message(save_notice)  # Save-button confirmation → top strip, priority over ambient msgs
    if save_msg:
        vals["msgs"] = [save_msg] + vals["msgs"]
    pygame.draw.rect(surf, BAND_COLOR, (0, 0, width, BAND_H))
    msg_font = i18n.pixel_font_for_lang(ACTIVE_LANG, MSG_NATIVE)  # localized msg-strip face, AA-off native
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BAND_BTN_TEXT_NATIVE)  # band control-button labels

    # right-edge control cluster: [pause][save][home], uniform squares (all sized to the home label).
    home_label = i18n.t("setup_tims.band.home")
    t = _BAND_BTN_TUNEABLES
    bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]
    # Uniform squares, locale-INDEPENDENT: size to the worst-case control label across ALL locales, so
    # the [pause][save][home] cluster is identical in en / zh_HK / zh_CN (per-locale sizing made it jump).
    worst = 0
    for _key in ("setup_tims.band.home", "setup_tims.band.pause", "setup_tims.band.resume", "setup_tims.band.save"):
        for _loc in i18n.SUPPORTED_LANGS:
            _lab = i18n.t(_key, lang=_loc)
            _lw, _lh = lowres_text_size(_lab, i18n.pixel_font_for_lang(_loc, BAND_BTN_BOX_NATIVE), BAND_BTN_BOX_K, t["line_gap"])
            worst = max(worst, _lw, _lh)
    btn_sz = int(worst + 2 * HOME_TEXT_MARGIN + bevel)
    btn_top = (BAND_H - btn_sz) // 2
    home_rect = pygame.Rect(width - btn_sz - HOME_MARGIN, btn_top, btn_sz, btn_sz)
    save_rect = pygame.Rect(home_rect.left - BAND_BTN_GAP - btn_sz, btn_top, btn_sz, btn_sz)
    pause_rect = pygame.Rect(save_rect.left - BAND_BTN_GAP - btn_sz, btn_top, btn_sz, btn_sz)

    # LEFT column: 3 lines bottom-aligned to the SAME row baselines as the readout (LIMIT_Y/SPEED_Y/
    # DIST_Y), so the state column and the speed column line up row-for-row. Per-line font: station
    # names → JP face ("en" key = NotoSansJP); localized chrome → the ACTIVE locale face (TC/SC) so
    # zh_CN renders Simplified glyphs instead of tofu boxes (TC font lacks Simplified-only).
    for (text, color, npx, kind), base in zip(vals["left"], (LIMIT_Y, SPEED_Y, DIST_Y)):
        if text:
            f = i18n.pixel_font_for_lang("en" if kind == "name" else ACTIVE_LANG, npx)
            _, th = lowres_text_size(text, f, 1, 0)
            chrome.blit_lowres(surf, text, LEFT_X, base - th, f, color, 1)

    # CENTER readout cell: speed limit / speed / distance, right-aligned between separators.
    num_font = i18n.pixel_font_for_lang("en", READOUT_NUM_SS_NATIVE)  # "en"=NotoSansJP — numbers are locale-independent
    unit_font = i18n.pixel_font_for_lang("en", READOUT_UNIT_NATIVE)  # unit (km/h, m) Latin, locale-independent
    pygame.draw.line(surf, SEP_COLOR, (CELL_X, 8), (CELL_X, BAND_H - 8), SEP_W)
    pygame.draw.line(surf, SEP_COLOR, (CELL_X + CELL_W, 8), (CELL_X + CELL_W, BAND_H - 8), SEP_W)
    rx = CELL_X + CELL_W - CELL_PAD
    ticks = pygame.time.get_ticks()
    no_rd = vals.get("no_readings", False)  # setup stage: dim '--' placeholders, no highlight/flash
    rd_ink = STATE_SUB if no_rd else CELL_INK
    # LIMIT carries the highlight block (only the limit value, NOT the whole column):
    #   * over speed   → the block FLASHES RED (warning), light ink.
    #   * just changed → BLINKS cyan↔plain for LIMIT_FLASH_WINDOW s, then plain (cyan = change cue).
    #   * resting      → PLAIN (no highlight) — cyan is NOT the limit's normal state.
    # short "制限" label ahead of the limit number — a STATIC row label (like the km/h unit), so it shows
    # in EVERY state including the no-readings setup band (identifies the limit row even beside dim '--').
    _lf = i18n.pixel_font_for_lang("en", LIMIT_LABEL_NATIVE)  # "en"=NotoSansJP renders the kanji
    _, _lh = lowres_text_size(LIMIT_LABEL, _lf, 1, 0)
    chrome.blit_lowres(surf, LIMIT_LABEL, LIMIT_LABEL_X, LIMIT_Y - _lh, _lf, LIMIT_LABEL_COLOR, 1)
    if vals["over_limit"]:
        red_on = force_flash_on or (ticks // OVER_LIMIT_FLASH_MS) % 2 == 0
        _blit_readout(
            surf,
            *vals["limit"],
            rx,
            LIMIT_Y,
            num_font,
            unit_font,
            CELL_INK,
            CELL_UNIT_INK,
            highlight=True,
            hl_color=OVER_LIMIT_BG if red_on else HINT_CYAN_COLOR,
            hl_ink=OVER_LIMIT_INK if red_on else HINT_INK_COLOR,
        )
    else:
        limit_hl = False  # PLAIN at rest — cyan is the change cue, not the resting state
        if vals["limit_changed"] and not no_rd:
            limit_hl = force_flash_on or (ticks // LIMIT_FLASH_MS) % 2 == 0
        _blit_readout(surf, *vals["limit"], rx, LIMIT_Y, num_font, unit_font, rd_ink, CELL_UNIT_INK, highlight=limit_hl)
    _blit_readout(surf, *vals["speed"], rx, SPEED_Y, num_font, unit_font, rd_ink, CELL_UNIT_INK)
    _blit_readout(surf, *vals["dist"], rx, DIST_Y, num_font, unit_font, rd_ink, CELL_UNIT_INK)

    # MESSAGE strips: two dim bars; active messages render BRIGHT YELLOW + FLASH (auto-clear when none)
    msg_w = pause_rect.left - MSG_GAP_R - MSG_X
    msg_on = force_flash_on or (pygame.time.get_ticks() // MSG_FLASH_MS) % 2 == 0
    for i in range(2):
        sy = STRIP_Y1 + i * (STRIP_H + STRIP_GAP)
        pygame.draw.rect(surf, STRIP_COLOR, (MSG_X, sy, msg_w, STRIP_H), border_radius=STRIP_RADIUS)
        if i < len(vals["msgs"]) and msg_on:
            text = vals["msgs"][i]
            _, th = lowres_text_size(text, msg_font, MSG_K, 0)
            chrome.blit_lowres(surf, text, MSG_X + MSG_PAD_X, sy + (STRIP_H - th) // 2, msg_font, _MSG_YELLOW, MSG_K)

    # Save/Pause are only wired in a live drive (sim_state present); in setup they're inert → SILVER.
    # Home is live everywhere EXCEPT the home screen itself (home_inert), where it's a no-op → SILVER.
    setup_ctx = sim_state is None
    dis_t = {**t, **chrome.DISABLED}
    # Pause is a play/pause TOGGLE: paused → "繼續/Play" (the label conveys the paused state), else
    # "暫停/Pause". Drawn NORMAL (not persistent-yellow) in both states so the click press-flash reads
    # on EITHER direction — the paused state is signaled by this label + the "已暫停" message strip.
    paused = not setup_ctx and vals["paused"]
    pause_label = i18n.t("setup_tims.band.resume") if paused else i18n.t("setup_tims.band.pause")
    draw_tims_button(surf, pause_rect, pause_label, font=btn_font, t=dis_t if setup_ctx else t)
    draw_tims_button(surf, save_rect, i18n.t("setup_tims.band.save"), font=btn_font, t=dis_t if setup_ctx else t)
    draw_tims_button(surf, home_rect, home_label, font=btn_font, t=dis_t if home_inert else t)
    return {"home": home_rect, "save": save_rect, "pause": pause_rect}


# Band control buttons flash yellow on press — the TIMS "registered" feedback every clickable
# button gets (conventions § UI code style, TIMS button model). The setup_tims screens already
# flash the band Home via press_transition; this is the same feedback for the LIVE-drive cluster
# (pause / save / home), called from app.py::_handle_band_click at the click site.
_BAND_BTN_LABEL_KEYS = {
    "home": "setup_tims.band.home",
    "pause": "setup_tims.band.pause",
    "resume": "setup_tims.band.resume",
    "save": "setup_tims.band.save",
}


def press_flash(surf, rect, which):
    """Yellow press-flash for a live-drive band control button (`which` ∈ home/pause/resume/save).

    Pure flash, no loading beat — the band strip is persistent chrome, not a navigable
    sub-region (a Home exit repaints the whole setup screen next via main.py). `surf` is the
    band surface (app.py's ``debug_surface`` subsurface, whose rects match render()'s output);
    `rect` is the hit-rect from render(). Blocks ~pressed_ms; call at the click site before
    running the action. The run loop's next _render_panel() restores the normal button.
    """
    press_transition(
        surf,
        rect=rect,
        label=i18n.t(_BAND_BTN_LABEL_KEYS[which]),
        font=i18n.pixel_font_for_lang(ACTIVE_LANG, BAND_BTN_TEXT_NATIVE),
        t=_BAND_BTN_TUNEABLES,
        blank_ms=0,
    )

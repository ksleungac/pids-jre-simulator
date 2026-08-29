# SPDX-License-Identifier: MIT
"""Persistent TIMS status band — the near-black top strip.

Two callers, one module (lives in the ``tims`` package):
  * the ``tims.setup`` screens render it as persistent chrome across the setup flow
    (``status=None`` → the placeholder no-readings mode);
  * the live in-drive app (``app.py::PASimulator._render_panel``) renders it as the
    OCR debug panel, feeding a live ``auto_input.driver`` status dict.

It IS the OCR debug panel — promoted from ``setup_tims/band.py`` when the live
wiring landed. Width is taken from the caller's surface (``surf.get_width()``); the
setup-window dims (SCREEN_W/H) live in ``tims/setup/dims.py`` — never a band concept.

  * LEFT         — OCR state, SMALL k=1: segment · inferred·played · BADGE.
  * CENTER       — readout cell: speed limit / speed / distance(m), WIDE numerals.
  * CENTER-RIGHT — two dim message strips (re-aligning / fire / stopping / paused), yellow flash.
  * RIGHT        — control cluster [save][home], uniform squares; home always rightmost.
"""

import time
import traceback
import webbrowser

import pygame

import frame_stream
import i18n
import qr
from . import chrome  # shared palette + low-res text blit (chrome.blit_lowres)
from .widgets import (
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
LEFT_PAD_R         = 8                 # clearance the left column keeps from the readout cell's separator
LEFT_FIT_STEP      = 0.08              # each shrink step when a row overruns that budget
LEFT_FIT_STEPS     = 6                 # ...and how many are allowed — 6 x 8% floors the row at ~0.6
NOTIF_TEXT         = "ツウコク　ジョウホウ"  # green notif — tims_002 通告情報, full-width gap. INTENDED fixed-JP (a real TIMS system label, like station names) — NOT an i18n miss; don't localize (user 2026-07-11)
NOTIF_NATIVE       = 11                # green notif px — SMALLER (least-important line)
NOTIF_COLOR        = chrome.GREEN     # TIMS dot-matrix green
STATE_NATIVE       = 16                # OCR state + badge px — LARGER (primary band info)
STATE_INK          = chrome.INK
STATE_SUB          = chrome.DIM   # dimmer secondary line

# STREAM rows — the browser-mirror address, directly under the green notif, CLICKABLE (opens the
# PC's own browser). Shown on the SETUP band only (status=None): in a drive rows 1–2 carry the OCR
# segment + state, and the address is wanted BEFORE you pick up the tablet, not while holding it.
# Styled AS the green notif above it — same colour, same px, same fixed-JP katakana system label
# with the full-width gap. That idiom is what makes 11px work: a localized kanji label (畫面轉送)
# mushes AA-off at this size, which is why NOTIF_TEXT is katakana in the first place.
#
# The name is the flightsim REMOTE CDU idea, not a video one: a second instance of the console on
# another device, which is what this is now that touch ships — the tablet drives, it does not just
# watch. 画面転送 ("screen transfer") named only the video half and named it from our side.
STREAM_LABEL       = "リモート"          # Fixed-JP like NOTIF_TEXT — a TIMS system label, not localized
STREAM_NATIVE      = NOTIF_NATIVE      # label px = the notif's — the label is the quiet half of the row
STREAM_ADDR_NATIVE = 15                # ADDRESS px — the part you read off the screen and type on a phone,
                                       # so it outranks its own label. Ink bottom-aligned to it (_blit_row)
STREAM_COLOR       = NOTIF_COLOR       # the notif's green — this row is the same kind of system notice
STREAM_HIT_PAD     = 4                 # click target grown past the ink — an 11px label is a small target
# IN A DRIVE the address SURFACES ON A TIMER and row 0 carries the green notif
# the rest of the time. All three rows are spoken for once OCR is live — notif,
# segment, state — and the address needs a whole row (188px worst case), so it
# cannot fold onto a neighbour. Giving row 0 up permanently was the first fix and
# the author declined it; a timer costs the notif only the seconds it is away.
#
# PERIODIC, not once at drive start. The case is a mid-drive reconnect — a
# sleeping tablet, a closed browser — which a one-shot at t=0 cannot reach
# (author, 2026-08-30). No trigger to remember, which is the author's ask; the
# same idiom the message strips and the model-select blink already use.
STREAM_SHOW_MS     = 6000              # address visible
STREAM_HIDE_MS     = 24000             # ...then the notif, before it comes round again
STREAM_RULE_GAP    = 3                 # hover underline: px below the row baseline
STREAM_RULE_W      = 1                 # ...and its thickness. Underline + hand cursor together are
                                       # what say "this is a link"; the row is green like its
                                       # neighbour, so colour alone carries no affordance

# QR popup — hovering the address shows a code to scan, because typing 192.168.0.104:8541 onto a
# phone is the tedious part of using the mirror. On HOVER rather than always: it is wanted for a
# few seconds once per session, and it is far too big to hold a permanent place on a 68px band.
QR_MODULE          = 4                 # px per QR module. 25 modules + quiet zone -> 132px square
QR_QUIET           = 4                 # quiet-zone modules; 4 is the standard's minimum
QR_DARK            = (16, 20, 26)      # near-black on white — a scanner wants contrast, not chrome
QR_LIGHT           = (236, 241, 246)
QR_BORDER          = chrome.FRAME      # a thin frame so the white block reads as a panel
QR_GAP             = 6                 # px below the band before the popup starts

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
READOUT_NUM_SS_NATIVE = 18          # readout number load px — AA-off native (supersample retired)
READOUT_UNIT_K      = 1             # unit stays crisp pixel (draw_lowres) at its own native grid
READOUT_UNIT_NATIVE = 15            # unit native (≈15px) — larger; bottom-aligned to the number baseline (grows upward), rendered dim
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
LIMIT_LABEL_COLOR  = chrome.DIM        # dim slate — a quiet annotation; the bright number stays the focus (was a (150,164,178) palette straggler)
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

BAND_BTN_GAP       = 6                 # gap between the right-edge control buttons (save/home)
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
    centered. ink_top/ink_bot = vertical ink extent shared across digits (baseline align).

    Keyed on the FONT OBJECT, never `id(font)`: CPython reuses a collected object's address, so an
    id-keyed side table silently hands a new font the metrics of a dead one (`conventions.md`
    § Tooling). Holding the object as the key also holds a reference, so the address cannot be
    reused while the entry lives — which is the property `id()` throws away."""
    key = (font, gap)
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


def _draw_number_ss(surf, text, pos, font, color, gap):
    """FAT TIMS numeral run, AA-OFF: each DIGIT is the full-width glyph (U+FF10..19) centered on a
    monospace cell (widest digit ink + `gap`) — the 全角 TIMS look; separators/unit letters render
    natural HALF-width inline. `pos` = top-left of
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
    key = (font, gap, unit)  # the object, not id(font) — see _tims_digit_cell
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
    _draw_number_ss(surf, number, (x0, num_y), num_font, num_ink, READOUT_DIGIT_GAP)
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


# Mirror rows drawn by the last `render`, with the URL each one opens. Module state for the same
# reason the hit-rects are re-derived every frame: the band is redrawn before events are read, so
# what was drawn IS what the click lands on.
_stream_links: "list[tuple[pygame.Rect, str]]" = []
_hover_hand = False  # whether WE set the hand cursor, so we only ever restore one of our own


def _short(url: str) -> str:
    """``http://192.168.1.42:8541/`` -> ``192.168.1.42:8541`` — what a person retypes on a phone.

    The scheme and the trailing slash are the two parts a browser supplies on its own, and the row
    is 13px in a 210px column, so they are the first things to go.
    """
    return url.split("://", 1)[-1].rstrip("/")


def _row0_drive():
    """Row 0 during a drive: the mirror address while its window is open, else
    the green notif.

    Returns the row in `(parts, link)` form either way, so the caller cannot
    tell them apart — which is what keeps the click target and the QR hover
    correct without a second code path. `_stream_links` is rebuilt from the rows
    on every render, so the address is only clickable in the seconds it shows.

    Falls back to the notif when mirroring is off, where `_stream_rows` is empty.
    """
    rows = _stream_rows()
    if rows:
        period = STREAM_SHOW_MS + STREAM_HIDE_MS
        # THE TIMER HOLDS WHILE THE ROW IS HOVERED. Hovering is what raises the
        # QR popup, and the popup is drawn only while the row's hit-rect exists —
        # so letting the timer hide the row mid-hover would take the code away
        # while it was being scanned, after at most STREAM_SHOW_MS. Six seconds
        # is not a scan. The timer governs the IDLE rotation; a hover suspends it
        # and it resumes the frame the pointer leaves.
        if _stream_hovered or pygame.time.get_ticks() % period < STREAM_SHOW_MS:
            return rows[0]
    return ([(NOTIF_TEXT, NOTIF_COLOR, NOTIF_NATIVE, "name")], None)


def _stream_rows():
    """The mirror-address row for the left column, or [] when mirroring is off.

    ONE row, always. ``frame_stream.lan_candidates`` may return several — a machine with a VPN up
    has a tunnel address as well as its real Wi-Fi one — but it now returns them best-first, and a
    band row is an instruction ("open this on your phone"), not an inventory. Two rows made the
    reader choose between them with nothing to choose on; the tunnel row was noise.

    Two chunks, not one string: the address renders LARGER than its label. The separator is a
    FULL-WIDTH space, the same one the notif uses between its own two words — a half-width space
    after a full-width katakana closes up to nothing and the two ran together.
    """
    return [
        (
            [
                (f"{STREAM_LABEL}　", STREAM_COLOR, STREAM_NATIVE, "name"),
                (_short(u), STREAM_COLOR, STREAM_ADDR_NATIVE, "name"),
            ],
            u,
        )
        for u in frame_stream.urls()[:1]
    ]


_qr_cache: dict = {}  # url -> rendered Surface. The matrix is fixed per URL and the popup is drawn
# every frame while hovered, so encoding once per address keeps ~15 encodes/second off the loop.


def _qr_surface(url: str):
    """The scannable block for ``url``, cached. None if it cannot be encoded.

    Fail-soft on purpose: a QR is a convenience over an address the user can still read and type,
    so a URL this encoder cannot take (`qr.matrix` raises past its version-4 ceiling) must cost the
    band nothing. It reports once rather than silently, because a QR that never appears is
    otherwise indistinguishable from one nobody hovered.
    """
    if url not in _qr_cache:
        try:
            m = qr.matrix(url)
            n = len(m) + 2 * QR_QUIET
            surf = pygame.Surface((n * QR_MODULE, n * QR_MODULE))
            surf.fill(QR_LIGHT)
            for r, row in enumerate(m):
                for c, dark in enumerate(row):
                    if dark:
                        px = ((c + QR_QUIET) * QR_MODULE, (r + QR_QUIET) * QR_MODULE, QR_MODULE, QR_MODULE)
                        pygame.draw.rect(surf, QR_DARK, px)
            pygame.draw.rect(surf, QR_BORDER, surf.get_rect(), 1)
            _qr_cache[url] = surf
        except Exception as e:  # noqa: BLE001 - convenience only; the address is still readable
            print(f"Warning: could not build a QR for {url} ({e}); the address is still shown.")
            _qr_cache[url] = None
    return _qr_cache[url]


_hovered_url = None  # set by `render`, consumed by the flip hook below
# Whether the mirror row was under the pointer on the LAST render. Separate from
# `_hovered_url` because that one is CONSUMED by the flip hook (set to None on
# every present), so by the time the next frame builds its rows it reads None and
# cannot answer "is the user on it". This flag is only ever read to decide which
# row 0 to draw, so a stale True costs one frame of the address instead of the
# notif — not the painting hazard `_draw_qr_popup` documents.
_stream_hovered = False
_overlay_installed = False  # see install_overlay_hook — a flag, not a wrapper attribute
_overlay_failed = False


def _guarded_overlay() -> None:
    """Draw the popup on the presented surface; report the FIRST failure, then stay quiet.

    Never raises into the render loop — a missing QR is a convenience lost, not a broken app — but
    a blanket `except: pass` on a 15 Hz call is how the bell window's topmost re-pin silently
    stopped working behind a `NameError` for a whole session (`conventions.md` § UI code style).
    """
    global _overlay_failed
    try:
        surf = pygame.display.get_surface()
        if surf is not None:
            draw_overlay(surf)
    except Exception:  # noqa: BLE001 - the render loop outranks the popup
        if not _overlay_failed:
            _overlay_failed = True
            print("Warning: the band's QR overlay failed and is now suppressed for this session:")
            traceback.print_exc()


def draw_overlay(surf) -> None:
    """Drop the QR popup under the band, left-aligned with the address row it belongs to.

    # CONTRACT: this must run AFTER the screen has drawn its own content, which is why it is not
    # part of `render`. The band is persistent chrome and every screen draws it FIRST, then paints
    # over the top — so a popup drawn inside `render` is buried. Measured 2026-08-29: the home
    # screen's 報站設定 card covered the right third of the code and it stopped scanning, while the
    # source surface decoded perfectly, which is a difference no look at the encoder would explain.

    Clamped to the surface so it cannot hang off a narrow window.
    """
    # CONSUMED, not merely read. `render` re-publishes `_hovered_url` on every frame it draws, so
    # taking it here means the popup survives exactly one present and a surface that stops drawing
    # the band cannot inherit it.
    #
    # That is the whole hazard: `_hovered_url` is module state whose only writer is `render`, and
    # `app.py::_render_panel` returns early for a drive with OCR off — so nothing re-renders the
    # band for the entire drive. A value carried out of the setup flow (click the mirror row, which
    # leaves the physical pointer resting on it, then finish setup from the mirrored page so the
    # cursor never moves) would paint a 132px block over the LCD on every frame with nothing to
    # clear it. Guarding on `_stream_links` instead does NOT close it: that list is also only
    # cleared by `render`, so it is stale-NON-empty in precisely this case — and `_hovered_url` is
    # only ever set inside the same branch that populates it, so the extra term never decided
    # anything at all.
    global _hovered_url
    url, _hovered_url = _hovered_url, None
    if url is None:
        return
    block = _qr_surface(url)
    if block is None:
        return
    w, h = block.get_size()
    x = max(0, min(LEFT_X, surf.get_width() - w))
    y = min(BAND_H + QR_GAP, max(0, surf.get_height() - h))
    surf.blit(block, (x, y))


def install_overlay_hook() -> None:
    """Wrap ``pygame.display.flip`` / ``update`` so the popup lands on every completed frame.

    One seam rather than a call in each of the nine setup screens' loops, which is the idiom this
    codebase already uses for window pinning and frame capture (`conventions.md` § Display module
    structure): the screens are many and grow, and the tenth would silently not have it.

    Idempotence is a MODULE FLAG, not an attribute on the wrapper. The attribute form asks "is the
    outermost flip mine?", and the answer is no as soon as `frame_stream.install_present_hook` wraps
    on top — so calling this after `start()` stacked a second copy and drew the popup twice per
    present, once more for every extra call. The flag asks "am I installed at all", which is the
    real question.

    Costs nothing when there is nothing to draw: `_hovered_url` is None unless a mirror row exists
    AND the pointer is on it, which is false on every frame of a live drive.
    """
    global _overlay_installed
    if _overlay_installed:
        return
    _overlay_installed = True
    for name in ("flip", "update"):
        orig = getattr(pygame.display, name)

        def _wrapped(*args, _orig=orig, **kwargs):
            _guarded_overlay()
            return _orig(*args, **kwargs)

        # Carry the link so `frame_stream._already_wrapped` can see PAST us: its idempotence check
        # walks the chain, and a wrapper that hides its own `_orig` would make the layer beneath
        # invisible and let a second present hook stack on top.
        _wrapped._orig = orig
        setattr(pygame.display, name, _wrapped)


def _mouse_pos():
    """The pointer, or None when there is no display to have one — a ``save_screenshot`` render
    goes to an offscreen Surface, where asking pygame for the mouse is meaningless. Checked rather
    than caught, so a real fault here still raises."""
    return None if pygame.display.get_surface() is None else pygame.mouse.get_pos()


def _update_hover_cursor():
    """Hand cursor while the pointer sits on a mirror row — the only cue that the row does anything.

    Owned by the band, called from its own ``render``, because the band owns the rows: a per-screen
    call would have to be added to all nine setup click loops and silently missed by the tenth
    (`conventions.md` § Display module structure — wrap the call, don't guard each site).

    Two things keep it from stomping another owner. It does nothing at all when there are no rows to
    hover, so a live drive — left column full of OCR state, ``_stream_links`` empty — keeps
    ``app.py``'s own LCD hover behaviour untouched. And it restores only a hand IT set.

    No display (a ``save_screenshot`` render into an offscreen Surface) means no cursor to set and
    no mouse to read; that is checked rather than caught, so a real fault here still raises.
    """
    global _hover_hand
    pos = _mouse_pos()
    if (not _stream_links and not _hover_hand) or pos is None:
        return
    over = any(r.collidepoint(pos) for r, _u in _stream_links)
    if over != _hover_hand:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if over else pygame.SYSTEM_CURSOR_ARROW)
        _hover_hand = over


def click_stream(pos) -> bool:
    """Open the mirror address under ``pos`` in the PC's own browser. True when the click was ours.

    Every setup screen calls this FIRST in its click branch. The band is persistent chrome, so the
    rows it draws are the band's to resolve — a screen that had to re-derive them would be a second
    implementation of this layout (`principles.md` § "A second implementation ... drifts silently").

    Only ever the loopback or a LAN address of this machine, and only one this process bound and
    printed itself — never a URL from the wire.
    """
    for rect, url in _stream_links:
        if rect.collidepoint(pos):
            webbrowser.open(url)
            return True
    return False


# NOTE: the live-status branch below (status != None) is exercised by the live in-drive app
# (app.py::_render_panel feeds the auto_input.driver status dict). The tims.setup callers pass
# status=None → only the placeholder branch runs there. Don't flag either branch as dead.
def _band_vals(status, sim_state, stops):
    """Map a live OCR `status` dict (auto_input.driver shape) onto the band's display fields. `status`
    None → standalone placeholders (home-menu preview). Encodes the OCR-panel migration decisions:
    badge grouped with the state (left column), NO confidence colour, events → the yellow strips."""
    if not status:
        # Setup stage: OCR is NOT running yet → the NO-READINGS state. Only the green notif hint shows;
        # no segment, no speed / limit / distance readings (dim '--'), no fire/stop messages, no cyan or
        # yellow flashing. Applies to EVERY tims.setup screen (all pre-OCR). The live-status branch below
        # drives the real readings once auto_input feeds a status dict.
        #
        # The MIRROR ROW keys on `status is None`, NOT on this falsy test. The two are different
        # questions and only the caller knows the answer: `app.py` initialises `auto_input_status = {}`
        # and passes it every frame, so `{}` means "in a drive, no OCR sample yet" — which is the whole
        # drive when the capture thread dies (critical_lessons §8), not a setup screen. Drawing the row
        # there put a dead link on the drive band (`app.py` never calls `click_stream`), fought
        # `app.py::_update_hover_cursor` for the cursor, and dropped the QR popup over the LCD.
        # The dim '--' placeholders below are right for BOTH cases, which is why the branch stays shared.
        return {
            # Rows 1–2 are free before OCR runs, which is exactly where the mirror address goes.
            "left": [
                ([(NOTIF_TEXT, NOTIF_COLOR, NOTIF_NATIVE, "name")], None),
            ]
            + (_stream_rows() if status is None else []),
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
        # NORMALISED — the space is stripped. A space in a `name` is the data
        # format's LINE-BREAK marker (`docs/DATA_FORMAT.md` § Station names), so
        # `さいたま 新都心` is one station instructing a two-line layout. This row
        # is a single line, so the marker has nothing to instruct and drawing it
        # renders a word gap that reads as two stations. The LCD's own name
        # renderers already drop it for the same reason.
        return (stops[i].get("name", "?") if 0 <= i < n else "?").replace(" ", "")

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
        # row0 green notif, yielding to the mirror address on a timer (see the
        # STREAM block); row1 segment; row2 state · played · BADGE, folded on.
        "left": [
            _row0_drive(),
            ([(seg, STATE_INK, STATE_NATIVE, "name")], None),
            ([(f"{word} · {played}{badge_tail}", STATE_SUB, STATE_NATIVE, "chrome")], None),
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
    # NO PAUSE BUTTON. It was a play/pause toggle on the auto-driver and the
    # author never used it once (2026-08-30). Dropping it returns 70px — a
    # button, a gap — to the message strips, which is what E233-0's 640px canvas
    # took away from them: three of the band's four regions are fixed, so the
    # strips absorbed the whole 90px difference and came out 72px wide against
    # messages that measure 102..142.
    #
    # `AutoDriver.paused` stays. Nothing sets it now, so it rests False and its
    # branches are inert — but it is the driver's own state, not the band's, and
    # a control for it can come back on the tap surface without the band having
    # to hold a square for it in the meantime.

    # LEFT column: 3 lines bottom-aligned to the SAME row baselines as the readout (LIMIT_Y/SPEED_Y/
    # DIST_Y), so the state column and the speed column line up row-for-row. Per-line font: station
    # names → JP face ("en" key = NotoSansJP); localized chrome → the ACTIVE locale face (TC/SC) so
    # zh_CN renders Simplified glyphs instead of tofu boxes (TC font lacks Simplified-only).
    # Each row is a list of chunks laid left to right, every chunk's ink BOTTOM landing on the row's
    # baseline — so a row may mix sizes (the mirror row's address is larger than its label) without
    # the two staggering, which a shared top y would do since the fonts' ascents differ.
    # A row carrying a `link` is the clickable mirror address; its rect is recorded for click_stream.
    global _hovered_url
    _stream_links.clear()
    hovered_qr = None
    for (parts, link), base in zip(vals["left"], (LIMIT_Y, SPEED_Y, DIST_Y)):
        # A ROW THAT OVERRUNS THE COLUMN COMPRESSES; it is never cut (author,
        # 2026-08-30). The budget is the gap to the readout cell's separator, so
        # the row can use everything up to it and no more. `npx` is the AA-off
        # native size, so stepping it down is the only lever — the face has no
        # condensed cut — and it is stepped for the WHOLE row at once, keeping
        # the chunks' relative sizes (the mirror row's address is deliberately
        # larger than its label).
        budget = CELL_X - LEFT_X - LEFT_PAD_R
        scale = 1.0
        for _ in range(LEFT_FIT_STEPS):
            wid = sum(
                lowres_text_size(txt, i18n.pixel_font_for_lang("en" if k == "name" else ACTIVE_LANG, max(8, int(px * scale))), 1, 0)[0]
                for txt, _c, px, k in parts
                if txt
            )
            if wid <= budget:
                break
            scale -= LEFT_FIT_STEP
        x, top = LEFT_X, base
        for text, color, npx, kind in parts:
            if not text:
                continue
            f = i18n.pixel_font_for_lang("en" if kind == "name" else ACTIVE_LANG, max(8, int(npx * scale)))
            cw, ch = lowres_text_size(text, f, 1, 0)
            chrome.blit_lowres(surf, text, x, base - ch, f, color, 1)
            x += cw
            top = min(top, base - ch)  # the tallest chunk sets the row's top, and so the hit height
        if link and x > LEFT_X:
            hit = pygame.Rect(LEFT_X, top, x - LEFT_X, base - top).inflate(2 * STREAM_HIT_PAD, 2 * STREAM_HIT_PAD)
            _stream_links.append((hit, link))
            mp = _mouse_pos()
            if mp is not None and hit.collidepoint(mp):  # hovered -> underline it, like a link
                uy = base + STREAM_RULE_GAP
                pygame.draw.line(surf, color, (LEFT_X, uy), (x - 1, uy), STREAM_RULE_W)
                hovered_qr = link  # the popup itself is drawn by the flip hook — see _hovered_url

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
    msg_w = save_rect.left - MSG_GAP_R - MSG_X
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
    draw_tims_button(surf, save_rect, i18n.t("setup_tims.band.save"), font=btn_font, t=dis_t if setup_ctx else t)
    draw_tims_button(surf, home_rect, home_label, font=btn_font, t=dis_t if home_inert else t)
    global _stream_hovered
    _hovered_url = hovered_qr  # the flip hook draws the popup once the screen is done painting
    _stream_hovered = hovered_qr is not None  # holds the drive band's row-0 timer — see `_row0_drive`
    _update_hover_cursor()  # after the rects are current, so the hand tracks what was just drawn
    return {"home": home_rect, "save": save_rect}


# Band control buttons flash yellow on press — the TIMS "registered" feedback every clickable
# button gets (conventions § UI code style, TIMS button model). The tims.setup screens already
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

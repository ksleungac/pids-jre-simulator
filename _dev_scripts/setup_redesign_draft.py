"""DRAFT mock — setup-screen redesign, page 1. NOT production; a layout sketch for the
visual judge (user). Renders the real setup canvas with the graduated chrome primitives
(widgets.py) + i18n-resolved pixel fonts, so the language selector + the big action buttons
can be eyeballed in context before any of it lands in setup.py.

Page 1 (this draft):
  * top-right  — 3 square language buttons, each self-labeled in its own script
                 (English / 繁體中文 / 简体中文); knobs rest in default state (yellow = pressed).
  * center     — 4 flush big action buttons, vertically centered:
                 Route Selection / Tutorial / Settings / Driving Record.

Interactive:   uv run _dev_scripts/setup_redesign_draft.py
                 (click Tutorial → opens the green TIMS tutorial screen; ESC back; other
                  cards are inert placeholders)
Static render: uv run _dev_scripts/setup_redesign_draft.py --screenshot setup_draft.png

The Tutorial-card → tutorial wiring is the menu→screen nav demo (dev-only; the real wiring
lands when the menu graduates into setup.py).
"""

import argparse
import sys
import time
import webbrowser

import pygame

sys.path.insert(0, ".")

import i18n  # noqa: E402
import update_check  # noqa: E402
from app_paths import project_root  # noqa: E402
from widgets import (  # noqa: E402
    _TUNEABLES_TIMS_BUTTON,
    HINT_CYAN_COLOR,
    HINT_INK_COLOR,
    draw_lowres_number,
    draw_lowres_text,
    draw_tims_button,
    lowres_fit_k,
    lowres_number_size,
    lowres_text_size,
    press_transition,
)

# Ark Pixel 12px MONOSPACED pixel face, per-locale, resolved via i18n.pixel_font_for_lang (the same
# per-locale dispatch font_for_lang already does — now graduated into fonts/ + i18n). ARK_NATIVE is
# the font's design grid: render there, then integer-upscale by k.
ARK_NATIVE = 12


def pixel_font(lang):
    return i18n.pixel_font_for_lang(lang, ARK_NATIVE)


# fmt: off
# ── page-1 layout tuneables (all derived coords flow from these) ──────────────
SCREEN_W, SCREEN_H = 730, 610          # setup is its OWN window — taller than the 420 LCD-sized
                                       # one (main.py SETUP_SIZE); height is a free knob. 610 keeps
                                       # the 2/3-height buttons clear of the top-corner lang strip.
BG_COLOR           = (62, 68, 80)      # current SetupScreen bg (mirror reality; tunable)

# language buttons (top-right corner, horizontal row). The box is CONTENT-SIZED to the 4-char CJK
# self-name (2x2) so the kanji pack tight with ZERO inter-char gap (box just-right, ~square). All
# three share that size (uniform knob row); EN sits in it as the short code, same multiplier.
LANG_K             = 2               # fixed pixel multiplier for EVERY language label (no ballooning)
LANG_LINE_GAP      = 0               # tight 2x2 grid — rows touch
LANG_TEXT_MARGIN   = 6               # uniform gap between the tight text block and the bevel
LANG_GAP           = 8               # gap between buttons in the row
LANG_MARGIN_BOTTOM = 10             # lang knobs sit BOTTOM-right now (band owns the top-right)
LANG_MARGIN_RIGHT  = 10
ACTIVE_LANG        = "zh_HK"         # language shown — drives the pressed knob + big-button chrome
LANG_SIZER         = "繁體\n中文"      # the label whose tight footprint sets the shared box size

# big action buttons (centered, side by side). Sized so 3–4 fit across (the eventual layout) — and
# smaller buttons keep the Ark text at k=2 (crisp pixel, like the knobs) instead of chunky-upscaled.
BIG_W              = 145               # wide enough for single-line 4-char zh labels at k=2
BIG_H              = 280               # tall cards (>=2x height per request; text stays k=2)
BIG_GAP            = 0                 # buttons flush — no space between

# persistent TIMS status band (top strip, full width). SAME band concept as the running app's OCR
# debug panel (app.py carves a 730 × DEBUG_PANEL_HEIGHT top strip when auto_input is on) — previewed
# here so it reads as persistent chrome. Height is a draft choice for now; it reconciles with
# DEBUG_PANEL_HEIGHT when the band graduates. The readout cell is a PLACEHOLDER swapped for live OCR
# fields ("might not be clock") — don't chase TIMS-clock fidelity. Rightmost button = ALWAYS home.
BAND_H             = 68                # shorter band (rows sit on an 8 / 26 / 44 grid)
BAND_COLOR         = (8, 10, 14)       # near-black strip

# LEFT column — green notification + OCR state (segment + inferred state), stacked, SMALL. Station
# names ONLY ever surface here, so k=1 keeps the dense left column from crowding the band (the real
# TIMS left column is small dense text — a k=2 segment would dominate the strip).
LEFT_X             = 12
NOTIF_TEXT         = "ツウコク ジョウホウ"  # green notification text (placeholder)
NOTIF_Y            = 8
NOTIF_K            = 1
NOTIF_COLOR        = (54, 230, 64)     # TIMS dot-matrix green
STATE_SEG          = "立川 → 川崎"       # OCR segment from -> to (placeholder; live OCR later)
STATE_INFO         = "巡航中 · 2/3"      # inferred state . played count (placeholder)
STATE_SEG_Y        = 26                # state lines sit on the band's shared row grid (8 / 26 / 44)
STATE_INFO_Y       = 44
STATE_K            = 1                 # SMALL — don't crowd the band (station names only live here)
STATE_INK          = (236, 241, 246)
STATE_SUB          = (150, 162, 174)   # dimmer secondary line

# CENTER readout cell — speed limit / speed / distance (OCR placeholders), right-aligned between
# separators. The LIMIT is ALWAYS cyan (steady highlight block); on CHANGE it FLASHES (blinks cyan↔
# plain) for a few seconds, then settles back to STEADY cyan — cyan is the resting state, the flash
# is the change cue. If SPEED exceeds the LIMIT the whole cell BACKGROUND flashes RED (over-speed
# warning). DRAFT models "changed" with a toggle; prod drives both off live OCR deltas.
CELL_X             = 150               # readout cell left edge (pushed left, near the left column)
CELL_W             = 120
CELL_PAD           = 8
SEP_COLOR          = (120, 132, 144)   # vertical separators flanking the cell
SEP_W              = 2
CELL_INK           = (236, 241, 246)   # the number ink (bright)
CELL_UNIT_INK      = (130, 144, 156)   # unit (km/h, m) ink — DIMMER than the number, not so bright
READOUT_NUM_H       = 18            # number rendered HEIGHT (px). SUPERSAMPLED (drawn big AA-on, scaled
                                    # DOWN) so this in-between size reads SMOOTH, not blocky — the pixel
                                    # face is crisp only at 12/24, so a size between them must be either
                                    # sub-grid (blocky, heavy strokes) or supersampled (this). Strokes
                                    # stay proportional ("pixel but not squary").
READOUT_NUM_SS_NATIVE = 48          # supersample SOURCE native (4× the 12 grid, AA-on) before scale-down
READOUT_UNIT_K      = 1             # unit stays crisp pixel (draw_lowres) at its own native grid
READOUT_UNIT_NATIVE = 13            # unit native (≈13px) — a touch larger than the old 12, rendered dim
READOUT_DIGIT_XSCALE = 1.3          # WIDE TIMS numerals: widen each digit, independent of the gap
READOUT_DIGIT_GAP    = 2            # px between digits at the rendered size
READOUT_UNIT_GAP     = 4            # gap between the number and its unit (km/h, m)
LIMIT_NUM          = "75"             # speed LIMIT (OCR) — top of cell
LIMIT_UNIT         = "km/h"
SPEED_NUM          = "0"              # current speed (OCR)
SPEED_UNIT         = "km/h"
DIST_NUM           = "1200"           # distance to next (OCR) — ALWAYS meters (OCR reads m; finer
DIST_UNIT          = "m"             # granularity than rounded km = better observability)
LIMIT_Y            = 2                 # 3-row grid, TIGHT pitch — fat glyphs packed close (was 8/26/44)
SPEED_Y            = 24
DIST_Y             = 46
LIMIT_PAD_X        = 4                 # cyan limit block inset (x)
LIMIT_PAD_Y        = 1
PREVIEW_LIMIT_CHANGED = True           # DRAFT: force the on-change cyan BLINK so it's visible in dev
LIMIT_FLASH_MS     = 400               # half-period of the change blink (cyan↔plain, then steady cyan)
OVER_LIMIT_BG      = (190, 30, 34)     # over-speed warning: the LIMIT block flashes this red (not the cell)
OVER_LIMIT_INK     = (245, 240, 240)   # light ink on the red block (dark cyan-ink would vanish on red)
OVER_LIMIT_FLASH_MS = 350              # half-period of the red over-limit block flash

# MESSAGE strips (center-right) — the original TIMS "two dim bars" look, restored where the OCR
# state used to sit. Houses the OCR fire event (top) + stopping-position reading (bottom).
MSG_X              = 285               # strips left edge (right of the pushed-left readout cell)
MSG_GAP_R          = 10                # gap before the control-button cluster (strips end here)
STRIP_H            = 20
STRIP_GAP          = 5
STRIP_Y1           = 11
STRIP_RADIUS       = 0                 # SHARP corners — no rounding (user: strips are sharp, not smooth)
STRIP_COLOR        = (34, 46, 58)      # dim slate — TIMS message-strip fill
STRIP_INK          = (210, 222, 230)
MSG_K              = 1
MSG_FLASH_MS       = 450               # message-display flash half-period (bright yellow, auto-clears)
MSG_PAD_X          = 6                 # text inset inside a strip
MSG_FIRE_TEXT      = "次駅 自動再生"      # OCR fire event (placeholder)
MSG_STOP_TEXT      = "停止位置 +1.2 m"   # stopping-position reading (placeholder)

BAND_BTN_GAP       = 6                 # gap between the right-edge control buttons (pause/save/home)
HOME_MARGIN        = 8                 # rightmost band button = always "return to home"
HOME_TEXT_MARGIN   = 2                 # all 3 control buttons CONTENT-SIZED to the home label (+ margin) → uniform squares (kept inside the shorter band)
BAND_BTN_BOX_K     = 2                 # the SQUARE is sized to the home label at k=2 (keeps button SIZE);
                                       # the label RENDERS from a native-BAND_BTN_TEXT_NATIVE font at k=1
                                       # — font size decoupled from the box (smaller text, same button)
BAND_BTN_TEXT_NATIVE = 16              # band-button label native px (≈16 — buttons keep their box size)
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# Band's rightmost button is ALWAYS return-to-home (persistent across screens). Label per UI language
# (draft constant; becomes an i18n key at graduation).
HOME_BY_LANG = {"en": "Back\nHome", "zh_HK": "返回\n主頁", "zh_CN": "返回\n主页"}
# Persistent band controls left of home (OCR debug-panel controls migrating onto the band): pause the
# auto-driver + save the driving record. Same TIMS button primitive, uniform with the home square.
PAUSE_BY_LANG = {"en": "Pause", "zh_HK": "暫停", "zh_CN": "暂停"}
SAVE_BY_LANG = {"en": "Save\nRec", "zh_HK": "儲存\n記錄", "zh_CN": "保存\n记录"}
_BAND_BTN_TUNEABLES = {
    **_TUNEABLES_TIMS_BUTTON,
    "text_align": "center",
    "text_pad": 0,  # margin lives in the CONTENT-SIZED box (HOME_TEXT_MARGIN), not here — an
    # internal pad on top of the box margin double-counts and starves k to 1
    "text_max_k": 1,  # SMALL band-button text (k=1 native pixel) — matches the k=1 left column /
    # message strips. Box stays sized to BAND_BTN_BOX_K so the SQUARE keeps its
    # size; only the label shrinks (font smaller, NOT the button)
    "line_gap": 1,
}

# (code, label) — full self-name (CJK wrapped 2x2); EN stays the short code. The font is resolved
# per code from its own Ark Pixel locale file (zh_HK = Traditional, zh_CN = Simplified, en = Latin).
LANGS = [
    ("en", "EN"),
    ("zh_HK", "繁體\n中文"),
    ("zh_CN", "简体\n中文"),
]

# Action-button tuneables: tight-centered label (no inter-char gap) held off the bevel by text_pad —
# same center mode as the knobs, just a bigger pad + the fill-to-fit k.
_ACTION_TUNEABLES = {**_TUNEABLES_TIMS_BUTTON, "text_align": "center", "text_pad": 12, "text_max_k": 2}

# Language-button tuneables: tight-centered label with a margin — drawn straight by draw_tims_button
# (the primitive owns align/pad).
_LANG_TUNEABLES = {
    **_TUNEABLES_TIMS_BUTTON,
    "line_gap": LANG_LINE_GAP,
    "text_max_k": LANG_K,
    "text_align": "center",
    "text_pad": 0,  # margin lives in the box (2*LANG_TEXT_MARGIN). A nonzero pad here double-
    # counts and starves k to 1 — the same trap the home button hit; after the
    # bevel was trimmed (-10%), the exact-cancel tipped under the k=2 threshold.
}

# Big-button chrome per language: [labels]. Placeholder translations for the draft; real strings come
# from translations_app.json at graduation. ACTION_IDS parallels each label list (stable hit keys —
# only "tutorial" is wired; the rest are inert placeholders).
ACTION_IDS = ["route", "tutorial", "settings", "record"]
# Single-line labels (no wrap) — the cards are wide enough to hold them at k=2. Leftmost = 報站設定
# (PA setup; the route → diagram → station flow). ACTION_IDS keeps "route" as the leftmost hit key.
ACTIONS_BY_LANG = {
    "en": ["PA Setup", "Tutorial", "Settings", "Driving Record"],
    "zh_HK": ["報站設定", "教學", "設定", "行車記錄"],
    "zh_CN": ["报站设置", "教程", "设置", "行车记录"],
}

# Version tag — i18n "Version" word + "054" bottom-left: no 'v', no dots, no colon. The numerals are
# drawn by draw_lowres_number (NOT full-width forms): each digit trimmed to ink + an explicit small
# gap, so they sit close like real TIMS. xscale widens them ("wider but not full width"); gap is the
# spacing knob, independent of width. VERSION is raw (production reads pyproject); shown dot-stripped.
VERSION = "0.5.4"
VERSION_K = 2
VERSION_DIGIT_XSCALE = 1.3  # widen each digit (1.0 = natural ink; >1 = wider TIMS cell)
VERSION_DIGIT_GAP = 1  # native px between digits (× k); small = near-touching, may be <0
VERSION_X, VERSION_Y = 22, SCREEN_H - 36
VERSION_COLOR = (200, 214, 211)

# Update-available hint — when a newer GitHub release exists, the version tag ALTERNATES in place
# (the TIMS 設定完了 idiom): on-phase swaps "Version 054" for the i18n update message under a cyan
# highlight block; off-phase shows the normal version. Both text AND colour change while flashing.
# Production reads update_check.get_update() (wired in main.py + setup.py); click the tag → release.
HINT_BLINK_MS = 550  # half-period: each state shown for 550ms before flipping
HINT_PAD_X, HINT_PAD_Y = 6, 3  # cyan block inset around the hint text
# DRAFT ONLY: force the flash on so it's visible in dev — update_check.get_update() no-ops when
# unfrozen (app_version() is None). Graduation to setup.py DROPS this: prod flashes iff get_update()
# is truthy. The fake tuple stands in for what the worker thread would stash.
PREVIEW_FORCE_HINT = True
PREVIEW_UPDATE = ("0.6.0", f"https://github.com/{update_check._REPO}/releases/latest")


def _blit_lowres(surf, text, x, y, font, color, k, *, right=False):
    """Draw low-res pixel text flush at (x, y); right=True right-anchors at x."""
    w, h = lowres_text_size(text, font, k, 0)
    tmp = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    draw_lowres_text(tmp, text, pygame.Rect(0, 0, w, h), font, color, max_k=k, line_gap=0, align="center")
    surf.blit(tmp, (x - w if right else x, y))


def _number_ss_size(text, font, target_h, xscale, gap):
    """Footprint (w, target_h) of a supersampled TIMS numeral run (see _draw_number_ss)."""
    fh = font.get_height()
    scale = target_h / fh
    w = 0
    for ch in text:
        bb = font.render(ch, True, (255, 255, 255)).get_bounding_rect()
        iw = bb.w if bb.w else font.size(ch)[0]
        w += max(1, round(iw * scale * xscale)) + gap
    return max(0, w - gap), target_h


def _draw_number_ss(surf, text, pos, font, color, target_h, xscale, gap):
    """TIMS numeral run rendered SMOOTH at `target_h` px: each digit drawn at `font`'s HIGH native
    (antialias ON), trimmed to ink, then smoothscale'd DOWN to target_h — anti-aliased edges instead
    of the blocky nearest-upscale, so a size BETWEEN the pixel grid's crisp 12/24 reads clean. Keeps
    the per-digit `xscale` widening + explicit `gap` (the wide-numeral look). `pos` = top-left."""
    fh = font.get_height()
    scale = target_h / fh
    x = float(pos[0])
    y0 = pos[1]
    for ch in text:
        full = font.render(ch, True, color)  # AA ON at the high native
        bb = full.get_bounding_rect()
        if not bb.w:  # blank: advance by its (scaled) cell, draw nothing
            x += max(1, round(font.size(ch)[0] * scale * xscale)) + gap
            continue
        g = full.subsurface((bb.x, 0, bb.w, fh)).copy()  # trim H to ink, keep full height
        gw = max(1, round(bb.w * scale * xscale))
        gh = max(1, round(fh * scale))
        surf.blit(pygame.transform.smoothscale(g, (gw, gh)), (round(x), y0))
        x += gw + gap


def _blit_readout(
    surf, number, unit, rx, y, num_font, unit_font, color, unit_color, *, highlight=False, hl_color=HINT_CYAN_COLOR, hl_ink=HINT_INK_COLOR
):
    """One readout value right-anchored at (rx, y): a SUPERSAMPLED TIMS numeral run (_draw_number_ss
    on `num_font`'s high native, smooth at READOUT_NUM_H) + a SMALLER, DIMMER unit (`unit_font`,
    READOUT_UNIT_K, `unit_color`) centred against the number's height. `highlight` paints a block (in
    `hl_color`, text in `hl_ink`) behind the footprint — the speed-limit's always-on cyan cue, its
    change blink, or the red over-speed flash (caller picks the colour)."""
    uw, uh = lowres_text_size(unit, unit_font, READOUT_UNIT_K, 0)
    nw, nh = _number_ss_size(number, num_font, READOUT_NUM_H, READOUT_DIGIT_XSCALE, READOUT_DIGIT_GAP)
    total_w = nw + READOUT_UNIT_GAP + uw
    x0 = rx - total_w
    num_ink = hl_ink if highlight else color
    unit_ink = hl_ink if highlight else unit_color
    if highlight:
        block = pygame.Rect(x0, y, total_w, nh)
        pygame.draw.rect(surf, hl_color, block.inflate(2 * LIMIT_PAD_X, 2 * LIMIT_PAD_Y), border_radius=3)
    _draw_number_ss(surf, number, (x0, y), num_font, num_ink, READOUT_NUM_H, READOUT_DIGIT_XSCALE, READOUT_DIGIT_GAP)
    _blit_lowres(surf, unit, x0 + nw + READOUT_UNIT_GAP, y + (nh - uh) // 2, unit_font, unit_ink, READOUT_UNIT_K)


_MSG_YELLOW = (250, 228, 70)  # TIMS message-display yellow (strips flash this, then auto-clear)
_BADGE_INK = (150, 162, 174)  # Layer-2 badge sits DIM with the state (decision: NO confidence colour)

# The band reads the SAME i18n strings the live OCR debug panel uses (auto_input/driver.py:
# _STATE_KEY / _FIRE_KEY → data/translations_app.json `panel.*`). Mirrored here (local const, not
# imported — keeps the draft off the heavy cv2/numpy driver module). i18n.t() resolves to the active
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


def _band_vals(status, sim_state, stops):
    """Map a live OCR `status` dict (auto_input.driver shape) onto the band's display fields. `status`
    None → standalone placeholders (home-menu preview). Encodes the OCR-panel migration decisions:
    badge grouped with the state (left column), NO confidence colour, events → the yellow strips."""
    if not status:
        return {
            "left": [(NOTIF_TEXT, NOTIF_COLOR), (STATE_SEG, STATE_INK), (STATE_INFO, STATE_SUB)],
            "limit": (LIMIT_NUM, LIMIT_UNIT),
            "speed": (SPEED_NUM, SPEED_UNIT),
            "dist": (DIST_NUM, DIST_UNIT),
            "limit_changed": PREVIEW_LIMIT_CHANGED,
            "over_limit": False,
            "msgs": [MSG_FIRE_TEXT, MSG_STOP_TEXT],
            "paused": False,
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
    return {
        "left": [(seg, STATE_INK), (f"{word} · {played}", STATE_SUB), (badge_disp, _BADGE_INK)],
        "limit": (str(sl) if sl is not None else "--", "km/h"),
        "speed": (str(sp) if sp is not None else "--", "km/h"),
        "dist": (str(ds) if ds is not None else "--", "m"),
        "limit_changed": False,
        "over_limit": over,
        "msgs": msgs,
        "paused": bool(status.get("paused")),
    }


def _render_topband(surf, status=None, sim_state=None, stops=None, *, force_flash_on=False):
    """Persistent TIMS status band across the top. Drives off a live OCR `status` dict (auto_input
    shape: badge / inferred_state / segment_start_stop / speed / speed_limit / distance /
    stopping_offset_cm / last_fire / reentry_pending / paused, + `sim_state.curr_stop/cnt_pa` + `stops`
    names) when given; else standalone placeholders.
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
    vals = _band_vals(status, sim_state, stops)
    pygame.draw.rect(surf, BAND_COLOR, (0, 0, SCREEN_W, BAND_H))
    cjk = pixel_font("zh_HK")  # pan-CJK Ark face — renders katakana + kanji (station names + chrome)
    font = pixel_font(ACTIVE_LANG)
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BAND_BTN_TEXT_NATIVE)  # button labels, a touch larger

    # right-edge control cluster: [pause][save][home], uniform squares (all sized to the home label).
    home_label = HOME_BY_LANG[ACTIVE_LANG]
    t = _BAND_BTN_TUNEABLES
    bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]
    sw, sh = lowres_text_size(home_label, font, BAND_BTN_BOX_K, t["line_gap"])  # box at k=2; label k=1
    btn_sz = int(max(sw, sh) + 2 * HOME_TEXT_MARGIN + bevel)
    btn_top = (BAND_H - btn_sz) // 2
    home_rect = pygame.Rect(SCREEN_W - btn_sz - HOME_MARGIN, btn_top, btn_sz, btn_sz)
    save_rect = pygame.Rect(home_rect.left - BAND_BTN_GAP - btn_sz, btn_top, btn_sz, btn_sz)
    pause_rect = pygame.Rect(save_rect.left - BAND_BTN_GAP - btn_sz, btn_top, btn_sz, btn_sz)

    # LEFT column: 3 small (k=1) lines — state/badge (status) or notif/state (placeholder)
    for (text, color), ry in zip(vals["left"], (NOTIF_Y, STATE_SEG_Y, STATE_INFO_Y)):
        if text:
            _blit_lowres(surf, text, LEFT_X, ry, cjk, color, STATE_K)

    # CENTER readout cell: speed limit / speed / distance, right-aligned between separators.
    num_font = i18n.pixel_font_for_lang("zh_HK", READOUT_NUM_SS_NATIVE)  # high native → supersampled down
    unit_font = i18n.pixel_font_for_lang("zh_HK", READOUT_UNIT_NATIVE)  # unit a touch larger
    pygame.draw.line(surf, SEP_COLOR, (CELL_X, 8), (CELL_X, BAND_H - 8), SEP_W)
    pygame.draw.line(surf, SEP_COLOR, (CELL_X + CELL_W, 8), (CELL_X + CELL_W, BAND_H - 8), SEP_W)
    rx = CELL_X + CELL_W - CELL_PAD
    ticks = pygame.time.get_ticks()
    # LIMIT carries the highlight block (only the limit value, NOT the whole column):
    #   * over speed   → the block FLASHES RED (warning), light ink.
    #   * just changed → BLINKS cyan↔plain, then settles to steady cyan.
    #   * resting      → steady cyan (cyan is the limit's normal state).
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
        limit_hl = True
        if vals["limit_changed"]:
            limit_hl = force_flash_on or (ticks // LIMIT_FLASH_MS) % 2 == 0
        _blit_readout(surf, *vals["limit"], rx, LIMIT_Y, num_font, unit_font, CELL_INK, CELL_UNIT_INK, highlight=limit_hl)
    _blit_readout(surf, *vals["speed"], rx, SPEED_Y, num_font, unit_font, CELL_INK, CELL_UNIT_INK)
    _blit_readout(surf, *vals["dist"], rx, DIST_Y, num_font, unit_font, CELL_INK, CELL_UNIT_INK)

    # MESSAGE strips: two dim bars; active messages render BRIGHT YELLOW + FLASH (auto-clear when none)
    msg_w = pause_rect.left - MSG_GAP_R - MSG_X
    msg_on = force_flash_on or (pygame.time.get_ticks() // MSG_FLASH_MS) % 2 == 0
    for i in range(2):
        sy = STRIP_Y1 + i * (STRIP_H + STRIP_GAP)
        pygame.draw.rect(surf, STRIP_COLOR, (MSG_X, sy, msg_w, STRIP_H), border_radius=STRIP_RADIUS)
        if i < len(vals["msgs"]) and msg_on:
            text = vals["msgs"][i]
            _, th = lowres_text_size(text, cjk, MSG_K, 0)
            _blit_lowres(surf, text, MSG_X + MSG_PAD_X, sy + (STRIP_H - th) // 2, cjk, _MSG_YELLOW, MSG_K)

    draw_tims_button(surf, pause_rect, PAUSE_BY_LANG[ACTIVE_LANG], font=btn_font, t=t, state="pressed" if vals["paused"] else "normal")
    draw_tims_button(surf, save_rect, SAVE_BY_LANG[ACTIVE_LANG], font=btn_font, t=t)
    draw_tims_button(surf, home_rect, home_label, font=btn_font, t=t)
    return {"home": home_rect, "save": save_rect, "pause": pause_rect}


def _version_tag_rect(word, digits):
    """Bounding Rect of a 'word + TIMS-numerals' tag anchored at (VERSION_X, VERSION_Y) — measure
    only, no draw. Used to size a stable click target across the blink phases."""
    font = pixel_font(ACTIVE_LANG)
    lw, lh = lowres_text_size(word + " ", font, VERSION_K, 0)
    num_w, _ = lowres_number_size(digits, font, k=VERSION_K, xscale=VERSION_DIGIT_XSCALE, gap=VERSION_DIGIT_GAP)
    return pygame.Rect(VERSION_X, VERSION_Y, lw + num_w, lh)


def _render_version_tag(surf, word, digits, *, text_color, highlight):
    """Draw the version-tag style at (VERSION_X, VERSION_Y): i18n `word` (low-res) flush-left + `digits`
    as trimmed/widened TIMS numerals (draw_lowres_number), baselines aligned. `highlight` paints the
    cyan block behind it (dark ink) — the new-version flash shares this exact style, just different
    word + digits + colour."""
    font = pixel_font(ACTIVE_LANG)
    wlabel = word + " "
    lw, lh = lowres_text_size(wlabel, font, VERSION_K, 0)
    rect = _version_tag_rect(word, digits)
    if highlight:
        pygame.draw.rect(surf, HINT_CYAN_COLOR, rect.inflate(2 * HINT_PAD_X, 2 * HINT_PAD_Y), border_radius=3)
    ltmp = pygame.Surface((lw, lh), pygame.SRCALPHA)
    draw_lowres_text(ltmp, wlabel, pygame.Rect(0, 0, lw, lh), font, text_color, max_k=VERSION_K, line_gap=0, align="center")
    surf.blit(ltmp, (VERSION_X, VERSION_Y))
    draw_lowres_number(surf, digits, (VERSION_X + lw, VERSION_Y), font, text_color, k=VERSION_K, xscale=VERSION_DIGIT_XSCALE, gap=VERSION_DIGIT_GAP)


def render_menu(surf):
    """Draw page-1 menu onto ``surf``. Returns (action_rects, action_font, action_t, hint_rect,
    lang_rects): the big-button hit-rects keyed by ACTION_IDS, the font + tuneable they were drawn
    with (so a caller can redraw one in the pressed state for the press/transition beat), the
    flashing version-tag hit-rect (None when no newer release), and the language-knob hit-rects
    keyed by lang code."""
    surf.fill(BG_COLOR)
    _render_topband(surf)  # persistent black status band across the top

    # ── version tag, bottom-left. NORMAL: i18n "Version" word + "054" TIMS numerals. When a newer
    #    release exists the tag ALTERNATES (blink) with a SAME-STYLE hint — i18n update word + the new
    #    version's numerals ("060") under a cyan highlight block (the TIMS 設定完了 idiom). Both the
    #    text AND colour change, but the hint keeps the version-tag look (word + TIMS numerals). ──
    ver_digits = VERSION.replace(".", "")
    info = update_check.get_update()
    if info is None and PREVIEW_FORCE_HINT:
        info = PREVIEW_UPDATE
    show_hint = info is not None and (pygame.time.get_ticks() // HINT_BLINK_MS) % 2 == 0
    if show_hint:
        _render_version_tag(surf, i18n.t("setup.new_version_label"), info[0].replace(".", ""), text_color=HINT_INK_COLOR, highlight=True)
    else:
        _render_version_tag(surf, i18n.t("setup.version_label"), ver_digits, text_color=VERSION_COLOR, highlight=False)
    # stable click target across both blink phases (union of the two tag footprints)
    hint_rect = None
    if info is not None:
        normal_r = _version_tag_rect(i18n.t("setup.version_label"), ver_digits)
        hint_r = _version_tag_rect(i18n.t("setup.new_version_label"), info[0].replace(".", "")).inflate(2 * HINT_PAD_X, 2 * HINT_PAD_Y)
        hint_rect = normal_r.union(hint_r)

    # ── language buttons: STRICTLY SQUARE, side = larger content dim + margin + bevel ──
    # Sized from the CJK sizer so all three knobs match; the 2x2 footprint isn't square (rows are
    # taller than cols), so we square up to its larger dim. Each label is drawn tight-packed and
    # centered, so the squaring-up just becomes extra margin on the narrower axis (EN gets more all
    # round). The margin keeps text off the bevel.
    t = _LANG_TUNEABLES
    bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]
    sw, sh = lowres_text_size(LANG_SIZER, pixel_font("zh_HK"), LANG_K, LANG_LINE_GAP)
    lang_w = lang_h = max(sw, sh) + 2 * LANG_TEXT_MARGIN + bevel

    # right-aligned horizontal row in the BOTTOM-right corner (top-right is the band's home button)
    row_w = len(LANGS) * lang_w + (len(LANGS) - 1) * LANG_GAP
    lang_x0 = SCREEN_W - LANG_MARGIN_RIGHT - row_w
    lang_y = SCREEN_H - LANG_MARGIN_BOTTOM - lang_h
    lang_rects = {}
    for i, (code, label) in enumerate(LANGS):
        x = lang_x0 + i * (lang_w + LANG_GAP)
        rect = pygame.Rect(x, lang_y, lang_w, lang_h)
        # yellow = PRESSED (momentary feedback), NOT selected — knobs rest in the default state
        draw_tims_button(surf, rect, label, font=pixel_font(code), t=_LANG_TUNEABLES, state="normal")
        lang_rects[code] = rect

    # ── four big action buttons: side by side, centered both axes ────────────────
    action_font = pixel_font(ACTIVE_LANG)
    actions = ACTIONS_BY_LANG[ACTIVE_LANG]
    # pin every action button to ONE text size: the densest label sets k, the rest cap to it
    at = _ACTION_TUNEABLES
    a_bevel = 2 * at["outer_border_w"] + at["bezel_lip_w"] + at["bezel_shadow_w"]
    a_face = pygame.Rect(0, 0, BIG_W - a_bevel, BIG_H - a_bevel)
    uniform_k = min(lowres_fit_k(lab, a_face, action_font, at["text_max_k"], at["line_gap"], at["text_pad"]) for lab in actions)
    at = {**at, "text_max_k": uniform_k}
    big_row_w = len(actions) * BIG_W + (len(actions) - 1) * BIG_GAP
    big_x0 = (SCREEN_W - big_row_w) // 2
    big_y = (SCREEN_H - BIG_H) // 2
    action_rects = {}
    for i, label in enumerate(actions):
        x = big_x0 + i * (BIG_W + BIG_GAP)
        rect = pygame.Rect(x, big_y, BIG_W, BIG_H)
        draw_tims_button(surf, rect, label, font=action_font, t=at)
        action_rects[ACTION_IDS[i]] = rect
    return action_rects, action_font, at, hint_rect, lang_rects


def _launch_tutorial():
    """Open the green TIMS tutorial screen (resizes the display to its window), run it to
    ESC/close, then hand control back so the menu loop can restore its own size."""
    from tutorial_tims import WINDOW_SIZE, TimsTutorial

    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("TIMS tutorial (green build)")
    TimsTutorial(screen).run()


def run_interactive():
    """Clickable menu preview: click a language knob to switch the UI language; click the Tutorial
    card to enter the tutorial screen (ESC returns here); click the flashing version tag to open the
    release page. Other cards are inert (placeholders, per the page-1 plan)."""
    global ACTIVE_LANG
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("TIMS home menu (draft)")
    clock = pygame.time.Clock()
    action_rects, action_font, action_t, hint_rect, lang_rects = render_menu(screen)
    running = True
    while running:
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # version tag (flashing) → release page
                if hint_rect is not None and hint_rect.collidepoint(event.pos):
                    info = update_check.get_update() or (PREVIEW_UPDATE if PREVIEW_FORCE_HINT else None)
                    if info:
                        webbrowser.open(info[1])
                    continue
                # language knob → momentary yellow beat, then switch the UI language
                lang_hit = next((c for c, r in lang_rects.items() if r.collidepoint(event.pos)), None)
                if lang_hit is not None:
                    press_transition(
                        screen,
                        rect=lang_rects[lang_hit],
                        label=dict(LANGS)[lang_hit],
                        font=pixel_font(lang_hit),
                        t=_LANG_TUNEABLES,
                        redraw=lambda s: render_menu(s),
                        blank_color=BG_COLOR,
                        blank_ms=0,
                    )
                    ACTIVE_LANG = lang_hit
                    i18n.set_language(lang_hit)
                    continue
                for i, aid in enumerate(ACTION_IDS):
                    rect = action_rects.get(aid)
                    if not (rect and rect.collidepoint(event.pos)):
                        continue
                    is_nav = aid == "tutorial"  # only Tutorial navigates; others are inert placeholders
                    # press beat (yellow) for every card; loading beat only for the navigational one
                    press_transition(
                        screen,
                        rect=rect,
                        label=ACTIONS_BY_LANG[ACTIVE_LANG][i],
                        font=action_font,
                        t=action_t,
                        redraw=lambda s: render_menu(s),
                        blank_color=BG_COLOR,
                        blank_ms=450 if is_nav else 0,
                    )
                    if is_nav:
                        _launch_tutorial()
                        # Tutorial owned the display at its own size — restore the menu window.
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                        pygame.display.set_caption("TIMS home menu (draft)")
                    break
        action_rects, action_font, action_t, hint_rect, lang_rects = render_menu(screen)
        pygame.display.flip()
    pygame.quit()


def save_screenshot(path):
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    render_menu(surf)
    out = str(project_root() / path)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH", help="static render to PATH instead of interactive")
    args = ap.parse_args()
    if args.screenshot:
        save_screenshot(args.screenshot)
    else:
        run_interactive()


if __name__ == "__main__":
    main()

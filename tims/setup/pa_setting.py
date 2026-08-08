"""PA-setting screen (案内設定 / TIMS C07AA), reached from the home menu's 報站設定 (PA Setup)
card. Models the real TIMS 案内設定 register: a settings-summary table (route / train-type /
origin-terminal / …) plus a route-picker entry button and launch buttons. Renders the persistent
top band (shared with the home menu) so it reads as the same chrome. This is the default production
PA-setting page; ``run_on()`` returns a launch config once a route is committed and launched.

Deltas from the real TIMS screen (tims-pa-setting.png):
  * the 6-car consist diagram + its 'A' consist button are REMOVED (we have no consist data)
    → replaced by a single 選擇路綫 (Select Route) button.
  * the 番線 (platform) button + 現在駅 (current-station) button are REMOVED (no platform model).

The 選擇路綫 button opens the route → diagram → station picker (the 始発駅選択 flow,
tims-route-selection.jpg); 列車型號 picks the train model; the launch buttons start the drive
(OCR auto-PA behind a one-time consent gate, or manual).

Preview:   uv run _dev_scripts/preview_setup_tims.py --screen pa   (L = cycle locale, ESC = quit)
Static:    uv run _dev_scripts/preview_setup_tims.py --screen pa --screenshot pa_setting.png
"""

import json
import os

import pygame

import i18n
from app_paths import project_root
from displays.train_models import DEFAULT_MODEL_KEY, model_choices
from ..widgets import (
    draw_lowres_text_fat,
    draw_tims_button,
    lowres_text_size,
    press_transition,
)

from .. import band
from .. import chrome
from . import dims

ACTIVE_LANG = "zh_HK"  # develop/preview in zh_HK (chrome is i18n; station/line names stay JP)

# fmt: off
# ── layout tuneables (all derived coords flow from these) ─────────────────────
SCREEN_W, SCREEN_H = dims.SCREEN_W, dims.SCREEN_H   # 730×610 — same own-window size as the home menu
BG_COLOR           = dims.BG_COLOR                  # mirror the menu bg

# title row (below the band): screen-code + cyan heading — drawn by chrome.title_row (shared recipe).
SCREEN_CODE        = "C07AA"             # real TIMS code for 案内設定 (kept for fidelity; droppable)

# 選擇路綫 button (replaces the removed consist diagram + 'A' button) — centered, just above the table
SELECT_GAP_ABOVE   = 10                  # 選擇路綫 button sits this far ABOVE the table top
BTN_MARGIN         = 12                  # gap between a button's label block and its bevel
BTN_NATIVE         = 20                  # button label render px

# settings-summary table — BLACK interior, tight rows. Left consist 'A' column, then label | value.
# WIDE (≥2× the earlier draft). Row text left-aligns to its column line (tiny CELL_PAD_X gap).
TABLE_X            = 40
TABLE_Y            = 232                   # dropped a bit — reserves space above for future train cars
A_COL_W            = 54                   # big consist 'A' column (spans all rows, one tall cell)
VALUE_COL_W        = 380                  # value column width (−20 — table a touch less wide)
ROW_H              = 26                   # tight — close to one text height
TABLE_BG           = chrome.PANEL_BG          # near-black interior (TIMS table)
TABLE_BORDER       = chrome.FRAME      # slate grid lines
TABLE_BORDER_W     = 1                    # thin INTERNAL grid lines (column / row dividers)
TABLE_BG_PAD       = 5                    # black background extends 5px OUTSIDE the table grid (all sides)
A_NATIVE           = 52                   # big consist letter px
A_XSCALE           = 1.4                  # 'A' uses the same x-stretched fat variant as the title
A_COLOR            = chrome.INK      # white — same as the table text
PATTERN_NO_NATIVE  = 16                   # operation-No. "(00x)" px — shown UNDER the big A after a commit
PATTERN_NO_GAP     = 3                    # gap below the A's ink bottom to the (00x)
PATTERN_NO_COLOR   = chrome.INK      # white — same as the A
ROW_LABEL_NATIVE   = 18                   # Japanese row labels px (+2 — fills the tight row)
ROW_LABEL_COLOR    = chrome.INK
ROW_VALUE_NATIVE   = 20                   # Japanese values (station / line names) px
ROW_VALUE_COLOR    = chrome.INK
CELL_PAD_X         = 2                    # text hugs the column line (1–2px gap)

# OCR launch cluster (bottom-right) — mirrors IRL tims_pa_setting_done.png: a 1-over-2 button group
# inside a thin white frame, right-aligned. All THREE buttons are EQUAL width + height (sized to the
# worst-case label; shorter labels just justify wider). Labels are 2-line (mode line / action line),
# localized via i18n (keys below) — resolved at render, so they re-flow on a locale switch. The manual
# button (手動報站起動) is the manual (PageDown) launch — it replaced the old 確認 button.
OCR_LAUNCH_KEY = "setup_tims.pa_setting.ocr_launch"  # TOP (right): arms OCR auto-PA → straight to the live LCD
OCR_MANUAL_KEY = "setup_tims.pa_setting.manual_launch"  # bottom-LEFT: manual launch
OCR_SETTING_KEY = "setup_tims.pa_setting.ocr_settings"  # bottom-RIGHT: opens the OCR settings / consent page
OCR_BTN_NATIVE     = 18                  # cluster label render px — LOCKED (readable, compact; page BTN_NATIVE=20)
OCR_BTN_MARGIN_X   = 12                  # cluster button horizontal padding (label ↔ bevel)
OCR_BTN_MARGIN_Y   = 5                   # cluster button VERTICAL padding — small = short buttons
OCR_CLUSTER_RIGHT  = SCREEN_W - 22       # cluster's right edge (margin off the window right)
OCR_CLUSTER_BOTTOM = SCREEN_H - 22       # cluster's bottom edge (margin off the window bottom)
OCR_BTN_GAP        = 1                   # gap between the 3 buttons (rows + columns) — near-flush
OCR_BOX_PAD        = 5                   # white frame inset around the 3 buttons (hugs close to the bevels)
OCR_BOX_COLOR      = chrome.GRID     # thin slate-white frame — follows the button silhouette (L-notch)
OCR_BOX_W          = 1                   # frame outline width
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# Chrome labels come from translations_app.json via i18n.t — keys setup_tims.action.pa_setup (title) /
# setup_tims.pa_setting.select_route / setup_tims.confirm.

# Summary-table row LABELS mirror the IRL TIMS field labels but are now LOCALIZED via i18n (keys below),
# resolved at render so they re-flow on a locale switch — zh_HK hugs the JP kanji, zh_CN is Simplified.
# VALUES stay Japanese route/station names, EMPTY until a route is picked — 選擇路綫 populates them from
# route.json. Row 4 (IRL 月台/platform, always blank here — no platform model) is REPURPOSED to show the
# picked train model / LCD skin — no IRL TIMS reference for this, a temporary home (drawn dynamically in
# render() from _current_model_label(), not stored in ROW_VALUES). Revisit the placement later.
MODEL_ROW = 3  # table row index that shows the current train model (the repurposed 月台 slot)
ROW_LABEL_KEYS = [
    "setup_tims.pa_setting.field.route",
    "setup_tims.pa_setting.field.type",
    "setup_tims.pa_setting.field.from_to",
    "setup_tims.pa_setting.field.model",
    "setup_tims.pa_setting.field.remark",
]
ROW_VALUES = ["", "", "", "", ""]
PATTERN_NO = None  # run-pattern No. (字軌選擇) → shown as "(00x)" under the big A; None until a commit
_committed = None  # raw route_select.run_on result for the committed route — drives the 起動 launch config
_model_override = None  # last user-picked train model (列車型號 picker); session-persistent, overrides the route default


def _current_model_label():
    """Designation of the model in effect (override > committed route's default > global default), e.g.
    'E235-1000' — shown in the 列車型號 table row so the pick is visible without re-opening the picker."""
    key = _model_override or (_committed["route"]["model"] if _committed else DEFAULT_MODEL_KEY)
    return dict(model_choices()).get(key, key)


def _apply_selection(result):
    """Fill the summary-table VALUES from a route_select commit ({"route": <variant dict>, "start_name":
    <stop name>, "pattern_no": <int>}). Row 3 = CHOSEN start stop → route terminal (始発・終着駅); row 5 = the composed 備考 (direction
    / through-service from the run-pattern page); platform (月台) has no model, stays blank. Stashes the
    raw result in `_committed` so 確認/起動 can build the launch config from it."""
    global ROW_VALUES, PATTERN_NO, _committed
    from . import route_select  # lazy (sibling) — reuse its remark composer

    route = result["route"]
    # Use the start NAME the picker resolved — the start grid is built from variants[0], but the
    # committed route is the chosen variant, so re-indexing here against a different stop list could
    # mis-resolve (see route_select.run_on). Name is variant-agnostic.
    start_name = result.get("start_name") or route.get("start", "")
    remark = route_select._compose_remark(route["name"], route.get("remarks"))
    ROW_VALUES = [route["name"], route["type"], f"{start_name} → {route['end']}", "", remark]
    PATTERN_NO = result.get("pattern_no")
    _committed = result


def _build_config(result, ocr=False):
    """Bridge a committed route_select result → a launch config shaped like the dict ``main._run_drive`` consumes
    (action / work_dir / route_data / model). `start_idx` = the chosen start stop resolved by NAME
    against the committed variant's own stops (variant-agnostic — variants can carry different stop
    lists; this closes the deferred v0-index finding). main.py jumps the sim to start_idx before run().
    `ocr=True` (OCR自動報站起動) merges the auto_input launch fields (auto_input=True + lead_m /
    interval_s from the 自動放送設定 page); default = MANUAL (auto_input False)."""
    route = result["route"]
    with open(os.path.join(route["path"], "route.json"), encoding="utf-8") as f:
        route_data = json.load(f)
    stops = route.get("stops", [])
    start_name = result.get("start_name") or ""
    start_idx = stops.index(start_name) if start_name in stops else 0
    cfg = {
        "action": "select",
        "work_dir": route["path"],
        "route_data": route_data,
        "model": _model_override or route["model"],
        "auto_input": False,
        "start_idx": start_idx,
    }
    if ocr:
        from . import ocr_setting

        cfg.update(ocr_setting.ocr_launch_extras())  # auto_input=True + lead_m / interval_s (fresh from settings)
    return cfg


# Page buttons use the shared LABEL preset (center/natural, crammed 1-by-1, v_pad=0) — chrome.BTN_LABEL.
_BTN_TUNEABLES = chrome.BTN_LABEL


def _button_size(label, font):
    """Content-derived (w, h): box hugs the AA-off native label + BTN_MARGIN + bevel."""
    lw, lh = lowres_text_size(label, font, 1, _BTN_TUNEABLES["line_gap"])
    t = _BTN_TUNEABLES
    bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]
    return int(lw + 2 * BTN_MARGIN + bevel), int(lh + 2 * BTN_MARGIN + bevel)


def render(surf):
    """Draw the PA-setting page onto ``surf``; returns hit-rects
    {"select", "model", "home", "ocr_launch", "manual", "ocr_setting"}."""
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(surf)  # persistent black status band across the top

    # title row: screen-code + cyan heading (shared chrome recipe — bottom-aligned, x-stretched)
    chrome.title_row(surf, SCREEN_CODE, i18n.t("setup_tims.action.pa_setup"), ACTIVE_LANG)

    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)

    # ── table geometry first (so the select button can sit above the VISIBLE table = the dark bg) ──
    # Label column width DERIVES from the widest RESOLVED label in the active locale (line 204) so the
    # label column hugs its text — the widest row varies by locale now that labels are localized.
    labels = [i18n.t(k) for k in ROW_LABEL_KEYS]  # localized field labels (re-resolve on locale switch)
    n = len(labels)
    table_h = n * ROW_H
    label_font = i18n.pixel_font_for_lang(ACTIVE_LANG, ROW_LABEL_NATIVE)  # active-locale face (labels localize now)
    value_font = i18n.pixel_font_for_lang("en", ROW_VALUE_NATIVE)  # "en"=NotoSansJP — values are JP proper nouns
    label_col_w = max(lowres_text_size(l, label_font, 1, 0)[0] for l in labels) + 2 * CELL_PAD_X
    table_w = A_COL_W + label_col_w + VALUE_COL_W
    grid = pygame.Rect(TABLE_X, TABLE_Y, table_w, table_h)
    bg = grid.inflate(2 * TABLE_BG_PAD, 2 * TABLE_BG_PAD)  # dark background extends beyond the grid

    # 選擇路綫 button — centered, SELECT_GAP_ABOVE above the visible table (the dark-bg top)
    sel_label = i18n.t("setup_tims.pa_setting.select_route")
    sw, sh = _button_size(sel_label, btn_font)
    sel_rect = pygame.Rect((SCREEN_W - sw) // 2, bg.top - SELECT_GAP_ABOVE - sh, sw, sh)
    draw_tims_button(surf, sel_rect, sel_label, font=btn_font, t=_BTN_TUNEABLES)

    # settings-summary table — the black BACKGROUND extends OUTSIDE the grid (a black margin around it);
    # the 1px outline frames the GRID itself, so the black shows beyond it. Thin internal grid lines.
    pygame.draw.rect(surf, TABLE_BG, bg)  # black background — bigger than the grid (shows outside it)
    label_x = TABLE_X + A_COL_W
    value_x = label_x + label_col_w
    pygame.draw.line(surf, TABLE_BORDER, (label_x, TABLE_Y), (label_x, TABLE_Y + table_h), TABLE_BORDER_W)
    pygame.draw.line(surf, TABLE_BORDER, (value_x, TABLE_Y), (value_x, TABLE_Y + table_h), TABLE_BORDER_W)
    for i, label in enumerate(labels):
        ry = TABLE_Y + i * ROW_H
        if i > 0:  # row dividers run across label+value only — the 'A' column stays one tall cell
            pygame.draw.line(surf, TABLE_BORDER, (label_x, ry), (TABLE_X + table_w, ry), 1)
        _, lh = lowres_text_size(label, label_font, 1, 0)
        chrome.blit_lowres(surf, label, label_x + CELL_PAD_X, ry + (ROW_H - lh) // 2, label_font, ROW_LABEL_COLOR, 1)
        value = _current_model_label() if i == MODEL_ROW else ROW_VALUES[i]  # model row is dynamic, not stored
        if value:
            _, vh = lowres_text_size(value, value_font, 1, 0)
            chrome.blit_lowres(surf, value, value_x + CELL_PAD_X, ry + (ROW_H - vh) // 2, value_font, ROW_VALUE_COLOR, 1)
    # big consist 'A' — white, x-stretched (same fat variant as the title), centered in its column
    a_font = i18n.pixel_font_for_lang("en", A_NATIVE)
    aw, ah = lowres_text_size("A", a_font, 1, 0)
    asw = max(1, round(aw * A_XSCALE))
    a_y = TABLE_Y + (table_h - ah) // 2
    draw_lowres_text_fat(surf, "A", (TABLE_X + (A_COL_W - asw) // 2, a_y), a_font, A_COLOR, xscale=A_XSCALE, k=1, line_gap=0)
    if PATTERN_NO is not None:  # run-pattern No. → "(00x)" centered under the A
        no_text = f"({PATTERN_NO:03d})"
        no_font = i18n.pixel_font_for_lang("en", PATTERN_NO_NATIVE)
        nw, _ = lowres_text_size(no_text, no_font, 1, 0)
        chrome.blit_lowres(surf, no_text, TABLE_X + (A_COL_W - nw) // 2, a_y + ah + PATTERN_NO_GAP, no_font, PATTERN_NO_COLOR, 1)
    pygame.draw.rect(surf, TABLE_BORDER, grid, TABLE_BORDER_W)  # 1px outline around the GRID — black bg shows OUTSIDE it

    # OCR launch cluster GEOMETRY (bottom-right) — 1-over-2, right-aligned, EQUAL-size buttons. Computed
    # BEFORE 列車型號 so that button can align to the cluster's bottom row (row2). Uniform size =
    # worst-case content size across the 3 labels (shorter labels center inside).
    ocr_font = i18n.pixel_font_for_lang(ACTIVE_LANG, OCR_BTN_NATIVE)
    ocr_launch_label, ocr_manual_label, ocr_setting_label = (i18n.t(OCR_LAUNCH_KEY), i18n.t(OCR_MANUAL_KEY), i18n.t(OCR_SETTING_KEY))
    lg = _BTN_TUNEABLES["line_gap"]
    _lbl_sz = [lowres_text_size(l, ocr_font, 1, lg) for l in (ocr_launch_label, ocr_manual_label, ocr_setting_label)]
    _bevel = 2 * _BTN_TUNEABLES["outer_border_w"] + _BTN_TUNEABLES["bezel_lip_w"] + _BTN_TUNEABLES["bezel_shadow_w"]
    bw = max(w for w, _ in _lbl_sz) + 2 * OCR_BTN_MARGIN_X + _bevel  # equal width (worst-case label)
    bh = max(h for _, h in _lbl_sz) + 2 * OCR_BTN_MARGIN_Y + _bevel  # equal height — MARGIN_Y keeps it short
    br_x = OCR_CLUSTER_RIGHT - OCR_BOX_PAD - bw  # bottom-right button x (top button shares it)
    bl_x = br_x - OCR_BTN_GAP - bw  # bottom-left button x
    row2_y = OCR_CLUSTER_BOTTOM - OCR_BOX_PAD - bh  # bottom row y
    row1_y = row2_y - OCR_BTN_GAP - bh  # top row y (above bottom-right = right-aligned)
    launch_rect = pygame.Rect(br_x, row1_y, bw, bh)
    manual_rect = pygame.Rect(bl_x, row2_y, bw, bh)
    setting_rect = pygame.Rect(br_x, row2_y, bw, bh)

    # 列車型號 button — IRL 番線 slot repurposed → model picker. SAME size + font as the OCR cluster
    # buttons (bw × bh, OCR_BTN_NATIVE) so the whole bottom row reads as ONE uniform button group;
    # LEFT-aligned under the table, sharing the cluster's bottom-row y (row2).
    model_label = i18n.t("setup_tims.pa_setting.model")
    model_rect = pygame.Rect(TABLE_X, row2_y, bw, bh)
    draw_tims_button(surf, model_rect, model_label, font=ocr_font, t=_BTN_TUNEABLES)

    # cluster white frame (L-notch, follows the silhouette — empty top-left cut out) + the 3 buttons
    p = OCR_BOX_PAD
    frame_pts = [
        (br_x - p, row1_y - p),  # top button: top-left
        (br_x + bw + p, row1_y - p),  # top button: top-right
        (br_x + bw + p, row2_y + bh + p),  # right column: bottom-right
        (bl_x - p, row2_y + bh + p),  # bottom row: bottom-left
        (bl_x - p, row2_y - p),  # bottom-left button: top-left
        (br_x - p, row2_y - p),  # notch: back in to the right column's left edge
    ]
    pygame.draw.polygon(surf, OCR_BOX_COLOR, frame_pts, OCR_BOX_W)
    # the two LAUNCH buttons are locked (silver) until a route is committed; OCR設定 stays always-available.
    # Once ready, OCR起動 FLASHES white to promote the OCR path (we steer users to OCR); 手動起動 stays steady.
    locked = _committed is None
    launch_t = {**_BTN_TUNEABLES, **chrome.DISABLED} if locked else _BTN_TUNEABLES
    ocr_flash = "waiting" if (not locked and (pygame.time.get_ticks() // 450) % 2 == 0) else "normal"  # 450ms half-period
    draw_tims_button(surf, launch_rect, ocr_launch_label, font=ocr_font, t=launch_t, state=ocr_flash)
    draw_tims_button(surf, manual_rect, ocr_manual_label, font=ocr_font, t=launch_t)
    draw_tims_button(surf, setting_rect, ocr_setting_label, font=ocr_font, t=_BTN_TUNEABLES)

    return {
        "select": sel_rect,
        "model": model_rect,
        "home": band_hits["home"],
        "ocr_launch": launch_rect,
        "manual": manual_rect,
        "ocr_setting": setting_rect,
    }


def run_on(screen):
    """Run the PA-setting page on an EXISTING display ``screen`` until the user launches or returns.
    Entry the home menu's 報站設定 card calls. Returns the LAUNCH CONFIG dict (action/work_dir/route_data/
    model/start_idx) when 手動報站起動 is pressed with a route committed; None on band Home / ESC (back to the
    menu). Home/select/confirm get the shared TIMS press beat; Home adds the loading beat."""
    global _model_override
    clock = pygame.time.Clock()
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)
    ocr_font = i18n.pixel_font_for_lang(ACTIVE_LANG, OCR_BTN_NATIVE)  # smaller cluster face (press beats)
    home_font = i18n.pixel_font_for_lang(band.ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE)
    running = True
    while running:
        hits = render(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))  # let the menu loop see it too
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits["home"].collidepoint(event.pos):  # band Home → press + load beat → back to menu
                    press_transition(
                        screen,
                        rect=hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=home_font,
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=lambda s: render(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        # the OCR band (top strip) is persistent chrome — exclude it from the load beat
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    running = False
                elif hits["select"].collidepoint(event.pos):  # 選擇路綫 → press + load beat → route/station picker
                    press_transition(
                        screen,
                        rect=hits["select"],
                        label=i18n.t("setup_tims.pa_setting.select_route"),
                        font=btn_font,
                        t=_BTN_TUNEABLES,
                        redraw=lambda s: render(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    from . import route_select  # local import — defers the route.json scan (load_routes) until 選擇路綫 is pressed

                    route_select.ACTIVE_LANG = ACTIVE_LANG
                    result = route_select.run_on(screen)
                    if result == "home":  # band Home pressed deep in the picker → bubble the return to the menu
                        running = False
                    elif isinstance(result, dict):  # 設定 committed a route + start stop → fill the summary table
                        _apply_selection(result)
                    # result is None → user backed out of the picker; stay on this page
                elif hits["manual"].collidepoint(event.pos):
                    # 手動報站起動 = manual launch (起動). Locked (silver) until a route is committed → a click on
                    # the locked button does nothing (no press flash). Once ready: yellow press + loading beat,
                    # then build the config + bubble up to boot the live LCD.
                    if _committed is not None:
                        press_transition(
                            screen,
                            rect=hits["manual"],
                            label=i18n.t(OCR_MANUAL_KEY),
                            font=ocr_font,
                            t=_BTN_TUNEABLES,
                            redraw=lambda s: render(s),
                            blank_color=BG_COLOR,
                            blank_ms=450,
                            blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                        )
                        return _build_config(_committed)
                elif hits["ocr_launch"].collidepoint(event.pos):
                    # OCR自動報站起動 = OCR auto-PA launch. Locked (silver) until a route is committed → a click on
                    # the locked button does nothing. Once ready: yellow press + loading beat, then the one-time
                    # consent gate (自動放送設定); on consent, build the launch config (auto_input=True).
                    if _committed is not None:
                        press_transition(
                            screen,
                            rect=hits["ocr_launch"],
                            label=i18n.t(OCR_LAUNCH_KEY),
                            font=ocr_font,
                            t=_BTN_TUNEABLES,
                            redraw=lambda s: render(s),
                            blank_color=BG_COLOR,
                            blank_ms=450,
                            blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                        )
                        from . import ocr_setting

                        ocr_setting.ACTIVE_LANG = ACTIVE_LANG
                        res = ocr_setting.ensure_consent(screen)
                        if res == "home":  # band Home in the consent gate → bubble to the menu
                            running = False
                        elif res:  # consent given → build the OCR launch config
                            return _build_config(_committed, ocr=True)
                elif hits["ocr_setting"].collidepoint(event.pos):
                    # OCR自動報站設定 = settings steppers (lead / interval) — DIRECT, no consent gate.
                    # Consent is a LAUNCH-time gate only (自動放送起動); the settings button just opens
                    # the page (load beat like 選擇路綫 / 列車型號).
                    press_transition(
                        screen,
                        rect=hits["ocr_setting"],
                        label=i18n.t(OCR_SETTING_KEY),
                        font=ocr_font,
                        t=_BTN_TUNEABLES,
                        redraw=lambda s: render(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    from . import ocr_setting

                    ocr_setting.ACTIVE_LANG = ACTIVE_LANG
                    if ocr_setting.run_settings(screen) == "home":  # band Home in settings → bubble to the menu
                        running = False
                elif hits["model"].collidepoint(event.pos):  # 列車型號 → model picker (X00AA)
                    press_transition(
                        screen,
                        rect=hits["model"],
                        label=i18n.t("setup_tims.pa_setting.model"),
                        font=ocr_font,
                        t=_BTN_TUNEABLES,
                        redraw=lambda s: render(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    from . import model_select  # local import (sibling)

                    model_select.ACTIVE_LANG = ACTIVE_LANG
                    current = _model_override or (_committed["route"]["model"] if _committed else DEFAULT_MODEL_KEY)
                    res = model_select.run_on(screen, current)
                    if res == "home":  # band Home deep in the picker → bubble to the menu
                        running = False
                    elif res is not None:  # a model key chosen → set the session override (persists this run)
                        _model_override = res
                    # res None → backed out; model unchanged


_LANGS = ("en", "zh_HK", "zh_CN")


def run_interactive():
    global ACTIVE_LANG
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("PA setting (draft)")
    clock = pygame.time.Clock()
    li = _LANGS.index(ACTIVE_LANG)
    running = True
    while running:
        render(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_l:
                    li = (li + 1) % len(_LANGS)
                    ACTIVE_LANG = _LANGS[li]
                    i18n.set_language(ACTIVE_LANG)
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

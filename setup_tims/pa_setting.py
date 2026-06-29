"""PA-setting screen (案内設定 / TIMS C07AA), reached from the home menu's 報站設定 (PA Setup)
card. Models the real TIMS 案内設定 register: a settings-summary table (route / train-type /
origin-terminal / …) plus a route-picker entry button and a confirm button. Renders the persistent
top band (shared with the home menu) so it reads as the same chrome. Staged for production
(setup_tims package); not yet wired into main.py — the run()→config launch bridge lands later.

Deltas from the real TIMS screen (tims-pa-setting.png):
  * the 6-car consist diagram + its 'A' consist button are REMOVED (we have no consist data)
    → replaced by a single 選擇路綫 (Select Route) button.
  * the 番線 (platform) button + 現在駅 (current-station) button are REMOVED (no platform model).

The 選擇路綫 button is the route → diagram → station picker entry (the 始発駅選択 flow,
tims-route-selection.jpg); 確認 commits the setting. Both are inert in this draft.

Preview:   uv run _dev_scripts/preview_setup_tims.py --screen pa   (L = cycle locale, ESC = quit)
Static:    uv run _dev_scripts/preview_setup_tims.py --screen pa --screenshot pa_setting.png
"""

import json
import os

import pygame

import i18n
from app_paths import project_root
from displays.train_models import DEFAULT_MODEL_KEY
from widgets import (
    _TUNEABLES_TIMS_BUTTON,
    draw_lowres_text_fat,
    draw_tims_button,
    lowres_text_size,
    press_transition,
)

from . import band, chrome

ACTIVE_LANG = "zh_HK"  # develop/preview in zh_HK (chrome is i18n; station/line names stay JP)

# fmt: off
# ── layout tuneables (all derived coords flow from these) ─────────────────────
SCREEN_W, SCREEN_H = band.SCREEN_W, band.SCREEN_H   # 730×610 — same own-window size as the home menu
BG_COLOR           = band.BG_COLOR                  # mirror the menu bg

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
TABLE_BG           = (8, 10, 14)          # near-black interior (TIMS table)
TABLE_BORDER       = (120, 132, 144)      # slate grid lines
TABLE_BORDER_W     = 1                    # thin INTERNAL grid lines (column / row dividers)
TABLE_BG_PAD       = 5                    # black background extends 5px OUTSIDE the table grid (all sides)
A_NATIVE           = 52                   # big consist letter px
A_XSCALE           = 1.4                  # 'A' uses the same x-stretched fat variant as the title
A_COLOR            = (236, 241, 246)      # white — same as the table text
PATTERN_NO_NATIVE  = 16                   # operation-No. "(00x)" px — shown UNDER the big A after a commit
PATTERN_NO_GAP     = 3                    # gap below the A's ink bottom to the (00x)
PATTERN_NO_COLOR   = (236, 241, 246)      # white — same as the A
ROW_LABEL_NATIVE   = 18                   # Japanese row labels px (+2 — fills the tight row)
ROW_LABEL_COLOR    = (236, 241, 246)
ROW_VALUE_NATIVE   = 20                   # Japanese values (station / line names) px
ROW_VALUE_COLOR    = (236, 241, 246)
CELL_PAD_X         = 2                    # text hugs the column line (1–2px gap)

CONFIRM_W          = 96                  # confirm width (1.2× the earlier 80)
CONFIRM_GAP_X      = 24                  # gap to the RIGHT of the table (confirm sits right of the table)
BTN_ROW_Y          = 392                 # SHARED y for 確認 + 列車型號 (a button row below the table); the coming
# OCR-choice buttons (自動放送始発起動 / 自動放送設定) reserve the area BELOW it
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# Chrome labels come from translations_app.json via i18n.t — keys setup_tims.action.pa_setup (title) /
# setup_tims.pa_setting.select_route / setup_tims.confirm.

# Summary-table row LABELS re-use the Japanese TIMS presentation (real TIMS renders these in Japanese):
# rows 1-3 mirror the reference, row 4 simplified to 月台 (no platform model), row 5 = 備考. Rendered in
# the JP face, locale-independent. VALUES are Japanese route/station names, EMPTY until a route is
# picked (item 5) — 選擇路綫 populates them from route.json.
ROW_LABELS = ["路線名", "列車種別", "始発・終着駅", "月台", "備注"]
ROW_VALUES = ["", "", "", "", ""]
PATTERN_NO = None  # run-pattern No. (字軌選擇) → shown as "(00x)" under the big A; None until a commit
_committed = None  # raw route_select.run_on result for the committed route — drives the 起動 launch config
_model_override = None  # last user-picked train model (列車型號 picker); session-persistent, overrides the route default


def _apply_selection(result):
    """Fill the summary-table VALUES from a route_select commit ({"route": <variant dict>, "start": <stop
    idx>}). Row 3 = CHOSEN start stop → route terminal (始発・終着駅); row 5 = the composed 備考 (direction
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


def _build_config(result):
    """Bridge a committed route_select result → a launch config shaped like setup.SetupScreen.run()
    (action / work_dir / route_data / model), MANUAL mode (auto_input False — OCR arming waits for the
    自動放送設定 page). `start_idx` = the chosen start stop resolved by NAME against the committed
    variant's own stops (variant-agnostic — variants can carry different stop lists; this closes the
    deferred v0-index finding). main.py jumps the sim to start_idx before run()."""
    route = result["route"]
    with open(os.path.join(route["path"], "route.json"), encoding="utf-8") as f:
        route_data = json.load(f)
    stops = route.get("stops", [])
    start_name = result.get("start_name") or ""
    start_idx = stops.index(start_name) if start_name in stops else 0
    return {
        "action": "select",
        "work_dir": route["path"],
        "route_data": route_data,
        "model": _model_override or route["model"],
        "auto_input": False,
        "start_idx": start_idx,
    }


# Button tuneable: JUSTIFY (両端揃え) — the label spreads across the full face with EQUAL outer margins
# + inter-char gaps (the TIMS look: a wide button's 2-char label gets equal space left / middle / right).
# v_pad=0 so justify uses the full face height (the box already holds its margin via BTN_MARGIN); AA-off.
_BTN_TUNEABLES = {**_TUNEABLES_TIMS_BUTTON, "text_align": "justify", "v_pad": 0, "text_max_k": 1, "line_gap": 3}


def _button_size(label, font):
    """Content-derived (w, h): box hugs the AA-off native label + BTN_MARGIN + bevel."""
    lw, lh = lowres_text_size(label, font, 1, _BTN_TUNEABLES["line_gap"])
    t = _BTN_TUNEABLES
    bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]
    return int(lw + 2 * BTN_MARGIN + bevel), int(lh + 2 * BTN_MARGIN + bevel)


def render(surf):
    """Draw the PA-setting page onto ``surf``; returns {"select"/"confirm": rect} hit-rects."""
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band._render_topband(surf)  # persistent black status band across the top

    # title row: screen-code + cyan heading (shared chrome recipe — bottom-aligned, x-stretched)
    chrome.title_row(surf, SCREEN_CODE, i18n.t("setup_tims.action.pa_setup"), ACTIVE_LANG)

    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)

    # ── table geometry first (so the select button can sit above the VISIBLE table = the dark bg) ──
    # Label column width DERIVES from the widest label (始発・終着駅, row 3) so column 2 hugs row 3's text.
    labels = ROW_LABELS
    n = len(labels)
    table_h = n * ROW_H
    label_font = i18n.pixel_font_for_lang("en", ROW_LABEL_NATIVE)  # "en"=NotoSansJP — Japanese labels
    value_font = i18n.pixel_font_for_lang("en", ROW_VALUE_NATIVE)  # "en"=NotoSansJP — Japanese values
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
        value = ROW_VALUES[i]
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

    # 確認 button — narrow, to the RIGHT of the visible table + dropped down (right-of + below, not under)
    conf_label = i18n.t("setup_tims.confirm")
    _, conf_h = _button_size(conf_label, btn_font)
    conf_rect = pygame.Rect(bg.right + CONFIRM_GAP_X, BTN_ROW_Y, CONFIRM_W, conf_h)
    draw_tims_button(surf, conf_rect, conf_label, font=btn_font, t=_BTN_TUNEABLES)

    # 列車型號 button — the IRL 番線 slot, repurposed: centered on the shared button row → opens the model
    # picker. Same y as 確認 (BTN_ROW_Y); the area below this row is reserved for the coming OCR-choice buttons.
    model_label = i18n.t("setup_tims.pa_setting.model")
    mw, mh = _button_size(model_label, btn_font)
    model_rect = pygame.Rect((SCREEN_W - mw) // 2, BTN_ROW_Y, mw, mh)
    draw_tims_button(surf, model_rect, model_label, font=btn_font, t=_BTN_TUNEABLES)

    return {"select": sel_rect, "confirm": conf_rect, "model": model_rect, "home": band_hits["home"]}


def run_on(screen):
    """Run the PA-setting page on an EXISTING display ``screen`` until the user launches or returns.
    Entry the home menu's 報站設定 card calls. Returns the LAUNCH CONFIG dict (action/work_dir/route_data/
    model/start_idx) when 確認/起動 is pressed with a route committed; None on band Home / ESC (back to the
    menu). Home/select/confirm get the shared TIMS press beat; Home adds the loading beat."""
    global _model_override
    clock = pygame.time.Clock()
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)
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
                elif hits["confirm"].collidepoint(event.pos):
                    # 確認 = manual launch (起動): once a route is committed, build the config + bubble it up.
                    press_transition(
                        screen,
                        rect=hits["confirm"],
                        label=i18n.t("setup_tims.confirm"),
                        font=btn_font,
                        t=_BTN_TUNEABLES,
                        redraw=lambda s: render(s),
                        blank_color=BG_COLOR,
                        blank_ms=0,
                    )
                    if _committed is not None:
                        return _build_config(_committed)
                elif hits["model"].collidepoint(event.pos):  # 列車型號 → model picker (X00AA)
                    press_transition(
                        screen,
                        rect=hits["model"],
                        label=i18n.t("setup_tims.pa_setting.model"),
                        font=btn_font,
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

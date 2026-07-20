"""TIMS selection-grid screens (route + start-station), variants of the general
始発駅選択 (C07AC) template (tims-route-selection-general style.png). Reached from the 案内設定
page's 選擇路綫 button:

    選擇路綫 → 路線選擇 (pick a route)  ──設定──▶  始發站選擇 (pick a start stop)  ──設定──▶  back to 案内設定

戻る chains back one level (station → route → 案内設定); the persistent band Home returns to the menu.

Both screens share ONE grid template: fat screen-code + green heading, a blue TIMS-button grid filled
COLUMN-major (down a column, then the next — as the real screen does), a 戻る button bottom-left and a
設定 button bottom-right. Each route box is loaded from audio/**/route.json (sampling
setup.SetupScreen.scan_routes); station boxes are the chosen route's stops.

NOTE — yellow selection: the shared press model (conventions.md § UI code style) reserves
yellow for the MOMENTARY press beat. This grid additionally uses yellow (the button "pressed" state) as
the PERSISTENT selected-box marker, because the reference screen does exactly that (the tan/yellow 川崎).
The momentary beat and the persistent selection share the colour by design here; 設定 going white-and-
flashing is the "a selection is ready to confirm" cue.

The default production route/start picker (reached from the 案内設定 page's 選擇路綫 button). Also previewed via the launcher below.

Preview:   uv run _dev_scripts/preview_setup_tims.py --screen route        (L = cycle locale, ESC = back/quit)
Static:    uv run _dev_scripts/preview_setup_tims.py --screen route --screenshot route_select.png
"""

import json
import math
import os

import pygame

import i18n
from app_paths import project_root
from displays.train_models import resolve_model_key
from widgets import (
    _TUNEABLES_TIMS_BUTTON,
    draw_lowres_text,
    draw_tims_button,
    lowres_text_size,
    press_transition,
    tims_button_size,
)

import status_band as band
import tims_chrome as chrome
from . import dims

ACTIVE_LANG = "zh_HK"  # develop/preview in zh_HK (chrome is i18n; route/station names stay Japanese)

# fmt: off
# ── layout tuneables (all derived coords flow from these) ─────────────────────
SCREEN_W, SCREEN_H = dims.SCREEN_W, dims.SCREEN_H   # 730×610 — same own-window size as the rest of the chrome
BG_COLOR           = dims.BG_COLOR                  # slate, mirror the menu / pa-setting bg

# title row (below the band): screen-code + cyan heading — drawn by chrome.title_row (shared recipe).

# button grid
GRID_X             = 48                   # grid left edge (reference is left-weighted, lots of empty right)
GRID_Y             = 142                  # grid top (just below the title row; nudged down)
COL_GAP            = 19                   # horizontal gap between columns
ROW_GAP            = 20                   # vertical gap between rows (roomier)
BOX_NATIVE         = 20                   # box label render px (JP face — route / station names)
ROWS_PER_COL       = 5                    # 5 items per column; column count = ceil(n / 5), filled column-major
                                          # (matches the reference: its first column holds exactly 5 stations).
MAX_COLS           = 4                    # clamp columns-per-page to this (overflow pages vertically via ▲/▼)
BOX_STD_CHARS      = 5                    # route boxes: fixed STANDARD width = this many full-width chars.
                                          # Names ≤ this render native; LONGER names squeeze horizontally to fit
                                          # (the text primitive's hx<1 hardening). Keeps every route box the same
                                          # width so 3 columns fit 730px regardless of name length. None = content-sized.
STATION_STD_CHARS  = 4                    # start-station boxes: standard width = 4 chars (2-char names → slots 1·3)

GRID_RIGHT_MARGIN  = 20                   # keep the grid this far off the right edge (drives columns-per-page)

# bottom bar — 返回 (back) bottom-left, 設定 (set/confirm) bottom-right, ▲/▼ page arrows LEFT of 設定
BAR_Y_FROM_BOTTOM  = 70                   # bar buttons' TOP sits this far up from the screen bottom
BACK_X             = 68                   # 返回 left edge (+20 — nudged right)
CONFIRM_RIGHT_PAD  = 48                   # gap from the screen right edge to the rightmost bar element
BTN_NATIVE         = 22                   # bar-button label render px
BAR_BTN_PAD_W      = 5                    # extra width added to 設定 beyond its content size
BACK_EXTRA_W       = 12                   # 返回 width = 設定 width + this (返回 a touch wider than 設定)
FLASH_MS           = 420                  # 設定 white-flash half-period (white ↔ blue) once a box is picked
ARROW_W            = 64                   # ▲/▼ page-button width (wider than tall; height tracks 設定)
ARROW_GAP          = 8                    # gap between the ▲ and ▼ page buttons
SET_ARROW_GAP      = 16                   # gap between the ▲/▼ page cluster and 設定 (arrows sit LEFT of 設定)
PAGE_IND_COLOR     = chrome.CODE_INK      # "1/2" page indicator (near-white, above the arrows)

# table-population: when 始發站選擇 commits, these row VALUES flow back to the 案内設定 summary table
# (whose LABELS are pa_setting.ROW_LABEL_KEYS — localized field.route/type/from_to/model/remark).
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# headings + codes per screen. Codes mirror the real TIMS register (C07AC is the photographed
# 始発駅選択; C07AB is a plausible sibling for route-selection — droppable, like pa_setting's C07AA).
SCREENS = {
    "route": {
        "code": "C07AB",
        "heading_key": "setup_tims.route_select.heading",
        "align": "slots",  # fixed-slot distribution: 3-char names spread to slots 1·3·5 of the 6-slot grid
        "std_chars": BOX_STD_CHARS,  # fixed-width boxes (long names squeeze) — names vary 3..13 chars
    },
    "station": {
        "code": "C07AC",
        "heading_key": "setup_tims.station_select.heading",
        "align": "slots",  # fixed 4-slot grid: 2-char station names land at slots 1·3 (gap capped at 1 slot)
        "std_chars": STATION_STD_CHARS,  # standard 4-char width; longer names (武蔵溝ノ口) squeeze to fit
    },
    # C07AF 運用パターン選択 — NOT a grid: a twin-table (No. | 列車種別 | 備考) run-pattern picker.
    "diagram": {
        "code": "C07AF",
        "heading_key": "setup_tims.diagram_select.heading",
    },
}

# Chrome labels (返回 / 設定 / column headers / recap labels) come from translations_app.json via i18n.t
# — keys setup_tims.back / .set / .col.{no,type,remark} / .hdr.{from_to,line}.
# NOTE: 案内設定 shortcut — the HIDDEN 報站設定 button (user: "no idea what that is for"). Restoring is a
# one-liner: re-add the draw in _render_diagram's bottom bar (left cluster, back_rect.right + GUIDE_GAP)
# with label=i18n.t("setup_tims.action.pa_setup"), the "guide" hit in _run_diagram, and the
# res3 == "guide" → return None branch in run_on.

# grid-box button tuneables — tighter padding than the default action button; AA-off native (k=1).
# `text_align` is overridden per screen (center for routes, justify for stations).
_BOX_T_BASE = {
    **_TUNEABLES_TIMS_BUTTON,
    "text_max_k": 1,
    "nominal_k": 1,
    "h_pad": 13,  # box width = content + 2·h_pad + bevel (−3 each side → 6px less wide)
    "v_pad": 12,  # box height = label + 2·v_pad + bevel (−2 each side → 4px less tall)
    "line_gap": 4,
    "min_w": 78,
}
# bar-button tuneables (返回 / 設定 / ▲▼) — justify spread; v_pad gives the bar buttons real height
# (v_pad=0 rendered them too short — height was just the label + bevel).
_BAR_T = chrome.BTN_BAR
# No.-cell select button (small blue square inside the table's No. column) — centered digit, k=1 native.
_NO_T = {**_TUNEABLES_TIMS_BUTTON, "text_align": "center", "text_pad": 0, "text_max_k": 1, "nominal_k": 1, "min_w": 0}

# fmt: off
# ── C07AF 運用パターン選択 (run-pattern / diagram) layout tuneables ───────────────
# black PANEL behind the recap box + tables (the table area is black, not slate — runs from just below
# the title down to the bottom bar). Title + bottom bar stay on the slate bg, like the other screens.
PANEL_COLOR        = chrome.PANEL_BG         # near-black (same as the status band)
PANEL_TOP          = 118                 # panel top — just below the title row
PANEL_BOTTOM_GAP   = 12                  # panel bottom sits this far ABOVE the bottom bar

# recap box (top): start・end + line name. Its two rows are MERGED (no horizontal divider) — left cell
# holds both labels stacked, right cell both values stacked.
HDR_X              = 16
HDR_Y              = 130                  # recap-box top (below the title row)
HDR_W              = int(0.70 * (SCREEN_W - 2 * HDR_X))  # recap box = 0.7 of content width, LEFT-aligned (tables below stay full width)
HDR_ROW_H          = 20                   # each recap row (tighter — rows 1 & 2 closer)
HDR_LABEL_PAD_R    = 4                     # gap from the row-name label text to the column-split line (hugs it, like 川崎 on the value side)
HDR_ARROW_PAD      = "　　"                # full-width padding flanking the → in start → end (wider gap)
HDR_NAME_LETTER_SP = 0.8                  # letter-spacing WITHIN a station name (fraction of a full-width advance)
HDR_NATIVE         = 18                   # recap text px
HDR_BORDER_COLOR   = chrome.GRID      # box border + divider
HDR_LABEL_COLOR    = (198, 208, 220)      # label ink (dimmer)
HDR_VALUE_COLOR    = chrome.INK      # value ink (bright)
HDR_PAD_X          = 4                    # recap label / value hug from the cell's left border (small gap)
HDR_PAD_Y          = 2                    # inner top/bottom padding (text ↔ horizontal borders); does NOT change inter-row spacing
HDR_VAL_PAD_X      = 4                     # start-station hugs the column-split line (small inset for the value side)

# twin pattern tables (No. | 列車種別 | 備考), side by side; filled COLUMN-MAJOR (left table fills
# first, then the right) — same fill order as the grid. With 1–2 variants only the left table fills.
TBL_Y              = 179                  # tables' top — 5px below the recap box (130 + 2·20 + 2·2 = 174)
TBL_MARGIN_X       = 16                   # table group left/right margin
TBL_GAP            = 5                    # gap between the two tables
TBL_HEADER_H       = 28                   # column-title row height
TBL_ROW_H          = 44                   # data row height
ROWS_PER_TABLE     = 5                    # 5 rows per table → 10 pattern slots (matches the reference)
COL_NO_W           = 46                   # No. column (holds the small blue select button)
COL_TYPE_W         = 108                  # 列車種別 (train-type) column
GRID_COLOR         = chrome.GRID      # table gridlines (light on slate)
TBL_HDR_TXT_COLOR  = (208, 218, 230)      # column-title ink
TBL_CELL_TXT_COLOR = chrome.INK      # cell ink (type / remarks)
TBL_NATIVE         = 18                   # table cell + column-header text px
TBL_REMARK_PAD_X   = 4                    # 備考 value left inset — hugs the column-split line (like 川崎 in the recap)
NO_BTN_INSET_X     = 3                    # No.-button inset within its cell (x) — small margin so the cell border shows
NO_BTN_INSET_Y     = 3                    # No.-button inset within its cell (y)
NO_NATIVE          = 18                   # No.-button digit px (smaller — the button grew)

GUIDE_GAP          = 14                   # gap between 戻る and the 案内設定 shortcut (bottom-left cluster)

# 備考 marquee — an overflowing remark slides CHAR-BY-CHAR (discrete TIMS steps, no smooth scroll):
# rests at the start (line+direction visible) → steps left one char at a time, revealing the through-
# service tail → rests at the end → steps back. Ping-pong.
MARQUEE_STEP_MS    = 460                  # ms held per one-character step
MARQUEE_DWELL_MS   = 1300                 # pause at each end (start shows direction; end shows the tail)
# fmt: on


def load_routes():
    """Scan audio/**/route.json → a list of route dicts (samples setup.SetupScreen.scan_routes, kept lean
    + dependency-free so the draft doesn't pull update_check / pygame display setup from setup.py).

    Each dict: path (route folder = work_dir) / name (line, e.g. 南武線) / diagram (4027F) / type (快速) /
    model (resolved train-model key) / dest / start / end / stops (names). path + model feed the launch bridge."""
    base = project_root() / "audio"
    routes = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith("_")]  # skip _mock/_joban/_archive… (not-shipped staging)
        if "route.json" not in files:
            continue
        try:
            with open(os.path.join(root, "route.json"), encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:  # malformed route.json — skip, surface in console (dev only)
            print(f"skip {root}: {e}")
            continue
        rel = os.path.relpath(root, base).split(os.sep)
        diagram = rel[-1] if len(rel) > 1 else d.get("diagram", "")
        stops_raw = d.get("stops", [])
        stops = [s.get("name", "").replace("\n", "") for s in stops_raw]
        # Stopping-station indices into `stops` — the train can START only at a station it halts at.
        # Passing stations omit pa/sta/time (DATA_FORMAT.md § Skipping Stations); a stop counts as a
        # halt if it has a time field, a non-empty pa, or an sta. The start grid uses these (no passers).
        stop_idxs = [i for i, s in enumerate(stops_raw) if ("time" in s) or s.get("pa") or s.get("sta")]
        routes.append(
            {
                "path": root,  # route folder → PASimulator work_dir (launch bridge)
                "name": d.get("route", "?"),
                "diagram": diagram,
                "type": d.get("type", ""),
                "model": resolve_model_key(d.get("model")),  # default train model for this route (route.json optional)
                "remarks": d.get("remarks") or {},  # 備考 kv: {direction, through, note} — composed for display by _compose_remark
                "dest": d.get("dest", "").replace("\n", ""),
                "start": stops[0] if stops else "",
                "end": stops[-1] if stops else "",
                "stops": stops,
                "stop_idxs": stop_idxs,
            }
        )
    routes.sort(key=lambda r: (r["name"], r["diagram"]))
    return routes


def grouped_routes(routes):
    """Group route.json variants by line NAME so the route grid shows each line exactly once.

    Multiple diagrams / train-types under one line (中央線快速 1654T + 916H, 京浜東北線 1275A + 727B, …)
    collapse to a single box here; choosing among the variants is deferred to the next screen
    (diagram / train-type selection). Returns ``[(name, [route dict, ...]), ...]`` in load order."""
    groups = []
    by_name = {}
    for r in routes:
        if r["name"] not in by_name:
            by_name[r["name"]] = []
            groups.append((r["name"], by_name[r["name"]]))
        by_name[r["name"]].append(r)
    return groups


def _grid_metrics(labels, box_font, t, std_chars=None):
    """Uniform (box_w, box_h) for the grid so every cell is the same size and columns line up.

    HEIGHT is always the max label footprint (2-line route labels → taller boxes than 1-line stations).
    WIDTH: if ``std_chars`` is set, a FIXED standard = that many full-width chars + padding (longer names
    squeeze horizontally via draw_lowres_text's hx<1 hardening); else the max content width."""
    if not labels:
        return 90, 44
    box_h = max(tims_button_size(lbl, box_font, t)[1] for lbl in labels)
    if std_chars:
        bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]
        box_w = int(std_chars * box_font.size("国")[0] + 2 * t["h_pad"] + bevel)  # 国 = a full-width advance
    else:
        box_w = max(tims_button_size(lbl, box_font, t)[0] for lbl in labels)
    return box_w, box_h


def _page_layout(box_w):
    """Columns that fit one page + items-per-page. Columns fill the usable width (left-weighted like the
    reference); each column holds ROWS_PER_COL items → per_page = cols × ROWS_PER_COL. Overflow pages
    vertically via the ▲/▼ arrows."""
    usable = SCREEN_W - GRID_X - GRID_RIGHT_MARGIN
    cols = max(1, int((usable + COL_GAP) // (box_w + COL_GAP)))
    cols = min(cols, MAX_COLS)  # clamp; overflow pages vertically
    return cols, cols * ROWS_PER_COL


def _cell_rect(local_i, box_w, box_h, x0):
    """Column-major placement of a page-LOCAL index from grid origin ``x0``: fills DOWN its column
    (ROWS_PER_COL items), then the next — the reference's order (a full first column, then the second)."""
    col, row = local_i // ROWS_PER_COL, local_i % ROWS_PER_COL
    x = x0 + col * (box_w + COL_GAP)
    y = GRID_Y + row * (box_h + ROW_GAP)
    return pygame.Rect(x, y, box_w, box_h)


def _draw_arrow(surf, rect, direction, *, enabled):
    """A square TIMS button + a chunky white BLOCK arrow (shaft + head) matching the TIMS arrow-pad style
    (tims-arrow-buttons.png) — vector-drawn (no font glyph, deployment-safe). Disabled (first page can't
    go up, last can't go down) → the SILVER inactive palette + a muted-gray arrow, like every other
    disabled TIMS button."""
    draw_tims_button(surf, rect, "", t=_BAR_T if enabled else {**_BAR_T, **chrome.DISABLED}, state="normal")
    fill = (240, 244, 248) if enabled else chrome.DISABLED["text_color"]  # white arrow on blue / muted-gray on silver
    edge = (18, 30, 46) if enabled else chrome.DISABLED["text_color"]  # crisp navy edge on blue; blends on silver
    cx, cy = rect.centerx, rect.centery
    ah = rect.height * 0.30  # arrow half-height
    aw = rect.width * 0.26  # arrowhead half-width
    sw = aw * 0.44  # shaft half-width
    hy = cy - ah + 2 * ah * 0.52  # head base = 52% down from the tip → head ~half, shaft ~half
    # up block arrow: tip · head corners · shaft sides (column-major polygon), mirrored for down
    pts = [(cx, cy - ah), (cx - aw, hy), (cx - sw, hy), (cx - sw, cy + ah), (cx + sw, cy + ah), (cx + sw, hy), (cx + aw, hy)]
    if direction == "down":
        pts = [(x, 2 * cy - y) for x, y in pts]
    ipts = [(round(x), round(y)) for x, y in pts]
    pygame.draw.polygon(surf, fill, ipts)
    pygame.draw.polygon(surf, edge, ipts, 1)  # thin dark outline for crispness on the blue face


def _render_grid(surf, screen_key, labels, box_font, box_w, box_h, *, selected_idx, flash_on, btn_font, page):
    """Draw ONE page of a selection-grid screen onto ``surf``; return hit-rects
    {"boxes":[(global_idx, rect)...], "back", "confirm", "up", "down", "home", "pages"}.

    selected_idx (global, or None) → if on this page that box draws yellow ("pressed", persistent). 設定
    flashes white ("waiting") ↔ blue once a box is selected. ▲/▼ appear only when pages > 1."""
    cfg = SCREENS[screen_key]
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(surf)  # persistent black status band across the top

    # title row: code + cyan heading (shared chrome recipe — bottom-aligned, x-stretched)
    chrome.title_row(surf, cfg["code"], i18n.t(cfg["heading_key"]), ACTIVE_LANG)

    # button grid — only this page's slice (column-major, ROWS_PER_COL items per column)
    box_t = {**_BOX_T_BASE, "text_align": cfg["align"], "text_slots": cfg["std_chars"]}
    cols_fit, per_page = _page_layout(box_w)
    pages = max(1, math.ceil(len(labels) / per_page))
    page = max(0, min(page, pages - 1))
    # centre the button group horizontally (equal margins both sides) on the columns a full page uses
    cols_used = min(cols_fit, max(1, math.ceil(len(labels) / ROWS_PER_COL)))
    grid_w = cols_used * box_w + (cols_used - 1) * COL_GAP
    x0 = max(GRID_X, (SCREEN_W - grid_w) // 2)
    box_rects = []
    for local_i in range(per_page):
        gi = page * per_page + local_i
        if gi >= len(labels):
            break
        r = _cell_rect(local_i, box_w, box_h, x0)
        state = "pressed" if gi == selected_idx else "normal"
        draw_tims_button(surf, r, labels[gi], font=box_font, t=box_t, state=state)
        box_rects.append((gi, r))

    # bottom bar — 返回 (back) left (+5px); 設定 (set) right-anchored (+5px); ▲/▼ page cluster LEFT of 設定
    bar_y = SCREEN_H - BAR_Y_FROM_BOTTOM
    _, bh = tims_button_size(i18n.t("setup_tims.back"), btn_font, _BAR_T)
    sw, sh = tims_button_size(i18n.t("setup_tims.set"), btn_font, _BAR_T)
    sw += BAR_BTN_PAD_W  # 設定: content + pad
    bw = sw + BACK_EXTRA_W  # shared bar-button width — 設定 matches 返回 (grouped = same size)
    back_rect = pygame.Rect(BACK_X, bar_y, bw, bh)
    draw_tims_button(surf, back_rect, i18n.t("setup_tims.back"), font=btn_font, t=_BAR_T, state="normal")

    # 設定 stays anchored at the right edge; the ▲/▼ cluster appears to its LEFT, only when paging
    conf_rect = pygame.Rect(SCREEN_W - CONFIRM_RIGHT_PAD - bw, bar_y, bw, sh)  # 設定 same width as 返回
    up_rect = down_rect = None
    if pages > 1:
        down_rect = pygame.Rect(conf_rect.x - SET_ARROW_GAP - ARROW_W, bar_y, ARROW_W, sh)
        up_rect = pygame.Rect(down_rect.x - ARROW_GAP - ARROW_W, bar_y, ARROW_W, sh)
        _draw_arrow(surf, up_rect, "up", enabled=page > 0)
        _draw_arrow(surf, down_rect, "down", enabled=page < pages - 1)
        # page indicator "p/N" centered over the arrow cluster, above it
        ind_font = i18n.pixel_font_for_lang("en", BTN_NATIVE - 4)
        ind = f"{page + 1}/{pages}"
        iw, ih = lowres_text_size(ind, ind_font, 1, 0)
        chrome.blit_lowres(surf, ind, (up_rect.x + down_rect.right - iw) // 2, bar_y - ih - 4, ind_font, PAGE_IND_COLOR, 1)

    conf_state = "waiting" if (selected_idx is not None and flash_on) else "normal"
    draw_tims_button(surf, conf_rect, i18n.t("setup_tims.set"), font=btn_font, t=_BAR_T, state=conf_state)

    return {"boxes": box_rects, "back": back_rect, "confirm": conf_rect, "up": up_rect, "down": down_rect, "home": band_hits["home"], "pages": pages}


def _run_grid(screen, screen_key, labels, *, preselect=None):
    """Run ONE selection-grid screen until the user backs out / confirms / goes Home.

    Returns: an int box index (设定 confirmed) · None (戻る / ESC — back one level) · "home" (band Home)."""
    global ACTIVE_LANG
    clock = pygame.time.Clock()
    box_font = i18n.pixel_font_for_lang("en", BOX_NATIVE)  # "en"=NotoSansJP — Japanese route/station names (locale-independent)
    box_t = {**_BOX_T_BASE, "text_align": SCREENS[screen_key]["align"], "text_slots": SCREENS[screen_key]["std_chars"]}
    box_w, box_h = _grid_metrics(labels, box_font, box_t, SCREENS[screen_key]["std_chars"])
    below_band = pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H)  # load-beat scope (band persists)
    selected = preselect
    _, per_page = _page_layout(box_w)
    page = preselect // per_page if preselect is not None else 0  # land on the page holding the preselection

    def frame(s):
        flash = (pygame.time.get_ticks() // FLASH_MS) % 2 == 0
        return _render_grid(s, screen_key, labels, box_font, box_w, box_h, selected_idx=selected, flash_on=flash, btn_font=btn_font, page=page)

    running = True
    while running:
        # localized chrome fonts (戻る / 設定 / Home) re-resolve each frame so the L-key locale cycle takes effect
        btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)
        home_font = i18n.pixel_font_for_lang(band.ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE)
        hits = frame(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))  # let an outer loop see it too
                return "home"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None  # back one level
            if event.type == pygame.KEYDOWN and event.key == pygame.K_l:  # dev: cycle locale (en / zh_HK / zh_CN)
                ACTIVE_LANG = _LANGS[(_LANGS.index(ACTIVE_LANG) + 1) % len(_LANGS)]
                band.ACTIVE_LANG = ACTIVE_LANG
                i18n.set_language(ACTIVE_LANG)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits["home"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=home_font,
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return "home"
                if hits["back"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["back"],
                        label=i18n.t("setup_tims.back"),
                        font=btn_font,
                        t=_BAR_T,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return None
                if selected is not None and hits["confirm"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["confirm"],
                        label=i18n.t("setup_tims.set"),
                        font=btn_font,
                        t=_BAR_T,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return selected
                if hits["up"] and hits["up"].collidepoint(event.pos) and page > 0:  # page up — press + load beat
                    press_transition(
                        screen,
                        rect=hits["up"],
                        label="",
                        font=btn_font,
                        t=_BAR_T,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    page -= 1
                    continue
                if hits["down"] and hits["down"].collidepoint(event.pos) and page < hits["pages"] - 1:
                    press_transition(
                        screen,
                        rect=hits["down"],
                        label="",
                        font=btn_font,
                        t=_BAR_T,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    page += 1
                    continue
                for gi, r in hits["boxes"]:
                    if r.collidepoint(event.pos):
                        # momentary press flash, then the box stays yellow (selected) on the next frame
                        press_transition(screen, rect=r, label=labels[gi], font=box_font, t=box_t, redraw=frame, blank_ms=0)
                        selected = gi
                        break
    return None


def _compose_remark(route_name, rem):
    """Compose the 備考 cell text from the kv block {direction, through, note}: line + direction FIRST
    (always shown — direction rests visible at the cell start), then the through-service tail and any
    note appended. When the whole string overflows the cell it ping-pong-slides (see _marquee_cell), so
    the appended tail is the part that scrolls into view. direction is nominal for circular lines."""
    if not isinstance(rem, dict):
        return ""
    direction, through, note = rem.get("direction", ""), rem.get("through", ""), rem.get("note", "")
    parts = [f"{route_name}{direction}"]
    if through:
        parts.append(f"{through}直通")
    if note:
        parts.append(note)
    return "　".join(parts)


def _cell_text(surf, text, font, color, cell, *, align="center"):
    """Blit one pixel-text string inside ``cell`` (a Rect), vertically centered. align: left / center /
    distribute (chars spread evenly across the cell with equal gaps incl. ends — the JR column-header look)."""
    if not text:
        return
    _, th = lowres_text_size(text, font, 1, 0)
    y = cell.y + (cell.h - th) // 2
    if align == "distribute" and len(text) > 1:
        widths = [font.size(ch)[0] for ch in text]
        gap = max(0.0, (cell.w - sum(widths)) / (len(text) + 1))  # n chars → n+1 equal gaps
        x = cell.x + gap
        for ch, w in zip(text, widths):
            chrome.blit_lowres(surf, ch, int(round(x)), y, font, color, 1)
            x += w + gap
        return
    if align == "left":
        chrome.blit_lowres(surf, text, cell.x + HDR_PAD_X, y, font, color, 1)
        return
    # center — via draw_lowres_text so an over-wide value (a 6–7 char 種別 like 快速アクティー) COMPRESSES
    # horizontally to fit the cell instead of spilling into the next column; short values render natural.
    draw_lowres_text(surf, text, cell, font, color, max_k=1, line_gap=0, align="center")


def _draw_from_to(surf, start, end, font, color, cell):
    """Recap 'start → end' value: each station name's chars are letter-spaced by HDR_NAME_LETTER_SP of a
    full-width advance (the JR spaced-name look); HDR_ARROW_PAD pads each side of the →, which is
    vertically centered on its OWN glyph height (kanji and → have different box heights)."""
    gap = HDR_NAME_LETTER_SP * font.size("国")[0]
    _, name_h = lowres_text_size(start, font, 1, 0)
    ny = cell.y + (cell.h - name_h) // 2  # station-name baseline row

    def spaced(name, x):
        for ch in name:
            chrome.blit_lowres(surf, ch, int(round(x)), ny, font, color, 1)
            x += font.size(ch)[0] + gap
        return x - gap  # strip the trailing gap after the last char

    pad_px = lowres_text_size(HDR_ARROW_PAD, font, 1, 0)[0]
    aw, ah = lowres_text_size("→", font, 1, 0)
    ax = spaced(start, cell.x + HDR_VAL_PAD_X) + pad_px
    chrome.blit_lowres(surf, "→", int(round(ax)), cell.y + (cell.h - ah) // 2, font, color, 1)  # arrow centered on its own height
    spaced(end, ax + aw + pad_px)


def _marquee_cell(surf, text, font, color, cell, *, t_ms):
    """Left-aligned remark in ``cell`` that ping-pong-slides CHAR-BY-CHAR when it overflows. Steps the
    window one character at a time (offsets land on glyph boundaries — discrete, no smooth scroll),
    dwelling at the start (direction visible) and the end (tail visible). Static when it already fits."""
    if not text:
        return
    pad = TBL_REMARK_PAD_X  # hug the column-split line on the left
    avail = cell.w - 2 * pad
    cum = [0]
    for ch in text:
        cum.append(cum[-1] + font.size(ch)[0])
    tw = cum[-1]
    _, th = lowres_text_size(text, font, 1, 0)
    x0, y = cell.x + pad, cell.y + (cell.h - th) // 2
    if tw <= avail:
        chrome.blit_lowres(surf, text, x0, y, font, color, 1)
        return
    max_off = tw - avail
    steps = [c for c in cum if c < max_off] + [max_off]  # one stop per char boundary, last shows the exact end
    seq = [(steps[0], MARQUEE_DWELL_MS)]
    seq += [(s, MARQUEE_STEP_MS) for s in steps[1:-1]]
    seq += [(steps[-1], MARQUEE_DWELL_MS)]
    seq += [(s, MARQUEE_STEP_MS) for s in reversed(steps[1:-1])]
    p = t_ms % sum(d for _, d in seq)
    off = steps[0]
    for o, d in seq:
        if p < d:
            off = o
            break
        p -= d
    prev = surf.get_clip()
    surf.set_clip(pygame.Rect(x0, cell.y, avail, cell.h))
    chrome.blit_lowres(surf, text, int(x0 - off), y, font, color, 1)
    surf.set_clip(prev)


def _render_diagram(surf, route_name, start_name, end_name, variants, *, selected_idx, flash_on, btn_font):
    """Draw the C07AF run-pattern (字軌選擇) picker: title + recap box + twin pattern tables + 3-button
    bar. The selectable element is the small blue No. button in each filled row (yellow when selected).

    Returns hits {"nos":[(variant_idx, btn_rect)...], "back", "guide", "confirm", "home"}."""
    cfg = SCREENS["diagram"]
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(surf)

    # title row — shared chrome recipe (fat code + cyan heading, bottom-aligned)
    chrome.title_row(surf, cfg["code"], i18n.t(cfg["heading_key"]), ACTIVE_LANG)

    # black panel behind the recap box + tables (slate only on the title row + bottom bar)
    panel = pygame.Rect(0, PANEL_TOP, SCREEN_W, (SCREEN_H - BAR_Y_FROM_BOTTOM - PANEL_BOTTOM_GAP) - PANEL_TOP)
    pygame.draw.rect(surf, PANEL_COLOR, panel)

    # recap box — 始發・終着站 | start → end  /  (路線名) | (line). Two rows MERGED (no row divider):
    # left cell = both labels stacked, right cell = both values stacked. Outer border + vertical divider only.
    lab_font = i18n.pixel_font_for_lang(ACTIVE_LANG, HDR_NATIVE)
    val_font = i18n.pixel_font_for_lang("en", HDR_NATIVE)  # "en"=NotoSansJP — names + → (locale-independent)
    box = pygame.Rect(HDR_X, HDR_Y, HDR_W, 2 * HDR_ROW_H + 2 * HDR_PAD_Y)
    pygame.draw.rect(surf, HDR_BORDER_COLOR, box, 1)
    # column-split hugs the WIDEST row-name label (+HDR_LABEL_PAD_R), mirroring how 川崎 hugs on the value side
    lab_w = max(
        lowres_text_size(i18n.t("setup_tims.hdr.from_to"), lab_font, 1, 0)[0], lowres_text_size(i18n.t("setup_tims.hdr.line"), lab_font, 1, 0)[0]
    )
    split_x = HDR_X + HDR_PAD_X + lab_w + HDR_LABEL_PAD_R
    lab_cell_w, val_cell_w = split_x - HDR_X, box.right - split_x
    pygame.draw.line(surf, HDR_BORDER_COLOR, (split_x, HDR_Y), (split_x, box.bottom), 1)
    # row 0 — 始發・終着站 | start → end (station-name chars letter-spaced). HDR_PAD_Y lifts the rows
    # off the top/bottom borders without touching the row-to-row spacing (still HDR_ROW_H apart).
    row0_y = HDR_Y + HDR_PAD_Y
    _cell_text(surf, i18n.t("setup_tims.hdr.from_to"), lab_font, HDR_LABEL_COLOR, pygame.Rect(HDR_X, row0_y, lab_cell_w, HDR_ROW_H), align="left")
    _draw_from_to(surf, start_name, end_name, val_font, HDR_VALUE_COLOR, pygame.Rect(split_x, row0_y, val_cell_w, HDR_ROW_H))
    # row 1 — (路線名) | (line). The (路線名) LABEL is centered in the label cell (per reference); the
    # line value stays left-aligned like the station row above it.
    ly1 = row0_y + HDR_ROW_H
    _cell_text(surf, i18n.t("setup_tims.hdr.line"), lab_font, HDR_LABEL_COLOR, pygame.Rect(HDR_X, ly1, lab_cell_w, HDR_ROW_H), align="center")
    _cell_text(surf, f"（{route_name}）", val_font, HDR_VALUE_COLOR, pygame.Rect(split_x, ly1, val_cell_w, HDR_ROW_H), align="left")

    # twin pattern tables — No. | 列車種別 | 備考, filled column-major (left table, then right)
    table_w = (SCREEN_W - 2 * TBL_MARGIN_X - TBL_GAP) // 2
    col_remark_w = table_w - COL_NO_W - COL_TYPE_W
    hdr_font = i18n.pixel_font_for_lang(ACTIVE_LANG, TBL_NATIVE)  # column titles (chrome)
    cell_font = i18n.pixel_font_for_lang("en", TBL_NATIVE)  # 列車種別 / 備考 values (Japanese)
    no_font = i18n.pixel_font_for_lang("en", NO_NATIVE)
    no_rects = []
    for ti in range(2):
        tx = TBL_MARGIN_X + ti * (table_w + TBL_GAP)
        tbl = pygame.Rect(tx, TBL_Y, table_w, TBL_HEADER_H + ROWS_PER_TABLE * TBL_ROW_H)
        cx1, cx2 = tx + COL_NO_W, tx + COL_NO_W + COL_TYPE_W
        pygame.draw.rect(surf, GRID_COLOR, tbl, 1)
        pygame.draw.line(surf, GRID_COLOR, (cx1, TBL_Y), (cx1, tbl.bottom), 1)
        pygame.draw.line(surf, GRID_COLOR, (cx2, TBL_Y), (cx2, tbl.bottom), 1)
        pygame.draw.line(surf, GRID_COLOR, (tx, TBL_Y + TBL_HEADER_H), (tbl.right, TBL_Y + TBL_HEADER_H), 1)
        for r in range(1, ROWS_PER_TABLE):
            ry = TBL_Y + TBL_HEADER_H + r * TBL_ROW_H
            pygame.draw.line(surf, GRID_COLOR, (tx, ry), (tbl.right, ry), 1)
        _cell_text(surf, i18n.t("setup_tims.col.no"), hdr_font, TBL_HDR_TXT_COLOR, pygame.Rect(tx, TBL_Y, COL_NO_W, TBL_HEADER_H))
        _cell_text(surf, i18n.t("setup_tims.col.type"), hdr_font, TBL_HDR_TXT_COLOR, pygame.Rect(cx1, TBL_Y, COL_TYPE_W, TBL_HEADER_H))
        _cell_text(
            surf,
            i18n.t("setup_tims.col.remark"),
            hdr_font,
            TBL_HDR_TXT_COLOR,
            pygame.Rect(cx2, TBL_Y, col_remark_w, TBL_HEADER_H),
            align="distribute",
        )
        for r in range(ROWS_PER_TABLE):
            gi = ti * ROWS_PER_TABLE + r
            if gi >= len(variants):
                continue
            v = variants[gi]
            ry = TBL_Y + TBL_HEADER_H + r * TBL_ROW_H
            no_rect = pygame.Rect(tx + NO_BTN_INSET_X, ry + NO_BTN_INSET_Y, COL_NO_W - 2 * NO_BTN_INSET_X, TBL_ROW_H - 2 * NO_BTN_INSET_Y)
            draw_tims_button(surf, no_rect, str(gi + 1), font=no_font, t=_NO_T, state="pressed" if gi == selected_idx else "normal")
            no_rects.append((gi, no_rect))
            vtype = v.get("type", "")
            # 2–3 char types (快速 / 各停) spread to fill the cell (the JR look); a 4+ char type (通勤快速
            # 特別快速 …) already fills it, so distributing reads as 'split' — cram it natural instead.
            _cell_text(
                surf,
                vtype,
                cell_font,
                TBL_CELL_TXT_COLOR,
                pygame.Rect(cx1, ry, COL_TYPE_W, TBL_ROW_H),
                align="center" if len(vtype) >= 4 else "distribute",
            )
            _marquee_cell(
                surf,
                _compose_remark(route_name, v.get("remarks")),
                cell_font,
                TBL_CELL_TXT_COLOR,
                pygame.Rect(cx2, ry, col_remark_w, TBL_ROW_H),
                t_ms=pygame.time.get_ticks(),
            )

    # bottom bar — 戻る left · 設定 right-anchored (flashes white when a No. is picked). The 案内設定
    # shortcut is HIDDEN for now (user: "no idea what that is for") — see the 案内設定-shortcut note up top.
    bar_y = SCREEN_H - BAR_Y_FROM_BOTTOM
    _, bh = tims_button_size(i18n.t("setup_tims.back"), btn_font, _BAR_T)
    sw, _ = tims_button_size(i18n.t("setup_tims.set"), btn_font, _BAR_T)
    sw += BAR_BTN_PAD_W
    bw = sw + BACK_EXTRA_W  # shared bar-button width — 設定 matches 返回 (grouped = same size)
    back_rect = pygame.Rect(BACK_X, bar_y, bw, bh)
    draw_tims_button(surf, back_rect, i18n.t("setup_tims.back"), font=btn_font, t=_BAR_T, state="normal")
    conf_rect = pygame.Rect(SCREEN_W - CONFIRM_RIGHT_PAD - bw, bar_y, bw, bh)  # 設定 same width as 返回
    conf_state = "waiting" if (selected_idx is not None and flash_on) else "normal"
    draw_tims_button(surf, conf_rect, i18n.t("setup_tims.set"), font=btn_font, t=_BAR_T, state=conf_state)

    return {"nos": no_rects, "back": back_rect, "confirm": conf_rect, "home": band_hits["home"]}


def _run_diagram(screen, route_name, start_name, end_name, variants, *, preselect=None):
    """Run the C07AF run-pattern picker. Returns: int variant index (設定 confirmed) · None (戻る — back
    to the station screen) · "guide" (案内設定 — jump to the PA-setting page) · "home" (band Home)."""
    global ACTIVE_LANG
    clock = pygame.time.Clock()
    below_band = pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H)
    selected = preselect
    # Single-diagram screen: pre-select the sole variant (renders yellow, arms 設定) so the user
    # confirms directly — no redundant box-click when there's only one choice.
    if selected is None and len(variants) == 1:
        selected = 0

    def frame(s):
        bf = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)
        flash = (pygame.time.get_ticks() // FLASH_MS) % 2 == 0
        return _render_diagram(s, route_name, start_name, end_name, variants, selected_idx=selected, flash_on=flash, btn_font=bf)

    while True:
        btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)
        home_font = i18n.pixel_font_for_lang(band.ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE)
        no_font = i18n.pixel_font_for_lang("en", NO_NATIVE)
        hits = frame(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return "home"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None  # back one level (→ station)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_l:
                ACTIVE_LANG = _LANGS[(_LANGS.index(ACTIVE_LANG) + 1) % len(_LANGS)]
                band.ACTIVE_LANG = ACTIVE_LANG
                i18n.set_language(ACTIVE_LANG)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits["home"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=home_font,
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return "home"
                if hits["back"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["back"],
                        label=i18n.t("setup_tims.back"),
                        font=btn_font,
                        t=_BAR_T,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return None
                if selected is not None and hits["confirm"].collidepoint(event.pos):
                    press_transition(
                        screen,
                        rect=hits["confirm"],
                        label=i18n.t("setup_tims.set"),
                        font=btn_font,
                        t=_BAR_T,
                        redraw=frame,
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=below_band,
                    )
                    return selected
                for gi, r in hits["nos"]:
                    if r.collidepoint(event.pos):
                        press_transition(screen, rect=r, label=str(gi + 1), font=no_font, t=_NO_T, redraw=frame, blank_ms=0)
                        selected = gi
                        break


def run_on(screen):
    """Drive the full route → start-station → run-pattern flow on an existing display ``screen``.

    Returns the chosen selection {"route": <variant dict>, "start": <stop index>} (committed via 設定 on
    the run-pattern screen), or None if the user backed/jumped out to the 案内設定 page, or "home" for a
    band-Home return to the menu. The 案内設定 page reads the return to populate its summary table."""
    groups = grouped_routes(load_routes())
    route_labels = [name for name, _ in groups]
    sel_route_idx = None
    while True:
        res = _run_grid(screen, "route", route_labels, preselect=sel_route_idx)
        if res == "home":
            return "home"
        if res is None:
            return None  # backed out to 案内設定
        sel_route_idx = res
        name, variants = groups[res]
        v0 = variants[0]  # station list comes from the first variant (draft: stations precede pattern)
        all_stops = v0["stops"]
        stop_idxs = v0["stop_idxs"]  # indices of STOPPING stations (passing stations excluded)
        station_labels = [all_stops[i] for i in stop_idxs]  # start grid shows stopping stations only
        end_name = v0["end"]
        sel_start = None  # filtered-space index into station_labels
        sel_var = None
        back_to_route = False
        while not back_to_route:
            res2 = _run_grid(screen, "station", station_labels, preselect=sel_start)
            if res2 == "home":
                return "home"
            if res2 is None:
                back_to_route = True  # 戻る → re-enter the route screen (picked route stays highlighted)
                break
            if res2 != sel_start:
                sel_var = None  # different start station → the diagram list changes; drop the stale pattern pick
            sel_start = res2
            start_name = station_labels[sel_start] if 0 <= sel_start < len(station_labels) else ""
            # C07AF shows ONLY diagrams (variants) that STOP at the chosen start station — a variant that
            # passes through / doesn't serve it is hidden. v0 always stops here (the station grid is built
            # from v0's stopping list), so ≥1 variant always remains.
            shown = [v for v in variants if start_name in (v["stops"][i] for i in v["stop_idxs"])]
            while True:
                pre = sel_var if (sel_var is not None and sel_var < len(shown)) else None
                res3 = _run_diagram(screen, name, start_name, end_name, shown, preselect=pre)
                if res3 == "home":
                    return "home"
                if res3 is None:
                    break  # 戻る → back to the station screen (start stays highlighted)
                sel_var = res3
                # Carry the RESOLVED start name (variant-agnostic). `start` stays the variants[0]-space
                # full index for the eventual launch bridge to re-resolve against the chosen variant —
                # variants can have different stop lists, so the index isn't trustworthy cross-variant.
                return {"route": shown[res3], "start": stop_idxs[sel_start], "start_name": start_name, "pattern_no": res3 + 1}


# ── standalone preview ────────────────────────────────────────────────────────
_LANGS = ("en", "zh_HK", "zh_CN")


def run_interactive():
    global ACTIVE_LANG
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("route / station selection (draft)")
    result = run_on(screen)
    print(f"selection → {result}")
    pygame.quit()


def save_screenshot(path):
    """Render all three screens (route grid → station grid → run-pattern table, all for 南武線) stacked
    into one tall PNG. The run-pattern 備考 column uses DRAFT sample text (route.json has no remarks yet)."""
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    groups = grouped_routes(load_routes())
    route_labels = [name for name, _ in groups]
    nambu = next((i for i, name in enumerate(route_labels) if name == "南武線"), 0)
    name, variants = groups[nambu]
    v0 = variants[0]
    station_labels = [v0["stops"][i] for i in v0["stop_idxs"]]  # stopping stations only (match run_on)
    box_font = i18n.pixel_font_for_lang("en", BOX_NATIVE)
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BTN_NATIVE)

    def one(screen_key, labels, selected, page=0):
        s = pygame.Surface((SCREEN_W, SCREEN_H))
        t = {**_BOX_T_BASE, "text_align": SCREENS[screen_key]["align"], "text_slots": SCREENS[screen_key]["std_chars"]}
        bw, bh = _grid_metrics(labels, box_font, t, SCREENS[screen_key]["std_chars"])
        _render_grid(s, screen_key, labels, box_font, bw, bh, selected_idx=selected, flash_on=True, btn_font=btn_font, page=page)
        return s

    s1 = one("route", route_labels, nambu)
    s2 = one("station", station_labels, 0)
    # run-pattern panel — real 備考 from route.json (remarks kv composed by _compose_remark)
    s3 = pygame.Surface((SCREEN_W, SCREEN_H))
    _render_diagram(s3, name, station_labels[0], v0["end"], variants, selected_idx=0, flash_on=True, btn_font=btn_font)

    out_surf = pygame.Surface((SCREEN_W, SCREEN_H * 3 + 16))
    out_surf.fill((18, 18, 22))
    for i, s in enumerate((s1, s2, s3)):
        out_surf.blit(s, (0, i * (SCREEN_H + 8)))
    out = str(project_root() / path)
    pygame.image.save(out_surf, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H * 3 + 16}; route / station / run-pattern)")

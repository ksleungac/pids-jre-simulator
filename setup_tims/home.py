"""Home menu — page 1 of the setup_tims flow. The first screen: a persistent OCR status
band across the top, four big action cards (報站設定 / 教學 / 設定 / 行車記錄), a bottom-right
language-knob row, and a bottom-left version tag (flashes a SAME-STYLE update hint when a
newer GitHub release exists).

報站設定 (leftmost card) enters the 案内設定 PA-setting page; 教學 opens the green TIMS
tutorial. The other two cards are inert placeholders for now.

The production entry that returns a launch-config dict lands in the manual-launch wiring
phase; for now ``run_interactive`` is the clickable preview (driven by
``_dev_scripts/preview_setup_tims.py``).
"""

import webbrowser

import pygame

import i18n
import update_check
from app_paths import project_root
from widgets import (
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

from . import band
from .band import BAND_H, BG_COLOR, SCREEN_H, SCREEN_W

# TIMS chrome face = Noto Sans, per-locale, AA-OFF at native px, NO upscale (WIP § Font decision).
# CHROME = big chrome labels (lang knobs / action cards / version). Resolved via i18n.pixel_font_for_lang.
CHROME_NATIVE = 22  # big chrome labels — render Noto AA-off at this px (<=40 envelope)

ACTIVE_LANG = "zh_HK"  # UI language shown — drives the pressed knob + big-button chrome


def pixel_font(lang):
    return i18n.pixel_font_for_lang(lang, CHROME_NATIVE)


# fmt: off
# ── page-1 layout tuneables (all derived coords flow from these) ──────────────
# language buttons (bottom-right corner, horizontal row). The box is CONTENT-SIZED to the 4-char CJK
# self-name (2x2) so the kanji pack tight with ZERO inter-char gap (box just-right, ~square). All
# three share that size (uniform knob row); EN sits in it as the short code, same multiplier.
LANG_K             = 1               # no upscale — AA-off native; box sizes to the native label
LANG_LINE_GAP      = 3               # small visual gap between the 2 rows (ink-based stacking now)
LANG_TEXT_MARGIN   = 6               # uniform gap between the tight text block and the bevel
LANG_GAP           = 8               # gap between buttons in the row
LANG_MARGIN_BOTTOM = 10             # lang knobs sit BOTTOM-right now (band owns the top-right)
LANG_MARGIN_RIGHT  = 10
LANG_SIZER         = "繁體\n中文"      # the label whose tight footprint sets the shared box size

# big action buttons (centered, side by side). Sized so 3–4 fit across (the eventual layout); labels
# render Noto AA-off at native px (k=1, no upscale), same crisp pixel look as the knobs.
BIG_W              = 145               # wide enough for single-line 4-char zh labels at k=2
BIG_H              = 280               # tall cards (>=2x height per request; text stays k=2)
BIG_GAP            = 0                 # buttons flush — no space between
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# (code, label) — full self-name (CJK wrapped 2x2); EN stays the short code. The font is resolved
# per code from its Noto Sans locale face (zh_HK = Traditional, zh_CN = Simplified, en = Latin).
LANGS = [
    ("en", "EN"),
    ("zh_HK", "繁體\n中文"),
    ("zh_CN", "简体\n中文"),
]

# Action-button tuneables: tight-centered label (no inter-char gap) held off the bevel by text_pad —
# same center mode as the knobs, just a bigger pad + the fill-to-fit k.
_ACTION_TUNEABLES = {**_TUNEABLES_TIMS_BUTTON, "text_align": "center", "text_pad": 12, "text_max_k": 1}

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

# Big-button chrome: ACTION_IDS = stable hit keys (only "route" + "tutorial" are wired; settings/record
# are inert placeholders). ACTION_KEYS parallels them — the i18n labels (translations_app.json). Leftmost
# card = 報站設定 (PA setup; the route → diagram → station flow), keyed "route" but labelled action.pa_setup.
ACTION_IDS = ["route", "tutorial", "settings", "record"]
ACTION_KEYS = [
    "setup_tims.action.pa_setup",
    "setup_tims.action.tutorial",
    "setup_tims.action.settings",
    "setup_tims.action.record",
]

# Version tag — i18n "Version" word + "054" bottom-left: no 'v', no dots, no colon. The numerals are
# drawn by draw_lowres_number (NOT full-width forms): each digit trimmed to ink + an explicit small
# gap, so they sit close like real TIMS. xscale widens them ("wider but not full width"); gap is the
# spacing knob, independent of width. VERSION is raw (production reads pyproject); shown dot-stripped.
VERSION = "0.5.4"
VERSION_K = 1  # no upscale — AA-off native
VERSION_DIGIT_XSCALE = 1.0  # natural ink width (Noto AA-off native; no stretch)
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
    # Number: draw to a temp, trim to its ink, vertical-center the ink against the word's ink band
    # (lh). draw_lowres_text now ink-centers the word; blitting the number at the raw font baseline
    # dropped it below the word — ink-centering both re-aligns them.
    nw, _ = lowres_number_size(digits, font, k=VERSION_K, xscale=VERSION_DIGIT_XSCALE, gap=VERSION_DIGIT_GAP)
    ntmp = pygame.Surface((max(1, nw + 2), font.get_height()), pygame.SRCALPHA)
    draw_lowres_number(ntmp, digits, (0, 0), font, text_color, k=VERSION_K, xscale=VERSION_DIGIT_XSCALE, gap=VERSION_DIGIT_GAP)
    nink = ntmp.get_bounding_rect()
    if nink.w:
        surf.blit(ntmp.subsurface(nink), (VERSION_X + lw, VERSION_Y + (lh - nink.height) // 2))


def render_menu(surf):
    """Draw page-1 menu onto ``surf``. Returns (action_rects, action_font, action_t, hint_rect,
    lang_rects): the big-button hit-rects keyed by ACTION_IDS, the font + tuneable they were drawn
    with (so a caller can redraw one in the pressed state for the press/transition beat), the
    flashing version-tag hit-rect (None when no newer release), and the language-knob hit-rects
    keyed by lang code."""
    surf.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG  # carry the UI language onto the shared band
    band._render_topband(surf)  # persistent black status band across the top

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
    actions = [i18n.t(k) for k in ACTION_KEYS]
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


def _launch_pa_setting():
    """Open the PA-setting page (案内設定) — same-size window — run it until the user returns (band Home /
    ESC) or launches (確認/起動). Returns the launch config dict on 起動, else None. Local import of the
    sibling screen — only needed on click, so it stays out of module-load (no top-level coupling)."""
    from . import pa_setting

    pa_setting.ACTIVE_LANG = ACTIVE_LANG  # carry the menu's UI language into the page
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("TIMS PA setting (draft)")
    return pa_setting.run_on(screen)


def run(screen):
    """Production menu loop on an EXISTING ``screen``. Returns a LAUNCH CONFIG dict when the user commits
    a route and 起動s in the PA-setting flow (bubbled up from pa_setting.run_on); None on quit / ESC. The
    caller owns the pygame lifecycle (does NOT pygame.quit() here — main.py hands off to PASimulator)."""
    global ACTIVE_LANG
    clock = pygame.time.Clock()
    action_rects, action_font, action_t, hint_rect, lang_rects = render_menu(screen)
    while True:
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None
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
                    is_nav = aid in ("tutorial", "route")  # Tutorial + 報站設定 navigate; others inert
                    # press beat (yellow) for every card; loading beat only for the navigational ones
                    press_transition(
                        screen,
                        rect=rect,
                        label=i18n.t(ACTION_KEYS[i]),
                        font=action_font,
                        t=action_t,
                        redraw=lambda s: render_menu(s),
                        blank_color=BG_COLOR,
                        # the OCR band (top strip) is persistent chrome — exclude it from the load beat
                        blank_rect=pygame.Rect(0, BAND_H, SCREEN_W, SCREEN_H - BAND_H),
                        blank_ms=450 if is_nav else 0,
                    )
                    if is_nav:
                        if aid == "route":
                            cfg = _launch_pa_setting()
                            if isinstance(cfg, dict):
                                return cfg  # 起動 committed → bubble the launch config up to main.py
                        else:
                            _launch_tutorial()
                        # the sub-screen owned the display — restore the menu window + caption.
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                        pygame.display.set_caption("TIMS home menu")
                    break
        action_rects, action_font, action_t, hint_rect, lang_rects = render_menu(screen)
        pygame.display.flip()


def run_interactive():
    """Dev preview wrapper: init pygame + the own-window, run the menu loop, print the launch config it
    returns. Production goes through ``run(screen)`` (main.py owns the window + the PASimulator hand-off)."""
    global ACTIVE_LANG
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("TIMS home menu (draft)")
    cfg = run(screen)
    print(f"launch config → {cfg}")
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

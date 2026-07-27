"""OCR auto-PA consent + settings screen (自動放送設定), TIMS-styled. Ported from setup.py's
`_draw_ocr_disclaimer_panel` + the lead/interval steppers, reskinned to TIMS chrome (band on top,
near-black panel, Noto AA-off text, bevel buttons).

Two views:
  * CONSENT — scrollable how-it-works + terms, with a SCROLL-TO-ACCEPT gate (設定 stays grayed until
    the panel is scrolled to the bottom). Shown ONCE as a LAUNCH-time gate the first time the user
    launches via OCR (自動放送始発起動); acceptance persists in settings.json ("ocr_consent"). Opening
    OCR settings (自動放送設定) goes DIRECT to SETTINGS — no gate. Afterwards the how-it-works view is
    read-only from the home Tutorials button.
  * SETTINGS — lead-distance / interval steppers, backed by settings.json (lead_m / interval_s).

Gate helper `ensure_consent(screen)` is what the pa-setting OCR buttons call.

The how-it-works flow strip is animated (cycling digit templates, moving train, pulsing PgDn key),
mirroring the legacy flow's motion.

Preview:  uv run _dev_scripts/preview_setup_tims.py --screen consent   (scroll wheel / drag; ESC quit)
          uv run _dev_scripts/preview_setup_tims.py --screen ocrset
"""

import math
import random

import pygame

import i18n
from app_paths import project_root
from ..widgets import draw_lowres_number, draw_tims_button, lowres_text_size, press_transition, tims_button_size

from .. import band
from .. import chrome
from . import dims

ACTIVE_LANG = "zh_HK"  # develop/preview in zh_HK (chrome is i18n)
OK_KEY = "setup.ocr_disclaimer.accept"  # accept button label key; 2-char justify-split like other pages' 返回/設定

# fmt: off
# ── layout tuneables ──────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = dims.SCREEN_W, dims.SCREEN_H
BG_COLOR           = dims.BG_COLOR

CONSENT_CODE       = "C07AG"              # screen code (placeholder — droppable / correct to real TIMS)
SETTINGS_CODE      = "C07AH"

PANEL_X            = 24                    # scrollable panel inset from the window edges
PANEL_TOP_GAP      = 6                     # gap below the title row to the panel top
FOOTER_H           = 60                    # settings-view footer band (steppers back button)
FOOTER_MARGIN      = 18                    # consent: EQUAL gap panel→footer-button AND button→screen-bottom
CONTENT_PAD        = 16                    # inner padding of the scroll content
COL_GAP            = 16                    # gap between the intro text column and the screenshot
LEFT_COL_W         = 300                   # intro-text column width (rest = screenshot)
DIAG_MAX_H         = 190                   # screenshot max height

TITLE_NATIVE       = 20                    # section-heading px (larger than body so headings read as headings)
BODY_NATIVE        = 17                    # body text px (kanji hold well AA-off)
CAP_NATIVE         = 15                    # caption / flow-label px
FOOT_NATIVE        = 20                    # footer button px (matches other pages' 2-char bar buttons)
LINE_GAP_PX        = 4                     # extra px between wrapped body lines

INK                = chrome.INK            # bright white body ink (was (232,238,245) drift → canonical)
HEADING_INK        = chrome.CYAN           # section headings = the one TIMS cyan (was a stray (150,205,235))
AMBER              = chrome.AMBER          # resolution / caution note
DIM                = chrome.DIM            # captions
PANEL_BG           = chrome.PANEL_BG       # near-black interior (was (10,13,18) drift → canonical (8,10,14))
PANEL_BORDER       = chrome.FRAME          # slate frame
FLOW_BOX_BG        = (26, 32, 44)          # flow-step box fill (one-off — stays local)
FLOW_ARROW         = chrome.GRID           # arrow (was (150,164,178) drift → canonical light-slate)

STEP_X             = 90                    # settings steppers: label left x
STEP_VALUE_NATIVE  = 26                    # stepper value px (fat TIMS numerals)
STEP_ROW_GAP       = 22                    # vertical gap between stepper rows
# ──────────────────────────────────────────────────────────────────────────────
# fmt: on

# Reused verbatim from the legacy panel — the same i18n keys + bundled images (data/disclaimer/).
_IMG_CACHE = {}


def _load(path):
    """Load + cache an image by absolute path once (no .convert — keeps headless preview working)."""
    key = str(path)
    if key not in _IMG_CACHE:
        try:
            _IMG_CACHE[key] = pygame.image.load(key) if path.exists() else None
        except Exception:
            _IMG_CACHE[key] = None
    return _IMG_CACHE[key]


def _img(name):
    """A bundled disclaimer image (data/disclaimer/<name>)."""
    return _load(project_root() / "data" / "disclaimer" / name)


_WRAP_CACHE = {}  # (font, max_w, text) -> [line, ...]; see _wrap
_WRAP_CACHE_MAX = 512  # inputs are a fixed string set x 3 locales; the cap is a runaway backstop


def _wrap(text, font, max_w):
    """Greedy pixel wrap (CJK char-by-char; blank line preserved). Caller owns the paragraph split.

    A Latin run backtracks to its last space so a word is never cut mid-run ("Windo / ws"),
    while CJK keeps breaking at the column edge — the same rule the classic panel's wrap_text
    uses. A single Latin word wider than the column still hard-breaks rather than overflowing.

    MEMOIZED. The consent view rebuilds its whole body every frame, and this loop measures
    `font.size()` once per CHARACTER — 1737 calls per build, 48% of the frame cost, all of it
    re-deriving identical breaks (#60). The result depends only on (text, font, max_w), so it is
    cached on exactly those. The font object IS the key, which both keys per-locale correctly and
    holds a reference so its id can never be reused by a later font. Callers must treat the
    returned list as read-only — it is the cached instance, not a copy.
    """
    key = (font, max_w, text)
    cached = _WRAP_CACHE.get(key)
    if cached is not None:
        return cached

    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if font.size(cur + ch)[0] <= max_w or not cur:
                cur += ch
                continue
            if ch == " ":
                lines.append(cur)
                cur = ""
                continue
            sp = cur.rfind(" ")
            tail = cur[sp + 1 :] if sp >= 0 else ""
            # Backtrack only when the carried tail is Latin: a CJK continuation has no word
            # boundary worth preserving, and moving it would just ragged the column for nothing.
            if sp > 0 and tail and ord(tail[0]) < 0x3000:
                lines.append(cur[:sp])
                cur = tail + ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)

    if len(_WRAP_CACHE) >= _WRAP_CACHE_MAX:
        _WRAP_CACHE.clear()
    _WRAP_CACHE[key] = lines
    return lines


# ── consent view ───────────────────────────────────────────────────────────────
_DIGIT_KEYS = ["0", "1", "2", "8", "9"]  # cycled digit templates for the 'match' flow step

# Scratch height for the scrollable body. NOT a measured bound — headroom over the tallest real
# locale, which is en at 912px (zh_HK 870, zh_CN 849). Kept generous because the body grows with
# every locale edit; _build_content warns if a body ever outgrows it (a silent clip otherwise).
_CONTENT_H_MAX = 2600
# One reusable scratch per panel width. The body is rebuilt every frame, so allocating 1.8M pixels
# per frame was pure churn — the surface is fully repainted by the fill below, never read stale.
# Safe because _build_content has exactly one caller (render_consent) which blits before returning.
_CONTENT_SCRATCH = {}  # w -> Surface


def _build_content(w):
    """Render the whole scrollable consent/tutorial body onto a tall surface; return (surf, content_h).
    The visible slice is blitted by render_consent — this keeps draw_lowres_text's own clip from
    fighting the scroll region. FULL tutorial (ported from setup.py _draw_ocr_disclaimer_panel): the
    how-it-works two-column, the animated 4-step pipeline flow strip, the trigger-timings journey
    diagram, and the terms."""
    heading_font = i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE)
    body_font = i18n.pixel_font_for_lang(ACTIVE_LANG, BODY_NATIVE)
    cap_font = i18n.pixel_font_for_lang(ACTIVE_LANG, CAP_NATIVE)
    body_lh = lowres_text_size("永", body_font, 1, 0)[1]

    surf = _CONTENT_SCRATCH.get(w)
    if surf is None:
        surf = _CONTENT_SCRATCH[w] = pygame.Surface((w, _CONTENT_H_MAX))
    surf.fill(PANEL_BG)
    x = CONTENT_PAD
    y = CONTENT_PAD

    def heading(key):
        nonlocal y
        chrome.blit_lowres(surf, i18n.t(key), x, y, heading_font, HEADING_INK, 1)
        y += lowres_text_size("永", heading_font, 1, 0)[1] + 10

    def paragraph(key, color=INK, max_w=None, indent=0):
        nonlocal y
        mw = max_w if max_w is not None else (w - 2 * CONTENT_PAD - indent)
        for line in _wrap(i18n.t(key), body_font, mw):
            if line:
                chrome.blit_lowres(surf, line, x + indent, y, body_font, color, 1)
            y += body_lh + LINE_GAP_PX

    def bullets(key, color=INK):
        nonlocal y
        for para in i18n.t(key).split("\n"):
            if not para:
                continue
            wrapped = _wrap(para, body_font, w - 2 * CONTENT_PAD - body_font.size("· ")[0])
            for j, line in enumerate(wrapped):
                chrome.blit_lowres(surf, ("· " if j == 0 else "  ") + line, x, y, body_font, color, 1)
                y += body_lh + LINE_GAP_PX
            y += 4

    # 功能說明 — intro text (left) + game screenshot (right) with pulsing HUD box
    heading("setup.ocr_disclaimer.how_it_works_heading")
    top_y = y
    right_x = x + LEFT_COL_W + COL_GAP
    right_w = w - CONTENT_PAD - right_x
    paragraph("setup.ocr_disclaimer.intro", max_w=LEFT_COL_W)
    y += 6
    # Two support tiers, mirroring hud_layout's `verified` flag: AMBER = the resolutions a live
    # drive has actually run on (PROFILES entries), DIM = every other 16:9 at 1080p or above,
    # whose geometry is interpolated from the ratio and expected-but-unproven.
    paragraph("setup.ocr_disclaimer.resolution", color=AMBER, max_w=LEFT_COL_W)
    paragraph("setup.ocr_disclaimer.resolution_extended", color=DIM, max_w=LEFT_COL_W)
    y += 8
    # Hybrid-GPU note. DIM, not amber: the lines above state whether the feature applies to your
    # machine at all; this one is the recovery step for the machines where it applies but capture
    # is blocked (issue #97 — DDA refuses when the process runs on the discrete GPU of a Microsoft
    # Hybrid system, and no adapter we can address from inside the process changes that).
    paragraph("setup.ocr_disclaimer.dual_gpu", color=DIM, max_w=LEFT_COL_W)
    text_bottom = y

    shot = _img("game_screenshot.png")
    img_bottom = top_y
    if shot is not None:
        rw, rh = shot.get_size()
        sc = min(right_w / rw, DIAG_MAX_H / rh)
        ss = pygame.transform.smoothscale(shot, (int(rw * sc), int(rh * sc)))
        ix = right_x + (right_w - ss.get_width()) // 2
        surf.blit(ss, (ix, top_y))
        pygame.draw.rect(surf, PANEL_BORDER, pygame.Rect(ix, top_y, ss.get_width(), ss.get_height()), 1)
        # pulsing amber HUD highlight (the cell the OCR reads)
        sc_w, sc_h = ss.get_size()
        hx = ix + int(sc_w * 0.78)
        hw = sc_w - int(sc_w * 0.78)
        hh = int(sc_h * 0.48)
        phase = (pygame.time.get_ticks() % 1500) / 1500
        halpha = int(math.sin(phase * math.pi) * 210)
        hud = pygame.Surface((hw, hh), pygame.SRCALPHA)
        hud.fill((*AMBER, halpha))
        pygame.draw.rect(hud, (255, 210, 80, min(255, halpha + 50)), pygame.Rect(0, 0, hw, hh), 2)
        surf.blit(hud, (hx, top_y))
        img_bottom = top_y + sc_h

    y = max(text_bottom, img_bottom) + 8
    cap = i18n.t("setup.ocr_disclaimer.capture_interval", n=_interval_s)
    chrome.blit_lowres(surf, cap, right_x, y, cap_font, DIM, 1)
    y += lowres_text_size("永", cap_font, 1, 0)[1] + 18

    # 動作原理 — animated 4-step pipeline flow strip (capture → match → deduce → fire)
    heading("setup.ocr_disclaimer.mechanism_heading")
    y = _draw_flow(surf, w, y, cap_font)

    # 起動タイミング — trigger-timings journey diagram (backdrop + animated train + dep/appr/arr markers)
    heading("setup.ocr_disclaimer.journey_heading")
    y = _draw_journey(surf, w, y, cap_font)

    # misfire caveat — belongs with the firing behavior the diagram shows
    paragraph("setup.ocr_disclaimer.beta", color=DIM)
    y += 12
    pygame.draw.line(surf, PANEL_BORDER, (x, y), (w - CONTENT_PAD, y))
    y += 14

    # 使用條款 — terms / consent / privacy (bulleted)
    heading("setup.ocr_disclaimer.terms_heading")
    bullets("setup.ocr_disclaimer.consent")
    y += 2
    bullets("setup.ocr_disclaimer.privacy")
    y += 4 + CONTENT_PAD  # bottom padding — the scroll-to-accept hint moved OUT of the scroll box (see render_consent)

    if y > _CONTENT_H_MAX:  # body outgrew the scratch: the tail is silently clipped, so say so
        print(f"[ocr_setting] consent body is {y}px, over the {_CONTENT_H_MAX}px scratch — raise _CONTENT_H_MAX")
    return surf, y


def _draw_flow(surf, w, y, cap_font):
    """The 4-step OCR pipeline flow strip (capture / match / deduce / fire). Each box hosts a live
    visual: [0] the HUD crop the OCR reads, [1] the distance cell + cycling digit templates (the scan),
    [2] the v×t→d formula, [3] the animated PgDn key. Ported from setup.py's flowchart; illustration
    primitives verbatim, text via the TIMS pixel face. Returns the new y cursor."""
    pad = CONTENT_PAD
    chart_w = w - 2 * pad
    arrow_w = 18
    n = 4
    step_w = (chart_w - (n - 1) * arrow_w) // n
    flow_h = 68
    inner = 5
    flow_keys = ["capture", "match", "deduce", "fire"]
    shot = _img("game_screenshot.png")
    hud_sample = _img("hud_sample.png")

    for i in range(n):
        sx = pad + i * (step_w + arrow_w)
        box = pygame.Rect(sx, y, step_w, flow_h)
        pygame.draw.rect(surf, FLOW_BOX_BG, box, border_radius=5)
        pygame.draw.rect(surf, PANEL_BORDER, box, 1, border_radius=5)
        cw, ch = step_w - 2 * inner, flow_h - 2 * inner

        if i == 0 and shot is not None:
            rw, rh = shot.get_size()
            hud = shot.subsurface(pygame.Rect(int(rw * 0.78), 0, rw - int(rw * 0.78), int(rh * 0.48)))
            hw, hh = hud.get_size()
            sc = min(cw / hw, ch / hh)
            scaled = pygame.transform.smoothscale(hud, (int(hw * sc), int(hh * sc)))
            surf.blit(scaled, (sx + inner + (cw - scaled.get_width()) // 2, y + inner + (ch - scaled.get_height()) // 2))

        elif i == 1:
            # Left: real distance-cell crop. Right: digit templates cycle to show the scan.
            dist_img = None
            if hud_sample is not None:
                ow, oh = hud_sample.get_size()
                ds = min((cw * 0.55) / ow, (ch - 8) / oh)
                dist_img = pygame.transform.smoothscale(hud_sample, (max(1, int(ow * ds)), max(1, int(oh * ds))))
            vx = sx + inner + 4
            if dist_img is not None:
                surf.blit(dist_img, (vx, y + inner + (ch - dist_img.get_height()) // 2))
                vw_used, target_th = dist_img.get_width(), dist_img.get_height()
            else:
                vw_used, target_th = 0, ch - 8
            digits = [(d, _load(project_root() / "ocr_templates" / "digits" / f"{d}.png")) for d in _DIGIT_KEYS]
            digits = [(d, im) for d, im in digits if im is not None]
            if digits:
                dlbl, tpl = digits[(pygame.time.get_ticks() // 350) % len(digits)]
                ow, oh = tpl.get_size()
                tw = max(1, int(ow * target_th / oh))
                scaled_d = pygame.transform.scale(tpl, (tw, target_th))
                rx_start = vx + vw_used + 10
                tx = rx_start + max(0, ((sx + step_w - inner) - rx_start - tw) // 2)
                ty = y + inner + (ch - target_th) // 2
                if dlbl in "855":  # digits visible in the bundled screenshot's cell → highlight the match
                    pygame.draw.rect(surf, AMBER, pygame.Rect(tx - 3, ty - 3, tw + 6, target_th + 6), 2, border_radius=3)
                surf.blit(scaled_d, (tx, ty))

        elif i == 2:
            # v × t → d  (→ drawn as a vector arrow — the pixel face tofus U+2192; × is Latin-1, renders)
            f3 = i18n.pixel_font_for_lang(ACTIVE_LANG, 20)
            lw, th = lowres_text_size("v × t", f3, 1, 0)
            rw = lowres_text_size("d", f3, 1, 0)[0]
            arr_gap = 24
            lx = box.centerx - (lw + arr_gap + rw) // 2
            cy = box.centery
            chrome.blit_lowres(surf, "v × t", lx, cy - th // 2, f3, INK, 1)
            ax0, ax1 = lx + lw + 5, lx + lw + arr_gap - 4
            pygame.draw.line(surf, INK, (ax0, cy), (ax1 - 2, cy), 3)
            pygame.draw.polygon(surf, INK, [(ax1 - 5, cy - 5), (ax1 + 1, cy), (ax1 - 5, cy + 5)])
            chrome.blit_lowres(surf, "d", lx + lw + arr_gap, cy - th // 2, f3, INK, 1)

        elif i == 3:
            # Animated PgDn key: cap slides down over a fixed shadow face on press
            key_w, cap_h, shadow_h = 56, 28, 5
            t_norm = (pygame.time.get_ticks() % 2000) / 2000
            if t_norm < 0.10:
                press = t_norm / 0.10
            elif t_norm < 0.50:
                press = 1.0
            elif t_norm < 0.65:
                press = 1.0 - (t_norm - 0.50) / 0.15
            else:
                press = 0.0
            kx = box.centerx - key_w // 2
            ky = box.centery - (cap_h + shadow_h) // 2
            cap_y = ky + int(press * shadow_h)
            pygame.draw.rect(surf, (32, 36, 48), pygame.Rect(kx, ky + cap_h, key_w, shadow_h), border_radius=4)
            pygame.draw.rect(surf, (75, 82, 100), pygame.Rect(kx, cap_y, key_w, cap_h), border_radius=5)
            pygame.draw.rect(surf, (95, 103, 124), pygame.Rect(kx + 2, cap_y + 2, key_w - 4, 3), border_radius=2)
            pygame.draw.rect(surf, PANEL_BORDER, pygame.Rect(kx, cap_y, key_w, cap_h), 1, border_radius=5)
            kf = i18n.pixel_font_for_lang("en", CAP_NATIVE)
            klw, klh = lowres_text_size("PgDn", kf, 1, 0)
            chrome.blit_lowres(surf, "PgDn", kx + (key_w - klw) // 2, cap_y + (cap_h - klh) // 2, kf, INK, 1)

        # label below box
        lbl = i18n.t(f"setup.ocr_disclaimer.flow.{flow_keys[i]}")
        lw2 = lowres_text_size(lbl, cap_font, 1, 0)[0]
        chrome.blit_lowres(surf, lbl, box.centerx - lw2 // 2, y + flow_h + 4, cap_font, DIM, 1)

        if i < n - 1:  # connector arrow between boxes
            cy = y + flow_h // 2
            ax, ahead = sx + step_w + 3, sx + step_w + arrow_w - 3
            pygame.draw.line(surf, DIM, (ax, cy), (ahead - 2, cy), 2)
            pygame.draw.polygon(surf, DIM, [(ahead - 4, cy - 3), (ahead, cy), (ahead - 4, cy + 3)])

    return y + flow_h + 4 + lowres_text_size("永", cap_font, 1, 0)[1] + 16


def _draw_journey(surf, w, y, cap_font):
    """Trigger-timings journey diagram: a flat daytime backdrop (Mt. Fuji / skyline / Skytree / Tokyo
    Tower / classic + modern stations), a railway, an animated Suica train running A→B, and the three
    trigger markers (departure / approach / arrival) glowing as the train passes. Illustration
    primitives ported verbatim from setup.py; the badge + trigger text routes through the TIMS pixel
    face. Returns the new y cursor."""
    pad = CONTENT_PAD
    sw = w
    j_x0 = pad + 44
    j_x1 = sw - pad - 44
    jw = j_x1 - j_x0
    track_y = y + 84

    dep_frac, appr_frac = 0.30, 0.70
    dep_x = int(j_x0 + jw * dep_frac)
    appr_x = int(j_x0 + jw * appr_frac)
    arr_x = j_x1

    _RAIL_HI = (238, 242, 250)
    _RAIL = (196, 202, 214)
    _RAIL_DK = (128, 134, 148)
    _SLP = (150, 112, 78)
    _SLP_HI = (176, 136, 96)
    _BALLAST = (120, 120, 126)
    _DEP = (82, 196, 118)
    _APPR = (230, 178, 58)
    _ARR = (98, 164, 228)
    rail_top = rail_bot = horizon = track_y

    def _ipts(pts):
        return [(int(px), int(py)) for px, py in pts]

    # ── Backdrop, far → near ─────────────────────────────────────────────────
    def draw_fuji(cx, base, h=40, hw=72):
        pygame.draw.polygon(
            surf,
            (124, 148, 196),
            _ipts(
                [
                    (cx - hw, base),
                    (cx - hw * 0.2, base - h * 0.9),
                    (cx - 7, base - h),
                    (cx + 7, base - h),
                    (cx + hw * 0.2, base - h * 0.9),
                    (cx + hw, base),
                ]
            ),
        )
        pygame.draw.polygon(
            surf,
            (240, 244, 252),
            _ipts(
                [
                    (cx - 7, base - h),
                    (cx + 7, base - h),
                    (cx + 13, base - h * 0.74),
                    (cx + 6, base - h * 0.78),
                    (cx + 1, base - h * 0.73),
                    (cx - 4, base - h * 0.79),
                    (cx - 9, base - h * 0.74),
                    (cx - 13, base - h * 0.74),
                ]
            ),
        )

    _BLD_TONES = [(150, 162, 188), (188, 158, 168), (146, 188, 190), (192, 180, 150), (164, 172, 200), (200, 168, 150)]

    def draw_skyline(x0, x1, seed):
        rng = random.Random(seed)  # deterministic per span (no flicker)
        bx = x0
        while bx < x1:
            bw = rng.randint(8, 16)
            bh = rng.randint(10, 24)
            top = horizon - bh
            tone = rng.choice(_BLD_TONES)
            pygame.draw.rect(surf, tone, pygame.Rect(bx, top, bw, bh))
            pygame.draw.rect(surf, tuple(min(255, c + 26) for c in tone), pygame.Rect(bx, top, 2, bh))
            glass = tuple(max(0, c - 48) for c in tone)
            for wy in range(top + 3, horizon - 2, 5):
                for wx in range(bx + 3, bx + bw - 2, 4):
                    pygame.draw.rect(surf, glass, pygame.Rect(wx, wy, 1, 2))
            bx += bw + rng.randint(1, 4)

    def draw_skytree(cx, base, h=52):
        col = (196, 214, 234)
        pygame.draw.polygon(
            surf,
            col,
            _ipts(
                [
                    (cx - 4, base),
                    (cx - 1.5, base - h * 0.5),
                    (cx - 1.2, base - h * 0.84),
                    (cx + 1.2, base - h * 0.84),
                    (cx + 1.5, base - h * 0.5),
                    (cx + 4, base),
                ]
            ),
        )
        pygame.draw.ellipse(surf, col, pygame.Rect(int(cx - 5), int(base - h * 0.60), 10, 5))
        pygame.draw.ellipse(surf, col, pygame.Rect(int(cx - 3), int(base - h * 0.74), 6, 4))
        pygame.draw.line(surf, col, (cx, int(base - h * 0.84)), (cx, int(base - h)), 1)

    def draw_tower(cx, base, h=46):
        col, white, dk, ant = (228, 118, 80), (244, 234, 224), (180, 86, 58), (210, 212, 218)
        yb = lambda f: int(base - h * f)  # noqa: E731
        pygame.draw.polygon(surf, col, _ipts([(cx - 11, base), (cx - 4, base - h * 0.34), (cx + 4, base - h * 0.34), (cx + 11, base)]))
        pygame.draw.line(surf, dk, (cx - 11, base), (cx + 4, yb(0.34)), 1)
        pygame.draw.line(surf, dk, (cx + 11, base), (cx - 4, yb(0.34)), 1)
        pygame.draw.line(surf, white, (cx - 8, yb(0.12)), (cx + 8, yb(0.12)), 1)
        pygame.draw.line(surf, white, (cx - 5, yb(0.25)), (cx + 5, yb(0.25)), 1)
        pygame.draw.rect(surf, col, pygame.Rect(int(cx - 7), yb(0.45), 14, 4))
        pygame.draw.rect(surf, white, pygame.Rect(int(cx - 7), yb(0.45), 14, 1))
        for wx in range(int(cx - 5), int(cx + 5), 3):
            pygame.draw.rect(surf, dk, pygame.Rect(wx, yb(0.45) + 2, 1, 2))
        pygame.draw.polygon(
            surf, col, _ipts([(cx - 4, base - h * 0.45), (cx - 2, base - h * 0.72), (cx + 2, base - h * 0.72), (cx + 4, base - h * 0.45)])
        )
        pygame.draw.line(surf, dk, (cx, yb(0.45)), (cx, yb(0.72)), 1)
        pygame.draw.line(surf, white, (cx - 3, yb(0.56)), (cx + 3, yb(0.56)), 1)
        pygame.draw.rect(surf, col, pygame.Rect(int(cx - 3), yb(0.74), 6, 2))
        pygame.draw.rect(surf, white, pygame.Rect(int(cx - 3), yb(0.74), 6, 1))
        pygame.draw.line(surf, ant, (cx, yb(0.76)), (cx, base - h), 1)

    def draw_station_classic(sx):
        brick, brick_dk, brick_sh = (182, 96, 80), (150, 74, 62), (130, 62, 52)
        brick_hi, band_c, band_sh = (202, 112, 94), (240, 236, 226), (206, 200, 188)
        slate, slate_hi, slate_dk = (84, 106, 138), (132, 156, 188), (52, 70, 98)
        clockc, arch, glassw, finial = (38, 42, 52), (44, 36, 36), (150, 172, 196), (238, 234, 224)
        bw, bh = 80, 26
        body = pygame.Rect(sx - bw // 2, horizon - bh, bw, bh)
        pygame.draw.rect(surf, brick_dk, body)
        lt = pygame.Rect(body.x, body.y, 16, bh)
        rt = pygame.Rect(body.right - 16, body.y, 16, bh)
        cp = pygame.Rect(sx - 12, body.y, 24, bh)
        for col in (lt, cp, rt):
            pygame.draw.rect(surf, brick, col)
            pygame.draw.line(surf, brick_hi, (col.x, col.y), (col.x, horizon - 1), 1)
        pygame.draw.rect(surf, brick_sh, pygame.Rect(lt.right, body.y, 2, bh))
        pygame.draw.rect(surf, brick_sh, pygame.Rect(cp.right, body.y, 2, bh))
        for by in range(body.y + 5, horizon - 2, 5):
            pygame.draw.rect(surf, band_sh, pygame.Rect(body.x, by, bw, 2))
            for col in (lt, cp, rt):
                pygame.draw.rect(surf, band_c, pygame.Rect(col.x, by, col.width, 2))
        for ry in range(body.y + 6, horizon - 8, 5):
            for wx in range(body.x + 7, body.right - 6, 7):
                pygame.draw.rect(surf, glassw, pygame.Rect(wx, ry, 2, 3))
        pygame.draw.rect(surf, band_sh, pygame.Rect(body.x, horizon - 7, bw, 1))
        for ax in range(body.x + 6, body.right - 6, 9):
            pygame.draw.rect(surf, arch, pygame.Rect(ax, horizon - 6, 5, 6), border_top_left_radius=2, border_top_right_radius=2)
        roof = pygame.Rect(body.x + 10, body.y - 4, bw - 20, 4)
        pygame.draw.polygon(surf, slate_dk, _ipts([(roof.x, roof.y), (roof.right, roof.y), (roof.right - 4, roof.y - 3), (roof.x + 4, roof.y - 3)]))
        pygame.draw.rect(surf, slate, roof)
        pygame.draw.line(surf, slate_hi, (roof.x, roof.y), (roof.right, roof.y), 1)
        for dxm in range(roof.x + 5, roof.right - 4, 9):
            pygame.draw.rect(surf, slate, pygame.Rect(dxm, roof.y - 2, 3, 2))
            pygame.draw.rect(surf, glassw, pygame.Rect(dxm, roof.y - 1, 3, 1))
        pygame.draw.rect(surf, band_c, pygame.Rect(body.x, body.y - 4, 3, bh + 4))
        pygame.draw.rect(surf, band_sh, pygame.Rect(body.right - 3, body.y - 4, 3, bh + 4))
        plum, plum_hi, plum_dk = (120, 86, 106), (152, 118, 138), (84, 58, 76)

        def _turret(dcx):
            base_y = horizon - bh - 6
            pygame.draw.rect(surf, brick, pygame.Rect(dcx - 8, base_y, 16, 6))
            pygame.draw.line(surf, brick_hi, (dcx - 8, base_y), (dcx - 8, base_y + 6), 1)
            pygame.draw.rect(surf, band_c, pygame.Rect(dcx - 8, base_y, 16, 1))
            pygame.draw.rect(surf, plum_dk, pygame.Rect(dcx - 9, base_y - 1, 18, 1))
            pygame.draw.polygon(surf, plum, _ipts([(dcx - 8, base_y - 1), (dcx - 3, base_y - 6), (dcx + 3, base_y - 6), (dcx + 8, base_y - 1)]))
            pygame.draw.polygon(surf, plum_dk, _ipts([(dcx + 3, base_y - 6), (dcx + 8, base_y - 1), (dcx, base_y - 1), (dcx, base_y - 6)]))
            pygame.draw.polygon(surf, plum, _ipts([(dcx - 3, base_y - 6), (dcx, base_y - 11), (dcx + 3, base_y - 6)]))
            pygame.draw.polygon(surf, plum_dk, _ipts([(dcx, base_y - 11), (dcx + 3, base_y - 6), (dcx, base_y - 6)]))
            pygame.draw.line(surf, plum_hi, (dcx, base_y - 10), (dcx, base_y - 6), 1)
            pygame.draw.line(surf, finial, (dcx, base_y - 11), (dcx, base_y - 17), 1)
            pygame.draw.circle(surf, finial, (dcx, base_y - 18), 1)

        _turret(sx - bw // 2 + 8)
        _turret(sx + bw // 2 - 8)
        cp_y = horizon - bh - 5
        pygame.draw.rect(surf, brick, pygame.Rect(sx - 11, cp_y, 22, 5))
        pygame.draw.rect(surf, band_c, pygame.Rect(sx - 11, cp_y, 22, 1))
        pygame.draw.polygon(surf, slate, _ipts([(sx - 12, cp_y), (sx, cp_y - 9), (sx + 12, cp_y)]))
        pygame.draw.polygon(surf, slate_dk, _ipts([(sx, cp_y - 9), (sx + 12, cp_y), (sx, cp_y)]))
        pygame.draw.circle(surf, band_c, (sx, cp_y - 3), 3)
        pygame.draw.circle(surf, clockc, (sx, cp_y - 3), 3, 1)
        pygame.draw.rect(surf, slate, pygame.Rect(sx - 3, cp_y - 13, 6, 4))
        pygame.draw.rect(surf, slate_dk, pygame.Rect(sx, cp_y - 13, 3, 4))
        pygame.draw.rect(surf, band_c, pygame.Rect(sx - 3, cp_y - 13, 6, 1))
        pygame.draw.line(surf, finial, (sx, cp_y - 13), (sx, cp_y - 17), 1)
        pygame.draw.circle(surf, finial, (sx, cp_y - 18), 1)

    def draw_station_modern(sx):
        wall, wall_hi, glass = (206, 210, 218), (230, 233, 239), (120, 166, 206)
        arch_d = (52, 56, 70)
        canopy, canopy_hi, post = (160, 202, 216), (222, 238, 244), (116, 124, 136)
        sign_w, sign_jr, clockc = (242, 244, 250), (40, 132, 92), (38, 42, 52)
        bw, bh = 66, 24
        body = pygame.Rect(sx - bw // 2, horizon - bh, bw, bh)
        pygame.draw.rect(surf, wall, body)
        pygame.draw.rect(surf, wall_hi, pygame.Rect(body.x, body.y, bw, 2))
        pygame.draw.rect(surf, glass, pygame.Rect(body.x + 3, body.y + 4, bw - 6, 6))
        for gx in range(body.x + 5, body.right - 4, 6):
            pygame.draw.line(surf, wall_hi, (gx, body.y + 4), (gx, body.y + 10), 1)
        for ax in range(body.x + 4, body.right - 6, 10):
            pygame.draw.rect(surf, arch_d, pygame.Rect(ax, horizon - 10, 7, 10), border_top_left_radius=3, border_top_right_radius=3)
        pygame.draw.circle(surf, sign_w, (sx, body.y + 6), 2)
        pygame.draw.circle(surf, clockc, (sx, body.y + 6), 2, 1)
        cap_y = horizon - bh - 10
        for px in (sx - 22, sx, sx + 22):
            pygame.draw.line(surf, post, (px, cap_y + 3), (px, horizon - bh), 1)
        pygame.draw.polygon(
            surf,
            canopy,
            _ipts(
                [
                    (sx - 32, horizon - bh - 2),
                    (sx - 14, cap_y),
                    (sx + 14, cap_y),
                    (sx + 32, horizon - bh - 2),
                    (sx + 32, horizon - bh - 4),
                    (sx + 14, cap_y - 2),
                    (sx - 14, cap_y - 2),
                    (sx - 32, horizon - bh - 4),
                ]
            ),
        )
        pygame.draw.line(surf, canopy_hi, (sx - 14, cap_y - 1), (sx + 14, cap_y - 1), 1)
        sgx = sx - bw // 2 - 7
        pygame.draw.line(surf, post, (sgx, horizon), (sgx, horizon - 10), 1)
        sign = pygame.Rect(sgx - 7, horizon - 15, 16, 6)
        pygame.draw.rect(surf, sign_w, sign)
        pygame.draw.rect(surf, sign_jr, pygame.Rect(sign.x, sign.bottom - 2, 16, 2))

    draw_fuji(j_x0 + int(jw * 0.30), horizon)
    draw_skyline(j_x0 + int(jw * 0.10), j_x0 + int(jw * 0.42), 1207)
    draw_skyline(j_x0 + int(jw * 0.58), j_x0 + int(jw * 0.88), 5530)
    draw_skytree(j_x0 + int(jw * 0.48), horizon)
    draw_tower(j_x0 + int(jw * 0.66), horizon)
    draw_station_classic(j_x0)
    draw_station_modern(j_x1)

    # ── Railway ──────────────────────────────────────────────────────────────
    rail_x0, rail_x1 = pad, sw - pad
    pygame.draw.rect(surf, _BALLAST, pygame.Rect(rail_x0, track_y + 1, rail_x1 - rail_x0, 5), border_radius=1)
    for slx in range(rail_x0 + 6, rail_x1, 13):
        pygame.draw.rect(surf, _SLP, pygame.Rect(slx - 1, track_y + 1, 4, 5))
        pygame.draw.rect(surf, _SLP_HI, pygame.Rect(slx - 1, track_y + 1, 4, 1))
    pygame.draw.line(surf, _RAIL_DK, (rail_x0, track_y + 1), (rail_x1, track_y + 1), 1)
    pygame.draw.line(surf, _RAIL, (rail_x0, track_y), (rail_x1, track_y), 2)
    pygame.draw.line(surf, _RAIL_HI, (rail_x0, track_y - 1), (rail_x1, track_y - 1), 1)

    # ── Train motion: forward-only A → B, fade out at B, fade back in at A ─────
    period = 7000
    tt = (pygame.time.get_ticks() % period) / period
    travel_end, fadeout_end, fadein_start = 0.70, 0.80, 0.90
    if tt < travel_end:
        train_frac, train_alpha = tt / travel_end, 255
    elif tt < fadeout_end:
        train_frac, train_alpha = 1.0, int(255 * (1 - (tt - travel_end) / (fadeout_end - travel_end)))
    elif tt < fadein_start:
        train_frac, train_alpha = 0.0, 0
    else:
        train_frac, train_alpha = 0.0, int(255 * (tt - fadein_start) / (1 - fadein_start))
    train_x = int(j_x0 + train_frac * jw)

    # ── Station name badges (A / B) below the rail ────────────────────────────
    def draw_station_badge(bx, accent, letter):
        bi_w, bi_h = lowres_text_size(letter, cap_font, 1, 0)
        bw = bi_w + 12
        badge = pygame.Rect(bx - bw // 2, track_y + 13, bw, 16)
        pygame.draw.rect(surf, (54, 60, 74), badge, border_radius=4)
        pygame.draw.rect(surf, accent, badge, width=1, border_radius=4)
        chrome.blit_lowres(surf, letter, bx - bi_w // 2, badge.centery - bi_h // 2, cap_font, (236, 242, 250), 1)
        return badge.bottom

    stn_bottom = draw_station_badge(j_x0, (140, 148, 162), i18n.t("setup.ocr_disclaimer.journey.station_a"))
    draw_station_badge(j_x1, _ARR, i18n.t("setup.ocr_disclaimer.journey.station_b"))

    # ── Trigger markers + labels + pass-glow ──────────────────────────────────
    label_top_y = y + 2
    _trigger_defs = [
        (dep_x, _DEP, "setup.ocr_disclaimer.journey.departure", ">30 km/h"),
        (appr_x, _APPR, "setup.ocr_disclaimer.journey.approach", f"~{_lead_m} m"),
        (arr_x, _ARR, "setup.ocr_disclaimer.journey.arrival", None),
    ]
    for tx, col, key, cond in _trigger_defs:
        glow = max(0.0, 1.0 - abs(train_x - tx) / 44.0) * (train_alpha / 255.0)
        mark_y = rail_top
        if glow > 0:
            ring_r = int(7 + (1 - glow) * 12)
            halo = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(halo, (*col, int(glow * 150)), (ring_r + 2, ring_r + 2), ring_r, 2)
            pygame.draw.circle(halo, (*col, int(glow * 90)), (ring_r + 2, ring_r + 2), max(1, ring_r - 5))
            surf.blit(halo, (tx - ring_r - 2, mark_y - ring_r - 2))
        lbl_col = tuple(min(255, int(c + glow * (255 - c))) for c in col)
        lbl = i18n.t(key)
        lw, lh = lowres_text_size(lbl, cap_font, 1, 0)
        lbl_x = min(tx - lw // 2, sw - pad - lw)
        chrome.blit_lowres(surf, lbl, lbl_x, label_top_y, cap_font, lbl_col, 1)
        ann_btm = label_top_y + lh
        if cond:
            cw2, ch2 = lowres_text_size(cond, cap_font, 1, 0)
            ci_x = min(tx - cw2 // 2, sw - pad - cw2)
            chrome.blit_lowres(surf, cond, ci_x, ann_btm + 1, cap_font, DIM, 1)
            ann_btm += 1 + ch2
        if tx != arr_x:
            tgt_y = mark_y - 8
            if tgt_y > ann_btm + 2:
                pygame.draw.line(surf, col, (tx, ann_btm + 1), (tx, tgt_y), 1)
            dot_r = 5 + int(glow * 2)
            pygame.draw.circle(surf, col, (tx, mark_y), dot_r)
            pygame.draw.circle(surf, (42, 46, 58), (tx, mark_y), dot_r - 2)

    # ── Animated train (drawn last so it rides over the markers) ──────────────
    train = _load(project_root() / "data" / "disclaimer" / "suica_train.png")
    if train is not None and train_alpha > 0:
        rw, rh = train.get_size()
        tr = pygame.transform.smoothscale(train, (max(1, int(rw * 48 / rh)), 48))
        if train_alpha < 255:
            tr = tr.copy()
            tr.set_alpha(train_alpha)
        surf.blit(tr, (train_x - tr.get_width() // 2, rail_bot - tr.get_height()))
    elif train is None:
        pygame.draw.rect(surf, (205, 210, 215), pygame.Rect(train_x - 24, rail_bot - 18, 48, 18), border_radius=2)

    return stn_bottom + 14


_FOOT_T = {**chrome.BTN_BAR, "v_pad": 9}  # bottom-bar 2-char; v_pad trimmed 14→9 (FOOT_NATIVE 20 made it too tall)
# 設定(accept) locked state — silver/grey palette (per conventions: grey = palette, not a scrim) until
# the user scrolls to the bottom. Once ready it FLASHES (normal↔waiting) to hint "you can proceed".
_FOOT_T_GREY = {**_FOOT_T, **chrome.DISABLED}  # canonical silver (was a darker private grey; unified to chrome.DISABLED)


def render_consent(screen, scroll_y, read_only=False):
    """Draw the consent view; return (cancel_rect, ok_rect, max_scroll, ok_ready). In read_only mode
    (from Tutorials) the footer shows a single 返回 and there's no accept gate."""
    screen.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(screen)
    chrome.title_row(screen, CONSENT_CODE, i18n.t("setup.ocr_disclaimer.title"), ACTIVE_LANG)

    # Footer button height drives the panel bottom, so the gap panel→button and button→screen-bottom
    # are EQUAL (FOOTER_MARGIN each) — a balanced bottom regardless of the button's height.
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE)
    foot_h = tims_button_size(i18n.t(OK_KEY), btn_font, _FOOT_T)[1]
    fy = SCREEN_H - FOOTER_MARGIN - foot_h  # footer button TOP
    panel_top = band.BAND_H + 40 + PANEL_TOP_GAP  # title row ≈ 40px under the band
    panel = pygame.Rect(PANEL_X, panel_top, SCREEN_W - 2 * PANEL_X, (fy - FOOTER_MARGIN) - panel_top)
    pygame.draw.rect(screen, PANEL_BG, panel)
    pygame.draw.rect(screen, PANEL_BORDER, panel, 1)

    content, content_h = _build_content(panel.w)
    max_scroll = max(0, content_h - panel.h)
    scroll_y = max(0, min(scroll_y, max_scroll))
    slice_h = min(panel.h, content_h - scroll_y)
    screen.blit(content.subsurface(pygame.Rect(0, scroll_y, panel.w, slice_h)), (panel.x, panel.y))

    if max_scroll > 0:  # scrollbar
        track = pygame.Rect(panel.right - 5, panel.y, 4, panel.h)
        pygame.draw.rect(screen, (40, 48, 60), track)
        kh = max(20, int(panel.h * panel.h / content_h))
        ky = panel.y + int((panel.h - kh) * scroll_y / max_scroll)
        pygame.draw.rect(screen, PANEL_BORDER, pygame.Rect(track.x, ky, 4, kh))

    # footer buttons — content-sized, justify-split (matches other pages' 2-char bar buttons); fy set above
    ok_ready = scroll_y >= max_scroll
    if read_only:
        bw = tims_button_size(i18n.t("setup_tims.back"), btn_font, _FOOT_T)[0]
        back_rect = pygame.Rect(SCREEN_W - PANEL_X - bw, fy, bw, foot_h)
        draw_tims_button(screen, back_rect, i18n.t("setup_tims.back"), font=btn_font, t=_FOOT_T)
        return band_hits, None, back_rect, max_scroll, True
    ow, oh = tims_button_size(i18n.t(OK_KEY), btn_font, _FOOT_T)
    cw, ch = tims_button_size(i18n.t("setup.ocr_disclaimer.cancel"), btn_font, _FOOT_T)
    ok_rect = pygame.Rect(SCREEN_W - PANEL_X - ow, fy, ow, oh)
    cancel_rect = pygame.Rect(ok_rect.left - 10 - cw, fy, cw, ch)  # both hug the right (IRL 取消/設定 pair)
    draw_tims_button(screen, cancel_rect, i18n.t("setup.ocr_disclaimer.cancel"), font=btn_font, t=_FOOT_T)
    if not ok_ready:  # scroll-to-accept hint — OUTSIDE the scroll box (footer-left), always visible while the OK gate is locked
        hint_font = i18n.pixel_font_for_lang(ACTIVE_LANG, CAP_NATIVE)
        hint = i18n.t("setup.ocr_disclaimer.scroll_hint")
        hh = lowres_text_size(hint, hint_font, 1, 0)[1]
        chrome.blit_lowres(screen, hint, PANEL_X, fy + (foot_h - hh) // 2, hint_font, AMBER, 1)
    if ok_ready:  # reached the bottom → flash lit↔normal to hint the user can proceed
        lit = (pygame.time.get_ticks() // 450) % 2 == 0
        draw_tims_button(screen, ok_rect, i18n.t(OK_KEY), font=btn_font, t=_FOOT_T, state="waiting" if lit else "normal")
    else:  # locked → grey palette until scrolled to bottom
        draw_tims_button(screen, ok_rect, i18n.t(OK_KEY), font=btn_font, t=_FOOT_T_GREY)
    return band_hits, cancel_rect, ok_rect, max_scroll, ok_ready


def run_consent(screen, read_only=False):
    """Run the consent view. Returns True if accepted (or read_only OK-closed), "home" if the band Home
    button was pressed (caller bubbles the return all the way to the home menu), False if cancelled/ESC."""
    _load_state()  # reflect the user's persisted interval/lead in the how-it-works flow + journey (else stale defaults)
    clock = pygame.time.Clock()
    scroll_y = 0
    while True:
        band_hits, cancel_rect, ok_rect, max_scroll, ok_ready = render_consent(screen, scroll_y, read_only)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            elif event.type == pygame.MOUSEWHEEL:
                scroll_y = max(0, min(scroll_y - event.y * 40, max_scroll))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if band_hits["home"].collidepoint(event.pos):  # band Home → press + load beat → bubble home
                    press_transition(
                        screen,
                        rect=band_hits["home"],
                        label=i18n.t("setup_tims.band.home"),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, band.BAND_BTN_TEXT_NATIVE),
                        t=band._BAND_BTN_TUNEABLES,
                        redraw=lambda s: render_consent(s, scroll_y, read_only),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    return "home"
                if read_only and ok_rect.collidepoint(event.pos):  # read-only 返回 → yellow press + loading beat
                    press_transition(
                        screen,
                        rect=ok_rect,
                        label=i18n.t("setup_tims.back"),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE),
                        t=_FOOT_T,
                        redraw=lambda s: render_consent(s, scroll_y, read_only),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    return True
                if not read_only and cancel_rect.collidepoint(event.pos):  # 取消 → yellow press + loading beat → decline
                    press_transition(
                        screen,
                        rect=cancel_rect,
                        label=i18n.t("setup.ocr_disclaimer.cancel"),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE),
                        t=_FOOT_T,
                        redraw=lambda s: render_consent(s, scroll_y, read_only),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    return False
                if not read_only and ok_ready and ok_rect.collidepoint(event.pos):  # 明白 accept → yellow press + loading beat
                    press_transition(
                        screen,
                        rect=ok_rect,
                        label=i18n.t(OK_KEY),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE),
                        t=_FOOT_T,
                        redraw=lambda s: render_consent(s, scroll_y, read_only),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    return True


# ── settings view (steppers) ─────────────────────────────────────────────────────
_lead_m = 900
_interval_s = 3
_entry_lead = None  # settings-page entry snapshot (working-copy semantics: 返回 reverts, 設定 commits)
_entry_int = None
_LEAD_MIN, _LEAD_MAX, _LEAD_STEP = 500, 1500, 100
_INT_MIN, _INT_MAX, _INT_STEP = 1, 10, 1


def _load_state():
    global _lead_m, _interval_s
    s = i18n.load_settings()
    _lead_m = int(s.get("lead_m", 900))
    _interval_s = int(s.get("interval_s", 3))


def _save_state():
    s = i18n.load_settings()
    s["lead_m"], s["interval_s"] = _lead_m, _interval_s
    i18n.save_settings(s)


_STEP_T = chrome.BTN_STEP


def _draw_stepper(surf, label, value_text, y, *, can_dec=True, can_inc=True):
    """A [−] value [+] row; returns (minus_rect, plus_rect). Value = fat TIMS numerals. A stepper button
    goes SILVER (inactive) when the value is at the respective bound (can_dec / can_inc False)."""
    label_font = i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE)
    num_font = i18n.pixel_font_for_lang("en", STEP_VALUE_NATIVE)
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE)
    lh = lowres_text_size(label, label_font, 1, 0)[1]
    chrome.blit_lowres(surf, label, STEP_X, y + (44 - lh) // 2, label_font, INK, 1)
    bw = 44
    minus_rect = pygame.Rect(STEP_X + 210, y, bw, 44)
    value_box = pygame.Rect(minus_rect.right + 8, y, 120, 44)
    plus_rect = pygame.Rect(value_box.right + 8, y, bw, 44)
    minus_t = _STEP_T if can_dec else {**_STEP_T, **chrome.DISABLED}
    plus_t = _STEP_T if can_inc else {**_STEP_T, **chrome.DISABLED}
    draw_tims_button(surf, minus_rect, "−", font=btn_font, t=minus_t)
    draw_tims_button(surf, plus_rect, "＋", font=btn_font, t=plus_t)
    pygame.draw.rect(surf, PANEL_BG, value_box)
    pygame.draw.rect(surf, PANEL_BORDER, value_box, 1)
    nw = draw_lowres_number(pygame.Surface((1, 1)), value_text, (0, 0), num_font, INK, k=1)[0]
    draw_lowres_number(surf, value_text, (value_box.centerx - nw // 2, value_box.centery - num_font.get_height() // 2), num_font, INK, k=1)
    return minus_rect, plus_rect


def render_settings(screen):
    """Draw the OCR settings (steppers) view; return hit-rects."""
    screen.fill(BG_COLOR)
    band.ACTIVE_LANG = ACTIVE_LANG
    band_hits = band.render(screen)
    chrome.title_row(screen, SETTINGS_CODE, i18n.t("setup_tims.ocr_settings.heading"), ACTIVE_LANG)

    y = band.BAND_H + 90
    lead_minus, lead_plus = _draw_stepper(
        screen, i18n.t("setup.lead_label"), f"{_lead_m}m", y, can_dec=_lead_m > _LEAD_MIN, can_inc=_lead_m < _LEAD_MAX
    )
    y += 44 + STEP_ROW_GAP
    int_minus, int_plus = _draw_stepper(
        screen, i18n.t("setup.interval_label"), f"{_interval_s}s", y, can_dec=_interval_s > _INT_MIN, can_inc=_interval_s < _INT_MAX
    )

    # footer: 返回 (cancel/revert) bottom-LEFT + 設定 (save) bottom-RIGHT — a grouped pair, same size + design.
    # 設定 FLASHES white once a value has changed from the entry snapshot ('press to apply'); steady otherwise.
    btn_font = i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE)
    back_label, set_label = i18n.t("setup_tims.back"), i18n.t("setup_tims.set")
    bw = max(tims_button_size(back_label, btn_font, _FOOT_T)[0], tims_button_size(set_label, btn_font, _FOOT_T)[0])
    bh = tims_button_size(set_label, btn_font, _FOOT_T)[1]
    fy = SCREEN_H - FOOTER_H
    back_rect = pygame.Rect(PANEL_X, fy, bw, bh)
    set_rect = pygame.Rect(SCREEN_W - PANEL_X - bw, fy, bw, bh)
    changed = _entry_lead is not None and (_lead_m != _entry_lead or _interval_s != _entry_int)
    set_state = "waiting" if (changed and (pygame.time.get_ticks() // 450) % 2 == 0) else "normal"
    draw_tims_button(screen, back_rect, back_label, font=btn_font, t=_FOOT_T)
    draw_tims_button(screen, set_rect, set_label, font=btn_font, t=_FOOT_T, state=set_state)
    return {
        "home": band_hits["home"],
        "back": back_rect,
        "set": set_rect,
        "lead_minus": lead_minus,
        "lead_plus": lead_plus,
        "int_minus": int_minus,
        "int_plus": int_plus,
    }


def _stepper_tap(screen, rect, glyph):
    """Momentary YELLOW press feedback for an in-place stepper — same press primitive as every other
    button, but blank_ms=0 (NO loading beat: the value changes on THIS page, there's no navigation)."""
    press_transition(
        screen,
        rect=rect,
        label=glyph,
        font=i18n.pixel_font_for_lang(ACTIVE_LANG, TITLE_NATIVE),
        t=_STEP_T,
        redraw=lambda s: render_settings(s),
        blank_color=BG_COLOR,
        blank_ms=0,
        pressed_ms=80,
    )


def run_settings(screen):
    """Run the OCR settings (steppers) view until 設定 (Set) / 返回 (Cancel) / Home. Working-copy semantics:
    steppers edit an in-memory copy; ONLY 設定 persists (_save_state). 返回 / ESC / Home / QUIT discard by
    reverting to the entry snapshot. Returns "home" on band Home (bubble to the menu), None on 設定 / 返回 / ESC."""
    global _lead_m, _interval_s, _entry_lead, _entry_int
    _load_state()
    _entry_lead, _entry_int = _lead_m, _interval_s  # snapshot for 返回=revert; 設定 commits the working copy
    clock = pygame.time.Clock()
    while True:
        hits = render_settings(screen)
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                _lead_m, _interval_s = _entry_lead, _entry_int  # discard unconfirmed edits (only 設定 saves)
                return
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                _lead_m, _interval_s = _entry_lead, _entry_int  # ESC = cancel → revert
                return
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits["home"].collidepoint(event.pos):  # band Home → press + load beat → bubble home
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
                    _lead_m, _interval_s = _entry_lead, _entry_int  # Home discards unconfirmed edits
                    return "home"
                elif hits["set"].collidepoint(event.pos):  # 設定 → SAVE the working copy + return (yellow press + loading beat)
                    press_transition(
                        screen,
                        rect=hits["set"],
                        label=i18n.t("setup_tims.set"),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE),
                        t=_FOOT_T,
                        redraw=lambda s: render_settings(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    _save_state()
                    return None
                elif hits["back"].collidepoint(event.pos):  # 返回 → CANCEL: revert to entry + return (yellow press + loading beat)
                    press_transition(
                        screen,
                        rect=hits["back"],
                        label=i18n.t("setup_tims.back"),
                        font=i18n.pixel_font_for_lang(ACTIVE_LANG, FOOT_NATIVE),
                        t=_FOOT_T,
                        redraw=lambda s: render_settings(s),
                        blank_color=BG_COLOR,
                        blank_ms=450,
                        blank_rect=pygame.Rect(0, band.BAND_H, SCREEN_W, SCREEN_H - band.BAND_H),
                    )
                    _lead_m, _interval_s = _entry_lead, _entry_int  # cancel → discard edits
                    return None
                elif hits["lead_minus"].collidepoint(event.pos):
                    if _lead_m > _LEAD_MIN:  # inactive (silver) at the lower bound → no tap, no change
                        _stepper_tap(screen, hits["lead_minus"], "−")
                        _lead_m = max(_LEAD_MIN, _lead_m - _LEAD_STEP)  # clamp too: safe if a stored value is step-misaligned
                elif hits["lead_plus"].collidepoint(event.pos):
                    if _lead_m < _LEAD_MAX:  # inactive at the upper bound
                        _stepper_tap(screen, hits["lead_plus"], "＋")
                        _lead_m = min(_LEAD_MAX, _lead_m + _LEAD_STEP)
                elif hits["int_minus"].collidepoint(event.pos):
                    if _interval_s > _INT_MIN:
                        _stepper_tap(screen, hits["int_minus"], "−")
                        _interval_s = max(_INT_MIN, _interval_s - _INT_STEP)
                elif hits["int_plus"].collidepoint(event.pos):
                    if _interval_s < _INT_MAX:
                        _stepper_tap(screen, hits["int_plus"], "＋")
                        _interval_s = min(_INT_MAX, _interval_s + _INT_STEP)


# ── consent gate ─────────────────────────────────────────────────────────────────
def consent_given():
    return bool(i18n.load_settings().get("ocr_consent", False))


def ensure_consent(screen):
    """The gate the pa-setting OCR buttons call. If consent already given → True immediately. Else show
    the consent view; on accept, persist ocr_consent=True and return True; band Home returns "home" (the
    caller bubbles the return to the home menu); cancel/ESC returns False.

    NOTE: "home" is truthy — callers MUST test it explicitly BEFORE any `if ensure_consent(...):`
    truthy check, else a band-Home return is mis-read as consent-accepted."""
    if consent_given():
        return True
    res = run_consent(screen, read_only=False)
    if res == "home":
        return "home"
    if res:
        s = i18n.load_settings()
        s["ocr_consent"] = True
        i18n.save_settings(s)
        return True
    return False


def ocr_launch_extras():
    """The auto_input launch fields (read fresh from settings) merged into a launch config."""
    _load_state()
    return {"auto_input": True, "lead_m": _lead_m, "interval_s": _interval_s}


# ── dev preview ──────────────────────────────────────────────────────────────────
def run_interactive(view="consent"):
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(f"OCR {view} (draft)")
    _load_state()
    if view == "consent":
        run_consent(screen, read_only=False)
    else:
        run_settings(screen)
    pygame.quit()


def save_screenshot(path, view="consent"):
    pygame.init()
    pygame.font.init()
    i18n.init(ACTIVE_LANG)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))  # set_mode so image loads/blits work headless
    _load_state()
    if view == "consent":
        render_consent(screen, 0, read_only=False)
    else:
        render_settings(screen)
    out = str(project_root() / path)
    pygame.image.save(screen, out)
    print(f"saved {out}  ({SCREEN_W}x{SCREEN_H})")

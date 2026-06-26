"""App-chrome widgets — the JR East TIMS cab-console look (glossy raised-bevel pixel buttons +
low-res pixel text). CHROME ONLY: setup screen, language picker, OCR debug panel, future OOBE.
The train LCD displays are NOT chrome — they own their own faces and primitives under `displays/`
(`displays/utils.py`); do not route LCD drawing through here. (Module boundary settled by /third-man,
2026-06-24: chrome widgets and LCD primitives stay separate — they share pygame, not primitives.)

Two collaborating primitive families:
  * draw_lowres_text / draw_lowres_text_highlight / draw_lowres_number / lowres_text_size /
    lowres_number_size / lowres_fit_k — the low-res pixel-text face: render a glyph at its NATIVE px
    (antialias OFF) then nearest-upscale by an integer k (the 'embedded-bitmap / MS-Word-zoomed-tiny'
    look). STANDALONE — no button knowledge. _highlight adds a cyan marker block behind the text.
  * draw_tims_button / tims_button_size — the glossy raised bevel; it hands its inner rect to the text
    primitive (collaboration, not ownership). Pass label="" for a bevel hosting custom content.

# CONTRACT: fonts arrive PRE-RESOLVED as pygame.font.Font objects — this module loads NO fonts.
# The caller resolves the per-locale pixel face via i18n.pixel_font_for_lang(lang, native_px) and
# passes the Font; native size lives in that Font. Keeps per-locale dispatch + path resolution in
# i18n (its canonical home), so widgets.py has no SysFont / project_root() / _MEIPASS surface at all.
# See conventions.md § "Never pygame.font.SysFont" + critical_lessons.md § 4.
"""

from functools import lru_cache

import pygame

# fmt: off
_TUNEABLES_TIMS_BUTTON = {
    # --- geometry ---
    "corner_radius":      5,     # OUTER rounded-corner radius (button outline + bevel outer edge)
    "face_corner_radius": 4,     # INNER rounded-corner radius (face / inner bevel edge) — independent
    "outer_border_w":     2,     # thin dark outline thickness
    "bezel_lip_w":        3.0,   # bevel width on the BRIGHT side (top + left) — thinned for small band buttons (was 4.5)
    "bezel_shadow_w":     1.8,   # bevel width on the DARK side (bottom + right) — thinned to match (was 2.7)
    "bezel_transition":      2,    # corner-miter blend half-width in PX (short; linear ramp)
    "bezel_transition_bias": 0,    # px the bright lip extends past the 45° miter toward the corner tip
    "face_blend":         4,     # soft gradient px: bevel inner edge -> face base (local bevel color)
    "h_pad":              22,    # horizontal text padding each side -> content width
    "v_pad":              14,    # vertical text padding each side -> content height
    "min_w":              60,    # floor on auto width
    # --- colors (flat deep-blue face under a bright top-left bezel lip) ---
    "outer_border_color": (14, 22, 38),     # near-black navy outline
    "bezel_hi_color":     (228, 243, 253),  # normal bevel lip: bright crest, top + left (lit)
    "bezel_lo_color":     (15, 34, 48),     # normal bevel shadow: dark slate, bottom + right
    "bezel_hi_pressed_color":  (255, 253, 185),  # PRESSED bevel lip: bright yellow
    "bezel_lo_pressed_color":  (138, 104, 10),   # PRESSED bevel shadow: dark yellow
    "bezel_hi_waiting_color":  (253, 254, 255),  # WAITING bevel lip: bright white
    "bezel_lo_waiting_color":  (120, 150, 172),  # WAITING bevel shadow: dim cool gray
    "face_top_color":     (1, 85, 155),     # normal face base: deep blue, near-flat
    "face_bottom_color":  (0, 73, 142),     # subtle bottom darkening
    "face_top_pressed_color":    (255, 244, 38),  # PRESSED: bright yellow, top
    "face_bottom_pressed_color": (250, 226, 8),   # PRESSED: bright yellow, bottom (near-flat)
    "face_top_waiting_color":    (245, 250, 255), # WAITING-CONFIRM flash phase: bright white, top
    "face_bottom_waiting_color": (228, 240, 250), # WAITING-CONFIRM flash phase: bright white, bottom
    # --- text (low-res pixel face: render at the Font's native px, nearest-upscale by integer k) ---
    "text_color":      (238, 241, 243),  # ink on dark face (normal): neutral white
    "text_dark_color": (20, 28, 40),     # ink on bright face (pressed/waiting): dark — flips for contrast
    "text_max_k":      2,    # ceiling on the integer pixel-multiplier. CONVENTION: chrome pixel text caps at k=2 (the
                             # small-size aesthetic — Ark upscaled bigger goes chunky). A big box gets more padding, NOT bigger text.
    "nominal_k":       2,    # chrome pixel-multiplier that content-sizing targets (tims_button_size); draw fills 1..text_max_k
    "line_gap":        1,    # px between stacked lines
}
# fmt: on


def _rounded_clip(surf, radius):
    """Zero the alpha outside a rounded-rect of the surface's own size (in place); returns surf."""
    w, h = surf.get_size()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return surf


def _feather_clip(surf, radius, blend):
    """Like _rounded_clip, but ramp the OUTER `blend` px of alpha 0→255 so the surface fades
    into whatever's underneath (a soft edge) instead of a hard rounded cut. blend<=0 = hard."""
    if blend <= 0:
        return _rounded_clip(surf, radius)
    w, h = surf.get_size()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(blend + 1):
        a = round(255 * i / blend)
        pygame.draw.rect(mask, (255, 255, 255, a), (i, i, w - 2 * i, h - 2 * i), border_radius=max(0, radius - i))
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return surf


@lru_cache(maxsize=64)
def _vgradient_rounded(w, h, top, bottom, radius, blend=0):
    """A w×h surface: vertical top→bottom gradient; outer `blend` px feathered to a soft edge.
    Cached per (size, colors, radius, blend) — the setup screen + OCR debug panel redraw every frame
    and this is a per-pixel Python loop; the returned surface is blitted, never mutated, so sharing
    one cached instance across frames is safe."""
    w, h = max(0, w), max(0, h)
    grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        grad.fill(
            (
                round(top[0] + (bottom[0] - top[0]) * t),
                round(top[1] + (bottom[1] - top[1]) * t),
                round(top[2] + (bottom[2] - top[2]) * t),
                255,
            ),
            (0, y, w, 1),
        )
    return _feather_clip(grad, radius, blend)


@lru_cache(maxsize=64)
def _bezel_ring(w, h, bright, dark, radius, transition, bias):
    """Bevel field (rounded-clipped). Each pixel takes the tone of its NEAREST edge: top / left =
    bright (lit), bottom / right = dark (shadow). The bright↔dark boundary is therefore the true
    45° corner MITER — at TR where dist-to-top == dist-to-right, at BL where dist-to-left ==
    dist-to-bottom — independent of the button's aspect ratio. (The old x/w + y/h full-diagonal was
    wrong: on a non-square button its angle isn't 45°, so the corner transition slanted off.)
    `transition` = blend half-width in PX across the miter; `bias` (px) extends the bright lip past
    the miter toward the corner tip. Linear ramp, never a jump. Face on top leaves it a ring."""
    w, h = max(1, w), max(1, h)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    tw = max(1e-6, transition)
    dr, dg, db = dark[0] - bright[0], dark[1] - bright[1], dark[2] - bright[2]
    for y in range(h):
        lit_y, shad_y = y, h - 1 - y
        for x in range(w):
            lit = lit_y if lit_y < x else x  # dist to nearest LIT edge (top/left)
            shad = shad_y if shad_y < (w - 1 - x) else (w - 1 - x)  # nearest SHADOW edge (bottom/right)
            s = 0.5 + (lit - shad - bias) / (2 * tw)  # 0 = bright, 1 = dark; miter at lit==shad
            s = 0.0 if s <= 0 else 1.0 if s >= 1 else s  # linear
            surf.set_at((x, y), (round(bright[0] + dr * s), round(bright[1] + dg * s), round(bright[2] + db * s), 255))
    return _rounded_clip(surf, radius)


def lowres_fit_k(label, area, font, max_k=2, line_gap=1, pad=0):
    """The integer pixel-multiplier draw_lowres_text would pick for `label` in `area` (same fit math,
    single source of truth). Use it to pin a ROW of elements to ONE uniform size: compute the k each
    label needs, pass the MIN back as every element's max_k — the densest label sets the size and the
    rest cap to it. `font` is a pygame.font.Font already at the native render size."""
    area = pygame.Rect(area)
    if pad:
        area = area.inflate(-2 * pad, -2 * pad)
    lines = label.split("\n")
    n = len(lines)
    gh = font.get_height()
    dense_w0 = max((sum(font.size(ch)[0] for ch in ln) for ln in lines), default=1)
    avail_h = area.h - line_gap * (n - 1)
    return max(1, min(max_k, avail_h // max(1, gh * n), area.w // max(1, dense_w0)))


def draw_lowres_text(surface, label, area, font, color, max_k=2, line_gap=1, align="justify", pad=0):
    """STANDALONE low-res pixel-text primitive — the cross-cutting TIMS chrome text face, reused
    app-wide EXCEPT the train LCD displays. Knows nothing about buttons.

    Renders `label` (caller owns \\n line breaks; never auto-wraps) inside `area` (Rect), vertically
    centered. Each glyph is drawn at the `font`'s native px with antialias OFF — the 'panel grid',
    keep ~12-15 so complex kanji hold their strokes — then nearest-neighbor upscaled by the LARGEST
    INTEGER k in 1..max_k that fits `area`. A big area -> bigger k (text scales up to fill, never
    stuck at 1×); a dense / 2-line label -> smaller k (stays sharp).

    `pad` insets `area` on all sides BEFORE layout — a margin that holds text off whatever frames it
    (e.g. a button bevel), independent of inter-char spacing. `align` picks the horizontal layout:
      * "justify" (両端揃え, default) — lines left-aligned sharing ONE even gap from the densest line;
        slack spreads into equal outer margins + inter-char gaps (a 2-char label reads evenly spread).
      * "center" — each line packed TIGHT (no inter-char gap) and centered. Combine with `pad` for
        tight text held off the edges (the language-knob look). The two are decoupled: `pad` is the
        margin, "center" zeroes the inter-char gap — justify alone can't give one without the other.

    `font` is a pre-resolved pygame.font.Font (caller: i18n.pixel_font_for_lang(lang, native)). The k
    fit subtracts the inter-line gap BEFORE dividing by the scaled per-line height — else a box sized
    for k=2 floors to k=1 (the unscaled gap eats the last pixel). HARDENED: never spills `area` — a
    too-wide line compresses horizontally (hx<1) and the whole draw is clipped to `area`."""
    area = pygame.Rect(area)
    if pad:
        area = area.inflate(-2 * pad, -2 * pad)  # lay out inside the margin
    lines = label.split("\n")
    n = len(lines)
    gh = font.get_height()

    def raw_w(line):
        return sum(font.size(ch)[0] for ch in line)

    dense_w0 = max((raw_w(ln) for ln in lines), default=1)
    k = lowres_fit_k(label, area, font, max_k, line_gap)  # area already padded above

    # HARDENING: if even k=1's densest line is wider than the area, squeeze glyphs horizontally
    # (hx<1) so text never spills; the clip rect below is the hard backstop (also covers a degenerate
    # area height where k=1 glyphs would still overrun vertically).
    line_px = dense_w0 * k
    hx = min(1.0, area.w / line_px) if line_px > 0 else 1.0

    line_h = gh * k
    total_h = line_h * n + line_gap * (n - 1)
    y = area.centery - total_h // 2
    prev_clip = surface.get_clip()
    surface.set_clip(area)

    def _glyph(ch):
        g = font.render(ch, False, color)  # antialias OFF -> aliased pixels
        gw, gh2 = max(1, round(g.get_width() * k * hx)), g.get_height() * k
        if (gw, gh2) != g.get_size():
            g = pygame.transform.scale(g, (gw, gh2))  # nearest: upscale by k, squeeze by hx
        return g

    if align == "center":
        for line in lines:
            if line:
                glyphs = [_glyph(ch) for ch in line]
                lw = sum(g.get_width() for g in glyphs)  # tight line width (no inter-char gap)
                x = area.centerx - lw // 2
                for g in glyphs:
                    surface.blit(g, (round(x), y + (line_h - g.get_height()) // 2))
                    x += g.get_width()
            y += line_h + line_gap
    else:
        wi = max(range(n), key=lambda i: raw_w(lines[i]))
        nw = len(lines[wi])
        gap = max(0.0, (area.w - line_px * hx) / (nw + 1)) if nw else 0.0  # 両端揃え on densest line
        for line in lines:
            if line:
                x = area.left + gap
                for ch in line:
                    g = _glyph(ch)
                    surface.blit(g, (round(x), y + (line_h - g.get_height()) // 2))
                    x += g.get_width() + gap
            y += line_h + line_gap
    surface.set_clip(prev_clip)


def lowres_text_size(label, font, k=2, line_gap=1):
    """Pixel-text footprint (w, h) at multiplier `k` — for content-deriving a box that fits it."""
    lines = label.split("\n")
    n = len(lines)
    gh = font.get_height()
    w = max((sum(font.size(ch)[0] for ch in ln) for ln in lines), default=1) * k
    h = gh * k * n + line_gap * (n - 1)
    return w, h


# TIMS "new / look-here" hint: a flat cyan block behind pixel text (a highlighter-pen marker). Used
# to flag a freshly-changed element (e.g. the new tutorial entry) without a separate badge.
HINT_CYAN_COLOR = (45, 216, 233)  # bright cyan block
HINT_INK_COLOR = (16, 30, 42)  # dark ink on the bright cyan (same contrast flip the button does)


def draw_lowres_text_highlight(
    surface, label, area, font, ink=HINT_INK_COLOR, highlight=HINT_CYAN_COLOR, max_k=2, line_gap=1, pad_x=4, pad_y=2, radius=3
):
    """draw_lowres_text wearing a filled `highlight` block (the cyan 'NEW / look-here' marker) — a
    flat rounded-rect that HUGS the text footprint, drawn BEHIND the glyphs. Text is center-laid
    (tight) in `ink`; pass a DARK ink — the bright cyan wants dark text, the same contrast flip
    draw_tims_button does on its pressed/waiting faces. The block = the text footprint at the fitted
    k, inflated by (pad_x, pad_y) and rounded by `radius`, centered in `area`. Shares lowres_fit_k
    with draw_lowres_text, so the block and the glyphs always agree on size."""
    area = pygame.Rect(area)
    k = lowres_fit_k(label, area, font, max_k, line_gap)
    tw, th = lowres_text_size(label, font, k, line_gap)
    block = pygame.Rect(0, 0, tw + 2 * pad_x, th + 2 * pad_y)
    block.center = area.center
    pygame.draw.rect(surface, highlight, block, border_radius=radius)
    draw_lowres_text(surface, label, area, font, ink, max_k=max_k, line_gap=line_gap, align="center")


def _ink_width(font, ch):
    """Horizontal ink extent of `ch` at this font (the glyph's drawn columns, NOT its advance cell).
    Falls back to the advance for blanks (space) where there's no ink."""
    bbox = font.render(ch, False, (255, 255, 255)).get_bounding_rect()
    return bbox.w if bbox.w else font.size(ch)[0]


def lowres_number_size(text, font, k=2, xscale=1.0, gap=0):
    """Footprint (w, h) of a TIMS numeral run — see draw_lowres_number for the model."""
    w = sum(max(1, round(_ink_width(font, ch) * k * xscale)) for ch in text)
    w += round(gap * k) * max(0, len(text) - 1)
    return w, font.get_height() * k


def draw_lowres_number(surface, text, pos, font, color, k=2, xscale=1.0, gap=0):
    """TIMS numeral run — digit WIDTH and inter-digit GAP are INDEPENDENT knobs. Each glyph is
    rendered at the `font`'s native px (antialias off), HORIZONTALLY TRIMMED to its ink, upscaled k×,
    widened by `xscale`, then laid out with an explicit `gap` between glyphs.

    Why not full-width forms (U+FFxx): those center the digit in a full em CELL with fat side-bearings,
    so adjacent digits sit far apart — and squeezing the whole render to condense scales the GAP down
    with the glyph, so it never closes. Trimming to ink drops the side-bearings entirely; the only
    space left between digits is the `gap` you ask for. TIMS digits read wider than half-width but not
    a full square — that's `xscale` (>1 widens) decoupled from `gap` (px between, may be negative to
    overlap). Vertical extent is kept full-height so glyphs stay baseline-aligned.

    `pos` = top-left; returns (w, h) drawn. Reusable: version tag, train numbers, diagram codes, clocks.
    For a label + a number ("Version 054"), render the word with draw_lowres_text and the run here,
    sharing the font + k so baselines line up."""
    fh = font.get_height()
    x0, y0 = pos
    x = float(x0)
    gp = round(gap * k)
    for ch in text:
        full = font.render(ch, False, color)
        bbox = full.get_bounding_rect()
        if not bbox.w:  # blank (space): advance by its cell, no glyph drawn
            x += max(1, round(font.size(ch)[0] * k * xscale)) + gp
            continue
        # trim HORIZONTALLY to ink (kill side-bearings), keep FULL height (preserve baseline)
        g = full.subsurface((bbox.x, 0, bbox.w, fh)).copy()
        gw, gh = max(1, round(bbox.w * k * xscale)), fh * k
        if (gw, gh) != g.get_size():
            g = pygame.transform.scale(g, (gw, gh))  # nearest: k upscale + xscale widen
        surface.blit(g, (round(x), y0))
        x += gw + gp
    return round(x) - gp - x0, fh * k


def press_transition(
    surface, *, rect, label, font, t=_TUNEABLES_TIMS_BUTTON, redraw=None, blank_color=(62, 68, 80), blank_rect=None, pressed_ms=130, blank_ms=450
):
    """Shared TIMS press / transition beat — one wrapper reused for every decisive press.

    Sequence: flash the pressed button bright YELLOW (the momentary feedback) and hold, then — for a
    decisive / navigational action (page change, language switch) — a brief 'loading' beat, after
    which the CALLER repaints the new screen. ``redraw(surface)`` repaints the current screen under
    the pressed button (pass None to overlay on the existing frame). ``blank_ms=0`` → pure press flash,
    no loading beat (non-navigational feedback; caller's next paint restores the normal button).

    The loading beat fills with ``blank_color`` = the screen's OWN BACKGROUND (not black) so it reads
    as the screen emptied of content, not a blackout — caller passes its bg. ``blank_rect`` scopes the
    beat to the region that actually changes (e.g. only the side panel of a sub-screen); None = the
    whole surface.

    Blocks via ``pygame.time.delay`` (a deliberate beat) and flips the display itself, so ``surface``
    must be the display surface. Leaves the beat region blank when ``blank_ms>0`` — caller repaints
    next."""
    if redraw is not None:
        redraw(surface)
    draw_tims_button(surface, rect, label, font=font, t=t, state="pressed")
    pygame.display.flip()
    pygame.time.delay(pressed_ms)
    if blank_ms > 0:
        surface.fill(blank_color, blank_rect)
        pygame.display.flip()
        pygame.time.delay(blank_ms)


def tims_button_size(label, font, t=_TUNEABLES_TIMS_BUTTON):
    """Content-derived (w, h): the box hugs the label's pixel-text footprint (at the nominal k=2
    chrome multiplier) + padding + bevel, so a 2-line label becomes a TALLER box rather than tiny
    text in a fixed one. draw_tims_button then renders at k=2 to match (or higher if the caller
    forces a bigger box — see draw_lowres_text's fill-to-fit)."""
    tw, th = lowres_text_size(label, font, t["nominal_k"], t["line_gap"])
    bevel = 2 * t["outer_border_w"] + t["bezel_lip_w"] + t["bezel_shadow_w"]  # rect - face footprint
    return (max(t["min_w"], tw + 2 * t["h_pad"]) + bevel, th + 2 * t["v_pad"] + bevel)


def draw_tims_button(surface, rect, label="", font=None, t=_TUNEABLES_TIMS_BUTTON, state="normal"):
    """Draw a TIMS-style glossy raised bevel button, then hand its inner (padded) face rect to
    draw_lowres_text — the pixel-text primitive owns the label; the button owns only the bevel + the
    padding inset. Pass label="" to draw the bevel/face alone (e.g. to host a custom drawing — the
    'special content' case); `font` may then be None.

    `state` colors the WHOLE button — face AND bevel (ink flips dark on the bright states):
        "normal"  -> deep-blue face + blue bevel, white ink
        "pressed" -> yellow face + yellow bevel, dark ink
        "waiting" -> white face + white bevel, dark ink (lit phase of a flash; runtime toggles on a timer)
    """
    rect = pygame.Rect(rect)
    r = t["corner_radius"]
    ob = t["outer_border_w"]
    lip = t["bezel_lip_w"]
    shd = t["bezel_shadow_w"]

    # state palette — highlighted states color the WHOLE button (bevel included); ink flips for contrast
    if state == "pressed":
        ftop, fbot = t["face_top_pressed_color"], t["face_bottom_pressed_color"]
        bhi, blo, ink = t["bezel_hi_pressed_color"], t["bezel_lo_pressed_color"], t["text_dark_color"]
    elif state == "waiting":
        ftop, fbot = t["face_top_waiting_color"], t["face_bottom_waiting_color"]
        bhi, blo, ink = t["bezel_hi_waiting_color"], t["bezel_lo_waiting_color"], t["text_dark_color"]
    else:
        ftop, fbot = t["face_top_color"], t["face_bottom_color"]
        bhi, blo, ink = t["bezel_hi_color"], t["bezel_lo_color"], t["text_color"]

    # 1) thin dark outline (whole rect)
    pygame.draw.rect(surface, t["outer_border_color"], rect, border_radius=r)

    # 2) raised bevel — bright lip (top+left) + dark shadow (bottom+right), 45° miter at TR/BL.
    #    The asymmetric face inset (next) makes the bright side wider. Face on top leaves it a ring.
    bezel = rect.inflate(-2 * ob, -2 * ob)
    br = max(1, r - ob)
    if bezel.w > 0 and bezel.h > 0:
        ring = _bezel_ring(bezel.w, bezel.h, bhi, blo, br, t["bezel_transition"], t["bezel_transition_bias"])
        surface.blit(ring, bezel.topleft)

    # 3) face — flat-ish gradient; outer edge feathered so the bevel blends into the base. Guard
    #    degenerate sizes (negative rect crashes alloc).
    face_rect = pygame.Rect(bezel.x + lip, bezel.y + lip, bezel.w - lip - shd, bezel.h - lip - shd)
    fr = max(1, t["face_corner_radius"])
    if face_rect.w > 0 and face_rect.h > 0:
        grad = _vgradient_rounded(face_rect.w, face_rect.h, ftop, fbot, fr, t["face_blend"])
        surface.blit(grad, face_rect.topleft)
        # 4) label — delegate to the standalone pixel-text primitive. Two layout modes via the
        #    tuneable:
        #      "justify" — inset VERTICALLY by v_pad, keep FULL width, so 両端揃え spreads the h_pad
        #                  slack into equal margins + inter-char gaps (the action-button spread).
        #      "center"  — hand the whole face + a text_pad margin so the label packs tight and
        #                  centers off the bevel (the language-knob look; no inter-char gap).
        align = t.get("text_align", "justify")
        if align == "center":
            text_area, text_pad = face_rect, t.get("text_pad", 0)
        else:
            text_area = pygame.Rect(face_rect.x, face_rect.y + t["v_pad"], face_rect.w, face_rect.h - 2 * t["v_pad"])
            text_pad = 0
        if label and font is not None and text_area.w > 0 and text_area.h > 0:
            draw_lowres_text(surface, label, text_area, font, ink, max_k=t["text_max_k"], line_gap=t["line_gap"], align=align, pad=text_pad)

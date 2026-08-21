# SPDX-License-Identifier: MIT
"""The platform departure-bell box (発車ベル), drawn as it looks on a JR platform.

A conductor steps down, presses ON, the melody starts and repeats; pressing OFF
releases the ON latch, the melody stops and the closing announcement plays. That
is exactly what Page Up already does — the box is a second face on the same
action, and its ON button being pressed IN is nothing more than a picture of
``AudioPlayer.is_sta_looping()``.

# CONTRACT: the box owns no state. Everything it draws is derived from audio.
# ``BellState.of()`` is the only place that mapping lives, and it is a pure
# function so a test can call it without a mixer, a window, or a route. Adding a
# field here that the audio cannot answer is how the picture and the sound drift
# apart while both look right on their own.

# CONTRACT: this is a 2D GAME ASSET, not a render of a 3D object. There is no
# camera and no perspective — the box is drawn flat-on, and every impression of
# depth comes from one convention applied everywhere: a single light from the
# top-left, so anything RAISED carries a lit edge on its top-left and a dark
# edge on its bottom-right, and anything SUNKEN carries exactly the inverse.
# ``_panel(raised=...)`` is that convention, and it is the only place it lives.
# Mixing in a photographic cue — a receding side wall, a vanishing point, a
# specular highlight that implies a light the rest of the box does not have —
# is what made the earlier draft read as a bad 3D render rather than a good
# sprite. The reference photo settles PROPORTION and COLOUR; it does not settle
# how a surface is shaded.

Geometry lives in the ``_TUNEABLES_BELL_*`` dicts so the calibration editor can
drag it. Everything downstream derives from those, so changing a cap size moves
the text, the socket, the shadow and the hit-rect together.

Reference anchors — measured in ``_references/bell/sta-bell.jpg`` (387x516) and
expressed as fractions of the enclosure so they survive the canvas being
resized. The photo is shot from below-left, so every ratio below is the
undistorted reading of a distorted source; it cannot settle these to the pixel,
which is why the numbers get finished by eye against the state strip.

    enclosure   x 82..302, y 82..458   220 x 376  ->  1 : 1.71
    label plate                        0.630 w  x 0.112 h, top at 0.153
    cavity collar                      0.653 w  x 0.622 h, top at 0.283
    ON  cap     y 218..296             0.324 w (square), top at 0.380
    OFF cap     x 148..224, y 326..401 same size  ->  the caps are equal
    cap gap                            0.33 of a cap

The casting is three levels, not two, and the corners are where that shows: an
outer body carrying the four screws on a low shelf, a raised central plateau
whose corners are cut away to clear them, and a lit ramp on the step between.
Drawing it as one chamfered silhouette loses the screws' shelf entirely.

The photo also happens to show the box MID-STATE: its ON cap sits low while OFF
stands proud, which is the ringing picture, not the resting one. Compare against
``--state ringing``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from font_atlas import lcd_font, lit

# The box is a fixed-resolution pixel artifact like every other surface in this
# app, so the window scales it by whole multiples rather than resampling — see
# window_utils § window zoom. This is the 1x size.
BELL_CANVAS = (192, 316)

# fmt: off
_TUNEABLES_BELL_BOX = {
    "box_x":              8,   # canvas margin — leaves room for the cast shadow
    "box_y":              8,
    "box_w":            176,
    "box_h":            300,   # 176 x 300 keeps the measured 1 : 1.71
    "box_radius":        12,   # the outer body is ROUNDED; the plateau is cut
    "box_edge":           2,   # lit/dark rim that makes the body read as raised
    "box_contour":        1,   # dark outline so the sprite reads off any window
    "box_shadow_off":     4,   # how far the cast shadow falls, down-right
}

_TUNEABLES_BELL_FACE = {
    "face_inset":         7,   # plateau, in from the body edge — the screw shelf
    "face_chamfer":      26,   # corner cut; must clear the screw bosses
    "face_ramp":          2,   # lit step from shelf up to plateau
    "face_edge":          2,
}

_TUNEABLES_BELL_SCREW = {
    "screw_inset_x":     12,   # centre, in from the body edge — on the shelf
    "screw_inset_y":     12,
    "screw_r":            4,   # head radius (0.045 of box w across)
    "screw_boss_r":       6,   # recess the head sits in
    "screw_slot_w":       2,   # cross-slot stroke
    "screw_slot_len":     6,   # cross-slot arm span
    "screw_tilt":        18,   # degrees — a driven screw never lands square
}

_TUNEABLES_BELL_PLATE = {
    "plate_w":          111,   # 0.630 of box w
    "plate_h":           34,   # 0.112 of box h
    "plate_top":         46,   # below the box top (0.153) — clears the screws
    "plate_radius":       2,
    "plate_edge":         1,   # recessed border the paper sits in
    "plate_text_size":   16,
    "plate_text_dy":      0,   # nudge the label off optical centre
}

_TUNEABLES_BELL_CAVITY = {
    "cavity_w":          85,   # the WELL opening; the collar adds collar_w each side
    "cavity_h":         158,
    "cavity_top":        90,   # below the box top — collar spans 0.277..0.850
    "cavity_radius":     18,
    "collar_w":           7,   # raised lip: 85 + 2*7 = 99 = 0.563 of box w
    "collar_radius":     25,
    "collar_edge":        2,
    "well_edge":          3,   # sunken rim — dark at top-left, lit at bottom-right
}

_TUNEABLES_BELL_CAP = {
    "cap_size":          57,   # square (0.324 of box w)
    "cap_radius":         5,
    "on_top":            98,   # below the box top — cap group centred in the well
    "off_top":          174,   # gap of 19 = 0.33 of a cap
    "cap_bezel":          2,   # clearance ring around the cap in the casing
    "cap_rise":           5,   # how far the cap stands proud — and therefore
                               # exactly how far it travels, since pressed is
                               # flush. One number, so the two cannot disagree.
                               # Kept short: a tall skirt makes a square cap
                               # read as an upright rectangle.
    "cap_edge":           2,   # bevel while proud...
    "cap_seam":           1,   # ...and the hairline left once it is flush
    "cap_shadow_off":     4,   # shadow a proud cap throws on the socket floor
    "cap_press_darken": 0.06,  # flush, it only loses its lit top edge. Nothing
                               # overhangs a coplanar face, so this is a hint,
                               # NOT the deep shade of a recess.
    "cap_wall_mix":    0.30,   # side wall, toward the face: a bottom-facing wall
                               # is darker than its face, but on a near-black cap
                               # "darker" has nowhere to go — pure black merges
                               # the two into one tall slab
    "cap_text_dy":        0,
}

_TUNEABLES_BELL_GLYPH = {
    "glyph_h":           19,   # cap height of ON / OFF, in px. Sized against the
                               # CAP, not for legibility: the word runs wide and
                               # sits short, so the left/right margin is about
                               # half the top/bottom one. That relation is what
                               # the reference has, and what these numbers encode
                               # — check it survives before nudging glyph_w.
    "glyph_stroke":    0.13,   # stroke weight, as a fraction of cap height. At
                               # glyph_h 19 this rounds to a 2px stroke — thin is
                               # correct here; the earlier 0.19 read as a bold
                               # face rather than engraved signage.
    "glyph_gap":       0.20,   # tracking, same units
    "glyph_w":         0.64,   # ONE width for EVERY letter — the cap lettering
                               # is monospaced, and each glyph is DRAWN to fill
                               # its width rather than centred in a cell, so a
                               # narrow letter never floats inside a wide slot.
                               # A fraction of glyph_h, like the two below.
    "glyph_o_round":   0.50,   # 0.5 = radius is half the WIDTH, so the top and
                               # bottom close into full semicircles and the
                               # sides stay straight: a capsule, which is what
                               # the reference draws. Lower values square it
                               # off — 0.34 read as a rounded rectangle and was
                               # visibly wrong beside the photo.
    "glyph_f_bar_y":   0.45,   # middle arm: where it sits, and how far it runs
    "glyph_f_bar_w":   0.74,   # short of the top arm, which is full width
}

_TUNEABLES_BELL_PALETTE = {
    # Hues sampled from the reference; values lifted and separated, because the
    # photo is shot under dim platform fluorescents and a sprite needs its tones
    # further apart than a photograph does. Every *_top/*_bot pair is a vertical
    # gradient; every *_hi/*_lo pair is the lit and shaded rim of one panel.
    "canvas_color":       ( 24,  26,  30),
    "shadow_color":       ( 12,  13,  15),
    "contour_color":      ( 16,  17,  20),
    "body_hi_color":      (224, 223, 213),
    "body_lo_color":      (138, 136, 126),
    "body_top_color":     (194, 193, 181),
    "body_bot_color":     (170, 169, 156),
    "ramp_color":         (240, 239, 230),   # the lit step up to the plateau
    "face_hi_color":      (233, 232, 223),
    "face_lo_color":      (148, 146, 136),
    "face_top_color":     (211, 210, 198),
    "face_bot_color":     (186, 185, 172),
    "screw_hi_color":     (230, 230, 225),
    "screw_lo_color":     (144, 144, 139),
    "screw_well_color":   (118, 116, 108),
    "screw_slot_color":   ( 66,  66,  62),
    "plate_hi_color":     (234, 233, 224),
    "plate_lo_color":     (124, 122, 114),
    "plate_top_color":    (241, 242, 244),
    "plate_bot_color":    (217, 219, 223),
    "plate_ink_color":    ( 26,  27,  31),
    "collar_hi_color":    (231, 230, 221),
    "collar_lo_color":    (150, 148, 138),
    "collar_top_color":   (209, 208, 196),
    "collar_bot_color":   (185, 184, 171),
    "well_hi_color":      (124, 119, 110),
    "well_lo_color":      ( 58,  55,  50),
    "well_top_color":     ( 76,  72,  66),
    "well_bot_color":     ( 94,  90,  83),
    "socket_hi_color":    ( 92,  88,  81),
    "socket_lo_color":    ( 38,  36,  33),
    "socket_top_color":   ( 58,  55,  50),
    "socket_bot_color":   ( 78,  74,  68),
    "cap_shadow_color":   ( 24,  22,  20),
    "cap_seam_color":     ( 28,  26,  24),   # clearance gap around a flush cap
    "cap_ink_color":      (238, 238, 236),
    "on_hi_color":        (104, 104, 104),
    "on_lo_color":        ( 24,  24,  24),
    "on_top_color":       ( 60,  60,  60),
    "on_bot_color":       ( 32,  32,  32),
    "off_hi_color":       (238, 104, 112),
    "off_lo_color":       (110,  14,  22),
    "off_top_color":      (214,  46,  56),
    "off_bot_color":      (170,  26,  36),
}
# fmt: on

_FACE_LABEL = "発車ベル"


@dataclass(frozen=True)
class BellState:
    """What the box is showing. Derived, never stored.

    ``on_latched`` is the melody looping. ``*_flash`` is a click being
    acknowledged — held for a fixed time rather than until mouse-release,
    because production handles no MOUSEBUTTONUP anywhere and a remote tap has
    no release to wait for. One rule serves both.
    """

    on_latched: bool = False
    on_flash: bool = False
    off_flash: bool = False

    @staticmethod
    def of(is_sta_looping: bool, on_flash: bool = False, off_flash: bool = False) -> "BellState":
        return BellState(on_latched=is_sta_looping, on_flash=on_flash, off_flash=off_flash)


# ── hit testing ───────────────────────────────────────────────────────────────


def cap_rects() -> "dict[str, pygame.Rect]":
    """The two button faces in canvas coordinates, at rest.

    Shared by the local window and the remote tap so one geometry answers both,
    and so the hit-rects cannot drift from what is drawn — both read the same
    tuneables.
    """
    b, c = _TUNEABLES_BELL_BOX, _TUNEABLES_BELL_CAP
    size = c["cap_size"]
    x = b["box_x"] + (b["box_w"] - size) // 2
    return {
        "on": pygame.Rect(x, b["box_y"] + c["on_top"], size, size),
        "off": pygame.Rect(x, b["box_y"] + c["off_top"], size, size),
    }


def hit_test(pos) -> "str | None":
    """Which button a canvas-space point lands on, or None."""
    for name, rect in cap_rects().items():
        if rect.collidepoint(pos):
            return name
    return None


# ── sprite primitives ─────────────────────────────────────────────────────────
#
# Three pieces, and everything in the box is built from them:
#
#   _mask_*   a SHAPE, as white-on-transparent alpha. Supersampled 4x, so the
#             plateau's diagonals and the rounded corners come out clean at 1x
#             and stay clean when the window scales by a whole multiple.
#   _panel    a shape lit as one solid object: rim tone on the top-left, its
#             opposite on the bottom-right, gradient face between. `raised`
#             swaps the two, which is the ONLY difference between a boss and a
#             recess anywhere in this file.
#   _flat     a shape in one tone — shadows, contours, the ramp.
#
# pygame has no gradient primitive and no shape-relative bevel, so both are done
# by multiplying an alpha mask into a filled surface. The mask is a callback,
# which is why one panel routine serves the rounded body, the cut plateau, the
# caps and every recess.

_SS = 4
_WHITE = (255, 255, 255, 255)


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _mask_rrect(radius):
    def fn(m, inset=0):
        w, h = m.get_size()
        if w - 2 * inset <= 0 or h - 2 * inset <= 0:
            return
        big = pygame.Surface((w * _SS, h * _SS), pygame.SRCALPHA)
        box = pygame.Rect(inset * _SS, inset * _SS, (w - 2 * inset) * _SS, (h - 2 * inset) * _SS)
        pygame.draw.rect(big, _WHITE, box, border_radius=max(0, radius - inset) * _SS)
        m.blit(pygame.transform.smoothscale(big, (w, h)), (0, 0))

    return fn


def _mask_octagon(chamfer):
    """The plateau: a rectangle with all four corners cut away.

    Not a rounded rect — the cut is what clears the screw shelf behind it, and
    the flat facet is what the ramp is drawn on.
    """

    def fn(m, inset=0):
        w, h = m.get_size()
        if w - 2 * inset <= 0 or h - 2 * inset <= 0:
            return
        c, x0, y0 = max(0, chamfer - inset), inset, inset
        x1, y1 = w - inset, h - inset
        pts = [
            (x0 + c, y0),
            (x1 - c, y0),
            (x1, y0 + c),
            (x1, y1 - c),
            (x1 - c, y1),
            (x0 + c, y1),
            (x0, y1 - c),
            (x0, y0 + c),
        ]
        big = pygame.Surface((w * _SS, h * _SS), pygame.SRCALPHA)
        pygame.draw.polygon(big, _WHITE, [(x * _SS, y * _SS) for x, y in pts])
        m.blit(pygame.transform.smoothscale(big, (w, h)), (0, 0))

    return fn


def _shape(size, mask_fn, inset=0):
    m = pygame.Surface(size, pygame.SRCALPHA)
    mask_fn(m, inset)
    return m


def _tinted(mask, color):
    out = mask.copy()
    out.fill(tuple(color) + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _gradient(size, top, bottom):
    g = pygame.Surface(size, pygame.SRCALPHA)
    h = max(1, size[1] - 1)
    for y in range(size[1]):
        pygame.draw.line(g, _mix(top, bottom, y / h) + (255,), (0, y), (size[0], y))
    return g


def _flat(surf, rect, mask_fn, color, inset=0):
    surf.blit(_tinted(_shape(rect.size, mask_fn, inset), color), rect.topleft)


def _panel(surf, rect, mask_fn, top, bottom, hi, lo, edge=2, raised=True):
    """One lit object. `hi`/`lo` are its lit and shaded rim; `raised` picks which
    lands on the top-left, and that single choice is the whole boss-vs-recess
    distinction. See the module CONTRACT."""
    near, far = (hi, lo) if raised else (lo, hi)
    mask = _shape(rect.size, mask_fn)
    lay = pygame.Surface(rect.size, pygame.SRCALPHA)
    lay.blit(_tinted(mask, near), (0, 0))
    lay.blit(_tinted(mask, far), (edge, edge))
    face = _gradient(rect.size, top, bottom)
    face.blit(_shape(rect.size, mask_fn, edge), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    lay.blit(face, (0, 0))
    lay.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(lay, rect.topleft)


# ── ON / OFF lettering ────────────────────────────────────────────────────────
#
# Drawn, not typeset. The cap lettering is engraved industrial signage: uniform
# stroke, flat-sided O, short middle arm on the F. None of the four Latin faces
# this project ships draws that O — Helvetica and Frutiger are both round — and
# a squarish grotesque is a new font file, a THIRD-PARTY.md entry and a licence
# question for four characters. Three stroke shapes cost less and land closer.


def _draw_glyph(dst, ch, rect, stroke, color):
    """One letter, built from strokes at 4x and downsampled into `rect`.

    Every pixel carries `color` and varies only in ALPHA — including the erased
    counter of the O. Downsampling a shape whose transparent pixels are black
    fringes the edges dark, which on near-white ink over a black cap is the one
    place it would show.
    """
    w, h, t = rect.w * _SS, rect.h * _SS, max(1, stroke * _SS)
    ink, void = tuple(color) + (255,), tuple(color) + (0,)
    big = pygame.Surface((w, h), pygame.SRCALPHA)
    big.fill(void)
    if ch == "O":
        r = round(w * _TUNEABLES_BELL_GLYPH["glyph_o_round"])
        pygame.draw.rect(big, ink, (0, 0, w, h), border_radius=r)
        pygame.draw.rect(big, void, (t, t, w - 2 * t, h - 2 * t), border_radius=max(0, r - t))
    elif ch == "N":
        pygame.draw.rect(big, ink, (0, 0, t, h))
        pygame.draw.rect(big, ink, (w - t, 0, t, h))
        pygame.draw.polygon(big, ink, [(0, 0), (t, 0), (w, h), (w - t, h)])
    elif ch == "F":
        pygame.draw.rect(big, ink, (0, 0, t, h))
        pygame.draw.rect(big, ink, (0, 0, w, t))
        bar = _TUNEABLES_BELL_GLYPH
        pygame.draw.rect(
            big,
            ink,
            (0, round(h * bar["glyph_f_bar_y"]), round(w * bar["glyph_f_bar_w"]), t),
        )
    dst.blit(pygame.transform.smoothscale(big, rect.size), rect.topleft)


def _render_word(word, color):
    g = _TUNEABLES_BELL_GLYPH
    cap_h = g["glyph_h"]
    stroke = max(2, round(cap_h * g["glyph_stroke"]))
    gap = max(1, round(cap_h * g["glyph_gap"]))
    cw = max(2 * stroke + 1, round(cap_h * g["glyph_w"]))
    widths = [cw] * len(word)
    surf = pygame.Surface((sum(widths) + gap * (len(word) - 1), cap_h), pygame.SRCALPHA)
    x = 0
    for ch, cw in zip(word, widths):
        _draw_glyph(surf, ch, pygame.Rect(x, 0, cw, cap_h), stroke, color)
        x += cw + gap
    return surf


# ── elements ──────────────────────────────────────────────────────────────────


def _box_rect():
    b = _TUNEABLES_BELL_BOX
    return pygame.Rect(b["box_x"], b["box_y"], b["box_w"], b["box_h"])


def _draw_body(surf):
    """Cast shadow, contour, and the outer body — the level the screws sit on."""
    b, p = _TUNEABLES_BELL_BOX, _TUNEABLES_BELL_PALETTE
    box, r = _box_rect(), b["box_radius"]
    off, c = b["box_shadow_off"], b["box_contour"]
    _flat(surf, box.move(off, off), _mask_rrect(r), p["shadow_color"])
    _flat(surf, box.inflate(2 * c, 2 * c), _mask_rrect(r + c), p["contour_color"])
    _panel(
        surf,
        box,
        _mask_rrect(r),
        p["body_top_color"],
        p["body_bot_color"],
        p["body_hi_color"],
        p["body_lo_color"],
        edge=b["box_edge"],
    )


def _draw_screws(surf):
    s, p = _TUNEABLES_BELL_SCREW, _TUNEABLES_BELL_PALETTE
    box = _box_rect()
    r, boss = s["screw_r"], s["screw_boss_r"]
    for i, (cx, cy) in enumerate(
        (
            (box.left + s["screw_inset_x"], box.top + s["screw_inset_y"]),
            (box.right - s["screw_inset_x"], box.top + s["screw_inset_y"]),
            (box.left + s["screw_inset_x"], box.bottom - s["screw_inset_y"]),
            (box.right - s["screw_inset_x"], box.bottom - s["screw_inset_y"]),
        )
    ):
        # The head sits in a recess, so its rim is lit bottom-right; the head
        # itself is a boss, lit top-left. Two panels, opposite `raised`.
        _panel(
            surf,
            pygame.Rect(cx - boss, cy - boss, 2 * boss, 2 * boss),
            _mask_rrect(boss),
            p["screw_well_color"],
            p["screw_well_color"],
            p["body_hi_color"],
            p["body_lo_color"],
            edge=1,
            raised=False,
        )
        _panel(
            surf,
            pygame.Rect(cx - r, cy - r, 2 * r, 2 * r),
            _mask_rrect(r),
            p["screw_hi_color"],
            p["screw_lo_color"],
            p["screw_hi_color"],
            p["screw_lo_color"],
            edge=1,
        )
        # Each head at its own angle — four identical screws read as printed.
        a = math.radians(s["screw_tilt"] * (1 + i * 0.9))
        half = s["screw_slot_len"] / 2
        for da in (0.0, math.pi / 2):
            dx, dy = math.cos(a + da) * half, math.sin(a + da) * half
            pygame.draw.line(
                surf,
                p["screw_slot_color"],
                (cx - dx, cy - dy),
                (cx + dx, cy + dy),
                s["screw_slot_w"],
            )


def _draw_plateau(surf):
    """The raised central face, and the lit ramp stepping up to it.

    Drawn AFTER the screws: the plateau is nearer the viewer, so where the two
    meet it is the plateau that occludes.
    """
    f, p = _TUNEABLES_BELL_FACE, _TUNEABLES_BELL_PALETTE
    box = _box_rect()
    face = box.inflate(-2 * f["face_inset"], -2 * f["face_inset"])
    ramp = f["face_ramp"]
    # The step itself: an octagon `ramp` px proud of the plateau on every side,
    # so what shows around the plateau is the sloped face of the step — bright
    # where it tilts into the light, shaded where it tilts away.
    _panel(
        surf,
        face.inflate(2 * ramp, 2 * ramp),
        _mask_octagon(f["face_chamfer"] + ramp),
        p["ramp_color"],
        p["face_bot_color"],
        p["ramp_color"],
        p["face_lo_color"],
        edge=1,
    )
    _panel(
        surf,
        face,
        _mask_octagon(f["face_chamfer"]),
        p["face_top_color"],
        p["face_bot_color"],
        p["face_hi_color"],
        p["face_lo_color"],
        edge=f["face_edge"],
    )


def _draw_plate(surf):
    t, p = _TUNEABLES_BELL_PLATE, _TUNEABLES_BELL_PALETTE
    box = _box_rect()
    x = box.x + (box.w - t["plate_w"]) // 2
    frame = pygame.Rect(x, box.y + t["plate_top"], t["plate_w"], t["plate_h"])
    _panel(
        surf,
        frame,
        _mask_rrect(t["plate_radius"] + 1),
        p["plate_top_color"],
        p["plate_bot_color"],
        p["plate_hi_color"],
        p["plate_lo_color"],
        edge=t["plate_edge"],
        raised=False,
    )
    font = lcd_font("ShinGoPr6N-Medium.otf", t["plate_text_size"], draws=lit(_FACE_LABEL))
    ink = font.render(_FACE_LABEL, True, p["plate_ink_color"])
    surf.blit(ink, ink.get_rect(center=(frame.centerx, frame.centery + t["plate_text_dy"])))


def _well_rect():
    c = _TUNEABLES_BELL_CAVITY
    box = _box_rect()
    return pygame.Rect(box.x + (box.w - c["cavity_w"]) // 2, box.y + c["cavity_top"], c["cavity_w"], c["cavity_h"])


def _draw_cavity(surf):
    c, p = _TUNEABLES_BELL_CAVITY, _TUNEABLES_BELL_PALETTE
    well = _well_rect()
    collar = well.inflate(2 * c["collar_w"], 2 * c["collar_w"])
    _panel(
        surf,
        collar,
        _mask_rrect(c["collar_radius"]),
        p["collar_top_color"],
        p["collar_bot_color"],
        p["collar_hi_color"],
        p["collar_lo_color"],
        edge=c["collar_edge"],
    )
    _panel(
        surf,
        well,
        _mask_rrect(c["cavity_radius"]),
        p["well_top_color"],
        p["well_bot_color"],
        p["well_hi_color"],
        p["well_lo_color"],
        edge=c["well_edge"],
        raised=False,
    )


def _opening_rect(rect):
    """The hole in the casing. A pressed cap sits FLUSH in it, so the opening is
    exactly the cap plus a clearance ring — NOT a well the cap drops into."""
    c = _TUNEABLES_BELL_CAP
    return rect.move(0, c["cap_rise"]).inflate(2 * c["cap_bezel"], 2 * c["cap_bezel"])


def _draw_cap(surf, rect, label, tones, pressed):
    """One button cap in its opening.

    # CONTRACT: pressed means FLUSH WITH THE CASING, never below it. The cap
    # travels exactly `cap_rise` — the same distance it stood proud — so its
    # face lands level with the surface around it and the opening is covered.
    # There is no well and nothing overhangs it, which is why the pressed cap
    # is not shaded: nothing is casting on it.
    #
    # In-versus-out is the box's ONLY display — it has no lamp, so the whole
    # difference has to survive on a near-black cap. Three cues carry it, and
    # each is the same top-left light the rest of the box obeys:
    #   1. proud, a band of THICKNESS shows under the face and the cap throws a
    #      shadow onto the casing; flush, both are gone
    #   2. proud, the cap's lit rim is bright; flush, there is no relief left to
    #      catch light, so the rim collapses to a hairline seam (`cap_seam`)
    #   3. the face itself sits `cap_rise` lower on the panel
    # Never invert the rim to fake depth: `raised=False` turns the cap into a
    # dent, which is subtly wrong in a way that is hard to name and impossible
    # to unsee. A button pushed in is still a convex slab.
    # Weakening any one of these is what makes `ready` and `ringing` the same
    # picture — check the state strip after touching this, never one state.
    """
    c, p = _TUNEABLES_BELL_CAP, _TUNEABLES_BELL_PALETTE
    top, bottom, hi, lo = tones
    rise = c["cap_rise"]
    _panel(
        surf,
        _opening_rect(rect),
        _mask_rrect(c["cap_radius"] + c["cap_bezel"]),
        p["socket_top_color"],
        p["socket_bot_color"],
        p["socket_hi_color"],
        p["socket_lo_color"],
        edge=c["cap_seam"],
        raised=False,
    )

    face = rect.move(0, rise) if pressed else rect
    if pressed:
        # Flush: no thickness, no cast shadow, and a seam instead of a bevel.
        # The face keeps its own lighting — level with the casing, it is lit
        # exactly as the casing is.
        k = c["cap_press_darken"]
        hi = lo = p["cap_seam_color"]
        top, bottom = _mix(top, (0, 0, 0), k), _mix(bottom, (0, 0, 0), k)
    else:
        drop = c["cap_shadow_off"]
        _flat(
            surf,
            pygame.Rect(face.x, face.y + drop, face.w, face.h + rise).move(drop, 0),
            _mask_rrect(c["cap_radius"]),
            p["cap_shadow_color"],
        )
        _flat(
            surf,
            pygame.Rect(face.x, face.y, face.w, face.h + rise),
            _mask_rrect(c["cap_radius"]),
            _mix(lo, top, c["cap_wall_mix"]),
        )
    _panel(
        surf,
        face,
        _mask_rrect(c["cap_radius"]),
        top,
        bottom,
        hi,
        lo,
        edge=c["cap_seam"] if pressed else c["cap_edge"],
    )

    ink = _render_word(label, p["cap_ink_color"])
    surf.blit(ink, ink.get_rect(center=(face.centerx, face.centery + c["cap_text_dy"])))


def render(state: BellState) -> pygame.Surface:
    """The whole box for one state, at 1x. The window scales this; the stream
    publishes it. Cheap enough to call per state change, never per frame."""
    p = _TUNEABLES_BELL_PALETTE
    surf = pygame.Surface(BELL_CANVAS)
    surf.fill(p["canvas_color"])
    _draw_body(surf)
    _draw_screws(surf)
    _draw_plateau(surf)
    _draw_plate(surf)
    _draw_cavity(surf)

    rects = cap_rects()
    _draw_cap(
        surf,
        rects["on"],
        "ON",
        (p["on_top_color"], p["on_bot_color"], p["on_hi_color"], p["on_lo_color"]),
        pressed=state.on_latched or state.on_flash,
    )
    _draw_cap(
        surf,
        rects["off"],
        "OFF",
        (p["off_top_color"], p["off_bot_color"], p["off_hi_color"], p["off_lo_color"]),
        pressed=state.off_flash,
    )
    return surf

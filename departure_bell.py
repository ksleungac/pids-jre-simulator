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

Reference anchors, as fractions of the enclosure so they survive the canvas
being resized. Three photographs, and they are NOT one box: the in-situ pair
(``sta-bell.jpg`` 387x516 below-left, and a later high-resolution near-straight-on
shot of the same casting) carry the chamfered corners this file draws, while a
third — a straight-on product shot of a grey casting — has rounded corners and
is used only where it can settle a proportion the other two cannot.

    enclosure   x 82..302, y 82..458   220 x 376  ->  1 : 1.71
    label plate                        0.630 w  x 0.112 h, top at 0.153
    cavity collar                      0.653 w  x 0.622 h, top at 0.283
    ON  cap     y 218..296             0.324 w (square), top at 0.380
    OFF cap     x 148..224, y 326..401 same size  ->  the caps are equal
    cap gap                            0.33 of a cap

Anything measured off a below-left shot is compressed along the VERTICAL, which
is why the cap gap reads 0.19 of a cap there against 0.31 straight on. Sizes
transfer from it; placements down the box do not. Read from the straight-on
shots instead:

    well floor            0.72 of the lit body face, SAME hue — one casting
    socket ring           0.50, and only because a proud cap shadows it
    legend cap-height     0.377 of the cap (0.378 ON / 0.375 OFF)
    legend stroke         0.12 of that height (0.115 ON / 0.122 OFF)
    legend word width     0.680 of the cap for ON, 0.795 for OFF

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
BELL_CANVAS = (192, 290)

# fmt: off
_TUNEABLES_BELL_BOX = {
    "box_x":              8,   # canvas margin — leaves room for the cast shadow
    "box_y":              8,
    "box_w":            176,
    "box_h":            274,   # 1 : 1.56, against 1 : 1.65 measured straight-on
                               # and 1 : 1.71 from below (a shot from under the
                               # box stretches it, so the taller figure is the
                               # distorted one). Both references still read
                               # taller than this; the author's eye is what set
                               # it, and the height was reduced twice.
                               #
                               # The height is a BUDGET, and it only balances
                               # because these seven add up to it:
                               #
                               #   plate_top                 30   margin
                               #   plate_h                   34
                               #   plate -> collar gap        9   (see below)
                               #   collar_w                  16
                               #   cavity_h                 155
                               #   collar_w                  16
                               #   bottom margin             14
                               #
                               # Narrowing the well does NOT change this total:
                               # collar_w is pinned by collar+well == plate_w,
                               # so it grows by exactly what cavity_w loses, and
                               # cavity_h moves with cavity_w to keep the floor
                               # around the caps square. The two cancel.
                               #
                               # cavity_h has a floor: the cap group is
                               # 2*cap_size + the gap = 133, and it needs pad
                               # either side. Shortening the box past about 255
                               # means shrinking the caps, which are pinned to
                               # box_w by measurement — so that is where this
                               # stops being a free parameter.
    "box_chamfer":       15,   # the outer body is CUT at all four corners, like
                               # the plateau — both in-situ references show a
                               # 45 degree facet there, not a radius. Drawing it
                               # round makes the silhouette disagree with the
                               # plateau it encloses, which is the one place the
                               # three-level casting is legible at all.
    "box_edge":           2,   # lit/dark rim that makes the body read as raised
    "box_contour":        1,   # dark outline so the sprite reads off any window
    "box_shadow_off":     4,   # how far the cast shadow falls, down-right
}

_TUNEABLES_BELL_FACE = {
    "face_inset":         7,   # plateau, in from the body edge — the screw shelf
    "face_chamfer":      33,   # corner cut; must clear the screw bosses. The
                               # binding constraint is the RAMP, one step
                               # further out than the plateau: with the screw
                               # centre at inset s and a boss of r, the cut
                               # needs 2*face_inset + chamfer - 2*face_ramp
                               # - 2*s comfortably over r*sqrt(2).
    "face_ramp":          2,   # lit step from shelf up to plateau
    "face_edge":          2,
}

_TUNEABLES_BELL_SCREW = {
    "screw_inset_x":     15,   # centre, in from the body edge — on the shelf.
    "screw_inset_y":     15,   # Moving these inboard costs plateau: the corner
                               # cut has to grow with them or the plateau lands
                               # on the boss. face_chamfer is that number.
    "screw_r":            6,   # head radius (0.068 of box w across)
    "screw_boss_r":       9,   # recess the head sits in
    "screw_slot_w":       3,   # cross-slot stroke
    "screw_slot_len":     9,   # cross-slot arm span
    "screw_tilt":        18,   # degrees — a driven screw never lands square
}

_TUNEABLES_BELL_PLATE = {
    "plate_w":          111,   # 0.630 of box w
    "plate_h":           34,   # 0.112 of box h
    "plate_top":         30,   # below the box top (0.109) — clears the screws
    "plate_radius":       2,
    "plate_edge":         1,   # recessed border the paper sits in
    "plate_frame":        3,   # casting margin visible around the paper card
    "plate_seam":         1,   # dark line where the card meets that margin
    "plate_text_size":   20,   # sized for the label's WIDTH, then squashed back
    "plate_text_squash":0.90,  # to height. Squashing the render is the lever
                               # that widens the letterforms WITHOUT thickening
                               # the stroke, which a heavier weight would have
                               # done. The reference measures 0.87 of the card
                               # wide; that came out too wide by eye and this
                               # sits at 0.76, so the photo is the ceiling here
                               # rather than the target.
    "plate_text_dy":      0,   # nudge the label off optical centre
}

_TUNEABLES_BELL_CAVITY = {
    # The well is sized so the floor showing around the cap group is the SAME on
    # all four sides — 9px. That is not four independent numbers; measure to the
    # SOCKET (the hole in the casing), because the cap is only a part sitting in
    # it, and the socket is the cap rect shifted down by cap_rise and grown by
    # cap_bezel. So:
    #
    #   cavity_w = cap_size + 2*cap_bezel              + 2*pad = 61 + 18 =  79
    #   cavity_h = cap group + cap_rise + 2*cap_bezel  + 2*pad = 137 + 18 = 155
    #
    # where the cap group is 2*cap_size + the gap = 133. Left as literals so the
    # calibration editor can drag them; re-derive both if any cap number moves.
    #
    # Note the shift means the visible floor ABOVE the cap face reads cap_rise -
    # cap_bezel px tighter than the figure below it, because the face stands
    # proud of its own hole. Equal holes, not equal-looking gaps.
    "cavity_w":          79,   # the WELL opening; the collar adds collar_w each side
    "cavity_h":         155,
    "cavity_top":        89,   # below the box top. What this really sets is the
                               # gap to the PLATE, and the gap is to the collar
                               # crest, not to the well: the lip stands collar_w
                               # proud of cavity_top, so at cavity_top 88 with a
                               # 13px lip the plate's bottom edge and the bezel
                               # were 1px apart and read as touching. The clear
                               # air is cavity_top - collar_w - (plate_top +
                               # plate_h) = 9. Move either one and re-derive it.
    "cavity_radius":     20,
    "collar_w":          16,   # raised lip: 79 + 2*16 = 111, which is EXACTLY
                               # plate_w. On the reference the label paper spans
                               # 230px and the bezel 232 with their edges in
                               # line, so the two recesses read as one column
                               # down the casting rather than two unrelated
                               # windows. Keep them equal if either moves.
                               # The lip is also a WIDE soft roll, so it needs
                               # face to gradient across; a narrow lip with a
                               # hard rim reads as an engraved ring instead.
    "collar_radius":     28,
    "collar_edge":        4,   # a WIDE rim, not a line. At 1-2 px the lit side
                               # thins to a hairline around the corner arc and
                               # reads as a scratch floating on the plateau
    "well_edge":          4,   # sunken rim — dark at top-left, lit at bottom-right
}

_TUNEABLES_BELL_CAP = {
    "cap_size":          57,   # square (0.324 of box w)
    "cap_radius":         5,
    "on_top":            95,   # below the box top — cap group centred in the well
    "off_top":          171,   # gap of 19 = 0.33 of a cap
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
    "cap_gloss_inset":    3,   # moulded caps are slightly domed: one lit line
    "cap_gloss_mix":   0.28,   # inside the top edge, toward the cap's own hi.
                               # Same top-left light as everything else — this
                               # is the dome catching it, not a new source.
    "cap_text_relief":    1,   # the lettering stands proud of the cap face, so
                               # it carries an under-edge down-right of the ink
    "cap_wall_mix":    0.30,   # side wall, toward the face: a bottom-facing wall
                               # is darker than its face, but on a near-black cap
                               # "darker" has nowhere to go — pure black merges
                               # the two into one tall slab
    "cap_text_dy":        0,
}

_TUNEABLES_BELL_GLYPH = {
    "glyph_h":           21,   # cap height of ON / OFF, in px. Sized against the
                               # CAP, not for legibility: the word runs wide and
                               # sits short, so the left/right margin is about
                               # half the top/bottom one. That relation is what
                               # the reference has, and what these numbers encode
                               # — check it survives before nudging the widths.
                               # 0.377 of the cap, measured on both legends of
                               # the straight-on reference (0.378 / 0.375).
    "glyph_stroke":    0.12,   # stroke weight, as a fraction of cap height —
                               # measured 0.115 (ON) and 0.122 (OFF). At
                               # glyph_h 21 this rounds to a 3px stroke. The
                               # earlier 0.19 read as a bold face rather than
                               # engraved signage; 0.12 is the reference.
                               #
                               # Widths and tracking are PER WORD, not one pair
                               # for the box. The real legends are each set to
                               # fill the cap, so the two-letter ON is drawn
                               # wider and looser than the three-letter OFF —
                               # measured 0.680 vs 0.795 of the cap width. Within
                               # a word the cell IS uniform (34/34 px for ON,
                               # 29/26/28 for OFF) and each glyph is DRAWN to
                               # fill its width rather than centred in a cell, so
                               # a narrow letter never floats inside a wide slot.
                               # Fractions of glyph_h, like the rest.
    "glyph_w_on":      0.76,
    "glyph_gap_on":    0.33,
    "glyph_w_off":     0.62,
    "glyph_gap_off":   0.16,
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
    "ramp_color":         (224, 223, 213),   # the lit step up to the plateau.
                                             # Kept close to the body: a bright
                                             # ramp beside the plateau's own lit
                                             # rim draws the step as two hard
                                             # lines, and the casting has one
                                             # soft roll there.
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
    # The label is a paper card DROPPED INTO a shallow casting recess, so a
    # margin of casting shows all round it and a seam separates the two. One
    # panel whose face was the paper had the card meeting the body with no edge.
    "plate_frame_top_color": (152, 151, 141),
    "plate_frame_bot_color": (172, 171, 159),
    "plate_seam_color":   ( 84,  83,  77),
    "collar_hi_color":    (240, 239, 231),   # the lip is a rolled edge: it takes
    "collar_lo_color":    (150, 148, 138),   # a brighter catch than a flat face
    # The lip must sit clear of the PLATEAU it stands on. At (209,208,196) it
    # was within 2 of face_top_color, so its face vanished into the background
    # and all that survived was its rim — a light line with nothing attached to
    # it. A raised object needs its own face tone, not just a lit edge.
    "collar_top_color":   (222, 221, 209),
    "collar_bot_color":   (198, 197, 184),
    # The well is the SAME CASTING as the body, in shadow — not a dark liner.
    # Measured on the straight-on reference: the floor between the caps reads
    # (121,114,109) against a lit body face of (163,163,152), so 0.72 of it, at
    # the same hue. The socket ring sits lower again (0.5) only because a proud
    # cap shadows it. Drawing the well near-black is what made the middle of the
    # box read as a different material — the author's first note on the photo.
    "well_hi_color":      (206, 205, 193),
    "well_lo_color":      (104, 103,  95),
    "well_top_color":     (133, 132, 123),
    "well_bot_color":     (151, 150, 140),
    "socket_hi_color":    (150, 149, 139),
    "socket_lo_color":    ( 66,  65,  60),
    "socket_top_color":   ( 92,  91,  84),
    "socket_bot_color":   (116, 115, 106),
    "cap_shadow_color":   ( 74,  73,  67),
    "cap_seam_color":     ( 56,  55,  51),   # clearance gap around a flush cap
    # The legends are moulded SILVER-GREY, not white — sampled (137,137,142)
    # against an ON face of (62,62,64). Lifted here like every other tone, but
    # the ink must stay short of white or the relief under it cannot show.
    "cap_ink_color":      (206, 206, 208),
    "cap_ink_relief_color": ( 18,  18,  18),  # under-edge of the raised lettering
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
    # Per-word metrics; the box carries exactly these two legends. An unknown
    # word falls back to OFF's tighter setting, which is the safe direction —
    # it can only come out narrower than the cap, never overflow it.
    key = word.lower() if word.lower() in ("on", "off") else "off"
    gap = max(1, round(cap_h * g[f"glyph_gap_{key}"]))
    cw = max(2 * stroke + 1, round(cap_h * g[f"glyph_w_{key}"]))
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
    box, ch = _box_rect(), b["box_chamfer"]
    off, c = b["box_shadow_off"], b["box_contour"]
    _flat(surf, box.move(off, off), _mask_octagon(ch), p["shadow_color"])
    _flat(surf, box.inflate(2 * c, 2 * c), _mask_octagon(ch + c), p["contour_color"])
    _panel(
        surf,
        box,
        _mask_octagon(ch),
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
        # Supersampled like every other shape here: pygame's line width is not
        # antialiased, so a stroke this thick drawn off-axis lands as a blob of
        # stair-steps rather than a cross recess.
        a = math.radians(s["screw_tilt"] * (1 + i * 0.9))
        d = 2 * r
        big = pygame.Surface((d * _SS, d * _SS), pygame.SRCALPHA)
        mid, half = d * _SS / 2, s["screw_slot_len"] * _SS / 2
        for da in (0.0, math.pi / 2):
            dx, dy = math.cos(a + da) * half, math.sin(a + da) * half
            pygame.draw.line(
                big,
                tuple(p["screw_slot_color"]) + (255,),
                (mid - dx, mid - dy),
                (mid + dx, mid + dy),
                s["screw_slot_w"] * _SS,
            )
        surf.blit(pygame.transform.smoothscale(big, (d, d)), (cx - r, cy - r))


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
    # Three levels, outside in: the casting recess, the seam, the paper card.
    _panel(
        surf,
        frame,
        _mask_rrect(t["plate_radius"] + t["plate_frame"]),
        p["plate_frame_top_color"],
        p["plate_frame_bot_color"],
        p["plate_hi_color"],
        p["plate_lo_color"],
        edge=t["plate_edge"],
        raised=False,
    )
    seam = frame.inflate(-2 * (t["plate_frame"] - t["plate_seam"]), -2 * (t["plate_frame"] - t["plate_seam"]))
    _flat(surf, seam, _mask_rrect(t["plate_radius"] + t["plate_seam"]), p["plate_seam_color"])
    card = frame.inflate(-2 * t["plate_frame"], -2 * t["plate_frame"])
    _panel(
        surf,
        card,
        _mask_rrect(t["plate_radius"]),
        p["plate_top_color"],
        p["plate_bot_color"],
        p["plate_hi_color"],
        p["plate_lo_color"],
        edge=t["plate_edge"],
    )
    font = lcd_font("ShinGoPr6N-Medium.otf", t["plate_text_size"], draws=lit(_FACE_LABEL))
    ink = font.render(_FACE_LABEL, True, p["plate_ink_color"])
    squash = t["plate_text_squash"]
    if squash != 1.0:
        ink = pygame.transform.smoothscale(ink, (ink.get_width(), max(1, round(ink.get_height() * squash))))
    surf.blit(ink, ink.get_rect(center=(card.centerx, card.centery + t["plate_text_dy"])))


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

    # The dome: one lit line inside the top edge, following the cap's corners.
    # Drawn as the top slice of a rounded rect so it curves in at the corners
    # rather than running square across them.
    gi = c["cap_gloss_inset"]
    gloss = face.inflate(-2 * gi, -2 * gi)
    if gloss.w > 0 and gloss.h > 0:
        band = pygame.Surface((gloss.w, gloss.h), pygame.SRCALPHA)
        _flat(
            band,
            pygame.Rect(0, 0, gloss.w, gloss.h),
            _mask_rrect(max(0, c["cap_radius"] - gi)),
            _mix(top, hi, c["cap_gloss_mix"]),
        )
        keep = max(1, c["cap_edge"] - 1)
        surf.blit(band, gloss.topleft, pygame.Rect(0, 0, gloss.w, keep))

    centre = (face.centerx, face.centery + c["cap_text_dy"])
    relief = c["cap_text_relief"]
    if relief and not pressed:
        under = _render_word(label, p["cap_ink_relief_color"])
        surf.blit(under, under.get_rect(center=(centre[0] + relief, centre[1] + relief)))
    ink = _render_word(label, p["cap_ink_color"])
    surf.blit(ink, ink.get_rect(center=centre))


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

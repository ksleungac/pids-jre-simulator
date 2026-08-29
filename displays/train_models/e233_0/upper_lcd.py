# SPDX-License-Identifier: MIT
"""E233-0 (中央線快速) Upper LCD.

Built element by element against ``docs/wip/WIP_e233_0_display.md`` § 8, which is
the spec. Only elements whose drill-down has happened are drawn; the rest are
explicit stubs naming what is still open, so a half-built upper reads as
half-built rather than as broken.

  drawn   train type (§ 8.4), destination, plate, station name, prefix,
          clock, station-code badge (§ 8.5)
  stub    car number

MODE HANDLING. v1 is Japanese only: all three ``DisplayMode`` values resolve to
the SAME ``JapaneseDisplay`` instance (WIP § 4, author 2026-08-23). One instance
rather than three, so a mode flip cannot re-trigger per-instance animation state.
The furigana and English renderers drop in later with no structural change.
"""

import math

import pygame

from app_paths import load_json_relative
from displays.base import DisplayMode, ModeCycler
from displays.utils import clip, draw_station_code_badge, draw_text_given_width
from font_atlas import DESTINATIONS, STATION_NAMES, STATION_READINGS, at, lcd_font, lit

from displays.train_models.e233_0 import (
    S_WIDTH,
    UPPER_HEIGHT,
    UPPER_BG,
    RULE_GREY,
    DIVIDE_RULE_H,
    BORDER_W,
    PLATE_WHITE,
    PLATE_BORDER,
)

# =============================================================================
# Region rects — one per element, in the upper band's own coordinates (y is
# measured from the top of the SCREEN, which is also the top of this band).
#
# CONTRACT: each draw method clips to its rect, so a glyph cannot escape into a
# neighbour's territory. Same guarantee as E235 — see docs/DISPLAY.md.
# A rect is added when its element's drill-down settles it, never before.
# =============================================================================

# Wide enough for the STACK, which is not bounded by the 2-slot box: a
# 5-character row at long_font_size 18 runs 90px from box_x. Still well
# clear of the plate (x=120) and the destination (x=135).
TRAIN_TYPE_RECT = pygame.Rect(8, 0, 104, 90)

# The destination row is the widest clear span on the display: measured on both
# references, nothing else carries ink between x 85 and x 588 at this height, so
# a long destination has room to run without a neighbour to collide with. The
# rect stops well short of that anyway — it is a clip, not a layout bound.
DESTINATION_RECT = pygame.Rect(130, 0, 330, 40)

# The plate. Synced from `_TUNEABLES_STATION_PLATE` every frame so the editor can
# drag it; the literal here is only what it starts at. The station name clips to
# the plate's INTERIOR, which is this rect inset by the border.
STATION_PLATE_RECT = pygame.Rect(120, 35, 398, 103)

# The prefix sits in the corner the train type leaves free: the type's stack
# bottoms out at y 90 and the plate starts at x 120, so this rect is bounded by
# neither.
PREFIX_RECT = pygame.Rect(4, 100, 116, 49)

# The clock, bottom right. Synced from its tuneables like the plate.
CLOCK_RECT = pygame.Rect(554, 106, 79, 32)

# The station-code badge, inside the plate at its left end. Synced from
# `_TUNEABLES_STATION_BADGE` every frame like the plate and the clock.
BADGE_RECT = pygame.Rect(134, 64, 58, 57)

# =============================================================================
# Train type — WIP § 8.4
#
# FOUR BOXES (author, 2026-08-23). The block is four fixed slots; characters go
# into them in reading order, top row first, left to right, and a slot with no
# character stays empty. Nothing here is computed from the text — a 2-character
# type (chuo/1654T is 快速) fills the top row and leaves the bottom row empty.
#
# Measured off `full-takao-stopping-ja.png` (通勤特快), ratios converted to this
# model's 640x149 upper band. The row gap is 5x the column gap: this is two
# lines of text set tight, not a symmetric grid of four boxes.
# =============================================================================
# fmt: off
_TUNEABLES_TRAIN_TYPE = {
    "box_x":         12,  # x of the left column's left edge   (measured x/W 0.0186)
    "box_y":          4,  # y of the top row's top edge        (ink lands at y/UH 0.026)
    "cell_w":        36,  # slot width                         (measured 0.0559 W)
    "cell_h":        36,  # slot height                        (measured 0.2378 UH)
    "col_gap":        1,  # between the two columns            (measured 0.0020 W)
    "row_gap":        5,  # between the two rows; row PITCH is the figure that
                          # was matched to the ref (0.2722 UH = 41px), not this
    "font_size":     38,  # sized so ink height matches the ref; see _TYPE_FACE
    "long_font_size": 18, # the ONE size every STACK row is drawn at, natural
                          # spacing, no compression (author, 2026-08-23). At 18
                          # a 5-char tail is 90px, past the 73px slot box — so
                          # TRAIN_TYPE_RECT is sized for the stack, not the box.
    "long_line_gap":  2,  # px of clear INK between the stack's two rows. The
                          # 41px cell pitch is calibrated for 38px glyphs, so
                          # reusing it here would leave a hole.
    "outline_w":    2.0,  # white halo total EXTENT beyond the ink, px — float.
                          # Confirmed by eye against the reference at 9x
                          # (author, 2026-08-25). Means what it says now the
                          # dilation source is a sharp 4x raster.
    "outline_feather": 2.0,  # px of that extent spent FADING, measured inward
                          # from the outer edge. EQUAL to outline_w here, so
                          # the halo is pure gradient with no solid white core
                          # — which is what the reference measures as.
    "outline_color": (255, 255, 255),
}
# fmt: on

_TYPE_SLOTS = 4  # two rows of two — see the FOUR BOXES note above

# DeBold, chosen against the reference over Heavy / Medium / Light — "the most
# accurate weight for train type" (author, 2026-08-25). It is the Pro cut
# (Adobe-Japan1-4), not Pr6N; renamed from Morisawa's own `A-OTF Shin Go Pro
# DB.otf` so the `ShinGo` family prefix covers it in both `ATLAS_FACES` and
# `.gitignore`, and NOT renamed to `Pr6N`, which would misstate the glyph set.
#
# In one place because it is a design choice rather than a per-call argument,
# and because a comparison harness needs to vary it without reaching into the
# renderer.
_TYPE_FACE = "ShinGoPro-DeBold.otf"

# EVERY route draws its type, the Yamanote included (author, 2026-08-25). An
# earlier pass suppressed it there on the reasoning that an all-stations line's
# designation carries no information; the author reversed that. `route.json`
# already records 各駅停車 for it, so there is nothing to special-case — the type
# and its colour come from the data like every other route's.

# =============================================================================
# Types longer than four characters — the box never grows
#
# `快速アクティー` (7), `快速ラビット` (6) and `快速アーバン` (6) ship on other
# lines and reach this model only through an out-of-spec route. The brief
# (author, 2026-08-23) is: stay inside the four-character box, shrinking the
# text is allowed, keep the feel of the 2x2, and the characters need NOT all be
# one size.
#
# So: always two rows in the same two places. A row of one or two characters
# fills the fixed slots at `font_size`, unchanged. A row of MORE than two is
# drawn as one run at `long_font_size` — ONE constant size, whatever the row
# holds — laid out to the full box width by `draw_text_given_width`, which
# compresses HORIZONTALLY at unchanged height. So the second row is the same
# height and the same width for four characters and for five; the fifth is
# absorbed by compression, not by shrinking the row.
#
# Two sizes, not a size per row length (author, 2026-08-23). Deriving a size
# from the character count made a 6-character type render its tail at 19 and a
# 7-character one at 15, so the same element changed height with its content.
#
# WHERE THE SPLIT GOES. Every long type in the corpus is 快速 + a katakana
# nickname, so the split is the ideograph->kana boundary: 快速 / アクティー. That
# earns its keep twice — it is the semantic break, and it leaves 快速 in the
# fixed slots at exactly the size plain 2-character 快速 gets, so the same word
# looks the same on both. A type with no such boundary splits evenly instead.
#
# This is NOT the author's first sketch, which was a 4-2 split (four characters
# on the top row, the rest below). Recorded because it was a real preference:
# 4-2 cuts 快速ラビット into 快速ラビ / ット, mid-word, and shrinks the top row —
# the row that carries the service name — while leaving the tail large. The
# author had already noted 4-2 "does not work" for six characters and deferred
# it. Flip `_split_type` if the sketch is preferred after seeing both.
# =============================================================================

_IDEOGRAPHS = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))
_KANA = ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F))


def _in_ranges(ch: str, ranges) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in ranges)


def _script_cut(text: str) -> int:
    """Index of the first ideograph->kana transition, or 0 if there is none."""
    for i in range(1, len(text)):
        if _in_ranges(text[i - 1], _IDEOGRAPHS) and _in_ranges(text[i], _KANA):
            return i
    return 0


# The type font draws ROW SUBSTRINGS, not only whole types — `快速アーバン`
# reaches it as `快速` and `アーバン`. `cuts=True` declares both halves of every
# two-way split of every declared type, deliberately over-approximating like
# `wrap=` does: it does not depend on WHERE `_split_type` puts the break, so
# changing that rule cannot leave the atlas a case short. A wide declaration
# costs no atlas area — it says what MAY be drawn, and the bake records what is.
_TYPE_DRAWS = at("audio/*/route.json:type", "data/train_types.json:*", cuts=True)


def _split_type(text: str) -> list:
    """Characters per row, top row first. Never more than two rows."""
    n = len(text)
    if n <= 2:
        return [text]
    if n <= _TYPE_SLOTS:
        return [text[:2], text[2:]]
    cut = _script_cut(text)
    if not 0 < cut < n:
        cut = (n + 1) // 2
    return [text[:cut], text[cut:]]


# =============================================================================
# The white outline, and how its width was arrived at
#
# The halo is real, not antialiasing. Sampling rings outward from the red ink in
# both references, the colour runs red -> pink -> near-white -> background, and
# the near-white rings read (254,220,220) with individual pixels at (255,255,255).
# A blend between the ink (213,3,4) and the background (168,177,202) cannot be
# BRIGHTER in red than either endpoint, so a white layer is the only explanation.
#
# COLOUR = pure white, and this is MEASURED rather than assumed. The probe that
# settles it is not "sample the halo" — a thin bright feature under blur never
# reads its own colour, and sampling its interior returns (219,218,222), which
# is thickness masquerading as colour. The probe is a KNOWN WHITE in the same
# image: the next-stop plate reads (254,254,254) in all three references, so the
# capture reproduces flat white faithfully and nothing is darkening whites
# globally. Against that, the halo's brightest pixels reach 253-255 and its
# R channel pins at 255 while G/B lag ~12 — red bleed from the ink beside it,
# not a warm outline. Our render's halo interior measures (255,255,255).
#
# WIDTH — the reference's white extends 1.28px beyond its red, measured on the
# HORIZONTAL axis of the bottom row. Two things make that the one trustworthy
# number here:
#
#   * Same glyphs. 特快 is the bottom row of the reference (通勤特快) AND of
#     chuo/916H (中央特快), so red and silhouette are compared glyph for glyph.
#     The first attempt compared 通勤特快 against 中央特快 and got a
#     contradiction — silhouette unchanged vertically, grown horizontally —
#     because kanji widths are per-glyph.
#   * Horizontal only. Padding the row band far enough to catch the halo above
#     and below also catches the halo of the row ABOVE; not padding clips it.
#     Nothing sits beside the ends of 特快, so that axis is clean. The vertical
#     figure moved between 1.49 and 2.78 depending on the padding — it is not
#     measurable on this block and is not used.
#
# `outline_w` is the halo's total EXTENT beyond the ink, and now delivers it. It
# did NOT mean this before the supersampling change — the old halo dilated a
# blur-upscale, so it spread further than its radius and every number derived
# against it was off. Every figure predating that change has been discarded.
#
# WIDTH IS NOT A "WHITE BEYOND RED" MEASUREMENT, and reading it as one is what
# kept this element wrong for three rounds. That probe classifies each pixel as
# the nearest of {ink, white, background}, so it reports where the halo crosses
# 50% — which lands at 1.28px on the reference and made 1.25 look like a match
# while the two looked nothing alike. The halo is a GRADIENT; a single crossing
# point cannot describe one.
#
# The probe that does is a RADIAL PROFILE — mean whiteness, measured against the
# background rather than by a classifier, binned by distance from the ink. On
# the 640 grid both are drawn on:
#
#            d =        1px    2px    3px
#     reference        0.10   0.53   0.11     <- peaks OUTSIDE the first ring
#     ow 1.25 / f 0.5  0.34   0.07   0.00     <- dead by 2px
#     ow 2.0  / f 2.0  ~0.4   ~0.5   ~0.1
#
# So the reference is both WIDER and SOFTER, and the two are separable: extent is
# where whiteness returns to zero, feather is the slope getting there. Settled at
# 2.0 / 2.0 by eye at 9x (author, 2026-08-25) — feather EQUAL to extent, i.e. no
# solid white core at all, which is what the reference measures as.
#
# SOFTNESS IS A SEPARATE AXIS, and the one that was actually wrong. The old
# construction got its falloff for free from that same blur: 987 halo pixels of
# which 6% reached pure white. Dilating a sharp raster instead gave 597 pixels
# at 27% pure — narrower AND harder, a stuck-on white band. The reference is
# almost all gradient (6px² pure, peaking at 253, never reaching its own colour).
# So the blur was doing two jobs and removing it dropped the load-bearing one.
# `outline_feather` makes that falloff explicit instead of an accident of
# resampling: coverage ramps from 1 to 0 over the outermost `feather` px, so
# softness is authored rather than inherited from whatever the resampler did.
#
# INWARD vs OUTWARD, because it looks inward and is not: stamps composite over
# the glyph's own antialiased edge, so adding a halo VISUALLY THINS the red.
# Our natural glyph is 38.00px tall; with the halo it measures 36.61, and the
# reference's red measures 35.86 against a silhouette that is larger still. Same
# signature, so this outward implementation already reproduces what the
# reference does. Do not re-derive this as an inset-red design.
# =============================================================================


# =============================================================================
# Antialiasing — the WHOLE outlined glyph is built at 4x and resolved once
#
# Everything in this block is drawn supersampled: the font is asked for
# `size * _TYPE_SUPERSAMPLE`, the halo is dilated in those same large pixels,
# the coloured glyph is composited onto the halo while still large, and ONE
# `smoothscale` at the end resolves the result. Area-averaging a 4x raster is
# analytic antialiasing — every edge, and the red/white boundary between them,
# gets its coverage computed rather than rasterised.
#
# Three defects this fixes, in the order they were found:
#
#   1. A POLYGONAL HALO BOUNDARY. Stamping the white glyph at integer offsets
#      can only put the halo edge on whole pixels, so the outer edge is a
#      staircase — most obvious on the diagonals these kanji are full of.
#      Quarter-pixel offsets plus the downscale resolve it into real coverage.
#   2. ACCUMULATED ALPHA. A normal blit composites, so two overlapping
#      antialiased edges give 0.5 + 0.5 = 0.75 rather than 0.5, and the halo
#      comes out thicker and harder than the radius asks for. Dilation is a MAX
#      over the structuring element, so `BLEND_RGBA_MAX` is the correct operator
#      and fixes this exactly.
#   3. A HARD GLYPH EDGE ON A SOFT HALO (author, 2026-08-25 — "jagged edges").
#      The first two were fixed while the halo alone was supersampled: it was
#      resolved to 1x and the coloured glyph then blitted over it at 1x, so the
#      red carried FreeType's own 38px raster — hinted, grid-fitted, and visibly
#      stepped against a halo that no longer was. The red/white boundary is the
#      highest-contrast edge in the element and it was the only one not being
#      antialiased properly. Compositing before the downscale is what makes the
#      two edges one problem, solved once.
#
# COST. A font size is part of the atlas key, so this bakes rasters at 4x size
# for the type glyphs — and ONLY for them, since nothing else in the display
# asks this renderer for a font. The set is small (the characters of every
# declared train type) and the atlas stores alpha coverage, so one baked entry
# still serves both the red fill and the white halo.
# =============================================================================

_TYPE_SUPERSAMPLE = 4


def outlined(core_big: "pygame.Surface", ow: float, feather: float, color) -> "pygame.Surface":
    """Halo a SUPERSAMPLED core and resolve the whole element to 1x.

    `core_big` is the coloured glyph or row already rendered at
    `_TYPE_SUPERSAMPLE` times its final size. What comes back is the finished
    element at 1x, padded by `ceil(ow)` on every side. See the antialiasing note
    above for why the composite happens before the downscale rather than after.

    Surfaces are pre-filled with the halo colour at zero alpha rather than left
    transparent-black: `smoothscale` does not premultiply, so resolving
    white-opaque against black-transparent would pull a grey fringe out of pixels
    that are supposed to be pure white fading out.

    Module-level and public because the lower LCD's 分 is the same construction —
    dark text with a white outline on the route bar (author, 2026-08-27: "text,
    white outline maybe some feathering, like train type display").
    """
    s = _TYPE_SUPERSAMPLE
    bw, bh = core_big.get_size()
    pad_b = int(math.ceil(ow)) * s

    comp = pygame.Surface((bw + 2 * pad_b, bh + 2 * pad_b), pygame.SRCALPHA, 32)
    comp.fill((*color, 0))
    if ow > 0:
        # The glyph's own coverage recoloured to the halo colour: MULT by black
        # zeroes RGB, ADD writes the colour in, and neither touches alpha. Exact
        # for any colour, where a single BLEND_RGB_MAX would only be exact for
        # white — and no second render, so one baked atlas entry still serves
        # both the fill and the halo.
        sil = core_big.copy()
        sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MULT)
        sil.fill((*color, 0), special_flags=pygame.BLEND_RGB_ADD)

        # Grouped by coverage, so a feathered dilation costs one pre-multiplied
        # copy per LEVEL rather than one per offset. The multiply scales alpha
        # only; MAX then keeps the strongest stamp reaching each pixel, which is
        # what makes this a dilation and not an accumulation.
        by_cov: dict = {}
        for dx, dy, cov in _halo_offsets(ow * s, feather * s):
            by_cov.setdefault(cov, []).append((dx, dy))
        for cov, offsets in by_cov.items():
            stamp = sil
            if cov < 1.0:
                stamp = sil.copy()
                stamp.fill((255, 255, 255, int(round(255 * cov))), special_flags=pygame.BLEND_RGBA_MULT)
            for dx, dy in offsets:
                comp.blit(stamp, (pad_b + dx, pad_b + dy), special_flags=pygame.BLEND_RGBA_MAX)
    comp.blit(core_big, (pad_b, pad_b))

    cw, ch = comp.get_size()
    return pygame.transform.smoothscale(comp, (max(1, round(cw / s)), max(1, round(ch / s))))


def _halo_offsets(radius_px: float, feather_px: float, levels: int = 64) -> tuple:
    """`(dx, dy, coverage)` for a FEATHERED max-dilation, in SUPERSAMPLED pixels.

    Euclidean, so the halo is as thick on a diagonal as on a vertical stroke —
    a square structuring element reads as a boxy corner on kanji. The centre is
    included: dilation is a max over the whole disc, and the coloured glyph is
    drawn on top afterwards regardless.

    Coverage is 1 out to `radius - feather` and ramps linearly to 0 at `radius`,
    so the FEATHER EATS INWARD and `outline_w` keeps meaning the halo's total
    extent. Quantised to `levels` steps because each distinct coverage costs one
    pre-multiplied copy of the silhouette. Raising it is nearly free: copies
    are keyed on the coverages actually PRESENT, and the lattice offers only
    as many distinct distances as fit in the feather band either way.
    """
    r = max(0.0, float(radius_px))
    f = max(0.0, float(feather_px))
    n = int(math.floor(r))
    out = []
    for dx in range(-n, n + 1):
        for dy in range(-n, n + 1):
            d = math.hypot(dx, dy)
            if d > r:
                continue
            cov = 1.0 if f <= 0 else min(1.0, (r - d) / f)
            # Round to nearest and DROP anything that rounds away. Flooring at
            # one level instead — which this did — gives every offset in the
            # disc a floor of 1/levels, so the outermost ring becomes a flat
            # low-alpha plateau in the shape of the DIGITAL disc: a faint
            # polygon traced around the glyph, read as "the halo is not uniform
            # on the edges" (author, 2026-08-25). The fade has to be allowed to
            # reach zero or its outer boundary is the lattice, not the radius.
            q = int(round(cov * levels))
            if q > 0:
                out.append((dx, dy, q / levels))
    return tuple(out)


# =============================================================================
# Destination — WIP § 8.5
#
# `{dest}` then a HALF-WIDTH space then `行` (author, 2026-08-25). The particle
# is composed here; `route.json` holds only `"dest": "東京"`. Same composition as
# E235, different particle — E235 draws ゆき / 方面.
#
# MONOSPACED on a full-width cell, like the train type but smaller and in one
# row. Measured on both references, all three glyphs of `東京 行` carry ink
# 25.6px wide and 25.2px tall, and the two kanji advance 27.2px — constant, so
# this is a fixed cell rather than proportional text. The space between 京 and 行
# adds 8.5px on top of that advance, which is what the face's own ASCII space
# measures at this size (9px), so the space is drawn as a space rather than as a
# fraction of the cell.
#
# WEIGHT is Medium, not the type's DeBold. Measured as ink COVERAGE inside each
# glyph's own bbox, which separates weight from size: the reference's 東 fills
# 0.470 of its box, against 0.324 (Light), 0.506 (Medium), 0.575 (DeBold) and
# 0.671 (Heavy). Medium is the only near miss, and it misses HIGH — a captured,
# resampled glyph loses coverage at its edges, so the true face is at or a hair
# under Medium and certainly not Light.
#
# NO HALO. The type's white outline is a type-block feature; the destination is
# flat black on the background in both references, with nothing brighter than
# the background anywhere around its ink.
#
# SIZE AND PLACEMENT ARE FITTED, not read off those ink figures — the region
# carries nothing but this element on flat background, so it can be scored pixel
# for pixel. Exhaustive over size 25-28 x x 132-137 x y 2-8 x advance 26.5-27.75:
# best RMS 17.0 at size 27 / x 134 / y 4 / advance 27.75. The run then lands at
# x 135..224 against the reference's 135..224, glyph for glyph.
#
# The fit was re-run after `_render_cells` started rendering small text above
# the clipping threshold and scaling down: that changes the raster, so every
# figure derived against the old one had to be re-derived rather than kept.
# =============================================================================
# fmt: off
_TUNEABLES_DESTINATION = {
    "x":            134,  # left edge of the FIRST CELL. Ink then lands at 135,
                          # which is the badge's left edge — an alignment the
                          # references share to under half a pixel (WIP § 8.5).
    "y":              4,  # top of the row's FONT BOX, not of its ink. Tuning the
                          # box rather than the ink keeps the baseline fixed when
                          # the destination changes: a row aligned by ink top
                          # would ride up and down with whichever glyph happens
                          # to be tallest.
    "font_size":     27,  # fitted
    "cell_adv":   27.75,  # fitted; ink starts measure 27.2
    "space_w":        9,  # the face's own half-width space at this size;
                          # measured 8.5 in the reference
    "color": (0, 0, 0),   # core ink samples (0,0,2) — flat black
}
# fmt: on

_DEST_FACE = "ShinGoPr6N-Medium.otf"
_DEST_SUFFIX = " 行"
# A LOOP LINE HAS NO TERMINUS, so its destination is a direction rather than a
# bound-for: 品川･東京方面, not 品川･東京行. Same rule and same predicate E235
# applies (`e235_0/upper_lcd.py` draw_destination — `"方面" if route_name ==
# "山手線"`), only this model's particle is 行 where E235's is ゆき. Keyed on the
# route NAME rather than on `circular`, so both models answer it the same way
# and a route that happens to carry the flag does not silently change wording.
_DEST_SUFFIX_LOOP = " 方面"
_LOOP_ROUTE = "山手線"

# The row is drawn CHARACTER BY CHARACTER, so what reaches the font is single
# characters of a destination plus the composed particle. `check_declared`
# admits any single character of a declared string, so `DESTINATIONS` covers the
# name itself; the particles exist in no route field and are declared as the
# literals they are.
_DEST_DRAWS = (DESTINATIONS, lit("行"), lit("方面"))


# =============================================================================
# Station-name plate — WIP § 8.5
#
# The big white box, and the first element on this display that is a SHAPE
# rather than text. Drawn before the prefix and the name so both have something
# to be positioned against — which is why it went in first (author, 2026-08-25).
#
# GEOMETRY is the tightest agreement of any figure taken off these references:
# all three put the white at x 121.9..628.9 and y 36.7..137.0 on the 640x149
# grid, within 0.3px of each other. Adding the 2px outline back gives the outer
# box below, and that box reproduces the measured white span exactly.
#
# THE OUTLINE IS A DIAGONAL GRADIENT, not a flat rule (author, 2026-08-25 —
# "if you probe the ref carefully, it's a boarder with gradient"). It is near
# black at the TOP-LEFT corner and fades to nothing before the BOTTOM-RIGHT,
# which is why the plate reads as lit from the upper left rather than as a boxed
# rectangle. Drawing it flat is what a first pass does, and it looks wrong.
#
# The probe that shows it: INTEGRATED ink across the edge — sum of
# `background - luminance` over a 6px band straddling the line — at points all
# the way round, plotted against the diagonal coordinate
#
#       u = ((x - x0)/w + (y - y0)/h) / 2      0 at top-left, 1 at bottom-right
#
# Integration rather than the darkest pixel, because a ~1.2px line lands on a
# different sub-pixel phase on each capture: the darkest pixel of the LEFT edge
# reads 43 on one reference and 64 on the other, while their integrals agree to
# within 1%. Reading the phase instead of the quantity is what makes the two
# captures look like they disagree.
#
# Ink against u, both references, all four edges pooled (bg luminance 180):
#
#       u     0.01  0.13  0.25  0.37  0.42  0.46  0.51  0.59  0.67  0.75  0.83  0.87
#       ink    209   207   208   208   194   184   178   132    87    40     7     0
#
# Top and left interleave along the flat; right and bottom interleave along the
# ramp. That the four edges land on ONE curve is what makes this a gradient
# across the box rather than four differently-drawn sides — a bevel would put
# top+left on one value and right+bottom on another, with no ramp at all.
#
# So: full strength out to u = 0.40, then linear to zero at u = 0.87. The flat's
# 209 is 1.2px of solid coverage at this background.
#
# EXTENT comes from the same integrals rather than from a white-threshold, since
# the outline's own shoulder moves where "white starts". Ink centroids put the
# left line at x 120.13, the right at 517.3, the top at y 34.83 and the bottom at
# 137.55.
#
# THE EDGE IS FEATHERED, on both of its parts (author, 2026-08-25 — "i think
# feather, try to pixel match, or approach it like the train type tuning
# yesterday"). Two separate softnesses, and what makes them separable is that the
# outline fades away along the diagonal: at the bottom-right the fill's own edge
# is left standing with nothing drawn over it.
#
#   * the OUTLINE is a triangle ~2.85px across carrying 1.2px of solid coverage
#   * the WHITE's own edge is a ramp ~2.85px wide centred on the same path
#
# The dark end transitions in ~1.2px and the faded end in ~2.6px, and BOTH
# captures give both figures despite their different upscales — which is what
# makes the difference the subject rather than the instrument. Measured in the
# captures' own pixels with distances converted to 640 units, never through a
# downscale to 640, since that folds my own resampling into the answer.
#
# Fit by coordinate descent on profile RMS over ten cuts: 8.28 -> 4.75, then
# 5.06 once RIGHT-edge cuts were added. That second number going UP is the
# honest one — the first pass had no cut on the right edge, so `w` was
# constrained only through its effect on the gradient and had drifted 0.9px
# while the score improved. A parameter no cut bears on is not fit, it is free,
# and the RMS says nothing about it.
#
# The fit errs SOFT and is a starting point for the eye, not a verdict: scoring
# needs the reference on the 640 grid, which costs one resampling of my own.
#
# ALL THREE REFERENCES ARE STOPPING FRAMES, so nothing here says whether the
# plate changes between approaching and at-station. Treated as invariant until a
# reference says otherwise.
# =============================================================================
# fmt: off
_TUNEABLES_STATION_PLATE = {
    # ALL SIX EDGE FIGURES ARE FLOATS, and are fit rather than rounded. The
    # outline is ~1px wide, so snapping a centreline to the grid moves it half
    # its own width — the largest single term in the fit, worth more than any
    # feather value. x/y are the outline's CENTRELINE, not an outer edge: half of
    # it lies outside, which is why the surface is drawn padded.
    "x":     120.23,  # ink centroids put the raw edges at 120.13 / 34.83 /
    "y":      34.98,  # 517.3 / 137.55; the fit moved each by under 0.3px
    "w":      397.7,
    "h":      103.5,
    "border_w":  2.85,  # TOTAL extent of the outline across it, centred on the
                        # path. Its INTEGRAL is what the reference gives — 1.2px
                        # of solid coverage — and a triangle of this extent
                        # delivers exactly that.
    "border_feather": 1.35,  # px of that extent spent FADING, inward from each
                        # outer edge. Half the extent, so the outline is a pure
                        # triangle with no solid core — the same shape the train
                        # type's halo settled on, arrived at independently.
    "corner_r":       0,  # SQUARE, and measured so: the left edge sits at x 121.73
                          # from y 37 through y 136 without moving. A 5px radius
                          # would put the y=37 edge 2.3px right of that.
    "fill_feather": 2.85,  # px over which the WHITE's own edge ramps, centred on
                        # the same path. Measured at the faded corner, where no
                        # outline survives to hide it.
    "grad_full": 0.40,  # u at or below which the outline is at full strength
    "grad_zero": 0.87,  # u at or above which it is not drawn at all
    "fill":   PLATE_WHITE,
    "border": PLATE_BORDER,
}
# fmt: on

# =============================================================================
# Station-code badge — WIP § 8.5
#
# The SHARED helper draws it: `displays.utils.draw_station_code_badge`, the same
# one E235 uses for its upper badge and its 8-station cells (author, 2026-08-26
# — "there's already the badge utility, wire that up and use, but adjust the
# size to the ref"). Only the sizes are this model's.
#
# WHAT THE REFERENCE SHOWS is an orange rounded square OUTLINE on white, with no
# black frame — E235's badge has a black ring outside its colour ring, E233-0
# has none. The helper reaches that shape with `ring_black = 0` and the two
# radii equal: it still lays a black rect down first, but the colour rect that
# follows has the same rect AND the same radius, so it covers that black
# exactly. Leaving the radii different is what would let black corners show.
#
# Both references measure the badge identically (JC24 at 高尾, JC03 at 御茶ノ水),
# which is the one thing they can cross-check here — they are the same capture
# scale and the plate behind them lands within half a pixel of the same place.
#
# Colour is `route.json`'s `color`, passed in — the model owns no orange. The
# reference's stroke samples (226,92,17) against Chūō's authored (233,91,31),
# inside what an upscale moves a colour by.
#
# FITTED over the whole badge region across BOTH references at once, so no
# parameter is left free: RMS 34.0 against 94.7 for drawing no badge at all.
# Ink then lands where the reference's does — letters y 74-88 and digits y 91-110
# against the reference's 74-88 and 91-111, both rows centred within a pixel.
#
# THE INTERCHANGE VARIANT — a black frame plus the 3-letter band, at the stations
# that carry a `code_3` in `data/stations.json` (author, 2026-08-26). On Chūō that
# is 東京 TYO, 神田 KND and 新宿 SJK; everywhere else the badge is the plain orange
# outline the references show. So `ring_black` is not a constant of this model —
# it is 0 unless the station has a 3-letter code, which is what makes the two
# shapes ONE element rather than two.
#
# THE BLACK FRAME GROWS OUTWARD. The rect handed to the helper is the badge's
# `x/y/w/h` expanded by `ring_black`, so the helper's colour rect lands back on
# exactly the measured orange square and the white interior does not move — the
# variant adds a frame around the calibrated badge rather than eating into it.
# The band then extends further up, still inside the white plate.
#
# THE BAND'S OWN FIGURES ARE THE HELPER'S, REUSED — frame 7, band 12, 20pt. No
# reference shows this variant (all five captures are non-code_3 stations), and
# the logic already exists and is calibrated on E235, so it is taken as it stands
# rather than re-fitted here. Tuneable if a capture at 東京 or 新宿 turns up.
# =============================================================================
# fmt: off
_TUNEABLES_STATION_BADGE = {
    "x":      134,  # outer square, left edge     (measured 133.9)
    "y":       64,  # top edge                    (measured 64.2)
    "w":       58,  # width                       (measured 57.5)
    "h":       57,  # height                      (measured 57.6)
    "ring":     5,  # orange stroke thickness     (measured 5.3-6.2 per side)
    "radius":   8,  # outer corner rounding       (circle fit 8.31, both refs)
    "interior_radius": 4,  # the white interior's own corner
    "prefix_size": 19,  # "JC" pt — face is fixed to Frutiger inside the helper
    "num_size":    27,  # "24" pt; the digits run half again the letters' height
    "text_gap":     3,  # px of clear ink between the two rows
    "text_y_offset": 0,  # the block is centred in the interior; the ref agrees
    "prefix_x_offset": 1,  # the letters sit a pixel right of the digits' centre
    # --- the interchange variant, drawn ONLY where the station has a code_3 ---
    # The shared helper's own values, reused as they stand — see the block above.
    "ring_black":      7,  # black frame, outside the orange
    "code_3_band_h":  12,  # the band above it
    "code_3_size":    20,  # "TYO" pt
    "code_3_x_offset": 0,  # 0 = centred on the badge
    "code_3_y_offset": 4,  # positive = lower in the band
}
# fmt: on

# =============================================================================
# Station name — the green run inside the plate
#
# ONE MECHANISM: `displays.utils.draw_text_given_width`, the same one E235 uses
# — horizontal compression only, never a change of size (author, 2026-08-26 —
# "only horizontal compression, just like the draw text given width, but only
# you need to have the advance set correct"). So the whole element is a SPAN
# plus, for short names, the width that puts the advance where the author put it.
#
# WEIGHT is Medium, by the same coverage probe the destination used: the
# reference's 高 fills 0.523 of its own ink box, against 0.303 (Light), 0.511
# (Medium), 0.569 (DeBold), 0.686 (Heavy).
#
# THE SPAN comes from the 御茶ノ水 capture, which is the reference that shows a
# name at its NATURAL length — four characters filling the span with no spread
# and no compression (author: "the left and right is defined by ochanomizu
# screenshot ... natural length is 4 chars"). Fitted over the plate interior
# pixel for pixel: RMS 29.5 at x 205 / span 296 / size 75 / y 54, against 110.7
# for drawing no name at all. Our run lands at x 206-500 against the reference's
# 206-501, and its advances measure 73 / 75 against 72 / 75.
#
# FIVE AND UP need nothing more — the same call compresses them into the same
# span, which is what `compose_text_parts` does once the text is wider than the
# width it is given.
#
# ONE TO THREE do NOT spread to the span, and that is the only thing here that
# is per-length. Left to itself the even-spread branch would push 高尾 to a
# 136px advance where the reference measures 96. So the advance is authored and
# the WIDTH is derived from it, rather than the other way round:
#
#     advance = (width + em) / (n + 1) + (14 if n == 2 else 0)
#     width   = (n + 1) * (advance - exp) - em
#
# The `+14` is `compose_text_parts`'s `exp = 7` two-character kick, which pushes
# the pair outwards by 7px each. It is part of that function's contract, so it
# is accounted for here rather than worked around.
#
# - `adv_2` = 96 is MEASURED — the reference's 高尾 sets its two glyphs 95.66
#   apart, and the author confirmed it as the value to use.
# - `adv_3` = the em, i.e. natural, no letter spacing at all (author,
#   2026-08-26). AUTHORED, not measured: no reference shows a 3-character name.
#   The 八王子 capture turned out to hold 武蔵小金井 — its ink divides into five
#   equal cells, and those cell boundaries land inside an ink gap four times out
#   of four, where three or four cells would cut through a character.
# - `adv_1` = the em as well, by the same reasoning. A one-character stop exists
#   in the corpus and no reference shows one.
#
# WHERE a short run sits is its own measured number, because the two references
# disagree and the difference is real. `draw_text_given_width` always centres the
# run in the width it is given, so a run's centre is the only positioning knob
# there is — and the reference centres 御茶ノ水 at 353.5 and 高尾 at 345.0. The
# two captures are aligned to within half a pixel on the plate behind them, so
# the 8.5px is the display's, not the crop's. Follow the reference (author,
# 2026-08-26 — "then follow the fucking ref"), which means the short branch
# carries its own centre rather than inheriting the span's.
# =============================================================================
# fmt: off
_TUNEABLES_STATION_NAME = {
    "center_x":  353,  # the span's centre: 205 + 296/2. Names of 4 and up are
                       # centred here — measured, the 御茶ノ水 run sits at 353.5.
    "center_x_short": 345,  # 1-3 characters, measured off the 高尾 run (345.0).
                       # Only one 2-character reference exists, so 1 and 3 inherit
                       # it rather than each having a number of their own.
    "y":          54,  # top of the row's FONT BOX, not of its ink — same reason
                       # as the destination: a baseline that does not move when
                       # the name does.
    "font_size":  75,  # fitted. The size NEVER changes with the name; only the
                       # horizontal compression does.
    "span_w":    296,  # the width four characters fill naturally, and the width
                       # everything longer is compressed into.
    "adv_1":      75,  # natural (= the em) — authored, no reference
    "adv_2":      96,  # measured off the reference's 高尾 (95.66)
    "adv_3":      75,  # natural (= the em) — authored, no reference
    "color": (0, 114, 0),  # darkest ink sampled (0,113,0) / (0,107,0)
}
# fmt: on

_NAME_FACE = "ShinGoPr6N-Medium.otf"

# =============================================================================
# Prefix — WIP § 8.5
#
# 次は / まもなく / ただいま, bottom left, below the train type. Same monospaced
# cell as the destination and about the same size; black, and with NO halo — the
# brightest pixel anywhere in its band is (184,188,209), barely above the
# background, where a white outline would be pinned near 255.
#
# The reference's ただいま splits into FIVE column runs for four characters
# because い is two disjoint strokes. Reading the cell off the four ink starts
# gives 27.2 / 28.2 / 27.2, i.e. one cell of about 27.5 plus per-glyph side
# bearing.
#
# FITTED, not read off those starts. The whole region carries nothing but this
# element on flat background, so it can be scored pixel for pixel rather than at
# hand-picked cuts — which means no parameter can go unconstrained the way the
# plate's `w` did. Exhaustive over size 28-31 x x 5-10 x y 110-116 x advance
# 26.5-27.75: best RMS 37.1 at size 28 / x 6 / y 113 / advance 27.0, against
# 69.7 for drawing nothing at all. The run then reproduces the reference run for
# run — five column runs for four characters, because い is two strokes:
#
#     ours  (8,31) (35,59) (62,74) (78,85) (90,111)
#     ref   (8,31) (35,59) (63,74) (78,85) (90,112)
#
# The RMS floor is high because text is high-frequency and the reference's
# rasters came back through a 2.35x upscale — position and size are what this
# can settle, not per-pixel identity.
#
# Re-fit after `_render_cells` started rendering small text above the clipping
# threshold and scaling down: that changes the raster, so every figure derived
# against the old one had to be re-derived rather than kept. The score improved
# from 41.9 to 37.1 across that change.
#
# LEFT EDGE IS ITS OWN. It is NOT aligned to the train type above it: prefix ink
# starts at x/W 0.0120 and the type's at 0.0186, and their centres disagree too
# (0.0939 vs 0.0762), so they are neither flush nor concentric (WIP § 8.5).
#
# WEIGHT is Medium, by the coverage probe: the reference's ま fills 0.463 /
# 0.466 of its box, against 0.26 (Light), 0.48 (Medium), 0.53 (DeBold).
#
# 次 OVERHANGS ITS CELL, and `_render_cells` pads for it — see the note there.
# Kana carry ~2px of side bearing so they sit inside a 27px cell at this size;
# 次 fills its em edge to edge and hung off the left, which no reference frame
# could have shown because all three of them read ただいま.
# =============================================================================
# fmt: off
_TUNEABLES_PREFIX = {
    "x":            6,  # left edge of the first CELL. x/y are INTEGERS on
                        # purpose: the row is a rendered raster blitted at a
                        # whole pixel, so a fractional origin would render
                        # identically to its own rounding.
    "y":          113,  # top of the row's FONT BOX — the same stable-baseline
                        # placement the destination and the name use
    "font_size":   28,  # fitted
    "cell_adv":  27.0,  # FLOAT — the cursor accumulates it and rounds per cell,
                        # so a fractional advance is expressible. The ink starts
                        # measure ~27.5; the fit settled on 27.0.
    "color": (0, 0, 0),
}
# fmt: on

_PREFIX_FACE = "ShinGoPr6N-Medium.otf"

# The three forms `UpperDisplay.set_state` can produce, and nothing else — they
# live in the source, not in any route file, so they are literals.
_PREFIX_DRAWS = lit("次は", "まもなく", "ただいま", "つぎは")

# =============================================================================
# Clock — WIP § 8.5
#
# A white box in the bottom-right corner with the time in black. Found by
# mapping the band rather than by eye: the stub inherited the description "white
# box, bottom right" from a session that had not measured it, and a white-region
# scan of the right-hand end found nothing, because the box's own edge is soft
# and the scan was looking for a hard one.
#
# THE BOX HAS NO OUTLINE. Unlike the station-name plate, which carries a fading
# black rule, this is a plain white rectangle with a ~2px soft edge on all four
# sides: reading across any edge gives background -> ramp -> white with nothing
# darker than the background anywhere. So it shares the plate's builder with the
# outline turned off, rather than getting a second implementation of a soft box.
#
# `H:MM`, NOT `HH:MM`. The reference reads 8:36 and the hour's leading cell is
# empty white — 16px of it, exactly one digit — so the hour is not zero-padded.
# `app.py` hands every model `time.strftime("%H:%M")`, which IS zero-padded, so
# the strip happens here. It is a presentation choice of this model and does not
# belong in the app: E235 draws the padded form.
#
# The time was read out of the pixels as text, not off the image by eye — the
# glyph shapes are printed as a character grid and the digits read from that.
#
# MONOSPACED, and the colon has its OWN narrower cell. All three digits carry
# ink exactly 15px wide on a 16px pitch, which no proportional setting produces;
# the colon's ink is 4px on a cell of about 9.
#
# THE FACE IS LATIN, NOT ShinGo. The model's "ShinGo throughout" is about its
# Japanese text: ShinGo sets a digit 19px wide at the height this needs, against
# the reference's 15, and no size fixes an aspect ratio. Ink 15 x 23 at coverage
# 0.508 puts it on Helvetica Neue, between Roman (0.484) and Medium (0.521).
#
# Settled by fitting the whole region: Medium 24.2 / Roman 32.4 / Bold 49.6 /
# Frutiger Bold 89.3 / ShinGo Medium 79.2 / ShinGo Light 83.6, against 92.4 for
# the box with no digits at all. So the Latin faces are not merely better, the
# ShinGo ones barely beat drawing nothing.
#
# THE FIRST PASS OF THAT FIT PICKED ShinGo Light, and was wrong for a reason
# worth keeping: it compared faces at a FIXED `y`. Each face seats its digits at
# a different height inside the font box, so a fixed y is a fixed handicap that
# has nothing to do with the face. Giving every candidate its own best y and
# right edge before comparing them reversed the answer and moved the score from
# 75 to 24. Same shape as the plate's `w` drifting while its RMS improved — a
# parameter the score cannot see is not being fit.
# =============================================================================
# fmt: off
_TUNEABLES_CLOCK = {
    # The BOX. Same float-centreline convention as the plate, and the same
    # builder — see `_build_soft_box`.
    "box_x":      554.6,  # white measured 555..632 x 106..137 on all three refs,
    "box_y":      106.1,  # agreeing to a pixel; these are the fitted centrelines
    "box_w":      78.45,
    "box_h":      31.85,
    "fill_feather": 1.45,  # px over which the box's edge ramps into the background
    "corner_r":    5.15,  # ROUNDED, unlike the plate. Its left edge walks
                          # 556.74 -> 555.59 -> 555.08 -> 554.70 -> 554.50 over
                          # four rows and then holds, which a circular corner of
                          # this radius reproduces to within 0.08px per row.
    "fill":   PLATE_WHITE,

    # The TIME.
    "right_x":      624,  # ink's RIGHT edge. The run is right-aligned so the
                          # minutes hold their place when the hour loses a digit.
    "y":            111,  # top of the row's FONT BOX
    "font_size":     31,  # fitted
    "cell_adv":    15.5,  # digit pitch; all three reference digits are 15px of
                          # ink, which is a tabular cell rather than proportional
    "colon_adv":    7.0,  # the colon's own narrower cell
    "color": (0, 0, 0),
}
# fmt: on

_CLOCK_FACE = "HelveticaNeue-Medium.otf"
_CLOCK_DRAWS = lit("0123456789:")


def _build_soft_box(w, h, fx, fy, bw, feather, fill_feather, radius, u_full, u_zero, fill, border) -> tuple:
    """A soft-edged filled box with an optional fading outline, plus its padding.

    Two callers: the station-name plate, which uses the outline and square
    corners, and the clock, which passes `bw = 0` and a corner radius. Both are
    measured, not assumed — the plate's left edge sits at x 121.73 from y 37
    through y 136 without moving, so it really is square, while the clock's
    walks 556.74 -> 555.59 -> 555.08 -> 554.70 -> 554.50 over four rows. Named for the shape rather than
    for the plate, because the second caller arrived and the first one's name
    would have made it look like a plate-only helper.

    Returns `(surface, pad)`; the caller blits it at `floor(origin) - pad` on
    both axes, because the outline is centred on the box edge and so half of it
    lies OUTSIDE the tuned rect. `fx`/`fy` are the origin's fractional parts, fed
    into the distance field rather than rounded away — the edges are measured to
    a fraction of a pixel, and a ~1px outline moved half its own width shows.

    Built once and cached by the caller — the plate never changes during a drive,
    and per-pixel work every frame for a static shape would be absurd. Coverage
    is computed analytically from the distance to the edge rather than by
    supersampling: a rectangle's distance field is exact in closed form, so there
    is nothing for a 4x raster to resolve that this does not already get right.

    Composited as real alpha rather than as a colour mixed toward the background,
    so the faded end of the outline blends into whatever is actually behind the
    element instead of painting a rectangle of assumed background over it.
    """
    bw = max(0.0, float(bw))
    fe = max(0.0, float(feather))
    ff = max(0.0, float(fill_feather))
    # w/h are FLOATS. The outline's centreline is measured to a fraction of a
    # pixel (the box is 102.7px tall between edge centres, not 102 or 103), and
    # rounding it to the grid moves a 1px line by half its own width — visible,
    # and the largest single term in the fit against the reference.
    w, h = float(w), float(h)
    half = bw / 2.0
    pad = int(math.ceil(max(half, ff / 2.0))) + 1
    iw, ih = int(math.ceil(w)), int(math.ceil(h))

    img = pygame.Surface((iw + 2 * pad, ih + 2 * pad), pygame.SRCALPHA, 32)
    img.fill((*fill, 0))
    # The deep interior is solid fill and needs no per-pixel work; only the band
    # either side of the edge does.
    band = max(half, ff / 2.0) + 1.0
    inner = int(math.ceil(band))
    pygame.draw.rect(
        img,
        (*fill, 255),
        pygame.Rect(pad + inner, pad + inner, max(0, iw - 2 * inner), max(0, ih - 2 * inner)),
    )

    x1, y1 = w - 1.0, h - 1.0
    rad = max(0.0, min(float(radius), x1 / 2.0, y1 / 2.0))
    span = max(1e-6, float(u_zero) - float(u_full))
    dux, duy = max(1, x1), max(1, y1)

    # SUB-SAMPLED, because a profile EVALUATED at the pixel centre is not the
    # pixel's coverage. Point-sampling the triangle put a pure-black pixel
    # wherever the centre landed on the peak, against a reference whose darkest
    # pixel is 27 — the same error the train-type halo made before it was
    # supersampled, and it looks the same: an edge harder than the one it copies.
    SUB = 4
    _OFF = [(k + 0.5) / SUB - 0.5 for k in range(SUB)]

    def pixel(px, py):
        acc_r = acc_g = acc_b = acc_a = 0.0
        for oy in _OFF:
            sy_ = py + oy - fy
            for ox in _OFF:
                sx_ = px + ox - fx
                # Signed distance to the edge PATH: negative inside the box,
                # positive outside. Inside, the nearest edge is whichever of the
                # four is closest.
                # Distance to the ROUNDED path: the distance to a rectangle
                # inset by the radius, less the radius. At radius 0 this reduces
                # to the square case exactly, so the plate is unaffected by the
                # clock needing it.
                ix = min(max(sx_, rad), max(rad, x1 - rad))
                iy = min(max(sy_, rad), max(rad, y1 - rad))
                if ix == sx_ and iy == sy_:
                    d = -min(sx_ - rad, x1 - rad - sx_, sy_ - rad, y1 - rad - sy_) - rad
                else:
                    d = math.hypot(sx_ - ix, sy_ - iy) - rad
                # `u` is a position ALONG the box, so it is taken against the
                # full rect rather than the inset one.
                cx = min(max(sx_, 0.0), x1)
                cy = min(max(sy_, 0.0), y1)
                a_d = abs(d)
                # The fill's own edge is a ramp centred on the path, not a hard
                # cut: at the faded corner, where no outline survives to hide it,
                # the reference runs white -> background over ~2.6px in BOTH
                # captures, while the dark edge transitions in ~1.2px in both.
                # Two captures at different upscales agreeing on both figures is
                # what makes the difference the subject, not the instrument.
                wa = 1.0 if ff <= 0 else min(1.0, max(0.0, 0.5 - d / ff))
                if fe <= 0:
                    lc = 1.0 if a_d <= half else 0.0
                else:
                    lc = min(1.0, max(0.0, (half - a_d) / fe))
                if lc > 0.0:
                    # `u` is taken at the NEAREST point on the path, so a pixel
                    # off the outside of an edge inherits that edge's place in
                    # the gradient rather than one from its own stray coordinate.
                    u = 0.5 * (cx / dux + cy / duy)
                    lc *= 1.0 if u <= u_full else max(0.0, 1.0 - (u - u_full) / span)
                a = lc + wa * (1.0 - lc)
                if a <= 0.0:
                    continue
                # Accumulated PREMULTIPLIED, so averaging sub-samples of
                # different opacity does not pull the colour toward whichever
                # one happened to be more transparent.
                acc_r += border[0] * lc + fill[0] * wa * (1.0 - lc)
                acc_g += border[1] * lc + fill[1] * wa * (1.0 - lc)
                acc_b += border[2] * lc + fill[2] * wa * (1.0 - lc)
                acc_a += a
        if acc_a <= 0.0:
            return
        img.set_at(
            (pad + px, pad + py),
            (
                round(acc_r / acc_a),
                round(acc_g / acc_a),
                round(acc_b / acc_a),
                round(255 * min(1.0, acc_a / (SUB * SUB))),
            ),
        )

    lo, hi = -pad, inner
    for py in range(-pad, ih + pad):
        edge_row = py < hi or py >= ih - hi
        xs = range(-pad, iw + pad) if edge_row else list(range(lo, hi)) + list(range(iw - hi, iw + pad))
        for px in xs:
            pixel(px, py)
    return img, pad


# =============================================================================
# Small text is rendered ABOVE a threshold and scaled down — pygame clips
#
# `Font.render` returns a surface exactly `get_height()` tall, which is
# `ascent + |descent|`, and at small sizes FreeType's grid-fitting can inflate a
# glyph past that. The overflow is only ever a pixel, but it is a pixel of INK
# and it goes silently: nothing raises, the row just loses its bottom row.
#
# Over the 251 distinct characters this display draws, at the destination's
# size 26 it hits 向 城 成 片 行 越, and at the prefix's 29 it hits 越. `行` is on
# EVERY destination, which is how it was spotted (author, 2026-08-25: "your dest
# has some px cutoff at bottom as well"). By size 38 no glyph overflows at all.
#
# So a row whose size is under the threshold is rendered at a whole multiple
# above it and resolved down. Two things fall out of that beyond the fix: the
# downscale is real antialiasing, and the glyph gets its TRUE proportions rather
# than its grid-fitted ones — 東's ink measures 1.000 of the em at 26 and 0.950
# at 80, and 0.950 is the outline. The reference agrees with the outline.
#
# The threshold is checked against the corpus rather than assumed, and the
# factor is derived per size rather than fixed, so an element already drawn
# large enough pays nothing. The station name at 76 is such an element.
# =============================================================================

_CELL_MIN_RENDER = 48  # clipping stops by 38 across the corpus; this is margin


def _cell_scale(size: int) -> int:
    """Whole factor to render `size` at so no glyph overflows its own surface."""
    return max(1, int(math.ceil(_CELL_MIN_RENDER / max(1, size))))


def _render_cells(font_for, size: int, text: str, adv: float, space_w: float, color, narrow: dict = None) -> tuple:
    """`text` on fixed cells: one `adv`-wide cell per character, glyph centred.

    Returns `(surface, pad)`. The caller blits at `cell-origin - pad`, because a
    GLYPH CAN BE WIDER THAN ITS CELL and the surface has to hold the overhang.

    `font_for` is a size -> font callable rather than a font, because the SIZE
    the row is rendered at is not always the size it is drawn at — see
    `_cell_scale`.

    That is not hypothetical. The prefix sets 30px glyphs on a 27px cell, which
    is what the reference measures; kana carry ~2px of side bearing so they sit
    inside it regardless, but 次 fills its em edge to edge and hung 2px off the
    left of a surface sized to the cells alone — silently clipped, and invisible
    on every reference frame because all three of them read ただいま (author,
    2026-08-25: "found your 'tsugi wa', left part has like 5 px cut off"). The
    pad is measured over the glyphs actually being drawn rather than assumed from
    the font size, so a face whose widest glyph is narrower costs nothing.

    Shared by the destination, the station name, the prefix and the clock,
    because all four measure as the same thing — a constant advance, independent
    of the glyph in it. A space takes `space_w` and draws nothing.

    `narrow` gives named characters their own advance. The clock needs it: its
    digits sit on a 16px cell and its colon on a narrower one, which is a real
    per-character width rather than a case the uniform advance can express.

    The surface is the FONT's full height rather than the ink's, so a caller
    positioning it by its top edge is positioning a baseline that does not move
    when the text changes. Pre-filled with the ink colour at zero alpha: nothing
    here premultiplies, so a transparent-black background would darken the
    antialiased edge of dark text on a light display.
    """
    # `adv` is a FLOAT and the cursor accumulates it before rounding, so a cell
    # measured at 27.5 does not have to become 27 or 28. Rounding the advance
    # itself would put half a pixel of error into every gap and compound it
    # across the run.
    adv, space_w = float(adv), float(space_w)
    scale = _cell_scale(size)
    font = font_for(size * scale)
    adv, space_w = adv * scale, space_w * scale
    widths = {c: float(w) * scale for c, w in (narrow or {}).items()}

    glyphs = {ch: font.render(ch, True, color) for ch in set(text) if ch != " "}
    pad = max([0] + [int(math.ceil((g.get_width() - widths.get(ch, adv)) / 2.0)) for ch, g in glyphs.items()])
    x = 0.0
    placed = []
    for ch in text:
        cell = space_w if ch == " " else widths.get(ch, adv)
        if ch != " ":
            placed.append((glyphs[ch], x, cell))
        x += cell
    img = pygame.Surface((max(1, int(math.ceil(x)) + 2 * pad), font.get_height()), pygame.SRCALPHA, 32)
    img.fill((*color, 0))
    for glyph, cx, cell in placed:
        img.blit(glyph, (pad + round(cx + (cell - glyph.get_width()) / 2.0), 0))
    if scale == 1:
        return img, pad
    w, h = img.get_size()
    return (
        pygame.transform.smoothscale(img, (max(1, round(w / scale)), max(1, round(h / scale)))),
        round(pad / scale),
    )


class JapaneseDisplay:
    """Upper LCD Japanese (KANJI) rendering for E233-0."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        # CONTRACT: LCD fonts resolve through font_atlas.lcd_font with a `draws=`
        # declaration — never a bare pygame.font.Font, never SysFont. The shipped
        # build carries no font files, so a bare construct works in dev and raises
        # there. See conventions.md § Tooling.
        #
        # `_TYPE_DRAWS` widens the shared TRAIN_TYPES declaration to cover the
        # row substrings this renderer produces — see its definition above.
        self._type_size = None
        self._type_fonts: dict = {}
        # Outlined glyphs are composed from a dozen blits, so they are built
        # once and kept. The key carries everything that changes the pixels, so
        # a calibration nudge invalidates only what it actually affected.
        self._type_glyphs: dict = {}
        self._type_rows: dict = {}
        self._sync_type_font()

        # Same deal for the destination: one composed row per (text, metrics),
        # rebuilt only when a tuneable in the key moves.
        self._dest_fonts: dict = {}
        self._dest_rows: dict = {}
        self._name_fonts: dict = {}
        # The plate is per-pixel work over a static shape, so it is built once
        # and rebuilt only when a tuneable in its key moves.
        self._plate_key = None
        self._plate_img = None
        self._plate_pad = 0
        self._prefix_fonts: dict = {}
        self._prefix_rows: dict = {}
        self._clock_fonts: dict = {}
        self._clock_rows: dict = {}
        self._clock_key = None
        self._clock_img = None
        self._clock_pad = 0

    def _sync_type_font(self) -> None:
        """Drop the cached glyphs when the tuneable size changes.

        A font size is part of the atlas key, so a size cannot be read from the
        dict per frame and handed to a font that was built for another one. What
        this watches is the calibration editor moving `font_size`; the fonts
        themselves are built on demand by `_type_font`, at `_TYPE_SUPERSAMPLE`
        times whatever size the caller asks for. The baker drives every route in
        every model, so those sizes bake with everything else.
        """
        size = _TUNEABLES_TRAIN_TYPE["font_size"]
        if size != self._type_size:
            self._type_size = size
            self._type_glyphs.clear()
            self._type_rows.clear()

    def _type_font(self, size: int):
        """The type face at `size`. Sizes are ints so the set stays small."""
        f = self._type_fonts.get(size)
        if f is None:
            f = lcd_font(_TYPE_FACE, size, draws=_TYPE_DRAWS)
            self._type_fonts[size] = f
        return f

    def _type_glyph(self, ch: str, color, size: int) -> "pygame.Surface":
        """One character, white-outlined, padded so the halo has room.

        The halo is real: sampling rings outward from the red ink in both
        references, the colour goes red -> pink -> near-white -> background,
        peaking at (255,255,255). Antialiasing between the ink (213,3,4) and
        the background (168,177,202) could never be BRIGHTER than either, so a
        white layer is the only thing that produces it.

        Both colours come from one baked atlas entry — `AtlasFont.render` fills
        the requested colour against stored alpha coverage, so drawing the same
        glyph white costs no extra atlas area.
        """
        t = _TUNEABLES_TRAIN_TYPE
        ow = max(0.0, float(t["outline_w"]))
        fe = max(0.0, float(t["outline_feather"]))
        oc = tuple(t["outline_color"])
        key = (ch, tuple(color), ow, fe, oc, size)
        img = self._type_glyphs.get(key)
        if img is not None:
            return img

        core = self._type_font(size * _TYPE_SUPERSAMPLE).render(ch, True, color)
        img = self._outlined(core, ow, fe, oc)
        self._type_glyphs[key] = img
        return img

    _outlined = staticmethod(outlined)

    def _type_row(self, row: str, color, size: int, width: int) -> "pygame.Surface":
        """One whole row of a long type, laid out to `width`, with the halo.

        Layout is `draw_text_given_width`, the project's existing constrained-
        text helper, drawn onto an offscreen surface rather than the screen —
        it takes its target as a parameter, so nothing here reaches past it into
        `compose_text_parts`, whose CONTRACT forbids re-deriving its spacing or
        its compression ratio. Its behaviour is exactly what is wanted: a run too
        wide for the box is squeezed HORIZONTALLY at unchanged height, so four
        characters and five both fill the same width at the same height.

        Offscreen is also what the halo needs — it derives its silhouette from a
        surface's alpha, so the run has to be flattened either way.
        """
        t = _TUNEABLES_TRAIN_TYPE
        ow = max(0.0, float(t["outline_w"]))
        fe = max(0.0, float(t["outline_feather"]))
        oc = tuple(t["outline_color"])
        key = (row, tuple(color), size, width, ow, fe, oc)
        img = self._type_rows.get(key)
        if img is not None:
            return img

        font = self._type_font(size * _TYPE_SUPERSAMPLE)
        # NATURAL width, never the box width: one scale for every row, and no
        # compression (author, 2026-08-23) — at a small enough size a 5-character
        # tail fits on its own, so squeezing it only makes it a different shape
        # from the 4-character ones. `width` is kept in the signature and the
        # cache key because it bounds what the caller will accept.
        #
        # Measured on the SUPERSAMPLED font, so the row is laid out in the same
        # pixels it is rasterised in — deriving it from the 1x metrics and
        # multiplying would round differently and re-introduce compression.
        natural, h = font.size(row)
        lay_w = natural
        core = pygame.Surface((lay_w, h), pygame.SRCALPHA, 32)
        core.fill((*color, 0))
        # collapse=True renders the run as ONE piece at natural spacing. The
        # default branch instead spreads the characters to fill the given width
        # AND pushes a two-character run outwards by a fixed amount, placing the
        # first glyph at a negative offset — which is right for E235's train-type
        # box and wrong for a stack, where it reads as a gap inside 快速. The
        # compression branch, which is what an over-wide row wants, is reached
        # before either and is unaffected.
        draw_text_given_width(0, 0, lay_w, font, row, color, core, collapse=True)

        img = self._outlined(core, ow, fe, oc)
        self._type_rows[key] = img
        return img

    def draw_train_type(self, train_type: str, type_color: tuple) -> None:
        """Lay the type into the fixed box: four slots, or two condensed rows.

        Up to four characters this is the settled FOUR BOXES rule — each
        character in its own fixed slot, in reading order, unfilled slots left
        empty. Longer types switch to two condensed rows at one middle size;
        see the long-type note above.
        """
        if not train_type:
            return
        self._sync_type_font()
        t = _TUNEABLES_TRAIN_TYPE
        cell_w, cell_h = t["cell_w"], t["cell_h"]
        box_w = 2 * cell_w + t["col_gap"]
        color = tuple(type_color)
        # SLOTS for exactly 2 or 4 characters, STACK for everything else
        # (author, 2026-08-23). Those two lengths are the ones the fixed 2x2
        # grid was measured for and fills exactly; 1, 3, 5+ all leave it ragged,
        # and the stack reads better than a half-empty grid.
        stack = len(train_type) not in (2, _TYPE_SLOTS)

        with clip(self.screen, TRAIN_TYPE_RECT):
            for r, row in enumerate(_split_type(train_type)):
                if not row:
                    continue
                if stack:
                    # Every row at ONE size, natural spacing, no compression —
                    # placed by its INK box rather than its surface, since the
                    # surface carries layout padding and aligning it would
                    # align the padding rather than the glyphs.
                    img = self._type_row(row, color, t["long_font_size"], box_w)
                    ink = img.get_bounding_rect()
                    # LEFT aligned, stacked on a pitch from the row's own size
                    # rather than the 38px cell pitch.
                    y = t["box_y"] + r * (t["long_font_size"] + t["long_line_gap"])
                    self.screen.blit(img, (t["box_x"] - ink.x, y - ink.y))
                    continue
                cy = t["box_y"] + r * (cell_h + t["row_gap"]) + cell_h // 2
                for i, ch in enumerate(row):
                    # Padding is symmetric, so centring is unaffected by the halo
                    # and the ink lands where it landed before the outline.
                    cx = t["box_x"] + i * (cell_w + t["col_gap"]) + cell_w // 2
                    glyph = self._type_glyph(ch, color, t["font_size"])
                    self.screen.blit(glyph, glyph.get_rect(center=(cx, cy)))

    # -------------------------------------------------------------------------
    # Destination — WIP § 8.5
    # -------------------------------------------------------------------------

    def _dest_font(self, size: int):
        """The destination face at `size`. See the CONTRACT in `__init__`."""
        f = self._dest_fonts.get(size)
        if f is None:
            f = lcd_font(_DEST_FACE, size, draws=_DEST_DRAWS)
            self._dest_fonts[size] = f
        return f

    def _dest_row(self, text: str, size: int, adv: int, space_w: int, color) -> tuple:
        """The composed destination on its cells. See `_render_cells`."""
        key = (text, size, adv, space_w, tuple(color))
        got = self._dest_rows.get(key)
        if got is None:
            got = _render_cells(self._dest_font, size, text, adv, space_w, color)
            self._dest_rows[key] = got
        return got

    def draw_destination(self, dest_text: str, route_name: str) -> None:
        """`{dest} 行` — or `方面` on the loop. See the note above."""
        if not dest_text:
            return
        t = _TUNEABLES_DESTINATION
        suffix = _DEST_SUFFIX_LOOP if route_name == _LOOP_ROUTE else _DEST_SUFFIX
        row, pad = self._dest_row(
            dest_text + suffix,
            t["font_size"],
            t["cell_adv"],
            t["space_w"],
            tuple(t["color"]),
        )
        with clip(self.screen, DESTINATION_RECT):
            self.screen.blit(row, (round(t["x"]) - pad, round(t["y"])))

    # -------------------------------------------------------------------------
    # Station-name plate and the name in it — WIP § 8.5
    # -------------------------------------------------------------------------

    def draw_station_plate(self) -> None:
        """The white box and its fading outline. Drawn before anything inside it."""
        t = _TUNEABLES_STATION_PLATE
        ox, oy = math.floor(t["x"]), math.floor(t["y"])
        STATION_PLATE_RECT.update(round(t["x"]), round(t["y"]), round(t["w"]), round(t["h"]))
        key = (
            (t["w"], t["h"], t["x"] - ox, t["y"] - oy)
            + tuple(
                t[k]
                for k in (
                    "border_w",
                    "border_feather",
                    "fill_feather",
                    "corner_r",
                    "grad_full",
                    "grad_zero",
                )
            )
            + (tuple(t["fill"]), tuple(t["border"]))
        )
        if self._plate_key != key:
            self._plate_key = key
            self._plate_img, self._plate_pad = _build_soft_box(*key)
        pad = self._plate_pad
        self.screen.blit(self._plate_img, (ox - pad, oy - pad))

    def draw_badge(self, sta_code: str, color, code_3: str = "") -> None:
        """The station-code badge, via the shared helper. See the block above.

        `color` is the route's own, handed down by the manager rather than read
        here — same reason the destination is: this renderer draws what it is
        given, and the route owns the orange. `code_3` arrives the same way, and
        being non-empty is the whole of what selects the interchange variant.
        """
        if not sta_code:
            return
        t = _TUNEABLES_STATION_BADGE
        x, y, w, h = (round(t["x"]), round(t["y"]), round(t["w"]), round(t["h"]))
        # The frame and the band exist only in the interchange variant. At every
        # other station both are zero, which collapses the call back to the plain
        # orange outline the references measure — same rect, same interior, and
        # radii equal so the helper's black rect is covered exactly.
        rb = round(t["ring_black"]) if code_3 else 0
        band = round(t["code_3_band_h"]) if code_3 else 0
        # Expanded by the frame's own thickness, so the colour rect the helper
        # insets by `rb` lands back on the measured square.
        fx, fy, fw, fh = x - rb, y - rb, w + 2 * rb, h + 2 * rb
        # The rect follows the variant rather than standing at E235's fixed
        # max-extent (`e235_0/upper_lcd.py` `_TUNEABLES_BADGE_RECT`): there the
        # rect is the authored value and the square is derived from it, here the
        # measured SQUARE is authored and the rect derives, so it can only ever
        # agree with what was drawn. Synced before the clip either way.
        BADGE_RECT.update(fx, fy - band, fw, fh + band)
        with clip(self.screen, BADGE_RECT):
            draw_station_code_badge(
                self.screen,
                fx,
                fy,
                fw,
                fh,
                sta_code,
                color,
                prefix_size=t["prefix_size"],
                num_size=t["num_size"],
                # The badge sits INSIDE the plate, so its white is the plate's
                # (254) — the helper's own default is the darker LCD white E235
                # sits on, which reads as a grey square in here. Measured: the
                # reference's interior samples 252-254, the plate around it 254.
                interior_color=PLATE_WHITE,
                code_3=code_3,
                code_3_size=t["code_3_size"],
                ring_black=rb,
                ring_color=t["ring"],
                # Concentric: the black corner runs a frame-thickness wider than
                # the orange one it wraps.
                outer_radius=t["radius"] + rb,
                color_radius=t["radius"],
                interior_radius=t["interior_radius"],
                text_gap=t["text_gap"],
                text_y_offset=t["text_y_offset"],
                prefix_x_offset=t["prefix_x_offset"],
                code_3_band_h=band,
                code_3_x_offset=t["code_3_x_offset"],
                code_3_y_offset=t["code_3_y_offset"],
            )

    def _name_font(self, size: int):
        """The station-name face at `size`. See the CONTRACT in `__init__`."""
        f = self._name_fonts.get(size)
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=STATION_NAMES)
            self._name_fonts[size] = f
        return f

    def draw_station(self, station_text: str) -> None:
        """The green name, centred inside the plate. See the block above.

        A space in a station name is the data format's line-break marker
        (`docs/DATA_FORMAT.md` § "Station names"), and this element has one row.
        It is dropped rather than drawn, so `さいたま 新都心` sets as one run —
        the two-line treatment belongs to a view with the height for it.
        """
        if not station_text:
            return
        t = _TUNEABLES_STATION_NAME
        text = station_text.replace(" ", "")
        if not text:
            return
        n = len(text)
        font = self._name_font(t["font_size"])
        # The same average cell `compose_text_parts` computes, taken the same
        # way — a name carrying a halfwidth character must not be measured as
        # though every cell were full width.
        em = max(1, font.size(text)[0] // n)

        if n >= 4:
            width, center = round(t["span_w"]), float(t["center_x"])
        else:
            # Authored advance -> derived width. See the algebra in the block
            # above; `exp` is compose_text_parts' two-character kick.
            adv = float(t["adv_%d" % n])
            exp = 14 if n == 2 else 0
            width = max(em * n, round((n + 1) * (adv - exp) - em))
            center = float(t["center_x_short"])
        x = round(center - width / 2.0)

        p = _TUNEABLES_STATION_PLATE
        bw = int(math.ceil(max(0.0, float(p["border_w"]))))
        inner = STATION_PLATE_RECT.inflate(-2 * bw, -2 * bw)
        with clip(self.screen, inner):
            draw_text_given_width(x, round(t["y"]), width, font, text, tuple(t["color"]), self.screen)

    # -------------------------------------------------------------------------
    # Prefix — WIP § 8.5
    # -------------------------------------------------------------------------

    def _prefix_font(self, size: int):
        """The prefix face at `size`. See the CONTRACT in `__init__`."""
        f = self._prefix_fonts.get(size)
        if f is None:
            f = lcd_font(_PREFIX_FACE, size, draws=_PREFIX_DRAWS)
            self._prefix_fonts[size] = f
        return f

    def draw_prefix(self, prefix_text: str) -> None:
        """次は / まもなく / ただいま, left-flush at the bottom left."""
        if not prefix_text:
            return
        t = _TUNEABLES_PREFIX
        key = (prefix_text, t["font_size"], t["cell_adv"], tuple(t["color"]))
        got = self._prefix_rows.get(key)
        if got is None:
            got = _render_cells(self._prefix_font, t["font_size"], prefix_text, t["cell_adv"], 0, tuple(t["color"]))
            self._prefix_rows[key] = got
        row, pad = got
        with clip(self.screen, PREFIX_RECT):
            self.screen.blit(row, (round(t["x"]) - pad, round(t["y"])))

    # -------------------------------------------------------------------------
    # Not yet specced — one stub per element still awaiting its drill-down
    # (WIP § 8.1). They are called unconditionally by UpperDisplay.draw so the
    # call sites exist and the render order is already fixed; each becomes real
    # in its own session. Do NOT quietly implement one to "fill it in".
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Clock — WIP § 8.5
    # -------------------------------------------------------------------------

    def _clock_font(self, size: int):
        """The clock face at `size`. See the CONTRACT in `__init__`."""
        f = self._clock_fonts.get(size)
        if f is None:
            f = lcd_font(_CLOCK_FACE, size, draws=_CLOCK_DRAWS)
            self._clock_fonts[size] = f
        return f

    def draw_clock(self, time_text: str) -> None:
        """The white box and the time in it, right-aligned. See the note above."""
        t = _TUNEABLES_CLOCK
        ox, oy = math.floor(t["box_x"]), math.floor(t["box_y"])
        CLOCK_RECT.update(round(t["box_x"]), round(t["box_y"]), round(t["box_w"]), round(t["box_h"]))
        key = (
            t["box_w"],
            t["box_h"],
            t["box_x"] - ox,
            t["box_y"] - oy,
            t["fill_feather"],
            t["corner_r"],
            tuple(t["fill"]),
        )
        if self._clock_key != key:
            self._clock_key = key
            w, h, fx, fy, ff, rad, fill = key
            # The outline is off (`bw = 0`); this is the plate's builder drawing
            # only its box, which is all the reference shows here.
            self._clock_img, self._clock_pad = _build_soft_box(w, h, fx, fy, 0, 0, ff, rad, 0.0, 1.0, fill, fill)
        self.screen.blit(self._clock_img, (ox - self._clock_pad, oy - self._clock_pad))

        if not time_text:
            return
        # `%H:%M` in, `H:MM` out — one leading zero, not `lstrip`, which would
        # eat the hour entirely at midnight and leave `:36`.
        text = time_text[1:] if len(time_text) > 1 and time_text[0] == "0" else time_text
        key = (text, t["font_size"], t["cell_adv"], t["colon_adv"], tuple(t["color"]))
        got = self._clock_rows.get(key)
        if got is None:
            got = _render_cells(
                self._clock_font,
                t["font_size"],
                text,
                t["cell_adv"],
                0,
                tuple(t["color"]),
                narrow={":": t["colon_adv"]},
            )
            self._clock_rows[key] = got
        row, pad = got
        # Positioned by the run's INK rather than its surface, since the surface
        # carries the cell padding and the glyphs' own side bearings.
        ink = row.get_bounding_rect()
        if len(text) > 4:
            # TWO-DIGIT HOUR: CENTRED, and this one is authored rather than
            # measured (author, 2026-08-25). No reference shows it — all three
            # read 8:36 — and the reference's own position is not centred: its
            # run sits +4.65px right of the box centre, with margins 16.0 left
            # and 6.7 right. Carrying that straight into `18:36` would put the
            # leading digit flush on the box's left edge with 6.7px still spare
            # on the right, which reads as bad spacing. So the long form centres
            # and the short form keeps the measured position.
            x = (t["box_x"] + t["box_w"] / 2.0) - ink.w / 2.0 - ink.x
        else:
            x = round(t["right_x"]) - (ink.x + ink.w) + 1
        with clip(self.screen, CLOCK_RECT):
            self.screen.blit(row, (round(x), round(t["y"])))


class FuriganaDisplay(JapaneseDisplay):
    """Kanji everything, except the PREFIX and the STATION NAME read as kana.

    Author, 2026-08-29: *"furigana happens only on the prefix and the station
    names"* — and `transfer-hachioji-ja.png` is a capture of exactly this mode,
    showing つぎは / はちおうじ beside a train type, destination and code badge
    that all stay in kanji. So this is a two-element override rather than a
    second renderer: geometry, plate, badge and clock are inherited unchanged
    and cannot drift from the kanji mode.

    Only 次は has a kana form to switch to; まもなく and ただいま are already
    kana and pass through, which is why the map has one entry rather than three.
    """

    _PREFIX_KANA = {"次は": "つぎは"}

    def __init__(self, screen, route_data, stops):
        super().__init__(screen, route_data, stops)
        self._readings = {k: v.get("furigana", "") for k, v in load_json_relative("data/translations.json").items()}
        self._kana_fonts: dict = {}
        self._drawing_kana = False

    def _name_font(self, size: int):
        """The name face at `size` — declared against the READINGS while drawing
        a reading, and against the parent's names while drawing a fallback.

        Two declarations rather than one covering both: the modes draw disjoint
        strings out of the same face at the same size, and a merged `draws=`
        would let an undeclared reading pass `font_atlas.check_declared` on the
        strength of some kanji name.
        """
        if not self._drawing_kana:
            return super()._name_font(size)
        f = self._kana_fonts.get(size)
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=STATION_READINGS)
            self._kana_fonts[size] = f
        return f

    def draw_prefix(self, prefix_text: str) -> None:
        super().draw_prefix(self._PREFIX_KANA.get(prefix_text, prefix_text))

    def draw_station(self, station_text: str) -> None:
        """The reading, or the kanji name where the data holds no reading.

        Falling back to the name is the honest degrade for an out-of-spec route
        whose stations are absent from `translations.json`; the alternative is a
        blank plate, and the plate is the one element that must never be empty.
        The fallback then draws KANJI, so it must not use the kana declaration —
        hence the flag rather than a second `draw_station`.
        """
        reading = self._readings.get(station_text, "")
        self._drawing_kana = bool(reading)
        try:
            super().draw_station(reading or station_text)
        finally:
            self._drawing_kana = False


class UpperDisplay:
    """E233-0 Upper LCD manager — owns state and the mode cycler, delegates drawing."""

    def __init__(self, screen, route_data, stops, audio=None):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.audio = audio

        self.prefix_text = "ただいま"
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_pa_at_station = -1
        self.at_station = True  # boots in STOPPING, matching AppState

        self.route_name = route_data.get("route", "Unknown")
        self.train_type = route_data.get("type", "")
        self.dest = route_data.get("dest", "")
        self.color = route_data.get("color", [255, 255, 255])
        self.type_color = route_data.get("type_color", [0, 0, 0])

        # Station metadata — read for `code_3`, which selects the badge's
        # interchange variant. Same source E235 reads.
        self.stations = load_json_relative("data/stations.json")

        # FURIGANA is its own renderer now; ENGLISH still resolves to the kanji
        # one (WIP § 4 — deferred, and all three modes render until it lands).
        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.furigana_display = FuriganaDisplay(screen, route_data, stops)
        self.english_display = self.japanese_display

        self.mode_displays = {
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            DisplayMode.ENGLISH: self.english_display,
        }
        self.mode_cycler = ModeCycler(self.mode_displays, default_mode=DisplayMode.KANJI)

    def set_state(self, curr_stop: int, cnt_pa: int, at_station: bool = False, cnt_pa_at_station: int = -1) -> None:
        """Update state and derive the prefix.

        The mapping is E235's unchanged — ``at_station`` is the only path to
        ただいま, and only the LAST entry in ``pa[]`` flips to まもなく. It is
        restated here rather than imported because it is the manager's own state
        logic, and E233-0's manager does not inherit from E235's.
        """
        self.curr_stop = curr_stop
        self.cnt_pa = cnt_pa
        self.at_station = at_station
        self.cnt_pa_at_station = cnt_pa_at_station

        pa = self.stops[curr_stop].get("pa", []) if 0 <= curr_stop < len(self.stops) else []
        is_final_approach_pa = len(pa) >= 1 and cnt_pa == len(pa) - 1

        if at_station:
            self.prefix_text = "ただいま"
        elif is_final_approach_pa:
            self.prefix_text = "まもなく"
        else:
            self.prefix_text = "次は"

    def _current_dest(self) -> str:
        """The destination in force at this stop.

        `route_loader._fill_dest_closure` writes `dest` onto EVERY stop by
        sticky propagation, so this is a direct read — the per-call
        `stop.get("dest") or self.dest` that looks equivalent is the smell
        principles.md § "JSON is input grammar" names, and it breaks the sticky
        override exactly where a circular route needs it.
        """
        if self.stops and 0 <= self.curr_stop < len(self.stops):
            return self.stops[self.curr_stop].get("dest", self.dest)
        return self.dest

    def _current_sta_code(self) -> str:
        """This stop's station code, or "" where the route does not carry one.

        A null code is the out-of-spec case WIP § 8.3 names — the badge is simply
        not drawn, rather than drawn empty.
        """
        if self.stops and 0 <= self.curr_stop < len(self.stops):
            return self.stops[self.curr_stop].get("sta_code") or ""
        return ""

    def _current_code_3(self) -> str:
        """This stop's 3-letter interchange code, or "" — the badge variant gate.

        A name absent from `data/stations.json`, or present without a `code_3`,
        both mean the plain badge, so one `.get` chain covers the whole corpus.
        """
        if not (self.stops and 0 <= self.curr_stop < len(self.stops)):
            return ""
        name = self.stops[self.curr_stop].get("name", "")
        return self.stations.get(name, {}).get("code_3", "")

    def draw(self, current_time_str: str = None) -> None:
        """Draw the upper band: chrome first, then every element in order."""
        display = self.mode_cycler.get_current_display()

        # Chrome. State-invariant by CONTRACT (see the package __init__): the
        # background and the divide rule never change, so they are drawn here
        # once and no element recolours them.
        pygame.draw.rect(self.screen, UPPER_BG, pygame.Rect(0, 0, S_WIDTH, UPPER_HEIGHT - DIVIDE_RULE_H))
        pygame.draw.rect(
            self.screen,
            RULE_GREY,
            pygame.Rect(0, UPPER_HEIGHT - DIVIDE_RULE_H, S_WIDTH, DIVIDE_RULE_H),
        )
        # The screen border runs around the whole display, so each half draws
        # its own edges — this band owns top, left and right.
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(0, 0, S_WIDTH, BORDER_W))
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(0, 0, BORDER_W, UPPER_HEIGHT))
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(S_WIDTH - BORDER_W, 0, BORDER_W, UPPER_HEIGHT))

        display.draw_train_type(self.train_type, self.type_color)
        display.draw_destination(self._current_dest(), self.route_name)
        display.draw_station_plate()
        display.draw_badge(self._current_sta_code(), self.color, self._current_code_3())
        display.draw_prefix(self.prefix_text)
        display.draw_station(self.stops[self.curr_stop]["name"] if self.stops else "")
        display.draw_clock(current_time_str or "")

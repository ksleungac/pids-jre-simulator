# SPDX-License-Identifier: MIT
"""E233-0 (中央線快速) Lower LCD: the full-route and 6-station views, plus the
manager that rotates every slot.

Built against ``docs/wip/WIP_e233_0_display.md``, which is the spec. § 9 covers
the full-route view and § 10 the 6-station one. The manager's other three slots
render elsewhere in the package: the standalone transfer view (§ 11) in
``transfer_info.py``, and the two standing notices (§ 12) in ``priority_seat.py``
and ``manner_mode.py``.

The diagram is the line, not the run (author, 2026-08-26). Chūō's full-route
view always draws 大月 → 東京. Row 1 is always 大月 → 武蔵境 and row 2 always
三鷹 → 東京, twenty stations each, whatever service is loaded. The eight
stations west of 高尾 are not on any diagram we run, so they arrive as
``pre_stops``, the display-only mechanism documented in ``docs/DATA_FORMAT.md``
§ pre_stops. Here it carries a line that extends beyond its origin rather than a
through service. Both cases render identically, as always-passed cells.

Both rows read right to left, wrapping row 1's left end to row 2's right end.
The diagram's screen order is therefore the reverse of its index order, and
"behind the train" is to the right. That is why the grey tail in the reference
sits right of the marker at 高尾, the run's first stop.

Full-route elements, in ``show_stops``'s own order: the two bars (orange ahead,
grey behind); the end treatment at each edge, taper or notch plus its chevrons
(§ 9.3.4; these belong to the bar rather than being an element of their own);
per-cell marks on the bar (white minute box where the train stops, arrow where
it passes); the 分 at each row's outer end; the green pentagon at the train,
which sits between two stations while it is running (§§ 9.3.2, 9.3.6); vertical
station names above each bar.

Sibling mapping (``conventions.md`` § "Forking a sibling-model renderer"): the
elements the author named (minute box, passing arrow, position marker,
continuity arrows) come from E235-1000's linear full-route, not E235-0's
racetrack, so the structural patterns are copied from there. E235-0 supplied the
two-row-with-a-wrap layout shape (``OpenRouteFullRouteDisplay``) and the
uncompressed vertical name stack.
"""

import colorsys
import json
import math
from typing import Dict, List, Optional, Tuple

import pygame

from app_paths import project_root
from constants import TIME_SCALE
from displays.transfer_info import apply_transfer_filter, load_icon, resolve_entry
from displays.lower_lcd import LowerDisplayBase
from displays.utils import arrow_points, column_width, draw_1col_text, draw_1col_text_plain, draw_aapolygon
from displays.train_models.e233_0.upper_lcd import _TYPE_SUPERSAMPLE, _build_soft_box, outlined
from displays.train_models.e233_0.transfer_info import TransferInfoDisplay
from displays.train_models.e233_0.priority_seat import PrioritySeatDisplay
from displays.train_models.e233_0.manner_mode import MannerModeDisplay
from font_atlas import STATION_NAMES, at, lcd_font, lit

from displays.train_models.e233_0 import (
    S_WIDTH,
    S_HEIGHT,
    UPPER_HEIGHT,
    LOWER_BG,
    RULE_GREY,
    BAR_ORANGE,
    BAR_BEYOND,
    BORDER_W,
)

# =============================================================================
# Full-route view (WIP § 9)
#
# Geometry is measured off `full-takao-stopping-ja.png` by colour-run detection
# (`_dev_scripts/_e233_lower_geometry.py`), as ratios against the reference's own
# 1502 x 1124, then taken onto the 640 x 480 canvas:
#
#   bar rows      centre y/H 0.5783 and 0.8768        -> 278, 421
#   bar height    h/H 0.0485                          -> 23
#   bar extent    x/W 0.0353 .. 0.9627                -> x 23, w 593
#   slot pitch    that extent / 20                    -> 29.65
#
# The slot count is confirmed rather than assumed. The green marker at 高尾
# measures centre x 853.5 in the reference, and 高尾 is the 9th cell from the
# right of a 20-slot row, whose computed centre is 853.4. The palette is measured
# the same way: served bar (225,92,18), beyond/behind (134,144,164), marker
# (51,168,58). The bar's two colours are read from the model's palette rather
# than restated here, so beyond/behind draws `RULE_GREY` (135,145,165). That is
# one level per channel off the run detection above, which is capture noise on
# the same grey the divide and the border draw at full strength.
#
# Not measured, and a draft until the author refines it: every mark's own shape
# and size (box, arrow, triangle, continuity), the name font size, and the gaps.
# Those are the per-element refinement passes.
# =============================================================================
# fmt: off
_TUNEABLES_FULL_ROUTE = {
    # The two ends are padded differently, and the reference shows it. Measured
    # at rows clear of the 分, on the two ends that terminate square: row 2's
    # left, which is the terminus, and row 1's right, which is the line's origin
    # end. The other two ends carry the wrap's chevrons at every row, so a bar
    # edge cannot be separated from a chevron arm there.
    #
    #   left  5.16, against slot 19's centre at 33.59  -> pad 28.43
    #   right 616.3, against slot 0's centre at 605.3  -> pad 11.00
    #
    # The left pad decomposes exactly: the box's half width 12.05 + a 1.1 gap +
    # the 分's 11.7 + 3.6 to the edge = 28.45. The bar is extended leftward to
    # carry the unit label (author, 2026-08-28: "the end of route color bar
    # should be longer"), the same 分-area extension E235 makes at its row ends.
    #
    # The right pad is the reference's 11.0 plus 3. 11.0 is narrower than a
    # minute box's own half-width, and the reference never has to hold one there:
    # its outermost marks are narrow passing arrows, and on row 1 slot 0 is a
    # `pre_stop` that is always grey. On an all-stations service that slot
    # carries a 24px box, which then hangs off the end of the bar it sits on
    # (author, 2026-08-27: "the route color bar itself should be longer since the
    # white box is quiet big"). 14 gives it the same 1.95 clearance it already
    # has above and below.
    #
    # The slot geometry does not move. `slot0_cx` and `slot_pitch` are fitted to
    # the reference's name columns and the stations stay where they are; only the
    # drawn bar grows under them.
    #
    # The 分 extension is per-end, because only the ends without chevrons have
    # room for it (author, 2026-08-28: "the route bar extension for 分 should not
    # break continuity arrow ... the color background is not a 分 feature, it's a
    # route bar feature"). Row 2's left is the terminus and nothing else is
    # there, so the bar runs out to 5.2 and the label sits on it. Row 1's left is
    # the wrap, where the chevrons have to fit between the bar and the screen
    # border; extending the bar there leaves them nowhere to go. The reference
    # does not extend it either: its 分 straddles the bar and the chevrons, all
    # of which is route-bar orange.
    #
    # The bar edges are whole pixels, because the wrap group is anchored on them
    # and every shape in it inherits their sub-pixel phase (see
    # `cont_chev_pitch`). Measured 5.16 and 615.3, then rounded.
    #
    # The walls are pads from the outermost slot rather than absolute x. Written
    # as absolutes they describe the screen; written as pads they describe the
    # bar, so a route that does not fill the row shortens and re-centres without
    # any of them moving (author, 2026-08-28: "for lines that has less than 40
    # stations, we should shorten the route bar and centers the route bar"). On
    # Chūō the four reproduce the measured absolutes exactly: 33.59 - 28.59 = 5,
    # 33.59 - 9.59 = 24, 605.3 + 9.70 = 615, 605.3 + 22.70 = 628.
    "pad_end_left":  28.59,  # [measured] a SQUARE left end — the terminus. The
                             # decomposition that confirms it: box half-width
                             # 12.05 + 1.1 gap + 分 11.7 + 3.6 = 28.45
    "pad_leaving":    9.59,  # a LEAVING left end. Shorter, because the taper's 11
                             # and two chevrons on the 6 pitch have to fit between
                             # the wall and the screen border; measured 12.3, which
                             # is short enough to push the outermost tip off-screen
    "pad_end_right":  9.70,  # [measured] a SQUARE right end — the line's origin
    "pad_arriving":  22.70,  # an ARRIVING right end. Longer, because the notch is
                             # cut INTO the bar and has to start clear of the
                             # outermost station's minute box, which reaches 11.2
                             # past the slot centre
    "bar_h":         22,   # bar height — [measured] against the SCALED reference
                           # rather than off the band detector's h/H 0.0485,
                           # which rounded up: both rows read 267..288 and
                           # 410..431, i.e. 22 rows about the row centre
    "row1_cy":      278,   # row 1 bar centre       (measured y/H 0.5783)
    "row2_cy":      421,   # row 2 bar centre       (measured y/H 0.8768)
    # A route that fits on one row gets one row (author, 2026-08-29). Splitting
    # 17 cells into 9 + 8 draws a wrap the diagram does not have, and the end
    # treatment then claims a continuation where the line simply runs on to its
    # terminus. The single row sits midway between the two, so a lone bar reads
    # as belonging to the area rather than as the top half of a layout missing
    # its other half. There is no reference for it, since E233-0 has no line
    # short enough, so this value is authored like the rest of the out-of-spec
    # path.
    "row_single_cy": 350,
    "slots_per_row": 20,   # 大月..武蔵境 / 三鷹..東京 (author) — a fact of the LINE
    # THE SLOTS ARE FITTED, NOT DERIVED FROM THE BAR. Deriving the pitch as
    # bar_w/20 looked right at the centre of the row and drifted at both ends —
    # 1.4% of pitch, which is nothing per slot and 7px by the nineteenth
    # (author: "scales are not matches at non-center stations"). Least-squares
    # over the reference's twenty name-column centroids, INDEPENDENTLY on each
    # row, agrees to within 0.15% of pitch:
    #     row 1   centre(k)/W = 0.94521 - k * 0.04698
    #     row 2   centre(k)/W = 0.94649 - k * 0.04705
    # k counts from the RIGHT, so k=0 is 大月 on row 1 and 三鷹 on row 2.
    "slot0_cx":   605.3,   # [measured] rightmost slot centre, mean of both rows.
                           # Held only while the route FILLS the row; a shorter
                           # one centres instead — `_slot0_cx`
    "slot_pitch":  30.09,  # [measured] ditto — never derived from the bar's width
    # DERIVED from the model's palette, not re-typed. Both constants live in the
    # package `__init__` as whole-display facts and had zero readers, while these
    # two keys restated them — `behind_color` had already drifted a level in every
    # channel off `RULE_GREY`, which is the same grey the divide and the border
    # draw. `conventions.md` § Tooling, "Canonical-source duplication".
    "bar_color":       tuple(BAR_ORANGE),   # served / ahead
    "behind_color":    tuple(BAR_BEYOND),   # beyond service AND behind the train
}

_TUNEABLES_FULL_ROUTE_NAMES = {
    "font_size":     14,   # [measured] the reference sets 14px of ink on a
                           # ~15.5px pitch — a 3-character column runs 218-231,
                           # 233-246, 249-261, so the gaps give the pitch exactly
    "line_gap":       2,   # extra px between stacked characters. The PAIR is
                           # what matters: size sets the ink, the gap makes up
                           # the pitch. 15/1 gave 15px of ink on a 16px pitch,
                           # which stands every stack 2-3px too tall.
    "bar_gap":        5,   # clear px between the stack's bottom and the bar
                           # (the reference leaves 5.5)
    "max_chars":      6,   # the box height the spacing allows (author); Chūō's
                           # longest name is 5, and names are NEVER compressed
    "col_gap":        1,   # px between the two columns of a spaced name
    "compound_raise": 4,   # px the RIGHT column of a spaced name sits higher —
                           # E235-1000 raises its by 6 on a taller cell
    "color_ahead":     (0, 0, 0),        # stopping ahead, and this station
    "color_dim":       (120, 130, 148),  # passed, and stations the train passes
}

_TUNEABLES_FULL_ROUTE_MARKS = {
    # [measured] off the reference's row 1, where 通勤特快's three stops (八王子,
    # 立川, 国分寺) carry boxes and the seven stations between them carry arrows.
    # THE MINUTE BOX IS A FIXED RECTANGLE WITH A FEATHERED EDGE, not a halo
    # around the digits. [measured] on the two boxes the reference shows: row 1
    # slot 10 carries a ONE-digit number (ink 20px native) and row 2 slot 9 a
    # TWO-digit one (ink 42px), and their white measures 52 and 53 px — the same
    # box either way, which a halo could not be. Walking across any edge gives a
    # ~3.5px native ramp (1.5 canvas) with nothing darker than the bar anywhere,
    # so it is soft-edged and unoutlined, and the top row is already full width,
    # so the corners are SQUARE. Drawn with the upper LCD's `_build_soft_box` —
    # the same builder the clock and the station-name plate use.
    # Sizes are the 50% CROSSINGS, not a white-threshold bbox. A >240 bbox
    # reports the box's solid CORE and throws its ramp away — it gives 22.4 x
    # 16.0 here, 1.7px short on each axis, and feeding that back in would shrink
    # the box by the width of its own feather every time it was re-measured.
    "box_w":       22.4,   # AUTHORED narrower than measured (author, 2026-08-28:
                           # "our minute box is too wide"). The 50% crossings put
                           # the reference at 24.3 and ours rendered 23.5, i.e.
                           # already the narrower of the two — so this is the
                           # reference's SOLID-CORE width (52px native) taken as
                           # the geometric one instead, which is the smaller
                           # figure the same box supports
    "box_h":       18.1,   # [measured] 963.8..1006.2 native = 42.4 / 2.347;
                           # leaves 1.95 of bar above and below, and the builder
                           # takes floats, so CENTRED needs no even height
                           # (author, 2026-08-27)
    "box_feather":  1.7,   # [measured] the edge ramp, ~4px native; cf. 1.45 on
                           # the clock, which is the same construction
    "box_corner_r": 0.0,   # SQUARE — the box's top row is already its full width
    "box_side_pad": 2.2,   # clear px each side of the digits. Only ever binds at
                           # THREE digits (author, 2026-08-28: "reserve the code
                           # for 3 digits time display") — no Chuo diagram reaches
                           # 100 minutes, but an out-of-spec route does, and a box
                           # that silently clips its own number reports nothing.
                           # 2.2 is what the measured box leaves round a 2-digit
                           # run, so one and two digits are byte-identical
    "box_color":       (253, 253, 253),
    "time_size":     17,   # digit ink measures 28px native tall, 20 wide -> 11.9
                           # x 8.5 canvas; a 2-digit run measures 42 -> 17.9
    "time_color":      (15, 15, 15),
    # THE UNIT LABEL. One 分 at the LEFT end of each bar, which is where the row
    # stops reading — the rows run right to left, so the left end is the far end
    # of the journey and the label sits past the last station's mark. Dark ink
    # with a white outline ON the bar, the same construction as the upper LCD's
    # train type (author, 2026-08-27: "the minute text ... text, white outline
    # maybe some feathering, like train type display"), and it uses that module's
    # `outlined` rather than a second implementation of it.
    #
    # [measured] ink 11.93 x 11.50 on row 1 and 11.50 x 11.50 on row 2, centred
    # at x 14.91 / 14.27 and 1.25 / 1.08 ABOVE the bar's centre. Placed by its
    # INK box rather than by its font box: 分 does not fill its em, so the two
    # differ by more than the tolerance this is being fitted to.
    "unit_text":      "分",
    "unit_size":       13,  # 14 rendered a point large (author, 2026-08-28)
    # ANCHORED TO THE ROW'S OUTERMOST SLOT, not to the screen. The reference puts
    # the ink centre at 14.27 on row 2 and 14.91 on row 1 against one slot centre
    # of 33.59 — i.e. 19.3 and 18.7 left of it, the same offset on both rows even
    # though their walls differ by 16px. Screen-anchoring reproduces Chūō and
    # then strands the label in the background once a shorter route centres its
    # bar; slot-anchoring gives 33.59 - 19.0 = 14.59, the measured value.
    "unit_dx":      -19.0,  # [measured] ink centre, from the outermost slot centre
    "unit_dy":       -1.2,  # [measured] ink centre, relative to the bar's centre
    "unit_color":      (5, 5, 5),   # core samples (5,0,3)
    # AUTHORED above the measured ~1.5 (author, 2026-08-28: "the white outline
    # for your current 分 can be thicker", twice) — the measurement is of a 2.35x
    # upscale whose own ringing eats the halo's outer tail, so the reference
    # under-reports it.
    #
    # It has a COST at the leaving edge, where the label sits over the taper and
    # the chevrons: an opaque white halo this wide spans 5.4..23.8 against a
    # group occupying 1..24, so it covers most of them. On an orange row that
    # passes for the reference's own white bands between the chevrons; on a
    # greyed row it reads as the arrows thinning out.
    "unit_outline_w": 3.2,
    "unit_outline_feather": 3.2,    # feather == extent, as the train type has
    # The arrow is TALLER THAN IT IS WIDE and hollow — a chevron, tip LEFT, the
    # way the row reads. 19 x 33 px with ~5px arms; E235's is a squat 14-wide
    # shape and does not carry over.
    "arrow_w":        8,   # 19px / 2.347
    "arrow_h":       14,   # 33px / 2.347 — NOT derived from the bar's height
    "arrow_stroke":   2,   # arm thickness (`arrow_points` body thickness)
    "arrow_color":     (253, 253, 253),
    # The current-stop marker is a PENTAGON, not a triangle (author, 2026-08-27
    # — "don't trust my word, probe it"). A classified pixel map of the reference
    # shows the top edge running flat from x 859 to the base at 871 before the
    # slants begin; a triangle would meet at a point there. Nose left, the way
    # the row reads.
    #
    # FREE VERTICES, not a parametric shape: this marker is drawn at ONE fixed
    # orientation in a slot the view re-centres on, so the vertices ARE the
    # shape (`conventions.md` § "Single-slot, fixed-orientation marker"). Offsets
    # from the slot centre on the bar's centre line, measured native and divided
    # by 2.347. Order: top-right, bottom-right, bottom-shoulder, apex,
    # top-shoulder — the shoulders differ by a pixel in the reference, as E235's
    # pentagon does.
    # FITTED, not read off the pixel map: each of the five edges is least-squares
    # fitted at native resolution and the vertices are where those lines meet, so
    # they carry sub-pixel positions the map's ±1px cannot. The two slants come
    # out -0.874 and +0.871, and the shoulders differ by 0.3px — the same
    # near-symmetry E235's pentagon has, and not something to round away.
    "tri_verts":     ((6.56, -11.08), (6.56, 10.65), (0.25, 10.65), (-9.39, -0.41), (-0.06, -11.08)),
    # `tri_h` and `tri_base_dx` USED TO LIVE HERE and both restated `tri_verts`:
    # the height was its y-extent and the base offset was literally `verts[0][0]`,
    # each with a comment admitting it. `tri_verts` is free calibration data the
    # editor DRAGS, so a nudge moved the drawn marker and left the copies behind —
    # and `tri_base_dx` feeds the orange/grey boundary, so the bar's split silently
    # stopped agreeing with the marker sitting on it. The height had no reader at
    # all. Both are now derived at their use sites from the vertices themselves.
    # THE SHADOW IS DIRECTIONAL — bottom and right only (author, 2026-08-27).
    # The rim is not: it runs all the way round (see `tri_rim` below), so the
    # two are independent and only this one keys on the light.
    #
    # `tri_light` is the direction the light comes FROM; an edge whose outward
    # normal faces AWAY from it is shadowed and one facing into it is not. On
    # this pentagon that selects the base and the bottom edge, and leaves the
    # top, the upper-left slant and the lower-left slant clear. Expressed as a
    # direction rather than as a per-edge list because the vertices are free
    # calibration data — a nudged vertex must not silently move an edge into the
    # wrong set.
    #
    # Walking outward from the green body in the reference [measured]:
    #
    #   right of base   52,62,59 -> grey (134,144,164) over 3.0 canvas px
    #   below           112 -> 65 -> background over ~3.8 px
    #   above           bright, then background. NOTHING dark.
    #   left of nose    bright, then orange. NOTHING dark.
    #
    # An isotropic shadow puts a dark ring on those last two as well, which is
    # what read as too much: it is the same total darkness spread over five
    # edges instead of two.
    "tri_light":     (-1.0, -1.0),
    "tri_shadow":      (52, 62, 59),
    "tri_shadow_reach": 3.2,   # [measured] 3.0 right, ~3.8 below — px beyond the
                               # RIM's outer edge, fading linearly to nothing
    "tri_shadow_alpha":  235,  # the reference's darkest is the shadow colour
                               # itself, i.e. effectively opaque where it starts
    # TWO TONES, split on the bar's centre line — a vertical slice through the
    # marker reads (65,176,60) above and (0,103,0) below, both flat. The dark one
    # is the route's own `contrast_color` within capture drift (Chūō authors
    # (0,92,0)); the light one is this element's.
    "tri_color_top":   (65, 176, 60),
    "tri_color_bot":   (0, 103, 0),
    # The rim is ~2px NATIVE — measured perpendicular, on the top edge and on the
    # base — which is under one canvas pixel. It only looks wider on the apex
    # side because a horizontal read across a 41-degree edge is 1.3x the true
    # width. Drawn at 4x so a sub-pixel rim survives.
    # THE RIM RUNS ALL THE WAY ROUND — every edge, concentric (author,
    # 2026-08-27: "i can see white rim on all sides"; "it's only the shadow
    # that's at right and bottom"). A probe walking outward from the green shows
    # the shadow's (52,62,59) immediately beyond the body on the base, with no
    # bright pixel between — that is the rim reading through a shadow drawn to
    # meet it at native resolution, not an absent rim. The eye on the artifact
    # outranks the walk (`critical_lessons.md` § 11).
    "tri_rim":         (255, 255, 255),
    "tri_rim_w":       1.5,
    # WHILE THE TRAIN IS RUNNING THE MARKER SITS BETWEEN STATIONS, not parked on
    # one (author, 2026-08-28: "it sits in between, as the case for all models").
    # The SHAPE does not change on approach: E235-1000 swaps its pentagon for a
    # chevron and E235-0 runs an arrow cascade; this model does neither, so
    # APPROACHING and STOPPING differ only by where the pentagon sits.
    #
    # NOT THE MIDPOINT — the spacing does not allow it (author, 2026-08-28: "i
    # tell you place in the middle, but spacing does not allow it, so itself it
    # should clear the white box at the next station"). Half a pitch is 15.0 and
    # the marker's nose reaches 9.4 ahead of its own centre, so a midpoint puts
    # the nose 5.6 INSIDE the box of the station being approached. The offset is
    # therefore DERIVED from what it has to clear — that box's half width plus
    # the nose plus this gap — rather than authored as a fraction, so it stays
    # right when the box widens for a three-digit number.
    #
    # One position, not two: at a passing station the mark is a narrow arrow and
    # the same offset simply leaves more air (author: "it should looks fine when
    # next station is a passing arrow").
    #
    # Not applied at a row's first cell, whose previous station is on the other
    # row — there is no leg on this row to sit in the middle of.
    "marker_box_gap":  1.0,
    "tri_split_dy":    0.5,  # where the two tones meet, relative to the bar's
                             # centre row: the reference's row 277 is still fully
                             # light and 278 is fully dark
    # THE WRAP IS THREE CHEVRONS AND NO TAIL. [measured] as connected orange
    # components past each bar end, which is what gives a repeating shape its
    # per-shape numbers — one row's run-length encoding only reports where that
    # row happens to cross the arms.
    #
    #   row 2, right   tips at 609.75 / 615.71 / 621.68, against bar end 616.1
    #   row 1, left    right edges at 17.04 / 23.01 / 28.98, against bar_x 23
    #
    # So it is ONE rule mirrored: the middle chevron sits ON the bar's end and
    # the other two step a pitch either side of it, the inner one lying over the
    # bar where it is invisible. The outermost then stops ~3px short of the
    # screen border by construction, which is what the drawn version was running
    # past. The bar's own end is SQUARE — the tapered tail that used to be drawn
    # on row 1 is not in the reference; what reads as a point there is the
    # chevrons overlapping, plus a smudge on the capture.
    # PLAIN ORANGE, NO OUTLINE (author, 2026-08-28: "your cont arrows should not
    # have that white shadow"). An earlier pass profiled across the group, found
    # pale bands between the chevrons brighter than the background, and read them
    # as a white outline. They are the CAPTURE RINGING. The reference is a 2.35x
    # upscale, and at a plain orange-to-background edge — one with nothing else
    # near it — it overshoots to (238,211,205): R above BOTH endpoints while G
    # and B fall. Across a 3px gap the overshoots from either side meet and pile
    # up, which is the "white" that was measured. The tell was there in the
    # numbers: the peaks ran pink (252,187,151), never neutral, and a white
    # outline cannot be pink. Same artefact the plate's outline note records.
    "cont_chev_w":       14,   # [measured] 13.64 and 14.06 on the two free ones
    "cont_chev_stroke":   3,   # [measured] 2.98 — `arrow_points` body thickness,
                               # which IS the run width at the tip's own row
    # Tip to tip, so the gap between one shape's trailing edge and the next one's
    # point is `pitch - stroke`. [measured] 5.97.
    #
    # KEEP THIS AN INTEGER. A fractional pitch alternates the sub-pixel PHASE of
    # every shape in the run — at 5.5 the tips fell at 13.0 / 7.5 / 2.0, so one
    # gap straddled the pixel grid at .82/.32 and the next at .32/.82, and two
    # gaps that are both geometrically 2.5px quantised to 2px and 1px. The author
    # read that as non-uniform spacing, correctly. Nothing about the geometry was
    # uneven; the rasterisation was.
    #
    # The apparent gap also moved once for a reason that was not the pitch at
    # all — `draw_aapolygon` fringed every edge toward white and ate ~2px off
    # each band — so readings from before that fix are not comparable.
    "cont_chev_pitch":  6,
    # ONE TRIANGLE, ADDED AT ONE EDGE AND SUBTRACTED AT THE OTHER (author,
    # 2026-08-28; WIP § 9.3.4). The predicate for an edge is the same either way
    # — does the route continue past it? — and it does not matter whether the
    # continuation is the next row or the next frame. A square end is reserved
    # for an edge where the route genuinely stops.
    #
    #   leaving   the triangle ADDED     bar tapers out to a point, chevrons behind
    #   arriving  the triangle SUBTRACTED  a notch cut into the wall, chevrons before
    #
    # Both apexes point the way the train travels, which on this model is LEFT,
    # so `apex = wall - cont_tri_w` at both ends; the wall is the bar's left end
    # at one and its right end at the other, which is what puts the same triangle
    # outside the bar in one case and inside it in the other.
    #
    # POINTINESS IS ONE PROPERTY OF THE DISPLAY, shared by everything with a point
    # — these tips, the taper, the notch, the passing arrows and the marker's nose.
    # Depth and height are what a shape may differ in; the slant between them is
    # not. Every shape at an edge stands exactly the bar's height (author).
    #
    # THE STRUCTURE IS CROSS-MODEL; THE NUMBERS ARE NOT. How many chevrons, their
    # pitch, pointiness and fatness are per-model (author) — two on E233-0, at
    # both edges. E235-1000 answers each differently and that is not a divergence.
    # THE DEPARTING END IS A TRIANGLE THEN TWO CHEVRONS, which is E235-1000's
    # own structure — `lower_lcd.py:694`, "bar (+row_tail_extra) → 分-area →
    # triangle (bar's tapered tail) → gap → chevron 1 → gap → chevron 2"
    # (author, 2026-08-28). That line also settles where the 分 belongs: INSIDE
    # the bar, before the tail, which is why its extension is a bar property.
    #
    # All three shapes sit on one uniform pitch, and the gap from the innermost
    # to the bar edge is that same pitch — [measured] tips at 15.35 / 9.38 / 3.41
    # against a bar starting at 21.3. The innermost is the solid tail; only the
    # two beyond it are chevrons.
    # THE TRIANGLE'S BASE IS THE BAR'S END WALL. Its base is its longest edge —
    # the full bar height — so that is the edge that has to make contact, flush
    # against the end face, apex pointing outward. Drawing it with the base set
    # back INSIDE the bar leaves nothing touching the wall and the tail reads as
    # a detached wedge (author, 2026-08-28).
    "cont_tri_w":       11,  # depth. = cont_chev_w - cont_chev_stroke, so the
                             # tail's slant matches the chevrons' tips and the
                             # group reads as one shape repeated — E235-1000's
                             # own relation, `lower_lcd.py:702`
    "cont_chev_n":      2,   # both edges (author, 2026-08-28)
    "cont_chev_n_arrive": 2,  # PROVISIONAL — an arriving edge has less room than
                              # a leaving one, because its notch has to start
                              # clear of the outermost station's minute box. 2
                              # runs the outer chevron 4.5px past the screen
                              # border; 1 fits. Author's call, undecided
}
# fmt: on

# The whole lower area — the view's hit-test and calibration-editor rect.
FULL_ROUTE_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)

_NAME_FACE = "ShinGoPr6N-Medium.otf"
_TIME_FACE = "HelveticaNeue-Bold.otf"
# The transfer band only — see `_transfer_font`.
_TRANSFER_FACE = "ShinGoPro-DeBold.otf"

# The position marker is composited at this scale and resolved by one
# downscale — see `_marker_image`. Same construction as the upper LCD's
# train-type halo, and for the same reason: sub-pixel rim and gradient shadow.
_MARKER_SUPERSAMPLE = 4

# The lines this model is IRL stock for. On these the marker keeps its own two
# greens; everywhere else it re-tints — see `_marker_tones`.
_IN_SPEC_LINE_CODES = ("JC",)


def _marker_tones(m: dict, route_data: dict):
    """`(top, bot)` for the position marker, re-tinted on out-of-spec routes.

    The marker's greens are the Chūō article and they read against the Chūō
    bar. On a route the model is not stock for, the bar takes that route's own
    `color`, and a green marker on a GREEN bar is the case this exists for:
    the Saikyō bar is `(46,139,87)` and the Yamanote `(116,193,30)`, 26.5° and
    31.7° of hue from the marker, so the shape survives only on its white rim.
    Luminance contrast does not see it — Saikyō scores BETTER there than Chūō
    itself (1.52 against 1.25) while looking far worse; hue distance is the
    measure that matches the eye, and matches the author naming those two.

    Gated on the LINE rather than on hue, because that is the author's own
    framing: this is out-of-spec compatibility, so an in-spec route is never
    re-tinted whatever it declares. Chūō's `contrast_color` is `(0,92,0)`,
    within capture drift of the measured `tri_color_bot` but not equal to it,
    and re-deriving from it would move a signed-off element by 19 levels of
    green for no gain (`principles.md` § "Surgical Changes").

    `contrast_color` supplies the DARK tone; the light one is derived by the
    lift the model's own pair already carries (−2.6° hue, ×0.659 saturation,
    ×1.709 value), read off `m` rather than restated, so retuning the greens
    carries the derivation with it. A route declaring no `contrast_color` keeps
    the native pair — the field is authored where a line needs it, not
    everywhere (author, 2026-08-29).
    """
    native_top, native_bot = tuple(m["tri_color_top"]), tuple(m["tri_color_bot"])
    cc = route_data.get("contrast_color")
    if not cc or route_data.get("line_code") in _IN_SPEC_LINE_CODES:
        return native_top, native_bot

    hb, sb, vb = colorsys.rgb_to_hsv(*[c / 255.0 for c in native_bot])
    ht, st, vt = colorsys.rgb_to_hsv(*[c / 255.0 for c in native_top])
    h, s, v = colorsys.rgb_to_hsv(*[c / 255.0 for c in cc[:3]])
    lifted = colorsys.hsv_to_rgb(
        ((h + (ht - hb)) % 1.0),
        min(1.0, s * (st / sb if sb else 1.0)),
        min(1.0, v * (vt / vb if vb else 1.0)),
    )
    return tuple(int(round(c * 255)) for c in lifted), tuple(cc[:3])


def _offset_polygon(verts, pad, facing=None):
    """A polygon's outline offset — each EDGE moved out by `pad`, vertices placed
    where the moved edges meet.

    A MITRE, not a push along the centroid ray. At a sharp vertex the two offset
    edges meet far ahead of the original point — by `pad / sin(half-angle)`,
    which at the position marker's 41-degree nose is 2.9x — and that convergence
    is what makes an outline widen at a point while staying thin along the flat
    edges. A centroid-ray push moves every vertex by the same `pad` and so cannot
    widen a point at all.

    `facing` restricts the offset to the edges whose outward normal has a
    positive component along it, leaving the rest ON the original outline. That
    is what puts the marker's rim and its drop shadow on disjoint edges: an edge
    the light reaches is rimmed, one it does not is shadowed, and neither can
    wrap round onto the other's side. Because the un-offset edges keep their
    original line, the mitre still closes the polygon and the boundary between a
    moved and an unmoved edge is a clean taper rather than a step.

    Capped at 4x so a near-degenerate vertex cannot throw a spike.

    Module-level because two elements need it: the marker builds its rim and its
    shadow ramp from it, and the continuity chevrons their white outline.
    """
    if pad == 0:
        return list(verts)
    n = len(verts)
    gx = sum(p[0] for p in verts) / n
    gy = sum(p[1] for p in verts) / n
    # Outward edge normals. The polygon is wound so that this sign points away
    # from the interior; the centroid decides it rather than an assumed winding,
    # so a re-ordered vertex list cannot silently invert it.
    edges = []
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        ln = max(1e-6, (ex * ex + ey * ey) ** 0.5)
        nx, ny = -ey / ln, ex / ln
        if ((x1 + x2) / 2 - gx) * nx + ((y1 + y2) / 2 - gy) * ny < 0:
            nx, ny = -nx, -ny
        p = pad if facing is None or nx * facing[0] + ny * facing[1] > 0 else 0.0
        edges.append((x1 + nx * p, y1 + ny * p, ex, ey))

    out = []
    for i in range(n):
        px, py, dx1, dy1 = edges[(i - 1) % n]
        qx, qy, dx2, dy2 = edges[i]
        den = dx1 * dy2 - dy1 * dx2
        if abs(den) < 1e-9:  # parallel edges — no mitre to compute
            out.append((qx, qy))
            continue
        tt = ((qx - px) * dy2 - (qy - py) * dx2) / den
        ix, iy = px + dx1 * tt, py + dy1 * tt
        vx, vy = verts[i]
        mx, my = ix - vx, iy - vy
        ml = (mx * mx + my * my) ** 0.5
        if ml > pad * 4:
            ix, iy = vx + mx / ml * pad * 4, vy + my / ml * pad * 4
        out.append((ix, iy))
    return out


def is_passing_stop(stop: Dict) -> bool:
    """A station the train runs through — no `pa` and no `pa_at_station`.

    Module level because three views ask it and a second wording of it drifts
    silently: the overview's greying test carried only the `pa` half for a while,
    which is right on every shipped route and wrong the moment a line whose
    origin announces only at-station gets a sheet. `principles.md` section "A
    second implementation of a production decision drifts silently".

    NOTE the predicate does NOT distinguish a `pre_stop`, which carries neither
    either and so answers True — see `JapaneseFullRouteDisplay._is_passing` for
    why that conflation is deliberate and closed.
    """
    return not stop.get("pa") and not stop.get("pa_at_station")


class JapaneseFullRouteDisplay:
    """The full line on two right-to-left rows. See the module docstring."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.state = None

        # The diagram's own list: the line, not the run. `display_offset` is
        # where the simulated route starts inside it, so a sim index becomes a
        # diagram index by adding it — the same convention E235 uses.
        self.pre_stops = route_data.get("pre_stops", [])
        self.display_stops: List[Dict] = list(self.pre_stops) + list(stops)
        self.display_offset = len(self.pre_stops)

        self.color = tuple(route_data.get("color", _TUNEABLES_FULL_ROUTE["bar_color"]))

        self._name_fonts: Dict[int, pygame.font.Font] = {}
        self._time_fonts: Dict[int, pygame.font.Font] = {}
        self._box_imgs: Dict[tuple, tuple] = {}
        self._unit_img = None
        self._unit_key: tuple = ()

        # The position marker is one cached surface — see `_marker_image`.
        self._marker_img: Optional[pygame.Surface] = None
        self._marker_key = None
        self._marker_ox = 0.0
        self._marker_oy = 0.0

    # -------------------------------------------------------------------------
    # State + geometry
    # -------------------------------------------------------------------------

    def set_state(self, state) -> None:
        """Bind AppState by reference — every draw reads it live."""
        self.state = state

    def _name_font(self, size: int):
        f = self._name_fonts.get(size)
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=STATION_NAMES)
            self._name_fonts[size] = f
        return f

    def _time_font(self, size: int):
        f = self._time_fonts.get(size)
        if f is None:
            f = lcd_font(_TIME_FACE, size, draws=lit("0123456789"))
            self._time_fonts[size] = f
        return f

    def _window(self) -> Tuple[int, int]:
        """`(first_di, count)` of the cells this frame draws.

        Two rows of `slots_per_row` is the display's CAPACITY — forty on this
        model, which is exactly Chūō's diagram. A route longer than that cannot
        be shown at once, so it windows and swaps, which is E235-1000's own
        long-route flip (`docs/DISPLAY.md` § "Long-Route Window Refresh") rather
        than a mechanism invented here (author, 2026-08-29). Keihin-Tōhoku's 46
        cells are the case; before the swap the window holds the first forty,
        after it the last forty.

        The flip rule is E235's, including its `display_offset` branch: a route
        carrying an always-passed prefix holds the window at the start until the
        train is forced off its right edge, so the prefix stays visible instead
        of the window flipping at boot.
        """
        n = len(self.display_stops)
        cap = 2 * int(_TUNEABLES_FULL_ROUTE["slots_per_row"])
        if n <= cap:
            return 0, n
        curr = self._curr()
        if self.display_offset:
            flip = curr > cap - 1
        else:
            flip = 0 < (n - curr) < cap
        return (n - cap, cap) if flip else (0, cap)

    def _per_row(self) -> int:
        """Cells on one row of the visible window.

        `ceil(count / 2)` REPRODUCES Chūō's twenty exactly, because its diagram
        is forty cells by construction, so the in-spec split needs no special
        case and the out-of-spec one is not a separate code path that can rot. A
        windowed route always yields exactly `slots_per_row`.

        A route that fits on ONE row gets one row rather than being halved: a
        17-cell line split 9 + 8 draws a wrap the diagram does not have, and the
        end treatment then claims a continuation at both halves of a junction
        that is not there.

        PROVISIONAL for a route between one row and the capacity — the author has
        not settled whether it holds a strict twenty per row or spreads evenly
        (WIP § 9.4). This is the even-spread answer; it is one function to change.
        """
        count = self._window()[1]
        if count <= int(_TUNEABLES_FULL_ROUTE["slots_per_row"]):
            return max(1, count)
        return max(1, (count + 1) // 2)

    def _row_cy(self, row: int) -> float:
        """A row's bar centre. One row sits midway between the measured two."""
        t = _TUNEABLES_FULL_ROUTE
        if self._rows() == 1:
            return float(t["row_single_cy"])
        return float(t["row1_cy"] if row == 0 else t["row2_cy"])

    def _pitch(self) -> float:
        """The measured pitch, shrunk only when a row cannot hold it.

        Never STRETCHED past the measured value: the pitch is a fact about the
        real display, so a short route draws a SHORTER bar rather than spacing
        its stations further apart than any E233 ever does.

        The room available is the screen minus the two widest walls, which are
        the ones a row can actually end up with. Deriving it from `slot0_cx`
        instead cannot work once that is itself centred — the two would define
        each other.
        """
        per = self._per_row()
        if per <= 1:
            return float(_TUNEABLES_FULL_ROUTE["slot_pitch"])
        return min(float(_TUNEABLES_FULL_ROUTE["slot_pitch"]), self._avail() / (per - 1))

    def _avail(self) -> float:
        """Room between the screen borders for the STATIONS, once both walls are
        allowed for.

        The two widest walls, because a row can end up with either — and a
        1px shoulder each side so a full-width bar does not sit under the border
        it is drawn beside.
        """
        t = _TUNEABLES_FULL_ROUTE
        return S_WIDTH - 2 * BORDER_W - float(t["pad_end_left"]) - float(t["pad_arriving"]) - 2.0

    def _slot0_cx(self) -> float:
        """The rightmost slot's centre.

        MEASURED only while the route fills the row exactly — the in-spec case,
        and the one the reference shows. ANY other length centres instead
        (author, 2026-08-28: "for lines that has less than 40 stations, we should
        shorten the route bar and centers the route bar"). A shorter route
        otherwise leaves its bar running out to an empty left end, and a LONGER
        one is worse: the measured anchor holds the right end while the shrunken
        pitch pushes the left wall — and the 分 sitting inside it — off the
        screen entirely, which is what keihin did.

        The BAR is what gets centred, not the station group. The two differ by
        the wall pads, which are not equal, so centring the group leaves the bar
        3px off and its left wall outside the border on the longest routes.

        One anchor serves both rows, so the columns stay aligned between them; a
        final row holding fewer cells is simply shorter on the left.
        """
        t = _TUNEABLES_FULL_ROUTE
        per = self._per_row()
        if per == int(t["slots_per_row"]):
            return float(t["slot0_cx"])
        group = (per - 1) * self._pitch()
        bar_w = group + float(t["pad_end_left"]) + float(t["pad_arriving"])
        bar_left = BORDER_W + (S_WIDTH - 2 * BORDER_W - bar_w) / 2.0
        return bar_left + float(t["pad_end_left"]) + group

    def _rows(self) -> int:
        per = self._per_row()
        return max(1, (self._window()[1] + per - 1) // per)

    def _slot(self, di: int) -> Tuple[int, float, float]:
        """`(row, centre_x, bar_top_y)` for diagram index `di`.

        The row is fixed by the slot count rather than derived from the route's
        length: on Chūō the split IS the line's, 大月..武蔵境 then 三鷹..東京.
        Within a row the cells read RIGHT to LEFT, so column 0 is the rightmost.
        """
        t = _TUNEABLES_FULL_ROUTE
        per = self._per_row()
        local = di - self._window()[0]
        row = local // per
        col = local % per
        cx = self._slot0_cx() - col * self._pitch()
        cy = self._row_cy(row)
        return row, cx, cy - t["bar_h"] / 2.0

    def _slot_w(self) -> float:
        return self._pitch()

    def _curr(self) -> int:
        """The train's position as a DIAGRAM index."""
        if self.state is None:
            return self.display_offset
        return int(self.state.curr_stop) + self.display_offset

    def _cursor(self) -> int:
        """The visual position — lags `_curr` during a skip animation."""
        if self.state is None:
            return self.display_offset
        return int(self.state.cursor_pos) + self.display_offset

    def _row_outer(self, row: int) -> Tuple[float, float]:
        """The centres of a row's outermost slots, `(left, right)`.

        Everything the row places against its ends reads these — the walls, and
        the 分 — so a centred or a part-filled row moves them all together. A
        final row holding fewer cells than the rest is shorter on the LEFT,
        because the rows read right to left.
        """
        per = self._per_row()
        start, count = self._window()
        first_di = start + row * per
        cells = max(1, min(per, start + count - first_di))
        outer_r = self._slot0_cx()
        return outer_r - (cells - 1) * self._pitch(), outer_r

    def _row_edges(self, row: int) -> Tuple[float, float, bool, bool]:
        """`(left_x, right_x, arriving, leaving)` for one row's bar.

        The edge KINDS come first and the geometry follows them, because each
        treatment wants a different wall: a leaving edge pulls in to leave the
        chevrons room inside the screen, an arriving one pushes out so its notch
        clears the outermost station's box, and a square end keeps its own
        measured pad. One shared `bar_x + bar_w` cannot serve all three.

        An edge is a continuation iff the diagram has a cell beyond it — which is
        the whole predicate, so the next row, a frame boundary and a route too
        long for the forty slots all answer it the same way.
        """
        t = _TUNEABLES_FULL_ROUTE
        per = self._per_row()
        n_cells = len(self.display_stops)
        start, count = self._window()
        first_di = start + row * per
        last_di = min(start + count - 1, first_di + per - 1)
        # Against the WHOLE diagram, not the window — so a route too long to fit
        # gets the arriving treatment on row 1's right, where the drawing would
        # otherwise begin (author, 2026-08-28).
        arriving = first_di > 0
        leaving = last_di < n_cells - 1
        outer_l, outer_r = self._row_outer(row)
        left = outer_l - float(t["pad_leaving"] if leaving else t["pad_end_left"])
        right = outer_r + float(t["pad_arriving"] if arriving else t["pad_end_right"])
        # SNAPPED TO WHOLE PIXELS, and that is load-bearing rather than tidy. The
        # bar is a rect and rounds its edges; `draw_aapolygon` TRUNCATES the
        # triangle's. A wall derived as 605.3 - 19*30.09 - 9.59 lands on
        # 23.999999999999996, which rounds to 24 and truncates to 23 — so the
        # taper stopped one column short of the bar it is supposed to grow out
        # of, and the background between read as a 1px vertical gap (author,
        # 2026-08-29: "the triangles is not touching with the route bar"). It
        # arrived with the walls becoming derived pads; as integer literals the
        # two roundings had nothing to disagree about.
        return float(round(left)), float(round(right)), arriving, leaving

    def _dest_di(self) -> int:
        """The service's last station, as a DIAGRAM index.

        THE DIAGRAM IS THE LINE, so a route may carry stations this train never
        reaches: Keihin 727B's `dest` is 磯子 at index 40 while its `stops` run
        on to 大船 at 45 (`docs/DISPLAY.md` § Terminus), and a Chūō service
        ending at 新宿 is the same shape (author, 2026-08-28). That existing
        mechanism is the answer — ordinary stops past the route-level `dest`,
        not a second list — so everything past this index is DRAWN AND NOT
        SERVED: grey bar, grey names, no marks.

        Reads the STOP-level `dest`, which the loader fills on every stop by
        sticky propagation, so a mid-route override moves the terminus.
        """
        n = len(self.display_stops)
        # A loop's diagram is entirely on the run, and its dest name occurs
        # twice — searching for it would grey the whole thing from the origin.
        if self.stops and self.stops[0].get("name") == self.stops[-1].get("name"):
            return n - 1
        dest = ""
        if self.state is not None:
            si = int(self.state.curr_stop)
            if 0 <= si < len(self.stops):
                dest = self.stops[si].get("dest") or ""
        dest = dest or self.route_data.get("dest", "")
        if dest:
            for di in range(max(self._curr(), self.display_offset), n):
                if self.display_stops[di].get("name") == dest:
                    return di
        return n - 1

    def _marker_slot(self, minutes: Dict[int, int]) -> Tuple[int, float, float]:
        """`(row, centre_x, bar_top_y)` for the position marker.

        STOPPING puts it on the station's own slot, which is what every
        reference shows. Otherwise the train is running and the marker sits
        BETWEEN the station behind it and the one ahead — offset back toward the
        one just left, which on a right-to-left row is +x.

        THE OFFSET IS DERIVED FROM WHAT IT HAS TO CLEAR, not authored as a
        fraction of the leg: the nose has to sit clear of the approached
        station's minute box, and a midpoint does not (see `marker_box_gap`). So
        it is that box's half width plus the nose's own reach plus the gap, which
        also tracks a box widened for a three-digit number. Clamped inside the
        pitch so a shrunken out-of-spec row cannot walk the marker onto the
        station behind it.

        Keyed on `cursor_pos` while running, so it walks station by station
        across the stations run through instead of jumping the whole gap
        (`docs/DISPLAY.md` § "Station Skip Logic"). Not offset at a row's first
        cell: the station behind it is on the other row, so there is no leg on
        this row to sit in the middle of.
        """
        m = _TUNEABLES_FULL_ROUTE_MARKS
        at_station = bool(getattr(self.state, "at_station", False)) if self.state else False
        di = self._curr() if at_station else self._cursor()
        start, count = self._window()
        di = max(start, min(di, start + count - 1))
        row, cx, bar_top = self._slot(di)
        # The row-first test is on the WINDOW-LOCAL column, not the raw diagram
        # index — `_slot` above derives its own column the same way (`di - start`,
        # then `% per`), and so do `_draw_bars` and `_row_edges`. A raw `di % per`
        # agrees with them only while `start` is 0, which is every Chūō frame and
        # is why it read as correct: on a route long enough to window (Keihin's 46
        # cells, `start` 6) it suppresses the offset at a mid-row cell and applies
        # it at a row-first one, putting the marker past that row's own wall.
        if not at_station and (di - start) % self._per_row() != 0:
            mins = minutes.get(di)
            half = self._box_width(m, "" if mins is None else str(mins), int(m["time_size"])) / 2.0
            nose = -min(float(vx) for vx, _ in m["tri_verts"])
            cx += min(half + nose + float(m["marker_box_gap"]), self._pitch() - 2.0)
        return row, cx, bar_top

    def _is_passing(self, stop: Dict) -> bool:
        """A station the train runs through — no `pa` and no `pa_at_station`.

        NOTE the predicate does NOT distinguish a `pre_stop`, which carries
        neither either and so answers True. In the FULL-ROUTE view that is
        harmless: a `pre_stop` is always behind the cursor, so the index test
        greys it and marks are only drawn from the cursor forward. In the
        6-STATION view it is visible — a `pre_stop` is an eligible past cell
        (WIP § 10.1), so it takes a passing chevron.

        That is DELIBERATE and closed (author, 2026-08-30) — see `TODO.md`
        § "Closed-off paths", "Giving `pre_stops` a positive identity in the
        render path". Both models make this inference and it is not worth
        unpicking until `pre_stops` has to carry more information anyway. Do not
        re-propose a flag for it; the docstring here used to claim an exclusion
        the body never performed, and stating the conflation is the fix that was
        wanted.
        """
        return is_passing_stop(stop)

    # -------------------------------------------------------------------------
    # Elements
    # -------------------------------------------------------------------------

    def _draw_bars(self, marker_row: int, marker_cx: float, dest_di: int) -> None:
        """The two bars. Grey everywhere the train is not running, orange over
        the stretch it still has to travel.

        ONE grey covers all three cases the diagram has — the eight stations west
        of 高尾, anything the train has already left, and anything past the
        service's own terminus (author, 2026-08-28). So the row is laid down grey
        and the served stretch overdrawn, rather than three rects deciding among
        themselves where they meet.

        The served stretch is bounded twice:

        - on the right by THE MARKER'S BASE, not a slot edge and not the outside
          of its rim. [measured] every pixel right of the reference's marker runs
          52 -> 62 -> 89 -> ... -> the bar's grey; orange never appears there.
          Carrying the rim and a spare pixel into the split left a strip of
          orange under the shadow's own gradient, reading as the bar poking out
          behind the train.
        - on the left by the destination's slot edge, and only where the diagram
          carries further cells on that row. Where the terminus is the row's last
          cell the orange runs to the bar's own end, which is what keeps the
          extension past 東京 orange.
        """
        t = _TUNEABLES_FULL_ROUTE
        m = _TUNEABLES_FULL_ROUTE_MARKS
        per = self._per_row()
        pitch = self._pitch()
        start, count = self._window()
        # Clamped into the window: a destination off the drawing is not a
        # boundary inside it, it just means every visible cell is on one side.
        dest_local = max(0, min(dest_di - start, count - 1))
        dest_row = dest_local // per

        for row in range(self._rows()):
            cy = self._row_cy(row)
            top = int(round(cy - t["bar_h"] / 2.0))
            left, right, _, _ = self._row_edges(row)
            x0, x1 = int(round(left)), int(round(right))
            pygame.draw.rect(self.screen, t["behind_color"], pygame.Rect(x0, top, x1 - x0, int(t["bar_h"])))

            if row < marker_row or row > dest_row:
                continue
            # The boundary is the MARKER'S BASE, read off the vertices rather than
            # from a copy of them, so dragging the shape in the editor carries the
            # bar's split with it.
            base_dx = max(vx for vx, _ in m["tri_verts"])
            hi = right if row > marker_row else marker_cx + base_dx
            if row < dest_row:
                lo = left
            else:
                col = dest_local % per
                more_on_row = col < per - 1 and dest_local + 1 < count
                lo = (self._slot0_cx() - col * pitch) - pitch / 2.0 if more_on_row else left
            x0, x1 = int(round(max(lo, left))), int(round(min(hi, right)))
            if x1 > x0:
                pygame.draw.rect(self.screen, self.color, pygame.Rect(x0, top, x1 - x0, int(t["bar_h"])))

    def _minutes(self, cursor: int, current_time: float) -> Dict[int, int]:
        """Cumulative minutes to each stopping station ahead, by diagram index.

        The chain is E235-1000's (`draw_times`): the first cell ahead counts
        down in real time, every later one adds its static `time`. In STOPPING
        the current cell is skipped — its leg is already travelled — and the
        chain starts fresh from the next one out.
        """
        out: Dict[int, int] = {}
        if self.state is None:
            return out

        at_station = bool(getattr(self.state, "at_station", False))
        curr = self._curr()
        departure = float(getattr(self.state, "departure_time", 0.0) or 0.0)
        is_last_pa = bool(getattr(self.state, "is_last_pa", False))

        elapsed_minutes = 0.0
        if current_time > 0 and departure > 0:
            elapsed_minutes = (current_time - departure) / TIME_SCALE

        cumulative = 0
        first = True
        # Stops past the service's terminus are drawn and not served, so there
        # are no minutes to them — see `_dest_di`.
        for di in range(max(cursor, 0), min(len(self.display_stops), self._dest_di() + 1)):
            if at_station and di == curr:
                continue
            stop = self.display_stops[di]
            if stop.get("time") is None:
                continue
            if first:
                if at_station:
                    cumulative = stop["time"]
                elif is_last_pa:
                    cumulative = 1
                else:
                    cumulative = max(1, stop["time"] - int(elapsed_minutes))
                first = False
            else:
                cumulative += stop["time"]
            out[di] = int(cumulative)
        return out

    def _draw_marks(self, cursor: int, minutes: Dict[int, int], dest_di: int) -> None:
        """Per-cell decoration ON the bar, for the cells ahead of the train and
        within the service.

        Behind the train the reference carries nothing at all — the grey run
        right of the marker measures 568px unbroken across its eight slots — so
        marks are drawn only from the cursor forward. PAST THE TERMINUS is the
        same: bare grey bar, no box and no arrow (author, 2026-08-28), and the
        destination station itself carries no special mark — it is simply the
        last one that still has a box and a number.
        """
        t = _TUNEABLES_FULL_ROUTE
        m = _TUNEABLES_FULL_ROUTE_MARKS
        curr = self._curr()
        at_station = bool(getattr(self.state, "at_station", False)) if self.state else False

        start, count = self._window()
        for di in range(max(cursor, start), min(start + count, dest_di + 1)):
            if di == curr and at_station:
                continue  # the triangle owns this cell
            stop = self.display_stops[di]
            row, cx, bar_top = self._slot(di)

            if self._is_passing(stop):
                # Centred on the bar: the reference's arrow spans y 635..667 of a
                # 623..677 bar, so its own height is the measurement, not an
                # inset from the bar's edges.
                inset = (t["bar_h"] - m["arrow_h"]) / 2.0
                draw_aapolygon(
                    self.screen,
                    m["arrow_color"],
                    self._arrow_left(cx, bar_top, m["arrow_w"], m["arrow_h"], m["arrow_stroke"], inset),
                )
                continue

            # Centred on the bar's GEOMETRIC centre, so an even-height box
            # leaves the same number of bar rows above and below (author,
            # 2026-08-27: "white square should also be centered vertically on
            # the route color bar").
            cy = bar_top + t["bar_h"] / 2.0
            mins = minutes.get(di)
            text = "" if mins is None else str(mins)
            bw = self._box_width(m, text, int(m["time_size"]))
            # THE BOX NEVER CROSSES ITS ROW'S WALL. Centred on the slot it
            # overhangs by 1.6px at a leaving edge and 1.5px at the square origin
            # — the slot sits closer to the end than the box is wide. The
            # overhang lands on background, and its feather then eats the taper's
            # outermost columns, which reads as a 1px gap between the bar and the
            # arrows rather than as a misplaced box (author, 2026-08-29). Only
            # ever the outermost slot of a row, and only by a pixel or two, so the
            # box stays visually on its station.
            row_l, row_r, _, _ = self._row_edges(int(row))
            bx = min(max(cx, row_l + bw / 2.0), row_r - bw / 2.0)
            self._blit_box(m, bx, cy, bw)
            if text:
                self._blit_number(m, text, (bx, cy), int(m["time_size"]), m["time_color"])

    def _draw_units(self) -> None:
        """One 分 at the left end of each bar. See the `unit_*` block.

        Positioned by the glyph's INK box, measured off the rendered surface
        rather than assumed: `分` sits high and narrow in its em, so placing the
        font box where the ink was measured would put the glyph somewhere else
        entirely. `get_bounding_rect` gives the offset exactly, and `outlined`
        pads by a known `ceil(ow)`, so the ink's position inside the finished
        surface is arithmetic rather than a fitted fudge.
        """
        m = _TUNEABLES_FULL_ROUTE_MARKS
        # Keyed on everything that SHAPES the glyph, the way `_blit_box` and
        # `_marker_image` already are. A bare `if got is None` read these
        # tuneables once per process, so nudging the 分 in the calibration editor
        # kept re-blitting the pre-edit raster. The 6-station `_draw_unit` had the
        # same defect against its own colour and text, and is keyed the same way.
        key = (
            int(m["unit_size"]),
            float(m["unit_outline_w"]),
            float(m["unit_outline_feather"]),
            tuple(m["unit_color"]),
            tuple(m["arrow_color"]),
            m["unit_text"],
        )
        got = self._unit_img if self._unit_key == key else None
        if got is None:
            ss = _TYPE_SUPERSAMPLE
            size = int(m["unit_size"])
            font = lcd_font(_NAME_FACE, size * ss, draws=lit(m["unit_text"]))
            core = font.render(m["unit_text"], True, tuple(m["unit_color"]))
            ink = core.get_bounding_rect()
            img = outlined(core, m["unit_outline_w"], m["unit_outline_feather"], tuple(m["arrow_color"]))
            pad = math.ceil(m["unit_outline_w"])
            got = (img, pad + ink.centerx / ss, pad + ink.centery / ss)
            self._unit_img, self._unit_key = got, key
        img, ink_cx, ink_cy = got

        for row in range(self._rows()):
            cy = self._row_cy(row)
            outer_l, _ = self._row_outer(row)
            self.screen.blit(
                img,
                (
                    int(round(outer_l + m["unit_dx"] - ink_cx)),
                    int(round(cy + m["unit_dy"] - ink_cy)),
                ),
            )

    def _box_width(self, m: dict, text: str, size: int) -> float:
        """The box's width. FIXED — the number is what gives, not the box.

        THREE DIGITS MUST BE REACHABLE (author, 2026-08-28), and they are made to
        fit by compressing the run rather than by growing the box (author,
        2026-08-29: *"either by compressing or lowering font size"*). Growing it
        would put a wider box at one station than at its neighbours, which reads
        as a mistake; compressing matches what this model already does to a long
        station name, and what `docs/DISPLAY_E235.md` records as the real PIDS's
        own answer — a uniform horizontal squeeze, never a condensed cut.
        """
        return float(m["box_w"])

    def _blit_box(self, m: dict, cx: float, cy: float, w: float) -> None:
        """The minute box, soft-edged, centred on `(cx, cy)`.

        Built by the upper LCD's `_build_soft_box` rather than by a `draw.rect`,
        because the reference's edge is a ~1.5px ramp and a rect has none. That
        builder computes coverage analytically from the distance to the edge and
        takes the origin's FRACTIONAL part, which matters here more than it does
        for the clock: slot centres are 30.09 apart, so every box on the row
        lands on a different sub-pixel phase and rounding them all to the grid
        would make the row's boxes visibly uneven.

        Cached per phase, quantised to a quarter pixel — a whole row is at most
        four distinct builds instead of twenty.
        """
        h = float(m["box_h"])
        x, y = cx - w / 2.0, cy - h / 2.0
        ox, oy = math.floor(x), math.floor(y)
        fx, fy = x - ox, y - oy
        key = (w, h, round(fx * 4), round(fy * 4), m["box_feather"], m["box_corner_r"], tuple(m["box_color"]))
        got = self._box_imgs.get(key)
        if got is None:
            got = _build_soft_box(w, h, fx, fy, 0, 0, m["box_feather"], m["box_corner_r"], 0.0, 1.0, tuple(m["box_color"]), tuple(m["box_color"]))
            self._box_imgs[key] = got
        img, pad = got
        self.screen.blit(img, (ox - pad, oy - pad))

    def _blit_number(self, m: dict, text: str, center, size: int, color) -> None:
        """Centre a number in a box, drawn DIGIT BY DIGIT.

        Per character rather than per string because the declaration that keys
        the atlas is `lit("0123456789")`: a digit is a source literal, and "11"
        is not — every multi-digit total the route could produce would otherwise
        need declaring one by one. Same reason the upper LCD's clock composes
        its run from cells.
        """
        font = self._time_font(size)
        imgs = [font.render(ch, True, color) for ch in text]
        if not imgs:
            return
        total = sum(i.get_width() for i in imgs)
        h = max(i.get_height() for i in imgs)
        room = float(m["box_w"]) - 2.0 * float(m["box_side_pad"])

        # CENTRED ON ITS INK, not on the rendered surface. A digit uses neither
        # the ascender room above it nor the descender room below, and those two
        # are not equal, so centring the surface parks the run low — the trap
        # `docs/DISPLAY_E235.md` records for the 5-station countdown circles.
        # Read off the rendered glyphs rather than from `font.metrics`, so it
        # holds for an atlas font as well as a live one.
        boxes = [i.get_bounding_rect() for i in imgs]
        ink_top = min(b.y for b in boxes)
        ink_bot = max(b.y + b.h for b in boxes)
        y = center[1] - (ink_top + ink_bot) / 2.0

        if total <= room:
            x = center[0] - total / 2.0
            for img in imgs:
                self.screen.blit(img, (int(round(x)), int(round(y))))
                x += img.get_width()
            return

        # WIDER THAN THE BOX — squeeze the run horizontally, height untouched.
        # Composed onto one surface and scaled once, so the digits keep their
        # relative spacing and get a single resample instead of one per glyph.
        # Only three digits ever reach here, and no shipped route produces one.
        run = pygame.Surface((total, h), pygame.SRCALPHA)
        x = 0
        for img in imgs:
            run.blit(img, (x, 0))
            x += img.get_width()
        run = pygame.transform.smoothscale(run, (max(1, int(round(room))), h))
        self.screen.blit(run, (int(round(center[0] - run.get_width() / 2.0)), int(round(y))))

    def _arrow_left(self, cx: float, bar_top: float, w: int, h: int, stroke: int, inset: int):
        """`arrow_points` mirrored — the rows read right to left, so every arrow
        on this display points LEFT. Mirroring the shared primitive keeps its
        tip geometry rather than re-deriving a left-pointing one."""
        pts = arrow_points(0, 0, w, h, stroke)
        x0 = cx - w / 2.0
        y0 = bar_top + inset
        return [(x0 + (w - px), y0 + py) for px, py in pts]

    def _draw_position(self, cx: float, bar_top: float) -> None:
        """The green pentagon at the train, apex LEFT — the direction of travel.

        Where it goes is `_marker_slot`'s answer: the station's own slot while
        STOPPING, the middle of the leg while running. The SHAPE never changes
        between those (author, 2026-08-28).
        """
        t = _TUNEABLES_FULL_ROUTE

        # `(bar_h - 1) / 2` — the bar's centre ROW, not its centre edge: with
        # rows 267..288 the centre is 277.5, and half-heights of 11 then land the
        # marker on exactly those rows. Using bar_h/2 puts it one row low.
        mid = bar_top + (t["bar_h"] - 1) / 2.0
        # The SUB-PIXEL part of the anchor is built INTO the image, and only the
        # whole part is a blit offset. Rounding the sum instead throws away up to
        # half a pixel, and — because the surface's own origin is one of the two
        # terms — which way it rounds depends on the marker's PADDING, so
        # retuning the shadow walked the whole marker off the bar by a row.
        fx, fy = cx - math.floor(cx), mid - math.floor(mid)
        img, ox, oy = self._marker_image(_TUNEABLES_FULL_ROUTE_MARKS, fx, fy)
        self.screen.blit(img, (int(math.floor(cx)) + ox, int(math.floor(mid)) + oy))

    def _marker_image(self, m: dict, fx: float = 0.0, fy: float = 0.0):
        """The position marker as one surface, built at 4x and resolved once.

        `m` is the VIEW'S marks dict rather than a module constant, because the
        6-station view draws the same marker construction at its own size and a
        second implementation of it would drift (`principles.md` § "A second
        implementation of a production decision drifts silently"). Everything
        that shapes the image is in the cache key, so the two views cannot
        collide in one instance's cache either.

        Cached because the marker is the same drawing at every stop and only its
        position moves; rebuilding it per frame would redo a supersampled render
        15 times a second for nothing.

        Same construction as the upper LCD's train-type halo — build everything
        large, composite while large, and let ONE downscale do the antialiasing.
        A sub-pixel rim (0.9px) and a 2.5px shadow gradient are not expressible
        at 1x at all; at 4x they are 3.6px and 10px of ordinary drawing.
        """
        # Re-tinted on out-of-spec routes, so the pair is IN THE KEY as the
        # resolved value rather than as the dict's — a cached Chūō marker must
        # not be handed back for a Saikyō drive in the same process.
        tone_top, tone_bot = _marker_tones(m, self.route_data)
        key = (
            tuple(m["tri_verts"]),
            m["tri_rim_w"],
            tuple(m["tri_rim"]),
            tone_top,
            tone_bot,
            tuple(m["tri_shadow"]),
            m["tri_shadow_reach"],
            m["tri_shadow_alpha"],
            m["tri_split_dy"],
            tuple(m["tri_light"]),
            # Quantised to the supersample: a finer residual than one large
            # pixel cannot change the resolved image, and leaving it continuous
            # would key a fresh 4x build on every slot.
            round(fx * _MARKER_SUPERSAMPLE),
            round(fy * _MARKER_SUPERSAMPLE),
        )
        if self._marker_key == key and self._marker_img is not None:
            return self._marker_img, self._marker_ox, self._marker_oy

        ss = _MARKER_SUPERSAMPLE
        verts = [(float(dx), float(dy)) for dx, dy in m["tri_verts"]]
        gx = sum(p[0] for p in verts) / len(verts)
        gy = sum(p[1] for p in verts) / len(verts)

        def grown(pad, facing=None):
            return _offset_polygon(verts, pad, facing)

        # THE SURFACE BOUNDS ARE WHOLE PIXELS, and that is load-bearing twice
        # over. `int(w * ss)` and `round(w)` disagree for a fractional `w`, so
        # the "4x" downscale is really 3.94x — it resamples the rim across two
        # output rows and dims it — and `x0` then carries a fraction that moves
        # whenever the padding is retuned, walking the whole marker by a pixel
        # for a reason that has nothing to do with its geometry.
        pad = max(m["tri_rim_w"] * 4.0, m["tri_rim_w"] + m["tri_shadow_reach"]) + 2
        x0 = math.floor(min(p[0] for p in verts) - pad)
        y0 = math.floor(min(p[1] for p in verts) - pad)
        # The +1 is room for the sub-pixel residual, which shifts the geometry
        # by up to one pixel down and right inside these bounds.
        w = math.ceil(max(p[0] for p in verts) + pad + 1) - x0
        h = math.ceil(max(p[1] for p in verts) + pad + 1) - y0

        surf = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
        # PRE-FILLED WITH THE RIM COLOUR AT ZERO ALPHA, not left transparent
        # black. `smoothscale` does not premultiply — it averages RGB and alpha
        # independently — so an opaque white edge against transparent BLACK
        # resolves to a half-grey at half alpha, and the marker comes back rimmed
        # in grey rather than white. Measured above the top edge: (176,183,195)
        # against a (213,223,239) background, i.e. the "white" rim reading DARKER
        # than what it sits on. Same fix, same reason, as the upper LCD's
        # train-type halo. The shadow's own outer boundary needs no equivalent:
        # its outermost ring is already at alpha 0, so what it fringes into
        # cannot show.
        surf.fill(tuple(m["tri_rim"]) + (0,))

        def poly(pad, facing=None):
            return [((x - x0 + fx) * ss, (y - y0 + fy) * ss) for x, y in grown(pad, facing)]

        # Shadow: nested outlines on the UNLIT edges only, outermost first, each
        # written with the alpha the final image should carry at that distance.
        #
        # WRITTEN, not blended. `pygame.draw` replaces pixels on an SRCALPHA
        # surface, so drawing outermost-to-innermost leaves every point holding
        # the alpha of the smallest ring that reaches it — which is exactly the
        # linear ramp. Compositing the rings as translucent layers instead
        # ACCUMULATES: a point near the body lies inside every ring, so its alpha
        # goes 1-(1-a)^n and saturates, which is a black edge wearing a gradient's
        # construction.
        # The ramp starts where the RIM ends, so the two abut instead of one
        # burying the other. The rim runs all the way round (author, 2026-08-27:
        # "the polygon has white outline all sides"), and it has to stay visible
        # on the two shadowed edges as well — but drawing it OVER a ramp anchored
        # on the body would hide the ramp's darkest third and leave only its
        # tail, i.e. a weaker shadow than the one that is right. Offsetting the
        # ramp keeps its profile exactly and just moves it out by the rim's
        # width, which is the one change that satisfies both.
        shadow_rgb = tuple(m["tri_shadow"])
        unlit = (-m["tri_light"][0], -m["tri_light"][1])
        steps = max(1, int(round(m["tri_shadow_reach"] * ss)))
        for i in range(steps, 0, -1):
            frac = (i - 0.5) / steps  # 1 = outermost
            a = int(round(m["tri_shadow_alpha"] * (1.0 - frac)))
            pad = m["tri_rim_w"] + m["tri_shadow_reach"] * frac
            pygame.draw.polygon(surf, shadow_rgb + (a,), poly(pad, unlit))

        if m["tri_rim_w"]:
            pygame.draw.polygon(surf, tuple(m["tri_rim"]), poly(m["tri_rim_w"]))
        pygame.draw.polygon(surf, tone_bot, poly(0))
        # The light tone is the TOP half only, split on the bar's centre line.
        # Clipped rather than given its own polygon, so the two halves share one
        # outline and cannot disagree along the slants.
        surf.set_clip(pygame.Rect(0, 0, surf.get_width(), int((m["tri_split_dy"] - y0 + fy) * ss)))
        pygame.draw.polygon(surf, tone_top, poly(0))
        surf.set_clip(None)

        self._marker_img = pygame.transform.smoothscale(surf, (w, h))
        self._marker_ox, self._marker_oy = x0, y0
        self._marker_key = key
        return self._marker_img, x0, y0

    @staticmethod
    def _stack_top(bottom: float, chars: int, pitch: float, font) -> float:
        """Top y that puts a `chars`-tall stack's LAST character on `bottom`.

        `draw_1col_text_plain` steps by `pitch` and draws each character at the
        font's own height, so the run ends at `top + (n-1)*pitch + get_height`,
        which is `line_gap` short of `top + n*pitch`. Anchoring on `n*pitch`
        therefore moves every name whenever the gap is retuned — the size and
        the gap stop being independent, and a fit on one drifts the other.
        """
        return bottom - ((chars - 1) * pitch + font.get_height())

    def _draw_names(self, dest_di: int) -> None:
        """Vertical names above each bar, never compressed.

        The box is a fixed six characters — the spacing the reference allows,
        against Chūō's five-character longest — and the stack is bottom-aligned
        onto the bar, so a short name hangs from the bar rather than from the
        top of the box.
        """
        n = _TUNEABLES_FULL_ROUTE_NAMES
        font = self._name_font(int(n["font_size"]))
        pitch = font.get_height() + int(n["line_gap"])
        curr = self._curr()

        start, count = self._window()
        for di in range(start, start + count):
            stop = self.display_stops[di]
            name = stop.get("name") or ""
            if not name:
                continue
            _, cx, bar_top = self._slot(di)
            # THE BAR AND THE NAMES ABOVE IT ARE ONE THING (author, 2026-08-28:
            # "if route bar it's gray, then station names should be gray as
            # well"), so a grey bar always carries grey names — behind the train
            # and past the service's terminus alike. The implication runs one way
            # only: an orange stretch can still carry a grey name, because a
            # station the train passes THROUGH is greyed on its own account. So a
            # name is black only where the bar is orange AND the train stops.
            #
            # `di == curr` is tested first and wins outright, rather than being
            # left to fall out of the other two. A route ORIGIN carries `pa: []`
            # — it is where the run begins, so it has no approach announcement —
            # and `_is_passing` reads that as a station the train runs through,
            # which greyed 高尾 while the train was standing at it. E235 has the
            # same hole and papers over it with a boot special case in its mark
            # drawing; here the author's rule already names this station, so
            # saying so directly is both the fix and the spec.
            dim = di != curr and (di < curr or di > dest_di or self._is_passing(stop))
            color = n["color_dim"] if dim else n["color_ahead"]

            parts = [p for p in name.split(" ") if p]
            bottom = bar_top - n["bar_gap"]

            if len(parts) == 1:
                draw_1col_text_plain(
                    font,
                    parts[0],
                    int(round(cx - font.size(parts[0][0])[0] / 2.0)),
                    int(round(self._stack_top(bottom, len(parts[0]), pitch, font))),
                    color,
                    self.screen,
                    line_gap=int(n["line_gap"]),
                )
                continue

            # A SPACE IS A LINE BREAK, not a character (docs/DATA_FORMAT.md), and
            # the handling is E235-1000's `utils.draw_stops_text` — which mimics
            # an E233-1000, so it is this family's own (author, 2026-08-27). Its
            # structure: the RIGHT column reads first and is RAISED, the left one
            # hangs from the bar like every other name.
            #
            # WITHOUT its compression (author). E235-1000 squeezes the longer
            # part into the shorter one's height; here names are never
            # compressed, so each column keeps its natural pitch and the longer
            # one simply starts higher.
            col_w = font.size(parts[0][0])[0] + int(n["col_gap"])
            leftmost = cx - (len(parts) - 1) * col_w / 2.0
            for i, part in enumerate(parts):
                px = leftmost + (len(parts) - 1 - i) * col_w  # i = 0 is RIGHTMOST
                col_bottom = bottom - (n["compound_raise"] if i == 0 else 0)
                draw_1col_text_plain(
                    font,
                    part,
                    int(round(px - font.size(part[0])[0] / 2.0)),
                    int(round(self._stack_top(col_bottom, len(part), pitch, font))),
                    color,
                    self.screen,
                    line_gap=int(n["line_gap"]),
                )

    def _draw_continuity(self, cursor: int, dest_di: int) -> None:
        """Every bar edge past which the route continues. See the `cont_*` block.

        ONE PREDICATE PER EDGE — does the route continue past it? — and it does
        not care whether the continuation is the next row, the next frame, or a
        part of the line the forty slots cannot hold (author, 2026-08-28: an
        out-of-spec route too long to fit puts the same arrows on row 1's RIGHT,
        where the diagram would otherwise begin). A square end is reserved for an
        edge where the route genuinely stops.

        Which of the two treatments an edge takes follows from where it sits in
        the row's travel: an edge at the END of travel is LEAVING and takes the
        added triangle, one at the START is ARRIVING and takes the subtracted
        one. So the two are derived per edge rather than hard-coded per row, and
        a windowed diagram gets them right without a new case.

        THE SHAPES DIM WITH THE BAR because they are part of it (author,
        2026-08-28: "grey, because it is A PART OF THE ROUTE BAR"). Each edge
        colours off the segment it draws — the one leg that crosses it.

        The leaving group anchors on `bar_wrap_x`, NOT on the extended terminus
        edge: the 分 sits wherever the bar happens to be and does not lengthen
        it, and anchoring here to the longer edge is what walked this group off
        the screen.
        """
        t = _TUNEABLES_FULL_ROUTE
        m = _TUNEABLES_FULL_ROUTE_MARKS
        per = self._per_row()
        start, count = self._window()
        h = int(t["bar_h"])
        w = float(m["cont_chev_w"])
        pitch = float(m["cont_chev_pitch"])
        tri_w = float(m["cont_tri_w"])

        for row in range(self._rows()):
            cy = self._row_cy(row)
            top = int(round(cy - h / 2.0))
            first_di = start + row * per
            last_di = min(start + count - 1, first_di + per - 1)
            left, right, arriving, leaving = self._row_edges(row)

            # (wall, the leg crossing this edge, subtract?, chevron direction).
            # The rows read right to left, so travel STARTS at the right edge and
            # ENDS at the left one.
            edges = []
            if arriving:  # the route runs in from off this row
                edges.append((right, first_di, True, +1.0))
            if leaving:  # it runs on past this row
                edges.append((left, last_di + 1, False, -1.0))

            for wall, leg_to, subtract, sign in edges:
                # EVERY SHAPE POINTS LEFT — the direction the rows read and the
                # train travels. The passing-station arrows, the marker's nose and
                # both edges' triangles all agree. Mirroring the arriving end so
                # its shapes faced outward was an invention (author, 2026-08-28:
                # "what are your arrows trying to achieve by pointing to the
                # right").
                #
                # So the apex is `wall - tri_w` at BOTH edges. At a leaving edge
                # the wall is the bar's left end, which puts the triangle outside
                # the bar and draws it in the bar's colour — a taper. At an
                # arriving edge the wall is the bar's right end, which puts the
                # SAME triangle inside, and drawing it in the background colour
                # subtracts it — a notch.
                #
                # `sign` is the direction the chevrons run from that apex:
                # downstream at a leaving edge (continuing away past the taper),
                # upstream at an arriving one (arriving into the notch). Drawn
                # AFTER the notch and in the bar's colour, so the nearest tip
                # lands inside the V and nestles rather than vanishing into the
                # background filling it (author).
                ahead = cursor <= leg_to - 1 if sign < 0 else cursor < leg_to
                color = self.color if (ahead and leg_to <= dest_di) else t["behind_color"]
                apex = wall - tri_w
                n = int(m["cont_chev_n_arrive"] if subtract else m["cont_chev_n"])
                draw_aapolygon(
                    self.screen,
                    LOWER_BG if subtract else color,
                    [(wall, top), (wall, top + h), (apex, top + h / 2.0)],
                )
                # THE GAP IS BETWEEN DRAWN EDGES, and which edge faces the gap
                # differs by treatment — so the first chevron's offset does too
                # (author, 2026-08-28: "you can push more the chevs into the
                # notch ... the margin between the notch and 1st chev are the
                # same to the 2nd chev"). At a LEAVING edge the triangle is solid
                # and its leading slant faces the chevron's TRAILING slant, which
                # sits `stroke` behind the tip, so a full pitch back leaves
                # `pitch - stroke` of background. At an ARRIVING edge the bar's
                # boundary IS the notch's apex slant and it faces the chevron's
                # LEADING slant, at the tip itself — so a full pitch there leaves
                # a whole pitch of background, twice the gap between the chevrons.
                # Starting at `pitch - stroke` puts both gaps on the same number.
                first = (pitch - float(m["cont_chev_stroke"])) if subtract else pitch
                for k in range(n, 0, -1):
                    point = apex + sign * (first + (k - 1) * pitch)
                    draw_aapolygon(
                        self.screen,
                        color,
                        self._arrow_left(point + w / 2.0, top, w, h, m["cont_chev_stroke"], 0),
                    )

    # -------------------------------------------------------------------------
    # Frame
    # -------------------------------------------------------------------------

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Draw the whole view. Pure render — mutates no state."""
        self.state = state
        cursor = self._cursor()
        dest_di = self._dest_di()
        minutes = self._minutes(cursor, current_time)
        marker_row, marker_cx, marker_top = self._marker_slot(minutes)

        self._draw_bars(marker_row, marker_cx, dest_di)
        self._draw_continuity(cursor, dest_di)
        self._draw_marks(cursor, minutes, dest_di)
        self._draw_units()
        self._draw_position(marker_cx, marker_top)
        self._draw_names(dest_di)

    def draw(self, current_time: float = 0.0) -> None:
        if self.state is not None:
            self.show_stops(self.state, current_time)

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Nearest slot on the row the click landed in, as a SIM stop index.

        A click on a `pre_stop` returns None — those cells are not places the
        simulator can be put.
        """
        t = _TUNEABLES_FULL_ROUTE
        per = self._per_row()
        slot_w = self._slot_w()
        for row in range(self._rows()):
            cy = self._row_cy(row)
            if abs(my - cy) > t["bar_h"] * 2:
                continue
            col = int(round((self._slot0_cx() - mx) / slot_w))
            if not (0 <= col < per):
                return None
            start, count = self._window()
            di = start + row * per + col
            if di < self.display_offset or di >= start + count or di >= len(self.display_stops):
                return None
            return di - self.display_offset
        return None


# =============================================================================
# 6-station view — WIP § 10
#
# SIX CELLS, AND THE TRAIN'S CELL IS THE RIGHTMOST. The window carries one
# already-passed cell behind it, and a `pre_stop` is eligible to be that cell
# (author, 2026-08-29). Near the end of the run the window LOCKS to the last six
# and the marker walks leftward inside it. That is E235-1000's 8-station rule at
# `VISIBLE_COUNT` 6 — and it needs no mirroring in index space, because a
# diagram index INCREASES in the direction of travel while screen x decreases.
# So the window arithmetic is E235's unchanged and only the slot -> x mapping is
# reversed.
#
# THE BAR IS ONE LEFT-POINTING ARROW. Its left end always tapers to a point and
# its right end always runs flush off the screen edge, whatever lies past either
# (author, 2026-08-29). This is NOT the full-route view's end treatment, whose
# taper answers "does the route continue past this edge?" — here it is the
# direction of travel and is unconditional. The ochanomizu capture is what
# separates the two: 東京 is the end of the line AND of the service, and the bar
# still tapers past it.
#
# THE BAR DOES NOT DIM. One colour end to end whatever the train has passed
# (author). Only the NAMES grey, and they grey on their own account at a station
# the train runs through — so the bar reads identically either side of the
# marker and the full-route view's orange/grey split has no counterpart here.
#
# GEOMETRY IS MEASURED off both 6-station references, which agree:
#
#   bar centre    y/H 0.6650                    -> 319.0
#   bar height    50% crossings 510.15..570.75  -> 35.8
#   left apex     x/W 0.0054                    -> 5.9
#   slot pitch    from the minute boxes         -> 94.2, slot 0 at 558.5
#
# The 36px bar is 64% thicker than the full-route view's 22 on the same canvas,
# and the marks scale by their own factors rather than by that one — the two
# views are separately proportioned and NOTHING scales from one to the other.
# =============================================================================
# fmt: off
_TUNEABLES_SIX_STATION = {
    "bar_cy":       319.0,  # [measured] both references, y/H 0.6650
    "bar_h":           36,  # [measured] 35.8 between the two 50% crossings
    # THE BAR SPANS THE WHOLE SCREEN and is not built out of the slots. Its left
    # end is a triangle whose APEX sits here and whose base is `arrow_depth` to
    # the right of it; its right end is flush with the screen edge. Both
    # references carry exactly six cells, so they cannot say whether the ends
    # track the outermost slots — and a bar that is one arrow across the display
    # is the reading that also survives a route with fewer stations.
    "arrow_apex_x":   6.0,  # [measured] 5.9 at the bar's centre row
    # DEPTH IS THE DISPLAY'S SHARED SLANT, not a free number: the full-route
    # view's triangle is 11 deep on a 22 bar, so half the height is the one
    # pointiness every pointed thing on this display carries (WIP § 9.3.4).
    # Measured here as ~18.7 against a bar of 36, which is that same half.
    "arrow_depth":     18,
    "slots":            6,  # cells in the window
    # [measured] LEAST-SQUARES over the takao reference's six name-column
    # centroids: centre(k)/W = 0.87474 - k * 0.14748, k from the RIGHT.
    #
    # Six points from one capture beat a two-point fit averaged across two. The
    # minute box's own centre is a >240 core whose edges quantise, so pairs of
    # boxes gave 94.55 (takao) against 94.05 (ochanomizu) and an anchor 3px
    # apart; the ochanomizu columns are the weaker set besides, since its three
    # RIGHTMOST names are grey and a threshold clips a grey glyph asymmetrically.
    # The overlay against takao is what showed the averaged anchor drifting ~2px
    # at the right-hand end while the left end sat true.
    "slot0_cx":     559.8,
    "slot_pitch":   94.38,
    # THE UNIT LABEL — （分）, WITH PARENTHESES, where the full-route view draws a
    # bare 分. One per bar, at the LEFT end: on the bar's SQUARE part, right of
    # the arrow, and BOTTOM-ALIGNED WITH THE MINUTE BOX'S BOTTOM rather than
    # centred on the bar (author, 2026-08-29).
    #
    # It is absent from both references — the author states it is there and that
    # the captures are wrong — so every number here is AUTHORED.
    #
    # WHITE, AND FLAT (author, 2026-08-29). NOT the full-route 分's construction:
    # that one is dark ink carrying a white outline, because it sits on a bar
    # whose colour it has to survive; this one is simply white on the bar and
    # takes no outline at all.
    #
    # SIZED AT ROUGHLY HALF THE MINUTE BOX (author) — the box is 26.3 tall, so
    # the label's ink is about 13. Derived from the box rather than authored as
    # its own number, so the two stay in proportion when the box is retuned.
    #
    # THE BAR'S LENGTH IS THE BAR'S OWN. The label sits on whatever is there and
    # the square part is not extended to carry it (author) — the same relation
    # WIP § 9.3.3 records, and reasoning the other way round is what once let a
    # label nudge move a bar.
    "unit_text":  "（分）",
    "unit_size_ratio": 0.5,  # of the minute box's height
    "unit_dx":         4.0,  # ink LEFT edge, right of the arrow's base
    "unit_color":  (255, 255, 255),
    "bar_color":   tuple(BAR_ORANGE),  # route `color` default; the bar never dims
}

# THE MARK SAYS WHAT KIND OF STATION IT IS, and the number is content that may be
# absent (author, 2026-08-29): a white box where the train stops, a white
# left-pointing chevron where it runs through. So the box is drawn EMPTY at a
# stopping station BEHIND the train; past the service's own terminus nothing is
# drawn on the bar at all.
#
# [measured] on both references, which agree to a tenth of a pixel — the box's
# white bbox is 49 x 41 native on takao (÷1.694) and 68 x 56 on ochanomizu
# (÷2.344). The chevron likewise, 18.5 x 33 and 27.5 x 46.5.
#
# NOTHING HERE SCALES FROM THE FULL-ROUTE VIEW. Its bar is 22 and this one is 36
# (×1.64), but the box goes 22.4 -> 29.0 (×1.29) and the chevron 8 -> 11.3
# (×1.41). Three different factors, so the two views are separately
# proportioned exactly as WIP § 7 says.
# fmt: off
_TUNEABLES_SIX_STATION_MARKS = {
    # SIZED SO OUR >240 CORE MATCHES THE REFERENCE'S, which is the only honest
    # comparison available: a white-threshold bbox under-reports a feathered box
    # by the feather (WIP § 9.3.3), so the reference's 28.9 x 24.2 core is NOT
    # the geometric size. Authoring those numbers directly rendered a core of
    # 26.5 x 22.0 — short by exactly the feather, twice over. The instrument
    # asks the identical question of both sides, so matching cores is what makes
    # the two numbers comparable at all.
    "box_w":       31.4,   # core 28.9 both sides
    "box_h":       26.3,   # core 24.2 both sides
    "box_feather":  1.7,   # inherited from the full-route box, not re-measured
    "box_corner_r": 0.0,   # square, as the full route's
    "box_side_pad": 2.2,   # clear px each side of the digits before they squeeze
    "box_color":       (253, 253, 253),
    "time_size":     30,   # [measured] a single digit's ink runs 14.1 x 20.3 on
                           # both references (takao's 7, ochanomizu's 5)
    "time_color":      (15, 15, 15),
    "arrow_w":       11,   # [measured] 11.3
    "arrow_h":       20,   # [measured] 19.8
    "arrow_stroke":   3,   # `arrow_points` body thickness
    "arrow_color":     (253, 253, 253),
    # THE POSITION MARKER IS NOT THE FULL-ROUTE ONE SCALED. Measured here at
    # 33.6 wide on a 36 bar (w/h 0.93) against 16 on a 22 bar (0.73), so it is
    # proportionally much wider — a different shape, not a bigger copy.
    #
    # [measured] off the takao reference's classified map, as offsets from the
    # slot centre (559.8) and the marker's anchor row (318.5). Same five-vertex
    # topology as the full route's — top-right, bottom-right, bottom-shoulder,
    # apex, top-shoulder — and a different SHAPE, which is the point: there the
    # shoulders sit near the centre so the nose is most of the width, here they
    # sit far left, so the body is a long flat block with a short 7px point.
    # Stretching the full-route pentagon to this bbox reproduced the extent and
    # not the shape, and the overlay showed it as a wedge against a block.
    #
    #   green body  x 538.5..575.7 (37.2)   y 303.2..333.3 (30.1)
    #   right edge  vertical, constant across every row
    #   left edge   two slants meeting at y 318.2, 7.1px proud of the shoulders
    "tri_verts":     ((15.9, -15.3), (15.9, 14.8), (-11.9, 14.8), (-21.3, -0.3), (-14.2, -15.3)),
    # No `tri_h` / `tri_base_dx` here either — same reason as the full-route dict.
    # The measured facts they carried are properties of `tri_verts` above: its
    # y-extent is 30.1, INSET from the 36px bar (unlike the full-route marker,
    # which stands its bar's full height), and its base sits at x 15.9.
    "tri_light":     (-1.0, -1.0),
    "tri_shadow":      (52, 62, 59),
    "tri_shadow_reach": 3.2,
    "tri_shadow_alpha":  235,
    # [measured] a vertical slice reads (64,177,62) above and (0,103,0) below —
    # the SAME two tones the full-route marker carries, so they are the model's,
    # not the view's.
    "tri_color_top":   (65, 176, 60),
    "tri_color_bot":   (0, 103, 0),
    "tri_rim":         (255, 255, 255),
    "tri_rim_w":       1.5,
    "tri_split_dy":    0.0,  # [measured] the tones change ON the anchor row
    "marker_box_gap":  1.0,  # clearance the nose keeps from the next box
}

# THE NAME BOX IS EXACTLY THREE CHARACTER SLOTS, and a name grows ABOVE it
# rather than squeezing into it. [measured] per character on BOTH references —
# the ink extent of a whole stack cannot say this, because a stack ending on a
# short glyph measures shorter at the same layout, so the numbers below are
# centre-to-centre PITCHES:
#
#   立川 (2, takao)      pitch 60.52   centres 201.6 / 262.1
#   神田 (2, ocha)       pitch 60.55   centres 202.3 / 262.9
#   八王子 (3, takao)    pitch 30.1    centres 202.2 .. 262.4
#   市ケ谷 (3, ocha)     pitch 29.85   centres 205.3 .. 265.0
#
# Two characters take the FIRST and LAST of three slots (60.5 = 2 x 30.2) and
# three fill all three — which is what `utils.draw_1col_text` does with a
# vert_space of three slots, and it is why the earlier reading of this as "a
# fixed box everything compresses into" was wrong: it happens to be right for
# every length up to three and wrong from four.
#
#   西八王子 (4, takao)  pitch 30.1  — the 3-char pitch KEPT, one slot above the box
#   御茶ノ水 (4, ocha)   pitch 27.3  — 9% tighter, and sitting lower
#
# 西八王子's IS THE RULE, and the ochanomizu frame is set aside (author,
# 2026-08-29 — "generally i don't understand why as well, let's just forget
# about ochanomizu"). Four characters keep the natural pitch and the stack grows
# above the box, which is the author's own model stated directly: "4 chars
# should be natural length as well, nothing says station names should all same
# height."
#
# The 9% difference is real rather than a crop artefact — the whole ochanomizu
# name band sits ~2.8px below takao's and correcting for that leaves the
# compression untouched — and nothing found selects it: neither passing-vs-
# stopping nor a kana in the name, since a kana changes nothing at three
# characters (市ケ谷 sets the same 29.85 as the all-kanji 水道橋). Recorded so it
# is not re-derived, NOT as an open question.
#
# FIVE AND UP COMPRESS INTO THE FOUR-CHARACTER EXTENT (author, 2026-08-29 —
# 武蔵小金井 "compress into 4 chars spacing, but it's the 西八王子's pitch"). So the
# stack has a CEILING of four slots at the natural pitch and never grows past it;
# a longer name squeezes into that same span. Which also means the element can
# never reach the upper band — the 4-slot extent tops out at ~158 against a
# lower area starting at 149 — so no clamp against the screen is needed, and one
# is not written: the cap is the rule, not a guard bolted onto it.
# fmt: off
_TUNEABLES_SIX_STATION_NAMES = {
    "font_size":     30,   # ink measures 28.3..29.5 wide per column; ShinGo sets
                           # ~0.95 of the em, so 30 is the em that produces it
    "box_top":    186.5,   # [measured] the band's top on both references
    "box_h":       90.5,   # [measured] 186.5..277 — THREE character slots
    "box_slots":      3,   # what `box_h` holds at the natural pitch
    "max_slots":      4,   # the ceiling: a longer name compresses into this span
    # A SPACE IS A LINE BREAK (docs/DATA_FORMAT.md), and this view has the width
    # for two columns, so it draws them — the RIGHT column reads first and is
    # RAISED, the left hangs from the box's bottom. That is E235-1000's
    # 8-station treatment and the full-route view's, i.e. this model's own norm
    # rather than a borrow; dropping the space instead crammed さいたま新都心's
    # seven characters into one column, which the coverage sheet showed at once.
    # Chūō has no compound name — the case exists only on a borrowed route.
    "compound_ratio": 0.75,  # of `box_h`, the height BOTH columns are laid into
    "col_gap":          2,   # px between the two columns
    "color_ahead":     (0, 0, 0),
    "color_dim":       (150, 160, 178),
    # THE CODE ROW — `JC-19`, hyphenated and horizontal, where the upper LCD's
    # badge stacks the same code without a hyphen and boxes it. DRAWN ONLY AT A
    # STATION THE TRAIN STOPS AT (author, 2026-08-29); one it runs through
    # carries its grey name and no code. The takao capture shows grey codes under
    # its passing stations and the ochanomizu one shows none — the author's rule
    # is the ochanomizu frame.
    #
    # The face is the JR signage one, which is also the badge helper's hardcoded
    # face — a station code is the same artefact whether it is boxed or not, so
    # it is not a per-view typeface choice.
    "code_face":  "NeueFrutigerWorld-Bold.otf",
    "code_size":     19,   # sized to the reference's CAP HEIGHT, 13.0. Its run
                           # is then ~14% wider than the reference's, and that is
                           # a FACE difference rather than a size one: only the
                           # Bold cut of the signage face ships, and the face is
                           # not a per-view choice (`conventions.md` § "Station-code
                           # badge typeface is fixed"). Left as it stands for the
                           # author rather than swapped for a Latin face that
                           # would fit the width and be the wrong typeface.
    "code_cy":    289.2,   # [measured] ink centre y, 281.6..296.4
    # No `code_color` — the code takes the NAME's colour, so the two cannot be
    # dimmed apart. A second key here would be a canonical-source duplication
    # of `color_ahead` / `color_dim` above (`conventions.md` § Tooling), and it
    # was one: it held a fixed black and silently outranked the greying.
}
# fmt: on

# THE INLINE TRANSFER BAND — one block per station, under its own cell.
#
# Its entries and their ORDER come from the EXISTING pipeline, not from anything
# authored here: `data/stations.json` `transfers` through `apply_transfer_filter`
# with the route's `line_code` / `transfer_view`, so the list matches what the
# standalone transfer view would show (author, 2026-08-29). A non-JR operator's
# mark is whatever that pipeline already resolves.
#
# [measured] off the takao reference's 立川 block, whose three rows give the
# pitch twice over: ink bands at y 341.25..354.83, 356.61..369.00 and
# 371.96..385.54, i.e. tops 15.36 and 15.35 apart. The bar ends at 337, so the
# band starts 4.25 below it. Row ink is ~13 and the badge ~12.9 square.
#
# THE NAMES ARE BLACK, not blue. WIP § 7's "line names in blue" was an eyeball
# note; the ink samples (3,6,9) / (12,13,14) / (14,15,20) — near-black with a
# blue cast the eye reads as blue at this size.
#
# CENTRED ON THE CELL, which is the one thing the references say cleanly: at
# 東京 the block's ink centres on 89.97 against a cell centre of 90.0. Every
# other block is wider than the 92.8 pitch it sits under, so neighbouring blocks
# interleave and an ink bbox cannot be attributed to one cell — which is exactly
# why the author asked to settle the horizontal rule against a render rather
# than a measurement (*"each transfer list optimizes itself … it would offset a
# little to the left from the fixed location to accept a longer line"*).
#
# OPEN — that optimisation. Today a block is centred and then clamped inside the
# screen, and nothing pushes it off its cell to make room for a neighbour.
# fmt: off
_TUNEABLES_SIX_STATION_TRANSFERS = {
    # THE BAND HANGS OFF THE BAR, NOT OFF THE SCREEN. `bar_gap` is clear px
    # between the bar's bottom edge and the first row's ink, so retuning the bar
    # carries the band with it instead of stranding it.
    #
    # AND IT TIGHTENS WHEN CROWDED (author, 2026-08-29): a station with a long
    # list runs its last row into the screen's bottom edge, and the whole band
    # then pushes up a few px rather than clipping. The reference is that case —
    # 東京's ten rows put its first ink at 341.25 against a bar ending at 337, a
    # gap of 4.25, which is the TIGHTENED value; 8 - 4 reproduces it exactly. A
    # route whose longest block is short sits at the full 8.
    "bar_gap":         2,  # nominal clear px below the bar — ALMOST TOUCHING it
                           # (author, 2026-08-29), so the list reads as belonging
                           # to the station above rather than floating
    "crowd_push":      4,  # max px the band tightens by when the tail is near
                           # the bottom edge — never past the bar
    "bottom_pad":      2,  # clear px the last row wants above the screen border
    "row_pitch":   14.07,  # [measured] on ochanomizu, twice (393.98 / 408.05 /
                           # 422.12). Takao's own block reads 15.35, and the
                           # overlay is what settled it: at 15.35 our 東京 block
                           # runs a row short of the reference's nine
    # WRAP IS NOT A WIDTH FALLBACK — compression is. A `･`-separated name
    # wraps only when squeezing it into one row would go below `min_squeeze`,
    # and it then splits at its MIDDLE separator. That reproduces the
    # reference exactly: 東海道･山陽新幹線 needs 0.94 and stays on one row, while
    # 東北･山形･秋田･北海道･上越･北陸新幹線 needs 0.40 and cuts 3 + 3 into
    # 東北･山形･秋田･ ｜ 北海道･上越･北陸新幹線 — the cut the author named.
    # Splitting on width instead put the cut a segment early and left the
    # second line squeezed to nothing.
    "min_squeeze":   0.7,  # of natural width, before a name wraps instead
    "badge":          12,  # row ink measures 13.2 and the badge sets it
    "badge_gap":       2,  # badge group -> name
    "inter_badge":     2,  # between stacked badges of one entry
    "name_size":      11,  # AUTHORED DOWN from a measured 14 (author,
                           # 2026-08-29: "think font size is tooo big for now").
                           # The reference's own row is hard to read a size off:
                           # its badge ink runs into its text with no separable
                           # gap at this scale, so badge-plus-gap cannot be
                           # subtracted to leave a glyph width. Tuned by eye
                           # against the overlay instead, which is what the
                           # element is for.
    "name_color":  (12, 13, 18),  # [measured] near-black, NOT blue
    "edge_pad":        3,  # clear px inside the screen border
    # TWO POSITIONS (author, 2026-08-29). A block sits at a NOMINAL anchor inset
    # into its cell, and a block too wide for the room shifts LEFT by however
    # much it overruns — "each transfer list optimizes itself … it would offset a
    # little to the left from the fixed location to accept a longer line".
    #
    # [measured] on the ochanomizu reference, and the sign of every offset from
    # the cell's left edge follows block WIDTH, not entry count:
    #
    #   東京 (9)          -1.4      水道橋 (1)          +6.7
    #   神田 (3)          -5.9      飯田橋 (4, short)  +14.0
    #   御茶ノ水 (4, long) -5.8      市ケ谷 (4, short)  +15.9
    #
    # 御茶ノ水 and 飯田橋 both hold four entries and land 20px apart, because the
    # first carries 中央・総武線（各駅停車）. Not a band-wide grid either — block
    # to block runs 88..105 against a 92.8 cell pitch.
    "nominal_inset":  15,  # of the cell's left edge, before any shift
    "max_shift":      22,  # furthest left a wide block may be pulled
    # TWO LISTS NEVER TOUCH — there is a gutter between them, and it is enforced
    # PER ROW (author, 2026-08-29): a row compresses to stop short of the
    # neighbouring station's row, rather than running up against it. A row whose
    # neighbour has nothing at that depth keeps its natural width and needs no
    # gutter, which is why this belongs to the row bound and not to the block.
    "list_gap":        5,  # clear px between one row and the next list's
}

# THE SKIP BREAK — the S-shaped slit through the bar where the far cell jumped
# over stations (author, 2026-08-29: "there's a 's' shape thing between
# musashisakai and shinjuku"). It marks the omission, so the far cell's big
# countdown reads as "and then, much later" rather than as a next-door station.
#
# [measured] on the kokubunji reference (1337 wide, scale 2.089), the slit's left
# edge walks cols 22 / 22 / 20 / 19 / 20 / 24 / 30 / 31 / 29 / 28 down the bar's
# height — one S, leaning left in the upper half and right in the lower. Sits at
# the MIDPOINT between the jumped cell and its neighbour: canvas ~134, against
# 新宿 at ~88 and 武蔵小金井 at ~182.
# fmt: off
_TUNEABLES_SIX_STATION_SKIP = {
    "width":         3.4,  # [measured] ~7 native / 2.089
    "amplitude":     3.0,  # [measured] half the peak-to-peak wander of the slit
    "steps":          24,  # quads down the bar; the curve is drawn as a strip
    "color":  tuple(LOWER_BG),  # the slit shows the background through the bar
}
# fmt: on

SIX_STATION_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)


def _wrapped_pairs(block):
    """Index pairs `(first, second)` for each wrapped entry in a block.

    A continuation row is the one carrying NO badges — every entry resolves at
    least the `_universal` icon, so an empty icon list can only mean "this is the
    tail of the row above". That keeps the pairing structural rather than
    re-deriving which names wrapped.
    """
    return [(i - 1, i) for i in range(1, len(block)) if not block[i][0]]


class JapaneseSixStationDisplay:
    """Six cells, the train's at the right. See the block above and WIP § 10."""

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self.state = None

        self.pre_stops = route_data.get("pre_stops", [])
        self.display_stops: List[Dict] = list(self.pre_stops) + list(stops)
        self.display_offset = len(self.pre_stops)
        self.color = tuple(route_data.get("color", _TUNEABLES_SIX_STATION["bar_color"]))

        self._unit_img = None
        # Transfer band — the parent's own pipeline, loaded once. `line_code` /
        # `transfer_view` are optional: an out-of-spec route without them renders
        # unfiltered, which is the soft floor CLAUDE.md's scope table asks for.
        root = project_root()
        self._tp_lines = json.loads((root / "data" / "lines.json").read_text(encoding="utf-8"))
        self._tp_stations = json.loads((root / "data" / "stations.json").read_text(encoding="utf-8"))
        self._tp_line_code = route_data.get("line_code")
        self._tp_transfer_view = route_data.get("transfer_view")
        self._tp_icon_cache: dict = {}

        self._name_fonts: Dict[int, pygame.font.Font] = {}
        self._time_fonts: Dict[int, pygame.font.Font] = {}
        self._code_fonts: Dict[int, pygame.font.Font] = {}
        self._box_imgs: Dict[tuple, tuple] = {}
        self._marker_img: Optional[pygame.Surface] = None
        self._marker_key = None
        self._marker_ox = 0.0
        self._marker_oy = 0.0

    # The construction of these is the full-route view's, parameterised by the
    # marks dict so there is ONE implementation of each rather than a fork
    # (`redlines.md` — expand the existing tool, never write a parallel one).
    # Bound as plain function attributes: the two views are siblings, not a
    # hierarchy, and inheriting would drag in twenty methods about two rows.
    _marker_image = JapaneseFullRouteDisplay._marker_image
    _box_width = JapaneseFullRouteDisplay._box_width
    _blit_box = JapaneseFullRouteDisplay._blit_box
    _blit_number = JapaneseFullRouteDisplay._blit_number
    _arrow_left = JapaneseFullRouteDisplay._arrow_left
    _time_font = JapaneseFullRouteDisplay._time_font
    _is_passing = JapaneseFullRouteDisplay._is_passing
    _dest_di = JapaneseFullRouteDisplay._dest_di
    _minutes = JapaneseFullRouteDisplay._minutes

    def _name_font(self, size: int):
        f = self._name_fonts.get(size)
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=STATION_NAMES)
            self._name_fonts[size] = f
        return f

    def _code_font(self, size: int):
        f = self._code_fonts.get(size)
        if f is None:
            f = lcd_font(
                _TUNEABLES_SIX_STATION_NAMES["code_face"],
                size,
                draws=(at("audio/*/route.json:stops[].sta_code"), lit("-")),
            )
            self._code_fonts[size] = f
        return f

    def set_state(self, state) -> None:
        """Bind AppState by reference — every draw reads it live."""
        self.state = state

    # -------------------------------------------------------------------------
    # Window + geometry
    # -------------------------------------------------------------------------

    def _cursor(self) -> int:
        """The VISUAL train position as a diagram index.

        `cursor_pos`, never `curr_stop`: this view re-centres on the train, so
        it is one of the position-locked views whose every regime must key on
        the visual position or the marker leaves the window during a skip
        (`docs/DISPLAY.md` § "Position-locked views always show the pointer").
        """
        if self.state is None:
            return self.display_offset
        return int(self.state.cursor_pos) + self.display_offset

    def _window(self) -> Tuple[int, int]:
        """`(first_di, count)` — the six cells this frame draws.

        E235-1000's three regimes at `VISIBLE_COUNT` 6, and the arithmetic is
        identical because a diagram index increases in the direction of travel:
        the one already-passed cell is `cursor - 1`, which is the LOWEST index in
        the window and therefore the RIGHTMOST cell on screen.

        A `pre_stop` is an eligible past cell (author, 2026-08-29) — nothing
        excludes it, because the window works in display-index space where a
        pre_stop is simply a cell with a lower index.
        """
        n = len(self.display_stops)
        cap = int(_TUNEABLES_SIX_STATION["slots"])
        if n <= cap:
            return 0, n
        cursor = self._cursor()
        if cursor <= 0:
            return 0, cap
        if cursor > n - cap:
            return n - cap, cap  # locked: the marker walks left inside it
        return cursor - 1, cap

    def _cells(self) -> List[int]:
        """The six diagram indices this frame draws, right to left.

        THE FURTHEST-AHEAD CELL IS A STATION THE TRAIN STOPS AT (author,
        2026-08-29 — *"last station is sometimes skipped to the next stopping
        station, if it was a skipping station"*). Six consecutive cells would
        otherwise end on a run-through station and name no reachable stop: a
        中央特快 approaching 国分寺 passes everything from 武蔵境 to 大久保, so its
        far end would be a chevron rather than an answer to "where next".

        The kokubunji reference is the case — its far cell jumps 武蔵小金井 JC-14
        straight to 新宿 JC-05, skipping eight stations, and carries the true 33
        minutes to 新宿. The omission is marked on the bar by the S-break
        (`_draw_skip_break`).

        So the window is NOT a consecutive range, which is why everything reads
        its slot position from this list rather than from an index offset.
        """
        start, count = self._window()
        cells = list(range(start, start + count))
        n = len(self.display_stops)
        if cells and self._is_passing(self.display_stops[cells[-1]]):
            nxt = next((d for d in range(cells[-1] + 1, n) if not self._is_passing(self.display_stops[d])), None)
            if nxt is not None:
                cells[-1] = nxt
        return cells

    def _slot_cx(self, di: int) -> float:
        """Screen centre x of diagram index `di`. Local 0 is the RIGHTMOST cell."""
        t = _TUNEABLES_SIX_STATION
        cells = self._cells()
        k = cells.index(di) if di in cells else di - self._window()[0]
        return float(t["slot0_cx"]) - k * float(t["slot_pitch"])

    def _bar_top(self) -> float:
        t = _TUNEABLES_SIX_STATION
        return float(t["bar_cy"]) - float(t["bar_h"]) / 2.0

    def _bar_square_x(self) -> float:
        """Left edge of the bar's SQUARE part — the arrow's base.

        Snapped to a whole pixel because the rect ROUNDS its edge while
        `draw_aapolygon` TRUNCATES the triangle's, and a derived value landing a
        hair under a whole pixel leaves a 1px gap between the two
        (`conventions.md` § UI code style; WIP § 9.3.4).
        """
        t = _TUNEABLES_SIX_STATION
        return float(round(float(t["arrow_apex_x"]) + float(t["arrow_depth"])))

    # -------------------------------------------------------------------------
    # Elements
    # -------------------------------------------------------------------------

    def _draw_bar(self) -> None:
        """The bar and its arrow head. One colour, end to end."""
        t = _TUNEABLES_SIX_STATION
        top = int(round(self._bar_top()))
        h = int(t["bar_h"])
        x0 = int(self._bar_square_x())
        pygame.draw.rect(self.screen, self.color, pygame.Rect(x0, top, S_WIDTH - x0, h))
        draw_aapolygon(
            self.screen,
            self.color,
            [(x0, top), (x0, top + h), (float(t["arrow_apex_x"]), top + h / 2.0)],
        )

    def _draw_unit(self) -> None:
        """（分）on the bar's square part, right of the arrow.

        Positioned by its INK box rather than its font box, and bottom-aligned
        with the minute box's bottom (author) rather than centred on the bar —
        so it reads as sitting on the same baseline as every number on the row.
        """
        t = _TUNEABLES_SIX_STATION
        m = _TUNEABLES_SIX_STATION_MARKS
        size = max(1, int(round(float(m["box_h"]) * float(t["unit_size_ratio"]))))
        # Keyed on everything that shapes the glyph, not just the derived size —
        # `unit_color` and `unit_text` are both editor-registered tuneables, so a
        # colour nudge on this 分 was re-blitting the pre-edit raster. Same defect
        # and same fix as the full-route `_draw_units`.
        key = (size, tuple(t["unit_color"]), t["unit_text"])
        got = self._unit_img
        if got is None or got[0] != key:
            font = lcd_font(_NAME_FACE, size, draws=lit(t["unit_text"]))
            img = font.render(t["unit_text"], True, tuple(t["unit_color"]))
            ink = img.get_bounding_rect()
            got = (key, img, float(ink.x), float(ink.y + ink.h))
            self._unit_img = got
        _, img, ink_x, ink_bot = got
        # The minute box's bottom is what the label bottoms with, so it is
        # derived from the box rather than restated as a y — a box retune moves
        # both together, which is what "bottom-aligned" has to mean.
        box_bottom = float(t["bar_cy"]) + float(m["box_h"]) / 2.0
        self.screen.blit(
            img,
            (int(round(self._bar_square_x() + float(t["unit_dx"]) - ink_x)), int(round(box_bottom - ink_bot))),
        )

    # -------------------------------------------------------------------------
    # Frame
    # -------------------------------------------------------------------------

    def _curr(self) -> int:
        """The train's position as a DIAGRAM index — the PA target."""
        if self.state is None:
            return self.display_offset
        return int(self.state.curr_stop) + self.display_offset

    def _marker_slot(self, minutes: Dict[int, int]) -> float:
        """The marker's centre x. Its own slot while STOPPING, otherwise between
        the cell just left and the one being approached.

        THE MIDPOINT, PUSHED BACK ONLY AS FAR AS CLEARING THE NEXT BOX REQUIRES.
        [measured] on the ochanomizu reference, whose train is mid-leg between
        飯田橋 and 市ケ谷: the marker's anchor sits 45.8 into a 94.38 pitch — 48.5%,
        i.e. the midpoint. The clearance its nose needs is only 38.0 here, so the
        midpoint already satisfies it and wins.

        ONE RULE SERVES BOTH VIEWS, and it is the full-route view's own numbers
        that show it: there the pitch is 30.09, so the midpoint is 15.05 against a
        clearance of 21.6 — the clearance wins, which IS the author's "i tell you
        place in the middle, but spacing does not allow it" (WIP § 9.3.6). The two
        views were never doing different things; the full-route one only ever
        exercises the clamped branch, which is why its rule reads as though the
        clearance were the whole story. Its own method still computes only the
        clearance and its render is unchanged, since its clearance always exceeds
        its midpoint — worth unifying the next time that view is open.

        Deriving the clearance from the box rather than authoring a fraction is
        what keeps it right when the box widens for a three-digit number. On a
        right-to-left row, "back toward the station just left" is +x.
        """
        m = _TUNEABLES_SIX_STATION_MARKS
        at_station = bool(getattr(self.state, "at_station", False)) if self.state else False
        di = self._curr() if at_station else self._cursor()
        start, count = self._window()
        di = max(start, min(di, start + count - 1))
        cx = self._slot_cx(di)
        if not at_station and di > start:
            pitch = float(_TUNEABLES_SIX_STATION["slot_pitch"])
            mins = minutes.get(di)
            half = self._box_width(m, "" if mins is None else str(mins), int(m["time_size"])) / 2.0
            nose = -min(float(vx) for vx, _ in m["tri_verts"])
            clear = half + nose + float(m["marker_box_gap"])
            cx += min(max(pitch / 2.0, clear), pitch - 2.0)
        return cx

    def _draw_skip_break(self) -> None:
        """The S-shaped slit through the bar where the far cell jumped.

        Drawn only when `_cells` actually skipped something, at the midpoint
        between the jumped cell and its neighbour. Built as a strip of quads
        following a sine, so the slit keeps a constant width around the curve
        rather than shearing — a single polygon with two sine edges pinches at
        the steep part.
        """
        cells = self._cells()
        start, count = self._window()
        if len(cells) < 2 or cells[-1] == start + count - 1:
            return
        t, k = _TUNEABLES_SIX_STATION, _TUNEABLES_SIX_STATION_SKIP
        cx = (self._slot_cx(cells[-1]) + self._slot_cx(cells[-2])) / 2.0
        top, h = self._bar_top(), float(t["bar_h"])
        half, amp, n = float(k["width"]) / 2.0, float(k["amplitude"]), int(k["steps"])
        for i in range(n):
            y0, y1 = top + h * i / n, top + h * (i + 1) / n
            # One full S over the bar's height, leaning left then right.
            o0 = amp * math.sin(2.0 * math.pi * (i / n) - math.pi)
            o1 = amp * math.sin(2.0 * math.pi * ((i + 1) / n) - math.pi)
            draw_aapolygon(
                self.screen,
                tuple(k["color"]),
                [(cx + o0 - half, y0), (cx + o0 + half, y0), (cx + o1 + half, y1), (cx + o1 - half, y1)],
            )

    def _draw_marks(self, minutes: Dict[int, int], dest_di: int) -> None:
        """Per-cell decoration ON the bar.

        THE MARK SAYS WHAT KIND OF STATION IT IS and the number is content that
        may be absent (author, 2026-08-29): a box where the train stops, a
        chevron where it runs through. So a stopping station BEHIND the train
        still draws its box, EMPTY — the bar reads the same either side of the
        marker, which is the same reason it does not dim. Past the service's own
        terminus nothing is drawn at all.
        """
        t = _TUNEABLES_SIX_STATION
        m = _TUNEABLES_SIX_STATION_MARKS
        cy = float(t["bar_cy"])
        top = self._bar_top()
        curr = self._curr()
        at_station = bool(getattr(self.state, "at_station", False)) if self.state else False

        for di in self._cells():
            if di > dest_di:
                continue
            if di == curr and at_station:
                continue  # the marker owns this cell
            stop = self.display_stops[di]
            cx = self._slot_cx(di)
            if self._is_passing(stop):
                inset = (float(t["bar_h"]) - float(m["arrow_h"])) / 2.0
                draw_aapolygon(
                    self.screen,
                    m["arrow_color"],
                    self._arrow_left(cx, top, m["arrow_w"], m["arrow_h"], m["arrow_stroke"], inset),
                )
                continue
            mins = minutes.get(di)
            text = "" if mins is None else str(mins)
            bw = self._box_width(m, text, int(m["time_size"]))
            self._blit_box(m, cx, cy, bw)
            if text:
                self._blit_number(m, text, (cx, cy), int(m["time_size"]), m["time_color"])

    def _draw_position(self, cx: float) -> None:
        """The green marker at the train, nose LEFT — the direction of travel."""
        t = _TUNEABLES_SIX_STATION
        mid = self._bar_top() + (float(t["bar_h"]) - 1) / 2.0
        fx, fy = cx - math.floor(cx), mid - math.floor(mid)
        img, ox, oy = self._marker_image(_TUNEABLES_SIX_STATION_MARKS, fx, fy)
        self.screen.blit(img, (int(math.floor(cx)) + ox, int(math.floor(mid)) + oy))

    def _draw_names(self, dest_di: int) -> None:
        """Vertical names in a FIXED box, and the code row under them.

        `draw_1col_text` distributes the characters into `box_h` and compresses
        anything that does not fit — so two, three and four characters all fill
        the same band, which is what both references measure (see the tuneables
        block). A space in a name is the data format's line-break marker; this
        view has one column per station, so it is dropped rather than drawn as
        two columns, and the compression absorbs the extra characters.

        The bar does not dim, so the name is the ONLY thing that carries state
        here: grey behind the train, grey at a station it runs through, grey past
        the service's terminus, black otherwise.
        """
        n = _TUNEABLES_SIX_STATION_NAMES
        font = self._name_font(int(n["font_size"]))
        code_font = self._code_font(int(n["code_size"]))
        curr = self._curr()
        cursor = self._cursor()
        bottom = float(n["box_top"]) + float(n["box_h"])

        for di in self._cells():
            stop = self.display_stops[di]
            name = stop.get("name") or ""
            parts = [p for p in name.split(" ") if p]
            if not parts:
                continue
            cx = self._slot_cx(di)
            passing = self._is_passing(stop)
            dim = di != curr and (di < cursor or di > dest_di or passing)
            color = n["color_dim"] if dim else n["color_ahead"]

            col_w = max(font.size(c)[0] for p in parts for c in p)
            if len(parts) == 1:
                draw_1col_text(
                    font,
                    parts[0],
                    int(round(cx - col_w / 2.0)),
                    int(round(bottom)),
                    int(round(self._name_span(font, len(parts[0])))),
                    color,
                    self.screen,
                )
            else:
                span = float(n["box_h"]) * float(n["compound_ratio"])
                step = col_w + int(n["col_gap"])
                left = cx - (len(parts) - 1) * step / 2.0
                for i, part in enumerate(parts):
                    # i = 0 is the RIGHTMOST column, and it is the raised one.
                    px = left + (len(parts) - 1 - i) * step
                    col_bottom = float(n["box_top"]) + span if i == 0 else bottom
                    draw_1col_text(
                        font,
                        part,
                        int(round(px - col_w / 2.0)),
                        int(round(col_bottom)),
                        int(round(span)),
                        color,
                        self.screen,
                    )

            # THE CODE IS DRAWN WHENEVER THE STATION HAS ONE, and it greys with
            # the name. It is NOT gated on whether the train stops:
            #
            #   * ochanomizu shows no code under 水道橋 / 飯田橋 / 市ケ谷 because
            #     those three carry `"sta_code": null` — the JC series numbers
            #     only 中央線快速 stations and they are 各駅停車-only.
            #   * takao's train is 通勤特快, which PASSES 日野 / 豊田 / 西八王子, and
            #     it draws all three codes greyed. They have JC20 / JC21 / JC23.
            #
            # So the two references never disagreed and the earlier reading of
            # them as a passing-station rule was wrong. It differs only on a
            # diagram that runs through a JC-numbered station — 中央特快 — where
            # gating on `pa` would blank a code the reference plainly shows.
            code = stop.get("sta_code") or ""
            if not code:
                continue
            # `color`, not a colour of its own: the code carries the same state
            # its name does (author, 2026-08-30), and the takao capture draws
            # the codes under its three passed stations greyed. The block above
            # already said so and the call did not — it passed a fixed black, so
            # every code stayed dark under a greyed name.
            self._blit_code(code_font, code, cx, float(n["code_cy"]), color)

    @staticmethod
    def _name_span(font, chars: int) -> float:
        """The vertical span `chars` characters are laid into, bottom-aligned.

        Three regimes, and `draw_1col_text` executes all three from this one
        number — it distributes into whatever span it is given and compresses
        only when the characters cannot fit:

          <= box_slots   the measured box. Two characters take its first and
                         last slot (pitch 60.5 = 2 x 30.2), three fill it.
          == max_slots   the natural pitch, so the stack grows one slot ABOVE
                         the box rather than squeezing into it.
          >  max_slots   the SAME span as max_slots, so a longer name compresses
                         into the four-character extent (author, 2026-08-29).

        The pitch is derived from the box rather than authored beside it, so the
        two cannot drift: a retune of `box_h` moves the 4-character extent with
        it, which is what keeps a 5-character name in proportion to a 3.
        """
        t = _TUNEABLES_SIX_STATION_NAMES
        box_h = float(t["box_h"])
        slots = max(1, int(t["box_slots"]))
        if chars <= slots:
            return box_h
        char_h = float(font.get_height())
        pitch = (box_h - char_h) / max(1, slots - 1)
        return char_h + (max(slots, int(t["max_slots"])) - 1) * pitch

    def _blit_code(self, font, code: str, cx: float, cy: float, color) -> None:
        """`JC24` -> `JC-19`-style: the letters, a hyphen, then the number.

        Drawn character by character because the declaration that keys the atlas
        admits any single character of a declared string — the composed string
        with its inserted hyphen is in no data file, so rendering it whole would
        need every station's composed form declared. Same reason the minute
        numbers and the clock compose from cells.
        """
        letters = "".join(c for c in code if c.isalpha())
        digits = "".join(c for c in code if c.isdigit())
        text = f"{letters}-{digits}" if digits else letters
        imgs = [font.render(ch, True, color) for ch in text]
        if not imgs:
            return
        total = sum(i.get_width() for i in imgs)
        # Positioned by the run's INK box: the code is a short run of caps and
        # digits whose font box carries ascender and descender room neither uses,
        # so centring the surface would sit it low.
        boxes = [i.get_bounding_rect() for i in imgs]
        top = min(b.y for b in boxes)
        bot = max(b.y + b.h for b in boxes)
        y = cy - (top + bot) / 2.0
        x = cx - total / 2.0
        for img in imgs:
            self.screen.blit(img, (int(round(x)), int(round(y))))
            x += img.get_width()

    def _transfer_font(self, size: int):
        """The band's line names — HEAVIER than the station names above the bar.

        DeBold rather than the model's Medium (author, 2026-08-29): at 11px the
        names sit under a dense bar and read thin against it. It is the Pro cut
        (Adobe-Japan1-4) where the rest of this model is Pr6N — already shipped
        and atlas-baked for the train type, and line names are common kanji, so
        the narrower glyph set is not a risk here. Heavy is the remaining step
        up if this still reads light.
        """
        f = self._name_fonts.get(-size)  # negative key: same cache, different face role
        if f is None:
            f = lcd_font(
                _TRANSFER_FACE,
                size,
                # `cuts=True` because the paren break is a rule, not a list. The
                # renderer splits at `（` and draws the tail WITH its paren, a
                # string no field holds — so an earlier declaration paired
                # `split="（"` (which yields the head, and a tail stripped of its
                # paren) with a `lit()` for the one tail Chūō has. `lines.json`
                # holds TWO full-width-paren names — the split is keyed on `（`,
                # so the five ASCII-paren names never reach it — and the second,
                # 京浜東北線（大井町・蒲田方面）, raised the moment Yamanote reached
                # it at 品川. Enumerating what the
                # author had seen is `critical_lessons.md` §9: a declaration
                # cooked from a hand-typed list cannot report the case it omits.
                # `cuts` takes both halves at every break position, so it does not
                # depend on where the rule cuts and cannot go a case short as the
                # data grows.
                draws=(
                    at(
                        "data/lines.json:*.name_ja",
                        "data/lines.json:*.variants.*.name_ja",
                        wrap="･",
                        cuts=True,
                    ),
                ),
            )
            self._name_fonts[-size] = f
        return f

    def _transfer_rows(self, di: int, font, badge_h: int, gap: int, inter: int, col_w: float):
        """The ROWS one station contributes: `[(icons, text), ...]`, top-down.

        ONE ROW IS ONE LINE (author, 2026-08-29). An entry is normally one row;
        a name too wide for its own column wraps at `･` into two, and the second
        row carries no badge — so a wrapped shinkansen occupies two rows rather
        than one tall one, and each of those rows is then free to compress or
        not on its own.

        The list and its ORDER are the parent pipeline's, so this view and the
        standalone transfer screen cannot disagree about what a station connects
        to: `apply_transfer_filter` drops the line the train is already on and
        applies the route's per-station view ops.
        """
        name = self.display_stops[di].get("name") or ""
        sd = self._tp_stations.get(name, {})
        refs = apply_transfer_filter(
            list(sd.get("transfers", [])),
            self._tp_line_code,
            self._tp_transfer_view,
            sd,
            self._tp_lines,
        )
        rows = []
        for ref in refs:
            e = resolve_entry(ref, self._tp_lines)
            ics = [load_icon(b["icon"], badge_h, self._tp_icon_cache) for b in (e.get("badges") or [{"icon": "_universal"}])]
            bw = sum(i.get_width() for i in ics) + inter * (len(ics) - 1) + gap
            text = e["name_ja"]
            # ONLY A `･`-SEPARATED NAME WRAPS. One row is one line, and an
            # over-wide name COMPRESSES rather than breaking (author) — so the
            # wrap is not a width fallback, it is the shinkansen's own
            # multi-line form, cut at the separator `docs/DATA_FORMAT.md`
            # names. Breaking on width alone split 上野東京ライン mid-word, which
            # the atlas declaration check caught before it could render: the
            # arbitrary substring comes from no declared source.
            #
            # Wrapped against the station's OWN column, not against whatever
            # room a neighbour happens to leave — the reference always cuts
            # 東北･山形･秋田 ｜ 北海道･上越･北陸新幹線, so the cut is a property of
            # the name and must not move when a neighbour's list runs short
            # further down.
            avail = col_w - bw
            # A PARENTHETICAL QUALIFIER TAKES ITS OWN ROW, unconditionally — it
            # is part of the name's written form rather than a width fallback
            # (author, 2026-08-29: 中央・総武線（各駅停車） puts （各駅停車） on line 2).
            # The break keeps the paren with line 2, where the `･` wrap keeps its
            # separator on line 1, so this cannot go through the same path.
            if "（" in text and not text.startswith("（"):
                head, _, tail = text.partition("（")
                rows.append((ics, head, bw))
                rows.append(([], "（" + tail, bw))
                continue
            squeeze = float(_TUNEABLES_SIX_STATION_TRANSFERS["min_squeeze"])
            if "･" in text and font.size(text)[0] * squeeze > avail:
                # SPLIT AT THE MIDDLE SEPARATOR, not at whatever fits. The
                # reference cuts 東北･山形･秋田･ ｜ 北海道･上越･北陸新幹線 — three
                # segments each — and a width-driven greedy cut lands a segment
                # early, which then leaves the second line carrying more than it
                # can compress into. The cut is a property of the NAME, so it
                # also cannot move when a neighbour's list runs short.
                segs = text.split("･")
                k = (len(segs) + 1) // 2
                rows.append((ics, "･".join(segs[:k]) + "･", bw))
                # THE CONTINUATION ROW INDENTS TO THE TEXT COLUMN, carrying its
                # parent's badge offset rather than starting at the badge's own x
                # (author, 2026-08-29: "shinkansen line 2, align that with the
                # text not the badge"). It draws no badge of its own, so without
                # the offset it would hang a glyph-width left of the line above.
                rows.append(([], "･".join(segs[k:]), bw))
                continue
            rows.append((ics, text, bw))
        return rows

    def _draw_transfers(self) -> None:
        """The connecting-line band under the bar, one column per station.

        A LINE COMPRESSES ONLY IF THE NEIGHBOUR HAS A LINE AT THAT SAME ROW, and
        that is decided ROW BY ROW rather than for the block as a whole (author,
        2026-08-29 — *"line compresses itself if it touches the neighbouring
        stations transfer lists (IF IT EXISTS, and it is a by row basis), if row
        10 does not have neibouring it means it can just span naturally"*).

        Which is why only ONE of a wrapped shinkansen's two lines comes out
        compressed: its rows sit at different depths, and the neighbouring
        station's list has usually run out by the lower one. A block-level rule
        cannot express that — it would squeeze both lines or neither.

        Compression is horizontal only, on the TEXT, never on the badge:
        The squeeze is one horizontal `smoothscale` of the row, the same idiom this model applies to
        a long station name and a three-digit countdown.
        """
        t = _TUNEABLES_SIX_STATION_TRANSFERS
        font = self._transfer_font(int(t["name_size"]))
        badge_h, gap, inter = int(t["badge"]), int(t["badge_gap"]), int(t["inter_badge"])
        pitch, color, pad = float(t["row_pitch"]), tuple(t["name_color"]), float(t["edge_pad"])
        cell = float(_TUNEABLES_SIX_STATION["slot_pitch"])

        # TWO POSITIONS. A block starts at a NOMINAL anchor inset into its cell,
        # and one too wide to fit before the next cell begins is pulled LEFT by
        # its overrun — bounded, so it stays legible as belonging to the station
        # above it. See the `nominal_inset` block.
        inset, max_shift = float(t["nominal_inset"]), float(t["max_shift"])
        gutter = float(t["list_gap"])
        cell_lefts = {di: self._slot_cx(di) - cell / 2.0 for di in self._cells()}
        rows = {di: self._transfer_rows(di, font, badge_h, gap, inter, cell) for di in cell_lefts}

        lefts = {}
        for di, cl in cell_lefts.items():
            widest = max((indent + font.size(txt)[0] for _, txt, indent in rows[di]), default=0.0)
            # Room from the nominal anchor to where the next cell starts. The
            # overrun past it is what the block gives back by shifting left.
            over = max(0.0, widest - (cell - inset))
            lefts[di] = cl + inset - min(over, max_shift)

        # Vertical: hang off the bar, and tighten toward it when the longest
        # block's tail reaches the bottom edge. One top for the whole band, so
        # the rows of adjacent stations stay on shared lines — which is what
        # makes the row-by-row compression rule meaningful in the first place.
        deepest = max((len(b) for b in rows.values()), default=0)
        top = self._bar_top() + float(_TUNEABLES_SIX_STATION["bar_h"]) + float(t["bar_gap"])
        if deepest:
            tail = top + (deepest - 1) * pitch + font.get_height()
            crowd = tail - (S_HEIGHT - BORDER_W - float(t["bottom_pad"]))
            top -= min(max(0.0, crowd), float(t["crowd_push"]))

        for di, block in rows.items():
            left = max(lefts[di], BORDER_W + pad)
            # The block to the RIGHT is the next slot toward slot 0, since the
            # cells read right to left. Nothing to the right of slot 0 but the
            # screen edge.
            right_di = di - 1
            y = top
            # A WRAPPED ENTRY'S TWO ROWS SHARE ONE RATIO (author, 2026-08-29 —
            # "if line 2 compresses, line 1 should follow"). Squeezing each row
            # on its own lets line 1 stay natural while line 2 tightens, and the
            # two then read as different sizes inside one entry. Computed here,
            # before anything is drawn, because a row cannot know what its
            # partner needs until both have been measured.
            ratios = []
            for r, (_, text, indent) in enumerate(block):
                neighbour = rows.get(right_di) or []
                # The gutter applies only where a neighbour actually is: at the
                # screen edge the row stops at `edge_pad` instead.
                bound = (lefts[right_di] - gutter) if r < len(neighbour) else S_WIDTH - BORDER_W - pad
                room = max(1.0, bound - (left + indent))
                w = font.size(text)[0]
                ratios.append(min(1.0, room / w) if w else 1.0)
            for a, b in _wrapped_pairs(block):
                ratios[a] = ratios[b] = min(ratios[a], ratios[b])

            for r, (ics, text, indent) in enumerate(block):
                img = font.render(text, True, color)
                # THE BADGE CENTRES ON THE TEXT'S INK, not on its font box. A
                # font box carries ascent and descent the glyphs never reach, and
                # the two are not equal — centring the badge on the box leaves it
                # sitting above the line the text actually draws on (author,
                # 2026-08-29: "your text is not on the same line as the badge").
                # The same trap the minute digits had.
                ink = img.get_bounding_rect()
                badge_top = y + ink.y + (ink.h - badge_h) / 2.0

                bx = left
                for j, ic in enumerate(ics):
                    self.screen.blit(ic, (int(round(bx)), int(round(badge_top))))
                    bx += ic.get_width() + (inter if j < len(ics) - 1 else 0)
                # One text column per block, whether or not this row drew a
                # badge — `indent` is the badge group's width plus its gap.
                x = left + indent
                # THE ROW'S OWN NEIGHBOUR decided the ratio above: a neighbour
                # whose list is shorter than this row's index imposes nothing,
                # and the line then runs at its natural width. Squeezed
                # horizontally on one surface, height untouched — the model's own
                # idiom, and what the reference does to a row that touches its
                # neighbour.
                if ratios[r] < 1.0:
                    img = pygame.transform.smoothscale(img, (max(1, int(round(img.get_width() * ratios[r]))), img.get_height()))
                self.screen.blit(img, (int(round(x)), int(round(y))))
                y += pitch

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Draw the whole view. Pure render — mutates no state."""
        self.state = state
        cursor = self._cursor()
        dest_di = self._dest_di()
        minutes = self._minutes(cursor, current_time)
        self._draw_bar()
        self._draw_skip_break()
        self._draw_unit()
        self._draw_marks(minutes, dest_di)
        self._draw_position(self._marker_slot(minutes))
        self._draw_names(dest_di)
        self._draw_transfers()

    def draw(self, current_time: float = 0.0) -> None:
        if self.state is not None:
            self.show_stops(self.state, current_time)

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        """Nearest cell, as a SIM stop index. A `pre_stop` cell is not a place
        the simulator can be put, so it returns None."""
        t = _TUNEABLES_SIX_STATION
        if abs(my - float(t["bar_cy"])) > float(t["bar_h"]) * 3:
            return None
        cells = self._cells()
        local = int(round((float(t["slot0_cx"]) - mx) / float(t["slot_pitch"])))
        if not 0 <= local < len(cells):
            return None
        di = cells[local]
        if di < self.display_offset or di >= len(self.display_stops):
            return None
        return di - self.display_offset


# =============================================================================
# Patterns-overview view (WIP § 14).
#
# Every service the 中央線 system runs, drawn as parallel coloured lines over one
# shared 32-station axis on the same two-row wrap the full-route view uses. The
# axis and the service set come from `audio/chuo/system.json`, attached by
# `route_loader` as `route_data["system"]`. Nothing about Chūō is stated here.
#
# Reading order is the opposite of the full-route view's: LEFT to RIGHT on both
# rows, and the screen's LOWER band comes FIRST (東京 … 高円寺), wrapping into the
# upper band (阿佐ヶ谷 … 高尾). Geometry off
# `overview-tokao-different-patterns-stopping-ja.png` by per-row ink counting
# (`_e233_lower_geometry.py --overview`), against the reference's 1502 x 1124:
#
#   name columns   fit centre(k) = 1381.52 - 80.156k, k from the RIGHT, both rows
#   line 0 centre  y/H 0.8265 (lower band) and 0.5343 (upper band)
#   line pitch     17.8px, mean of both rows, uniform within a pixel
#
# Twelve bands were counted mechanically rather than read off the picture: six
# services on each of two rows, in the legend's own order. Only 各駅停車 stops
# short — at 三鷹 above and 御茶ノ水 below — and the five rapid services each span
# the whole line. That last fact contradicts § 7's parked note that a service's
# line ends where the service terminates, which was tagged `[observed]`.
#
# Six elements are drawn, in this order: the service lines, their stop markers,
# the station names, the 立川 junction pill, the two spurs (立川's branch and
# 各駅停車's 千葉方面), and the legend the lines fold into. Order matters twice —
# the marks go under the pill, and so does 立川's axis name, because on the
# reference the pill's own white text IS that station's name.
# =============================================================================
# fmt: off
_TUNEABLES_OVERVIEW = {
    # The two rows are anchored SEPARATELY, indexed by DATA row: row 0 is
    # 東京 … 高円寺 and draws on the screen's LOWER band; row 1 is 阿佐ヶ谷 … 高尾
    # and draws on the upper one. Their right edges differ by 11.4 reference px
    # and their pitches by 0.85, which one shared grid cannot express — assuming
    # one put the lower row 10px out and lost every stop right of 新宿.
    #
    # Row 1 is the name-column fit over 17 clean columns. Row 0 is fitted to
    # 各駅停車's own markers, which ARE that row's slots since it stops
    # everywhere, and it then predicts 東京's measured name column to 0.06px.
    "row_r_cx":     (593.4, 588.7),   # rightmost slot centre, per data row
    "row_pitch":    ( 34.51,  34.15),
    "row_cy0":      (396.7,  256.5),  # that row's FIRST service line

    "line_pitch":       7.65,  # service to service, within a band
    # Thickness by COVERAGE INTEGRAL (`--thick`), not by a tolerance test: a
    # saturated ink sits further from the page than a muted one, so one threshold
    # admits more of its skirt and calls it thicker. Integrating settles it —
    # every ordinary line measures 2.1-2.3 across both rows and every colour.
    "line_h":           2,
    # The ACTIVE service is drawn heavier, and by DIFFERENT amounts per row:
    # 通勤特快 measures 3.31 on the upper band and 4.83 on the lower, steady
    # along the whole row at four sampled x. Indexed by DATA row, so [0] is the
    # screen's lower band.
    #
    # OPEN — why the two rows differ is not known. The reference is one capture
    # of one active service, so "the active line is heavier" and "the lower band
    # is heavier" cannot be told apart; a capture with a different service
    # highlighted separates them.
    "line_h_active":   (5, 3),
    "pad":              8.0,   # line overhang past a slot centre at a WRAP end
    "pad_terminus":    12.0,   # and at the axis's own last station (高尾), which
                               # the reference pads half again as far — the same
                               # wrap-versus-terminus split section 9.3.4 measured
                               # on the full-route bar

    "mark_w":           4,     # stop marker, white with a rim in the line colour.
    "mark_h":           4,     # The reference's white CORE measures 1.6-2.4
    "mark_rim":         1,     # canvas px across, so a 4px marker with a 1px rim
                               # leaves the 2 it wants; at 5 the core was 3

    "name_size":       16,     # fitted on ink WIDTH: the reference's characters
                               # measure 14.9 canvas px across
    "name_pitch":      14.4,   # and they are stacked TIGHTER than they are wide —
                               # 阿佐ケ谷's four characters span 57.5, so the cell
                               # is 14.38 against a 14.9 glyph. Deriving the pitch
                               # from `get_height()` gave 17.25 and pushed every
                               # name a fifth of its own height too low
    "name_lift":        9.1,   # from the row's first line up to the name's foot.
                               # Measured on the ink, not on the fit that set the
                               # pitch — that one checked width only, and the whole
                               # band sat 3.1px low on both rows
    "name_color":      (20,  20,  20),
    "name_dim":        (150, 155, 168),

    "pill_w":          17.9,   # 立川's junction pill: left edge 409.05 measured,
    "pill_top":       238.0,   # against the slot's own centre at 418.0
    "pill_h":          63.0,
    "pill_r":           8.0,
    "pill_color":     (116, 116, 116),  # sampled, not assumed — it is not 128
    "pill_ink":       (255, 255, 255),
    "pill_size":       14,     # the reference's 立 is 12.4 canvas px across and
                               # 13 tall, against 10 x 11 at size 12. Bigger than
                               # the axis names it replaces, which is the point
    "pill_line_gap":   -1,     # ink tops 14 apart on the reference; get_height()
                               # at 14 is 15, and the axis names are stacked
                               # tighter than their glyph for the same reason
    "pill_text_dy":    -2.5,   # ink block y 254..281, against a pill of 238..301.
                               # Re-fitted when the block height became exact:
                               # the old expression overstated it by `gap`, so
                               # half of that was living in this number

    # Legend, measured by `_e233_lower_geometry.py --legend`. The chip pitch is
    # 51.5 reference px and the chips are NOT on the service lines' own pitch —
    # they are half again as far apart, which is what gives the fold its slope.
    "leg_cy0":        322.0,   # first row centre, y/H 0.6708
    "leg_pitch":       22.0,
    "leg_h":           13.0,   # the row's own height. Its HALF is where the
                               # underline and the slant's head sit: measured
                               # y 329 on a row centred 322, and y 350 on one
                               # centred 344
    "leg_size":        11,     # fitted on ink HEIGHT, not width: the run's width
                               # is set by the four-cell pitch and barely moves
                               # with the size, so it cannot discriminate. The
                               # reference's label ink is 11.08 tall; size 13
                               # rendered 14.0
    "leg_text_dy":     -3.8,   # the label rides ABOVE the row's centre — ink
                               # centre 428.2 on a row centred 432

    # A row is FOUR separate marks, not one block. The active service does not
    # fill its whole row — traced by colour, `y` 317-329 carries the vertical
    # rectangle at x 3.8-8.1, `y` 314-327 the label box at x 11.1-80.5, and
    # `y` 329 an underline running the whole way from the rectangle out to the
    # slant's head. The gap at x 8.1-11.1 is what says the rectangle and the box
    # are two marks; filling one rect across both is what swallowed it.
    "leg_swatch_x":     3.8,   # the vertical rectangle, on EVERY row
    "leg_swatch_w":     4.3,
    "leg_swatch_h":    14.8,   # measured at native resolution on 青梅特快's, the
    "leg_swatch_dy":   -1.4,   # one row where nothing else shares its colour
    "leg_box_x":       11.1,   # the label box, on the active row only
    "leg_box_w":       69.5,
    "leg_box_h":       12.7,   # sized so its foot clears the underline by ONE
    "leg_box_dy":      -1.5,   # pixel — the reference's box ends y 327 and its
                               # underline starts 329, and that gap is visible
    "leg_rule_x":       3.6,   # the underline, on EVERY row, out to the slant
    "leg_rule_h":       1.3,   # thinner than the slant, which is thinner again
                               # than the line — three weights, all measured

    # The label is a FOUR-CELL run whatever the type's length, and a shorter type
    # spreads to the ends of it rather than setting tight from the left. 快速's
    # two characters measure at cells 1 and 4 of the same run 各駅停車 fills, so
    # this is the reference's own behaviour, not a borrowed convention.
    "leg_cell_cx0":    22.2,   # centre of cell 1; ink starts x 39 on the reference
    "leg_cell":        14.5,   # cell to cell, 34 reference px
    "leg_cells":        4,

    # Each chip reaches its own service line down a single straight DIAGONAL —
    # no right angle and no horizontal stub. Traced per row by colour
    # (`--crun`): 通勤特快 walks x 85.2 -> 92.9 over y 331 -> 393 at a constant
    # 0.11 px per row, and 青梅特快 x 82.2 -> 90.8 at 0.18. Two different slopes,
    # because what is constant is the horizontal RUN (10.7 and 11.1) while the
    # drop varies with how far that chip sits above its line. So the segment is
    # stated by its two ENDS and the slope falls out.
    #
    # It leaves the chip's BOTTOM edge, not its centre. On the active chip the
    # fill reaches the start and the two meet; on an inactive one the stroke
    # simply begins in clear space right of the label.
    # EVERY row's underline stops at one x and the slant takes over there —
    # green 82.66, navy 82.24, orange 83.09, 各駅停車 82.24, measured at native
    # resolution. An earlier reading made this a per-row staircase, which is the
    # FOOT's pattern, not the head's.
    "fold_head_x":     83.0,
    # The foot is where the thin slant becomes the thick line, so it is also
    # that line's left end. Taken from a LEAST-SQUARES fit over each stroke's own
    # run centres (`--slants`), not from its endpoints: an endpoint is where the
    # stroke meets the underline above or the line below, which is exactly where
    # the trace is contaminated. Reading the feet off the band extents instead
    # put 通勤快速 at 94.2 against a fitted 88.3, and that was the visible error.
    "fold_foot_x":     (95.3, 92.0, 90.4, 88.3, 88.3),
    "fold_w":           1.7,   # the slant is THINNER than the line it becomes,
                               # measured across it at native resolution

    # 各駅停車 leaves the axis rather than folding straight into its line: down
    # from the underline, a long horizontal stub, then up to where the line
    # starts at 御茶ノ水. The 方面 label sits under the stub.
    "spur_y":         441.3,   # the stub, x 87.8..160.6 on the reference
    "spur_x0":         87.8,
    "spur_x1":        160.6,
    "spur_top_x":     168.3,   # where it meets the line, y 434
    "spur_label_x":   103.1,   # the reference's ink edge. NOT the stub's centre,
                               # which sits 2.1px left of where the label starts
    "spur_label_dy":    5.6,   # ink lands y 446.1..457.6 on the reference
    "spur_label_size": 11,     # ink 11.50 tall on the reference, which is an 11
                               # plus the downscale's fringe — a 12 renders 12.9
    # Both 方面 labels are LETTER-SPACED, and by the same amount: 千葉方面 runs
    # 29.83 against a natural 28.00 over three gaps, and the 立川 label 167.88
    # against 159.00 over thirteen. 0.65 and 0.68 — one value serves both, which
    # is why it is here rather than per label.
    "label_track":      0.66,

    # The 立川 junction spur: every service that SERVES the junction leaves it
    # for the branch, which on this sheet is all five rapid services. 各駅停車
    # never reaches 立川, so the same test that draws the others withholds it —
    # no service list is stated here.
    #
    # The slants emerge at x 410, which is the pill's own left edge, so where
    # each one actually meets its line is hidden underneath the pill and cannot
    # be measured. What IS measured is the foot and the stub.
    "jspur_head_x":   410.0,
    "jspur_foot_x":   (437.6, 435.4, 433.4, 431.4, 429.5),
    "jspur_stub_y0":  308.0,   # the stubs CONVERGE — 3px per row against the
    "jspur_stub_step":  3.0,   # lines' own 7.65, which is what bunches them
    "jspur_right":    453.4,   # and they all end together, as the folds do
    "jspur_label_x":  456.4,   # the reference's ink edge, 3px clear of the stub's
                               # end at 453.4. An earlier window started left of
                               # that and adopted the stub tail as label ink,
                               # which read the run 11px wide and bought a size 12
    "jspur_label_cy": 315.1,
    "jspur_label_size": 11,    # same size as the other 方面 label. The run spans
                               # 156.80 on the reference (x 456.35..613.16) and
                               # 11 + the 0.66 tracking gives 156.2. The label uses
                               # the HALF-WIDTH ･, as the transfer panel does —
                               # the full-width form runs the whole 方面 line 10px
                               # past where the reference ends it
}
# fmt: on


# The sheet's own text, declared from the sheet rather than from `route.json`:
# its axis is the SYSTEM's, so it can carry a station no diagram on that line
# stops at, and its service types include the ones no diagram runs at all. Both
# are exactly the strings `STATION_NAMES` cannot reach.
#
# `STATION_NAMES` itself is deliberately NOT here. Every string this view draws
# comes from the sheet, so including it widened the declared domain from 32 to
# 268 — and `check_declared`, which is the half that keeps a declaration honest,
# validates against that domain. A corpus-wide alias would have let an
# accidental draw of any station name pass unremarked.
_OVERVIEW_DRAWS = (
    at("audio/*/system.json:rows[][]"),
    at("audio/*/system.json:services[].type"),
    at("audio/*/system.json:services[].spur"),
    at("audio/*/system.json:junctions[].spur"),
    at("audio/*/system.json:junctions[].station"),
)


class JapanesePatternsOverviewDisplay:
    """The service-pattern sheet: lines, marks, names, pill, spurs and legend.

    The axis, the service list, their colours and their spans all arrive in
    `route_data["system"]`, so this class holds no station name and no service
    name. A line with no sheet draws nothing rather than falling back to
    something Chūō-shaped.

    What it does NOT yet take from the sheet is the GEOMETRY. The row split, the
    slot pitch, the per-service stack spacing and the legend's placement are
    fitted against the one Chūō reference and live in `_TUNEABLES_OVERVIEW` as
    per-row and per-service tuples, so their LENGTHS carry Chūō's 2 rows and 6
    services even though no name does. `WIP_e233_0_display.md` section 14.2
    records that those four have to derive from the axis they are handed before
    a second system can draw here; the author deferred that until more overview
    references are collected, so `_assert_shape` refuses a sheet this drawing
    cannot express rather than the drawing pretending to be general.
    """

    def __init__(self, screen, route_data, stops):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops
        self._state = None
        self._bind_sheet(route_data.get("system"), stops)
        self._name_fonts: Dict[int, pygame.font.Font] = {}

    def _bind_sheet(self, sheet, stops) -> None:
        """Everything the content decisions read, derived from the sheet once.

        Its own method so a headless test can bind it onto a stub rather than
        restate it — a fixture that rebuilds `_route_idx` by hand keeps agreeing
        with the old shape after this derivation changes (`principles.md` § "A
        second implementation of a production decision drifts silently").
        """
        self._sheet = sheet
        # Flatten once: a service's span is stated as two station names on the
        # whole axis, and each row draws the part of that span it holds.
        self._rows = [list(r) for r in sheet["rows"]] if sheet else []
        self._axis = [n for r in self._rows for n in r]
        # Axis station -> this run's stop index, which is what makes the greying
        # live. Most of the axis is absent from any one run, and that absence is
        # itself the answer (see `_dim`).
        #
        # FIRST occurrence wins, matching `route_loader._resolve_frames`. A
        # circular route names its origin twice (Yamanote's stops[0] and
        # stops[29] are both 大崎), and last-wins would pin that station to the
        # terminus so `di < curr` never fires and it stays black for the whole
        # loop. No line with a duplicate stop name has a sheet today; the two
        # maps agreeing is what stops that being a surprise later.
        self._route_idx: Dict[str, int] = {}
        for i, s in enumerate(stops):
            self._route_idx.setdefault(s["name"], i)
        if sheet:
            self._assert_shape(sheet)

    @staticmethod
    def _assert_shape(sheet) -> None:
        """Refuse a sheet whose shape the fitted geometry cannot express.

        The row and service tuneables are TUPLES indexed by row and by service,
        so a sheet with more rows raises `IndexError` deep inside a draw, and one
        with more services silently draws a line from the legend's x and runs its
        chip off the canvas. Two failure modes for one cause is worse than
        either; state the requirement once, here, and name the sheet in it.
        `critical_lessons.md` section 2 — fail loudly, never degrade quietly.

        The service bound is asked PER SERVICE, not as one count. `fold_foot_x`
        and `jspur_foot_x` hold five entries against Chūō's six services, and
        that is not an off-by-one: 各駅停車 starts mid-axis so it needs no fold
        foot, and never reaches 立川 so it needs no spur foot. A flat
        `len(...) + 1` would admit any sixth service and then let two fallbacks
        mis-draw it — `_fold_ends` would hand back the LEGEND's x as a foot, and
        `_draw_junction_spurs` would reuse the fifth service's slant. Asking
        which feet a service actually needs is derived from the sheet and cannot
        be true only because Chūō's last service happens to need neither.
        """
        t = _TUNEABLES_OVERVIEW
        rows, services = sheet.get("rows", []), sheet.get("services", [])
        max_rows = min(len(t["row_r_cx"]), len(t["row_pitch"]), len(t["row_cy0"]), len(t["line_h_active"]))
        problems = []
        if len(rows) > max_rows:
            problems.append(f"{len(rows)} rows against {max_rows} fitted")
        axis = [n for r in rows for n in r]
        # Only a junction that DECLARES a spur draws one; `_draw_junction_spurs`
        # skips the rest, so counting those would refuse a sheet for a foot it
        # never uses.
        junctions = {j.get("station") for j in sheet.get("junctions", ()) if j.get("spur")}
        for i, svc in enumerate(services):
            label = svc.get("type", f"#{i}")
            # A service whose span starts at the axis origin folds out of the
            # legend, so it needs its own foot x.
            if svc.get("from") == (axis[0] if axis else None) and i >= len(t["fold_foot_x"]):
                problems.append(f"{label} folds from the legend but is service {i}, past {len(t['fold_foot_x'])} fitted feet")
            if junctions & set(svc.get("stops") or ()) and i >= len(t["jspur_foot_x"]):
                problems.append(f"{label} serves a junction but is service {i}, past {len(t['jspur_foot_x'])} fitted spur feet")
        # The legend is stacked, not fitted per service, so it bounds the count
        # on its own — and it is the bound that catches a service needing neither
        # foot, which the two tests above are both silent about.
        if services:
            last_chip = t["leg_cy0"] + (len(services) - 1) * t["leg_pitch"] + t["leg_h"] / 2
            if last_chip > S_HEIGHT:
                problems.append(f"{len(services)} services put the last legend chip at y {last_chip:.0f}, past the {S_HEIGHT}px canvas")
        if problems:
            raise ValueError(
                f"system.json for {sheet.get('system', '?')} does not fit this drawing: "
                + "; ".join(problems)
                + ". Deriving the geometry from the axis is WIP_e233_0_display.md section 14.2, still open."
            )

    def set_state(self, state) -> None:
        self._state = state

    def _name_font(self, size: int):
        """One cache for every text on this page.

        The declaration spans station names AND service-type labels, because the
        legend draws types out of the sheet while the axis and the pill draw
        station names. `lcd_font` validates each draw against it in dev, so an
        undeclared type fails on the first frame rather than in a build that
        ships no font software.
        """
        f = self._name_fonts.get(size)
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=_OVERVIEW_DRAWS)
            self._name_fonts[size] = f
        return f

    def _span(self, service) -> Tuple[int, int]:
        """A service's span as inclusive indices into the flattened axis.

        Fails loud on a station the axis does not carry: a `.index` miss here
        means the sheet and its own axis disagree, which is a data defect rather
        than something to draw around.
        """
        return self._axis.index(service["from"]), self._axis.index(service["to"])

    def _slot_cx(self, r: int, j: int) -> float:
        """Centre x of slot `j` (0 = leftmost) on data row `r`."""
        t = _TUNEABLES_OVERVIEW
        n = len(self._rows[r])
        return t["row_r_cx"][r] - (n - 1 - j) * t["row_pitch"][r]

    def _dim(self, name: str) -> bool:
        """Is this axis station BEHIND the train, or one it runs through?

        The run-through half is `is_passing_stop`, the same predicate the
        full-route view uses, rather than a second wording of it. Grey for a
        station already passed AND for one the train passes through, black for
        this station and every stopping station ahead. The current station is
        tested first and wins outright, because a route ORIGIN carries `pa: []`
        and would otherwise be greyed while the train stands at it.

        The axis is the SYSTEM's, so most of it is not on the loaded route at
        all — every 各駅停車-only station on a 快速 run, and the whole 高尾 half
        on an 青梅 diagram. Those are stations this train never reaches, which is
        the same thing the grey says, so an absent station greys.

        NOT carried: the full-route view's third term, `di > dest_stop_idx`, which
        greys everything past a run that terminates before its stop list ends. No
        sheet-carrying line does that today (only keihin/727B and saikyo/759K
        terminate early, and neither has a sheet), and the whole greying rule is
        an OPEN item against the reference — WIP § 14.4 records that the capture
        greys upper-row stations its own train stops at, which no rule here
        reproduces. Settle that before adding a term to match a sibling view.
        """
        state = self._state
        if state is None:
            return False
        di = self._route_idx.get(name)
        if di is None:
            return True
        curr = state.curr_stop
        if di == curr:
            return False
        return di < curr or is_passing_stop(self.stops[di])

    def show_stops(self, state, current_time: float = 0.0) -> None:
        self._state = state
        self.draw()

    def draw(self, current_time: float = 0.0) -> None:
        if not self._sheet:
            return
        self._draw_lines()
        self._draw_folds()
        self._draw_junction_spurs()
        # The pill is the topmost thing at 立川 and it covers both the marks and
        # the axis name. 立川 is a stop on all five rapid services and the
        # reference shows none of those five markers; nor does it carry a grey
        # 立川 above the pill, because the pill's own white text IS the name.
        self._draw_marks()
        self._draw_names()
        self._draw_junctions()
        self._draw_legend()

    # -- elements --------------------------------------------------------------

    def _bands(self):
        """`(r, row, i, service, base, lo, hi, cy, color)` per drawn band.

        Where service `i`'s band sits on row `r`, in one place. The lines pass
        and the marks pass are deliberately separate — a later service's thicker
        active band would otherwise paint over an earlier service's markers — but
        they answer the same geometric question, and a marker that stopped
        tracking its own line is a visible defect. Yields nothing for a service
        that does not reach the row.
        """
        t = _TUNEABLES_OVERVIEW
        base = 0
        for r, row in enumerate(self._rows):
            for i, service in enumerate(self._sheet["services"]):
                a, b = self._span(service)
                lo, hi = max(a, base), min(b, base + len(row) - 1)
                if lo <= hi:
                    cy = t["row_cy0"][r] + i * t["line_pitch"]
                    yield r, row, i, service, base, lo, hi, cy, tuple(service["color"])
            base += len(row)

    def _draw_lines(self) -> None:
        """One coloured line per service per row. Markers are their own pass."""
        t = _TUNEABLES_OVERVIEW
        active = self.route_data.get("type")
        for r, row, i, service, base, lo, hi, cy, color in self._bands():
            h = t["line_h_active"][r] if service["type"] == active else t["line_h"]
            # At the axis ORIGIN the line begins where its slant's FOOT is —
            # the point the stroke stops being thin. Reading it from
            # `_fold_ends` means the thickness change and the join are one
            # value, so retuning the slant cannot leave a step at the seam.
            # A service leaving the axis meets its line at the spur's top
            # instead, which is the same idea one bend further along.
            if lo == 0:
                x0 = self._fold_ends(i)[1][0]
            elif service.get("spur") and r == 0:
                x0 = t["spur_top_x"]
            else:
                x0 = self._slot_cx(r, lo - base) - t["pad"]
            end = t["pad_terminus"] if hi == len(self._axis) - 1 else t["pad"]
            x1 = self._slot_cx(r, hi - base) + end
            pygame.draw.rect(
                self.screen,
                color,
                pygame.Rect(round(x0), round(cy - h / 2), round(x1) - round(x0), h),
            )

    def _draw_marks(self) -> None:
        """Stop markers, as their own pass AFTER every line and BEFORE the pill.

        Separate from `_draw_lines` because the services stack at 7.65px while the
        loaded train's own line is 5px tall, so drawing each line with its markers
        lets the next service's band paint over the previous one's marks.

        Under the pill, not over it. An earlier docstring here claimed the
        reference showed four markers on top of the 立川 pill; measured inside the
        pill on the reference (x 960..1002, y 557..705 at 1502x1124) there is no
        service colour and no marker at all, only pill grey and the white 立川.
        What the slot-by-slot probe read as four marker cores was that kanji —
        its strokes cross four of the six line rows, and 快速's row happens to
        fall in the gap between 立 and 川, which is why exactly one came back
        missing. Do not reorder these calls on the strength of that reading.
        """
        t = _TUNEABLES_OVERVIEW
        for r, row, _i, service, base, lo, hi, cy, color in self._bands():
            stops = set(service["stops"])
            for j in range(lo - base, hi - base + 1):
                if row[j] not in stops:
                    continue
                outer = pygame.Rect(0, 0, t["mark_w"], t["mark_h"])
                outer.center = (round(self._slot_cx(r, j)), round(cy))
                pygame.draw.rect(self.screen, color, outer)
                pygame.draw.rect(self.screen, (255, 255, 255), outer.inflate(-2 * t["mark_rim"], -2 * t["mark_rim"]))

    def _draw_names(self) -> None:
        """Vertical station names, bottom-aligned onto each row's first line.

        Never compressed and never wrapped: this axis's longest name is five
        characters and the pitch carries it, which is the full-route view's rule
        on the same data.
        """
        t = _TUNEABLES_OVERVIEW
        font = self._name_font(int(t["name_size"]))
        # `draw_1col_text_plain` steps by `get_height() + line_gap`, so a cell
        # tighter than the glyph is a NEGATIVE gap. Derived from the authored
        # pitch rather than the other way round, so the pitch stays the number
        # that was measured and does not move when the size is retuned.
        gap = int(round(t["name_pitch"] - font.get_height()))
        pitch = font.get_height() + gap
        # A junction carries no axis name. Its pill's own white text IS the name,
        # and the reference leaves the slot above the pill empty — drawing both
        # puts a second 立川 in the band, since the pill starts below the name.
        pilled = {j["station"] for j in self._sheet.get("junctions", ())}
        for r, row in enumerate(self._rows):
            bottom = t["row_cy0"][r] - t["line_h"] / 2 - t["name_lift"]
            for j, name in enumerate(row):
                if name in pilled:
                    continue
                text = name.replace(" ", "")  # a space is the data's line break;
                # this element has one column, so it is dropped rather than drawn
                color = t["name_dim"] if self._dim(name) else t["name_color"]
                cx = self._slot_cx(r, j)
                # Centre on the COLUMN, which `draw_1col_text_plain` sizes to the
                # widest glyph and treats `x` as the left edge of. Measuring the
                # first glyph instead is right only while it happens to be the
                # widest, which every full-width name on this axis is.
                col_w = column_width(font, text)
                draw_1col_text_plain(
                    font,
                    text,
                    int(round(cx - col_w / 2.0)),
                    int(round(bottom - ((len(text) - 1) * pitch + font.get_height()))),
                    color,
                    self.screen,
                    line_gap=gap,
                )

    def _draw_junction_spurs(self) -> None:
        """The branch leaving a junction: a slant per service, then one stub each.

        Drawn BEFORE the pill, because the pill covers where each slant meets its
        line — which is also why that meeting point cannot be measured and the
        slants are stated from the pill's own left edge outward.
        """
        t = _TUNEABLES_OVERVIEW
        w = float(t["fold_w"])
        for junction in self._sheet.get("junctions", ()):
            name = junction["station"]
            if not junction.get("spur"):
                continue
            for r, row in enumerate(self._rows):
                if name not in row:
                    continue
                for i, service in enumerate(self._sheet["services"]):
                    # Serving the junction IS the test — no service list.
                    if name not in service["stops"]:
                        continue
                    color = tuple(service["color"])
                    feet = t["jspur_foot_x"]
                    foot = feet[i] if i < len(feet) else feet[-1]
                    stub_y = t["jspur_stub_y0"] + i * t["jspur_stub_step"]
                    self._stroke(color, t["jspur_head_x"], t["row_cy0"][r] + i * t["line_pitch"], foot, stub_y, w)
                    pygame.draw.rect(
                        self.screen,
                        color,
                        pygame.Rect(
                            round(foot - w / 2),
                            round(stub_y - w / 2),
                            round(t["jspur_right"]) - round(foot - w / 2),
                            max(1, round(w)),
                        ),
                    )
                self._draw_tracked(
                    self._name_font(int(t["jspur_label_size"])),
                    junction["spur"],
                    t["jspur_label_x"],
                    t["jspur_label_cy"],
                    t["name_color"],
                )

    def _draw_junctions(self) -> None:
        """The grey pill over a branch node, with its name reversed out of it.

        Drawn AFTER the lines and names so it covers them, which is what the
        reference does — the pill is the topmost thing at 立川.
        """
        t = _TUNEABLES_OVERVIEW
        font = self._name_font(int(t["pill_size"]))
        for junction in self._sheet.get("junctions", ()):
            name = junction["station"]
            for r, row in enumerate(self._rows):
                if name not in row:
                    continue
                cx = self._slot_cx(r, row.index(name))
                rect = pygame.Rect(0, 0, round(t["pill_w"]), round(t["pill_h"]))
                rect.centerx = round(cx)
                rect.top = round(t["pill_top"])
                pygame.draw.rect(self.screen, t["pill_color"], rect, border_radius=round(t["pill_r"]))
                gap = int(t["pill_line_gap"])
                pitch = font.get_height() + gap
                # The EXACT stack height, the same expression `_draw_names` uses.
                # `len(name) * pitch` overstates it by `gap`, so half the gap was
                # absorbed into `pill_text_dy` and retuning `pill_line_gap` moved
                # the text by the intended amount plus half the gap change.
                block_h = (len(name) - 1) * pitch + font.get_height()
                draw_1col_text_plain(
                    font,
                    name,
                    int(round(cx - column_width(font, name) / 2.0)),
                    int(round(rect.centery - block_h / 2.0 + t["pill_text_dy"])),
                    t["pill_ink"],
                    self.screen,
                    line_gap=gap,
                )

    def _draw_legend(self) -> None:
        """One chip per service, and the loaded train's own type highlights.

        The highlight is LIVE, not authored: it matches `route.json`'s `type`
        against the sheet's service list, so loading a different diagram moves
        it. A type the sheet does not carry highlights nothing rather than
        falling back to the first row, which would claim the train is running a
        service it is not.
        """
        t = _TUNEABLES_OVERVIEW
        font = self._name_font(int(t["leg_size"]))
        active = self.route_data.get("type")
        for i, service in enumerate(self._sheet["services"]):
            color = tuple(service["color"])
            cy = t["leg_cy0"] + i * t["leg_pitch"]

            # The vertical rectangle is on every row, active or not.
            pygame.draw.rect(
                self.screen,
                color,
                pygame.Rect(
                    round(t["leg_swatch_x"]),
                    round(cy + t["leg_swatch_dy"] - t["leg_swatch_h"] / 2),
                    round(t["leg_swatch_w"]),
                    round(t["leg_swatch_h"]),
                ),
            )

            # The underline is on every row too, running from the rectangle out
            # to the slant's head — so it ends where the slant begins by
            # construction rather than by two numbers agreeing. 各駅停車 has no
            # slant, so its underline stops at the head its row WOULD have.
            head_x, head_y = self._fold_ends(i)[0]
            pygame.draw.rect(
                self.screen,
                color,
                pygame.Rect(
                    round(t["leg_rule_x"]),
                    round(head_y - t["leg_rule_h"] / 2),
                    round(head_x) - round(t["leg_rule_x"]),
                    round(t["leg_rule_h"]),
                ),
            )

            # Only the box and the reversed ink mark the active service. It does
            # NOT fill the row: the rectangle and the underline are the same on
            # every row, and the gap at x 8.1-11.1 is what keeps them separate
            # marks rather than one block (author, and the colour trace agrees).
            ink = t["name_color"]
            if service["type"] == active:
                ink = (255, 255, 255)
                pygame.draw.rect(
                    self.screen,
                    color,
                    pygame.Rect(
                        round(t["leg_box_x"]),
                        round(cy + t["leg_box_dy"] - t["leg_box_h"] / 2),
                        round(t["leg_box_w"]),
                        round(t["leg_box_h"]),
                    ),
                )
            self._draw_type_cells(font, service["type"], cy, ink)

    def _draw_type_cells(self, font, text: str, cy: float, ink) -> None:
        """A service type on the legend's fixed four-cell run.

        Four characters fill the run one per cell. A shorter type SPREADS to the
        run's ends rather than setting tight from the left, so 快速 lands in
        cells 1 and 4 — which is what the reference measures, its two characters
        sitting exactly where 各駅停車's first and last do.
        """
        t = _TUNEABLES_OVERVIEW
        n = len(text)
        last = int(t["leg_cells"]) - 1
        for i, ch in enumerate(text):
            # One character centres on the run; more spread evenly across it, so
            # the first and last always land on the outer cells.
            slot = last / 2.0 if n == 1 else i * last / (n - 1)
            cx = t["leg_cell_cx0"] + slot * t["leg_cell"]
            g = font.render(ch, True, ink)
            self.screen.blit(
                g,
                (round(cx - g.get_width() / 2), round(cy + t["leg_text_dy"] - g.get_height() / 2)),
            )

    def _draw_folds(self) -> None:
        """Each chip's line running out to meet its service on the lower row.

        Only a service that starts at the axis ORIGIN gets one, which is what
        makes this data-driven rather than a count: 各駅停車 begins mid-row at
        御茶ノ水 and reaches its chip through the 千葉方面 spur instead, so the
        same test that places the fold also withholds it.

        The turns NEST — the chip with the longest drop turns furthest right —
        so no vertical crosses another row's horizontal.
        """
        t = _TUNEABLES_OVERVIEW
        w = float(t["fold_w"])
        for i, service in enumerate(self._sheet["services"]):
            color = tuple(service["color"])
            (x0, y0), (x1, y1) = self._fold_ends(i)
            if self._span(service)[0] == 0:
                self._stroke(color, x0, y0, x1, y1, w)
                continue
            # A service that leaves the axis reaches its line the long way: down
            # from the underline, along a stub carrying the 方面 label, then back
            # up to where its line starts. Keyed on the span rather than on the
            # service's name, so the sheet decides which row does this.
            if not service.get("spur"):
                continue
            self._stroke(color, x0, y0, t["spur_x0"], t["spur_y"], w)
            self._stroke(color, t["spur_x1"], t["spur_y"], t["spur_top_x"], y1, w)
            # The stub is horizontal, where a constant-horizontal-width quad
            # degenerates to a zero-area sliver — so it is a rect.
            pygame.draw.rect(
                self.screen,
                color,
                pygame.Rect(
                    round(t["spur_x0"] - w / 2),
                    round(t["spur_y"] - w / 2),
                    round(t["spur_x1"] + w / 2) - round(t["spur_x0"] - w / 2),
                    max(1, round(w)),
                ),
            )
            font = self._name_font(int(t["spur_label_size"]))
            self._draw_tracked(
                font,
                service["spur"],
                t["spur_label_x"],
                t["spur_y"] + t["spur_label_dy"] + font.get_height() / 2,
                t["name_color"],
            )

    def _fold_ends(self, i: int):
        """`((head_x, head_y), (foot_x, foot_y))` of row `i`'s slant.

        The head is also where every row's underline stops, so the two read it
        from here rather than each computing it — a second expression is how the
        underline would drift out from under the slant the first time it moves.
        """
        t = _TUNEABLES_OVERVIEW
        feet = t["fold_foot_x"]
        foot = feet[i] if i < len(feet) else t["fold_head_x"]
        return (
            (t["fold_head_x"], t["leg_cy0"] + i * t["leg_pitch"] + t["leg_h"] / 2),
            (foot, t["row_cy0"][0] + i * t["line_pitch"]),
        )

    def _draw_tracked(self, font, text: str, x: float, cy: float, ink) -> float:
        """A letter-spaced run, drawn left to right. Returns its right edge.

        Per character rather than one `render`, because pygame has no tracking
        and the reference's 方面 labels carry two thirds of a pixel between every
        glyph — which over the 立川 label's thirteen gaps is 9px, enough to end
        the line in the wrong place.
        """
        track = _TUNEABLES_OVERVIEW["label_track"]
        cx = x
        for ch in text:
            g = font.render(ch, True, ink)
            self.screen.blit(g, (round(cx), round(cy - g.get_height() / 2)))
            cx += font.size(ch)[0] + track
        # The right edge. No caller consumes it — it is what a measurement pass
        # reads back, and the 立川 label's 156.80px run was fitted against it.
        return cx - track

    def _stroke(self, color, x0, y0, x1, y1, w) -> None:
        """A straight stroke of constant HORIZONTAL width between two points.

        Horizontal rather than perpendicular, so a slant's foot is a flat edge
        on the line it becomes and the join needs no mitre.
        """
        draw_aapolygon(self.screen, color, [(x0 - w / 2, y0), (x0 + w / 2, y0), (x1 + w / 2, y1), (x1 - w / 2, y1)])


class LowerDisplay(LowerDisplayBase):
    """E233-0 lower LCD manager — rotates five slots, all of them built.

    Full route (§ 9) and 6-station (§ 10) live in this module; the standalone
    transfer view (§ 11) and the two standing notices (§ 12) are constructed from
    their own modules in this package. The notices join the rotation at most one
    at a time and only every third lap, so a page turns up about every 108s —
    see `_available_slots`.
    """

    # Stations-from-terminus below which the view locks to the zoomed slot.
    # `slots - 1`, which is E235-1000's own relation (VISIBLE_COUNT 8 ->
    # threshold 7): the zoomed window locks at exactly the point it can no
    # longer slide, so FULL leaves the rotation on the same frame the marker
    # starts walking inside a fixed window rather than a frame either side of it.
    LOCK_THRESHOLD = int(_TUNEABLES_SIX_STATION["slots"]) - 1

    def __init__(self, screen, route_data, stops, mode_cycler):
        super().__init__(screen, route_data, stops, mode_cycler)

        full = JapaneseFullRouteDisplay(screen, route_data, stops)
        six = JapaneseSixStationDisplay(screen, route_data, stops)
        transfer = TransferInfoDisplay(screen, route_data, stops)

        # Both Japanese modes and English resolve to the same instance while
        # v1 is kanji-only (WIP § 4) — one instance, not three, so a mode flip
        # cannot re-trigger per-instance animation state.
        self.japanese_display = full
        self.english_display = full
        # The 6-station view owns the EIGHT slot, as E235-0's 5-station one does
        # on that model — the slot is "the zoomed view", not a station count.
        self.japanese_eight_display = six
        self.transfer_display = transfer
        self.priority_seat_display = PrioritySeatDisplay(screen, route_data, stops)
        self.manner_mode_display = MannerModeDisplay(screen, route_data, stops)
        self.overview_display = JapanesePatternsOverviewDisplay(screen, route_data, stops)
        self._lap = 0
        self._notice_showing = False

    def set_state(self, state) -> None:
        super().set_state(state)
        self.japanese_display.set_state(state)
        self.japanese_eight_display.set_state(state)
        self.priority_seat_display.set_state(state)
        self.manner_mode_display.set_state(state)
        self.overview_display.set_state(state)
        # `transfer_display` is bound by the base — not repeated here.

    # -- the two standing notices -----------------------------------------
    #
    # 優先席 and マナーモード ride the SAME beat as the other views (author,
    # 2026-08-29: *"they are in the beat"*) at 3 beats = ~12s, the dwell FULL
    # and EIGHT already use and the one the author has confirmed. What makes
    # them rarer is not a longer dwell but a lower FREQUENCY: at most one of
    # them joins the rotation, and only every `_NOTICE_EVERY` laps — *"they
    # only show once in 2/3 loops, so those pages should be less often"*.
    #
    # They are LANGUAGE-INVARIANT (author), so unlike FULL / EIGHT there is no
    # reason for their dwell to span the 3-language cycle; it matches only
    # because a uniform beat is what the schedule is made of.
    _SLOT_PRIORITY = 3
    _SLOT_MANNER = 4
    # WIP § 14. Deliberately absent from `_available_slots`, so it is reachable
    # from the preview and the editor and never rotates into a drive — the sheet
    # is Chūō-only and the page's cadence is not settled, and the same call was
    # made for the transfer slot's `_PendingView`. It IS in the atlas bake,
    # which sweeps every `_SLOT_*` defined rather than every one with a beat.
    _SLOT_OVERVIEW = 5
    _NOTICE_EVERY = 3  # laps between notices — one notice per three rotations
    _SLOT_BEATS = {
        **LowerDisplayBase._SLOT_BEATS,
        _SLOT_PRIORITY: 3,
        _SLOT_MANNER: 3,
    }
    _NOTICES = (_SLOT_PRIORITY, _SLOT_MANNER)

    def _available_slots(self, state) -> list:
        """The base rotation, plus at most ONE notice page when a lap is due.

        Keyed on a lap counter rather than on wall-clock, so the answer is
        stable for the whole of a rotation — this is called every frame, and a
        list that changed mid-lap would make the cadence jump slots.

        Appended at the END so a notice never displaces the view a stop's
        arrival wants: the `at_station` force-switch still lands on TRANSFER,
        and the notice is simply the last page before the lap restarts.
        """
        slots = super()._available_slots(state)
        if len(slots) > 1 and self._lap % self._NOTICE_EVERY == 0:
            slots = slots + [self._NOTICES[(self._lap // self._NOTICE_EVERY) % len(self._NOTICES)]]
        return slots

    def apply_slot(self, slot: int, now: float) -> None:
        """Commit, and count a lap when the rotation returns to its first slot.

        Counted here rather than in `scheduled_slot` because this is the single
        commit funnel — a forced switch and a scheduled rotation both arrive
        here, so neither can advance the lap behind the other's back.
        """
        prev = self._current_slot
        super().apply_slot(slot, now)
        if slot != prev and slot in self._NOTICES:
            # A notice is the LAST page of its lap, so the lap closes when the
            # notice is left, not when it is entered. Advancing on ENTER would
            # rebuild `_available_slots` without it while it is still on screen,
            # and the base would reconcile it away as layout-invalid.
            self._notice_showing = True
        elif slot != prev and self._notice_showing:
            self._notice_showing = False
            self._lap += 1
        elif slot != prev and slot == self._SLOT_FULL:
            self._lap += 1

    def _pick_renderer(self, mode):
        """Slot decides the view; mode does not, while v1 is kanji-only (WIP § 4).

        The TRANSFER slot rotates like the other two AND is force-switched to on
        the rising edge of `at_station` by `LowerDisplayBase` — the author's
        *"approach, and full switch at the stop"* (WIP § 11.1). Both halves are
        the base's existing machinery; nothing here schedules it.
        """
        if self._current_slot == self._SLOT_OVERVIEW:
            return self.overview_display
        if self._current_slot == self._SLOT_PRIORITY:
            return self.priority_seat_display
        if self._current_slot == self._SLOT_MANNER:
            return self.manner_mode_display
        if self._current_slot == self._SLOT_TRANSFER:
            return self.transfer_display
        if self._current_slot == self._SLOT_EIGHT:
            return self.japanese_eight_display
        return self.japanese_display

    def draw(self, current_time: float) -> None:
        """Lower background, the screen border this half owns, then the view."""
        area = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)
        pygame.draw.rect(self.screen, LOWER_BG, area)

        renderer = self._pick_renderer(self.mode_cycler.current_mode)
        if renderer is not None and hasattr(renderer, "show_stops") and self._state is not None:
            renderer.show_stops(self._state, current_time)

        # Border: this half owns left, right and bottom (the upper band draws
        # top, left and right of its own region). Drawn last so no element can
        # paint over the screen edge.
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(0, UPPER_HEIGHT, BORDER_W, area.height))
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(S_WIDTH - BORDER_W, UPPER_HEIGHT, BORDER_W, area.height))
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(0, S_HEIGHT - BORDER_W, S_WIDTH, BORDER_W))

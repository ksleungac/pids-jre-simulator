# SPDX-License-Identifier: MIT
"""E233-0 priority-seat (優先席) page — the lower LCD's static notice.

AN ORIGINAL RENDITION, DRAWN FROM MEASUREMENT. Nothing here is imported: the
placard is built from primitives whose every number was measured off
`_references/lcd/e233_0/priority-seats.png` (1273x953, 1.989x the 640x480
canvas) with `_dev_scripts/_e233_lower_geometry.py --placard / --runs / --fit`.
The artwork it depicts is a JR East design and the rights in that design are
theirs; what this module contains is our own drawing of it, which is why the
project ships no image file for this page and must not gain one.

WHAT IS MEASURED AND WHAT IS AUTHORED. Every key below is marked. `[measured]`
means a figure subtracted from the reference by the named mode of that script,
in canvas units. AUTHORED means chosen — a colour rounded off a noisy sample, a
corner radius fitted to a handful of rows, a polygon vertex that stands in for a
curve the reference draws smoothly. The distinction matters most where the two
disagree: a measured number that looks wrong is a fact about the reference, and
an authored one that looks wrong is mine.

THE PAGE IS THE PLACARD. A rounded white card fills most of the lower region and
carries three bands — a green header (優先席 over a `Priority Seat` / 优先座位 /
노약자 석 stack), a white panel of five blue pictograms, and a green caption
strip naming the five categories. Two lines of black text sit on the page
background beneath it. The upper band is untouched; it keeps its ordinary つぎは
display.

FOUR SCRIPTS, THREE FACES. Japanese is ShinGo DeBold and Latin is HelveticaNeue
Medium, as everywhere else in this model. The Chinese and Korean lines are
NotoSansCJKsc — the only face in `fonts/` that carries Hangul at all
(`NotoSansSC` / `NotoSansTC` / `NotoSansJP` / ShinGo all render 노약자 as four
identical tofu boxes, checked by comparing the rendered buffers). So all four
scripts draw for real and none of them is a box.

STATIC. The content depends on neither the route nor the stop, so `route_data`,
`stops`, `state` and `current_time` are accepted and unused: the signature
exists so the manager constructs and drives this view exactly as it does the
other three.

NOT WIRED. This module is the page only. The slot that shows it, its dwell and
its place in the rotation belong to `LowerDisplay` and are not touched here.
"""

import math

import pygame

from displays.train_models.e233_0 import LOWER_BG, S_HEIGHT, S_WIDTH, UPPER_HEIGHT
from displays.utils import draw_aapolygon, draw_text
from font_atlas import lcd_font, lit

_JA_FACE = "ShinGoPro-DeBold.otf"
_EN_FACE = "HelveticaNeue-Medium.otf"
# The Chinese and Korean lines. Noto Sans CJK SC is pan-CJK — it carries Hangul
# as well as Simplified Chinese — and it is the ONLY face in `fonts/` that does.
# Verified by rendering 노 / 약 / 자 / 석 and comparing the buffers: in every
# other bundled face all four come back byte-identical, which is tofu.
_CJK_FACE = "NotoSansCJKsc-Regular.otf"

# fmt: off
_TUNEABLES_PRIORITY_SEAT = {
    # =====================================================================
    # The card — the white rounded placard the whole page is
    # =====================================================================
    # [measured] `--placard`: the card's own extent is x 105.58..549.51,
    # y 160.38..410.75, and its thin grey outline runs at x 105.32 / 548.24 and
    # y 409.9 (there is no outline row along the TOP in this capture; treated as
    # capture smear rather than as a three-sided border, since a card outlined on
    # three sides is not a thing the artwork would do).
    #
    # THE CARD SITS RIGHT OF THE CANVAS CENTRE, and that is a measurement, not a
    # crop: the station plate in this same capture lands at x 120.16 against the
    # committed 120.23, so the frame is aligned to within a tenth of a pixel. The
    # card's centre is 326.9 and the canvas centre is 320.
    "card_x":            105.40,  # [measured]
    "card_y":            160.40,  # [measured]
    "card_w":            443.10,  # [measured]
    "card_h":            249.70,  # [measured]
    "card_r":              9.00,  # AUTHORED. Fitted to the corner's row-by-row
                                  # inset (`--placard` prints it): the inset
                                  # reaches zero 8.6 rows below the top edge.
    "card_color":  (254, 254, 254),  # [measured] the placard palette's most
                                     # common colour, 19586 samples
    "card_edge_color": (178, 184, 192),  # AUTHORED, rounded off four probes that
                                         # read 174..187 per channel — a 1px line
                                         # under a resampler never reads one value
    # =====================================================================
    # The green — one rect spanning all three bands, then the white panel
    # punched out of its middle
    # =====================================================================
    # [measured] `--runs ... G`: the green holds x 109.60..544.98 flat from
    # y 168.5 down to y 403, its first row is 163.0 and its last 405.0.
    "green_x":           109.60,  # [measured]
    "green_y":           162.75,  # [measured] the edge the first full row implies
    "green_w":           435.40,  # [measured]
    "green_r":             8.00,  # AUTHORED. Fitted to the corner insets the same
                                  # way as `card_r`: 5.5px of inset spent over
                                  # 5.5 rows wants a radius near 7.5-8.5.
    "header_h":          104.55,  # [measured] green from 162.75 to 267.30
    "panel_h":           110.00,  # [measured] white from 267.30 to 377.30
    "caption_h":          28.10,  # [measured] green from 377.30 to 405.40
    "green_color":  (52, 127, 25),  # [measured] 7238 samples
    # =====================================================================
    # Header — 優先席
    # =====================================================================
    # [measured] the three glyphs' ink boxes are 84.46 / 80.44 / 82.95 wide and
    # 82.45 tall, centred 104.07 and 102.31 apart. SIZE AND TRACKING ARE TWO
    # PARAMETERS and the pitch alone cannot separate them: `--fit` puts 優's own
    # ink at 84x83 at size 87, which leaves 16.2px of the 103.19 pitch unspent.
    # Fitting the run width alone would have bought the same width with a size
    # near 103 and glyphs a fifth too tall.
    "title_text":        "優先席",
    "title_size":            87,  # [measured] via `--fit ShinGoPro-DeBold 優`
    "title_tracking":     16.20,  # [measured] pitch 103.19 minus the advance
    "title_ink_x":       149.30,  # [measured] first glyph's ink left
    "title_ink_y":       177.20,  # [measured] ink top
    "title_color":  (254, 254, 254),  # AUTHORED — the card white, reused
    # =====================================================================
    # Header — the four-line stack at the right
    # =====================================================================
    # [measured] all four lines share a left edge at 453.5..454.0 and their ink
    # tops are 183 / 197 / 220 / 244. Widths 52.79 / 31.68 / 53.79 / 49.77.
    #
    # ONE SIZE SERVES BOTH CJK LINES even though the Korean then draws 3px wider
    # than the reference. Our Noto sets 노약자 석 at 53 where the reference has
    # 49.77, and the difference is the space, not the glyphs — a per-line size
    # would buy 3px by making two adjacent lines of equal rank different sizes.
    "stack_x":           453.70,  # [measured]
    "stack_lines": (
        # (text, face, size, ink-top y).  Sizes from `--fit`; each lands within
        # a pixel of the measured width.
        ("Priority",   _EN_FACE,  16, 183.00),  # [measured] y; 52 vs 52.79 wide
        ("Seat",       _EN_FACE,  16, 197.00),  # [measured] y; 32 vs 31.68 wide
        ("优先座位",     _CJK_FACE, 14, 220.00),  # [measured] y; 54 vs 53.79 wide
        ("노약자 석",    _CJK_FACE, 14, 244.00),  # [measured] y; 53 vs 49.77 wide
    ),
    # =====================================================================
    # Caption strip — five bulleted labels
    # =====================================================================
    # [measured] the five groups are 57.31 / 82.45 / 82.45 / 82.45 / 65.36 wide
    # with a 5.5-6.0 gap between them, ink rows 388.12..396.17, the whole run
    # 131.72..524.37 whose centre 328.05 is the green's own centre (327.29) to
    # within a pixel. So the run is CENTRED and laid out left to right, rather
    # than each label being placed under its pictogram — the pictograms sit
    # further left than the labels do, by 11px at the first and 43px at the last.
    "caption_texts": (
        "●お年寄りの方",
        "●からだの不自由な方",
        "●内部障がいのある方",
        "●乳幼児をお連れの方",
        "●妊娠している方",
    ),
    "caption_size":           8,  # [measured] `--fit` gives 56 / 80 / 64 against
                                  # 57.31 / 82.45 / 65.36
    "caption_ink_y":     388.10,  # [measured]
    "caption_cx":        328.05,  # [measured] centre of the whole run
    "caption_gap":         5.70,  # [measured] label to label
    "caption_color": (254, 254, 254),  # AUTHORED — the card white, reused
    # =====================================================================
    # The two body lines, on the page background under the card
    # =====================================================================
    # BOTH LINES ARE HORIZONTALLY CONDENSED, and that is measured rather than
    # assumed: 優 in the body line has an ink box of 16.09 x 20.11, while the
    # SAME character in the header of the SAME capture is 84.46 x 82.45 — square.
    # So the body face is a condensed cut, which `fonts/` does not hold; the
    # nearest we can draw is the normal cut squeezed by `displays.utils.draw_text`
    # (`h_ratio`), which is the primitive that already exists for it.
    #
    # Each line carries its own centre because the reference disagrees with
    # itself about them: the Japanese line's ink centres on 327.29 (with the card,
    # at 326.9) and the English on 320.50 (with the canvas). Averaging the two
    # would reproduce neither.
    "body_ja_text":  "優先席を必要とされるお客様がいらっしゃいましたら、席をお譲りください。",
    "body_ja_size":          20,  # [measured] ink 20 tall vs 20.11
    "body_ja_squeeze":    0.857,  # [measured] 589.22 measured / 688 natural
    "body_ja_ink_y":     424.80,  # [measured]
    "body_ja_cx":        327.29,  # [measured] ink centre
    "body_en_text":  "Please offer your seat to those who may need it.",
    "body_en_size":          23,  # [measured] ink 22 tall vs 21.12
    "body_en_squeeze":    0.908,  # [measured] 462.03 measured / 509 natural
    "body_en_ink_y":     453.50,  # [measured]
    "body_en_cx":        320.50,  # [measured] ink centre
    "body_color":     (0, 0, 0),  # AUTHORED. The reference's darkest body pixel
                                  # is (6,10,16); black is what every other view
                                  # in this model inks with and the difference is
                                  # capture noise.
    # =====================================================================
    # The five pictograms
    # =====================================================================
    # ONE SKELETON, FIVE COPIES. Measured per figure with `--runs ... B` and the
    # five agree to within half a pixel on every part: figure 1's torso front
    # edge is 25.1 past its own back edge and figure 2's is 25.1 past its own.
    # So the seated body is authored ONCE, in figure-local units, and each figure
    # is that shape at its own x with its own attribute.
    #
    # Local origin = (the torso's back edge where the torso begins, the head's
    # ink top). Chosen because those are the two edges every figure agrees on;
    # anchoring on the seat bar instead put figure 5's head 3px out, since that
    # figure leans back further.
    "figure_color":  (11, 79, 134),  # [measured] 886 samples
    "figure_y":          283.00,  # [measured] head ink top, identical on all five
    "figure_x": (123.20, 198.10, 280.50, 353.40, 426.80),  # [measured] per figure
                                  # own offset from the shared position. Figure 5
                                  # leans back and figure 4 forward; the rest sit
                                  # within a quarter-pixel of each other.
                                  # figures holding something reach forward
    # =====================================================================
    # The five pictograms, TRACED
    # =====================================================================
    # [measured] `--trace <ref> 0.45` — the outer contour of every blue
    # component, Douglas-Peucker simplified at 0.45 canvas px, in each
    # figure's own local units. A parametric body could not reproduce these:
    # no parameterisation represents an arbitrary outline, and the fourth
    # figure (adult holding an infant) is a single fused silhouette that the
    # torso/thigh/shin model drew as unrelated blocks. Same call as the
    # E233-0 current-stop marker — a fixed-orientation mark is a free vertex
    # list and the vertices ARE the shape (`conventions.md` § Display module
    # structure).
    "figure_polys": (
        (  # figure 0
            ((-2.54, 64.80), (-3.04, 65.19), (-3.18, 65.91), (-3.17, 68.42), (-3.03, 68.92), (-2.54, 69.29), (25.11, 69.41), (26.12, 69.07), (26.32, 68.42), (26.27, 65.41), (25.61, 64.73), (-2.54, 64.80)),
            ((-1.03, 19.95), (-1.31, 20.66), (4.38, 54.34), (5.68, 57.36), (8.02, 59.99), (10.53, 61.15), (29.13, 61.61), (29.84, 62.89), (34.78, 87.53), (35.17, 88.08), (36.17, 88.39), (42.71, 88.38), (43.49, 88.03), (43.79, 87.02), (41.34, 53.84), (40.33, 51.33), (38.18, 49.17), (36.17, 48.36), (22.09, 47.45), (21.54, 47.31), (21.20, 46.80), (20.79, 38.76), (21.09, 37.54), (22.09, 37.26), (30.14, 36.98), (37.18, 36.39), (37.84, 35.74), (38.26, 34.74), (39.71, 30.72), (39.60, 30.21), (38.69, 29.76), (22.60, 29.70), (14.05, 23.07), (8.52, 19.98), (6.51, 19.69), (-0.03, 19.70), (-1.03, 19.95)),
            ((5.50, 0.43), (3.49, 1.23), (1.48, 2.71), (0.15, 4.57), (-0.68, 6.58), (-0.83, 9.10), (-0.05, 12.11), (1.27, 14.12), (2.49, 15.13), (3.49, 15.80), (6.01, 16.71), (8.52, 16.75), (11.03, 15.96), (12.54, 15.00), (14.29, 13.12), (15.45, 10.61), (15.76, 8.59), (15.53, 6.58), (14.70, 4.57), (12.54, 2.01), (11.03, 1.07), (9.02, 0.36), (5.50, 0.43)),
            ((45.22, 29.64), (42.71, 30.56), (41.06, 32.22), (40.45, 33.73), (40.39, 39.26), (40.59, 39.77), (41.20, 40.07), (42.63, 39.77), (42.91, 33.73), (43.50, 32.73), (44.22, 32.29), (45.72, 31.87), (48.74, 31.95), (50.15, 32.73), (50.84, 33.73), (51.00, 88.03), (51.25, 88.62), (52.76, 88.87), (53.77, 88.67), (54.06, 88.03), (53.94, 33.73), (53.03, 31.72), (51.25, 30.32), (48.74, 29.63), (45.22, 29.64)),
        ),
        (  # figure 1
            ((-2.53, 64.89), (-2.84, 65.41), (-2.89, 68.42), (-2.78, 68.92), (-2.03, 69.34), (25.62, 69.34), (26.45, 68.92), (26.58, 66.91), (26.55, 65.41), (26.23, 64.90), (25.62, 64.73), (-2.53, 64.90)),
            ((-0.52, 19.81), (-0.99, 20.16), (-1.04, 20.66), (3.98, 50.32), (4.70, 54.34), (5.97, 57.36), (8.53, 60.11), (11.04, 61.18), (13.56, 61.42), (28.14, 61.41), (29.65, 61.74), (30.77, 65.91), (35.18, 87.72), (36.18, 88.40), (43.22, 88.35), (43.80, 88.03), (44.04, 87.02), (41.62, 53.84), (40.71, 51.53), (38.69, 49.28), (36.68, 48.42), (22.61, 47.45), (21.60, 46.99), (21.46, 46.30), (21.19, 37.75), (22.10, 37.30), (37.19, 36.46), (38.36, 35.24), (39.90, 31.22), (39.92, 30.21), (38.69, 29.79), (23.11, 29.73), (22.10, 29.32), (15.07, 23.59), (10.04, 20.48), (7.02, 19.72), (-0.52, 19.81)),
            ((5.51, 0.48), (3.00, 1.71), (1.49, 3.04), (0.41, 4.57), (-0.52, 7.05), (-0.37, 10.61), (0.86, 13.12), (2.50, 14.94), (4.01, 15.92), (6.52, 16.73), (9.03, 16.72), (11.55, 15.83), (13.56, 14.39), (15.07, 12.29), (15.77, 10.61), (15.99, 8.59), (15.93, 7.09), (15.23, 5.08), (14.35, 3.57), (12.55, 1.80), (9.54, 0.37), (7.52, 0.21), (5.51, 0.48)),
            ((39.70, 12.33), (39.43, 13.12), (40.58, 16.14), (41.48, 17.64), (41.54, 38.26), (46.99, 44.79), (48.28, 46.80), (48.24, 87.02), (48.74, 88.03), (49.25, 88.15), (50.26, 87.93), (50.60, 87.53), (50.63, 47.31), (57.41, 38.76), (57.39, 17.64), (58.53, 15.63), (59.39, 12.62), (58.80, 12.26), (56.79, 12.18), (39.70, 12.34)),
            ((44.75, 17.14), (45.73, 16.80), (53.27, 16.81), (54.08, 17.14), (54.24, 17.64), (54.17, 37.75), (50.43, 42.28), (49.76, 42.75), (49.25, 42.60), (47.62, 40.77), (45.07, 37.75), (44.63, 36.75), (44.75, 17.14)),
        ),
        (  # figure 2
            ((-1.98, 64.80), (-2.56, 65.41), (-2.59, 68.42), (-2.45, 68.92), (-1.47, 69.34), (25.67, 69.37), (26.68, 69.01), (26.90, 68.42), (26.86, 65.41), (26.18, 64.76), (-1.98, 64.80)),
            ((5.06, 0.49), (3.05, 1.39), (1.52, 2.56), (-0.04, 4.57), (-0.86, 6.58), (-1.04, 9.10), (-0.62, 11.11), (0.36, 13.12), (2.30, 15.13), (3.55, 15.94), (6.57, 16.77), (8.58, 16.68), (11.09, 15.83), (13.11, 14.39), (14.18, 13.12), (15.28, 10.61), (15.54, 8.59), (15.33, 6.58), (14.81, 5.08), (13.61, 3.18), (12.10, 1.81), (10.59, 0.93), (8.58, 0.31), (6.57, 0.21), (5.06, 0.49)),
            ((0.54, 19.65), (-0.47, 19.81), (-0.93, 20.66), (2.80, 42.78), (3.38, 44.79), (4.36, 51.83), (5.14, 55.35), (6.46, 57.86), (7.58, 59.27), (9.08, 60.43), (10.09, 60.99), (12.60, 61.55), (28.69, 61.65), (29.70, 61.85), (30.32, 62.89), (34.44, 84.01), (35.46, 88.03), (36.73, 88.63), (43.27, 88.64), (44.28, 88.18), (44.54, 87.02), (44.16, 84.51), (43.25, 68.92), (42.70, 64.90), (42.39, 57.36), (41.74, 52.84), (40.80, 50.83), (39.25, 49.32), (37.24, 48.35), (22.53, 47.31), (22.19, 46.80), (22.22, 32.73), (21.39, 30.21), (18.87, 26.19), (17.57, 24.68), (14.61, 22.11), (10.59, 20.04), (7.07, 19.67), (0.54, 19.65)),
            ((5.76, 27.70), (6.57, 27.42), (8.08, 27.46), (11.09, 28.86), (13.61, 27.52), (15.62, 27.50), (17.62, 28.70), (18.81, 30.72), (18.97, 32.73), (17.85, 35.74), (16.62, 37.73), (13.61, 40.61), (11.09, 41.89), (9.30, 41.27), (6.57, 39.21), (4.56, 36.64), (3.00, 33.23), (2.83, 31.72), (3.05, 30.63), (4.06, 28.94), (5.76, 27.70)),
            ((10.59, 30.61), (9.88, 31.22), (9.59, 32.89), (7.58, 33.37), (7.18, 34.23), (7.58, 35.44), (9.59, 35.90), (10.09, 37.81), (10.59, 38.10), (11.60, 38.06), (11.99, 37.75), (12.22, 36.25), (12.58, 35.74), (14.61, 35.30), (14.86, 34.23), (14.61, 33.53), (12.60, 33.04), (12.26, 32.73), (12.02, 31.22), (11.52, 30.72), (10.59, 30.61)),
        ),
        (  # figure 3
            ((-1.98, 64.83), (-2.55, 65.41), (-2.58, 68.42), (-2.45, 68.92), (-1.48, 69.34), (25.67, 69.38), (26.68, 69.04), (26.92, 68.42), (26.84, 65.41), (26.18, 64.77), (-1.98, 64.83)),
            ((-0.47, 19.93), (-0.74, 20.66), (4.99, 54.34), (6.26, 57.36), (8.51, 59.88), (11.09, 61.13), (14.11, 61.43), (29.70, 61.57), (30.33, 62.39), (35.12, 86.52), (35.67, 88.03), (36.73, 88.39), (43.27, 88.41), (44.11, 88.03), (44.36, 87.02), (41.96, 53.84), (40.63, 50.83), (39.09, 49.32), (36.73, 48.35), (22.35, 47.31), (21.93, 46.80), (22.31, 40.27), (22.06, 32.73), (21.28, 30.21), (19.14, 26.67), (17.45, 24.68), (15.12, 22.65), (13.61, 21.56), (10.09, 20.02), (7.57, 19.70), (1.04, 19.69), (-0.47, 19.93)),
            ((6.57, 0.48), (4.05, 1.74), (2.09, 3.57), (0.57, 7.09), (0.73, 10.61), (2.04, 13.33), (3.55, 14.88), (5.06, 15.88), (7.57, 16.73), (10.09, 16.72), (12.60, 15.85), (14.89, 14.12), (16.12, 12.31), (16.85, 10.61), (17.07, 8.59), (16.89, 6.58), (16.29, 5.08), (15.43, 3.57), (13.99, 2.06), (12.60, 1.16), (10.59, 0.40), (8.58, 0.20), (6.57, 0.48)),
            ((26.68, 14.63), (24.38, 16.14), (23.64, 17.14), (23.09, 18.65), (23.05, 20.16), (23.35, 21.16), (25.17, 23.33), (26.68, 24.15), (28.19, 24.35), (30.70, 23.39), (31.71, 22.49), (32.56, 21.16), (32.87, 19.15), (32.26, 17.14), (30.70, 15.37), (28.69, 14.51), (26.68, 14.62)),
            ((24.16, 26.80), (23.72, 27.70), (24.06, 39.77), (24.32, 40.77), (25.92, 42.78), (27.18, 43.68), (28.69, 44.16), (34.22, 44.42), (39.75, 46.78), (40.71, 46.30), (42.57, 43.79), (42.26, 43.17), (37.24, 40.05), (33.21, 39.07), (32.46, 38.26), (32.30, 35.74), (32.71, 34.93), (36.73, 36.42), (37.74, 36.54), (38.48, 35.74), (39.17, 34.23), (39.17, 33.73), (38.74, 33.24), (29.19, 27.43), (24.16, 26.80)),
        ),
        (  # figure 4
            ((2.55, 0.45), (0.91, 1.05), (-1.28, 2.56), (-2.71, 4.57), (-3.64, 7.09), (-3.66, 9.60), (-2.90, 12.11), (-1.58, 14.12), (-0.47, 15.05), (1.04, 15.98), (3.05, 16.69), (6.07, 16.72), (8.08, 15.98), (9.59, 15.08), (11.43, 13.12), (12.59, 10.61), (12.87, 8.59), (12.65, 6.58), (11.80, 4.57), (11.23, 3.57), (9.59, 1.94), (6.07, 0.31), (2.55, 0.45)),
            ((-2.48, 64.85), (-3.01, 65.41), (-3.03, 68.42), (-2.89, 68.92), (-1.98, 69.35), (25.17, 69.35), (26.18, 69.08), (26.44, 68.42), (26.39, 65.41), (25.67, 64.77), (-2.48, 64.85)),
            ((-0.97, 19.97), (-1.21, 20.66), (4.51, 54.34), (5.54, 56.86), (7.00, 58.87), (8.09, 59.88), (10.59, 61.12), (13.11, 61.43), (27.18, 61.40), (29.19, 61.71), (29.51, 62.39), (29.57, 64.90), (30.73, 66.91), (34.67, 86.52), (35.23, 88.03), (36.23, 88.43), (42.77, 88.40), (43.64, 88.03), (43.90, 87.53), (42.24, 63.90), (42.77, 63.45), (44.78, 63.28), (45.21, 62.89), (41.86, 54.34), (40.40, 51.83), (38.24, 49.57), (34.50, 47.81), (33.14, 40.77), (32.35, 38.26), (31.20, 35.87), (29.11, 33.23), (26.18, 31.09), (24.17, 30.27), (20.14, 29.43), (19.14, 28.99), (17.63, 27.67), (12.84, 22.17), (9.59, 20.13), (7.07, 19.71), (0.03, 19.70), (-0.97, 19.97)),
        ),
    ),
    # ---- the shared body, as sub-dicts per part ------------------------
    # Each part is its own dict so a nudge to the thigh cannot move the shin.
    # ---- the five attributes -------------------------------------------
    # ---- drawing ---------------------------------------------------------
    "aa_scale":  4,  # AUTHORED. `draw_aapolygon`'s supersample factor. 2 gives
                     # three alpha levels across an edge, which shows as steps on
                     # a head this small.
    "ink_min_alpha": 110,  # AUTHORED — matches the transfer view's threshold, so
                           # the two views place text against one definition of
                           # where a glyph starts
}
# fmt: on

# The whole lower region — this page has no sub-element the calibration editor
# picks apart, so its hit-test rect is the region it draws into. Same shape as
# the transfer view's `TRANSFER_VIEW_RECT`.
PRIORITY_SEAT_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)


def _draws():
    """The atlas declaration for every string this page draws, DERIVED.

    Read out of the tuneables rather than restated beside them, so an edit to the
    notice cannot leave the declaration behind. The title is declared PER
    CHARACTER because tracking is applied by drawing one glyph at a time — a
    declaration of the whole run would not cover what is actually rendered.
    """
    t = _TUNEABLES_PRIORITY_SEAT
    per_face = {
        _JA_FACE: [*t["title_text"], *t["caption_texts"], t["body_ja_text"]],
        _EN_FACE: [t["body_en_text"]],
        _CJK_FACE: [],
    }
    for text, face, _size, _y in t["stack_lines"]:
        per_face.setdefault(face, []).append(text)
    return {face: lit(*strings) for face, strings in per_face.items()}


_DRAWS = _draws()


# ---------------------------------------------------------------------------
# Geometry primitives
#
# All three return a vertex list for `displays.utils.draw_aapolygon`, which
# TRUNCATES each coordinate to an int and supersamples what is left. So a shape
# lands on the pixel grid whatever is passed; the sub-pixel figures in the
# tuneables above set where the truncation lands, not where the edge does.
# ---------------------------------------------------------------------------


def _round_rect(x, y, w, h, r_tl=0.0, r_tr=0.0, r_br=0.0, r_bl=0.0, seg=8):
    """A rectangle with per-corner radii, as a polygon.

    Per-corner rather than one radius because the green header's BOTTOM corners
    are square — it meets the white panel — and the caption strip's TOP corners
    are. One radius would round all four and put a white notch at each join.
    """
    pts = []

    def arc(cx, cy, r, a0, a1):
        if r <= 0:
            pts.append((cx, cy))
            return
        for i in range(seg + 1):
            a = a0 + (a1 - a0) * i / seg
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    arc(x + r_tl, y + r_tl, r_tl, math.pi, 1.5 * math.pi)
    arc(x + w - r_tr, y + r_tr, r_tr, 1.5 * math.pi, 2 * math.pi)
    arc(x + w - r_br, y + h - r_br, r_br, 0.0, 0.5 * math.pi)
    arc(x + r_bl, y + h - r_bl, r_bl, 0.5 * math.pi, math.pi)
    return pts


def _bar(x0, y0, x1, y1, r=0.0):
    """An axis-aligned bar, optionally with rounded ends."""
    if r <= 0:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return _round_rect(x0, y0, x1 - x0, y1 - y0, r, r, r, r, seg=4)


class PrioritySeatDisplay:
    """The 優先席 notice. Static — see the module docstring."""

    def __init__(self, screen, route_data: dict, stops: list):
        self.screen = screen
        # Held, not read. The page is the same on every route and at every stop;
        # these exist so the manager can construct this view with the same call
        # it uses for the other three.
        self.route_data = route_data
        self.stops = stops
        self.state = None

        self._fonts: dict = {}
        # The page is expensive to draw and never changes, so it is composed once
        # into a surface and blitted thereafter. Keyed on the tuneables so a live
        # edit still takes effect — `repr` of this dict is microseconds and the
        # alternative is a cache the calibration editor cannot invalidate.
        self._page = None
        self._page_key = None

    # ---- state ----------------------------------------------------------

    def set_state(self, state) -> None:
        """Bind AppState by reference, as the sibling views do.

        Nothing on this page reads it. The binding is kept so the manager's
        `set_state` fan-out needs no per-view exception.
        """
        self.state = state

    # ---- fonts + ink ----------------------------------------------------

    def _font(self, face: str, size: int):
        f = self._fonts.get((face, size))
        if f is None:
            f = lcd_font(face, size, draws=_DRAWS[face])
            self._fonts[(face, size)] = f
        return f

    def _text(self, face: str, size: int, text: str, color, squeeze: float = 1.0):
        """`(surface, ink_rect)` — the render plus where its ink sits in it.

        The ink rect is what every placement here uses: the page's figures are
        measured as ink and its text was measured as ink, so a line placed by the
        font BOX lands wrong by the face's internal leading — which is what put
        the transfer view's English line on top of its Japanese one.
        """
        font = self._font(face, size)
        surf = draw_text(text, font, color, 0, 0, h_ratio=squeeze) if squeeze != 1.0 else font.render(text, True, color)
        return surf, surf.get_bounding_rect(min_alpha=int(_TUNEABLES_PRIORITY_SEAT["ink_min_alpha"]))

    def _blit_ink(self, surface, face, size, text, color, ink_x, ink_y, squeeze=1.0):
        """Blit so the ink's top-left lands on `(ink_x, ink_y)`."""
        surf, box = self._text(face, size, text, color, squeeze)
        surface.blit(surf, (int(round(ink_x - box.x)), int(round(ink_y - box.y))))
        return box

    # ---- the card -------------------------------------------------------

    def _draw_card(self, surface) -> None:
        t = _TUNEABLES_PRIORITY_SEAT
        aa = int(t["aa_scale"])
        x, y, w, h = (float(t[k]) for k in ("card_x", "card_y", "card_w", "card_h"))
        r = float(t["card_r"])
        draw_aapolygon(surface, tuple(t["card_color"]), _round_rect(x, y, w, h, r, r, r, r), scale=aa)
        # The outline is a stroked path, so it is the same polygon drawn again
        # with a width rather than a second, inset shape — an inset copy would
        # need its own radius and would drift from the fill's the moment either
        # moved.
        draw_aapolygon(surface, tuple(t["card_edge_color"]), _round_rect(x, y, w, h, r, r, r, r), scale=aa, width=1)

        gx, gy, gw = (float(t[k]) for k in ("green_x", "green_y", "green_w"))
        gr = float(t["green_r"])
        head_h, cap_h = float(t["header_h"]), float(t["caption_h"])
        cap_y = gy + head_h + float(t["panel_h"])
        # Two separate bands rather than one green rect with the panel punched
        # out of it: the punch would have to be drawn in the CARD's white, and a
        # white rect over a rounded green one leaves the green's side edges
        # showing beside it wherever the two disagree by a fraction of a pixel.
        draw_aapolygon(surface, tuple(t["green_color"]), _round_rect(gx, gy, gw, head_h, gr, gr, 0, 0), scale=aa)
        draw_aapolygon(surface, tuple(t["green_color"]), _round_rect(gx, cap_y, gw, cap_h, 0, 0, gr, gr), scale=aa)

    # ---- the header -----------------------------------------------------

    def _draw_header(self, surface) -> None:
        t = _TUNEABLES_PRIORITY_SEAT
        color = tuple(t["title_color"])
        size = int(t["title_size"])
        x = float(t["title_ink_x"])
        y = float(t["title_ink_y"])
        # ONE GLYPH AT A TIME, because the run is tracked out: its 103.19 pitch
        # is 16.2 wider than the advance of the size whose glyphs match, and no
        # single `render` call can produce that.
        for i, ch in enumerate(str(t["title_text"])):
            box = self._blit_ink(surface, _JA_FACE, size, ch, color, x, y)
            x += box.w + float(t["title_tracking"])

        for text, face, size, ink_y in t["stack_lines"]:
            self._blit_ink(surface, face, int(size), text, color, float(t["stack_x"]), float(ink_y))

    # ---- the caption strip ----------------------------------------------

    def _draw_caption(self, surface) -> None:
        t = _TUNEABLES_PRIORITY_SEAT
        size = int(t["caption_size"])
        color = tuple(t["caption_color"])
        gap = float(t["caption_gap"])
        labels = [self._text(_JA_FACE, size, s, color) for s in t["caption_texts"]]
        total = sum(b.w for _s, b in labels) + gap * (len(labels) - 1)
        # Laid out left to right from the run's own centre. Our labels come out
        # 10px narrower than the reference's over the whole run, so anchoring the
        # first one at its measured x would push the last one 10px short of where
        # the reference ends it; centring splits that between the two ends.
        x = float(t["caption_cx"]) - total / 2.0
        y = float(t["caption_ink_y"])
        for surf, box in labels:
            surface.blit(surf, (int(round(x - box.x)), int(round(y - box.y))))
            x += box.w + gap

    # ---- the pictograms -------------------------------------------------

    def _draw_figures(self, surface) -> None:
        """All five figures, built at `aa_scale` and resolved by ONE downscale.

        One scratch for the whole row rather than one per figure: the figures do
        not touch, so nothing merges that should not, and a single `smoothscale`
        is both cheaper and free of the per-figure rounding that five separate
        resolves would introduce.

        The scratch is pre-filled with the FIGURE COLOUR at zero alpha, which is
        `displays/utils.py::draw_aapolygon`'s own contract and for its reason:
        `smoothscale` averages RGB and alpha independently, so an edge resolving
        against a differently-coloured transparent field comes back carrying that
        colour as a fringe (`conventions.md` § UI code style).
        """
        t = _TUNEABLES_PRIORITY_SEAT
        scale = int(t["aa_scale"])
        # The white panel between the header and the caption strip — the band
        # the figures live in, taken from the same keys that draw it.
        org_x = float(t["green_x"])
        org_y = float(t["green_y"]) + float(t["header_h"])
        w, h = float(t["green_w"]), float(t["panel_h"])
        scratch = pygame.Surface((int(w * scale), int(h * scale)), pygame.SRCALPHA)
        scratch.fill((*tuple(t["figure_color"]), 0))
        self._fig_ctx = (scratch, scale, org_x, org_y)
        for i in range(len(t["figure_x"])):
            self._draw_figure(surface, i)
        surface.blit(pygame.transform.smoothscale(scratch, (int(round(w)), int(round(h)))), (int(round(org_x)), int(round(org_y))))

    @staticmethod
    def _signed_area(points) -> float:
        """Shoelace. Its SIGN is what separates a solid loop from a hole."""
        n = len(points)
        return 0.5 * sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))

    def _fpoly(self, points, color=None) -> None:
        """One part of a figure, HARD-EDGED into the shared supersampled scratch.

        The figures were being composited from separately antialiased parts —
        head, torso, arm, thigh, shin, seat, each `draw_aapolygon`'d onto the
        page in turn. Every place two parts abut, their edge alphas then blend
        against the BACKGROUND instead of merging, so the join shows as a pale
        seam and the silhouette reads rough (author, 2026-08-29: *"the drawing
        on the human body needs more work, it is not smooth"*).

        The fix is the construction the position marker already uses: build
        everything large, composite while large, and let ONE downscale do the
        antialiasing. At 4x the parts merge into a single silhouette and there
        are no internal edges left to fringe.
        """
        surf, scale, org_x, org_y = self._fig_ctx
        pygame.draw.polygon(
            surf,
            color or tuple(_TUNEABLES_PRIORITY_SEAT["figure_color"]),
            [(round((px - org_x) * scale), round((py - org_y) * scale)) for px, py in points],
        )

    def _draw_figure(self, surface, index: int) -> None:
        """One pictogram, as the contours traced off the reference.

        A parametric body — a torso from two edge lists, a thigh quad, a shin
        quad, an attribute per figure — was the wrong construction. No
        parameterisation reproduces an arbitrary drawn outline, and the fourth
        figure is where that showed: an adult holding an infant is ONE fused
        silhouette, and the part model drew it as unrelated blocks (author,
        2026-08-29: *"completely bugged"*, and the suggestion that settled it,
        *"extract the drawings using a color filter"*).

        So the vertices ARE the shape, which is the same call
        `conventions.md` § "Display module structure" already records for this
        model's current-stop marker. The parts and their attribute drawers are
        gone; what is left is a list of contours per figure and this loop.
        """
        del surface  # contours go to the scratch in `_fig_ctx`, not to the page
        t = _TUNEABLES_PRIORITY_SEAT
        ox = float(t["figure_x"][index])
        oy = float(t["figure_y"])
        # SOLIDS FIRST, THEN HOLES, decided by WINDING. Marching squares walks
        # every loop with the high side of the field on one hand, so an outer
        # boundary and the boundary of an enclosed white shape come back with
        # opposite signed area. That is what draws the heart: it is a hole in the
        # blue, invisible to a blue-only filter, and here it needs no special
        # case at all — its loop simply winds the other way.
        blue = tuple(t["figure_color"])
        white = tuple(t["card_color"])
        loops = sorted(
            (([(ox + px, oy + py) for px, py in c], self._signed_area(c)) for c in t["figure_polys"][index]),
            key=lambda lp: -abs(lp[1]),
        )
        if not loops:
            return
        # The LARGEST loop of a figure is a solid by construction, so its sign
        # defines which way round "solid" winds — rather than assuming marching
        # squares' convention, which screen-space y (down-positive) flips. The
        # first render did assume it and came out as outlines: every body drawn
        # in the panel white and every hole in blue.
        solid = 1.0 if loops[0][1] >= 0 else -1.0
        for pts, area in loops:
            self._fpoly(pts, blue if area * solid >= 0 else white)
        return

    # ---- composition ----------------------------------------------------

    def _build_page(self) -> pygame.Surface:
        """The whole page, composed once at CANVAS coordinates.

        Full-canvas rather than region-sized so every number in the tuneables is
        the number that was measured, with no offset arithmetic between the two.
        Only the lower sub-rect is ever blitted, so the upper band is untouched.
        """
        surface = pygame.Surface((S_WIDTH, S_HEIGHT), pygame.SRCALPHA)
        surface.fill((*LOWER_BG, 255), PRIORITY_SEAT_RECT)
        self._draw_card(surface)
        self._draw_header(surface)
        self._draw_figures(surface)
        self._draw_caption(surface)

        t = _TUNEABLES_PRIORITY_SEAT
        body = tuple(t["body_color"])
        for face, key in ((_JA_FACE, "body_ja"), (_EN_FACE, "body_en")):
            surf, box = self._text(face, int(t[f"{key}_size"]), str(t[f"{key}_text"]), body, float(t[f"{key}_squeeze"]))
            # Centred on the INK, not the surface: both lines end in a full-stop
            # whose right-hand half is empty, so centring by surface width sits
            # them visibly left of the axis they were measured on.
            x = float(t[f"{key}_cx"]) - box.w / 2.0 - box.x
            surface.blit(surf, (int(round(x)), int(round(float(t[f"{key}_ink_y"]) - box.y))))
        return surface

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Draw the whole page. Pure render — mutates nothing but the surface.

        `state` and `current_time` are accepted and unused: the page is static,
        and the signature is the one the manager calls every view with.
        """
        del current_time
        self.state = state

        key = repr(_TUNEABLES_PRIORITY_SEAT)
        if self._page is None or self._page_key != key:
            self._page = self._build_page()
            self._page_key = key
        self.screen.blit(self._page, PRIORITY_SEAT_RECT.topleft, PRIORITY_SEAT_RECT)

    def draw(self, current_time: float = 0.0) -> None:
        """Redraw from the bound state, matching the sibling views' entry."""
        self.show_stops(self.state, current_time)


# Module-level so the calibration editor's registry and any preview reach the
# same dict the renderer reads (`conventions.md` § UI code style).
__all__ = ["PrioritySeatDisplay", "PRIORITY_SEAT_RECT", "_TUNEABLES_PRIORITY_SEAT"]

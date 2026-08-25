# SPDX-License-Identifier: MIT
"""E233-0 (中央線快速) — per-model dimensions and palette.

Values here are the whole-display basics settled in
``docs/wip/WIP_e233_0_display.md`` § 2. They are the denominator every later
number in this model is expressed against, so they are decided once, up front,
and not adjusted to make a later element fit.

Constants are defined BEFORE the class imports at the bottom, so ``upper_lcd`` /
``lower_lcd`` can ``from displays.train_models.e233_0 import S_WIDTH, ...``
without hitting a partial-module circular import.

The model is registered in ``displays/train_models/__init__.py`` and selectable,
but it is a BUILD IN PROGRESS: the upper band draws only the elements whose
drill-down has happened, and the lower LCD is a background placeholder. See
``docs/wip/WIP_e233_0_display.md`` for what is specced and what is not.
"""

# =============================================================================
# Canvas
# =============================================================================
# E233-0 is a 4:3 panel. Measured 1.3363 / 1.3350 / 1.3363 across three
# references at two pixel sizes; the residual above 4:3 is capture crop.
#
# This is the first thing NOT inherited from the E235 fork source, which is
# 730x420 (~16:9). The window changes size when the model changes — supported,
# since TRAIN_MODELS carries S_WIDTH / S_HEIGHT per model.
S_WIDTH = 640
S_HEIGHT = 480

# Upper / lower divide, measured at 0.3105 of full height in all three
# references — agreement to within a pixel, tighter than any other figure taken
# off them. round(0.3105 * 480) = 149, leaving a 331px lower area.
#
# UPPER_HEIGHT is where the LOWER AREA BEGINS. The upper background stops a
# little short of it (see DIVIDE_RULE_H below) — the gap is the separator.
UPPER_HEIGHT = 149

# =============================================================================
# Palette
# =============================================================================
# Sampled from the references by colour-run detection, not picked by eye.
UPPER_BG = [168, 177, 202]  # blue-grey, flat, no gradient
LOWER_BG = [213, 223, 239]  # paler blue, flat

# RULE_GREY draws every hairline on this display, and they are one colour on
# purpose — measured, not assumed equal:
#
#   * the divide between upper and lower. Not a bare colour change: the upper
#     background ends at y/H 0.3052 and ~2px of this grey sits between it and
#     the lower background, which begins at 0.3105.
#   * the border around the whole screen (author-confirmed as real, 2026-08-22).
#     Measured one pixel in from each edge, every edge of both references lands
#     on this same grey: (136,145,165) / (144,151,168) / (147,152,165). The
#     OUTERMOST pixel reads darker still and disagrees per edge — 105..145 —
#     which is what a crop clipping through the border into a dark surround
#     looks like, so it is treated as contamination rather than as the colour.
#   * the route bar where the line continues BEYOND this train's service
#     (the diagram draws the line, not the run — see the WIP doc).
#
# One constant rather than three that drift apart. Widths are separate because
# they genuinely differ.
RULE_GREY = [135, 145, 165]
DIVIDE_RULE_H = 2  # px; measured ~2px in both refs regardless of their size
BORDER_W = 1  # px; ~0.26% of the dimension in the refs. Tuneable — the exact
# width wants a reference that is not an upscale.

# Route bar. ORANGE where this train serves; RULE_GREY where the line continues
# beyond its service. Element-level geometry belongs to the full-route
# drill-down; only the colours are whole-display facts.
BAR_ORANGE = [225, 92, 18]
BAR_BEYOND = RULE_GREY

PLATE_WHITE = [254, 254, 254]
# The plate is OUTLINED, and the outline is black rather than RULE_GREY — this
# is the one hairline on the display that is not that grey. It also FADES; the
# geometry of the fade belongs to the element, so it lives with the plate in
# upper_lcd.py. This is the colour it fades FROM.
PLATE_BORDER = [0, 0, 0]

# =============================================================================
# Chrome is STATE-INVARIANT
# =============================================================================
# CONTRACT: the two backgrounds, the divide rule and the border never change —
# not per train type, not per approach/stop state, not per view (author,
# 2026-08-22). So a renderer may fill its own region freely and must never
# recolour the chrome. If a future reference contradicts this, change it HERE;
# do not let one view start tinting its own background.

from displays.train_models.e233_0.upper_lcd import UpperDisplay  # noqa: E402
from displays.train_models.e233_0.lower_lcd import LowerDisplay  # noqa: E402

__all__ = [
    "UpperDisplay",
    "LowerDisplay",
    "S_WIDTH",
    "S_HEIGHT",
    "UPPER_HEIGHT",
    "UPPER_BG",
    "LOWER_BG",
    "RULE_GREY",
    "DIVIDE_RULE_H",
    "BORDER_W",
    "BAR_ORANGE",
    "BAR_BEYOND",
    "PLATE_WHITE",
]

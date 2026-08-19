# SPDX-License-Identifier: MIT
"""Shared rendering utilities for display system.

Contains both generic pygame primitives (text, polygons, chevron-arrow
geometry, vertical column text) and display-domain helpers (badges,
continuity indicators, route-map disclaimer). Single home for the
display package — every train-model module imports from here.
"""

import re
from contextlib import contextmanager
from typing import Dict, List, Tuple

import pygame
import pygame.gfxdraw

import font_atlas
from app_paths import project_root

BADGE_TEXT = (15, 15, 15)  # dark — text sits on white interior
WHITE_BG = (230, 230, 230)

# Station-code badges ALWAYS render in NeueFrutigerWorld-Bold — the JR East
# signage typeface (Frutiger). The face is hardcoded here on purpose: callers
# pass only a point size, never a font, so no badge can ever be drawn in the
# wrong face. Cached by size to avoid per-frame Font construction.
_BADGE_FONT_FILE = "NeueFrutigerWorld-Bold.otf"
_badge_font_cache: Dict[int, pygame.font.Font] = {}


def _badge_font(size: float) -> pygame.font.Font:
    key = max(1, int(round(size)))
    f = _badge_font_cache.get(key)
    if f is None:
        f = pygame.font.Font(str(project_root() / "fonts" / _BADGE_FONT_FILE), key)
        _badge_font_cache[key] = f
    return f


# Font resolution for LCD renderers lives in font_atlas.lcd_font — one owner,
# so a renderer cannot accidentally get a live font in a build that ships none.
# Badges are the exception above: _badge_font hardcodes its face on purpose.


# =============================================================================
# Generic pygame primitives
# =============================================================================


@contextmanager
def clip(surface: pygame.Surface, rect):
    """Restrict drawing to ``rect`` for the duration of the with-block.

    Pixels drawn outside ``rect`` are silently dropped at the pygame layer —
    a hard guarantee that a region's draw cannot bleed into a neighbouring
    region's territory. Pairs with the per-region rect manifest at the top
    of each train-model's LCD module.

    Restores the previous clip rect on exit (nested clips work correctly).
    """
    old = surface.get_clip()
    surface.set_clip(rect)
    try:
        yield
    finally:
        surface.set_clip(old)


# =============================================================================
# JR East logo — vector primitive (through-service frame-swap restart screen)
#
# The single closed path from JR_logo_(east).svg (viewBox 300×162.6), rendered
# as a flattened-bezier filled polygon rather than a rasterized asset: no
# SDL-image SVG runtime dependency, no committed binary to ship/copy, scales
# clean at any size. Path flattened + bbox-normalized once, cached.
# =============================================================================

_JR_LOGO_PATH = (
    "M-249,264.4h40.8v49.7c0,11.1,27.8,11.5,34.1,11.5c6.3,0,41.6-0.4,41.6-14.5"
    "V199.5H19c27.1,0,32,38.7,32,48.6c0,9.5-4.5,52-29.7,52H5.5L51,357.4H-0.1"
    "l-74-92.9H2.7c8.9,0,9.3-12.2,9.3-14.8c0-2.6-0.4-13.4-8.9-13.4h-95.4v82.4"
    "c0,36.4-57.2,43.4-78.7,43.4c-29.7,0-78-10-78-40.8L-249,264.4"
)
_JR_LOGO_GREEN = (10, 140, 13)  # SVG fill #0A8C0D
_jr_logo_norm_cache: List[Tuple[float, float]] = []


def _flatten_svg_path(d: str, steps: int = 24) -> List[Tuple[float, float]]:
    """Flatten an SVG path (M/L/l/H/h/V/v/C/c/Z subset) to a polygon point list.

    Cubic beziers are sampled at ``steps`` segments. Sufficient for the static
    JR logo path; not a general-purpose SVG parser (only the commands that path
    uses are handled).
    """
    toks = re.findall(r"[MmHhVvCcLlZz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    i, cur, start, poly = 0, (0.0, 0.0), (0.0, 0.0), []

    def num() -> float:
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def cubic(p0, p1, p2, p3):
        for s in range(1, steps + 1):
            t = s / steps
            u = 1 - t
            x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
            y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
            poly.append((x, y))

    while i < len(toks):
        c = toks[i]
        i += 1
        if c == "M":
            cur = (num(), num())
            start = cur
            poly.append(cur)
        elif c == "L":
            cur = (num(), num())
            poly.append(cur)
        elif c == "l":
            cur = (cur[0] + num(), cur[1] + num())
            poly.append(cur)
        elif c == "H":
            cur = (num(), cur[1])
            poly.append(cur)
        elif c == "h":
            cur = (cur[0] + num(), cur[1])
            poly.append(cur)
        elif c == "V":
            cur = (cur[0], num())
            poly.append(cur)
        elif c == "v":
            cur = (cur[0], cur[1] + num())
            poly.append(cur)
        elif c == "C":
            p1, p2, p3 = (num(), num()), (num(), num()), (num(), num())
            cubic(cur, p1, p2, p3)
            cur = p3
        elif c == "c":
            p1 = (cur[0] + num(), cur[1] + num())
            p2 = (cur[0] + num(), cur[1] + num())
            p3 = (cur[0] + num(), cur[1] + num())
            cubic(cur, p1, p2, p3)
            cur = p3
        elif c in "Zz":
            cur = start
    return poly


def _jr_logo_norm() -> List[Tuple[float, float]]:
    """Bbox-normalized (0..1) JR logo polygon, built once and cached."""
    global _jr_logo_norm_cache
    if not _jr_logo_norm_cache:
        poly = _flatten_svg_path(_JR_LOGO_PATH)
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        minx, miny = min(xs), min(ys)
        w, h = max(xs) - minx, max(ys) - miny
        _jr_logo_norm_cache = [((x - minx) / w, (y - miny) / h) for x, y in poly]
    return _jr_logo_norm_cache


# Logo aspect ratio (width / height) from the 300×162.6 viewBox.
JR_LOGO_ASPECT = 300.0 / 162.6


def draw_jr_logo(screen, center_x: float, center_y: float, height: float, color=_JR_LOGO_GREEN) -> None:
    """Draw the JR East logo (green) centered at (center_x, center_y), sized to
    ``height`` px (width follows JR_LOGO_ASPECT). Anti-aliased filled polygon."""
    norm = _jr_logo_norm()
    width = height * JR_LOGO_ASPECT
    left, top = center_x - width / 2.0, center_y - height / 2.0
    pts = [(int(round(left + nx * width)), int(round(top + ny * height))) for nx, ny in norm]
    pygame.gfxdraw.filled_polygon(screen, pts, color)
    pygame.gfxdraw.aapolygon(screen, pts, color)


def draw_aapolygon(
    surface: pygame.Surface,
    color: Tuple[int, int, int],
    points: List[Tuple[float, float]],
    scale: int = 2,
    width: int = 0,
) -> None:
    """Draw antialiased polygon using supersampling.

    Args:
        surface: Pygame surface to draw on
        color: RGB color tuple
        points: List of (x, y) tuples defining the polygon
        scale: Supersampling scale factor
        width: Line width (0 for filled polygon)
    """
    x_coords = tuple(int(x) for x, _ in points)
    y_coords = tuple(int(y) for _, y in points)
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    w = x_max - x_min + 1
    h = y_max - y_min + 1

    s = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA, surface)
    s.fill((255, 255, 255, 0))
    s_points = [((int(x) - x_min) * scale, (int(y) - y_min) * scale) for x, y in points]
    pygame.draw.polygon(s, color, s_points, width)
    s2 = pygame.transform.smoothscale(s, (w, h))
    surface.blit(s2, (x_min, y_min))


def arrow_points(x: int, y: int, w: int, h: int, stroke: int) -> Tuple[Tuple[float, float], ...]:
    """Generate a 6-point chevron-arrow polygon (right-pointing).

    The result describes a horizontally-pointing chevron: a thick "<" with
    the tip at (x + w, y + h/2) and a notch carved into its left edge at
    (x + w - stroke, y + h/2). The notch makes the shape readable as an
    arrow rather than a triangle — the deeper the notch, the more the
    chevron looks like an arrowhead-with-tail.

    Geometry knobs:
        w  — total width (left edge to tip).
        h  — total height (top edge to bottom edge).
        stroke — chevron BODY THICKNESS, **not** a typical line stroke.
            Geometrically, `stroke` is the horizontal distance from the
            outer-left edge of the body to where the slanted side begins
            (and equivalently from the notch vertex to the tip).
            - stroke == w / 2: notch is exactly centered → "fat" chevron,
              equal-width body and tip portions.
            - stroke ~ w * 0.55: full-route-pointer ratio; body slightly
              wider than the tip portion.
            - small stroke (e.g. w * 0.3): pointier, longer-tip arrow.
            - stroke == w: degenerates to a thin line (no inside).
            - stroke == 0: pure right-pointing triangle (no notch).

    Scaling tips: to make the chevron larger WITHOUT changing its shape,
    scale `w`, `h`, and `stroke` by the same factor. Bumping only `w`
    makes the tip protrude → the chevron looks pointier even though it
    got "bigger".

    **Drawing a chevron with a uniform halo (filled inner + outline outer).**
    Common pattern: render an inner filled chevron in the foreground color,
    then a slightly larger outer chevron as an outline (`draw_aapolygon`
    with `width > 0`) for a halo behind it. For the halo to read as the
    same thickness along the body AND the tip, the outer's tip-length
    must equal the inner's tip-length, i.e.
        outer_w - outer_stroke == inner_w - inner_stroke
    The simplest way to achieve this — and to keep the halo uniform on
    every side — is:
        delta = halo width  # halo thickness in px
        outer_w      = inner_w      + delta
        outer_stroke = inner_stroke + delta
        outer_x      = inner_x - delta // 2  # centers outer around inner
    A common pitfall: scaling `outer_w` by some delta but using a fixed
    `outer_stroke` (or scaling stroke by a different delta). The body
    halo will look right but the tip halo will read as a different
    thickness — visible as the outline being more or less pointy than
    the inner fill.

    Args:
        x, y: Top-left of the chevron's bounding box.
        w, h: Bounding-box width and height.
        stroke: Body thickness — see notes above.

    Returns:
        Tuple of 6 (x, y) points suitable for `draw_aapolygon` (filled
        polygon when `width=0`, outline-only chevron when `width>0`).
    """
    return ((x, y), (x + w - stroke, y + h / 2), (x, y + h), (x + stroke, y + h), (x + w, y + h / 2), (x + stroke, y))


def draw_1col_text(
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    vert_space: int,
    text_color: Tuple[int, int, int],
    screen: pygame.Surface,
) -> None:
    """Draw text vertically (one column).

    Per-character horizontal centering: narrow glyphs (digits, katakana like
    ビル) are centered relative to the widest character's column width so
    mixed strings like "空港第2ビル" don't have stragglers off to the left.

    Args:
        font: Pygame font object
        text: Text to draw vertically
        x: X position (left edge of the column for the WIDEST char)
        y: Y position (bottom of the column)
        vert_space: Vertical space to fill
        text_color: RGB color tuple
        screen: Pygame surface to draw on
    """
    _, t_h = font.size(text)
    length = len(text)

    if length <= 0:
        return

    # Handle division by zero
    vert_dist = (vert_space - t_h) / (length - 1) if length > 1 else 20
    vr = 1.0

    if length * t_h > vert_space:
        vr = vert_space / (length * t_h)
        vert_dist = vert_dist + (t_h - (t_h * vr)) / (length - 1) if length > 1 else vert_dist

    char_widths = [font.size(c)[0] for c in text]
    col_w = max(char_widths)

    for k, s in enumerate(text):
        y_pos = y - vert_space + vert_dist * k
        char_w = char_widths[k]
        x_pos = x + (col_w - char_w) // 2
        img = draw_text(s, font, text_color, int(x_pos), int(y_pos), v_ratio=vr)
        screen.blit(img, (int(x_pos), int(y_pos)))


def draw_1col_text_plain(
    font: pygame.font.Font,
    text: str,
    x: int,
    top_y: int,
    text_color: Tuple[int, int, int],
    screen: pygame.Surface,
    line_gap: int = 0,
) -> int:
    """Draw text vertically (one column), tight stacking, no compression / distribution.

    Sibling of ``draw_1col_text``. Each character renders at the font's natural
    height (``font.get_height()``); pitch = ``font.get_height() + line_gap``
    so chars stack from ``top_y`` downward with optional ``line_gap`` of extra
    pixels between them. No fitting to a vert_space, no per-char compression.
    Long strings overflow rather than squish.

    Per-char horizontal centering: narrow glyphs (digits, small katakana like
    ゲ ー) are centered relative to the widest character's column width so
    mixed strings don't drift left of their column.

    Args:
        font: Pygame font object
        text: Text to draw vertically
        x: X position (left edge of the column for the WIDEST char)
        top_y: Y position (TOP of the column — chars stack downward from here)
        text_color: RGB color tuple
        screen: Pygame surface to draw on
        line_gap: Extra pixels between adjacent characters (default 0 = touching).

    Returns:
        Y-coordinate immediately after the last character.
    """
    if not text:
        return top_y

    line_pitch = font.get_height() + line_gap
    char_widths = [font.size(c)[0] for c in text]
    col_w = max(char_widths)

    for i, c in enumerate(text):
        ch_img = font.render(c, True, text_color)
        ch_x = x + (col_w - char_widths[i]) // 2
        ch_y = top_y + i * line_pitch
        screen.blit(ch_img, (ch_x, ch_y))

    return top_y + len(text) * line_pitch


def draw_stops_text(
    font: pygame.font.Font,
    stop_text: str,
    text_color: Tuple[int, int, int],
    x: int,
    y: int,
    stops_w: int,
    screen: pygame.Surface,
) -> None:
    """Draw station name text with support for multi-line stations.

    Args:
        font: Pygame font object
        stop_text: Station name (may contain space for line break)
        text_color: RGB color tuple
        x: X position
        y: Y position
        stops_w: Width of the station box
        screen: Pygame surface to draw on
    """
    t = stop_text.split()
    _, t_h = font.size(stop_text)
    w = stops_w

    if len(t) > 1:
        r_col_offset = 10
        offset = (w - t_h * 2) / 2
        draw_1col_text(font, t[0], int(x + offset + t_h), int(y - 6), 74, text_color, screen)
        draw_1col_text(font, t[1], int(x + offset), y, 80 - r_col_offset, text_color, screen)
    else:
        offset = (w - t_h) / 2
        if len(t[0]) == 1:
            draw_1col_text(font, t[0], int(x + offset), y, 48, text_color, screen)
        else:
            draw_1col_text(font, t[0], int(x + offset), y, 80, text_color, screen)


# =============================================================================
# Display-domain helpers
# =============================================================================


def draw_continuity_arrow(
    screen: pygame.Surface,
    x: int,
    y: int,
    h: int,
    color,
    *,
    n_chevrons: int = 3,
    chevron_w: int = 7,
    chevron_stroke: int = 4,
    chevron_gap: int = 0,
) -> int:
    """Stack of right-pointing chevrons signaling "route continues."

    Used at slots 0 / 2 (line-tail "to" indicator) and slot 1 (line-head
    "from" indicator) when the route has stops outside the visible display
    area. Chevrons render at the full bar height `h`. Returns total width
    consumed so callers can chain.
    """
    step = chevron_w + chevron_gap
    for i in range(n_chevrons):
        cx = x + i * step
        draw_aapolygon(
            screen,
            color,
            arrow_points(int(cx), int(y), chevron_w, h, chevron_stroke),
        )
    return n_chevrons * chevron_w + (n_chevrons - 1) * chevron_gap


def draw_continuity_triangle(
    screen: pygame.Surface,
    x: int,
    y: int,
    h: int,
    color,
    *,
    tri_w: int = 12,
) -> int:
    """Right-pointing triangle for slots 0 / 2 — bar tail (route continues).

    Used as the bar's tapered RIGHT tail (apex right, base on the left at the
    bar's right edge). (x, y) is the top-left of the triangle's bounding rect.
    Returns `tri_w`. (Slot 1's left-head notch is drawn inline in lower_lcd.py
    as a WHITE_BG triangle carved INTO the bar; it doesn't go through this
    helper.)
    """
    points = [
        (x, y),
        (x, y + h),
        (x + tri_w, y + h // 2),
    ]
    draw_aapolygon(screen, color, points)
    return tri_w


# Boilerplate route-map disclaimer — same text on both full-route and
# 8-station views, anchored bottom-right. Source: real PIDS reference.
ROUTE_DISCLAIMER = "のりかえ、待合せ時間は含まれません。電車により多少時間が異なります。一部区間では時間を表示しません。"
EN_ROUTE_DISCLAIMER = "Transfer and waiting times are not included. Times may differ by train. In the part of journey, time is not shown."


def draw_route_disclaimer(
    screen: pygame.Surface,
    font: pygame.font.Font,
    right_x: int,
    bottom_y: int,
    color,
    text: str | None = None,
) -> None:
    """Render the route-map disclaimer right- and bottom-anchored to (right_x, bottom_y)."""
    if text is None:
        text = ROUTE_DISCLAIMER
    img = font.render(text, True, color)
    w, h = img.get_size()
    screen.blit(img, (right_x - w, bottom_y - h))


def draw_station_code_badge(
    screen: pygame.Surface,
    x: int,
    y: int,
    w: int,
    h: int,
    sta_code: str,
    color,
    *,
    prefix_size: float,
    num_size: float,
    code_3: str = "",
    code_3_size: float = 20,
    text_color=BADGE_TEXT,
    ring_black: int = 7,
    ring_color: int = 7,
    outer_radius: int = 8,
    color_radius: int = 4,
    interior_radius: int = 0,
    text_gap: int = 3,
    text_y_offset: int = 0,
    prefix_x_offset: int = 1,
    code_3_band_h: int = 12,
    code_3_x_offset: int = 0,
    code_3_y_offset: int = 4,
) -> None:
    """Draw the framed station-code badge (e.g. JO25, JY03, or line-only "JO").

    The (x, y, w, h) rect describes the **framed JY/03 portion only** — the
    optional `code_3` 3-letter top band, when present, is drawn above the
    framed square (the outer black rect extends upward by `code_3_band_h`).

    Layered as: outer black → route-color ring → white interior → letters
    centered horizontally with `prefix_x_offset` nudge → number row below
    separated by `text_gap` (visible-pixel gap, measured via
    `get_bounding_rect`).

    `sta_code` may be letters+digits (`JY03`) or letters-only (`JY` — used
    by the route selection screen as a line marker without station number,
    in which case the letters are vertically centered with no number row).

    Returns silently if `sta_code` cannot be parsed into letters [+ digits].
    Used by upper-LCD (large badge with optional code_3 band), the lower-LCD
    8-station view (smaller per-cell badge, no code_3 band), and the setup
    screen (line-marker mode, letters only).

    The typeface is fixed (NeueFrutigerWorld-Bold, the JR signage face) — see
    `_badge_font`. Callers control only the point sizes (`prefix_size`,
    `num_size`, `code_3_size`), which scale per badge.
    """
    m = re.match(r"([A-Za-z]+)(\d*)", sta_code or "")
    if not m:
        return
    letters = m.group(1).upper()
    number = m.group(2)  # may be empty (line-marker mode)

    font_prefix = _badge_font(prefix_size)
    font_num = _badge_font(num_size)

    inset = ring_black + ring_color
    interior_x = x + inset
    interior_y = y + inset
    interior_w = w - 2 * inset
    interior_h = h - 2 * inset
    center_x = interior_x + interior_w // 2

    if code_3:
        outer_y = y - code_3_band_h
        outer_h = h + code_3_band_h
    else:
        outer_y = y
        outer_h = h

    pygame.draw.rect(screen, (0, 0, 0), pygame.Rect(x, outer_y, w, outer_h), 0, outer_radius)
    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(x + ring_black, y + ring_black, w - 2 * ring_black, h - 2 * ring_black),
        0,
        color_radius,
    )
    pygame.draw.rect(screen, WHITE_BG, pygame.Rect(interior_x, interior_y, interior_w, interior_h), 0, interior_radius)

    letter_surf = font_prefix.render(letters, True, text_color)
    l_rect = letter_surf.get_bounding_rect()

    if number:
        num_surf = font_num.render(number, True, text_color)
        n_rect = num_surf.get_bounding_rect()
        total_h = l_rect.height + text_gap + n_rect.height
    else:
        total_h = l_rect.height

    start_y = interior_y + (interior_h - total_h) // 2 + text_y_offset
    screen.blit(letter_surf, (center_x + prefix_x_offset - l_rect.width // 2 - l_rect.x, start_y - l_rect.y))

    if number:
        num_y = start_y + l_rect.height + text_gap
        screen.blit(num_surf, (center_x - n_rect.width // 2 - n_rect.x, num_y - n_rect.y))

    if code_3:
        code_3_surf = _badge_font(code_3_size).render(code_3, True, WHITE_BG)
        c_rect = code_3_surf.get_bounding_rect()
        band_center_x = x + w // 2
        band_center_y = outer_y + code_3_band_h // 2
        code_3_x = band_center_x + code_3_x_offset - c_rect.width // 2 - c_rect.x
        code_3_y = band_center_y + code_3_y_offset - c_rect.height // 2 - c_rect.y
        screen.blit(code_3_surf, (code_3_x, code_3_y))


def draw_text(
    text: str,
    font: pygame.font.Font,
    color: tuple,
    x: int,
    y: int,
    bg: tuple = None,
    h_ratio: float = 1.0,
    v_ratio: float = 1.0,
) -> pygame.Surface:
    """Draw text with optional scaling."""
    if bg is None:
        img = font.render(text, True, color).convert_alpha()
        txt_w, txt_h = img.get_size()
        if h_ratio != 1.0 or v_ratio != 1.0:
            img = pygame.transform.smoothscale(img, (int(txt_w * h_ratio), int(txt_h * v_ratio)))
    else:
        img = font.render(text, True, color, bg)
    return img


def draw_text_given_width(
    x: int,
    y: int,
    width: int,
    font: pygame.font.Font,
    text: str,
    color: tuple,
    screen: pygame.Surface,
    collapse: bool = False,
    script: str = "japanese",
) -> None:
    """Draw text constrained to a specific width, compressing if needed.

    Args:
        x, y: Position
        width: Maximum width for the text
        font: Pygame font object
        text: Text to draw
        color: RGB color tuple
        screen: Pygame surface to draw on
        collapse: If True, render as single centered text (for Latin scripts)
        script: 'latin' for proportional fonts (preserves kerning),
                'japanese' for monospaced square characters
    """
    for offset, img in font_atlas.text_parts(compose_text_parts, font, text, color, width, collapse, script):
        screen.blit(img, (x + offset, y))


def compose_text_parts(font, text, color, width, collapse=False, script="japanese"):
    """Lay `text` out. THE layout implementation.

    Returns `[(offset_from_x, surface), ...]` — the parts the caller blits, in
    order. Deliberately NOT flattened into one surface: the compression branch
    can place adjacent characters a pixel apart from their scaled widths, and
    flattening an overlap onto transparency then blitting the result differs from
    blitting each part onto the background in turn. Measured: 90 differing pixels
    across 36 frames. Handing back the parts keeps the blit sequence identical to
    what it has always been, so storing them in an atlas is exact by
    construction instead of by measurement.

    # CONTRACT: this is the only place LCD text layout exists, and the font
    # atlas stores this function's OUTPUT. Nothing may re-derive the spacing, the
    # compression ratio, or the collapse branch elsewhere — not a baker, not a
    # test, not a proof script. A second implementation drifts silently, and the
    # drift renders as correct-looking text at the wrong spacing.
    # See docs/wip/WIP_font_atlas.md.

    Offsets are integers in every branch, so pulling x out of the original
    `int(x + sep * i)` and adding it back at blit time is exact, not approximate:
    x is a non-negative int, and `int(x + f) == x + int(f)` for such x.
    """
    t_w, t_h = font.size(text)
    t_w_s = t_w // len(text) if len(text) > 0 else 0

    # Each branch produces (offset_from_x, surface) pairs; they are then packed
    # into one surface below. Same arithmetic as when this blitted to the screen
    # directly — only the destination changed.
    parts = []

    if script == "latin":
        # Latin script: render full string centered, scale if needed
        if t_w > width:
            h_ratio = width / t_w
            img = draw_text(text, font, color, 0, 0, h_ratio=h_ratio)
            scaled_w = int(t_w * h_ratio)
            parts.append(((width - scaled_w) // 2, img))
        else:
            img = draw_text(text, font, color, 0, 0)
            parts.append(((width - t_w) // 2, img))
    elif t_w > width:
        # Japanese text too wide - compress character by character
        sep = width / len(text)
        hr = width / (len(text) * t_w_s) if t_w_s > 0 else 1.0
        for i, char in enumerate(text):
            img = draw_text(char, font, color, 0, 0, h_ratio=hr)
            parts.append((int(sep * i), img))
    elif collapse:
        # Collapse mode for Japanese: render full text centered
        img = draw_text(text, font, color, 0, 0)
        parts.append(((width - t_w) // 2, img))
    else:
        # Japanese text fits - add even spacing between characters.
        # Per-char measured widths (not uniform stride) — handles mixed-width
        # text like compound dests `品川･東京` where `･` (U+FF65) is halfwidth.
        # Uniform-width inputs (every other Japanese render) produce identical
        # output because their per-char widths all equal the previous t_w_s.
        char_widths = [font.size(c)[0] for c in text]
        sep = (width - t_w) // (len(text) + 1)
        exp = 7 if len(text) == 2 else 0
        cumulative = 0
        for i, char in enumerate(text):
            parts.append((sep * (i + 1) + cumulative + (exp if i > 0 else -exp), draw_text(char, font, color, 0, 0)))
            cumulative += char_widths[i]

    return [(off, img) for off, img in parts if img.get_width() and img.get_height()]

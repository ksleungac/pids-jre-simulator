# SPDX-License-Identifier: MIT
"""E233-0 manner-mode (マナーモード) page — the lower LCD's mobile-phone notice.

A pictogram panel on the left, and a right-hand column carrying the request in
Japanese over the same request in smaller English. Static: the content depends
on neither the route nor the stop.

THE REFERENCE. `_references/lcd/e233_0/manner-mode.png` — 快速 東京行 at 阿佐ケ谷,
つぎは, 7:01, car 10; 1273 x 953, so 2.0x the 640 x 480 canvas. This page was
first written against a brief stating no reference existed, and every number in
it was authored; the file was then found in the references folder and every
number was replaced by a measurement of it. Values below carry `[measured]`
only where that is literally true, on the same terms as the rest of this model.

The page is NOT in `docs/wip/WIP_e233_0_display.md` § 3's view inventory and has
had no drill-down, so what follows is a measurement, not a settled spec. Two
things the author still has to rule on are named at their tuneables: the English
point size, whose width fit and height fit disagree by 6%, and the panel's
border, which is a sub-pixel rule on a 2x upscale.

THE PICTOGRAM IS AN ORIGINAL RENDITION, DRAWN FROM MEASUREMENT. It depicts a
JR East design — a handset carrying マナーモード with 通話 struck through — whose
rights are JR East's. Nothing here is imported: there is no PNG, no SVG, no
asset file of any kind. Every shape is a pygame primitive placed from figures
read off the reference with `_dev_scripts/_e233_lower_geometry.py`, so what
ships is our own drawing of the same subject rather than a copy of theirs, and
no third-party file enters the tree. See `THIRD-PARTY.md` for how asset classes
are inventoried; this element adds none.

WHAT THE PICTOGRAM IS MADE OF, all measured in canvas units:

  * a grey rounded plate inset in the white panel — the drawing's own field;
  * a white handset, a rounded rect tilted 45 degrees with its top at the upper
    right, carrying a screen in the same grey and a short antenna at its
    top-right corner;
  * four pairs of concentric sound arcs, ONE AT EACH CORNER of the handset,
    each opening along a SCREEN axis (up / right / down / left) rather than
    along the corner's own diagonal. The two on the plate are drawn white; the
    two that fall on the white margin outside it are drawn in the plate's grey,
    which is what the reference does and the only way they are visible there;
  * マナー in red along the handset, モード smaller beside it, both reading up
    and to the right at the handset's own angle;
  * 通話 in white at the lower right, struck through by a red X — two arms, not
    the single diagonal it reads as at 1x.

WHAT THE MEASUREMENT SETTLED, against the guesses it replaced:

  * The page carries ONE request, not two. There is no priority-seat clause on
    it — that notice is its own page, with its own reference
    (`priority-seats.png`) and its own renderer (`priority_seat.py`).
  * The Japanese does not name the phone: 「マナーモードに設定の上、」, not
    「携帯電話はマナーモードに設定の上、」.
  * The text is LEFT-ALIGNED in a right-hand column, not centred on the canvas
    the way the priority-seat page is.
  * `to silent  mode` really does carry two spaces. It reads as a typo and is in
    the artifact: the gap measures 16.1px against 9.0 / 9.6 / 10.1 for the other
    three word gaps on that line, i.e. one extra space advance almost exactly.
    Do not "fix" it — it is what the display shows.

STATIC. `route_data`, `stops`, `state` and `current_time` are all accepted and
unused: the signature exists so the manager constructs and drives this view
exactly as it does the others.

NOT WIRED. This module is the page only. The slot that shows it, its dwell and
its place in the rotation belong to `LowerDisplay` and are not touched here.
"""

import math

import pygame

from displays.train_models.e233_0 import LOWER_BG, S_HEIGHT, S_WIDTH, UPPER_HEIGHT
from font_atlas import lcd_font, lit

_JA_FACE = "ShinGoPro-DeBold.otf"
_EN_FACE = "HelveticaNeue-Medium.otf"

# The pictogram is composed at this multiple of the canvas and resolved down
# ONCE, so every edge in it — the plate's corners, the tilted handset, the arcs,
# the rotated red text — is antialiased by the same resample rather than by four
# different ones. AUTHORED: 4 is the smallest factor that also carries every
# text size on this page above the 48px floor `upper_lcd._CELL_MIN_RENDER`
# documents, below which ShinGo glyphs clip against their own render surface.
# The surface is drawn OPAQUE (it starts as the panel's white), so the resample
# never averages alpha and no edge can pick up a fringe — the failure
# `displays/utils.draw_aapolygon` carries its own note about.
_PICT_SS = 4

# fmt: off
_TUNEABLES_MANNER_MODE = {
    # ---- the text ---------------------------------------------------------
    # TRANSCRIBED from the reference, and the ONLY place it is written. The line
    # breaks are the reference's own — five ink bands, two Japanese and three
    # English — so nothing here wraps at draw time. That is also what keeps the
    # atlas declaration below honest: `_DRAWS` reads these tuples, so a string
    # cannot be drawn that was not declared.
    #
    # The two spaces in `to silent  mode` are deliberate — see the docstring.
    "ja_lines":  (
        "マナーモードに設定の上、",
        "通話はご遠慮ください。",
    ),
    "en_lines":  (
        "Please set your mobile phone",
        "to silent  mode and refrain",
        "from talking on the phone.",
    ),
    # ---- the pictogram panel ----------------------------------------------
    # [measured] as the near-white run inside the lower region: x 40.7..232.2,
    # y 216.6..383.3 in canvas units. This is the FILL; the border sits just
    # outside it, which is why it is given as a width rather than as a second
    # rect — inflating one rect keeps the two from drifting apart.
    #
    "panel_x":       40.7,
    "panel_y":      216.6,
    "panel_w":      191.5,
    "panel_h":      166.7,
    "panel_color":  (255, 255, 255),  # fill sampled (255,253,252) — white
                                      # within the capture's own drift
    # [measured] by walking OUT of the fill on all four sides: white, then two
    # reference pixels of a neutral dark grey, then the background. The samples
    # run (110,119,133) / (106,113,120) / (112,114,115) / (116,119,123), mean
    # (111,116,123). NOT `RULE_GREY` (135,145,165), which is blue-tinted and
    # lighter — this is its own colour.
    #
    # PROVISIONAL. Two reference pixels is one canvas pixel, and a 1px rule on a
    # 2x upscale reads lighter than it is, because the upscale averages it with
    # the white and the background either side. So the true colour is at most
    # this dark and probably darker, and the width is at most this wide. The
    # author's eye settles both.
    "panel_border_color":  (111, 116, 123),
    "panel_border_w":       1.0,
    # ---- the pictogram: the grey plate -------------------------------------
    # The drawing's own field, inset in the white panel. [measured] as the run
    # that is neither white nor the panel border, read on strips clear of the
    # sound arcs — the first attempt took the panel-wide extent and came back
    # 12px too tall at the top and 16 too short at the bottom, because the arcs
    # above and below the plate are grey too and sit on the white margin.
    #
    # The insets are NOT symmetric — 6.3 left, 5.7 right, 14.7 top, 23.1 bottom
    # — and they are kept as measured rather than centred. The handset's top and
    # bottom corners fall outside the plate, on the white margin, where a white
    # shape is invisible; the extra vertical margin is the room that costs.
    "plate_x":       47.0,   # [measured]
    "plate_y":      231.3,   # [measured]
    "plate_w":      179.5,   # [measured]
    "plate_h":      128.9,   # [measured]
    "plate_radius":   5.0,   # [measured] the top-left corner walks 4.3px in
                             # over 5 rows before the edge goes straight
    # [measured] (132,129,119), sampled at four places inside the plate; a warm
    # grey, NOT the blue-tinted RULE_GREY. The handset's SCREEN samples the same
    # value to within the capture's own drift, so the two share this one key
    # rather than carrying a colour each that would then drift apart.
    "plate_color":  (132, 129, 119),
    # ---- the pictogram: the handset ---------------------------------------
    # A rounded rect, tilted, drawn WHITE. Everything about it is [measured] by
    # fitting straight lines to its four visible edges rather than by reading a
    # bounding box: the shape is rotated, so its bbox is a function of the angle
    # and tells you neither dimension. Both long sides came out at dx/dy -0.99
    # and -1.00 and the top end edge at +1.00 over baselines of 60-95px, which
    # is what makes 45 degrees a reading rather than a guess.
    #
    # The centre lands on the plate's own centre (136.75, 295.75) to within half
    # a pixel. Kept as the measured (136.3, 295.6) rather than snapped to it —
    # one capture cannot say which of the two is the drawing and which is the
    # crop, and this is the same call `banner_cx` makes in `transfer_info.py`.
    "phone_x":      136.3,   # [measured] body centre
    "phone_y":      295.6,   # [measured]
    "phone_w":       56.9,   # [measured] across the body
    "phone_h":      149.3,   # [measured] along it, cap to cap
    "phone_radius":   4.8,   # [measured] from how far the leftmost point of the
                             # bottom-left corner sits inside the sharp corner
    "phone_angle":   45.0,   # [measured] degrees CLOCKWISE — top to the right
    "phone_color":  (255, 254, 250),  # [measured]
    # The screen, in the plate's grey. Placed along the body rather than in
    # canvas x/y: `_v` is the offset from the body centre toward the TOP (so it
    # is negative), `_u` would be the offset across it and is zero — the screen
    # is centred on the body's axis to within a fifth of a pixel.
    "screen_w":      42.3,   # [measured]
    "screen_h":      49.3,   # [measured]
    "screen_v":     -33.2,   # [measured]
    "screen_radius":  3.6,   # [measured], same method as `phone_radius`
    # The antenna: a rounded stub at the body's top-RIGHT, running along the
    # body's own axis. That it is parallel to the body rather than splayed is
    # measured, not assumed — its centreline sits at u 17.5 / 17.7 / 18.1 on
    # three rows 6px apart, which a splayed stub could not do.
    "antenna_w":      7.1,   # [measured]
    "antenna_u":     17.8,   # [measured] across the body from its axis
    "antenna_v":    -93.9,   # [measured] the tip, from the body centre
    "antenna_root_v": -66.0,  # AUTHORED — where the stub is cut off inside the
                              # body. Invisible (white on white); it only has to
                              # sit far enough in that the two never part.
    # ---- the pictogram: the sound arcs ------------------------------------
    # Four pairs of concentric arcs, one pair at each corner of the handset.
    # The right and left pairs land on their corners to within a pixel; the top
    # and bottom pairs sit ~5px further in, and are recorded where they measure
    # rather than snapped onto the corners, because those two are the pairs
    # drawn grey on the white margin where the reading is weakest.
    #
    # Each pair opens along a SCREEN axis — the right pair is symmetric about a
    # horizontal, the top pair about a vertical — NOT along its corner's own
    # 45-degree diagonal. Checked on the right pair, whose three extreme points
    # are collinear-with-the-horizontal to a fifth of a pixel.
    "arc_top_x":     168.0,  # [measured] — up
    "arc_top_y":     229.7,
    "arc_right_x":   208.7,  # [measured] — right
    "arc_right_y":   263.2,
    "arc_bottom_x":  103.4,  # [measured] — down
    "arc_bottom_y":  363.5,
    "arc_left_x":     64.3,  # [measured] — left
    "arc_left_y":    327.8,
    "arc_r_inner":     6.5,  # [measured] four apexes agree within 1.0px
    "arc_r_outer":    12.5,  # [measured] fitted per pair at 10.2 / 12.3 / 15.6
                             # / 17.2 — a 2px stroke on a 2x upscale is the
                             # noise floor, so this is their middle
    "arc_stroke":      2.4,  # [measured]
    "arc_span_outer":  88.0,  # [measured] degrees subtended: 40.9 / 42.8 /
                              # 44.7 / 46.4 half-angles
    "arc_span_inner": 110.0,  # [measured] the inner arcs really do subtend
                              # MORE than the outer ones — 51 / 54.6 / 57.8 / 74
                              # half-angles. Widest spread of any figure here
    # ---- the pictogram: マナー / モード ------------------------------------
    # Both runs read up and to the right at the handset's angle, and both are
    # placed by their INK CENTRE in the handset's own frame, so moving or
    # re-angling the phone carries them with it. `_u` is across the body, `_v`
    # along it toward the bottom. The two sit at the same `_v` and differ only
    # across — モード is beside マナー, not below it.
    "manner_text":  "マナー",
    "manner_size":     23,
    "manner_u":      -8.8,   # [measured]
    "manner_v":      32.0,   # [measured]
    "mode_text":    "モード",
    "mode_size":       12,
    "mode_u":        14.0,   # [measured]
    "mode_v":        31.5,   # [measured]
    # [measured] (233,51,36), the same core value in マナー and in the strike, so
    # they share one key.
    "pict_red":  (233, 51, 36),
    # ---- the pictogram: 通話 and its strike --------------------------------
    # 通話 is drawn flat, not along the handset. Placed by its INK left/top.
    "call_text":    "通話",
    "call_size":       26,
    "call_ink_x":   163.9,   # [measured]
    "call_ink_y":   326.8,   # [measured]
    "call_color":  (255, 252, 250),  # [measured]
    # The strike is an X — TWO arms. At 1x it reads as one diagonal, and the
    # reference resolves into two the moment it is measured: the red narrows to
    # a 5.5px waist at y 337.8 and opens back out below it.
    #
    # `_w` / `_h` span the arms' CENTRELINES, which is 2.7 x 1.7 inside the
    # measured red bbox (54.3 x 33.1) — the difference is the stroke's own half
    # width carried past each tip.
    "strike_x":     190.6,   # [measured] centre
    "strike_y":     337.9,   # [measured]
    "strike_w":      51.6,   # [measured]
    "strike_h":      31.4,   # [measured]
    "strike_stroke":  3.2,   # [measured] perpendicular, off the arm's own
                             # 6.0px horizontal chord
    # ---- the text column --------------------------------------------------
    # x is a PEN origin, not an ink edge: the surface is blitted at it and the
    # face's own left side bearing does the rest. That is the model the
    # measurement validated rather than an assumption — the implied pen x came
    # out 279.5 on BOTH Japanese lines (マ and 通, different bearings) and
    # 282.1 / 282.0 / 282.0 on the three English ones (P, t, f). Five lines
    # agreeing to a fifth of a pixel within each face means our bearings match
    # the reference's, so one number per face reproduces all five ink edges.
    #
    # TWO NUMBERS, NOT ONE. The faces disagree by 2.5px and there is no reading
    # that says which — if any — is the designer's single axis. Both are
    # measured; collapsing them to a compromise would put both 1.3px wrong to
    # express a symmetry the reference does not assert.
    "ja_left_x":     279.5,  # [measured]
    "en_left_x":     282.0,  # [measured]
    # y is an INK TOP. ShinGo and HelveticaNeue carry different internal
    # leading, so two groups placed by their font BOXES sit at gaps neither of
    # these numbers describes — the trap that put the transfer view's English
    # line on top of its Japanese one.
    "ja_ink_y":      205.5,  # [measured]
    "ja_line_pitch":  32.7,  # [measured] ink top 205.5 -> 238.2
    "en_ink_y":      318.8,  # [measured]
    "en_line_pitch":  30.25,  # [measured] ink tops 318.8 / 349.0 / 379.3. All
                              # three lines are ascender-topped, so the three
                              # tops are comparable and the two steps agree to
                              # 0.05px
    # ---- sizes ------------------------------------------------------------
    # JAPANESE IS 27, AND THE CELL PITCH IS WHY. A CJK advance IS the em, so the
    # gap between one character's ink and the next gives the size with no
    # fitting at all: the run マ ナ ー モ ー steps 27.1 / 27.1 / 27.1 / 27.4.
    # Our own render at 27 then draws the two lines 305 and 280 px wide against
    # a measured 306.2 and 281.5 — within 1.5px on both, unfitted.
    #
    # That reading is also what caught a 15% error. Fitting the size to the
    # measured ink WIDTH first gave 31.3, because the ink extent had been read
    # from a column clipped at the panel's edge and the panel's own dark border
    # overlaps every line vertically — so all five lines reported starting at
    # the panel. A width fit cannot tell a bigger font from a tracked one or
    # from a contaminated edge; a pitch can.
    "ja_size":  27,
    # ENGLISH IS 24 ON WIDTH, and its height disagrees — OPEN. The three lines
    # fit 24.48 / 24.38 / 24.29 on ink width and 25.59 / 25.52 / 26.14 on ink
    # height, so our HelveticaNeue-Medium is proportionally shorter for its
    # width than whatever the reference is set in. Width wins here because it
    # clusters across three lines of different content while the height fit
    # spreads with the ascenders and descenders each line happens to carry, and
    # because 24 is the closer of the two candidates on total width error
    # (14.6px against 23.0 over the three lines). It is still a 6% disagreement
    # that a face change, not a size change, would explain — the author's call.
    "en_size":  24,
    # ---- ink --------------------------------------------------------------
    # Black, as the sibling notice pages set it. Two keys rather than one so a
    # later pass can lift or dim one language without recolouring the page.
    "ja_color":  (0, 0, 0),
    "en_color":  (0, 0, 0),
    # Alpha at or above which a pixel counts as ink when the ink box is
    # measured. Matches the transfer and priority-seat views, so every page on
    # this model places text against the same definition of where a glyph
    # starts.
    "ink_min_alpha":  110,
}
# fmt: on

# The whole lower region — this page's hit-test and calibration-editor rect.
# Same shape as the transfer view's `TRANSFER_VIEW_RECT`.
MANNER_MODE_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)


# What this page draws, DERIVED from the dict above rather than restated beside
# it. Every string is a source literal — nothing on this page comes from
# `route.json` or from `data/` — so a `lit(...)` per group is the whole domain,
# and reading it out of the tuneables is what stops the declaration drifting
# behind an edit to the notice. (The calibration editor tunes numbers, not
# strings, so a live edit cannot desynchronise these.)
_DRAWS = {
    "ja": (_JA_FACE, lit(*_TUNEABLES_MANNER_MODE["ja_lines"])),
    "en": (_EN_FACE, lit(*_TUNEABLES_MANNER_MODE["en_lines"])),
    # The three strings inside the pictogram. Same shape as the two above — read
    # out of the tuneables, so the declaration cannot fall behind an edit to
    # them. They are drawn at `_PICT_SS` times their tuneable size, which is a
    # different atlas key from the size written here; the bake records what
    # `lcd_font` is actually asked for, so nothing extra has to be declared.
    "pict": (
        _JA_FACE,
        lit(
            _TUNEABLES_MANNER_MODE["manner_text"],
            _TUNEABLES_MANNER_MODE["mode_text"],
            _TUNEABLES_MANNER_MODE["call_text"],
        ),
    ),
}


def _rot(u: float, v: float, deg: float):
    """`(u, v)` in a frame tilted `deg` CLOCKWISE, as an offset in screen axes.

    Screen y points DOWN, which is why the ordinary rotation matrix with a
    POSITIVE angle turns clockwise here: local up `(0, -1)` at 45 degrees comes
    back as `(0.707, -0.707)`, which is up and to the right — the handset's own
    direction. Getting that sign backwards mirrors the whole pictogram, and the
    mirror image is plausible enough to survive a glance.
    """
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return u * c - v * s, u * s + v * c


def _rrect_points(cx: float, cy: float, w: float, h: float, r: float, deg: float, segs: int = 6):
    """A rounded rect's outline, tilted `deg` clockwise about `(cx, cy)`.

    Returned as a float point list for `pygame.draw.polygon` on the
    supersampled surface. `displays.utils.draw_aapolygon` is the house
    antialiased-polygon primitive and is the wrong instrument HERE: it truncates
    every vertex to a whole CANVAS pixel, which a 4.8px corner radius and a
    2.4px arc stroke cannot survive. Composing at `_PICT_SS` and resolving down
    once is the same supersampling that helper performs, applied where the
    vertices still carry their fractions.
    """
    hw, hh = w / 2.0, h / 2.0
    r = max(0.0, min(r, hw, hh))
    pts = []
    # Corner arc centres, clockwise from the top-left, each with the angle its
    # quarter STARTS at. With y down, 180 points left and 270 points up, so
    # 180 -> 270 sweeps left-to-up: the top-left corner, travelled clockwise.
    for ax, ay, a0 in (
        (-hw + r, -hh + r, 180.0),
        (hw - r, -hh + r, 270.0),
        (hw - r, hh - r, 0.0),
        (-hw + r, hh - r, 90.0),
    ):
        for k in range(segs + 1):
            a = math.radians(a0 + 90.0 * k / segs)
            du, dv = ax + r * math.cos(a), ay + r * math.sin(a)
            dx, dy = _rot(du, dv, deg)
            pts.append((cx + dx, cy + dy))
    return pts


def _arc_ring_points(cx: float, cy: float, r_in: float, r_out: float, mid_deg: float, span_deg: float, segs: int = 14):
    """One arc of the sound marks, as a closed annular-sector outline.

    Angles are screen angles with y down, so 270 is up and 0 is right. Drawn as
    a polygon rather than with `pygame.draw.arc`, whose width argument lays
    concentric circles and leaves gaps on a stroke this thin.
    """
    a0 = mid_deg - span_deg / 2.0
    outer = [math.radians(a0 + span_deg * k / segs) for k in range(segs + 1)]
    return [(cx + r_out * math.cos(a), cy + r_out * math.sin(a)) for a in outer] + [
        (cx + r_in * math.cos(a), cy + r_in * math.sin(a)) for a in reversed(outer)
    ]


class MannerModeDisplay:
    """The マナーモード notice. Static — see the module docstring."""

    def __init__(self, screen, route_data: dict, stops: list):
        self.screen = screen
        # Held, not read. The page is the same on every route and at every stop;
        # these exist so the manager can construct this view with the same call
        # it uses for the others.
        self.route_data = route_data
        self.stops = stops
        self.state = None

        self._fonts: dict = {}
        self._text_cache: dict = {}

    # ---- state ----------------------------------------------------------

    def set_state(self, state) -> None:
        """Bind AppState by reference, as the sibling views do.

        Nothing on this page reads it. The binding is kept so the manager's
        `set_state` fan-out needs no per-view exception, and so a later version
        that DOES vary has the state already in hand.
        """
        self.state = state

    # ---- fonts + ink ----------------------------------------------------

    def _font(self, group: str, size: int):
        f = self._fonts.get((group, size))
        if f is None:
            face, draws = _DRAWS[group]
            f = lcd_font(face, size, draws=draws)
            self._fonts[(group, size)] = f
        return f

    def _ink(self, group: str, size: int, text: str, color):
        """`(surface, ink_left, ink_top, ink_width)` — the render plus its ink box.

        `ink_top` is what places the line, since the tuneables are ink tops.
        `ink_left` and `ink_width` are returned for the same reason the sibling
        pages return them — they are what a measurement of our own render reads,
        so the instrument that measured the reference can ask our render the
        identical question. Cached on the drawn string: the offsets are a
        property of the glyphs rather than of the face.
        """
        key = (group, size, text)
        hit = self._text_cache.get(key)
        if hit is not None:
            return hit
        surf = self._font(group, size).render(text, True, color)
        box = surf.get_bounding_rect(min_alpha=int(_TUNEABLES_MANNER_MODE["ink_min_alpha"]))
        out = (surf, box.x, box.y, box.w)
        self._text_cache[key] = out
        return out

    # ---- drawing --------------------------------------------------------

    def _draw_panel(self) -> None:
        """The white pictogram panel — its border, then the pictogram over it.

        Border first and the panel's contents over it, so the border's width is
        measured from the OUTSIDE of the fill exactly as the reference was
        walked. Drawing the border as an outline on the fill rect instead would
        eat a pixel of the fill and shrink the measured panel by the width of
        its own rule.
        """
        t = _TUNEABLES_MANNER_MODE
        fill = self._panel_rect()
        bw = int(round(float(t["panel_border_w"])))
        if bw > 0:
            pygame.draw.rect(self.screen, tuple(t["panel_border_color"]), fill.inflate(bw * 2, bw * 2))
        self.screen.blit(self._pictogram(), fill.topleft)

    @staticmethod
    def _panel_rect() -> pygame.Rect:
        """The panel's fill rect, whole-pixel. Every pictogram coordinate is an
        offset from its top-left, so the drawing and the panel cannot part."""
        t = _TUNEABLES_MANNER_MODE
        return pygame.Rect(
            int(round(float(t["panel_x"]))),
            int(round(float(t["panel_y"]))),
            int(round(float(t["panel_w"]))),
            int(round(float(t["panel_h"]))),
        )

    # ---- the pictogram --------------------------------------------------

    def _pict_text(self, text: str, size: int, color, ccw_deg: float = 0.0):
        """One pictogram string at `_PICT_SS` scale, plus its ink box there.

        Returns `(surface, ink_rect)` in SUPERSAMPLED pixels — the caller places
        it inside the composition surface and the single resample at the end is
        what antialiases both the glyph and, for マナー / モード, the rotation.
        Rendering at 1x and rotating there would soften a 23px bold kana past
        legibility, and would also put a second resample in the path.

        Cached on the drawn string and its size, as `_ink` is: the ink offsets
        are a property of the glyphs.
        """
        key = ("pict", size, text, ccw_deg, tuple(color))
        hit = self._text_cache.get(key)
        if hit is not None:
            return hit
        surf = self._font("pict", int(size) * _PICT_SS).render(text, True, tuple(color))
        if ccw_deg:
            surf = pygame.transform.rotozoom(surf, ccw_deg, 1.0)
        box = surf.get_bounding_rect(min_alpha=int(_TUNEABLES_MANNER_MODE["ink_min_alpha"]))
        out = (surf, box)
        self._text_cache[key] = out
        return out

    def _pictogram(self) -> pygame.Surface:
        """The whole panel interior, composed at `_PICT_SS` and resolved once.

        Cached on the tuneables themselves rather than built per frame — the
        page is static, but the calibration editor mutates the dict live, so the
        cache has to key on its contents or a nudge would not show.
        """
        t = _TUNEABLES_MANNER_MODE
        key = repr(sorted(t.items()))
        hit = self._text_cache.get(("pict_surface", key))
        if hit is not None:
            return hit

        rect = self._panel_rect()
        ss = _PICT_SS
        big = pygame.Surface((rect.w * ss, rect.h * ss))
        big.fill(tuple(t["panel_color"]))

        def P(x: float, y: float):
            """A canvas point as a supersampled point inside the composition."""
            return ((x - rect.x) * ss, (y - rect.y) * ss)

        grey = tuple(t["plate_color"])
        white = tuple(t["phone_color"])

        # 1. The plate.
        pygame.draw.polygon(
            big,
            grey,
            _rrect_points(
                *P(float(t["plate_x"]) + float(t["plate_w"]) / 2.0, float(t["plate_y"]) + float(t["plate_h"]) / 2.0),
                float(t["plate_w"]) * ss,
                float(t["plate_h"]) * ss,
                float(t["plate_radius"]) * ss,
                0.0,
                segs=10,
            ),
        )

        # 2. The four sound-arc pairs. The two on the plate are white; the two
        #    on the white margin outside it are drawn in the plate's grey, which
        #    is what the reference does — a white arc there would not exist.
        r_in, r_out = float(t["arc_r_inner"]), float(t["arc_r_outer"])
        stroke = float(t["arc_stroke"])
        for group, mid_deg, color in (
            ("top", 270.0, grey),
            ("right", 0.0, white),
            ("bottom", 90.0, grey),
            ("left", 180.0, white),
        ):
            cx, cy = float(t[f"arc_{group}_x"]), float(t[f"arc_{group}_y"])
            for r, span in ((r_in, float(t["arc_span_inner"])), (r_out, float(t["arc_span_outer"]))):
                pygame.draw.polygon(
                    big,
                    color,
                    _arc_ring_points(*P(cx, cy), (r - stroke) * ss, r * ss, mid_deg, span),
                )

        # 3. The handset: antenna first so the body's edge closes over its root,
        #    then the body, then the screen.
        px, py = float(t["phone_x"]), float(t["phone_y"])
        ang = float(t["phone_angle"])

        def local(u: float, v: float):
            du, dv = _rot(u, v, ang)
            return P(px + du, py + dv)

        a_top, a_root = float(t["antenna_v"]), float(t["antenna_root_v"])
        a_w = float(t["antenna_w"])
        pygame.draw.polygon(
            big,
            white,
            _rrect_points(
                *local(float(t["antenna_u"]), (a_top + a_root) / 2.0),
                a_w * ss,
                abs(a_root - a_top) * ss,
                a_w / 2.0 * ss,
                ang,
                segs=8,
            ),
        )
        pygame.draw.polygon(
            big,
            white,
            _rrect_points(
                *local(0.0, 0.0),
                float(t["phone_w"]) * ss,
                float(t["phone_h"]) * ss,
                float(t["phone_radius"]) * ss,
                ang,
                segs=10,
            ),
        )
        pygame.draw.polygon(
            big,
            grey,
            _rrect_points(
                *local(0.0, float(t["screen_v"])),
                float(t["screen_w"]) * ss,
                float(t["screen_h"]) * ss,
                float(t["screen_radius"]) * ss,
                ang,
                segs=10,
            ),
        )

        # 4. マナー / モード, placed by their ink CENTRE in the handset's frame.
        #    Both runs read ALONG the body toward its top, so in the body's own
        #    frame they are turned a quarter turn; pygame's rotation is
        #    counter-clockwise while `phone_angle` is clockwise, which is why
        #    the two combine as a difference. It happens to come out 45 again at
        #    the measured angle — that is a coincidence of 90 - 45, not an
        #    identity, and re-angling the phone breaks it.
        red = tuple(t["pict_red"])
        text_ccw = 90.0 - ang
        for name in ("manner", "mode"):
            surf, box = self._pict_text(str(t[f"{name}_text"]), int(t[f"{name}_size"]), red, text_ccw)
            cx, cy = local(float(t[f"{name}_u"]), float(t[f"{name}_v"]))
            big.blit(surf, (round(cx - box.centerx), round(cy - box.centery)))

        # 5. 通話, placed by its ink LEFT/TOP, then the strike over it.
        call, box = self._pict_text(str(t["call_text"]), int(t["call_size"]), tuple(t["call_color"]))
        cx, cy = P(float(t["call_ink_x"]), float(t["call_ink_y"]))
        big.blit(call, (round(cx - box.x), round(cy - box.y)))

        sx, sy = float(t["strike_x"]), float(t["strike_y"])
        hw, hh = float(t["strike_w"]) / 2.0, float(t["strike_h"]) / 2.0
        half = float(t["strike_stroke"]) / 2.0 * ss
        for sign in (1.0, -1.0):
            x0, y0 = P(sx - hw, sy - sign * hh)
            x1, y1 = P(sx + hw, sy + sign * hh)
            dx, dy = x1 - x0, y1 - y0
            n = math.hypot(dx, dy) or 1.0
            ox, oy = -dy / n * half, dx / n * half
            pygame.draw.polygon(
                big,
                red,
                [(x0 + ox, y0 + oy), (x1 + ox, y1 + oy), (x1 - ox, y1 - oy), (x0 - ox, y0 - oy)],
            )

        out = pygame.transform.smoothscale(big, (rect.w, rect.h))
        self._text_cache[("pict_surface", key)] = out
        return out

    def _draw_group(self, group: str, lines, size: int, color, left_x: float, ink_y: float, pitch: float) -> None:
        """One group's lines: left-aligned on a PEN x, each seated on its INK top.

        The x is the surface's left edge, NOT the ink's — the face's own side
        bearing is part of the layout, and the reference confirms ours match its
        (see `ja_left_x`). Placing by ink x instead would flatten every line's
        bearing to zero and shift the column left by a per-glyph amount.
        """
        for i, text in enumerate(lines):
            surf, _ink_x, ink_top, _ink_w = self._ink(group, size, text, color)
            self.screen.blit(surf, (int(round(left_x)), int(round(ink_y + i * pitch - ink_top))))

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Draw the whole page. Pure render — mutates nothing but the surface.

        `state` and `current_time` are accepted and unused: the page is static,
        and the signature is the one the manager calls every view with.
        """
        del current_time
        self.state = state

        t = _TUNEABLES_MANNER_MODE
        # The background is CHROME and is never recoloured here — `LOWER_BG` is
        # the model's own constant, not a tuneable of this page (see the CONTRACT
        # in `displays/train_models/e233_0/__init__.py`). Filling is idempotent
        # with the manager's own fill; it is repeated so the view renders
        # correctly when driven directly, as the sibling views do.
        pygame.draw.rect(self.screen, LOWER_BG, MANNER_MODE_RECT)

        self._draw_panel()
        for group in ("ja", "en"):
            self._draw_group(
                group,
                tuple(t[f"{group}_lines"]),
                int(t[f"{group}_size"]),
                tuple(t[f"{group}_color"]),
                float(t[f"{group}_left_x"]),
                float(t[f"{group}_ink_y"]),
                float(t[f"{group}_line_pitch"]),
            )

    def draw(self, current_time: float = 0.0) -> None:
        """Redraw from the bound state, matching the sibling views' entry."""
        self.show_stops(self.state, current_time)


# Module-level so the calibration editor's registry and any preview reach the
# same dict the renderer reads (`conventions.md` § UI code style).
__all__ = ["MannerModeDisplay", "MANNER_MODE_RECT", "_TUNEABLES_MANNER_MODE"]

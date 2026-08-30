# SPDX-License-Identifier: MIT
"""E233-0 transfer-info display (concrete) — the standalone のりかえ view.

Spec: `docs/wip/WIP_e233_0_display.md` § 11. A rounded blue banner, then one row
per connecting line: a square badge, the line name in kanji, the English name
beneath it. Long lists wrap into a SECOND COLUMN rather than paging or being
cut (author, 2026-08-29).

This shares NOTHING with E235's panel but the parent pipeline and `load_icon`.
E235 packs entries horizontally across up to three rows through the Rule 1-4
column cascade because its lower region is wide and short; E233-0's is
640 x 331 and stacks vertically. Importing that cascade would be the borrowed
behaviour `CLAUDE.md` § "Per-model IRL line scope" bars — the author confirmed
E235 does not change, and that shared *utilities* are welcome where shared
*layout* is not.
"""

from typing import List

import pygame

from displays.train_models.e233_0 import LOWER_BG, S_HEIGHT, S_WIDTH, UPPER_HEIGHT
from displays.transfer_info import TransferInfoDisplay as _BaseTransferInfoDisplay
from displays.transfer_info import load_icon, resolve_entry, wrap_two_lines
from font_atlas import at, lcd_font, lit

_NAME_FACE = "ShinGoPro-DeBold.otf"
_EN_FACE = "HelveticaNeue-Medium.otf"

# fmt: off
_TUNEABLES_TRANSFER_VIEW = {
    # ---- the banner -----------------------------------------------------
    # [measured] off `transfer-hachioji-ja.png` via
    # `_dev_scripts/_e233_lower_geometry.py --transfer`, in canvas units.
    # That mode measures what is NOT the background rather than ink, because
    # this pill's luminance sits between the background and its own white text
    # and no single threshold finds both.
    "banner_cx":       315.3,  # the reference's own centre, 4.7 left of the
                               # canvas centre. Kept as measured rather than
                               # snapped to 320 — one capture cannot say which
                               # is the panel and which is the crop.
    "banner_w":        260.8,
    "banner_h":         29.0,
    "banner_top":      181.9,  # 32.9 below the divide
    # A GLOSSY pill: dark at BOTH edges, brightest across the middle
    # (78,102,216 -> 182,200,225 -> 78,102,216), symmetric about the centre.
    # NOT a plain triangle — a 40-sample walk at 2px clear of the text shows the
    # dark holding FLAT for the first ~38% from each edge and only then ramping.
    # Ramping from the edge instead put visibly more light in the pill, which is
    # what the author saw ("i think your pill is too bright").
    "banner_edge":  (78, 102, 216),
    "banner_mid":  (182, 200, 225),
    "banner_flat":  0.38,  # of the half-height, held at `banner_edge`
    "banner_text":     "のりかえ / Transfer",
    "banner_size":      20,
    "banner_ink":  (255, 255, 255),
    # ---- the rows -------------------------------------------------------
    "col0_x":          198.8,  # badge LEFT edge. The two reference rows read
                               # 196.0 and 201.5; the difference is the
                               # threshold, not the layout — a green-bordered
                               # badge and a flat grey one feather into the
                               # background over different distances, so their
                               # measured extents differ where their drawn
                               # rects do not.
    "row0_top":        238.2,  # first badge's top
    "row_pitch":        67.8,  # badge top to badge top
    "badge":            48.5,
    "badge_gap":         6.0,  # badge right edge -> text left edge. With
                               # col0_x 199 and badge 48.5 this puts the text at
                               # 253.5, which is where both reference rows have
                               # it to within half a pixel — the text edge is
                               # the one thing the two rows agree on exactly.
    "ja_ink_dy":         1.3,  # badge top -> JA ink top
    # Sizes fitted against WIDTH AND HEIGHT together, not height alone: the
    # first pass solved 31/19 from the ink heights and came out 8% wide, because
    # a size that matches cap height need not match the run. Every ShinGo weight
    # lands on 33 for the kanji and every Latin candidate within a size of 18
    # for the English, so the fit picks the SIZE and cannot pick the FACE —
    # weight is the author's eye against the overlay.
    "ja_size":          33,    # 横浜線 97x33 against a measured 97.58x31.53
    "en_size":          18,    # Yokohama Line 126x13 against 124.42x14.49
    "ja_line_step":     36.0,  # JA ink top -> next JA ink top, within one entry
    "en_line_step":     18.0,  # EN ink top -> next EN ink top, within one entry
    "ja_en_step":       34.5,  # JA ink top -> EN ink top. NOT the 26.0 that
                               # `--rows` prints: that is centre-to-centre, and
                               # the two lines have different ink heights, so
                               # using it directly overlapped them.
    "col_gap":          18.0,  # between a column's widest entry and the next
    "max_cols":          3,    # two normally; three where the station is
                               # congested (author, 2026-08-29). Past three the
                               # ladder runs out and the block is drawn at the
                               # smallest rung rather than clipped.
    "side_pad":         14.0,  # the wrapped block's own margin either side
    "bottom_pad":        4.0,
    # Entry-count size classes, the E235 `name_size_ladder` idea: a busy station
    # reads as busy, so N picks a FLOOR on the ladder and the fit may only go
    # smaller from there. <=4 -> rung 0, <=9 -> rung 1, else rung 2.
    "class_small":       4,
    "class_mid":         9,
    # A NAME THIS WIDE TAKES A ROW TO ITSELF (author, 2026-08-29). Of the usable
    # width, so a two-badge group or a long English name counts toward it too.
    # The references bracket it: 中央・総武線(各駅停車) is 450px and alone at
    # 御茶ノ水, 青梅・五日市線 and 多摩モノレール are 285px and alone at 立川,
    # while 丸ノ内線 at 186px pairs. 0.40 of 612 is 245 — between the two.
    "long_row_frac":    0.40,
    # A trailing row of ONE folds into the row above, whose extra entry then
    # overhangs — but only on a LIST THIS TALL. 新宿's nine pair into five rows
    # and `transfer-shinjuku.png` draws (2,2,2,3); 武蔵小杉's five make three
    # and the author keeps (2,2,1), so the orphan is tolerated at three rows
    # and not at five.
    "fold_min_rows":     4,
    # A SHINKANSEN WRAPS AGAINST THE BLOCK, NOT THE CANVAS — E235's own
    # `tp_shink_wrap_x` idea (*"narrower fixed shinkansen 2-line wrap
    # boundary"*). Its name is the one entry that can outgrow every other row
    # combined, and the shared left edge is set by the widest row, so left
    # unbudgeted it drags the whole block against the left margin.
    #
    # ONLY AT THE SMALL RUNGS (author, 2026-08-30: *"wrap effect is not so good.
    # i think generally when the shinkansen is a small size like in those dense
    # station, it's better"*). At a large rung the two-line name reads loose
    # beside single-line neighbours, and the second line costs a row — which at
    # 上野 was enough to push the list from two columns to three and shrink
    # everything. `_max_rung` is that gate, as a rung VALUE rather than an index
    # so it survives a change to the ladder.
    #
    # `_frac` is the FLOOR on the budget, of the usable width: without it a
    # station whose grid is narrow (宇都宮's 153px) would squeeze the shinkansen
    # to three or four lines.
    #
    # OFF, because the two conditions never coincide in the shipped corpus and
    # the rule is kept rather than the behaviour. Measured 2026-08-30 with
    # `_dev_scripts/_e233_transfer_cases.py`: the stations where the shinkansen
    # IS the widest row — 上野 JU/JY, 大宮 JU/JA, 品川 JY/JK/JT, 小山, 宇都宮 —
    # all sit at rung 0.84 or 1.0, the large end. At every dense station (0.71,
    # 0.6) the grid is already wider, so there is nothing to wrap. With the gate
    # in, exactly ONE case fired — 宇都宮 東京 — and it fell 0.71 -> 0.6, because
    # the second line costs a row and the row broke the cap. Flip to True if a
    # future line produces a dense station whose shinkansen still leads.
    "shink_wrap_block": False,
    "shink_wrap_max_rung": 0.71,
    "shink_wrap_frac":  0.55,
    "ink":         (0, 0, 0),
    # A LADDER, because a font size is part of the atlas key: a pitch scaled
    # continuously to fit would ask for an arbitrary size and the bake has no
    # way to know it. Rung 0 is the measured row; the rest are that row scaled,
    # so there is one authored tuple and the others cannot drift from it.
    # Three rungs is what 新宿's nine entries need — at rung 0 a column holds
    # three, so two columns hold six.
    "rungs":       (1.0, 0.84, 0.71, 0.60),
}
# fmt: on

# What this view draws: the two name fields, and — because a name too wide for
# its row is laid over two lines — every two-way CUT of them. `cuts=True` rather
# than `wrap="･"` because the break rule is the caller's and has three arms (the
# half-width dot, a space, then a bare character prefix), so declaring the
# separator would leave the third undeclared. It over-approximates on purpose:
# the declaration says what MAY be drawn and the bake records what is, so
# changing where the break lands cannot leave the atlas a case short.
_LINE_JA = at("data/lines.json:*.name_ja", "data/lines.json:*.variants.*.name_ja", cuts=True)
_LINE_EN = at("data/lines.json:*.name_en", "data/lines.json:*.variants.*.name_en", cuts=True)


# The whole lower region — the view has no sub-element the editor picks apart,
# so its hit-test rect is the region it draws into.
TRANSFER_VIEW_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)


class TransferInfoDisplay(_BaseTransferInfoDisplay):
    """E233-0's のりかえ view. The parent resolves the list; this draws it."""

    def __init__(self, screen, route_data: dict, stops: list):
        super().__init__(screen, route_data, stops)
        self._icons: dict = {}
        self._fonts: dict = {}
        self._text_cache: dict = {}

    # ---- fonts ----------------------------------------------------------

    def _ja_font(self, size: int):
        f = self._fonts.get(("ja", size))
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=_LINE_JA)
            self._fonts[("ja", size)] = f
        return f

    def _en_font(self, size: int):
        f = self._fonts.get(("en", size))
        if f is None:
            f = lcd_font(_EN_FACE, size, draws=_LINE_EN)
            self._fonts[("en", size)] = f
        return f

    def _ink(self, kind: str, size: int, text: str, color):
        """`(surface, ink_dy)` — the rendered text plus where its ink starts.

        Every figure in § 11.2 is an INK measurement, so a row placed by the
        font BOX lands wrong by the face's internal leading — which is what put
        the English line on top of the Japanese one on the first render. Cached
        by the drawn string: the ink offset is a property of the glyphs, not of
        the face, so kanji and Latin at one size do not share one.
        """
        key = (kind, size, text)
        hit = self._text_cache.get(key)
        if hit is not None:
            return hit
        font = self._ja_font(size) if kind == "ja" else self._en_font(size) if kind == "en" else self._banner_font(size)
        surf = font.render(text, True, color)
        ys = [y for y in range(surf.get_height()) if any(surf.get_at((x, y))[3] > 110 for x in range(surf.get_width()))]
        out = (surf, ys[0] if ys else 0)
        self._text_cache[key] = out
        return out

    def _banner_font(self, size: int):
        f = self._fonts.get(("banner", size))
        if f is None:
            f = lcd_font(_NAME_FACE, size, draws=lit(_TUNEABLES_TRANSFER_VIEW["banner_text"]))
            self._fonts[("banner", size)] = f
        return f

    # ---- the banner -----------------------------------------------------

    def _draw_banner(self) -> None:
        t = _TUNEABLES_TRANSFER_VIEW
        w, h = float(t["banner_w"]), float(t["banner_h"])
        x0 = float(t["banner_cx"]) - w / 2.0
        y0 = float(t["banner_top"])
        r = h / 2.0

        edge = tuple(t["banner_edge"])
        mid = tuple(t["banner_mid"])
        pill = pygame.Surface((int(round(w)), int(round(h))), pygame.SRCALPHA)
        ih = pill.get_height()
        flat = float(t["banner_flat"])
        for y in range(ih):
            # Distance from the centre as a fraction of the half-height, then
            # the flat plateau taken off the OUTER end of it: 0 across the dark
            # band nearest each edge, ramping to 1 at the centre line.
            u = 1.0 - abs((y + 0.5) - ih / 2.0) / (ih / 2.0)  # 0 at the edge, 1 at the centre
            f = max(0.0, (u - flat) / (1.0 - flat)) if flat < 1.0 else 0.0
            c = tuple(int(round(edge[i] + (mid[i] - edge[i]) * min(1.0, f))) for i in range(3))
            pygame.draw.line(pill, c, (0, y), (pill.get_width(), y))

        # Round the ends by punching the corners out of the gradient rather than
        # drawing a rounded rect in a flat colour — the fill varies per row, so
        # the shape has to be applied to it, not instead of it.
        mask = pygame.Surface(pill.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=int(round(r)))
        pill.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(pill, (int(round(x0)), int(round(y0))))

        # Centred on its INK, not its font box — the box carries ShinGo's
        # leading, which is asymmetric, so box-centring sits the label high.
        label, dy = self._ink("banner", int(t["banner_size"]), str(t["banner_text"]), tuple(t["banner_ink"]))
        ys = [y for y in range(label.get_height()) if any(label.get_at((x, y))[3] > 110 for x in range(label.get_width()))]
        ink_h = (ys[-1] + 1 - ys[0]) if ys else label.get_height()
        self.screen.blit(
            label,
            (
                int(round(float(t["banner_cx"]) - label.get_width() / 2.0)),
                int(round(y0 + (h - ink_h) / 2.0 - dy)),
            ),
        )

    # ---- the rows -------------------------------------------------------

    def _entries(self, transfers: List[str]):
        """`[(badges, name_ja, name_en, is_shinkansen), ...]` for the refs."""
        out = []
        for ref in transfers:
            e = resolve_entry(ref, self.lines)
            out.append(
                (
                    e.get("badges", []) or [{"icon": "_universal"}],
                    e.get("name_ja", ""),
                    e.get("name_en", ""),
                    e.get("category") == "shinkansen",
                )
            )
        return out

    def _solo(self, entries, scale: float, avail_w: float):
        """Indices that take a row to themselves: shinkansen, and LONG names.

        The author's rule, and what the references draw (2026-08-29: *"when the
        line got a very long transfer name, it has it's own row"*).
        `transfer-ocha-ja.png` is (1,2) — 中央・総武線(各駅停車) alone above
        丸ノ内線 | 千代田線 — and `transfer-tachikawa-ja.png` is (1,1,1), where
        南武線 is short but ends up alone because both its neighbours are long.
        So this is not a per-N grouping table; it is a per-ENTRY property, and
        the pairing falls out of what is left.

        Measured as a fraction of the usable width rather than a glyph count, so
        a badge group of two and a long English name both count toward it.
        """
        t = _TUNEABLES_TRANSFER_VIEW
        bar = float(t["long_row_frac"]) * avail_w
        out = set()
        for k, e in enumerate(entries):
            if e[3]:
                out.add(k)
                continue
            if self._entry_width(e, scale, self._wrap(e, scale, avail_w)) > bar:
                out.add(k)
        return out

    def _grid(self, entries, cols: int, solo=()):
        """Row-major cell assignment: `[[entry index, ...], ...]` by row.

        ROW-MAJOR (author, 2026-08-29: *"fill the row first"*). 新宿's nine
        entries are five rows of two, not columns of five — the list reads
        across and then drops, so a wrap adds a row rather than a column.

        A SHINKANSEN TAKES A ROW TO ITSELF, the treatment E235 gives it (author,
        2026-08-29), keyed on the same `category` field in `lines.json` rather
        than on the name — so a line reclassified in the data moves on both
        models and neither string-matches 新幹線.
        """
        rows, cur = [], []
        for i, e in enumerate(entries):
            if i in solo:
                if cur:
                    rows.append(cur)
                    cur = []
                rows.append([i])
                continue
            cur.append(i)
            if len(cur) == cols:
                rows.append(cur)
                cur = []
        if cur:
            rows.append(cur)
        return rows

    @staticmethod
    def _fold(grid):
        """The same grid with a trailing row of ONE folded into the row above.

        新宿 on JC is (2,2,2,3) with the last row's third entry overhanging the
        two-column grid (author, 2026-08-29). It is a FITTING device rather than
        a style — nine entries pair into (2,2,2,2,1), five rows that no rung
        holds at a readable size, and folding the orphan gives four, which one
        rung down does hold. Offered as an alternative and taken only when the
        plain grid does not fit, which is why 武蔵小杉 keeps (2,2,1) and 御茶ノ水
        keeps (2,1): both place unfolded at the top rung.
        """
        t = _TUNEABLES_TRANSFER_VIEW
        if len(grid) < int(t["fold_min_rows"]) or len(grid[-1]) != 1 or len(grid[-2]) <= 1:
            return None
        # ONLY ON A UNIFORM GRID. Where solo rows are already in play — 東京's
        # two shinkansen — the page reads as a list of unlike rows, and folding
        # the orphan into a three-wide one adds a third shape rather than
        # tidying anything. The author compared both and kept the six-row form
        # (2026-08-29). 新宿's grid is all pairs, so the orphan is the only odd
        # row there and folding it is what the reference draws.
        if any(len(r) == 1 for r in grid[:-1]):
            return None
        return grid[:-2] + [grid[-2] + grid[-1]]

    def _sizes(self, scale: float):
        t = _TUNEABLES_TRANSFER_VIEW
        return (
            max(1, int(round(float(t["badge"]) * scale))),
            max(6, int(round(float(t["ja_size"]) * scale))),
            max(6, int(round(float(t["en_size"]) * scale))),
        )

    def _badge_w(self, badges, badge_h: int) -> float:
        return sum(load_icon(b.get("icon", "_universal"), badge_h, self._icons).get_width() for b in badges)

    def _wrap(self, entry, scale: float, budget: float, deliberate_wrap: bool = False):
        """`(ja1, ja2, en1, en2)` — the entry's name lines within `budget`.

        Second lines are empty for everything that fits, which is every entry on
        every station but the shinkansen ones. `東京` is what forces this: its
        東北･山形･秋田･北海道･上越･北陸新幹線 overruns the canvas at every rung, so
        no amount of shrinking places it and the block ran off both edges.

        `deliberate_wrap` marks a wrap that is the LAYOUT'S INTENT rather than a
        fit failure — the shinkansen budgeted against the block instead of the
        canvas (`_place`). Without it the shrink-before-wrap preference reads
        every such row as a failure and steps down a rung for nothing.
        """
        t = _TUNEABLES_TRANSFER_VIEW
        badges, name_ja, name_en = entry[0], entry[1], entry[2]
        badge_h, ja, en = self._sizes(scale)
        avail = budget - self._badge_w(badges, badge_h) - float(t["badge_gap"]) * scale
        f_ja, f_en = self._ja_font(ja), self._en_font(en)
        ok = True
        deliberate = deliberate_wrap
        # NO UNCONDITIONAL PARENTHETICAL BREAK IN THIS VIEW. The 6-station band
        # puts （各駅停車） on its own line because its columns are one station
        # wide; `transfer-ocha-ja.png` draws 中央・総武線(各駅停車) on ONE line
        # and gives the entry a row to itself instead. Same name, different
        # answer, because the two views have different room.
        if f_ja.size(name_ja)[0] <= avail:
            ja1, ja2 = name_ja, ""
        else:
            # A name with no separator can only be cut MID-WORD, which
            # 上野東京ライン and 横須賀線・総武線快速 both showed as 上野東京ラ / イン
            # at three columns. That is never an acceptable render, so it
            # disqualifies the candidate layout rather than being drawn — the
            # search then finds a wider column at a smaller rung, which is the
            # outcome the ladder exists for.
            ok = "･" in name_ja or "（" in name_ja[1:]
            ja1, ja2 = wrap_two_lines(name_ja, f_ja, int(avail))
        if not name_en or f_en.size(name_en)[0] <= avail:
            en1, en2 = name_en, ""
        else:
            ok = ok and " " in name_en
            deliberate = deliberate_wrap  # a width-driven EN wrap is not itself intent
            en1, en2 = wrap_two_lines(name_en, f_en, int(avail))
        return ja1, ja2, en1, en2, ok, deliberate

    def _entry_width(self, entry, scale: float, lines) -> float:
        """What `_draw_row` will occupy, without drawing it.

        Measured from the same fonts and badge heights the draw uses, so the fit
        and the render cannot disagree — a width model restating the row's
        arithmetic would be the drift `principles.md` § "A second implementation
        of a production decision" describes.
        """
        t = _TUNEABLES_TRANSFER_VIEW
        badges = entry[0]
        badge_h, ja, en = self._sizes(scale)
        ink = tuple(t["ink"])
        ja1, ja2, en1, en2 = lines[:4]
        w = max(
            [self._ink("ja", ja, s, ink)[0].get_width() for s in (ja1, ja2) if s]
            + [self._ink("en", en, s, ink)[0].get_width() for s in (en1, en2) if s]
            or [0]
        )
        return self._badge_w(badges, badge_h) + float(t["badge_gap"]) * scale + w

    def _layout(self, entries):
        """`(scale, cols, col_widths, wrapped)` — the largest rung the list fits.

        Fits on WIDTH as well as height, which is E235's own lesson rather than
        a precaution: its ladder keys on entry COUNT and under-predicts width
        when a name is long, which is how 秋葉原 came to render two names
        touching at 620px inside a 618px row (`docs/DISPLAY_E235.md` § Pipeline).
        So the columns are laid out for real at each rung and the block is
        measured, not estimated.

        Falls through to the smallest rung rather than clipping — a column that
        cannot hold its share is the failure this exists to prevent, and a
        silently short list is the worst outcome available.
        """
        t = _TUNEABLES_TRANSFER_VIEW
        n = len(entries)
        avail_h = S_HEIGHT - float(t["row0_top"]) - float(t["bottom_pad"])
        avail_w = S_WIDTH - 2.0 * float(t["side_pad"])
        # A SIZE FLOOR KEYED ON ENTRY COUNT, which is E235's `name_size_ladder`
        # doing the same job: a busy station reads as busy, and the largest size
        # that happens to fit is not the one it should get. Five entries were
        # rendering at the top rung and the author called them too big
        # (2026-08-29, 武蔵小杉).
        floor = 0 if n <= int(t["class_small"]) else 1 if n <= int(t["class_mid"]) else 2
        chosen = fallback = None
        for scale in t["rungs"][floor:]:
            pitch = float(t["row_pitch"]) * scale
            gap = float(t["col_gap"]) * scale
            cap = max(1, int((avail_h - float(t["badge"]) * scale) // pitch) + 1)
            # THREE OR MORE ENTRIES PAIR UP; TWO DO NOT (author, 2026-08-29:
            # 御茶ノ水 is (2,1) and 武蔵小杉 is (2,2,1)). Both fall out of a
            # minimum column count rather than a per-N table, and it is E235's
            # own small-N structural rule reached the same way. N=2 is where the
            # two models part: E235 pairs it when the widths allow, and the
            # 八王子 reference stacks its two with room either side — so a
            # fits-in-one-column search is wrong for N>=3 and right for N<=2.
            solo = self._solo(entries, scale, avail_w)
            # A LONG NAME'S OWN ROW IS A PREFERENCE, NOT A CONSTRAINT — it yields
            # when keeping it would cost a column. E235 reaches its groupings by
            # trying and repairing rather than from an absolute table
            # (`docs/DISPLAY_E235.md` § Pipeline step 2, "greedy walk + cascade
            # dry-run"), and this is that idea at this view's scale: the strict
            # form is tried first at every column count, and only where it does
            # not place is the long-name row allowed to pair.
            #
            # 上野 on JY is the case (author, 2026-08-30: *"JU utsu and JU takasaki
            # can be one 1 row?"*). 宇都宮線(東北線) measures 266 against a 245 bar,
            # clearing it by 21px — so it took a row, which made 7 entries need 5
            # rows against a cap of 4, which sent the station to THREE columns.
            # Paired with 高崎線 (139) the row is 420 inside 612 and the station
            # places in two.
            #
            # A SHINKANSEN IS NEVER RELAXED. Its own row is the treatment E235
            # gives it off the same `category` field, not a width judgement, so it
            # is the one member of `_solo`'s output that the relaxation keeps.
            forced = {k for k, e in enumerate(entries) if e[3]}
            for cols in range(1 if n <= 2 else 2, int(t["max_cols"]) + 1):
                for keep in (solo, forced) if solo != forced else (solo,):
                    plain = self._grid(entries, cols, keep)
                    # FOLDED FIRST where one is offered — `_fold` only offers on a
                    # list tall enough for the orphan to be the IRL form, so
                    # preferring it there cannot reach 武蔵小杉's (2,2,1).
                    for grid in [g for g in (self._fold(plain), plain) if g]:
                        cand = self._place(entries, grid, scale, cols, gap, cap, avail_w)
                        if cand is None:
                            continue
                        ok, wrapped, widths, wraps = cand
                        if not ok:
                            continue
                        if not wraps:
                            return (scale, cols, widths, wrapped, grid)
                        # SHRINK BEFORE YOU WRAP. A two-line entry beside one-line
                        # neighbours reads loose, and one rung down it usually fits
                        # whole — so a wrapping candidate is held and the search
                        # carries on, to be used only if no rung places the list
                        # without one.
                        if fallback is None:
                            fallback = (scale, cols, widths, wrapped, grid)
        return (
            fallback
            or chosen
            or (t["rungs"][-1], 1, [avail_w], {k: self._wrap(entries[k], t["rungs"][-1], avail_w) for k in range(n)}, self._grid(entries, 1))
        )

    def _place(self, entries, grid, scale, cols, gap, cap, avail_w):
        """Try one grid at one rung: `(fits, wrapped, widths, wrap_count)`.

        Split out of `_layout` so the rung / column / fold loops stay flat —
        three nested loops around forty lines of measurement is where the
        indentation stops carrying the logic.
        """
        # COLUMNS ARE NOT EQUAL SHARES. Deciding the wrap against `avail_w /
        # cols` asks each entry to fit half the canvas, which is stricter than
        # the question the layout answers: columns size to their own content, so
        # a wide entry beside a narrow one fits at a size neither would clear on
        # an equal split. 御茶ノ水 shrank two rungs for that reason with 168px to
        # spare. First pass wraps only what cannot fit the WHOLE width; the equal
        # share is the second, reached only when that genuinely overflows.
        t = _TUNEABLES_TRANSFER_VIEW
        share = (avail_w - gap * (cols - 1)) / cols
        wrapped = widths = None
        total = 0.0
        for budget in (avail_w, share):
            # SHARED ROWS FIRST — they alone set the column widths, so the block's
            # own width is known before any solo row is measured against it.
            wrapped = {k: self._wrap(entries[k], scale, budget) for row in grid if len(row) > 1 for k in row}
            span = max(len(row) for row in grid)
            widths = [
                max((self._entry_width(entries[row[c]], scale, wrapped[row[c]]) for row in grid if len(row) > c and len(row) > 1), default=0.0)
                for c in range(span)
            ]
            # A SHINKANSEN WRAPS AGAINST THE BLOCK, NOT THE CANVAS — E235's own
            # `tp_shink_wrap_x`, *"narrower fixed shinkansen 2-line wrap
            # boundary"*, which is the second half of its shape rule: the widest
            # row defines the page width, and a shinkansen is not allowed to be
            # that row unaided. Without it 東北･山形･秋田･北海道･上越･北陸新幹線 sets
            # a 564px page on a 612px canvas, and the shared left edge it forces
            # leaves a two-entry grid ~200px of dead right margin.
            #
            # Only a SHINKANSEN, keyed on `lines.json`'s `category` exactly as
            # E235 keys on it. A long ordinary name must not wrap here:
            # `transfer-ocha-ja.png` draws 中央・総武線(各駅停車) on ONE line and
            # gives it a row to itself instead (§ 11.3), so a blanket rule would
            # break the reference at 御茶ノ水 / 四ツ谷.
            block = sum(widths[:cols]) + gap * (cols - 1)
            if block <= 0:
                # A ONE-COLUMN LIST HAS NO SHARED ROWS, so `widths` is all zeros
                # and the block would measure nothing — which silently exempted
                # exactly the worst case (宇都宮: a 153px 日光線 beside a 501px
                # shinkansen). Fall back to the widest ordinary solo row. A list
                # that is ONLY a shinkansen (那須塩原) still measures 0 and is
                # left alone, which is right: there is no block for it to match.
                block = max(
                    (
                        self._entry_width(entries[r[0]], scale, self._wrap(entries[r[0]], scale, avail_w))
                        for r in grid
                        if len(r) == 1 and not entries[r[0]][3]
                    ),
                    default=0.0,
                )
            narrow = float(t["shink_wrap_frac"]) * avail_w
            for row in grid:
                if len(row) == 1:
                    k = row[0]
                    to_block = entries[k][3] and block > 0 and bool(t["shink_wrap_block"]) and scale <= float(t["shink_wrap_max_rung"]) + 1e-9
                    b = max(block, narrow) if to_block else avail_w
                    wrapped[k] = self._wrap(entries[k], scale, b, deliberate_wrap=to_block and b < avail_w)
            # The GRID is `cols` wide; a folded row's extra entry OVERHANGS it
            # and is not part of the block's width. That is what "sticks out"
            # means in `transfer-shinjuku.png`, and measuring it into the block
            # is what kept rejecting (2,2,2,3) at every rung.
            total = sum(widths[:cols]) + gap * (cols - 1)
            if total <= avail_w and self._reach(widths, cols, gap, total) <= avail_w:
                break
        # A second line costs its row an extra pitch either way, so the VERTICAL
        # fit counts every one. The shrink-before-wrap preference counts only the
        # width-driven ones — a parenthetical taking line 2 is the name's written
        # form, so treating it as a fit failure would shrink every station
        # carrying 中央・総武線（各駅停車） by a rung for nothing.
        extra = sum(1 for row in grid if any(wrapped[k][1] or wrapped[k][3] for k in row))
        wraps = sum(1 for row in grid if any((wrapped[k][1] or wrapped[k][3]) and not wrapped[k][5] for k in row))
        fits = (
            total <= avail_w and self._reach(widths, cols, gap, total) <= avail_w and len(grid) + extra <= cap and all(w[4] for w in wrapped.values())
        )
        return fits, wrapped, widths, wraps

    @staticmethod
    def _reach(widths, cols, gap, total):
        """Left edge of the block to the right edge of its overhang, if any.

        A block WITH an overhang anchors left rather than centring, which is
        what `transfer-shinjuku.png` shows — its list starts hard against the
        left margin, not balanced. So the overhang has the whole usable width to
        reach into, and this is what bounds it.
        """
        return total + gap + widths[cols] if len(widths) > cols else total

    def _draw_row(self, x: float, top: float, entry, lines, scale: float) -> float:
        """One entry. Returns the rows it consumed — 1, or 2 when it wrapped."""
        t = _TUNEABLES_TRANSFER_VIEW
        badge_h, ja, en = self._sizes(scale)
        ink = tuple(t["ink"])
        ja1, ja2, en1, en2 = lines[:4]

        bx = x
        for b in entry[0]:
            icon = load_icon(b.get("icon", "_universal"), badge_h, self._icons)
            self.screen.blit(icon, (int(round(bx)), int(round(top))))
            bx += icon.get_width()

        tx = bx + float(t["badge_gap"]) * scale
        # The JA line's INK sits level with the badge's top and the EN below it,
        # by the step both reference rows agree on to the pixel — so a row is a
        # fixed block rather than one sizing to its content.
        #
        # A WRAPPED ENTRY STACKS BOTH JAPANESE LINES FIRST, then both English
        # ones. Interleaving them a full row-pitch apart — JA1, EN1, then JA2 —
        # put （各駅停車） below its own English line and a whole row away from
        # the 中央・総武線 it belongs to, which reads as two entries rather than
        # one name over two lines.
        ja_step = float(t["ja_line_step"]) * scale
        en_step = float(t["en_line_step"]) * scale
        ja_top = top + float(t["ja_ink_dy"]) * scale
        for k, line in enumerate((ja1, ja2)):
            if line:
                s, dy = self._ink("ja", ja, line, ink)
                self.screen.blit(s, (int(round(tx)), int(round(ja_top + k * ja_step - dy))))
        en_top = ja_top + (ja_step if ja2 else 0.0) + float(t["ja_en_step"]) * scale
        for k, line in enumerate((en1, en2)):
            if line:
                s, dy = self._ink("en", en, line, ink)
                self.screen.blit(s, (int(round(tx)), int(round(en_top + k * en_step - dy))))
        # How many row slots the block consumed, so the next row clears it.
        bottom = en_top + (en_step if en2 else 0.0) + float(t["en_size"]) * scale
        return max(1, int(-(-(bottom - top) // (float(t["row_pitch"]) * scale))))

    def _render(self, transfers: List[str], current_time: float) -> None:
        del current_time
        area = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)
        pygame.draw.rect(self.screen, LOWER_BG, area)
        self._draw_banner()
        if not transfers:
            return

        t = _TUNEABLES_TRANSFER_VIEW
        entries = self._entries(transfers)
        scale, cols, widths, wrapped, grid = self._layout(entries)
        pitch = float(t["row_pitch"]) * scale
        gap = float(t["col_gap"]) * scale

        overhang = len(widths) > cols

        # ONE LEFT EDGE FOR EVERY ROW — E235's shape rule, ported (author,
        # 2026-08-30: *"find overall rule of shape from e235 transfers, that is
        # well tuned"*). Its column-system blueprint states the principle in the
        # overhang-trim comment at `e235_1000/transfer_info.py:756`: *"justifying
        # is right whenever the anchor row is the TOP row: it is then the widest
        # row by construction, so it defines the page width and nothing can stick
        # out past it"*. So the WIDEST row sets the page width and every other row
        # anchors on its left edge, which is what makes a badge column uniform all
        # the way down. What does NOT come across is the horizontal cascade — that
        # is packing machinery for a wide short region (WIP § 11.1).
        #
        # This replaces two INDEPENDENT centrings — the widest shinkansen row on
        # the canvas, the grid on the canvas — plus a `len(shink_rows) >= 2` gate.
        # The count was a proxy for "is the grid at least as wide as the shinkansen
        # row", which holds whenever there are two (the block is 3-column by then)
        # and fails otherwise: the two badge columns then sat up to 174px apart
        # (宇都宮 at 宇都宮 — measured across the corpus, one shinkansen, grid 153
        # against a 501 shinkansen row).
        #
        # `widths` is a per-COLUMN table built from SHARED rows only, so a grid of
        # nothing but solo rows — 立川's (1,1,1) — leaves it all zeros; a row's
        # width therefore comes from its own entry when it is alone.
        def _row_w(row):
            if len(row) > 1:
                return sum(widths[: len(row)]) + gap * (len(row) - 1)
            return self._entry_width(entries[row[0]], scale, wrapped[row[0]])

        widest = max([_row_w(row) for row in grid] or [0.0])
        room = S_WIDTH - float(t["side_pad"])
        if overhang:
            # A block with an overhang anchors LEFT — centring the grid pushes the
            # sticking-out entry off the right edge, and `transfer-shinjuku.png`
            # starts its list hard against the left margin.
            left = float(t["side_pad"])
        elif cols < 2 and float(t["col0_x"]) + widest <= room:
            # THE CHUO ORIGIN. A single column sits where the reference puts it
            # (`transfer-hachioji-ja.png` measures `col0_x`), not where centring
            # would — that anchor is measured, and the in-spec renders are
            # accepted against it. It yields only when a row would not fit beside
            # it, which is the lone-shinkansen case (宇都宮, 那須塩原).
            left = float(t["col0_x"])
        else:
            left = (S_WIDTH - widest) / 2.0

        y = float(t["row0_top"])
        for row in grid:
            used = 1
            for c, k in enumerate(row):
                # Solo or shared, every row starts on the block's edge; a shared
                # row takes its column's x from the same widths the fit measured.
                x = left if len(row) == 1 else left + sum(widths[:c]) + gap * c
                used = max(used, self._draw_row(x, y, entries[k], wrapped[k], scale))
            y += used * pitch


# Kept module-level so the calibration editor's registry and any future preview
# reach the same dict the renderer reads (`conventions.md` § UI code style).
__all__ = ["TransferInfoDisplay", "_TUNEABLES_TRANSFER_VIEW"]

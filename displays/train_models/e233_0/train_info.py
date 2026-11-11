# SPDX-License-Identifier: MIT
"""E233-0 train-information (運行情報) page — one line's disruption notice.

Spec: `docs/wip/WIP_e233_0_display.md` § 15. A glossy pink pill reading
`運行情報 ／ Train Information`, then one message: a bracketed headline
`【{line}　{status}】` over its body. Headline and body share one monospaced
full-width grid that wraps at a STRICT 22 characters, punctuation allowed to
open a line, and spans the screen edge to edge, as a real E233-0 does.

THE REFERENCES. Geometry follows the PHOTO (author, 2026-11-11: *"follow the IRL
shot, span full left right"*): `_references/lcd/e233_0/train-information-photo-ja.png`,
rectified onto the canvas by `_dev_scripts/_e233_lower_geometry.py --rectify`
with the divide anchored at 149. Colour follows the CAPTURE,
`train-information-ja.png` cropped to its screen (x 12..1349, y 0..1000), because
a photograph shifts colour: the photo's background reads (180,198,223) against
the panel's (213,223,239). Every `[measured]` figure came from that script.

PROTOTYPE. The message comes from the authored pool
`data/train_info_pool.json`. § 15.3's build order puts the rare-turn share,
the live fetch and the CP932 bake after this page, so this module draws the
message it is handed and decides nothing about which one or when.
"""

import json
import re
import unicodedata

import pygame

from app_paths import project_root
from displays.train_models.e233_0 import LOWER_BG, S_HEIGHT, S_WIDTH, UPPER_HEIGHT
from displays.train_models.e233_0.transfer_info import glossy_pill
from displays.train_models.e233_0.upper_lcd import _cell_scale, _render_cells
from font_atlas import at, lcd_font, lit

_POOL = "data/train_info_pool.json"

_GRID_FACE = "ShinGoPr6N-Medium.otf"
_LABEL_JA_FACE = "ShinGoPr6N-Medium.otf"
_LABEL_EN_FACE = "HelveticaNeue-Roman.otf"

# fmt: off
_TUNEABLES_TRAIN_INFO = {
    # ---- the pill ---------------------------------------------------------
    # The same glossy shape as the のりかえ banner, so it is drawn by the same
    # function. [measured] BOX off the photo: x 169.0..481.0, y 159.3..185.0 —
    # 5.0 right of the canvas centre, kept as measured. The photo's own shading
    # (pale on top, deepest at the bottom edge) is not taken; the COLOURS are the
    # capture's, the darkest and palest rows of its walk at x 145 and x 300.
    "pill_cx":       325.0,
    "pill_w":        312.0,
    "pill_h":         25.7,
    "pill_top":      159.3,
    "pill_edge":  (223, 82, 155),
    "pill_mid":   (248, 199, 234),
    "pill_flat":       0.22,  # the capture's dark holds ~3px before the ramp
    # ---- the pill's label: 運行情報 ／ Train Information --------------------
    # Three runs, each placed by its INK centre, as the のりかえ label is.
    # [measured] off the photo; both sizes agree with the capture's, where
    # 運行情報 steps 19.0 a character and Train Information runs 141 against 142.
    "label_ja":       "運行情報",
    "label_ja_size":     19,
    "label_ja_cx":      233.5,
    "label_slash":    "／",
    "label_slash_cx":   281.6,
    "label_cy":         173.5,
    # HelveticaNeue-Roman because only it reaches the capture's width/height
    # ratio of 9.9 at this height: ShinGo, HelveticaNeue-Medium and Frutiger
    # Bold all run 10.4..11.2. Its coverage reads lighter than the capture's
    # (0.340 against 0.389), so the face is still § 15.3's last OPEN.
    "label_en":       "Train Information",
    "label_en_size":     19,
    "label_en_cx":      374.0,
    "label_color":   (0, 0, 0),
    # ---- the grid ---------------------------------------------------------
    # [measured] off the photo. Pitch 28.14, the same in the body (直 -> ム over
    # 11 cells, 相 -> ム over 14) and the headline (鉄 -> せ over 12). Headline and
    # body share one left edge: their 相 centres agree to 0.15. Cell 0 starts
    # at 8.8, so 22 cells end at 627.9 — the screen edge to edge.
    "grid_x":           8.8,
    "head_x":           8.8,
    "cell_adv":        28.14,
    "cols":            22,       # SETTLED, strict — see the module docstring
    "grid_size":       28,       # a CJK advance is the em
    # Surface TOPS of the rows, not ink tops: a row positioned by its surface
    # keeps its baseline whatever characters it carries. Fitted by moving our
    # render's ink onto the photo's (headline 211.5, body rows 247.5 / 283.0 /
    # 319.0) under the same `--rows` probe.
    "head_top":       210.0,
    "body_top":       246.0,
    "line_pitch":      36.0,     # [measured] 36.25 / 35.75 / 36.0, headline included
    # Five, because a sixth row would run into the bottom-right page counter
    # (photo: y 436.5..473.5), which the IRL layout keeps clear.
    "max_body_lines":   5,
    "text_color":    (0, 0, 0),
    # Alpha at or above which a pixel is ink, matching the sibling pages.
    "ink_min_alpha":  110,
}
# fmt: on

# The whole lower region — this page's hit-test and calibration-editor rect.
TRAIN_INFO_RECT = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)

# What the grid draws: the pool's three fields, plus the brackets and the
# full-width space the headline composes around them.
_GRID_DRAWS = (
    at(f"{_POOL}:messages[].line", f"{_POOL}:messages[].status", f"{_POOL}:messages[].body"),
    lit("【", "】", "　"),
)
_DRAWS = {
    "grid": (_GRID_FACE, _GRID_DRAWS),
    "label_ja": (_LABEL_JA_FACE, lit(_TUNEABLES_TRAIN_INFO["label_ja"], _TUNEABLES_TRAIN_INFO["label_slash"])),
    "label_en": (_LABEL_EN_FACE, lit(_TUNEABLES_TRAIN_INFO["label_en"])),
}


_FIELDS = ("line", "status", "body")


def load_pool() -> list:
    """The pool's messages, `[{"line", "status", "body"}, ...]`.

    A missing file, or an entry without all three non-empty strings, raises at
    load, naming the entry. The pool is what the page shows when nothing live
    is available, so a fault in it is a packaging fault: loud at startup, never
    a KeyError at the first draw mid-drive. `validate_data.check_train_info_pool`
    holds the same line before a build.
    """
    with open(project_root() / _POOL, encoding="utf-8") as f:
        messages = json.load(f)["messages"]
    for i, m in enumerate(messages):
        if not isinstance(m, dict) or not all(isinstance(m.get(k), str) and m[k] for k in _FIELDS):
            raise ValueError(f"{_POOL}: messages[{i}] needs non-empty strings {'/'.join(_FIELDS)}, got {m!r}")
    return messages


def _clean(text: str) -> str:
    """`text` without control or format characters.

    A newline, tab or zero-width character has no glyph, yet on a cell grid it
    would still take a cell, and in a shipped build it is a character the atlas
    never baked. Scraped text is where they arrive, so every message passes
    through here on its way to the grid.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf"))


def _rows(text: str, cols: int) -> list:
    """`text` cut every `cols` characters, with no line-start rule."""
    return [text[i : i + cols] for i in range(0, len(text), cols)] or [""]


def layout(line: str, status: str, body: str, cols: int, max_body_lines: int) -> tuple:
    """`(head_rows, body_rows)` for one message — the page's whole text layout.

    The headline is `【{line}　{status}】`, both verbatim from the source. Rows
    are a strict `cols`-character count, so 、 or 。 may open a row.

    A body longer than the panel keeps the WHOLE SENTENCES that fit and drops
    the rest, since the first sentence carries the disruption (§ 15.3). A first
    sentence that alone overflows is cut at the panel. A headline that wraps
    pushes the body down, so each extra headline row costs one body row.
    """
    line, status, body = _clean(line), _clean(status), _clean(body)
    head = _rows(f"【{line}　{status}】", cols)
    budget = max(1, max_body_lines - (len(head) - 1))
    rows = _rows(body, cols)
    if len(rows) <= budget:
        return head, rows
    kept = ""
    for sentence in re.findall(r"[^。]*。|[^。]+$", body):
        if len(_rows(kept + sentence, cols)) > budget:
            break
        kept += sentence
    return head, (_rows(kept, cols) if kept else rows[:budget])


class TrainInfoDisplay:
    """The 運行情報 page. Draws `self.message`; see the module docstring."""

    def __init__(self, screen, route_data: dict, stops: list):
        self.screen = screen
        # Held, not read: the page does not depend on the route or the stop.
        self.route_data = route_data
        self.stops = stops
        self.state = None

        self.pool = load_pool()
        # None draws the pill alone. The rotation is to skip the page when there
        # is nothing to say (§ 15.3, no disruption no page); this only keeps an
        # empty pool from raising on construction.
        self.message = self.pool[0] if self.pool else None
        self._fonts: dict = {}
        self._cache: dict = {}

    def set_state(self, state) -> None:
        self.state = state

    def set_message(self, message: dict) -> None:
        """Show `message` (`{"line", "status", "body"}`) from the next frame."""
        self.message = message

    def messages(self) -> list:
        """The messages there are to show now; empty means no disruption, no page.

        The pool, which is also what § 15.3 shows when the live feed is switched
        off or unavailable.
        NOTE: deliberately pool-only until the live fetch lands (§ 15.3 build
        step 3). That step returns the live list here when a fetch has
        succeeded, empty when nothing is disrupted, and keeps the pool for the
        two cases above. The rotation reads only this method, so nothing else
        changes when it does.
        """
        return self.pool

    # ---- fonts + ink ------------------------------------------------------

    def _font(self, group: str, size: int):
        f = self._fonts.get((group, size))
        if f is None:
            face, draws = _DRAWS[group]
            f = lcd_font(face, size, draws=draws)
            self._fonts[(group, size)] = f
        return f

    def _cells(self, group: str, size: int, text: str, adv: float):
        """`(surface, pad)` from `_render_cells`, cached on the drawn string."""
        key = ("cells", group, size, text, adv)
        hit = self._cache.get(key)
        if hit is None:
            color = tuple(_TUNEABLES_TRAIN_INFO["text_color" if group == "grid" else "label_color"])
            hit = _render_cells(lambda s: self._font(group, s), size, text, adv, adv, color)
            self._cache[key] = hit
        return hit

    def _proportional(self, group: str, size: int, text: str):
        """Latin text rendered above the clipping threshold and resolved down,
        for the same reasons `_render_cells` does it for the grid."""
        key = ("prop", group, size, text)
        hit = self._cache.get(key)
        if hit is None:
            scale = _cell_scale(size)
            big = self._font(group, size * scale).render(text, True, tuple(_TUNEABLES_TRAIN_INFO["label_color"]))
            w, h = big.get_size()
            hit = pygame.transform.smoothscale(big, (max(1, round(w / scale)), max(1, round(h / scale))))
            self._cache[key] = hit
        return hit

    def _blit_ink_centred(self, surf: pygame.Surface, cx: float, cy: float) -> None:
        box = surf.get_bounding_rect(min_alpha=int(_TUNEABLES_TRAIN_INFO["ink_min_alpha"]))
        self.screen.blit(surf, (int(round(cx - box.centerx)), int(round(cy - box.centery))))

    # ---- drawing ----------------------------------------------------------

    def _draw_pill(self) -> None:
        t = _TUNEABLES_TRAIN_INFO
        w, h = float(t["pill_w"]), float(t["pill_h"])
        pill = glossy_pill(w, h, tuple(t["pill_edge"]), tuple(t["pill_mid"]), float(t["pill_flat"]))
        self.screen.blit(pill, (int(round(float(t["pill_cx"]) - w / 2.0)), int(round(float(t["pill_top"])))))

        size, cy = int(t["label_ja_size"]), float(t["label_cy"])
        for key in ("label_ja", "label_slash"):
            run, _pad = self._cells("label_ja", size, str(t[key]), float(size))
            self._blit_ink_centred(run, float(t[f"{key}_cx"]), cy)
        en = self._proportional("label_en", int(t["label_en_size"]), str(t["label_en"]))
        self._blit_ink_centred(en, float(t["label_en_cx"]), cy)

    def _draw_text(self) -> None:
        t = _TUNEABLES_TRAIN_INFO
        m = self.message
        head, body = layout(m["line"], m["status"], m["body"], int(t["cols"]), int(t["max_body_lines"]))
        size, adv, pitch = int(t["grid_size"]), float(t["cell_adv"]), float(t["line_pitch"])
        body_top = float(t["body_top"]) + (len(head) - 1) * pitch
        placed = [(row, float(t["head_x"]), float(t["head_top"]) + i * pitch) for i, row in enumerate(head)]
        placed += [(row, float(t["grid_x"]), body_top + i * pitch) for i, row in enumerate(body)]
        for row, x, top in placed:
            surf, pad = self._cells("grid", size, row, adv)
            self.screen.blit(surf, (int(round(x)) - pad, int(round(top))))

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Draw the whole page. Pure render — mutates nothing but the surface."""
        del current_time
        self.state = state
        # Chrome, never recoloured here (the CONTRACT in the model's
        # `__init__.py`); repeated so the page renders when driven directly.
        pygame.draw.rect(self.screen, LOWER_BG, TRAIN_INFO_RECT)
        self._draw_pill()
        if self.message is not None:
            self._draw_text()

    def draw(self, current_time: float = 0.0) -> None:
        self.show_stops(self.state, current_time)


__all__ = ["TrainInfoDisplay", "TRAIN_INFO_RECT", "_TUNEABLES_TRAIN_INFO", "layout", "load_pool"]

# SPDX-License-Identifier: MIT
"""Annotate the README hero: mark what the OCR reads and where it comes out.

    uv run --with pillow _dev_scripts/gen_readme_hero.py

    in   docs/assets/15-in-use.jpg          clean plate — game + app, no annotation
    out  docs/assets/15-in-use-ocr.jpg      what the README shows

Two translucent callouts over a screenshot of the game running with the app beside it:
the HUD region the reader crops, and the status band where that reading surfaces. The
point is that both numbers are visible in one frame and they agree — the game shows
24.7 km/h / 954 m, the band shows 24 / 962, a couple of frames behind.

THE HUD BOX IS DERIVED, NEVER TYPED. It comes from `auto_input.hud_layout`'s profile for
the plate's resolution, so if the HUD geometry moves the box follows. A hand-placed
rectangle would be right the day it was drawn and quietly point at scenery afterwards
(`principles.md` § "A second implementation of a production decision drifts silently").
Note `hud_bbox` is (x, y, w, h) and NOT corners — 2200 + 350 = 2550 on a 2560 desktop,
which is also how the driver logs it ("HUD 350x480").

THE BAND BOX CANNOT BE DERIVED and is authored below. It is wherever the author happened
to drag the app window when the screenshot was taken, which no code knows. Re-taking the
plate means re-measuring it; that is the cost of annotating a photograph rather than a
render, and it is why only this one number is hardcoded.

Dev-only; does not ship. Writes into docs/assets/ (tracked README images)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"

# fmt: off
PLATE          = ASSETS / "15-in-use.jpg"
PLATE_DESKTOP  = (2560, 1440)   # resolution the plate was captured at, for the profile lookup
ACCENT         = (255, 138, 43) # warm orange; reads over both sky and the dark cab
INK            = (255, 255, 255)
SCRIM          = (14, 18, 26)   # callout fill, composited at SCRIM_ALPHA
SCRIM_ALPHA    = 165            # "half opaque" — legible without hiding the frame
BOX_W          = 4              # marker outline
RULE_GUTTER    = 46             # column to the left of every row, holding its accent rule
GROUP_GAP      = 10             # between feature groups
# The app's status band, in PLATE pixel coords. Authored — see the docstring.
BAND_BOX       = (1199, 538, 1593, 598)
# The app window in PLATE coords. Panels are ASSERTED clear of it — covering the thing
# the screenshot exists to show is the one mistake that cannot be allowed through.
APP_WINDOW     = (1199, 528, 1600, 900)
FEAT_SIZE      = 28
TITLE_SIZE     = 21             # group headers; small caps-ish, accent colour
FEAT_LEAD      = 12             # gap between feature lines
FEAT_AT        = (60, 56)
STEPS_AT       = (1080, 300)    # right side, in the gap between the HUD box above and
# the app window below — beside the two things the sequence runs between
# fmt: on

# The feature list, set INTO the frame's empty sky rather than printed under it.
#
# STYLE: NOUN PHRASES, NO VERBS. This is a label layer over a photograph, and labels name
# things — a verb makes it read as prose that happens to be sitting on a picture. Each
# line is the Japanese term for the thing being reproduced plus a short English
# qualifier, which keeps the vocabulary the app and the railway both use. Anything
# needing a verb goes in the README under the image.
#
# 系 NOT 番台. Listing sub-series does not scale: with -1000 / -5000 / -7000 / -8000 due
# as skins, this line would grow to six entries and stop being a glance. The series
# scales, and the 番台 detail already lives per-model in the README's Screenshots
# headings, which is where someone looking for it would go.
# GROUPED BY THE WORKING PART OF THE APP, not by what-it-is versus what-it-does. The
# subsystems are what a reader is actually choosing between — someone here for the sound
# and someone here for the auto-drive are different people, and each should find their
# row without reading the others.
#
# The groups are TITLED. An earlier cut used a bare gap and left the reader to infer why
# three lines sat apart from three others, which is a puzzle rather than a glance.
#
# Order runs from the thing the project began as to the thing it grew into: audio was the
# original product, the display came second as a navigation aid, and the auto-drive is
# what it is now mostly used through.
#
# PLACEMENT IS THE BRIDGE between the steps panel and the photo — not numbering. The
# steps ran as numerals matched by numbered discs drawn on the HUD and the band, and the
# discs were cut: they collided at any radius that made the numeral legible, and a marker
# that has to be got exactly right to add anything is not worth the image being wrong.
# Author, after the third round of it: "if you can't get it right don't use it." What
# survives does the same job geometrically — the panel sits between the HUD box above and
# the app window below, so the sequence is beside the two things it runs between.
#
# The features panel is UNTITLED and the steps panel is TITLED. Titles earned their keep
# only where a group is a sequence the reader has to know is a sequence; three parallel
# features need no header telling them they are features.
#
# "OCR Auto-PA", NOT "Auto-drive". The app announces; the player drives. "Auto-drive"
# reads as autopilot and promises something this does not do — and OCR Auto-PA is the
# name the app itself uses (`setup_tims.tutorial.ocr`), so it is also the string a reader
# will meet on the PA-setting screen.
#
# Transfer info is NOT a line of its own: it is drawn by the LCD, so listing it separately
# split one feature into two and implied a second subsystem that does not exist.
# PER-LANGUAGE CONTENT. The README ships in three languages and the hero carries most of
# the copy, so a single English image would leave a zh reader looking at a picture they
# cannot read while the prose around it is translated.
#
# Terms come from the APP, not from a dictionary: OCR自動報站 / OCR自动报站 and 遠端控制 /
# 远程控制 are the strings on its own screens (`setup_tims.tutorial.ocr`,
# `setup_tims.stream.heading`), so a reader meets the same words in both places.
#
# 運転曲線 stays Japanese in all three. It is the heading the report itself prints, not a
# term being translated — the zh form 運轉曲線 would name something the reader never sees.
LANGS = {
    "en": {
        "out": "15-in-use-ocr.jpg",
        "features": [
            (
                None,
                [
                    "In-car Announcements and Departure Melodies",
                    "In-car LCD — E233系 · E235系",
                    "Remote Control from a Phone or Tablet",
                ],
            )
        ],
        "steps": [
            (
                "OCR Auto-PA",
                [
                    "Reads the game's HUD",
                    "Plays the announcement",
                    "Logs the 運転曲線",
                ],
            )
        ],
        "badges_label": "Supported Lines",
    },
    "zh-HK": {
        "out": "15-in-use-ocr.zh-HK.jpg",
        "features": [
            (
                None,
                [
                    "車內廣播同發車音樂",
                    "車內 LCD — E233系 · E235系",
                    "用手機或平板遠端控制",
                ],
            )
        ],
        "steps": [
            (
                "OCR自動報站",
                [
                    "讀取遊戲畫面",
                    "自動播放廣播",
                    "記錄運転曲線",
                ],
            )
        ],
        "badges_label": "對應路線",
    },
    "zh-CN": {
        "out": "15-in-use-ocr.zh-CN.jpg",
        "features": [
            (
                None,
                [
                    "车内广播与发车音乐",
                    "车内 LCD — E233系 · E235系",
                    "用手机或平板远程控制",
                ],
            )
        ],
        "steps": [
            (
                "OCR自动报站",
                [
                    "读取游戏画面",
                    "自动播放广播",
                    "记录運転曲線",
                ],
            )
        ],
        "badges_label": "支持的路线",
    },
}
FEAT_BADGES = ["JY", "JK", "JC", "JA", "JN", "JE", "JT", "JU", "JO"]
BADGE_PX = 34


def _hud_box(w: int, h: int) -> tuple[int, int, int, int]:
    """The profile's own HUD rect, scaled from its desktop size onto the plate."""
    sys.path.insert(0, str(ROOT))
    from auto_input.hud_layout import PROFILES

    p = PROFILES[PLATE_DESKTOP]
    x, y, bw, bh = p.hud_bbox
    sx, sy = w / p.desktop_w, h / p.desktop_h
    return (round(x * sx), round(y * sy), round((x + bw) * sx), round((y + bh) * sy))


def _panel(base: Image.Image, groups: list, at: tuple[int, int], *, badges: str | None = None) -> tuple[int, int, int, int]:
    """One translucent slab of titled rows, its top-left at `at`.

    TWO PANELS, not one. The features are things the app HAS and can be read in any
    order; the OCR Auto-PA steps are a sequence that happens somewhere you can point at.
    Mixing them in one column made the sequence look like three more bullets. Split, the
    steps panel can also sit on the RIGHT, between the HUD box it reads and the status
    band it writes — so the sequence is next to the things it describes.

    One slab, not a pill per line: four separate pills over a photograph read as clutter,
    and a single block gives every line the same backdrop, so contrast does not change
    with whatever happens to be behind it.

    A CJK-capable face is REQUIRED — these strings carry 車内放送 / 発車メロディ / 運転曲線,
    and HelveticaNeue (what the numbered callouts use) has no glyphs for them and would
    render tofu SILENTLY, since PIL does not raise on a missing glyph.

    `NotoSansJP.otf` is the obvious pick and is the WRONG one: it ships at weight Thin,
    which is right for the TIMS chrome it was added for and far too light over a
    photograph. The Bold CJK face is used instead. It is the SC regional cut, so the
    rendered kanji were checked by eye against the JP forms for these exact strings
    before it was settled on — a regional variant can differ on shared codepoints, and
    nothing in the pipeline would flag it.
    """
    f = ImageFont.truetype(str(ROOT / "fonts" / "NotoSansCJKsc-Bold.otf"), FEAT_SIZE)
    ft = ImageFont.truetype(str(ROOT / "fonts" / "NotoSansCJKsc-Bold.otf"), TITLE_SIZE)
    d0 = ImageDraw.Draw(base)
    line_h = FEAT_SIZE + FEAT_LEAD
    title_h = TITLE_SIZE + FEAT_LEAD + 6
    pad = 26

    items = [t for _, g in groups for t in g]
    # ONE text column for every row — titles, items and the badge label all start at the
    # same x, with a fixed-width gutter to its left carrying each row's accent rule. The
    # gutter is a constant rather than derived from the rule, so a title row and an item
    # row line up instead of the text stepping in and out down the panel.
    text_x = pad + RULE_GUTTER
    label_w = round(d0.textlength((badges or "").upper(), font=ft)) + 16 if badges else 0

    w = text_x + round(max(d0.textlength(t, font=f) for t in items)) + pad
    h = pad + sum((title_h if t else 0) + len(g) * line_h + GROUP_GAP for t, g in groups) + pad
    if badges:
        w = max(w, text_x + label_w + len(FEAT_BADGES) * (BADGE_PX + 7) + pad)
        h += BADGE_PX + 18

    slab = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ds = ImageDraw.Draw(slab)
    ds.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=(*SCRIM, SCRIM_ALPHA))

    y = pad
    for title, group in groups:
        if title:
            ds.text((text_x, y), title.upper(), font=ft, fill=ACCENT)
            y += title_h
        for t in group:
            # Centre the rule on the TEXT'S MEASURED INK, not on a guessed fraction of
            # the font size. The guess (y + FEAT_SIZE//2 + 2) put every dash 5-8px high,
            # and the error changed per row because ink height varies with descenders and
            # with CJK glyphs. textbbox is the only thing that knows where the ink is.
            bb = ds.textbbox((0, y), t, font=f)
            cy = (bb[1] + bb[3]) // 2
            ds.line((pad + 4, cy, pad + RULE_GUTTER - 18, cy), fill=ACCENT, width=3)
            ds.text((text_x, y), t, font=f, fill=INK)
            y += line_h
        y += GROUP_GAP

    if badges:
        y = h - pad - BADGE_PX
        ds.text((text_x, y + (BADGE_PX - TITLE_SIZE) // 2 - 1), badges.upper(), font=ft, fill=ACCENT)
        bx = text_x + label_w
        for code in FEAT_BADGES:
            icon = Image.open(ROOT / "data" / "line_icons" / f"{code}.png").convert("RGBA")
            slab.alpha_composite(icon.resize((BADGE_PX, BADGE_PX), Image.LANCZOS), (bx, y))
            bx += BADGE_PX + 7

    base.alpha_composite(slab, at)
    return (at[0], at[1], at[0] + w, at[1] + h)


def _render(lang: str, spec: dict) -> int:
    im = Image.open(PLATE).convert("RGBA")
    hud = _hud_box(im.width, im.height)

    d = ImageDraw.Draw(im)
    d.rectangle(hud, outline=ACCENT, width=BOX_W)
    d.rectangle(BAND_BOX, outline=ACCENT, width=BOX_W)

    # NO NUMBERED DISCS and no connecting arrow. Both were tried and cut: at any radius
    # that fitted the line spacing the numerals were too small to read, and on the photo
    # they landed on top of the status bar they were meant to mark. The two accent boxes
    # already show where the reading comes from and where it surfaces.
    rects = [
        _panel(im, spec["features"], FEAT_AT, badges=spec["badges_label"]),
        _panel(im, spec["steps"], STEPS_AT),
    ]
    # The screenshot exists to show the app. A panel covering it is the one failure that
    # must not ship, so it is asserted rather than eyeballed — the text length changes per
    # language, and a longer translation silently growing a panel over the window is
    # exactly the kind of thing nobody would notice until it was published.
    for r in rects:
        if r[0] < APP_WINDOW[2] and r[2] > APP_WINDOW[0] and r[1] < APP_WINDOW[3] and r[3] > APP_WINDOW[1]:
            print(f"ERROR [{lang}]: panel {r} covers the app window {APP_WINDOW}", file=sys.stderr)
            return 1
        if r[2] > im.width or r[3] > im.height:
            print(f"ERROR [{lang}]: panel {r} runs off the {im.width}x{im.height} canvas", file=sys.stderr)
            return 1

    out = ASSETS / spec["out"]
    im.convert("RGB").save(out, quality=92, optimize=True)
    print(f"  {lang:<6} {out.name:<28} {im.width}x{im.height}  {out.stat().st_size / 1e3:.0f} KB")
    return 0


def main() -> int:
    if not PLATE.exists():
        print(f"ERROR: plate not found: {PLATE}", file=sys.stderr)
        return 1
    rc = 0
    for lang, spec in LANGS.items():
        rc |= _render(lang, spec)
    return rc


if __name__ == "__main__":
    sys.exit(main())

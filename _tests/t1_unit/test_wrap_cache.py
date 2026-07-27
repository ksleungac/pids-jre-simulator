# TIER: T1 — the consent-body wrap cache never changes the answer
"""Guards the #60 memoization of `ocr_setting._wrap`.

The consent view rebuilds its whole body every frame, and `_wrap` measured
`font.size()` once per character — 1737 calls per build, 48% of the frame cost,
all re-deriving identical line breaks. It is now cached on (font, max_w, text).

The failure that buys is a stale hit: a key that drops `max_w` returns the
previous column's breaks, and one that drops `font` returns another locale's.
Both render as silently wrong text with no error anywhere.

Oracle is the uncached function itself: clear the cache, take the answer, then
warm it with competing keys and ask again. Same inputs must give the same lines
whatever else the cache holds.

Discriminator: drop `max_w` from the key in `_wrap` and case (2) fails; drop
`font` and case (3) fails.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame  # noqa: E402

import i18n  # noqa: E402
import tims.setup.ocr_setting as oc  # noqa: E402

# Latin (has word boundaries to backtrack over) + CJK (breaks at the column edge).
LATIN = "Windows graphics settings let you force the app onto the integrated GPU."
CJK = "本功能透過螢幕擷取辨識遊戲畫面上的速度與距離，並據此自動播放廣播。"


def uncached(text, font, max_w):
    oc._WRAP_CACHE.clear()
    return list(oc._wrap(text, font, max_w))


def main():
    pygame.init()
    pygame.font.init()
    i18n.init("zh_HK")
    font_hk = i18n.pixel_font_for_lang("zh_HK", oc.BODY_NATIVE)
    # A SIZE difference, not a locale difference. The per-locale Noto faces carry identical
    # advances for these glyphs, so zh_HK vs zh_CN at one size wraps the same and cannot tell
    # whether `font` is in the key at all — that version of this test passed with `font` removed.
    font_big = i18n.pixel_font_for_lang("zh_HK", oc.TITLE_NATIVE)

    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # --- (1) a warm cache returns the same lines as a cold one ---
    want = uncached(LATIN, font_hk, 300)
    oc._wrap(LATIN, font_hk, 300)  # warm
    check(oc._wrap(LATIN, font_hk, 300) == want, "a cache HIT must equal the cold-path result")
    check(len(want) > 1, f"fixture must actually wrap at 300px (else the test proves nothing); got {len(want)} line(s)")

    # --- (2) width is part of the key: a narrow column must not serve a wide one ---
    narrow = uncached(LATIN, font_hk, 200)
    wide = uncached(LATIN, font_hk, 600)
    check(narrow != wide, f"fixture widths must differ to discriminate; both gave {len(narrow)} line(s)")
    oc._WRAP_CACHE.clear()
    oc._wrap(LATIN, font_hk, 200)  # warm with the NARROW column first
    check(oc._wrap(LATIN, font_hk, 600) == wide, "a warm narrow-column entry must not be served for a wide column")

    # --- (3) font is part of the key: one face must not serve a different one ---
    small = uncached(CJK, font_hk, 260)
    big = uncached(CJK, font_big, 260)
    check(small != big, f"fixture fonts must wrap differently to discriminate; both gave {len(small)} line(s)")
    oc._WRAP_CACHE.clear()
    oc._wrap(CJK, font_hk, 260)  # warm with the BODY face first
    check(oc._wrap(CJK, font_big, 260) == big, "a warm body-font entry must not be served for the title font")
    check(oc._wrap(CJK, font_hk, 260) == small, "the body-font entry must still be correct after the title font is cached")

    # --- (4) the runaway backstop clears rather than growing without bound ---
    oc._WRAP_CACHE.clear()
    for n in range(oc._WRAP_CACHE_MAX + 5):
        oc._wrap(f"filler {n}", font_hk, 300)
    check(len(oc._WRAP_CACHE) <= oc._WRAP_CACHE_MAX, f"cache must stay bounded; got {len(oc._WRAP_CACHE)} entries")
    check(oc._wrap(LATIN, font_hk, 300) == want, "a post-clear miss must still compute the right answer")

    if failures:
        print("FAIL: consent wrap cache")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: wrap cache keys on font + width (no stale hit across locale or column)")


if __name__ == "__main__":
    main()

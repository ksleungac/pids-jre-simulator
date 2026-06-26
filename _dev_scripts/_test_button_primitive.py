"""Headless stress test for the TIMS button + low-res text primitives (widgets.py).
No display needed — renders onto offscreen Surfaces and asserts: no crashes across edge cases,
sizing functions return sane positive values, responsive sizing holds (2 lines -> taller box).
    uv run _dev_scripts/_test_button_primitive.py
"""

import sys

import pygame

sys.path.insert(0, ".")

import i18n  # noqa: E402
from widgets import (  # noqa: E402
    _TUNEABLES_TIMS_BUTTON as T,
    draw_lowres_text,
    draw_tims_button,
    lowres_text_size,
    tims_button_size,
)

pygame.init()
pygame.font.init()
# zh_HK Ark pixel face covers both the CJK and Latin test labels; fonts arrive pre-resolved now.
FONT = i18n.pixel_font_for_lang("zh_HK", 12)
SURF = pygame.Surface((1400, 900), pygame.SRCALPHA)

LABELS = [
    "",
    "設",
    "設定",
    "列車選別",
    "運転情報\n画面",
    "運転士\nメニュー",
    "異常扱い",
    "初期\n選択",
    "応急マニ\nュアル",
    "SETTINGS",
    "TRAIN\nINFO",
    "A",
    "AB",
    "VERY LONG SINGLE LINE LABEL THAT OVERFLOWS A SMALL BOX",
    "三\n行\n目",
    "　",
    "\n",
    "A\n\nB",
    "12345678901234567890",
]
STATES = ["normal", "pressed", "waiting"]
RECTS = [
    (0, 0, 1, 1),
    (0, 0, 5, 5),
    (0, 0, 13, 13),
    (0, 0, 40, 24),
    (0, 0, 120, 70),
    (0, 0, 300, 150),
    (0, 0, 600, 80),
    (0, 0, 80, 300),
]

fails = []

# 1) draw_tims_button never crashes across labels x states x rects
for lab in LABELS:
    for st in STATES:
        for rc in RECTS:
            try:
                draw_tims_button(SURF, pygame.Rect(rc), lab, font=FONT, state=st)
            except Exception as e:  # noqa: BLE001
                fails.append(f"draw_tims_button({lab!r},{st},{rc}): {e!r}")

# 2) draw_lowres_text standalone never crashes
for lab in LABELS:
    for rc in RECTS:
        try:
            draw_lowres_text(SURF, lab, pygame.Rect(rc), FONT, (255, 255, 255))
        except Exception as e:  # noqa: BLE001
            fails.append(f"draw_lowres_text({lab!r},{rc}): {e!r}")

# 3) sizing functions: positive, >= min_w, sane
for lab in LABELS:
    if not lab.strip("\n　 "):
        continue
    w, h = tims_button_size(lab, FONT)
    if w <= 0 or h <= 0:
        fails.append(f"tims_button_size({lab!r}) -> {(w, h)} non-positive")
    if w < T["min_w"]:
        fails.append(f"tims_button_size({lab!r}) w {w} < min_w {T['min_w']}")
    tw, th = lowres_text_size(lab, FONT)
    if tw <= 0 or th <= 0:
        fails.append(f"lowres_text_size({lab!r}) -> {(tw, th)} non-positive")

# 4) responsive: a 2-line label yields a taller content box than the same text on 1 line
h1 = tims_button_size("設定", FONT)[1]
h2 = tims_button_size("設定\n設定", FONT)[1]
if not h2 > h1:
    fails.append(f"2-line box not taller: 1-line {h1}, 2-line {h2}")

# 5) a wider label -> wider content box (monotonic width)
w_short = tims_button_size("設", FONT)[0]
w_long = tims_button_size("設定列車選別", FONT)[0]
if not w_long > w_short:
    fails.append(f"wider label not wider box: {w_short} vs {w_long}")

# 6) determinism — same inputs render byte-identical (no Date/random in the path)
a = pygame.Surface((200, 100), pygame.SRCALPHA)
b = pygame.Surface((200, 100), pygame.SRCALPHA)
draw_tims_button(a, pygame.Rect(10, 10, 160, 80), "設定", font=FONT, state="pressed")
draw_tims_button(b, pygame.Rect(10, 10, 160, 80), "設定", font=FONT, state="pressed")
if pygame.image.tostring(a, "RGBA") != pygame.image.tostring(b, "RGBA"):
    fails.append("non-deterministic render for identical inputs")

# 7) hardening — a too-long label stays contained (clip + horizontal compression, no spill)
spill = pygame.Surface((400, 120), pygame.SRCALPHA)
box = pygame.Rect(150, 40, 100, 40)
draw_lowres_text(spill, "OVERFLOWING LONG LABEL 123456", box, FONT, (255, 255, 255))
for px, py in [(box.left - 6, box.centery), (box.right + 6, box.centery), (box.centerx, box.top - 6), (box.centerx, box.bottom + 6)]:
    if spill.get_at((px, py))[3] != 0:
        fails.append(f"text spilled outside area at {(px, py)}")

if fails:
    print(f"FAIL ({len(fails)} issues):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"PASS — {len(LABELS)} labels x {len(STATES)} states x {len(RECTS)} rects (no crashes), " "sizing sane, responsive + monotonic, deterministic.")

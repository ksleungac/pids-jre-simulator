# SPDX-License-Identifier: MIT
"""TIMS button-style sandbox — preview harness for the glossy raised bevel + low-res pixel text.
The primitives themselves GRADUATED to the production chrome module `widgets.py` (2026-06-24); this
file is now a thin montage that imports them and renders the button states / responsive sizing /
english cases for eyeballing. Iterate the look by nudging widgets._TUNEABLES_TIMS_BUTTON, re-run,
eyeball button_sandbox.png. The user is the visual judge.

Reference: tims_002.jpg (full TIMS cab console) + tims_button.png (設定 close-up).

Fonts come from i18n (the production per-locale pixel-face dispatch) so the preview matches what
ships — no system-font hatch. CJK labels use the zh_HK Ark face; English uses the Latin one.

    uv run _dev_scripts/button_style_sandbox.py
"""

import sys

import pygame

sys.path.insert(0, ".")

import i18n  # noqa: E402
from app_paths import project_root  # noqa: E402
from tims.widgets import (  # noqa: E402
    draw_lowres_text,
    draw_tims_button,
    tims_button_size,
)

ARK_NATIVE = 12  # the pixel face's native render grid


def main():
    pygame.init()
    pygame.font.init()

    cjk = i18n.pixel_font_for_lang("zh_HK", ARK_NATIVE)  # CJK montage labels
    latin = i18n.pixel_font_for_lang("en", ARK_NATIVE)  # english montage labels

    W, H = 980, 520
    surf = pygame.Surface((W, H))
    surf.fill((12, 26, 36))  # TIMS dark slate

    def cap(text, x, y):
        surf.blit(i18n.pixel_font_for_lang("zh_HK", 14).render(text, True, (150, 175, 190)), (x, y))

    # states — three button states, content-sized
    cap("states: normal / pressed / waiting", 26, 14)
    hw, hh = tims_button_size("設定", cjk)
    for i, st in enumerate(("normal", "pressed", "waiting")):
        draw_tims_button(surf, pygame.Rect(26 + i * (hw + 26), 34, hw, hh), "設定", font=cjk, state=st)

    # responsive — content-sized; a 2-line label gets a TALLER box, all text at the same k=2 size
    cap("responsive: 2 lines -> taller box, uniform pixel size, width hugs label", 26, 150)
    x = 26
    for lab in ["列車選別", "運転情報\n画面", "設定", "運転士\nメニュー", "異常扱い", "初期\n選択"]:
        w, h = tims_button_size(lab, cjk)
        draw_tims_button(surf, pygame.Rect(x, 172, w, h), lab, font=cjk)
        x += w + 12

    # point #1 — oversized box + short label: the multiplier climbs to fill (never stuck at 1×)
    cap("big box + short label -> multiplier fills it", 26, 300)
    draw_tims_button(surf, pygame.Rect(26, 322, 280, 150), "設定", font=cjk)

    # english uses the SAME low-res pixel face; a standalone label (no button) proves the primitive
    cap("english (same face) + standalone pixel text (no button)", 340, 300)
    ex = 340
    for lab in ["SETTINGS", "TRAIN\nINFO"]:
        w, h = tims_button_size(lab, latin)
        draw_tims_button(surf, pygame.Rect(ex, 322, w, h), lab, font=latin)
        ex += w + 12
    draw_lowres_text(surf, "READY", pygame.Rect(340, 440, 170, 44), latin, (210, 230, 240))

    out = str(project_root() / "button_sandbox.png")
    pygame.image.save(surf, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()

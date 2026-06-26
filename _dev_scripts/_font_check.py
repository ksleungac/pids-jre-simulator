"""DEV one-off — render the kanji from each Ark eval font and SAVE, to see tofu vs real glyphs.
uv run _dev_scripts/_font_check.py            # prints glyph-coverage
uv run _dev_scripts/_font_check.py --render   # also saves _font_render_test.png
"""

import sys

import pygame

sys.path.insert(0, ".")
from app_paths import project_root  # noqa: E402

pygame.font.init()
E = project_root() / "_dev_scripts" / "_fonts_eval"
FILES = {
    "12mono-ja": E / "ark-pixel-font-12px-monospaced-otf-v2026.05.07" / "ark-pixel-12px-monospaced-ja.otf",
    "12prop-ja": E / "ark-pixel-font-12px-proportional-otf-v2026.05.07" / "ark-pixel-12px-proportional-ja.otf",
    "16prop-ja": E / "ark-pixel-font-16px-proportional-otf-v2026.05.07" / "ark-pixel-16px-proportional-ja.otf",
    "16prop-zhhk": E / "ark-pixel-font-16px-proportional-otf-v2026.05.07" / "ark-pixel-16px-proportional-zh_hk.otf",
}
SAMPLE = "報知設定 恵比寿"
for name, p in FILES.items():
    f = pygame.font.Font(str(p), 16)
    have = {c: (f.metrics(c) or [None])[0] is not None for c in "報知設定恵比寿渋谷75"}
    missing = [c for c, ok in have.items() if not ok]
    print(f"{name:12} missing={missing or 'none'}")

if "--render" in sys.argv:
    rows = list(FILES.items())
    surf = pygame.Surface((520, 56 * len(rows)))
    surf.fill((26, 30, 38))
    label = pygame.font.Font(str(FILES["12mono-ja"]), 12)
    for i, (name, p) in enumerate(rows):
        y = i * 56
        f = pygame.font.Font(str(p), 40)
        surf.blit(label.render(name, False, (150, 162, 174)), (8, y + 22))
        g = f.render(SAMPLE, True, (236, 241, 246))  # AA ON, size 40
        surf.blit(g, (140, y + (56 - g.get_height()) // 2))
    out = str(project_root() / "_font_render_test.png")
    pygame.image.save(surf, out)
    print("saved", out)

"""DEV preview — the persistent TIMS top band driven by the OCR debug-panel mock scenarios.

Wires `setup_tims.band._render_topband` (status-driven) to the SAME mock `status` dicts that
`preview_debug_panel.py` feeds the old `draw_debug_panel`, so the band can be iterated against
realistic OCR states (boot / stopped / approaching / paused / fire). Lives under `_dev_scripts/`
because it reuses `preview_debug_panel`'s mock OCR states — a dev-only fixture.

Keys:  1-6 scenario   P pause   L language (en / zh_HK / zh_CN)   ESC/Q quit
Click: the band's Pause button toggles pause.

  uv run _dev_scripts/preview_band_ocr.py
  uv run _dev_scripts/preview_band_ocr.py --screenshot _band_ocr.png   (montage of ALL scenarios)
"""

import argparse
import sys
import time

import pygame

sys.path.insert(0, ".")

import i18n  # noqa: E402
from app_paths import project_root  # noqa: E402
from setup_tims import band  # noqa: E402  (production package — dev → prod import is allowed)
from preview_debug_panel import _STOPS, _MockState, _scenarios  # noqa: E402  (reuse the mock OCR states)

_LANGS = ("en", "zh_HK", "zh_CN")
FOOTER_H = 96
W = band.SCREEN_W  # 730 — band spans the full app width


def _footer(surf, font, label, paused, lang):
    surf.fill((30, 30, 36))
    pygame.draw.line(surf, (60, 60, 70), (0, 0), (surf.get_width(), 0), 1)
    surf.blit(font.render(f"{label}    [lang {lang}]", True, (220, 220, 220)), (12, 10))
    surf.blit(font.render("1-6 scenario   P pause   L language   ESC/Q quit", True, (160, 160, 160)), (12, 34))
    surf.blit(font.render("click the band Pause button to toggle pause", True, (160, 160, 160)), (12, 54))
    if paused:
        surf.blit(font.render("[PAUSED — OCR frozen]", True, (240, 200, 60)), (12, 74))


def _live(status, paused, fire_ts):
    """Overlay the live pause flag; stamp the fire ts to `fire_ts` = the moment the scenario was
    ENTERED (not now()), so the auto-played message ages out after its ~3 s window instead of being
    pinned fresh every frame — lets the flash-then-auto-clear be observed. Boot status stays empty."""
    live = {**status, "paused": paused} if status else status
    if live and "last_fire" in live:
        live["last_fire"] = {**live["last_fire"], "ts": fire_ts}
    return live or None


def _draw(window, footer_font, scenarios, idx, paused, lang, fire_ts):
    label, status, mock_state = scenarios[idx]
    hits = band._render_topband(window.subsurface((0, 0, W, band.BAND_H)), _live(status, paused, fire_ts), mock_state, _STOPS)
    _footer(window.subsurface((0, band.BAND_H, W, FOOTER_H)), footer_font, label, paused, lang)
    return hits


def _over_limit_case():
    """A synthetic OVER-SPEED scenario (speed > limit) — the imported mock set has none, but the band
    flashes the cell background red here, so the montage needs one to show it."""
    status = {
        "badge": "MOVING",
        "speed": 108,
        "speed_score": 0.95,
        "distance": 700,
        "distance_score": 0.9,
        "speed_limit": 95,
        "speed_limit_score": 0.92,
        "inferred_state": "CRUISING",
        "segment_start_stop": 2,
        "paused": False,
    }
    return ("7. OVER LIMIT — speed > limit (red cell flash)", status, _MockState(curr_stop=3, cnt_pa=1))


def _save_montage(path, scenarios, label_font):
    """Render EVERY scenario's band stacked into one tall PNG (the band per row + a caption strip),
    flash pinned ON so the yellow message strips + cyan limit cue are visible in the frozen frame.
    Each row uses the scenario's own `paused` flag so the paused case lights its Pause knob."""
    LABEL_H = 26
    GAP = 6
    row_h = band.BAND_H + LABEL_H + GAP
    surf = pygame.Surface((W, row_h * len(scenarios)))
    surf.fill((18, 18, 22))
    for i, (label, status, mock_state) in enumerate(scenarios):
        y = i * row_h
        sc_paused = bool(status.get("paused")) if status else False
        band._render_topband(surf.subsurface((0, y, W, band.BAND_H)), _live(status, sc_paused, time.time()), mock_state, _STOPS, force_flash_on=True)
        surf.blit(label_font.render(label, True, (205, 205, 210)), (12, y + band.BAND_H + 5))
    out = str(project_root() / path)
    pygame.image.save(surf, out)
    print(f"saved {out}  ({W}x{row_h * len(scenarios)}, {len(scenarios)} scenarios)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshot", metavar="PATH")
    args = ap.parse_args()
    pygame.init()
    pygame.font.init()
    i18n.init("zh_HK")
    band.ACTIVE_LANG = "zh_HK"
    scenarios = _scenarios()
    footer_font = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 14)
    win_h = band.BAND_H + FOOTER_H

    if args.screenshot:
        _save_montage(args.screenshot, scenarios + [_over_limit_case()], footer_font)
        return

    pygame.display.set_caption("OCR band preview")
    window = pygame.display.set_mode((W, win_h))
    clock = pygame.time.Clock()
    lang_idx, idx, paused = 1, 2, False
    fire_ts = time.time()
    running = True
    while running:
        hits = _draw(window, footer_font, scenarios, idx, paused, _LANGS[lang_idx], fire_ts)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_l:
                    lang_idx = (lang_idx + 1) % len(_LANGS)
                    band.ACTIVE_LANG = _LANGS[lang_idx]
                    i18n.set_language(_LANGS[lang_idx])
                elif pygame.K_1 <= event.key <= pygame.K_6:
                    ni = event.key - pygame.K_1
                    if ni < len(scenarios):
                        idx = ni
                        fire_ts = time.time()  # re-arm the fire chip so it flashes then auto-clears
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits and hits["pause"].collidepoint(event.pos):
                    paused = not paused
        clock.tick(30)
    pygame.quit()


if __name__ == "__main__":
    main()

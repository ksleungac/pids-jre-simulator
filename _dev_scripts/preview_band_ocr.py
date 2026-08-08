# SPDX-License-Identifier: MIT
"""DEV preview — the persistent TIMS top band driven by the OCR debug-panel mock scenarios.

Wires `tims.band.render` (status-driven) to a set of mock `status` dicts covering the
realistic OCR states (boot / stopped / approaching / paused / fire), so the band can be iterated
without the game. The mock fixtures (`_MockState` / `_STOPS` / `_scenarios`) are inlined below —
self-contained, dev-only.

Keys:  1-7 scenario   P pause   S save   L language (en / zh_HK / zh_CN)   ESC/Q quit
Click: the band's Pause / Save button. Save flashes the confirmation strip (generating → saved).

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
import tims.band as band  # noqa: E402  (the live OCR panel; dev preview reuses it)
from tims.setup import dims  # noqa: E402  (setup-window dims — for the preview width)

_LANGS = ("en", "zh_HK", "zh_CN")
FOOTER_H = 96
W = dims.SCREEN_W  # 730 — preview the band at the full app width


class _MockState:
    """Stand-in for `app.AppState` — only the fields the panel reads."""

    def __init__(self, curr_stop: int = 0, cnt_pa: int = 0) -> None:
        self.curr_stop = curr_stop
        self.cnt_pa = cnt_pa


# Mock stops list — the panel only reads `name` on the row 3 station-name lookup.
_STOPS = [
    {"name": "高尾"},
    {"name": "西八王子"},
    {"name": "八王子"},
    {"name": "豊田"},
    {"name": "日野"},
    {"name": "立川"},
]


# Representative panel states. Each entry is (label, status_dict, mock_state).
def _scenarios() -> list[tuple[str, dict, _MockState]]:
    return [
        (
            "1. boot — no capture yet",
            {},
            _MockState(curr_stop=0, cnt_pa=0),
        ),
        (
            "2. stopped at platform (high confidence)",
            {
                "badge": "STOPPED",
                "badge_diff": 0.8,
                "speed": 0,
                "speed_score": 0.97,
                "distance": None,
                "distance_score": 1.0,
                "stopping_offset_cm": -3,
                "stopping_offset_score": 0.94,
                "speed_limit": 0,
                "speed_limit_score": 1.0,
                "departure_observed": True,
                "arrival_observed": True,
                "at_station_observed": True,
                "inferred_state": "STOPPED",
                "segment_start_stop": 4,
                "paused": False,
            },
            _MockState(curr_stop=5, cnt_pa=2),
        ),
        (
            "3. mid-approach (MOVING, dist 600m)",
            {
                "badge": "MOVING",
                "badge_diff": 1.4,
                "speed": 72,
                "speed_score": 0.93,
                "distance": 600,
                "distance_score": 0.95,
                "stopping_offset_cm": None,
                "stopping_offset_score": 1.0,
                "speed_limit": 95,
                "speed_limit_score": 0.92,
                "departure_observed": True,
                "arrival_observed": False,
                "at_station_observed": False,
                "inferred_state": "CRUISING",
                "segment_start_stop": 2,
                "paused": False,
            },
            _MockState(curr_stop=3, cnt_pa=1),
        ),
        (
            "4. mid-transit, low confidence (orange)",
            {
                "badge": "MOVING",
                "badge_diff": 11.5,
                "speed": 58,
                "speed_score": 0.78,
                "distance": 1850,
                "distance_score": 0.81,
                "stopping_offset_cm": None,
                "stopping_offset_score": 1.0,
                "speed_limit": 90,
                "speed_limit_score": 0.66,
                "departure_observed": True,
                "arrival_observed": False,
                "at_station_observed": False,
                "inferred_state": "CRUISING",
                "segment_start_stop": 1,
                "paused": False,
            },
            _MockState(curr_stop=2, cnt_pa=1),
        ),
        (
            "5. paused (frozen — last reading retained)",
            {
                "badge": "MOVING",
                "badge_diff": 1.2,
                "speed": 65,
                "speed_score": 0.91,
                "distance": 1200,
                "distance_score": 0.94,
                "stopping_offset_cm": None,
                "stopping_offset_score": 1.0,
                "speed_limit": 95,
                "speed_limit_score": 0.93,
                "departure_observed": True,
                "arrival_observed": False,
                "at_station_observed": False,
                "inferred_state": "CRUISING",
                "segment_start_stop": 2,
                "paused": True,
            },
            _MockState(curr_stop=3, cnt_pa=1),
        ),
        (
            "6. just departed — auto-played chip + (Passing)",
            {
                "badge": "PASSING",
                "badge_diff": 2.0,
                "speed": 88,
                "speed_score": 0.95,
                "distance": 2400,
                "distance_score": 0.9,
                "stopping_offset_cm": None,
                "stopping_offset_score": 1.0,
                "speed_limit": 100,
                "speed_limit_score": 0.9,
                "departure_observed": True,
                "arrival_observed": False,
                "at_station_observed": False,
                "inferred_state": "CRUISING",
                "segment_start_stop": 2,
                "last_fire": {"ts": 0.0, "type": "departure"},  # ts refreshed live in the loop
                "paused": False,
            },
            _MockState(curr_stop=3, cnt_pa=0),
        ),
        (
            "7. limit just changed (cyan flash then clears)",
            {
                "badge": "MOVING",
                "badge_diff": 1.3,
                "speed": 68,
                "speed_score": 0.94,
                "distance": 900,
                "distance_score": 0.92,
                "stopping_offset_cm": None,
                "stopping_offset_score": 1.0,
                "speed_limit": 45,
                "speed_limit_score": 0.95,
                "limit_change_ts": 0.0,  # refreshed to the scenario-enter ts in _live → flashes then clears
                "departure_observed": True,
                "arrival_observed": False,
                "at_station_observed": False,
                "inferred_state": "CRUISING",
                "segment_start_stop": 2,
                "paused": False,
            },
            _MockState(curr_stop=3, cnt_pa=1),
        ),
    ]


def _footer(surf, font, label, paused, lang):
    surf.fill((30, 30, 36))
    pygame.draw.line(surf, (60, 60, 70), (0, 0), (surf.get_width(), 0), 1)
    surf.blit(font.render(f"{label}    [lang {lang}]", True, (220, 220, 220)), (12, 10))
    surf.blit(font.render("1-7 scenario   P pause   S save   L language   ESC/Q quit", True, (160, 160, 160)), (12, 34))
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
    if live and "limit_change_ts" in live:
        live["limit_change_ts"] = fire_ts  # re-arm the cyan change-flash on scenario enter → flashes then clears
    return live or None


def _draw(window, footer_font, scenarios, idx, paused, lang, fire_ts, save_notice):
    label, status, mock_state = scenarios[idx]
    hits = band.render(window.subsurface((0, 0, W, band.BAND_H)), _live(status, paused, fire_ts), mock_state, _STOPS, save_notice=save_notice)
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
        band.render(surf.subsurface((0, y, W, band.BAND_H)), _live(status, sc_paused, time.time()), mock_state, _STOPS, force_flash_on=True)
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
    save_notice = None  # {ts, phase}; S / Save-button stamps "generating", auto-flips to "saved" after ~1.5 s
    running = True

    def _save_click():
        nonlocal save_notice
        save_notice = {"ts": time.time(), "phase": "generating"}

    while running:
        if save_notice and save_notice["phase"] == "generating" and time.time() - save_notice["ts"] > 1.5:
            save_notice = {"ts": time.time(), "phase": "saved"}  # mock async completion
        hits = _draw(window, footer_font, scenarios, idx, paused, _LANGS[lang_idx], fire_ts, save_notice)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_s:
                    _save_click()
                elif event.key == pygame.K_l:
                    lang_idx = (lang_idx + 1) % len(_LANGS)
                    band.ACTIVE_LANG = _LANGS[lang_idx]
                    i18n.set_language(_LANGS[lang_idx])
                elif pygame.K_1 <= event.key <= pygame.K_9:
                    ni = event.key - pygame.K_1
                    if ni < len(scenarios):
                        idx = ni
                        fire_ts = time.time()  # re-arm the fire chip so it flashes then auto-clears
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hits and hits["pause"].collidepoint(event.pos):
                    paused = not paused
                elif hits and hits["save"].collidepoint(event.pos):
                    _save_click()
        clock.tick(30)
    pygame.quit()


if __name__ == "__main__":
    main()

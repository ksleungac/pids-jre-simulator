"""Preview script for the auto-input debug panel.

Iterates the panel's visual design without the game running. Renders the actual
`draw_debug_panel` from auto_input.py against a set of mock status dicts that
cover the realistic states (boot / running / paused / etc.).

Keys:
    1-5    switch scenario
    P      toggle pause (same effect as clicking the Pause button)
    ESC/Q  quit

Click:
    Pause  / Report buttons work — Pause flips the mock driver's state, Report
    just prints (no real drive log to render).
"""

from __future__ import annotations

import sys

import pygame

from app_paths import project_root
from auto_input import draw_debug_panel, handle_panel_click
from constants import DEBUG_PANEL_HEIGHT

PANEL_W = 730
FOOTER_H = 90
WIN_W = PANEL_W
WIN_H = DEBUG_PANEL_HEIGHT + FOOTER_H


class _MockState:
    """Stand-in for `app.AppState` — only the fields the panel reads."""

    def __init__(self, curr_stop: int = 0, cnt_pa: int = 0) -> None:
        self.curr_stop = curr_stop
        self.cnt_pa = cnt_pa


class _MockDriver:
    """Stand-in for AutoDriver — only the .paused field the click handler toggles."""

    paused: bool = False


class _MockSim:
    """Minimal duck-typed PASimulator for handle_panel_click."""

    def __init__(self) -> None:
        self.auto_driver = _MockDriver()
        self.drive_log_path = None


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
    ]


def _draw_footer(surface: pygame.Surface, font: pygame.font.Font, label: str, paused: bool) -> None:
    """Render the preview chrome below the panel."""
    surface.fill((30, 30, 36))
    pad = 12
    pygame.draw.line(surface, (60, 60, 70), (0, 0), (surface.get_width(), 0), 1)
    surface.blit(font.render(label, True, (220, 220, 220)), (pad, pad))
    hint1 = "Keys:  1-5 switch scenario   P toggle pause   ESC/Q quit"
    hint2 = "Click: Pause / Report buttons on the panel above"
    surface.blit(font.render(hint1, True, (160, 160, 160)), (pad, pad + 24))
    surface.blit(font.render(hint2, True, (160, 160, 160)), (pad, pad + 44))
    if paused:
        tag = "  [DRIVER PAUSED — click Pause again to resume]"
        surface.blit(font.render(tag, True, (240, 140, 60)), (pad, pad + 64))


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Debug-panel preview")
    window = pygame.display.set_mode((WIN_W, WIN_H))
    clock = pygame.time.Clock()
    footer_font = pygame.font.Font(str(project_root() / "fonts" / "ShinGoPr6N-Medium.otf"), 14)

    sim = _MockSim()
    scenarios = _scenarios()
    idx = 1  # default to "stopped at platform" — most informative

    panel_surface = window.subsurface((0, 0, PANEL_W, DEBUG_PANEL_HEIGHT))
    footer_surface = window.subsurface((0, DEBUG_PANEL_HEIGHT, WIN_W, FOOTER_H))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_p:
                    sim.auto_driver.paused = not sim.auto_driver.paused
                elif pygame.K_1 <= event.key <= pygame.K_5:
                    new_idx = event.key - pygame.K_1
                    if new_idx < len(scenarios):
                        idx = new_idx
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if event.pos[1] < DEBUG_PANEL_HEIGHT:
                    handle_panel_click(sim, event.pos)

        label, status, mock_state = scenarios[idx]
        # Override the scenario's `paused` with the live driver flag — clicking
        # Pause should affect any scenario, not only the "5. paused" one.
        live_status = {**status, "paused": sim.auto_driver.paused} if status else status
        draw_debug_panel(panel_surface, live_status, mock_state, _STOPS)
        _draw_footer(footer_surface, footer_font, label, sim.auto_driver.paused)
        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    sys.exit(main())

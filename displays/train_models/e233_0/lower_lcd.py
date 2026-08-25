# SPDX-License-Identifier: MIT
"""E233-0 (中央線快速) Lower LCD — PLACEHOLDER.

None of the three lower views is specced yet: the full-route drill-down comes
after the upper LCD's elements (``docs/wip/WIP_e233_0_display.md`` § 3 build
order). This module exists so the model is constructible and its upper band can
be previewed and calibrated — it draws the lower background and the screen
border it owns, and nothing else.

Every renderer slot points at ONE placeholder. That is deliberate rather than
lazy: leaving a slot bound to an E235 renderer is how a fork silently inherits a
sibling model's view (``conventions.md`` § "Inherited slot/manager infra leaks
parent bindings"). A visibly empty view is a state the author can see; a
borrowed one is not.
"""

from typing import Optional

import pygame

from displays.lower_lcd import LowerDisplayBase

from displays.train_models.e233_0 import (
    S_WIDTH,
    S_HEIGHT,
    UPPER_HEIGHT,
    LOWER_BG,
    RULE_GREY,
    BORDER_W,
)


class _PendingView:
    """Stands in for a renderer whose drill-down has not happened.

    Carries the interface the manager and the preview harness reach for — a
    ``screen`` the preview rebinds on resize, and ``set_state`` — and draws
    nothing.
    """

    def __init__(self, screen):
        self.screen = screen
        self._state = None

    def set_state(self, state) -> None:
        self._state = state

    def draw(self, *args, **kwargs) -> None:
        pass

    def hit_test(self, state, mx: int, my: int) -> Optional[int]:
        return None

    def _resolve_transfers(self, name: str) -> list:
        """No transfers resolve while there is no transfer view.

        The slot cycle asks this to decide whether the TRANSFER slot is
        available at a stop; an empty list keeps that slot out of the rotation
        entirely, which is the honest answer until the view is built.
        """
        return []


class LowerDisplay(LowerDisplayBase):
    """E233-0 lower LCD manager. Slot cycle inherited; no views built yet."""

    # Stations-from-terminus below which the view locks to the zoomed slot.
    # Inherited value, not a measured one — it belongs to the full-route
    # drill-down and is here only so the base's contract check passes.
    LOCK_THRESHOLD = 8

    def __init__(self, screen, route_data, stops, mode_cycler):
        super().__init__(screen, route_data, stops, mode_cycler)

        placeholder = _PendingView(screen)
        self.japanese_display = placeholder
        self.japanese_eight_display = placeholder
        self.english_display = placeholder
        self.transfer_display = placeholder

    def _pick_renderer(self, mode):
        """One renderer for every mode and slot until the views are built."""
        return self.japanese_display

    def draw(self, current_time: float) -> None:
        """Lower background plus the screen border this half owns."""
        area = pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, S_HEIGHT - UPPER_HEIGHT)
        pygame.draw.rect(self.screen, LOWER_BG, area)

        # Border: this half owns left, right and bottom (the upper band draws
        # top, left and right of its own region).
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(0, UPPER_HEIGHT, BORDER_W, area.height))
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(S_WIDTH - BORDER_W, UPPER_HEIGHT, BORDER_W, area.height))
        pygame.draw.rect(self.screen, RULE_GREY, pygame.Rect(0, S_HEIGHT - BORDER_W, S_WIDTH, BORDER_W))

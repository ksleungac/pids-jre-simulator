"""E235-1000 transfer-info display (concrete).

Renders the resolved transfer list onto the lower LCD area
(S_WIDTH × (S_HEIGHT − UPPER_HEIGHT) = 730 × 303), positioned right
below the upper LCD. The actual drawing is currently delegated to
``preview_transfers.render_transfer`` — scaffolding while we tune the
visual layout. See ``WIP_transfer_display.md`` § "Open follow-ups" for
the promotion plan.
"""

from typing import List

import pygame

from displays.train_models.e235_1000 import S_WIDTH, S_HEIGHT, UPPER_HEIGHT
from displays.transfer_info import TransferInfoDisplay as _BaseTransferInfoDisplay


class TransferInfoDisplay(_BaseTransferInfoDisplay):
    """E235-1000-specific transfer-info renderer.

    Subclass exists from day one (rather than only when a 2nd train
    model lands) so the parent/child split is real, not aspirational —
    and so future train models drop in by mirroring this file.
    """

    def _render(self, transfers: List[str], current_time: float) -> None:
        del current_time  # not used yet — animations may consume it later

        # Lower-LCD sub-surface: render_transfer paints (0,0)-relative within
        # this region, so it lands directly under the upper LCD without
        # caller-side coordinate math.
        lower_h = S_HEIGHT - UPPER_HEIGHT
        sub = self.screen.subsurface(pygame.Rect(0, UPPER_HEIGHT, S_WIDTH, lower_h))

        # render_transfer's blueprint algorithm calls max() on derived row
        # sums — an empty transfers list crashes it. Bail early with a blank
        # white fill (matches lower-LCD WHITE_BG); the cycle still rotates
        # past this slot in 6 s. Pending UX decision on whether the cycle
        # should skip this slot entirely for no-transfer stations.
        if not transfers:
            sub.fill((255, 255, 255))
            return

        # SCAFFOLDING: import the renderer from preview_transfers while we
        # tune visuals. Promote to displays/transfer_info.py (or a sibling
        # render module) once the layout stabilizes — see
        # WIP_transfer_display.md § "Open follow-ups" #0.
        from preview_transfers import render_transfer

        render_transfer(sub, transfers, self.lines)

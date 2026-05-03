"""Transfer-info display base class (model-agnostic).

Resolves the per-stop transfer list each frame: looks up the current
station in ``data/stations.json``, applies the active-line filter
(drops slugs whose badges include the route's own ``line_code``), then
applies any per-station view drop/edit ops keyed by the route's
``transfer_view``. The resolved slug list is handed to ``_render``,
which subclasses implement per train model.

The renderer itself currently lives in ``preview_transfers`` —
imported lazily by subclasses while we tune visuals. Promotion to a
permanent home is tracked in ``WIP_transfer_display.md``.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional


def _project_root() -> Path:
    """Project root, both in dev and PyInstaller frozen builds.

    Mirrors ``displays.train_models.e235_1000.upper_lcd.get_base_dir`` —
    when that helper is promoted to ``displays/utils.py`` per its TODO,
    consolidate this one too.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # displays/transfer_info.py → repo root (2-parent climb).
    return Path(__file__).resolve().parent.parent


class TransferInfoDisplay:
    """Base class for the lower-LCD transfer-info view.

    Subclasses (per train model) implement ``_render`` to draw the
    resolved transfer list. The base handles state binding, station
    lookup, filter application, and the public LCD interface.
    """

    def __init__(self, screen, route_data: dict, stops: list):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        root = _project_root()
        self.lines = json.loads((root / "data" / "lines.json").read_text(encoding="utf-8"))
        self.stations = json.loads(
            (root / "data" / "stations.json").read_text(encoding="utf-8")
        )

        # Route-level filter knobs read once. Both optional — absent means
        # "no filtering" (renders raw transfers list). Out-of-spec routes
        # without these fields still get a best-effort render per CLAUDE.md
        # "Per-model IRL line scope" soft floor.
        self.line_code: Optional[str] = route_data.get("line_code")
        self.transfer_view: Optional[str] = route_data.get("transfer_view")
        self._state = None

    def set_state(self, state) -> None:
        """Bind to an AppState instance; subsequent show_stops reads live state."""
        self._state = state

    def _resolve_badges(self, slug_ref: str) -> list:
        """Look up badges for a slug_ref via lines.json + variant resolution.

        Lazy import from ``preview_transfers`` to keep the resolution
        rule single-sourced while the renderer is still being tuned in
        the preview script. Promote when the renderer is promoted.
        """
        from preview_transfers import resolve_entry

        return resolve_entry(slug_ref, self.lines).get("badges", [])

    def _resolve_transfers(self, station_name: str) -> List[str]:
        """Return the post-filter / post-view-edit slug_ref list for a station.

        Empty when the station has no transfers entry, or when filtering
        wipes everything out. Mirrors ``preview_transfers.main``'s filter
        order: active-line filter first, then view drops, then view edits.
        """
        sd = self.stations.get(station_name, {})
        transfers = list(sd.get("transfers", []))

        if self.line_code:
            transfers = [
                ref
                for ref in transfers
                if not any(
                    b.get("code") == self.line_code for b in self._resolve_badges(ref)
                )
            ]

        if self.transfer_view:
            view_ops = sd.get("transfers_by_view", {}).get(self.transfer_view, {})
            dropset = set(view_ops.get("drop", []))
            if dropset:
                transfers = [
                    r for r in transfers if r.split(".", 1)[0] not in dropset
                ]
            editmap = view_ops.get("edit", {})
            if editmap:
                transfers = [editmap.get(r.split(".", 1)[0], r) for r in transfers]

        return transfers

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the transfer-info frame for the current stop.

        Public interface mirrors the other lower-LCD renderers
        (JapaneseDisplay / JapaneseEightStationDisplay) so LowerDisplay
        can dispatch to any of them uniformly.
        """
        if state is None:
            return
        sim_curr_stop = state.curr_stop
        if not (0 <= sim_curr_stop < len(self.stops)):
            return
        station_name = self.stops[sim_curr_stop].get("name", "")
        transfers = self._resolve_transfers(station_name)
        self._render(transfers, current_time)

    def _render(self, transfers: List[str], current_time: float) -> None:
        """Draw the resolved transfer list. Subclass responsibility."""
        del transfers, current_time
        raise NotImplementedError("TransferInfoDisplay subclass must implement _render")

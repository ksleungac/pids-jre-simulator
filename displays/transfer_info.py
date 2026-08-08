# SPDX-License-Identifier: MIT
"""Transfer-info display base class (model-agnostic).

Resolves the per-stop transfer list each frame: looks up the current
station in ``data/stations.json``, applies the active-line filter
(drops slugs whose badges include the route's own ``line_code``), then
applies any per-station view drop/edit ops keyed by the route's
``transfer_view``. The resolved slug list is handed to ``_render``,
which subclasses implement per train model.

Also hosts ``resolve_entry`` — the generic ``slug``/``slug.variant``/
``...scale(N)`` reference resolver used by both the base class
filter logic and per-model renderers.
"""

import json
import re
from typing import List, Optional

from app_paths import project_root as _project_root

SCALE_SUFFIX_RE = re.compile(r"\.scale\(([0-9]*\.?[0-9]+)\)$")


def resolve_entry(slug_ref: str, lines: dict) -> dict:
    """Resolve 'slug', 'slug.variant', or '...scale(N)' to effective entry dict.

    Variant fields override base fields; missing fields inherit from base.
    Dot-notation is one-level only for variants — `slug.variant.subvariant`
    is invalid. A trailing `.scale(N)` modifier (parsed first) overrides
    `name_ja_compress` for this reference only; default is 1.0 if neither
    suffix nor any inherited field provides one.
    Fails loud (KeyError) on missing base or unknown variant; per
    `critical_lessons.md` § runtime-required artifacts, silent fallback on
    missing data hides bugs at the worst time.
    """
    scale_override = None
    m = SCALE_SUFFIX_RE.search(slug_ref)
    if m:
        scale_override = float(m.group(1))
        slug_ref = slug_ref[: m.start()]

    if "." in slug_ref:
        base_slug, variant_name = slug_ref.split(".", 1)
        if "." in variant_name:
            raise ValueError(f"Dot-notation is one level only; got '{slug_ref}'")
        if base_slug not in lines:
            raise KeyError(f"Base slug '{base_slug}' not in lines.json (referenced as '{slug_ref}')")
        base = lines[base_slug]
        variants = base.get("variants", {})
        if variant_name not in variants:
            raise KeyError(f"Variant '{variant_name}' not under '{base_slug}' (referenced as '{slug_ref}')")
        merged = {k: v for k, v in base.items() if k != "variants"}
        merged.update(variants[variant_name])
    else:
        if slug_ref not in lines:
            raise KeyError(f"Slug '{slug_ref}' not in lines.json")
        merged = {k: v for k, v in lines[slug_ref].items() if k != "variants"}

    if scale_override is not None:
        merged["name_ja_compress"] = scale_override
    return merged


def apply_transfer_filter(
    transfers: List[str],
    line_code: Optional[str],
    transfer_view: Optional[str],
    station_data: dict,
    lines: dict,
) -> List[str]:
    """Apply active-line filter, then view drops, then view edits.

    Single source of truth for the transfer filtering pipeline shared by
    the production class (``TransferInfoDisplay._resolve_transfers``) and
    the preview CLI. Pure function — no class state.
    """
    if line_code:
        transfers = [ref for ref in transfers if not any(b.get("code") == line_code for b in resolve_entry(ref, lines).get("badges", []))]

    if transfer_view:
        view_ops = station_data.get("transfers_by_view", {}).get(transfer_view, {})
        dropset = set(view_ops.get("drop", []))
        if dropset:
            transfers = [r for r in transfers if r.split(".", 1)[0] not in dropset]
        editmap = view_ops.get("edit", {})
        if editmap:
            transfers = [editmap.get(r.split(".", 1)[0], r) for r in transfers]

    return transfers


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
        self.stations = json.loads((root / "data" / "stations.json").read_text(encoding="utf-8"))

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

        Empty-list fallback (vs the renderer's ``_universal`` fallback) is
        intentional: filter logic uses badges to read ``code`` for line-match;
        a badgeless entry has no code → never filter-dropped, always passes.
        """
        return resolve_entry(slug_ref, self.lines).get("badges", [])

    def _resolve_transfers(self, station_name: str) -> List[str]:
        """Return the post-filter / post-view-edit slug_ref list for a station.

        Empty when the station has no transfers entry, or when filtering
        wipes everything out. Delegates to ``apply_transfer_filter`` so
        preview tooling and production share one filter pipeline.
        """
        sd = self.stations.get(station_name, {})
        return apply_transfer_filter(
            list(sd.get("transfers", [])),
            self.line_code,
            self.transfer_view,
            sd,
            self.lines,
        )

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

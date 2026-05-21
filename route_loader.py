"""Route-data loader."""

# CONTRACT: route.json is input grammar, not runtime shape.
# The loader parses + applies loader-time computations (dest closure,
# station translation merge, dest_furigana lookup) to produce the runtime
# route_data. Renderers consume the runtime shape via direct key access -
# no fallback logic, no recomputation per draw.
# See DATA_FORMAT.md "Stop-Level Destination Override".

import json
from pathlib import Path


def load_route_from_dir(work_dir, station_db: dict) -> dict:
    """Read ``<work_dir>/route.json`` from disk and finalize."""
    path = Path(work_dir) / "route.json"
    with open(path, encoding="utf-8") as f:
        route_data = json.load(f)
    return finalize_route(route_data, station_db)


def finalize_route(route_data: dict, station_db: dict) -> dict:
    """Apply loader-time computations to a parsed route_data dict.

    Mutates the dict in place and returns the same reference. Adding
    further loader-time computations (e.g. is_first / is_passing /
    is_terminus precomputation) lands here.
    """
    _fill_dest_closure(route_data)
    _merge_station_translations(route_data, station_db)
    _resolve_dest_furigana(route_data, station_db)
    return route_data


def _fill_dest_closure(route_data: dict) -> None:
    """Fill ``stop['dest']`` on every stop via sticky-override propagation.

    Walk forward; an override stop sets the current value; subsequent stops
    inherit it until the next override. After this pass, every stop has a
    ``dest`` field — renderers read it directly.
    """
    current = route_data.get("dest", "")
    for stop in route_data.get("stops", []):
        if "dest" in stop:
            current = stop["dest"]
        else:
            stop["dest"] = current


def _merge_station_translations(route_data: dict, station_db: dict) -> None:
    """Merge ``furigana`` / ``english`` from ``station_db`` onto each stop.

    Stop-level fields take precedence; only fill what isn't already set.
    """
    for stop in route_data.get("pre_stops", []) + route_data.get("stops", []):
        name = stop.get("name", "")
        if not name or name not in station_db:
            continue
        entry = station_db[name]
        if "furigana" not in stop and "furigana" in entry:
            stop["furigana"] = entry["furigana"]
        if "english" not in stop and "english" in entry:
            stop["english"] = entry["english"]


def _resolve_dest_furigana(route_data: dict, station_db: dict) -> None:
    """Lookup ``dest_furigana`` from ``station_db`` if not already set on the route."""
    if route_data.get("dest_furigana"):
        return
    dest = route_data.get("dest", "")
    if dest and dest in station_db:
        route_data["dest_furigana"] = station_db[dest].get("furigana", "")

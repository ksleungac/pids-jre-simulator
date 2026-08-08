# SPDX-License-Identifier: MIT
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


def resolve_audio_root(work_dir, route_data: dict) -> Path:
    """Directory holding this route's ``pa/`` and ``sta/`` folders.

    # CONTRACT: exactly one audio root per route - never a search order.
    # Audio lives in the PER-LINE POOL (``<work_dir>/..``, shared by every
    # diagram on that line) unless route.json declares ``audio_root``
    # otherwise; ``"."`` selects the pre-pool shape where audio sits beside
    # route.json. Every shipped line is pooled, so the key is authored only by
    # the two fixtures that are not (``_mock/main``, ``_joban/tsuchiura``) -
    # the exception is written down, the rule is not.
    # A diagram-local FALLBACK was rejected and must not be reintroduced:
    # legacy PA slugs are diagram-local ("1.mp3" means different announcements
    # in different diagrams), so a missing file would silently resolve to the
    # other root and play the WRONG announcement with no error - the exact
    # silent-breakage class of critical_lessons.md 2. One root means a missing
    # track fails loud at its single resolved path. Note this is about SEARCH
    # ORDER, not about which root is the default: the resolved root depends
    # only on the declared value, never on what happens to be on disk.
    # See DATA_FORMAT.md "audio_root Field".
    """
    return (Path(work_dir) / route_data.get("audio_root", "..")).resolve()


def finalize_route(route_data: dict, station_db: dict) -> dict:
    """Apply loader-time computations to a parsed route_data dict.

    Mutates the dict in place and returns the same reference. Adding
    further loader-time computations (e.g. is_first / is_passing /
    is_terminus precomputation) lands here.
    """
    _fill_dest_closure(route_data)
    _merge_station_translations(route_data, station_db)
    _resolve_dest_furigana(route_data, station_db)
    _resolve_frames(route_data)
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


def _resolve_frames(route_data: dict) -> None:
    """Resolve the optional through-service ``frames`` array into the closure.

    A through-service route partitions its station list into display
    ``frames``; the LCD renders only the frame containing the train's
    position and swaps at junctions. No ``frames`` key = legacy single-frame
    route (today's behavior) — return untouched.

    Per frame, enrich in place with:
      - ``from_idx`` / ``to_idx`` — indices into the combined
        ``pre_stops + stops`` list (the ``from`` may reference a pre_stop).
      - ``line_entry`` — resolved ``lines.json`` entry (name_ja/name_en/
        badges/color) for the frame's ``line`` slug (+ optional ``.variant``).

    Fails loud (KeyError / ValueError) on any unresolved station, bad line
    slug, non-abutting boundary, or incomplete coverage. The
    ``check_route_loads`` smoke test in validate_data.py exercises this at
    validate time. See DATA_FORMAT.md § frames.
    """
    frames = route_data.get("frames")
    if not frames:
        return

    # Lazy imports: only through-service routes pay; keeps the legacy load
    # path and validate_data's smoke test free of the displays/ dependency.
    from app_paths import project_root
    from displays.transfer_info import resolve_entry

    lines = json.loads((project_root() / "data" / "lines.json").read_text(encoding="utf-8"))

    combined = route_data.get("pre_stops", []) + route_data.get("stops", [])
    # First-occurrence-wins. Frames assume a LINEAR route: a circular route
    # (Yamanote — stops[0] == stops[-1], duplicate loop-point name) would
    # resolve a `to` at the loop terminus to the first copy, tripping the
    # "last frame must end at the route's final station" check below. Circular +
    # frames is unsupported (and unneeded — through-service routes are linear).
    name_to_idx: dict = {}
    for i, stop in enumerate(combined):
        name_to_idx.setdefault(stop.get("name", ""), i)

    def _idx(name: str, role: str, fi: int) -> int:
        if name not in name_to_idx:
            raise KeyError(f"frame[{fi}] {role}='{name}' not found in pre_stops+stops")
        return name_to_idx[name]

    prev_to = None
    for fi, frame in enumerate(frames):
        f_idx = _idx(frame["from"], "from", fi)
        t_idx = _idx(frame["to"], "to", fi)
        if f_idx > t_idx:
            raise ValueError(f"frame[{fi}] from='{frame['from']}'(#{f_idx}) is after " f"to='{frame['to']}'(#{t_idx})")
        if prev_to is not None and f_idx != prev_to:
            raise ValueError(
                f"frame[{fi}] from='{frame['from']}'(#{f_idx}) does not abut "
                f"the previous frame's to(#{prev_to}); frames must share a "
                f"boundary station"
            )
        frame["from_idx"] = f_idx
        frame["to_idx"] = t_idx
        frame["line_entry"] = resolve_entry(frame["line"], lines)  # fails loud
        prev_to = t_idx

    last = len(combined) - 1
    if frames[0]["from_idx"] != 0:
        raise ValueError(f"first frame must start at the route's first station " f"(from_idx={frames[0]['from_idx']}, expected 0)")
    if frames[-1]["to_idx"] != last:
        raise ValueError(f"last frame must end at the route's last station " f"(to_idx={frames[-1]['to_idx']}, expected {last})")

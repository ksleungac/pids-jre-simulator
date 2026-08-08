"""Resolve the audio folder layout for the by-ear verifiers.

Two layouts exist since per-line audio pooling (see DATA_FORMAT.md § audio_root Field):

    per-diagram   audio/<line>/<diagram>/route.json  +  <diagram>/{pa,sta}/
    pooled line   audio/<line>/<diagram>/route.json  +  <line>/{pa,sta}/
                  (the default; route.json writes no audio_root)

Under a pool one mp3 has SEVERAL referrers, which is what breaks the old
`work_dir/route.json` assumption: the pool folder has `pa/` and `sta/` but no
route.json beside them. Discovery is shared here; each verifier keeps its own
merge because STA dedupes on `sta` (carrying `sta_cut`) while PA spans both
`pa` and `pa_at_station`.

Writers must patch EVERY route.json a file appears in — patching the first
match silently desyncs the pool.
"""

from __future__ import annotations

import json
from pathlib import Path


def discover_route_sources(work_dir: Path, media_subdir: str) -> tuple[list[Path], Path, list[tuple[Path, list[dict]]]]:
    """Return (route_paths, media_dir, [(route_path, stops), ...]).

    `media_subdir` is "pa" or "sta". Raises FileNotFoundError when neither
    layout is present, so callers can report and exit.
    """
    media_dir = work_dir / media_subdir
    own = work_dir / "route.json"
    # Guard BOTH layouts, not just the pooled one. Handing a pooled line's DIAGRAM folder
    # (which is what these tools' own examples used to say) still finds route.json there and
    # takes the per-diagram branch, then returns a media_dir that does not exist — the caller
    # reports "no playable entries", naming the wrong cause. critical_lessons.md §2: fail loud.
    if not media_dir.is_dir():
        hint = ""
        if own.exists() and (work_dir.parent / media_subdir).is_dir():
            hint = f" — this line is pooled; pass the LINE folder ({work_dir.parent}) instead of the diagram"
        raise FileNotFoundError(f"{media_subdir} folder not found: {media_dir}{hint}")
    if own.exists():
        stops = json.loads(own.read_text(encoding="utf-8"))["stops"]
        return [own], media_dir, [(own, stops)]

    route_paths = sorted(work_dir.glob("*/route.json"))
    if not route_paths:
        raise FileNotFoundError(f"no route.json at {own} and no <diagram>/route.json under {work_dir}")

    loaded = [(p, json.loads(p.read_text(encoding="utf-8"))["stops"]) for p in route_paths]
    return route_paths, media_dir, loaded


def order_by_reference_count(loaded: list[tuple[Path, list[dict]]], keys: tuple[str, ...]) -> list[tuple[Path, list[dict]]]:
    """Diagram referencing the most files first, so the merged order reads as route order."""

    def count(entry: tuple[Path, list[dict]]) -> int:
        return sum(len(stop.get(k, [])) for stop in entry[1] for k in keys)

    return sorted(loaded, key=count, reverse=True)

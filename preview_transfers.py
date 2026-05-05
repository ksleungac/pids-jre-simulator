"""Standalone preview CLI for the transfer-info display element.

Renders the transfer block for a given station onto a lower-LCD-sized
surface, saved to PNG. Used to iterate the layout against IRL reference
photos without spinning up the full simulator.

Hooked to the E235-1000 train model. Future work may extend this to
preview other train models — until then, only E235-1000 ships a
``transfer_info`` renderer.

Usage:
    uv run preview_transfers.py [--station 東京] [--out _visual_iter/v2.png]
"""

import argparse
import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from displays.transfer_info import apply_transfer_filter
from displays.utils import project_root
from displays.train_models.e235_1000.transfer_info import (
    W,
    H,
    render_transfer,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--station", default="東京")
    parser.add_argument("--out", default="_visual_iter/v2_transfer.png")
    parser.add_argument(
        "--filter-line",
        default="",
        help="Simulate active-line filter — drop transfers whose badges include this code "
        "(matches audio behavior: on a JT/JU train, audio skips JT/JU/Ueno-Tōkyō entirely, "
        "so UT's [JT, JU] compound also gets filtered). "
        "Pass e.g. 'JO' to mimic the IRL reference photo (taken on a JO train).",
    )
    parser.add_argument(
        "--view",
        default="",
        help="Apply per-view drops from station's transfers_by_view[<view>] map. "
        "Format: '<line>_<direction>' e.g. 'JY_inner'. Combines with --filter-line. "
        "Drop matches by base slug name, so a `drop: ['keihin_tohoku']` entry "
        "drops both plain `keihin_tohoku` and any `keihin_tohoku.<variant>` references.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Render only first N transfers (post-filter). 0 = no limit. Use for testing "
        "raw drawing logic with a small input — e.g. --limit 2 → just the shinkansen pair.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print structured layout trace: per-entry widths, grouping candidates, "
        "blueprint state, per-row rule taken, chosen xs, and gaps.",
    )
    args = parser.parse_args()

    if args.debug:
        # CJK strings in debug output crash cp1252 stdout on Windows.
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    pygame.init()
    pygame.display.set_mode((1, 1))  # required by convert_alpha() under SDL dummy
    surf = pygame.Surface((W, H))

    root = project_root()
    lines = json.loads((root / "data" / "lines.json").read_text(encoding="utf-8"))
    stations = json.loads((root / "data" / "stations.json").read_text(encoding="utf-8"))

    if args.station not in stations:
        print(f"Station {args.station!r} not in stations.json")
        return 1
    station_data = stations[args.station]
    transfers = list(station_data.get("transfers", []))
    if not transfers:
        print(f"Station {args.station!r} has no 'transfers' field")
        return 1

    # Diagnostics: inspect view ops before the shared filter pipeline runs
    # so the CLI can announce what's being dropped/edited.
    rows_override = None
    if args.view:
        view_ops = station_data.get("transfers_by_view", {}).get(args.view, {})
        view_dropset = set(view_ops.get("drop", []))
        view_editmap = view_ops.get("edit", {})
        rows_override = view_ops.get("rows")
        if not view_dropset and not view_editmap and rows_override is None:
            print(f"View {args.view!r}: no ops defined (or view-key absent)")
        else:
            if view_dropset:
                print(f"View {args.view!r} drops: {sorted(view_dropset)}")
            if view_editmap:
                print(f"View {args.view!r} edits: {view_editmap}")
            if rows_override is not None:
                print(f"View {args.view!r} rows override: {rows_override}")

    before = len(transfers)
    transfers = apply_transfer_filter(
        transfers,
        args.filter_line or None,
        args.view or None,
        station_data,
        lines,
    )
    if args.filter_line or args.view:
        print(f"Filter+view: {before} -> {len(transfers)} transfers remain")

    if args.limit > 0:
        transfers = transfers[: args.limit]
        print(f"Limit to first {args.limit}: {transfers}")

    render_transfer(surf, transfers, lines, debug=args.debug, rows_override=rows_override)

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(out_path))
    print(f"Saved to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

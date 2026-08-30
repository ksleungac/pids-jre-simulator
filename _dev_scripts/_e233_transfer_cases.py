# SPDX-License-Identifier: MIT
"""Which transfer cases does the shipped corpus produce on E233-0, and how does each lay out?

KEEP. Written 2026-08-30 as a one-off and misclassified: it answered four separate
questions that day — the reachable case list, the badge-column offsets that exposed
the `len(shink_rows) >= 2` hardcode, the `--band` sweep around `long_row_frac`, and
whether the shinkansen wrap ever fires — and it is the only instrument that drives
the production `_layout` across every route. Any change to the transfer layout wants
it again.


Enumerates every stop of every shipped route, resolves its transfer list through
the PRODUCTION pipeline (`apply_transfer_filter`), and asks the PRODUCTION
E233-0 renderer what layout it picks (`TransferInfoDisplay._layout`) — rung,
column count, row grouping, block extent. Nothing here re-implements the layout;
it drives it, per `principles.md` § "A second implementation of a production
decision drifts silently".

Written to pick the cells of the transfer coverage sheet from what the data
actually contains rather than from memory of it, and to flag the ones that
overflow before they are rendered.

Run:  uv run _dev_scripts/_e233_transfer_cases.py [--all] [--csv]
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
pygame.init()
pygame.display.set_mode((64, 64))

from app_paths import project_root  # noqa: E402
from displays.train_models.e233_0 import S_HEIGHT, S_WIDTH  # noqa: E402
from displays.train_models.e233_0.transfer_info import (  # noqa: E402
    TransferInfoDisplay,
    _TUNEABLES_TRANSFER_VIEW as TV,
)

ROOT = project_root()


def routes():
    """Every shipped route dir, `_`-prefixed lines excluded as the picker does."""
    out = []
    for p in sorted((ROOT / "audio").glob("*/*/route.json")):
        if p.parent.parent.name.startswith("_"):
            continue
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="list every station, not just the notable ones")
    ap.add_argument("--csv", action="store_true", help="one line per case, machine-readable")
    ap.add_argument("--why", default=None, help="LINE/DIAGRAM@IDX — per-entry widths and why each row grouped as it did")
    ap.add_argument(
        "--band",
        nargs=2,
        type=float,
        default=None,
        metavar=("LO", "HI"),
        help="list every corpus entry whose width falls in [LO,HI] — the entries a move of `long_row_frac` would flip",
    )
    args = ap.parse_args()

    if args.why:
        where, _, idx = args.why.partition("@")
        rp = ROOT / "audio" / where / "route.json"
        route = json.loads(rp.read_text(encoding="utf-8"))
        stops = route["stops"]
        disp = TransferInfoDisplay(pygame.Surface((S_WIDTH, S_HEIGHT)), route, stops)
        entries = disp._entries(disp._resolve_transfers(stops[int(idx)]["name"]))
        avail_w = S_WIDTH - 2.0 * float(TV["side_pad"])
        scale, cols, widths, wrapped, grid = disp._layout(entries)
        bar = float(TV["long_row_frac"]) * avail_w
        print(f"{stops[int(idx)]['name']}  n={len(entries)}  rung={scale}  cols={cols}  grid={[len(r) for r in grid]}")
        print(f"solo bar = long_row_frac {TV['long_row_frac']} x {avail_w:.0f} = {bar:.0f}\n")
        solo = disp._solo(entries, scale, avail_w)
        for k, e in enumerate(entries):
            w = disp._entry_width(e, scale, disp._wrap(e, scale, avail_w))
            tag = "SHINKANSEN" if e[3] else ("SOLO" if k in solo else "pairs")
            print(f"  [{k}] {e[1]:<14} {w:>6.0f}  {tag}{'  (' + str(round(w - bar)) + ' over)' if (k in solo and not e[3]) else ''}")
        return

    avail_w = S_WIDTH - 2.0 * float(TV["side_pad"])
    avail_h = S_HEIGHT - float(TV["row0_top"]) - float(TV["bottom_pad"])

    seen = {}
    rows_out = []
    band_hits = []
    for rp in routes():
        route = json.loads(rp.read_text(encoding="utf-8"))
        line, diagram = rp.parent.parent.name, rp.parent.name
        stops = route.get("stops", [])
        disp = TransferInfoDisplay(pygame.Surface((S_WIDTH, S_HEIGHT)), route, stops)
        for idx, stop in enumerate(stops):
            name = stop.get("name", "")
            # A STATION THE TRAIN PASSES NEVER SHOWS THIS VIEW. TRANSFER joins
            # the rotation only inside `_in_transfer_window`, which returns
            # False outright when the stop has no `pa` tracks — so a `pa: []`
            # station is unreachable however many transfers it has. Chuo 1654T
            # passes 代々木 / 市ヶ谷 / 飯田橋 / 水道橋; counting them put three
            # unreachable cells on a coverage sheet, each of which rendered as
            # its roll-back station because `jump_to_stop` walks back to the
            # nearest stopping one.
            if not stop.get("pa"):
                continue
            refs = disp._resolve_transfers(name)
            if not refs:
                continue
            key = (route.get("line_code"), route.get("transfer_view"), name)
            if key in seen:
                seen[key][1].append(f"{line}/{diagram}@{idx}")
                continue
            entries = disp._entries(refs)
            scale, cols, widths, wrapped, grid = disp._layout(entries)
            shape = ",".join(str(len(r)) for r in grid)
            # Block extent, measured the way the renderer measures it.
            gap = float(TV["col_gap"]) * scale
            pitch = float(TV["row_pitch"]) * scale
            row_w = []
            for r in grid:
                if len(r) > 1:
                    row_w.append(sum(widths[: len(r)]) + gap * (len(r) - 1))
                else:
                    row_w.append(disp._entry_width(entries[r[0]], scale, wrapped[r[0]]))
            extra = sum(1 for r in grid if any(wrapped[k][1] or wrapped[k][3] for k in r))
            # The same measure `_layout`'s `cap` applies: the last row's TOP is
            # (rows-1+extra) pitches down, and the row block is a badge tall.
            # Counting a whole pitch for the last row instead reports every
            # three-row station as overflowing when none of them do.
            h = (len(grid) - 1 + extra) * pitch + float(TV["badge"]) * scale
            if args.band:
                lo, hi = args.band
                solo = disp._solo(entries, scale, avail_w)
                for k, e in enumerate(entries):
                    if e[3]:
                        continue
                    ew = disp._entry_width(e, scale, disp._wrap(e, scale, avail_w))
                    if lo <= ew <= hi:
                        band_hits.append((ew, f"{line}/{diagram} {name} {e[1]} {'SOLO' if k in solo else 'pairs'} rung={scale}"))
            wraps = [entries[k][1] for r in grid for k in r if wrapped[k][1] or wrapped[k][3]]
            # THE TWO CENTRINGS. `_render` centres the widest shinkansen row on
            # the canvas and the grid on the canvas independently, so the gap
            # between their badge columns is half the difference of their widths
            # — which is the misalignment, stated as a number instead of eyed off
            # a sheet. Widths come from the production `_entry_width`.
            shink_w = max([row_w[i] for i, r in enumerate(grid) if len(r) == 1 and entries[r[0]][3]] or [0.0])
            grid_w = max([row_w[i] for i, r in enumerate(grid) if not (len(r) == 1 and entries[r[0]][3])] or [0.0])
            n_shink = sum(1 for r in grid if len(r) == 1 and entries[r[0]][3])
            badge_gap = abs(grid_w - shink_w) / 2.0 if (shink_w and grid_w) else 0.0
            flags = []
            if n_shink:
                flags.append(f"shink={n_shink} dx={badge_gap:.0f}")
            if max(row_w) > avail_w + 0.5:
                flags.append(f"WIDE({max(row_w):.0f}>{avail_w:.0f})")
            if h > avail_h + 0.5:
                flags.append(f"TALL({h:.0f}>{avail_h:.0f})")
            if scale != TV["rungs"][0]:
                flags.append(f"rung{TV['rungs'].index(scale)}")
            if wraps:
                flags.append("wrap:" + "|".join(wraps))
            seen[key] = (
                dict(
                    line=line,
                    diagram=diagram,
                    idx=idx,
                    name=name,
                    n=len(entries),
                    shape=shape,
                    cols=cols,
                    scale=scale,
                    w=max(row_w),
                    h=h,
                    flags=flags,
                    names=[e[1] for e in entries],
                ),
                [f"{line}/{diagram}@{idx}"],
            )
            rows_out.append(key)

    if args.band:
        for w, s in sorted(band_hits):
            print(f"{w:>6.0f}  {s}")
        print(f"\n{len(band_hits)} entries in [{args.band[0]:.0f}, {args.band[1]:.0f}]")
        return

    if args.csv:
        for key in rows_out:
            r, where = seen[key]
            print(
                f"{r['line']}/{r['diagram']}|{r['idx']}|{r['name']}|{r['n']}|{r['shape']}|"
                f"{r['cols']}|{r['scale']}|{r['w']:.0f}|{r['h']:.0f}|{';'.join(r['flags'])}"
            )
        return

    by_line = {}
    for key in rows_out:
        by_line.setdefault(seen[key][0]["line"], []).append(key)

    print(f"usable {avail_w:.0f} x {avail_h:.0f}   rungs {TV['rungs']}\n")
    for line, keys in by_line.items():
        print(f"=== {line} ===")
        for key in keys:
            r, where = seen[key]
            notable = r["flags"] or r["n"] >= 5 or "," not in r["shape"] or len(set(r["shape"].split(","))) > 1
            if not (args.all or notable):
                continue
            print(
                f"  {r['name']:<8} n={r['n']:<2} ({r['shape']:<9}) cols={r['cols']} "
                f"rung={r['scale']:<5} {r['w']:>5.0f}x{r['h']:<5.0f} "
                f"{' '.join(r['flags'])}"
            )
            if args.all:
                print(f"       {' / '.join(r['names'])}")
                print(f"       {', '.join(where[:4])}")
        print()

    print(f"{len(rows_out)} distinct (view, station) cases across {len(by_line)} lines")


if __name__ == "__main__":
    main()

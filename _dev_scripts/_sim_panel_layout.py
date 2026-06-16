"""Headless simulation of the inline transfer-panel layout algorithm.

NOT shipped (``_`` prefix). Validates the column-anchor + curved-right-edge
grouping algorithm against real Yamanote transfer data BEFORE any render code
is written, so we can confirm it is deterministic + stable (no oscillation,
no overlap, no col-2 overflow) across every stop.

Run: PYTHONPATH=. uv run _dev_scripts/_sim_panel_layout.py
"""

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
from displays.transfer_info import apply_transfer_filter, resolve_entry  # noqa: E402
from displays.train_models.e235_1000.transfer_info import load_icon  # noqa: E402

ROOT = project_root()
LINES = json.loads((ROOT / "data" / "lines.json").read_text(encoding="utf-8"))
STATIONS = json.loads((ROOT / "data" / "stations.json").read_text(encoding="utf-8"))
ROUTE = json.loads((ROOT / "audio" / "yamanote" / "route.json").read_text(encoding="utf-8"))
LINE_CODE = ROUTE["line_code"]
TRANSFER_VIEW = ROUTE["transfer_view"]

# --- panel params: read LIVE from the shipping module's _TUNEABLES_TRANSFER_PANEL
# (no hand-copied drift; this file is the ground-truth generator for the
# DISPLAY_E235.md regression corpus). ---
from displays.train_models.e235_0.lower_lcd import _TUNEABLES_TRANSFER_PANEL as _TP  # noqa: E402

PX = int(_TP["tp0_x"])
BADGE = int(_TP["tp_badge"])
BADGE_GAP = int(_TP["tp_badge_gap"])
INTER_BADGE = int(_TP["tp_inter_badge"])
NAME_SIZE = int(_TP["tp_name_size"])
COL_GAP = int(_TP["tp_col_gap"])
ROW_PITCH = int(_TP["tp_row_pitch"])
LIST_GAP = int(_TP["tp_list_gap"])
SUB_GAP = int(_TP["tp_sub_gap"])
HEADER_SIZE = int(_TP["tp_header_size"])
SUB_SIZE = int(_TP["tp_sub_size"])
TP0_Y = int(_TP["tp0_y"])
WRAP_LGAP = int(_TP["tp_wrap_lgap"])
PAIR_MIN_N = int(_TP["tp_pair_min_n"])  # pair only when ≥ this many transfers; fewer → all solo
SHINK_WRAP_X = int(_TP["tp_shink_wrap_x"])  # narrower fixed shinkansen 2-line wrap boundary
# right-edge curve control points (y, x), piecewise-linear (mirrors tp1/tp2/tp3).
CURVE = sorted(
    [
        (int(_TP["tp1_y"]), int(_TP["tp1_x"])),
        (int(_TP["tp2_y"]), int(_TP["tp2_x"])),
        (int(_TP["tp3_y"]), int(_TP["tp3_x"])),
    ]
)

_font_cache = {}


def font(name, size):
    key = (name, size)
    f = _font_cache.get(key)
    if f is None:
        f = pygame.font.Font(str(ROOT / "fonts" / name), size)
        _font_cache[key] = f
    return f


NAME_FONT = font("ShinGoPr6N-Medium.otf", NAME_SIZE)
HEADER_FONT = font("ShinGoPr6N-Heavy.otf", HEADER_SIZE)
SUB_FONT = font("ShinGoPr6N-Light.otf", SUB_SIZE)
LINE_H = NAME_FONT.get_height()
_icon_cache = {}


def boundary(y):
    pts = CURVE
    if y <= pts[0][0]:
        (y0, x0), (y1, x1) = pts[0], pts[1]
    elif y >= pts[-1][0]:
        (y0, x0), (y1, x1) = pts[-2], pts[-1]
    else:
        (y0, x0), (y1, x1) = pts[0], pts[1]
        for k in range(len(pts) - 1):
            if pts[k][0] <= y <= pts[k + 1][0]:
                (y0, x0), (y1, x1) = pts[k], pts[k + 1]
                break
    if y1 == y0:
        return float(x0)
    return x0 + (x1 - x0) * (y - y0) / (y1 - y0)


def icons(e):
    return [load_icon(b["icon"], BADGE, _icon_cache) for b in (e.get("badges") or [{"icon": "_universal"}])]


def is_shink(e):
    return e.get("category") == "shinkansen"


def entry_w(e):
    ics = icons(e)
    bw = sum(ic.get_width() for ic in ics) + INTER_BADGE * (len(ics) - 1)
    return bw + BADGE_GAP + NAME_FONT.size(e["name_ja"])[0]


def shink_line_count(e, ex):
    """Lines a solo shinkansen wraps into against the NARROWER SHINK_WRAP_X
    boundary (mirrors shipped _entry_lines): 2 if its name exceeds the budget,
    else 1. Drives faithful row height so rows below a wrapped shinkansen sit at
    the right y (the curve boundary depends on y)."""
    ics = icons(e)
    bw = sum(ic.get_width() for ic in ics) + INTER_BADGE * (len(ics) - 1)
    text_x = ex + bw + BADGE_GAP
    avail = SHINK_WRAP_X - text_x
    return 2 if NAME_FONT.size(e["name_ja"])[0] > avail else 1


def list_y0():
    hy = TP0_Y
    sy = hy + HEADER_FONT.get_height() + SUB_GAP
    return sy + SUB_FONT.get_height() + LIST_GAP


def layout(entries, trace):
    """Return list of rows; each row = list of (entry, x) plus meta. Mutates
    `trace` with a human-readable decision log. col-1 left-aligned at PX; col-2
    shares one anchor x = PX + max(col1 widths over paired rows) + COL_GAP;
    a pair is kept only if its col-2 entry fits under boundary(row_y)."""
    row_gap = max(0, ROW_PITCH - max(LINE_H, BADGE))

    # --- pass 1: tentative grouping, greedy 2-per-row by each pair's own
    # natural footprint against the boundary at that row's y. shinkansen always
    # solo (full width). y advances as rows are laid down.
    def build(pairs_allowed):
        rows = []
        y = list_y0()
        i = 0
        while i < len(entries):
            e = entries[i]
            nxt = entries[i + 1] if i + 1 < len(entries) else None
            paired = False
            if len(entries) >= PAIR_MIN_N and pairs_allowed.get(i, True) and nxt is not None and not is_shink(e) and not is_shink(nxt):
                if entry_w(e) + COL_GAP + entry_w(nxt) <= boundary(y) - PX:
                    rows.append({"members": [e, nxt], "y": y, "i": i})
                    i += 2
                    paired = True
            if not paired:
                rows.append({"members": [e], "y": y, "i": i})
                i += 1
            members = rows[-1]["members"]
            if len(members) == 1 and is_shink(members[0]):
                nlines = shink_line_count(members[0], PX)
                ch = nlines * LINE_H + (nlines - 1) * WRAP_LGAP
                rows[-1]["row_h"] = max(BADGE, ch)
            else:
                rows[-1]["row_h"] = max(LINE_H, BADGE)
            y += rows[-1]["row_h"] + row_gap
        return rows

    pairs_allowed = {}
    for _round in range(len(entries) + 1):
        rows = build(pairs_allowed)
        paired_rows = [r for r in rows if len(r["members"]) == 2]
        if not paired_rows:
            col2_x = None
            break
        col2_x = PX + max(entry_w(r["members"][0]) for r in paired_rows) + COL_GAP
        violators = [r for r in paired_rows if col2_x + entry_w(r["members"][1]) > boundary(r["y"])]
        if not violators:
            break
        for r in violators:
            pairs_allowed[r["i"]] = False
            trace.append(
                f"    unpair idx{r['i']} ({r['members'][0]['name_ja']} | {r['members'][1]['name_ja']}): "
                f"col2_x {col2_x} + w{entry_w(r['members'][1])} = {col2_x + entry_w(r['members'][1])} "
                f"> boundary(y={r['y']})={boundary(r['y']):.0f}"
            )
    return rows, col2_x


def run_station(name):
    sd = STATIONS.get(name, {})
    refs = apply_transfer_filter(list(sd.get("transfers", [])), LINE_CODE, TRANSFER_VIEW, sd, LINES)
    if not refs:
        return None
    entries = [resolve_entry(r, LINES) for r in refs]
    trace = []
    rows, col2_x = layout(entries, trace)
    return entries, rows, col2_x, trace


def main():
    targets = [s.get("name", "") for s in ROUTE["stops"]]
    print(f"col2 anchor rule: PX({PX}) + max(col1_w paired) + COL_GAP({COL_GAP})")
    print(f"boundary curve: {CURVE}\n")
    for name in targets:
        res = run_station(name)
        if res is None:
            continue
        entries, rows, col2_x, trace = res
        print(f"=== {name}駅  ({len(entries)} transfers)  col2_x={col2_x} ===")
        for r in rows:
            y = r["y"]
            b = boundary(y)
            tag = "SHINK" if is_shink(r["members"][0]) else ("PAIR" if len(r["members"]) == 2 else "solo")
            if len(r["members"]) == 2:
                a, c = r["members"]
                aw, cw = entry_w(a), entry_w(c)
                c_right = col2_x + cw
                ov = "  ⚠OVERFLOW" if c_right > b else ""
                print(f"  y={y:>3} [{tag}] {a['name_ja']}(w{aw}) | col2_x={col2_x} {c['name_ja']}(w{cw})→{c_right}  bound={b:.0f}{ov}")
            else:
                e = r["members"][0]
                ew = entry_w(e)
                print(f"  y={y:>3} [{tag}] {e['name_ja']}(w{ew})  PX+w={PX + ew}  bound={b:.0f}")
        for line in trace:
            print(line)
        print()


if __name__ == "__main__":
    main()

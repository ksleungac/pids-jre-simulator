# SPDX-License-Identifier: MIT
# TIER: T1 — the TIMS start-station grid never offers the terminus (loop duplicate)
"""Locks the #59 fix: a loop route offered its terminus station twice in the
start-station picker, and the launch bridge resolved the pick by NAME.

`pa_setting._build_config` turns the picked start into an index with
`stops.index(start_name)`, which returns the FIRST match. Yamanote lists 大崎 at
index 0 (loop origin) and index 29 (loop terminus), so picking the second one
started the drive at the first — a full loop early, 29 stops off.

The grid is built by `route_select._start_station_labels`, which now drops the
terminus. That is correct for every route (the terminus leaves zero stops to
drive) and it is what makes the name unique on a loop.

Discriminator: delete the `[:-1]` and case (1) reports 30 labels with 大崎 twice
while (2) and (3) keep their terminus — three failures.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tims.setup.route_select import _start_station_labels  # noqa: E402

# Yamanote 内回り, verbatim from audio/yamanote/1208G/route.json — 30 stops, none passing,
# 大崎 at both ends. Pinned literally so the fixture cannot drift with the data.
YAMANOTE = [
    "大崎",
    "品川",
    "田町",
    "浜松町",
    "新橋",
    "有楽町",
    "東京",
    "神田",
    "秋葉原",
    "御徒町",
    "上野",
    "鶯谷",
    "日暮里",
    "西日暮里",
    "田端",
    "駒込",
    "巣鴨",
    "大塚",
    "池袋",
    "目白",
    "高田馬場",
    "新大久保",
    "新宿",
    "代々木",
    "原宿",
    "渋谷",
    "恵比寿",
    "目黒",
    "五反田",
    "大崎",
]


def main():
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    # --- (1) loop route: terminus dropped, so the repeated name is offered ONCE ---
    got = _start_station_labels({"stops": YAMANOTE, "stop_idxs": list(range(30))})
    check(len(got) == 29, f"yamanote start grid must offer 29 stations (30 stops − terminus); got {len(got)}")
    check(got.count("大崎") == 1, f"大崎 must appear exactly once in the start grid; got {got.count('大崎')}")
    check(got[0] == "大崎", f"the loop ORIGIN 大崎 is the one kept (index 0); got {got[0]!r}")
    check(got[-1] == "五反田", f"last offered start is the stop BEFORE the terminus; got {got[-1]!r}")
    check("大崎" not in got[1:], "the end-of-loop 大崎 must not be selectable")

    # --- (2) linear route: terminus dropped there too (zero stops left to drive) ---
    got = _start_station_labels({"stops": ["川崎", "尻手", "矢向", "鹿島田"], "stop_idxs": [0, 1, 2, 3]})
    check(got == ["川崎", "尻手", "矢向"], f"linear route must drop its terminus; got {got}")

    # --- (3) passing stations stay excluded (stop_idxs filter survives the change) ---
    got = _start_station_labels({"stops": ["A", "pass1", "B", "pass2", "C", "D"], "stop_idxs": [0, 2, 4, 5]})
    check(got == ["A", "B", "C"], f"passing stations excluded AND terminus dropped; got {got}")

    if failures:
        print("FAIL: TIMS start-station grid")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: start-station grid excludes the terminus (loop duplicate unselectable)")


if __name__ == "__main__":
    main()

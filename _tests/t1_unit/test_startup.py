# SPDX-License-Identifier: MIT
# TIER: T1 — what a launch resolves before a drive can start
"""The pure decisions between double-click and the first frame of a drive.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). Three
resolutions, one property: each must produce a usable answer with no screen, no
interactive step, and no dependence on what happens to be on this machine.

  1. WHICH LANGUAGE      — i18n.resolve_language
  2. WHERE THE AUDIO IS  — route_loader.resolve_audio_root
  3. WHICH STARTS ARE ON OFFER — route_select._start_station_labels

They share a failure mode as well as a shape: each was, or could be, wrong only
on a machine unlike this one — a clean install (§1, `critical_lessons §6`), a
pooled corpus (§2), or a loop route (§3).

Expected values are pinned LITERALLY rather than imported from the module under
test. A test that reads its own expectation out of the code scales with any
mutation of it and stops discriminating (`principles.md` § "Test real logic").
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
# _tests/ is dev harness (never shipped, exempt from the production path-resolver
# ban) — Path(__file__) here is fine. Put the repo root on sys.path for the import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import i18n  # noqa: E402
from route_loader import resolve_audio_root  # noqa: E402
from tims.setup.route_select import _diagrams_for_start, _start_station_labels  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append("  " + msg)


# ── 1. which language ─────────────────────────────────────────────────────────
# First-run language resolution as a PURE, screen-free function — the unit-level
# regression guard for the 2026-07-16 language-picker incident (a stale interactive
# first-run picker no dev ever saw, because settings.json is always populated
# locally; critical_lessons §6).
#
# Pure: dict in, lang out. No disk, no display, no interactive step. The fact that
# this is a TOTAL function over a settings dict is itself the invariant — a first-run
# path can't reintroduce an interactive picker without bypassing it.
#
# `detect_default_lang()` reads the OS locale, so the no-valid-saved-language cases
# assert only that the result is a SUPPORTED language (not a specific one): the point
# is that resolution always yields a usable language, on any machine, without a screen.


def check_language() -> None:
    # Valid saved language → returned verbatim, independent of the OS locale.
    for lang in i18n.SUPPORTED_LANGS:
        got = i18n.resolve_language({"language": lang})
        check(got == lang, f"saved {lang!r} → {got!r}, expected {lang!r}")

    # Absent / null / unsupported / wrong-typed → falls back to a SUPPORTED language
    # (the OS default); never crashes, never returns the bad value. Returning any
    # unsupported value (e.g. "xx") fails the membership check below.
    for bad in ({}, {"language": None}, {"language": "xx"}, {"language": "en_US"}, {"language": 5}, {"other": 1}):
        got = i18n.resolve_language(bad)
        check(got in i18n.SUPPORTED_LANGS, f"{bad!r} → {got!r}, not a SUPPORTED language")


# ── 2. where the audio is ─────────────────────────────────────────────────────
# Every shipped line's audio lives in a per-line pool (`audio/<line>/{pa,sta}/`) while
# its route.json sits one level deeper, so EVERY reference in the app passes through
# this function. It had no test until 2026-08-08, which is also when two sites that
# bypassed it were found silently broken by the pooling — the OOBE tutorial's asset
# pre-flight and the auto-driver's long-approach probe.


def check_audio_root() -> None:
    wd = Path("audio/tokaido/1865E")

    # ABSENT — the per-line pool. This is the default because every shipped line is pooled,
    # so the key carries no information there and is not authored (2026-08-08 graduation).
    got = resolve_audio_root(wd, {})
    check(got == (wd / "..").resolve(), f"absent audio_root must default to the line pool, got {got}")
    check(got.name == "tokaido", f"absent audio_root must land on audio/tokaido, got {got.name}")

    # ".." — the same thing said explicitly.
    check(resolve_audio_root(wd, {"audio_root": ".."}) == got, "an explicit '..' must equal the default")

    # "." — audio beside route.json. THE authored exception: _mock/main, _joban/tsuchiura.
    got = resolve_audio_root(wd, {"audio_root": "."})
    check(got == wd.resolve(), f'audio_root "." must resolve to the work_dir, got {got}')
    check(got.name == "1865E", f'audio_root "." must stay in the diagram folder, got {got.name}')

    # A str work_dir is what app.py hands it (self.work_dir).
    got = resolve_audio_root(str(wd), {})
    check(got.name == "tokaido", f"str work_dir must behave like Path, got {got}")

    # THE contract: exactly one root, NO search order. The property that distinguishes it
    # from a fallback design is that the answer depends only on the declared value — never
    # on what happens to be on disk. A fallback would let a missing file resolve to a
    # different root and play the WRONG announcement (critical_lessons.md §2).
    #
    # An earlier version of this test asserted `pooled != wd.resolve()`, which is true by
    # construction for any implementation — a claim about pathlib, not about this function.
    # A resolver implementing exactly the forbidden fallback passed it.
    empty = Path("audio/_nonexistent_line/_nonexistent_diagram")
    for label, data, want in (
        ("default (pool)", {}, (empty / "..").resolve()),
        ("explicit '..'", {"audio_root": ".."}, (empty / "..").resolve()),
        ("explicit '.'", {"audio_root": "."}, empty.resolve()),
    ):
        got = resolve_audio_root(empty, data)
        check(
            got == want,
            f"{label}: root must follow the declared/default value even when that folder holds "
            f"no pa/ or sta/ — a fallback would divert here. want {want}, got {got}",
        )


# ── 3. which starts are on offer ──────────────────────────────────────────────
# The #59 fix: a loop route offered its terminus station twice in the start-station
# picker, and the launch bridge resolved the pick by NAME.
#
# `pa_setting._build_config` turns the picked start into an index with
# `stops.index(start_name)`, which returns the FIRST match. Yamanote lists 大崎 at
# index 0 (loop origin) and index 29 (loop terminus), so picking the second one
# started the drive at the first — a full loop early, 29 stops off.
#
# The grid is built by `route_select._start_station_labels`, which now drops the
# terminus. That is correct for every route (the terminus leaves zero stops to
# drive) and it is what makes the name unique on a loop.
#
# Discriminator, MEASURED 2026-08-22 after the union rewrite — not inferred:
#   delete `[:-1]`      -> (2)(4)(5)(7) fail. Four.
#   seed the cursor at 0 -> (7) fails. One.
#   filter untrimmed     -> (8) fails. One.
# Cases (1) and (6) do NOT fail on any of them, and cannot: the union's dedup
# (`if name in out`) collapses a repeated loop name whether or not `[:-1]` is there, so
# NO loop case can pin the terminus guard — the linear cases are what pin it. (1) and (6)
# are kept for the outcome they assert (the name is offered exactly once), not as
# discriminators for `[:-1]`. Stated because a check believed to cover more than it does
# is how a class goes unwatched — principles.md § "A measurement is a claim…".
#
# Cases (4) and (5) guard a SECOND defect, 2026-08-22. The station screen runs before
# the diagram screen, and it used to read `variants[0]` only — so any start served by a
# later diagram was unreachable, silently, with the grid still looking complete. Four of
# the six multi-diagram lines shipped that way (南武線 14 stations, 宇都宮線 10, 京浜東北線 6,
# 埼京線 4); it surfaced when utsunomiya gained 3520M and 黒磯 could not be picked.
#
# Discriminator: make the function read only `variants[0]` and (4) loses 黒磯/岡本 while
# (5) loses 尻手/矢向 — two failures. Both are shaped like the real lines: (4) is a
# diagram extending the line at the HEAD, (5) is an express sorting ahead of its local.

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


def check_start_stations() -> None:
    # --- (1) loop route: terminus dropped, so the repeated name is offered ONCE ---
    got = _start_station_labels([{"stops": YAMANOTE, "stop_idxs": list(range(30))}])
    check(len(got) == 29, f"yamanote start grid must offer 29 stations (30 stops − terminus); got {len(got)}")
    check(got.count("大崎") == 1, f"大崎 must appear exactly once in the start grid; got {got.count('大崎')}")
    check(got[0] == "大崎", f"the loop ORIGIN 大崎 is the one kept (index 0); got {got[0]!r}")
    check(got[-1] == "五反田", f"last offered start is the stop BEFORE the terminus; got {got[-1]!r}")
    check("大崎" not in got[1:], "the end-of-loop 大崎 must not be selectable")

    # --- (2) linear route: terminus dropped there too (zero stops left to drive) ---
    got = _start_station_labels([{"stops": ["川崎", "尻手", "矢向", "鹿島田"], "stop_idxs": [0, 1, 2, 3]}])
    check(got == ["川崎", "尻手", "矢向"], f"linear route must drop its terminus; got {got}")

    # --- (3) passing stations stay excluded (stop_idxs filter survives the change) ---
    got = _start_station_labels([{"stops": ["A", "pass1", "B", "pass2", "C", "D"], "stop_idxs": [0, 2, 4, 5]}])
    check(got == ["A", "B", "C"], f"passing stations excluded AND terminus dropped; got {got}")

    # --- (4) a diagram extending the line at the HEAD contributes its own starts ---
    #     utsunomiya shape: 1545E sorts first and begins mid-line; 3520M begins at 黒磯.
    got = _start_station_labels(
        [
            {"stops": ["宇都宮", "雀宮", "小山"], "stop_idxs": [0, 1, 2]},
            {"stops": ["黒磯", "岡本", "宇都宮", "雀宮", "小山"], "stop_idxs": [0, 1, 2, 3, 4]},
        ]
    )
    check(got == ["黒磯", "岡本", "宇都宮", "雀宮"], f"head-extending diagram must contribute its starts, in route order; got {got}")

    # --- (5) an express sorting ahead of its local must not hide the local's stops ---
    #     南武線 / 京浜東北線 / 埼京線 shape.
    got = _start_station_labels(
        [
            {"stops": ["川崎", "尻手", "矢向", "鹿島田"], "stop_idxs": [0, 3]},
            {"stops": ["川崎", "尻手", "矢向", "鹿島田"], "stop_idxs": [0, 1, 2, 3]},
        ]
    )
    check(got == ["川崎", "尻手", "矢向"], f"local-only stops must stay reachable behind an express; got {got}")

    # --- (6) a loop whose repeated name is NOT at index 0 of the accumulated list ---
    #     This is what pins `[:-1]`: the union's dedup cannot save it, because the second
    #     大崎 arrives before the first has been seen.
    got = _start_station_labels([{"stops": ["品川", "大崎", "五反田", "大崎"], "stop_idxs": [0, 1, 2, 3]}])
    check(got == ["品川", "大崎", "五反田"], f"a loop's end-of-loop name must be dropped, not offered twice; got {got}")

    # --- (7) a diagram beginning MID-LINE at a station no earlier variant serves ---
    #     Seeding the splice cursor at 0 would prepend 尻手/矢向 to the whole list, putting
    #     them ahead of 川崎 which precedes them on the real line.
    got = _start_station_labels(
        [
            {"stops": ["川崎", "鶴見"], "stop_idxs": [0, 1]},
            {"stops": ["尻手", "矢向", "鶴見"], "stop_idxs": [0, 1, 2]},
        ]
    )
    check(got == ["川崎", "尻手", "矢向"], f"a mid-line-start diagram must splice before its shared stop, not at index 0; got {got}")

    # --- (8) the terminus guard is the FILTER's job too, not only the grid's ---
    #     A station that ends one diagram is an ordinary stop on another. The grid offers it
    #     (for the diagram that runs on past it); the diagram it terminates must be hidden,
    #     or the drive opens on the last stop with nothing ahead. 宇都宮線 上野 shape.
    a = {"stops": ["宇都宮", "大宮", "上野", "東京"], "stop_idxs": [0, 1, 2, 3], "diagram": "long"}
    b = {"stops": ["黒磯", "大宮", "上野"], "stop_idxs": [0, 1, 2], "diagram": "ends-at-ueno"}
    check("上野" in _start_station_labels([a, b]), "上野 must still be offered — it is a mid-route stop on the longer diagram")
    got = [v["diagram"] for v in _diagrams_for_start([a, b], "上野")]
    check(got == ["long"], f"only the diagram running PAST 上野 may be offered for it; got {got}")
    got = [v["diagram"] for v in _diagrams_for_start([a, b], "大宮")]
    check(got == ["long", "ends-at-ueno"], f"a shared mid-route stop offers both diagrams; got {got}")


def main() -> int:
    check_language()
    check_audio_root()
    check_start_stations()

    if FAILURES:
        print("FAIL: launch resolution")
        print("\n".join(FAILURES))
        return 1
    print(
        f"PASS: launch resolution (language x{len(i18n.SUPPORTED_LANGS)} + corrupt-to-OS-default, "
        "audio root single-answer no-fallback, start grid excludes the terminus and unions every diagram's starts)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

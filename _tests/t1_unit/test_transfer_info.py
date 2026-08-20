# SPDX-License-Identifier: MIT
"""T1 — transfer-list resolution (`displays/transfer_info.apply_transfer_filter`).

Covers the op pipeline that turns a station's authored `transfers[]` into the
list the LCD renders: add -> active-line filter -> drop -> edit. Pure
dict-in/list-out, no pygame, no I/O.

Placement geometry (row grouping, the overhang trim, centring, shrink-to-fit)
is NOT tested here — that is rendering, which `_tests/README.md` excludes by
design and the author judges by eye against IRL references.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from displays.transfer_info import apply_transfer_filter, resolve_entry  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}\n      got:  {got}\n      want: {want}")


# Minimal fixture. Mirrors the SHAPE of data/lines.json (badges carry the line
# `code` the active-line filter matches on) without depending on its contents —
# a fixture that read the real file would drift with every data edit.
LINES = {
    "utsunomiya_takasaki": {
        "badges": [{"icon": "_universal", "code": "JU"}],
        "name_ja": "宇都宮線・高崎線",
        "variants": {
            "utsunomiya": {"name_ja": "宇都宮線(東北線)"},
            "takasaki": {"name_ja": "高崎線"},
        },
    },
    "keihin_tohoku": {"badges": [{"icon": "_universal", "code": "JK"}], "name_ja": "京浜東北線"},
    "shonan_shinjuku": {"badges": [{"icon": "_universal", "code": "JS"}], "name_ja": "湘南新宿ライン"},
    "tobu_noda": {"badges": [{"icon": "_universal"}], "name_ja": "東武野田線"},
}

TRANSFERS = [
    "keihin_tohoku",
    "utsunomiya_takasaki.utsunomiya",
    "utsunomiya_takasaki.takasaki",
    "shonan_shinjuku",
    "tobu_noda",
]


def station(view_ops=None):
    sd = {"transfers": list(TRANSFERS)}
    if view_ops is not None:
        sd["transfers_by_view"] = view_ops
    return sd


def run(line_code, view, view_ops=None):
    sd = station(view_ops)
    return apply_transfer_filter(list(sd["transfers"]), line_code, view, sd, LINES)


# --- active-line filter -------------------------------------------------------
# Riding JU drops BOTH JU-coded variants — the sibling problem `add` exists for.
check(
    "active-line filter drops every ref carrying the route's own code",
    run("JU", None),
    ["keihin_tohoku", "shonan_shinjuku", "tobu_noda"],
)
# A badgeless entry has no code, so it can never be filter-dropped.
check("no line_code -> nothing filtered", run(None, None), list(TRANSFERS))


# --- add ----------------------------------------------------------------------
# The sibling survives; the route's OWN variant still goes. This is why matching
# is by exact ref — a base slug ("utsunomiya_takasaki") would re-admit both.
check(
    "add exempts the exact ref, and only that ref",
    run("JU", "JU_utsunomiya", {"JU_utsunomiya": {"add": ["utsunomiya_takasaki.takasaki"]}}),
    ["keihin_tohoku", "utsunomiya_takasaki.takasaki", "shonan_shinjuku", "tobu_noda"],
)
# Re-admitted entries keep their authored position, so IRL order needs no index:
# .takasaki stays at index 2 of the source list, i.e. after keihin_tohoku.
check(
    "add preserves authored order (no index argument needed)",
    run("JU", "JU_utsunomiya", {"JU_utsunomiya": {"add": ["utsunomiya_takasaki.takasaki"]}})[1],
    "utsunomiya_takasaki.takasaki",
)
# A base slug in `add` matches nothing — the guard validate_data.py enforces.
check(
    "add by base slug re-admits nothing",
    run("JU", "JU_utsunomiya", {"JU_utsunomiya": {"add": ["utsunomiya_takasaki"]}}),
    ["keihin_tohoku", "shonan_shinjuku", "tobu_noda"],
)


# --- ordering: add -> filter -> drop -> edit -----------------------------------
# drop runs AFTER the filter, so a drop of the same base beats the add.
check(
    "drop of the same base still wins over add",
    run(
        "JU",
        "v",
        {"v": {"add": ["utsunomiya_takasaki.takasaki"], "drop": ["utsunomiya_takasaki"]}},
    ),
    ["keihin_tohoku", "shonan_shinjuku", "tobu_noda"],
)
# drop matches by BASE slug, so it takes plain and variant refs alike.
check(
    "drop matches by base slug",
    run(None, "v", {"v": {"drop": ["utsunomiya_takasaki"]}}),
    ["keihin_tohoku", "shonan_shinjuku", "tobu_noda"],
)
# edit runs last, keyed by base slug, replacing whichever ref carried that base.
check(
    "edit replaces by base slug and runs after drop",
    run(None, "v", {"v": {"drop": ["shonan_shinjuku"], "edit": {"keihin_tohoku": "tobu_noda"}}}),
    ["tobu_noda", "utsunomiya_takasaki.utsunomiya", "utsunomiya_takasaki.takasaki", "tobu_noda"],
)
# An add survives the filter and is then editable — proves add lands BEFORE edit.
check(
    "add then edit composes",
    run(
        "JU",
        "v",
        {"v": {"add": ["utsunomiya_takasaki.takasaki"], "edit": {"utsunomiya_takasaki": "tobu_noda"}}},
    ),
    ["keihin_tohoku", "tobu_noda", "shonan_shinjuku", "tobu_noda"],
)


# --- view selection -----------------------------------------------------------
# Ops are keyed by the route's transfer_view; a route with none applies none.
check(
    "no transfer_view -> view ops ignored",
    run("JU", None, {"JU_utsunomiya": {"add": ["utsunomiya_takasaki.takasaki"]}}),
    ["keihin_tohoku", "shonan_shinjuku", "tobu_noda"],
)
check(
    "unknown transfer_view -> view ops ignored",
    run("JU", "JU_nonexistent", {"JU_utsunomiya": {"add": ["utsunomiya_takasaki.takasaki"]}}),
    ["keihin_tohoku", "shonan_shinjuku", "tobu_noda"],
)


# --- resolve_entry: variant inheritance ---------------------------------------
check(
    "variant overrides its own field",
    resolve_entry("utsunomiya_takasaki.takasaki", LINES)["name_ja"],
    "高崎線",
)
check(
    "variant inherits unlisted fields from the base",
    resolve_entry("utsunomiya_takasaki.takasaki", LINES)["badges"],
    [{"icon": "_universal", "code": "JU"}],
)
check(
    "variants key never leaks into the resolved entry",
    "variants" in resolve_entry("utsunomiya_takasaki.utsunomiya", LINES),
    False,
)
# Fails loud on missing data per critical_lessons.md § runtime-required materials.
for ref, exc in (("nope", KeyError), ("utsunomiya_takasaki.nope", KeyError), ("a.b.c", ValueError)):
    try:
        resolve_entry(ref, LINES)
    except exc:
        pass
    except Exception as e:  # noqa: BLE001
        failures.append(f"resolve_entry({ref!r}) raised {type(e).__name__}, expected {exc.__name__}")
    else:
        failures.append(f"resolve_entry({ref!r}) did not raise {exc.__name__}")


if failures:
    print(f"FAIL  test_transfer_info.py  ({len(failures)} case(s))")
    for f in failures:
        print(f"   - {f}")
    sys.exit(1)
print("PASS  test_transfer_info.py")

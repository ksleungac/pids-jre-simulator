"""One-off: enumerate all (station, active-line) configs filtered to a target N range.

For each station, identifies which JR East lines pass through it (lines whose codes
appear in the station's transfer badges), then renders under each plausible
--filter-line + line's-own-view config. Reports configs whose post-filter N falls
in the range hardcoded at the bottom (currently 5..8; was originally 3 — adjust
the `5 <= n <= 8` line as needed for ad-hoc surveys).
"""

import json
import subprocess
import re
from pathlib import Path

ROOT = Path(__file__).parent
STATIONS = json.loads((ROOT / "data" / "stations.json").read_text(encoding="utf-8"))
LINES = json.loads((ROOT / "data" / "lines.json").read_text(encoding="utf-8"))

# JR East codes whose stations are in our dataset
JR_EAST_CODES = {
    "JY",
    "JK",
    "JT",
    "JO",
    "JU",
    "JC",
    "JB",
    "JA",
    "JS",
    "JN",
    "JE",
    "JJ",
    "JH",
    "JM",
}

# Line-code → default direction view (used when station has no transfers_by_view entry).
# Pick one direction arbitrarily; both directions render identically when no view-specific drops.
DEFAULT_VIEWS = {
    "JY": "JY_inner",
    "JK": "JK_south",
    "JA": "JA_north",
    "JO": "JO_east",
    # No direction views for: JT, JU, JC, JB, JS, JN, JE, JJ, JH, JM
}


def jr_east_codes_for_station(name: str) -> set[str]:
    """Codes appearing in any transfer badge of this station (i.e., lines passing through)."""
    sd = STATIONS[name]
    codes = set()
    for ref in sd.get("transfers", []):
        # Resolve nested variant
        slug = ref.split(".")[0].split(".scale(")[0]
        line = LINES.get(slug, {})
        for b in line.get("badges", []):
            c = b.get("code")
            if c in JR_EAST_CODES:
                codes.add(c)
    return codes


def run_render(station: str, filter_line: str, view: str) -> tuple[int, list[int], int, str] | None:
    """Returns (N, widths, total_w, chosen_shape) or None if station has no transfers etc."""
    cmd = [
        "uv",
        "run",
        "preview_transfers.py",
        "--station",
        station,
        "--filter-line",
        filter_line,
        "--debug",
        "--out",
        "_visual_iter/_enum_tmp.png",
    ]
    if view:
        cmd += ["--view", view]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    out = result.stdout
    m_n = re.search(r"entries: (\d+)\s+total_w=(\d+)", out)
    if not m_n:
        return None
    n = int(m_n.group(1))
    total_w = int(m_n.group(2))
    widths = [int(w) for w in re.findall(r"\[\d+\]\s+\S+\s+w=(\d+)", out)]
    m_chosen = re.search(r"✓ shape=(\([^)]+\))", out)
    chosen = m_chosen.group(1) if m_chosen else "?"
    return (n, widths, total_w, chosen)


def views_to_try(station: str, code: str) -> list[str]:
    """For (station, line), return list of views to try.
    Includes all transfers_by_view keys for this line + the default if no view-specific
    drops apply. Returns at least one entry (possibly empty string for no view)."""
    sd = STATIONS[station]
    tbv = sd.get("transfers_by_view", {})
    matching = [k for k in tbv.keys() if k.startswith(f"{code}_") or k == code]
    if matching:
        return matching
    # No view-specific drops for this line at this station: use default direction view
    default = DEFAULT_VIEWS.get(code, "")
    return [default]


def main():
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    rows = []  # (station, line, view, N, widths, Σ, h_singlerow)
    seen = set()
    for station in STATIONS:
        if not STATIONS[station].get("transfers"):
            continue
        codes = jr_east_codes_for_station(station)
        for code in sorted(codes):
            for view in views_to_try(station, code):
                key = (station, code, view)
                if key in seen:
                    continue
                seen.add(key)
                r = run_render(station, code, view)
                if r is None:
                    continue
                n, widths, total_w, chosen = r
                if 5 <= n <= 8:
                    W = 730
                    h = (W - total_w) / (n + 1)
                    rows.append((station, code, view, n, widths, total_w, h, chosen))

    print(f"\n=== Stations matching N range after filter+view ({len(rows)} configs) ===\n")
    print(f"{'station':<10} {'line':<5} {'view':<10} {'widths':<25} {'Σ':>5} {'h_(N,)':>7}  chosen")
    for r in sorted(rows, key=lambda r: r[6]):  # sort by h ascending (most cramped first)
        s, c, v, n, w, sigma, h, chosen = r
        print(f"{s:<10} {c:<5} {v:<10} {str(w):<25} {sigma:>5} {h:>7.1f}  {chosen}")


if __name__ == "__main__":
    main()

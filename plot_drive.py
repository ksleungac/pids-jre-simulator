"""Render an interactive HTML drive report (走行記録) from a blackbox JSONL.

Reads the three record types written by `auto_input.AutoDriver`:
    _type=meta    — route + per-stop dicts (name/english/furigana/stops_here/...)
    _type=event   — arrival / departure / passing_start / passing_end
    _type=sample  — one OCR cycle (speed / distance / badge / sim state)

Output is a single HTML page (plotly inlined), Japanese chrome, two views:

    ┌─ Page header
    │   走行記録 (eyebrow) · {route} {diagram} (title) · origin → dest · date
    │   right-side metric strip: 走行時間 / 停車駅数 / 最高速度 / 平均速度 / 平均停止位置誤差
    │
    ├─ Overview ribbon (運転曲線 / 全区間)
    │   single chart spanning the whole drive, doubles as nav:
    │     hover any segment → soft slate-blue tint
    │     click → jump zoom view to that segment + smooth scroll
    │
    └─ Zoom view (運転曲線 / {from} → {to})
        per-segment enlarged chart with prev/next + seekbar nav,
        directional slide animation, segment summary strip
        (最高速度 / 所要時間 / 最高制限速度 / 停止位置目標誤差).

CLI:
    uv run python plot_drive.py
    uv run python plot_drive.py path/to/drive.jsonl

Reads partial-write-safe — last truncated line of a still-recording log
is silently skipped.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go

from app_paths import project_root

# PowerShell defaults stdout to cp1252; route name + station kanji crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = project_root()
RECORDINGS_DIR = ROOT / "_recordings"


# ─────────────────────────── readers ────────────────────────────


def load_jsonl(path: Path) -> tuple[dict, list[dict], list[dict]]:
    meta: dict = {}
    events: list[dict] = []
    samples: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("_type")
            if t == "meta":
                meta = rec
            elif t == "event":
                events.append(rec)
            elif t == "sample":
                samples.append(rec)
    return meta, events, samples


# ─────────────────────────── derivers ────────────────────────────


def derive_stopped_runs(samples: list[dict]) -> list[tuple[float, float]]:
    runs: list[tuple[float, float]] = []
    in_run = False
    run_start = run_end = 0.0
    for s in samples:
        if s.get("badge") == "STOPPED":
            if not in_run:
                run_start = s["ts"]
                in_run = True
            run_end = s["ts"]
        else:
            if in_run:
                runs.append((run_start, run_end))
                in_run = False
    if in_run:
        runs.append((run_start, run_end))
    return runs


def derive_arrival_offsets(events: list[dict], samples: list[dict], window_s: float = 6.0) -> dict[float, int]:
    """Map each arrival event ts → first captured stopping_offset_cm (cm).

    Walks forward from each arrival.ts; takes the first sample (within window_s)
    whose `stopping_offset_cm` is non-null. The cm cell is shown briefly at
    platform before the cell swaps back to m-distance, so the window is narrow.
    Arrivals where nothing was captured are absent from the returned dict.
    """
    arrivals = sorted([e for e in events if e["kind"] == "arrival"], key=lambda e: e["ts"])
    out: dict[float, int] = {}
    sample_idx = 0
    for arr in arrivals:
        arr_ts = arr["ts"]
        while sample_idx < len(samples) and samples[sample_idx]["ts"] < arr_ts:
            sample_idx += 1
        i = sample_idx
        while i < len(samples) and samples[i]["ts"] <= arr_ts + window_s:
            cm = samples[i].get("stopping_offset_cm")
            if cm is not None:
                out[arr_ts] = int(cm)
                break
            i += 1
    return out


def split_into_rows(events: list[dict], samples: list[dict], stops_per_row: int) -> list[tuple[float, float, list[dict], dict | None]]:
    """Returns list of (window_start_ts, window_end_ts, arrivals_in_row, entry_arrival_or_None).

    `entry_arrival` is the previous row's last arrival — it sits AT this row's
    left edge by construction, so we draw an extra station post for it so each
    row visibly opens with a station marker. None for the first row (the drive
    started here, no inbound station).
    """
    if not samples:
        return []
    arrivals = sorted([e for e in events if e["kind"] == "arrival"], key=lambda e: e["ts"])
    drive_start = samples[0]["ts"]
    drive_end = samples[-1]["ts"]
    if not arrivals:
        return [(drive_start, drive_end, [], None)]

    rows: list[tuple[float, float, list[dict], dict | None]] = []
    n = len(arrivals)
    n_rows = max(1, math.ceil(n / stops_per_row))
    for i in range(n_rows):
        chunk = arrivals[i * stops_per_row : (i + 1) * stops_per_row]
        if not chunk:
            continue
        start = drive_start if i == 0 else rows[-1][1]
        end = chunk[-1]["ts"] if i < n_rows - 1 else drive_end
        entry = arrivals[i * stops_per_row - 1] if i > 0 else None
        rows.append((start, end, chunk, entry))
    return rows


def compute_metrics(
    events: list[dict], samples: list[dict], start_ts: float, stopped_runs: list[tuple[float, float]], arrival_offsets: dict[float, int] | None = None
) -> dict:
    if not samples:
        return {"duration_s": 0, "n_arrivals": 0, "top_speed": 0, "avg_speed": 0, "avg_dwell_s": 0, "dwell_ratio": 0, "avg_abs_offset_cm": None}

    duration_s = samples[-1]["ts"] - start_ts
    n_arrivals = sum(1 for e in events if e["kind"] == "arrival")

    speeds: list[int] = [int(s["speed"]) for s in samples if s.get("speed") is not None]
    top_speed = max(speeds) if speeds else 0

    moving_speeds = [int(s["speed"]) for s in samples if s.get("speed") is not None and s.get("badge") in ("MOVING", "PASSING") and s["speed"] > 0]
    avg_speed = round(sum(moving_speeds) / len(moving_speeds)) if moving_speeds else 0

    # Dwell stats from STOPPED runs (each run = one platform dwell)
    dwell_durations = [end_ts - st for st, end_ts in stopped_runs]
    avg_dwell_s = round(sum(dwell_durations) / len(dwell_durations)) if dwell_durations else 0
    total_dwell_s = sum(dwell_durations)
    dwell_ratio = round(100 * total_dwell_s / duration_s) if duration_s > 0 else 0

    captured_offsets = [abs(v) for v in (arrival_offsets or {}).values()]
    avg_abs_offset_cm = round(sum(captured_offsets) / len(captured_offsets)) if captured_offsets else None

    return {
        "duration_s": duration_s,
        "n_arrivals": n_arrivals,
        "top_speed": top_speed,
        "avg_speed": avg_speed,
        "avg_dwell_s": avg_dwell_s,
        "dwell_ratio": dwell_ratio,
        "avg_abs_offset_cm": avg_abs_offset_cm,
    }


def compute_section_metrics(samples: list[dict], rs: float, re_: float, stopped_runs: list[tuple[float, float]]) -> dict:
    """Per-section stats for the section header strip."""
    in_window = [s for s in samples if rs <= s["ts"] <= re_]
    speeds: list[int] = [int(s["speed"]) for s in in_window if s.get("speed") is not None]
    top = max(speeds) if speeds else 0
    moving_speeds = [int(s["speed"]) for s in in_window if s.get("speed") is not None and s.get("badge") in ("MOVING", "PASSING") and s["speed"] > 0]
    avg = round(sum(moving_speeds) / len(moving_speeds)) if moving_speeds else 0

    # Total dwell within this section's window (clip to window bounds)
    dwell_s = 0.0
    for st, end_ts in stopped_runs:
        if end_ts < rs or st > re_:
            continue
        dwell_s += min(end_ts, re_) - max(st, rs)

    return {"top_speed": top, "avg_speed": avg, "dwell_s": int(round(dwell_s))}


# ─────────────────────────── styling ────────────────────────────


_ACCENT = "#226e91"
_ACCENT_LINE = "rgba(34,110,145,0.7)"
# Speed trace — purple, matching the Omiya museum drive-record aesthetic.
# Distinct from chrome's accent blue; readable against salmon limit-zone fill.
_SPEED_LINE = "#7c3aed"
_SPEED_FILL = "rgba(124,58,237,0.12)"
# Above-limit "danger zone" fill — single flat tint, shallow so the speed line
# remains readable through it. Same orange family as _LIMIT_LINE.
_LIMIT_ZONE_FILL = "rgba(234,88,12,0.10)"
# Start = origin station of the drive (first arrival captured)
_START_ACCENT = "#15803d"
_START_LINE = "rgba(21,128,61,0.75)"
# End = terminus of the drive (last arrival captured)
_END_ACCENT = "#b91c1c"
_END_LINE = "rgba(185,28,28,0.75)"
_STOPPED_FILL = "rgba(120,120,120,0.13)"
# Cab speed-limit line — orange, matching the Omiya museum drive-record aesthetic.
_LIMIT_LINE = "#ea580c"
_LIMIT_LINE_W = 4.0  # px; the line is drawn so its BOTTOM edge sits on the value (a ceiling cap), not centered

# Stopping-offset chip colour by |cm|. Tiers: ≤10 best, ≤30 good, ≤100 acceptable
# (game floor before screen-blacks-out on overrun), >100 bad.
_OFFSET_TIER_BEST = "#0d9488"  # teal-600
_OFFSET_TIER_GOOD = "#16a34a"  # green-600
_OFFSET_TIER_OK = "#d97706"  # amber-600
_OFFSET_TIER_BAD = "#dc2626"  # red-600


def _offset_tier_color(cm: int) -> str:
    a = abs(cm)
    if a <= 10:
        return _OFFSET_TIER_BEST
    if a <= 30:
        return _OFFSET_TIER_GOOD
    if a <= 100:
        return _OFFSET_TIER_OK
    return _OFFSET_TIER_BAD


def _format_offset_text(cm: int) -> str:
    """Sign convention: negative = stopped past the mark (overrun); shown with `-`.
    Positive and zero are unsigned (matches the in-game cell rendering)."""
    if cm < 0:
        return f"-{abs(cm)}cm"
    return f"{cm}cm"


# Brand-ish colours per JR East line. The accent strip at the top of the
# dashboard pulls from this; falls back to the default accent if unknown.
# Hex from JR East's own marketing palette where I could find it; a few are
# my best guesses by sight (corrigible — easy to update).
_LINE_COLOURS: dict[str, str] = {
    "keiyo": "#E60012",
    "yamanote": "#9ACD32",
    "saikyo": "#00B26C",
    "rinkai": "#00BFFF",
    "chuo": "#F15A22",
    "chuo_rapid": "#F15A22",
    "sobu": "#FFD400",
    "sobu_rapid": "#005FAE",
    "keihin": "#33A6BE",
    "keihin-tohoku": "#33A6BE",
    "yokosuka": "#1069B4",
    "tokaido": "#F68B1E",
    "takasaki": "#F39800",
    "utsunomiya": "#F39800",
    "joban": "#0072BC",
    "joban_rapid": "#0072BC",
    "musashino": "#F15A22",
    "nambu": "#FFD400",
    "nanbu": "#FFD400",
    "ome": "#F15A22",
}


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _disp_speed(s: dict):
    """Report display speed: decimal-precision (`speed_decimal`) when the log carries it,
    else the integer `speed` (older logs). The report shows decimal; the live status band
    stays integer by design (see auto_input/driver.py + tims/band.py)."""
    d = s.get("speed_decimal")
    return d if d is not None else s.get("speed")


def _hover_text(s: dict, meta: dict, start_ts: float) -> str:
    cs = s.get("curr_stop", -1)
    stops = meta.get("stops", [])
    name = stops[cs].get("name", "?") if 0 <= cs < len(stops) else "?"
    elapsed = s["ts"] - start_ts
    spd = _disp_speed(s)
    dst = s.get("distance")
    lim = s.get("speed_limit")
    spd_str = (f"{spd:.1f}" if isinstance(spd, float) else str(spd)) if spd is not None else "—"
    clock = datetime.fromtimestamp(s["ts"]).strftime("%H:%M:%S")
    lines = [
        f"<span style='color:#94a3b8'>+{_fmt_elapsed(elapsed)} · {clock}</span>",
        f"<b>{spd_str} km/h</b>",
    ]
    if lim is not None:
        lines.append(f"<span style='color:#ea580c'><b>制限</b> {lim} km/h</span>")
    if dst is not None:
        lines.append(f"<span style='color:#64748b'>{name}まで {dst} m</span>")
    return "<br>".join(lines)


# ─────────────────────────── per-section chart ────────────────────────────


def build_section_figure(
    meta: dict,
    start_ts: float,
    rs: float,
    re_: float,
    row_arrivals: list[dict],
    entry_arrival: dict | None,
    samples: list[dict],
    stopped_runs: list[tuple[float, float]],
    ymax: int,
    x_axis_duration_s: float,
    drive_first_arrival_ts: float | None = None,
    drive_last_arrival_ts: float | None = None,
    arrival_offsets: dict[float, int] | None = None,
    height: int = 240,
    compact: bool = False,
) -> go.Figure:
    """One section chart — speed line, station signposts, dwell/passing bands.
    No internal title or metrics — those are in the surrounding HTML."""
    stops = meta.get("stops", [])
    row_samples = [s for s in samples if rs <= s["ts"] <= re_]

    # Plot-area pixel height + px-per-data-unit. Single source, used by the limit-line
    # bottom-edge offset (below) AND the square-grid x-dtick sizing (further down).
    _plot_h = height - 52 - 40  # total height minus the t=52 / b=40 margins (see update_layout)
    _y_px_per_unit = _plot_h / max(ymax + 10, 1)
    # Shift the limit line up by half its pixel width so its BOTTOM edge lands on the
    # value (reads as a ceiling cap): px → data units via _y_px_per_unit.
    _limit_y_off = (_LIMIT_LINE_W / 2) / max(_y_px_per_unit, 1e-6)

    fig = go.Figure()

    # Background bands ──────────────────────────────────────────────
    for st_ts, end_ts in stopped_runs:
        if end_ts < rs or st_ts > re_:
            continue
        fig.add_vrect(
            x0=datetime.fromtimestamp(max(st_ts, rs)),
            x1=datetime.fromtimestamp(min(end_ts, re_)),
            fillcolor=_STOPPED_FILL,
            line_width=0,
            layer="below",
        )

    # Above-limit "danger zone" salmon fill (per-run rects) ──────────
    # Compute contiguous constant-limit runs first; each becomes a rect from
    # (ts_start, lim) to (ts_end, ymax) at layer="below" so the speed trace
    # paints over it.
    limit_runs: list[tuple[float, float, int]] = []
    _prev_lim: int | None = None
    _run_start: float | None = None
    for s in row_samples:
        lim_val = s.get("speed_limit")
        if lim_val != _prev_lim:
            if _prev_lim is not None and _run_start is not None:
                limit_runs.append((_run_start, s["ts"], _prev_lim))
            _run_start = s["ts"] if lim_val is not None else None
            _prev_lim = lim_val
    if _prev_lim is not None and _run_start is not None and row_samples:
        limit_runs.append((_run_start, row_samples[-1]["ts"], _prev_lim))

    for ts_s, ts_e, lim_val in limit_runs:
        if ymax <= lim_val:
            continue
        # Visible salmon-filled polygon (the danger zone above the limit).
        x_s = datetime.fromtimestamp(ts_s)
        x_e = datetime.fromtimestamp(ts_e)
        fig.add_trace(
            go.Scatter(
                x=[x_s, x_e, x_e, x_s, x_s],
                y=[lim_val, lim_val, ymax, ymax, lim_val],
                mode="lines",
                fill="toself",
                fillcolor=_LIMIT_ZONE_FILL,
                line=dict(width=0, color="rgba(0,0,0,0)"),
                hoveron="fills",
                hoverinfo="none",
                name="speed_limit_zone",
                showlegend=False,
            )
        )
        # Invisible hover strip centered on the line — extends ±4 km/h so
        # hovering ON or NEAR the line itself reliably fires the same hover
        # event the salmon zone fires (line traces alone don't fire hover
        # along their length, only at sample points).
        y_lo = max(0, lim_val - 4)
        y_hi = lim_val + 4
        fig.add_trace(
            go.Scatter(
                x=[x_s, x_e, x_e, x_s, x_s],
                y=[y_lo, y_lo, y_hi, y_hi, y_lo],
                mode="lines",
                fill="toself",
                fillcolor="rgba(0,0,0,0)",
                line=dict(width=0, color="rgba(0,0,0,0)"),
                hoveron="fills",
                hoverinfo="none",
                name="speed_limit_zone",
                showlegend=False,
            )
        )

    # Speed trace ───────────────────────────────────────────────────
    if row_samples:
        fig.add_trace(
            go.Scatter(
                x=[datetime.fromtimestamp(s["ts"]) for s in row_samples],
                y=[_disp_speed(s) if _disp_speed(s) is not None else 0 for s in row_samples],
                mode="lines",
                line=dict(color=_SPEED_LINE, width=4.0, shape="spline", smoothing=0.4),
                fill="tozeroy",
                fillcolor=_SPEED_FILL,
                hovertemplate="%{customdata}<extra></extra>",
                hoverlabel=dict(
                    bgcolor="white",
                    bordercolor=_SPEED_LINE,
                    font=dict(
                        color="#0f172a",
                        size=12,
                        family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif",
                    ),
                    align="left",
                ),
                customdata=[_hover_text(s, meta, start_ts) for s in row_samples],
                showlegend=False,
            )
        )

    # Speed-limit trace (cab signal) ──────────────────────────────────
    # Solid horizontal segments per run, no vertical risers at transitions.
    # Inserting None between runs breaks the line so plotly doesn't connect them.
    if limit_runs:
        # Sample-resolution points so hover triggers anywhere along the line.
        # When the value transitions L1→L2 at sample T, extend L1's line to T
        # before breaking — otherwise L1's line stops at the previous sample
        # and leaves a visible gap before the transition.
        xs_l: list[datetime | None] = []
        ys_l: list[int | None] = []
        prev_lim: int | None = None
        for s in row_samples:
            lim = s.get("speed_limit")
            cur_x = datetime.fromtimestamp(s["ts"])
            if lim != prev_lim and prev_lim is not None:
                # Extend previous run to the transition point, then break.
                xs_l.append(cur_x)
                ys_l.append(int(prev_lim) + _limit_y_off)
                xs_l.append(None)
                ys_l.append(None)
            if lim is not None:
                xs_l.append(cur_x)
                ys_l.append(int(lim) + _limit_y_off)
            prev_lim = lim
        fig.add_trace(
            go.Scatter(
                x=xs_l,
                y=ys_l,
                mode="lines",
                line=dict(color=_LIMIT_LINE, width=_LIMIT_LINE_W, shape="linear"),
                connectgaps=False,
                hoverinfo="none",
                name="speed_limit_line",
                showlegend=False,
            )
        )

        # Hidden-by-default static labels at the start of each limit run.
        # JS hover handler at the bottom of the page toggles their opacity
        # when the user hovers over the limit line or salmon zone.
        for ts_s, ts_e, lim_val in limit_runs:
            fig.add_annotation(
                x=datetime.fromtimestamp(ts_s),
                y=lim_val,
                text=f"<b>{lim_val}</b>",
                showarrow=False,
                yanchor="bottom",
                xanchor="left",
                xshift=1,
                yshift=0,
                font=dict(size=15, color=_LIMIT_LINE, weight="bold"),
                opacity=0,
                name="limit_label",
            )

    # Station signposts (solid vertical line + badge label) ─────────
    # `entry_arrival` (when present) is the previous row's last arrival sitting
    # AT this row's left edge — drawing it gives every row a station post at
    # its opening. row_arrivals are this row's own served stops.
    # Drive's first arrival = origin (green), last arrival = terminus (red).
    # Station name annotation sits in the top margin via yref="paper" so it
    # never collides with the y=ymax tick label and is unaffected by ymax.
    entry_ts = entry_arrival["ts"] if entry_arrival is not None else None
    posts_to_draw: list[dict] = ([entry_arrival] if entry_arrival is not None else []) + list(row_arrivals)
    for arr in posts_to_draw:
        cs = arr.get("curr_stop", -1)
        if not 0 <= cs < len(stops):
            continue
        name = stops[cs].get("name", "")
        if not name:
            continue

        if drive_first_arrival_ts is not None and arr["ts"] == drive_first_arrival_ts:
            post_bg, post_line = _START_ACCENT, _START_LINE
        elif drive_last_arrival_ts is not None and arr["ts"] == drive_last_arrival_ts:
            post_bg, post_line = _END_ACCENT, _END_LINE
        else:
            post_bg, post_line = _ACCENT, _ACCENT_LINE

        x = datetime.fromtimestamp(arr["ts"])
        fig.add_shape(
            type="line",
            x0=x,
            x1=x,
            y0=0,
            y1=ymax,  # post line spans full chart height; label sits above in the top margin
            line=dict(color=post_line, width=1.8),
            layer="above",
        )
        _name_font = 12 if compact else 14
        _name_pad = 4 if compact else 5
        fig.add_annotation(
            x=x,
            y=1.0,
            xref="x",
            yref="paper",
            text=f" {name} ",
            showarrow=False,
            yanchor="bottom",
            xanchor="center",
            font=dict(
                size=_name_font,
                color="white",
                weight="bold",
                family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif",
            ),
            bgcolor=post_bg,
            bordercolor=post_bg,
            borderwidth=0,
            borderpad=_name_pad,
        )

        # Stopping-offset chip: stacked just below the station name annotation.
        # Skip the entry signpost (its chip was drawn in the previous section).
        if arrival_offsets is None or arr["ts"] == entry_ts:
            continue
        offset_cm = arrival_offsets.get(arr["ts"])
        if offset_cm is None:
            continue
        chip_bg = _offset_tier_color(offset_cm)
        _chip_font = 11 if compact else 13
        _chip_pad = 3 if compact else 4
        fig.add_annotation(
            x=x,
            y=0.998 if compact else 0.965,
            xref="x",
            yref="paper",
            text=f" {_format_offset_text(offset_cm)} ",
            showarrow=False,
            yanchor="top",
            xanchor="center",
            font=dict(
                size=_chip_font,
                color="white",
                weight="bold",
                family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            ),
            bgcolor=chip_bg,
            bordercolor=chip_bg,
            borderwidth=0,
            borderpad=_chip_pad,
        )

    # Layout ────────────────────────────────────────────────────────
    fig.update_layout(
        height=height,
        # Compact (overview) drops the right-side y-tick labels to free horizontal
        # space for dense station packing, so its right margin can shrink too.
        margin=dict(l=64, r=16 if compact else 64, t=52, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        # Compact (overview) disables hover entirely — the overview is a nav
        # strip; the segment overlay handles hover/click. Zoom view uses
        # hovermode="x" so cursor anywhere over the chart triggers the speed
        # tooltip (not just on the line itself).
        hovermode=False if compact else "x",
        # Disable all zoom/pan/box-select interactions on the chart.
        dragmode=False,
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif", size=12),
    )
    # X-axis spans `x_axis_duration_s` from the section's start, regardless of
    # this section's own duration — sections shorter than the longest leave
    # blank space on the right, so all rows share the same minutes-per-pixel
    # scale and you can compare segment durations at a glance.
    x_end = rs + x_axis_duration_s
    # ── Square-grid sizing: pick MINOR x-dtick so one minor x-cell renders ≈
    # same pixel size as one minor y-cell (10 km/h, matching the y-axis minor
    # grid). MAJOR x-dtick is a coarser label-friendly interval — picked
    # independently so the chart isn't crowded with timestamps.
    # Assumes container ≈ 1550px plot-area (90vw on 1920px screen).
    _ASSUMED_PLOT_W = 1550
    # _plot_h / _y_px_per_unit hoisted to the top of the function (shared with the limit-line offset).
    # Target = one y-MINOR (10 km/h) in pixels, so x-minor matches y-minor.
    _target_x_px = 10 * _y_px_per_unit
    _target_x_s = _target_x_px * x_axis_duration_s / _ASSUMED_PLOT_W
    _minor_s = min(
        [5, 10, 15, 20, 30, 45, 60, 90, 120],
        key=lambda v: abs(v - _target_x_s),
    )
    # Major (with labels): aim for ~4–6 labels visible across the segment.
    # Pick the smallest nice value ≥ a duration-based floor.
    _label_floor = (
        15
        if x_axis_duration_s <= 90
        else 30 if x_axis_duration_s <= 300 else 60 if x_axis_duration_s <= 900 else 120 if x_axis_duration_s <= 1800 else 300
    )
    _major_s = next(
        (v for v in [15, 30, 60, 120, 300, 600] if v >= _label_floor and v >= _minor_s),
        max(_minor_s, _label_floor),
    )
    fig.update_xaxes(
        range=[datetime.fromtimestamp(rs), datetime.fromtimestamp(x_end)],
        tickformat="%H:%M",
        showgrid=True,
        gridcolor="rgba(140,140,140,0.55)",
        gridwidth=1,
        dtick=_major_s * 1000,
        showline=True,
        linecolor="rgba(150,150,150,0.5)",
        mirror="ticks",
        fixedrange=True,
        tickfont=dict(size=14, color="#334155", weight="bold"),
        minor=dict(
            dtick=_minor_s * 1000,
            showgrid=True,
            gridcolor="rgba(220,220,220,0.45)",
            gridwidth=0.5,
        ),
    )
    # Extend y-axis range 10 above the highest tick so station-post labels in
    # the top margin clear the y=ymax tick label. +10 isn't on a dtick=20
    # boundary so no label appears at the buffer top.
    fig.update_yaxes(
        range=[0, ymax + 10],
        rangemode="nonnegative",
        showgrid=True,
        gridcolor="rgba(200,200,200,0.35)",
        showline=True,
        linecolor="rgba(150,150,150,0.5)",
        mirror="ticks",
        fixedrange=True,
        title=dict(text="km/h", font=dict(size=13, color="#334155", weight="bold")),
        tickfont=dict(size=14, color="#334155", weight="bold"),
        tick0=0,
        dtick=20,
        minor=dict(
            dtick=10,
            showgrid=True,
            gridcolor="rgba(220,220,220,0.45)",
            gridwidth=0.5,
        ),
    )
    # Right-side y-axis labels via per-tick annotations (yaxis2 didn't render
    # reliably). Anchored at x=1 in paper coords so they sit on the right edge
    # of the plot, with xshift to position outside. Skipped on compact overview
    # — single-axis labelling there gives more horizontal room for station packing.
    if not compact:
        for tick_y in range(0, ymax + 1, 20):
            fig.add_annotation(
                x=1,
                y=tick_y,
                xref="paper",
                yref="y",
                text=str(tick_y),
                showarrow=False,
                xanchor="left",
                yanchor="middle",
                xshift=6,
                font=dict(size=14, color="#334155", weight="bold"),
            )
    return fig


# ─────────────────────────── HTML composition ────────────────────────────


_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif;
  background:
    /* Subtle paper-grain crosshatch — ~2% opacity, 22px cell. */
    repeating-linear-gradient(0deg,   rgba(120, 95, 60, 0.025) 0 1px, transparent 1px 22px),
    repeating-linear-gradient(90deg,  rgba(120, 95, 60, 0.025) 0 1px, transparent 1px 22px),
    #f6f3ec;
  color: #0f172a;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "tnum" 1, "ss01" 1;
}
.container {
  max-width: 90vw;
  margin: 0 auto;
  padding: 32px 32px 48px;
}
.line-accent {
  height: 6px;
  background: var(--line-color, #226e91);
  border-radius: 3px;
  margin-bottom: 22px;
}
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 36px;
  margin-bottom: 22px;
  flex-wrap: wrap;
}
.page-header-left {
  flex: 0 1 auto;
  min-width: 0;
}
.page-header-right {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  justify-content: flex-end;
}
.page-eyebrow {
  font-size: 14px;
  font-weight: 800;
  color: var(--line-color, #226e91);
  margin-bottom: 8px;
  letter-spacing: 0.04em;
}
.page-title {
  margin: 0;
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #0f172a;
  line-height: 1.2;
  font-family: 'Yu Mincho', 'YuMincho', 'Hiragino Mincho ProN', 'Hiragino Mincho Pro', 'MS Mincho', serif;
}
.page-subtitle {
  font-size: 14px;
  font-weight: 600;
  color: #475569;
  margin-top: 6px;
}
.metrics-card {
  display: flex;
  flex-wrap: wrap;
  gap: 26px;
  justify-content: flex-end;
}
.metric {
  background: transparent;
  padding: 0;
  text-align: right;
}
.metric .label {
  font-size: 13px;
  font-weight: 700;
  color: #64748b;
  margin-bottom: 4px;
  letter-spacing: 0.01em;
}
.metric .value {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1;
  letter-spacing: -0.01em;
}
.metric .unit {
  font-size: 13px;
  color: #64748b;
  font-weight: 600;
  margin-left: 3px;
}
.section {
  background: white;
  border: 1px solid #e2e8f0;
  border-top: 3px solid var(--line-color, #226e91);
  border-radius: 4px;
  margin-bottom: 16px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.06);
}
.overview-strip .section-body {
  position: relative;  /* anchor for the segment overlay */
}
.overview-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 12px 22px 6px;
}
.overview-eyebrow {
  font-size: 14px;
  font-weight: 800;
  color: var(--line-color, #226e91);
  letter-spacing: 0.04em;
}
.overview-title {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
  line-height: 1.2;
  font-family: 'Yu Mincho', 'YuMincho', 'Hiragino Mincho ProN', 'Hiragino Mincho Pro', 'MS Mincho', serif;
}
/* Segment overlay sits over the overview chart's plot area. Margins:
   compact chart layout l=64, r=16, t=52, b=40; section-body padding = 4px each side.
   So overlay = (4+64)px left, (4+16)px right, (4+52)px top, (4+40)px bottom.
   Each segment button is positioned by % of plot width. */
.overview-segments-overlay {
  position: absolute;
  top: 56px;
  bottom: 44px;
  left: 68px;
  right: 20px;
  pointer-events: none;
  z-index: 5;
}
.overview-seg {
  position: absolute;
  top: 0;
  bottom: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 0;
  margin: 0;
  pointer-events: auto;
  transition: background 0.15s ease-out, box-shadow 0.15s ease-out;
  /* Hint color is a fixed chrome-accent slate blue — independent of route's
     line-color, so it never collides with orange/salmon (speed-limit zone)
     or purple (speed curve). */
  box-shadow: inset 0 0 0 0 #226e91;
}
.overview-seg:hover {
  background: rgba(34, 110, 145, 0.10);
  box-shadow: inset 0 2px 0 0 #226e91;
}
.overview-seg.active {
  background: rgba(34, 110, 145, 0.18);
  box-shadow: inset 0 2px 0 0 #226e91, inset 0 -2px 0 0 #226e91;
}
.overview-seg.active:hover {
  background: rgba(34, 110, 145, 0.24);
}
.zoom-view {
  margin-bottom: 24px;
}
.zoom-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 18px;
  border-bottom: 1px solid #f1f5f9;
  background: #fafbfc;
}
.zoom-eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #226e91;
}
.seek-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px 8px;
  background: #fcfcfd;
  gap: 16px;
}
.seek-arrow {
  width: 32px;
  height: 32px;
  border: 1px solid #e2e8f0;
  background: white;
  border-radius: 50%;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: inherit;
  flex-shrink: 0;
  user-select: none;
}
.seek-arrow:hover:not(:disabled) {
  background: #f4f5f7;
  color: #0f172a;
}
.seek-arrow:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.seek-info {
  flex: 1;
  text-align: left;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}
.seek-eyebrow {
  font-size: 14px;
  font-weight: 800;
  color: var(--line-color, #226e91);
  letter-spacing: 0.04em;
}
.seek-counter {
  font-size: 13px;
  font-weight: 700;
  color: #64748b;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  margin-right: 4px;
}
.seek-title {
  font-size: 26px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
  line-height: 1.2;
  max-width: 100%;
  font-family: 'Yu Mincho', 'YuMincho', 'Hiragino Mincho ProN', 'Hiragino Mincho Pro', 'MS Mincho', serif;
}
.seekbar-wrap {
  position: relative;
  margin: 0 38px 18px;
  padding: 12px 0 28px;
  cursor: pointer;
  user-select: none;
}
.seekbar {
  position: relative;
  height: 4px;
  background: #e2e8f0;
  border-radius: 2px;
}
.seekbar-fill {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  background: rgba(34,110,145,0.35);
  border-radius: 2px;
  transition: width 0.22s ease-out;
  pointer-events: none;
}
.seekbar-current {
  position: absolute;
  top: -2px;
  bottom: -2px;
  background: #226e91;
  border-radius: 3px;
  transition: left 0.22s ease-out;
  pointer-events: none;
  z-index: 1;
  box-shadow: 0 0 0 3px rgba(34,110,145,0.18);
}
/* Passive station-name labels at segment boundaries (N+1 nodes for N segments). */
.seekbar-node {
  position: absolute;
  top: 100%;
  margin-top: 12px;
  transform: translateX(-50%);
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  font-family: inherit;
  font-feature-settings: inherit;
  white-space: nowrap;
  transition: color 0.15s ease-out;
  line-height: 1.2;
  pointer-events: none;
}
.seekbar-node::before {
  content: "";
  position: absolute;
  left: 50%;
  bottom: 100%;
  margin-bottom: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  transform: translate(-50%, 0);
  transition: background 0.15s ease-out;
}
.seekbar-node[data-edge="left"]  { transform: translateX(0); }
.seekbar-node[data-edge="right"] { transform: translateX(-100%); }
.seekbar-node.active {
  color: #226e91;
  font-weight: 700;
}
.seekbar-node.active::before {
  background: #226e91;
}
/* Invisible click target spanning the segment slice on the bar.
   z-index above .seekbar-current so clicks register; vertical extension
   covers the labels below for a generous click area. */
.seekbar-segment {
  position: absolute;
  top: -16px;
  bottom: -32px;
  background: transparent;
  border: 0;
  cursor: pointer;
  padding: 0;
  margin: 0;
  z-index: 2;
}
.segment-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 32px;
  padding: 14px 22px 16px;
  border-bottom: 1px solid #f1f5f9;
  background: #fafbfc;
}
.seg-stat {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
}
.seg-stat-label {
  font-size: 13px;
  font-weight: 700;
  color: #475569;
  letter-spacing: 0.02em;
}
.seg-stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
}
.seg-stat-value .unit {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin-left: 3px;
}
.seg-offset-chip {
  display: inline-flex;
  align-items: center;
  font-size: 24px;
  font-weight: 800;
  color: #78350f;
  background: linear-gradient(135deg, #fef3c7 0%, #fbbf24 55%, #f59e0b 100%);
  padding: 2px 14px;
  border-radius: 8px;
  letter-spacing: -0.01em;
  line-height: 1.1;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.22), 0 2px 6px rgba(245, 158, 11, 0.18);
}
.zoom-charts {
  position: relative;
  min-height: 560px;
}
.zoom-chart {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 4px;
  opacity: 1;
  visibility: visible;
  transform: translateX(0);
  transition: opacity 0.3s ease-out, transform 0.3s ease-out;
}
.zoom-chart.hidden {
  opacity: 0;
  /* visibility:hidden disables ALL mouse events on this chart (including
     plotly's inner hoverlayer which has pointer-events:all and overrides
     parent pointer-events:none). Without this, the LAST chart in DOM order
     intercepts events for whichever chart is on screen. */
  visibility: hidden;
  transform: translateX(0);
}
/* Animation classes — overlap visibility:visible with .hidden so animations
   are seen, then JS swaps to .hidden once the slide-out finishes. */
.zoom-chart.slide-out-left {
  opacity: 0;
  transform: translateX(-36px);
  visibility: visible;
}
.zoom-chart.slide-out-right {
  opacity: 0;
  transform: translateX(36px);
  visibility: visible;
}
.zoom-chart.slide-in-from-right {
  opacity: 0;
  transform: translateX(36px);
  visibility: visible;
  transition: none; /* set initial position instantly, then transition runs */
}
.zoom-chart.slide-in-from-left {
  opacity: 0;
  transform: translateX(-36px);
  visibility: visible;
  transition: none;
}
.section-body {
  padding: 4px 4px 4px;
}
.legend {
  display: flex;
  gap: 24px;
  /* Padding aligns the legend with the chart's plot area: chart layout has
     l=r=64 margin, so 64px left/right padding lines the legend up with
     the y-axis. */
  padding: 12px 64px 14px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  flex-wrap: wrap;
  border-top: 1px solid #f1f5f9;
  background: #fafbfc;
}
.legend-item { display: inline-flex; align-items: center; gap: 8px; }
.legend-swatch {
  width: 18px; height: 10px; border-radius: 2px; display: inline-block;
}
.legend-swatch.dashed {
  width: 22px; height: 0;
  border-radius: 0; border-bottom: 3px solid currentColor;
  background: transparent !important;
}
.legend-chip {
  display: inline-block;
  color: white;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  margin-right: 2px;
}
.footer {
  text-align: center;
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
  margin-top: 28px;
}
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _format_metric_value(label: str, metrics: dict) -> str:
    if label == "走行時間":
        return f'<span class="value">{_fmt_elapsed(metrics["duration_s"])}</span>'
    if label == "停車駅数":
        return f'<span class="value">{metrics["n_arrivals"]}</span>'
    if label == "最高速度":
        return f'<span class="value">{metrics["top_speed"]}<span class="unit">km/h</span></span>'
    if label == "平均速度":
        return f'<span class="value">{metrics["avg_speed"]}<span class="unit">km/h</span></span>'
    if label == "平均停止位置誤差":
        v = metrics.get("avg_abs_offset_cm")
        if v is None:
            return '<span class="value">—</span>'
        return f'<span class="value">{v}<span class="unit">cm</span></span>'
    return ""


def render_html_report(meta: dict, events: list[dict], samples: list[dict], stops_per_row: int, out_path: Path) -> None:
    if not samples:
        out_path.write_text("<html><body>No samples — empty drive log.</body></html>", encoding="utf-8")
        return

    start_ts = meta.get("start_ts", samples[0]["ts"])
    rows = split_into_rows(events, samples, stops_per_row)

    speeds_all: list[int] = [int(s["speed"]) for s in samples if s.get("speed") is not None]
    max_speed = max(speeds_all) if speeds_all else 0
    ymax = max(math.ceil((max_speed * 1.18) / 10) * 10, 100)

    stopped_runs = derive_stopped_runs(samples)
    arrival_offsets = derive_arrival_offsets(events, samples)
    metrics = compute_metrics(events, samples, start_ts, stopped_runs, arrival_offsets)

    # Drive-level first/last arrivals — origin/terminus tinting in section charts
    all_arrivals_sorted = sorted([e for e in events if e["kind"] == "arrival"], key=lambda e: e["ts"])
    drive_first_arrival_ts = all_arrivals_sorted[0]["ts"] if all_arrivals_sorted else None
    drive_last_arrival_ts = all_arrivals_sorted[-1]["ts"] if all_arrivals_sorted else None

    # Common x-axis duration: longest section's actual duration. Every section
    # uses this same span so the time scale (minutes-per-pixel) is identical
    # across rows; shorter sections show blank space on the right.
    x_axis_duration_s = max((re_ - rs for rs, re_, _, _ in rows), default=60.0)
    # Add a small padding (5%) so the right edge of the data isn't flush
    # against the chart border in the longest section.
    x_axis_duration_s *= 1.05

    # ── Page header
    route = meta.get("route", "")
    diagram = meta.get("diagram", "")
    line = meta.get("line", "")
    dest = meta.get("dest", "")
    stops_meta = meta.get("stops", [])
    origin = stops_meta[0].get("name", "") if stops_meta else ""
    _dt = datetime.fromtimestamp(start_ts)
    date_str = f"{_dt.year}年{_dt.month}月{_dt.day}日 {_dt:%H:%M}"

    title_parts = [p for p in [route, diagram] if p]
    title_text = " · ".join(title_parts) if title_parts else line.upper()
    subtitle_parts = [p for p in [f"{origin} → {dest}" if origin and dest else "", date_str] if p]
    subtitle_text = " · ".join(subtitle_parts)

    head = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>走行記録 — {_esc(title_text)}</title>
<style>{_CSS}</style>
</head>
<body style="--line-color: {_LINE_COLOURS.get(line.lower(), _ACCENT)};">
<div class="container">
"""

    line_accent_strip = '<div class="line-accent"></div>\n'

    metric_labels = ["走行時間", "停車駅数", "最高速度", "平均速度", "平均停止位置誤差"]
    metric_cells = "\n".join(
        f'<div class="metric"><div class="label">{label}</div><div class="value-wrap">{_format_metric_value(label, metrics)}</div></div>'
        for label in metric_labels
    )
    metrics_card = f'<div class="metrics-card">{metric_cells}</div>'

    page_header = f"""<div class="page-header">
  <div class="page-header-left">
    <div class="page-eyebrow">走行記録</div>
    <h1 class="page-title">{_esc(title_text)}</h1>
    <div class="page-subtitle">{_esc(subtitle_text)}</div>
  </div>
  <div class="page-header-right">
    {metrics_card}
  </div>
</div>
"""

    legend = f"""<div class="legend">
  <span class="legend-item"><span class="legend-swatch" style="background:{_SPEED_LINE};"></span>速度</span>
  <span class="legend-item" style="color:{_LIMIT_LINE};"><span class="legend-swatch dashed"></span><span style="color:#64748b;">制限速度</span></span>
  <span class="legend-item"><span class="legend-swatch" style="background:rgba(120,120,120,0.4);"></span>停車中</span>
  <span class="legend-item"><span class="legend-chip" style="background:{_OFFSET_TIER_BEST};">0cm</span>停止位置目標誤差（−は行き過ぎ）</span>
</div>
"""

    # ── Overview row cards (rendered FIRST so the first chart in DOM order
    # inlines plotly.js — overview cards sit above the zoom view in the body).
    chart_idx = 0  # global counter so only the first chart inlines plotly.js
    section_cards: list[str] = []
    for i, (rs, re_, row_arrivals, entry_arrival) in enumerate(rows):
        fig = build_section_figure(
            meta,
            start_ts,
            rs,
            re_,
            row_arrivals,
            entry_arrival,
            samples,
            stopped_runs,
            ymax,
            x_axis_duration_s=re_ - rs,
            drive_first_arrival_ts=drive_first_arrival_ts,
            drive_last_arrival_ts=drive_last_arrival_ts,
            arrival_offsets=arrival_offsets,
            compact=True,
        )
        chart_html = fig.to_html(
            full_html=False,
            include_plotlyjs="inline" if chart_idx == 0 else False,
            div_id=f"chart_{i}",
            config={"displayModeBar": False, "responsive": True},
        )
        chart_idx += 1
        # Build segment-overlay buttons. Each spans the segment's x range as a
        # percentage of THIS row's chart plot area. With the default
        # `--per-row 999` there's a single row containing every segment; with a
        # smaller --per-row, segments are filtered + clamped to the row window
        # so each row's overlay only references segments visible on its chart.
        chart_start_ts = rs
        chart_span = max(re_ - rs, 1.0)
        seg_overlay: list[str] = []
        for seg_i, arr in enumerate(all_arrivals_sorted):
            seg_start_ts = all_arrivals_sorted[seg_i - 1]["ts"] if seg_i > 0 else samples[0]["ts"]
            # Last segment extends to chart end so the post-terminus dwell is
            # also clickable; non-last segments end at the arrival itself.
            seg_end_ts = re_ if seg_i == len(all_arrivals_sorted) - 1 else arr["ts"]
            # Skip segments fully outside this row's window.
            if seg_end_ts < rs or seg_start_ts > re_:
                continue
            seg_start_ts = max(seg_start_ts, rs)
            seg_end_ts = min(seg_end_ts, re_)
            left_pct = (seg_start_ts - chart_start_ts) / chart_span * 100
            width_pct = (seg_end_ts - seg_start_ts) / chart_span * 100
            seg_overlay.append(
                f'<button class="overview-seg" type="button" data-segment-idx="{seg_i}" '
                f'style="left: {left_pct:.3f}%; width: {width_pct:.3f}%;" '
                f'aria-label="区間 {seg_i+1}"></button>'
            )

        # Overview is a navigation strip — no per-row stat chips, no legend.
        # Header gives it identity ("運転曲線 / 全区間"); the chart is the ribbon;
        # the overlay turns it into a click-to-jump nav.
        section_cards.append(f"""<div class="section overview-strip">
  <div class="overview-header">
    <span class="overview-eyebrow">運転曲線</span>
    <span class="overview-title">全区間</span>
  </div>
  <div class="section-body">
    {chart_html}
    <div class="overview-segments-overlay">{"".join(seg_overlay)}</div>
  </div>
</div>
""")

    # ── Per-segment zoomed view (primary detail) ──────────────────────
    # One chart per arrival = one segment (prev arrival → this arrival + dwell).
    # Pre-rendered into hidden divs; left/right arrows + clickable seekbar
    # ticks + keyboard arrow keys swap which chart is visible.
    zoom_block_html = ""
    if all_arrivals_sorted:
        seg_titles_for_js: list[str] = []
        seg_summaries_for_js: list[str] = []
        zoom_charts: list[str] = []
        last_sample_ts = samples[-1]["ts"]
        n_segs = len(all_arrivals_sorted)

        # N+1 boundary station names (one per node). Node 0 is the segment 0
        # "from" — derived as `arrival[0].curr_stop - 1` if valid, else
        # falls back to the route's first station.
        node_names: list[str] = []
        first_cs = all_arrivals_sorted[0].get("curr_stop", -1)
        if 0 < first_cs and first_cs - 1 < len(stops_meta):
            node_names.append(stops_meta[first_cs - 1].get("name", "?"))
        else:
            node_names.append(stops_meta[0].get("name", "Start") if stops_meta else "Start")

        for i, arr in enumerate(all_arrivals_sorted):
            arr_ts = arr["ts"]
            cs = arr.get("curr_stop", -1)
            to_name = stops_meta[cs].get("name", "?") if 0 <= cs < len(stops_meta) else "?"
            node_names.append(to_name)

            rs_z = all_arrivals_sorted[i - 1]["ts"] if i > 0 else samples[0]["ts"]
            re_z = arr_ts + 30.0
            if i < n_segs - 1:
                re_z = min(re_z, all_arrivals_sorted[i + 1]["ts"])
            re_z = min(re_z, last_sample_ts)
            entry_z = all_arrivals_sorted[i - 1] if i > 0 else None

            from_name = node_names[i]  # node N corresponds to segment N's "from"
            seg_title = f"{from_name} → {to_name}"
            seg_titles_for_js.append(seg_title)

            fig_z = build_section_figure(
                meta,
                start_ts,
                rs_z,
                re_z,
                [arr],
                entry_z,
                samples,
                stopped_runs,
                ymax,
                x_axis_duration_s=re_z - rs_z,
                drive_first_arrival_ts=drive_first_arrival_ts,
                drive_last_arrival_ts=drive_last_arrival_ts,
                arrival_offsets=arrival_offsets,
                height=540,
            )
            chart_html_z = fig_z.to_html(
                full_html=False,
                include_plotlyjs="inline" if chart_idx == 0 else False,
                div_id=f"zoom_chart_{i}",
                config={"displayModeBar": False, "responsive": True},
            )
            chart_idx += 1
            hidden_cls = "" if i == 0 else " hidden"
            zoom_charts.append(f'<div class="zoom-chart{hidden_cls}" data-segment-idx="{i}">{chart_html_z}</div>')

            # ── Segment summary strip (one-line stats above the chart)
            seg_metrics = compute_section_metrics(samples, rs_z, re_z, stopped_runs)
            seg_max_limit = max(
                (s["speed_limit"] for s in samples if rs_z <= s["ts"] <= re_z and s.get("speed_limit") is not None),
                default=None,
            )
            seg_offset = (arrival_offsets or {}).get(arr["ts"])
            stats: list[str] = []
            stats.append(
                f'<span class="seg-stat"><span class="seg-stat-label">最高速度</span>'
                f'<span class="seg-stat-value">{seg_metrics["top_speed"]}<span class="unit">km/h</span></span></span>'
            )
            stats.append(
                f'<span class="seg-stat"><span class="seg-stat-label">所要時間</span>'
                f'<span class="seg-stat-value">{_fmt_elapsed(re_z - rs_z)}</span></span>'
            )
            if seg_max_limit is not None:
                stats.append(
                    f'<span class="seg-stat"><span class="seg-stat-label">最高制限速度</span>'
                    f'<span class="seg-stat-value">{seg_max_limit}<span class="unit">km/h</span></span></span>'
                )
            if seg_offset is not None:
                tier_color = _offset_tier_color(seg_offset)
                offset_text = _format_offset_text(seg_offset)
                if abs(seg_offset) <= 10:
                    value_html = f'<span class="seg-offset-chip">{offset_text}</span>'
                else:
                    value_html = f'<span class="seg-stat-value" style="color:{tier_color};">' f"{offset_text}</span>"
                stats.append(f'<span class="seg-stat"><span class="seg-stat-label">停止位置目標誤差</span>' f"{value_html}</span>")
            seg_summaries_for_js.append("".join(stats))

        # Build seekbar elements: N+1 nodes (passive labels) + N segment buttons (clickable slices)
        seek_nodes_html: list[str] = []
        for i, name in enumerate(node_names):
            pos = i / n_segs * 100
            edge_attr = ""
            if i == 0:
                edge_attr = ' data-edge="left"'
            elif i == len(node_names) - 1:
                edge_attr = ' data-edge="right"'
            active_cls = " active" if i in (0, 1) else ""
            seek_nodes_html.append(
                f'<div class="seekbar-node{active_cls}"{edge_attr} data-node-idx="{i}" style="left: {pos:.3f}%;">{_esc(name)}</div>'
            )

        seek_segments_html: list[str] = []
        for i in range(n_segs):
            seg_left = i / n_segs * 100
            seg_w = 100 / n_segs
            seek_segments_html.append(
                f'<button class="seekbar-segment" type="button" data-segment-idx="{i}" '
                f'style="left: {seg_left:.3f}%; width: {seg_w:.3f}%;" '
                f'aria-label="{_esc(seg_titles_for_js[i])}"></button>'
            )

        # Initial state: segment 0 is active
        seg_w_pct = 100.0 / n_segs
        seek_fill_w = seg_w_pct  # bar fills 1 segment's worth at start
        seek_curr_left = 0.0  # current-slice highlight starts at left edge
        prev_disabled = "disabled" if n_segs <= 1 else ""
        next_disabled = "disabled" if n_segs <= 1 else ""

        # JS-side title list (already escaped per element)
        seg_titles_json = json.dumps(seg_titles_for_js, ensure_ascii=False)
        seg_summaries_json = json.dumps(seg_summaries_for_js, ensure_ascii=False)

        zoom_block_html = f"""<div class="section zoom-view">
  <div class="seek-row">
    <button class="seek-arrow seek-prev" aria-label="前の区間" {prev_disabled}>◀</button>
    <div class="seek-info">
      <span class="seek-eyebrow">運転曲線</span>
      <span class="seek-title">{_esc(seg_titles_for_js[0])}</span>
    </div>
    <span class="seek-counter">01 / {n_segs:02d}</span>
    <button class="seek-arrow seek-next" aria-label="次の区間" {next_disabled}>▶</button>
  </div>
  <div class="segment-summary">{seg_summaries_for_js[0]}</div>
  <div class="zoom-charts">{"".join(zoom_charts)}</div>
  {legend}
  <div class="seekbar-wrap">
    <div class="seekbar">
      <div class="seekbar-fill" style="width: {seek_fill_w:.3f}%;"></div>
      <div class="seekbar-current" style="left: {seek_curr_left:.3f}%; width: {seg_w_pct:.3f}%;"></div>
      {"".join(seek_segments_html)}
      {"".join(seek_nodes_html)}
    </div>
  </div>
</div>
<script>
(function() {{
  var total = {n_segs};
  var segWidth = 100 / total;
  var titles = {seg_titles_json};
  var summaries = {seg_summaries_json};
  var active = 0;

  function show(idx) {{
    if (idx < 0 || idx >= total) return;
    if (idx === active) return;
    var dir = idx > active ? 'forward' : 'backward';
    var oldIdx = active;
    active = idx;
    var counter = String(idx + 1).padStart(2, '0') + ' / ' + String(total).padStart(2, '0');
    document.querySelector('.seek-counter').textContent = counter;
    document.querySelector('.seek-title').textContent = titles[idx];
    var summaryEl = document.querySelector('.segment-summary');
    if (summaryEl) {{ summaryEl.innerHTML = summaries[idx]; }}
    var transitionMs = 320;
    document.querySelectorAll('.zoom-chart').forEach(function(c) {{
      c.classList.remove('slide-out-left', 'slide-out-right', 'slide-in-from-left', 'slide-in-from-right');
      var ci = parseInt(c.dataset.segmentIdx, 10);
      if (ci === oldIdx) {{
        // Old chart slides out — forward → exits left, backward → exits right.
        c.classList.remove('hidden');
        c.classList.add(dir === 'forward' ? 'slide-out-left' : 'slide-out-right');
        setTimeout(function() {{
          c.classList.add('hidden');
          c.classList.remove('slide-out-left', 'slide-out-right');
        }}, transitionMs);
      }} else if (ci === idx) {{
        // New chart starts off-screen, then animates to center.
        c.classList.remove('hidden');
        c.classList.add(dir === 'forward' ? 'slide-in-from-right' : 'slide-in-from-left');
        // Force reflow so the no-transition initial state takes effect, then
        // remove the slide-in class so the regular transition kicks in.
        void c.offsetWidth;
        c.classList.remove('slide-in-from-right', 'slide-in-from-left');
        if (window.Plotly) {{
          var plotDiv = c.querySelector('.plotly-graph-div, .js-plotly-plot');
          if (plotDiv) {{ window.Plotly.Plots.resize(plotDiv); }}
        }}
      }} else {{
        c.classList.add('hidden');
      }}
    }});
    // Highlight both boundary nodes of the active segment (segment i is
    // bounded by node[i] and node[i+1]).
    document.querySelectorAll('.seekbar-node').forEach(function(n) {{
      var ni = parseInt(n.dataset.nodeIdx, 10);
      n.classList.toggle('active', ni === idx || ni === idx + 1);
    }});
    document.querySelector('.seekbar-fill').style.width = ((idx + 1) * segWidth) + '%';
    document.querySelector('.seekbar-current').style.left = (idx * segWidth) + '%';
    document.querySelector('.seek-prev').disabled = (idx === 0);
    document.querySelector('.seek-next').disabled = (idx === total - 1);
  }}

  // Expose for the overview-click handler — clicks on overview segment overlay
  // call window.showZoomSegment(idx).
  window.showZoomSegment = show;
  // Notify listeners (overview overlay) when active segment changes so they
  // can update their highlight band.
  var origShow = show;
  show = function(idx) {{
    origShow(idx);
    document.dispatchEvent(new CustomEvent('zoomSegmentChanged', {{ detail: {{ idx: active }} }}));
  }};
  window.showZoomSegment = show;
  document.querySelector('.seek-prev').addEventListener('click', function() {{ show(active - 1); }});
  document.querySelector('.seek-next').addEventListener('click', function() {{ show(active + 1); }});
  // Each segment button covers its full slice (top:-16px / bottom:-32px
  // extends the click area to cover the labels below). Click anywhere in
  // the slice → activate that segment.
  document.querySelectorAll('.seekbar-segment').forEach(function(s) {{
    s.addEventListener('click', function() {{
      show(parseInt(s.dataset.segmentIdx, 10));
    }});
  }});
  document.addEventListener('keydown', function(e) {{
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowLeft') {{ show(active - 1); }}
    else if (e.key === 'ArrowRight') {{ show(active + 1); }}
  }});

  show(0);
}})();
</script>
"""

    # JS: hover over the speed-limit line or salmon zone reveals the static
    # limit-value labels (annotations with name="limit_label" that are
    # opacity=0 by default). Unhover hides them again.
    limit_hover_js = """<script>
window.addEventListener('load', function() {
  function setupChart(div) {
    if (!div || !div.layout) return;
    var ann = div.layout.annotations || [];
    var indices = [];
    for (var i = 0; i < ann.length; i++) {
      if (ann[i].name === 'limit_label') indices.push(i);
    }
    if (indices.length === 0) return;
    function setOpacity(value) {
      var updates = {};
      for (var k = 0; k < indices.length; k++) {
        updates['annotations[' + indices[k] + '].opacity'] = value;
      }
      window.Plotly.relayout(div, updates);
    }
    div.on('plotly_hover', function(data) {
      if (!data || !data.points) return;
      // Scan all hovered points; with hovermode="x" multiple traces fire.
      for (var p = 0; p < data.points.length; p++) {
        var nm = data.points[p].fullData && data.points[p].fullData.name;
        if (nm === 'speed_limit_line' || nm === 'speed_limit_zone') {
          setOpacity(1);
          return;
        }
      }
    });
    div.on('plotly_unhover', function() { setOpacity(0); });
  }
  document.querySelectorAll('[id^="chart_"], [id^="zoom_chart_"]').forEach(setupChart);
});
</script>
"""

    _gen_dt = datetime.now()
    _gen_str = f"{_gen_dt.year}年{_gen_dt.month}月{_gen_dt.day}日 {_gen_dt:%H:%M}"
    overview_nav_js = """<script>
(function() {
  var segs = document.querySelectorAll('.overview-seg');
  if (!segs.length) return;
  function setActive(idx) {
    segs.forEach(function(s) {
      var si = parseInt(s.dataset.segmentIdx, 10);
      s.classList.toggle('active', si === idx);
    });
  }
  segs.forEach(function(s) {
    s.addEventListener('click', function() {
      var idx = parseInt(s.dataset.segmentIdx, 10);
      if (window.showZoomSegment) {
        window.showZoomSegment(idx);
      }
      var zoomEl = document.querySelector('.zoom-view');
      if (zoomEl) zoomEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
  document.addEventListener('zoomSegmentChanged', function(e) {
    if (e && e.detail && typeof e.detail.idx === 'number') setActive(e.detail.idx);
  });
  // Initial: zoom view starts on segment 0.
  setActive(0);
})();
</script>
"""
    footer = f'<div class="footer">生成 {_gen_str} · {_esc(out_path.stem.replace(".html",""))}.jsonl</div>\n' + limit_hover_js + overview_nav_js

    # Overview rows now sit immediately under the header (acting as both
    # summary AND nav). Metrics merged into the header (right side).
    body = line_accent_strip + page_header + "".join(section_cards) + zoom_block_html + footer
    out_path.write_text(head + body + "</div></body></html>", encoding="utf-8")


# ─────────────────────────── CLI ────────────────────────────


def out_path_for(jsonl_path: Path) -> Path:
    return ROOT / f"{jsonl_path.stem}.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an interactive HTML drive report from a blackbox JSONL.")
    parser.add_argument("path", nargs="?", help="JSONL path (default: most recent in _recordings/)")
    parser.add_argument("--out", help="Output HTML path (default: <jsonl_stem>.html at project root)")
    parser.add_argument("--per-row", type=int, default=999, help="Stops per overview row (default: 999 = single-row whole drive).")
    args = parser.parse_args()

    if args.path:
        jsonl = Path(args.path)
    else:
        if not RECORDINGS_DIR.exists():
            print("No _recordings/ folder yet. Run a drive with OCR Auto-PA on first.", file=sys.stderr)
            return 1
        candidates = sorted(RECORDINGS_DIR.glob("drive_*.jsonl"))
        if not candidates:
            print(f"No drive logs found in {RECORDINGS_DIR}/", file=sys.stderr)
            return 1
        jsonl = candidates[-1]

    if not jsonl.exists():
        print(f"Not found: {jsonl}", file=sys.stderr)
        return 1

    print(f"Loading {jsonl}")
    meta, events, samples = load_jsonl(jsonl)
    n_arr = sum(1 for e in events if e["kind"] == "arrival")
    n_dep = sum(1 for e in events if e["kind"] == "departure")
    n_pas = sum(1 for e in events if e["kind"] == "passing_start")
    print(f"  meta: route={meta.get('route','?')} diagram={meta.get('diagram','?')} stops={len(meta.get('stops',[]))}")
    print(f"  events: {len(events)} ({n_arr} arrivals, {n_dep} departures, {n_pas} passing)")
    print(f"  samples: {len(samples)}")

    out = Path(args.out) if args.out else out_path_for(jsonl)
    render_html_report(meta, events, samples, args.per_row, out)
    size_mb = out.stat().st_size / (1024 * 1024)
    n_rows = math.ceil(n_arr / args.per_row) if n_arr else 1
    print(f"Wrote: {out} ({size_mb:.1f} MB)  sections={n_rows}  per-section={args.per_row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

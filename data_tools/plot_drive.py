"""Render an interactive HTML drive report from a blackbox JSONL.

Reads the three record types written by `auto_input.AutoDriver`:
    _type=meta    — route + per-stop dicts (name/english/furigana/stops_here/...)
    _type=event   — arrival / departure / passing_start / passing_end
    _type=sample  — one OCR cycle (speed / distance / badge / sim state)

Output structure (custom HTML page, plotly inlined):
    ┌─ Drive · {route} {diagram}
    │  shortdate · 蘇我 → 東京
    ├─ Metrics card  [Duration | Stops | Max | Avg moving | % stopped | PA fires]
    ├─ Section 1 — 蘇我 → 検見川浜  · 5 stops · 12 min
    │   └─ Plotly speed chart for this window
    ├─ Section 2 — ...
    └─ ...

Each section is its own card with header + Plotly chart. Pan/zoom is
per-section; y is clamped non-negative.

CLI:
    uv run python data_tools/plot_drive.py
    uv run python data_tools/plot_drive.py path/to/drive.jsonl
    uv run python data_tools/plot_drive.py --per-row 8

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

ROOT = Path(__file__).parent.parent
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


def derive_passing_runs(events: list[dict], samples: list[dict]) -> list[tuple[float, float, int]]:
    runs: list[tuple[float, float, int]] = []
    open_start: float | None = None
    open_curr = -1
    for ev in events:
        if ev["kind"] == "passing_start":
            open_start = ev["ts"]
            open_curr = ev.get("curr_stop", -1)
        elif ev["kind"] == "passing_end" and open_start is not None:
            runs.append((open_start, ev["ts"], open_curr))
            open_start = None
            open_curr = -1
    if open_start is not None and samples:
        runs.append((open_start, samples[-1]["ts"], open_curr))
    return runs


def find_passing_station_name(meta: dict, curr_stop: int) -> str | None:
    stops = meta.get("stops", [])
    if not 0 <= curr_stop < len(stops) or curr_stop == 0:
        return None
    prev = stops[curr_stop - 1]
    if not prev.get("stops_here", True):
        return prev.get("name", "")
    return None


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


def compute_metrics(events: list[dict], samples: list[dict], start_ts: float, stopped_runs: list[tuple[float, float]]) -> dict:
    if not samples:
        return {"duration_s": 0, "n_arrivals": 0, "top_speed": 0, "avg_speed": 0, "avg_dwell_s": 0, "dwell_ratio": 0}

    duration_s = samples[-1]["ts"] - start_ts
    n_arrivals = sum(1 for e in events if e["kind"] == "arrival")

    speeds: list[int] = [int(s["speed"]) for s in samples if s.get("speed") is not None]
    top_speed = max(speeds) if speeds else 0

    moving_speeds = [
        int(s["speed"]) for s in samples
        if s.get("speed") is not None and s.get("badge") in ("MOVING", "PASSING") and s["speed"] > 0
    ]
    avg_speed = round(sum(moving_speeds) / len(moving_speeds)) if moving_speeds else 0

    # Dwell stats from STOPPED runs (each run = one platform dwell)
    dwell_durations = [end_ts - st for st, end_ts in stopped_runs]
    avg_dwell_s = round(sum(dwell_durations) / len(dwell_durations)) if dwell_durations else 0
    total_dwell_s = sum(dwell_durations)
    dwell_ratio = round(100 * total_dwell_s / duration_s) if duration_s > 0 else 0

    return {
        "duration_s": duration_s,
        "n_arrivals": n_arrivals,
        "top_speed": top_speed,
        "avg_speed": avg_speed,
        "avg_dwell_s": avg_dwell_s,
        "dwell_ratio": dwell_ratio,
    }


def compute_section_metrics(samples: list[dict], rs: float, re_: float, stopped_runs: list[tuple[float, float]]) -> dict:
    """Per-section stats for the section header strip."""
    in_window = [s for s in samples if rs <= s["ts"] <= re_]
    speeds: list[int] = [int(s["speed"]) for s in in_window if s.get("speed") is not None]
    top = max(speeds) if speeds else 0
    moving_speeds = [
        int(s["speed"]) for s in in_window
        if s.get("speed") is not None and s.get("badge") in ("MOVING", "PASSING") and s["speed"] > 0
    ]
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
_ACCENT_FILL = "rgba(34,110,145,0.16)"
_ACCENT_LINE = "rgba(34,110,145,0.7)"
# Start = origin station of the drive (first arrival captured)
_START_ACCENT = "#15803d"
_START_LINE = "rgba(21,128,61,0.75)"
# End = terminus of the drive (last arrival captured)
_END_ACCENT = "#b91c1c"
_END_LINE = "rgba(185,28,28,0.75)"
_PASSING_ACCENT = "#c97f2c"
_PASSING_FILL = "rgba(201,127,44,0.10)"
_PASSING_LINE = "rgba(201,127,44,0.7)"
_STOPPED_FILL = "rgba(120,120,120,0.13)"

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


def _hover_text(s: dict, meta: dict, start_ts: float) -> str:
    cs = s.get("curr_stop", -1)
    stops = meta.get("stops", [])
    name = stops[cs].get("name", "?") if 0 <= cs < len(stops) else "?"
    elapsed = s["ts"] - start_ts
    spd = s.get("speed")
    dst = s.get("distance")
    bdg = s.get("badge") or "?"
    # Read renamed `*_observed` keys; fall back to legacy `*_fired` for old logs.
    dep = "✓" if s.get("departure_observed", s.get("departure_fired")) else "·"
    arr = "✓" if s.get("arrival_observed", s.get("arrival_fired")) else "·"
    return (
        f"<b>+{_fmt_elapsed(elapsed)}</b>  ({datetime.fromtimestamp(s['ts']).strftime('%H:%M:%S')})<br>"
        f"<b>{spd if spd is not None else '—'} km/h</b><br>"
        f"distance to {name}: {dst if dst is not None else '—'} m<br>"
        f"badge: {bdg}<br>"
        f"PA: dep {dep} · arr {arr}"
    )


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
    passing_runs: list[tuple[float, float, int]],
    ymax: int,
    x_axis_duration_s: float,
    drive_first_arrival_ts: float | None = None,
    drive_last_arrival_ts: float | None = None,
) -> go.Figure:
    """One section chart — speed line, station signposts, dwell/passing bands.
    No internal title or metrics — those are in the surrounding HTML."""
    stops = meta.get("stops", [])
    row_samples = [s for s in samples if rs <= s["ts"] <= re_]

    fig = go.Figure()

    # Background bands ──────────────────────────────────────────────
    for st_ts, end_ts in stopped_runs:
        if end_ts < rs or st_ts > re_:
            continue
        fig.add_vrect(
            x0=datetime.fromtimestamp(max(st_ts, rs)),
            x1=datetime.fromtimestamp(min(end_ts, re_)),
            fillcolor=_STOPPED_FILL, line_width=0, layer="below",
        )
    for st_ts, end_ts, _ in passing_runs:
        if end_ts < rs or st_ts > re_:
            continue
        fig.add_vrect(
            x0=datetime.fromtimestamp(max(st_ts, rs)),
            x1=datetime.fromtimestamp(min(end_ts, re_)),
            fillcolor=_PASSING_FILL, line_width=0, layer="below",
        )

    # Speed trace ───────────────────────────────────────────────────
    if row_samples:
        fig.add_trace(go.Scatter(
            x=[datetime.fromtimestamp(s["ts"]) for s in row_samples],
            y=[int(s["speed"]) if s.get("speed") is not None else 0 for s in row_samples],
            mode="lines",
            line=dict(color=_ACCENT, width=2.0, shape="spline", smoothing=0.4),
            fill="tozeroy", fillcolor=_ACCENT_FILL,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[_hover_text(s, meta, start_ts) for s in row_samples],
            showlegend=False,
        ))

    # Station signposts (solid vertical line + badge label) ─────────
    # `entry_arrival` (when present) is the previous row's last arrival sitting
    # AT this row's left edge — drawing it gives every row a station post at
    # its opening. row_arrivals are this row's own served stops.
    # Drive's first arrival = origin (green), last arrival = terminus (red).
    label_y = ymax * 0.93
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
            x0=x, x1=x, y0=0, y1=label_y - 4,
            line=dict(color=post_line, width=1.8),
            layer="above",
        )
        fig.add_annotation(
            x=x, y=label_y, text=f"  {name}  ",
            showarrow=False, yanchor="bottom", xanchor="center",
            font=dict(size=13, color="white", family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif"),
            bgcolor=post_bg, bordercolor=post_bg,
            borderwidth=0, borderpad=4,
        )

    # Passing-station markers ───────────────────────────────────────
    for st_ts, _, curr_stop in passing_runs:
        if not (rs <= st_ts <= re_):
            continue
        passing_name = find_passing_station_name(meta, curr_stop)
        x = datetime.fromtimestamp(st_ts)
        fig.add_shape(
            type="line",
            x0=x, x1=x, y0=0, y1=ymax * 0.7,
            line=dict(color=_PASSING_LINE, width=1.5, dash="dash"),
            layer="above",
        )
        if passing_name:
            fig.add_annotation(
                x=x, y=ymax * 0.72, text=f" {passing_name} ",
                showarrow=False, yanchor="bottom", xanchor="center",
                font=dict(size=11, color="white", family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif"),
                bgcolor=_PASSING_ACCENT, bordercolor=_PASSING_ACCENT,
                borderwidth=0, borderpad=3,
            )

    # Layout ────────────────────────────────────────────────────────
    fig.update_layout(
        height=240,
        margin=dict(l=56, r=24, t=12, b=36),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        hovermode="closest",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif", size=12),
    )
    # X-axis spans `x_axis_duration_s` from the section's start, regardless of
    # this section's own duration — sections shorter than the longest leave
    # blank space on the right, so all rows share the same minutes-per-pixel
    # scale and you can compare segment durations at a glance.
    x_end = rs + x_axis_duration_s
    fig.update_xaxes(
        range=[datetime.fromtimestamp(rs), datetime.fromtimestamp(x_end)],
        tickformat="%H:%M",
        showgrid=True, gridcolor="rgba(200,200,200,0.35)",
        showline=True, linecolor="rgba(150,150,150,0.5)",
        tickfont=dict(size=11, color="#6b7280"),
    )
    fig.update_yaxes(
        range=[0, ymax],
        rangemode="nonnegative",
        showgrid=True, gridcolor="rgba(200,200,200,0.35)",
        showline=True, linecolor="rgba(150,150,150,0.5)",
        title=dict(text="km/h", font=dict(size=11, color="#6b7280")),
        tickfont=dict(size=11, color="#6b7280"),
    )
    return fig


# ─────────────────────────── HTML composition ────────────────────────────


_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif;
  background: #f4f5f7;
  color: #0f172a;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "tnum" 1, "ss01" 1;
}
.container {
  max-width: 1340px;
  margin: 0 auto;
  padding: 32px 32px 48px;
}
.line-accent {
  height: 4px;
  background: var(--line-color, #226e91);
  border-radius: 2px;
  margin-bottom: 18px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid #e2e8f0;
  gap: 24px;
}
.page-title-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
}
.page-eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #226e91;
  margin-bottom: 6px;
}
.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #0f172a;
  line-height: 1.2;
}
.page-subtitle {
  font-size: 13px;
  color: #64748b;
  margin-top: 4px;
}
.page-header .right {
  font-size: 12px;
  color: #64748b;
  text-align: right;
  letter-spacing: 0.02em;
}
.metrics-card {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1px;
  background: #e2e8f0;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 24px;
}
.metric {
  background: white;
  padding: 14px 18px 16px;
}
.metric .label {
  font-size: 10px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}
.metric .value {
  font-size: 22px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1;
  letter-spacing: -0.01em;
}
.metric .unit {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
  margin-left: 3px;
}
.section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 18px;
  border-bottom: 1px solid #f1f5f9;
  background: #fafbfc;
}
.section-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 22px;
  border-radius: 4px;
  background: #226e91;
  color: white;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  flex: 1;
}
.section-stats {
  display: flex;
  gap: 18px;
  font-size: 11px;
  color: #64748b;
  letter-spacing: 0.02em;
}
.section-stats .stat {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}
.section-stats .stat-label {
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  font-size: 10px;
}
.section-stats .stat-value {
  color: #0f172a;
  font-weight: 600;
  font-size: 12px;
}
.section-body {
  padding: 4px 4px 4px;
}
.legend {
  display: flex;
  gap: 16px;
  padding: 0 4px 18px;
  font-size: 11px;
  color: #64748b;
  flex-wrap: wrap;
}
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-swatch {
  width: 12px; height: 8px; border-radius: 2px; display: inline-block;
}
.footer {
  text-align: center;
  font-size: 10px;
  color: #94a3b8;
  margin-top: 24px;
  letter-spacing: 0.04em;
}
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _format_metric_value(label: str, metrics: dict) -> str:
    if label == "Duration":
        return f'<span class="value">{_fmt_elapsed(metrics["duration_s"])}</span>'
    if label == "Stops":
        return f'<span class="value">{metrics["n_arrivals"]}</span>'
    if label == "Top speed":
        return f'<span class="value">{metrics["top_speed"]}<span class="unit">km/h</span></span>'
    if label == "Avg speed":
        return f'<span class="value">{metrics["avg_speed"]}<span class="unit">km/h</span></span>'
    if label == "Avg dwell":
        return f'<span class="value">{_fmt_elapsed(metrics["avg_dwell_s"])}</span>'
    if label == "Dwell ratio":
        return f'<span class="value">{metrics["dwell_ratio"]}<span class="unit">%</span></span>'
    return ""


def _section_label(meta: dict, row_arrivals: list[dict], entry_arrival: dict | None, rs: float, re_: float) -> tuple[str, str]:
    """Return (title, meta-line). Title is '<from> → <to>': from = entry station
    (previous row's last arrival, sitting at this row's left edge) for non-first
    rows; from = first arrival of the row for row 0."""
    stops = meta.get("stops", [])
    if not row_arrivals:
        return (f"{datetime.fromtimestamp(rs).strftime('%H:%M')} – {datetime.fromtimestamp(re_).strftime('%H:%M')}", "no arrivals captured")
    from_arrival = entry_arrival if entry_arrival is not None else row_arrivals[0]
    last_cs = row_arrivals[-1].get("curr_stop", -1)
    first_cs = from_arrival.get("curr_stop", -1)
    first_name = stops[first_cs].get("name", "?") if 0 <= first_cs < len(stops) else "?"
    last_name = stops[last_cs].get("name", "?") if 0 <= last_cs < len(stops) else "?"
    title = f"{first_name} → {last_name}" if first_name != last_name else first_name
    duration = _fmt_elapsed(re_ - rs)
    n = len(row_arrivals)
    meta_line = f'{n} stop{"s" if n != 1 else ""} <span class="dot">·</span> {duration}'
    return title, meta_line


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
    passing_runs = derive_passing_runs(events, samples)
    metrics = compute_metrics(events, samples, start_ts, stopped_runs)

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
    date_str = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M")

    title_parts = [p for p in [route, diagram] if p]
    title_text = " · ".join(title_parts) if title_parts else line.upper()
    subtitle_parts = [p for p in [f"{origin} → {dest}" if origin and dest else "", date_str] if p]
    subtitle_text = " · ".join(subtitle_parts)

    head = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Drive — {_esc(title_text)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
"""

    line_color = _LINE_COLOURS.get(line.lower(), _ACCENT)
    line_accent_strip = f'<div class="line-accent" style="background: {line_color};"></div>\n'

    right_block = f'<div class="right">{len(samples)} samples · {len(events)} events</div>'

    page_header = f"""<div class="page-header">
  <div>
    <div class="page-eyebrow">Drive replay</div>
    <h1 class="page-title">{_esc(title_text)}</h1>
    <div class="page-subtitle">{_esc(subtitle_text)}</div>
  </div>
  <div>
    {right_block}
  </div>
</div>
"""

    metric_labels = ["Duration", "Stops", "Top speed", "Avg speed", "Avg dwell", "Dwell ratio"]
    metric_cells = "\n".join(
        f'<div class="metric"><div class="label">{label}</div><div class="value-wrap">{_format_metric_value(label, metrics)}</div></div>'
        for label in metric_labels
    )
    metrics_card = f'<div class="metrics-card">{metric_cells}</div>\n'

    legend = f"""<div class="legend">
  <span class="legend-item"><span class="legend-swatch" style="background:{_ACCENT};"></span>speed</span>
  <span class="legend-item"><span class="legend-swatch" style="background:rgba(120,120,120,0.4);"></span>stopped at platform</span>
  <span class="legend-item"><span class="legend-swatch" style="background:{_PASSING_FILL.replace('0.10','0.6')};"></span>passing-through (cargo / non-stop)</span>
</div>
"""

    # ── Section cards
    section_cards: list[str] = []
    for i, (rs, re_, row_arrivals, entry_arrival) in enumerate(rows):
        fig = build_section_figure(
            meta, start_ts, rs, re_, row_arrivals, entry_arrival,
            samples, stopped_runs, passing_runs, ymax, x_axis_duration_s,
            drive_first_arrival_ts=drive_first_arrival_ts,
            drive_last_arrival_ts=drive_last_arrival_ts,
        )
        chart_html = fig.to_html(
            full_html=False,
            include_plotlyjs="inline" if i == 0 else False,
            div_id=f"chart_{i}",
            config={"displayModeBar": False, "responsive": True},
        )
        sec_title, _ = _section_label(meta, row_arrivals, entry_arrival, rs, re_)
        sec_metrics = compute_section_metrics(samples, rs, re_, stopped_runs)
        n_stops_sec = len(row_arrivals)
        sec_duration = _fmt_elapsed(re_ - rs)

        stats_html = (
            f'<span class="stat"><span class="stat-label">Stops</span><span class="stat-value">{n_stops_sec}</span></span>'
            f'<span class="stat"><span class="stat-label">Time</span><span class="stat-value">{sec_duration}</span></span>'
            f'<span class="stat"><span class="stat-label">Top</span><span class="stat-value">{sec_metrics["top_speed"]} km/h</span></span>'
            f'<span class="stat"><span class="stat-label">Avg</span><span class="stat-value">{sec_metrics["avg_speed"]} km/h</span></span>'
            f'<span class="stat"><span class="stat-label">Dwell</span><span class="stat-value">{_fmt_elapsed(sec_metrics["dwell_s"])}</span></span>'
        )

        section_cards.append(f"""<div class="section">
  <div class="section-header">
    <span class="section-num">{i+1:02d}</span>
    <span class="section-title">{_esc(sec_title)}</span>
    <div class="section-stats">{stats_html}</div>
  </div>
  <div class="section-body">{chart_html}</div>
</div>
""")

    footer = f'<div class="footer">Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} from {_esc(out_path.stem.replace(".html",""))}.jsonl</div>\n'

    body = line_accent_strip + page_header + metrics_card + legend + "".join(section_cards) + footer
    out_path.write_text(head + body + "</div></body></html>", encoding="utf-8")


# ─────────────────────────── CLI ────────────────────────────


def out_path_for(jsonl_path: Path) -> Path:
    return ROOT / f"{jsonl_path.stem}.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an interactive HTML drive report from a blackbox JSONL.")
    parser.add_argument("path", nargs="?", help="JSONL path (default: most recent in _recordings/)")
    parser.add_argument("--out", help="Output HTML path (default: <jsonl_stem>.html at project root)")
    parser.add_argument("--per-row", type=int, default=5, help="Stops per section (default: 5)")
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

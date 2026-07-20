"""Auto-input driver — same-process integration.

Reads the JR EAST Train Sim HUD via dxcam in a background thread, runs OCR + a
simple state machine, and queues PA-fire requests onto the simulator's main
thread via the `pending_next_pa` flag. The simulator's existing input loop
checks that flag alongside `keyboard.is_pressed("page down")`, so the same
`_next_pa()` call path runs for auto-fire and manual fire.

Manual-press precedence is implicit: the auto-driver inspects `sim.state.curr_stop`
and `sim.state.cnt_pa` directly. If the user manually pressed PageDown ahead of
an auto-fire (advancing the simulator state), the auto-fire detects the mismatch
and skips. No synthetic keystrokes, no keyboard hooks, no parallel route loading.

Architecture pointer: auto_input/README.md "Architecture" section.

Usage (from `main.py`):
    driver = AutoDriver(sim, lead_m=900, interval_s=3)
    driver.start()
    sim.run()  # blocks main thread
    driver.stop()
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TextIO

import dxcam
import numpy as np
import pygame
import soundfile as sf

from .hud_layout import PROFILES
from .ocr import (
    DEFAULT_TEMPLATES_DIR,
    MAX_DRIVABLE_SPEED_KMH,
    Templates,
    build_templates,
    classify_badge_state,
    load_badge_anchors,
    read_distance,
    read_speed,
    read_speed_limit,
    read_speed_tenths,
    read_stopping_offset,
    seg_for_scale,
)

if TYPE_CHECKING:
    from app import PASimulator


SAMPLE_INTERVAL_S = 3
SPEED_DEPARTURE_KMH = 30
DEFAULT_LEAD_M = 900
# Long-approach lead bump. Major junctions / termini have arrival announcements
# far longer than a normal stop's (transfer guides, terminal sequences). A 900m
# approach covers ~40s of talking at cruising speed (~23 m/s), so a stop whose
# arrival PA (pa[1]) runs longer than that gets its arrival fired this much
# earlier — the guide then finishes nearer the platform instead of overrunning.
# Flat bump, same for every long stop (Atami ~128s and Shinjuku ~59s alike):
# long PA ↔ slow approach already self-compensates in distance terms (the train
# covers less ground during a long guide), so a proportional bump would
# double-count and fire the slow-approach termini absurdly early. Threshold is
# the duration 900m can't cover; the bump lands long stops at 1300m, which is
# ~56s of cruise — matching the manual setting used IRL for Shinjuku-class stops.
# See auto_input/README.md § "Arrival lead — per-stop long-approach bump".
LONG_APPROACH_BUMP_M = 400
LONG_APPROACH_PA_SEC = 40.0


class Layer3State:
    """Canonical names for AutoDriver's inferred view of the IRL game state.

    Renamed 2026-05-09 from trigger-fire-shape names (STOPPING_FRESH,
    APPROACHING_BEFORE_DEP, etc.) to verb-form transit vocabulary. The new
    names describe what the train is *doing*, not which detector flag has
    flipped. See auto_input/README.md § "Layer 3 — AutoDriver's inferred game state"
    for the full inference truth table.
    """

    IDLE = "IDLE"  # parked at start, no movement yet
    STOPPED = "STOPPED"  # parked at platform after arrival
    DEPARTING = "DEPARTING"  # rolling out, speed not yet >30 km/h
    CRUISING = "CRUISING"  # at full speed between stops
    ARRIVING = "ARRIVING"  # dist <900m, decelerating into platform
    UNKNOWN = "UNKNOWN"


# ─────────────────────────── drive recorder (blackbox) ────────────────────────
# Per-drive JSONL log written by AutoDriver. Each file is one drive session.
# Three record types (`_type` field discriminates):
#
#   _type=meta    — line 0, written once at session start. Route metadata + a
#                   richer per-stop list (stops_here flag distinguishes PASSING
#                   stations; english/furigana included for self-containment;
#                   scheduled_time is the route.json "time" field passed through
#                   verbatim — null for passing stations).
#   _type=event   — emitted whenever the OCR badge transitions: arrival,
#                   departure, passing_start, passing_end. Carries `curr_stop`
#                   at the moment of transition. Plot tools read these directly
#                   to place stop markers — no need to derive from sample stream.
#   _type=sample  — one per OCR sample interval. All OCR fields + sim state.
#
# Local-only (gitignored). Crash-safe: each line flushed immediately. Plot
# generator (separate script — TODO) reads all three record types.
from app_paths import project_root

RECORDINGS_DIR = project_root() / "_recordings"

# Speed-limit OCR misread debug dump. When a grammar-valid speed_limit read scores
# below this threshold, the source cell is saved as a PNG under the dump dir for
# offline calibration. Local-only (parent _ocr_calibration/ is gitignored).
SUSPICIOUS_SPEED_LIMIT_SCORE = 0.75
MISREAD_DUMP_DIR = project_root() / "_ocr_calibration" / "_misread_dumps"

# Cross-attribute hardening: on a badge-reject frame (badge is None — classifier diff >
# BADGE_DIFF_REJECT, a degraded frame), digit reads below this confidence are dropped.
# Set from the badge=None sampling: those reads cluster at score ~0.60 (the docs' <0.6
# random-match danger zone) vs ~0.90 (p25 0.88) when the badge reads. 0.80 splits them.
BADGE_NONE_SCORE_GATE = 0.80

# Distance plausibility guard: slack (m) added on top of the physical v·Δt bound so legit
# approach reads + OCR jitter pass, while the 1000m+ single-frame spikes are still rejected.
DISTANCE_GUARD_SLACK_M = 50.0


def _dump_misread_speed_limit_cell(cell: np.ndarray, sl_val: int, sl_score: float, ts: float) -> None:
    """Save a low-confidence speed-limit cell crop as PNG for offline calibration.
    Filename encodes ts (millisecond int, matches JSONL ts*1000), score, and the
    misread value. Failures are logged but do not raise — debug-only."""
    try:
        MISREAD_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        h, w, _ = cell.shape
        surf = pygame.image.frombuffer(cell.tobytes(), (w, h), "RGB")
        path = MISREAD_DUMP_DIR / f"sl_{int(ts * 1000)}_score{int(sl_score * 100)}_read{sl_val}.png"
        pygame.image.save(surf, str(path))
    except Exception as e:
        print(f"[AutoDriver] misread cell dump failed: {e}")


def _build_stops_meta(sim) -> list[dict]:
    """Per-stop dicts for the meta line. Self-contained — plot tool doesn't need
    to re-load route.json. PASSING stations included in geographic order with
    stops_here=False so the plot can mark them on the timeline.

    `stops_here` discriminator: per project convention (DATA_FORMAT.md), passing
    stations have NO `time` field while stopping stations always have one (even
    `time: 0` for the start station). NOT `bool(pa)` — terminus / starting
    stations may have empty `pa` but the train still stops there.
    """
    out = []
    for s in sim.stops:
        out.append(
            {
                "name": s.get("name", ""),
                "english": s.get("english", ""),
                "furigana": s.get("furigana", ""),
                "stops_here": s.get("time") is not None,
                "scheduled_time": s.get("time"),
                "sta_code": s.get("sta_code"),
            }
        )
    return out


def _open_drive_log(sim, probe_wh, profile) -> tuple[Optional[TextIO], Optional[Path]]:
    """Open a fresh JSONL log for this drive session and write the meta header.

    ``probe_wh`` is the raw dxcam desktop probe ``(w, h)``; ``profile`` is the
    ResolutionProfile selected from it. Both are recorded in the meta header so a
    "problematic OCR" report is self-diagnosing — the log alone tells whether the
    OCR ran at the resolution the user thinks it did (they are equal by
    construction today; recorded separately so any future divergence — windowed
    capture, multi-monitor, DPI — is attributable without re-driving).

    Returns (file_handle, path) or (None, None) if anything goes wrong.
    Caller is responsible for closing the handle on shutdown.
    """
    try:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        work_path = Path(sim.work_dir)
        diagram = work_path.name or "unknown"
        line = work_path.parent.name or "unknown"
        ts_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RECORDINGS_DIR / f"drive_{line}_{diagram}_{ts_str}.jsonl"
        f = open(path, "w", encoding="utf-8")
        meta = {
            "_type": "meta",
            "start_ts": time.time(),
            "line": line,
            "diagram": diagram,
            "route": sim.route_data.get("route", ""),
            "dest": sim.route_data.get("dest", ""),
            # Resolution self-diagnosis: raw desktop probe vs the OCR profile it
            # selected (profile.scale drives every seg threshold). See docstring.
            "desktop_resolution": [probe_wh[0], probe_wh[1]],
            "ocr_profile_resolution": [profile.desktop_w, profile.desktop_h],
            "ocr_scale": profile.scale,
            "stops": _build_stops_meta(sim),
        }
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        f.flush()
        return f, path
    except Exception as e:
        print(f"[AutoDriver] Could not open drive log: {e}")
        return None, None


def _write_sample(f: TextIO, sample: dict) -> None:
    """Write one sample line + flush. Swallow errors so logging never crashes the capture loop."""
    try:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        f.flush()
    except Exception as e:
        print(f"[AutoDriver] Drive-log write failed: {e}")


def _write_event(f: TextIO, kind: str, curr_stop: int, ts: float) -> None:
    """Write a transition event line. `kind` ∈ {arrival, departure, passing_start, passing_end, cross_reject, offset_reject}."""
    try:
        f.write(
            json.dumps(
                {
                    "_type": "event",
                    "ts": ts,
                    "kind": kind,
                    "curr_stop": curr_stop,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        f.flush()
    except Exception as e:
        print(f"[AutoDriver] Drive-log event write failed: {e}")


def _badge_transition_kind(prev: Optional[str], curr: Optional[str]) -> Optional[str]:
    """Map a badge state change to an event kind. Returns None if no event applies."""
    if prev is None or curr is None or prev == curr:
        return None
    if prev == "STOPPED" and curr in ("MOVING", "PASSING"):
        return "departure"
    if prev in ("MOVING", "PASSING") and curr == "STOPPED":
        return "arrival"
    if prev == "MOVING" and curr == "PASSING":
        return "passing_start"
    if prev == "PASSING" and curr == "MOVING":
        return "passing_end"
    return None


def _accept_stopping_offset(offset_cm: Optional[int], badge: Optional[str]) -> Optional[int]:
    """Gate the phantom-prone ±cm offset read on the badge groundtruth.

    The green ±cm offset is a precise, transient VALUE the game shows only after
    MOVING→STOPPED (train at rest, STOPPED badge up). The read itself is phantom-prone
    — scenery-green bleeding through the semi-transparent HUD can fabricate a ±cm value
    mid-transit. Gate it on `badge == "STOPPED"`: the badge is the most reliable read on
    the HUD (canonical — the game never shows STOPPED in motion — with a clean
    pixel-diff separation), strictly more reliable than the speed/distance digit reads
    (which suffer decimal-slip and segmentation misreads). So the badge, not speed, is
    the groundtruth for "is the train stopped." A phantom survives only if the badge
    itself misreads to STOPPED while moving — far rarer than a speed/offset digit slip.

    Deliberately NOT speed-gated: adding the noisier speed read to a badge that is
    already groundtruth would only add false-rejects (a speed misread at a real stop)
    with no phantom protection the badge doesn't already give. Same reason
    FIRE_AT_STATION stays badge-only — badge read > (distance, speed). Rejections log an
    `offset_reject` event so a valid offset ever lost to a badge misread stays visible
    and correctable from evidence.
    """
    return offset_cm if (offset_cm is not None and badge == "STOPPED") else None


def _apply_badge_reject_gate(
    badge: Optional[str],
    speed: Optional[int],
    speed_score: float,
    distance: Optional[int],
    distance_score: float,
    speed_limit: Optional[int],
    speed_limit_score: float,
) -> tuple[Optional[int], Optional[int], Optional[int], tuple[str, ...]]:
    """Cross-attribute hardening: drop low-confidence digit reads on a badge-reject frame.

    When the badge fails to classify (``badge is None`` — the classifier's best anchor
    diff exceeded ``BADGE_DIFF_REJECT``, i.e. a degraded frame: black-screen at platform
    or a mid-animation transient), the other digit reads are phantom-prone. Sampling the
    drive logs on ``badge=None`` frames, speed/distance land at score median ~0.60 (the
    docs' "<0.6 random-match danger zone") vs ~0.90 when the badge reads — a clean
    separation. So when the most reliable HUD read fails ("badge > distance, speed"), any
    accompanying read below ``BADGE_NONE_SCORE_GATE`` is dropped to ``None``.

    CONDITIONAL, not a global score floor: a genuine 0.6 read is kept whenever the badge
    confirms the frame (``badge is not None`` → returned unchanged); only a low-confidence
    read on an already-degraded frame is rejected. Offset is intentionally absent — it is
    already badge-gated to STOPPED (`_accept_stopping_offset`), so ``badge=None`` rejects
    it upstream. Sibling to that gate and the black-screen cross-reject.

    Returns the (possibly-nulled) ``(speed, distance, speed_limit)`` plus the tuple of
    gated field names, so the caller can emit a paired ``score_gate`` drive-log event.
    """
    if badge is not None:
        return speed, distance, speed_limit, ()
    gated: list[str] = []
    if speed is not None and speed_score < BADGE_NONE_SCORE_GATE:
        speed = None
        gated.append("speed")
    if distance is not None and distance_score < BADGE_NONE_SCORE_GATE:
        distance = None
        gated.append("distance")
    if speed_limit is not None and speed_limit_score < BADGE_NONE_SCORE_GATE:
        speed_limit = None
        gated.append("speed_limit")
    return speed, distance, speed_limit, tuple(gated)


def guard_distance(
    prev_badge: Optional[str],
    badge: Optional[str],
    distance: Optional[int],
    last_valid: Optional[int],
    dt_s: float,
) -> tuple[Optional[int], bool]:
    """Physical-plausibility gate on the remaining-distance read. Returns (value, rejected).

    A degraded 1080p frame mis-segments the distance number into a single-frame spike (e.g.
    `1372 → 3 → 1257`), correlated with the speed decimal-slip. The badge-reject gate misses
    these — the badge still reads MOVING on ~60% of them — but distance obeys physics: between
    two samples the train moves at most `v·Δt`. So reject a read whose change from the last
    VALID distance exceeds `MAX_DRIVABLE_SPEED_KMH · Δt` (+ slack) and HOLD-LAST-GOOD (return the
    last valid value). The ceiling speed, not the current frame's (co-corrupted on spike frames),
    keeps the bound false-reject-proof while still catching the 1000m+ spikes.

    Gate ONLY during steady MOVING travel. A STOPPED/PASSING frame — on EITHER the prior or the
    current badge — is a reference-frame-in-flux where distance legitimately jumps (departure
    STOPPED→MOVING, PASSING→MOVING or MOVING→PASSING switch, a passing run): accept + re-anchor
    unconditionally, so `v·Δt` never wrongly rejects it. A `badge=None` degraded frame while the
    PRIOR badge was MOVING IS still gated (not reset) — else a confident-but-garbage spike on an
    unreadable-badge frame would re-anchor and poison the guard. No consensus latch: a genuine
    double spike is rejected on both frames (held) and self-heals when a plausible read near the
    anchor returns. `prev_badge` is the detector's prior-frame badge (guard runs before
    `detector.update`). See auto_input/README.md § "Distance plausibility guard".
    """
    if distance is None:
        return None, False  # OCR dropout, not a spike — pass through (the detector tolerates None)
    if last_valid is None or prev_badge != "MOVING" or badge in ("STOPPED", "PASSING"):
        return distance, False  # boot, or reference-frame in flux (either badge) → accept + re-anchor
    max_delta = (MAX_DRIVABLE_SPEED_KMH / 3.6) * dt_s + DISTANCE_GUARD_SLACK_M
    if abs(distance - last_valid) > max_delta:
        return last_valid, True  # implausible single-frame spike → hold last valid
    return distance, False


def _render_report_async(log_path: Path, sim) -> None:
    """Background-thread report generation so the simulator UI doesn't freeze.

    `auto_input/` package and `plot_drive.py` both live at the project root, so
    the import resolves via the standard sys.path that the launching
    `main.py` set up — no per-call sys.path.insert needed (and previously
    accumulated duplicate entries on every click).

    Flips `sim.last_save` phase → "saved" / "failed" on completion (atomic attr rebind, read by the
    main-thread status band — same single-writer/single-reader pattern as `sim.auto_input_status`).
    """
    try:
        from plot_drive import render_html_report, load_jsonl

        out_path = project_root() / f"{log_path.stem}.html"
        meta, events, samples = load_jsonl(log_path)
        render_html_report(meta, events, samples, 999, out_path)
        print(f"[Drive recorder] Report saved -> {out_path}")
        sim.last_save = {"ts": time.time(), "phase": "saved"}
    except Exception as e:
        print(f"[Drive recorder] Report generation failed: {e}")
        sim.last_save = {"ts": time.time(), "phase": "failed"}


def generate_report(sim) -> None:
    """Kick off async HTML drive-report generation from the sim's live JSONL log. The migrated
    Report control — called by the status band's Save button (app.py). No-op (with a note) when no
    drive log is open yet. Stamps `sim.last_save` {ts, phase} so the status band can flash a
    save-confirmation message (phase: nolog → generating → saved/failed)."""
    log_path = getattr(sim, "drive_log_path", None)
    if log_path is None:
        print("[Drive recorder] No drive log open yet — wait for the AutoDriver to capture some samples.")
        sim.last_save = {"ts": time.time(), "phase": "nolog"}
        return
    print(f"[Drive recorder] Generating report from {log_path.name} ...")
    sim.last_save = {"ts": time.time(), "phase": "generating"}
    threading.Thread(target=_render_report_async, args=(log_path, sim), daemon=True).start()


# ─────────────────────────── auto-input driver ────────────────────────────


def _crop_cell(frame_bgra: np.ndarray, hud_bbox: tuple[int, int, int, int], cell_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop a HUD cell from a BGRA frame as RGB numpy array. Pure-numpy, thread-safe.

    Used instead of pygame.image.frombuffer + Surface.blit so we don't touch pygame
    DISPLAY state from the background thread (the simulator owns the display thread).
    Display-independent pygame.image calls (frombuffer + image.save with no display
    init dependency) are safe from this thread and are used by the misread dump hook.
    """
    hx, hy, _, _ = hud_bbox
    vx, vy, vw, vh = cell_bbox
    cell_bgra = frame_bgra[hy + vy : hy + vy + vh, hx + vx : hx + vx + vw]
    # BGRA -> RGB; .copy() ensures contiguous memory for downstream OCR
    return cell_bgra[:, :, [2, 1, 0]].copy()


@dataclass
class _Detector:
    """State machine over distance + speed + badge samples.

    Per-segment observed-flags (`departure_observed` / `arrival_observed` /
    `at_station_observed`): record whether each trigger condition has been
    observed in the current segment, reset on BADGE_STOPPED→(MOVING|PASSING).
    These are **Layer 3 observation memory** — they feed `inferred_state()` so the
    panel reflects what the *game* is doing. They do NOT gate PA fires: fire gating
    reads Layer 1's app sub-state directly in `AutoDriver._fire_*` (the Layer 1 ↔
    Layer 2 coupling). The two roles share one flag-set but stay conceptually
    distinct — see auto_input/README.md § "State machine layering". Within
    `update()` the flags still short-circuit duplicate FIRE_* emissions per segment
    (OCR-misread debounce); the app-sub-state guard is the authoritative gate.

    `inferred_state()` returns the canonical Layer 3 state — what AutoDriver
    thinks the IRL game train is doing. See auto_input/README.md § "Layer 3" for the
    inference truth table.

    PASSING badge handling: while the badge reads PASSING the HUD distance is to
    the passing-through station, NOT to the next stopping station — so arrival
    is only checked when badge==MOVING. Arrival uses a level test (distance ≤
    threshold) rather than a downward crossing so we still fire correctly when
    the badge transitions PASSING→MOVING with distance already under the lead.
    """

    arrival_lead_m: int = DEFAULT_LEAD_M
    prev_speed: Optional[int] = None
    prev_badge: Optional[str] = None
    departure_observed: bool = False
    arrival_observed: bool = False
    at_station_observed: bool = False
    # Re-entry consensus latch: the target ("1A"/"1B") resolved on the PREVIOUS
    # cycle, awaiting a second agreeing probe before _maybe_reentry commits the
    # silent-advance. None = no pending re-entry. Surfaced to the panel as the
    # "re-aligning…" indicator. See auto_input/README.md § "Re-entry".
    reentry_latch: Optional[str] = None

    def inferred_state(self) -> str:
        """Return the canonical Layer 3 state for the current sample.

        Pure function of `prev_badge` + Layer 2 cache. See auto_input/README.md
        § "Layer 3 — AutoDriver's inferred game state" for the truth table.
        """
        badge = self.prev_badge
        if badge is None:
            return Layer3State.UNKNOWN
        if badge == "STOPPED":
            return Layer3State.STOPPED if self.arrival_observed else Layer3State.IDLE
        # MOVING or PASSING
        if self.arrival_observed:
            return Layer3State.ARRIVING
        if self.departure_observed:
            return Layer3State.CRUISING
        return Layer3State.DEPARTING

    def update(self, distance: Optional[int], speed: Optional[int], badge: Optional[str]) -> list[str]:
        events: list[str] = []
        # Cross-attribute reject (black-screen guard). The game sometimes blacks the
        # screen briefly to fast-forward simulated time, but ONLY while parked at a
        # platform — never mid-transit. During that window the badge cell goes uniform-
        # dark and the classifier picks whichever anchor pixel-diffs lowest (typically
        # PASSING — blue is closer to black than green); the dist cell drops out
        # consistently while speed sometimes survives showing the parked-at-platform 0.
        # Structural rule: a real STOPPED→{MOVING,PASSING} transition always shows
        # speed climbing from 0 (the game can't fake movement without rendering it),
        # so when prev_badge==STOPPED, require speed>0 to accept the transition.
        # Without this the spurious PASSING fires a phantom STOPPED→PASSING and resets
        # observed-flags as if a new segment began. See auto_input/README.md § "Cross-attribute reject".
        if self.prev_badge == "STOPPED" and badge in ("MOVING", "PASSING") and (speed is None or speed == 0):
            print(
                f"          [AD] >>> CROSS-REJECT raw_badge={badge} (prev=STOPPED, speed={speed} — train hasn't moved; likely black-screen at platform)"
            )
            # Surface the rejection to the caller so it lands in the JSONL drive
            # log too — the sample line keeps the raw badge, so without this
            # marker a replay tool sees transitions the live detector ignored.
            events.append("CROSS_REJECT")
            badge = None
        # Segment boundaries: STOPPED ↔ (MOVING | PASSING). Both MOVING and
        # PASSING signal "the train is moving" — the OCR can mis-classify
        # a normal MOVING segment as PASSING for many consecutive frames
        # (live drive on Keiyo 2026-04-27 showed the ~80s run from 千葉みなと to
        # 稲毛海岸 stuck at PASSING). If we only reset on STOPPED→MOVING, those
        # mis-classified segments inherit observed-flags from the previous
        # segment and skip both PAs entirely. Resetting on
        # STOPPED→(MOVING|PASSING) makes the detector resilient to that misread.
        # Mid-segment MOVING↔PASSING transitions remain silent — those are the
        # legitimate "we're crossing a passing-through station" markers within
        # an already-active segment.
        if badge is not None and self.prev_badge is not None and badge != self.prev_badge:
            if self.prev_badge == "STOPPED" and badge in ("MOVING", "PASSING"):
                events.append("STOPPED->MOVING")
                self.departure_observed = False
                self.arrival_observed = False
                self.at_station_observed = False
            elif self.prev_badge in ("MOVING", "PASSING") and badge == "STOPPED":
                events.append("MOVING->STOPPED")
        # Departure: speed crossing 30 km/h upward — own-train speed, badge-independent.
        if speed is not None and self.prev_speed is not None:
            if not self.departure_observed and self.prev_speed < SPEED_DEPARTURE_KMH <= speed:
                events.append("FIRE_DEPARTURE")
                self.departure_observed = True
        # Arrival: level test, gated on badge==MOVING. Skips PASSING (wrong distance ref);
        # handles PASSING→MOVING with distance already <lead via the level (not crossing) check.
        if badge == "MOVING" and distance is not None:
            if not self.arrival_observed and distance <= self.arrival_lead_m:
                events.append("FIRE_ARRIVAL")
                self.arrival_observed = True
        # At-station: level test, gated on (badge==STOPPED AND arrival_observed).
        # `arrival_observed` ensures the train *just* arrived in this segment —
        # it rules out boot (parked at start station with no preceding approach)
        # and post-jump_to_stop. Triggers the press that flips `at_station=True`
        # on the simulator (no audio — unified state machine's APPROACHING→STOPPING
        # transition is silent; pa_at_station cycling happens on subsequent presses).
        # DELIBERATELY badge-only — do NOT add a speed/distance gate here. The STOPPED
        # badge is canonical groundtruth (the game never shows it in motion) and is the
        # most reliable read on the HUD; the speed/distance digit reads are noisier, so
        # folding one in would only dilute an already-stable trigger. The stopping-offset
        # gate uses the same badge-only rule. Badge read > (distance, speed).
        if badge == "STOPPED" and self.arrival_observed and not self.at_station_observed:
            events.append("FIRE_AT_STATION")
            self.at_station_observed = True
        if speed is not None:
            self.prev_speed = speed
        if badge is not None:
            self.prev_badge = badge
        return events


@dataclass
class AutoDriver:
    """Background-thread auto-driver. Captures HUD, runs OCR, sets sim.pending_next_pa.

    Lifecycle:
        driver = AutoDriver(sim)
        driver.start()        # spawn daemon thread
        sim.run()             # blocks main thread; auto-driver runs alongside
        driver.stop()         # signals thread to exit; joins with timeout
    """

    sim: "PASimulator"
    lead_m: int = DEFAULT_LEAD_M
    interval_s: int = SAMPLE_INTERVAL_S
    # Toggled by the status band's Pause button (app.py _handle_band_click). While True, the
    # capture loop skips frame.grab() / OCR / detector.update() and only updates the
    # status flag — last OCR readings stay frozen on screen so the user can
    # inspect them without the live stream overwriting.
    paused: bool = False

    # Internal state — set by _run on thread start
    _detector: _Detector = field(init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _segment_start_stop: int = field(default=-1, init=False)
    # Most recent successful auto-fire — surfaced on the debug panel as a
    # transient chip so the user can verify the auto-driver is acting. Updated
    # by _fire_departure / _fire_arrival / _fire_at_station on success only;
    # skipped fires don't count.
    _last_fire: Optional[dict] = field(default=None, init=False)
    # Speed-limit change tracking → the band's cyan change-cue. `_last_speed_limit` = last non-None
    # OCR read; a value→different-value change stamps `_limit_change_ts` (None reads are OCR dropouts /
    # no-limit segments, ignored so they don't spuriously flash). Published as `limit_change_ts`.
    _last_speed_limit: Optional[int] = field(default=None, init=False)
    _limit_change_ts: float = field(default=0.0, init=False)
    # Distance plausibility guard anchor: last VALID remaining-distance read + its ts. A read that
    # moves further from this than the train physically could (v·Δt) is a spike → held. See
    # guard_distance. Guard is active only during steady MOVING; any STOPPED/PASSING frame re-anchors.
    _last_valid_distance: Optional[int] = field(default=None, init=False)
    _last_valid_distance_ts: float = field(default=0.0, init=False)
    # Stop indices whose arrival PA is long enough to warrant the long-approach
    # lead bump (see LONG_APPROACH_PA_SEC). Probed once from audio headers on
    # thread start; empty until then. Looked up per-cycle by _lead_for.
    _long_approach: set = field(default_factory=set, init=False)
    # DXGI camera created in _run; released in stop() so a re-entered drive (band Home →
    # setup → new AutoDriver) rebuilds a FRESH duplicator. dxcam.create() returns the stale
    # cached singleton for a (device, output, backend) tuple UNLESS the prior instance is
    # is_released — so releasing on teardown is what lets the next drive's OCR arm at all.
    _camera: Optional["dxcam.DXCamera"] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._detector = _Detector(arrival_lead_m=self.lead_m)

    def _lead_for(self, stop_idx: int) -> int:
        """Arrival lead for the stop being approached: base + long-approach bump."""
        bump = LONG_APPROACH_BUMP_M if stop_idx in self._long_approach else 0
        return self.lead_m + bump

    def _compute_long_approach(self) -> set:
        """Stop indices whose arrival PA (pa[1]) exceeds LONG_APPROACH_PA_SEC.

        Probed from the audio file headers via soundfile — header read only,
        no decode, ~ms per file. Stops with <2 PA have no arrival announcement
        (skipped). A missing/unreadable PA fails soft → treated as a normal stop
        (base lead), never crashes the drive.
        """
        pa_dir = Path(self.sim.work_dir) / "pa"
        long_set: set = set()
        for i, st in enumerate(self.sim.stops):
            pa = st.get("pa") or []
            if len(pa) < 2:
                continue
            try:
                if sf.info(str(pa_dir / (pa[1] + ".mp3"))).duration >= LONG_APPROACH_PA_SEC:
                    long_set.add(i)
            except Exception:
                pass
        return long_set

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AutoDriver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Release the DXGI camera (idempotent) so the next drive rebuilds a fresh duplicator —
        # without this, dxcam.create() hands back the stale cached singleton and OCR never arms
        # on any drive after the first. Runs after the join, so the capture thread is dead.
        if self._camera is not None:
            try:
                self._camera.release()
            except Exception as e:
                print(f"[AutoDriver] camera release failed: {e}")
            self._camera = None

    def _run(self) -> None:
        print("[AutoDriver] Initializing dxcam...")
        camera = dxcam.create(output_color="BGRA")
        if camera is None:
            print("[AutoDriver] dxcam.create() returned None — DXGI capture unavailable. Auto-driver disabled.")
            return
        self._camera = camera  # tracked so stop() can release it (see the _camera field note)
        # Resolution gate. HUD bboxes scale per ResolutionProfile; templates
        # reused across resolutions via NN-resize in compare(). Probe desktop
        # dims → PROFILES.get((w,h)) → fail loud if unsupported so user sees
        # the cause instead of silent OCR garbage at wrong bbox geometry.
        # One-shot full grab gives the desktop dims; bounded retry mirrors the
        # main-loop retry pattern (dxcam can return None right after create()).
        probe = None
        for _ in range(5):
            probe = camera.grab()
            if probe is not None:
                break
            if self._stop_event.wait(0.2):
                return
        if probe is None:
            print("[AutoDriver] dxcam returned None on resolution probe — auto-driver disabled.")
            return
        ph, pw = probe.shape[:2]
        profile = PROFILES.get((pw, ph))
        if profile is None:
            supported = ", ".join(f"{w}×{h}" for w, h in sorted(PROFILES))
            print(f"[AutoDriver] FATAL: desktop resolution {pw}×{ph} not supported. " f"Supported: {supported}. Auto-driver disabled.")
            return
        seg = seg_for_scale(profile.scale)

        # Dark digit templates: always load from 1440p set. The resize-in-compare
        # approach (compare() in ocr.py) handles cross-resolution matching without
        # needing a separate 1080p dark-digit template set.
        templates = build_templates()
        missing = set("0123456789") - templates.glyphs.keys()
        if missing:
            print(f"[AutoDriver] FATAL: missing digit templates: {sorted(missing)} — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract from _ocr_calibration/.")
            return

        # Red digit templates: prefer resolution-specific set; fall back to the
        # global cache (1440p) via None so read_speed_limit uses _get_red_digit_templates().
        red_dir = (
            DEFAULT_TEMPLATES_DIR / profile.templates_subdir / "digits_red" if profile.templates_subdir else DEFAULT_TEMPLATES_DIR / "digits_red"
        )
        red_templates: Templates | None = build_templates(red_dir) if red_dir.exists() else None

        badges_dir = DEFAULT_TEMPLATES_DIR / profile.badges_subdir
        badge_anchors = load_badge_anchors(badges_dir)
        if not any(badge_anchors.values()):
            print(f"[AutoDriver] FATAL: no badge anchors at {badges_dir} — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract.")
            return
        print(
            f"[AutoDriver] Started {pw}×{ph}. Lead {self.lead_m}m, interval {self.interval_s}s. "
            f"Capture region {profile.capture_region} (top-right quadrant)."
        )

        # Probe arrival-PA durations once → the long-approach set. These stops
        # fire arrival LONG_APPROACH_BUMP_M earlier so their long guides finish
        # nearer the platform. Auto-derived per route from audio headers, so it
        # needs no route.json authoring and applies to every (incl. future) route.
        self._long_approach = self._compute_long_approach()
        if self._long_approach:
            names = ", ".join(self.sim.stops[i].get("name", "?") for i in sorted(self._long_approach))
            print(f"[AutoDriver] Long-approach stops (lead +{LONG_APPROACH_BUMP_M}m → {self.lead_m + LONG_APPROACH_BUMP_M}m): {names}")

        # Open per-drive blackbox log (JSONL). One file per AutoDriver lifetime;
        # each sample below appends a line + flushes for crash safety. Path is
        # also stashed on the simulator so the debug-bar Report button can find
        # the live log to render.
        log_file, log_path = _open_drive_log(self.sim, (pw, ph), profile)
        if log_path is not None:
            print(f"[AutoDriver] Recording drive log -> {log_path}")
            self.sim.drive_log_path = log_path

        # Track previous-cycle badge for emitting transition events into the log.
        # Distinct from `self._detector.prev_badge` — that one drives PA-fire
        # logic; this one drives the blackbox event stream.
        prev_log_badge: Optional[str] = None

        # Initial segment label (display/log only); reconciled from app state
        # every cycle below — see the coupling note in the capture loop.
        self._segment_start_stop = self._segment_from()

        try:
            while not self._stop_event.is_set():
                try:
                    if self.paused:
                        # Mark status so panel renders the indicator. Preserve last OCR
                        # values — only the paused flag flips so the panel doesn't blank.
                        self.sim.auto_input_status = {**self.sim.auto_input_status, "paused": True}
                        # Short poll while paused — resume must take effect promptly,
                        # not after a full sample interval of dead lag.
                        self._stop_event.wait(min(self.interval_s, 0.5))
                        continue
                    # Click-jump re-anchor (Layer 1 authoritative → Layer 2 belief).
                    # The user clicked a station on the lower LCD; App jumped to
                    # STOPPING@curr_stop (jump_to_stop). Mirror that into Layer 2 so
                    # subsequent fires track from the new position. Consumed before the
                    # fresh OCR read so the re-anchored prev_badge="STOPPED" is in place
                    # when detector.update() runs this cycle. Re-anchor has no failing
                    # preconditions, so consume immediately.
                    # Scope: resets OCR memory for the parked case (Layer 3
                    # STOPPED/IDLE). A click-jump mid-transit (Layer 3 driving) is
                    # then caught by _maybe_reentry below — the re-anchor zeroes the
                    # memory, re-entry silent-advances Layer 1 up to the game.
                    if self.sim.click_jump_pending:
                        self.sim.click_jump_pending = False
                        self._reanchor_to_app()
                    # Coupling (Layer 1 → Layer 2): Layer 2 is a pure function of
                    # Layer 1, computed not stored. Here we keep the displayed
                    # segment label in sync with the app's authoritative curr_stop
                    # every cycle, so the panel's "A → B" tracks any advance — auto
                    # fire, manual PageDown, or click-jump. Fire gating reads app
                    # sub-state directly in _fire_* (the other half of the coupling).
                    # The detector's per-segment observed-flags are deliberately
                    # NOT touched here: they stay OCR-driven so Layer 3 keeps
                    # observing the game, not the app. See auto_input/README.md
                    # § "State machine layering".
                    self._segment_start_stop = self._segment_from()
                    frame = None
                    for _ in range(5):
                        frame = camera.grab(region=profile.capture_region)
                        if frame is not None:
                            break
                        if self._stop_event.wait(0.2):
                            return
                    if frame is None:
                        self._stop_event.wait(self.interval_s)
                        continue

                    hud = profile.hud_bbox_in_capture
                    d_cell = _crop_cell(frame, hud, profile.distance_value_bbox)
                    s_cell = _crop_cell(frame, hud, profile.speed_value_bbox)
                    sl_cell = _crop_cell(frame, hud, profile.speed_limit_value_bbox)
                    b_cell = _crop_cell(frame, hud, profile.badge_bbox)
                    badge, b_diff = classify_badge_state(b_cell, badge_anchors)
                    s_val, s_raw, s_score = read_speed(s_cell, templates, seg=seg)
                    # Decimal-precision speed for the LOG/report only (never a driver
                    # decision — those key off the integer s_val). The tenths is read
                    # against s_raw so a dropped `.0` degrades to None (→ `.0`), never a
                    # wrong integer. See read_speed_tenths. Status band stays integer.
                    s_tenths = read_speed_tenths(s_cell, templates, seg=seg, int_raw=s_raw) if s_val is not None else None
                    s_decimal = (
                        (s_val + s_tenths / 10) if (s_val is not None and s_tenths is not None) else (float(s_val) if s_val is not None else None)
                    )
                    # The DISTANCE cell is shared and self-identifies via color: dark text
                    # `Nm` (distance to next stop, both transit and ~5s+ after arriving at
                    # platform) vs green text `+/-Ncm` (stopping offset, briefly after
                    # arrival). Run both readers unconditionally — their masks are
                    # mutually exclusive, only one returns non-None per frame.
                    d_val, _, d_score = read_distance(d_cell, templates, seg=seg)
                    offset_raw, _, offset_score = read_stopping_offset(d_cell, templates, seg=seg)
                    # Cross-attribute hardening: the phantom-prone green ±cm read is
                    # trusted only when the badge groundtruth says STOPPED (scenery-green
                    # bleed can fabricate a ±cm value mid-transit). Badge read is more
                    # reliable than speed/distance, so it's the sole gate — no speed.
                    # See _accept_stopping_offset. Rejections logged below.
                    offset_val = _accept_stopping_offset(offset_raw, badge)
                    # Speed limit (最高速度): line-dependent, often empty. None is normal.
                    sl_val, _, sl_score = read_speed_limit(sl_cell, templates, seg=seg, red_templates=red_templates)
                    # Badge-reject score gate — when the badge fails to classify (degraded
                    # frame), drop the low-confidence digit reads BEFORE any decision, the
                    # log, or the band sees them. See _apply_badge_reject_gate. Runs after
                    # every read so speed/distance/limit are gated together; s_tenths/s_decimal
                    # (log-only) follow the integer speed to None.
                    s_val, d_val, sl_val, gated_fields = _apply_badge_reject_gate(badge, s_val, s_score, d_val, d_score, sl_val, sl_score)
                    if "speed" in gated_fields:
                        s_tenths = s_decimal = None
                    sample_ts = time.time()
                    # Distance plausibility guard (physical-motion gate + hold-last-good). Runs BEFORE
                    # detector.update, so self._detector.prev_badge is the PRIOR frame's badge (the
                    # reference-frame signal). Rejects an implausible single-frame spike, holds the last
                    # valid distance, and re-anchors on a reference-frame change. See guard_distance.
                    dt_dist = (sample_ts - self._last_valid_distance_ts) if self._last_valid_distance_ts else 0.0
                    d_val, dist_rejected = guard_distance(self._detector.prev_badge, badge, d_val, self._last_valid_distance, dt_dist)
                    if d_val is not None and not dist_rejected:
                        self._last_valid_distance = d_val
                        self._last_valid_distance_ts = sample_ts
                    if sl_val is not None and sl_score < SUSPICIOUS_SPEED_LIMIT_SCORE:
                        _dump_misread_speed_limit_cell(sl_cell, sl_val, sl_score, sample_ts)
                    # Speed-limit change-cue: stamp on a value→different-value change (drives the band's
                    # cyan flash). Ignore None (OCR dropout / no-limit segment) so flicker doesn't flash.
                    if sl_val is not None:
                        if self._last_speed_limit is not None and sl_val != self._last_speed_limit:
                            self._limit_change_ts = sample_ts
                        self._last_speed_limit = sl_val

                    # Publish status to the simulator's debug panel (atomic dict swap).
                    # Single-writer (this thread), single-reader (main thread) — no lock needed.
                    self.sim.auto_input_status = {
                        "badge": badge,
                        "badge_diff": b_diff,
                        "speed": s_val,
                        "speed_score": s_score,
                        "distance": d_val,
                        "distance_score": d_score,
                        "stopping_offset_cm": offset_val,
                        "stopping_offset_score": offset_score,
                        "speed_limit": sl_val,
                        "speed_limit_score": sl_score,
                        "limit_change_ts": self._limit_change_ts,
                        "segment_start_stop": self._segment_start_stop,
                        "departure_observed": self._detector.departure_observed,
                        "arrival_observed": self._detector.arrival_observed,
                        "at_station_observed": self._detector.at_station_observed,
                        "reentry_pending": self._detector.reentry_latch,
                        "inferred_state": self._detector.inferred_state(),
                        "ts": sample_ts,
                        "paused": False,
                        "last_fire": self._last_fire,
                    }

                    if log_file is not None:
                        # Emit a transition event BEFORE the sample so the plot
                        # reader sees event-then-sample in chronological order.
                        kind = _badge_transition_kind(prev_log_badge, badge)
                        if kind is not None:
                            _write_event(log_file, kind, self.sim.state.curr_stop, sample_ts)

                        _write_sample(
                            log_file,
                            {
                                "_type": "sample",
                                "ts": sample_ts,
                                "speed": s_val,
                                "speed_decimal": s_decimal,
                                "speed_score": s_score,
                                "distance": d_val,
                                "distance_score": d_score,
                                "stopping_offset_cm": offset_val,
                                "stopping_offset_score": offset_score,
                                "speed_limit": sl_val,
                                "speed_limit_score": sl_score,
                                "badge": badge,
                                "badge_diff": b_diff,
                                "curr_stop": self.sim.state.curr_stop,
                                "cnt_pa": self.sim.state.cnt_pa,
                                "cnt_pa_at_station": self.sim.state.cnt_pa_at_station,
                                "at_station": self.sim.state.at_station,
                                "departure_observed": self._detector.departure_observed,
                                "arrival_observed": self._detector.arrival_observed,
                                "at_station_observed": self._detector.at_station_observed,
                                "inferred_state": self._detector.inferred_state(),
                                "segment_start_stop": self._segment_start_stop,
                            },
                        )
                        if offset_raw is not None and offset_val is None:
                            # A green ±cm read was rejected because the badge groundtruth
                            # was not STOPPED — logged so a rare valid-offset loss (badge
                            # misread at a true stop) is visible against the paired
                            # sample's badge context.
                            _write_event(log_file, "offset_reject", self.sim.state.curr_stop, sample_ts)
                        if gated_fields:
                            # One or more digit reads dropped by the badge-reject score gate
                            # (badge=None + score < BADGE_NONE_SCORE_GATE). Pairs with the
                            # sample line, whose *_score fields still hold the rejected reads'
                            # confidences for offline review.
                            _write_event(log_file, "score_gate", self.sim.state.curr_stop, sample_ts)
                        if dist_rejected:
                            # A distance read was an implausible physical-motion spike and was
                            # replaced by the last valid value (guard_distance). Log-only marker.
                            _write_event(log_file, "distance_reject", self.sim.state.curr_stop, sample_ts)

                    if badge is not None:
                        prev_log_badge = badge

                    ts = time.strftime("%H:%M:%S")
                    s_str = f"{s_decimal:>5.1f}km/h" if s_decimal is not None else " --"
                    b_str = badge or "?"
                    # Cell-content priority: cm reading wins (only shows briefly after
                    # arrival); fall through to m if cm is empty.
                    if offset_val is not None:
                        dist_field = f"off={offset_val:+d}cm"
                    elif d_val is not None:
                        dist_field = f"dst={d_val:>5}m"
                    else:
                        dist_field = "dst=  ---"
                    sl_field = f"  lim={sl_val}km/h" if sl_val is not None else ""
                    print(
                        f"[AD {ts}]  badge={b_str:<7}({b_diff:5.1f})  spd={s_str}  {dist_field}{sl_field}  "
                        f"sim:stop={self.sim.state.curr_stop} cnt_pa={self.sim.state.cnt_pa}"
                    )

                    # Per-stop arrival lead: base + long-approach bump for the
                    # stop being approached (curr_stop is the arrival target).
                    # Both arrival-check sites — detector.update's level-test and
                    # _resolve_reentry_target (via _maybe_reentry below) — read
                    # _detector.arrival_lead_m, so set it once here before either
                    # runs this cycle.
                    self._detector.arrival_lead_m = self._lead_for(self.sim.state.curr_stop)
                    for ev in self._detector.update(d_val, s_val, badge):
                        if ev == "CROSS_REJECT":
                            # Log-only marker, not a fire. Pairs with the sample
                            # line just written (same ts) which holds the raw
                            # badge/diff/speed the detector rejected.
                            if log_file is not None:
                                _write_event(log_file, "cross_reject", self.sim.state.curr_stop, sample_ts)
                            continue
                        self._handle_event(ev)
                    # Re-entry (Layer 3 → Layer 2/1 catch-up) runs AFTER the
                    # event loop so it reads the cross-reject-guarded badge and
                    # stands down if a normal fire already succeeded this cycle.
                    self._maybe_reentry(s_val, d_val)

                    self._stop_event.wait(self.interval_s)
                except Exception as e:
                    print(f"[AutoDriver] Error in capture loop: {e}")
                    self._stop_event.wait(self.interval_s)
        finally:
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass

        print("[AutoDriver] Stopped.")

    def _handle_event(self, event: str) -> None:
        if event == "STOPPED->MOVING":
            print("          [AD] >>> BADGE STOPPED->MOVING (Layer 3 observed-flags reset)")
            return
        if event == "MOVING->STOPPED":
            print("          [AD] >>> BADGE MOVING->STOPPED (arrived)")
            return
        if event == "FIRE_DEPARTURE":
            self._fire_departure()
            return
        if event == "FIRE_ARRIVAL":
            self._fire_arrival()
            return
        if event == "FIRE_AT_STATION":
            self._fire_at_station()
            return

    def _maybe_reentry(self, speed: Optional[int], distance: Optional[int]) -> None:
        """Re-entry: Layer 3 → Layer 2/1 reconciliation (the catch-up path).

        Called once per cycle AFTER detector.update() + the _handle_event loop.
        Fires only when the app is parked (at_station=True ⇔ Layer 1 at 1C) but
        the game is in transit — the genuine desync (cold boot mid-drive,
        mid-transit click-jump, or OCR that missed the real events). When the app
        is already moving (1A/1B) the normal streaming flow owns it, so no-op.

        Writes ONLY a single-shot signal (`sim.pending_silent_advance`) + the
        detector's observed-flags — never AppState directly (that mutation stays
        on the main thread). The Layer 1 advance + the flag seed are one
        consistent snapshot; the coupling is read-only on Layer 1, so this does
        not cascade. See auto_input/README.md § "Re-entry (Layer 3 → Layer 2
        reconciliation)".

        Lockstep ±1: advances by one stop. There is no station-name OCR, so a
        cold boot multiple stops behind the game is NOT recoverable here — the
        user must click-jump to their platform first.

        Consensus gate: a re-entry commits only after TWO consecutive cycles
        resolve to the *same* target. Re-entry is forward-only and irreversible
        (it never retreats Layer 1), so a lone transient misread while parked
        would stick the LCD +1 ahead of reality until the user click-jumps back.
        The cost of waiting is one sample interval on the genuine cases (cold
        boot, click-jump) — cheap, and the "re-aligning…" panel indicator turns
        the wait into a legible transition instead of an abrupt snap.
        """
        target = self._resolve_reentry_target(speed, distance)
        if target is None:
            # No desync this cycle (live fire landed, app moving, OCR fail, or
            # game parked) — drop any pending latch.
            self._detector.reentry_latch = None
            return
        if target != self._detector.reentry_latch:
            # First sighting, or the target changed during the wait (e.g. 1A→1B
            # as the game crossed the arrival lead) — a changed read is NOT a
            # confirmation. Latch the new target and wait one more cycle.
            self._detector.reentry_latch = target
            print(f"          [AD] >>> RE-ENTRY: re-aligning… (probe 1, target={target})")
            return
        # Two consecutive identical targets — commit the silent-advance.
        self._detector.reentry_latch = None
        if target == "1B":
            # 3D ARRIVING → land 1B (まもなく); seed dep + arr.
            self._detector.departure_observed = True
            self._detector.arrival_observed = True
            self.sim.pending_silent_advance = "1B"
            print(f"          [AD] >>> RE-ENTRY: silent advance to 1B (game ARRIVING, dist={distance})")
        else:  # "1A"
            # 3C CRUISING (speed≥30, MOVING or PASSING) → land 1A; seed dep.
            self._detector.departure_observed = True
            self.sim.pending_silent_advance = "1A"
            print(f"          [AD] >>> RE-ENTRY: silent advance to 1A (game CRUISING/PASSING, speed={speed})")

    def _resolve_reentry_target(self, speed: Optional[int], distance: Optional[int]) -> Optional[str]:
        """Resolve THIS cycle's re-entry target — ``"1A"`` / ``"1B"`` / ``None``.

        Pure read: no flag mutation, no signal write. The consensus latch in
        `_maybe_reentry` owns the commit decision. Returns None whenever there is
        no genuine parked-while-game-in-transit desync to correct.
        """
        # A normal fire already succeeded this cycle (e.g. the live 3B→3C
        # departure crossing, which plays audio) — let it land; re-entry stands
        # down. This is the discriminator between the live departure (audio) and
        # a re-entry (silent): the arriving-while-parked case is NOT suppressed
        # because there _fire_arrival skips and pending_next_pa stays False.
        if self.sim.pending_next_pa:
            return None
        if not self.sim.state.at_station:
            return None  # app already moving (1A/1B) — normal flow owns it
        inferred = self._detector.inferred_state()
        if inferred in (Layer3State.UNKNOWN, Layer3State.IDLE, Layer3State.STOPPED):
            return None  # OCR fail / first cycle / game parked — no desync
        # Game in transit while app parked at 1C. Disambiguate via the guarded
        # badge (prev_badge, post cross-reject) + raw speed/distance —
        # inferred_state can't tell 3B from 3C (both read DEPARTING cold), so the
        # speed>=30 gate is what separates "still in the departure window" (3B,
        # let the normal crossing play it with audio) from "already cruising" (3C).
        badge = self._detector.prev_badge
        if badge == "MOVING" and distance is not None and distance <= self._detector.arrival_lead_m:
            return "1B"
        if speed is not None and speed >= SPEED_DEPARTURE_KMH:
            return "1A"
        # MOVING or PASSING, speed<30 → 3B → no-op. PASSING is treated identically to
        # MOVING here (the 900m arrival is the ONLY thing PASSING changes, and that's
        # the 1B branch above, MOVING-only), so the normal SPEED_UP_30 path plays the
        # departure with audio when speed crosses 30. A PASSING badge must NOT force a
        # silent re-entry at low speed — that ate the departure PA when departing a
        # station the app was parked at (e.g. start-from-middle). speed>=30 still
        # silent-advances above (fast-sample-past-the-ramp is a correct silent advance).
        return None

    def _reanchor_to_app(self) -> None:
        """Reset OCR memory after a click-jump (parked case).

        A click-jump (jump_to_stop) puts App in STOPPING@curr_stop. The segment
        label and fire gating both derive from app state every cycle now, so the
        *only* thing left for click-jump to do is reset the detector's OCR memory
        so a stale pre-jump read can't fire a spurious event on the next cycle:

          - prev_badge="STOPPED"               (badge memory reflects platform)
          - prev_speed=None                    (drop stale speed so the very next
                                                 cycle can't satisfy the departure
                                                 crossing test prev_speed<30<=speed
                                                 on a transient parked-platform
                                                 speed misread; self-heals next read)

        The three observed-flags are also reset to a parked reading so Layer 3
        shows IDLE (`prev_badge=STOPPED` + `arrival_observed=False`) instead of a
        stale prior-segment state — cosmetic only; fire gating no longer reads them.

        Scope: parked case (the realistic desync correction). Mid-transit
        click-jump (game still driving) is a Layer-1↔Layer-3 desync handled by
        re-entry (_maybe_reentry) — see auto_input/README.md § "Re-entry".
        """
        target = self.sim.state.curr_stop
        print(f"          [AD] >>> CLICK-JUMP re-anchor: OCR memory reset for App STOPPING@{target}")
        self._detector.departure_observed = False
        self._detector.arrival_observed = False
        self._detector.at_station_observed = True
        self._detector.prev_badge = "STOPPED"
        self._detector.prev_speed = None

    def _fire_departure(self) -> None:
        # Coupling: departure is valid only at 1C (app parked, at_station=True) —
        # firing it advances the app off the platform into 1A. If the app already
        # left (at_station=False, by auto-fire or a manual PageDown), departure has
        # effectively happened — skip. The app sub-state IS the debounce.
        if not self.sim.state.at_station:
            print(f"          [AD] >>> SKIPPED departure fire (app not parked; curr_stop={self.sim.state.curr_stop}, already departed)")
            return
        # Silent pa_at_station drain — if user lagged on at-station announcements,
        # the synthesized press below would consume one queue entry instead of
        # advancing the segment. Mark the queue as exhausted so _next_in_stopping
        # falls through to _advance_to_next_stop (plays pa[0] of next stop).
        if self.sim.state.at_station:
            pa_at_st = self.sim.stops[self.sim.state.curr_stop].get("pa_at_station", [])
            if self.sim.state.cnt_pa_at_station + 1 < len(pa_at_st):
                dropped = len(pa_at_st) - 1 - self.sim.state.cnt_pa_at_station
                self.sim.state.cnt_pa_at_station = len(pa_at_st) - 1
                print(f"          [AD] >>> Silent drain: dropped {dropped} unplayed pa_at_station entr{'y' if dropped == 1 else 'ies'}")
        self.sim.pending_next_pa = True
        self._last_fire = {"ts": time.time(), "type": "departure"}
        print("          [AD] >>> FIRED departure (set pending_next_pa)")

    def _segment_from(self) -> int:
        """The stop the current leg departed from — display/log label only.

        Derived live from authoritative app state, per the coupling:
          - parked (1C, `at_station=True`)  → `curr_stop`
          - in transit (1A/1B)              → the previous stopping station

        "Stopping station" detected via `stop.get("time") is not None` — the
        canonical DATA_FORMAT.md discriminator (passing stations have NO `time`
        field), matching `_build_stops_meta`'s `stops_here` test in this module.
        Routes with passing-through stops mean the previous stopping station may
        be several indices back (e.g. chuo Shinjuku → previous stop skips 大久保 /
        東中野), so we scan backward rather than assuming `curr_stop - 1`.

        NOT used by fire gating — those read app sub-state directly. This exists
        only so the panel's "A → B" label and the JSONL stay aligned with
        `curr_stop` no matter how it changed (auto-fire, manual PageDown, click-jump).
        """
        st = self.sim.state
        if st.at_station:
            return st.curr_stop
        for k in range(st.curr_stop - 1, -1, -1):
            if self.sim.stops[k].get("time") is not None:
                return k
        return st.curr_stop

    def _fire_arrival(self) -> None:
        # Coupling: arrival is valid only while the app is approaching its target
        # (at_station=False) — that target IS curr_stop, so no segment anchor is
        # needed. If still parked (1C), departure hasn't fired — premature.
        if self.sim.state.at_station:
            print(f"          [AD] >>> SKIPPED arrival fire (app parked at stop {self.sim.state.curr_stop}; departure not fired)")
            return
        curr = self.sim.state.curr_stop
        target = self.sim.stops[curr] if curr < len(self.sim.stops) else None
        if target is None:
            print(f"          [AD] >>> SKIPPED arrival fire (curr_stop {curr} out of range)")
            return

        pa_count = len(target.get("pa", []))
        if pa_count <= 1:
            name = target.get("name", "?")
            print(f"          [AD] >>> SKIPPED arrival fire (stop '{name}' has {pa_count} PA — no arrival announcement)")
            return

        if self.sim.state.cnt_pa >= pa_count - 1:
            print(f"          [AD] >>> SKIPPED arrival fire (cnt_pa={self.sim.state.cnt_pa} already at last PA; user fired manually)")
            return

        self.sim.pending_next_pa = True
        self._last_fire = {"ts": time.time(), "type": "arrival"}
        print("          [AD] >>> FIRED arrival (set pending_next_pa)")

    def _fire_at_station(self) -> None:
        # The press that flips the sim from APPROACHING into STOPPING (ただいま).
        # No audio — the unified state machine's APPROACHING→STOPPING transition
        # is silent; this press just sets `state.at_station=True`. Subsequent
        # presses cycle pa_at_station (if any) then advance.
        #
        # Coupling: valid only at 1B (app in final approach — at_station=False AND
        # cnt_pa at the last approach PA). The two guards below enforce exactly
        # that: at_station rules out 1C (already stopping); the cnt_pa check rules
        # out 1A (still on an earlier approach PA).
        if self.sim.state.at_station:
            print("          [AD] >>> SKIPPED at-station fire (sim already STOPPING)")
            return
        curr = self.sim.state.curr_stop
        target = self.sim.stops[curr] if curr < len(self.sim.stops) else None
        if target is None:
            return
        pa = target.get("pa", [])
        # cnt_pa must be at the last approach PA (or pa empty) — otherwise the
        # press would play the next approach PA instead of entering STOPPING,
        # leaving the display on "まもなく" while the train is parked.
        if pa and self.sim.state.cnt_pa != len(pa) - 1:
            print(f"          [AD] >>> SKIPPED at-station fire (cnt_pa={self.sim.state.cnt_pa}, expected={len(pa) - 1}; arrival likely missed)")
            return
        self.sim.pending_next_pa = True
        self._last_fire = {"ts": time.time(), "type": "at-station"}
        print("          [AD] >>> FIRED at-station (set pending_next_pa)")

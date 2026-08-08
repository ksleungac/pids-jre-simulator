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
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TextIO

import dxcam
import numpy as np
import pygame
import soundfile as sf

from .hud_layout import DOWNSCALE_PROFILE, PROFILES, profile_for
from .sampling import GuardState, Reading, downscale_hud, read_hud  # noqa: F401  (Reading re-exported for the 1b diagnostic)
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
# Upper bound of the audible-departure band. At or above this the train is
# demonstrably long into the segment, the departure PA is stale, and re-entry's
# SILENT 1A advance owns it. Partitions the speed axis with SPEED_DEPARTURE_KMH so
# the audible primary and the silent fallback are disjoint rather than competing —
# see auto_input/README.md § "Primary/fallback strictness must not invert".
DEPARTURE_STALE_KMH = 60
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


def _open_drive_log(sim, probe_wh, read_profile, legacy: bool = False) -> tuple[Optional[TextIO], Optional[Path]]:
    """Open a fresh JSONL log for this drive session and write the meta header.

    ``probe_wh`` is the raw dxcam desktop probe ``(w, h)``; ``read_profile`` is the profile
    the READERS ran under — normally the 1080p model the HUD was downscaled into, so the two
    differ on any larger desktop. Both are recorded so a "problematic OCR" report is
    self-diagnosing: the log alone says what was captured, what read it, and which path ran.

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
            # Resolution self-diagnosis: what was captured vs what read it (read scale
            # drives every seg threshold). These differ whenever the HUD was downscaled.
            "desktop_resolution": [probe_wh[0], probe_wh[1]],
            "ocr_profile_resolution": [read_profile.desktop_w, read_profile.desktop_h],
            "ocr_scale": read_profile.scale,
            # True only when --legacy-ocr forced the per-resolution path (debug).
            "ocr_legacy": legacy,
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
    """Write an event line. Canonical `kind` list: auto_input/README.md § Files, `_recordings/`."""
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
    observed in the current segment, reset on STOPPED->(MOVING|PASSING).
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
    # Motion provenance: True while the current motion began with a WITNESSED
    # STOPPED→(MOVING|PASSING) edge (a valid, cross-reject-passed badge read).
    # Motion of known origin is a normal departure the audible primary owns —
    # re-entry's BASE arming condition is `not motion_origin_known` (re-entry
    # exists only for motion of unknown origin: cold boot mid-transit, or a
    # post-jump history reset). Set at the edge, cleared on MOVING→STOPPED and
    # by _reanchor_to_app. 2026-07-23 incident: on a segment shorter than the
    # arrival lead, the 1B condition is true from the first moving frame of a
    # perfectly normal departure — only provenance separates the two.
    motion_origin_known: bool = False

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
                # Witnessed edge — this motion has a known origin (a normal
                # departure). Disarms re-entry for the segment; see the
                # motion_origin_known field comment.
                self.motion_origin_known = True
            elif self.prev_badge in ("MOVING", "PASSING") and badge == "STOPPED":
                events.append("MOVING->STOPPED")
                # Parked — the next motion must witness its own edge.
                self.motion_origin_known = False
        # CONTRACT: departure = LEVEL test speed >= SPEED_DEPARTURE_KMH, gated by
        # departure_observed. Badge-independent, direction-agnostic, no prev_speed.
        # See auto_input/README.md § "Arrival and departure are level tests, not crossings".
        # Re-adding a crossing loses the departure whenever prev_speed is absent or stale-high.
        #
        # Upper bound (DEPARTURE_STALE_KMH) applies ONLY to unknown-origin motion —
        # it reserves the >=60 cold-join case for re-entry's silent 1A (arrow (d)).
        # On a WITNESSED departure edge (motion_origin_known) the segment just
        # started, so the announcement is FRESH at any speed: fire with no ceiling,
        # audibly (arrow (a) mimicking (d)). Without this, a platform dwell whose
        # acceleration lands entirely inside an OCR dropout (badge/speed = ? through
        # the whole [30,60) band, first valid read already >=60) loses the departure
        # AND re-entry is disarmed by the witnessed edge → nothing catches it, app
        # stuck at 1C (2026-07-24 01:36 log). Normal drive must never be compromised.
        if speed is not None and not self.departure_observed:
            ceiling_ok = speed < DEPARTURE_STALE_KMH or self.motion_origin_known
            if SPEED_DEPARTURE_KMH <= speed and ceiling_ok:
                events.append("FIRE_DEPARTURE")
                self.departure_observed = True
        # Arrival: level test, gated on badge==MOVING. Skips PASSING (wrong distance ref);
        # handles PASSING→MOVING with distance already <lead via the level (not crossing) check.
        if badge == "MOVING" and distance is not None:
            if not self.arrival_observed and distance <= self.arrival_lead_m:
                events.append("FIRE_ARRIVAL")
                self.arrival_observed = True
        # At-station: level test on badge==STOPPED alone — the reachability rule:
        # "in 1A/1B, a new STOPPED badge is the arrival fact; the app must always
        # reach the next stage." NOT gated on arrival_observed: a dropout that ate
        # the arrival must not strand the app in transit (the fire-side drain
        # normalizes cnt_pa — see _fire_at_station). Boot (parked at start with no
        # preceding approach) is ruled out by _fire_at_station's app-parked skip;
        # post-jump refire by _reanchor_to_app setting at_station_observed=True.
        # Triggers the press that flips `at_station=True` on the simulator (no
        # audio — unified state machine's APPROACHING→STOPPING transition is
        # silent; pa_at_station cycling happens on subsequent presses).
        # DELIBERATELY badge-only — do NOT add a speed/distance gate here. The STOPPED
        # badge is canonical groundtruth (the game never shows it in motion) and is the
        # most reliable read on the HUD; the speed/distance digit reads are noisier, so
        # folding one in would only dilute an already-stable trigger. The stopping-offset
        # gate uses the same badge-only rule. Badge read > (distance, speed).
        if badge == "STOPPED" and not self.at_station_observed:
            events.append("FIRE_AT_STATION")
            self.at_station_observed = True
        if speed is not None:
            self.prev_speed = speed
        if badge is not None:
            self.prev_badge = badge
        return events


def _enumerate_capture_targets() -> list[tuple[int, int, bool]]:
    """Every (device_idx, output_idx, is_primary) dxcam can address, primary first.

    dxcam.create() with its defaults picks adapter 0's primary output. On an
    iGPU+dGPU / multi-GPU machine, adapter 0 may not be the one whose D3D device
    can duplicate the display, and there is no guarantee the display's adapter is
    enumerated first. Parsing output_info() gives us the full set to walk so we can
    find the combo that actually works. Primary-first so a working primary display
    always beats a secondary monitor (the game runs on the primary; a wrong-monitor
    capture is rejected downstream by the resolution-profile probe).
    """
    try:
        info = dxcam.output_info()
    except Exception as e:
        print(f"[AutoDriver] dxcam.output_info() failed ({e}); falling back to device 0 / output 0.")
        return [(0, 0, True)]
    targets: list[tuple[int, int, bool]] = []
    for line in info.strip().splitlines():
        m = re.match(r"Device\[(\d+)\] Output\[(\d+)\]:.*Primary:(True|False)", line)
        if m:
            targets.append((int(m.group(1)), int(m.group(2)), m.group(3) == "True"))
    if not targets:
        return [(0, 0, True)]
    targets.sort(key=lambda t: not t[2])  # primary outputs first
    return targets


def _open_capture_camera(output_color: str = "BGRA") -> Optional["dxcam.DXCamera"]:
    """Open a working DXGI capture camera, trying every adapter/output combo.

    The bare ``dxcam.create()`` addresses only adapter 0's primary output. When the
    display is driven by a different adapter (iGPU+dGPU laptops, a monitor plugged
    into the motherboard, multi-GPU desktops), ``IDXGIOutput1::DuplicateOutput``
    raises ``DXGI_ERROR_UNSUPPORTED`` (0x887A0004) — a hard ``COMError`` that used
    to kill the whole capture thread with a raw traceback (issue #97). We walk every
    addressable combo instead and return the first whose ``create()`` succeeds (a
    successful create IS a live duplicator — DuplicateOutput runs inside it).

    On total failure we DO NOT mute the error: the last full traceback is printed so
    the next machine's failure is diagnosable, then None is returned so the caller
    disables the auto-driver gracefully while the rest of the app keeps running.
    """
    targets = _enumerate_capture_targets()
    last_trace: Optional[str] = None
    for device_idx, output_idx, is_primary in targets:
        tag = f"device={device_idx} output={output_idx}{' (primary)' if is_primary else ''}"
        try:
            camera = dxcam.create(device_idx=device_idx, output_idx=output_idx, output_color=output_color)
            if camera is None:
                print(f"[AutoDriver] {tag}: dxcam.create() returned None; trying next combo.")
                continue
            print(f"[AutoDriver] dxcam capture opened on {tag}.")
            return camera
        except Exception as e:
            last_trace = traceback.format_exc()
            print(f"[AutoDriver] {tag}: capture failed ({e.__class__.__name__}: {e}); trying next combo.")
    # No adapter/output could be duplicated. Surface the original error IN FULL —
    # muting it is exactly what leaves us blind on the next report (#97). The most
    # common residual cause here (every dxgi combo raising UNSUPPORTED) is a GPU/driver
    # with no Desktop Duplication support; the fallback lever is dxcam's winrt backend
    # (needs the `winrt` package bundled), noted on #97.
    print(f"[AutoDriver] No DXGI capture target worked. Tried: {targets}. Auto-driver disabled.")
    if last_trace:
        print("[AutoDriver] Last capture error (full traceback, retained for debugging):")
        print(last_trace, end="")
    return None


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
    # Debug lever (main.py --legacy-ocr): read at the capture's own resolution using its
    # per-resolution templates, instead of downscaling into the 1080p model. Only for
    # isolating a downscale-side fault — it is the approach the downscale path replaces,
    # and it only works on a resolution that already has a hand-calibrated profile.
    legacy_ocr: bool = False

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
    _guard_state: GuardState = field(default_factory=GuardState, init=False)
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
        # app.py already resolved this through route_loader.resolve_audio_root — reuse it
        # rather than re-deriving. Joining work_dir/"pa" by hand was correct only while
        # audio sat beside route.json; since the per-line pool it names a directory that
        # exists on no shipped line, and the except below swallowed every miss, so the
        # bump was silently inert on every route (route_loader CONTRACT: nothing else
        # resolves audio paths; critical_lessons.md §4).
        pa_dir = Path(self.sim.audio_root) / "pa"
        long_set: set = set()
        candidates = probed = 0
        for i, st in enumerate(self.sim.stops):
            pa = st.get("pa") or []
            if len(pa) < 2:
                continue  # no arrival announcement — a whole line may be like this (yamanote)
            candidates += 1
            try:
                if sf.info(str(pa_dir / (pa[1] + ".mp3"))).duration >= LONG_APPROACH_PA_SEC:
                    long_set.add(i)
                probed += 1
            except (RuntimeError, OSError) as e:
                print(f"[autodriver] long-approach probe failed for {pa[1]}.mp3: {e}")
        if candidates and not probed:
            # Candidates existed but none was readable — the directory is wrong, not the
            # route. Say so rather than degrading to base lead in silence, which is how
            # this went unnoticed across every pooled line.
            print(f"[autodriver] long-approach probe read 0 of {candidates} arrival PAs under {pa_dir} — bump disabled")
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
        camera = _open_capture_camera(output_color="BGRA")
        if camera is None:
            # _open_capture_camera already reported the cause (and the full traceback
            # on a hard COMError) — nothing was capturable on any adapter/output.
            # Disable the auto-driver; the rest of the app keeps running.
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
        profile = profile_for(pw, ph)
        if profile is None:
            tested = ", ".join(f"{w}×{h}" for w, h in sorted(PROFILES))
            print(
                f"[AutoDriver] FATAL: desktop resolution {pw}×{ph} is outside the supported scope "
                f"(16:9 at 1080p or larger). Live-tested: {tested}. Auto-driver disabled."
            )
            return
        if not profile.verified:
            print(
                f"[AutoDriver] NOTE: {pw}×{ph} has no live-tested profile — geometry interpolated "
                f"from the 16:9 fractions (HUD {profile.hud_bbox}). Expected to be correct; watch the reads."
            )
        if self.legacy_ocr and not profile.verified:
            # Legacy reads natively and needs a template set extracted at THIS resolution.
            # An interpolated profile has none, so every read would silently fail.
            print(f"[AutoDriver] --legacy-ocr is not available at {pw}×{ph} (no native template set). Using the downscale path.")
            self.legacy_ocr = False

        # `profile` always describes the CAPTURE — which region to grab and where the HUD
        # sits in it. The READ side (cell bboxes, seg thresholds, templates, anchors) is
        # normally DOWNSCALE_PROFILE: the HUD is shrunk into the one 1080p model, so a new
        # desktop resolution needs no profile and no templates of its own.
        #
        # `legacy_ocr` reads at the capture's own resolution with its per-resolution
        # templates instead — a debug lever for isolating a downscale-side fault, not a
        # supported path. Keeping capture and read as SEPARATE variables is what stops a
        # cell being cropped at one geometry and thresholded at another.
        read_profile = profile if self.legacy_ocr else DOWNSCALE_PROFILE
        seg = seg_for_scale(read_profile.scale)

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
            DEFAULT_TEMPLATES_DIR / read_profile.templates_subdir / "digits_red"
            if read_profile.templates_subdir
            else DEFAULT_TEMPLATES_DIR / "digits_red"
        )
        red_templates: Templates | None = build_templates(red_dir) if red_dir.exists() else None

        badges_dir = DEFAULT_TEMPLATES_DIR / read_profile.badges_subdir
        badge_anchors = load_badge_anchors(badges_dir)
        if not any(badge_anchors.values()):
            print(f"[AutoDriver] FATAL: no badge anchors at {badges_dir} — auto-driver disabled.")
            print("[AutoDriver] Re-run `uv run python _dev_scripts/extract_ocr_assets.py` to re-extract.")
            return
        print(
            f"[AutoDriver] Started {pw}×{ph}. Lead {self.lead_m}m, interval {self.interval_s}s. "
            f"Capture region {profile.capture_region} (top-right quadrant)."
        )
        hw, hh = profile.hud_bbox_in_capture[2], profile.hud_bbox_in_capture[3]
        rw, rh = read_profile.hud_bbox_in_capture[2], read_profile.hud_bbox_in_capture[3]
        if self.legacy_ocr:
            print(f"[AutoDriver] LEGACY OCR (debug): reading the HUD at its native {hw}×{hh} with the {profile.desktop_h}p template set.")
        else:
            print(f"[AutoDriver] OCR: HUD {hw}×{hh} -> {rw}×{rh}, read by the {read_profile.desktop_h}p model.")

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
        log_file, log_path = _open_drive_log(self.sim, (pw, ph), read_profile, self.legacy_ocr)
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
                    # fresh OCR read so the invalidated badge history (prev_badge=None,
                    # motion_origin_known=False) is in place when detector.update()
                    # runs this cycle. Re-anchor has no failing preconditions, so
                    # consume immediately.
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

                    # THE read path — shared verbatim with _dev_scripts/ocr_observe.py so the
                    # diagnostic observes exactly what production does. Reader + guard ORDER is
                    # load-bearing; the contract lives in auto_input/sampling.py. `prev_badge` is
                    # the PRIOR frame's badge (detector.update runs after), which is what the
                    # distance guard needs as its reference-frame signal.
                    # Downscale BEFORE the read so every cell this cycle is cropped from one
                    # frame at one geometry (sampling.py CONTRACT step 0). At 1080p this is a
                    # plain copy; under --legacy-ocr the native frame goes through untouched.
                    if not self.legacy_ocr:
                        frame = downscale_hud(frame, profile)

                    sample_ts = time.time()
                    r = read_hud(
                        frame,
                        read_profile,
                        templates,
                        red_templates,
                        badge_anchors,
                        seg,
                        prev_badge=self._detector.prev_badge,
                        guard=self._guard_state,
                        ts=sample_ts,
                        crop=_crop_cell,
                        accept_stopping_offset=_accept_stopping_offset,
                        apply_badge_reject_gate=_apply_badge_reject_gate,
                        guard_distance=guard_distance,
                    )
                    badge, b_diff = r.badge, r.badge_diff
                    s_val, s_score = r.speed, r.speed_score
                    s_tenths, s_decimal = r.speed_tenths, r.speed_decimal
                    d_val, d_score = r.distance, r.distance_score
                    offset_raw, offset_val, offset_score = r.raw_stopping_offset_cm, r.stopping_offset_cm, r.stopping_offset_score
                    sl_val, sl_score = r.speed_limit, r.speed_limit_score
                    gated_fields, dist_rejected = r.gated_fields, r.distance_rejected
                    sl_cell = r.cells["speed_limit"]
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
                                "reentry_pending": self._detector.reentry_latch,
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
                    committed = self._maybe_reentry(s_val, d_val)
                    if committed is not None and log_file is not None:
                        # A silent advance just landed. Log-only marker — without it
                        # re-entry is console-print only and its frequency has to be
                        # reverse-engineered from the parked-while-moving sample runs.
                        _write_event(log_file, f"reentry_{committed.lower()}", self.sim.state.curr_stop, sample_ts)

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

    def _maybe_reentry(self, speed: Optional[int], distance: Optional[int]) -> Optional[str]:
        """Re-entry: Layer 3 → Layer 2/1 reconciliation (the catch-up path).

        Called once per cycle AFTER detector.update() + the _handle_event loop.
        Fires only when the app is parked (at_station=True ⇔ Layer 1 at 1C) but
        the game is in transit — the genuine desync (cold boot mid-drive,
        mid-transit click-jump, or OCR that missed the real events). When the app
        is already moving (1A/1B) the normal streaming flow owns it, so no-op.

        Writes ONLY a single-shot signal (`sim.pending_silent_advance`) + the
        detector's observed-flags — never AppState directly (that mutation stays
        on the main thread). Returns the COMMITTED target ("1A"/"1B") or None, so
        the caller writes the drive-log event — same split as update()'s
        CROSS_REJECT token: the detector decides, the loop owns the log file.

        The Layer 1 advance + the flag seed are one consistent snapshot; the
        coupling is read-only on Layer 1, so this does not cascade. See auto_input/README.md § "Re-entry (Layer 3 → Layer 2
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
            return None
        if target != self._detector.reentry_latch:
            # First sighting, or the target changed during the wait (e.g. 1A→1B
            # as the game crossed the arrival lead) — a changed read is NOT a
            # confirmation. Latch the new target and wait one more cycle.
            self._detector.reentry_latch = target
            print(f"          [AD] >>> RE-ENTRY: re-aligning… (probe 1, target={target})")
            return None
        # Two consecutive identical targets — commit the silent-advance.
        self._detector.reentry_latch = None
        if target == "1B":
            # 3D ARRIVING → land 1B (まもなく); seed dep + arr.
            self._detector.departure_observed = True
            self._detector.arrival_observed = True
            self.sim.pending_silent_advance = "1B"
            print(f"          [AD] >>> RE-ENTRY: silent advance to 1B (game ARRIVING, dist={distance})")
        else:  # "1A"
            # 3C CRUISING (speed ≥ DEPARTURE_STALE_KMH, MOVING or PASSING) → land 1A; seed dep.
            self._detector.departure_observed = True
            if self._next_stopping_pa_count() == 1:
                # pa=1: the single announcement is NEVER stale — the catch-up
                # plays it AUDIBLY (user rule: "pa=1 always play it"). Same
                # press as a departure fire (pa_at_station backlog drains, app
                # advances 1A playing pa[0]) instead of a silent advance.
                self._fire_departure()
                print(f"          [AD] >>> RE-ENTRY: audible catch-up to 1A (pa=1 — announcement never stale; speed={speed})")
            else:
                self.sim.pending_silent_advance = "1A"
                print(f"          [AD] >>> RE-ENTRY: silent advance to 1A (game CRUISING/PASSING, speed={speed})")
        return target

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
        # BASE ARMING CONDITION — validated before any target resolution:
        # re-entry handles only motion of UNKNOWN origin. A witnessed
        # STOPPED→(MOVING|PASSING) edge means this is a normal departure the
        # audible primary owns — re-entry never activates, whatever the
        # speed/distance reads say (2026-07-23: a 703m segment < 900m lead made
        # the 1B condition true from the first moving frame of a normal
        # departure and silently ate the departure PA).
        if self._detector.motion_origin_known:
            return None
        inferred = self._detector.inferred_state()
        if inferred in (Layer3State.UNKNOWN, Layer3State.IDLE, Layer3State.STOPPED):
            return None  # OCR fail / first cycle / game parked — no desync
        # Game in transit while app parked at 1C. Disambiguate via the guarded
        # badge (prev_badge, post cross-reject) + raw speed/distance —
        # inferred_state can't tell 3B from 3C (both read DEPARTING cold), so the
        # DEPARTURE_STALE_KMH gate is what separates "the departure PA is still
        # worth playing" (below it — the normal LEVEL test already fired it with
        # audio) from "long into the segment, announcement stale" (at or above).
        badge = self._detector.prev_badge
        if badge == "MOVING" and distance is not None and distance <= self._detector.arrival_lead_m:
            # pa=1 segments have NO distinct 1B — cnt_pa = len(pa)-1 = 0 makes
            # 1A ≡ 1B the same AppState, and the single announcement must never
            # be skipped by a silent landing. Only a pa>=2 landing stop (a real
            # まもなく sub-state) is a 1B target; on pa=1 re-entry may only
            # resolve 1A, and the STOPPING state is reached by the at-station
            # transition edge itself (STOPPED badge → FIRE_AT_STATION).
            next_pa = self._next_stopping_pa_count()
            if next_pa is not None and next_pa >= 2:
                return "1B"
        if speed is not None and speed >= DEPARTURE_STALE_KMH:
            return "1A"
        # Below DEPARTURE_STALE_KMH → no target: the audible primary owns [30, 60), this
        # silent fallback owns [60, ∞). PASSING is treated as MOVING here (the arrival lead
        # is the ONLY thing PASSING changes — the MOVING-only 1B branch above).
        # See auto_input/README.md § "Primary/fallback strictness must not invert".
        return None

    def _next_stopping_pa_count(self) -> Optional[int]:
        """pa count of the stop a re-entry advance would land on, or None if no
        advance is possible (parked at terminus, non-circular).

        Mirrors app.py `_advance_to_next_stop`'s landing rule (its `_is_stopping`
        predicate + the circular loop-back past duplicate idx 0) — that method is
        the canonical source of the landing semantics; keep in sync.
        """
        stops = self.sim.stops
        st = self.sim.state

        def _is_stopping(stop) -> bool:
            return bool(stop.get("pa")) or bool(stop.get("pa_at_station"))

        for k in range(st.curr_stop + 1, len(stops)):
            if _is_stopping(stops[k]):
                return len(stops[k].get("pa", []))
        if getattr(st, "circular", 0) == 1:
            for k in range(1, len(stops)):
                if _is_stopping(stops[k]):
                    return len(stops[k].get("pa", []))
        return None

    def _reanchor_to_app(self) -> None:
        """Reset OCR memory after a click-jump (parked case).

        A click-jump (jump_to_stop) puts App in STOPPING@curr_stop. The segment
        label and fire gating both derive from app state every cycle now, so the
        *only* thing left for click-jump to do is reset the detector's OCR memory
        so a stale pre-jump read can't fire a spurious event on the next cycle:

          - prev_badge=None                    (badge history INVALIDATED — a jump
                                                 discards provenance. NOT a synthetic
                                                 "STOPPED": that would fabricate a
                                                 witnessed STOPPED→MOVING edge on the
                                                 first post-jump MOVING read, setting
                                                 motion_origin_known and wrongly
                                                 disarming re-entry for the mid-transit
                                                 jump case re-entry exists to catch)
          - motion_origin_known=False          (re-entry re-armed: post-jump motion
                                                 is motion of unknown origin until a
                                                 real dwell + edge is witnessed)
          - prev_speed=None                    (UNREAD since #82 — not a guard, and not
                                                 logged either. It protected the old
                                                 departure CROSSING; the level test reads
                                                 only the current speed, so that protection
                                                 is simply gone. Nothing replaces it: the
                                                 departure test is badge-independent, so
                                                 post-jump a SINGLE spurious speed read in
                                                 [30,60) fires a departure PA — at_station
                                                 is True by construction after jump_to_stop
                                                 and this method clears departure_observed,
                                                 so no other gate stands in the way. Open
                                                 risk, tracked in #85)

        The three observed-flags are also reset so Layer 3 shows UNKNOWN
        (`prev_badge=None`) instead of a stale prior-segment state — cosmetic
        only; fire gating no longer reads them. (Pre-provenance this set a
        synthetic `prev_badge="STOPPED"` for an IDLE reading; UNKNOWN is the
        honest state and restores itself on the first clean badge read.)

        Scope: parked case (the realistic desync correction). Mid-transit
        click-jump (game still driving) is a Layer-1↔Layer-3 desync handled by
        re-entry (_maybe_reentry) — see auto_input/README.md § "Re-entry".
        """
        target = self.sim.state.curr_stop
        print(f"          [AD] >>> CLICK-JUMP re-anchor: OCR memory reset for App STOPPING@{target}")
        self._detector.departure_observed = False
        self._detector.arrival_observed = False
        # at_station_observed=False, NOT True: with prev_badge=None there is no
        # STOPPED->MOVING edge post-jump, so nothing would ever reset a True here
        # and the arrival STOPPED read at the segment's end would be suppressed
        # (2026-07-24 log: click-jump @12 mid-transit → re-entry 1A@13 → arrived
        # with NO at-station fire, app stranded at 1A). The parked-case refire
        # this once guarded is covered by _fire_at_station's app-parked skip.
        self._detector.at_station_observed = False
        self._detector.prev_badge = None
        self._detector.prev_speed = None
        self._detector.motion_origin_known = False

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
        # Coupling: valid from ANY in-transit state (1A or 1B) — the reachability
        # rule: a STOPPED badge while the app is in transit IS the arrival fact,
        # so the app must always reach STOPPING. at_station rules out 1C (already
        # stopping / boot at the start station).
        if self.sim.state.at_station:
            print("          [AD] >>> SKIPPED at-station fire (sim already STOPPING)")
            return
        curr = self.sim.state.curr_stop
        target = self.sim.stops[curr] if curr < len(self.sim.stops) else None
        if target is None:
            return
        pa = target.get("pa", [])
        # Silent approach-PA drain — if cnt_pa is not at the last approach PA
        # (arrival fire was missed, e.g. OCR dropout through the lead), the press
        # below would play the next approach PA instead of entering STOPPING,
        # leaving the display on まもなく while the train is parked. Normalize
        # cnt_pa to the last entry so the press lands as the STOPPING transition.
        # Same pattern as _fire_departure's pa_at_station drain.
        if pa and self.sim.state.cnt_pa != len(pa) - 1:
            dropped = len(pa) - 1 - self.sim.state.cnt_pa
            self.sim.state.cnt_pa = len(pa) - 1
            # App invariant: is_last_pa ≡ cnt_pa >= len(pa)-1 — every other
            # cnt_pa write maintains it (_next_in_approaching, _silent_advance_to).
            self.sim.state.is_last_pa = True
            print(
                f"          [AD] >>> Silent drain: skipped {dropped} unplayed approach PA entr{'y' if dropped == 1 else 'ies'} (arrival missed; STOPPED badge is the arrival fact)"
            )
        self.sim.pending_next_pa = True
        self._last_fire = {"ts": time.time(), "type": "at-station"}
        print("          [AD] >>> FIRED at-station (set pending_next_pa)")

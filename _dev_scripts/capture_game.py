"""
Auto-driver — captures the JR EAST Train Sim HUD, detects PA-fire events, and
fires synthetic PageDown keystrokes to drive the simulator.

Architecture: separate process. The simulator runs as a normal pygame app with its
existing keyboard listener. This script reads HUD via dxcam, decides when to fire
PA, sends keystrokes via the `keyboard` library — same code path as a manual
PageDown press from the user. No coupling with simulator code.

Manual override: if you press PageDown manually, the auto-driver detects it via
a global keyboard hook and skips the auto-fire for that segment. Self-press guard
(500ms window after we send) keeps us from re-detecting our own keystrokes.

Verbose log per sample + every event so you can watch the state machine work.

Run: uv run python _dev_scripts/capture_game.py
Flags:
  --no-fire        log only, no synthetic keystrokes (debug mode)
  --lead N         arrival distance threshold in meters (default 900;
                   bump to 1200 for transfer-heavy lines like Tokaido or Yamanote)
  --interval N     sample interval seconds (default 5)
  --res 1080p|1440p  override desktop resolution (default: auto-detect from first frame)

Stop: Ctrl+C
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import dxcam
import keyboard
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))
from auto_input.hud_layout import PROFILES  # noqa: E402
from auto_input.ocr import (  # noqa: E402
    DEFAULT_TEMPLATES_DIR,
    Templates,
    build_templates,
    classify_badge_state,
    load_badge_anchors,
    read_distance,
    read_speed,
    read_speed_limit,
    read_stopping_offset,
    seg_for_scale,
)

import numpy as np  # noqa: E402

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    ctypes.windll.user32.SetProcessDPIAware()

_RES_FLAG_MAP = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
}

DEFAULT_INTERVAL_S = 5
DEFAULT_LEAD_M = 900
OUTPUT_DIR = Path(__file__).parent.parent / "_experiments" / "live_captures"

SPEED_DEPARTURE_KMH = 30
SELF_PRESS_GUARD_S = 0.5  # ignore key callbacks within this window after we send


# ─────────────────────────── shared state for keyboard hook ────────────────────────────
@dataclass
class KeyTracker:
    """Tracks user manual presses vs the auto-driver's own synthetic sends.

    The keyboard library's global hook fires on ALL PageDown events, including the
    ones we send synthetically. We can't tell them apart from the event alone, so we
    use a brief timestamp guard: any press within SELF_PRESS_GUARD_S of our own send
    is treated as our own.
    """

    last_user_pagedown_ts: float = 0.0
    last_user_pageup_ts: float = 0.0
    last_auto_send_ts: float = 0.0

    def on_pagedown(self) -> None:
        now = time.time()
        if now - self.last_auto_send_ts < SELF_PRESS_GUARD_S:
            return  # our own synthetic press
        self.last_user_pagedown_ts = now
        print(f"          >>> USER pressed PageDown at {time.strftime('%H:%M:%S')}")

    def on_pageup(self) -> None:
        now = time.time()
        if now - self.last_auto_send_ts < SELF_PRESS_GUARD_S:
            return
        self.last_user_pageup_ts = now
        print(f"          >>> USER pressed PageUp at {time.strftime('%H:%M:%S')}")

    def send_pagedown(self) -> None:
        # Simulator uses keyboard.is_pressed() polling (app.py), so a millisecond
        # press-release via keyboard.send() can fall between polls and be missed.
        # Hold the key explicitly long enough to overlap multiple poll cycles.
        self.last_auto_send_ts = time.time()
        keyboard.press("page down")
        time.sleep(0.1)
        keyboard.release("page down")


# ─────────────────────────── PA event detector ────────────────────────────
@dataclass
class PaEventDetector:
    """Tracks distance + speed + badge state; emits PA-fire events.

    Per-segment fired flags prevent double-firing when OCR misreads transiently flip
    a threshold-crossing condition. Segment boundary = BADGE_STOPPED→MOVING transition,
    which resets all flags.

    `arrival_lead_m` is configurable via the --lead CLI flag (default 900). Bump to
    1200 for lines with longer arrival announcements (transfer-hub stations).

    None values for distance/speed/badge are tolerated — OCR FAIL frames don't reset
    state, so transient unreadable frames don't break segment continuity.
    """

    arrival_lead_m: int = DEFAULT_LEAD_M
    prev_speed: int | None = None
    prev_badge: str | None = None
    departure_fired: bool = False
    arrival_fired: bool = False
    segment_start_ts: float = field(default_factory=time.time)
    # Counts BADGE_STOPPED->MOVING transitions. None until first transition observed.
    # If route data is loaded, this maps to: heading from stops[segment_idx] to stops[segment_idx+1].
    segment_idx: int | None = None

    def update(self, distance: int | None, speed: int | None, badge: str | None) -> list[str]:
        events: list[str] = []
        # Cross-attribute reject (black-screen guard). Game black-screens for fast-
        # forward only while parked at a platform, never mid-transit. Real
        # STOPPED→{MOVING,PASSING} departures always show speed climbing from 0;
        # black-screen at platform leaves speed=0 (parked) or None (OCR FAIL).
        # When prev_badge==STOPPED, require speed>0 to accept the transition.
        # Mirrors auto_input/driver.py:_Detector. See auto_input/README.md § "Cross-attribute reject".
        if self.prev_badge == "STOPPED" and badge in ("MOVING", "PASSING") and (speed is None or speed == 0):
            events.append(f"CROSS-REJECT raw_badge={badge} (prev=STOPPED, speed={speed} — train hasn't moved; likely black-screen at platform)")
            badge = None
        # Segment boundaries: STOPPED ↔ (MOVING | PASSING). The OCR badge classifier
        # can stick on PASSING for an entire normal MOVING segment (live drive
        # 2026-04-27 on Keiyo 千葉みなと→稲毛海岸: ~80s of mis-classified PASSING).
        # Resetting only on STOPPED→MOVING leaves segment-flags True from the
        # previous segment, suppressing both PA fires. Resetting on
        # STOPPED→(MOVING|PASSING) makes the detector tolerant to that misread.
        # Mid-segment MOVING↔PASSING transitions remain silent (legitimate
        # passing-station crossings inside an already-active segment).
        if badge is not None and self.prev_badge is not None and badge != self.prev_badge:
            if self.prev_badge == "STOPPED" and badge in ("MOVING", "PASSING"):
                self.segment_idx = 0 if self.segment_idx is None else self.segment_idx + 1
                events.append(f"BADGE_STOPPED->MOVING (segment {self.segment_idx}, reset flags)")
                self.departure_fired = False
                self.arrival_fired = False
                self.segment_start_ts = time.time()
            elif self.prev_badge in ("MOVING", "PASSING") and badge == "STOPPED":
                events.append("BADGE_MOVING->STOPPED (arrived at platform)")
        if speed is not None and self.prev_speed is not None:
            if not self.departure_fired and self.prev_speed < SPEED_DEPARTURE_KMH <= speed:
                events.append(f"SPEED_UP_{SPEED_DEPARTURE_KMH} (fire departure PA)")
                self.departure_fired = True
        # Arrival: level test, gated on badge==MOVING. Skips PASSING (HUD distance reference
        # is wrong); handles PASSING→MOVING resumption when distance is already < lead via
        # the level (not crossing) check.
        if badge == "MOVING" and distance is not None:
            if not self.arrival_fired and distance <= self.arrival_lead_m:
                events.append(f"DIST_DOWN_{self.arrival_lead_m} (fire arrival PA)")
                self.arrival_fired = True
        if speed is not None:
            self.prev_speed = speed
        if badge is not None:
            self.prev_badge = badge
        return events


# ─────────────────────────── helpers ────────────────────────────
def save_hud_crop(surf: pygame.Surface, path: Path, profile) -> None:
    hx, hy, hw, hh = profile.hud_bbox
    hud = pygame.Surface((hw, hh))
    hud.blit(surf, (0, 0), area=pygame.Rect(hx, hy, hw, hh))
    pygame.image.save(hud, str(path))


def _crop_cell(surf: pygame.Surface, profile, cell_bbox: tuple) -> np.ndarray:
    """Crop a HUD-relative cell bbox from a full-desktop surface."""
    hx, hy, _, _ = profile.hud_bbox
    vx, vy, vw, vh = cell_bbox
    cell = pygame.Surface((vw, vh))
    cell.blit(surf, (0, 0), area=pygame.Rect(hx + vx, hy + vy, vw, vh))
    arr = pygame.surfarray.array3d(cell)
    return np.transpose(arr, (1, 0, 2))


def load_route(route_path: Path) -> dict[str, Any] | None:
    """Load route.json from the given line+diagram directory."""
    p = route_path / "route.json"
    if not p.exists():
        print(f"WARNING: --route given but {p} not found; PA-count check disabled")
        return None
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    n_stops = len(data.get("stops", []))
    print(f"Loaded route: {p} ({n_stops} stops)")
    return data


def target_stop(route_data: dict[str, Any] | None, segment_idx: int | None) -> dict[str, Any] | None:
    """Return the stop the train is currently approaching, given segment_idx. None if unknown."""
    if route_data is None or segment_idx is None:
        return None
    stops = route_data.get("stops", [])
    target_idx = segment_idx + 1
    if target_idx >= len(stops):
        return None
    return stops[target_idx]


def handle_event(
    event: str,
    detector: PaEventDetector,
    keys: KeyTracker,
    fire: bool,
    route_data: dict[str, Any] | None,
) -> None:
    """Dispatch a PaEventDetector event: log it; fire PageDown if appropriate."""
    print(f"          >>> {event}")
    is_departure = "fire departure PA" in event
    is_arrival = "fire arrival PA" in event
    if not (is_departure or is_arrival):
        return
    if not fire:
        print("          >>> (--no-fire mode; skipping synthetic PageDown)")
        return

    # Skip arrival fire when next stop has ≤1 PA (the only PA is the departure announcement).
    # Departure fires unconditionally — assume every stop has at least one PA.
    if is_arrival:
        stop = target_stop(route_data, detector.segment_idx)
        if stop is not None:
            pa_count = len(stop.get("pa", []))
            if pa_count <= 1:
                name = stop.get("name", "?")
                print(f"          >>> SKIPPED auto-fire (target stop '{name}' has {pa_count} PA, no arrival announcement)")
                return

    if keys.last_user_pagedown_ts > detector.segment_start_ts:
        ts_user = time.strftime("%H:%M:%S", time.localtime(keys.last_user_pagedown_ts))
        print(f"          >>> SKIPPED auto-fire (user already pressed PageDown at {ts_user})")
        return
    keys.send_pagedown()
    print("          >>> AUTO sent PageDown")


# ─────────────────────────── main loop ────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    parser.add_argument("--no-fire", action="store_true", help="log only, no synthetic keystrokes")
    parser.add_argument("--lead", type=int, default=DEFAULT_LEAD_M, help=f"arrival threshold in meters (default {DEFAULT_LEAD_M})")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_S, help=f"sample interval seconds (default {DEFAULT_INTERVAL_S})")
    parser.add_argument(
        "--res", choices=list(_RES_FLAG_MAP), default=None, help="override desktop resolution (default: auto-detect from first frame)"
    )
    parser.add_argument(
        "--route",
        type=Path,
        default=None,
        help="route.json directory (e.g. audio/sobu/1217F) — enables PA-count check so DIST_DOWN doesn't fire when next stop has only 1 PA",
    )
    args = parser.parse_args()
    route_data = load_route(args.route) if args.route else None

    pygame.init()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Initializing dxcam...")
    camera = dxcam.create(output_color="BGRA")
    if camera is None:
        print("dxcam.create() returned None — DXGI capture unavailable.")
        return 1

    # ── Resolution detection ───────────────────────────────────────────────────
    if args.res:
        res_key = _RES_FLAG_MAP[args.res]
        print(f"Resolution: {args.res} (forced via --res)")
    else:
        print("Detecting desktop resolution from first frame...")
        probe = None
        for _ in range(5):
            probe = camera.grab()
            if probe is not None:
                break
            time.sleep(0.2)
        if probe is None:
            print("FATAL: dxcam returned None on probe — cannot detect resolution.")
            return 1
        ph, pw = probe.shape[:2]
        res_key = (pw, ph)
        print(f"Detected: {pw}x{ph}")

    profile = PROFILES.get(res_key)
    if profile is None:
        supported = ", ".join(f"{w}x{h}" for w, h in sorted(PROFILES))
        print(f"FATAL: resolution {res_key[0]}x{res_key[1]} not supported. Supported: {supported}")
        return 1

    res_label = f"{profile.desktop_w}x{profile.desktop_h}"
    seg = seg_for_scale(profile.scale)

    # ── Load resolution-appropriate assets ────────────────────────────────────
    print(f"\nResolution profile: {res_label} (scale={profile.scale})")
    print("Building templates from ocr_templates/")
    templates = build_templates()  # always 1440p — resize-to-glyph handles cross-res
    missing = set("0123456789") - templates.glyphs.keys()
    if missing:
        print(f"WARNING: missing digit templates: {sorted(missing)}")
    else:
        print(f"Templates loaded: {sorted(templates.glyphs.keys())}")

    red_dir = DEFAULT_TEMPLATES_DIR / profile.templates_subdir / "digits_red" if profile.templates_subdir else DEFAULT_TEMPLATES_DIR / "digits_red"
    red_templates: Templates | None = build_templates(red_dir) if red_dir.exists() else None
    rt_count = len(red_templates.glyphs) if red_templates else 0
    print(f"Red templates: {rt_count}/10 from {red_dir}")

    badges_dir = DEFAULT_TEMPLATES_DIR / profile.badges_subdir
    badge_anchors = load_badge_anchors(badges_dir)
    print(f"Badge anchors: { {k: len(v) for k, v in badge_anchors.items()} }")

    keys = KeyTracker()
    keyboard.on_press_key("page down", lambda _: keys.on_pagedown())
    keyboard.on_press_key("page up", lambda _: keys.on_pageup())

    detector = PaEventDetector(arrival_lead_m=args.lead)
    fire = not args.no_fire

    print(f"\nMode: {'AUTO-FIRE' if fire else 'LOG-ONLY (--no-fire)'}")
    print(f"Arrival threshold: {args.lead} m")
    print(f"Sample interval: {args.interval} s")
    print(f"Route: {args.route if args.route else '(no --route; PA-count check disabled — DIST_DOWN fires for every stop)'}")
    print(f"Saving HUD crops to: {OUTPUT_DIR}")
    print("Ctrl+C to stop.\n")

    while True:
        try:
            frame = None
            for _ in range(5):
                frame = camera.grab()
                if frame is not None:
                    break
                time.sleep(0.2)
            if frame is None:
                print("[wait] dxcam returned None on all retries.")
                time.sleep(args.interval)
                continue

            height, width = frame.shape[:2]
            if (width, height) != (profile.desktop_w, profile.desktop_h):
                print(f"[warn] captured {width}x{height}, expected {res_label} — skipping frame")
                time.sleep(args.interval)
                continue

            surf = pygame.image.frombuffer(frame.tobytes(), (width, height), "BGRA")

            d_cell = _crop_cell(surf, profile, profile.distance_value_bbox)
            s_cell = _crop_cell(surf, profile, profile.speed_value_bbox)
            sl_cell = _crop_cell(surf, profile, profile.speed_limit_value_bbox)
            b_cell = _crop_cell(surf, profile, profile.badge_bbox)
            badge, b_diff = classify_badge_state(b_cell, badge_anchors)
            s_val, _, s_score = read_speed(s_cell, templates, seg=seg)
            # Cell self-identifies via color — run both readers, only one will succeed.
            d_val, _, d_score = read_distance(d_cell, templates, seg=seg)
            offset_val, _, offset_score = read_stopping_offset(d_cell, templates, seg=seg)
            sl_val, _, sl_score = read_speed_limit(sl_cell, templates, seg=seg, red_templates=red_templates)

            ts = time.strftime("%H:%M:%S")
            s_str = f"{s_val:>3}km/h" if s_val is not None else " --"
            b_str = f"{badge:<7}" if badge else "    ?  "
            # cm wins (transient post-arrival display); fall through to m.
            if offset_val is not None:
                dist_field = f"off={offset_val:+d}cm (s={offset_score:.2f})"
            elif d_val is not None:
                dist_field = f"dst={d_val:>5}m (s={d_score:.2f})"
            else:
                dist_field = "dst=  ---"
            sl_field = f"   lim={sl_val}km/h (s={sl_score:.2f})" if sl_val is not None else ""
            print(f"[{ts}]  badge={b_str} (d={b_diff:5.1f})   spd={s_str} (s={s_score:.2f})   {dist_field}{sl_field}")

            for ev in detector.update(d_val, s_val, badge):
                handle_event(ev, detector, keys, fire, route_data)

            ts_fname = time.strftime("%Y%m%d_%H%M%S")
            d_label = str(d_val) if d_val is not None else "FAIL"
            save_hud_crop(surf, OUTPUT_DIR / f"hud_{ts_fname}_d{d_label}.png", profile)

            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0


if __name__ == "__main__":
    sys.exit(main())

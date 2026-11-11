# SPDX-License-Identifier: MIT
"""What does the E233-0 lower LCD show over time, in each train state?

KEEP — WIP § 15.3 cites it as the instrument for the heartbeat redesign. It drives
the REAL scheduler and lower-LCD manager headless, records every slot change, and
draws the timeline, so a picture of the heartbeat is a picture of the code rather
than of someone's description of it. Re-run it after any rotation change.

    uv run _dev_scripts/_heartbeat_timeline.py [--seconds 216] [--out screenshot_heartbeat.png]

Rows are train states on `chuo/1654T`. A row may carry a PROPOSAL, patched in
memory onto the manager it drives and never into production (`principles.md` §
"Prototype inside the code that will hold it", the monkeypatch clause). Every row
replays one fixed draw sequence for the rare turn, so rows differ only by their
rules.
"""

import argparse
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pygame  # noqa: E402

import preview_display  # noqa: E402
from app import PASimulator  # noqa: E402
from app_paths import project_root  # noqa: E402

ROUTE = "audio/chuo/1654T"


TI_PAGE = 100  # a batch's pages are slots 100, 101, ...: every page change is a real slot change


GRID = 3.0  # proposal grid: the E233-0 upper beat (author, 2026-11-12)
# Proposal dwells in 3s grid beats: the author's lower beat is 6s, so a 2-lower-beat
# page is 4 here and a 1-lower-beat page is 2. TRANSFER's 12s is PROVISIONAL.
GRID_DWELL = {"route": 4, "train_info": 4, "notice": 2, "transfer": 4}


def _grouped(messages=None, cap=None, notice_share=0.75, skip_share=0.5):
    """PROPOSAL (WIP §§ 4, 15.3, 2026-11-12): route → train information → arrival,
    on E233-0's own cadence — upper beat 3s, lower beat 6s.

    Route is OVERVIEW → FULL → EIGHT, big to small, FULL gone under the eight-lock.
    Train information joins a cycle unless it is skipped, `skip_share` of the time
    and never twice running; it opens with one 12s page per message, then the
    マナーモード + 優先席 pair, 6s each, `notice_share` of the time. Arrival is the
    transfer page, shown all along (§ 11.1). The cycle is replanned each time it
    restarts. `messages` stands in for the live feed (None = the pool); `cap`
    limits a batch. `record` runs a patch carrying `grid` with
    `constants.BEAT_SECONDS` set to it, which moves the language cadence and the
    change floor to 3s; the dwells below are in those 3s beats.
    """

    def patch(low):
        from displays.lower_lcd import LowerDisplayBase

        if messages is not None:
            low.train_info_display.messages = lambda: list(messages)
        g = GRID_DWELL
        low._SLOT_BEATS = {
            **low._SLOT_BEATS,
            low._SLOT_OVERVIEW: g["route"],
            low._SLOT_FULL: g["route"],
            low._SLOT_EIGHT: g["route"],
            low._SLOT_MANNER: g["notice"],
            low._SLOT_PRIORITY: g["notice"],
            low._SLOT_TRANSFER: g["transfer"],
            **{TI_PAGE + k: g["train_info"] for k in range(32)},
        }
        plan = {"batch": 0, "notices": [], "skipped": True}

        def plan_info():
            joins = plan["skipped"] or low._rng.random() >= skip_share
            plan["skipped"] = not joins
            msgs = low.train_info_display.messages() if joins else []
            plan["batch"] = len(msgs) if cap is None else min(cap, len(msgs))
            pair = joins and low._rng.random() < notice_share
            plan["notices"] = [low._SLOT_MANNER, low._SLOT_PRIORITY] if pair else []

        def available(state):
            route = [low._SLOT_OVERVIEW] if low.overview_display.has_sheet else []
            if not low._should_lock_to_eight(state.cursor_pos):
                route.append(low._SLOT_FULL)
            route.append(low._SLOT_EIGHT)
            info = [TI_PAGE + k for k in range(plan["batch"])] + plan["notices"]
            arrival = [low._SLOT_TRANSFER] if low._station_has_transfers(state) else []
            return route + info + arrival

        def apply(slot, now):
            prev = low._current_slot
            LowerDisplayBase.apply_slot(low, slot, now)
            if slot != prev and low._state is not None and slot == available(low._state)[0]:
                plan_info()

        plan_info()
        low._available_slots = available
        low.apply_slot = apply
        low._current_slot = available(low._state)[0]  # a cycle opens on its first page, not on boot's FULL

    patch.grid = GRID
    return patch


def _two_lines():
    from displays.train_models.e233_0.train_info import load_pool

    return load_pool()[2:4]  # 中央線快速電車, 東海道線: two real disruptions


# (title, subtitle, stop index, PA phase as preview_display --pa, proposal or None)
ROWS = [
    ("Running · 次は 立川", "now", 5, 0, None),
    ("Running · 次は 立川", "proposal 3s/6s · 2 lines disrupted", 5, 0, _grouped(messages=_two_lines())),
    ("Running · 次は 立川", "proposal 3s/6s · offline pool, batch ≤ 3", 5, 0, _grouped(cap=3)),
    ("Running · 次は 立川", "proposal 3s/6s · nothing disrupted", 5, 0, _grouped(messages=[])),
    ("Near terminus · 次は 御茶ノ水", "proposal 3s/6s · 2 lines disrupted", 29, 0, _grouped(messages=_two_lines())),
]

ROUTE_GROUP = {"OVERVIEW": "O", "FULL": "F", "EIGHT": "6"}
INFO_GROUP = {"TRAIN_INFO": "運", "PRIORITY": "優", "MANNER": "マ"}
ARRIVAL_GROUP = {"TRANSFER": "T"}
GROUP_COLOURS = {  # (fill, ink)
    "route": ((159, 225, 203), (8, 80, 65)),
    "info": ((244, 192, 209), (114, 36, 62)),
    "arrival": ((206, 203, 246), (60, 52, 137)),
}


def record(stop, pa, proposal, seconds, seed=1):
    """`[(slot_name, start_s, end_s), ...]` from the real scheduler, 15 fps.

    A proposal carrying `grid` runs with `constants.BEAT_SECONDS` set to it for
    this row only — `displays.base.beats` reads it at call time, so the language
    cadence, the change floor and every dwell move together — and restored after.
    """
    import constants

    saved = constants.BEAT_SECONDS
    constants.BEAT_SECONDS = getattr(proposal, "grid", saved)
    try:
        return _record(stop, pa, proposal, seconds, seed)
    finally:
        constants.BEAT_SECONDS = saved


def _record(stop, pa, proposal, seconds, seed):
    sim = PASimulator(ROUTE, preview=True, model="e233_0")
    preview_display.apply_state(sim, stop=stop, pa=pa)
    low = sim.lower
    low._rng = random.Random(seed)
    low._notice_turn = 0
    low._rare_slot = low._pick_rare_page()
    if proposal:
        proposal(low)
    names = {getattr(low, n): n[6:] for n in dir(low) if n.startswith("_SLOT_") and isinstance(getattr(low, n), int)}
    name = lambda s: names.get(s) or ("TRAIN_INFO" if s >= TI_PAGE else str(s))  # noqa: E731
    t0 = t = 1000.0
    sim.scheduler.seed(t)
    segs, cur, start = [], low._current_slot, 0.0
    for _ in range(int(seconds * 15)):
        t += 1 / 15
        sim.scheduler.tick(t, sim.state)
        if low._current_slot != cur:
            segs.append((name(cur), start, t - t0))
            cur, start = low._current_slot, t - t0
    segs.append((name(cur), start, float(seconds)))
    return segs


def draw(rows, seconds, out):
    W, LABEL, PAD, ROW_H, TOP = 1600, 330, 24, 84, 70
    H = TOP + ROW_H * len(rows) + 80
    surf = pygame.Surface((W, H))
    surf.fill((255, 255, 255))
    face = project_root() / "fonts" / "NotoSansJP.otf"  # OFL, shipped; not an LCD font
    f, fs = pygame.font.Font(str(face), 22), pygame.font.Font(str(face), 17)
    x = lambda s: LABEL + (W - PAD - LABEL) * min(s, seconds) / seconds  # noqa: E731

    for s in range(0, int(seconds) + 1, 4):
        major = s % 36 == 0
        pygame.draw.line(surf, (200, 200, 195) if major else (232, 232, 228), (x(s), TOP - (14 if major else 6)), (x(s), H - 70))
        if major:
            lab = fs.render(f"{s}s", True, (120, 120, 115))
            surf.blit(lab, (x(s) - lab.get_width() / 2, TOP - 40))

    for i, (title, sub, segs) in enumerate(rows):
        y = TOP + i * ROW_H
        surf.blit(f.render(title, True, (20, 20, 20)), (8, y + 6))
        surf.blit(fs.render(sub, True, (120, 120, 115)), (8, y + 38))
        for name, a, b in segs:
            if a >= seconds:
                break
            group = "info" if name in INFO_GROUP else "arrival" if name in ARRIVAL_GROUP else "route"
            fill, ink = GROUP_COLOURS[group]
            r = pygame.Rect(round(x(a)) + 1, y + 4, max(1, round(x(b)) - round(x(a)) - 2), ROW_H - 22)
            pygame.draw.rect(surf, fill, r, border_radius=4)
            lab = f.render((ROUTE_GROUP | INFO_GROUP | ARRIVAL_GROUP).get(name, name[:2]), True, ink)
            if r.w > lab.get_width() + 4:
                surf.blit(lab, (r.centerx - lab.get_width() / 2, r.centery - lab.get_height() / 2))

    y = H - 58
    legend = [
        (GROUP_COLOURS["route"][0], "Route:  O overview · F full route · 6 six-station"),
        (GROUP_COLOURS["info"][0], "Train information:  運 運行情報 (one page per line) · 優 優先席 · マ マナーモード"),
        (GROUP_COLOURS["arrival"][0], "Arrival:  T transfer"),
    ]
    xx = 8
    for fill, text in legend:
        pygame.draw.rect(surf, fill, (xx, y + 6, 22, 22), border_radius=4)
        lab = fs.render(text, True, (60, 60, 58))
        surf.blit(lab, (xx + 30, y + 6))
        xx += 30 + lab.get_width() + 40
    note = fs.render(
        "Grid: one line per beat (4s), labels every 3 beats. Recorded from the real scheduler; one draw sequence for every row.",
        True,
        (120, 120, 115),
    )
    surf.blit(note, (8, y + 36))
    pygame.image.save(surf, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=288.0)
    ap.add_argument("--out", default="screenshot_heartbeat.png")
    args = ap.parse_args()
    pygame.init()
    pygame.display.set_mode((640, 480))
    rows = []
    for title, sub, stop, pa, proposal in ROWS:
        segs = record(stop, pa, proposal, args.seconds)
        rows.append((title, sub, segs))
        print(f"{title} ({sub}): " + " ".join(f"{n[:4]}@{a:.0f}" for n, a, _ in segs))
    draw(rows, args.seconds, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: MIT
# TIER: T1 — window mirroring: exposure and touch, as pure decisions
"""T1 — window mirroring: the pure decisions behind exposure and touch.

Module scope is the FEATURE, not a function or an incident. Two decisions live
here because both are pure, both belong to mirroring, and both fail silently:

  1. WHO CAN REACH IT  — resolve_bind_host: launch flags -> bind address
  2. WHERE A TAP LANDS — frame_point: a normalised tap -> a frame pixel
  3. WHICH VIEW OWNS IT — compose / tap_event: the docked second view, and the
                          routing of a tap that lands in it

None has a loud failure mode. A bind regression silently exposes the app on
every network the user joins; a mapping regression silently presses the button
next to the one that was tapped; a routing regression hands one view's
coordinates to another, which is still a valid click somewhere. No smoke test
notices any of them.

The stateful half of the feature (frames keeping up, taps reaching the app's
event queue) is T3 `test_stream.py` — same feature, different tier.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import frame_stream  # noqa: E402

# ── 1. exposure ───────────────────────────────────────────────────────────────
# Oracle is the exposure contract, independent of the implementation: LAN
# binding must require an explicit opt-in, and streaming must be off unless
# asked for.

BIND_CASES = [
    # (stream, lan, expected)
    (False, False, None),  # default launch -> streaming off entirely
    (True, False, "127.0.0.1"),  # --stream -> loopback only, no firewall prompt
    (False, True, "0.0.0.0"),  # --stream-lan alone implies streaming
    (True, True, "0.0.0.0"),  # both -> LAN wins (widest requested)
]

# ── 2. where a tap lands ──────────────────────────────────────────────────────
# Oracle: a tap lands where the finger was. The centre of the image is the
# centre of the frame, the corners are the corners, and nothing outside the
# image resolves to a pixel at all.
#
# The 1.0 edge is the specific trap: `int(1.0 * w)` is `w`, one past the last
# column, which is exactly where a button flush against the frame edge lives.

W, H = 730, 420

TAP_CASES = [
    # (fx, fy, expected) — expected pinned literally, never computed from W/H
    (0.0, 0.0, (0, 0)),  # top-left corner
    (1.0, 1.0, (729, 419)),  # bottom-right: clamped INSIDE, not (730, 420)
    (1.0, 0.0, (729, 0)),
    (0.0, 1.0, (0, 419)),
    (0.5, 0.5, (365, 210)),  # centre of the image -> centre of the frame
    (0.25, 0.75, (182, 315)),
    (-0.01, 0.5, None),  # left of the image
    (0.5, -0.01, None),  # above it
    (1.01, 0.5, None),  # right of it
    (0.5, 1.01, None),  # below it
]

# A frame with no pixels has none to land on. Unreachable today (`_frame` is a copy
# of a live display surface), but the invariant below claims "never outside the
# frame" and `min(int(f*0), -1)` is -1, which is outside it.
DEGENERATE_CASES = [(0.5, 0.5, 0, 0), (0.0, 0.0, 0, 100), (1.0, 1.0, 100, 0)]

# Mutation-proven 2026-08-19: removing the `min(..., n-1)` edge clamp fails 5 checks
# (the three corner rows + both invariant sweeps at f == 1.0).


def check_bind() -> int:
    failed = 0
    for stream, lan, expected in BIND_CASES:
        got = frame_stream.resolve_bind_host(stream, lan)
        if got != expected:
            print(f"FAIL  bind stream={stream} lan={lan}: expected {expected!r}, got {got!r}")
            failed += 1
    if frame_stream.resolve_bind_host(stream=True, lan=False) == "0.0.0.0":
        print("FAIL  --stream alone must NOT bind the LAN")
        failed += 1
    return failed


def check_tap() -> int:
    failed = 0
    for fx, fy, expected in TAP_CASES:
        got = frame_stream.frame_point(fx, fy, W, H)
        if got != expected:
            print(f"FAIL  frame_point({fx}, {fy}, {W}, {H}): expected {expected!r}, got {got!r}")
            failed += 1

    # No accepted tap may ever resolve outside the frame. One out-of-range pixel
    # is a click the app cannot possibly own.
    for i in range(0, 101):
        f = i / 100
        for pt in (frame_stream.frame_point(f, 0.5, W, H), frame_stream.frame_point(0.5, f, W, H)):
            if pt is None:
                print(f"FAIL  f={f} inside [0,1] was rejected")
                failed += 1
                continue
            x, y = pt
            if not (0 <= x < W and 0 <= y < H):
                print(f"FAIL  f={f} resolved to {pt}, outside the {W}x{H} frame")
                failed += 1

    for fx, fy, w, h in DEGENERATE_CASES:
        got = frame_stream.frame_point(fx, fy, w, h)
        if got is not None:
            print(f"FAIL  frame_point({fx}, {fy}, {w}, {h}) = {got!r}, expected None (no pixels to land on)")
            failed += 1

    # The frame changes size under the client (setup 730x610 -> drive 730x420+band
    # -> tutorial 1100x500), which is why the wire carries fractions at all.
    if frame_stream.frame_point(0.5, 0.5, 1100, 500) != (550, 250):
        print("FAIL  the same fraction did not follow a differently-sized frame")
        failed += 1
    return failed


# ── 3. which view owns the tap ────────────────────────────────────────────────
# The frame can carry a second view docked beside the main one — the departure
# bell, which is a real second OS window on the PC and so is invisible to the
# present hook. `compose` decides where it goes and `tap_event` routes by that
# same rect, so the layout and the hit-routing cannot disagree.
#
# Each viewer picks its own view, which is what makes this worth testing three
# times over rather than once: the SAME fraction is a different point in each
# one, so a view that composes correctly and routes against another view's
# geometry sends every tap somewhere plausible and wrong.
#
# The failure this catches is quiet: a tap in the dock posted with FRAME
# coordinates is still a well-formed click, and the LCD handlers would happily
# resolve it against a station they were never pointed at.
DOCK_W, DOCK_H = 192, 290


def check_dock() -> int:
    import pygame

    pygame.init()
    failed = 0
    main_surf = pygame.Surface((W, H))
    side = pygame.Surface((DOCK_W, DOCK_H))

    frame, rect = frame_stream.compose(main_surf, side, "both")
    want = (W + frame_stream.SIDE_GAP + DOCK_W, max(H, DOCK_H))
    if frame.get_size() != want:
        print(f"FAIL  compose size {frame.get_size()}, expected {want}")
        failed += 1
    if (rect.x, rect.y, rect.w, rect.h) != (W + frame_stream.SIDE_GAP, 0, DOCK_W, DOCK_H):
        print(f"FAIL  dock landed at {rect}, expected it beside the main view with tops level")
        failed += 1

    # Nothing to dock -> the frame is the main view alone.
    bare, none_rect = frame_stream.compose(main_surf, None, "both")
    if bare.get_size() != (W, H) or none_rect is not None:
        print(f"FAIL  compose with no dock gave {bare.get_size()} / {none_rect}, expected {(W, H)} / None")
        failed += 1

    # Each viewer picks a view, so every one of them has to resolve a tap
    # correctly. `main` carries no dock at all; `side` IS the dock, edge to edge,
    # so every point in it belongs to the docked view.
    solo, solo_rect = frame_stream.compose(main_surf, side, "main")
    if solo.get_size() != (W, H) or solo_rect is not None:
        print(f"FAIL  the main-only view gave {solo.get_size()} / {solo_rect}, expected {(W, H)} / None")
        failed += 1
    only, only_rect = frame_stream.compose(main_surf, side, "side")
    if only.get_size() != (DOCK_W, DOCK_H) or (only_rect.x, only_rect.y, only_rect.w, only_rect.h) != (0, 0, DOCK_W, DOCK_H):
        print(f"FAIL  the dock-only view gave {only.get_size()} / {only_rect}, expected the dock filling the frame")
        failed += 1
    if not getattr(frame_stream.tap_event((DOCK_W - 1, DOCK_H - 1), only_rect), "side_view", False):
        print("FAIL  in the dock-only view the far corner was not routed to the dock")
        failed += 1

    # Asking for the dock when nothing is docked — it closed, or a setup screen
    # with no second window — shows the main view rather than an empty frame.
    fallback, fb_rect = frame_stream.compose(main_surf, None, "side")
    if fallback.get_size() != (W, H) or fb_rect is not None:
        print(f"FAIL  dock-only with no dock gave {fallback.get_size()} / {fb_rect}, expected a fallback to the main view")
        failed += 1
    if frame_stream.compose(None, None, "both")[0] is not None:
        print("FAIL  compose with nothing published at all must yield no frame")
        failed += 1

    # A view name off the wire is never trusted. Anything unknown is the default,
    # so a stale bookmark still shows the app rather than erroring.
    for raw in ("both", "main", "side"):
        if frame_stream.clean_view(raw) != raw:
            print(f"FAIL  clean_view rejected the valid view {raw!r}")
            failed += 1
    for raw in (None, "", "BOTH", "bell", "../etc", 7, ["side"]):
        if frame_stream.clean_view(raw) != frame_stream.DEFAULT_VIEW:
            print(f"FAIL  clean_view({raw!r}) = {frame_stream.clean_view(raw)!r}, expected the default")
            failed += 1
    if frame_stream.DEFAULT_VIEW not in frame_stream.VIEWS:
        print("FAIL  the default view is not one of the views")
        failed += 1

    # A tap aimed at a view that is NOT on screen must miss, never be re-aimed at
    # whatever occupies that point in the fallback. Serving the main view when the
    # dock is absent is a kindness (a frame beats a broken <img>); resolving a tap
    # against it is a press the user never aimed at.
    #
    # Found 2026-08-23: on the setup menu, where no bell window exists, a tap at
    # the ON cap's position in the dock-only view resolved to (365, 256) of the
    # 730x610 setup screen — inside a TIMS button.
    for view, dock, want in [
        ("side", True, "side"),  # the dock is there: resolve against it
        ("side", False, None),  # the dock is gone: DROP, do not fall back
        ("both", True, "both"),
        ("both", False, "both"),  # no dock just means no dock in the frame
        ("main", True, "main"),
        ("main", False, "main"),
    ]:
        got = frame_stream.tap_target(view, dock)
        if got != want:
            print(f"FAIL  tap_target({view!r}, has_dock={dock}) = {got!r}, expected {want!r}")
            failed += 1

    # A tap in the dock is marked and arrives in the DOCK's coordinates, so its
    # consumer never learns where the dock was placed.
    inside = (rect.x + 10, rect.y + 20)
    ev = frame_stream.tap_event(inside, rect)
    if not getattr(ev, "side_view", False) or ev.pos != (10, 20):
        print(f"FAIL  a tap in the dock gave side_view={getattr(ev, 'side_view', False)} pos={ev.pos}, expected True/(10, 20)")
        failed += 1

    # Everything else is the event this file has always posted: unmarked, in
    # main-view coordinates. The gutter counts as everything else.
    for pt, why in [((5, 5), "inside the main view"), ((W + 2, 5), "in the gutter"), ((rect.right + 1, 5), "past the dock")]:
        ev = frame_stream.tap_event(pt, rect)
        if getattr(ev, "side_view", False) or ev.pos != pt:
            print(f"FAIL  a tap {why} was claimed by the dock or moved: side_view={getattr(ev, 'side_view', False)} pos={ev.pos}")
            failed += 1

    # Corners: the dock's own top-left belongs to it, one pixel outside does not.
    if not getattr(frame_stream.tap_event(rect.topleft, rect), "side_view", False):
        print("FAIL  the dock's top-left pixel was not claimed by the dock")
        failed += 1
    if getattr(frame_stream.tap_event((rect.x - 1, rect.y), rect), "side_view", False):
        print("FAIL  the pixel left of the dock was claimed by it")
        failed += 1

    # No dock published -> nothing can ever be routed to one.
    for pt in ((5, 5), (W + 100, 100)):
        if getattr(frame_stream.tap_event(pt, None), "side_view", False):
            print(f"FAIL  {pt} was routed to a dock that does not exist")
            failed += 1

    pygame.quit()
    return failed


def main() -> int:
    failed = check_bind() + check_tap() + check_dock()
    total = len(BIND_CASES) + 1 + len(TAP_CASES) + len(DEGENERATE_CASES) + 2 + 33
    print(f"test_stream: {total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

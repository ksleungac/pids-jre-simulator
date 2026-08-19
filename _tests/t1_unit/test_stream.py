# SPDX-License-Identifier: MIT
# TIER: T1 — window mirroring: exposure and touch, as pure decisions
"""T1 — window mirroring: the pure decisions behind exposure and touch.

Module scope is the FEATURE, not a function or an incident. Two decisions live
here because both are pure, both belong to mirroring, and both fail silently:

  1. WHO CAN REACH IT  — resolve_bind_host: launch flags -> bind address
  2. WHERE A TAP LANDS — frame_point: a normalised tap -> a frame pixel

Neither has a loud failure mode. A bind regression silently exposes the app on
every network the user joins; a mapping regression silently presses the button
next to the one that was tapped. No smoke test notices either.

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


def main() -> int:
    failed = check_bind() + check_tap()
    total = len(BIND_CASES) + 1 + len(TAP_CASES) + len(DEGENERATE_CASES) + 2
    print(f"test_stream: {total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

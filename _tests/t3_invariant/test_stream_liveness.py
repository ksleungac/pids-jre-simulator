# SPDX-License-Identifier: MIT
"""T3 — the streamed frames must keep up with the display.

The realistic silent failure is not "the page 404s" (loud, obvious). It is the
server pinning a STALE frame — thread died, surface cached, lock never
released — while still serving 200 OK. A browser shows a picture and the bug
looks like nothing at all.

Independent oracle: change the display, and the bytes on the wire must change.
That holds regardless of how the encoder is written.

Headless (SDL dummy driver), so it runs in the normal suite.
"""

import os
import sys
import urllib.request
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "hide")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame  # noqa: E402

import frame_stream  # noqa: E402

PORT = 8421  # not DEFAULT_PORT — never collide with a real running app


def _pull_frame(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read()


def main() -> int:
    failed = 0
    pygame.init()
    screen = pygame.display.set_mode((200, 120))

    url = frame_stream.start("127.0.0.1", PORT)
    if url is None:
        print(f"FAIL  could not bind 127.0.0.1:{PORT}")
        return 1

    single = f"http://127.0.0.1:{PORT}/frame.png"

    # 1. a frame is served at all, and it is a real PNG
    screen.fill((10, 13, 18))
    pygame.display.flip()
    a = _pull_frame(single)
    if not a.startswith(b"\x89PNG\r\n\x1a\n"):
        print("FAIL  /frame.png did not return a PNG")
        failed += 1

    # 2. THE INVARIANT: display changes -> served bytes change
    screen.fill((255, 200, 0))
    pygame.display.flip()
    b = _pull_frame(single)
    if a == b:
        print("FAIL  frame did not change after the display changed (stale-frame pin)")
        failed += 1

    # 3. an unchanged display serves stable bytes (no spurious churn)
    c = _pull_frame(single)
    if b != c:
        print("FAIL  frame changed while the display did not")
        failed += 1

    # 4. surviving a display teardown — the setup<->drive transition. The
    #    guard must keep this from crashing, and the last good frame stands in.
    pygame.display.quit()
    d = _pull_frame(single)
    if not d.startswith(b"\x89PNG\r\n\x1a\n"):
        print("FAIL  no frame served while the display was torn down")
        failed += 1

    # 5. multipart stream yields at least two distinct parts
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/stream", timeout=5) as r:
        raw = r.read(120_000)
    parts = [p for p in raw.split(b"--" + frame_stream.BOUNDARY.encode()) if b"image/png" in p]
    if len(parts) < 2:
        print(f"FAIL  multipart stream produced {len(parts)} parts, expected >=2")
        failed += 1

    # 6. CAPTURE-ON-PRESENT, not on request. Frames must be sampled when the
    #    app presents a completed frame — never read off the live surface at
    #    request time, which catches renderers mid-clear and shows as flicker
    #    (the 2026-07-20 "lower LCD flashing" report).
    #
    #    Oracle: mutate the surface WITHOUT flipping. A capture-on-present
    #    implementation still serves the last presented frame; an on-demand
    #    one leaks the un-presented state.
    screen = pygame.display.set_mode((200, 120))
    screen.fill((0, 128, 0))
    pygame.display.flip()  # present green
    presented = _pull_frame(single)

    screen.fill((200, 0, 200))  # draw magenta but DO NOT present it
    after = _pull_frame(single)
    if after != presented:
        print("FAIL  served an un-presented frame (sampling the live surface, not capturing on flip)")
        failed += 1

    pygame.display.flip()  # now present magenta
    if _pull_frame(single) == presented:
        print("FAIL  frame did not update after a genuine flip")
        failed += 1

    frame_stream.stop()
    print(f"test_stream_liveness: {7 - failed}/7 checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

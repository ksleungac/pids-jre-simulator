# SPDX-License-Identifier: MIT
# TIER: T3 — window mirroring, live: frames out, taps back
"""T3 — window mirroring, live: frames go out and taps come back.

Module scope is the FEATURE. Both halves of mirroring are stateful, both run
against a real display, and both have the same class of silent failure — the
page keeps working while the thing it is for stops.

  1. FRAMES KEEP UP     — a stale/hung server still serves 200 OK with a
                          picture on it, and the bug looks like nothing at all
  2. TAPS COME BACK     — a tap that lands one button over produces no error;
                          a tap posted off the main thread appears to work

The pure decisions behind the same feature (who may bind, where a tap maps to)
are T1 `test_stream.py`.

Headless (SDL dummy driver), so it runs in the normal suite.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "hide")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame  # noqa: E402

import frame_stream  # noqa: E402

PORT = 8421  # not DEFAULT_PORT — never collide with a real running app
W, H = 200, 120


def _pull_frame(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read()


def _post_raw(body: bytes, content_type=None) -> int:
    """POST /tap with an arbitrary body, optionally without a Content-Type."""
    headers = {"Content-Type": content_type} if content_type else {}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/tap", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def _tap(fx: float, fy: float) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/tap",
        data=json.dumps({"x": fx, "y": fy}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def _clicks() -> list:
    return pygame.event.get(pygame.MOUSEBUTTONDOWN)


def main() -> int:
    failed = 0
    pygame.init()
    screen = pygame.display.set_mode((W, H))

    if frame_stream.start("127.0.0.1", PORT) is None:
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
    screen = pygame.display.set_mode((W, H))
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

    # ── taps come back ────────────────────────────────────────────────────────
    # The display was torn down and rebuilt above; publish a frame so a tap has
    # something to be relative to, then drain anything left in the queue.
    screen.fill((10, 13, 18))
    pygame.display.flip()
    _clicks()

    # 1. the tap is accepted
    if _tap(0.5, 0.5) != 204:
        print("FAIL  POST /tap did not return 204")
        failed += 1

    # 2. ORDERING: it must not be in the queue yet. The server thread records;
    #    only the main thread's next present may act.
    if _clicks():
        print("FAIL  a tap reached the event queue without a present (posted off-thread)")
        failed += 1

    # 3. presenting replays it, as a left click, at the centre of the frame
    pygame.display.flip()
    got = _clicks()
    if len(got) != 1:
        print(f"FAIL  expected exactly 1 click after present, got {len(got)}")
        failed += 1
    elif got[0].pos != (100, 60) or got[0].button != 1:
        print(f"FAIL  click landed at {got[0].pos} button {got[0].button}, expected (100, 60) button 1")
        failed += 1

    # 4. a tap outside the image is dropped, not clamped to an edge. Clamping
    #    would turn a miss into a press on whatever sits at the border.
    _tap(1.4, 0.5)
    pygame.display.flip()
    if _clicks():
        print("FAIL  an out-of-image tap produced a click")
        failed += 1

    # 5. THE CALLER IS CHECKED, not just the body. /tap is the only WRITE endpoint,
    #    and any page in the user's browser can reach loopback — a CORS-*simple*
    #    POST (text/plain) is sent with no preflight. Requiring application/json
    #    forces a preflight this server answers with 501. Without this, `--stream`
    #    on its own lets any web page drive the app, which is not what D9's
    #    "loopback = zero network exposure" describes.
    for ctype, why in ((None, "no Content-Type"), ("text/plain", "CORS-simple text/plain")):
        try:
            _post_raw(b'{"x": 0.5, "y": 0.5}', ctype)
            print(f"FAIL  a well-formed tap with {why} was accepted (CSRF gate open)")
            failed += 1
        except urllib.error.HTTPError as e:
            if e.code != 415:
                print(f"FAIL  {why} returned {e.code}, expected 415")
                failed += 1

    # 6. a malformed body, correctly typed, is refused and produces nothing
    try:
        _post_raw(b"not json", "application/json")
        print("FAIL  a malformed tap body was accepted")
        failed += 1
    except urllib.error.HTTPError as e:
        if e.code != 400:
            print(f"FAIL  malformed tap body returned {e.code}, expected 400")
            failed += 1
    pygame.display.flip()
    if _clicks():
        print("FAIL  a refused tap produced a click")
        failed += 1

    # 7. presenting with nothing queued must not invent a click
    pygame.display.flip()
    if _clicks():
        print("FAIL  a present with no pending tap produced a click")
        failed += 1

    # 8. rapid taps are not swallowed by each other — a queue, not a slot
    _tap(0.0, 0.0)
    _tap(1.0, 1.0)
    pygame.display.flip()
    got = _clicks()
    if [e.pos for e in got] != [(0, 0), (W - 1, H - 1)]:
        print(f"FAIL  two quick taps replayed as {[e.pos for e in got]}, expected [(0, 0), (199, 119)]")
        failed += 1

    # 9. THE FRAME A TAP IS RESOLVED AGAINST is the one before the present it is
    #    drained on — not the one about to go out. That is what lets a tap arriving
    #    on the same present as a screen change land against the size the client
    #    last saw. Without the drain-before-publish order this resolves against the
    #    NEW size and the click lands somewhere the user never aimed at.
    pygame.display.set_mode((W, H))
    pygame.display.flip()  # publish at 200x120
    _clicks()
    _tap(1.0, 1.0)  # bottom-right of the 200x120 frame the client is looking at
    pygame.display.set_mode((400, 240))  # screen change
    pygame.display.flip()  # drains against the OLD frame, then publishes the new one
    got = _clicks()
    if [e.pos for e in got] != [(W - 1, H - 1)]:
        print(f"FAIL  tap across a screen change resolved to {[e.pos for e in got]}, expected [(199, 119)] (the OLD size)")
        failed += 1

    # 10. the tap queue is BOUNDED — a wedged main loop must not let it grow without
    #     limit. Past the bound the OLDEST taps drop, which is the intended loss:
    #     the newest presses are the ones the user still means.
    pygame.display.set_mode((W, H))
    pygame.display.flip()
    _clicks()
    for i in range(10):  # maxlen is 8
        _tap(i / 10, 0.5)
    pygame.display.flip()
    got = [e.pos[0] for e in _clicks()]
    if len(got) != 8 or got[0] != int(0.2 * W):
        print(
            f"FAIL  10 taps against a bound of 8 replayed {len(got)} starting at x={got[0] if got else None}, expected 8 starting at x={int(0.2 * W)}"
        )
        failed += 1

    frame_stream.stop()
    print(f"test_stream: {18 - failed}/18 checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

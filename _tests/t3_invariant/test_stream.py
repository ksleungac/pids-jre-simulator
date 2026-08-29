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

Each viewer also picks WHICH of the app's windows to look at, so a tap carries
the view it was measured against. That wiring is here rather than in T1 because
it runs from the POST body through the queue to the posted event; T1 owns the
geometry it resolves with.

The pure decisions behind the same feature (who may bind, where a tap maps to,
which view owns a point) are T1 `test_stream.py`.

Headless (SDL dummy driver), so it runs in the normal suite.
"""

import json
import os
import socket
import sys
import time
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


def _tap(fx: float, fy: float, view: str = None) -> int:
    body = {"x": fx, "y": fy}
    if view is not None:
        body["view"] = view
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/tap",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def _post_host(host) -> int:
    """POST a well-formed tap with an arbitrary (or absent) Host; return the status.

    Raw socket rather than urllib, because urllib always supplies a Host and the ABSENT case is
    exactly the one that used to pass.
    """
    body = b'{"x": 0.5, "y": 0.5}'
    head = f"POST /tap HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    if host is not None:
        head += f"Host: {host}\r\n"
    with socket.create_connection(("127.0.0.1", PORT), timeout=5) as s:
        s.sendall((head + "Connection: close\r\n\r\n").encode() + body)
        s.settimeout(5)
        return int(s.recv(64).split(b" ")[1])


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

    # 6b. THE HOST GATE, on reads as well as writes. Any page in the user's browser can point a
    #     short-TTL hostname at 127.0.0.1 and become same-origin with this server; without a Host
    #     check `GET /frame.png` hands it the app's screen, which it can read back off a canvas.
    #     Measured 2026-08-29: before the fix that request returned 200 with the frame while the
    #     same header on /tap correctly returned 421 — the gate existed on exactly one endpoint
    #     while `_allowed_hosts`' docstring and `conventions.md` both said it covered the reads.
    #     An ABSENT Host must fail too; it used to pass, which made the gate opt-out.
    for path, hdrs, want, why in [
        ("/frame.png", {"Host": "evil.example.com"}, 421, "a rebound name must not read the screen"),
        ("/views", {"Host": "evil.example.com"}, 421, "a rebound name must not probe for a second window"),
        ("/", {"Host": "evil.example.com"}, 421, "a rebound name must not be served the page"),
        ("/frame.png", {"Host": f"127.0.0.1:{PORT}"}, 200, "the real client must still be served"),
    ]:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", headers=hdrs)
        try:
            got = urllib.request.urlopen(req, timeout=5).status
        except urllib.error.HTTPError as e:
            got = e.code
        if got != want:
            print(f"FAIL  {path} with Host={hdrs['Host']!r} returned {got}, expected {want} ({why})")
            failed += 1
    # 6c. THE PAGE IS SERVED SUBSTITUTED, not concatenated. `_page_prelude` injects the TIMS button
    #     palette and VIEW_IDS at a `<!--PRELUDE-->` marker; prepending instead put a <style> ahead
    #     of the doctype and dropped the page into quirks mode. And if a `_PAGE` edit ever loses the
    #     marker, `.replace` becomes a silent no-op whose failure is NOT cosmetic: every `--btn-*`
    #     goes invalid AND `VIEW_IDS` is undefined, which throws at `VIEW_IDS.map(...)` and takes out
    #     the whole script — view cells, zoom, reconnect and the tap POST — while the <img> keeps
    #     streaming, so the page looks alive and does nothing.
    page = _pull_frame(f"http://127.0.0.1:{PORT}/")
    if not page.startswith(b"<!doctype html>"):
        print(f"FAIL  the served page does not start with the doctype: {page[:40]!r}")
        failed += 1
    if b"<!--PRELUDE-->" in page:
        print("FAIL  the PRELUDE marker survived into the served page; the substitution silently no-opped")
        failed += 1
    for token in (b"--btn-top", b"VIEW_IDS"):
        if token not in page:
            print(f"FAIL  the served page is missing {token!r}; the injected prelude did not land")
            failed += 1

    if _post_host(None) != 421:
        print("FAIL  a POST with NO Host header was accepted; an absent Host must fail closed")
        failed += 1
    if _post_host("evil.example.com") != 421:
        print("FAIL  a POST with a foreign Host was accepted")
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

    # 9b. A TAP CARRIES ITS VIEWER'S VIEW, and is resolved against THAT frame.
    #     Each viewer picks what to look at (`/stream?view=`), so the same fraction
    #     is a different point per view — 0.5,0.5 is the middle of the docked box
    #     in `side` and the middle of the PIDS in `main`. Resolving every tap
    #     against one view sends the others somewhere plausible and wrong, with no
    #     error anywhere. T1 covers the geometry; only this reaches the wiring that
    #     carries the view from the POST body through to the posted event.
    pygame.display.set_mode((W, H))
    dock = pygame.Surface((40, 60))
    frame_stream.set_side_view(dock)
    pygame.display.flip()
    _clicks()

    _tap(0.5, 0.5, view="side")
    pygame.display.flip()
    got = _clicks()
    if len(got) != 1 or not getattr(got[0], "side_view", False) or got[0].pos != (20, 30):
        print(f"FAIL  a tap in the dock-only view gave {[(e.pos, getattr(e, 'side_view', False)) for e in got]}, expected [((20, 30), True)]")
        failed += 1

    _tap(0.5, 0.5, view="main")
    pygame.display.flip()
    got = _clicks()
    if len(got) != 1 or getattr(got[0], "side_view", False) or got[0].pos != (W // 2, H // 2):
        print(
            f"FAIL  the same fraction in the main-only view gave {[(e.pos, getattr(e, 'side_view', False)) for e in got]}, expected [((100, 60), False)]"
        )
        failed += 1

    # An unknown view is the default, never an error: a stale bookmark still taps.
    _tap(0.5, 0.5, view="bogus")
    pygame.display.flip()
    got = _clicks()
    if len(got) != 1 or getattr(got[0], "side_view", False):
        print(f"FAIL  an unknown view did not fall back to the default: {[(e.pos, getattr(e, 'side_view', False)) for e in got]}")
        failed += 1

    # 9c. THE DOCK GOES AWAY UNDER A VIEWER who is still asking for it — the
    #     drive ends and the app returns to the setup menu. The frame falls back
    #     to the main view so the <img> keeps working, but a tap must MISS: the
    #     finger was aimed at a box that is no longer on screen, and re-aiming it
    #     presses whatever occupies that point. Found 2026-08-23 on the real setup
    #     menu, where it landed inside a TIMS button.
    frame_stream.set_side_view(None)
    pygame.display.flip()
    _clicks()

    _tap(0.5, 0.5, view="side")
    pygame.display.flip()
    got = _clicks()
    if got:
        print(f"FAIL  a tap for the absent dock was re-aimed at the main view: {[e.pos for e in got]}, expected no click")
        failed += 1

    # The page is told, so it can stop offering a view that is not there.
    for expect_side, when in ((False, "with nothing docked"),):
        state = json.loads(_pull_frame(f"http://127.0.0.1:{PORT}/views").decode())
        if state.get("side") is not expect_side:
            print(f"FAIL  /views {when} reported {state}, expected side={expect_side}")
            failed += 1
    frame_stream.set_side_view(pygame.Surface((10, 10)))
    state = json.loads(_pull_frame(f"http://127.0.0.1:{PORT}/views").decode())
    if state.get("side") is not True:
        print(f"FAIL  /views with a dock reported {state}, expected side=True")
        failed += 1
    frame_stream.set_side_view(None)
    pygame.display.flip()
    _clicks()

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

    # 11. SWITCHING VIEW MUST NEVER RUN OUT OF STREAM SLOTS.
    #     Re-pointing the page's <img> abandons the previous request. A browser that leaves that
    #     socket OPEN is invisible to the server until its send buffer fills and the write times
    #     out — measured at 8.5s — so with a refusing cap, MAX_CLIENTS switches inside that window
    #     locked every later stream out with 503, which draws as a broken image. Reported
    #     2026-08-29 ("after some swaps the image can't be loaded and gives me a question mark").
    #
    #     Oracle is the user-visible contract, independent of how the cap is implemented: every
    #     request I make gets a stream, and the newest one carries frames. Sockets are deliberately
    #     kept open and unread — closing them is what the old code needed in order to cope, and is
    #     exactly what the real browser did not do.
    abandoned = []
    try:
        for i in range(frame_stream.MAX_CLIENTS * 3 + 1):
            s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
            abandoned.append(s)
            s.sendall(f"GET /stream?view=both HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n\r\n".encode())
            s.settimeout(3)
            status = s.recv(60).split(b"\r\n")[0]
            if b"200" not in status:
                print(f"FAIL  stream request {i + 1} after {i} abandoned switches was refused: {status!r}")
                failed += 1
                break
        else:
            pygame.display.flip()
            newest, blob = abandoned[-1], b""
            deadline = time.time() + 3
            while time.time() < deadline and b"\x89PNG" not in blob:
                blob += newest.recv(8192)
            if b"\x89PNG" not in blob:
                print("FAIL  the newest stream was admitted but delivered no frame")
                failed += 1
        if len(frame_stream._streams) > frame_stream.MAX_CLIENTS:
            print(f"FAIL  {len(frame_stream._streams)} live handlers, cap is {frame_stream.MAX_CLIENTS}")
            failed += 1
    finally:
        for s in abandoned:
            s.close()

    # 12. TURNING MIRRORING OFF MUST STOP THE MIRRORING, not merely close the listener.
    #     The oracle is the promise, not a proxy for it: an EXISTING stream has to end. Checking
    #     only that a NEW connection is refused passes while a live handler keeps shipping frames,
    #     which is precisely the hole the shared `_stop` latch left — `apply_mode` clears it to
    #     start the next generation, so a handler whose write straddles the clear sees an unset
    #     event and carries on with no server left to evict it (`principles.md` § "Validate against
    #     the outcome, not a proxy"). `stop` now sets every registered handler's own Event instead.
    live = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    try:
        live.sendall(f"GET /stream HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n\r\n".encode())
        live.settimeout(3)
        live.recv(4096)  # headers + first part: the stream is genuinely running
        frame_stream.apply_mode("off", PORT)
        live.settimeout(5)
        drained = b""
        while True:  # EOF is the assertion — the server ended the handler, not just the listener
            chunk = live.recv(8192)
            if not chunk:
                break
            drained += chunk
            if len(drained) > 2_000_000:
                print("FAIL  a live stream kept delivering frames after mirroring was turned off")
                failed += 1
                break
    except (socket.timeout, TimeoutError):
        print("FAIL  a live stream neither ended nor errored after mirroring was turned off")
        failed += 1
    except OSError:
        pass  # a reset is a clean end too
    finally:
        live.close()
    if frame_stream._streams:
        print(f"FAIL  {len(frame_stream._streams)} handler(s) still registered after stop()")
        failed += 1

    # 13. and the settings page's apply really rebinds — including onto the SAME port it just
    #     released, which is the common case since only the mode changed.
    for mode, want in (("local", True), ("off", False), ("local", True)):
        urls = frame_stream.apply_mode(mode, PORT)
        if bool(urls) is not want:
            print(f"FAIL  apply_mode({mode!r}) returned {urls}, expected {'addresses' if want else 'none'}")
            failed += 1
    frame_stream.apply_mode("off", PORT)

    frame_stream.stop()
    # No denominator: it was a hand-maintained literal that drifted the moment a section was added
    # (`principles.md` § "A measurement is a claim…" — claim only what is known).
    print("test_stream: all checks passed" if not failed else f"test_stream: {failed} check(s) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

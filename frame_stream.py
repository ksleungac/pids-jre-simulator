# SPDX-License-Identifier: MIT
"""Mirror the app's window to a browser over HTTP, and take taps back.

Serves whatever is currently on the PC screen — setup flow, tutorial, drive —
as an MJPEG-style ``multipart/x-mixed-replace`` stream of PNG frames. The
client is a plain ``<img>``; no JavaScript on the display path.

Design decisions + rejected alternatives live in ``docs/wip/WIP_frame_streaming.md``.
Summary of the load-bearing ones:

- **PNG, not JPEG.** Measured on this app's AA-off content: PNG is 4x smaller
  than JPEG *and* pixel-exact, where JPEG damages ~7% of subpixels. LCD content
  (flat fills, sharp glyphs) is JPEG's worst case.
- **Zero new dependencies.** stdlib ``http.server`` + pygame's own PNG writer.
  If this design ever needs a dep, re-examine the design (critical_lessons 3).
- **Off by default.** Enabled per-launch via ``--stream`` / ``--stream-lan``.
- **A tap is a synthetic left MOUSEBUTTONDOWN, nothing more** (stage 2). Every
  click consumer in this app — the whole TIMS setup flow, the tutorial, and the
  drive's click-to-jump — reads ``event.pos`` off a ``MOUSEBUTTONDOWN`` with
  ``button == 1``, and production contains no ``MOUSEBUTTONUP``, ``MOUSEMOTION``
  or ``mouse.get_pressed`` at all. So posting that one event reaches every
  existing target with no changes to any of them, and the remote can do exactly
  what a mouse can do here — no more (there is no other event to forge) and no
  less. ``app.py`` and ``tims/`` stay untouched.

# CONTRACT: never cache the display Surface; capture on the MAIN thread.
# ``main.py`` calls ``pygame.display.quit()`` between setup and drive, which
# frees the surface — a cached reference would be read-after-free. ``_publish``
# re-fetches via ``pygame.display.get_surface()`` on every present, from the
# flip/update hook, and stores a COPY. ``_snapshot`` (server thread) only
# encodes that copy, which is why a frame is still served across a teardown.
"""

from __future__ import annotations

import io
import json
import socket
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import pygame

DEFAULT_PORT = 8541
FPS = 15  # stream pacing; the LCD is mostly static so this is ample
MAX_CLIENTS = 3  # browsers routinely open a speculative 2nd connection, so >1
BOUNDARY = "pidsframe"

_lock = threading.Lock()  # held across display teardown (install_display_quit_guard)
_clients = 0
_clients_lock = threading.Lock()
_server: Optional[ThreadingHTTPServer] = None

# Published by the main thread on present (flip/update); encoded lazily by the
# server thread. `_seq` lets the encoder skip re-encoding an unchanged frame.
_frame: Optional[pygame.Surface] = None
_seq = 0
_png: Optional[bytes] = None  # cache of _frame at _png_seq
_png_seq = -1

# Taps arrive on server threads and are replayed on the MAIN thread by the
# present hook. Same shape as the OCR driver's `pending_next_pa`: the background
# side only records, the main side acts. A deque rather than a single slot so a
# quick second tap is not swallowed by the one before it; bounded so a wedged
# main loop cannot grow it without limit.
_taps: "deque[tuple[float, float]]" = deque(maxlen=8)
_taps_lock = threading.Lock()


def _allowed_hosts() -> set:
    """Host-header values this server answers to.

    Loopback names plus whatever `lan_candidates()` found, so a tablet reaching
    the printed LAN URL is accepted while an attacker-controlled DNS name
    resolving to 127.0.0.1 (DNS rebinding) is not.
    """
    return {"localhost", "127.0.0.1", "0.0.0.0", "::1", *lan_candidates()}


def resolve_bind_host(stream: bool, lan: bool) -> Optional[str]:
    """Map the launch flags to a bind address, or None when streaming is off.

    Pure function — the unit-test seam for the flag matrix. ``lan`` implies
    streaming even without ``--stream``, so ``--stream-lan`` alone works.

    LAN binding is deliberately opt-in: 127.0.0.1 needs no firewall grant and
    exposes nothing, while 0.0.0.0 raises the Windows Defender prompt.
    """
    if lan:
        return "0.0.0.0"
    if stream:
        return "127.0.0.1"
    return None


def _is_usable_lan(ip: str) -> bool:
    """True for an address a phone on the same Wi-Fi could plausibly reach.

    Excludes loopback and APIPA/link-local (169.254.x — an adapter that failed
    DHCP, present on every idle virtual NIC and never routable).
    """
    return not (ip.startswith("127.") or ip.startswith("169.254."))


def lan_candidates() -> list[str]:
    """Every address a client might reach this server on, best guess first.

    # CONTRACT: return a LIST, never a single "the" IP.
    # The route-to-8.8.8.8 trick names the DEFAULT route, which on any machine
    # running a VPN is the tunnel (observed: NordLynx 10.5.0.2) and not the
    # Wi-Fi LAN the phone is actually on. There is no reliable way to tell a
    # VPN tunnel from a real LAN by address alone — 10.x is legitimately both.
    # So offer the candidates and let the user pick, rather than confidently
    # printing one wrong URL.
    """
    found: list[str] = []

    # Default-route address first — usually right, and when a VPN is up it is
    # at least a real interface, just possibly not the useful one.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if _is_usable_lan(ip):
            found.append(ip)
    except OSError:
        pass
    finally:
        s.close()

    # Then everything else bound to this host.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _is_usable_lan(ip) and ip not in found:
                found.append(ip)
    except OSError:
        pass

    return found or ["127.0.0.1"]


def install_display_quit_guard() -> None:
    """Wrap ``pygame.display.quit`` so every teardown holds the frame lock.

    Same one-seam idiom as ``window_utils.install_topmost_hook``: there are two
    teardown sites (``main.py`` setup->drive, ``app.py`` cleanup on home-return)
    and new ones would be easy to add without remembering to guard them. Hooking
    the call itself is regression-proof; scattering the guard is what rots.
    Idempotent.
    """
    if getattr(pygame.display.quit, "_stream_wrapped", False):
        return
    _orig = pygame.display.quit

    def _quit(*args, **kwargs):
        with _lock:
            return _orig(*args, **kwargs)

    _quit._stream_wrapped = True
    pygame.display.quit = _quit


def _publish() -> None:
    """Capture the just-presented frame. Runs on the MAIN thread, from the
    flip/update hook — never from a server thread.

    # CONTRACT: capture on present, never asynchronously.
    # Reading pygame.display.get_surface() from the server thread samples the
    # surface MID-DRAW — between a renderer's clear and its redraw — so the
    # client sees half-drawn frames as flicker. It is invisible in the app
    # window, which only ever shows completed frames via flip(). Observed
    # 2026-07-20 as "lower LCD elements flashing", worst on e235_0 transfer
    # pages: the most elements to redraw = the widest window to catch torn.
    # Capturing here means every published frame is one the user actually saw.
    """
    global _frame, _seq
    surf = pygame.display.get_surface()
    if surf is None:
        return
    _frame = surf.copy()  # ~0.4ms; never mutated after publish, so no lock needed
    _seq += 1


def _snapshot() -> Optional[bytes]:
    """Encode the latest published frame as PNG. Runs on the server thread.

    Reuses the cached encoding while the frame is unchanged, so a static
    display costs one encode rather than one per client per tick.
    """
    global _png, _png_seq
    frame, seq = _frame, _seq  # atomic reads; a torn pair only costs one stale tick
    if frame is None:
        return _png
    if seq != _png_seq:
        buf = io.BytesIO()
        pygame.image.save(frame, buf, "frame.png")
        _png, _png_seq = buf.getvalue(), seq
    return _png


def frame_point(fx: float, fy: float, w: int, h: int) -> Optional[tuple[int, int]]:
    """Map a NORMALISED tap (0..1 across the frame) to a pixel in a ``w`` x ``h`` frame.

    Returns None when the tap is outside the frame, which the caller drops.

    # CONTRACT: the client sends fractions, never pixels.
    # The client cannot know the frame's true size -- it knows what its <img>
    # last decoded, and the frame changes size under it (setup 730x610 -> drive
    # 730x420+band -> tutorial 1100x500). Fractions are resolved here against
    # the frame actually published, so a tap in flight across a screen change
    # lands proportionally instead of at a stale absolute pixel. It also keeps
    # the arithmetic on this side of the wire, where a test can reach it.
    """
    if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
        return None
    if w <= 0 or h <= 0:
        return None  # a frame with no pixels has none to land on
    # Clamp: fx == 1.0 would index one past the edge.
    x = min(int(fx * w), w - 1)
    y = min(int(fy * h), h - 1)
    return x, y


def queue_tap(fx: float, fy: float) -> None:
    """Record a normalised tap. Runs on a SERVER thread -- records only, never acts."""
    with _taps_lock:
        _taps.append((fx, fy))


def _drain_taps() -> None:
    """Replay recorded taps as synthetic left-clicks. Runs on the MAIN thread.

    # CONTRACT: post from the main thread, never from the server thread.
    # Mirrors how the auto-driver hands work across the boundary (it sets a
    # flag; `_handle_input_main` acts). Keeping every pygame call on the main
    # thread is what makes this feature unable to introduce a threading bug
    # into a render path it otherwise does not touch.
    """
    with _taps_lock:
        if not _taps:
            return
        pending = list(_taps)
        _taps.clear()
    # Drained BEFORE this frame is published, deliberately: `_frame` is the frame
    # BEFORE the one about to go out, so a tap arriving on the same present as a
    # screen change resolves against the size the client last saw rather than the
    # one it has not received yet. That is one present of slack (~33 ms), not a
    # guarantee about the frame the remote was actually looking at, which is
    # older by the stream pacing plus the network plus human reaction. Correctness
    # does not rest on it: a stale tap misses, exactly as a real mouse click does
    # during a screen transition.
    frame = _frame
    if frame is None:
        return  # nothing published yet; a tap has no frame to be relative to
    w, h = frame.get_size()
    for fx, fy in pending:
        pt = frame_point(fx, fy, w, h)
        if pt is None:
            continue
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pt, button=1))


def install_present_hook() -> None:
    """Wrap ``pygame.display.flip`` / ``update`` so each completed frame is
    captured. One seam — flip/update are called from 18 files and a new screen
    must not have to remember to publish. Idempotent.
    """
    for name in ("flip", "update"):
        orig = getattr(pygame.display, name)
        if getattr(orig, "_stream_wrapped", False):
            continue

        def _wrapped(*args, _orig=orig, **kwargs):
            r = _orig(*args, **kwargs)
            # Separate guards: the tap half is the newer, optional one, and a fault
            # in it must not stop the display half from publishing. Sharing a
            # try/except would freeze the browser on a cached frame with nothing
            # logged anywhere (`principles.md` § "A bonus feature ... is not a bonus").
            try:
                _drain_taps()
            except Exception:
                pass
            try:
                _publish()
            except Exception:
                pass  # mirroring must never break the app's render loop
            return r

        _wrapped._stream_wrapped = True
        setattr(pygame.display, name, _wrapped)


_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PA Simulator</title>
<style>
  html,body{margin:0;height:100%;background:#0a0d12;overflow:hidden}
  body{display:flex;align-items:center;justify-content:center}
  /* NO image-rendering override by default.
     The stream mixes two kinds of content: TIMS chrome drawn anti-aliasing-OFF
     at native pixel size, and LCD text drawn anti-aliasing-ON. One filter
     cannot serve both, so the answer is to avoid RESAMPLING rather than to
     pick a filter -- see the 1:1 mode below. When the image must be resized,
     smooth (the browser default) is the lesser evil: `pixelated` on a
     DOWNSCALE (the phone case, 730px into ~390 CSS px) drops thin 1px strokes
     outright and stair-steps every edge. */
  /* Neither mode may overflow the viewport: the body is `overflow:hidden`, so an
     oversized image is CLIPPED rather than scrolled -- the edges of the display
     just disappear. So `fit` is the default, and 1:1 keeps the same clamp, which
     makes it "1:1 unless that would overflow" rather than "1:1 or nothing".
     Author 2026-08-19: "as long as it's reactive of some sorts, meaning it does
     not overflow on a 'normal' resolution. resolution even smaller than my app's
     1x drawing resolution i don't care." */
  img{display:block;max-width:100vw;max-height:100vh}
  #tag{position:fixed;left:0;right:0;bottom:0;padding:6px;
       font:12px system-ui,sans-serif;color:#96a2b0;text-align:center;
       background:#0a0d12cc;opacity:0;transition:opacity .25s}
  #tag.show{opacity:1}
  /* The zoom control is its OWN button, not a gesture on the image: a tap on
     the image now means "click the thing under my finger", so a whole-page
     gesture would fight every button in the app. Deliberately browser chrome
     rather than a pygame-drawn control -- a control drawn into the frame would
     either appear on the PC window too, or make the stream a composited view
     that no longer matches what the PC shows. */
  #zoom{position:fixed;right:10px;bottom:10px;z-index:2;
        -webkit-appearance:none;appearance:none;border:1px solid #2a3340;
        border-radius:6px;background:#141a22cc;color:#96a2b0;
        font:600 12px system-ui,sans-serif;letter-spacing:.05em;
        padding:8px 12px;min-width:52px;cursor:pointer}
  #zoom:active{background:#1e2733}
</style>
<img id="v" src="/stream" alt="PA Simulator"
     onerror="setTimeout(()=>this.src='/stream?'+Date.now(),1000)">
<button id="zoom" type="button">1:1</button>
<div id="tag"></div>
<script>
// Display path works without this -- the <img> above renders on its own.
// JS only adds the 1:1 mode and the reconnect nudge.
const img = document.getElementById('v'), tag = document.getElementById('tag'),
      zoom = document.getElementById('zoom');
// FIT is the default; tap switches to 1:1. 1:1 maps one source pixel to one
// PHYSICAL device pixel, so AA-on LCD text and AA-off TIMS chrome both land
// with no resampling -- but it is an opt-in now rather than the default,
// because a frame wider than the viewport is clipped, not scrolled.
// (Until 2026-08-14 the 1:1 default also bought sharpness the app window did
// not have, which is why it was chosen: the process was DPI-unaware and
// Windows resampled the window at 125%. window_utils.declare_dpi_awareness
// plus whole-multiple zoom fixed that at the source, so 1:1 now only avoids
// the CLIENT's resample. See #72.)
let native = false, lastW = 0;
function apply() {
  lastW = img.naturalWidth;
  if (native) {
    img.style.width = (img.naturalWidth / window.devicePixelRatio) + 'px';
    say('1:1 pixel-exact');
  } else {
    img.style.width = '';
    say('fit to screen');
  }
}
function say(t) {
  tag.textContent = t;
  tag.classList.add('show');
  clearTimeout(say.t);
  say.t = setTimeout(() => tag.classList.remove('show'), 1800);
}
zoom.addEventListener('click', () => {
  native = !native;
  zoom.textContent = native ? 'FIT' : '1:1';
  apply();
});

// --- taps ------------------------------------------------------------------
// Sent as FRACTIONS of the image, not pixels: the displayed size is whatever
// CSS settled on (fit mode resamples, 1:1 divides by devicePixelRatio), and the
// frame itself changes size across screens. getBoundingClientRect is the only
// thing that knows the on-screen box, and a fraction of it survives both.
// The server resolves the fraction against the frame it actually published.
img.addEventListener('click', e => {
  const r = img.getBoundingClientRect();
  if (!r.width || !r.height) return;
  fetch('/tap', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      x: (e.clientX - r.left) / r.width,
      y: (e.clientY - r.top) / r.height
    })
  }).catch(() => {});   // a dropped tap is a missed press, not a broken page
});
// A multipart stream fires `load` on EVERY frame, so only re-apply when the
// frame size actually changed (setup 730x610 -> drive 730x420+band ->
// tutorial 1100x500). Without the guard the label would flash 15x/second.
img.addEventListener('load', () => { if (img.naturalWidth !== lastW) apply(); });
addEventListener('resize', apply);
</script>
"""


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silence per-request console spam
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_page()
        elif path == "/frame.png":
            self._send_single()
        elif path == "/stream":
            self._send_stream()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/tap":
            self.send_error(404)
            return
        # CONTRACT: /tap is the only WRITE endpoint — check the caller, not just the body.
        # Stage 1 was read-only, so D9's "loopback = zero network exposure" held on its own.
        # A tap drives the app, and any page in the user's browser can reach loopback: a
        # CORS-*simple* POST (text/plain) is sent with no preflight. Requiring
        # application/json forces a preflight, which this server answers with 501 (no
        # do_OPTIONS), and checking Host closes DNS rebinding. Both are what the client
        # already sends, so nothing on the page changes.
        if not self.headers.get("Content-Type", "").split(";")[0].strip() == "application/json":
            self.send_error(415, "expected Content-Type: application/json")
            return
        host = self.headers.get("Host", "").rsplit(":", 1)[0].strip("[]")
        if host and host not in _allowed_hosts():
            self.send_error(421, "unrecognised Host")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > 256:  # a tap is ~40 bytes; anything else is not one
                raise ValueError("bad length")
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            queue_tap(float(body["x"]), float(body["y"]))
        except Exception:
            self.send_error(400, 'expected {"x": <0..1>, "y": <0..1>}')
            return
        # 204: the tap's effect arrives on the video stream, not in this reply.
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_page(self):
        body = _PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_single(self):
        """One-shot frame. Fallback for clients where multipart in an <img>
        misbehaves (historically iOS Safari) -- poll this instead."""
        png = _snapshot()
        if png is None:
            self.send_error(503, "no frame yet")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(png)

    def _send_stream(self):
        global _clients
        with _clients_lock:
            if _clients >= MAX_CLIENTS:
                self.send_error(503, "too many clients")
                return
            _clients += 1
        try:
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            delay = 1.0 / FPS
            while True:
                png = _snapshot()
                if png is not None:
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/png\r\n")
                    self.wfile.write(f"Content-Length: {len(png)}\r\n\r\n".encode())
                    self.wfile.write(png)
                    self.wfile.write(b"\r\n")
                # Mobile browsers reconnect on screen-lock / network roam; a
                # stale handler would otherwise block on write until an OS
                # timeout, leaking a thread per reconnect.
                if _stop.wait(delay):
                    break
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            pass  # ordinary client disconnect
        finally:
            with _clients_lock:
                _clients -= 1


_stop = threading.Event()


def start(host: str, port: int = DEFAULT_PORT) -> Optional[list[str]]:
    """Start the streaming server on a daemon thread. Returns the URLs it can be
    reached on (see ``lan_candidates``), or None if the bind failed.

    # CONTRACT: bind failure must be LOUD.
    # A declined Windows Defender prompt or a blocked public-Wi-Fi profile
    # leaves a dead port. Swallowing that silently is the critical_lessons 2
    # silent-skip pathology -- the caller prints the failure.
    """
    global _server
    install_display_quit_guard()
    install_present_hook()
    try:
        _server = ThreadingHTTPServer((host, port), _Handler)
    except OSError as e:
        print(f"[stream] FAILED to bind {host}:{port} -- {e}")
        print("[stream] streaming is OFF for this session (firewall prompt declined, or port in use)")
        return None
    _server.daemon_threads = True
    _server.timeout = 1.0
    threading.Thread(target=_server.serve_forever, daemon=True, name="frame-stream").start()
    hosts = lan_candidates() if host == "0.0.0.0" else ["127.0.0.1"]
    return [f"http://{h}:{port}/" for h in hosts]


def stop() -> None:
    """Shut the server down and release its socket."""
    _stop.set()
    if _server is not None:
        _server.shutdown()

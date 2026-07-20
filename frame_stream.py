"""Mirror the app's window to a browser over HTTP (stage 1: display-only).

Serves whatever is currently on the PC screen — setup flow, tutorial, drive —
as an MJPEG-style ``multipart/x-mixed-replace`` stream of PNG frames. The
client is a plain ``<img>``; no JavaScript on the display path.

Design decisions + rejected alternatives live in ``WIP_frame_streaming.md``.
Summary of the load-bearing ones:

- **PNG, not JPEG.** Measured on this app's AA-off content: PNG is 4x smaller
  than JPEG *and* pixel-exact, where JPEG damages ~7% of subpixels. LCD content
  (flat fills, sharp glyphs) is JPEG's worst case.
- **Zero new dependencies.** stdlib ``http.server`` + pygame's own PNG writer.
  If this design ever needs a dep, re-examine the design (critical_lessons 3).
- **Off by default.** Enabled per-launch via ``--stream`` / ``--stream-lan``.

# CONTRACT: never cache the display Surface across frames.
# ``main.py`` calls ``pygame.display.quit()`` between setup and drive, which
# frees the surface — a cached reference would be read-after-free. Always
# re-fetch via ``pygame.display.get_surface()`` inside ``_snapshot()``, under
# the pause lock.
"""

from __future__ import annotations

import io
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import pygame

DEFAULT_PORT = 8420
FPS = 15  # stream pacing; the LCD is mostly static so this is ample
MAX_CLIENTS = 3  # browsers routinely open a speculative 2nd connection, so >1
BOUNDARY = "pidsframe"

_lock = threading.Lock()  # held across display teardown (see paused())
_clients = 0
_clients_lock = threading.Lock()
_server: Optional[ThreadingHTTPServer] = None

# Published by the main thread on present (flip/update); encoded lazily by the
# server thread. `_seq` lets the encoder skip re-encoding an unchanged frame.
_frame: Optional[pygame.Surface] = None
_seq = 0
_png: Optional[bytes] = None  # cache of _frame at _png_seq
_png_seq = -1


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


class paused:
    """Context manager: suspend frame grabbing across a display teardown, so a
    streaming thread can never snapshot a surface that is being freed."""

    def __enter__(self):
        _lock.acquire()
        return self

    def __exit__(self, *exc):
        _lock.release()
        return False


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
  img{display:block}
  img.fit{max-width:100vw;max-height:100vh}
  #tag{position:fixed;left:0;right:0;bottom:0;padding:6px;
       font:12px system-ui,sans-serif;color:#96a2b0;text-align:center;
       background:#0a0d12cc;opacity:0;transition:opacity .25s}
  #tag.show{opacity:1}
</style>
<img id="v" class="fit" src="/stream" alt="PA Simulator"
     onerror="setTimeout(()=>this.src='/stream?'+Date.now(),1000)">
<div id="tag"></div>
<script>
// Display path works without this -- the <img> above renders on its own.
// JS only adds the 1:1 mode and the reconnect nudge.
const img = document.getElementById('v'), tag = document.getElementById('tag');
// 1:1 is the DEFAULT. Mapping one source pixel to one PHYSICAL device pixel
// means no resampling at all, so AA-on LCD text and AA-off TIMS chrome both
// land exactly as rendered -- sharper than the app's own window, which
// Windows softens under display scaling (125% on the dev machine).
let native = true, lastW = 0;
function apply() {
  lastW = img.naturalWidth;
  if (native) {
    img.classList.remove('fit');
    img.style.width = (img.naturalWidth / window.devicePixelRatio) + 'px';
    say('1:1 pixel-exact');
  } else {
    img.classList.add('fit');
    img.style.width = '';
    say('fit to screen');
  }
}
function say(t) {
  tag.textContent = t + ' -- tap to switch';
  tag.classList.add('show');
  clearTimeout(say.t);
  say.t = setTimeout(() => tag.classList.remove('show'), 1800);
}
addEventListener('click', () => { native = !native; apply(); });
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

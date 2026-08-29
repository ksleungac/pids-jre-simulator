# SPDX-License-Identifier: MIT
"""Mirror the app's window to a browser over HTTP, and take taps back.

Serves whatever is currently on the PC screen — setup flow, tutorial, drive —
as an MJPEG-style ``multipart/x-mixed-replace`` stream of PNG frames. The
client is a plain ``<img>``; no JavaScript on the display path.

Design decisions + rejected alternatives live in ``docs/APP.md`` § "Window mirroring".
Summary of the load-bearing ones:

- **PNG, not JPEG.** Measured on this app's AA-off content: PNG is 4x smaller
  than JPEG *and* pixel-exact, where JPEG damages ~7% of subpixels. LCD content
  (flat fills, sharp glyphs) is JPEG's worst case.
- **Zero new dependencies.** stdlib ``http.server`` + pygame's own PNG writer.
  If this design ever needs a dep, re-examine the design (critical_lessons 3).
- **Off by default.** Turned on in the TIMS 設定 page, which persists a mode
  (``off`` / ``local`` / ``lan``) that ``main.py`` reads at launch.
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
import ipaddress
import json
import select
import socket
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs

import pygame

# The page dresses its controls as TIMS bevel buttons; the palette is read, never restated.
# Safe at module scope: `tims/__init__` deliberately re-exports nothing and `tims.widgets` imports
# only stdlib + pygame, so this cannot close a cycle with `tims.band`, which imports this module.
from tims.widgets import _TUNEABLES_TIMS_BUTTON

DEFAULT_PORT = 8541
FPS = 15  # stream pacing; the LCD is mostly static so this is ample
MAX_CLIENTS = 3  # browsers routinely open a speculative 2nd connection, so >1
# A stream handler must not be able to sit in a blocked write forever. Switching view re-points the
# page's <img>, which ABANDONS the request; the browser may leave the socket open, so the server
# writes into a buffer nobody drains, fills it, and blocks in `wfile.write` — never reaching the
# `finally` that releases its MAX_CLIENTS slot. Three switches then exhaust the cap and every
# stream after that is refused with 503, which the browser draws as a broken-image icon. Measured
# 2026-08-29: swaps 1-3 returned 200 and swap 4 onward 503, with `_clients` pinned at 3.
STREAM_WRITE_TIMEOUT = 2.0  # seconds; a live client drains a ~4 KB frame in microseconds
BOUNDARY = "pidsframe"

# NOTE: deliberately has NO reader. `install_display_quit_guard` takes this across
# `pygame.display.quit`, and nothing else acquires it — capture moved to `_publish` on the MAIN
# thread (see the CONTRACT at the top of this file), so no server thread touches the display
# surface and the read-after-free race it was built for is already closed (D14).
# Kept because the NEXT teardown site is the one that would race, and the guard is what makes
# forgetting impossible. Wire a reader in if anything ever reads the display surface off-thread.
_lock = threading.Lock()
# Live /stream handlers, oldest first, each with the Event that ends its loop. A deque rather than
# a counter because MAX_CLIENTS is enforced by EVICTION, not refusal — see `_admit`.
_streams: "deque[threading.Event]" = deque()
# When each live handler last got a frame out. Keyed on the handler's OWN Event, which it holds for
# its whole life and `_retire` removes — not a side table on a recycled identity.
_last_write: "dict[threading.Event, float]" = {}
_clients_lock = threading.Lock()
_server: Optional[ThreadingHTTPServer] = None
# The addresses `start` bound and printed, kept so the UI can show them too. `start` returns
# them as well; a caller that only wants to DISPLAY the feature's state should not have to have
# been the one that turned it on (`tims.band` renders them on every setup screen).
_urls: "list[str]" = []
# Every address this server is actually reachable at, captured at bind time — the Host allow-list.
# Distinct from `_urls`, which is the shortlist the UI OFFERS: a 0.0.0.0 bind listens on interfaces
# `lan_candidates` deliberately does not advertise, and a client arriving on one of those is
# legitimate. See `_allowed_hosts`.
_bound_hosts: "set[str]" = set()

# Published by the main thread on present (flip/update); COMPOSED and encoded
# lazily by the server thread, per view. `_seq` lets the encoder skip work on an
# unchanged frame.
#
# Composition is deferred rather than done at publish because each viewer picks
# its own view (below): composing all three eagerly would do work nobody is
# watching, on the render thread. Both sources are copies, never the live display
# Surface, so a server thread may blit them — the contract at the top of this
# file is about the DISPLAY surface, which only `_publish` touches.
_main: Optional[pygame.Surface] = None
_side: Optional[pygame.Surface] = None
_seq = 0
_png: "dict[str, bytes]" = {}  # per view, valid at _png_seq
_png_seq: "dict[str, int]" = {}

# What a viewer can ask to see. Chosen per CONNECTION (`/stream?view=`) rather
# than as a server setting: two people on two devices legitimately want
# different things, and a query parameter is per-client by construction with no
# shared state and no new write endpoint. The cost is that switching drops and
# re-opens the stream, which the page's existing reconnect already handles.
VIEWS = ("both", "main", "side")
DEFAULT_VIEW = "both"

# A second view docked beside the main window's, published by the main thread
# alongside it. Today that is the departure-bell box, which is a real second OS
# window on the PC and so has no frame of its own to publish.
#
# CONTRACT: the stream shows what the PC shows. Docking a view in here is only
# legitimate because the PC really is displaying it, in its own window — this is
# mirroring both windows, not compositing a remote-only control. The page's
# 1:1/FIT button is deliberately browser chrome for exactly that reason; a
# control drawn into the frame would be visible on the PC too, or would make the
# stream diverge from it. So a view that closes on the PC must leave here as
# well: the caller publishes None and the dock disappears.
#
# The per-viewer VIEWS above do not weaken that: choosing to look at one of the
# PC's windows is not the same as inventing something the PC is not showing.
SIDE_GAP = 8  # px between the two views, in frame pixels
# The gutter behind them. Matches the page background so the dock reads as two
# panes on one surface rather than a box floating on grey.
_BG = (10, 13, 18)

# Taps arrive on server threads and are replayed on the MAIN thread by the
# present hook. Same shape as the OCR driver's `pending_next_pa`: the background
# side only records, the main side acts. A deque rather than a single slot so a
# quick second tap is not swallowed by the one before it; bounded so a wedged
# main loop cannot grow it without limit.
_taps: "deque[tuple[float, float, str]]" = deque(maxlen=8)
_taps_lock = threading.Lock()


def _allowed_hosts() -> set:
    """Host-header values this server answers to: loopback names plus the addresses it BOUND.

    Bound, not displayable. `lan_candidates()` answers "what should we show the user", and
    `_is_usable_lan` deliberately narrows that to private ranges — but a `lan` bind takes 0.0.0.0,
    i.e. every interface, so the two sets can differ. On a machine whose only routable address is
    public (bridge-mode modem, no NAT router — the configuration this was found on), the mirror
    really is reachable at an address `lan_candidates()` refuses to list, and deriving the
    allow-list from the display list refused that client's taps with 421 while still serving it
    video. `_bound_hosts` is captured in `start` from the interfaces actually listening.

    Recomputing per request also cost a `getaddrinfo(gethostname())` on every POST.
    """
    return {"localhost", "127.0.0.1", "::1", *(h.lower() for h in _bound_hosts)}


# How far the mirror reaches. A TRI-STATE, not two booleans: the three are mutually exclusive by
# nature, and the two launch flags are a 4-cell truth table with a duplicate cell (both set = lan).
# The settings page shows exactly these three, so this is the shape the user picks from and the
# shape that is persisted; the flags resolve INTO it rather than beside it, so there is one
# decision (`principles.md` § "A second implementation of a production decision drifts silently").
MODES = ("off", "local", "lan")
# A fresh install mirrors to LOOPBACK. It costs nothing a user would notice — a 127.0.0.1 socket is
# unreachable from the network, so Windows raises no firewall prompt — and it buys the second-window
# case (a browser on this PC, freely resizable) without anyone having to discover a setting first.
# `lan` stays opt-in precisely because it does not have that property: it is the bind that prompts,
# and it is the one that lets another device drive the app.
DEFAULT_MODE = "local"


def bind_host_for(mode: str) -> Optional[str]:
    """Bind address for a mirror mode, or None when it is off. The ONE place a mode becomes an address.

    ``local`` (127.0.0.1) serves a browser on this PC with zero network exposure and NO Windows
    firewall prompt — a loopback socket is unreachable from the network, so there is nothing for
    Defender to ask about. ``lan`` (0.0.0.0) is what a phone or tablet needs, and it is the bind
    that raises the prompt. That asymmetry is the whole reason these are separate positions.
    """
    if mode == "lan":
        return "0.0.0.0"
    if mode == "local":
        return "127.0.0.1"
    return None


def clean_mode(raw) -> str:
    """A mode from settings.json, or the default. Never raises, never trusts a persisted value."""
    return raw if raw in MODES else DEFAULT_MODE


# The range the settings page steps over. Here rather than there because `main.py` binds the value
# at launch, long before that page could clamp it — one owner for the range and for the reading.
PORT_MIN, PORT_MAX = 8500, 8599


def clean_port(raw) -> int:
    """A port from settings.json, clamped to the offered range. Never raises — same contract as
    `clean_mode`, for the same reason.

    Three readers had three behaviours: the settings page guarded its own read, `main.py` did not,
    and `start` caught only `OSError`. `"stream_port": 99999` therefore raised an uncaught
    `OverflowError` out of `bind()` and killed the app BEFORE any window existed — so the user
    could not reach the page that would have fixed it. A value outside the range was also bound
    raw while the page displayed the clamped one.
    """
    try:
        return min(PORT_MAX, max(PORT_MIN, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_PORT


def resolve_bind_host(saved=None) -> Optional[str]:
    """The saved setting as a bind address, or None when mirroring is off. Pure — the test seam.

    There were launch flags here (`--stream` / `--stream-lan`) and they are gone: the TIMS 設定
    page is the switch now, and a second way to set the same thing is a second answer to one
    question. The settings value is the only input, which is why an unrecognised one must land on
    the default rather than anywhere wider (see `clean_mode`).
    """
    return bind_host_for(clean_mode(saved))


def _is_usable_lan(ip: str) -> bool:
    """True for an address a phone on the same local network could plausibly reach.

    PRIVATE ranges only (RFC 1918 and friends, via ``ipaddress.is_private``), minus loopback and
    APIPA/link-local — 169.254.x means an adapter that failed DHCP, which sits on every idle
    virtual NIC and is never routable.

    Excluding PUBLIC addresses is the load-bearing part, and it is not a tidy-up. A machine whose
    Ethernet takes a public address by DHCP (no NAT router — an ordinary setup with a modem in
    bridge mode) had that address enumerated and drawn on the status band as a "connect here"
    target: useless, since no phone reaches it from another network, and a real leak, because this
    window gets screenshotted and streamed. Observed 2026-08-29 on the author's own machine, which
    offered its public IP alongside a VPN tunnel and no private address at all.

    A malformed value is not usable — the caller collects these from the OS, but `ipaddress` is
    strict and a non-address must not take the enumeration down.
    """
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private and not (a.is_loopback or a.is_link_local)


def _all_local_addresses() -> "list[str]":
    """Every IPv4 address bound to this host, unfiltered — the Host allow-list's raw material.

    Deliberately NOT `lan_candidates()`: that one narrows to what is worth OFFERING a user, and a
    0.0.0.0 bind answers on everything regardless. Filtering here would reject a real client.
    """
    try:
        return [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        return []


def _default_route_address() -> Optional[str]:
    """The local address a packet to the internet would leave by, or None.

    A UDP connect sends nothing — it only makes the OS pick a route — so this costs no traffic.
    Split out from `lan_candidates` so the discovery sources are seams a test can stand in for;
    otherwise the ordering could only be checked by re-implementing the sort, which is the
    second-implementation trap.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _own_names() -> "list[str]":
    """This machine's own host names, lower-cased — Host values a client may legitimately arrive by.

    A phone on the LAN often reaches a PC by name or by its mDNS `.local` form rather than by the
    printed IP, and the Host gate covers the READ endpoints now, so refusing those serves a blank
    page instead of the mirror.
    """
    try:
        name = socket.gethostname().lower()
    except OSError:
        return []
    return [name, f"{name}.local"] if not name.endswith(".local") else [name]


def _lan_rank(ip: str) -> int:
    """Sort key for `lan_candidates`: home-router ranges first, VPN-ish ranges last. Stable, so
    two addresses in the same range keep the order they were discovered in."""
    if ip.startswith("192.168."):
        return 0
    if ip.startswith("172."):
        return 1
    return 2  # 10/8 — a real LAN sometimes, a tunnel more often


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
    route = _default_route_address()
    if route is not None and _is_usable_lan(route):
        found.append(route)

    # Then everything else bound to this host.
    for ip in _all_local_addresses():
        if _is_usable_lan(ip) and ip not in found:
            found.append(ip)

    # Order by how likely the range is to be the Wi-Fi a phone is on, rather than by discovery.
    # The default-route probe above finds the tunnel first whenever a VPN is up — measured on the
    # author's machine, which offered NordLynx's 10.5.0.2 ahead of the real 192.168.0.104. 192.168/16
    # is the home-router default; 10/8 is where WireGuard and corporate VPNs land, so it goes last.
    # Nothing is hidden — every candidate is still offered, this only decides which is read first.
    return sorted(found, key=_lan_rank) or ["127.0.0.1"]


def install_display_quit_guard() -> None:
    """Wrap ``pygame.display.quit`` so every teardown holds ``_lock`` — which today no reader takes.

    See the NOTE on `_lock`: this is reserved scaffolding, not a live protection.

    Same one-seam idiom as ``window_utils.install_topmost_hook``: there are two
    teardown sites (``main.py`` setup->drive, ``app.py`` cleanup on home-return)
    and new ones would be easy to add without remembering to guard them. Hooking
    the call itself is regression-proof; scattering the guard is what rots.
    Idempotent.
    """
    if _already_wrapped(pygame.display.quit, "_stream_wrapped"):
        return
    _orig = pygame.display.quit

    def _quit(*args, **kwargs):
        with _lock:
            return _orig(*args, **kwargs)

    _quit._stream_wrapped = True
    _quit._orig = _orig  # same scheme as the present hook: the chain must stay walkable
    pygame.display.quit = _quit


def set_side_view(surf: Optional[pygame.Surface]) -> None:
    """Publish (or withdraw) the view docked beside the main window's.

    Main thread only, same as everything else that writes ``_main``. Pass None
    when there is nothing to dock — no second window, or the user closed it —
    and the next frame is the main window alone.
    """
    global _side
    _side = surf


def compose(
    main_surf: Optional[pygame.Surface], side_surf: Optional[pygame.Surface], view: str = DEFAULT_VIEW
) -> "tuple[Optional[pygame.Surface], Optional[pygame.Rect]]":
    """Build the frame for ``view``; return it and where the dock landed in it.

    The rect is what resolves a tap, so the layout and the hit-routing cannot
    disagree — they are the same arithmetic, returned together from here
    (`principles.md` § "A second implementation of a production decision drifts
    silently"). A caller that only wants the geometry still gets it by asking
    for the frame.

    Degrades rather than refuses: a viewer asking for the docked view when
    nothing is docked — the box closed, or a setup screen with no second window
    — gets the main view instead of an empty frame. That is what the PC is
    showing, which is the rule this file is built on.

    Neither surface is copied here, and the two are safe to blit off-thread for DIFFERENT reasons:
    `_main` because `_publish` stored a copy, `_side` because its producer REBINDS rather than
    redraws (`bell_window.update` renders a fresh Surface on each state change). The second is a
    cross-module invariant, so it is named at both ends — see the CONTRACT on
    `bell_window.surface()`. An in-place redraw there for perf would tear the docked view, which
    is the same mid-draw sampling the `_publish` CONTRACT exists to prevent.
    """
    if view == "side" and side_surf is not None:
        return side_surf, pygame.Rect(0, 0, *side_surf.get_size())
    if main_surf is None:
        return None, None
    if view != "both" or side_surf is None:
        return main_surf, None
    mw, mh = main_surf.get_size()
    sw, sh = side_surf.get_size()
    frame = pygame.Surface((mw + SIDE_GAP + sw, max(mh, sh)))
    frame.fill(_BG)
    frame.blit(main_surf, (0, 0))
    rect = pygame.Rect(mw + SIDE_GAP, 0, sw, sh)
    frame.blit(side_surf, rect.topleft)
    return frame, rect


def frame_for(view: str) -> "tuple[Optional[pygame.Surface], Optional[pygame.Rect]]":
    """`compose` against whatever was last published. One reader for the encoder
    and the tap router, so a tap always resolves against the frame its viewer got."""
    return compose(_main, _side, view)


def clean_view(raw) -> str:
    """A view name from the wire, or the default. Never raises, never trusts."""
    return raw if raw in VIEWS else DEFAULT_VIEW


def has_side() -> bool:
    """Whether a second view is currently docked. Read by `/views` so the page
    can offer the choice only while there is one to make."""
    return _side is not None


def urls() -> "list[str]":
    """Every address the running server can be reached on; empty when mirroring is off.

    A COPY, so a caller cannot mutate what `start` recorded. Empty is the honest answer for both
    "never started" and "the bind failed" — in each case there is nothing to open, which is all a
    display surface needs to know.
    """
    return list(_urls)


def tap_target(view: str, has_dock: bool) -> Optional[str]:
    """Which view a tap should resolve against, or None to DROP it.

    # CONTRACT: a tap for a view that is not there must MISS, never land
    # somewhere else. Showing the main view as a fallback is a kindness — a
    # frame beats a broken <img>. RESOLVING a tap against that fallback is not:
    # the finger was aimed at a box that is not on screen, and re-aiming it
    # turns a miss into a press on whatever occupies that point. Measured
    # 2026-08-23 on the setup menu: a tap at the ON cap's position resolved to
    # (365, 256) of the 730x610 setup screen, which is inside a TIMS button.
    #
    # A miss is the correct outcome and the one a real mouse gives — the same
    # reasoning as `_drain_taps`' note on a tap arriving across a screen change.
    """
    if view == "side" and not has_dock:
        return None
    return view


def _forget_frames() -> None:
    """Drop everything captured from the last session. Called by `stop`."""
    global _main, _side, _seq
    _main = _side = None
    _seq += 1  # invalidate the per-view PNG cache rather than trusting it to be re-keyed
    _png.clear()
    _png_seq.clear()


def _publish() -> None:
    """Capture the just-presented frame. Runs on the MAIN thread, from the
    flip/update hook — never from a server thread.

    No server, no capture. D7 justified publishing unconditionally on the grounds that the cost was
    "bounded by the feature being off by default"; `DEFAULT_MODE = "local"` retired that premise, so
    a user who turns mirroring OFF would otherwise keep paying a full-window copy (0.37 ms) on every
    present, forever, for nobody (`principles.md` § "A simplification must carry its constraints
    forward"). One attribute read replaces the copy.

    # CONTRACT: capture on present, never asynchronously.
    # Reading pygame.display.get_surface() from the server thread samples the
    # surface MID-DRAW — between a renderer's clear and its redraw — so the
    # client sees half-drawn frames as flicker. It is invisible in the app
    # window, which only ever shows completed frames via flip(). Observed
    # 2026-07-20 as "lower LCD elements flashing", worst on e235_0 transfer
    # pages: the most elements to redraw = the widest window to catch torn.
    # Capturing here means every published frame is one the user actually saw.
    """
    global _main, _seq
    if _server is None:
        return  # mirroring is off — nothing to publish to
    surf = pygame.display.get_surface()
    if surf is None:
        return
    _main = surf.copy()  # ~0.4ms; never mutated after publish, so no lock needed
    _seq += 1


def _snapshot(view: str = DEFAULT_VIEW) -> Optional[bytes]:
    """Compose and encode the latest published frame for ``view``, as PNG. Runs
    on the server thread.

    Cached PER VIEW while the frame is unchanged, so a static display costs one
    compose+encode per view being WATCHED — not one per client per tick, and
    nothing at all for a view nobody asked for.
    """
    seq = _seq  # read once; a torn pair against the surfaces costs one stale tick
    if _png_seq.get(view) == seq:
        return _png.get(view)
    frame, _rect = frame_for(view)
    if frame is None:
        return _png.get(view)  # nothing published yet; serve the last one if there is one
    buf = io.BytesIO()
    pygame.image.save(frame, buf, "frame.png")
    _png[view], _png_seq[view] = buf.getvalue(), seq
    return _png[view]


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


def queue_tap(fx: float, fy: float, view: str = DEFAULT_VIEW) -> None:
    """Record a normalised tap and WHICH VIEW it was normalised against. Runs on
    a SERVER thread -- records only, never acts.

    The view travels with the tap because viewers differ: a fraction of the
    docked-only view is a completely different point in the both view, and the
    server has no other way to know which frame the finger was on.
    """
    with _taps_lock:
        _taps.append((fx, fy, clean_view(view)))


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
    # Drained BEFORE this frame is published, deliberately: `_main` is the frame
    # BEFORE the one about to go out, so a tap arriving on the same present as a
    # screen change resolves against the size the client last saw rather than the
    # one it has not received yet. That is one present of slack (~33 ms), not a
    # guarantee about the frame the remote was actually looking at, which is
    # older by the stream pacing plus the network plus human reaction. Correctness
    # does not rest on it: a stale tap misses, exactly as a real mouse click does
    # during a screen transition.
    for fx, fy, view in pending:
        view = tap_target(view, has_side())
        if view is None:
            continue  # aimed at a view that is not on screen — a miss, not a re-aim
        frame, side = frame_for(view)
        if frame is None:
            continue  # nothing published yet; a tap has no frame to be relative to
        w, h = frame.get_size()
        pt = frame_point(fx, fy, w, h)
        if pt is None:
            continue
        pygame.event.post(tap_event(pt, side))


def tap_event(pt, side: Optional[pygame.Rect]) -> pygame.event.Event:
    """The synthetic click for a frame-space point: which view it belongs to, and
    that view's own coordinates.

    A tap in the dock carries ``side_view=True`` and coordinates relative to the
    DOCK, not the frame — so the consumer works in the docked view's own space
    and never has to know where the dock was placed. A tap anywhere else is
    exactly the event this file has always posted, unmarked, in main-window
    coordinates.

    Split out from `_drain_taps` because this is the whole of the routing
    decision and it is worth testing without a display, a server or a queue.
    """
    if side is not None and side.collidepoint(pt):
        return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(pt[0] - side.x, pt[1] - side.y), button=1, side_view=True)
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pt, button=1)


_reported: "set[str]" = set()


def _guarded(fn, what: str) -> None:
    """Run ``fn``; on failure print the traceback ONCE for ``what``, then stay quiet.

    Mirroring must never break the app's render loop, but a guard that has never spoken has not
    been shown to run: the thing a silent swallow hides is usually a bug in the guarded call
    itself, and at 15 Hz an unconditional `pass` hides it forever.
    """
    try:
        fn()
    except Exception:  # noqa: BLE001 - the render loop outranks any of this
        if what not in _reported:
            _reported.add(what)
            print(f"Warning: {what} failed and is now suppressed for this session:")
            traceback.print_exc()


def _already_wrapped(fn, marker: str) -> bool:
    """Whether ``marker`` appears ANYWHERE in a wrapper chain, not merely on its outermost link.

    Every hook here and in `tims.band` replaces `pygame.display.flip`/`update` with a closure that
    carries `_orig`. Asking only about the top function makes idempotence depend on install ORDER —
    whoever wrapped last hides everyone beneath, and the next install stacks a duplicate layer.
    """
    seen = 0
    while fn is not None and seen < 16:  # bounded: a cycle here would hang the app at import
        if getattr(fn, marker, False):
            return True
        fn = getattr(fn, "_orig", None)
        seen += 1
    return False


def install_present_hook() -> None:
    """Wrap ``pygame.display.flip`` / ``update`` so each completed frame is
    captured. One seam — flip/update are called from 18 files and a new screen
    must not have to remember to publish. Idempotent.
    """
    for name in ("flip", "update"):
        orig = getattr(pygame.display, name)
        # Walk the CHAIN, not just the outermost. Reading the top function only asks "is the
        # outermost wrapper mine?", so anything that wraps on top of us — `band.install_overlay_hook`
        # deliberately marks nothing — hides us and the next call stacks a second publish layer,
        # costing an extra full-window copy per present forever. The wrappers carry `_orig`, so the
        # chain is walkable and the answer becomes order-independent.
        if _already_wrapped(orig, "_stream_wrapped"):
            continue

        def _wrapped(*args, _orig=orig, **kwargs):
            r = _orig(*args, **kwargs)
            # Separate guards: the tap half is the newer, optional one, and a fault
            # in it must not stop the display half from publishing. Sharing a
            # try/except would freeze the browser on a cached frame with nothing
            # logged anywhere (`principles.md` § "A bonus feature ... is not a bonus").
            # Each REPORTS ONCE — a blanket swallow on a 15 Hz call is how the bell window's
            # topmost re-pin silently stopped working for a whole session behind a NameError
            # (`conventions.md` § UI code style).
            _guarded(_drain_taps, "the streamed tap queue")
            _guarded(_publish, "the streamed frame capture")
            return r

        _wrapped._stream_wrapped = True
        _wrapped._orig = orig  # the link _already_wrapped walks
        setattr(pygame.display, name, _wrapped)


def _rgb(c) -> str:
    return "rgb(%d,%d,%d)" % tuple(c[:3])


def _page_prelude() -> str:
    """The values `_PAGE` must not restate: the TIMS button palette, the gutter colour, the view ids.

    The page dresses its controls as TIMS bevel buttons, and nine RGB literals spelling that out in
    CSS is `conventions.md` § Tooling's canonical-source duplication — correct the day it is typed
    and silently forked by the next hand-nudge of `_TUNEABLES_TIMS_BUTTON`, under a comment claiming
    the two match. Injected as CSS custom properties rather than formatted into `_PAGE`, because the
    page is full of literal `{}` in CSS and JS and `%` in `100%`, so every templating syntax would
    need escaping throughout — a var block needs none.

    The view IDS come across the same way: the JS array restated the Python `VIEWS` tuple, and a
    drift there is silent (`clean_view` falls back to the default, so the lit cell and the served
    view simply disagree). Only the human-readable labels stay client-side.
    """
    t = _TUNEABLES_TIMS_BUTTON
    return (
        "<style>:root{"
        f"--page-bg:{_rgb(_BG)};"
        # The caption scrim, derived from the same tuple. As `color-mix()` it needed Chrome 111 /
        # Safari 16.2, and an older tablet — which D12 says is the target — would drop the whole
        # declaration and lose the scrim. rgba() has no such floor and is just as derived.
        f"--page-bg-80:rgba({_BG[0]},{_BG[1]},{_BG[2]},.8);"
        f"--btn-edge:{_rgb(t['outer_border_color'])};"
        f"--btn-hi:{_rgb(t['bezel_hi_color'])};"
        f"--btn-lo:{_rgb(t['bezel_lo_color'])};"
        f"--btn-top:{_rgb(t['face_top_color'])};"
        f"--btn-bot:{_rgb(t['face_bottom_color'])};"
        f"--btn-ink:{_rgb(t['text_color'])};"
        f"--btn-hi-on:{_rgb(t['bezel_hi_pressed_color'])};"
        f"--btn-lo-on:{_rgb(t['bezel_lo_pressed_color'])};"
        f"--btn-top-on:{_rgb(t['face_top_pressed_color'])};"
        f"--btn-bot-on:{_rgb(t['face_bottom_pressed_color'])};"
        f"--btn-ink-on:{_rgb(t['text_dark_color'])};"
        "}</style>"
        f"<script>const VIEW_IDS={json.dumps(list(VIEWS))};</script>"
    )


_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PA Simulator</title>
<!--PRELUDE-->
<style>
  html,body{margin:0;height:100%;background:var(--page-bg);overflow:hidden}
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
       background:var(--page-bg-80);opacity:0;transition:opacity .25s}
  #tag.show{opacity:1}
  /* The controls are their OWN buttons, not gestures on the image: a tap on the
     image now means "click the thing under my finger", so a whole-page gesture
     would fight every button in the app. Deliberately browser chrome rather
     than pygame-drawn -- a control drawn into the frame would either appear on
     the PC window too, or make the stream a composited view that no longer
     matches what the PC shows.
     Browser chrome does NOT have to look like a web page. These are dressed as
     TIMS bevel buttons, with every colour read off
     `tims/widgets.py::_TUNEABLES_TIMS_BUTTON` rather than invented, so the
     controls belong to the same console as the picture above them. */
  button.ctl{-webkit-appearance:none;appearance:none;cursor:pointer;
        border:1px solid var(--btn-edge);        /* outer_border_color */
        border-top-color:var(--btn-hi);          /* bezel_hi_color -- lit crest, top + left */
        border-left-color:var(--btn-hi);
        border-bottom-color:var(--btn-lo);       /* bezel_lo_color -- shadow, bottom + right */
        border-right-color:var(--btn-lo);
        background:linear-gradient(var(--btn-top),var(--btn-bot));  /* face_top/bottom_color */
        color:var(--btn-ink);                    /* text_color */
        font:600 12px system-ui,sans-serif;letter-spacing:.08em;
        padding:9px 12px;min-width:56px;border-radius:4px}
  /* Selected = the TIMS "pressed" palette: the WHOLE button goes yellow, bevel
     included, and the ink flips dark for contrast. The same idiom as the
     存取範圍 cells on the settings page, so a picked view reads the way a
     picked anything reads in this app. */
  button.ctl.on{background:linear-gradient(var(--btn-top-on),var(--btn-bot-on));
        border-top-color:var(--btn-hi-on);border-left-color:var(--btn-hi-on);
        border-bottom-color:var(--btn-lo-on);border-right-color:var(--btn-lo-on);
        color:var(--btn-ink-on)}
  #bar{position:fixed;bottom:10px;right:10px;z-index:2;display:flex;gap:10px}
  /* The three views are a SEGMENTED row with the current one lit, not one button
     cycling through them. Cycling forced the label to name the NEXT view while
     you were looking at the current one, which is a puzzle rather than a control:
     press BELL, get the bell, and the button then reads PIDS. Three cells show
     every option AND where you are, in one glance and one tap.
     Hidden entirely until the app has a second window -- see refreshViews(). */
  #view{display:none;gap:2px}
  #view button:not(:first-child){border-top-left-radius:0;border-bottom-left-radius:0}
  #view button:not(:last-child){border-top-right-radius:0;border-bottom-right-radius:0}
</style>
<img id="v" src="/stream" alt="PA Simulator">
<div id="bar">
  <div id="view"></div>
  <button id="zoom" class="ctl" type="button">1:1</button>
</div>
<div id="tag"></div>
<script>
// Display path works without this -- the <img> above renders on its own.
// JS only adds the 1:1 mode and the reconnect nudge.
const img = document.getElementById('v'), tag = document.getElementById('tag'),
      zoom = document.getElementById('zoom'), viewBtn = document.getElementById('view');

// --- which of the PC's windows to look at ----------------------------------
// The app can put two windows on screen -- the PIDS itself, and the departure
// bell box in its own window -- and the stream carries both side by side. On a
// phone that shrinks the PIDS to make room, so this cycles through looking at
// one of them full-size instead.
//
// The choice is a query parameter on the stream, NOT a POST: it is a read, so
// it adds no write endpoint, and it is per-connection so two devices can watch
// different things. Switching re-points the <img>, which drops and re-opens the
// stream -- one brief reconnect, which the error handler above already covers.
//
// Labels name today's only docked view. The mechanism is generic; the copy is
// not, because "SIDE VIEW" would tell the reader nothing.
//
// Each entry describes ITSELF, and every one gets its own cell -- the current
// cell is lit, so the control shows both the options and where you are.
// The IDS come from Python (VIEW_IDS, injected by _page_prelude) so the wire values cannot drift;
// only the labels below are client-side copy. Order is the server's.
const LABELS = {both: ['BOTH', 'PIDS and bell'], side: ['BELL', 'bell only'], main: ['PIDS', 'PIDS only']};
const VIEWS = VIEW_IDS.map(id => ({id: id, name: (LABELS[id] || [id, id])[0], say: (LABELS[id] || [id, id])[1]}));
let vi = 0;
function streamSrc() { return '/stream?view=' + VIEWS[vi].id + '&r=' + Date.now(); }

const cells = VIEWS.map((v, i) => {
  const b = document.createElement('button');
  b.className = 'ctl';
  b.type = 'button';
  b.textContent = v.name;
  b.addEventListener('click', () => { if (i !== vi) { vi = i; paint(); say(v.say); show(); } });
  viewBtn.appendChild(b);
  return b;
});
function paint() { cells.forEach((b, i) => b.classList.toggle('on', i === vi)); }
paint();

// ONE place that re-points the <img>, and ONE pending retry at a time.
//
// Both halves matter. Assigning `src` ABORTS the in-flight multipart request, and an aborted
// <img> load fires `error` -- indistinguishable from the stream actually dying. The old handler
// was an inline `onerror` that scheduled a reload 1s later with no timer handle, so every switch
// left a retry pending: three quick switches stacked three of them, each re-pointing `src`, each
// aborting the last, each firing `error` again. It compounded, which is why switching worked at
// first and broke after a few. Now a switch cancels any pending retry, and a retry can never
// queue behind another. (2026-08-29, reported as the toggle breaking on the way back to BOTH.)
let retry = 0;
function show() {
  clearTimeout(retry);
  retry = 0;
  lastW = 0;                    // the frame changes size per view, so re-apply the zoom on load
  img.src = streamSrc();
}
img.addEventListener('error', () => {
  if (retry) return;            // one in flight is enough; never build a queue of them
  retry = setTimeout(show, 1000);
});

// The control only exists while the app has a second window to choose between.
// On the setup menu there is one window, so all three views are the same picture
// and the button is a no-op that LOOKS broken -- pressing BELL there served the
// setup screen. Worse, a tap in that state used to be re-aimed at the screen
// underneath and could press a real setup button; the server drops those now,
// and this stops the user being offered the state at all.
//
// Polled rather than pushed: an <img> stream carries no side channel, and the
// transition this tracks (setup -> drive) is human-paced, so 2s is ample.
let hasDock = null;
function refreshViews() {
  fetch('/views').then(r => r.json()).then(s => {
    if (s.side === hasDock) return;
    hasDock = s.side;
    // 'flex', not '': the hidden state is a STYLESHEET rule (`#view{display:none}`), so clearing
    // the inline style falls back to that rule and the control stays hidden forever. It looked
    // right and could never appear -- 2026-08-29, reported as "the bell toggle is not shown".
    viewBtn.style.display = hasDock ? 'flex' : 'none';
    if (!hasDock && VIEWS[vi].id !== 'both') {
      vi = 0;                   // the view we were on is gone; fall back visibly
      paint();
      show();
    }
  }).catch(() => {});           // server gone: leave the control as it is
}
refreshViews();
setInterval(refreshViews, 2000);
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
      y: (e.clientY - r.top) / r.height,
      // Which frame the finger was on. A fraction of the bell-only view is a
      // different point entirely in the both view, and the server has no other
      // way to tell them apart.
      view: VIEWS[vi].id
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


def _admit() -> threading.Event:
    """Register a new /stream handler, evicting the STALEST if that puts us over MAX_CLIENTS.

    # CONTRACT: a new stream request always succeeds. The cap bounds concurrent writers; it must
    # never refuse the request the user just made.
    #
    # Refusing was the original behaviour and it is the wrong end to give way. Switching view
    # re-points the page's <img>, which abandons the previous request; a browser that leaves that
    # socket open is not noticed until its send buffer fills and the write times out — measured at
    # 8.5s. Three switches inside that window filled the cap and every later stream got 503, drawn
    # as a broken image.
    #
    # STALEST, not oldest. "Oldest == abandoned" holds for the view-switch case this was written
    # for and fails for two real devices: A watching (plus the speculative second connection every
    # browser opens) and B arriving would evict A's LIVE stream, whose page then retries and evicts
    # B's — the two ping-pong indefinitely.
    #
    # What the ranking actually measures is the last SUCCESSFUL WRITE, which lags abandonment by
    # one send buffer: for roughly the first second after a switch the abandoned socket still
    # accepts writes and looks as fresh as a live one, so the victim among them is arbitrary. That
    # is the best signal available on this side — `_peer_gone` is the fast path for a socket that
    # was actually closed — and the user-visible contract holds either way, because a live viewer
    # that loses the draw simply reconnects.
    """
    ev = threading.Event()
    with _clients_lock:
        _streams.append(ev)
        # Seed the clock NOW. A handler that has not written yet would otherwise rank as the
        # stalest thing here and evict ITSELF on the very admission that created it — which is the
        # one outcome the CONTRACT above forbids. Freshness starts at birth and decays.
        _last_write[ev] = time.monotonic()
        while len(_streams) > MAX_CLIENTS:
            victim = min(_streams, key=lambda e: _last_write.get(e, 0.0))
            _streams.remove(victim)
            _last_write.pop(victim, None)
            victim.set()
    return ev


def _note_write(ev: threading.Event) -> None:
    """Record that this handler just got a frame out — its liveness, for `_admit`'s ranking."""
    _last_write[ev] = time.monotonic()


def _retire(ev: threading.Event) -> None:
    """Drop a finished handler's registration. Safe to call for one already evicted."""
    with _clients_lock:
        try:
            _streams.remove(ev)
        except ValueError:
            pass  # already evicted by _admit
        _last_write.pop(ev, None)


def _peer_gone(conn) -> bool:
    """True once the client has hung up — checked WITHOUT blocking, before each frame is written.

    A closed peer makes the socket readable at EOF, so a zero-length peek is the signal. The peek
    is deliberate: a pipelined request would otherwise be consumed here and lost.

    This is the fast exit. It fires the instant a browser closes an aborted request, which is the
    common case when the view switches; the write timeout is the backstop for a client that
    abandons the request but leaves the socket open.
    """
    try:
        if not select.select([conn], [], [], 0)[0]:
            return False
        return conn.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return True  # unreadable socket: gone by any definition


class _Server(ThreadingHTTPServer):
    """Only difference from the stock server: an ordinary client hang-up is not an error.

    `socketserver` prints a full traceback per disconnect, and a phone reconnects on every
    screen-lock and network roam (D11), so the console fills with them — which is exactly when
    someone is reading it to debug something else. Anything that is NOT a disconnect still prints.
    """

    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Applied by `StreamRequestHandler.setup()` BEFORE the request line is read, which is the one
    # phase the in-body `settimeout` calls in `_send_stream` / `do_POST` cannot cover: a peer that
    # connects and then dribbles (or sends nothing) would otherwise park a thread for the life of
    # the process, and MAX_CLIENTS does not bound it because `_admit` is never reached. D11's
    # "explicit socket timeout" is what this completes. Generous, because it must not cut a slow
    # but real request short; the stream loop sets its own tighter one once it starts writing.
    timeout = STREAM_WRITE_TIMEOUT * 5

    def log_message(self, *a):  # silence per-request console spam
        pass

    def _view(self) -> str:
        """The view this request asked for. A READ parameter, so it adds no write
        surface — and being per-request makes it per-viewer with no server state.
        Anything unrecognised falls back to the default rather than erroring: a
        stale bookmark should still show the app."""
        _, _, query = self.path.partition("?")
        return clean_view(parse_qs(query).get("view", [None])[0])

    def _host_ok(self) -> bool:
        """Whether this request's Host names an address we actually bound.

        # CONTRACT: EVERY endpoint, read and write. The reads are not exempt.
        # A page in the user's own browser can point a short-TTL hostname at 127.0.0.1 and become
        # same-origin with this server (DNS rebinding); `GET /frame.png` then hands it the app's
        # screen, which it can draw to a canvas and read back. Gating only `/tap` left that open —
        # measured 2026-08-29, `Host: evil.example.com` on /frame.png returned 200 with the frame
        # while the same header on /tap correctly returned 421, and both `_allowed_hosts`' own
        # docstring and `conventions.md` § Tooling already claimed the reads were covered.
        #
        # An ABSENT Host fails. It was previously admitted (`if host and ...`), which made the gate
        # opt-out for any client that simply omits the header — HTTP/1.1 requires it, so nothing
        # legitimate does.
        """
        host = self.headers.get("Host", "").strip()
        if host.startswith("["):  # IPv6 literal: [::1]:8541 — the colons are part of the address
            host = host[1:].split("]", 1)[0]
        elif host.count(":") == 1:  # host:port. A bare IPv6 has several colons and no port.
            host = host.rsplit(":", 1)[0]
        return bool(host) and host.lower() in _allowed_hosts()

    def do_GET(self):
        if not self._host_ok():
            self.send_error(421, "unrecognised Host")
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_page()
        elif path == "/frame.png":
            self._send_single()
        elif path == "/stream":
            self._send_stream()
        elif path == "/views":
            self._send_views()
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._host_ok():
            self.send_error(421, "unrecognised Host")
            return
        if self.path.split("?", 1)[0] != "/tap":
            self.send_error(404)
            return
        # CONTRACT: /tap is the only WRITE endpoint — check the caller, not just the body.
        # Stage 1 was read-only, so D9's "loopback = zero network exposure" held on its own.
        # A tap drives the app, and any page in the user's browser can reach loopback: a
        # CORS-*simple* POST (text/plain) is sent with no preflight. Requiring
        # application/json forces a preflight, which this server answers with 501 (no
        # do_OPTIONS). The Host half now lives in `_host_ok`, shared with do_GET.
        # Media types are case-insensitive per RFC 9110, so the comparison is folded.
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self.send_error(415, "expected Content-Type: application/json")
            return
        try:
            # A client-declared Content-Length with no timeout parks this thread until the peer
            # closes — D11's connection hygiene applies to reads on this endpoint too, and did not
            # get carried over. A ~40-byte body has no honest reason to take seconds.
            self.connection.settimeout(STREAM_WRITE_TIMEOUT)
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > 256:  # a tap is ~40 bytes; anything else is not one
                raise ValueError("bad length")
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            # `view` is optional and validated by `clean_view`, so an older
            # client that does not send it still taps the default view.
            queue_tap(float(body["x"]), float(body["y"]), body.get("view"))
        except Exception:
            self.send_error(400, 'expected {"x": <0..1>, "y": <0..1>}')
            return
        # 204: the tap's effect arrives on the video stream, not in this reply.
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_page(self):
        # Substituted INTO the document, never prepended. Concatenating in front put a <style>
        # element ahead of <!doctype html>, which per the HTML tree-construction algorithm sets
        # quirks mode and makes the later doctype a parse error — measured, the doctype landed at
        # byte 393 and `document.compatMode` went CSS1Compat -> BackCompat. A single marker also
        # needs no brace escaping, which is why this is `.replace` and not `.format`.
        body = _PAGE.replace("<!--PRELUDE-->", _page_prelude()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_views(self):
        """Which views exist right now, so the page can offer only the real ones.

        A READ endpoint: it adds no write surface, so it carries no body gate. It is NOT exempt
        from the Host check — `do_GET` applies `_host_ok` to every path. This docstring used to
        claim the exemption, which is the reasoning that left the reads open to DNS rebinding in
        the first place, sitting at the one site a reader would consult before exempting another.
        """
        body = json.dumps({"side": has_side()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_single(self):
        """One-shot frame. Fallback for clients where multipart in an <img>
        misbehaves (historically iOS Safari) -- poll this instead."""
        png = _snapshot(self._view())
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
        evicted = _admit()
        try:
            # CONTRACT: this loop must always be able to END. It holds one of MAX_CLIENTS slots,
            # and the only thing that frees a slot is leaving here — so a write that can block
            # forever is a permanent leak, not a slow frame. THREE independent exits, because a
            # client goes away in three different ways: a clean abort closes the socket (caught by
            # `_peer_gone` on the next tick); an abandoned-but-open one stops READING, which only
            # surfaces once the buffer fills and the write times out, ~8.5s; and a newer request
            # for the same cap evicts this one immediately (`evicted`). The third exists because
            # the second is far too slow to keep up with someone tapping through views.
            self.connection.settimeout(STREAM_WRITE_TIMEOUT)
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            view = self._view()
            delay = 1.0 / FPS
            while not evicted.is_set():
                if _peer_gone(self.connection):
                    break
                png = _snapshot(view)
                if png is not None:
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/png\r\n")
                    self.wfile.write(f"Content-Length: {len(png)}\r\n\r\n".encode())
                    self.wfile.write(png)
                    self.wfile.write(b"\r\n")
                    _note_write(evicted)  # liveness, so _admit evicts the stalest and not this one
                # Mobile browsers reconnect on screen-lock / network roam; a
                # stale handler would otherwise block on write until an OS
                # timeout, leaking a thread per reconnect.
                if _stop.wait(delay):
                    break
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            pass  # ordinary client disconnect
        finally:
            _retire(evicted)


_stop = threading.Event()


def start(host: str, port: int = DEFAULT_PORT) -> Optional[list[str]]:
    """Start the streaming server on a daemon thread. Returns the URLs it can be
    reached on (see ``lan_candidates``), or None if the bind failed.

    # CONTRACT: bind failure must be LOUD.
    # A declined Windows Defender prompt or a blocked public-Wi-Fi profile
    # leaves a dead port. Swallowing that silently is the critical_lessons 2
    # silent-skip pathology -- the caller prints the failure.
    """
    # NOTE: `port` is taken as given. `clean_port` belongs at the SETTINGS boundary — the callers
    # that read a persisted value — not here: clamping inside the general API silently binds a
    # different port than the caller asked for, which is how this first broke T3 (it uses 8421 to
    # avoid colliding with a real running app, and got 8500).
    global _server, _urls, _bound_hosts
    install_display_quit_guard()
    install_present_hook()
    _stop.clear()  # `stop()` latches this; clearing HERE makes a bare stop()->start() work too,
    # rather than only the apply_mode path that happened to know about the latch. It is pacing now:
    # ending live streams is `stop()`'s per-handler `evicted` Events.
    # Both address sets are computed BEFORE the listener exists. Assigning them after would leave a
    # window — spanning a UDP connect and two getaddrinfo calls — in which the server accepts
    # requests with an empty allow-list and 421s a legitimate client.
    #
    # What the UI OFFERS (private only, best-first) vs what is REACHABLE. The allow-list must be a
    # SUPERSET of everything the server can be reached by, because the gate now covers reads: a
    # miss costs the whole page, not just the taps. So it unions three sources — the interfaces
    # enumerated, whatever the UI advertises (`lan_candidates` has a route probe `getaddrinfo`
    # does not, and would otherwise be advertising an address the gate refuses), and this machine's
    # own NAMES, since a client that reached us as `<hostname>` or `<hostname>.local` is legitimate.
    # None of that weakens the DNS-rebinding property: an attacker-controlled name is still absent.
    hosts = lan_candidates() if host == "0.0.0.0" else ["127.0.0.1"]
    # Note the bind address itself is NOT in the set for a LAN bind: no client can send
    # `Host: 0.0.0.0` meaningfully, so it would be dead weight inside a security gate.
    _bound_hosts = {*_all_local_addresses(), *hosts, *_own_names()} if host == "0.0.0.0" else {host}
    try:
        _server = _Server((host, port), _Handler)
    except (OSError, OverflowError, ValueError) as e:
        # OverflowError is NOT an OSError: `bind()` raises it for a port outside 0-65535, so an
        # `except OSError` alone turned "bind failure must be LOUD" into "bind failure is fatal"
        # and killed the app before any window existed. `clean_port` above makes that unreachable;
        # this stays as the backstop the CONTRACT actually promises.
        print(f"[stream] FAILED to bind {host}:{port} -- {e}")
        print("[stream] streaming is OFF for this session (firewall prompt declined, or port in use)")
        _bound_hosts = set()  # the allow-list must never outlive the listener it describes
        return None
    threading.Thread(target=_server.serve_forever, daemon=True, name="frame-stream").start()
    _urls = [f"http://{h}:{port}/" for h in hosts]
    return list(_urls)


def stop() -> None:
    """Shut the server down, end every live stream, and release the socket.

    # CONTRACT: ending the streams is PER-HANDLER, not via `_stop`.
    # `_stop` is one latch shared by every server generation, and `apply_mode` clears it to start
    # the next one — so a handler whose write cycle straddles that clear sees an unset event and
    # keeps mirroring, with no new server to evict it. Each handler already owns an `evicted` Event
    # from `_admit` and checks it at the top of its loop; setting all of them is deterministic where
    # the latch is a race. `_stop` stays, but only as pacing.
    """
    global _urls, _server, _bound_hosts
    with _clients_lock:
        for ev in _streams:
            ev.set()
        _streams.clear()
    _stop.set()
    _urls = []  # the addresses stop being reachable here, so nothing may still offer them
    if _server is not None:
        _server.shutdown()
        _server.server_close()  # release the port NOW, so an immediate re-bind on it succeeds
        _server = None
    # AFTER the listener is down. Clearing first left a window where the server was still accepting
    # and every request met an empty allow-list, so a legitimate in-flight one got 421.
    _bound_hosts = set()
    # Publishing is hooked into flip/update with no removal path, so `_publish` keeps running; it
    # now no-ops on `_server is None`. Drop what the last session captured rather than retaining a
    # copy of the user's screen after they turned mirroring off.
    _forget_frames()


def apply_mode(mode: str, port: int = DEFAULT_PORT) -> "list[str]":
    """Switch mirroring to ``mode`` right now; return the URLs it can be reached on ([] when off).

    What the TIMS 設定 page calls when the user commits. The alternative was a caption telling them
    to restart the app, which is a worse answer to the same question and would have had to be
    deleted the moment this landed.

    A bind address cannot be changed on a live socket, so this really is stop-then-start. The hooks
    ``start`` installs are idempotent, so re-entering costs nothing, and ``start`` itself clears the
    ``_stop`` latch — this function no longer needs to know the latch exists, which also makes a
    bare ``stop(); start(...)`` from anywhere else work rather than serving one frame and freezing.
    """
    stop()
    host = bind_host_for(clean_mode(mode))
    return (start(host, port) or []) if host is not None else []

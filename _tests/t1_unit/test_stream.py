# SPDX-License-Identifier: MIT
# TIER: T1 — window mirroring: exposure and touch, as pure decisions
"""T1 — window mirroring: the pure decisions behind exposure and touch.

Module scope is the FEATURE, not a function or an incident. Two decisions live
here because both are pure, both belong to mirroring, and both fail silently:

  1. WHO CAN REACH IT  — resolve_bind_host / clean_mode: saved setting -> bind address
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
    # (saved, expected). The launch flags are gone — the TIMS 設定 page is the only switch, so the
    # saved mode is the whole input. The unrecognised rows are the ones that matter: settings.json
    # is a hand-editable file read before any UI runs, and whatever is in it must never widen the
    # bind. `0.0.0.0` is reachable only from the one literal value that asks for it, which is the
    # invariant these rows exist to hold: not "the default is X" but "nothing but 'lan' opens the
    # machine to the network".
    ("off", None),
    ("local", "127.0.0.1"),  # loopback only — no firewall prompt, nothing reachable off this PC
    ("lan", "0.0.0.0"),  # the ONLY value that may bind past loopback
    (None, "127.0.0.1"),  # never configured -> the shipped default, which is loopback
    ("LAN", "127.0.0.1"),  # case-sensitive: not a mode, so the default — crucially NOT 0.0.0.0
    ("everywhere", "127.0.0.1"),  # garbage likewise falls to the default, never to a wider bind
    ("", "127.0.0.1"),
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


# Which addresses may be OFFERED as a connect target. The band draws these and the page opens
# them, so an address here is a claim that a phone on the local network can reach it.
#
# The public rows are the ones with teeth. A machine whose Ethernet takes a public address by DHCP
# (a modem in bridge mode, no NAT router) enumerated it and put it on the status band — useless as
# a LAN target, and a leak, since that window is screenshotted and streamed. Observed 2026-08-29.
LAN_FILTER_CASES = [
    ("192.168.1.42", True),  # the ordinary home-router case
    ("10.5.0.2", True),  # RFC1918 10/8 — also where a VPN tunnel lands; private either way
    ("172.16.4.9", True),
    ("172.32.4.9", False),  # just OUTSIDE 172.16/12 — public, and the easy off-by-one to get wrong
    ("221.127.188.34", False),  # the observed public DHCP address
    ("8.8.8.8", False),
    ("127.0.0.1", False),  # loopback is not a LAN target
    ("169.254.9.205", False),  # APIPA: an adapter that failed DHCP, never routable
    ("", False),  # the OS is the source, but a malformed value must not raise
    ("not-an-ip", False),
]

# WHICH address the band prints. `_stream_rows` shows exactly ONE (`urls()[:1]`), so this ordering
# IS the address the user types into a phone — get it wrong and they get the VPN tunnel, which is
# the precise failure `_lan_rank` exists to prevent (observed: NordLynx 10.5.0.2 ranked ahead of
# the real 192.168.0.104). Expected lists are pinned literally, never computed from `_lan_rank`.
# (route-probe address, interface addresses) -> what the band would offer, in order.
# The ROUTE half matters on its own: it is the first place a public address surfaces — the observed
# bridge-mode machine got 221.127.188.34 from the default route, not from the interface list — so a
# row with `route=None` everywhere would leave `lan_candidates`' own `_is_usable_lan(route)` guard
# untested while LAN_FILTER_CASES proved the predicate in isolation.
RANK_CASES = [
    ("10.5.0.2", ["10.5.0.2", "192.168.0.104"], ["192.168.0.104", "10.5.0.2"]),  # the observed VPN case
    (None, ["10.0.0.1", "172.16.4.9", "192.168.1.1"], ["192.168.1.1", "172.16.4.9", "10.0.0.1"]),
    (None, ["192.168.1.1", "192.168.0.104"], ["192.168.1.1", "192.168.0.104"]),  # equal rank keeps discovery order
    (None, ["10.5.0.2"], ["10.5.0.2"]),  # a tunnel alone is still offered — ranking never drops anything
    ("221.127.188.34", ["192.168.0.104"], ["192.168.0.104"]),  # a PUBLIC route address must not be offered
    ("221.127.188.34", [], ["127.0.0.1"]),  # ...and with nothing else, the fallback, never the public one
    ("192.168.0.104", ["192.168.0.104", "10.5.0.2"], ["192.168.0.104", "10.5.0.2"]),  # route also in the list -> no dupe
]

# `clean_port` — the persisted value is read before any window exists, so it must never raise.
PORT_CASES = [(8541, 8541), (8500, 8500), (8599, 8599), (8499, 8500), (99999, 8599), (None, 8541), ("abc", 8541), ("8550", 8550)]

# `clean_mode` is asserted DIRECTLY, because the bind rows above cannot see it: `bind_host_for`
# falls through to None for anything it does not recognise, so an unvalidated garbage mode reaches
# the same address a validated one does. Mutation-proven 2026-08-29 — relaxing `clean_mode` to
# accept any non-None value left every bind row green, which is the downstream-backstop trap
# (`principles.md` § "Test real logic, not ceremony"). The settings page is where it IS observable:
# it lights the cell whose name equals the mode, so an unrecognised one lights nothing at all.
MODE_CASES = [
    ("off", "off"),
    ("local", "local"),
    ("lan", "lan"),
    (None, "local"),  # unset -> the shipped default
    ("LAN", "local"),
    ("everywhere", "local"),
    (3, "local"),  # a non-string survives the `in` test without raising
]


def check_bind() -> int:
    failed = 0
    for saved, expected in BIND_CASES:
        got = frame_stream.resolve_bind_host(saved)
        if got != expected:
            print(f"FAIL  bind saved={saved!r}: expected {expected!r}, got {got!r}")
            failed += 1
    if frame_stream.resolve_bind_host() == "0.0.0.0":  # no argument at all = never configured
        print("FAIL  an absent setting must NOT bind the LAN")
        failed += 1
    for ip, expected in LAN_FILTER_CASES:
        got = frame_stream._is_usable_lan(ip)
        if got != expected:
            print(f"FAIL  _is_usable_lan({ip!r}): expected {expected}, got {got}")
            failed += 1
    # Driven through `lan_candidates` itself, with its two discovery sources stubbed — asserting
    # `sorted(addrs, key=_lan_rank)` would have re-implemented production's own line, so a
    # `reverse=True` or a re-sort after the rank would leave every row green while the phone got
    # the tunnel (`principles.md` § "A second implementation of a production decision drifts").
    _real_all, _real_route = frame_stream._all_local_addresses, frame_stream._default_route_address
    try:
        for route, addrs, expected in RANK_CASES:
            frame_stream._all_local_addresses = lambda a=addrs: list(a)
            frame_stream._default_route_address = lambda r=route: r
            got = frame_stream.lan_candidates()
            if got != expected:
                print(f"FAIL  lan_candidates(route={route!r}, addrs={addrs}): expected {expected}, got {got}")
                failed += 1
    finally:
        frame_stream._all_local_addresses, frame_stream._default_route_address = _real_all, _real_route
    for raw, expected in PORT_CASES:
        got = frame_stream.clean_port(raw)
        if got != expected:
            print(f"FAIL  clean_port({raw!r}): expected {expected}, got {got}")
            failed += 1
    for raw, expected in MODE_CASES:
        got = frame_stream.clean_mode(raw)
        if got != expected:
            print(f"FAIL  clean_mode({raw!r}): expected {expected!r}, got {got!r}")
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


# ── 4. what the UI is allowed to offer ────────────────────────────────────────
# `urls()` is what the setup band draws as a clickable row, so it is a claim
# that the address is live. The silent failure is a STALE claim: `stop()`
# releasing the socket while `urls()` still names it leaves the band offering a
# dead link that opens a browser on nothing, with no error anywhere. Same
# "a key read but never written" family as `reentry_pending` (conventions.md
# § Tooling), one step along — here it is read but never CLEARED.
#
# Oracle is the lifecycle, not the implementation: nothing is reachable before
# start and nothing is reachable after stop. Written against the module state
# directly so the check needs no socket — binding a real port in a unit test
# would make it fail on a machine where 8541 is busy.


def check_urls() -> int:
    failed = 0
    saved = frame_stream._urls
    try:
        frame_stream._urls = []
        if frame_stream.urls():
            print("FAIL  urls() offers an address while mirroring is off")
            failed += 1

        frame_stream._urls = ["http://10.0.0.4:8541/"]
        got = frame_stream.urls()
        if got != ["http://10.0.0.4:8541/"]:
            print(f"FAIL  urls() did not report the bound address: {got}")
            failed += 1
        got.append("http://evil/")  # a caller must not be able to edit what start recorded
        if len(frame_stream.urls()) != 1:
            print("FAIL  urls() handed out its own list, so a caller can add addresses to it")
            failed += 1

        frame_stream.stop()
        if frame_stream.urls():
            print("FAIL  urls() still offers an address after stop() released the socket")
            failed += 1
    finally:
        frame_stream._urls = saved
        frame_stream._stop.clear()  # stop() latches the event; leave the module as we found it
    return failed


def main() -> int:
    failed = check_bind() + check_tap() + check_dock() + check_urls()
    # NO DENOMINATOR. It used to be a hand-maintained sum carrying bare magic numbers (`+ 33 + 4`)
    # for two of the sections, so it drifted the moment a case was added and then described a run
    # that never happened. A total that cannot be trusted is worse than none —
    # `principles.md` § "A measurement is a claim until the instrument is calibrated". Counting for
    # real would mean instrumenting all 32 assertion sites; the honest cheap answer is to claim
    # only what is known, which is whether anything failed.
    print("test_stream: all checks passed" if not failed else f"test_stream: {failed} check(s) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: MIT
"""The departure-bell box in its own OS window, standing beside the PA window.

`departure_bell.py` draws the box; this module is the window it lives in and the
wiring that keeps it truthful. The box shows what the audio is doing and nothing
else — pressing a cap calls the same entry Page Up calls, so there is one audio
path and the picture cannot drift from the sound.

# CONTRACT: the bell is an ACCESSORY. Every failure in here — a window that
# cannot be created, a renderer that dies, a win32 call that is unavailable —
# closes the bell and leaves the drive running. Nothing in this module may raise
# into `app.py`'s loop. The tracebacks are printed in full and carry a distinct
# leading line, so a user report can be told apart from the crash it replaced
# (critical_lessons.md § 8).

# CONTRACT: the window's lifetime is drive-start to drive-end, and `close()`
# MUST run before `pygame.display.quit()`. Tearing down the display subsystem
# destroys `_sdl2` windows *silently* — the Python object survives, `.size`
# returns garbage and nothing raises — so a bell outliving its display is a
# read-after-free that looks like a rendering bug.

# CONTRACT: the box must NEVER take the keyboard focus, and this file must never
# call SetForegroundWindow. The app is an overlay for a game the user is driving:
# focus landing here stops their keys reaching the game. The mechanism is
# WS_EX_NOACTIVATE plus a window created HIDDEN and shown with SW_SHOWNOACTIVATE
# — both halves are needed, because SDL activates a window when it shows it and
# no ex-style prevents that. See the measurements below for why the obvious
# alternative is worse than doing nothing.

Platform facts behind the shape of this file, each established by probe on
pygame 2.6.1 / SDL 2.28.4 (upstream, not -ce):

  * `Window` here has no `get_surface()` / `flip()`. Drawing goes through
    `Renderer` + `Texture`, so the surface is scaled to the window size FIRST
    and the texture drawn 1:1 — that keeps the whole-multiple nearest-neighbour
    rule the rest of the app renders under, instead of handing scaling to SDL.
  * `Window._kwarg_to_flag` maps `always_on_top` and `tooltip` to 0 in this
    build: they are accepted and do nothing. Topmost is win32's job.
  * `SetWindowPos` without `SWP_NOACTIVATE` ACTIVATES the window it pins.
  * REMEMBER-AND-RESTORE — letting the click activate the box and handing focus
    back with `SetForegroundWindow` — measurably does not work, and fails in the
    way that looks like the box being broken rather than the focus being wrong:
    the first press registers and EVERY LATER PRESS IS SWALLOWED. Handing the
    foreground away desynchronises SDL's mouse-focus tracking, so it stops
    delivering `MOUSEBUTTONDOWN` to this window at all and starts reporting
    `WindowEnter` against the PA window while the cursor sits over the box.
    Measured 2026-08-22: 1 of 4 presses under restore, 6 of 6 under
    WS_EX_NOACTIVATE, with the foreground never leaving the unrelated app that
    held it.
  * `WS_EX_NOACTIVATE` also drops the taskbar button, which would make MINIMISE
    a one-way trip. `WS_EX_APPWINDOW` puts it back.
  * A main-window `set_mode` — the zoom path — does NOT disturb this window.
    Only `display.quit()` does, which is what the lifetime contract is about.
  * A resize arrives as `WINDOWSIZECHANGED` carrying the new size in `.x`/`.y`,
    for a user drag AND for a programmatic `Window.size =`. One handler serves
    both, which is also what terminates the snap loop.
  * `SetWindowPos` costs ~0.008 ms, so re-asserting topmost every frame is
    ~0.12 ms per second of drive. That is why the pin is unconditional below
    rather than throttled.
"""

from __future__ import annotations

import traceback

import pygame
from pygame._sdl2.video import Renderer, Texture, Window

import departure_bell as bell
import i18n
import window_utils

try:
    from win32 import win32gui

    _HWND_TOPMOST = -1
    _SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
    _GWL_EXSTYLE = -20
    _WS_EX_NOACTIVATE, _WS_EX_APPWINDOW = 0x08000000, 0x00040000
    _SW_SHOWNOACTIVATE = 4
except Exception:  # non-Windows / pywin32 absent — placement and focus degrade, the box still draws
    win32gui = None

# The OS window title, which is also how its HWND is found. Same wording as the
# plate, because that is what the box is called.
TITLE = "発車ベル"

# How long a cap stays visibly pressed after a click. Production handles no
# MOUSEBUTTONUP anywhere and a remote tap (stage 3) has no release to wait for,
# so the acknowledgment is a fixed hold rather than a held-down state — see
# `BellState`. At FRAME_RATE 15 this is between two and three frames, which is
# the shortest hold that reads as a press rather than a flicker.
FLASH_S = 0.16

# Gap between the PA window and the box when they are placed side by side.
GAP_PX = 8

# Share of the work area the box opens at, against `window_utils`'s 0.40 for the
# PA window. Same rule, smaller share: this is an accessory standing beside the
# window the user looks AT, not a second thing to look at. Gives 1x on 1080p and
# 1440p, 2x on 4K and 5K — the same ladder the PA window climbs, independently.
TARGET_HEIGHT_FRAC = 0.25


def pick_zoom(work_w: int, work_h: int) -> int:
    """The box's own opening multiple, from the SCREEN alone.

    Deliberately independent of the PA window: the two are separate windows the
    user sizes separately, so the box neither inherits nor follows the other's
    zoom. Pure, so it can be evaluated for a hypothetical screen rather than
    only the one this process is on — same reason `window_utils.max_zoom` takes
    the work area as arguments.
    """
    cw, ch = bell.BELL_CANVAS
    return window_utils.pick_default_zoom(cw, ch, work_w, work_h, frac=TARGET_HEIGHT_FRAC)


def place_beside(main_rect, size, work) -> "tuple[int, int]":
    """Top-left for the box, put to the RIGHT of the PA window with tops level.

    Falls to the left of it when the right would run off the work area, and
    clamps into the work area either way. Pure — `main_rect` is
    (left, top, right, bottom) as win32 reports it.
    """
    left, top, right, _bottom = main_rect
    w, h = size
    work_w, work_h = work
    x = right + GAP_PX
    if x + w > work_w:
        x = left - GAP_PX - w
    return max(0, min(x, max(0, work_w - w))), max(0, min(top, max(0, work_h - h)))


class BellWindow:
    """The box's window. Construct via `open()`, which never raises."""

    @classmethod
    def open(cls, main_hwnd) -> "BellWindow | None":
        try:
            return cls(main_hwnd)
        except Exception:  # noqa: BLE001 - an accessory must not take the drive with it
            print("Departure-bell window could not open; the drive is unaffected:")
            traceback.print_exc()
            return None

    def __init__(self, main_hwnd):
        self._closed = False
        self._state = None
        self._tex = None
        self._surf = None
        self._pin_failed = False
        self._flash_until = {"on": 0.0, "off": 0.0}
        # Pointer state, tracked from events rather than polled: with two windows
        # `pygame.mouse.get_pos()` reports against whichever one holds the mouse,
        # so a poll cannot tell you WHICH window it is answering for.
        self._mouse_in = False
        self._hover = None

        cw, ch = bell.BELL_CANVAS
        info = pygame.display.Info()
        self._work = window_utils.work_area(info.current_w, info.current_h)
        self._max_zoom = window_utils.max_zoom(cw, ch, *self._work)
        # A size the user chose deliberately outranks the default, and it is the
        # box's OWN setting — the PA window's `window_zoom` says nothing about it.
        saved = i18n.load_settings().get("bell_zoom")
        self.zoom = saved if isinstance(saved, int) and 1 <= saved <= self._max_zoom else pick_zoom(*self._work)

        # Created HIDDEN so the styles that keep it out of the focus chain are in
        # place before it is ever shown. SDL activates a window when it shows it,
        # whatever its ex-style says, so this order is the whole trick.
        self._win = Window(TITLE, size=(cw * self.zoom, ch * self.zoom), hidden=True, resizable=True)
        self._hwnd = win32gui.FindWindow(None, TITLE) if win32gui else None
        self._show(main_hwnd)
        self._ren = Renderer(self._win)

    # ── window chrome ─────────────────────────────────────────────────────────

    def _show(self, main_hwnd) -> None:
        """Style, place, pin and reveal the box, all without activating it.

        Fails soft in pieces: no win32 means SDL's own show and placement, which
        costs the focus guarantee but still draws a box.
        """
        if not (win32gui and self._hwnd):
            self._win.show()
            return
        try:
            ex = win32gui.GetWindowLong(self._hwnd, _GWL_EXSTYLE)
            win32gui.SetWindowLong(self._hwnd, _GWL_EXSTYLE, ex | _WS_EX_NOACTIVATE | _WS_EX_APPWINDOW)
            x, y = 0, 0
            if main_hwnd:
                x, y = place_beside(win32gui.GetWindowRect(main_hwnd), self._win.size, self._work)
            # One call puts it beside the PA window and pins it. The pin is
            # re-asserted every frame afterwards — see `_pin`.
            win32gui.SetWindowPos(self._hwnd, _HWND_TOPMOST, x, y, 0, 0, _SWP_NOSIZE | _SWP_NOACTIVATE)
            win32gui.ShowWindow(self._hwnd, _SW_SHOWNOACTIVATE)
        except Exception as e:  # noqa: BLE001 - a visible box beats a correctly-styled invisible one
            print(f"Warning: departure-bell window styling failed ({e}); showing it plainly.")
            self._win.show()

    def _pin(self) -> None:
        """Re-assert always-on-top, without activating the window or moving it.

        Called every frame, which is what gives the box the SAME property the PA
        window has rather than a one-shot version of it. The PA window re-pins on
        every `set_mode` through `window_utils.install_topmost_hook`; this window
        never goes through `set_mode`, so a pin at birth would be the only one it
        ever got — and a full-screen game, which is exactly what this app sits
        over, is what pushes a topmost window down. At ~0.008 ms a call,
        re-asserting is cheaper than reasoning about when it was lost.

        NOACTIVATE is the difference between pinning it and yanking focus off the
        game. NOSIZE|NOMOVE is what leaves a window the user dragged where they
        put it.

        Resizing is one of the things that loses the pin: SDL's own
        `SetWindowSize` clears WS_EX_TOPMOST, so `_apply_zoom` re-pins too rather
        than waiting for the next frame.

        Reported ONCE and then suppressed. A blanket silent `pass` on a per-frame
        call is how the first cut of this method hid a `NameError` in its own
        argument list — it never pinned anything and said nothing.
        """
        if not (win32gui and self._hwnd):
            return
        try:
            win32gui.SetWindowPos(self._hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)
        except Exception as e:  # noqa: BLE001 - always-on-top is a nicety, never fatal
            if not self._pin_failed:
                self._pin_failed = True
                print(f"Warning: the departure-bell window could not be pinned topmost ({e!r}); not reported again.")

    def _apply_zoom(self, k: int) -> None:
        """Adopt whole multiple ``k`` and remember it as the box's own choice.

        The guard is the WINDOW SIZE, not ``k`` — same reason as
        `PASimulator._apply_zoom`: a drag that snaps back to the same multiple
        still leaves the OS window at whatever odd size the user released at, and
        returning early there would leave every later frame scaling into a
        non-multiple. It is also the loop terminator, because setting `.size`
        emits another `WINDOWSIZECHANGED` that snaps to the same k and finds the
        size already right.
        """
        cw, ch = bell.BELL_CANVAS
        k = max(1, min(self._max_zoom, k))
        target = (cw * k, ch * k)
        if k == self.zoom and tuple(self._win.size) == target:
            return
        changed = k != self.zoom
        self.zoom = k
        self._win.size = target
        self._state = None  # forces the texture to be rebuilt at the new size
        self._pin()
        if changed:  # only a deliberate zoom change is worth a settings write
            settings = i18n.load_settings()
            settings["bell_zoom"] = k
            i18n.save_settings(settings)

    # ── events ────────────────────────────────────────────────────────────────

    def owns(self, event) -> bool:
        """Whether this event belongs to the box rather than the PA window.

        Identity against our own `Window`, not `event.window is not None`: the
        run loop's other click handlers read `event.pos` in PA-window
        coordinates, and mis-claiming in either direction puts a click through
        the wrong geometry. Matching the object exactly cannot do that, and it
        is what lets those handlers stay unguarded — this branch runs first and
        consumes, so nothing below it ever sees a bell event.
        """
        return not self._closed and getattr(event, "window", None) is self._win

    def handle(self, event, now: float) -> "str | None":
        """Consume one bell-window event; returns "on" / "off" when a cap was hit.

        The caller decides what a press DOES. This returns which cap it was and
        nothing more, so the audio path stays in `app.py` where Page Up's is.
        """
        if self._closed:
            return None
        if event.type == pygame.WINDOWCLOSE:
            # The author's spec: closing it affects nothing, and there is no way
            # to reopen it for the rest of the drive.
            self.close()
            return None
        if event.type == pygame.WINDOWSIZECHANGED:
            # A user drag, snapped to a whole multiple so the box is only ever
            # nearest-neighbour — the window visibly sticks at each multiple,
            # which is the same affordance the PA window has, and setting the
            # size emits the event that terminates the loop.
            #
            # The `> 0` is not decoration: a minimise can report a zero size, and
            # snapping to that would silently reset a zoom the user chose. The
            # bound is zero rather than one whole box, because a drag SMALLER
            # than the box is a real drag and must still snap back to 1x.
            if event.y > 0:
                self._apply_zoom(window_utils.snap_zoom(bell.BELL_CANVAS[1], event.y, self._max_zoom))
            return None
        if event.type == pygame.WINDOWENTER:
            self._mouse_in = True
            return None
        if event.type == pygame.WINDOWLEAVE:
            # Hand the pointer back: the PA window's own hover logic resumes the
            # frame after this, because `set_hover_cursor` stops claiming it.
            self._mouse_in = False
            self._hover = None
            return None
        if event.type == pygame.MOUSEMOTION:
            self._mouse_in = True
            self._hover = self._cap_at(event.pos)
            return None
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        which = self._cap_at(event.pos)
        self._hover = which
        if which:
            self._flash_until[which] = now + FLASH_S
        return which

    def _cap_at(self, pos) -> "str | None":
        """Which cap a WINDOW-space point is over. The zoom is the only difference
        between window pixels and the canvas the hit-rects are authored in."""
        return bell.hit_test((pos[0] // self.zoom, pos[1] // self.zoom))

    def tap(self, pos, now: float) -> "str | None":
        """A press from the STREAM, in docked-view coordinates.

        The dock carries the same surface this window draws, so a point in it is
        a window-space point and resolves through exactly the same `_cap_at` —
        one geometry answers the local click and the remote tap, which is what
        stops the hit-rects drifting from what is drawn. The flash is set here
        too, so a remote press is acknowledged on the PC's own box as well.
        """
        if self._closed:
            return None
        which = self._cap_at(pos)
        if which:
            self._flash_until[which] = now + FLASH_S
        return which

    # CONTRACT: the returned Surface must never be drawn into after it is returned.
    # `frame_stream` docks it and a SERVER thread blits it without copying — safe only because
    # `update` renders a fresh Surface and REBINDS `_surf` rather than redrawing in place. Changing
    # that to an in-place redraw for perf would tear the docked view, which is exactly the mid-draw
    # sampling the `_publish` CONTRACT in frame_stream.py exists to prevent. Named at both ends
    # because nothing else records the dependency.
    def surface(self) -> "pygame.Surface | None":
        """The box exactly as this window is showing it, for the stream to dock.

        None once closed — the stream shows what the PC shows, so a box the user
        closed leaves the remote view too. There is no reopen either way.
        """
        return None if self._closed else self._surf

    def set_hover_cursor(self) -> bool:
        """Set the pointer for the box, and report whether the box claimed it.

        While the mouse is inside this window the box owns the cursor outright —
        hand over a cap, arrow elsewhere on the casting — and the PA window's
        hover logic must stand down. That is not merely politeness: with two
        windows `pygame.mouse.get_pos()` answers for whichever holds the mouse,
        so the PA window would be reading bell-window pixels as LCD pixels.
        """
        if self._closed or not self._mouse_in:
            return False
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if self._hover else pygame.SYSTEM_CURSOR_ARROW)
        return True

    # ── frame ─────────────────────────────────────────────────────────────────

    def update(self, is_sta_looping: bool, now: float) -> None:
        """Draw the box for what the audio is doing. Called once per app frame.

        The texture is rebuilt only when the state changes — `render()` is cheap
        per change and wasteful per frame — but the renderer presents every
        frame, because an SDL back buffer holds nothing guaranteed after a
        present and a re-exposed window would otherwise show whatever is left.
        """
        if self._closed:
            return
        try:
            self._pin()
            state = bell.BellState.of(
                is_sta_looping,
                on_flash=now < self._flash_until["on"],
                off_flash=now < self._flash_until["off"],
            )
            if state != self._state or self._tex is None:
                self._state = state
                surf = bell.render(state)
                if self.zoom != 1:
                    surf = pygame.transform.scale(surf, self._win.size)
                # Kept, not discarded: the stream docks this same surface beside
                # the PA window's, so the remote sees the box at the size the PC
                # is actually showing it.
                self._surf = surf
                self._tex = Texture.from_surface(self._ren, surf)
            self._ren.clear()
            self._tex.draw()
            self._ren.present()
        except Exception:  # noqa: BLE001 - see the accessory contract at the top
            print("Departure-bell window failed and is closing; the drive is unaffected:")
            traceback.print_exc()
            self.close()

    def close(self) -> None:
        """Destroy the window. Idempotent, and must precede `display.quit()`."""
        if self._closed:
            return
        self._closed = True
        self._tex = None
        self._surf = None
        self._ren = None
        try:
            self._win.destroy()
        except Exception:  # noqa: BLE001 - already gone is the outcome we wanted
            pass

"""Window-lifecycle concerns: always-on-top pinning, and DPI awareness.

This app is a companion OVERLAY for JRE Train Sim — it must float above the game window. Every
``pygame.display.set_mode`` (re)creates the OS window and drops the topmost style, and the TIMS setup
flow calls ``set_mode`` on every screen transition, so a one-shot pin regresses. ``install_topmost_hook``
wraps ``set_mode`` so ANY call re-pins — one seam, regression-proof as new screens are added.

History: the monolith (``old_version.py``) re-pinned after every ``set_mode``; the modular rewrite kept
the pin ONLY in the sim (``app.py``), so the long TIMS setup flow (now the default) lost it. This
restores always-on-top app-wide. pywin32 is already a runtime dep (``app.py`` imports ``win32gui``).
"""

import ctypes

import pygame

try:
    from win32 import win32gui

    _HWND_TOPMOST = -1
    _SWP_NOSIZE, _SWP_NOMOVE = 0x0001, 0x0002
except Exception:  # non-Windows / pywin32 absent — topmost is simply a no-op
    win32gui = None


def declare_dpi_awareness() -> None:
    """Declare the process PER-MONITOR DPI aware. Call ONCE at app entry, before any window exists.

    Without this, Windows renders the app at logical size and bitmap-stretches the window by the
    display scale factor — at 125% a 730px window is resampled to 912px, which softens every
    pixel of a display whose elements are calibrated against IRL reference photos.

    It also removes a real inconsistency rather than only sharpening things. ``dxcam`` calls
    ``SetProcessDpiAwareness(2)`` as an IMPORT side effect (``dxcam/core/output.py``, reached when
    ``dxcam/__init__`` builds its factory at module scope), and ``auto_input`` is imported lazily —
    only when OCR is enabled, or when the Report button is pressed. So the app was DPI-unaware for
    the setup flow and became aware on entering an OCR drive, and awareness is one-way: it never
    reverted. Same build, same machine, two different window scalings decided by a lazy import.
    Declaring it here up front makes every screen consistent, and matches the level dxcam wants so
    its later call is a harmless no-op.

    Fail-silent: sharpness is a nicety, and a non-Windows or pre-8.1 host simply has no such API.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:  # noqa: BLE001 - pre-8.1, non-Windows, or already set by an earlier call
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # Vista+ system-DPI fallback
        except Exception as e:  # noqa: BLE001
            print(f"Warning: could not declare DPI awareness ({e}); window may be scaled by Windows.")


# ── window zoom ───────────────────────────────────────────────────────────────
# The app is a fixed-resolution pixel artifact: every element — the free-polygon current-stop
# marker, the _TUNEABLES_* vertex data, the AA-off TIMS chrome with its ~40px envelope — is
# authored at one pixel size. So it scales the way an emulator scales, by WHOLE multiples with
# nearest-neighbour, where each source pixel becomes a clean k*k block and nothing is invented.
# A fractional factor (Windows' own 125% / 150%) has to interpolate, which is the softness this
# whole path exists to remove.
TARGET_HEIGHT_FRAC = 0.40  # of the work area; middle of the 1/3-1/2 window the app looks right in
_FALLBACK_TASKBAR = 48  # only used when the real work area can't be read


def work_area(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Usable desktop area (screen minus taskbar) in PHYSICAL pixels, for the CURRENT desktop.

    The arguments are the fallback only — on Windows the real work rect is queried, because the
    taskbar is ~96px at 200% and a fixed allowance would over-report room on a high-DPI display and
    let the picker choose a multiple that does not fit. Pass the result to ``max_zoom`` /
    ``pick_default_zoom`` rather than letting them call this: those two must stay pure so they can
    be evaluated for a hypothetical screen, not only the one this process happens to be on.
    """
    try:
        import ctypes.wintypes

        rect = ctypes.wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.right - rect.left, rect.bottom - rect.top
    except Exception:  # noqa: BLE001 - non-Windows, or the call is unavailable
        pass
    return screen_w, max(1, screen_h - _FALLBACK_TASKBAR)


def max_zoom(canvas_w: int, canvas_h: int, work_w: int, work_h: int) -> int:
    """Largest whole multiple of the canvas that still fits the work area. Never below 1 — the
    floor matters more than the ceiling, since rendering BELOW native is what actually destroys a
    pixel-calibrated display, and a small screen must still get a usable (if proportionally large)
    window rather than a shrunken one."""
    k = 1
    while canvas_w * (k + 1) <= work_w and canvas_h * (k + 1) <= work_h:
        k += 1
    return k


def pick_default_zoom(canvas_w: int, canvas_h: int, work_w: int, work_h: int) -> int:
    """The multiple whose height sits closest to TARGET_HEIGHT_FRAC of the work area.

    This is the "app looks right without anyone touching it" default: 1x on 1080p and 1440p, 2x on
    4K, 2x on 5K. Ties break toward the SMALLER multiple — the app is a companion overlay beside a
    game, so when two choices are equally close it should take the lesser of the screen.
    """
    target = work_h * TARGET_HEIGHT_FRAC
    best, best_d = 1, abs(canvas_h - target)
    for k in range(2, max_zoom(canvas_w, canvas_h, work_w, work_h) + 1):
        d = abs(canvas_h * k - target)
        if d < best_d - 0.5:  # strict improvement -> equal-distance keeps the smaller k
            best, best_d = k, d
    return best


def snap_zoom(canvas_h: int, requested_h: int, kmax: int) -> int:
    """Snap a dragged window height to the nearest whole multiple, clamped to [1, kmax].

    Every size the window can settle on is therefore an exact multiple, so the blit is always
    nearest-neighbour and always sharp — the user feels it stick, which is how the sharp sizes get
    discovered without a settings dialog.
    """
    return max(1, min(kmax, round(requested_h / canvas_h)))


def pin_topmost() -> None:
    """Pin the current pygame display window as HWND_TOPMOST (no move / no resize). No-op when the
    window handle or win32 is unavailable (fail-silent — always-on-top is a nicety, never fatal)."""
    if win32gui is None:
        return
    try:
        hwnd = pygame.display.get_wm_info().get("window")
        if hwnd:
            win32gui.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOSIZE | _SWP_NOMOVE)
    except Exception as e:  # window not up yet / headless — nicety only, don't crash the flow
        print(f"Warning: could not pin window topmost: {e}")


def install_topmost_hook() -> None:
    """Wrap ``pygame.display.set_mode`` so every (re)created window is auto-pinned topmost. Idempotent.
    Call once at app entry (main.py) so the WHOLE flow — setup screens, tutorials, sim — stays on top
    without each ``set_mode`` site remembering to re-pin (that scatter is what regressed)."""
    if getattr(pygame.display.set_mode, "_topmost_wrapped", False):
        return
    _orig = pygame.display.set_mode

    def _set_mode(*args, **kwargs):
        surf = _orig(*args, **kwargs)
        pin_topmost()
        return surf

    _set_mode._topmost_wrapped = True
    pygame.display.set_mode = _set_mode

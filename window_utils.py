"""Keep the app window pinned always-on-top (Windows).

This app is a companion OVERLAY for JRE Train Sim — it must float above the game window. Every
``pygame.display.set_mode`` (re)creates the OS window and drops the topmost style, and the TIMS setup
flow calls ``set_mode`` on every screen transition, so a one-shot pin regresses. ``install_topmost_hook``
wraps ``set_mode`` so ANY call re-pins — one seam, regression-proof as new screens are added.

History: the monolith (``old_version.py``) re-pinned after every ``set_mode``; the modular rewrite kept
the pin ONLY in the sim (``app.py``), so the long TIMS setup flow (now the default) lost it. This
restores always-on-top app-wide. pywin32 is already a runtime dep (``app.py`` imports ``win32gui``).
"""

import pygame

try:
    from win32 import win32gui

    _HWND_TOPMOST = -1
    _SWP_NOSIZE, _SWP_NOMOVE = 0x0001, 0x0002
except Exception:  # non-Windows / pywin32 absent — topmost is simply a no-op
    win32gui = None


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

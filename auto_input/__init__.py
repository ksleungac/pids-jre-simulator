"""auto_input — OCR-driven PA firing from JR EAST Train Sim HUD.

Public-facing surface. Re-exports the three symbols consumed by production
entry points (main.py, app.py) + preview_debug_panel.py. Internal modules
(driver, hud_layout, ocr) are importable directly when needed (1b dev tool,
calibration extractor) — see AUTO_INPUT.md § Files for the breakdown.

Architecture / pipeline / state-machine details: AUTO_INPUT.md.
"""

from .driver import AutoDriver, draw_debug_panel, handle_panel_click

__all__ = ["AutoDriver", "draw_debug_panel", "handle_panel_click"]

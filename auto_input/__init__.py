# SPDX-License-Identifier: MIT
"""auto_input — OCR-driven PA firing from JR EAST Train Sim HUD.

Public-facing surface. Re-exports the two symbols consumed by production
entry points (main.py, app.py). Internal modules (driver, hud_layout, ocr)
are importable directly when needed (1b dev tool, calibration extractor) —
see auto_input/README.md § Files for the breakdown.

Architecture / pipeline / state-machine details: auto_input/README.md.
"""

from .driver import AutoDriver, generate_report

__all__ = ["AutoDriver", "generate_report"]

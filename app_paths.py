"""Project-root path resolution — single source of truth.

Every module that loads bundled assets (``data/*.json``, ``fonts/*``,
``audio/**``, ``ocr_templates/**``, etc.) imports ``project_root()``
from here. Adding a new path-resolution helper anywhere else in the
codebase is a smell — promote it here.
"""

import sys
from pathlib import Path


def project_root() -> Path:
    # CONTRACT: Resolve repo root for asset loading; frozen-aware (alongside-exe, NOT _MEIPASS).
    # See critical_lessons.md § "PyInstaller deployment-frame divergence — path resolution + bundle coverage".
    # Inventing a local path-resolver elsewhere is the smell that produced the 2026-05-05 crashes.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

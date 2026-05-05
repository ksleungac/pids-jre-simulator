"""Project-root path resolution — single source of truth.

Every module that loads bundled assets (``data/*.json``, ``fonts/*``,
``audio/**``, ``data/line_icons/*.png``) imports ``project_root()`` from
here. Centralizing the resolver eliminates the helper-triplication
class of bugs documented in ``critical_lessons.md`` § "PyInstaller —
alongside-exe vs ``_MEIPASS``".

Adding a new path-resolution helper anywhere else in the codebase is a
smell — promote it here.
"""

import sys
from pathlib import Path


def project_root() -> Path:
    # CONTRACT: Resolve repo root for asset loading; frozen-aware (alongside-exe, NOT _MEIPASS).
    # See WIP_pathology_family.md (pending promotion to critical_lessons.md).
    # Inventing a local path-resolver elsewhere is the smell that produced the 2026-05-05 crash.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

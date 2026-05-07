"""Project-root path resolution — single source of truth.

Every module that loads bundled assets (``data/*.json``, ``fonts/*``,
``audio/**``, ``ocr_templates/**``, etc.) imports ``project_root()``
from here. Adding a new path-resolution helper anywhere else in the
codebase is a smell — promote it here.
"""

import json
import sys
from pathlib import Path


def project_root() -> Path:
    # CONTRACT: Resolve repo root for asset loading; frozen-aware (alongside-exe, NOT _MEIPASS).
    # See critical_lessons.md § "PyInstaller deployment-frame divergence — path resolution + bundle coverage".
    # Inventing a local path-resolver elsewhere is the smell that produced the 2026-05-05 crashes.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def load_json_relative(filename: str) -> dict:
    """Load a JSON file resolved against project_root.

    Returns ``{}`` if the file is missing — callers tolerate empty dicts
    (e.g. ``self.translations.get(key, {})``). For required-asset loads
    where missing should fail loudly, use ``project_root() / filename``
    directly with explicit error handling.
    """
    path = project_root() / filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

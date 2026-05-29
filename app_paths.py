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


def app_version() -> str | None:
    # CONTRACT: frozen-aware version read — sys.frozen detection stays confined to
    # this module (conventions.md § Tooling), same as project_root().
    # /build stamps FileVersion into version_info.txt → the exe; this reads it
    # back so the running app knows its own version with NO hand-maintained
    # constant. Returns None in dev (no PE metadata) — callers skip version-
    # dependent behavior (update_check no-ops in dev).
    if not getattr(sys, "frozen", False):
        return None
    try:
        import win32api

        info = win32api.GetFileVersionInfo(sys.executable, "\\")
        ms, ls = info["FileVersionMS"], info["FileVersionLS"]
        major, minor = ms >> 16, ms & 0xFFFF
        patch, build = ls >> 16, ls & 0xFFFF
        version = f"{major}.{minor}.{patch}"
        # build N>0 → sub-revision letter (1→a, 2→b, …), matching /build's scheme.
        if build:
            version += chr(ord("a") + build - 1)
        return version
    except Exception:
        return None


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

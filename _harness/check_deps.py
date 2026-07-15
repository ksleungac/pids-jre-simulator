"""Dep scanner — verify all production imports are in pyproject.toml [project.dependencies].

Catches critical_lessons.md §3: lazy import ≠ optional dep. Any third-party package
imported anywhere in production code (including nested/conditional imports) must be in
[project.dependencies], not [dev].

Run:  uv run _harness/check_deps.py
Also called as a pre-flight gate by /build.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

# pyproject.toml install name → import-time top-level package names (when they differ)
# pywin32 installs several independent top-level modules (win32api, win32con, win32gui
# via the win32 package, pywintypes, …); list each name production actually imports.
_INSTALL_TO_IMPORT: dict[str, list[str]] = {
    "pywin32": ["win32", "win32api", "pywintypes"],
}

# Non-production dirs to exclude from scanning
_EXCLUDE_DIRS = {
    "dist",
    "dist-release",
    "build",
    "memory",
    "lcd_references",
    "audio_src",
    "docs",
    "audio",
    "data",
    "fonts",
    "ocr_templates",
}


# Root-level non-production Python excluded from the scan: the preserved monolith +
# preview/testing harnesses. Not shipped, not reachable from main.py, so their imports
# don't affect release safety — and they legitimately import dev-only tools
# (preview_display.py loads _dev_scripts/calibration_editor via a sys.path hack).
# NOTE: plot_drive.py is deliberately NOT excluded — it IS production-reachable
# (Report button → auto_input/driver.py), per critical_lessons.md §3.
_EXCLUDE_ROOT_FILES = {"old_version.py"}
_EXCLUDE_ROOT_PREFIXES = ("preview_",)


def _production_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for item in root.iterdir():
        if item.is_file() and item.suffix == ".py":
            if item.name.startswith("_") or item.name in _EXCLUDE_ROOT_FILES:
                continue
            if item.name.startswith(_EXCLUDE_ROOT_PREFIXES):
                continue
            files.append(item)
        elif item.is_dir():
            if item.name.startswith(("_", ".")) or item.name in _EXCLUDE_DIRS:
                continue
            files.extend(item.rglob("*.py"))
    return sorted(files)


def _all_imports(path: Path) -> set[str]:
    """Top-level package names for every import statement in the file, regardless of nesting."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute imports only
                names.add(node.module.split(".")[0])
    return names


def _allowed_imports(root: Path) -> set[str]:
    stdlib = set(sys.stdlib_module_names)  # Python 3.10+

    local: set[str] = set()
    for f in root.glob("*.py"):
        local.add(f.stem)
    for d in root.iterdir():
        if d.is_dir() and (d / "__init__.py").exists():
            local.add(d.name)

    with open(root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    dep_imports: set[str] = set()
    for spec in data.get("project", {}).get("dependencies", []):
        install_name = spec.split(">")[0].split("<")[0].split("=")[0].split("!")[0].split("[")[0].strip().lower()
        if install_name in _INSTALL_TO_IMPORT:
            dep_imports.update(_INSTALL_TO_IMPORT[install_name])
        else:
            dep_imports.add(install_name.replace("-", "_"))

    return stdlib | local | dep_imports


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parent.parent

    allowed = _allowed_imports(root)
    files = _production_files(root)

    violations: list[tuple[str, str]] = []
    for f in files:
        for name in sorted(_all_imports(f)):
            if name.startswith("_"):
                continue  # _*/ imports caught by lint_primitives ban
            if name not in allowed:
                violations.append((str(f.relative_to(root)), name))

    if violations:
        print("Dep violations — imported in production but not in [project.dependencies]:")
        for filepath, name in violations:
            print(f"  {filepath}: imports '{name}'")
        print(f"\n{len(violations)} violation(s). Fix: add to [project.dependencies], or check alias map in check_deps.py.")
        print("See critical_lessons.md §3.")
        return 1

    print(f"OK — {len(files)} production files checked, no dep violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

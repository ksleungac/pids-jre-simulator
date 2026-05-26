"""Harness integrity — verify all script references in settings.json and SKILL.md files exist on disk.

Catches: a hook or skill pointing to a renamed or deleted script.
Run: uv run _dev_scripts/check_harness.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# _dev_scripts/foo.py anywhere in text
_PAT_DEV = re.compile(r"_dev_scripts/([\w.]+\.py)")
# `uv run foo.py` or `python foo.py` for root-level scripts (negative lookahead skips _dev_scripts/ refs)
_PAT_ROOT = re.compile(r"(?:uv run|python)\s+(?!_dev_scripts/)([\w.-]+\.py)")


def _harness_sources(root: Path) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    settings = root / ".claude" / "settings.json"
    if settings.exists():
        sources.append(("settings.json", settings.read_text(encoding="utf-8")))
    for skill_md in sorted((root / ".claude" / "skills").rglob("SKILL.md")):
        sources.append((str(skill_md.relative_to(root)), skill_md.read_text(encoding="utf-8")))
    return sources


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sources = _harness_sources(root)

    refs: dict[str, set[str]] = {}  # script path → set of source labels
    for label, text in sources:
        for m in _PAT_DEV.finditer(text):
            path = f"_dev_scripts/{m.group(1)}"
            refs.setdefault(path, set()).add(label)
        for m in _PAT_ROOT.finditer(text):
            path = m.group(1)
            refs.setdefault(path, set()).add(label)

    missing = [(p, s) for p, s in sorted(refs.items()) if not (root / p).exists()]

    if missing:
        print("Missing scripts referenced in harness:")
        for path, labels in missing:
            print(f"  {path}")
            for label in sorted(labels):
                print(f"    <- {label}")
        print(f"\n{len(missing)} missing script(s).")
        return 1

    print(f"OK — {len(refs)} script references checked across {len(sources)} harness files, all exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

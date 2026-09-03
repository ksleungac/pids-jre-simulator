# SPDX-License-Identifier: MIT
"""Harness soundness — the harness's own references AND the environment it needs.

Three checks, each reporting independently (session-start tier: reports, never blocks):

1. Script references in settings.json and SKILL.md files exist on disk.
   Catches a hook or skill pointing at a renamed or deleted script.
2. The `private` remote is configured and its memory ref is reachable.
   Without it publish_memory writes nowhere and a whole session's narrative is
   silently queue-only. The public ref was deleted 2026-09-03, so there is no
   fallback to notice the loss by.
3. Every font face NAMED IN PRODUCTION CODE has a file in fonts/.
   2026-09-02 named `ShinGoPro-DeBold.otf` in an e233_0 renderer on a machine
   that did not have it. Nothing said so until a render raised deep inside
   lcd_font, by which point the face was committed and the lower LCD would not
   draw at all. This is the check that would have caught it in one second.

Run: uv run _harness/check_harness.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# any _<prefix>/foo.py reference (covers _harness/, _dev_scripts/, etc.)
# negative lookbehind prevents matching _input/ inside auto_input/
_PAT_SUBDIR = re.compile(r"(?<!\w)(_\w+/[\w.]+\.py)")
# `uv run foo.py` or `python foo.py` for root-level scripts (negative lookahead skips _*/  refs)
_PAT_ROOT = re.compile(r"(?:uv run|python)\s+(?!_\w+/)([\w.-]+\.py)")
# A font filename as a string literal. Spaces are allowed: Morisawa ships
# `A-OTF Shin Go Pro DB.otf`, which is why .gitignore carries three patterns.
_PAT_FACE = re.compile(r"[\"']([A-Za-z0-9][\w \-]*\.otf)[\"']")

PRIVATE_REMOTE = "private"


def _git(root: Path, *args):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- 1. script refs


def _harness_sources(root: Path) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    settings = root / ".claude" / "settings.json"
    if settings.exists():
        sources.append(("settings.json", settings.read_text(encoding="utf-8")))
    for skill_md in sorted((root / ".claude" / "skills").rglob("SKILL.md")):
        sources.append((str(skill_md.relative_to(root)), skill_md.read_text(encoding="utf-8")))
    return sources


def check_scripts(root: Path) -> tuple[bool, list[str]]:
    sources = _harness_sources(root)
    refs: dict[str, set[str]] = {}  # script path -> set of source labels
    for label, text in sources:
        for m in _PAT_SUBDIR.finditer(text):
            refs.setdefault(m.group(1), set()).add(label)
        for m in _PAT_ROOT.finditer(text):
            refs.setdefault(m.group(1), set()).add(label)

    missing = [(p, s) for p, s in sorted(refs.items()) if not (root / p).exists()]
    if not missing:
        return True, [f"OK — {len(refs)} script references across {len(sources)} harness files, all exist."]

    lines = ["Missing scripts referenced in harness:"]
    for path, labels in missing:
        lines.append(f"  {path}")
        lines.extend(f"    <- {label}" for label in sorted(labels))
    return False, lines


# ---------------------------------------------------------------- 2. private remote


def check_private_remote(root: Path) -> tuple[bool, list[str]]:
    rc, out = _git(root, "remote")
    if rc != 0 or PRIVATE_REMOTE not in out.split():
        return False, [
            f"NO '{PRIVATE_REMOTE}' REMOTE — narrative publishes nowhere and fonts cannot sync.",
            "  git remote add private https://github.com/ksleungac/private-pids-jre-simulator.git",
            "  (CLAUDE.md § Run)",
        ]
    rc, _ = _git(root, "rev-parse", "--verify", "--quiet", f"{PRIVATE_REMOTE}/memory")
    if rc != 0:
        return False, [
            f"'{PRIVATE_REMOTE}' remote configured but {PRIVATE_REMOTE}/memory is not fetched —",
            "  narrative would bootstrap a NEW ref rather than append to the existing one.",
            f"  git fetch {PRIVATE_REMOTE}",
        ]
    return True, [f"OK — {PRIVATE_REMOTE}/memory reachable; narrative has somewhere to publish."]


# ---------------------------------------------------------------- 3. named faces


def _production_py(root: Path) -> list[Path]:
    """Tracked .py outside every _*-prefixed DIRECTORY.

    parts[:-1] because the prefix marks a directory: testing the basename too
    would drop every __init__.py, and a model's __init__ is where its canvas
    and palette live (conventions.md § Naming).
    """
    rc, out = _git(root, "ls-files", "*.py")
    if rc != 0:
        return []
    files = []
    for rel in out.splitlines():
        p = Path(rel)
        if any(part.startswith("_") for part in p.parts[:-1]):
            continue
        files.append(root / p)
    return files


def check_named_faces(root: Path) -> tuple[bool, list[str]]:
    fonts_dir = root / "fonts"
    named: dict[str, set[str]] = {}  # face filename -> set of source rel-paths
    for path in _production_py(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _PAT_FACE.finditer(text):
            named.setdefault(m.group(1), set()).add(str(path.relative_to(root)).replace("\\", "/"))

    missing = sorted((f, s) for f, s in named.items() if not (fonts_dir / f).exists())
    if not missing:
        return True, [f"OK — {len(named)} font face(s) named in production, all present in fonts/."]

    lines = ["FONT FACE NAMED IN CODE BUT NOT ON THIS MACHINE — that surface will raise on first draw:"]
    for face, sources in missing:
        lines.append(f"  {face}")
        lines.extend(f"    <- {s}" for s in sorted(sources))
    lines.append("  uv run _harness/sync_fonts.py    (or push it from the machine that has it)")
    return False, lines


# ---------------------------------------------------------------- entry


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parent.parent

    failed = False
    for check in (check_scripts, check_private_remote, check_named_faces):
        ok, lines = check(root)
        failed = failed or not ok
        for line in lines:
            print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

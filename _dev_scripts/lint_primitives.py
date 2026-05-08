"""Lint forbidden production primitives — `conventions.md § Tooling`.

Run via the `ban-production-primitives` pre-commit hook. Files come from
pre-commit (staged .py files) or `pre-commit run --all-files`.

Adding a new ban: append a 4-tuple to BANS. Adding a new exempt path: extend
the per-ban exempt list. Keep in sync with `conventions.md § Tooling`.

Per-ban exempt list = files that ARE production but exempt for that specific
primitive (e.g. `app_paths.py` IS allowed to use `sys._MEIPASS`). Whole-folder
exclusions (`_dev_scripts/`, `_experiments/`, etc.) live in `.pre-commit-config.yaml`'s
`exclude` regex — those folders aren't production at all.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path
from typing import Iterable

# (compiled pattern, exempt-path substrings (forward-slash), human message)
BANS: list[tuple[re.Pattern[str], list[str], str]] = [
    (
        re.compile(r"pygame\.font\.SysFont\b"),
        ["compare_fonts.py", "compare_grid.py"],
        "pygame.font.SysFont is banned in production (crashes on Chinese-locale Windows) — load via pygame.font.Font(str(project_root() / 'fonts' / fname), ...). See conventions.md § Tooling.",
    ),
    (
        re.compile(r"sys\._MEIPASS\b"),
        ["app_paths.py"],
        "sys._MEIPASS only allowed in app_paths.py (this project ships assets alongside-exe via build copy, not --add-data). See conventions.md § Tooling.",
    ),
    (
        re.compile(r"Path\(__file__\)\.parent"),
        ["app_paths.py"],
        "Path(__file__).parent for bundled assets is banned — use app_paths.project_root(). See conventions.md § Tooling.",
    ),
    (
        re.compile(r"sys\.frozen\b"),
        ["app_paths.py"],
        "sys.frozen branching only allowed in app_paths.py — use app_paths.project_root() to resolve asset paths. See conventions.md § Tooling.",
    ),
]


def is_exempt(path_str: str, exempt: list[str]) -> bool:
    return any(token in path_str for token in exempt)


def get_skip_ranges(text: str) -> list[tuple[int, int]]:
    """Byte ranges of comments + string literals — match positions inside these
    are documentation, not violations. CONTRACT blocks and docstrings citing
    forbidden primitives are the common false-positive source.
    """
    skip: list[tuple[int, int]] = []
    line_offsets = [0]
    for line in text.split("\n"):
        line_offsets.append(line_offsets[-1] + len(line) + 1)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenizeError, SyntaxError, IndentationError):
        return []
    for tok in tokens:
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        start_off = line_offsets[tok.start[0] - 1] + tok.start[1]
        end_off = line_offsets[tok.end[0] - 1] + tok.end[1]
        skip.append((start_off, end_off))
    return skip


def in_skip_range(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in ranges)


def check_file(path: Path) -> Iterable[str]:
    norm = str(path).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    skip_ranges = get_skip_ranges(text)
    for pattern, exempt, msg in BANS:
        if is_exempt(norm, exempt):
            continue
        for m in pattern.finditer(text):
            if in_skip_range(m.start(), skip_ranges):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            yield f"{norm}:{line_no}: {msg}"


def main(argv: list[str]) -> int:
    findings: list[str] = []
    for arg in argv[1:]:
        path = Path(arg)
        if not path.is_file() or path.suffix != ".py":
            continue
        findings.extend(check_file(path))
    if findings:
        for f in findings:
            print(f)
        print(f"\n{len(findings)} forbidden primitive(s) found. See conventions.md § Tooling.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

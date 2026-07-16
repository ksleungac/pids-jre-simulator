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

import ast
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


# ── Derivable-literal bans — conventions.md § Tooling "canonical-source duplication" ──
# The BANS above match CODE primitives OUTSIDE string literals. These are the INVERSE:
# they inspect literal VALUES that must instead DERIVE from a single canonical source,
# because a hand-typed copy drifts silently when the source moves (a hardcoded "0.5.4"
# shipped while the build was 0.6.0). AST-based, not token/regex, so it distinguishes a
# value from a docstring/comment and (R2) checks the call context — the false-positive
# surface (version examples in docstrings, "data/…" in error strings) that a blind
# string-scan would either flag as noise or paper over with production-file-wide exempts.
_VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+[a-z]?$")  # 0.5.4 / v0.6.0 / 0.6.0a
_ASSET_RE = re.compile(r"^(?:\./)?(?:fonts|data|audio|ocr_templates)/")
# Call names that load a bundled asset from a path argument.
_ASSET_LOADERS = frozenset({"Font", "SysFont", "load", "Sound", "image", "open"})


def _docstring_ids(tree: ast.AST) -> set[int]:
    """id()s of the Constant nodes that are module/class/func docstrings — skipped by R1."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                val = body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    ids.add(id(val))
    return ids


def check_derivable_literals(path: Path) -> Iterable[str]:
    norm = str(path).replace("\\", "/")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return
    docs = _docstring_ids(tree)

    # R1 — hardcoded version literal in a value position (docstrings skipped; comments
    #      aren't AST nodes). Canonical source: app_paths.display_version().
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and _VERSION_RE.match(node.value):
            yield (
                f"{norm}:{node.lineno}: hardcoded version literal {node.value!r} — derive from "
                "app_paths.display_version() (frozen→PE metadata, dev→pyproject); a hand-maintained "
                "constant shipped 0.5.4 while the build was 0.6.0. See conventions.md § Tooling."
            )

    # R2 — bare bundled-asset path passed to a loader call. Paths built from
    #      project_root() are Call/Name args (not str Constants) → not flagged.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if fn not in _ASSET_LOADERS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _ASSET_RE.match(arg.value):
                yield (
                    f"{norm}:{arg.lineno}: bare bundled-asset path {arg.value!r} in {fn}(...) — resolve via "
                    "app_paths.project_root() / '<dir>' / '<file>'; a bare relative path works in the dev "
                    "cwd but crashes in the frozen exe. See critical_lessons.md § 4."
                )


def main(argv: list[str]) -> int:
    # Messages carry non-ASCII (→, §); cp1252 pipes on Windows would mojibake them.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = argv[1:]
    check, label = check_file, "forbidden primitive"
    if args and args[0] == "--derivable":
        check, label, args = check_derivable_literals, "hardcoded derivable literal", args[1:]
    findings: list[str] = []
    for arg in args:
        path = Path(arg)
        if not path.is_file() or path.suffix != ".py":
            continue
        findings.extend(check(path))
    if findings:
        for f in findings:
            print(f)
        print(f"\n{len(findings)} {label}(s) found. See conventions.md § Tooling.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

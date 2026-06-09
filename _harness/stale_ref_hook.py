"""PostToolUse(Edit) hook — surface stale refs when an identifier is renamed.

Fires when old_string → new_string removes 1–3 Python identifiers (rename signal).
Greps codebase for remaining instances and injects as context.
Silent for big refactors (>3 removed ids) and trivial edits (no ids removed).
"""

from __future__ import annotations

import io
import json
import keyword
import re
import subprocess
import sys
from pathlib import Path

_SKIP = set(keyword.kwlist) | {
    "self",
    "cls",
    "None",
    "True",
    "False",
    "int",
    "str",
    "float",
    "list",
    "dict",
    "set",
    "tuple",
    "bool",
    "type",
    "object",
    "super",
    "print",
    "range",
    "len",
    "open",
}


def _identifiers(text: str) -> set[str]:
    return {w for w in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]+\b", text) if w not in _SKIP and len(w) >= 4}


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    tool_input = data.get("tool_input", {})
    old_string = tool_input.get("old_string", "")
    new_string = tool_input.get("new_string", "")

    if not old_string or old_string == new_string:
        return

    removed = _identifiers(old_string) - _identifiers(new_string)

    if not removed or len(removed) > 3:
        return

    root = Path(__file__).resolve().parent.parent
    findings: list[tuple[str, list[str]]] = []

    for symbol in sorted(removed):
        result = subprocess.run(
            ["git", "grep", "-n", "--", symbol],
            capture_output=True,
            text=True,
            cwd=root,
        )
        lines = [l for l in result.stdout.splitlines() if not l.startswith("Binary file")]
        if lines:
            findings.append((symbol, lines))

    if not findings:
        return

    buf = io.StringIO()
    buf.write("=== Stale ref check ===\n")
    for symbol, lines in findings:
        buf.write(f"  '{symbol}' still found in:\n")
        for line in lines[:10]:
            buf.write(f"    {line}\n")
        if len(lines) > 10:
            buf.write(f"    ... {len(lines) - 10} more\n")

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": buf.getvalue(),
                }
            }
        )
    )


if __name__ == "__main__":
    main()

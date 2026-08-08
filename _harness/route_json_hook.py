# SPDX-License-Identifier: MIT
"""PostToolUse(Edit) hook — validate route.json immediately on edit.

Fires when the edited file is */route.json. Runs validate_data.py scoped to
that one file only (skips global catalog checks). Silent on clean; injects
issues as context on violation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith("route.json"):
        return

    root = Path(__file__).resolve().parent.parent
    # Edit tool passes absolute paths; validate_data.py's AUDIO_ROOT is relative,
    # so relative_to() inside check_route raises ValueError on an absolute input.
    try:
        route_path_arg = str(Path(file_path).relative_to(root))
    except ValueError:
        route_path_arg = file_path  # already relative or outside root

    result = subprocess.run(
        ["uv", "run", "validate_data.py", "--route", route_path_arg],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=root,
        env={**os.environ, "PYTHONUTF8": "1"},
    )

    output = result.stdout.strip()
    if not output:
        if result.returncode != 0:
            err = result.stderr.strip()
            output = f"validator exited {result.returncode} with no stdout" + (f"\n{err}" if err else "")
        else:
            return

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": f"=== route.json validator ===\n{output}\n",
                }
            }
        )
    )


if __name__ == "__main__":
    main()

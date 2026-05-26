"""PreToolUse(Edit) hook — inject context reminders for high-risk file edits.

Non-blocking. Fires only for file patterns where missing context has caused
documented incidents (display renderers, route loader, route.json).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent).replace("\\", "/")

_NUDGES: list[tuple[object, str]] = [
    (
        lambda p: "displays/train_models/" in p and p.endswith(".py"),
        "Display renderer — check # CONTRACT: blocks in this file. Docs: DISPLAY.md, DISPLAY_E235.md.",
    ),
    (
        lambda p: p == "route_loader.py",
        "Route loader — blast radius = all routes. Test multiple, not just one.",
    ),
    (
        lambda p: p.endswith("route.json") and "audio/" in p,
        "Route data — after edit verify: audio files exist, translations.json coverage, time fields.",
    ),
]


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    normalized = file_path.replace("\\", "/")
    if normalized.startswith(_ROOT):
        normalized = normalized[len(_ROOT) :].lstrip("/")

    hits = [msg for test, msg in _NUDGES if test(normalized)]
    if not hits:
        return

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": "=== Edit context ===\n" + "\n".join(f"  {h}" for h in hits),
                }
            }
        )
    )


if __name__ == "__main__":
    main()

"""PreToolUse(Glob) hook — flag when accessing a module dir without having read its README.

Fires before Glob executes under a directory that has a README.md, if that README
was never opened (Read tool_use) earlier in this session transcript.

Self-suppressing: once the README is Read, the hook goes silent for that dir.
Re-arms for different unread-README dirs. Allows the Glob to proceed always.
Scopes via README presence: only active where a module-level README exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _readme_was_read(transcript_path: str, readme_abs: Path) -> bool:
    """Return True if readme_abs appears as a Read tool_use in the transcript."""
    if not transcript_path:
        return False
    tp = Path(transcript_path)
    if not tp.exists():
        return False

    readme_norm = readme_abs.as_posix().lower()

    try:
        with tp.open(encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    msg = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                # Claude Code JSONL: tool_uses nested under msg['message']['content']
                if msg.get("type") != "assistant":
                    continue
                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use" or block.get("name") != "Read":
                        continue
                    fp = block.get("input", {}).get("file_path", "")
                    if fp and Path(fp).as_posix().lower() == readme_norm:
                        return True
    except (OSError, PermissionError):
        pass

    return False


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    if data.get("tool_name") != "Glob":
        return

    pattern = data.get("tool_input", {}).get("pattern", "")
    if not pattern:
        return

    # Extract base dir from pattern (everything before first glob character)
    base = pattern
    for ch in ("*", "?", "["):
        idx = base.find(ch)
        if idx != -1:
            base = base[:idx]

    root = Path(__file__).resolve().parent.parent
    search_dir = (root / base.rstrip("/\\")) if base else root

    # Walk up to find nearest README.md — stop before project root
    readme_path = None
    readme_dir = None
    for check_dir in (search_dir, search_dir.parent):
        if check_dir == root or not check_dir.is_relative_to(root):
            break
        candidate = check_dir / "README.md"
        if candidate.exists():
            readme_path = candidate
            readme_dir = check_dir
            break

    if readme_path is None:
        return

    transcript_path = data.get("transcript_path", "")
    if _readme_was_read(transcript_path, readme_path):
        return

    try:
        rel_readme = readme_path.relative_to(root)
        rel_dir = readme_dir.relative_to(root)
    except ValueError:
        rel_readme = readme_path
        rel_dir = readme_dir

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "additionalContext": (
                        f"[module-readme] glob under {rel_dir}/ but {rel_readme} not yet read — " f"read it; layout may be non-standard"
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()

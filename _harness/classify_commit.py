# SPDX-License-Identifier: MIT
"""Classify git-status files into commit buckets.

Runs as a PostToolUse hook after `git status` — injects a structured
classification report so the model skips the reasoning-heavy
file-classification step in /commit.
"""

import subprocess
import datetime
from pathlib import Path


def classify(path: str, status: str) -> str:
    """Classify a file path into a commit bucket."""
    # Never commit
    if any(path.endswith(ext) or path.startswith(prefix) for ext in (".exe", ".pyc") for prefix in ("dist/", "build/", "__pycache__/")):
        return "NEVER_COMMIT"

    # Data (shipped)
    if path.startswith("data/") and path.endswith(".json"):
        return "data_shipped"
    if path.startswith("audio/") and not path.startswith("audio/_"):
        return "data_shipped"

    # Data (harness)
    if path.startswith("audio/_"):
        return "data_harness"

    # Memory — narrative auto-publishes to the origin/memory journal ref via
    # _harness/publish_memory.py. Never commit cargo: a dirty memory file is
    # unpublished queue state, not a change.
    if path.startswith("memory/"):
        return "memory_pipe"

    # Program — docs/internal
    if path.endswith(".md") or path.startswith(".claude/"):
        return "program_docs"
    if path.startswith(".github/") or path == ".gitignore":
        return "program_docs"

    # Program — fonts
    if path.startswith("fonts/"):
        return "program_fonts"

    # Program — preview/harness
    if path.startswith("preview_") and path.endswith(".py"):
        return "program_preview"

    # Program — tools
    if path.startswith("_dev_scripts/") or path.startswith("_experiments/"):
        return "program_tools"
    if path.startswith("validate_") and path.endswith(".py"):
        return "program_tools"

    # Program — code
    if path.endswith(".py") or path in ("pyproject.toml", "uv.lock"):
        return "program_code"

    # Config
    if path.endswith(".toml") or path.endswith(".yaml") or path.endswith(".yml"):
        return "program_code"

    return "unknown"


BUCKET_LABELS = {
    "data_shipped": "Data (shipped)",
    "data_harness": "Data (harness)",
    "memory_pipe": "Memory (auto-published — do NOT stage; publish_memory.py owns these)",
    "program_code": "Program (code)",
    "program_docs": "Program (docs)",
    "program_preview": "Program (preview)",
    "program_tools": "Program (tools)",
    "program_fonts": "Program (fonts)",
    "NEVER_COMMIT": "⚠ NEVER COMMIT",
    "unknown": "Unclassified",
}


def main():
    result = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return

    # No outer strip(): `git status --short` encodes the staged/worktree state in
    # the first TWO columns, so an unstaged change begins with a literal space
    # (" M path"). Stripping the whole blob eats that space on the FIRST line
    # only, shifting line[3:] by one and printing the path a character short
    # (`_harness/...` -> `harness/...`). splitlines() already drops the trailing
    # newline; the per-line filter drops blanks.
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    if not lines:
        return

    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

    today = datetime.date.today().isoformat()
    recap_path = Path("memory") / f"{today}.md"
    if recap_path.exists():
        recap_status = "found"
    else:
        # Canonical memory lives on the origin/memory ref (publish_memory.py) — a
        # folder that didn't author today's block may still have it published there.
        origin = subprocess.run(
            ["git", "show", f"origin/memory:memory/{today}.md"],
            capture_output=True,
        )
        recap_status = "found (published on origin/memory)" if origin.returncode == 0 else "NOT FOUND"

    buckets: dict[str, list[str]] = {}
    for line in lines:
        status = line[:2].strip()
        path = line[3:].strip().strip('"')
        bucket = classify(path, status)
        buckets.setdefault(bucket, []).append(f"  {status:>2}  {path}")

    print(f"=== Commit Classification (auto) ===")
    print(f"Branch: {branch}")
    print(f"Session recap: memory/{today}.md {recap_status}")
    print()

    for bucket_key in BUCKET_LABELS:
        if bucket_key in buckets:
            print(f"{BUCKET_LABELS[bucket_key]}:")
            for entry in buckets[bucket_key]:
                print(entry)
            print()

    # Detect mix
    has_data = "data_shipped" in buckets
    has_code = "program_code" in buckets
    has_never = "NEVER_COMMIT" in buckets

    if has_data and has_code:
        print("⚠ Mix detected: data + program files in same commit")
    if has_never:
        print("⚠ Files that should never be committed are present")


def main_hook():
    """Output classification as Claude Code hook JSON."""
    import io
    import json

    buf = io.StringIO()
    import sys

    old_stdout = sys.stdout
    sys.stdout = buf
    main()
    sys.stdout = old_stdout

    text = buf.getvalue()
    if not text.strip():
        return

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    import sys

    if "--hook" in sys.argv:
        main_hook()
    else:
        main()

"""PreToolUse hook — surface sta-make / pa-make when work touches the audio corpus.

WHY. The skills' frontmatter `triggers` only fire on their own vocabulary
("trim sta", "sta_cut"). Real requests don't use it — "finish the audio
pooling", "start on the next line" — so the workflow spec sat unread until the
user handed it over by hand, every time. 2026-08-08: *"i had enough of having
to hand you skill when asking you to work on these"*.

Fires when a tool call touches `audio/` or `audio_src/` and the relevant
SKILL.md has neither been Read nor invoked via the Skill tool this session.
Self-suppressing per skill; always allows the call through.

Deliberately NOT matched: `audio.py` / `audio_layout.py` (production + dev
modules whose names collide with the corpus dir) — the pattern requires a
path separator after `audio`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_AUDIO_PATH = re.compile(r"\baudio(?:_src)?[/\\]", re.IGNORECASE)
# which skill a mention implicates; both when the work spans them
_STA_HINT = re.compile(r"[/\\]sta[/\\]|\bsta_cut\b|\bsta-make\b|[/\\]sta\b", re.IGNORECASE)
_PA_HINT = re.compile(r"[/\\]pa[/\\]|\bpa_at_station\b|\bpa-make\b|[/\\]pa\b", re.IGNORECASE)

SKILLS = {
    "sta-make": ".claude/skills/sta-make/SKILL.md",
    "pa-make": ".claude/skills/pa-make/SKILL.md",
}


def _loaded(transcript_path: str, skill: str, skill_rel: str) -> bool:
    """True if this session already Read the SKILL.md or invoked it via Skill."""
    if not transcript_path:
        return False
    tp = Path(transcript_path)
    if not tp.exists():
        return False
    target = (ROOT / skill_rel).as_posix().lower()
    try:
        with tp.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "assistant":
                    continue
                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    inp = block.get("input", {}) or {}
                    if block.get("name") == "Read":
                        fp = inp.get("file_path", "")
                        if fp and Path(fp).as_posix().lower() == target:
                            return True
                    elif block.get("name") == "Skill":
                        if str(inp.get("skill", "")).strip().lower() == skill:
                            return True
    except (OSError, PermissionError):
        pass
    return False


def _haystack(data: dict) -> str:
    ti = data.get("tool_input", {}) or {}
    parts = [
        str(ti.get("command", "")),
        str(ti.get("file_path", "")),
        str(ti.get("pattern", "")),
        str(ti.get("path", "")),
    ]
    return " ".join(p for p in parts if p)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return

    if data.get("tool_name") not in ("Bash", "PowerShell", "Edit", "Write", "Glob", "Read"):
        return

    text = _haystack(data)
    if not text or not _AUDIO_PATH.search(text):
        return

    wanted = []
    if _STA_HINT.search(text):
        wanted.append("sta-make")
    if _PA_HINT.search(text):
        wanted.append("pa-make")
    if not wanted:  # touches the corpus but names neither side
        wanted = ["sta-make", "pa-make"]

    transcript = data.get("transcript_path", "")
    unread = [s for s in wanted if not _loaded(transcript, s, SKILLS[s])]
    if not unread:
        return

    names = " + ".join(f"/{s}" for s in unread)
    paths = ", ".join(SKILLS[s] for s in unread)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "additionalContext": (
                        f"[audio-skill] touching the audio corpus without {names} loaded — read {paths} "
                        f"first; it owns the procedure, the gates and the named instruments "
                        f"(_dev_scripts/audio_id.py). Re-deriving them per session is how these jobs go wrong."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()

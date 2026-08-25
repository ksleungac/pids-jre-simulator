# SPDX-License-Identifier: MIT
"""PreToolUse(Bash|PowerShell) — deny editing a TRACKED file by GENERATING it.

WHY THIS IS A GATE AND NOT A RULE. `conventions.md` § Tooling already says
"Editing source by GENERATING it is one escape level too many — use Edit/Write
instead", and names the counter-force in its own text: bypass-permissions mode
injects, every single turn, "make file changes with sed, heredocs, or short
scripts, rather than using the dedicated Read, Edit, or Write tools." A rule in a
~33k-token preloaded corpus cannot out-argue an instruction with a 100% attention
share, and on 2026-08-26 it did not — the rule was in context and lost anyway.
`principles.md` § "Rules do not reach that bar; gates do".

WHAT IT COSTS WHEN IT LOSES: a string literal written INTO a file has its escapes
interpreted by the writer first, so a `\\n` in a heredoc reaches the file as a
real newline. 2026-08-20 that broke `validate_data.py` twice in one edit, each
time as a SyntaxError pointing at a line that looked fine in the heredoc.

TWO SHAPES, AND THEY NEED DIFFERENT TESTS. The first cut of this hook used one
loose conjunction — any shell-write shape × any tracked path named anywhere ×
any write verb — and denied `black --check <tracked>.py; printf … > /tmp/x.json`
on its first live run, because the tracked path was a read-only ARGUMENT. A gate
that fires on innocent commands gets tuned out, which is worse than no gate. So:

  A. TARGET VISIBLE — `> f`, `>> f`, `tee f`, `sed -i … f`, `Set-Content f`.
     The write target is syntactically there, so test exactly it and nothing else.
  B. TARGET HIDDEN — `python -c …`, `python - <<PY`, `uv run python -c …`.
     The write may be `pathlib`, `io.open`, `shutil`, a `with` block or a
     variable, and a parser that tried to resolve it would be the second
     implementation this whole rule is against. Fall back to the conjunction:
     a tracked path named anywhere × a write verb in the body.

CANNOT CATCH, by construction: a path built at runtime; a path held in a variable
from an earlier call; a two-step write-then-execute (the tracked path never
appears in the command that writes); a write inside an already-committed script
invoked normally; misuse of the Edit tool itself; shape B where the tracked path
is also only being read (accepted — that is the residual, and the bypass clears
it in one retry).

BYPASS: prefix with CLAUDE_GENERATED_SOURCE_OK=1 — same idiom as the git-commit
hook's CLAUDE_COMMIT_VIA_SKILL=1. Genuine codegen (a bake writing a manifest)
needs it.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BYPASS = "CLAUDE_GENERATED_SOURCE_OK=1"

# --- Shape A: the write target is syntactically visible. -------------------
_VISIBLE_TARGET = re.compile(
    r"""(?x)
    (?<![0-9])>>?\s*(?P<redir>[^\s;&|<>]+)
  | \btee\s+(?:-a\s+)?(?P<tee>[^\s;&|<>]+)
  | \bsed\s+-i\b[^;&|]*?\s(?P<sed>[^\s;&|<>]+)\s*$
  | \b(?:Set|Add)-Content\b[^;|]*?(?:-Path\s+)?(?P<ps>[^\s;|]+)
    """,
    re.MULTILINE,
)

# --- Shape B: an inline program, target not visible. -----------------------
_INLINE_PROGRAM = re.compile(r"""(?x)
    (?:python3?|uv\s+run\s+python|uv\s+run)\s+(?:-\s*<<|-c\b)
  | (?:^|[;&|(])\s*cat\s+<<
  | @'[\s\S]*?'@\s*\|\s*(?:Set|Add)-Content
    """)

_WRITE_VERB = re.compile(r"""(?x)
    open\([^)]*['"][wa]
  | \bwrite_text\b | \bwrite_bytes\b | \bwritelines\b | \.write\(
  | shutil\.(?:copy|copy2|copyfile|move)
  | os\.(?:replace|rename)
    """)

_PATHY = re.compile(r"""[A-Za-z0-9_./\\:-]+\.(?:py|md|json)""")


def _norm(tok: str) -> str:
    p = tok.strip("'\"").replace("\\", "/")
    root = str(ROOT).replace("\\", "/")
    if p.lower().startswith(root.lower()):
        p = p[len(root) :]
    p = p.lstrip("/")
    if p.startswith("./"):
        p = p[2:]
    return p


def _tracked(paths):
    """Which of `paths` git tracks. One subprocess, batched."""
    paths = [p for p in paths if p and ":" not in p and not p.startswith("/")]
    if not paths:
        return []
    try:
        out = subprocess.run(
            ["git", "ls-files", "--"] + paths,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def _offenders(cmd: str):
    # Shape A — test exactly the visible targets.
    targets = set()
    for m in _VISIBLE_TARGET.finditer(cmd):
        for g in ("redir", "tee", "sed", "ps"):
            if m.group(g):
                targets.add(_norm(m.group(g)))
    hits = _tracked(sorted(targets))
    if hits:
        return hits

    # Shape B — target hidden inside an inline program.
    if _INLINE_PROGRAM.search(cmd) and _WRITE_VERB.search(cmd):
        return _tracked(sorted({_norm(t) for t in _PATHY.findall(cmd)}))
    return []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd or BYPASS in cmd:
        return 0

    hits = _offenders(cmd)
    if not hits:
        return 0

    named = ", ".join(hits[:4]) + (" ..." if len(hits) > 4 else "")
    reason = (
        f"Generated-source edit blocked: this command writes tracked file(s) through a "
        f"redirect or an inline program - {named}. Use the Edit or Write tool instead.\n\n"
        'conventions.md section Tooling: "Editing source by GENERATING it is one escape '
        'level too many." A string literal written INTO a file has its escapes interpreted '
        "by the writer first, so a newline escape in a heredoc reaches the file as a real "
        "newline; 2026-08-20 that broke validate_data.py twice in one edit, each time as a "
        "SyntaxError pointing at a line that looked fine in the heredoc.\n\n"
        f"Bypass for genuine codegen only: prefix the command with {BYPASS}."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

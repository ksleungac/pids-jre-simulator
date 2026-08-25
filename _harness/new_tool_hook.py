# SPDX-License-Identifier: MIT
"""PreToolUse(Write|Bash|PowerShell) — a NEW .py is being created; show what already exists.

`redlines.md`: never write a new tool or instrument while one exists, discover
before you even think to write one, and expand rather than fork when the existing
one falls short. That is unenforceable as a recollection — the model has to think
of looking, and the reflex to construct wins. So this fires at the one moment the
redline governs: the instant a file that does not yet exist is about to.

It does not recite the rule. It answers it — the emission is the tool inventory
FILTERED by the verbs in the proposed filename and body, so the closest existing
tools are named at the decision point. `conventions.md` § Tooling: "flag
violations directly, not inject rules into context"; a filtered list is the flag.

WHAT IT COST NOT TO HAVE THIS. 2026-08-26: 32 temp-directory scripts written to
answer four questions, and every one already had a home —
`_dev_scripts/calibration_editor.py` holds the reference overlay, the live render,
the `_TUNEABLES_*` dicts AND the write-back; `compare_fonts.py` / `compare_grid.py`
do reference-vs-candidate composites; one-shot probes have seven
`_dev_scripts/_<question>.py` precedents. The search that would have found them
fails on "does anything do my JOB" and succeeds on "does anything hold my INPUTS",
which is the line this hook prints.

NON-BLOCKING. Writing a genuinely new file is legitimate and a deny would teach
the model to route around the gate.

CANNOT CATCH, by construction: an inline `python -c` that never writes a file
(`no_generated_source_hook.py` covers the tracked-file half of that); APPENDING to
an existing scratch file, which is the behaviour the rule wants anyway; a new file
whose name shares no verb with any tool (falls back to the unfiltered list); a
capability buried inside a tool that its docstring's first line does not mention.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_DIRS = ("_dev_scripts", "_harness")

# A new .py appearing as a heredoc or redirect target.
_PY_TARGET = re.compile(r"""(?:>>?|\btee\s+(?:-a\s+)?)\s*([^\s;&|<>'"]+\.py)\b""")

_VERBS = (
    "fit",
    "compare",
    "measure",
    "resample",
    "overlay",
    "bbox",
    "score",
    "probe",
    "inspect",
    "classify",
    "render",
    "preview",
    "montage",
    "grid",
    "mask",
    "layout",
    "panel",
    "font",
    "atlas",
    "audio",
    "ocr",
    "verify",
    "check",
    "bake",
    "calib",
    "sim",
    "test",
    "id",
)


def _docline(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    for quote in ('"""', "'''"):
        i = text.find(quote)
        if i == -1:
            continue
        rest = text[i + 3 :].lstrip().splitlines()
        if rest:
            return rest[0].strip().rstrip(".")
    return ""


def _inventory():
    rows = []
    for folder in TOOL_DIRS:
        d = ROOT / folder
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name != "__init__.py":
                rows.append((f"{folder}/{f.name}", _docline(f)))
    return rows


def _closest(name: str, body: str, rows):
    """Rows whose path or docline shares a verb with the proposed file."""
    hay = (name + " " + body[:4000]).lower()
    wanted = {v for v in _VERBS if v in hay}
    if not wanted:
        return rows[:6]
    scored = []
    for path, doc in rows:
        blob = (path + " " + doc).lower()
        hits = sum(1 for v in wanted if v in blob)
        if hits:
            scored.append((hits, path, doc))
    scored.sort(key=lambda r: -r[0])
    return [(p, d) for _, p, d in scored[:6]] or rows[:6]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}

    if tool == "Write":
        fp = (ti.get("file_path") or "").strip()
        if not fp.endswith(".py"):
            return 0
        try:
            if Path(fp).exists():
                return 0
        except Exception:
            return 0
        name, body = Path(fp).name, ti.get("content") or ""
    else:
        body = ti.get("command") or ""
        targets = [t for t in _PY_TARGET.findall(body)]
        targets = [t for t in targets if not Path(t).exists()]
        if not targets:
            return 0
        name = Path(targets[0]).name

    rows = _inventory()
    if not rows:
        return 0
    near = _closest(name, body, rows)
    width = max(len(p) for p, _ in near)
    listing = "\n".join(f"    {p:<{width}}  {d[:84]}" for p, d in near)

    msg = (
        f"[new-tool] creating {name}, which does not exist yet.\n"
        "  REDLINE: never write a new tool while one exists; expand the existing one.\n"
        "  Closest existing:\n"
        f"{listing}\n"
        "  A HIT is a tool that already holds your INPUTS, even if it does not do your JOB.\n"
        "  Display tuning is the calibration editor: register the element in its _REGISTRY,\n"
        "  then `preview_display.py --edit --overlay <ref>` (docs/DISPLAY.md step 6).\n"
        '  Genuinely one-off? `_dev_scripts/_<question>.py` with a """Throwaway: <question>"""\n'
        "  docstring, tracked — never the OS temp dir (conventions.md section Naming)."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "additionalContext": msg,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

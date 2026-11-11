# SPDX-License-Identifier: MIT
"""Memory loop hooks: session start, a step line per edit during work, the turn-end check.

Subcommands (wired in .claude/settings.json):
  session-start  SessionStart  run session_init (git sync, memory pull + publish, backlog, tools)
                               and add the loop's notes: unrecapped days, orphaned edits, corpus size
  track          PostToolUse   record project files this session edited; clear them once the
                               session edits today's daily log
  stop           Stop          block the end of a turn while this session has unlogged edits
  skip [path…]   manual        clear tracked edits (scratch-only work); no path = the most recent session
  status         manual        print the tracker state

Ported from game-in-idea's .claude/hooks/memory_loop.py (2026-11-09), which grew out of this
repo's publish_memory.py. Differences here:
- Several sessions share one working tree (CLAUDE.md § "Working loop"), so the tracker keys
  edits by session, the Stop check reads only its own session's entries, and each session logs
  under its own `## Session: in progress — <topic>` block.
- session-start wraps session_init.main() instead of reimplementing it.
- The size check covers the whole always-loaded corpus, measured by check_rules_corpus.py.

A hook must not break a session: track and stop swallow their own errors, and session-start
reports one in the context it injects rather than failing.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"
STATE = ROOT / ".claude" / "state" / "memory-loop.json"
FULL_OUTPUT = ROOT / ".claude" / "state" / "session-start.txt"
TRACKED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
IN_PROGRESS = "## Session: in progress"
# A session silent this long is taken as ended; its unlogged edits pass to the next one.
ORPHAN_AFTER = datetime.timedelta(hours=6)
# Claude Code caps a hook's injected context; past this the full text goes to a file.
CONTEXT_LIMIT = 9_500

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _now():
    return datetime.datetime.now().replace(microsecond=0)


def read_input():
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return {}


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def emit(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def today_log_rel(today=None):
    return f"memory/{(today or datetime.date.today()).isoformat()}.md"


def project_relative(file_path):
    path = Path(file_path)
    if not path.is_absolute():
        path = ROOT / path
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None  # outside the project: scratchpad, another repo


# ---------------------------------------------------------------- pure tracker logic
# T1-tested in _tests/t1_unit/test_memory_loop.py — keep these free of I/O.


def record_edit(state, session_id, rel, now, today):
    """Apply one edit to the tracker. Returns the new state.

    Editing today's daily log clears this session's pending edits; any other project
    file is added to them. memory/ upkeep (the index, older logs) is not project work.
    """
    if rel is None or rel.startswith(".claude/state/"):
        return state
    if rel.startswith("memory/") and rel != today_log_rel(today):
        return state
    sessions = state.setdefault("sessions", {})
    entry = sessions.setdefault(session_id or "?", {"pending": {}})
    entry["seen"] = now.isoformat()
    if rel == today_log_rel(today):
        entry["pending"] = {}
    else:
        entry["pending"][rel] = now.isoformat()
    return state


def pending_for(state, session_id):
    return sorted((state.get("sessions", {}).get(session_id or "?") or {}).get("pending") or {})


def adopt_orphans(state, session_id, now):
    """Move the unlogged edits of sessions silent past ORPHAN_AFTER onto this session.

    Returns (state, adopted_paths, live_others). A recently active session may still be
    running in parallel, so its edits are only reported, never adopted.
    """
    sessions = state.setdefault("sessions", {})
    mine = sessions.setdefault(session_id or "?", {"pending": {}})
    adopted, live = [], []
    for sid, entry in list(sessions.items()):
        if sid == (session_id or "?"):
            continue
        pending = entry.get("pending") or {}
        seen = entry.get("seen")
        stale = seen is None or now - datetime.datetime.fromisoformat(seen) > ORPHAN_AFTER
        if pending and stale:
            mine.setdefault("pending", {}).update(pending)
            adopted += sorted(pending)
            del sessions[sid]
        elif pending:
            live += sorted(pending)
        elif stale:
            del sessions[sid]
    if adopted:
        mine["seen"] = now.isoformat()
    return state, adopted, live


def in_progress_days(logs):
    """Dates whose log still holds an in-progress block. `logs` is [(date, text)]."""
    return [d for d, text in logs if any(line.startswith(IN_PROGRESS) for line in text.splitlines())]


# ---------------------------------------------------------------- subcommands


def _daily_logs():
    if not MEMORY_DIR.is_dir():
        return []
    out = []
    for p in MEMORY_DIR.iterdir():
        m = DAILY_RE.match(p.name)
        if m:
            out.append((m.group(1), p.read_text(encoding="utf-8", errors="replace")))
    return sorted(out, reverse=True)


def _corpus_note():
    """One line when the always-loaded corpus is over its cap, else None."""
    sys.path.insert(0, str(ROOT / "_dev_scripts"))
    import check_rules_corpus

    total = check_rules_corpus.always_loaded_chars()
    cap = check_rules_corpus.ALWAYS_LOADED_CHARS
    if total > cap:
        return (
            f"The always-loaded corpus is {total:,} chars, over its {cap:,} cap "
            "(check_rules_corpus.py). Tighten, or move a domain rule to its path-scoped file."
        )
    return None


def loop_notes(data, today=None):
    today = today or datetime.date.today()
    now = _now()
    session_id = data.get("session_id")
    notes = [f"=== Memory loop — today is {today:%Y-%m-%d (%A)} ==="]

    state, adopted, live = adopt_orphans(load_state(), session_id, now)
    save_state(state)
    if adopted:
        notes.append(
            "A session that has gone quiet ended with unlogged edits to: "
            + ", ".join(adopted)
            + f". They are now this session's: add the missing step line under an in-progress block in "
            f"{today_log_rel(today)} before new work (ask the author for the why if it cannot be reconstructed)."
        )
    if live:
        notes.append(
            "Another session active in the last few hours has unlogged edits to: "
            + ", ".join(live)
            + ". It may still be running in this tree; leave those files and that log line to it."
        )

    stuck = in_progress_days(_daily_logs())
    older = [d for d in stuck if d != today.isoformat()]
    if older:
        notes.append(
            f"memory/ day(s) {', '.join(older)} hold a `{IN_PROGRESS}` block that was never recapped, "
            "so it never published. Offer /session-recap for them before new work."
        )
    if today.isoformat() in stuck:
        notes.append(
            f"{today_log_rel(today)} already holds an in-progress block. It may belong to a parallel "
            "session; start your own `## Session: in progress — <topic>` block rather than writing into it."
        )

    try:
        line = _corpus_note()
        if line:
            notes.append(line)
    except Exception as e:  # the size check is advisory
        notes.append(f"(corpus size check skipped: {type(e).__name__}: {e})")

    if data.get("source") == "compact":
        notes.append(
            f"Context was just compacted: {today_log_rel(today)} is the durable record of this session. "
            "Add any step from before compaction that is missing there."
        )
    return "\n".join(notes)


def cmd_session_start(data):
    # Notes first: they are short and actionable, and truncation cuts from the end.
    try:
        parts = [loop_notes(data)]
    except Exception:
        parts = ["=== Memory loop notes FAILED ===\n" + traceback.format_exc(limit=3)]
    if data.get("source") != "compact":
        # A real text stream, not StringIO: session_init's siblings call
        # sys.stdout.reconfigure() at import, and StringIO has no such method.
        buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="replace", write_through=True)
        try:
            # Imported OUTSIDE the redirect: session_init rewraps sys.stdout.buffer at import.
            import session_init
        except Exception:
            session_init = None
            buf.write("=== session_init failed to import ===\n" + traceback.format_exc(limit=3))
        with contextlib.redirect_stdout(buf):
            try:
                if session_init is not None:
                    session_init.main(brief=True)
            except Exception:
                print("=== session_init FAILED — run `uv run _harness/session_init.py` by hand ===")
                print(traceback.format_exc(limit=3))
        buf.flush()
        parts.append(buf.buffer.getvalue().decode("utf-8", errors="replace").strip())

    text = "\n\n".join(p for p in parts if p)
    FULL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FULL_OUTPUT.write_text(text, encoding="utf-8")
    if len(text) > CONTEXT_LIMIT:
        tail = f"\n\n[… truncated at {CONTEXT_LIMIT:,} of {len(text):,} chars — Read {FULL_OUTPUT.relative_to(ROOT).as_posix()} for the rest]"
        text = text[:CONTEXT_LIMIT] + tail
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})


def cmd_track(data):
    if data.get("tool_name") not in TRACKED_TOOLS:
        return
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    rel = project_relative(file_path) if file_path else None
    state = load_state()
    before = json.dumps(state, sort_keys=True)
    state = record_edit(state, data.get("session_id"), rel, _now(), datetime.date.today())
    if json.dumps(state, sort_keys=True) != before:
        save_state(state)


def cmd_stop(data):
    if data.get("stop_hook_active"):
        return  # already blocked once this turn; never loop
    pending = pending_for(load_state(), data.get("session_id"))
    if not pending:
        return
    shown = ", ".join(pending[:10]) + (f" (+{len(pending) - 10} more)" if len(pending) > 10 else "")
    log = today_log_rel()
    emit(
        {
            "decision": "block",
            "reason": (
                f"Memory loop: these files changed without a step line in today's daily log: {shown}. "
                f"Add or update one line under this session's `{IN_PROGRESS} — <topic>` block in {log} "
                f"(create the file with a `# {log[7:17]}` heading if missing): the step and why, one line. "
                "If the turn continues a step already logged, edit that line instead. "
                "Rules, preferences and decisions go to their home in CLAUDE.md § Memory loop's table, not the log. "
                "Scratch-only edits: run `uv run _harness/memory_loop.py skip <path>` instead. "
                "Then stop; don't repeat your previous reply."
            ),
        }
    )


def cmd_skip(argv):
    state = load_state()
    sessions = state.get("sessions", {})
    cleared = []
    if argv:
        wanted = {project_relative(a) or a for a in argv}
        for entry in sessions.values():
            for rel in list(entry.get("pending") or {}):
                if rel in wanted:
                    del entry["pending"][rel]
                    cleared.append(rel)
    elif sessions:
        sid = max(sessions, key=lambda s: sessions[s].get("seen") or "")
        cleared = sorted(sessions[sid].get("pending") or {})
        sessions[sid]["pending"] = {}
    save_state(state)
    print("memory loop: cleared " + (", ".join(sorted(set(cleared))) if cleared else "nothing"))


def cmd_status(_argv):
    print(json.dumps(load_state(), indent=2, sort_keys=True, ensure_ascii=False))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "session-start":
        cmd_session_start(read_input())
    elif cmd in ("track", "stop"):
        try:
            (cmd_track if cmd == "track" else cmd_stop)(read_input())
        except Exception:  # a tracker fault must not block the session's work
            print(f"memory_loop {cmd}: {traceback.format_exc(limit=2)}", file=sys.stderr)
    elif cmd == "skip":
        cmd_skip(sys.argv[2:])
    elif cmd == "status":
        cmd_status(sys.argv[2:])
    else:
        print("usage: memory_loop.py {session-start|track|stop|skip [path…]|status}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

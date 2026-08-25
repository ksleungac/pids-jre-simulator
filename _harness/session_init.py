# SPDX-License-Identifier: MIT
"""Session initialization — dump memory context + GitHub-Issues backlog in one shot.

Replaces 3-4 separate Read calls at session start.
Outputs: today's memory, yesterday's memory, MEMORY.md index, GitHub-Issues backlog
summary, and the TODO.md long-term directions (which are deliberately NOT issues).

Usage:
    uv run _harness/session_init.py
"""

import io
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Allow importing sibling modules
sys.path.insert(0, str(Path(__file__).parent))


def git_sync():
    """Fetch + fast-forward if possible; report divergence for manual resolution.

    Branch-aware: on a non-master branch (worktree folder B), fetch only — the
    master ff/divergence nag doesn't apply there; narrative flows via
    publish_memory against the dedicated origin/memory ref either way."""
    subprocess.run(["git", "fetch", "origin"], capture_output=True)

    branch_r = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, encoding="utf-8")
    branch = branch_r.stdout.strip() if branch_r.returncode == 0 else "?"
    if branch != "master":
        print(f"=== Git sync — on branch '{branch}' (fetched; master ff-sync skipped) ===\n")
        return

    rev = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", "HEAD...origin/master"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if rev.returncode != 0:
        print("=== Git sync — could not compare with origin ===\n")
        return

    ahead, behind = (int(x) for x in rev.stdout.strip().split())

    if ahead == 0 and behind == 0:
        print("=== Git sync — already up to date ===\n")
    elif ahead == 0:
        result = subprocess.run(
            ["git", "merge", "--ff-only", "origin/master"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            # git writes its "Updating <old>..<new>" header before it checks whether the
            # working tree is in the way, so stdout reads like a completed fast-forward on
            # a run that aborted. The exit code is the only thing that separates them —
            # never report the pull from result.stdout.
            detail = (result.stderr or result.stdout).strip()
            print(
                f"=== Git sync — FAILED, still {behind} commit(s) behind ===\n"
                f"{detail}\n"
                f"  This checkout is NOT current. Usual cause: a dirty file that also\n"
                f"  changed upstream — stash or commit it, then re-run:\n"
                f"    git merge --ff-only origin/master\n"
            )
        else:
            print(f"=== Git sync — pulled {behind} commit(s) ===\n{result.stdout.strip()}\n")
    else:
        print(
            f"=== Git sync — NEEDS MANUAL RESOLUTION ===\n"
            f"  Local is {ahead} ahead, {behind} behind origin/master.\n"
            f"  Run: git pull --rebase  (or merge manually)\n"
        )


def memory_text(rel_path):
    """Canonical narrative view: origin/memory ∪ local files (publish_memory merge).

    origin/memory (journal-only ref) is the canonical memory store — all writes
    flow through publish_memory.py; the union covers the offline / unpublished-
    queue case."""
    from publish_memory import _norm, _origin_text, merged_view

    origin = _origin_text(rel_path)
    p = Path(rel_path)
    local = _norm(p.read_bytes()) if p.exists() else None
    return merged_view(origin, local, rel_path)


def print_memory(rel_path, label):
    """Print the merged narrative view with a header, or a 'not found' note."""
    content = memory_text(rel_path)
    if content and content.strip():
        print(f"=== {label} ({Path(rel_path).name}) ===")
        print(content.strip())
        print()
    else:
        print(f"=== {label} — not found ===\n")


def _gh():
    """Resolve the gh executable, or None if unavailable."""
    import shutil

    if shutil.which("gh"):
        return "gh"
    fallback = r"C:\Program Files\GitHub CLI\gh.exe"
    return fallback if Path(fallback).exists() else None


def gh_backlog(stale_days=14, closed_lookback_days=3):
    """GitHub-Issues backlog summary at session start. Fail-soft when offline / gh missing."""
    import json

    gh = _gh()
    if not gh:
        print("=== Backlog — gh CLI not found; see github.com issues ===\n")
        return

    def run(args):
        r = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8")
        return r.stdout if r.returncode == 0 else None

    def loads(s):
        try:
            return json.loads(s) if s else []
        except Exception:
            return []

    out = run(["issue", "list", "--state", "open", "--limit", "300", "--json", "number,title,labels"])
    if out is None:
        print("=== Backlog — gh unavailable (offline / not authed); skipped ===\n")
        return

    issues = loads(out)
    areas = ["review-finding", "display", "auto-input", "chrome-i18n", "housekeeping", "distribution", "build-incident"]
    counts = {a: 0 for a in areas}
    in_progress = []
    for it in issues:
        names = {l["name"] for l in it.get("labels", [])}
        for a in areas:
            if a in names:
                counts[a] += 1
        if "in-progress" in names:
            in_progress.append(it)

    print(f"=== Backlog (GitHub Issues) — {len(issues)} open ===")
    area_line = " · ".join(f"{a} {counts[a]}" for a in areas if counts[a])
    if area_line:
        print(f"  by area: {area_line}")

    if in_progress:
        print(f"  in-progress ({len(in_progress)}):")
        for it in in_progress:
            print(f"    #{it['number']} {it['title'][:70]}")
    else:
        print("  in-progress: none")

    since = (date.today() - timedelta(days=closed_lookback_days)).isoformat()
    closed = loads(run(["issue", "list", "--state", "closed", "--limit", "50", "--search", f"closed:>={since}", "--json", "number,title"]))
    if closed:
        print(f"  closed since {since} ({len(closed)}):")
        for it in closed:
            print(f"    #{it['number']} {it['title'][:70]}")

    stale_before = (date.today() - timedelta(days=stale_days)).isoformat()
    stale = loads(
        run(["issue", "list", "--state", "open", "--label", "in-progress", "--search", f"updated:<{stale_before}", "--json", "number,title"])
    )
    if stale:
        print(f"  ⚠ stale in-progress (untouched >{stale_days}d):")
        for it in stale:
            print(f"    #{it['number']} {it['title'][:70]}")
    print()


def directions():
    """Print the TODO.md "Directions" headings — long-term paths that are NOT issues.

    A direction has no closure event, so it cannot live in the tracker without
    reading as owed work forever. It lives in TODO.md and gets PUSHED here at
    session start, because that is the moment the author asks what to work on.
    Each entry in that file carries its own description; only headings print."""
    todo = Path(__file__).resolve().parent.parent / "TODO.md"
    if not todo.exists():
        return
    lines = todo.read_text(encoding="utf-8").splitlines()
    titles, inside = [], False
    for ln in lines:
        if ln.startswith("## "):
            inside = ln.startswith("## Directions")
            continue
        if inside and ln.startswith("### "):
            titles.append(ln[4:].strip())
    if not titles:
        return
    print(f"=== Directions — wanted, not yet scoped ({len(titles)}) ===")
    for t in titles:
        print(f"  · {t}")
    print("  full description per entry: TODO.md § Directions")
    print()


def _docline(path: Path) -> str:
    """First sentence of a module's docstring, or "" if it has none."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    for quote in ('"""', "'''"):
        i = text.find(quote)
        if i == -1:
            continue
        line = text[i + 3 :].lstrip().splitlines()
        if line:
            return line[0].strip().rstrip(".")
    return ""


def tools():
    """Print the tool inventory — the redline's "discover before you write" as a PUSH.

    `redlines.md`: never write a new tool or instrument while one exists, and
    expand rather than fork when one falls short. That is unenforceable as a
    recollection — the model has to think of looking — so the inventory is put in
    front of it at the one moment guaranteed to precede the thought
    (`principles.md` § "Natural adoption gates tool value": a PULL tool loses to
    the reflex; this converts it to a push).

    2026-08-26 is the cost of not having this: 32 temp-directory scripts written
    to answer four questions, every one of which already had a home here —
    `calibration_editor.py`, `compare_fonts.py`, `compare_grid.py`, and the
    `_dev_scripts/_<question>.py` throwaway convention.

    Docstring first lines, so the inventory cannot drift from the tools: it is
    derived, never a list typed into this file
    (`principles.md` § "A second implementation of a production decision drifts").
    """
    root = Path(__file__).resolve().parent.parent
    rows = []
    for folder in ("_dev_scripts", "_harness"):
        d = root / folder
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name == "__init__.py":
                continue
            rows.append((f"{folder}/{f.name}", _docline(f)))
    if not rows:
        return
    print(f"=== Tools you already have ({len(rows)}) — expand one before writing a new one ===")
    width = max(len(n) for n, _ in rows)
    for name, doc in rows:
        print(f"  {name:<{width}}  {doc[:88]}")
    print("  A HIT is a tool that already holds your INPUTS, even if it does not do your JOB.")
    print('  redlines.md · principles.md § "Search before authoring"')
    print()


def main():
    git_sync()

    # Publish any narrative queued in the checkout (fail-soft; fetch already done).
    try:
        from publish_memory import sync as publish_sync

        publish_sync(fetch=False)
    except Exception as e:
        print(f"[publish-memory] skipped ({e})\n")

    today = date.today()
    yesterday = today - timedelta(days=1)

    print_memory(f"memory/{today.isoformat()}.md", "Today's memory")
    print_memory(f"memory/{yesterday.isoformat()}.md", "Yesterday's memory")
    # MEMORY.md — only last 10 entries (older rarely matters for session pickup)
    mem_text = memory_text("memory/MEMORY.md")
    if mem_text:
        lines = mem_text.strip().splitlines()
        # Find entry lines (start with "- [")
        entries = [(i, l) for i, l in enumerate(lines) if l.startswith("- [")]
        if len(entries) > 10:
            header = [l for l in lines[: entries[0][0]] if l.strip()]
            recent = [l for _, l in entries[:10]]
            print(f"=== Memory index (last 10 of {len(entries)} entries) ===")
            for h in header:
                print(h)
            print()
            for r in recent:
                print(r)
            print(f"\n  ({len(entries) - 10} older entries omitted)")
            print()
        else:
            print(f"=== Memory index (MEMORY.md) ===")
            print(mem_text.strip())
            print()
    else:
        print("=== Memory index — not found ===\n")

    try:
        from check_harness import main as harness_check

        result = harness_check()
        if result != 0:
            print("=== Harness integrity — BROKEN (see above) ===\n")
        # clean pass is already printed by check_harness
    except Exception as e:
        print(f"=== Harness integrity check failed: {e} ===\n")

    tools()
    gh_backlog()
    directions()


if __name__ == "__main__":
    main()

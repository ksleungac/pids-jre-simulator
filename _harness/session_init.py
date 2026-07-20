"""Session initialization — dump memory context + GitHub-Issues backlog in one shot.

Replaces 3-4 separate Read calls at session start.
Outputs: today's memory, yesterday's memory, MEMORY.md index, GitHub-Issues backlog summary.

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
    """Fetch + fast-forward if possible; report divergence for manual resolution."""
    subprocess.run(["git", "fetch", "origin"], capture_output=True)

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
        print(f"=== Git sync — pulled {behind} commit(s) ===\n{result.stdout.strip()}\n")
    else:
        print(
            f"=== Git sync — NEEDS MANUAL RESOLUTION ===\n"
            f"  Local is {ahead} ahead, {behind} behind origin/master.\n"
            f"  Run: git pull --rebase  (or merge manually)\n"
        )


def read_if_exists(path, label):
    """Print file contents with a header, or a 'not found' note."""
    p = Path(path)
    if p.exists():
        content = p.read_text(encoding="utf-8").strip()
        if content:
            print(f"=== {label} ({p.name}) ===")
            print(content)
            print()
            return
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


def main():
    git_sync()

    today = date.today()
    yesterday = today - timedelta(days=1)

    read_if_exists(f"memory/{today.isoformat()}.md", "Today's memory")
    read_if_exists(f"memory/{yesterday.isoformat()}.md", "Yesterday's memory")
    # MEMORY.md — only last 10 entries (older rarely matters for session pickup)
    mem_path = Path("memory/MEMORY.md")
    if mem_path.exists():
        lines = mem_path.read_text(encoding="utf-8").strip().splitlines()
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
            print(mem_path.read_text(encoding="utf-8").strip())
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

    gh_backlog()


if __name__ == "__main__":
    main()

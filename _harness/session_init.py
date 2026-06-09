"""Session initialization — dump memory context + TODO sweep in one shot.

Replaces 3-4 separate Read calls at session start.
Outputs: today's memory, yesterday's memory, MEMORY.md index, TODO sweep.

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

    try:
        from sweep_todo import get_recent_commits, keyword_match, parse_todo

        sections = parse_todo()
        commits = get_recent_commits(days=14)

        print(f"=== TODO sweep (last 14 days, {len(commits)} commits) ===\n")

        total_open = 0
        total_closed = 0
        likely_closed = []

        for section in sections:
            all_items = list(section["items"])
            for sub in section.get("subsections", []):
                all_items.extend(sub["items"])

            open_items = [i for i in all_items if not i["done"]]
            closed_items = [i for i in all_items if i["done"]]
            total_open += len(open_items)
            total_closed += len(closed_items)

            print(f"  {section['name']}: {len(open_items)} open, {len(closed_items)} closed")

            for item in open_items:
                hits = keyword_match(item["title"], commits)
                if hits:
                    likely_closed.append((item, hits, section["name"]))

        print(f"\n  Totals: {total_open} open, {total_closed} closed")

        if likely_closed:
            print(f"\n  Possibly closed (open items matching recent commits):")
            for item, hits, section in likely_closed:
                print(f"    [ ] {item['title']}")
                print(f"        match: {hits[0]}")

        if total_closed > 10:
            print(f"\n  Note: {total_closed} stale [x] items — consider cleanup pass.")
    except Exception as e:
        print(f"=== TODO sweep failed: {e} ===")
        print("  Fallback: read TODO.md manually.")


if __name__ == "__main__":
    main()

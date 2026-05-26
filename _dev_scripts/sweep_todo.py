"""Pre-digest TODO.md for session-recap.

Parses TODO.md items, cross-references against recent git commits,
and reports: section counts, likely-closed items, stale [x] items
that could be cleaned up.

Usage:
    uv run _dev_scripts/sweep_todo.py           # plain text report
    uv run _dev_scripts/sweep_todo.py --days 7   # look back N days (default 14)
"""

import io
import re
import subprocess
import sys
from datetime import datetime, timedelta


def _ensure_utf8_stdout():
    if hasattr(sys.stdout, "encoding") and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def parse_todo(path="TODO.md"):
    """Parse TODO.md into sections with items."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    sections = []
    current_section = None
    current_subsection = None

    for line in lines:
        if line.startswith("## "):
            current_section = {"name": line.strip("# \n"), "items": [], "subsections": []}
            current_subsection = None
            sections.append(current_section)
        elif line.startswith("### ") and current_section:
            current_subsection = {"name": line.strip("# \n"), "items": []}
            current_section["subsections"].append(current_subsection)
        elif re.match(r"^- \[([ x])\]", line) and current_section:
            done = line[3] == "x"
            text = line[6:].strip()
            # Extract bold title if present
            title_match = re.match(r"\*\*(?:~~)?(.*?)(?:~~)?\*\*", text)
            title = title_match.group(1) if title_match else text[:80]
            item = {"done": done, "title": title, "full": text[:120]}
            target = current_subsection if current_subsection else current_section
            target["items"].append(item)

    return sections


def get_recent_commits(days=14):
    """Get commit messages from the last N days."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--oneline"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]


def keyword_match(title, commits):
    """Check if any commit message loosely matches an item title."""
    title_lower = title.lower()
    # Extract meaningful keywords (3+ chars, skip common words)
    skip = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "not",
        "are",
        "was",
        "has",
        "have",
        "been",
        "when",
        "will",
        "but",
        "all",
        "can",
        "per",
        "also",
    }
    words = [w for w in re.findall(r"[a-z0-9_]{3,}", title_lower) if w not in skip]
    if not words:
        return []

    hits = []
    for commit in commits:
        commit_lower = commit.lower()
        matched = [w for w in words if w in commit_lower]
        if len(matched) >= 2 or (len(words) <= 2 and len(matched) >= 1):
            hits.append(commit)
    return hits


def main():
    days = 14
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            days = int(sys.argv[idx + 1])

    sections = parse_todo()
    commits = get_recent_commits(days)

    print(f"=== TODO.md Sweep (last {days} days, {len(commits)} commits) ===\n")

    total_open = 0
    total_closed = 0
    likely_closed = []
    stale_closed = []

    for section in sections:
        all_items = list(section["items"])
        for sub in section.get("subsections", []):
            all_items.extend(sub["items"])

        open_items = [i for i in all_items if not i["done"]]
        closed_items = [i for i in all_items if i["done"]]
        total_open += len(open_items)
        total_closed += len(closed_items)

        print(f"## {section['name']}: {len(open_items)} open, {len(closed_items)} closed")

        for item in open_items:
            hits = keyword_match(item["title"], commits)
            if hits:
                likely_closed.append((item, hits, section["name"]))

        for item in closed_items:
            stale_closed.append((item, section["name"]))

    print(f"\nTotals: {total_open} open, {total_closed} closed")

    if likely_closed:
        print(f"\n--- Likely closed (open items matching recent commits) ---")
        for item, hits, section in likely_closed:
            print(f"  [ ] {item['title']}")
            print(f"      in: {section}")
            print(f"      matches: {hits[0]}")

    if stale_closed:
        print(f"\n--- Stale [x] items ({len(stale_closed)} total, consider removal) ---")
        for item, section in stale_closed:
            print(f"  [x] {item['title'][:60]}")


if __name__ == "__main__":
    _ensure_utf8_stdout()
    main()

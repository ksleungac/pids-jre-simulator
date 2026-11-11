# SPDX-License-Identifier: MIT
"""Publish narrative memory to the dedicated `memory` ref — mechanical suffix-sync.

memory/*.md are append-only narrative (daily logs + MEMORY.md index). The canonical
store is `private/memory` — a journal-only ref on the PRIVATE remote, so master's
history stays pure code and a recap is not a publishing surface. This script computes
the blocks/entries present in the local files but absent from the ref, appends them
onto the ref's copy, and pushes the result as a commit built with git plumbing — no
branch switch, so it works identically from master, a feature branch, or a worktree.
If the ref doesn't exist yet it is BOOTSTRAPPED (parentless orphan commit) from the
local memory files.

The store moved off `origin/memory` on 2026-09-03 (TODO.md § "A private remote for
what the public repo cannot hold"). `private/memory` was seeded with origin's full
history, so there is one ref to read rather than a cutover date splitting it in two.
`origin/memory` is FROZEN, not retracted: this script refuses edits to published
blocks, so its 69 commits stay public whatever happens next.

Design (2026-07-23, third-man-adjusted; moved off master same day — commit-noise):
- The local memory/ files ARE the queue, origin/memory the canonical store.
  /session-recap writes local files exactly as before; the local-minus-origin
  difference is what gets published. Offline -> no-op (the queue persists on disk).
- Merging is mechanical + idempotent: daily logs merge at "## " block granularity,
  MEMORY.md at entry-line granularity. A block/entry already on origin (verbatim)
  is skipped, so retries / double-runs cannot duplicate content.
- A local block whose HEADING matches an origin block but whose body differs is an
  edit, not an append -> NOT published, loud warning, manual resolution. Same for a
  MEMORY.md entry whose [label] matches but text differs.
- Non-fast-forward push (a concurrent push won the race) -> refetch, recompute the
  merge against the new tip, retry. Appends are position-independent, so the retry
  is purely mechanical.

Memory loop (2026-11-09, ported from game-in-idea, which built on this script):
- Step lines are written to today's log DURING work, under a block headed
  `## Session: in progress — <topic>`. Such a block never publishes; /session-recap
  replaces it with a narrative block, and only that one goes out.
- `pull` writes the ref's blocks/entries into the local files, so a log recapped on
  the other PC exists on disk here rather than only in session_init's merged view.
- Network calls never open a credential prompt and time out, because a hook runs this.

# CONTRACT: memory/*.md are append-only; every write to origin flows through this
# script. /commit never stages memory/** (classify_commit.py buckets them out).

Usage:
    uv run _harness/publish_memory.py             # pull, then publish pending narrative
    uv run _harness/publish_memory.py --dry-run   # show what would pull / publish
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = REPO_ROOT / "memory"
PUBLISH_REMOTE = "private"  # NOT origin — a recap is not a publishing surface
PUBLISH_BRANCH = "memory"  # journal-only ref; master history stays pure code
REMOTE_REF = f"{PUBLISH_REMOTE}/{PUBLISH_BRANCH}"
MAX_PUSH_RETRIES = 3
# A block under this heading is a session still being logged; it stays local.
IN_PROGRESS_HEADING = "## Session: in progress"
NET_TIMEOUT = 60
# Runs inside the SessionStart hook: never open a credential prompt.
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


# ---------------------------------------------------------------- git helpers


def _git(args, input_bytes=None):
    """Run git in the repo root. Returns (returncode, stdout_bytes, stderr_bytes)."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            input=input_bytes,
            env=GIT_ENV,
            capture_output=True,
            timeout=NET_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, b"", str(e).encode()
    return r.returncode, r.stdout, r.stderr


def _norm(raw: bytes) -> str:
    """Decode UTF-8 and normalize newlines to \\n (checkout may be CRLF, blobs LF)."""
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _origin_text(rel_path: str):
    """Content of a file at origin/memory (normalized), or None if absent."""
    rc, out, _ = _git(["show", f"{REMOTE_REF}:{rel_path}"])
    return _norm(out) if rc == 0 else None


# ---------------------------------------------------------------- pure merge logic
# T1-tested in _tests/t1_unit/test_publish_memory.py — keep these free of git/I/O.


def split_daily(text: str):
    """Lossless partition of a daily log: (preamble, [blocks]).

    A block starts at a line beginning "## " and runs to the next such line.
    Preamble is everything before the first block. "".join back == text.
    """
    lines = text.splitlines(keepends=True)
    preamble_parts, blocks, current = [], [], None
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                blocks.append("".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
        else:
            preamble_parts.append(line)
    if current is not None:
        blocks.append("".join(current))
    return "".join(preamble_parts), blocks


def is_recapped(block: str) -> bool:
    """False for a block still being logged — it stays local until /session-recap."""
    return not block.startswith(IN_PROGRESS_HEADING)


def merge_daily(origin_text, local_text, keep=None):
    """Merge a daily log: origin + local blocks origin lacks.

    Returns (merged_text, new_blocks, warnings). origin_text None => file is new
    on origin, local publishes verbatim. A local block whose heading collides
    with an origin block but whose body differs is skipped with a warning
    (edited, not appended — manual case).

    `keep` filters the local blocks (publish passes `is_recapped`). With a filter
    and no origin copy, the new file is the preamble plus the kept blocks, or
    None when nothing is kept. `pull` calls this with the arguments swapped.
    """
    warnings = []
    preamble, local_blocks = split_daily(local_text)
    if keep is not None:
        local_blocks = [b for b in local_blocks if keep(b)]
    if origin_text is None:
        if keep is None:
            return local_text, list(local_blocks), warnings
        if not local_blocks:
            return None, [], warnings
        merged = preamble.rstrip("\n") + "\n\n" + "\n\n".join(b.strip("\n") for b in local_blocks) + "\n"
        return merged.lstrip("\n"), list(local_blocks), warnings

    _, origin_blocks = split_daily(origin_text)
    origin_keys = {b.strip() for b in origin_blocks}
    origin_headings = {b.splitlines()[0].strip() for b in origin_blocks}

    new_blocks = []
    for block in local_blocks:
        stripped = block.strip()
        if not stripped or stripped in origin_keys:
            continue
        heading = block.splitlines()[0].strip()
        if heading in origin_headings:
            warnings.append(f"edited block NOT published (heading exists on origin with different body): {heading!r}")
            continue
        new_blocks.append(block)

    if not new_blocks:
        return origin_text, [], warnings

    merged = origin_text.rstrip("\n") + "\n\n" + "\n\n".join(b.strip("\n") for b in new_blocks) + "\n"
    return merged, new_blocks, warnings


# Progressive disclosure, enforced: MEMORY.md is the pointer layer, the daily log it
# links to is the detail layer. One capped line per session block keeps the index a
# lookup surface instead of a second copy of the recap. The cap has been stated in
# session-recap/SKILL.md since the index existed and never once bound — measured
# 2026-07-25 across all 143 entries: 0% over cap in Mar-Apr, then 97% / 100% / 100%
# for May / Jun / Jul, with the median rising 135 -> 313 -> 783 -> 1538. A stated rule
# is not a control surface here, so the refusal lives at the publish boundary. Entries
# already on origin are grandfathered: publishing is append-only, and the bootstrap
# path takes existing history verbatim.
MAX_INDEX_ENTRY_CHARS = 150


def _entry_label(line: str):
    """The [label] of a MEMORY.md entry line, or None."""
    if line.startswith("- [") and "](" in line:
        return line[3 : line.index("](")]
    return None


def merge_index(origin_text, local_text, cap=MAX_INDEX_ENTRY_CHARS):
    """Merge MEMORY.md: local entry lines origin lacks, inserted newest-first (top).

    Returns (merged_text, new_entries, warnings). Entries dedup on exact line;
    a local entry whose [label] exists on origin with different text is skipped
    with a warning (edited, not appended). A new entry over `cap` is skipped the
    same way — the index is the pointer layer, so the overflow belongs in the
    daily log the entry links to. `pull` passes cap=None: entries already on the
    ref were grandfathered when the cap arrived, and refusing them locally would
    only hide published history.
    """
    warnings = []
    if origin_text is None:
        new = [l for l in local_text.splitlines() if l.startswith("- [")]
        return local_text, new, warnings

    origin_lines = origin_text.splitlines(keepends=True)
    origin_entries = {l.strip() for l in origin_lines if l.startswith("- [")}
    origin_labels = {_entry_label(l) for l in origin_lines if _entry_label(l)}

    new_entries = []
    for line in local_text.splitlines():
        if not line.startswith("- ["):
            continue
        if line.strip() in origin_entries:
            continue
        label = _entry_label(line)
        if label in origin_labels:
            warnings.append(f"edited index entry NOT published (label exists on origin with different text): [{label}]")
            continue
        if cap and len(line.rstrip()) > cap:
            warnings.append(
                f"over-cap index entry NOT published ({len(line.rstrip())} chars > {cap}): "
                f"[{label}] — the index is a pointer line; move the detail into the daily log it links to"
            )
            continue
        new_entries.append(line)

    if not new_entries:
        return origin_text, [], warnings

    # Insert before the first existing entry (list is newest-first); if origin has
    # no entries yet, append at end of file.
    insert_at = next(
        (i for i, l in enumerate(origin_lines) if l.startswith("- [")),
        len(origin_lines),
    )
    inserted = [e.rstrip() + "\n" for e in new_entries]
    merged = "".join(origin_lines[:insert_at] + inserted + origin_lines[insert_at:])
    return merged, new_entries, warnings


def merged_view(origin_text, local_text, rel_path: str):
    """Union view for DISPLAY (session_init): what a reader should see now.

    Pure — no push. Covers the offline / publish-failed case where the checkout
    holds blocks origin lacks, and the stale-mirror case where origin holds
    blocks the checkout lacks.
    """
    if local_text is None:
        return origin_text
    if origin_text is None:
        return local_text
    merge = merge_index if rel_path.endswith("MEMORY.md") else merge_daily
    merged, _, _ = merge(origin_text, local_text)
    return merged


# ---------------------------------------------------------------- transport


def _remote_files():
    """memory/*.md paths present on the ref."""
    rc, out, _ = _git(["ls-tree", "-r", "--name-only", REMOTE_REF, "memory/"])
    return [l for l in _norm(out).splitlines() if l.endswith(".md")] if rc == 0 else []


def pull(dry_run: bool = False):
    """Write the ref's blocks/entries that the local files lack. Returns (changed, warnings).

    The checkout is the working copy a session reads and writes, so a log recapped on
    the other PC has to land here as a file, not only in session_init's merged view.
    """
    changed, warnings = [], []
    for rel in _remote_files():
        origin_text = _origin_text(rel)
        if origin_text is None:
            continue
        path = REPO_ROOT / rel
        local_text = _norm(path.read_bytes()) if path.exists() else None
        if path.name == "MEMORY.md":
            merged, new, warns = merge_index(local_text, origin_text, cap=None)
        else:
            merged, new, warns = merge_daily(local_text, origin_text)
        warnings.extend(f"{rel} (pull): {w}" for w in warns)
        if new and merged is not None and merged != local_text:
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(merged, encoding="utf-8", newline="\n")
            changed.append(f"{rel} +{len(new)}")
    return changed, warnings


def _pending_changes():
    """Compute {rel_path: merged_text} for every memory file with unpublished
    content, plus a list of (rel_path, new_count) summaries and all warnings."""
    changes, summary, warnings = {}, [], []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        rel = f"memory/{path.name}"
        local_text = _norm(path.read_bytes())
        origin_text = _origin_text(rel)
        if path.name == "MEMORY.md":
            merged, new_items, warns = merge_index(origin_text, local_text)
        else:
            merged, new_items, warns = merge_daily(origin_text, local_text, keep=is_recapped)
        warnings.extend(f"{rel}: {w}" for w in warns)
        if new_items and merged is not None and merged != origin_text:
            changes[rel] = merged
            summary.append((rel, len(new_items)))
    return changes, summary, warnings


def _build_and_push(changes: dict) -> bool:
    """Build a memory-only commit on the origin/memory tip (temp index, no
    checkout) and push it. No tip yet -> parentless bootstrap commit.
    Returns True on success."""
    rc, out, _ = _git(["rev-parse", "--verify", "--quiet", REMOTE_REF])
    parent = out.decode().strip() if rc == 0 and out.strip() else None

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        index_path = tf.name
    import os

    env = {**os.environ, "GIT_INDEX_FILE": index_path}
    try:
        read_tree = ["git", "read-tree", REMOTE_REF] if parent else ["git", "read-tree", "--empty"]
        r = subprocess.run(read_tree, cwd=REPO_ROOT, env=env, capture_output=True)
        if r.returncode != 0:
            print(f"[publish-memory] read-tree failed: {r.stderr.decode(errors='replace').strip()}")
            return False
        for rel, text in changes.items():
            rc, out, err = _git(["hash-object", "-w", "--stdin"], input_bytes=text.encode("utf-8"))
            if rc != 0:
                print(f"[publish-memory] hash-object failed for {rel}")
                return False
            blob = out.decode().strip()
            r = subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
            )
            if r.returncode != 0:
                print(f"[publish-memory] update-index failed for {rel}")
                return False
        r = subprocess.run(["git", "write-tree"], cwd=REPO_ROOT, env=env, capture_output=True)
        if r.returncode != 0:
            print("[publish-memory] write-tree failed")
            return False
        tree = r.stdout.decode().strip()
    finally:
        Path(index_path).unlink(missing_ok=True)

    files = ", ".join(sorted(changes))
    if parent:
        msg = f"publish narrative ({files})"
        args = ["commit-tree", tree, "-p", parent, "-m", msg]
    else:
        msg = "bootstrap narrative store"
        args = ["commit-tree", tree, "-m", msg]
    rc, out, _ = _git(args)
    if rc != 0:
        print("[publish-memory] commit-tree failed")
        return False
    commit = out.decode().strip()

    rc, _, err = _git(["push", PUBLISH_REMOTE, f"{commit}:refs/heads/{PUBLISH_BRANCH}"])
    if rc != 0:
        print(f"[publish-memory] push rejected: {err.decode(errors='replace').strip().splitlines()[-1]}")
        return False
    print(f"[publish-memory] pushed {commit[:9]} -> {REMOTE_REF} ({msg})")
    return True


def sync(fetch: bool = True, dry_run: bool = False) -> int:
    """Publish pending narrative. Returns 0 on success/no-op, 1 on failure.

    Offline / push-failure is fail-soft: the checkout keeps the queue and the
    next run publishes. Warnings (edited blocks) always print loudly.
    """
    rc, out, _ = _git(["remote"])
    if rc != 0 or PUBLISH_REMOTE not in out.decode(errors="replace").split():
        print(
            f"[publish-memory] no '{PUBLISH_REMOTE}' remote on this checkout — narrative NOT published; "
            "queue kept. See TODO.md § 'A private remote for what the public repo cannot hold'"
        )
        return 0

    if fetch:
        rc, _, _ = _git(["fetch", PUBLISH_REMOTE])
        if rc != 0:
            print("[publish-memory] offline (fetch failed) — narrative not published; queue kept in checkout")
            return 0

    pulled, pull_warnings = pull(dry_run)
    for w in pull_warnings:
        print(f"[publish-memory] WARNING: {w}")
    if pulled:
        print(f"[publish-memory] {'would pull' if dry_run else 'pulled'} {', '.join(pulled)} from {REMOTE_REF}")

    for attempt in range(MAX_PUSH_RETRIES):
        changes, summary, warnings = _pending_changes()
        for w in warnings:
            print(f"[publish-memory] WARNING: {w}")
        if not changes:
            print(f"[publish-memory] narrative in sync with {REMOTE_REF}")
            return 0
        if dry_run:
            for rel, n in summary:
                print(f"[publish-memory] would publish {rel}: {n} new block(s)/entr(ies)")
            return 0
        if _build_and_push(changes):
            return 0
        # Push lost a race or transport failed — refetch and recompute.
        rc, _, _ = _git(["fetch", PUBLISH_REMOTE])
        if rc != 0:
            break
        print(f"[publish-memory] retrying ({attempt + 2}/{MAX_PUSH_RETRIES})")

    print("[publish-memory] publish FAILED — narrative remains queued in checkout; will retry next run")
    return 1


if __name__ == "__main__":
    sys.exit(sync(dry_run="--dry-run" in sys.argv))

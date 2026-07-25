# TIER: T3 — publish_memory transport: bootstrap + journal-ref push + race union, sandboxed
"""End-to-end publish against a throwaway bare repo (never the real origin).

Proves the git transport under the journal-ref model: first run BOOTSTRAPS
origin/memory (parentless orphan commit) from local files; later runs append
publish commits to it; master is NEVER touched; two folders publishing
divergent same-day blocks converge to the union; re-runs are no-ops. The merge
LOGIC is T1 (test_publish_memory.py); this tier proves the composed pipeline
over real git repos.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_harness"))

import publish_memory

FAILED = []


def check(name, cond, detail=""):
    if cond:
        return
    FAILED.append(name)
    print(f"FAIL: {name} {detail}")


def git(cwd, *args, input_bytes=None):
    r = subprocess.run(["git", *args], cwd=cwd, input=input_bytes, capture_output=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed in {cwd}: {r.stderr.decode(errors='replace')}"
    return r.stdout.decode("utf-8", errors="replace")


def clone(bare, dest):
    subprocess.run(["git", "clone", str(bare), str(dest)], capture_output=True, check=True)
    git(dest, "config", "user.name", "t3")
    git(dest, "config", "user.email", "t3@test")


def point_module_at(repo):
    publish_memory.REPO_ROOT = Path(repo)
    publish_memory.MEMORY_DIR = Path(repo) / "memory"


BASE = "# 2026-07-23\n\n## Session: base\n\nBase story.\n"
BLOCK_A = "\n## Session: from folder A\n\nA's block.\n"
BLOCK_B = "\n## Session: from folder B\n\nB's block.\n"

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "master", str(bare)], capture_output=True, check=True)

    # Seed master with a CODE file only — memory lives outside master's tree.
    repo_a = tmp / "a"
    clone(bare, repo_a)
    (repo_a / "code.py").write_text("# code\n", encoding="utf-8")
    git(repo_a, "add", "code.py")
    git(repo_a, "commit", "-m", "seed code")
    git(repo_a, "push", "origin", "master")
    master_before = git(repo_a, "rev-parse", "origin/master").strip()

    # Local memory files (untracked queue — mirrors the gitignored layout).
    (repo_a / "memory").mkdir()
    daily_a = repo_a / "memory" / "2026-07-23.md"
    daily_a.write_text(BASE, encoding="utf-8", newline="\n")

    # --- first run: BOOTSTRAP origin/memory from local files ---
    point_module_at(repo_a)
    rc = publish_memory.sync()
    check("bootstrap: rc 0", rc == 0)
    origin_daily = git(repo_a, "show", "origin/memory:memory/2026-07-23.md")
    check("bootstrap: content on ref", "Base story." in origin_daily)
    log_mem = git(repo_a, "log", "--oneline", "origin/memory").splitlines()
    check("bootstrap: single orphan commit", len(log_mem) == 1 and "bootstrap narrative store" in log_mem[0], log_mem)

    # --- append from A: publish commit chained on the bootstrap ---
    daily_a.write_text(BASE + BLOCK_A, encoding="utf-8", newline="\n")
    rc = publish_memory.sync()
    check("A publish: rc 0", rc == 0)
    origin_daily = git(repo_a, "show", "origin/memory:memory/2026-07-23.md")
    check("A publish: block on ref", "from folder A" in origin_daily)
    log_mem = git(repo_a, "log", "--oneline", "origin/memory").splitlines()
    check("A publish: chained (2 commits)", len(log_mem) == 2 and "publish narrative" in log_mem[0], log_mem)

    # --- master NEVER touched by any publish ---
    master_after = git(repo_a, "rev-parse", "origin/master").strip()
    check("master untouched", master_before == master_after)
    master_tree = git(repo_a, "ls-tree", "--name-only", "origin/master")
    check("master tree has no memory/", "memory" not in master_tree, master_tree)

    # --- publish from B (feature branch, divergent same-day block) -> union ---
    repo_b = tmp / "b"
    clone(bare, repo_b)
    git(repo_b, "checkout", "-b", "feature")
    git(repo_b, "config", "user.name", "t3")
    git(repo_b, "config", "user.email", "t3@test")
    (repo_b / "memory").mkdir()
    (repo_b / "memory" / "2026-07-23.md").write_text(BASE + BLOCK_B, encoding="utf-8", newline="\n")  # never saw A's block
    point_module_at(repo_b)
    rc = publish_memory.sync()
    check("B publish: rc 0", rc == 0)
    origin_daily = git(repo_b, "show", "origin/memory:memory/2026-07-23.md")
    check("B publish: union has A", "from folder A" in origin_daily)
    check("B publish: union has B", "from folder B" in origin_daily)
    check("B publish: A before B", origin_daily.index("folder A") < origin_daily.index("folder B"))
    check("B publish: base kept once", origin_daily.count("Base story.") == 1)
    check("B publish: stayed on feature", git(repo_b, "branch", "--show-current").strip() == "feature")

    # --- idempotency over transport: re-run publishes nothing new ---
    before = git(repo_b, "rev-parse", "origin/memory").strip()
    rc = publish_memory.sync()
    after = git(repo_b, "rev-parse", "origin/memory").strip()
    check("re-run: no-op", rc == 0 and before == after)

# Restore module globals for any later importer in the same process.
publish_memory.REPO_ROOT = Path(publish_memory.__file__).resolve().parent.parent
publish_memory.MEMORY_DIR = publish_memory.REPO_ROOT / "memory"

if FAILED:
    print(f"\n{len(FAILED)} check(s) FAILED")
    sys.exit(1)
print("PASS: publish_memory transport (bootstrap + journal-ref push + race union + idempotency; master untouched)")

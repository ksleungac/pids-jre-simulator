# SPDX-License-Identifier: MIT
"""Fail when a tracked file is matched by the repo's own .gitignore.

Adding an ignore rule does NOT untrack anything — `git rm --cached` does. The two
steps look like one, so an ignore rule lands alone and the file keeps shipping in
every clone while the commit message says it is gone. That is how three Morisawa
faces stayed on master for eleven days after the commit that claimed to remove
them (2026-08-08 -> 2026-08-19; docs/wip/WIP_font_atlas.md, docs/wip/WIP_licensing.md).

Repo ignores only (--exclude-per-directory), never the user's global excludes: a
machine-local ~/.config/git/ignore shadowing a deliberately tracked file is a
per-machine fact, not a repo contradiction.
"""

import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")  # conventions.md § Tooling: Windows pipes are cp1252

out = subprocess.run(
    ["git", "ls-files", "-i", "-c", "--exclude-per-directory=.gitignore"],
    capture_output=True,
    text=True,
)
if out.returncode != 0:
    print(out.stderr.strip() or "git ls-files failed")
    sys.exit(1)

offenders = [ln for ln in out.stdout.splitlines() if ln.strip()]
if offenders:
    print("Tracked files matched by .gitignore — the ignore rule did not untrack them:")
    for f in offenders:
        print(f"  {f}")
    print("\nUntrack them (files stay on disk):")
    print("  git rm --cached " + " ".join(offenders))
    sys.exit(1)

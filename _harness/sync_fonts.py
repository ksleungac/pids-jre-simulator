# SPDX-License-Identifier: MIT
"""Sync the local-only font software across machines via the `private/fonts` ref.

The Morisawa Shin Go faces left the public tree in `62133d4` (THIRD-PARTY.md
§ Fonts), correctly — and nothing replaced the transport, so each face existed
only on whichever machine it was installed on. That is what stranded
`ShinGoPro-DeBold.otf` on one PC while the other could not render E233-0 at all.

This carries them on an orphan `fonts` ref on the PRIVATE remote, alongside the
narrative memory ref. Same design as publish_memory.py: git plumbing on a temp
index, so no branch switch and no working-tree churn, and it runs identically
from master, a feature branch or a worktree.

# CONTRACT: the file set is DERIVED, never enumerated here. `.gitignore` already
# owns which faces are local-only (it carries three patterns for Morisawa's
# naming variants), so the domain is "ignored + untracked under fonts/" straight
# from git. A glob typed into this file would be a second copy of that answer.

# CONTRACT: pull WRITES BYTES, never the index. `git checkout private/fonts --
# fonts/` would stage gitignored files and trip the no-tracked-ignored hook.

A pull only ever fills an ABSENT file. A local file whose bytes differ from the
ref is reported and left alone — font software does not legitimately change, so
a difference is a question for the author, not something to resolve silently.

Usage:
    uv run _harness/sync_fonts.py             # pull anything this machine lacks
    uv run _harness/sync_fonts.py --push      # publish this machine's faces
    uv run _harness/sync_fonts.py --status    # report both directions, write nothing
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_REMOTE = "private"
FONTS_BRANCH = "fonts"
REMOTE_REF = f"{PRIVATE_REMOTE}/{FONTS_BRANCH}"


# ---------------------------------------------------------------- git helpers


def _git(args, input_bytes=None):
    """Run git in the repo root. Returns (returncode, stdout_bytes, stderr_bytes)."""
    r = subprocess.run(["git", *args], cwd=REPO_ROOT, input=input_bytes, capture_output=True)
    return r.returncode, r.stdout, r.stderr


def have_remote() -> bool:
    """True when the private remote is configured on this checkout."""
    rc, out, _ = _git(["remote"])
    return rc == 0 and PRIVATE_REMOTE in out.decode(errors="replace").split()


def fetch() -> bool:
    """Fetch the private remote. False when offline or unauthorized (fail-soft)."""
    rc, _, _ = _git(["fetch", PRIVATE_REMOTE])
    return rc == 0


# ---------------------------------------------------------------- the two sides


def local_files():
    """Ignored-and-untracked paths under fonts/ — the faces this machine holds.

    Derived from .gitignore via git itself; see the CONTRACT above.
    """
    rc, out, _ = _git(["ls-files", "--others", "--ignored", "--exclude-standard", "--", "fonts/"])
    if rc != 0:
        return []
    return sorted(l for l in out.decode("utf-8", errors="replace").splitlines() if l.strip())


def ref_files():
    """{rel_path: blob_sha} on the fonts ref, or {} when the ref does not exist."""
    rc, out, _ = _git(["ls-tree", "-r", REMOTE_REF])
    if rc != 0:
        return {}
    files = {}
    for line in out.decode("utf-8", errors="replace").splitlines():
        meta, _, rel = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and rel.strip():
            files[rel.strip()] = parts[2]
    return files


def _blob_sha(rel: str):
    """The sha git WOULD give the working-tree file, without writing it."""
    rc, out, _ = _git(["hash-object", "--", rel])
    return out.decode().strip() if rc == 0 else None


def classify():
    """(missing_here, missing_on_ref, differing) as sorted rel-path lists."""
    ref = ref_files()
    local = set(local_files())
    missing_here = sorted(r for r in ref if not (REPO_ROOT / r).exists())
    missing_on_ref = sorted(local - set(ref))
    differing = sorted(r for r in ref if (REPO_ROOT / r).exists() and _blob_sha(r) != ref[r])
    return missing_here, missing_on_ref, differing


# ---------------------------------------------------------------- pull / push


def pull(dry_run: bool = False) -> int:
    """Write every ref file this machine lacks. Returns the count written."""
    ref = ref_files()
    missing_here, _, differing = classify()
    for rel in differing:
        print(f"[sync-fonts] WARNING: {rel} differs from the ref and was NOT overwritten — resolve by hand")
    written = 0
    for rel in missing_here:
        if dry_run:
            print(f"[sync-fonts] would write {rel}")
            continue
        rc, blob, _ = _git(["cat-file", "blob", ref[rel]])
        if rc != 0:
            print(f"[sync-fonts] failed to read {rel} from {REMOTE_REF}")
            continue
        dest = REPO_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        print(f"[sync-fonts] wrote {rel} ({len(blob):,} bytes)")
        written += 1
    return written


def push(dry_run: bool = False) -> int:
    """Publish this machine's faces onto the fonts ref. Returns 0 on success/no-op."""
    local = local_files()
    if not local:
        print("[sync-fonts] no local-only fonts to publish")
        return 0
    _, missing_on_ref, differing = classify()
    for rel in differing:
        print(f"[sync-fonts] WARNING: {rel} differs from the ref — publishing this machine's copy would replace it; skipped")
    if not missing_on_ref:
        print(f"[sync-fonts] {REMOTE_REF} already carries every face on this machine")
        return 0
    if dry_run:
        for rel in missing_on_ref:
            print(f"[sync-fonts] would publish {rel}")
        return 0

    rc, out, _ = _git(["rev-parse", "--verify", "--quiet", REMOTE_REF])
    parent = out.decode().strip() if rc == 0 and out.strip() else None

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        index_path = tf.name
    env = {**os.environ, "GIT_INDEX_FILE": index_path}
    try:
        read_tree = ["git", "read-tree", REMOTE_REF] if parent else ["git", "read-tree", "--empty"]
        if subprocess.run(read_tree, cwd=REPO_ROOT, env=env, capture_output=True).returncode != 0:
            print("[sync-fonts] read-tree failed")
            return 1
        for rel in missing_on_ref:
            rc, out, _ = _git(["hash-object", "-w", "--", rel])
            if rc != 0:
                print(f"[sync-fonts] hash-object failed for {rel}")
                return 1
            blob = out.decode().strip()
            r = subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
            )
            if r.returncode != 0:
                print(f"[sync-fonts] update-index failed for {rel}")
                return 1
        r = subprocess.run(["git", "write-tree"], cwd=REPO_ROOT, env=env, capture_output=True)
        if r.returncode != 0:
            print("[sync-fonts] write-tree failed")
            return 1
        tree = r.stdout.decode().strip()
    finally:
        Path(index_path).unlink(missing_ok=True)

    msg = "add " + ", ".join(Path(r).name for r in missing_on_ref)
    args = ["commit-tree", tree, "-m", msg] + (["-p", parent] if parent else [])
    rc, out, _ = _git(args)
    if rc != 0:
        print("[sync-fonts] commit-tree failed")
        return 1
    commit = out.decode().strip()

    rc, _, err = _git(["push", PRIVATE_REMOTE, f"{commit}:refs/heads/{FONTS_BRANCH}"])
    if rc != 0:
        tail = err.decode(errors="replace").strip().splitlines()
        print(f"[sync-fonts] push rejected: {tail[-1] if tail else '?'}")
        return 1
    print(f"[sync-fonts] pushed {commit[:9]} -> {REMOTE_REF} ({msg})")
    return 0


# ---------------------------------------------------------------- reporting


def report_lines():
    """Session-start report: what this machine is missing. [] when all is well.

    The REF is the manifest — a face nobody has pushed yet cannot be reported,
    which is why a machine holding a face it has not published is also named.
    """
    if not have_remote():
        return [f"no '{PRIVATE_REMOTE}' remote — font sync unavailable (TODO.md § A private remote…)"]
    missing_here, missing_on_ref, differing = classify()
    lines = []
    for rel in missing_here:
        lines.append(f"MISSING: {rel} — on {REMOTE_REF} but not on this machine. `uv run _harness/sync_fonts.py`")
    for rel in missing_on_ref:
        lines.append(f"unpublished: {rel} — only on this machine. `uv run _harness/sync_fonts.py --push`")
    for rel in differing:
        lines.append(f"DIFFERS: {rel} — local bytes differ from {REMOTE_REF}")
    return lines


def print_report():
    """Print the report under a heading, or nothing at all when in sync."""
    lines = report_lines()
    if not lines:
        return
    print("=== Fonts (private ref) ===")
    for line in lines:
        print(f"  {line}")
    print()


def main(argv) -> int:
    if not have_remote():
        print(f"[sync-fonts] no '{PRIVATE_REMOTE}' remote configured — nothing to do")
        return 0
    if not fetch():
        print(f"[sync-fonts] offline or unauthorized (fetch {PRIVATE_REMOTE} failed) — nothing written")
        return 0
    dry = "--dry-run" in argv
    if "--status" in argv:
        lines = report_lines()
        print("\n".join(f"[sync-fonts] {l}" for l in lines) if lines else f"[sync-fonts] in sync with {REMOTE_REF}")
        return 0
    if "--push" in argv:
        return push(dry_run=dry)
    pull(dry_run=dry)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

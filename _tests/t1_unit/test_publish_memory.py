# SPDX-License-Identifier: MIT
# TIER: T1 — publish_memory merge logic (daily-log block merge + MEMORY.md entry merge)
"""Pure-function tests for _harness/publish_memory.py merge logic.

The transport (git plumbing) is thin and exercised by --dry-run; the
regression-worthy logic is the mechanical merge: dedup, divergence union,
edited-block refusal, over-cap index refusal, idempotency. Expected values are
pinned literally — never derived from the module under test, so the 150-char cap
is typed here rather than imported and mutating the constant fails the test.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_harness"))

from publish_memory import merge_daily, merge_index, merged_view, split_daily

FAILED = []


def check(name, cond, detail=""):
    if cond:
        return
    FAILED.append(name)
    print(f"FAIL: {name} {detail}")


# ---------------------------------------------------------------- fixtures

BASE = "# 2026-07-23\n\n## Session: alpha work\n\nDid alpha things.\nMore alpha.\n"
BLOCK_A = "## Session: concurrent A\n\nA's story.\n"
BLOCK_B = "## Session: concurrent B\n\nB's story.\n"


# ---------------------------------------------------------------- split_daily

pre, blocks = split_daily(BASE)
check("split: preamble", pre == "# 2026-07-23\n\n")
check("split: one block", len(blocks) == 1)
check("split: lossless", pre + "".join(blocks) == BASE)

pre2, blocks2 = split_daily(BASE + "\n" + BLOCK_A)
check("split: two blocks", len(blocks2) == 2)
check("split: lossless 2", pre2 + "".join(blocks2) == BASE + "\n" + BLOCK_A)


# ---------------------------------------------------------------- merge_daily

# No-op: identical -> origin returned byte-exact, zero new.
m, new, warns = merge_daily(BASE, BASE)
check("daily noop: unchanged", m == BASE)
check("daily noop: no new", new == [] and warns == [])

# Local suffix: origin + one appended block.
local = BASE + "\n" + BLOCK_B
m, new, warns = merge_daily(BASE, local)
check("daily suffix: 1 new", len(new) == 1)
check(
    "daily suffix: merged literal",
    m == "# 2026-07-23\n\n## Session: alpha work\n\nDid alpha things.\nMore alpha.\n\n## Session: concurrent B\n\nB's story.\n",
    f"got {m!r}",
)

# Diverged: origin gained A, local gained B off the same base -> union, A before B.
origin_d = BASE + "\n" + BLOCK_A
local_d = BASE + "\n" + BLOCK_B
m, new, warns = merge_daily(origin_d, local_d)
check("daily diverged: 1 new", len(new) == 1)
check("daily diverged: keeps A", "## Session: concurrent A" in m)
check("daily diverged: appends B", m.index("concurrent A") < m.index("concurrent B"))
check("daily diverged: B present once", m.count("B's story.") == 1)

# Idempotency: merging the merged result with the same local adds nothing.
m2, new2, _ = merge_daily(m, local_d)
check("daily idempotent", m2 == m and new2 == [])

# Edited block (same heading, different body): refused with warning, origin untouched.
edited = "# 2026-07-23\n\n## Session: alpha work\n\nREWRITTEN body.\n"
m, new, warns = merge_daily(BASE, edited)
check("daily edited: refused", m == BASE and new == [])
check("daily edited: warned", len(warns) == 1 and "alpha work" in warns[0])

# New file on origin: local publishes verbatim.
m, new, warns = merge_daily(None, BASE)
check("daily new file: verbatim", m == BASE and len(new) == 1)


# ---------------------------------------------------------------- merge_index

IDX_HEADER = "# Memory Index\n\nLong-term curated memories.\n\n---\n\n"
E_OLD = "- [2026-07-22 old](2026-07-22.md) — old headline"
E_NEW = "- [2026-07-23 fresh](2026-07-23.md) — fresh headline"
E_OTHER = "- [2026-07-23 other](2026-07-23.md) — other session's headline"

origin_idx = IDX_HEADER + E_OLD + "\n"
local_idx = IDX_HEADER + E_NEW + "\n" + E_OLD + "\n"

# New entry inserted at TOP of entry list (newest-first).
m, new, warns = merge_index(origin_idx, local_idx)
check("index: 1 new", len(new) == 1)
check("index: literal", m == IDX_HEADER + E_NEW + "\n" + E_OLD + "\n", f"got {m!r}")

# No-op.
m, new, _ = merge_index(origin_idx, origin_idx)
check("index noop", m == origin_idx and new == [])

# Diverged: origin gained OTHER, local gained NEW -> both kept, local's on top.
origin_div = IDX_HEADER + E_OTHER + "\n" + E_OLD + "\n"
m, new, _ = merge_index(origin_div, local_idx)
check("index diverged: both", E_OTHER in m and E_NEW in m)
check("index diverged: literal", m == IDX_HEADER + E_NEW + "\n" + E_OTHER + "\n" + E_OLD + "\n")

# Idempotency.
m2, new2, _ = merge_index(m, local_idx)
check("index idempotent", m2 == m and new2 == [])

# Edited entry (same [label], different text): refused with warning.
edited_idx = IDX_HEADER + "- [2026-07-22 old](2026-07-22.md) — REWORDED headline\n"
m, new, warns = merge_index(origin_idx, edited_idx)
check("index edited: refused", m == origin_idx and new == [])
check("index edited: warned", len(warns) == 1 and "2026-07-22 old" in warns[0])

# Over-cap entry: refused with warning. The index is the pointer layer — a
# recap-sized entry belongs in the daily log it links to. Cap pinned literally at 150.
E_PREFIX = "- [2026-07-25 long](2026-07-25.md) — "
E_AT_CAP = E_PREFIX + "x" * 113
E_OVER_CAP = E_PREFIX + "x" * 114
check("cap fixture: at-cap is exactly 150", len(E_AT_CAP) == 150, f"got {len(E_AT_CAP)}")
check("cap fixture: over-cap is 151", len(E_OVER_CAP) == 151, f"got {len(E_OVER_CAP)}")

m, new, warns = merge_index(origin_idx, IDX_HEADER + E_OVER_CAP + "\n" + E_OLD + "\n")
check("index over-cap: refused", m == origin_idx and new == [])
check("index over-cap: warned", len(warns) == 1 and "over-cap" in warns[0], f"got {warns!r}")

# Boundary: exactly at the cap still publishes (the gate is >, not >=).
m, new, warns = merge_index(origin_idx, IDX_HEADER + E_AT_CAP + "\n" + E_OLD + "\n")
check("index at-cap: publishes", new == [E_AT_CAP] and warns == [], f"got {new!r} {warns!r}")


# ---------------------------------------------------------------- merged_view

check("view: origin only", merged_view(BASE, None, "memory/2026-07-23.md") == BASE)
check("view: local only", merged_view(None, BASE, "memory/2026-07-23.md") == BASE)
v = merged_view(origin_d, local_d, "memory/2026-07-23.md")
check("view: union", "concurrent A" in v and "concurrent B" in v)
vi = merged_view(origin_div, local_idx, "memory/MEMORY.md")
check("view: index dispatch", E_OTHER in vi and E_NEW in vi)


# ---------------------------------------------------------------- verdict

if FAILED:
    print(f"\n{len(FAILED)} check(s) FAILED")
    sys.exit(1)
print("PASS: publish_memory merge logic (daily blocks + index entries + merged view)")

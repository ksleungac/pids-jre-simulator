# SPDX-License-Identifier: MIT
# TIER: T1 — memory-loop tracker: per-session pending edits, log clears, orphan adoption
"""Pure-function tests for _harness/memory_loop.py's tracker.

Several sessions share one working tree, so the tracker's whole job is to keep their
edits apart: one session's log line must not clear another's pending edits, and a
running parallel session's edits must not be handed to a new one. These are the
cases that would let the Stop hook block the wrong session or let edits go unlogged.
"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_harness"))

from memory_loop import adopt_orphans, in_progress_days, pending_for, record_edit

FAILED = []


def check(name, cond, detail=""):
    if cond:
        return
    FAILED.append(name)
    print(f"FAIL: {name} {detail}")


TODAY = datetime.date(2026, 11, 9)
NOW = datetime.datetime(2026, 11, 9, 22, 0, 0)
LOG = "memory/2026-11-09.md"


# ---------------------------------------------------------------- record_edit

s = {}
s = record_edit(s, "A", "app.py", NOW, TODAY)
s = record_edit(s, "B", "tims/band.py", NOW, TODAY)
check("edit: A pending", pending_for(s, "A") == ["app.py"])
check("edit: B pending", pending_for(s, "B") == ["tims/band.py"])

s = record_edit(s, "A", LOG, NOW, TODAY)
check("log: clears A", pending_for(s, "A") == [])
check("log: leaves B", pending_for(s, "B") == ["tims/band.py"], repr(s))

for rel in ("memory/MEMORY.md", "memory/2026-11-08.md", ".claude/state/memory-loop.json", None):
    before = repr(s)
    s = record_edit(s, "A", rel, NOW, TODAY)
    check(f"ignored: {rel}", repr(s) == before)

check("unknown session: empty", pending_for(s, "Z") == [])


# ---------------------------------------------------------------- adopt_orphans

old = (NOW - datetime.timedelta(hours=7)).isoformat()
recent = (NOW - datetime.timedelta(minutes=20)).isoformat()
state = {
    "sessions": {
        "dead": {"pending": {"route_loader.py": old}, "seen": old},
        "live": {"pending": {"displays/base.py": recent}, "seen": recent},
        "idle": {"pending": {}, "seen": old},
    }
}
state, adopted, live = adopt_orphans(state, "new", NOW)
check("orphans: dead adopted", adopted == ["route_loader.py"], repr(adopted))
check("orphans: now this session's", pending_for(state, "new") == ["route_loader.py"])
check("orphans: dead dropped", "dead" not in state["sessions"])
check("orphans: live reported only", live == ["displays/base.py"] and pending_for(state, "live") == ["displays/base.py"])
check("orphans: idle pruned", "idle" not in state["sessions"])


# ---------------------------------------------------------------- in_progress_days

logs = [
    ("2026-11-09", "# 2026-11-09\n\n## Session: in progress — harness\n\n- step\n"),
    ("2026-11-08", "# 2026-11-08\n\n## Session: recapped\n\nStory.\n\n**Codifications:** none\n"),
]
check("in-progress: only the open day", in_progress_days(logs) == ["2026-11-09"])


if FAILED:
    print(f"\n{len(FAILED)} check(s) FAILED")
    sys.exit(1)
print("PASS: memory_loop tracker (per-session pending, log clears, orphan adoption)")

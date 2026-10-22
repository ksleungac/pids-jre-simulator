# SPDX-License-Identifier: MIT
"""Ratchet the preloaded rules corpus so it cannot grow back.

The rules files carry their own EDIT-CONTRACT with hard numbers, and those numbers
were violated at scale for months — `principles.md` sat at 70 entries against its
own cap of 30. Nothing enforced them, because a cap written in prose competes for
attention with 33k tokens of sibling rules and loses. `principles.md` § "Preloaded
mental model" records the identical pathology one artifact over: the MEMORY.md cap
"stated and unread for three months at 97-100% violation", concluding that rules do
not reach that bar and gates do.

So this is a RATCHET, not the contract's aspirational cap. It fails when a measure
gets WORSE than the recorded baseline, which is what "getting fatter over time"
actually means. Gating at the contract's 30 would fail every commit today and be
disabled within a week; gating at today's value stops regrowth immediately and lets
the caps be approached deliberately. Lower a BASELINE number whenever a distill pass
improves it — that is the ratchet tightening, and it is the only edit this file
should normally need.

Usage:
    uv run _dev_scripts/check_rules_corpus.py            # check (pre-commit)
    uv run _dev_scripts/check_rules_corpus.py --report   # print measures, never fail
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RULES = Path(__file__).resolve().parent.parent / ".claude" / "rules"

# Recorded 2026-10-22, after domain rules moved into path-scoped files (principles.md
# 49 -> 32 entries, conventions.md 108 -> 24 bullets, critical_lessons.md 11 -> 6).
# Each value is a CEILING: equal is fine, greater fails. Tighten as passes land.
#
# `tails` is HARD at 0 — a sibling cross-ref tail is on both contracts' refuse-list,
# so there is no legitimate first one. `entries` and `worst_entry_words` carry a few
# percent, since a genuine new rule is legitimate growth and only bloat is not
# (`docs.md` § "Preloaded mental model": a rule earns removal by being wrong,
# never by redundancy). `words` carries ~5% as a slow-drift alarm rather than a fence:
# it is the measure that catches a file getting fatter without gaining rules.
# fmt: off
BASELINE = {
    "principles.md":       {"entries":  33, "words": 13200, "worst_entry_words": 1050, "tails": 0},
    "conventions.md":      {"entries":  25, "words":  3650, "worst_entry_words":  320, "tails": 0},
    "critical_lessons.md": {"entries":   7, "words":  1550, "worst_entry_words":  490, "tails": 0},
}
# fmt: on

# The ALWAYS-LOADED budget, in characters: `CLAUDE.md` plus every rules file with no
# `paths:` frontmatter. Claude Code warns once the instruction files loaded at session
# start add up past ~150k; the author's global `~/.claude/CLAUDE.md` takes ~1.6k of that,
# so the repo's share is capped below it. A path-scoped file loads only when a matching
# file is read or edited, so it is not counted. Over budget means a domain rule is sitting
# in an always-loaded file: move it to the path-scoped file for its domain (2026-10-22).
ALWAYS_LOADED_CHARS = 148_000
REPO = RULES.parent.parent
PATHS_RE = re.compile(r"\A---\n(?:.*\n)*?paths:", re.M)

# Sibling cross-ref tails: both preloaded contracts put these on their refuse-list.
# `conventions.md`'s own contract quotes the first three verbatim as what to strip.
TAIL_RE = re.compile(r"\b(Sibling to|Pairs with|Same family as|Distinct from|Complements §)\b")


def _entry_word_counts(text: str, path_name: str) -> list[int]:
    """Words per entry. `principles.md` and `critical_lessons.md` use headings;
    `conventions.md` states its rules as top-level bullets with sub-bullets."""
    if path_name == "conventions.md":
        counts: list[int] = []
        cur: int | None = None
        for line in text.splitlines():
            if re.match(r"^- ", line):
                if cur is not None:
                    counts.append(cur)
                cur = len(line.split())
            elif re.match(r"^ +- ", line) and cur is not None:
                cur += len(line.split())
        if cur is not None:
            counts.append(cur)
        return counts

    marker = "### " if path_name == "principles.md" else "## "
    counts, cur = [], None
    for line in text.splitlines():
        if line.startswith(marker):
            if cur is not None:
                counts.append(cur)
            cur = 0
        elif cur is not None:
            cur += len(line.split())
    if cur is not None:
        counts.append(cur)
    return counts


def measure(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    # The contract block is the gate itself, never counted against the file.
    body = re.sub(r"<!-- EDIT-CONTRACT.*?-->", "", text, flags=re.S)
    per_entry = _entry_word_counts(body, path.name)
    return {
        "entries": len(per_entry),
        "words": len(body.split()),
        "worst_entry_words": max(per_entry) if per_entry else 0,
        # Skip the contract's own quoted examples by measuring the body only.
        "tails": len(TAIL_RE.findall(body)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print measures, never fail")
    # pre-commit passes the staged filenames; we always check the whole corpus.
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()

    failures: list[str] = []
    for name, caps in BASELINE.items():
        path = RULES / name
        if not path.exists():
            failures.append(f"{name}: missing from {RULES}")
            continue
        got = measure(path)
        for key, cap in caps.items():
            if args.report:
                continue
            if got[key] > cap:
                failures.append(
                    f"{name}: {key} {got[key]} exceeds baseline {cap} (+{got[key] - cap}). "
                    f"Fold or trim, or lower the baseline if this pass improved it."
                )
        if args.report:
            print(f"{name}")
            for key, cap in caps.items():
                slack = cap - got[key]
                print(f"    {key:18} {got[key]:6}   baseline {cap:6}   slack {slack:+}")

    # Every rules file, scoped or not: a tail has no legitimate first one.
    for path in sorted(RULES.glob("*.md")):
        if path.name not in BASELINE:
            n = len(TAIL_RE.findall(path.read_text(encoding="utf-8")))
            if n and not args.report:
                failures.append(f"{path.name}: tails {n} exceeds baseline 0")

    loaded = [REPO / "CLAUDE.md"] + [p for p in sorted(RULES.glob("*.md")) if not PATHS_RE.match(p.read_text(encoding="utf-8").replace("\r\n", "\n"))]
    total = sum(len(p.read_text(encoding="utf-8")) for p in loaded)
    if args.report:
        names = ", ".join(p.name for p in loaded)
        print(f"always-loaded       {total:6} chars   budget {ALWAYS_LOADED_CHARS}   ({names})")
    elif total > ALWAYS_LOADED_CHARS:
        failures.append(
            f"always-loaded corpus {total} chars exceeds budget {ALWAYS_LOADED_CHARS} "
            f"(+{total - ALWAYS_LOADED_CHARS}). Move domain rules to a path-scoped file."
        )

    if failures:
        print("Rules corpus grew (harness.md § Tooling, sensor tiers):")
        for f in failures:
            print(f"  - {f}")
        return 1
    if not args.report:
        print("rules corpus within baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())

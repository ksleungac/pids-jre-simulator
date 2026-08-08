#!/usr/bin/env python
# SPDX-License-Identifier: MIT
"""Test-suite runner + live coverage map. `_tests/README.md` defines the hierarchy.

Runs every test in the physical tiers (t1_unit / t3_invariant / t4_clean_frame) and
prints ONE status line per tier. An empty tier prints a loud `NO TESTS (gap)` line
(fail-loud ethos) but does NOT fail the run — a gap is visible, never a silent pass.
Exit 1 iff a test actually FAILS. External gates (T0 linters, T2 validators) and the
manual T5/rendering tiers are indexed here by reference, not re-run.

Dev-only harness (`_tests/` is `_`-prefixed → never shipped, never scanned by the
production-primitive linters), so `Path(__file__)` here is fine — not a production path.

Wire into `/build` pre-flight next to `_harness/check_deps.py`.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# (tier label, purpose, kind, target)
#   kind="dir"      -> physical tests in _tests/<target>/test_*.py (run them)
#   kind="external" -> wired gate elsewhere; referenced, not re-run here
#   kind="manual"   -> by-eye / not automatable
TIERS = [
    (
        "T0 Static",
        "code shape — banned primitives, derivable literals, .otf, Black",
        "external",
        "pre-commit: _dev_scripts/lint_primitives.py, check_fonts.py",
    ),
    ("T1 Unit", "pure function I/O — no pygame, no I/O", "dir", "t1_unit"),
    ("T2 Contract", "authored data conforms + cross-file parity", "external", "validate_data.py (root)"),
    ("T3 Invariant", "cross-module behavior over real files, headless (no display)", "dir", "t3_invariant"),
    ("T4 Clean-frame", "first-run / OOBE from a deleted settings.json", "dir", "t4_clean_frame"),
    ("T5 Smoke/E2E", "built exe boots + frozen-only paths", "manual", "run against the exe post-build"),
    ("Rendering", "pixel fidelity", "manual", "EXCLUDED - by-eye by design"),
]


def _run_dir(target: str):
    d = ROOT / target
    tests = sorted(d.glob("test_*.py")) if d.is_dir() else []
    results = []
    for t in tests:
        # Decode child output as utf-8 (tests reconfigure stdout to utf-8 and print
        # Japanese); the Windows default cp1252 would crash the reader thread on
        # non-cp1252 bytes. errors="replace" is a belt-and-suspenders. (conventions.md
        # § Tooling "reconfigure(encoding=utf-8)".)
        r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        results.append((t.name, r.returncode, (r.stdout or "") + (r.stderr or "")))
    return results


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    any_fail = False
    print("=== _tests coverage map  (hierarchy: _tests/README.md) ===\n")
    for label, purpose, kind, target in TIERS:
        if kind == "dir":
            results = _run_dir(target)
            if not results:
                print(f"  {label:15} NO TESTS (gap)     -- {purpose}")
                continue
            for name, rc, output in results:
                if rc == 0:
                    print(f"  {label:15} PASS  {name}")
                else:
                    any_fail = True
                    print(f"  {label:15} FAIL  {name}")
                    tail = output.strip()
                    if tail:
                        print("      " + tail.replace("\n", "\n      "))
        elif kind == "external":
            print(f"  {label:15} wired externally   -- {target}")
        else:  # manual
            print(f"  {label:15} manual / gap       -- {target}")

    print()
    if any_fail:
        print("FAIL - a test failed.")
        return 1
    print("OK - no test failures (gaps above are visible, not blocking).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

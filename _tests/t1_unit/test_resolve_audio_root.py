"""T1 — route_loader.resolve_audio_root: the single audio-path resolver.

Every shipped line's audio lives in a per-line pool (`audio/<line>/{pa,sta}/`) while its
route.json sits one level deeper, so EVERY reference in the app passes through this function.
It had no test until 2026-08-08, which is also when two sites that bypassed it were found
silently broken by the pooling — the OOBE tutorial's asset pre-flight and the auto-driver's
long-approach probe.

Expected paths are pinned LITERALLY rather than imported from the module: a test that reads
the default out of the code under test scales its own expectations with any mutation of that
default and stops discriminating (`principles.md` § "Test real logic, not ceremony").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from route_loader import resolve_audio_root  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def main() -> int:
    wd = Path("audio/tokaido/1865E")

    # ".." — the pool. Every shipped route.json carries this.
    got = resolve_audio_root(wd, {"audio_root": ".."})
    check(got == (wd / "..").resolve(), f'audio_root ".." must resolve to the line folder, got {got}')
    check(got.name == "tokaido", f'audio_root ".." must land on audio/tokaido, got {got.name}')

    # Absent — audio beside route.json. Still used by _mock/main and _joban/tsuchiura.
    got = resolve_audio_root(wd, {})
    check(Path(got) == wd, f"absent audio_root must return the work_dir unchanged, got {got}")

    # "." — beside route.json, stated explicitly.
    got = resolve_audio_root(wd, {"audio_root": "."})
    check(got == wd.resolve(), f'audio_root "." must resolve to the work_dir, got {got}')

    # A str work_dir is what app.py hands it (self.work_dir).
    got = resolve_audio_root(str(wd), {"audio_root": ".."})
    check(got.name == "tokaido", f"str work_dir must behave like Path, got {got}")

    # THE contract: exactly one root, NO search order. The property that distinguishes it
    # from a fallback design is that the answer depends only on the declared value — never
    # on what happens to be on disk. A fallback would let a missing file resolve to a
    # different root and play the WRONG announcement (critical_lessons.md §2).
    #
    # An earlier version of this test asserted `pooled != wd.resolve()`, which is true by
    # construction for any implementation — a claim about pathlib, not about this function.
    # A resolver implementing exactly the forbidden fallback passed it.
    empty = Path("audio/_nonexistent_line/_nonexistent_diagram")
    declared = resolve_audio_root(empty, {"audio_root": ".."})
    check(
        declared == (empty / "..").resolve(),
        f"root must follow the DECLARED value even when that folder holds no pa/ or sta/ "
        f"(a fallback would divert to the work_dir here), got {declared}",
    )
    check(
        Path(declared) != empty.resolve(),
        "root must not fall back to the work_dir when the declared pool is empty — that is a search order",
    )

    for msg in FAILURES:
        print(f"  FAIL: {msg}")
    print(f"resolve_audio_root: {'PASS' if not FAILURES else f'{len(FAILURES)} FAILURE(S)'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

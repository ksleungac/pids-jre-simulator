# SPDX-License-Identifier: MIT
"""Require an SPDX licence identifier in every Python file's header.

`LICENSE` grants MIT over authored code and documentation only; every other
class in the tree — audio, fonts, operator marks, game-derived assets — is
carved out in `THIRD-PARTY.md`. A per-file identifier is what makes that split
machine-readable, so a reader (or a tool) knows which half a given file is in
without applying the scope note by judgment.

This gate exists because the headers are otherwise write-once: 124 files were
tagged in one pass, and without a check every file added afterwards silently
lowers coverage. See docs/wip/WIP_licensing.md.
"""

import sys

TAG = "SPDX-License-Identifier: MIT"

# A header, not a mention. Three lines is what the deepest legal prologue needs:
# a shebang, a PEP 263 coding declaration (which must itself stay in the first
# two lines), then the tag. Scanning the whole file would pass on any module that
# merely talks about SPDX — this file being the obvious one.
HEADER_LINES = 3


def head_of(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return [line for _, line in zip(range(HEADER_LINES), fh)]


def main(paths: list[str]) -> int:
    missing = [p for p in paths if not any(TAG in line for line in head_of(p))]
    for p in missing:
        print(f"{p}: no `# {TAG}` in the first {HEADER_LINES} lines. See docs/wip/WIP_licensing.md.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# SPDX-License-Identifier: MIT
# TIER: T1 — the QR encoder behind the mirror address
"""T1 — `qr.py`, the encoder that puts the mirror's address on a phone.

Module scope is the FEATURE. A QR is the one thing in this app whose output nobody can eyeball:
a matrix with a single wrong module is indistinguishable, to a reader, from a correct one, and it
fails at the only moment that matters — someone standing there with a phone. Three oracles, in
descending order of independence:

  1. FORMAT INFORMATION vs the published table (ISO/IEC 18004 Annex C). Fully independent of this
     implementation, and it is where the encoder was actually wrong: the two copies of the format
     word are indexed in OPPOSITE directions, which one wrong guess makes decode for three of the
     eight masks and another makes decode for none.
  2. STRUCTURE — finder eyes, timing, the dark module. Stated by the standard, not by the code.
  3. REGRESSION FIXTURES — matrices this encoder produced and `cv2.QRCodeDetector` decoded back to
     the exact input string at generation time. Their provenance is a real decode, not agreement
     with the code (`principles.md` § "A fixture is not an observation"). opencv is NOT a project
     dependency, so the decode happened once via `uvx --with opencv-python-headless`; regenerating
     these means re-running that decode, never copying whatever the encoder currently emits.

Not asserted: byte-identity with another encoder. `segno` on the same input emits one extra 0x00
pad codeword, so the matrices legitimately differ while both decode — comparing them would fail on
a difference that is not a defect.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import qr  # noqa: E402

# ── 1. format information — the independent oracle ────────────────────────────
# ISO/IEC 18004 Annex C, error-correction level L, masks 0-7, written MSB first.
FORMAT_L = [
    "111011111000100",
    "111001011110011",
    "111110110101010",
    "111100010011101",
    "110011000101111",
    "110001100011000",
    "110110001000001",
    "110100101110110",
]

# ── 3. regression fixtures ────────────────────────────────────────────────────
# '#' = dark. See the module docstring for how these were obtained; both decoded back to their own
# key under cv2.QRCodeDetector before being written here.
DECODED = {
    "http://127.0.0.1:8541/": [
        "#######.##...##...#######",
        "#.....#.......#...#.....#",
        "#.###.#.#..###.##.#.###.#",
        "#.###.#.##.#.#..#.#.###.#",
        "#.###.#.####...#..#.###.#",
        "#.....#..#..###...#.....#",
        "#######.#.#.#.#.#.#######",
        ".........#.#.............",
        "####..#.#........#..###.#",
        "..##.#...#....#..#.....#.",
        ".#...####................",
        "..##.#..#..###.#.###.##..",
        "#.##.###.#.#.#....###.###",
        ".###.#..####...#.##.#...#",
        ".#.####.#.#.##..###...##.",
        "#..#.#.##...#.##.....#..#",
        "..##.##.####.##.#########",
        "........##..#..##...#...#",
        "#######..#.####.#.#.#####",
        "#.....#...#.#...#...#..##",
        "#.###.#..#.###..#####..#.",
        "#.###.#.###.##.##.###.###",
        "#.###.#.######.##.#.####.",
        "#.....#.#...........#.#..",
        "#######.#.#.#.##..#######",
    ],
    "http://192.168.0.104:8541/": [
        "#######.#....#.#..#######",
        "#.....#.#..####...#.....#",
        "#.###.#.##..#.#...#.###.#",
        "#.###.#.###.##..#.#.###.#",
        "#.###.#..##.##.#..#.###.#",
        "#.....#.###..##...#.....#",
        "#######.#.#.#.#.#.#######",
        "..........##...##........",
        "##..###...#.#.#.#..#.####",
        ".....#.#.....#.#.#.###.#.",
        ".#.#..##.##...####.#.##..",
        "#.###...##..#....##.#.##.",
        ".#....#....##.##..#..####",
        "##.###.####.#..#...##..#.",
        "......#.#.####.##.##.##..",
        "..#.#.......#..####..###.",
        "####.###...##.#########..",
        "........#..##..##...#.#..",
        "#######..####...#.#.##...",
        "#.....#.####...##...#####",
        "#.###.#.###...#.#####.#..",
        "#.###.#..#####..#.#..####",
        "#.###.#....#..#.#.#....#.",
        "#.....#.##.##.#..#.#####.",
        "#######.#.#...#..##...###",
    ],
}


def check_format() -> int:
    failed = 0
    for mask, expected in enumerate(FORMAT_L):
        got = f"{qr._format_bits(mask):015b}"
        if got != expected:
            print(f"FAIL  format bits for mask {mask}: expected {expected}, got {got}")
            failed += 1
    return failed


def check_structure() -> int:
    """Function patterns the standard fixes, so a layout regression cannot hide behind a fixture."""
    failed = 0
    m = qr.matrix("http://192.168.0.104:8541/")
    n = len(m)
    if n != 25 or any(len(row) != 25 for row in m):
        print(f"FAIL  a 26-byte payload should be version 2 (25x25), got {n}x{len(m[0]) if m else 0}")
        failed += 1
        return failed
    for name, (r0, c0) in (("top-left", (0, 0)), ("top-right", (0, n - 7)), ("bottom-left", (n - 7, 0))):
        eye = all(m[r0 + d][c0] and m[r0 + d][c0 + 6] for d in range(7)) and all(m[r0][c0 + d] and m[r0 + 6][c0 + d] for d in range(7))
        core = all(m[r0 + 2 + d][c0 + 2 + e] for d in range(3) for e in range(3))
        if not (eye and core):
            print(f"FAIL  the {name} finder pattern is malformed")
            failed += 1
    if not all(m[6][i] == (i % 2 == 0) for i in range(8, n - 8)):
        print("FAIL  horizontal timing pattern is not alternating")
        failed += 1
    if not all(m[i][6] == (i % 2 == 0) for i in range(8, n - 8)):
        print("FAIL  vertical timing pattern is not alternating")
        failed += 1
    # The always-dark module. It sits one cell along the SAME column as the vertical format copy,
    # which is exactly why an off-by-one in that copy's length silently overwrote it.
    if not m[n - 8][8]:
        print("FAIL  the always-dark module at (n-8, 8) is not set")
        failed += 1
    return failed


# Module sizes per version, pinned literally — 21 + 4*(version-1), from the standard, not from qr.py.
_VERSION_SIZE = {1: 21, 2: 25, 3: 29, 4: 33}


def check_capacity() -> int:
    """The version table, and that the ceiling REFUSES rather than truncating."""
    failed = 0
    for version, expected in ((1, 17), (2, 32), (3, 53), (4, 78)):
        if qr.capacity(version) != expected:
            print(f"FAIL  version {version} capacity: expected {expected}, got {qr.capacity(version)}")
            failed += 1
    for n, version in ((17, 1), (18, 2), (32, 2), (33, 3), (53, 3), (54, 4), (78, 4)):
        if qr._pick_version(n) != version:
            print(f"FAIL  {n} bytes should pick version {version}, got {qr._pick_version(n)}")
            failed += 1
    try:
        qr.matrix("x" * 79)
    except ValueError:
        pass
    else:
        print("FAIL  79 bytes silently produced a code instead of raising")
        failed += 1
    # BYTES, not characters — the whole capacity path reasons in the UTF-8 encoding (`matrix`
    # encodes first, `_pick_version` takes `len(data)`, and the length field written into the
    # header is a BYTE count). Every other case here is ASCII, where the two are the same number
    # and the distinction is unguarded. 26 CJK characters are 78 bytes: the version-4 ceiling
    # exactly. 27 are 81, and must refuse.
    if len(qr.matrix("材" * 26)) != _VERSION_SIZE[4]:
        print("FAIL  78 bytes of multi-byte text should fill version 4")
        failed += 1
    try:
        qr.matrix("材" * 27)
    except ValueError:
        pass
    else:
        print("FAIL  81 bytes of multi-byte text was encoded; capacity is counting characters")
        failed += 1
    return failed


def check_fixtures() -> int:
    failed = 0
    for text, rows in DECODED.items():
        got = ["".join("#" if v else "." for v in row) for row in qr.matrix(text)]
        if got != rows:
            bad = next(i for i, (a, b) in enumerate(zip(got, rows)) if a != b)
            print(f"FAIL  matrix for {text!r} changed; first differing row {bad}:\n        got {got[bad]}\n        was {rows[bad]}")
            failed += 1
    return failed


def main() -> int:
    failed = check_format() + check_structure() + check_capacity() + check_fixtures()
    print("test_qr: all checks passed" if not failed else f"test_qr: {failed} check(s) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: MIT
"""A minimal QR encoder — just enough to put a `http://<addr>:<port>/` URL on a phone.

Why this exists rather than a dependency: the mirror's address is only useful on a device that is
not this one, and typing `192.168.0.104:8541` off a status band is the annoying part of using the
feature. A QR removes it. `docs/APP.md` § "Window mirroring" makes zero new dependencies a hard
constraint for this subsystem, and a QR generator is small enough to own — bounded, frozen by a
1994 standard, and never needing to change.

# CONTRACT: byte mode, EC level L, versions 1-4 only.
# That is 78 characters, against the ~30 a mirror URL takes, and it is what keeps this file small:
# versions 1-4 at level L are all SINGLE-BLOCK, so the codeword interleaving that dominates a
# general encoder is absent. Anything longer raises rather than silently truncating. If a caller
# ever needs more, add the version rows and the block-splitting; do not widen the capacity table
# alone, because past version 4 the single-block assumption below is false.

Correctness is not self-evident here, so it is not self-asserted: `_tests/t1_unit/test_qr.py`
compares this encoder's matrices against fixtures produced by `segno`, an independent mature
encoder, over the address shapes this app actually emits.
"""

# ── GF(256), the field QR's Reed-Solomon lives in ────────────────────────────
# Generated from the primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11d), which is the one the
# standard names. Tables rather than repeated multiplication: 512 entries, built once at import.
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    """Multiply in GF(256). Zero is special-cased because it has no logarithm."""
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n: int) -> "list[int]":
    """The degree-``n`` Reed-Solomon generator polynomial, (x - 2^0)...(x - 2^(n-1)).

    Computed rather than tabulated: the table would be four hardcoded coefficient lists restating
    what this loop derives, which is `conventions.md` § Tooling's canonical-source duplication with
    extra steps.
    """
    g = [1]
    for i in range(n):
        g = [(g[j] if j < len(g) else 0) ^ _mul(g[j - 1] if j else 0, _EXP[i]) for j in range(len(g) + 1)]
    return g


def _rs_encode(data: "list[int]", n_ec: int) -> "list[int]":
    """The ``n_ec`` error-correction codewords for ``data`` — polynomial division's remainder."""
    gen = _rs_generator(n_ec)
    rem = [0] * n_ec
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(n_ec):
            rem[i] ^= _mul(gen[i + 1], factor)
    return rem


# version -> (data codewords, EC codewords, module size, alignment-pattern centre)
# Level L only. The alignment centre is None for version 1, which has no alignment pattern.
_VERSIONS = {
    1: (19, 7, 21, None),
    2: (34, 10, 25, 18),
    3: (55, 15, 29, 22),
    4: (80, 20, 33, 26),
}
# Header is 4 bits of mode indicator + 8 bits of length (byte mode, versions 1-9).
_HEADER_BITS = 12
_PAD = (0xEC, 0x11)  # the standard's alternating pad bytes


def capacity(version: int) -> int:
    """Bytes encodable at ``version``, level L, byte mode."""
    return (_VERSIONS[version][0] * 8 - _HEADER_BITS) // 8


def _pick_version(n: int) -> int:
    """Smallest version holding ``n`` bytes. Raises past version 4 — see the module contract."""
    for v in sorted(_VERSIONS):
        if n <= capacity(v):
            return v
    raise ValueError(f"{n} bytes exceeds the {capacity(max(_VERSIONS))}-byte ceiling of this encoder")


def _codewords(data: bytes, version: int) -> "list[int]":
    """Data codewords for ``data``: header, payload, terminator, pad to the version's capacity."""
    n_data = _VERSIONS[version][0]
    bits = "0100"  # byte mode
    bits += f"{len(data):08b}"
    bits += "".join(f"{b:08b}" for b in data)
    bits += "0" * min(4, n_data * 8 - len(bits))  # terminator, truncated if it would overrun
    bits += "0" * (-len(bits) % 8)  # pad to a byte boundary
    words = [int(bits[i : i + 8], 2) for i in range(0, len(bits), 8)]
    while len(words) < n_data:  # fill the rest with the alternating pad pattern
        words.append(_PAD[(len(words) - len(bits) // 8) % 2])
    return words


# ── matrix ───────────────────────────────────────────────────────────────────
# Cells are None until written, so "is this reserved?" needs no second map: function patterns are
# placed first, and the data walk simply skips anything that is not None.


def _finder(m, r, c):
    """One 7x7 finder eye plus its one-module separator, top-left anchored at (r, c)."""
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            rr, cc = r + dr, c + dc
            if 0 <= rr < len(m) and 0 <= cc < len(m):
                ring = dr in (0, 6) or dc in (0, 6)
                core = 2 <= dr <= 4 and 2 <= dc <= 4
                m[rr][cc] = (0 <= dr <= 6 and 0 <= dc <= 6) and (ring or core)


def _reserve_format(m):
    """Blank the format-information cells so the data walk steps over them; filled in later."""
    n = len(m)
    for i in range(9):
        if m[8][i] is None:
            m[8][i] = False
        if m[i][8] is None:
            m[i][8] = False
    for i in range(8):
        m[8][n - 1 - i] = False  # horizontal copy: 8 modules, columns n-1 .. n-8
    for i in range(7):
        m[n - 1 - i][8] = False  # vertical copy: SEVEN, rows n-1 .. n-7
    # The eighth cell up that column, (n-8, 8), is the always-dark module, NOT format space.
    # Reserving 8 here overwrote it with False, and since it is set in `_skeleton` BEFORE this
    # runs, nothing complained — the matrix was well-formed and simply decoded to nothing.


def _skeleton(version: int):
    """The function patterns: finders, timing, alignment, the always-dark module, format space."""
    n = _VERSIONS[version][2]
    m = [[None] * n for _ in range(n)]
    _finder(m, 0, 0)
    _finder(m, 0, n - 7)
    _finder(m, n - 7, 0)
    for i in range(n):  # timing patterns, row 6 and column 6
        if m[6][i] is None:
            m[6][i] = i % 2 == 0
        if m[i][6] is None:
            m[i][6] = i % 2 == 0
    centre = _VERSIONS[version][3]
    if centre is not None:  # single alignment pattern for versions 2-6
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                m[centre + dr][centre + dc] = max(abs(dr), abs(dc)) != 1
    m[n - 8][8] = True  # the dark module, always set
    _reserve_format(m)
    return m


def _walk(n: int):
    """The zigzag the data codewords are written along: right to left in column pairs, alternating
    upward and downward, skipping the vertical timing column."""
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:  # column 6 is timing; the pairs shift left past it
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for row in rows:
            yield row, col
            yield row, col - 1
        col -= 2
        upward = not upward


_MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
)


def _penalty(m) -> int:
    """The standard's four penalty rules. Only used to CHOOSE a mask — every mask decodes, since
    the format bits say which one was applied, so this is about scannability, not correctness."""
    n = len(m)
    score = 0
    # Rule 1: runs of five or more same-coloured modules, per row and per column.
    for line in list(m) + [[m[r][c] for r in range(n)] for c in range(n)]:
        run = 1
        for i in range(1, n):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run = 1
        if run >= 5:
            score += 3 + run - 5
    # Rule 2: every 2x2 block of one colour.
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    # Rule 3: the finder-like 1:1:3:1:1 pattern with four light modules either side.
    pats = ([True, False, True, True, True, False, True, False, False, False, False], [False] * 4 + [True, False, True, True, True, False, True])
    for r in range(n):
        row = m[r]
        col = [m[i][r] for i in range(n)]
        for line in (row, col):
            for i in range(n - 10):
                if list(line[i : i + 11]) in pats:
                    score += 40
    # Rule 4: deviation of the dark-module ratio from 50%.
    dark = sum(1 for row in m for v in row if v)
    score += 10 * (abs(dark * 100 // (n * n) - 50) // 5)
    return score


_FORMAT_MASK = 0b101010000010010  # the standard's format-info XOR mask


def _format_bits(mask: int) -> int:
    """15-bit BCH(15,5) format information for level L with ``mask``."""
    v = (0b01 << 3) | mask  # 01 = level L
    d = v << 10
    for i in range(4, -1, -1):
        if d & (1 << (i + 10)):
            d ^= 0b10100110111 << i
    return ((v << 10) | d) ^ _FORMAT_MASK


def _place_format(m, mask: int):
    """Write the format bits into both of their copies."""
    n = len(m)
    bits = _format_bits(mask)
    # THE TWO COPIES ARE INDEXED IN OPPOSITE DIRECTIONS, which is the whole difficulty of this
    # function and is not guessable from either copy alone. Derived by reading a known-good matrix
    # (segno's) rather than reasoned about, after two wrong versions: one decoded for exactly three
    # of the eight masks, the other for none.
    for i in range(15):
        # Copy 1, wrapping the top-left finder: position i carries bit 14-i, so it reads MSB first
        # as you go right along row 8 and then up column 8.
        hi = (bits >> (14 - i)) & 1 == 1
        if i < 6:
            m[8][i] = hi
        elif i == 6:
            m[8][7] = hi
        elif i == 7:
            m[8][8] = hi
        elif i == 8:
            m[7][8] = hi
        else:
            m[14 - i][8] = hi
        # Copy 2, split between the other two finders: position i carries bit i — LSB first. The
        # low 8 run leftward along row 8 from the top-right finder; the high 7 run up the column by
        # the bottom-left one. The cell between the two runs, (n-8, 8), is the always-dark module,
        # which is why the split is 8 and 7 rather than even.
        lo = (bits >> i) & 1 == 1
        if i < 8:
            m[8][n - 1 - i] = lo
        else:
            m[n - 15 + i][8] = lo


def matrix(text: str) -> "list[list[bool]]":
    """Encode ``text`` as a QR matrix — a square list of rows of booleans, True = dark.

    No quiet zone: the caller draws it, and how much margin to leave is a rendering decision (four
    modules is the standard's minimum). Raises on anything past the version-4 ceiling rather than
    returning a code that does not carry what was asked.
    """
    data = text.encode("utf-8")
    version = _pick_version(len(data))
    n_data, n_ec, size, _ = _VERSIONS[version]
    words = _codewords(data, version)
    words += _rs_encode(words, n_ec)  # single block at these versions: EC simply follows the data

    base = _skeleton(version)
    bits = "".join(f"{w:08b}" for w in words)
    i = 0
    for r, c in _walk(size):
        if base[r][c] is None:
            base[r][c] = i < len(bits) and bits[i] == "1"
            i += 1

    # Mask selection: apply each candidate to the DATA modules only (function patterns are never
    # masked), score it, keep the best. Ties go to the lower mask number, which is what makes the
    # output deterministic and comparable against another encoder.
    skeleton = _skeleton(version)  # a second copy: tells data cells from function cells
    best, best_score = 0, None
    for k, fn in enumerate(_MASKS):
        cand = [[(v != fn(r, c)) if skeleton[r][c] is None else v for c, v in enumerate(row)] for r, row in enumerate(base)]
        _place_format(cand, k)
        s = _penalty(cand)
        if best_score is None or s < best_score:
            best, best_score = k, s
    out = [[(v != _MASKS[best](r, c)) if skeleton[r][c] is None else v for c, v in enumerate(row)] for r, row in enumerate(base)]
    _place_format(out, best)
    return out

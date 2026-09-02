# SPDX-License-Identifier: MIT
"""Where are the E233-0 lower-LCD full-route bars, slots and names?

KEEP — written as a throwaway and it was not one. It has measured this view across
four sessions and is the only instrument that asks the identical question of the
reference and of our own render, which is what makes the two numbers comparable.


Measures `_references/lcd/e233_0/full-takao-stopping-ja.png` — the two route
bars' vertical extent, the served/beyond-service colour boundary, the slot
pitch, the name box above each bar, and the palette. Ratios against the
reference's own size, so they survive the 1502 -> 640 canvas change.

    uv run _dev_scripts/_e233_lower_geometry.py [image]

Takes an image argument so the SAME measurement runs over our own render — the
reference and the renderer answer the identical question, and comparing two runs
of one instrument is what makes the numbers comparable at all.
"""

import math
import os
import sys
from collections import Counter

import pygame

# The repo root, so the probes can READ production's own tuneables and data
# rather than restating them. `_dev_scripts` importing production is the
# sanctioned direction; the ban in `conventions.md` is on the other one.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout.reconfigure(encoding="utf-8")

REF = "_references/lcd/e233_0/full-takao-stopping-ja.png"
SPLIT = 0.3105  # upper/lower divide, WIP § 2.2


def near(c, t, tol=26):
    return max(abs(int(c[i]) - t[i]) for i in range(3)) <= tol


def runs(row):
    """Run-length encode a list of colours into (colour, start, end)."""
    out = []
    for i, c in enumerate(row):
        if out and near(c, out[-1][0], 18):
            out[-1][2] = i
        else:
            out.append([c, i, i])
    return [(tuple(c), a, b) for c, a, b in out]


def name_columns(s, y_lo_ratio, y_hi_ratio, thr=175, min_px=4):
    """Ink-column runs inside a name band, as `x/W` centroids.

    The name columns are what the slot pitch actually has to hit, so they are a
    better instrument for it than the bar's own coloured extent: a bar can carry
    a margin past its first and last slot, and that margin is invisible until a
    column at the END of a row lands wrong while the centre looks perfect.
    """
    W, H = s.get_size()
    lo, hi = int(H * y_lo_ratio), int(H * y_hi_ratio)
    cols = []
    for x in range(W):
        n = sum(1 for y in range(lo, hi) if max(s.get_at((x, y))[:3]) < thr)
        cols.append(n)

    runs_, cur = [], None
    for x, n in enumerate(cols):
        if n >= 1:
            cur = [x, x] if cur is None else [cur[0], x]
        elif cur:
            runs_.append(cur)
            cur = None
    if cur:
        runs_.append(cur)

    out = []
    for a, b in runs_:
        weight = sum(cols[a : b + 1])
        # Width filter as well as weight: the reference's own screen border is a
        # 2px-wide column of dark pixels at each edge, and it is heavy enough to
        # pass a weight test — it would then sit in the fit as two phantom slots.
        if weight < min_px or (b - a + 1) < max(4, W // 120):
            continue
        num = sum(x * cols[x] for x in range(a, b + 1))
        out.append((num / weight, a, b))
    return out


def fit_pitch(centres):
    """Least-squares `centre = intercept - k * pitch`, k counted from the RIGHT."""
    n = len(centres)
    if n < 2:
        return None
    xs = list(range(n))  # 0 = rightmost
    ys = list(reversed(sorted(centres)))
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    slope = num / den
    return my - slope * mx, -slope  # intercept at k=0, pitch


def main():
    pygame.init()
    s = pygame.image.load(sys.argv[1] if len(sys.argv) > 1 else REF)
    W, H = s.get_size()
    lower_top = int(H * SPLIT)
    print(f"reference {W}x{H}, lower area y {lower_top}..{H}")

    # --- 1. Find the bar bands: rows carrying a long saturated (orange) run ---
    bands, cur = [], None
    for y in range(lower_top, H):
        n = sum(1 for x in range(W) if max(s.get_at((x, y))[:3]) - min(s.get_at((x, y))[:3]) > 60)
        if n > W * 0.25:
            cur = [y, y] if cur is None else [cur[0], y]
        elif cur:
            bands.append(cur)
            cur = None
    if cur:
        bands.append(cur)
    print("\n-- bar bands (rows with a long saturated run) --")
    for a, b in bands:
        print(f"   y {a}..{b}  h={b - a + 1}  h/H={(b - a + 1) / H:.4f}  centre/H={((a + b) / 2) / H:.4f}")

    # --- 2. Along each bar's centre row: the colour runs ---
    for a, b in bands:
        cy = (a + b) // 2
        row = [s.get_at((x, cy))[:3] for x in range(W)]
        big = [(c, lo, hi) for c, lo, hi in runs(row) if hi - lo >= 6]
        print(f"\n-- bar centre row y={cy} : runs >= 7px --")
        for c, lo, hi in big:
            print(f"   x {lo:4d}..{hi:4d} ({hi - lo + 1:4d}px)  {c}  x/W {lo / W:.4f}..{(hi + 1) / W:.4f}")

    # --- 3. Palette of the lower area ---
    cnt = Counter()
    for y in range(lower_top, H, 3):
        for x in range(0, W, 3):
            cnt[tuple(s.get_at((x, y))[:3])] += 1
    print("\n-- 12 most common lower-area colours --")
    for c, n in cnt.most_common(12):
        print(f"   {c}  {n}")

    # --- 4. Ink above each bar = the vertical name box ---
    for a, b in bands:
        top = lower_top if a == bands[0][0] else bands[0][1] + 1
        rows = []
        for y in range(top, a):
            n = sum(1 for x in range(W) if max(s.get_at((x, y))[:3]) < 150)
            if n:
                rows.append((y, n))
        if rows:
            print(
                f"\n-- dark ink above bar at y {a}: rows {rows[0][0]}..{rows[-1][0]} "
                f"(h={rows[-1][0] - rows[0][0] + 1}, {(rows[-1][0] - rows[0][0] + 1) / H:.4f} of H)"
            )


def report_marks(path, bar_cy_ratio, bar_h_ratio, slot0_ratio, pitch_ratio, n=20):
    """What sits ON the bar, slot by slot: the white box and the ink inside it.

    Walks each slot's own window rather than run-length-encoding the whole row,
    so a box and the digit in it are attributed to the station they belong to
    instead of to whichever run they happen to fall in.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    cy = H * bar_cy_ratio
    half = H * bar_h_ratio / 2.0
    lo, hi = int(round(cy - half)), int(round(cy + half))
    slot0 = W * slot0_ratio
    pitch = W * pitch_ratio

    print(f"\n== {path}: marks on the bar at y {lo}..{hi} (h={hi - lo + 1}) ==")
    for k in range(n):
        cx = slot0 - k * pitch
        x0, x1 = int(round(cx - pitch / 2)), int(round(cx + pitch / 2))
        # >240, not >200: the lower background is (213,223,239) and would pass a
        # looser test wherever the band overshoots the bar by a row, which reads
        # as a mark the width of the whole slot.
        white = [(x, y) for x in range(max(0, x0), min(W, x1)) for y in range(lo, hi + 1) if min(s.get_at((x, y))[:3]) > 240]
        dark = [(x, y) for x in range(max(0, x0), min(W, x1)) for y in range(lo, hi + 1) if max(s.get_at((x, y))[:3]) < 90]
        if not white:
            print(f"   slot {k:2d}  cx {cx:7.1f}   no white")
            continue
        wx = [p[0] for p in white]
        wy = [p[1] for p in white]
        box = f"x {min(wx)}..{max(wx)} ({max(wx) - min(wx) + 1}) y {min(wy)}..{max(wy)} ({max(wy) - min(wy) + 1})"
        ink = ""
        if dark:
            dx = [p[0] for p in dark]
            dy = [p[1] for p in dark]
            ink = f"   ink x {min(dx)}..{max(dx)} ({max(dx) - min(dx) + 1}) y {min(dy)}..{max(dy)} ({max(dy) - min(dy) + 1})"
        print(f"   slot {k:2d}  cx {cx:7.1f}   white {box}{ink}")


def report_marker(path, pad=10):
    """Walk OUTWARD from the green marker on all four sides.

    The question this answers is which sides carry a drop shadow and how far it
    reaches — so it prints the raw pixel run beyond the green body rather than a
    summary. Reading outward crosses the white rim first, then whatever shadow
    there is, then the background, and those three are trivially told apart by
    eye in the printout; a single "shadow extent" number would have to threshold
    against a background that DIFFERS per side (orange bar left, grey bar right,
    pale lower background above and below), which is exactly the assumption that
    makes such a number wrong.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0

    def is_green(c):
        r, g, b = c[0], c[1], c[2]
        return g > 60 and g > r + 20 and g > b + 20

    px = [(x, y) for y in range(int(H * 0.3), H) for x in range(W) if is_green(s.get_at((x, y)))]
    if not px:
        print(f"== {path}: no green marker found ==")
        return
    xs = [p[0] for p in px]
    ys = [p[1] for p in px]
    x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
    print(f"\n== {path}: marker probe (W={W}, canvas scale {scale:.3f}) ==")
    print(
        f"   green body x {x_lo}..{x_hi} ({x_hi - x_lo + 1}px = {(x_hi - x_lo + 1) / scale:.2f} canvas)"
        f"  y {y_lo}..{y_hi} ({y_hi - y_lo + 1}px = {(y_hi - y_lo + 1) / scale:.2f} canvas)"
    )

    def show(label, pts):
        cells = " ".join(f"{s.get_at(p)[0]:3d},{s.get_at(p)[1]:3d},{s.get_at(p)[2]:3d}" for p in pts if 0 <= p[0] < W and 0 <= p[1] < H)
        print(f"   {label:22s} {cells}")

    n = int(round(pad * scale))
    ymid = (y_lo + y_hi) // 2
    # Base (right) and nose (left) read along the marker's own centre row.
    show("RIGHT of base", [(x_hi + 1 + d, ymid) for d in range(n)])
    show("LEFT of nose", [(x_lo - 1 - d, ymid) for d in range(n)])
    # Top and bottom read down three columns spread across the flat edges, so a
    # single column landing on a slant cannot be mistaken for the whole side.
    for f in (0.35, 0.6, 0.85):
        x = int(round(x_lo + (x_hi - x_lo) * f))
        col = [y for y in range(y_lo, y_hi + 1) if is_green(s.get_at((x, y)))]
        if not col:
            continue
        show(f"ABOVE x={x}", [(x, min(col) - 1 - d) for d in range(n)])
        show(f"BELOW x={x}", [(x, max(col) + 1 + d) for d in range(n)])


def report_map(path, cx, cy, cw, ch, cls=None):
    """Classified map of an arbitrary region, addressed in CANVAS coordinates.

    The generalisation of the two hard-coded bar ends: any element can be looked
    at without first knowing which end it is near, and the same call works on the
    reference and on our own render because the region is given in canvas units
    and scaled per image.

    `cls` picks the classifier. The default reads a route-bar view; the
    priority-seat page has a palette that view has no class for, so it passes
    `_placard_cls` rather than a second copy of this function.
    """
    _cls_fn = cls or _cls
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    lo, hi = int(cx * scale), int((cx + cw) * scale)
    top, bot = int(cy * scale), int((cy + ch) * scale)
    print(f"\n== {path}: canvas {cx},{cy} {cw}x{ch} (scale {scale:.3f}) ==")
    ticks = ["|" if not (x - lo) % 12 else " " for x in range(lo, hi)]
    labels = list(" " * (hi - lo))
    for x in range(lo, hi, 12):
        for j, ch_ in enumerate(f"{x / scale:.0f}"):
            if x - lo + j < len(labels):
                labels[x - lo + j] = ch_
    print("           " + "".join(ticks))
    print("           " + "".join(labels) + "   <- canvas x")
    for y in range(max(0, top), min(H, bot)):
        row = "".join(_cls_fn(s.get_at((x, y))) for x in range(max(0, lo), min(W, hi)))
        print(f"   {y / scale:6.1f} |{row}|")


def report_ink(path, cx, cy, cw, ch, thr=110):
    """Dark-ink bbox inside a canvas rect, reported in canvas units.

    The counterpart to `report_map`: the map says what is there, this says
    exactly where. Both take canvas coordinates so the reference and our render
    answer with numbers that can be subtracted.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    xs, ys = [], []
    for y in range(max(0, int(cy * scale)), min(H, int((cy + ch) * scale))):
        for x in range(max(0, int(cx * scale)), min(W, int((cx + cw) * scale))):
            if max(s.get_at((x, y))[:3]) < thr:
                xs.append(x)
                ys.append(y)
    if not xs:
        print(f"   {path}: no ink under {thr} in {cx},{cy} {cw}x{ch}")
        return
    print(
        f"   {path}: ink x {min(xs) / scale:.2f}..{(max(xs) + 1) / scale:.2f} "
        f"({(max(xs) + 1 - min(xs)) / scale:.2f} wide, centre {(min(xs) + max(xs) + 1) / 2 / scale:.2f})  "
        f"y {min(ys) / scale:.2f}..{(max(ys) + 1) / scale:.2f} "
        f"({(max(ys) + 1 - min(ys)) / scale:.2f} tall, centre {(min(ys) + max(ys) + 1) / 2 / scale:.2f})"
    )


def report_rows(path, cx, cw, cy, ch, thr=205):
    """Ink-ROW runs inside a column band, as canvas-unit bands and pitches.

    The row-axis companion to `name_columns`, which does the column axis. A
    vertical name stack's LAYOUT is its per-character pitch, and the ink bbox of
    the whole stack cannot report it — a stack ending on a short glyph (the ノ of
    御茶ノ水) measures shorter than the same layout ending on a dense one, so two
    identical layouts read as different heights and two different ones can read
    the same. Printing each character's own band, and the centre-to-centre steps
    between them, is what separates the layout from the glyphs sitting in it.

    Threshold defaults ABOVE the grey name colour, so a greyed station is
    measured on the same footing as a black one — the earlier 175 silently
    dropped grey glyphs and biased every fit that used them.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    x0, x1 = int(cx * scale), int((cx + cw) * scale)
    y0, y1 = int(cy * scale), int((cy + ch) * scale)

    rows = []
    for y in range(max(0, y0), min(H, y1)):
        n = sum(1 for x in range(max(0, x0), min(W, x1)) if max(s.get_at((x, y))[:3]) < thr)
        rows.append((y, n))

    bands, cur = [], None
    for y, n in rows:
        if n:
            cur = [y, y] if cur is None else [cur[0], y]
        elif cur:
            bands.append(cur)
            cur = None
    if cur:
        bands.append(cur)

    print(f"\n== {path}: rows in x {cx}..{cx + cw} (scale {scale:.3f}, thr {thr}) ==")
    prev = None
    for a, b in bands:
        top, bot = a / scale, (b + 1) / scale
        mid = (top + bot) / 2.0
        step = f"  step {mid - prev:6.2f}" if prev is not None else ""
        print(f"   y {top:7.2f}..{bot:7.2f}  h {bot - top:5.2f}  centre {mid:7.2f}{step}")
        prev = mid


def _cls(c):
    """One character per pixel, by colour test — never by eye."""
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    if g > 60 and g > r + 20 and g > b + 20:
        return "#"  # marker green
    if r > 170 and g < 150 and b < 90:
        return "O"  # served bar, orange
    if abs(r - 134) < 26 and abs(g - 144) < 26 and abs(b - 164) < 26:
        return "g"  # beyond / behind, grey
    if min(r, g, b) > 200 and b - r < 15:
        return "W"  # white mark
    if abs(r - 213) < 14 and abs(g - 223) < 14 and abs(b - 239) < 14:
        return "."  # lower background
    if max(r, g, b) < 110:
        return "s"  # dark ink
    return "-"


def report_profile(path, x, y, dx, dy, n=12):
    """Raw pixel walk from a point along a direction, in NATIVE coordinates.

    The general primitive the shape-specific readouts above kept re-deriving:
    an edge is hard or feathered, and a threshold cannot tell you which because
    it answers with a position rather than a ramp. Prints RGB so the answer is
    read off the numbers.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    pts = [(int(x + dx * i), int(y + dy * i)) for i in range(n)]
    cells = " ".join(f"{s.get_at(p)[0]:3d},{s.get_at(p)[1]:3d},{s.get_at(p)[2]:3d}" for p in pts if 0 <= p[0] < W and 0 <= p[1] < H)
    print(f"   ({x},{y}) step ({dx},{dy}) x{n}:  {cells}")


def report_ends(path, cy1_ratio=0.5783, cy2_ratio=0.8768, span=95):
    """Classified pixel maps of the two ends the WRAP joins.

    Row 1's LEFT end continues into row 2's RIGHT end, and what sits there — a
    tapered tail, how many chevrons, how far past the bar they run — is a SHAPE.
    A run-length summary flattens a shape into numbers that each look plausible;
    a map shows the taper and the chevron count directly, which is what
    `conventions.md` § UI code style means by not reading structure off a photo
    by eye. Every glyph here comes from a colour test, not from looking.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    bar_h = int(round(22 * scale))

    def cls(c):
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        if g > 60 and g > r + 20 and g > b + 20:
            return "#"  # marker green
        if r > 170 and g < 150 and b < 90:
            return "O"  # served bar, orange
        if abs(r - 134) < 26 and abs(g - 144) < 26 and abs(b - 164) < 26:
            return "g"  # beyond / behind, grey
        if min(r, g, b) > 200 and b - r < 15:
            return "W"  # white mark
        if abs(r - 213) < 14 and abs(g - 223) < 14 and abs(b - 239) < 14:
            return "."  # lower background
        if max(r, g, b) < 110:
            return "s"  # dark: shadow or name ink
        return "-"

    print(f"\n== {path}: bar ends (W={W}, canvas scale {scale:.3f}, bar {bar_h}px) ==")
    for label, cy_ratio, side in (("ROW 1 LEFT", cy1_ratio, "L"), ("ROW 2 RIGHT", cy2_ratio, "R")):
        cy = H * cy_ratio
        top = int(round(cy - bar_h / 2)) - 4
        bot = int(round(cy + bar_h / 2)) + 4
        if side == "L":
            x_lo = int(W * 0.0353) - int(round(30 * scale))
        else:
            x_lo = int(W * 0.9627) + int(round(30 * scale)) - span
        print(f"\n   -- {label}: x {x_lo}..{x_lo + span - 1}, y {top}..{bot} --")
        print(f"      x0={x_lo} (canvas {x_lo / scale:.1f})")
        # Run-length of the classified CENTRE row, in canvas coordinates. The map
        # below shows the shape; this gives the numbers a tuneable needs, so no
        # boundary is ever arrived at by counting characters in the map.
        mid = int(round(cy))
        rle, prev = [], None
        for x in range(max(0, x_lo), min(W, x_lo + span)):
            c = cls(s.get_at((x, mid)))
            if prev is None or c != prev[0]:
                rle.append([c, x, x])
                prev = rle[-1]
            else:
                prev[2] = x
        print("      centre-row runs: " + "  ".join(f"{c}{a / scale:.1f}..{(b + 1) / scale:.1f}" for c, a, b in rle if b - a >= 1))
        # A ruler, so a boundary in the map is READ off an index instead of
        # counted along a row of characters — counting is the failure mode
        # `conventions.md` § UI code style bars for reference photos, and it does
        # not stop being one because the photo has been classified first.
        lo, hi = max(0, x_lo), min(W, x_lo + span)
        ticks = ["|" if not (x - lo) % 12 else " " for x in range(lo, hi)]
        labels = list(" " * (hi - lo))
        for x in range(lo, hi, 12):
            for j, ch in enumerate(f"{x / scale:.0f}"):
                if x - lo + j < len(labels):
                    labels[x - lo + j] = ch
        print("           " + "".join(ticks))
        print("           " + "".join(labels) + "   <- canvas x")
        for y in range(top, bot + 1):
            row = "".join(cls(s.get_at((x, y))) for x in range(lo, hi))
            print(f"      {y:4d} |{row}|")


def report_chevrons(path, cy_ratio, x_from, x_to=None):
    """Connected orange components past the bar's end, with their boxes.

    The continuity marks are a repeating SHAPE, so the numbers a tuneable needs
    are per-shape: how many, each one's tip, its span, the pitch between them.
    A run-length readout of one row cannot give any of those — it reports where a
    row happens to cross the arms — and reading them off the classified map means
    counting characters, which is the same eye-measurement the map was built to
    replace.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    cy = H * cy_ratio
    bar_h = 22 * scale
    lo_y, hi_y = int(cy - bar_h), int(cy + bar_h)
    lo_x = int(x_from * scale)
    hi_x = min(W, int((x_to or 640) * scale))

    def is_o(c):
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        return r > 150 and g < 160 and b < 110 and r - b > 90

    seen = set()
    comps = []
    for y in range(lo_y, hi_y + 1):
        for x in range(lo_x, hi_x):
            if (x, y) in seen or not is_o(s.get_at((x, y))):
                continue
            stack, cells = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy_ = stack.pop()
                cells.append((cx, cy_))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy_ + dy
                        if lo_x <= nx < hi_x and lo_y <= ny <= hi_y and (nx, ny) not in seen and is_o(s.get_at((nx, ny))):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            if len(cells) > 20:
                comps.append(cells)

    print(f"\n== {path}: orange components right of canvas {x_from} (scale {scale:.3f}) ==")
    comps.sort(key=lambda c: min(p[0] for p in c))
    prev_tip = None
    for i, cells in enumerate(comps):
        xs = [p[0] for p in cells]
        ys = [p[1] for p in cells]
        tip_y = min(ys, key=lambda y: min(p[0] for p in cells if p[1] == y))
        tip = min(xs)
        # Stroke measured on the tip's own row, which is the one row where a
        # left-pointing chevron crosses as a single run.
        row = sorted(p[0] for p in cells if p[1] == tip_y)
        pitch = "" if prev_tip is None else f"  pitch {(tip - prev_tip) / scale:.2f}"
        print(
            f"   comp {i}: x {tip / scale:.2f}..{(max(xs) + 1) / scale:.2f} "
            f"({(max(xs) + 1 - tip) / scale:.2f} wide)  y {min(ys) / scale:.2f}..{(max(ys) + 1) / scale:.2f} "
            f"({(max(ys) + 1 - min(ys)) / scale:.2f} tall)  tip row stroke {(row[-1] + 1 - row[0]) / scale:.2f}{pitch}"
        )
        prev_tip = tip


def report_columns(path, band, thr=175):
    """Per-slot name-column centres for one image, printed as `x/W`.

    `thr` MATTERS AND IS NOT COSMETIC. A greyed station name is much lighter
    than a black one, so a threshold tuned for black clips a grey glyph's
    antialiased flanks and shifts its ink CENTROID — and a fit over six columns
    where only some are grey is then biased on exactly those slots. Pass a value
    above the grey when a capture greys part of its row.
    """
    pygame.init()
    s = pygame.image.load(path)
    W = s.get_width()
    cols = name_columns(s, *band, thr=thr)
    print(f"\n== {path}: {len(cols)} name columns in band {band} thr {thr} ==")
    fit = fit_pitch([c for c, _, _ in cols])
    for i, (c, a, b) in enumerate(reversed(cols)):
        print(f"   slot {i:2d} from right   centre x {c:8.2f}   x/W {c / W:.5f}   ink {a}..{b}")
    if fit:
        intercept, pitch = fit
        print(f"   FIT  centre(k) = {intercept:.2f} - k * {pitch:.3f}     " f"x/W: {intercept / W:.5f} - k * {pitch / W:.5f}")


def report_transfer(path, cy=152.0, ch=325.0, inset=6.0, bg=(213, 223, 239), tol=14):
    """The transfer view's banner and per-entry rows, in canvas units.

    Everything else in this module measures INK — dark glyphs on a pale field —
    and this view's headline element is a mid-blue pill whose luminance sits
    between the background and the text, so a threshold that finds the rows
    cannot find the banner and vice versa. The question here is "what is not the
    background", which separates both in one pass and needs no threshold tuned
    per element.

    Reports the banner's box, then each content band below it with the band's own
    left-hand BADGE box split out — the badge is a solid square and the text is
    ink, so the split is where the band stops being one colour. Row PITCH is the
    band-to-band step, which is the number the layout is actually made of; a
    single band's height is the glyphs that happen to sit in it.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    y0, y1 = int(cy * scale), int(min(H, (cy + ch) * scale))
    # A capture carries a frame the panel does not — inset past it, or every
    # scanline hits the border and the whole view reports as one band.
    x0, x1 = int(inset * scale), int(W - inset * scale)

    def content_cols(a, b):
        out = []
        for x in range(x0, x1):
            if any(not near(s.get_at((x, y))[:3], bg, tol) for y in range(a, b)):
                out.append(x)
        return out

    bands, cur = [], None
    for y in range(y0, y1):
        hit = any(not near(s.get_at((x, y))[:3], bg, tol) for x in range(x0, x1))
        if hit:
            cur = [y, y] if cur is None else [cur[0], y]
        elif cur:
            bands.append(cur)
            cur = None
    if cur:
        bands.append(cur)

    print(f"\n== {path}: transfer view, lower {cy}..{cy + ch} canvas ({len(bands)} bands) ==")
    prev_mid = None
    for i, (a, b) in enumerate(bands):
        xs = content_cols(a, b)
        if not xs:
            continue
        lo, hi = min(xs) / scale, (max(xs) + 1) / scale
        top, bot = a / scale, (b + 1) / scale
        mid = (top + bot) / 2.0
        step = f"  step {mid - prev_mid:6.2f}" if prev_mid is not None else ""
        print(f"   band {i}: x {lo:7.2f}..{hi:7.2f} ({hi - lo:6.2f})   y {top:7.2f}..{bot:7.2f} ({bot - top:5.2f})   mid {mid:7.2f}{step}")
        # Where the solid badge ends: the first column, scanning right from the
        # band's left edge, that is background for the band's full height.
        gap = None
        for x in range(int(min(xs)), int(max(xs))):
            if all(near(s.get_at((x, y))[:3], bg, tol) for y in range(a, b + 1)):
                gap = x
                break
        if gap is not None:
            # The badge is a SQUARE and the text block beside it is two lines, so
            # the two do not share a height — report each side's own vertical
            # extent rather than the band's, or the badge reads as tall as the
            # text and every derived pad is wrong by the difference.
            def vext(xa, xb):
                ys = [y for y in range(a, b + 1) if any(not near(s.get_at((x, y))[:3], bg, tol) for x in range(xa, xb))]
                return (min(ys) / scale, (max(ys) + 1) / scale) if ys else (0.0, 0.0)

            bx0, bx1 = int(min(xs)), gap
            tx = next((x for x in range(gap, int(max(xs)) + 1) if any(not near(s.get_at((x, y))[:3], bg, tol) for y in range(a, b + 1))), gap)
            bt, bb = vext(bx0, bx1)
            tt, tb = vext(tx, int(max(xs)) + 1)
            print(f"            badge x {lo:7.2f}..{gap / scale:7.2f} ({gap / scale - lo:6.2f} wide)   y {bt:7.2f}..{bb:7.2f} ({bb - bt:5.2f} tall)")
            print(
                f"            text  x {tx / scale:7.2f}..{hi:7.2f} ({hi - tx / scale:6.2f} wide)   y {tt:7.2f}..{tb:7.2f}   badge->text gap {tx / scale - gap / scale:5.2f}"
            )
        prev_mid = mid


def _placard_cls(c):
    """One character per pixel for the 優先席 page — by colour test, never by eye.

    Order matters. The page background is (213,223,239), whose channels are all
    above 200, so a plain "is it light" test claims it as placard white; the
    background is therefore tested FIRST and the white test only ever sees what
    is left.
    """
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    if abs(r - 213) < 16 and abs(g - 223) < 16 and abs(b - 239) < 16:
        return "."  # page background
    if g > 70 and g > r + 15 and g > b + 15:
        # The caption labels are ~6px glyphs and EVERY pixel of them is a blend
        # of white and the field, topping out at (190,230,175) — still green by
        # any hue test, and never close to white. So a lightened green is its own
        # class: the field itself sits at r=52, so a red channel past 110 is ink
        # and nothing else on this page reaches it.
        return "w" if r > 110 else "G"
    # b > g by only 12, not 30: the pictograms' SEAT bars read (37,81,104) —
    # the same hue as the figures but darker — and a 30 margin drops them, which
    # left a hole across the panel wide enough to cut the placard in two.
    if b > 85 and b > r + 40 and b > g + 12:
        return "B"  # pictogram blue
    if min(r, g, b) > 200:
        return "W"  # placard white, and the white ink on the green
    if max(r, g, b) < 110:
        return "s"  # dark ink (the two body lines under the placard)
    return "-"


def _classify(s, x0, x1, y0, y1):
    """The classified region as a list of strings, one per row."""
    W, H = s.get_size()
    return ["".join(_placard_cls(s.get_at((x, y))) for x in range(max(0, x0), min(W, x1))) for y in range(max(0, y0), min(H, y1))]


def _groups(flags, min_gap=1):
    """`[(start, end), ...]` runs of True, merging gaps shorter than `min_gap`."""
    out, cur = [], None
    gap = 0
    for i, f in enumerate(flags):
        if f:
            if cur is None:
                cur = [i, i]
            else:
                cur[1] = i
            gap = 0
        elif cur is not None:
            gap += 1
            if gap >= min_gap:
                out.append(tuple(cur))
                cur = None
                gap = 0
    if cur is not None:
        out.append(tuple(cur))
    return out


def report_placard(path, split=SPLIT):
    """The 優先席 page band by band — placard box, pictograms, captions, body.

    Every other measurement in this module looks at a bar or a line of ink. This
    page is a PLACARD: three stacked bands of solid colour, each carrying ink of
    the OPPOSITE polarity to its neighbour (white on green, then blue on white,
    then white on green again), sitting on the pale page background with two
    lines of dark text beneath it. No single threshold separates all of that, so
    every pixel is classified by colour first and each band is then asked its own
    question — the same move `report_transfer` makes for a pill whose luminance
    sits between its background and its own text.

    Reports in CANVAS units (the 640x480 panel), so the reference and our own
    render answer with numbers that subtract.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    y_top = int(H * split)
    print(f"\n== {path}: priority-seat page (W={W} H={H}, canvas scale {scale:.4f}) ==")

    rows = _classify(s, 0, W, y_top, H)

    def cu_x(px):
        return px / scale

    def cu_y(px):
        return px / scale

    # --- 1. The placard: rows carrying a long run of placard colour ----------
    # A placard row is one that is mostly NOT page background — not one that is
    # mostly a named placard colour. Every edge inside the placard is feathered
    # and lands in no class, so counting the classes leaves gaps the row-grouping
    # then reads as the placard ending; counting the background cannot, because
    # the background is flat.
    solid = [r.count(".") < W * 0.5 for r in rows]
    bands = _groups(solid, min_gap=1)
    if not bands:
        print("   no placard found")
        return
    a, b = max(bands, key=lambda t: t[1] - t[0])
    p_top, p_bot = y_top + a, y_top + b
    cols = [any(rows[y][x] in "GWBw" for y in range(a, b + 1)) for x in range(W)]
    cgroups = _groups(cols, min_gap=1)
    p_left, p_right = cgroups[0][0], cgroups[-1][1]
    print(
        f"\n-- placard box --\n"
        f"   x {cu_x(p_left):7.2f}..{cu_x(p_right + 1):7.2f}  ({cu_x(p_right + 1 - p_left):6.2f} wide, centre {cu_x((p_left + p_right + 1) / 2):7.2f})\n"
        f"   y {cu_y(p_top):7.2f}..{cu_y(p_bot + 1):7.2f}  ({cu_y(p_bot + 1 - p_top):6.2f} tall)"
    )

    # --- 2. Corner profile: the first placard-coloured x per row, top-down ----
    # A radius read off a map is a radius counted by eye; the inset per row IS
    # the corner, and printing it lets a circle be fitted to it instead.
    print("\n-- top-left corner: inset of the first placard pixel, row by row --")
    for k in range(0, min(28, b - a + 1)):
        row = rows[a + k]
        hit = next((x for x in range(p_left, min(W, p_left + 60)) if row[x] in "GWB"), None)
        if hit is not None:
            print(f"   +{k / scale:5.2f}  inset {cu_x(hit - p_left):5.2f}   ({row[hit]})")

    # --- 3. Bands inside the placard: green / white / green ------------------
    print("\n-- bands inside the placard (majority colour per row) --")
    maj = []
    for y in range(a, b + 1):
        row = rows[y][p_left : p_right + 1]
        maj.append("G" if row.count("G") + row.count("w") > row.count("W") else "W")
    runs_ = []
    k0 = 0
    for i in range(1, len(maj) + 1):
        if i == len(maj) or maj[i] != maj[k0]:
            runs_.append((maj[k0], a + k0, a + i - 1))
            k0 = i
    for kind, ya, yb in runs_:
        print(f"   {kind}  y {cu_y(y_top + ya):7.2f}..{cu_y(y_top + yb + 1):7.2f}  ({cu_y(yb + 1 - ya):6.2f} tall)")

    # --- 4. Palette --------------------------------------------------------
    cnt = Counter()
    for y in range(p_top, p_bot + 1, 2):
        for x in range(p_left, p_right + 1, 2):
            cnt[tuple(s.get_at((x, y))[:3])] += 1
    print("\n-- 10 most common placard colours --")
    for c, n in cnt.most_common(10):
        print(f"   {c}  {n}")

    # --- 5. Ink groups per band --------------------------------------------
    # White ink on green, blue ink on white: same question, different class.
    inset = int(round(14 * scale))  # past the placard's own outer rim

    def ink_report(label, ya, yb, hit, min_col_gap, min_row_gap=2):
        x0 = p_left + inset
        seg = [rows[y][x0 : p_right + 1 - inset] for y in range(ya, yb + 1)]
        if not seg:
            return
        wrows = [any(hit(c) for c in r) for r in seg]
        rg = _groups(wrows, min_gap=min_row_gap)
        if not rg:
            print(f"\n-- {label}: no ink --")
            return
        # COLUMNS ARE GROUPED WITHIN THE TALLEST ROW GROUP, not over the whole
        # band. A band's own top and bottom rows feather into the neighbouring
        # band, so they satisfy any "not the field" test right across the width —
        # which merges every column group into one and reports the band instead
        # of the text in it.
        ra, rb = max(rg, key=lambda t: t[1] - t[0])
        wcols = [any(hit(seg[y][x]) for y in range(ra, rb + 1)) for x in range(len(seg[0]))]
        cg = _groups(wcols, min_gap=min_col_gap)
        print(f"\n-- {label}: {len(cg)} column groups in row group {ra}..{rb} / {len(rg)} row groups --")
        for i, (u, v) in enumerate(rg):
            print(f"   row {i}: y {cu_y(y_top + ya + u):7.2f}..{cu_y(y_top + ya + v + 1):7.2f} ({cu_y(v + 1 - u):5.2f} tall)")
        prev_c = None
        for i, (u, v) in enumerate(cg):
            ys = [y for y in range(ra, rb + 1) if any(hit(seg[y][x]) for x in range(u, v + 1))]
            if not ys:
                continue
            c = cu_x(x0 + (u + v + 1) / 2)
            step = f"  pitch {c - prev_c:6.2f}" if prev_c is not None else ""
            prev_c = c
            print(
                f"   col {i}: x {cu_x(x0 + u):7.2f}..{cu_x(x0 + v + 1):7.2f} "
                f"({cu_x(v + 1 - u):6.2f} wide, centre {c:7.2f})"
                f"   y {cu_y(y_top + ya + ys[0]):7.2f}..{cu_y(y_top + ya + ys[-1] + 1):7.2f}{step}"
            )

    # Reuses the band boundaries computed above, so the ink pass and the band
    # pass cannot disagree about where a band starts.
    #
    # A green band is asked TWICE and the two answers are not the same question.
    # `W` finds ink that reaches full white — the big kanji and the caption
    # bullets — while the caption LABELS are 5px glyphs whose every pixel is a
    # blend of white and green, so they reach no class at all and are invisible
    # to it. `not G` finds anything that is not the band's own field, which is
    # the only test that sees them.
    for kind, ya, yb in runs_:
        if yb - ya < int(6 * scale):
            continue
        y_lab = cu_y(y_top + ya)
        if kind == "G":
            ink_report(f"green band y {y_lab:.1f}: SOLID white ink", ya, yb, lambda c: c == "W", int(round(4 * scale)))
            ink_report(f"green band y {y_lab:.1f}: ALL light ink", ya, yb, lambda c: c in "Ww", int(round(4 * scale)))
        else:
            ink_report(f"white band y {y_lab:.1f}: blue ink", ya, yb, lambda c: c == "B", int(round(6 * scale)))

    # --- 6. The two body lines under the placard ----------------------------
    print("\n-- body text under the placard --")
    below = rows[b + 1 :]
    brows = ["s" in r for r in below]
    for i, (u, v) in enumerate(_groups(brows, min_gap=int(round(3 * scale)))):
        xs = [x for y in range(u, v + 1) for x in range(W) if below[y][x] == "s"]
        if not xs:
            continue
        print(
            f"   line {i}: y {cu_y(p_bot + 1 + u):7.2f}..{cu_y(p_bot + 1 + v + 1):7.2f} "
            f"({cu_y(v + 1 - u):5.2f} tall)   x {cu_x(min(xs)):7.2f}..{cu_x(max(xs) + 1):7.2f} "
            f"({cu_x(max(xs) + 1 - min(xs)):6.2f} wide, centre {cu_x((min(xs) + max(xs) + 1) / 2):7.2f})"
        )


def render_priority_seat(out="screenshot_priority_seat.png"):
    """Render the E233-0 priority-seat page headless, at canvas size.

    Lives here rather than in a harness of its own because this module's whole
    point is asking one question of the reference and of our own render — and
    until the page is wired into `LowerDisplay` there is nothing else that can
    produce the second one. The upper band is left as the model's flat
    background: it is not this view's, and filling it would put content in the
    overlay that neither side is being judged on.
    """
    import os

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()

    from displays.train_models.e233_0 import S_HEIGHT, S_WIDTH, UPPER_BG
    from displays.train_models.e233_0.priority_seat import PrioritySeatDisplay

    screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
    screen.fill(UPPER_BG)
    PrioritySeatDisplay(screen, {}, []).show_stops(None, 0.0)
    pygame.image.save(screen, out)
    print(f"   wrote {out} ({S_WIDTH}x{S_HEIGHT})")


def report_fit(face, lo, hi, text, tracking=0.0):
    """Ink box of one string in one face across a size range, in canvas px.

    The counterpart to `--ink`, pointed at OUR font instead of at the reference,
    so a size is chosen by subtracting two measurements of the same quantity
    rather than by eye. Rendering goes through `font_atlas.lcd_font`, which is
    what the renderer calls — a size read off `pygame.font.Font` directly would
    be measuring a font the display never uses.

    `tracking` adds per-character advance, which the placard header needs: its
    glyph pitch is 9px wider than any size whose ink height matches, so size and
    spacing are two parameters and a single width fit cannot separate them.
    """
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    import font_atlas

    pygame.init()
    pygame.display.set_mode((8, 8))
    print(f"\n== fit {face!r} {text!r} tracking {tracking} ==")
    for size in range(int(lo), int(hi) + 1):
        f = font_atlas.lcd_font(face, size, draws=font_atlas.lit(text))
        if tracking:
            surfs = [f.render(c, True, (0, 0, 0)) for c in text]
            w = int(sum(s.get_width() for s in surfs) + tracking * (len(text) - 1)) + 4
            surf = pygame.Surface((max(1, w), f.get_height() + 4), pygame.SRCALPHA)
            x = 0.0
            for c, s in zip(text, surfs):
                surf.blit(s, (int(round(x)), 2))
                x += s.get_width() + tracking
        else:
            surf = f.render(text, True, (0, 0, 0))
        box = surf.get_bounding_rect(min_alpha=110)
        print(f"   size {size:3d}   ink {box.w:7.2f} x {box.h:6.2f}   advance {f.size(text)[0]:7.2f}   w/h {box.w / max(1, box.h):5.3f}")


def report_runs(path, cx, cy, cw, ch, klass="B", step=1.0):
    """Per-row runs of one class inside a canvas rect, as canvas intervals.

    The compact form of `report_map`, and the one a SHAPE is actually read from.
    A map is a picture and a picture is read by eye, which is what
    `conventions.md` § Tooling bars for a reference; a row's runs are numbers, so
    a limb's edge is subtracted rather than counted. `step` samples every Nth
    canvas row — a pictogram is 90px tall and its outline does not need every one.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    print(f"\n== {path}: '{klass}' runs in canvas {cx},{cy} {cw}x{ch} step {step} ==")
    y = cy
    while y < cy + ch:
        py = int(round(y * scale))
        if not 0 <= py < H:
            y += step
            continue
        row = [_placard_cls(s.get_at((x, py))) for x in range(max(0, int(cx * scale)), min(W, int((cx + cw) * scale)))]
        x0 = max(0, int(cx * scale))
        runs_, cur = [], None
        for i, c in enumerate(row):
            if c == klass:
                cur = [i, i] if cur is None else [cur[0], i]
            elif cur:
                runs_.append(cur)
                cur = None
        if cur:
            runs_.append(cur)
        txt = "  ".join(f"{(x0 + a) / scale:6.2f}..{(x0 + b + 1) / scale:6.2f}" for a, b in runs_ if b >= a)
        print(f"   y {y:7.2f} |  {txt}")
        y += step


def report_trace(path, cy, ch, origins, oy, tol=0.18, iso=0.5):
    """The five pictograms traced as SUB-PIXEL contours, in figure-local units.

    Marching squares over a COVERAGE FIELD, not a boundary walk over a binary
    mask. The mask version was both too strict and too coarse, and those are one
    fault: thresholding throws away the antialiased rim, so the shapes came out
    eroded, and it puts every vertex on an integer, so a curve came out as a
    staircase. Coverage keeps the rim as a fraction and the iso-line crosses
    cell edges wherever the fraction says, which is what makes a traced circle
    round.

    The field is each pixel's position along the WHITE -> BLUE axis, so it is
    high on the figures, zero on the panel and — because the axis is a
    projection, not a distance — unbothered by the green bands at the edge of
    the strip. A white shape enclosed by blue (the heart) becomes a dip in the
    field and marching squares emits it as its own loop, which a blue-only
    filter could not see at all.

    NOT an image extraction. What crosses into the repository is a list of
    coordinates a person could have digitised off the same photograph.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    y0, y1 = int(cy * scale), int(min(H, (cy + ch) * scale))
    h = y1 - y0

    white = (254.0, 254.0, 254.0)
    blue = (11.0, 79.0, 134.0)
    ax = tuple(blue[i] - white[i] for i in range(3))
    den = sum(v * v for v in ax) or 1.0

    def cov(x, y):
        c = s.get_at((x, y0 + y))
        t = sum((float(c[i]) - white[i]) * ax[i] for i in range(3)) / den
        return 0.0 if t < 0 else 1.0 if t > 1 else t

    field = [[cov(x, y) for x in range(W)] for y in range(h)]

    def interp(a, b, va, vb):
        d = vb - va
        f = 0.5 if abs(d) < 1e-9 else (iso - va) / d
        f = 0.0 if f < 0 else 1.0 if f > 1 else f
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

    # Marching squares. Segments are emitted with the high side on the LEFT, so
    # chaining them head-to-tail walks each loop once.
    segs = {}
    for y in range(h - 1):
        for x in range(W - 1):
            v = (field[y][x], field[y][x + 1], field[y + 1][x + 1], field[y + 1][x])
            code = sum((1 << i) for i, t in enumerate(v) if t >= iso)
            if code in (0, 15):
                continue
            c = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            e = [interp(c[0], c[1], v[0], v[1]), interp(c[1], c[2], v[1], v[2]), interp(c[2], c[3], v[2], v[3]), interp(c[3], c[0], v[3], v[0])]
            for a, b in _MS_CASES.get(code, ()):
                segs.setdefault(_key(e[a]), []).append(e[b])

    loops = []
    while segs:
        startk = next(iter(segs))
        pt = segs[startk][0]
        loop = [_unkey(startk)]
        cur = startk
        while True:
            outs = segs.get(cur)
            if not outs:
                break
            nxt = outs.pop()
            if not outs:
                del segs[cur]
            loop.append(nxt)
            cur = _key(nxt)
            if cur == startk:
                break
        del pt
        if len(loop) >= 8:
            loops.append(loop)

    def rdp(pts, eps):
        if len(pts) < 3:
            return pts
        ax_, ay = pts[0]
        bx, by = pts[-1]
        dx, dy = bx - ax_, by - ay
        n = math.hypot(dx, dy) or 1.0
        worst, wi = 0.0, 0
        for i in range(1, len(pts) - 1):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax_) / n
            if d > worst:
                worst, wi = d, i
        if worst <= eps:
            return [pts[0], pts[-1]]
        return rdp(pts[: wi + 1], eps)[:-1] + rdp(pts[wi:], eps)

    print(f"\n== {path}: traced pictograms (marching squares, iso {iso}, tol {tol}) ==")
    for i, ox in enumerate(origins):
        lo, hi = (ox - 6) * scale, (ox + 64) * scale
        mine = [lp for lp in loops if lo <= min(p[0] for p in lp) <= hi]
        print(f"\n   # figure {i} — origin ({ox}, {oy}): {len(mine)} loop(s)")
        for lp in sorted(mine, key=lambda c: (min(p[0] for p in c), min(p[1] for p in c))):
            poly = rdp(lp, tol * scale)
            pts = ", ".join(f"({x / scale - ox:.2f}, {(y + y0) / scale - oy:.2f})" for x, y in poly)
            print(f"      ({pts}),")


def _key(p):
    return (round(p[0] * 64), round(p[1] * 64))


def _unkey(k):
    return (k[0] / 64.0, k[1] / 64.0)


# Marching-squares edge pairs per corner code (edges: 0 top, 1 right, 2 bottom,
# 3 left). Corners are numbered TL, TR, BR, BL and the bit is set where the
# field is at or above the iso value.
_MS_CASES = {
    1: ((3, 0),),
    2: ((0, 1),),
    3: ((3, 1),),
    4: ((1, 2),),
    5: ((3, 0), (1, 2)),
    6: ((0, 2),),
    7: ((3, 2),),
    8: ((2, 3),),
    9: ((2, 0),),
    10: ((0, 1), (2, 3)),
    11: ((2, 1),),
    12: ((1, 3),),
    13: ((1, 0),),
    14: ((0, 3),),
}


def report_figures(path, cy, ch, split=SPLIT, min_cells=40):
    """Connected blue components in a canvas band — the five pictograms.

    A figure is not one component: the person, the seat and a cane are separate
    strokes, and which of them touch depends on the capture. So this prints every
    component AND the x-clusters they fall into, and the cluster is what a
    pictogram's box is read from — grouping by a gap in x is a measurement, while
    deciding by eye which strokes belong to which figure is not.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    y0, y1 = int(cy * scale), int(min(H, (cy + ch) * scale))

    def is_b(c):
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        return b > 90 and b > r + 45 and b > g + 30

    grid = [[is_b(s.get_at((x, y))) for x in range(W)] for y in range(y0, y1)]
    seen = [[False] * W for _ in grid]
    comps = []
    for gy in range(len(grid)):
        for gx in range(W):
            if seen[gy][gx] or not grid[gy][gx]:
                continue
            stack, cells = [(gx, gy)], []
            seen[gy][gx] = True
            while stack:
                cx, cy_ = stack.pop()
                cells.append((cx, cy_))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy_ + dy
                        if 0 <= nx < W and 0 <= ny < len(grid) and not seen[ny][nx] and grid[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            if len(cells) >= min_cells:
                comps.append(cells)

    comps.sort(key=lambda c: min(p[0] for p in c))
    print(f"\n== {path}: {len(comps)} blue components in canvas y {cy}..{cy + ch} ==")
    for i, cells in enumerate(comps):
        xs = [p[0] for p in cells]
        ys = [p[1] + y0 for p in cells]
        print(
            f"   comp {i:2d}: x {min(xs) / scale:7.2f}..{(max(xs) + 1) / scale:7.2f} "
            f"({(max(xs) + 1 - min(xs)) / scale:6.2f})  y {min(ys) / scale:7.2f}..{(max(ys) + 1) / scale:7.2f} "
            f"({(max(ys) + 1 - min(ys)) / scale:6.2f})  cells {len(cells)}"
        )

    # Cluster by a gap in x wider than a figure's own internal gaps.
    occupied = [False] * W
    for cells in comps:
        for x, _ in cells:
            occupied[x] = True
    clusters = _groups(occupied, min_gap=int(round(6 * scale)))
    print(f"\n   -- {len(clusters)} x-clusters (gap >= 6 canvas px) --")
    prev = None
    for i, (u, v) in enumerate(clusters):
        ys = [p[1] + y0 for cells in comps for p in cells if u <= p[0] <= v]
        c = (u + v + 1) / 2 / scale
        step = f"  pitch {c - prev:6.2f}" if prev is not None else ""
        print(
            f"   fig {i}: x {u / scale:7.2f}..{(v + 1) / scale:7.2f} ({(v + 1 - u) / scale:6.2f} wide, "
            f"centre {c:7.2f})  y {min(ys) / scale:7.2f}..{(max(ys) + 1) / scale:7.2f} "
            f"({(max(ys) + 1 - min(ys)) / scale:6.2f} tall){step}"
        )
        prev = c


def report_overview(path, min_ink=0.13, gap=20, white=190, half=8, split=SPLIT):
    """The patterns-overview sheet read as stacked service lines.

    A row belongs to a service line when its most common saturated colour covers
    more than `min_ink` of the width. Counting INK rather than the longest run is
    what makes the busy services visible at all: a stop marker interrupts the
    colour, so the two services that stop nearly everywhere are chopped into
    fragments and a longest-run gate drops them silently while the sparse ones
    report cleanly. The same threshold still excludes the legend chips, which are
    the same colours and heights but cover about a tenth of the width.

    Per band it prints the colour, the extent of that colour, and the pale runs
    inside the extent, which are that service's per-station stop markers. It does
    NOT fit a pitch to those marks — a service skips stations, so consecutive
    marks are not consecutive slots. The slot axis comes from the name columns
    (`--columns`), the same separation the full-route view needed.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    top = int(H * split)
    lim = W * min_ink

    def sat(c):
        return max(c[:3]) - min(c[:3]) > 55

    def key(c):
        return tuple(v // 40 for v in c[:3])

    rows = {}
    for y in range(top, H):
        row = [s.get_at((x, y))[:3] for x in range(W)]
        cnt = Counter(key(c) for c in row if sat(c))
        if cnt and cnt.most_common(1)[0][1] >= lim:
            rows[y] = cnt.most_common(1)[0][0]

    bands = []
    for y in sorted(rows):
        if bands and y == bands[-1][1] + 1:
            bands[-1][1] = y
        else:
            bands.append([y, y])

    # Six services on the upper band then six on the lower, in that y order, so
    # a band's grid follows from which row it is in.
    #
    # The rows are anchored SEPARATELY. Their right edges differ by 11.4px and
    # their pitches by 0.85, which a shared right-anchored grid cannot express.
    # The upper figures are the name-column fit over 17 clean columns; the lower
    # ones are fitted to 各駅停車's own markers, which ARE that row's slots since
    # it stops everywhere, and they then predict 東京's measured name column to
    # 0.06px. Assuming one grid put the lower row 10px out and silently lost
    # every stop right of 新宿.
    # Scaled by W, so the SAME command runs over the 1502-wide reference and our
    # 640-wide render and the two answers are comparable — which is the whole
    # design of this file (see its docstring).
    #
    # READ off production, never restated. A copy of the anchors here is correct
    # the day it is typed and then checks our render against numbers nobody
    # moved, which is the failure `principles.md` section "Prototype inside the
    # code that will hold it" names: it may read production's values, it may
    # never restate them. The dict is in CANVAS px (640 wide), so scale by
    # W/640 for whichever image is loaded.
    from displays.train_models.e233_0.lower_lcd import _TUNEABLES_OVERVIEW as _T

    k = W / 640.0
    _rows = _sheet_rows()
    # The band count per row is the SHEET's service count, not a literal 6. The
    # rows were de-restated a moment ago and this was the same restatement one
    # field over: a sheet with a different service count would silently assign
    # every band to the wrong row grid.
    n_svc = len(_sheet()["services"])
    row_grid = [(len(_rows[1]), _T["row_r_cx"][1] * k, _T["row_pitch"][1] * k)] * n_svc + [
        (len(_rows[0]), _T["row_r_cx"][0] * k, _T["row_pitch"][0] * k)
    ] * n_svc
    bands_seen = []

    print(f"\n== {path} {W}x{H}: {len(bands)} service-line bands below y {top} ==")
    for a, b in bands:
        cy = (a + b) // 2
        h = b - a + 1
        # `ckey`, not `k` — `k` three lines up is the canvas-to-image SCALE, and
        # a colour key sharing its name reads as one the moment either use moves.
        ckey = rows[cy]
        row = [s.get_at((x, cy))[:3] for x in range(W)]
        xs = [x for x, c in enumerate(row) if sat(c) and key(c) == ckey]
        lo, hi = xs[0], xs[-1]
        mean = tuple(round(sum(row[x][i] for x in xs) / len(xs)) for i in range(3))
        print(
            f"\n   band y {a}..{b}  h {h} ({h / H:.4f})  centre/H {(a + b) / 2 / H:.4f}  {mean}"
            f"\n      extent x {lo}..{hi} ({hi - lo + 1}px)  x/W {lo / W:.4f}..{(hi + 1) / W:.4f}"
        )
        # Intervals, not just min..max. A legend chip is the SAME colour as its
        # line and sits in the same rows, so min..max silently swallows the gap
        # between them and reports a service as starting at the screen edge. The
        # gap threshold has to clear a stop marker and not a fold, which is why
        # it is an argument.
        occ = [False] * W
        for x in xs:
            occ[x] = True
        parts = _groups(occ, min_gap=gap)
        if len(parts) > 1:
            print(f"      {len(parts)} intervals (gap >= {gap}px):")
            for u, v in parts:
                print(f"        x {u:4d}..{v:4d} ({v - u + 1:4d}px)  x/W {u / W:.4f}..{(v + 1) / W:.4f}")
        # Stops, asked SLOT BY SLOT rather than by run-length encoding the row.
        # A marker is a near-WHITE square on the line, so testing whiteness at a
        # known slot centre is immune to the two things that defeat a gap scan:
        # the 立川 pill is grey and reads as a gap, and the legend chip shares
        # the line's own colour so the fold between them reads as one too. The
        # grid comes from the name-column fit, so this also cross-checks it — a
        # wrong pitch shows up as stops on stations the service cannot serve.
        n, r_slot0, r_pitch = row_grid[len(bands_seen)] if len(bands_seen) < len(row_grid) else (0, 0, 1)
        if n:
            # A junction slot carries a grey pill with the station name reversed
            # out of it in WHITE, and the pill is drawn OVER every line. So the
            # whiteness test reads that kanji's strokes as marker cores: at 立川
            # it reported a stop on four of the six services and missed the fifth
            # purely because 快速's row falls in the gap between 立 and 川. Nothing
            # under a pill can be measured at all, so refuse the slot rather than
            # answer for it — the stops there are author-supplied.
            row_names = _rows[1] if len(bands_seen) < n_svc else _rows[0]
            pilled = {j["station"] for j in _sheet().get("junctions", ())}
            blind = {row_names.index(nm) for nm in pilled if nm in row_names}
            hits = []
            for j in range(n):
                if j in blind:
                    continue
                cx = r_slot0 - (n - 1 - j) * r_pitch
                px = int(round(cx))
                if not lo + half <= px <= hi - half:
                    continue  # the window must sit wholly ON the line. The pale
                    # page background reads as white, so a window hanging off
                    # either end reports a stop at a station the service does
                    # not reach — which it did, at every row's outermost slot
                win = [s.get_at((x, y))[:3] for x in range(max(0, px - half), min(W, px + half + 1)) for y in range(max(0, cy - 1), min(H, cy + 2))]
                if any(min(c) > white for c in win):
                    hits.append(j)
            note = f"  (slots {sorted(blind)} sit under a junction pill — unmeasurable)" if blind else ""
            print(f"      stops at slots (0 = leftmost of the row): {hits}{note}")
        bands_seen.append((a, b))


def _sheet():
    """`audio/chuo/system.json`, which owns the axis and the service list.

    Read rather than restated for the same reason the row grid is: the six
    service names and their order live in the sheet now, and a copy here would
    keep answering for a sheet that had changed under it.
    """
    import json

    from app_paths import project_root

    with open(project_root() / "audio" / "chuo" / "system.json", encoding="utf-8") as f:
        return json.load(f)


def _sheet_rows():
    return _sheet()["rows"]


def _legend_colors():
    """(type, measured line colour) per service, in the sheet's own order.

    The COLOURS are measured off the reference and stay here: they are what this
    file is for, and they differ from the sheet's authored `color` for three of
    the six (see the session note). The NAMES come from the sheet.
    """
    measured = {
        "通勤特快": (165, 20, 6),
        "青梅特快": (14, 100, 38),
        "中央特快": (12, 64, 149),
        "通勤快速": (15, 34, 112),
        "快速": (203, 95, 43),
        "各駅停車": (224, 202, 33),
    }
    out = []
    for s in _sheet()["services"]:
        if s["type"] not in measured:
            # Loud, because the silent fallback would swap a measured colour for
            # the authored one and answer for a service nobody measured.
            raise KeyError(f"no measured line colour for {s['type']} — add it to _legend_colors, or re-measure the sheet")
        out.append((s["type"], measured[s["type"]]))
    return tuple(out)


def report_legend_rows(path, x_hi=105.0, tol=45, step=0.4):
    """Per service: the vertical rectangle, the underline, and the slant head.

    One row at a time, keyed on that service's OWN colour, so the six never
    contaminate each other — which is what defeated the earlier whole-window
    scan, since a chip and its line share a colour and a y band.

    Native-resolution steps. Reading these off the 2.35x upscale at whole canvas
    rows undersamples a 1px rule badly enough to report it as 2px, which is how
    the underline got drawn too heavy.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    x_stop = min(W, int(x_hi * scale))

    print(f"\n== {path} {W}x{H}: legend rows, native steps, tol {tol} ==")
    for name, rgb in _legend_colors():

        def near_c(c, _t=rgb):
            return max(abs(int(c[i]) - _t[i]) for i in range(3)) <= tol

        rows = {}
        y = 300.0
        while y < 460.0:
            py = int(round(y * scale))
            if 0 <= py < H:
                xs = [x for x in range(x_stop) if near_c(s.get_at((x, py))[:3])]
                if xs:
                    rows[round(y, 2)] = xs
            y += step
        if not rows:
            print(f"\n   {name}: nothing")
            continue

        # Both the underline and the row's own service LINE reach far right, so
        # "furthest right" alone picks the line. The underline is the only one
        # that ALSO starts at the rectangle, which is the discriminator.
        anchored = {y: xs for y, xs in rows.items() if xs[0] / scale < 12.0}
        if not anchored:
            print(f"\n   {name}: no anchored row")
            continue
        rule_y = max(anchored, key=lambda y: anchored[y][-1])
        rule = anchored[rule_y]
        below = [y for y in rows if y > rule_y + 0.5]
        head = rows[min(below)] if below else []
        left = {y: xs for y, xs in anchored.items() if xs[-1] / scale < 12.0}
        if left:
            ys = sorted(left)
            xs_all = [x for y in ys for x in left[y] if x / scale < 12.0]
            print(
                f"\n   {name}  rect  x {min(xs_all) / scale:6.2f}..{(max(xs_all) + 1) / scale:6.2f}"
                f" (w {(max(xs_all) + 1 - min(xs_all)) / scale:4.2f})"
                f"  y {ys[0]:7.2f}..{ys[-1]:7.2f} (h {ys[-1] - ys[0] + step:5.2f})"
            )
        print(
            f"      rule  y {rule_y:7.2f}  x {rule[0] / scale:6.2f}..{(rule[-1] + 1) / scale:6.2f}"
            f"   head  y {min(below) if below else 0:7.2f}"
            f"  x {(head[0] / scale) if head else 0:6.2f}..{((head[-1] + 1) / scale) if head else 0:6.2f}"
        )


def report_legend(path, x0=0.0, x1=0.13, y0=0.62, y1=0.95, split=SPLIT):
    """The legend column: one chip per service, its swatch, and its label ink.

    Scoped to an x WINDOW rather than the whole row, because a chip is the same
    colour and the same rows as the service line it belongs to — the full-width
    scan `--overview` uses cannot separate them, which is why this is its own
    probe rather than another column in that report.

    Per chip it prints the coloured extent (the swatch, or the whole chip when
    that service is the active one) and the DARK-or-WHITE ink bbox beside it,
    which is the label. The label's own width is what says whether the type is
    set on a fixed cell run.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    xa, xb = int(W * x0), int(W * x1)
    ya, yb = int(H * y0), int(H * y1)

    def sat(c):
        return max(c[:3]) - min(c[:3]) > 55

    rows = {}
    for y in range(ya, yb):
        xs = [x for x in range(xa, xb) if sat(s.get_at((x, y))[:3])]
        if len(xs) >= 6:
            rows[y] = xs

    bands = []
    for y in sorted(rows):
        if bands and y == bands[-1][1] + 1:
            bands[-1][1] = y
        else:
            bands.append([y, y])

    print(f"\n== {path} {W}x{H}: {len(bands)} legend chips in x/W {x0}..{x1} ==")
    prev = None
    for a, b in bands:
        cy = (a + b) // 2
        xs = rows[cy]
        h = b - a + 1
        c = tuple(s.get_at((xs[len(xs) // 2], cy))[:3])
        step = f"  pitch {((a + b) / 2 - prev):.1f}" if prev is not None else ""
        print(
            f"\n   chip y {a}..{b}  h {h} ({h / H:.4f})  centre/H {(a + b) / 2 / H:.4f}{step}"
            f"\n      colour x {xs[0]}..{xs[-1]} ({xs[-1] - xs[0] + 1}px)  x/W {xs[0] / W:.4f}..{(xs[-1] + 1) / W:.4f}  {c}"
        )
        prev = (a + b) / 2
        # Label ink: anything clearly darker OR clearly lighter than the page,
        # so a reversed white label on a filled chip is found by the same pass
        # as a black one beside a swatch.
        ink = []
        for x in range(xa, min(W, xb + int(W * 0.02))):
            col = [s.get_at((x, y))[:3] for y in range(a, b + 1)]
            if any(max(v) < 110 or min(v) > 235 for v in col):
                ink.append(x)
        if ink:
            groups = []
            for x in ink:
                if groups and x == groups[-1][1] + 1:
                    groups[-1][1] = x
                else:
                    groups.append([x, x])
            wide = [g for g in groups if g[1] - g[0] >= 2]
            if wide:
                print(
                    f"      label ink x {wide[0][0]}..{wide[-1][1]} ({wide[-1][1] - wide[0][0] + 1}px)"
                    f"  x/W {wide[0][0] / W:.4f}..{(wide[-1][1] + 1) / W:.4f}  in {len(wide)} runs"
                )
                print("        runs: " + " ".join(f"{g[0]}..{g[1]}" for g in wide))


def report_thickness(path, cx, cy, half, r, g, b, bg=(213, 223, 239), span=8.0):
    """A stroke's thickness by COVERAGE INTEGRAL along a vertical cut.

    A tolerance test cannot compare two colours: a saturated ink sits further
    from the page than a muted one, so the same tolerance admits more of its
    antialiased skirt and reports it thicker. Integrating each pixel's position
    along the background-to-ink axis is scale-free, so red and green become
    comparable — and on an upscaled reference it also returns the true width
    rather than whichever side of a threshold the resampling happened to land.

    Same idea as the coverage field the placard tracer uses, one dimension down.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    denom = max(abs(int(r) - bg[0]), abs(int(g) - bg[1]), abs(int(b) - bg[2])) or 1

    def cov(c):
        # Project onto the background->ink axis, clamped, so an unrelated colour
        # crossing the cut contributes near zero rather than a spurious slab.
        num = max(abs(int(c[0]) - bg[0]), abs(int(c[1]) - bg[1]), abs(int(c[2]) - bg[2]))
        near = max(abs(int(c[i]) - (r, g, b)[i]) for i in range(3))
        return 0.0 if near > denom else min(1.0, num / denom)

    total, n = 0.0, 0
    for dx in range(-int(half), int(half) + 1):
        px = int(round(cx * scale)) + dx
        if not 0 <= px < W:
            continue
        acc = 0.0
        y = cy - span / 2
        while y < cy + span / 2:
            py = int(round(y * scale))
            if 0 <= py < H:
                acc += cov(s.get_at((px, py))[:3])
            y += 1.0 / scale  # one SOURCE pixel per step
        total += acc / scale  # source px -> canvas px
        n += 1
    print(f"   {path.split('/')[-1][:14]:<15} x~{cx:6.1f} y~{cy:6.1f} rgb{(r, g, b)}  thickness {total / max(n, 1):5.2f} canvas px")


def report_slants(path, tol=32, step=0.42):
    """Every legend slant as a fitted line: head, foot and slope.

    A least-squares fit over the stroke's own run centres, rather than reading
    two endpoints. Endpoints are where the stroke MEETS something — the underline
    above, the service line below — so both are exactly where the measurement is
    contaminated, and a slope taken from them is the one number the trace can
    give wrong. The fit uses only the clear middle and extrapolates.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    # Row i's underline sits at `head_y`, its service line at `line_y`.
    rows = [(name, rgb, 328.5 + 22.0 * i, 396.7 + 7.65 * i) for i, (name, rgb) in enumerate(_legend_colors()[:5])]

    print(f"\n== {path} {W}x{H}: legend slants, fitted ==")
    for name, rgb, head_y, line_y in rows:

        def near_c(c, _t=rgb):
            return max(abs(int(c[i]) - _t[i]) for i in range(3)) <= tol

        pts = []
        y = head_y + 2.0  # clear of the underline
        while y < line_y - 2.0:  # and of the line
            py = int(round(y * scale))
            xs = [x for x in range(int(70 * scale), min(W, int(105 * scale))) if near_c(s.get_at((x, py))[:3])]
            if xs and (xs[-1] - xs[0]) / scale < 6.0:
                pts.append((y, (xs[0] + xs[-1] + 1) / 2 / scale))
            y += step
        if len(pts) < 8:
            print(f"   {name}: only {len(pts)} clean rows")
            continue
        n = len(pts)
        my = sum(p[0] for p in pts) / n
        mx = sum(p[1] for p in pts) / n
        den = sum((p[0] - my) ** 2 for p in pts)
        slope = sum((p[0] - my) * (p[1] - mx) for p in pts) / den
        at = lambda yy: mx + slope * (yy - my)  # noqa: E731
        print(
            f"   {name:<5} n={n:3d}  slope {slope:5.3f}" f"   head({head_y:6.1f}) x {at(head_y):6.2f}" f"   foot({line_y:6.1f}) x {at(line_y):6.2f}"
        )


def report_color_runs(path, cx, cy, cw, ch, r, g, b, tol=60, step=1.0):
    """Per-row x-runs of ONE colour inside a canvas rect — a shape, as numbers.

    Written for the legend fold, where the question is what SHAPE a coloured
    stroke takes: a run whose x holds constant is a vertical, one that walks a
    fixed amount per row is a straight diagonal, and one whose walk accelerates
    is a curve. Reading that off a 2.35x upscale by eye gives a different answer
    every time, which is what `conventions.md` bars.

    Canvas units in and out, so the same call describes the reference and our
    own render and the two are directly comparable.
    """
    pygame.init()
    s = pygame.image.load(path)
    W, H = s.get_size()
    scale = W / 640.0
    target = (r, g, b)

    def near_c(c):
        return max(abs(int(c[i]) - target[i]) for i in range(3)) <= tol

    print(f"\n== {path}: {target} +-{tol} in canvas {cx},{cy} {cw}x{ch} ==")
    y = cy
    while y < cy + ch:
        py = int(round(y * scale))
        if not 0 <= py < H:
            y += step
            continue
        xs = [x for x in range(int(cx * scale), min(W, int((cx + cw) * scale))) if near_c(s.get_at((x, py))[:3])]
        if xs:
            groups = []
            for x in xs:
                if groups and x - groups[-1][1] <= 2:
                    groups[-1][1] = x
                else:
                    groups.append([x, x])
            cells = "  ".join(f"{u / scale:6.2f}..{(v + 1) / scale:6.2f}" for u, v in groups)
            print(f"   y {y:7.2f} | {cells}")
        y += step


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--transfer":
        # `--transfer <image> [cy] [ch]` — the transfer view's banner + rows.
        report_transfer(
            sys.argv[2] if len(sys.argv) > 2 else "_references/lcd/e233_0/transfer-hachioji-ja.png",
            *[float(v) for v in sys.argv[3:5]],
        )
    elif len(sys.argv) > 2 and sys.argv[1] == "--marks":
        # `--marks <image> <bar_cy/H> [n] [bar_h/H] [slot0/W] [pitch/W]` — what
        # sits on one row's bar. The four ratios default to the full-route view's;
        # the 6-station view is the same question asked of a differently
        # proportioned bar, so they are arguments rather than a second function.
        report_marks(
            sys.argv[2],
            float(sys.argv[3]),
            float(sys.argv[5]) if len(sys.argv) > 5 else 0.0485,
            float(sys.argv[6]) if len(sys.argv) > 6 else 0.94585,
            float(sys.argv[7]) if len(sys.argv) > 7 else 0.047015,
            n=int(sys.argv[4]) if len(sys.argv) > 4 else 20,
        )
    elif len(sys.argv) > 2 and sys.argv[1] == "--marker":
        # `--marker <image> [pad]` — the position marker's rim and drop shadow.
        report_marker(sys.argv[2], pad=int(sys.argv[3]) if len(sys.argv) > 3 else 10)
    elif len(sys.argv) > 5 and sys.argv[1] == "--ink":
        # `--ink <image> <x> <y> <w> <h> [thr]` — dark-ink bbox, canvas units.
        report_ink(sys.argv[2], *[float(v) for v in sys.argv[3:8]])
    elif len(sys.argv) > 5 and sys.argv[1] == "--map":
        # `--map <image> <x> <y> <w> <h>` — a classified map, in CANVAS units.
        report_map(sys.argv[2], *[float(v) for v in sys.argv[3:7]])
    elif len(sys.argv) > 5 and sys.argv[1] == "--pmap":
        # `--pmap <image> <x> <y> <w> <h>` — the same map read with the
        # priority-seat page's palette (green / white / blue / light ink).
        report_map(sys.argv[2], *[float(v) for v in sys.argv[3:7]], cls=_placard_cls)
    elif len(sys.argv) > 6 and sys.argv[1] == "--profile":
        # `--profile <image> <x> <y> <dx> <dy> [n]` — a raw pixel walk.
        report_profile(*([sys.argv[2]] + [int(v) for v in sys.argv[3:7]] + ([int(sys.argv[7])] if len(sys.argv) > 7 else [])))
    elif len(sys.argv) > 3 and sys.argv[1] == "--chevrons":
        # `--chevrons <image> <bar_cy/H> <x_from_canvas> [x_to]`
        report_chevrons(
            sys.argv[2],
            float(sys.argv[3]),
            float(sys.argv[4]),
            float(sys.argv[5]) if len(sys.argv) > 5 else None,
        )
    elif len(sys.argv) > 2 and sys.argv[1] == "--ends":
        # `--ends <image> [span]` — the wrap's tail and continuity chevrons.
        report_ends(sys.argv[2], span=int(sys.argv[3]) if len(sys.argv) > 3 else 95)
    elif len(sys.argv) > 5 and sys.argv[1] == "--rows":
        # `--rows <image> <x> <w> <y> <h> [thr]` — per-character bands + pitch.
        report_rows(sys.argv[2], *[float(v) for v in sys.argv[3:8]])
    elif len(sys.argv) > 2 and sys.argv[1] == "--placard":
        # `--placard <image>` — the 優先席 page: placard box, corner profile,
        # the three bands, per-band ink groups, and the two body lines.
        report_placard(sys.argv[2])
    elif len(sys.argv) > 5 and sys.argv[1] == "--fit":
        # `--fit <face> <lo> <hi> <text> [tracking]` — our own ink box per size.
        report_fit(
            sys.argv[2],
            int(sys.argv[3]),
            int(sys.argv[4]),
            sys.argv[5],
            tracking=float(sys.argv[6]) if len(sys.argv) > 6 else 0.0,
        )
    elif len(sys.argv) > 5 and sys.argv[1] == "--runs":
        # `--runs <image> <x> <y> <w> <h> [class] [step]` — per-row runs of one
        # placard class, as canvas intervals. The shape read as numbers.
        report_runs(
            sys.argv[2],
            *[float(v) for v in sys.argv[3:7]],
            klass=sys.argv[7] if len(sys.argv) > 7 else "B",
            step=float(sys.argv[8]) if len(sys.argv) > 8 else 1.0,
        )
    elif len(sys.argv) > 2 and sys.argv[1] == "--trace":
        # `--trace <image> [tol]` — the five pictograms as polygons, figure-local.
        report_trace(
            sys.argv[2],
            267.0,
            110.0,
            (123.20, 198.10, 280.50, 353.40, 426.80),
            283.0,
            tol=float(sys.argv[3]) if len(sys.argv) > 3 else 0.35,
        )
    elif len(sys.argv) > 4 and sys.argv[1] == "--figures":
        # `--figures <image> <y> <h>` — blue pictogram components + x-clusters.
        report_figures(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]))
    elif len(sys.argv) > 2 and sys.argv[1] == "--overview":
        # `--overview <image> [min_ink/W] [gap_px]` — the patterns sheet's
        # service lines, their intervals, and the stop markers on each.
        report_overview(
            sys.argv[2],
            min_ink=float(sys.argv[3]) if len(sys.argv) > 3 else 0.13,
            gap=int(sys.argv[4]) if len(sys.argv) > 4 else 20,
        )
    elif len(sys.argv) > 8 and sys.argv[1] == "--crun":
        # `--crun <image> <x> <y> <w> <h> <r> <g> <b> [tol] [step]` — per-row
        # x-runs of one colour in a canvas rect. A stroke's shape as numbers.
        report_color_runs(
            sys.argv[2],
            *[float(v) for v in sys.argv[3:7]],
            *[int(v) for v in sys.argv[7:10]],
            tol=int(sys.argv[10]) if len(sys.argv) > 10 else 60,
            step=float(sys.argv[11]) if len(sys.argv) > 11 else 1.0,
        )
    elif len(sys.argv) > 8 and sys.argv[1] == "--thick":
        # `--thick <image> <x> <y> <half> <r> <g> <b> [span]` — stroke thickness
        # by coverage integral on a vertical cut, in canvas px.
        report_thickness(
            sys.argv[2],
            *[float(v) for v in sys.argv[3:6]],
            *[int(v) for v in sys.argv[6:9]],
            span=float(sys.argv[9]) if len(sys.argv) > 9 else 8.0,
        )
    elif len(sys.argv) > 2 and sys.argv[1] == "--slants":
        # `--slants <image> [tol]` — every legend slant fitted, head/foot/slope.
        report_slants(sys.argv[2], tol=int(sys.argv[3]) if len(sys.argv) > 3 else 32)
    elif len(sys.argv) > 2 and sys.argv[1] == "--legrows":
        # `--legrows <image> [x_hi] [tol]` — per service: rectangle, underline,
        # slant head. Native-resolution steps.
        report_legend_rows(
            sys.argv[2],
            x_hi=float(sys.argv[3]) if len(sys.argv) > 3 else 105.0,
            tol=int(sys.argv[4]) if len(sys.argv) > 4 else 45,
        )
    elif len(sys.argv) > 2 and sys.argv[1] == "--legend":
        # `--legend <image> [x0/W x1/W y0/H y1/H]` — the legend chips and labels.
        report_legend(sys.argv[2], *[float(v) for v in sys.argv[3:7]])
    elif len(sys.argv) > 2 and sys.argv[1] == "--columns":
        # `--columns <image> <y_lo/H> <y_hi/H> [thr]` — the name band of one row.
        report_columns(
            sys.argv[2],
            (float(sys.argv[3]), float(sys.argv[4])),
            thr=int(sys.argv[5]) if len(sys.argv) > 5 else 175,
        )
    else:
        main()

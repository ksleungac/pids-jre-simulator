# SPDX-License-Identifier: MIT
"""Throwaway: what colour shift puts the badge classifier at the diffs #137 reports, and would a
normalised metric survive it?

#137's reporter (2560x1440, HDR display) records `badge_diff` medians of 70-102 across seven drives
and 39.2 across two, against a documented <15 for real reads and a reject at 50. Their speed and
distance reads are NORMAL over the same frames (score 0.88-0.92 against an observed 0.880), and
those two binarise to shape while the badge compares raw RGB. So the badge's absolute-colour
comparison is the only reader that fails, which is the signature of a global colour-pipeline shift
rather than a geometry, sharpness or capture fault.

We do not have the reporter's framebuffer — the JSONL carries scores, not images, and their video is
a 720p SDR tonemap. So this works on the committed anchors, plus the one committed badge cell that
was never an anchor, and asks two questions:

  1. What magnitude of shift (offset / gain / gamma) drives `mean_abs_diff` to 39 and to 78?
     Stands in the live cell with its own anchor, which is good to ~15 since that is where real
     within-state reads sit. So the figures below are the shift PLUS up to ~15 of ordinary
     mismatch, and are a floor on the shift rather than a point estimate.

  2. Does a shift-invariant metric still separate the three states? The classifier only has to
     rank six anchors, so it needs within-state < cross-state, not a small absolute number. If
     z-normalising each cell preserves that ordering under a shift that breaks raw diff, the fix
     is a metric change and needs no new calibration data.

Run: uv run _dev_scripts/_badge_colour_shift.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np  # noqa: E402

from app_paths import project_root  # noqa: E402
from auto_input.ocr import BADGE_ANCHOR_FILES, BADGE_DIFF_REJECT, load_badge_anchors  # noqa: E402
from auto_input.ocr import classify_badge_state as production_classify  # noqa: E402

REPORTED = {"good drives": 39.2, "bad drives": 78.0, "worst drive": 102.4}


NONANCHOR = project_root() / "_tests" / "fixtures" / "ocr" / "1080p" / "cells" / "badge__reporter_slip_lowspeed.png"


def load_nonanchor_cell():
    """The one committed badge cell that was never an anchor — a reporter's capture.

    Shifting an anchor and matching it against itself is honest about the TRANSFORM and
    silent about the pixels: within-state mismatch starts at 0 instead of the ~12 a real
    read carries. This cell starts where a real one does, so a shift that survives on it
    survives with the ordinary mismatch already on the board.
    """
    if not NONANCHOR.exists():
        return None
    import pygame

    pygame.init()
    arr = pygame.surfarray.array3d(pygame.image.load(str(NONANCHOR)))
    return ("MOVING", np.transpose(arr, (1, 0, 2)))


def raw_diff(cell, anchor):
    """The production metric — `classify_badge_state`'s mean absolute difference."""
    return float(np.abs(cell.astype(int) - anchor.astype(int)).mean())


def z_diff(cell, anchor):
    """Shift-and-gain invariant: compare after per-cell standardisation.

    Kills any affine `v -> a*v + b`, which is what a display/capture pipeline change looks like to
    first order. Scaled back onto a 0-255 axis so the numbers read like the production ones.
    """

    def z(x):
        x = x.astype(float)
        s = x.std()
        return (x - x.mean()) / (s if s > 1e-6 else 1.0)

    return float(np.abs(z(cell) - z(anchor)).mean() * 40.0)


def ncc_dist(cell, anchor):
    """1 - Pearson r, on a 0-100 axis. Affine-invariant like z-norm, but unlike it the
    STRUCTURE has to agree: noise correlates ~0 with a badge whatever its levels, so
    garbage lands near 100 while a level-shifted real badge stays near 0."""
    a = cell.astype(float).ravel()
    b = anchor.astype(float).ravel()
    a -= a.mean()
    b -= b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 100.0
    return float((1.0 - (a @ b) / (na * nb)) * 100.0)


def _r(a, b):
    a = a - a.mean()
    b = b - b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return None
    return float(a @ b / (na * nb))


def ncc_chan_mean(cell, anchor):
    """Per-CHANNEL correlation, averaged. Cancels a per-channel gain, which the flattened
    form cannot: raveling R,G,B into one vector makes `v -> a*v + b` cancel only when `a`
    is the same for all three. A colour cast is exactly the case where it is not."""
    rs = [_r(cell[:, :, c].astype(float).ravel(), anchor[:, :, c].astype(float).ravel()) for c in range(3)]
    if any(r is None for r in rs):
        return 100.0
    return float((1.0 - sum(rs) / 3.0) * 100.0)


def ncc_chan_max(cell, anchor):
    """As above but the WORST channel decides — stricter, and the question is whether it
    is too strict to still accept a real badge under a heavy cast."""
    rs = [_r(cell[:, :, c].astype(float).ravel(), anchor[:, :, c].astype(float).ravel()) for c in range(3)]
    if any(r is None for r in rs):
        return 100.0
    return float((1.0 - min(rs)) * 100.0)


def _chan_z(x):
    """Standardise each channel, then flatten. A per-channel affine cancels, but the three
    channels still correlate as ONE vector — so a channel that goes flat contributes zeros
    instead of destroying the score, which is what killed the per-channel forms above."""
    out = np.empty(x.shape, float)
    for c in range(3):
        ch = x[:, :, c].astype(float)
        s = ch.std()
        out[:, :, c] = (ch - ch.mean()) / s if s > 1e-6 else 0.0
    return out.ravel()


def ncc_chan_znorm(cell, anchor):
    """Flat NCC over per-channel-standardised inputs — cast-invariant, single correlation."""
    a, b = _chan_z(cell), _chan_z(anchor)
    r = _r(a, b)
    return 100.0 if r is None else float((1.0 - r) * 100.0)


def ncc_luma(cell, anchor):
    """Flat NCC on luminance only. Discards colour entirely, which the desaturation result
    says is affordable: fully grey anchors still self-classify on the RAW pass, so the text
    content carries the discrimination and the fill colour only helps."""
    a = cell.astype(float) @ np.array([0.2126, 0.7152, 0.0722])
    b = anchor.astype(float) @ np.array([0.2126, 0.7152, 0.0722])
    r = _r(a.ravel(), b.ravel())
    return 100.0 if r is None else float((1.0 - r) * 100.0)


def classify(cell, anchors, metric):
    best, best_d = None, float("inf")
    for state, arrs in anchors.items():
        for a in arrs:
            if a.shape != cell.shape:
                continue
            d = metric(cell, a)
            if d < best_d:
                best, best_d = state, d
    return best, best_d


def shifts():
    """Candidate global transforms, each a plausible display/capture pipeline change."""
    out = []
    for k in range(0, 121, 10):
        out.append((f"offset +{k}", lambda x, k=k: np.clip(x.astype(float) + k, 0, 255)))
    for g in (1.1, 1.25, 1.5, 1.75, 2.0, 2.5):
        out.append((f"gain x{g}", lambda x, g=g: np.clip(x.astype(float) * g, 0, 255)))
    for y in (0.7, 0.55, 0.45, 0.35, 0.25):
        out.append((f"gamma {y}", lambda x, y=y: 255.0 * np.power(np.clip(x.astype(float), 0, 255) / 255.0, y)))

    # Desaturation is the one candidate a per-array z-norm cannot be assumed to survive: it is a
    # CHANNEL-RELATIVE change, not a global affine, and the badge's three states are separated
    # partly by hue (green MOVING/STOPPED against blue PASSING). The reporter's video shows their
    # badge at about half our anchors' green excess, which is what put this on the list — though
    # that video is a YouTube SDR tonemap and cannot be read as their framebuffer.
    def desat(x, s):
        lum = x.astype(float) @ np.array([0.2126, 0.7152, 0.0722])
        return np.clip(lum[..., None] + s * (x.astype(float) - lum[..., None]), 0, 255)

    for s in (0.8, 0.6, 0.5, 0.4, 0.2, 0.0):
        out.append((f"desat s={s}", lambda x, s=s: desat(x, s)))

    # And the combination, since a tonemap does both.
    for k, s in ((40, 0.6), (90, 0.6), (40, 0.4), (90, 0.4)):
        out.append((f"+{k} & desat {s}", lambda x, k=k, s=s: np.clip(desat(x, s) + k, 0, 255)))

    # The two shapes a real pipeline applies, as opposed to the analytic ones above. Neither
    # is an affine on encoded values, which is the point of listing them separately: the
    # sweep's offsets and gains are diagnostics for reading a magnitude off the reporter's
    # numbers, while these two are what an HDR desktop and a ReShade preset actually do.
    for paper in (240.0, 400.0):
        out.append((f"hdr paper {paper:.0f}", lambda x, p=paper: hdr_paperwhite(x, p)))
    out.append(("reshade mild", lambda x: reshade_grade(x)))
    out.append(("reshade strong", lambda x: reshade_grade(x, lift=40.0, gain=1.5, gamma=0.8, sat=1.6)))

    # The per-channel casts T1 pins, at the exact parameters T1 uses, so the raw_owns flag
    # in that file is read off this table rather than guessed.
    out.append(("warm cast", lambda x: _cast(x, 2.2, 1.0, 0.4)))
    out.append(("cool cast", lambda x: _cast(x, 0.4, 1.0, 2.2)))
    out.append(("green pull cast", lambda x: _cast(x, 1.0, 3.5, 1.0)))
    return out


def _srgb_to_lin(v):
    v = v / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(v):
    v = np.clip(v, 0.0, 1.0)
    return 255.0 * np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def hdr_paperwhite(x, paper=240.0, sdr=80.0):
    """SDR content composited at a paper-white above 80 nits, then tonemapped back down.

    Windows scales SDR content into the scRGB swap chain by paper-white/80, and anything
    downstream that treats the result as ordinary SDR sees a frame whose whole curve is
    lifted and whose top end is compressed. Done in LINEAR light, which is where the
    scaling happens — an offset on encoded values is a different curve and lands the
    shadows in the wrong place.
    """
    lin = _srgb_to_lin(x.astype(float)) * (paper / sdr)
    return _lin_to_srgb(lin / (1.0 + lin))  # Reinhard shoulder, the tonemap back


def reshade_grade(x, lift=18.0, gain=1.25, gamma=0.9, sat=1.35):
    """Lift / gain / gamma plus a saturation push — the shape of a common ReShade preset.

    ReShade grades INSIDE the game's swap chain, so its output is what the desktop
    composites and therefore what DDA hands dxcam: the OCR reads the graded image, not the
    game's own. Saturation is included because it is the one component a per-array affine
    normalisation is not guaranteed to survive — it is channel-relative.
    """
    v = np.clip(x.astype(float) * gain + lift, 0, 255)
    v = 255.0 * np.power(v / 255.0, gamma)
    grey = v.mean(axis=2, keepdims=True)
    return np.clip(grey + (v - grey) * sat, 0, 255)


def _cast(x, rg, gg, bg):
    """Per-channel gain — a colour cast. Both an HDR tonemap and a ReShade preset move the
    channels by different amounts, which no single-number offset or gain can express."""
    v = x.astype(float) * np.array([rg, gg, bg])
    return np.clip(v, 0, 255)


def _desat(x, s):
    lum = x.astype(float) @ np.array([0.2126, 0.7152, 0.0722])
    return np.clip(lum[..., None] + s * (x.astype(float) - lum[..., None]), 0, 255)


# Each axis is walked from "no change" outward until production stops classifying 6/6.
# The parameter is whatever that axis's knob is; the label is what a person would call it.
AXES = [
    ("lift", [(f"+{k}", lambda x, k=k: np.clip(x.astype(float) + k, 0, 255)) for k in range(0, 221, 20)]),
    ("gain", [(f"x{g:.1f}", lambda x, g=g: np.clip(x.astype(float) * g, 0, 255)) for g in np.arange(1.0, 6.01, 0.5)]),
    (
        "crush",
        [(f"x{g:.2f}", lambda x, g=g: np.clip(x.astype(float) * g, 0, 255)) for g in (1.0, 0.7, 0.5, 0.35, 0.25, 0.15, 0.08, 0.04)],
    ),
    (
        "gamma",
        [
            (f"y{y:.2f}", lambda x, y=y: 255.0 * np.power(np.clip(x.astype(float), 0, 255) / 255.0, y))
            for y in (1.0, 0.7, 0.5, 0.35, 0.25, 0.15, 0.08)
        ],
    ),
    ("desat", [(f"s{s:.1f}", lambda x, s=s: _desat(x, s)) for s in (1.0, 0.6, 0.3, 0.0)]),
    (
        "warm cast",
        [
            (f"R{r:.1f}/B{b:.1f}", lambda x, r=r, b=b: _cast(x, r, 1.0, b))
            for r, b in ((1.0, 1.0), (1.3, 0.8), (1.7, 0.6), (2.2, 0.4), (3.0, 0.2), (4.0, 0.05))
        ],
    ),
    (
        "cool cast",
        [
            (f"R{r:.1f}/B{b:.1f}", lambda x, r=r, b=b: _cast(x, r, 1.0, b))
            for r, b in ((1.0, 1.0), (0.8, 1.3), (0.6, 1.7), (0.4, 2.2), (0.2, 3.0), (0.05, 4.0))
        ],
    ),
    ("green pull", [(f"G{g:.1f}", lambda x, g=g: _cast(x, 1.0, g, 1.0)) for g in (1.0, 1.4, 1.9, 2.5, 3.5, 5.0)]),
    (
        "hdr paper",
        [(f"{p:.0f} nits", lambda x, p=p: hdr_paperwhite(x, p)) for p in (80, 240, 400, 800, 1600, 3200, 6400)],
    ),
    (
        "reshade",
        [
            (f"x{s:.1f}", lambda x, s=s: reshade_grade(x, 18.0 * s, 1 + 0.25 * s, 1 - 0.1 * s, 1 + 0.35 * s))
            for s in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        ],
    ),
]


def compare_ncc_variants(anchors) -> None:
    """Flattened NCC against two per-channel forms, on both halves of the question.

    A metric that survives more shifts is only better if it still REFUSES garbage — the
    fallback must stay stricter than the raw pass it sits behind (`principles.md` § "A
    fallback must be stricter than the path it replaces"). So every candidate is scored on
    the axes AND on the garbage set, and the gap between worst-real and best-garbage is
    what decides whether a threshold can live between them.
    """
    subjects = [(st, a) for st, arrs in anchors.items() for a in arrs]
    shape = subjects[0][1].shape
    rng = np.random.default_rng(0)
    garbage = {
        "black": np.zeros(shape, np.uint8),
        "white": np.full(shape, 255, np.uint8),
        "uniform 128": np.full(shape, 128, np.uint8),
        "uniform noise": rng.integers(0, 256, shape, dtype=np.uint8),
        "dark noise": rng.integers(0, 60, shape, dtype=np.uint8),
        "h-gradient": np.tile(np.linspace(0, 255, shape[1], dtype=np.uint8)[None, :, None], (shape[0], 1, 3)),
    }

    print("\n=== NCC variants: how many axis rungs survive, and can garbage still be refused ===")
    print(f"{'metric':<16}{'rungs 6/6':>11}{'worst real':>12}{'best garbage':>14}{'gap':>8}")
    for name, metric in (
        ("flat (current)", ncc_dist),
        ("per-chan mean", ncc_chan_mean),
        ("per-chan max", ncc_chan_max),
        ("per-chan znorm", ncc_chan_znorm),
        ("luma only", ncc_luma),
    ):
        rungs_ok = tot_rungs = 0
        worst_real = 0.0
        for _axis, steps in AXES:
            for _lbl, fn in steps:
                tot_rungs += 1
                ok = 0
                for true_state, a in subjects:
                    cell = fn(a).astype(np.uint8)
                    s, d = classify(cell, anchors, metric)
                    ok += int(s == true_state)
                    if s == true_state:
                        worst_real = max(worst_real, d)
                rungs_ok += int(ok == len(subjects))
        best_garbage = min(classify(g, anchors, metric)[1] for g in garbage.values())
        print(f"{name:<16}{rungs_ok:>7}/{tot_rungs}{worst_real:>12.1f}{best_garbage:>14.1f}" f"{best_garbage - worst_real:>8.1f}")


def ladder(anchors) -> list:
    """Per axis: how far can it go and still classify 6/6? Emit the last good rung and the
    first bad one, plus a midpoint, so the sheet shows the survivable range AND its edge.

    Clipping is what eventually kills every axis. Once the badge's bright fill saturates,
    the structure the shape-only pass matches on is destroyed rather than displaced, and no
    normalisation can recover it — which is the honest bound on the whole approach.
    """
    subjects = [(st, a) for st, arrs in anchors.items() for a in arrs]

    def verdict(fn):
        ok, vias = 0, set()
        for true_state, a in subjects:
            s, _d, v, _lvl = production_classify(fn(a).astype(np.uint8), anchors)
            ok += int(s == true_state)
            vias.add(str(v))
        return ok, len(subjects), vias

    rungs = []
    print(f"\n=== how far can each axis go and still classify 6/6 ({len(AXES)} axes) ===")
    for axis, steps in AXES:
        scored = [(lbl, fn, *verdict(fn)) for lbl, fn in steps]
        good = [s for s in scored if s[2] == s[3]]
        bad = [s for s in scored if s[2] != s[3]]
        last_good = good[-1] if good else scored[0]
        first_bad = bad[0] if bad else None
        mid = good[len(good) // 2] if len(good) > 2 else None
        print(
            f"  {axis:<11} survives to {last_good[0]:<12} ({len(good)}/{len(scored)} rungs)"
            + (f"   breaks at {first_bad[0]} -> {first_bad[2]}/{first_bad[3]}" if first_bad else "   never broke in range")
        )
        for s in [x for x in (mid, last_good, first_bad) if x is not None]:
            rungs.append((f"{axis} {s[0]}", s[1], s[2], s[3], s[4]))
    return rungs


def render_sheet(anchors, rungs) -> None:
    """Contact sheet: what the badge LOOKS like at each rung, beside what production says.

    The numbers say it survives; the picture says how unrecognisable it is by then, which
    is the part a table cannot carry.
    """
    import pygame

    pygame.init()
    order = [(st, a) for st in ("MOVING", "STOPPED", "PASSING") for a in anchors.get(st, [])]
    ch, cw = order[0][1].shape[:2]
    zoom, pad, label_w = 3, 5, 300
    sheet = pygame.Surface((label_w + len(order) * (cw * zoom + pad) + pad, (ch * zoom + pad) * len(rungs) + pad))
    sheet.fill((22, 22, 26))
    font = pygame.font.Font(str(project_root() / "fonts" / "HelveticaNeue-Medium.otf"), 15)

    y = pad
    for label, fn, ok, tot, vias in rungs:
        x = label_w
        for _st, a in order:
            cell = fn(a).astype(np.uint8)
            surf = pygame.surfarray.make_surface(np.transpose(cell, (1, 0, 2)))
            sheet.blit(pygame.transform.scale(surf, (cw * zoom, ch * zoom)), (x, y))
            x += cw * zoom + pad
        via = "/".join(sorted(v for v in vias if v != "None")) or "refused"
        good = ok == tot
        sheet.blit(font.render(label, True, (240, 240, 240)), (8, y + 6))
        sheet.blit(
            font.render(f"{ok}/{tot} correct   via {via}", True, (120, 220, 140) if good else (240, 120, 110)),
            (8, y + 26),
        )
        y += ch * zoom + pad
    out = project_root() / "screenshot_badge_shift_ladder.png"
    pygame.image.save(sheet, str(out))
    print(f"\n-> {out}   columns: MOVING en/ja, STOPPED en/ja, PASSING en/ja")


def digit_readers_under_shift() -> None:
    """Where do the DIGIT readers break under the same shifts, and on which guard?

    The badge is the first casualty of a level shift and the reason is written down, but
    "the digit readers binarise to shape so they are invariant" is only true inside two
    ABSOLUTE bounds — `OTSU_CLAMP_HI` (the adaptive threshold cannot exceed 100) and
    `OTSU_MIN_CONTRAST` (a band flatter than 60 falls back to a fixed 70). Both are the
    same species as `BADGE_DIFF_REJECT`: a number that was right for the captures it was
    measured on. This walks the committed cells up the same ramp and prints the first
    shift at which each read changes, plus the threshold the cell resolved to.
    """
    import json

    import pygame

    from auto_input import ocr as O
    from auto_input.hud_layout import DOWNSCALE_PROFILE

    pygame.init()
    res_dir = project_root() / "_tests" / "fixtures" / "ocr" / "1080p"
    manifest = json.loads((res_dir / "manifest.json").read_text(encoding="utf-8"))
    templates = O.build_templates()
    red = O.build_templates(O.DEFAULT_TEMPLATES_DIR / "digits_red")
    # Same seg as production and as T3 — a wrong scale here reads 0/23 at ZERO shift, which
    # is what caught it. The unshifted row is the calibration: anything but 23/23 there means
    # the harness is broken, not the readers (`principles.md` § "A measurement is a claim").
    seg = O.seg_for_scale(DOWNSCALE_PROFILE.scale)

    readers = {
        "speed": lambda c: O.read_speed(c, templates, seg=seg)[0],
        "speed_limit": lambda c: O.read_speed_limit(c, templates, seg=seg, red_templates=red)[0],
        "stopping_offset": lambda c: O.read_stopping_offset(c, templates, seg=seg)[0],
    }
    cells = []
    for e in manifest["cells"]:
        if e["type"] not in readers:
            continue
        p = res_dir / "cells" / f"{e['type']}__{e['stem']}.png"
        if p.exists():
            arr = np.transpose(pygame.surfarray.array3d(pygame.image.load(str(p))), (1, 0, 2))
            cells.append((e["type"], e["stem"], arr, e["expected"]))

    print(f"\n=== digit readers under the same shifts ({len(cells)} committed cells) ===")
    print(f"{'shift':<16}{'correct':>9}{'thr lo-hi':>12}   first cells to break")
    for name, fn in shifts():
        ok, broke, thrs = 0, [], []
        for ctype, stem, arr, expected in cells:
            cell = fn(arr).astype(np.uint8)
            thrs.append(O._cell_dark_threshold(cell, seg))
            got = readers[ctype](cell)
            if got == expected:
                ok += 1
            else:
                broke.append(f"{stem}={got}")
        print(f"{name:<16}{ok:>6}/{len(cells)}{min(thrs):>7.0f}-{max(thrs):<4.0f}   {', '.join(broke[:3])}")


def main() -> int:
    anchors = load_badge_anchors(project_root() / "ocr_templates" / "badges")
    n = sum(len(v) for v in anchors.values())
    print(f"anchors loaded: {n} across {list(anchors)}   (declared {BADGE_ANCHOR_FILES})")
    if n == 0:
        print("FAIL: no anchors on disk")
        return 1
    print(f"production reject threshold: {BADGE_DIFF_REJECT}\n")

    # Baseline: every anchor against the anchor set, raw and normalised. This is the
    # separation the classifier lives on, with NO shift applied.
    print("=== baseline, no shift — within-state vs cross-state ===")
    for label, metric in (("raw", raw_diff), ("z-norm", z_diff)):
        within, cross = [], []
        for st, arrs in anchors.items():
            for a in arrs:
                for st2, arrs2 in anchors.items():
                    for b in arrs2:
                        if a is b or a.shape != b.shape:
                            continue
                        (within if st == st2 else cross).append(metric(a, b))
        print(f"  {label:7} within {np.median(within):6.1f}   cross {np.median(cross):6.1f}   margin {np.median(cross) - np.median(within):6.1f}")

    # Q1 — which shift reproduces the reported diffs, and does the classifier survive it?
    print("\n=== shift sweep: best raw diff (what production computes) and whether the state still wins ===")
    print(f"{'shift':<14}{'raw diff':>10}{'raw rank':>10}{'raw ok':>9}{'z diff':>9}{'z ok':>7}{'ncc':>9}{'ncc ok':>7}   note")
    subjects = [(st, a) for st, arrs in anchors.items() for a in arrs]
    extra = load_nonanchor_cell()
    if extra is not None:
        subjects.append(extra)
        print(f"  (+1 non-anchor subject: {NONANCHOR.name}, the one committed badge cell cut from another capture)")

    for name, fn in shifts():
        raw_ds, raw_hit, raw_rank, z_ds, z_hit, n_ds, n_hit, tot = [], 0, 0, [], 0, [], 0, 0
        for true_state, a in subjects:
            shifted = fn(a).astype(np.uint8)
            tot += 1
            s_raw, d_raw = classify(shifted, anchors, raw_diff)
            s_z, d_z = classify(shifted, anchors, z_diff)
            s_n, d_n = classify(shifted, anchors, ncc_dist)
            raw_ds.append(d_raw)
            z_ds.append(d_z)
            n_ds.append(d_n)
            n_hit += int(s_n == true_state)
            # "ok" = right state AND production would not have rejected it
            raw_hit += int(s_raw == true_state and d_raw <= BADGE_DIFF_REJECT)
            # Separately: did raw pick the right anchor at all, threshold aside? The two
            # questions come apart, and which one fails decides what the bug IS. A wrong
            # rank means the metric stopped discriminating; a right rank over the reject
            # means the read was correct and the threshold threw it away.
            raw_rank += int(s_raw == true_state)
            z_hit += int(s_z == true_state)
        med = float(np.median(raw_ds))
        note = ""
        for k, v in REPORTED.items():
            if abs(med - v) < 6:
                note = f"<- matches {k} ({v})"
        print(
            f"{name:<14}{med:>10.1f}{raw_rank:>7}/{tot}{raw_hit:>6}/{tot}{float(np.median(z_ds)):>9.1f}{z_hit:>4}/{tot}{float(np.median(n_ds)):>9.2f}{n_hit:>4}/{tot}   {note}"
        )

    print(
        "\nraw ok = production picks the right state AND clears the 50 reject."
        "\nz ok   = the z-normalised metric picks the right state (it has no absolute threshold)."
    )

    # Per-SUBJECT spread for the two real-pipeline shapes. The sweep above prints a median,
    # and a T1 entry has to say which pass owns a transform for EVERY subject — a transform
    # whose subjects straddle the 50 reject cannot be pinned either way, so the range is
    # what decides whether it is a usable test case.
    print("\n=== per-subject range, real-pipeline shapes (what a T1 raw_owns flag must hold for) ===")
    print(f"{'shape':<18}{'raw diff min':>14}{'max':>8}   via seen           correct")
    for name, fn in shifts():
        if not (name.startswith("hdr") or name.startswith("reshade") or "cast" in name or "desat" in name):
            continue
        ds, vias, ok = [], set(), 0
        for true_state, a in subjects:
            cell = fn(a).astype(np.uint8)
            s, d, v, _lvl = production_classify(cell, anchors)
            ds.append(d)
            vias.add(str(v))
            ok += int(s == true_state)
        print(f"{name:<18}{min(ds):>14.1f}{max(ds):>8.1f}   {'/'.join(sorted(vias)):<18} {ok}/{len(subjects)}")

    # Q3 — can the normalised metric REFUSE garbage? A second-chance path that accepts
    # everything is the inversion `principles.md § "A fallback must be stricter than the
    # path it replaces"` bars: raw rejects black-screen frames at 60-110 precisely so the
    # detector is not fed a state during a teleport or a dark cell. If z-norm has no
    # separation between a shifted badge and noise, it cannot be gated and must not ship.
    shape = next(iter(anchors.values()))[0].shape
    rng = np.random.default_rng(0)
    garbage = {
        "black": np.zeros(shape, np.uint8),
        "white": np.full(shape, 255, np.uint8),
        "uniform 40": np.full(shape, 40, np.uint8),
        "uniform 128": np.full(shape, 128, np.uint8),
        "uniform noise": rng.integers(0, 256, shape, dtype=np.uint8),
        "dark noise": rng.integers(0, 60, shape, dtype=np.uint8),
        "h-gradient": np.tile(np.linspace(0, 255, shape[1], dtype=np.uint8)[None, :, None], (shape[0], 1, 3)),
    }
    print("\n=== can the normalised metric refuse garbage? ===")
    print(f"{'input':<18}{'raw diff':>10}{'raw verdict':>14}{'z diff':>9}{'ncc dist':>12}")
    for name, g in garbage.items():
        _, dr = classify(g, anchors, raw_diff)
        _, dz = classify(g, anchors, z_diff)
        _, dn = classify(g, anchors, ncc_dist)
        print(f"{name:<18}{dr:>10.1f}{('REJECT' if dr > BADGE_DIFF_REJECT else 'accept'):>14}{dz:>9.1f}{dn:>12.2f}")

    # The number that matters: the worst z diff a REAL (shifted) badge produces, against
    # the best z diff any garbage produces. A gap means a threshold exists between them.
    worst_real = 0.0
    for _name, fn in shifts():
        for arrs in anchors.values():
            for a in arrs:
                _, d = classify(fn(a).astype(np.uint8), anchors, z_diff)
                worst_real = max(worst_real, d)
    best_garbage = min(classify(g, anchors, z_diff)[1] for g in garbage.values())
    print(f"\nworst z diff over ALL shifted real badges : {worst_real:.1f}")
    print(f"best  z diff over garbage                 : {best_garbage:.1f}")
    print(
        f"gap                                       : {best_garbage - worst_real:+.1f}"
        f"   -> {'a threshold fits between them' if best_garbage > worst_real else 'NO SEPARATION — do not ship the fallback'}"
    )

    digit_readers_under_shift()
    compare_ncc_variants(anchors)
    render_sheet(anchors, ladder(anchors))
    return 0


if __name__ == "__main__":
    sys.exit(main())

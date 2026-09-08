# SPDX-License-Identifier: MIT
"""Throwaway: what colour shift puts the badge classifier at the diffs #137 reports, and would a
normalised metric survive it?

#137's reporter (2560x1440, HDR display) records `badge_diff` medians of 70-102 across seven drives
and 39.2 across two, against a documented <15 for real reads and a reject at 50. Their speed and
distance reads are NORMAL over the same frames (score 0.88-0.92 against an observed 0.880), and
those two binarise to shape while the badge compares raw RGB. So the badge's absolute-colour
comparison is the only reader that fails, which is the signature of a global colour-pipeline shift
rather than a geometry, sharpness or capture fault.

We do not have the reporter's pixels — the JSONL carries scores, not images — so this works on the
COMMITTED anchors instead and asks two questions:

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

REPORTED = {"good drives": 39.2, "bad drives": 78.0, "worst drive": 102.4}


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
    return out


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
    print(f"{'shift':<14}{'raw diff':>10}{'raw ok':>9}{'z diff':>9}{'z ok':>7}{'ncc':>9}{'ncc ok':>7}   note")
    for name, fn in shifts():
        raw_ds, raw_hit, z_ds, z_hit, n_ds, n_hit, tot = [], 0, [], 0, [], 0, 0
        for true_state, arrs in anchors.items():
            for a in arrs:
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
                z_hit += int(s_z == true_state)
        med = float(np.median(raw_ds))
        note = ""
        for k, v in REPORTED.items():
            if abs(med - v) < 6:
                note = f"<- matches {k} ({v})"
        print(
            f"{name:<14}{med:>10.1f}{raw_hit:>6}/{tot}{float(np.median(z_ds)):>9.1f}{z_hit:>4}/{tot}{float(np.median(n_ds)):>9.2f}{n_hit:>4}/{tot}   {note}"
        )

    print(
        "\nraw ok = production picks the right state AND clears the 50 reject."
        "\nz ok   = the z-normalised metric picks the right state (it has no absolute threshold)."
    )

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
    return 0


if __name__ == "__main__":
    sys.exit(main())

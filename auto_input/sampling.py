"""One HUD sample: grab-frame in, fully-read-and-guarded values out.

THE single per-cycle read path. `AutoDriver._run` (production) and
`_dev_scripts/ocr_observe.py` (diagnostic) both call `read_hud`, so the diagnostic
observes byte-for-byte what production observes — crop geometry, reader order, and
every cross-attribute guard. The predecessor diagnostic carried its OWN copy of this
sequence and it drifted (cropping via a pygame Surface off a FULL-desktop grab while
production sliced numpy off a REGION grab), which makes a corpus collected with it
suspect exactly where it matters most: diagnosing a production misread. Any future
diagnostic MUST call this function rather than re-derive it.

# CONTRACT: reader order and guard order are load-bearing, not stylistic.
#   0. if the frame is downscaled (downscale_hud), that happens BEFORE read_hud and the
#      caller passes DOWNSCALE_PROFILE — every cell must be cropped from the SAME frame,
#      never a mix of native and downscaled geometry
#   1. all four cells cropped from ONE frame (same instant — cross-attribute guards
#      compare speed against distance against badge, so a re-grab between cells breaks them)
#   2. badge classified FIRST — it gates the offset read and the score gate
#   3. tenths read against the integer's raw string (never //10) — see read_speed_tenths
#   4. offset accepted only at badge==STOPPED, BEFORE the score gate
#   5. score gate runs after ALL reads so speed/distance/limit are gated together
#   6. distance guard runs LAST and takes the PRIOR frame's badge
# See auto_input/README.md § "Cross-attribute reject" / "Badge-reject score gate" /
# "Distance plausibility guard".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .hud_layout import DOWNSCALE_PROFILE
from .ocr import (
    classify_badge_state,
    read_distance,
    read_speed,
    read_speed_limit,
    read_speed_tenths,
    read_stopping_offset,
)


def _box_axis(a: np.ndarray, n_out: int) -> np.ndarray:
    """Exact area-average along axis 0, from `a.shape[0]` samples down to `n_out`.

    Each output sample is the mean of the input span it covers, fractional edges weighted by
    how much of the edge pixel falls inside. Computed from a cumulative sum, so the cost is
    one pass over the data regardless of the downscale factor — the naive form (a dense
    n_in x n_out weight matrix per axis) is the same arithmetic and ran ~100x slower.
    """
    n_in = a.shape[0]
    if n_in == n_out:
        return a
    f = a.astype(np.float32)
    # csum[i] = total of rows 0..i-1, so an integral to any integer boundary is one lookup.
    csum = np.concatenate([np.zeros((1, *f.shape[1:]), np.float32), np.cumsum(f, axis=0)], axis=0)
    step = n_in / n_out
    edges = np.arange(n_out + 1, dtype=np.float64) * step

    def integral(p: np.ndarray) -> np.ndarray:
        # Clipped so p == n_in resolves as csum[n_in-1] + 1.0 * row[n_in-1] == csum[n_in].
        i = np.clip(np.floor(p).astype(np.int64), 0, n_in - 1)
        frac = (p - i).astype(np.float32).reshape(-1, *([1] * (f.ndim - 1)))
        return csum[i] + frac * f[i]

    return (integral(edges[1:]) - integral(edges[:-1])) / np.float32(step)


def _resize_area(arr: np.ndarray, th: int, tw: int) -> np.ndarray:
    """Area-average (box) resample of an (H, W, C) image to (th, tw, C).

    The correct downsampler at ANY ratio: an output pixel is the mean of exactly the input
    pixels it covers, so nothing aliases however far the image shrinks. Bilinear — the
    previous implementation — always samples a fixed 2x2 neighbourhood no matter the scale
    factor, which is adequate around 0.75 (1440p) but progressively ignores more of the input
    as the ratio drops: at 4K's 0.5 an output pixel covers 4 inputs, at 5K's 0.36 nearly 8.
    Area removes the ratio from the question entirely.

    Distinct from `ocr._resize_nn`, which snaps a TEMPLATE onto a glyph's exact box and must
    NOT average — it compares binary masks and any interpolation there would invent grey.

    `rint` before the cast, never a bare `astype`: uint8 conversion TRUNCATES, which biases
    every pixel down by up to 1 LSB. A uniform field of 137 came back as 136. One level of
    systematic darkening is precisely the margin the binarization threshold works in
    (`critical_lessons.md §7`).
    """
    out = np.swapaxes(_box_axis(np.swapaxes(_box_axis(arr, th), 0, 1), tw), 0, 1)
    return np.rint(np.clip(out, 0, 255)).astype(arr.dtype)


def downscale_hud(frame_bgra: np.ndarray, src_profile) -> np.ndarray:
    """Cut the HUD out of a capture-region frame and downscale it to the 1080p model.

    This is the whole of multi-resolution support: shrink the INPUT into one model rather
    than calibrating a model per resolution. The caller then reads with `DOWNSCALE_PROFILE`
    — the returned frame IS the HUD, so its origin is (0, 0). A 1080p capture is already
    the right size and comes back as a plain copy.

    Resizes the HUD RECT, not the whole capture region: the region is ~14x the pixels for
    the same result, and the HUD is the only part any reader looks at.
    """
    hx, hy, hw, hh = src_profile.hud_bbox_in_capture
    hud = frame_bgra[hy : hy + hh, hx : hx + hw]
    # Fail loud on a short grab. numpy slices past the end SILENTLY, and downscaling a
    # partial HUD is worse than not downscaling at all: the resize restores it to the model's
    # dimensions, so every downstream shape check passes and the readers return confident
    # garbage. The capture loop catches this, logs it, and skips the cycle.
    if hud.shape[0] != hh or hud.shape[1] != hw:
        raise ValueError(
            f"HUD crop is {hud.shape[1]}x{hud.shape[0]}, expected {hw}x{hh} — the captured frame "
            f"({frame_bgra.shape[1]}x{frame_bgra.shape[0]}) is smaller than the "
            f"{src_profile.desktop_w}x{src_profile.desktop_h} capture region implies."
        )
    tw, th = DOWNSCALE_PROFILE.hud_bbox_in_capture[2], DOWNSCALE_PROFILE.hud_bbox_in_capture[3]
    if hud.shape[0] == th and hud.shape[1] == tw:
        return hud.copy()  # cost, not fidelity: area at 1:1 is already the identity
    return _resize_area(hud, th, tw)


@dataclass
class GuardState:
    """Cross-cycle state the read path carries — the distance guard's anchor.

    Owned by the caller (the driver keeps one per drive) so `read_hud` itself stays a
    function of (frame, state) rather than hiding history in module scope.
    """

    last_valid_distance: Optional[int] = None
    last_valid_distance_ts: float = 0.0


@dataclass
class Reading:
    """Everything one HUD sample yields: decision values, raw values, diagnostics.

    `speed` / `distance` / `speed_limit` / `stopping_offset_cm` are POST-guard — what
    production decides on. The `raw_*` siblings are the pre-guard reader output, carried
    so a diagnostic can show what was rejected and why. Production ignores them.
    """

    badge: Optional[str] = None
    badge_diff: float = 0.0

    speed: Optional[int] = None
    speed_raw: str = ""
    speed_score: float = 0.0
    speed_tenths: Optional[int] = None
    speed_decimal: Optional[float] = None

    distance: Optional[int] = None
    distance_score: float = 0.0

    stopping_offset_cm: Optional[int] = None
    stopping_offset_score: float = 0.0

    speed_limit: Optional[int] = None
    speed_limit_score: float = 0.0

    # Pre-guard reader output (diagnostic only).
    raw_speed: Optional[int] = None
    raw_distance: Optional[int] = None
    raw_stopping_offset_cm: Optional[int] = None
    raw_speed_limit: Optional[int] = None

    # Which guard fired, if any.
    gated_fields: tuple = ()
    distance_rejected: bool = False

    ts: float = 0.0
    cells: dict = field(default_factory=dict)


def read_hud(
    frame_bgra: np.ndarray,
    profile,
    templates,
    red_templates,
    badge_anchors,
    seg,
    *,
    prev_badge: Optional[str],
    guard: GuardState,
    ts: float,
    crop,
    accept_stopping_offset,
    apply_badge_reject_gate,
    guard_distance,
) -> Reading:
    """Read + guard one frame. Mutates `guard` (re-anchors on an accepted distance).

    The four guard/crop callables are injected rather than imported to keep this module
    free of a cycle back into `driver` — `driver` owns them and passes them in. They are
    the SAME function objects in both callers, so behaviour cannot fork.
    """
    hud = profile.hud_bbox_in_capture
    d_cell = crop(frame_bgra, hud, profile.distance_value_bbox)
    s_cell = crop(frame_bgra, hud, profile.speed_value_bbox)
    sl_cell = crop(frame_bgra, hud, profile.speed_limit_value_bbox)
    b_cell = crop(frame_bgra, hud, profile.badge_bbox)

    badge, b_diff = classify_badge_state(b_cell, badge_anchors)
    s_val, s_raw, s_score = read_speed(s_cell, templates, seg=seg)
    # Decimal-precision speed for LOG/report only (never a driver decision — those key
    # off the integer). Read against s_raw so a dropped `.0` degrades to None (→ `.0`),
    # never a wrong integer. See read_speed_tenths.
    s_tenths = read_speed_tenths(s_cell, templates, seg=seg, int_raw=s_raw) if s_val is not None else None
    s_decimal = (s_val + s_tenths / 10) if (s_val is not None and s_tenths is not None) else (float(s_val) if s_val is not None else None)

    # The DISTANCE cell is shared and self-identifies via colour: dark `Nm` vs green
    # `±Ncm`. Run both readers unconditionally — masks are mutually exclusive.
    d_val, _, d_score = read_distance(d_cell, templates, seg=seg)
    offset_raw, _, offset_score = read_stopping_offset(d_cell, templates, seg=seg)
    offset_val = accept_stopping_offset(offset_raw, badge)
    sl_val, _, sl_score = read_speed_limit(sl_cell, templates, seg=seg, red_templates=red_templates)

    raw_speed, raw_distance, raw_limit = s_val, d_val, sl_val

    s_val, d_val, sl_val, gated_fields = apply_badge_reject_gate(badge, s_val, s_score, d_val, d_score, sl_val, sl_score)
    if "speed" in gated_fields:
        s_tenths = s_decimal = None

    dt_dist = (ts - guard.last_valid_distance_ts) if guard.last_valid_distance_ts else 0.0
    d_val, dist_rejected = guard_distance(prev_badge, badge, d_val, guard.last_valid_distance, dt_dist)
    if d_val is not None and not dist_rejected:
        guard.last_valid_distance = d_val
        guard.last_valid_distance_ts = ts

    return Reading(
        badge=badge,
        badge_diff=b_diff,
        speed=s_val,
        speed_raw=s_raw,
        speed_score=s_score,
        speed_tenths=s_tenths,
        speed_decimal=s_decimal,
        distance=d_val,
        distance_score=d_score,
        stopping_offset_cm=offset_val,
        stopping_offset_score=offset_score,
        speed_limit=sl_val,
        speed_limit_score=sl_score,
        raw_speed=raw_speed,
        raw_distance=raw_distance,
        raw_stopping_offset_cm=offset_raw,
        raw_speed_limit=raw_limit,
        gated_fields=gated_fields,
        distance_rejected=dist_rejected,
        ts=ts,
        cells={"distance": d_cell, "speed": s_cell, "speed_limit": sl_cell, "badge": b_cell},
    )

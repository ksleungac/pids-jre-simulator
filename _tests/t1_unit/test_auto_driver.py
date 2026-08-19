# SPDX-License-Identifier: MIT
# TIER: T1 — the auto-driver: from a HUD read to a PA firing
"""What auto-drive guarantees between reading the HUD and pressing a key.

Module scope is the FEATURE (`_tests/README.md` § "Module scope"). This is the
app's most consequential logic and its failures are uniformly silent — a wrong
decision produces no error, just an announcement that does not play or plays in
the wrong place. The five sections are the decision pipeline in order:

  1. IS THIS READ TRUSTWORTHY — the cross-attribute gates that drop phantoms
  2. WHAT STATE IS THE GAME IN — _Detector.inferred_state, the Layer-3 truth table
  3. WHAT DOES A SAMPLE STREAM MEAN — _Detector.update, the direct-read path
  4. DID WE JOIN MID-SEGMENT — re-entry: resolve a target, then commit it
  5. WHAT ACTUALLY HAPPENS — _fire_at_station

Vocabulary (Layer 1/2/3, the arrow notation, the badge transitions) is canonical
in `auto_input/README.md`; read it before reasoning about any of this.

Threshold literals are DELIBERATELY hardcoded here, never imported from `driver`.
Importing the constant under test makes the test agree with any mutation of it and
stop discriminating (`principles.md` § "Test real logic, not ceremony"). Widening a
band is a behaviour change and must break a line in this file.

Two cross-cutting invariants run through several sections and are asserted where
each one bites: **PASSING ≡ MOVING** (§2 grid, §3 cases D/G, §4 facet) — its
violation is the 2026-07-16 re-entry PA-drop class; and **badge > distance, speed**
— the badge is the gate in §1, never the thing being second-guessed.

Pure throughout: bare dataclasses, `object.__new__(AutoDriver)` to skip the camera
`__init__`, and `SimpleNamespace` sims. No pygame init, no camera, no I/O.

The reader that produces these inputs is T1 `test_ocr_read.py`.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

# _tests/ is dev harness (never shipped, exempt from the production path-resolver
# ban) — Path(__file__) here is fine. Put the repo root on sys.path for the import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from auto_input.driver import (  # noqa: E402
    BADGE_NONE_SCORE_GATE,
    AutoDriver,
    Layer3State,
    _accept_stopping_offset,
    _apply_badge_reject_gate,
    _Detector,
    badge_anchor_problems,
    guard_distance,
)
from auto_input.hud_layout import DOWNSCALE_PROFILE  # noqa: E402
from auto_input.ocr import BADGE_ANCHOR_FILES, DEFAULT_TEMPLATES_DIR, load_badge_anchors  # noqa: E402

FAILURES: list[str] = []


def check(cond, msg) -> None:
    if not cond:
        FAILURES.append("  " + msg)


# ══ 1. is this read trustworthy ═══════════════════════════════════════════════
# Three gates, one principle: the badge is the most reliable read on the HUD, so it
# is what the noisier reads are judged against — never the other way round.

# ── 1a. badge-reject score gate ───────────────────────────────────────────────
# When the badge fails to classify (`badge is None` — classifier diff > BADGE_DIFF_REJECT,
# a degraded frame: black-screen / mid-animation), the other digit reads are phantom-prone:
# sampling the drive logs, speed/distance land at score median ~0.60 (the docs' "<0.6
# random-match danger zone") vs ~0.90 when the badge reads. So when the most reliable HUD
# read fails ("badge > distance, speed"), any read below BADGE_NONE_SCORE_GATE is dropped.
# CONDITIONAL on badge=None, NOT a global floor — a real 0.6 read is kept whenever the
# badge confirms the frame. Offset is absent (already badge-gated to STOPPED).

T = BADGE_NONE_SCORE_GATE  # 0.80

# (badge, speed, s_score, dist, d_score, limit, sl_score) -> (speed, dist, limit, gated)
# fmt: off
BADGE_GATE_CASES = [
    # Badge readable → gate is a NO-OP; low scores pass through untouched (a real low read
    # is trusted when the badge confirms the frame).
    ("MOVING",  73, 0.55, 500, 0.55, 60, 0.55, (73, 500, 60, ())),
    ("STOPPED",  0, 0.60, 999, 0.60, 45, 0.60, (0, 999, 45, ())),
    # Badge=None + all reads below gate → all dropped, all named.
    (None,      73, 0.55, 500, 0.60, 60, 0.70, (None, None, None, ("speed", "distance", "speed_limit"))),
    # Badge=None + all reads above gate → all kept (a strong read on a degraded frame stays).
    (None,      73, 0.95, 500, 0.90, 60, 0.85, (73, 500, 60, ())),
    # Badge=None + mixed → only the sub-threshold reads drop.
    (None,      73, 0.55, 500, 0.95, 60, 0.70, (None, 500, None, ("speed", "speed_limit"))),
    # Badge=None + a field already None → not "gated" (nothing to drop); others still gate.
    (None,    None, 1.00, 500, 0.50, None, 1.00, (None, None, None, ("distance",))),
    # Boundary: score exactly at the gate is KEPT (strict <).
    (None,      73, T,    500, T,    60, T,    (73, 500, 60, ())),
    # Just below the boundary → dropped.
    (None,      73, T - 0.001, 500, T - 0.001, 60, T - 0.001,
                                                (None, None, None, ("speed", "distance", "speed_limit"))),
]
# fmt: on

# ── 1b. stopping-offset badge gate ────────────────────────────────────────────
# The game shows the ±cm offset only after MOVING→STOPPED (STOPPED badge up). The green
# read is phantom-prone — scenery-green bleed through the semi-transparent HUD can
# fabricate a ±cm value mid-transit — so it is trusted only when the badge groundtruth
# says STOPPED. The badge is the most reliable read on the HUD (canonical, clean
# pixel-diff separation), strictly more reliable than the speed/distance digit reads, so
# it is the SOLE gate — deliberately NOT speed-gated, because folding the noisier speed
# read into a badge that is already groundtruth would only add false-rejects. Same
# badge-only rule as FIRE_AT_STATION: badge read > (distance, speed).

# (offset_cm, badge, expected)
# fmt: off
OFFSET_CASES = [
    # Real offset with the STOPPED badge up — accepted, sign + zero preserved.
    (40,   "STOPPED", 40),
    (-11,  "STOPPED", -11),
    (0,    "STOPPED", 0),      # stopped exactly on the mark
    # Green read while the badge says moving/passing — phantom scenery bleed, rejected.
    (40,   "MOVING",  None),
    (40,   "PASSING", None),
    (-11,  "MOVING",  None),
    # Badge unreadable (OCR dropout) — cannot confirm stopped, so reject.
    (40,   None,      None),
    # No green read at all — None regardless of badge.
    (None, "STOPPED", None),
    (None, "MOVING",  None),
    (None, None,      None),
]
# fmt: on

# ── 1c. distance plausibility guard ───────────────────────────────────────────
# A degraded 1080p frame mis-segments distance into a single-frame spike (1372→3→1257),
# correlated with the speed decimal-slip; the badge-reject gate misses these (badge still
# reads MOVING). But distance obeys physics: between samples the train moves ≤ v·Δt.
# Reject a read that moves further from the last VALID distance than
# MAX_DRIVABLE_SPEED_KMH·Δt (+ slack) and hold-last-good.
#
# Re-anchor only on a **re-point** — the HUD switching its distance to a NEW target. Two
# conditions, both required: the pair is in DISTANCE_RETARGET_PAIRS (STOPPED→STOPPED dwell
# refresh, PASSING→PASSING next passed station, PASSING→MOVING to the stopping station) AND
# the jump is UPWARD, since a re-point always goes from something just reached (≈0) to
# something farther. No consensus latch; a double spike is rejected on both frames and
# self-heals as Δt grows.
# Design consult: third-man 2026-07-21; re-point pairs + direction condition 2026-08-11.

DT = 3.0  # representative OCR interval (measured ~3s in drive logs)
# The allowance the rows below are built around:
#   (MAX_DRIVABLE_SPEED_KMH / 3.6) * DT + DISTANCE_GUARD_SLACK_M  ~= 162.5 m at dt=3
# Stated, not bound to a name — a test that computes its own expectation from the
# constants under test agrees with any mutation of them.

# (prev_badge, badge, distance, last_valid, dt) -> (value, rejected)
# fmt: off
DISTANCE_CASES = [
    # Boot: no anchor yet → accept the first read.
    ("MOVING",  "MOVING", 1695, None, DT, (1695, False)),
    # OCR dropout (None) → pass through, not a "reject".
    ("MOVING",  "MOVING", None, 1695, DT, (None, False)),
    # Plausible approach step (well within v·Δt) → accepted.
    ("MOVING",  "MOVING", 1600, 1695, DT, (1600, False)),
    # Spike DOWN (1372→3) while steady MOVING → implausible, hold last valid.
    ("MOVING",  "MOVING",    3, 1372, DT, (1372, True)),
    # Spike UP (152→2242) → implausible, hold last valid.
    ("MOVING",  "MOVING", 2242,  152, DT, (152,  True)),
    # NOT a re-point — departure. The dwell refresh is guaranteed to complete while the badge
    # still reads STOPPED (author-stated 2026-08-11), so by the departure edge the anchor is
    # already the next station's distance and the departure's own motion is ~3.75m against a
    # ~162m allowance. Was (1800, False) until 2026-08-11: that fixture encoded the design's
    # assumption ("accepted unconditionally"), not an observed drive.
    ("STOPPED", "MOVING", 1800,    3, DT, (3,    True)),
    # Same for a departure toward a passed-through station.
    ("STOPPED", "PASSING", 1800,   3, DT, (3,    True)),
    # Re-point — PASSING→MOVING up-jump (prior PASSING): accepted.
    ("PASSING", "MOVING", 1800,   50, DT, (1800, False)),
    # Re-point — dwell refresh, both frames STOPPED: accepted.
    ("STOPPED", "STOPPED", 1400,   3, DT, (1400, False)),
    # Re-point — consecutive passed-through stations, both frames PASSING: accepted.
    ("PASSING", "PASSING",  900, 645, DT, (900,  False)),
    # DOWNWARD jump on a reference-in-flux pair is NOT a re-point — a re-point always goes from
    # something just reached (≈0) to something farther. This is the frame after a one-frame
    # PASSING misread: it presents as PASSING→MOVING, identical by badge to a genuine one, and
    # only the direction separates them. Was accepted pre-2026-08-11 → まもなく ~400m early.
    ("PASSING", "MOVING",     5, 1330, DT, (1330, True)),
    ("PASSING", "PASSING",    5, 1330, DT, (1330, True)),
    ("STOPPED", "STOPPED",    5, 1330, DT, (1330, True)),
    # MOVING→PASSING is physically impossible (auto_input/README.md § "Only four badge
    # transitions are physically possible"), so there is no re-point for an exemption to absorb
    # → ordinary gated path. NOT a claim that the badge is unreliable; the badge outranks the
    # distance read. Was (500, False) pre-2026-08-11, which is the model that change corrected.
    ("MOVING",  "PASSING", 500, 1695, DT, (1695, True)),
    # ...and UPWARD too. This is the case that isolates the removal: a downward MOVING→PASSING is
    # gated by the direction condition whether or not PASSING is treated as reference-in-flux, so
    # only an upward one discriminates. Mutation-proven 2026-08-11 (restoring the old
    # `badge in ("STOPPED","PASSING")` must fail HERE).
    ("MOVING",  "PASSING", 1800,  50, DT, (50,   True)),
    # badge=None degraded frame while prior was MOVING → STILL gated (a spike can't poison the anchor).
    ("MOVING",  None,        3, 1372, DT, (1372, True)),
    # MOVING→STOPPED is deliberately NOT a re-point pair. The dwell refresh fires only after the
    # badge reads STOPPED, so physically it lands on STOPPED→STOPPED; a coarse SAMPLE_INTERVAL_S
    # can make it first OBSERVED here, and that timing artifact is explicitly not designed around
    # (author-stated 2026-08-11 — the lever is the interval, not the guard). Pinned so the pair
    # is not quietly added back.
    ("MOVING",  "STOPPED", 1400,  40, DT, (40,   True)),
    # prev_badge=None (set by _reanchor_to_app on a click-jump, and on the frame after a boot whose
    # first badge read failed) with an anchor already held → gated, NOT exempt. The game's distance
    # is continuous across a click-jump — only the APP moved — so there is no re-point to absorb.
    (None,      "MOVING",    3, 1372, DT, (1372, True)),
    # Boundary: a change within the bound (Δ=162 ≤ ~162.5) is KEPT.
    ("MOVING",  "MOVING", 1533, 1695, DT, (1533, False)),
    # Just past the bound (Δ=170) → rejected, hold.
    ("MOVING",  "MOVING", 1525, 1695, DT, (1695, True)),
    # Long dropout: a big legit change passes because Δt scales the bound.
    ("MOVING",  "MOVING", 1000, 1695, 20.0, (1000, False)),
]
# fmt: on


def check_read_gates() -> None:
    for badge, sp, ss, ds, dss, lim, ls, expected in BADGE_GATE_CASES:
        got = _apply_badge_reject_gate(badge, sp, ss, ds, dss, lim, ls)
        check(got == expected, f"badge-gate badge={badge} sp={sp}/{ss} ds={ds}/{dss} lim={lim}/{ls}: expected {expected}, got {got}")

    for offset_cm, badge, expected in OFFSET_CASES:
        got = _accept_stopping_offset(offset_cm, badge)
        check(got == expected, f"_accept_stopping_offset({offset_cm!r}, {badge!r}) = {got!r}, expected {expected!r}")

    for prev_badge, badge, dist, last_valid, dt, expected in DISTANCE_CASES:
        got = guard_distance(prev_badge, badge, dist, last_valid, dt)
        check(got == expected, f"guard_distance({prev_badge!r}, {badge!r}, {dist}, {last_valid}, {dt}): expected {expected}, got {got}")

    # Double spike: both frames rejected + held (no consensus accept); self-heals only when a
    # plausible read near the anchor returns.
    v1, r1 = guard_distance("MOVING", "MOVING", 3, 1372, DT)  # spike 1 → hold
    v2, r2 = guard_distance("MOVING", "MOVING", 5, v1, 2 * DT)  # spike 2 vs the held anchor → still rejected
    check(r1 and r2 and v1 == 1372 and v2 == 1372, f"double-spike: expected both rejected holding 1372, got ({v1},{r1}) ({v2},{r2})")


# ══ 2. what state is the game in ══════════════════════════════════════════════
# The canonical Layer-3 inference (`_Detector.inferred_state`).
#
# Every cell of the (prev_badge x arrival_observed x departure_observed) grid is
# asserted against the truth table in auto_input/README.md § "Layer 3 — AutoDriver's
# inferred game state". The expected values are hand-derived FROM THE README table
# (the spec), not read back from the code — so a future edit to inferred_state() that
# disagrees with the documented table fails here.
#
# The MOVING and PASSING rows are IDENTICAL by design: PASSING is a transient
# sub-state of MOVING and never changes the inferred game state (the canonical
# `PASSING ≡ MOVING` invariant). That equality is asserted separately at the end —
# re-introducing a PASSING special-case (the class of the 2026-07-16 re-entry PA-drop
# incident) flips a MOVING/PASSING cell and trips it.

L = Layer3State

# Spec table — hand-derived from README § "Layer 3" truth table (NOT from the code).
#   (prev_badge, arrival_observed, departure_observed) -> expected Layer 3 state
# fmt: off
INFER_CASES = [
    (None,      False, False, L.UNKNOWN),
    (None,      False, True,  L.UNKNOWN),
    (None,      True,  False, L.UNKNOWN),
    (None,      True,  True,  L.UNKNOWN),
    ("STOPPED", False, False, L.IDLE),
    ("STOPPED", False, True,  L.IDLE),      # departure flag irrelevant while STOPPED
    ("STOPPED", True,  False, L.STOPPED),
    ("STOPPED", True,  True,  L.STOPPED),
    ("MOVING",  False, False, L.DEPARTING),
    ("MOVING",  False, True,  L.CRUISING),
    ("MOVING",  True,  False, L.ARRIVING),  # arrival wins over departure flag
    ("MOVING",  True,  True,  L.ARRIVING),
    ("PASSING", False, False, L.DEPARTING),
    ("PASSING", False, True,  L.CRUISING),
    ("PASSING", True,  False, L.ARRIVING),
    ("PASSING", True,  True,  L.ARRIVING),
]
# fmt: on


def _infer(badge, arr, dep):
    d = _Detector()
    d.prev_badge = badge
    d.arrival_observed = arr
    d.departure_observed = dep
    return d.inferred_state()


def check_inferred_state() -> None:
    for badge, arr, dep, expected in INFER_CASES:
        got = _infer(badge, arr, dep)
        check(got == expected, f"inferred_state(badge={badge!r}, arr={arr}, dep={dep}) = {got!r}, expected {expected!r}")

    # Invariant: PASSING is identical to MOVING on the inferred state for every
    # (arr, dep). Its violation is the 2026-07-16 re-entry PA-drop bug class.
    for arr in (False, True):
        for dep in (False, True):
            mv = _infer("MOVING", arr, dep)
            pv = _infer("PASSING", arr, dep)
            check(mv == pv, f"PASSING != MOVING at arr={arr}, dep={dep}: MOVING={mv!r} PASSING={pv!r}")


# ══ 3. what a sample stream means ═════════════════════════════════════════════
# `_Detector.update()` — the DIRECT-READ path: raw (distance, speed, badge)
# samples in → PA-fire event names + observed-flags out.
#
# This is the part that actually *reads the sensors and decides* (threshold crossings),
# as opposed to `inferred_state()`, which only formats the flags this method sets. The
# 2026-07-16 re-entry bug was NOT in here (the detector handles PASSING correctly — see
# cases D and G), but this is where the same class of bug *could* live, so the raw→decision
# behaviors are pinned.
#
# Stateful: one `_Detector`, exercised over a call sequence.


def run(samples, **detector_kw):
    """Feed (distance, speed, badge) samples through a fresh detector; collect events."""
    d = _Detector(**detector_kw)
    events = []
    for dist, speed, badge in samples:
        events.extend(d.update(dist, speed, badge))
    return d, events


def check_detector_stream() -> None:
    # A. Departure fires once when own-speed enters the audible band on a fresh segment.
    d, ev = run([(2000, 0, "STOPPED"), (2000, 5, "MOVING"), (2000, 35, "MOVING")])
    check(ev.count("FIRE_DEPARTURE") == 1, f"A departure: expected 1 FIRE_DEPARTURE, got {ev.count('FIRE_DEPARTURE')} ({ev})")
    check(d.departure_observed is True, "A departure: departure_observed should be True")

    # B. No re-fire when speed dips below 30 and re-crosses (the flag debounces —
    #    "current speed lies" case: a cruising train slowing mid-segment isn't departing).
    d, ev = run([(2000, 0, "STOPPED"), (2000, 5, "MOVING"), (2000, 35, "MOVING"), (2000, 25, "MOVING"), (2000, 40, "MOVING")])
    check(ev.count("FIRE_DEPARTURE") == 1, f"B debounce: expected exactly 1 FIRE_DEPARTURE across dip+recross, got {ev.count('FIRE_DEPARTURE')}")

    # C. Arrival fires once on MOVING with distance <= lead (level test).
    d, ev = run([(2000, 0, "STOPPED"), (2000, 35, "MOVING"), (800, 40, "MOVING")])
    check(ev.count("FIRE_ARRIVAL") == 1, f"C arrival: expected 1 FIRE_ARRIVAL, got {ev.count('FIRE_ARRIVAL')} ({ev})")

    # D. [PASSING facet] PASSING does NOT arrive even at distance <= lead — its
    #    distance is to the passing station, not the stopping target.
    d, ev = run([(2000, 0, "STOPPED"), (2000, 35, "MOVING"), (300, 40, "PASSING")])
    check("FIRE_ARRIVAL" not in ev, f"D passing-skip-arrival: PASSING@dist=300 must NOT fire arrival ({ev})")
    check(d.arrival_observed is False, "D passing-skip-arrival: arrival_observed should stay False")

    # E. STOPPED -> MOVING starts a new segment: resets all three observed-flags.
    d, ev = run([(2000, 5, "MOVING")], prev_badge="STOPPED", departure_observed=True, arrival_observed=True, at_station_observed=True)
    check("STOPPED->MOVING" in ev, f"E reset: expected STOPPED->MOVING event ({ev})")
    check(not d.departure_observed and not d.arrival_observed and not d.at_station_observed, "E reset: all three flags should reset to False")

    # F. Black-screen cross-reject: prev=STOPPED, moving-ish badge at speed 0 is
    #    rejected (the game can't move without rendering speed climbing from 0).
    d, ev = run([(None, 0, "PASSING")], prev_badge="STOPPED")
    check("CROSS_REJECT" in ev, f"F cross-reject: expected CROSS_REJECT ({ev})")
    check("STOPPED->MOVING" not in ev, "F cross-reject: must NOT begin a segment")
    check(d.prev_badge == "STOPPED", "F cross-reject: prev_badge should stay STOPPED (read rejected)")

    # G. [PASSING facet] Departure fires through a PASSING-badged rollout — PASSING is
    #    a moving segment, departure is speed-based and badge-independent. This is the
    #    detector's slice of the incident path, and it handles it correctly; the bug
    #    lived in the re-entry resolver (§4), not here.
    d, ev = run([(2000, 0, "STOPPED"), (2000, 5, "PASSING"), (2000, 20, "PASSING"), (2000, 35, "MOVING")])
    check(
        ev.count("FIRE_DEPARTURE") == 1,
        f"G passing-departure: expected 1 FIRE_DEPARTURE through PASSING rollout, got {ev.count('FIRE_DEPARTURE')} ({ev})",
    )

    # ── Departure-as-level-test (#82). H and I are the two ways the old crossing
    #    (prev_speed < 30 <= speed) lost a departure PERMANENTLY for the segment; both
    #    fire under the level test. J pins the ceiling. Each discriminates: H/I fail if
    #    the crossing is restored, J fails if the upper bound is dropped.

    # H. Stale-high prev_speed. prev_speed only updates on a non-None read, so dropped
    #    reads through deceleration + dwell carry the pre-station cruise value into the
    #    next departure. The crossing can never satisfy prev_speed < 30 again.
    d, ev = run([(2000, 45, "MOVING")], prev_badge="STOPPED", prev_speed=78)
    check(ev.count("FIRE_DEPARTURE") == 1, f"H stale-prev-speed: departure must fire with prev_speed=78 stale, got {ev}")

    # I. Absent prev_speed — thread start, or post-click-jump (_reanchor_to_app nulls it).
    d, ev = run([(2000, 35, "MOVING")], prev_badge="STOPPED", prev_speed=None)
    check(ev.count("FIRE_DEPARTURE") == 1, f"I absent-prev-speed: departure must fire with prev_speed=None, got {ev}")

    # J. Ceiling (UNKNOWN origin): at or above the stale bound the PA is unrecoverable
    #    and re-entry's SILENT 1A advance owns it — the level test must NOT fire. Cold
    #    boot mid-cruise: fresh detector, prev_badge=None, no witnessed edge.
    d, ev = run([(2000, 86, "MOVING")])
    check("FIRE_DEPARTURE" not in ev, f"J stale-ceiling: speed 86 unknown-origin is re-entry territory, must not fire departure ({ev})")
    check(d.departure_observed is False, "J stale-ceiling: departure_observed should stay False")

    # K. Band edges are [30, 60). Literals DELIBERATELY hardcoded, not imported from
    #    driver — importing the constants under test would make this pass for any band
    #    (see principles.md § "Test real logic, not ceremony"). Widening the band is a
    #    behaviour change and must break this line.
    d, ev = run([(2000, 30, "MOVING")])
    check("FIRE_DEPARTURE" in ev, f"K lower-edge: speed == 30 must fire ({ev})")
    d, ev = run([(2000, 59, "MOVING")])
    check("FIRE_DEPARTURE" in ev, f"K in-band-top: speed == 59 must fire ({ev})")
    d, ev = run([(2000, 60, "MOVING")])
    check("FIRE_DEPARTURE" not in ev, f"K upper-edge: speed == 60 must NOT fire ({ev})")

    # L. Reachability rule: at-station fires on a STOPPED badge WITHOUT arrival_observed —
    #    a dropout that ate the arrival must not strand the app in transit (the app-parked
    #    skip in _fire_at_station handles boot; the fire-side drain normalizes cnt_pa).
    #    Discriminates: restoring the old `and self.arrival_observed` gate fails this.
    d, ev = run([(2000, 40, "MOVING"), (5, 0, "STOPPED")])
    check(d.arrival_observed is False, f"L reachability: precondition — arrival must NOT have been observed ({ev})")
    check("FIRE_AT_STATION" in ev, f"L reachability: STOPPED badge must fire at-station even with arrival missed ({ev})")
    #    Debounce: a repeated STOPPED level read must not refire (at_station_observed).
    d, ev = run([(2000, 40, "MOVING"), (5, 0, "STOPPED"), (5, 0, "STOPPED")])
    check(
        ev.count("FIRE_AT_STATION") == 1, f"L debounce: expected exactly 1 FIRE_AT_STATION across repeated STOPPED, got {ev.count('FIRE_AT_STATION')}"
    )

    # M. Post-click-jump segment arrives (the 2026-07-24 01:21 incident): _reanchor_to_app
    #    sets prev_badge=None, so NO STOPPED->MOVING edge ever fires post-jump and nothing
    #    resets the observed-flags — the reanchor itself must leave at_station_observed
    #    False or the arrival STOPPED read is suppressed and the app strands at 1A.
    #    Discriminates: reanchor setting at_station_observed=True fails this.
    ad = object.__new__(AutoDriver)
    ad._detector = _Detector()
    ad.sim = SimpleNamespace(state=SimpleNamespace(curr_stop=12))
    ad._reanchor_to_app()
    ev = []
    for sample in [(319, 61, "MOVING"), (100, 40, "MOVING"), (2, 0, "MOVING"), (None, 0, "STOPPED")]:
        ev.extend(ad._detector.update(*sample))
    check("FIRE_AT_STATION" in ev, f"M post-jump arrival: STOPPED after a post-reanchor transit must fire at-station ({ev})")

    # N. Witnessed-edge NO ceiling (the 2026-07-24 01:36 incident): a platform dwell whose
    #    acceleration lands entirely in an OCR dropout — badge/speed = None through the whole
    #    [30,60) band, first valid read already >=60. The STOPPED->MOVING edge is witnessed
    #    (prev_badge=STOPPED survives the None run, speed>0 passes cross-reject), so the
    #    departure is FRESH and must fire despite speed>=60 — re-entry is disarmed here, so
    #    nothing else catches it. Discriminates: reverting the ceiling relaxation fails this.
    d, ev = run(
        [(752, 0, "STOPPED"), (None, None, None), (None, None, None), (552, 65, "MOVING")],
    )
    check("STOPPED->MOVING" in ev, f"N witnessed-edge: edge must fire through the None run ({ev})")
    check("FIRE_DEPARTURE" in ev, f"N witnessed-edge: fresh departure must fire at speed 65 (no ceiling on a witnessed edge) ({ev})")
    #    Same speed, UNKNOWN origin (no preceding STOPPED) still declines — the relaxation is
    #    provenance-gated, NOT a blanket removal of the ceiling.
    d, ev = run([(552, 65, "MOVING")])
    check("FIRE_DEPARTURE" not in ev, f"N unknown-origin control: speed 65 with no witnessed edge must NOT fire ({ev})")


# ══ 4. did we join mid-segment ════════════════════════════════════════════════
# Re-entry, in two halves: resolve a target, then commit it.

# ── 4a. the resolver ──────────────────────────────────────────────────────────
# `AutoDriver._resolve_reentry_target()` — THE 2026-07-16 bug site.
#
# The resolver is a pure read of (prev_badge, speed, distance) + the app-parked guards,
# returning the re-entry target "1A" / "1B" / None. The bug was an `or badge=="PASSING"`
# clause that forced "1A" (departed) for a PASSING badge at ANY speed — so departing a
# station whose next station is a pass-through silent-advanced and ATE the departure PA.
#
# The `resolve(PASSING,s,d) == resolve(MOVING,s,None)` block is this site's facet of the
# cross-cutting `PASSING ≡ MOVING` invariant: PASSING behaves like a MOVING whose distance
# is unusable.

LEAD = 900


def resolve(
    prev_badge, speed, distance, *, pending_next_pa=False, at_station=True, arr_obs=False, dep_obs=False, lead=LEAD, origin_known=False, next_pa=2
):
    det = _Detector(
        arrival_lead_m=lead, prev_badge=prev_badge, arrival_observed=arr_obs, departure_observed=dep_obs, motion_origin_known=origin_known
    )
    # Parked at stop 0; the joined segment lands on stop 1 with `next_pa` approach
    # PAs (default 2 — a real 1B exists; pa=1 collapses 1A ≡ 1B, see facet below).
    stops = [{"pa": ["p"]}, {"pa": ["p"] * next_pa}]
    sim = SimpleNamespace(pending_next_pa=pending_next_pa, state=SimpleNamespace(at_station=at_station, curr_stop=0), stops=stops)
    fake_self = SimpleNamespace(sim=sim, _detector=det, _next_stopping_pa_count=lambda: AutoDriver._next_stopping_pa_count(fake_self))
    return AutoDriver._resolve_reentry_target(fake_self, speed, distance)


# Spec grid — reachable domain is badge in {MOVING, PASSING} (STOPPED/None are filtered
# upstream by the inferred_state guard). Guards satisfied (parked, no live fire).
#   speed: None / 10 (below band) / 40 (IN the audible band) / 80 (stale)
#   dist:  None / >lead / <=lead
# Expected derived from the invariant: arrival(1B) = MOVING AND dist<=lead (checked first);
# departure(1A) = speed >= 60 ONLY, badge-independent; else None.
#
# The 40 rows are #82's partition: [30, 60) belongs to the AUDIBLE level test in
# _Detector.update, so this silent fallback must decline it. Before #82 both keyed on 30
# and this resolver returned "1A" there — inheriting every departure the crossing dropped.
# 60 is hardcoded, not imported, so widening the band breaks these rows.
# fmt: off
GRID = [
    # badge,     speed, dist,  expected
    ("MOVING",   None,  None,  None),
    ("MOVING",   None,  2000,  None),
    ("MOVING",   None,  300,   "1B"),
    ("MOVING",   10,    None,  None),
    ("MOVING",   10,    2000,  None),
    ("MOVING",   10,    300,   "1B"),
    ("MOVING",   40,    None,  None),   # in-band: audible primary owns it
    ("MOVING",   40,    2000,  None),   # in-band: audible primary owns it
    ("MOVING",   40,    300,   "1B"),   # arrival checked BEFORE speed
    ("MOVING",   80,    None,  "1A"),
    ("MOVING",   80,    2000,  "1A"),
    ("MOVING",   80,    300,   "1B"),   # arrival checked BEFORE speed
    ("PASSING",  None,  None,  None),
    ("PASSING",  None,  2000,  None),
    ("PASSING",  None,  300,   None),   # PASSING never arrives (distance unusable)
    ("PASSING",  10,    None,  None),
    ("PASSING",  10,    2000,  None),
    ("PASSING",  10,    300,   None),   # <-- 2026-07-16 INCIDENT: was "1A" on the buggy clause
    ("PASSING",  40,    None,  None),
    ("PASSING",  40,    2000,  None),
    ("PASSING",  40,    300,   None),
    ("PASSING",  80,    None,  "1A"),
    ("PASSING",  80,    2000,  "1A"),
    ("PASSING",  80,    300,   "1A"),   # PASSING never returns 1B
]
# fmt: on


def check_reentry_resolver() -> None:
    for badge, speed, dist, expected in GRID:
        got = resolve(badge, speed, dist)
        check(got == expected, f"resolve(badge={badge!r}, speed={speed}, dist={dist}) = {got!r}, expected {expected!r}")

    # [PASSING facet] departure axis is badge-independent: PASSING resolves like a
    # MOVING whose distance is unusable, and PASSING never resolves to the arrival target.
    for speed in (None, 10, 40, 80):
        for dist in (None, 2000, 300):
            pv = resolve("PASSING", speed, dist)
            mv_nodist = resolve("MOVING", speed, None)
            check(pv == mv_nodist, f"PASSING != MOVING-no-dist at speed={speed}, dist={dist}: PASSING={pv!r} MOVING(None)={mv_nodist!r}")
            check(pv != "1B", f"PASSING resolved to 1B at speed={speed}, dist={dist} — arrival is MOVING-only")

    # Regression anchor — the 2026-07-16 incident: parked, next station passes, low speed.
    check(
        resolve("PASSING", 10, 300) is None,
        "REGRESSION: resolve(PASSING, speed=10, dist=300) must be None (was '1A' — ate the departure PA)",
    )

    # Regression anchor — #82 strictness inversion. This silent fallback must never be
    # satisfiable where the audible primary is: [30, 60) is the primary's band, so a
    # freshly-departed train at 45 km/h resolves to no target no matter the badge.
    for badge in ("MOVING", "PASSING"):
        check(
            resolve(badge, 45, 2000) is None,
            f"REGRESSION: resolve({badge}, speed=45, dist=2000) must be None — [30,60) is the AUDIBLE primary's band",
        )

    # Guard branches — resolver stands down regardless of badge.
    check(resolve("PASSING", 80, 2000, pending_next_pa=True) is None, "guard: pending_next_pa=True must return None (a live fire owns this cycle)")
    check(resolve("MOVING", 80, 2000, at_station=False) is None, "guard: at_station=False (app already moving) must return None")

    # [Provenance facet] BASE ARMING CONDITION: motion of KNOWN origin (a witnessed
    # STOPPED→(MOVING|PASSING) edge) never resolves to ANY target — the audible
    # primary owns the whole segment. Every grid cell goes None, whatever the reads.
    for badge, speed, dist, _expected in GRID:
        got = resolve(badge, speed, dist, origin_known=True)
        check(
            got is None,
            f"PROVENANCE: resolve({badge!r}, speed={speed}, dist={dist}, origin_known=True) = {got!r}, expected None — witnessed motion never re-enters",
        )

    # [pa=1 facet] A pa=1 landing stop has NO distinct 1B (cnt_pa = len(pa)-1 = 0 makes
    # 1A ≡ 1B one AppState, and the single announcement must never be silently skipped):
    # every 1B grid cell declines; the 1A (speed>=60) cells are unaffected. STOPPING on
    # pa=1 is reached by the at-station transition edge itself, not a re-entry landing.
    for badge, speed, dist, expected in GRID:
        got = resolve(badge, speed, dist, next_pa=1)
        if expected == "1B":
            # 1B declines and falls THROUGH to the 1A speed test — "PA=1 case
            # only re-entry to 1a" (60 hardcoded, not imported — see K-note).
            want = "1A" if (speed is not None and speed >= 60) else None
        else:
            want = expected
        check(got == want, f"PA1: resolve({badge!r}, speed={speed}, dist={dist}, next_pa=1) = {got!r}, expected {want!r} — pa=1 has no 1B target")
    # Fall-through: pa=1, inside the lead, speed already stale-high → 1A (not None) —
    # "PA=1 case only re-entry to 1a".
    check(resolve("MOVING", 80, 300, next_pa=1) == "1A", "PA1: resolve(MOVING, speed=80, dist=300, next_pa=1) must fall through to '1A'")

    # Regression anchor — the 2026-07-23 Nambu incident: normal departure from 武蔵溝ノ口,
    # segment 703m < 900m lead, first moving frames at speed 1-3. The witnessed edge
    # must disarm re-entry entirely (the departure PA plays via the audible primary).
    check(
        resolve("MOVING", 1, 703, origin_known=True) is None,
        "REGRESSION: resolve(MOVING, speed=1, dist=703, origin_known=True) must be None (2026-07-23: ate the departure PA on a short segment)",
    )
    # Discrimination check for the anchor above: the SAME reads with UNKNOWN origin
    # (mid-transit join inside the lead) still resolve 1B — proves the provenance
    # gate, not some other condition, is what suppresses the incident.
    check(
        resolve("MOVING", 1, 703, origin_known=False) == "1B",
        "DISCRIMINATION: resolve(MOVING, speed=1, dist=703, origin_known=False) must be '1B' (unknown-origin join inside the lead is re-entry's legitimate case)",
    )


# ── 4b. the commit ────────────────────────────────────────────────────────────
# What a consensus-confirmed target actually does to the sim. The 2026-07-24 rule:
#
#   - landing stop pa>=2 → SILENT advance (announcement stale mid-segment)
#   - landing stop pa=1  → AUDIBLE catch-up ("pa=1 always play it" — the single
#     announcement is never stale), via the same press as a departure fire.


def make_driver(next_pa):
    ad = object.__new__(AutoDriver)
    ad._detector = _Detector(prev_badge="MOVING")
    ad.sim = SimpleNamespace(
        pending_next_pa=False,
        pending_silent_advance=None,
        state=SimpleNamespace(at_station=True, curr_stop=0, cnt_pa_at_station=-1),
        stops=[{"pa": ["p"], "pa_at_station": []}, {"pa": ["p"] * next_pa}],
    )
    return ad


def commit_1a(next_pa):
    """Two consecutive CRUISING probes (speed 80, dist beyond lead) → commit 1A."""
    ad = make_driver(next_pa)
    first = ad._maybe_reentry(80, 2000)
    second = ad._maybe_reentry(80, 2000)
    return ad, first, second


def check_reentry_commit() -> None:
    # pa>=2 → silent advance signal, no audible press.
    ad, first, second = commit_1a(next_pa=2)
    check(first is None and second == "1A", f"pa=2: expected commit on 2nd probe, got ({first}, {second})")
    check(ad.sim.pending_silent_advance == "1A", f"pa=2: expected silent advance '1A', got {ad.sim.pending_silent_advance!r}")
    check(ad.sim.pending_next_pa is False, "pa=2: silent commit must NOT press (no audio)")

    # pa=1 → AUDIBLE press (pending_next_pa, the departure-fire path), no silent signal.
    # Discriminates: reverting to the silent advance fails both checks below.
    ad, first, second = commit_1a(next_pa=1)
    check(first is None and second == "1A", f"pa=1: expected commit on 2nd probe, got ({first}, {second})")
    check(ad.sim.pending_next_pa is True, "pa=1: commit must press AUDIBLY (pa=1 announcement never stale)")
    check(ad.sim.pending_silent_advance is None, "pa=1: no silent-advance signal on the audible path")


# ══ 5. what actually happens ══════════════════════════════════════════════════
# `_fire_at_station`'s reachability contract: a STOPPED badge while the app is in
# transit (1A/1B) must ALWAYS land the STOPPING transition.
#
# The 2026-07-24 rule replaced the old cnt_pa REFUSAL ("arrival likely missed" →
# skip → app stuck at 1A until click-jump) with a silent approach-PA drain: cnt_pa
# is normalized to the last approach entry so the synthesized press enters STOPPING
# instead of playing a leftover approach PA.


def fire(*, at_station=False, curr_stop=0, cnt_pa=0, pa=("a", "b")):
    """Run one _fire_at_station against a stubbed sim; return the sim state."""
    sim = SimpleNamespace(
        pending_next_pa=False,
        state=SimpleNamespace(at_station=at_station, curr_stop=curr_stop, cnt_pa=cnt_pa, is_last_pa=False),
        stops=[{"name": "X", "pa": list(pa)}],
    )
    fake_self = SimpleNamespace(sim=sim, _last_fire=None)
    AutoDriver._fire_at_station(fake_self)
    return sim


def check_fire_at_station() -> None:
    # 1. REACHABILITY (the rule): arrival missed — pa=2 but cnt_pa still 0 (app at 1A).
    #    Must drain to the last approach entry and land the press. Discriminates:
    #    restoring the old refusal leaves pending_next_pa False.
    sim = fire(cnt_pa=0, pa=("approach0", "approach1"))
    check(sim.pending_next_pa is True, "reachability: press must land despite missed arrival (was: refusal → stuck at 1A)")
    check(sim.state.cnt_pa == 1, f"reachability: cnt_pa must drain to last approach entry, got {sim.state.cnt_pa}")
    check(sim.state.is_last_pa is True, "reachability: drain must keep the is_last_pa ≡ cnt_pa>=len-1 invariant")

    # 2. Normal 1B: cnt_pa already at the last approach PA — press lands, no drain.
    sim = fire(cnt_pa=1, pa=("approach0", "approach1"))
    check(sim.pending_next_pa is True, "normal 1B: press must land")
    check(sim.state.cnt_pa == 1, "normal 1B: cnt_pa untouched")

    # 3. pa=1 stop (1A≡1B collapse): cnt_pa=0 == len(pa)-1 — press lands, no drain.
    sim = fire(cnt_pa=0, pa=("only",))
    check(sim.pending_next_pa is True, "pa=1: press must land")
    check(sim.state.cnt_pa == 0, "pa=1: cnt_pa untouched")

    # 4. App parked (1C / boot at start station): skip — the app-parked guard is what
    #    lets the detector emit FIRE_AT_STATION unconditionally on STOPPED.
    sim = fire(at_station=True, cnt_pa=0)
    check(sim.pending_next_pa is False, "parked: fire must skip (already STOPPING)")


def check_badge_anchor_set() -> None:
    """The shipped anchor set must be complete and at the model's scale.

    Behind `badge_anchor_problems` sit three silent-skip layers, so a partial or
    wrong-scale set starts the driver, reads no badge for the whole drive and fires
    nothing, printing no error. Measured 2026-08-19: three of the six stems could be
    deleted with the entire suite still green — the badge assertions elsewhere are
    self-comparisons (the cell fixtures ARE the anchors, diff 0.00), so only this
    checks the set itself. Shapes are pinned literally, never imported.
    """
    import numpy as np

    MODEL_H, MODEL_W = 30, 83  # the model badge cell; a literal, so it discriminates

    badges = DEFAULT_TEMPLATES_DIR / "badges"
    anchors = load_badge_anchors(badges)

    # 1. The set that actually ships is usable.
    check(
        badge_anchor_problems(badges, anchors, DOWNSCALE_PROFILE) == [],
        f"shipped anchors must be usable, got {badge_anchor_problems(badges, anchors, DOWNSCALE_PROFILE)}",
    )
    check(
        DOWNSCALE_PROFILE.badge_bbox[2:] == (MODEL_W, MODEL_H),
        f"model badge cell must be {MODEL_W}x{MODEL_H}, got {DOWNSCALE_PROFILE.badge_bbox[2:]}",
    )
    for state, stems in BADGE_ANCHOR_FILES.items():
        for stem in stems:
            check((badges / f"{stem}.png").exists(), f"declared anchor {state}/{stem}.png must exist on disk")
    for state, group in anchors.items():
        for a in group:
            check(a.shape[:2] == (MODEL_H, MODEL_W), f"anchor in {state} must be {MODEL_W}x{MODEL_H}, got {a.shape[1]}x{a.shape[0]}")

    # 2. A declared stem going missing must be caught — the case the suite was blind to.
    check(badge_anchor_problems(Path("no_such_dir"), anchors, DOWNSCALE_PROFILE) != [], "an absent anchor dir must be reported")

    # 3. Right count, wrong scale (the 1440p set restored by hand) must be caught. This
    #    is the one that otherwise starts cleanly and classifies nothing, forever.
    wrong_scale = {k: [np.zeros((40, 111, 3), np.uint8) for _ in v] for k, v in anchors.items()}
    check(
        any("wrong shape" in p for p in badge_anchor_problems(badges, wrong_scale, DOWNSCALE_PROFILE)),
        "a 111x40 (1440p) anchor set must be reported as wrong shape",
    )


def main() -> int:
    check_read_gates()
    check_inferred_state()
    check_detector_stream()
    check_reentry_resolver()
    check_reentry_commit()
    check_fire_at_station()
    check_badge_anchor_set()

    if FAILURES:
        print(f"FAIL: auto-driver ({len(FAILURES)} check(s))")
        print("\n".join(FAILURES))
        return 1
    print(
        f"PASS: auto-driver (read gates {len(BADGE_GATE_CASES)} badge-reject + {len(OFFSET_CASES)} stopping-offset + "
        f"{len(DISTANCE_CASES)} distance + double-spike; {len(INFER_CASES)} inferred-state cells + MOVING==PASSING; "
        f"detector stream A-N; {len(GRID)} re-entry grid cells + PASSING/provenance/pa=1 facets + regressions + guards; "
        f"re-entry commit pa>=2 silent / pa=1 audible; at-station reachability drain + 1B + pa=1 + parked skip; badge anchor set complete + model-scale)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

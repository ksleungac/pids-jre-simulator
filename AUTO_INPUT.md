# Auto-Input — OCR-driven PA firing from JR EAST Train Sim HUD

Companion module that automates PA-firing in the simulator by reading the JR EAST
Train Simulator game's HUD via screen capture. Removes the need to press PageDown
manually during normal driving.

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** schema reference, gotchas, invariants — implementation specifics looked up when editing the relevant submodule.
>
> **Refuses:**
> - History notes / change logs (`### 2026-03-14`, "pre-X behavior", "Key Changes from legacy …") — `git log` has this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future sections ("When X is implemented, …") — defer until needed
> - Design-discussion rationale (multi-paragraph framings of *why* a model exists) — the rule lives here; the rationale lives in `memory/YYYY-MM-DD.md`
> - Facts already in [CLAUDE.md](CLAUDE.md) mental model / a skill / an inline `# CONTRACT:` — cross-reference, don't restate
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](.claude/rules/principles.md).

## Mental model

The auto-driver is an **input layer** — it observes game state via OCR on the game
window, detects state transitions, and emits PA-fire events. The simulator's existing
state machine (`AppState`, `_next_pa`, `state.curr_stop`) is the source of truth for
*what* PA to play; the auto-driver only decides *when* to advance the queue.

This split keeps fidelity work (LCD rendering, route data, audio cuts) decoupled from
input automation. The auto-driver can be disabled and the simulator behaves exactly
as today, with manual PageDown control.

**Two integrations.** Both live in this repo and share the OCR + state-machine
implementation:

- **In-process** (`auto_input.py` `AutoDriver`) — spawned from `main.py` when
  the **OCR Auto-PA** toggle is enabled on the setup screen. Runs in a daemon
  thread and sets `PASimulator.pending_next_pa = True` at fire-time, same code
  path as manual PageDown. Manual-press precedence is implicit: the driver
  inspects `sim.state.curr_stop` / `sim.state.cnt_pa` each cycle and skips its
  fire on mismatch. Includes the in-window debug panel.
- **Separate-process** (`_dev_scripts/capture_game.py`) — standalone diagnostic
  script. Synthesizes PageDown via the `keyboard` library and uses a
  self-press timestamp guard for manual-press precedence. No debug panel.

## State machine layering

The auto-driver subsystem involves three distinct state machines. They align in
normal flow but diverge after manual user action — keeping them separate in
vocabulary prevents the wrong fix landing in the wrong layer.

### Layer 1 — App (sim's own state machine)

State on `AppState` (`curr_stop`, `cnt_pa`, `cnt_pa_at_station`, `at_station`).
Exists whether the auto-driver is enabled or not. Three press-driven sub-states
per stop: `APPROACHING_EARLY` → `APPROACHING_FINAL` → `STOPPING`. Spec in
[DISPLAY.md § Unified State Machine](DISPLAY.md); mental-model summary in
[CLAUDE.md § App state machine](CLAUDE.md). The auto-driver triggers transitions
by setting `pending_next_pa=True`, same code path as manual PageDown.

### Layer 2 — AutoDriver belief

Per-segment flag set on the `_Detector` instance: `_segment_start_stop`,
`departure_observed`, `arrival_observed`, `at_station_observed`. The auto-driver's belief
about which segment the App layer is mid-way through and which fires it has
already dispatched. Lives across samples; all flags reset on
`BADGE_STOPPED→(MOVING|PASSING)` (segment boundary).

### Layer 3 — AutoDriver's inferred game state

What the auto-driver thinks the IRL game train is doing — expressed as one of
five canonical named states + a sentinel:

| Canonical name | Game-side meaning |
|---|---|
| `STOPPING_FRESH` | At platform, no in-segment arrival was observed (boot, post-click, or arrival trigger missed by OCR). State 1. |
| `APPROACHING_BEFORE_DEP` | In-transit, dep-trigger not yet observed in this segment. State 2. |
| `APPROACHING_AFTER_DEP` | In-transit, dep-trigger observed, arr-trigger not yet observed. State 3. |
| `MOVING_AFTER_ARR` | In-transit, arr-trigger observed, decelerating to platform. State 4. |
| `STOPPING_AFTER_ARR` | At platform, arr-trigger observed in this segment. State 5. |
| `UNKNOWN` | OCR FAIL or insufficient context. Sentinel. |

**Naming-collision note.** Layer 1 also uses `STOPPING` / `APPROACHING_EARLY` /
`APPROACHING_FINAL` semantically. Layer 3 names always carry a suffix (`_FRESH`,
`_BEFORE_DEP`, ...) to keep them distinguishable in code and design discussion.
Never use bare `STOPPING` / `APPROACHING_*` for Layer 3.

These are **inference outputs**, not direct OCR reads. Inputs:

- **Raw OCR observations**: `badge_read ∈ {STOPPED, MOVING, PASSING}`,
  `speed_read`, `distance_read` — single-sample reads of the game HUD.
- **Layer 2 cache** (per-segment): `departure_observed`, `arrival_observed`,
  `at_station_observed`. Necessary because OCR alone doesn't distinguish e.g.
  `APPROACHING_BEFORE_DEP` from `APPROACHING_AFTER_DEP` — both show
  `badge∈{MOVING,PASSING}`; the cache disambiguates. The flags semantically
  record "we observed the trigger condition this segment," not "we dispatched
  a fire" — the dispatcher's mismatch-skip is a separate concern.

**Streaming inference truth table** (per-sample, with cache):

| `badge` | `arrival_observed` | `departure_observed` | → state |
|---|---|---|---|
| `STOPPED` | False | * | `STOPPING_FRESH` |
| `STOPPED` | True | * | `STOPPING_AFTER_ARR` |
| `MOVING` or `PASSING` | True | * | `MOVING_AFTER_ARR` |
| `MOVING` or `PASSING` | False | True | `APPROACHING_AFTER_DEP` |
| `MOVING` or `PASSING` | False | False | `APPROACHING_BEFORE_DEP` |
| `None` | * | * | `UNKNOWN` |

(`at_station_observed` doesn't appear — it gates dispatch of FIRE_AT_STATION, not
the inferred state.)

**Entry-point inference** (no Layer 2 cache; toggle-ON, click reanchor):
substitute `distance ≤ lead` for `arrival_observed`. `STOPPING_FRESH` ≡
`STOPPING_AFTER_ARR` (collapsed at entry — functionally identical anchoring).
`APPROACHING_BEFORE_DEP` lumped into `APPROACHING_AFTER_DEP` (the brief
acceleration window is functionally equivalent at entry).

The inference function is pluggable; future cross-attribute hardening enriches
it without changing the named-state vocabulary.

**Vocabulary discipline.** In design conversations and code comments:

1. **Use the Layer 1 / 2 / 3 named states verbatim** — say *"AutoDriver thinks
   the game is in `STOPPING_FRESH`"*, not *"badge is STOPPED"* or any invented
   parallel vocabulary. The badge is one input to the inference; the inferred
   state is what the design reasons about. The vocabulary separation lets us
   harden inference without re-litigating design conclusions.
2. **Use arrow-flow notation for state progressions** — write
   `STOPPING(queue) → STOPPING(queue exhausted) → APPROACHING_EARLY`, not a
   multi-column table. Tables fit orthogonal cross-products (Layer 3 × Layer 1
   alignment table); progressions are a sequence and read as arrows. Tables on
   transitions read as over-engineered.
3. **Don't redesign the state machine** — the named states are already
   implemented in `_Detector.update`. Design how flows interact with them, not
   what they should be.

### Layer interaction

Normal flow:

```
Layer 3 observation → event → Layer 2 dispatch (mismatch-skip) → pending_next_pa
                                                                    ↓
                                                         Layer 1 advance via _next_pa
```

Layer 2 follows Layer 3. Layer 1 follows Layer 2. The reverse direction —
Layer 1 drifting from Layer 2 due to user action — is reconciled via dispatcher
mismatch-skip + flag reset on next `BADGE_STOPPED→(MOVING|PASSING)`.

### When layers diverge

| Cause | Effect | Reconciled by |
|---|---|---|
| Manual PageDown | Layer 1 advances by one press; Layer 2 unchanged | Dispatcher mismatch-skip on next event; full flag reset on next `STOPPED→(MOVING\|PASSING)` |
| Click-jump on lower LCD | Layer 1 jumps to STOPPING@target; Layer 2 unchanged | Mismatch-skip for small drift; multi-stop drift waits for next `STOPPED→(MOVING\|PASSING)` reset (or explicit re-anchor flow if implemented) |
| Auto-driver toggled ON mid-drive | Layer 1 is whatever the user advanced to; Layer 2 has no belief yet | Entry-point flow probes Layer 3, anchors Layer 2 to match the detected segment context |

Layer 3 stays accurate at all times — it observes the game, not the sim.
Reconciling Layer 1 ↔ Layer 2 is what mismatch-skip and the entry-point flow
exist to do.

## Architecture

```
[JR EAST Train Sim window — DirectX]
              │
              │ DXGI Output Duplication (dxcam)
              ▼
[Full desktop frame — 2560×1440 BGRA]
              │
              │ HUD_BBOX crop
              ▼
[HUD region — 350×480]
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
  [Distance][Speed][Badge]
   cell      cell  cell
       │      │      │
   OCR digits OCR  pixel-diff
   + 'm' filter +  vs anchors
                decimal-stop
       │      │      │
       ▼      ▼      ▼
   int m   int km/h  "MOVING" | "STOPPED" | "PASSING"
       │      │      │
       └──────┼──────┘
              ▼
     [PaEventDetector]
              │
              ▼
   ┌──────────────────────────────────┐
   │ Events:                          │
   │   BADGE_STOPPED→MOVING           │
   │   SPEED_UP_30                    │
   │   DIST_DOWN_<lead_m>             │
   │   BADGE_MOVING→STOPPED           │
   │   FIRE_AT_STATION                │
   └──────────────────────────────────┘
              │
              ▼ for each "fire ... PA" event:
   [AutoDriver._handle_event — inspects sim.state directly]
   sim.state.curr_stop changed unexpectedly?  → skip (manual advance)
   target stop has only 1 PA?                 → skip (no arrival announcement)
   sim.state.cnt_pa already at last PA?       → skip (user fired manually)
   otherwise                                  → sim.pending_next_pa = True
              │
              ▼ (next pygame frame on main thread)
   [PASimulator._handle_input_main — pending_next_pa OR keyboard.is_pressed]
              │
              ▼
   PASimulator._next_pa() → state.curr_stop / state.cnt_pa advance
```

## Resolution dependency

Currently calibrated for **2560×1440 native fullscreen game window**. Other
resolutions need `HUD_BBOX` recalibration and re-extracted digit templates.
See "Recalibration" below.

The user's setup happens to be 2560×1440 native, which makes this a non-issue for
their workflow. Multi-resolution support is future work.

## HUD layout (2560×1440)

All bboxes are `(x, y, w, h)`. Cell bboxes are HUD-relative; the HUD bbox is
screen-relative.

| Constant | Value | Notes |
|---|---|---|
| `HUD_BBOX` | `(2200, 20, 350, 480)` | Top-right corner of game window |
| `DISTANCE_VALUE_BBOX` | `(120, 314, 230, 55)` | Right side of "Distance" / "残距離" row |
| `SPEED_VALUE_BBOX` | `(120, 165, 230, 55)` | Right side of "Speed" / "速度" row |
| `BADGE_BBOX` | `(15, 117, 125, 45)` | Green pentagon in next-station row |

Position invariant across language modes (EN/JA), game states (running/stopped/at-platform), and scenes — verified against 7 reference screenshots.

## Capture: dxcam (DXGI Output Duplication)

**Why not Win32 PrintWindow or BitBlt-from-desktop:** the game renders via DirectX,
and the swap chain isn't visible to GDI. Both APIs return all-black frames even with
`PW_RENDERFULLCONTENT` flag set. **dxcam** uses DXGI Output Duplication (the same
GPU-level capture API used by Discord/OBS), reading the GPU framebuffer directly.

```python
import dxcam
camera = dxcam.create(output_color="BGRA")  # native, skips cv2 conversion
frame = camera.grab()  # full desktop, (H, W, 4) BGRA numpy array
```

Notes:
- BGRA output is DXGI's native format; choosing it avoids requiring opencv as a dep
- `grab()` can return `None` (no new frame since last call) — retry with brief sleep
- Game must be **rendering** (not minimized/alt-tabbed in a state where it pauses)
- Top-right corner where HUD lives must not be covered by other windows

## OCR pipeline (digit cells)

### Stage 1 — segmentation

```
cell (RGB) → grayscale → threshold (gray < 70) → column-sum > 2 = "has text"
                         (text band y=15..52)
                                 │
                                 ▼
            Find runs of has-text columns separated by gaps → raw bboxes
```

The text band excludes the HUD's top/bottom borders and any scenery bleed-through
near the cell edges.

### Stage 2 — filtering

Three filters in sequence:

1. **Digit-shape filter**: keep only bboxes with `h ≥ 22` and `7 ≤ w ≤ 30`.
   Drops 'm' suffix strokes (h≈10), label tail fragments, scenery blobs.
2. **Decimal-stop** (speed only): scan raw bboxes for a small bbox
   (`h ≤ 10, w ≤ 7`) in the bottom half of the text band — that's the decimal
   point. Stop accepting digits at its x-position. **Robust against gap variance**;
   replaces the gap-based heuristic that was failing on `1x.x` and `11x.x`.
3. **Gap-stop** (safety net): stop accepting digits at first horizontal gap
   greater than `MAX_GAP`. Distance: 20 (anything past 'm' has bigger gap).
   Speed: 25 (relaxed because decimal-stop is the primary boundary; 25 catches
   scenery blobs but lets through wide kerning like '1' to '1' which can be 18px).

### Stage 3 — template matching

Templates: 10 binary glyphs (digits 0-9) extracted from labeled reference
screenshots via the `KNOWN_VALUES` dict in `ocr.py`.

Matching: each segmented bbox's binary glyph is padded to the size of the
template, then compared pixel-equality. Score = fraction of matching pixels
(0.5 = random for binary). Best-scoring template wins per glyph; concatenate
to integer.

Live scores observed: 0.75–1.00. Below 0.6 is the danger zone (random match
territory).

### Tunable constants (in `ocr.py`)

| Constant | Value | Rationale |
|----------|-------|-----------|
| `DARK_THRESHOLD` | 70 | Excludes gray scenery; keeps near-black text |
| `COLUMN_TEXT_MIN` | 2 | Filters single-pixel column noise |
| `ROW_TEXT_MIN` | 1 | Tight row bounds |
| `TEXT_BAND_Y` | (15, 52) | Excludes borders + scenery bleed at cell edges |
| `DIGIT_MIN_H` | 22 | Distance/speed digits ≈ 30-33 px tall |
| `DIGIT_MIN_W` | 7 | Narrowest digit ('1') ≈ 8-9 px |
| `DIGIT_MAX_W` | 30 | Widest digit ≈ 23 px |
| `DECIMAL_MAX_H` | 10 | Decimal point ≈ 4-5 px tall |
| `DECIMAL_MAX_W` | 7 | Decimal point ≈ 3 px wide |
| `DECIMAL_BASELINE_FRACTION` | 0.55 | Decimal sits in bottom half of text band |
| `DISTANCE_MAX_GAP` | 20 | Inter-digit gap < 20; m-stroke gap > 20 |
| `SPEED_MAX_GAP` | 25 | Wider for narrow `1`-to-`1` kerning (~18 px) |

## Badge classification (state cell)

Game shows a pentagon badge in the next-station row, with text inside:

| State | EN text | JA text | Color | Meaning |
|---|---|---|---|---|
| MOVING | "Next" | "次停車駅" | green | Train heading to next stopping station (badge displays target) |
| STOPPED | "Stopping at" | "停車中" | green | Train at platform |
| PASSING | "Pass" | "通過" | **blue** | Train crossing a station that won't be stopped at; badge still displays the next *stopping* station, but **HUD distance is to the passing station, not the stopping target** |

**Critical observations:**
- Pentagon shape is **identical** across all three states — only text content + fill colour differ.
- MOVING and STOPPED both use the same green pentagon; pixel-diff against text-content anchors is what discriminates them.
- PASSING's blue fill gives the classifier a wide separation margin: cross-state mean diff to MOVING/STOPPED is ~43, vs within-state ~6–10.

### Classifier

Pixel-diff against 6 anchor templates:

```python
BADGE_ANCHOR_FILES = {
    "MOVING":  ["running_en", "running_ja"],             # Next, 次停車駅
    "STOPPED": ["stopping_en", "stopping_next_station"], # Stopping at, 停車中
    "PASSING": ["passing_en", "passing_jp"],             # Pass, 通過
}
```

Per frame: crop badge cell, compute mean-abs-diff against each anchor, pick the
state with the lowest-diff anchor. Language-agnostic — whichever anchor matches
best determines the state, regardless of which language the user plays in.

Diff < 15 = high confidence. Transient diff spikes (e.g. > 70) at exact transition
moments are normal — the badge is mid-animation and matches neither anchor cleanly
for one frame. The state machine handles this via flag-resets only on transitions.

## State machine — `PaEventDetector`

Lives in `_dev_scripts/capture_game.py` (1b) + `auto_input.py` `_Detector` (1a, kept in sync). Tracks distance + speed + badge across samples, emits PA-fire event names on transitions.

### State vocabulary

The state machine works in the Layer 3 named-state vocabulary — see "State machine layering" above for the canonical names + inference truth table. The 5 states (`STOPPING_FRESH`, `APPROACHING_BEFORE_DEP`, `APPROACHING_AFTER_DEP`, `MOVING_AFTER_ARR`, `STOPPING_AFTER_ARR`) + `UNKNOWN` sentinel describe the autodriver's inferred view of where the IRL game train is in its segment cycle. They map onto the per-sample event emissions below.

**When designing flows that interact with the state machine** (entry-point, resync, click-to-jump): say *"AutoDriver thinks the game is in `STOPPING_FRESH`"*, not *"badge is STOPPED."* The badge is one input to the inference; the inferred state is what the design reasons about. The separation matters for hardening — and avoids design conclusions accidentally over-trusting a single OCR attribute.

### Events

| Event | Trigger | Effect |
|---|---|---|
| `BADGE_STOPPED→MOVING` | badge transition | New segment begins; reset all three observed-flags + segment_start_ts |
| `BADGE_MOVING→STOPPED` | badge transition | Train just arrived at platform (logged only — see `FIRE_AT_STATION`) |
| `SPEED_UP_30` | speed crossed 30 km/h upward AND `departure_observed=False` | Fire departure PA, set `departure_observed=True` |
| `DIST_DOWN_<lead>` | `badge==MOVING` AND `distance ≤ arrival_lead_m` AND `arrival_observed=False` | Fire arrival PA, set `arrival_observed=True` |
| `FIRE_AT_STATION` | `badge==STOPPED` AND `arrival_observed=True` AND `at_station_observed=False` | Fire the silent press that flips sim into STOPPING (sets `state.at_station=True`); set `at_station_observed=True` |

`arrival_lead_m` defaults to **900m**. For 1a, adjust on the setup-screen Lead
stepper (range 500–1500, ±100m) before launching. For 1b, override with `--lead`
on the `_dev_scripts/capture_game.py` invocation. Use 1200m for transfer-heavy
lines (Tokyo, Shinjuku scenarios).

**Per-segment observed flags** prevent double-firing within a single segment when
OCR misreads transiently flip a threshold-crossing condition (e.g. a speed misread
as `7` between two real `>30` reads would fire `SPEED_UP_30` twice without the
flag). All three flags (`departure_observed`, `arrival_observed`, `at_station_observed`)
reset on `BADGE_STOPPED→MOVING`. PASSING transitions do NOT reset flags — PASSING
is a transient sub-state of MOVING within a segment, not a new segment.

**`at_station_observed` is gated on `arrival_observed`** so it only triggers in this
segment's stopping moment. Without that gate, the level test would fire on the
first capture cycle (train parked at session start with `badge==STOPPED`) and
desync the simulator before the first real drive begins. Pa-empty stops still
get the at-station fire — `_fire_at_station` accepts `pa==[]` because the
APPROACHING→STOPPING transition is silent regardless of pa contents.

### Arrival is a level test, not a downward crossing

The arrival trigger fires whenever `badge==MOVING AND distance ≤ arrival_lead_m`,
gated by the per-segment `arrival_observed` flag. It does **not** require a
downward-crossing of the threshold.

This matters because of PASSING. While the badge reads PASSING, HUD distance is
to the passing-through station (NOT to the next stopping target). The detector
ignores those samples entirely:

- **Arrival check is gated on `badge==MOVING`** — a PASSING-relative sample at, say,
  300m to the passing station does not trigger arrival for the actual stopping
  station that's still 1500m away.
- **`prev_distance` is no longer tracked** — the level test doesn't need it. The
  old downward-crossing test (`prev > lead >= curr`) couldn't handle the case
  where `PASSING→MOVING` resumed with distance already < lead (the first MOVING
  sample's distance jumps *up* relative to the PASSING-relative prev, defeating
  the crossing check). Level test handles it cleanly: any MOVING sample with
  `distance ≤ lead` fires arrival, exactly once per segment.

Speed/departure logic is unchanged — speed is own-train and badge-independent.

**Manual-press precedence.** When a `fire ... PA` event would auto-send PageDown,
the dispatcher first checks `keys.last_user_pagedown_ts > detector.segment_start_ts`.
If the user already pressed PageDown manually since the segment began, the
auto-fire is skipped (logged as `SKIPPED auto-fire (user already pressed ...)`).
This means: pressing PageDown manually always wins; the auto-driver fills in only
where you didn't.

**Self-press guard.** The `keyboard.on_press_key` global hook fires on ALL
PageDown events including the synthetic ones we send. Within `SELF_PRESS_GUARD_S`
(500ms) of an auto-send, key callbacks ignore the press as our own. Prevents
self-detection that would mark the segment as "user already pressed".

`None` values for distance/speed/badge are tolerated — OCR FAIL frames don't
reset state, so transient unreadable frames don't break the segment continuity.

## Debug panel (in-process integration only)

When OCR Auto-PA is enabled at the setup screen, `PASimulator` allocates an
extra `DEBUG_PANEL_HEIGHT = 80` row above the LCD via pygame sub-surfaces. The window
becomes 730×500 instead of 730×420; the LCD code is **completely unchanged** because
it gets a sub-surface positioned at `(0, 80)` and thinks it's drawing to a regular
730×420 screen.

**Strict separation per user requirement:** the panel render logic lives entirely
in `auto_input.py` (function `draw_debug_panel`). `app.py`'s `_render_panel()`
helper just hands the sub-surface to the auto-input module. The simulator
**doesn't know** how the panel renders — colors, layout, fonts, text — all owned
by `auto_input.py`. Zero `displays/` imports in the panel render code.

The panel and LCD never overlap render areas. The panel uses its own background
color `_PANEL_BG = (18, 22, 28)` (visually distinct from LCD's `DARK_BG`).

### Layout

3 lines, font ShinGoPr6N-Medium @ 14pt (loaded lazily, supports both Latin + CJK
so station names in the state line render correctly):

```
[AUTO-INPUT]   badge: MOVING (d=3.2)
spd:  73 km/h    dst:  850m   cnt_pa=1  dep✓  arr·
state: between 錦糸町 → 新小岩  (curr_stop=4)
```

Confidence color encoding:

| Color | Meaning |
|---|---|
| **Green** | OCR score ≥ 0.90; badge diff ≤ 5 |
| **Yellow** | 0.75–0.90; diff 5–15 |
| **Orange** | < 0.75; diff > 15 |
| **Gray** | None / OCR FAIL |

`dep✓ arr·` flags reflect `auto_input_status["departure_observed"]` and
`auto_input_status["arrival_observed"]` — the per-segment observed flags reset on
`BADGE_STOPPED→MOVING` transitions.

State line uses simulator's `state.curr_stop` + the captured `segment_start_stop`
to display "between A → B" or "stopped at A".

### Width adaptivity

Panel uses whatever surface width the caller provides (`PASimulator` allocates
the sub-surface at `S_WIDTH` from the active train model). When future train
models with different LCD widths are added, panel follows automatically.

### Status dict (single-writer / single-reader, atomic dict assignment)

`AutoDriver` thread populates `sim.auto_input_status` after each capture:

```python
{
    "badge": "MOVING" | "STOPPED" | None,
    "badge_diff": float | None,
    "speed": int | None,           # km/h, integer (decimal stripped)
    "speed_score": float,           # OCR confidence 0..1
    "distance": int | None,         # meters
    "distance_score": float,
    "segment_start_stop": int,      # sim.state.curr_stop snapshot at last STOPPED→MOVING
    "departure_observed": bool,
    "arrival_observed": bool,
    "at_station_observed": bool,       # set when the silent STOPPING-entry press has fired
    "inferred_state": str,             # canonical Layer 3 state name (see § "Layer 3" truth table)
    "ts": float,                    # time.time() of capture
}
```

CPython dict assignment is atomic. No lock needed for single writer (BG thread)
+ single reader (main thread).

## Sample interval

**5 seconds.** Trade-off:

- **Tighter** would catch threshold crossings more precisely but burns more CPU
  and could flood logs with redundant identical reads
- **Wider** would miss events; at 100 km/h the train moves ~140m in 5s, so a
  wider sample could miss the 900m threshold entirely

5s is a good balance for both threshold detection and event cadence.

The state machine is robust to the granularity — `prev_<X>` carries forward
between samples, and threshold-crossings fire on the first sample after the
boundary is crossed.

## Usage

**In-process integration** (the default path):

```bash
# Toggle OCR Auto-PA on the setup screen, adjust Lead (default 900m, ±100m
# steps) and Interval (default 5s, ±1s), then select a route with Enter.
uv run main.py
```

**Separate-process script** (diagnostic / observation):

```bash
# Default — 900m arrival threshold, 5s sample interval, fires synthetic PageDowns
uv run python _dev_scripts/capture_game.py

# Transfer-heavy line — bump arrival threshold
uv run python _dev_scripts/capture_game.py --lead 1200

# Debug / observation mode — log OCR + events but don't send keystrokes
uv run python _dev_scripts/capture_game.py --no-fire

# Pass --route to enable PA-count cross-check
uv run python _dev_scripts/capture_game.py --route audio/sobu/1217F
```

Stop with Ctrl+C. The script prints one line per sample (badge state, speed,
distance, scores) plus indented `>>>` lines for state-machine events and
auto/manual key activity.

## Files

| Path | Role |
|---|---|
| `auto_input.py` | **Primary** — `AutoDriver` class (in-process daemon thread) + `draw_debug_panel()` (panel render) + `_Detector` state machine + `handle_panel_click()` dispatcher (in-panel buttons, currently the Report download). All auto-input logic lives here. |
| `main.py` | Reads `auto_input` / `lead_m` / `interval_s` from the setup-screen config dict. Spawns `AutoDriver` when `auto_input=True` and passes the same flag to `PASimulator`. |
| `setup.py` | OCR Auto-PA toggle pill + Lead/Interval steppers under the route list. `_handle_band_click` updates state; selected route's Enter returns config dict including the auto-input fields. |
| `app.py` | `PASimulator`: allocates debug sub-surface in `_init_pygame`; `pending_next_pa` flag checked alongside keyboard in `_handle_input_main`; `auto_input_status` dict written by AutoDriver, read by `_render_panel()` which delegates to `auto_input.draw_debug_panel`. `MOUSEBUTTONDOWN` events landing in the panel area get forwarded to `auto_input.handle_panel_click`. `drive_log_path` attribute stashes the live JSONL path so the Report button can find it. **No panel rendering logic lives in app.py.** |
| `constants.py` | `DEBUG_PANEL_HEIGHT = 80` |
| `hud_layout.py` | HUD + cell bbox constants for 2560×1440 |
| `ocr.py` | OCR pipeline + badge classifier; runnable for offline validation (`uv run python ocr.py`) |
| `_dev_scripts/capture_game.py` | Standalone observation/debug script (separate process, synthetic keystrokes, optional `--route` flag for PA-count check) |
| `_dev_scripts/test_dxcam.py` | Diagnostic — full-desktop dxcam capture + brightness check |
| `ocr_templates/digits/*.png` | **Runtime input** — 10 pre-extracted digit glyphs (~20×30 binary PNGs, ~1 KB each). Loaded by `ocr.build_templates()`. Committed. |
| `ocr_templates/badges/*.png` | **Runtime input** — 6 pre-extracted badge cell crops (125×45 RGB PNGs, ~5 KB each). Loaded by `ocr.load_badge_anchors()`. Committed. |
| `_ocr_calibration/*.png` | **Local-only** source screenshots (full 2560×1440 desktop captures, ~33 MB total). Gitignored. Only needed when re-extracting `ocr_templates/` after a game HUD layout change. |
| `_dev_scripts/extract_ocr_assets.py` | One-shot extractor: reads `_ocr_calibration/` source screenshots → writes `ocr_templates/`. Run after re-capturing sources, then commit the diff. |
| `_recordings/drive_<line>_<diagram>_<TS>.jsonl` | **Blackbox / drive recorder log** — one file per AutoDriver lifetime. Line 0 is `_type: "meta"` (route/diagram/dest/stops); subsequent lines are `_type: "sample"` (one OCR cycle each). Written inside `auto_input.py`'s capture loop with per-line `flush()` for crash safety. Local-only / gitignored. Schema is locked — downstream plot generator depends on the layout. |
| `_experiments/live_captures/` | Saved HUD crops from prior live testing (gitignored — `_experiments/` itself is now an artifact-only folder; OCR + layout modules promoted to root) |
| `fonts/ShinGoPr6N-Medium.otf` | Latin + CJK font used by debug panel for station names |

## Recalibration for other resolutions

If the game runs at a different resolution:

1. Capture screenshots in the target resolution with HUD visible (running mode + at-platform mode + passing-through mode)
2. Identify HUD position (top-right); update `HUD_BBOX` in `hud_layout.py`
3. Crop HUD; identify cell positions within it; update `*_VALUE_BBOX` and `BADGE_BBOX`
4. Save the 9 source screenshots into `_ocr_calibration/` (gitignored). Filenames must match the keys in `KNOWN_VALUES` (digits) + `BADGE_ANCHOR_FILES` (badges) — both live in `_dev_scripts/extract_ocr_assets.py` and `ocr.py` respectively. PASSING is the rapid-service "Pass" / "通過" blue pentagon (filenames `passing_en.png`, `passing_jp.png`).
5. Run `uv run python _dev_scripts/extract_ocr_assets.py` — extracts digit glyphs + badge anchor crops into `ocr_templates/`.
6. Run `uv run python ocr.py` to sanity-check the new templates load + cross-classify cleanly. Commit the `ocr_templates/` diff.

Digit templates are resolution-specific because exact-pixel matching requires
the same glyph dimensions. A future enhancement could resize templates by
scaling factor, but pixel-perfect matching is more reliable.

## Limitations

- **Fixed resolution**: 2560×1440 only. Other resolutions need full recalibration.
- **Game must be visible**: HUD area (top-right) must not be covered.
- **Game must be actively rendering**: minimized/alt-tabbed games may stop rendering and produce stale captures.
- **Scenery bleed**: HUD background is semi-transparent; very dark scenery behind reduces match scores (still reads correctly above ~0.7).
- **No station-name OCR**: auto-driver doesn't validate which station the user is at; it trusts simulator's `state.curr_stop`. If they desync, manual PageDown is the recovery.
- **Game DRM**: irrelevant to the OCR pipeline (works on legit + cracked installs identically since dxcam reads GPU output regardless of game's startup path).

Pending design (entry-point flow), validation history, calibration insights /
guardrails, and the priority-ordered backlog all live in
[WIP_autodriver.md](WIP_autodriver.md).

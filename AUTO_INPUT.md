# Auto-Input — OCR-driven PA firing from JR EAST Train Sim HUD

Companion module that automates PA-firing in the simulator by reading the JR EAST
Train Simulator game's HUD via screen capture. Removes the need to press PageDown
manually during normal driving.

## Status (as of 2026-04-27)

**PASSING badge** (rapid-service passing-through stations, "Pass" / "通過", blue
pentagon) recognized in addition to MOVING/STOPPED. Arrival-PA logic suppresses
firing while badge==PASSING (HUD distance during PASSING is to the passing-through
station, not the next stopping target). On PASSING→MOVING the level-test arrival
check correctly fires even if distance is already < lead.

**Two working integrations:**

- **(1b) Separate-process auto-driver** — `data_tools/capture_game.py`. Synthesizes
  PageDown via `keyboard` library. **Live-validated end-to-end** on Keihin-Tōhoku
  727B Omiya→Kanda full route — flawless. Use `--route audio/<line>/<diagram>` to
  enable PA-count check.
- **(1a) In-process auto-driver** — `auto_input.py` `AutoDriver` class spawned
  from `main.py` when the **OCR Auto-PA** toggle is enabled on the setup screen.
  Runs in daemon thread, sets `PASimulator.pending_next_pa = True` at fire-time
  (same code path as manual PageDown — no synthetic keystrokes, no parallel
  route loading, no segment counter parallel to `state.curr_stop`). **Compiles
  + renders cleanly. NOT yet live-validated** — Omiya→Kanda was on 1b. First
  task next session: live-test 1a.

**Debug panel (1a only)** — when OCR Auto-PA is enabled at the setup screen, an
80px panel renders above the LCD showing badge state, speed/distance with
confidence-color encoding, fired flags, and "between A → B" / "stopped at A"
state. Architecturally separated from LCD code (see "Debug panel" section below).

```bash
# Run the in-process integration. Toggle OCR Auto-PA on the setup screen,
# adjust Lead (default 900m, ±100m steps) and Interval (default 5s, ±1s) as
# needed, then select a route with Enter to launch.
uv run main.py

# Run the standalone observation/debug script
uv run python data_tools/capture_game.py --route audio/sobu/1217F
```

Manual-press precedence is implicit in 1a: the auto-driver inspects
`sim.state.curr_stop` and `sim.state.cnt_pa` directly each cycle. If you press
PageDown manually before an auto-fire, simulator state advances; the auto-driver
detects mismatch and skips its own fire. In 1b this is via global keyboard hooks
+ self-press timestamp guard.

Future work (in priority order): live-validate 1a (Omiya→Kanda equivalent),
dynamic 900/1200m threshold from per-stop PA durations, multi-PA queue
auto-advance, multi-resolution support, separate-window debug panel (today
shares window with LCD via sub-surfaces).

## Mental model

The auto-driver is an **input layer** — it observes game state via OCR on the game
window, detects state transitions, and emits PA-fire events. The simulator's existing
state machine (`AppState`, `_next_pa`, `state.curr_stop`) is the source of truth for
*what* PA to play; the auto-driver only decides *when* to advance the queue.

This split keeps fidelity work (LCD rendering, route data, audio cuts) decoupled from
input automation. The auto-driver can be disabled and the simulator behaves exactly
as today, with manual PageDown control.

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

Lives in `data_tools/capture_game.py` (1b) + `auto_input.py` `_Detector` (1a, kept in sync). Tracks distance + speed + badge across samples, emits PA-fire event names on transitions:

| Event | Trigger | Effect |
|---|---|---|
| `BADGE_STOPPED→MOVING` | badge transition | New segment begins; reset both fired-flags + segment_start_ts |
| `BADGE_MOVING→STOPPED` | badge transition | Train just arrived at platform |
| `SPEED_UP_30` | speed crossed 30 km/h upward AND `departure_fired=False` | Fire departure PA, set `departure_fired=True` |
| `DIST_DOWN_<lead>` | `badge==MOVING` AND `distance ≤ arrival_lead_m` AND `arrival_fired=False` | Fire arrival PA, set `arrival_fired=True` |

`arrival_lead_m` defaults to **900m**. For 1a, adjust on the setup-screen Lead
stepper (range 500–1500, ±100m) before launching. For 1b, override with `--lead`
on the `data_tools/capture_game.py` invocation. Use 1200m for transfer-heavy
lines (Tokyo, Shinjuku scenarios).

**Per-segment fired flags** prevent double-firing within a single segment when
OCR misreads transiently flip a threshold-crossing condition (e.g. a speed misread
as `7` between two real `>30` reads would fire `SPEED_UP_30` twice without the
flag). Both flags reset on `BADGE_STOPPED→MOVING`. PASSING transitions do NOT
reset flags — PASSING is a transient sub-state of MOVING within a segment, not a
new segment.

### Arrival is a level test, not a downward crossing

The arrival trigger fires whenever `badge==MOVING AND distance ≤ arrival_lead_m`,
gated by the per-segment `arrival_fired` flag. It does **not** require a
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

`dep✓ arr·` flags reflect `auto_input_status["departure_fired"]` and
`auto_input_status["arrival_fired"]` — the per-segment fired flags reset on
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
    "departure_fired": bool,
    "arrival_fired": bool,
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

```bash
# Default — 900m arrival threshold, 5s sample interval, fires synthetic PageDowns
uv run python data_tools/capture_game.py

# Transfer-heavy line — bump arrival threshold
uv run python data_tools/capture_game.py --lead 1200

# Debug / observation mode — log OCR + events but don't send keystrokes
uv run python data_tools/capture_game.py --no-fire

# Tighter / looser sampling
uv run python data_tools/capture_game.py --interval 3
```

Stop with Ctrl+C. The script prints one line per sample (badge state, speed,
distance, scores) plus indented `>>>` lines for state-machine events and
auto/manual key activity.

## Files

| Path | Role |
|---|---|
| `auto_input.py` | **Primary** — `AutoDriver` class (in-process daemon thread) + `draw_debug_panel()` (panel render) + `_Detector` state machine. All auto-input logic lives here. |
| `main.py` | Reads `auto_input` / `lead_m` / `interval_s` from the setup-screen config dict. Spawns `AutoDriver` when `auto_input=True` and passes the same flag to `PASimulator`. |
| `setup.py` | OCR Auto-PA toggle pill + Lead/Interval steppers under the route list. `_handle_band_click` updates state; selected route's Enter returns config dict including the auto-input fields. |
| `app.py` | `PASimulator`: allocates debug sub-surface in `_init_pygame`; `pending_next_pa` flag checked alongside keyboard in `_handle_input_main`; `auto_input_status` dict written by AutoDriver, read by `_render_panel()` which delegates to `auto_input.draw_debug_panel`. **No panel rendering logic lives in app.py.** |
| `constants.py` | `DEBUG_PANEL_HEIGHT = 80` |
| `hud_layout.py` | HUD + cell bbox constants for 2560×1440 |
| `ocr.py` | OCR pipeline + badge classifier; runnable for offline validation (`uv run python ocr.py`) |
| `data_tools/capture_game.py` | Standalone observation/debug script (separate process, synthetic keystrokes, optional `--route` flag for PA-count check) |
| `data_tools/test_dxcam.py` | Diagnostic — full-desktop dxcam capture + brightness check |
| `ocr_templates/digits/*.png` | **Runtime input** — 10 pre-extracted digit glyphs (~20×30 binary PNGs, ~1 KB each). Loaded by `ocr.build_templates()`. Committed. |
| `ocr_templates/badges/*.png` | **Runtime input** — 6 pre-extracted badge cell crops (125×45 RGB PNGs, ~5 KB each). Loaded by `ocr.load_badge_anchors()`. Committed. |
| `_ocr_calibration/*.png` | **Local-only** source screenshots (full 2560×1440 desktop captures, ~33 MB total). Gitignored. Only needed when re-extracting `ocr_templates/` after a game HUD layout change. |
| `data_tools/extract_ocr_assets.py` | One-shot extractor: reads `_ocr_calibration/` source screenshots → writes `ocr_templates/`. Run after re-capturing sources, then commit the diff. |
| `_experiments/live_captures/` | Saved HUD crops from prior live testing (gitignored — `_experiments/` itself is now an artifact-only folder; OCR + layout modules promoted to root) |
| `fonts/ShinGoPr6N-Medium.otf` | Latin + CJK font used by debug panel for station names |

## Recalibration for other resolutions

If the game runs at a different resolution:

1. Capture screenshots in the target resolution with HUD visible (running mode + at-platform mode + passing-through mode)
2. Identify HUD position (top-right); update `HUD_BBOX` in `hud_layout.py`
3. Crop HUD; identify cell positions within it; update `*_VALUE_BBOX` and `BADGE_BBOX`
4. Save the 9 source screenshots into `_ocr_calibration/` (gitignored). Filenames must match the keys in `KNOWN_VALUES` (digits) + `BADGE_ANCHOR_FILES` (badges) — both live in `data_tools/extract_ocr_assets.py` and `ocr.py` respectively. PASSING is the rapid-service "Pass" / "通過" blue pentagon (filenames `passing_en.png`, `passing_jp.png`).
5. Run `uv run python data_tools/extract_ocr_assets.py` — extracts digit glyphs + badge anchor crops into `ocr_templates/`.
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

## Calibration insights worth remembering

- **PrintWindow returns black for DirectX games.** Even with `PW_RENDERFULLCONTENT`. Same for BitBlt-from-desktop. dxcam (DXGI Output Duplication) is the only path that works reliably.
- **`output_color="BGRA"`** in dxcam is native; `"RGB"` requires opencv-python.
- **Set DPI awareness** before any window measurement: `ctypes.windll.shcore.SetProcessDpiAwareness(2)`. At 2560×1440 + DPI scaling, omitting this misaligns coordinates.
- **HUD text varies in pixel-population** by anti-aliasing. Fixed binarization threshold (70) is more stable than Otsu, which gets confused by 3-population distributions (text + bg + scenery bleed-through).
- **Decimal point detection by shape** (small bbox in bottom half of text band) is more robust than gap-based heuristics. Speed values like `110.7` have inter-`1` gaps of ~18px, exceeding any reasonable digit-gap threshold; only decimal-stop reliably catches the integer/decimal boundary.
- **Right-most green pixel test failed** as a badge state discriminator — both Next/Stopping pentagons are identical shapes. Pixel-diff against text-content anchors is what works.

## Validation history

- **2026-04-26 evening (Phase 1)**: dxcam capture pipeline; distance OCR (HUD bbox calibration, digit segmentation, template matching, scenery-bleed handling, gap filter, m-stroke filter); validated against 6 reference screenshots + live drive (24 distance reads through one full station segment, all correct).
- **2026-04-26 evening (Phase 2)**: speed OCR (decimal-place stripping, gap tuning); badge classifier (4-anchor pixel-diff); event state machine with per-segment fired-flags; validated against multi-station live drive (2 segments, all transitions detected correctly).
- **2026-04-26 late evening (Phase 3)**: speed OCR robustness — decimal-point detection (replaces gap heuristic for boundary), gap relaxation for narrow-digit kerning; validated on 17 live frames spanning 0–120+ km/h.
- **2026-04-27 (Phase 4)**: PASSING badge added (rapid-service "Pass" / "通過" blue pentagon); classifier expanded from 4 to 6 anchors. Arrival logic switched from downward-crossing to level test gated on `badge==MOVING` so post-PASSING under-threshold cases fire correctly. OCR + layout modules promoted from `_experiments/` to project root. Auto-input toggle + Lead/Interval steppers moved from CLI flags to setup screen. Offline OCR validation 6/6 PASS; detector scenarios cover normal segment, mid-segment PASSING, post-PASSING already-under-threshold, double-fire prevention, STOPPED gate.

## Future enhancements

Priority-ordered for next session pickup:

- [ ] **Live-validate the in-process integration (1a).** Both 1a and 1b are
  feature-complete and compile/render cleanly. **1b is the only path live-tested
  end-to-end** (Keihin 727B Omiya→Kanda flawless). 1a should behave identically
  but needs a real drive to confirm. Run `uv run main.py`, toggle OCR Auto-PA on
  the setup screen, then drive a scenario and verify PAs auto-fire at correct
  moments, debug panel updates, manual PageDown still overrides.
- [ ] **Dynamic arrival threshold**: per-stop 1200m vs 900m based on whether the
  stop's last PA is "significantly longer" than the route's average PA duration
  (transfer guides are characteristically longer). User's exact words:
  *"if it's significantly longer than the average length of other PA, then it's
  a long arriving PA, if no please go and have the most fun"*. In-process
  driver has direct access to `sim.stops` + can probe audio durations via
  `mutagen` or `soundfile` — no extra `--route` flag needed. Currently uses the
  static Lead value chosen on the setup screen.
- [ ] **Multi-PA queue auto-advance**: simulator's `_next_pa()` plays one PA per
  invocation. For multi-PA stops (transfer hubs with 3+ PAs), only the first
  arrival PA fires automatically; user manually fires the rest with PageDown.
  Auto-advance would either fire multiple `pending_next_pa` flags spaced by PA
  audio durations, or have the simulator auto-chain when configured.
- [ ] **Multi-resolution support**: bboxes + digit templates are pixel-fixed at
  2560×1440. Other resolutions need full recalibration. Future: proportional
  layout + template scaling.
- [ ] **Separate-window debug panel**: today the panel shares the LCD's pygame
  window via sub-surfaces (no overlap, but same window). User has flagged
  preference for further decoupling — possible via `pygame._sdl2.video.Window`
  for a fully separate OS window. Not a blocker; deferred.
- [ ] **STA auto-fire**: not modeled. STA is IRL-manual (station master, not
  driver), per user spec. Plumbing for synthetic PageUp + user-press monitoring
  exists in 1b if needed later.

See `data_tools/capture_game.py` and `auto_input.py` for inline notes on the
existing integration semantics.

## For next-session Claude (zero-context pickup)

If you're picking this up cold, the **highest-value task** is live-validating
the in-process integration. Steps:

1. Read this doc + `memory/2026-04-27.md` for full context.
2. Verify offline OCR still passes: `uv run python ocr.py` (should
   show 6/6 PASS).
3. Boot the simulator (`uv run main.py`), toggle OCR Auto-PA on the setup
   screen (defaults Lead 900m / Interval 5s — change via the steppers if needed),
   then select a route. Game must be running fullscreen at 2560×1440 with HUD
   visible at top-right.
4. Drive 2 stations on Keihin-Tōhoku 727B (already validated route on 1b).
   Confirm:
   - Debug panel renders all 3 lines correctly
   - Speed/distance values track HUD readings
   - `dep✓` lights up when speed crosses 30 km/h after a `STOPPED→MOVING`
   - `arr✓` lights up when distance crosses 900m descending
   - `state:` line shows correct "between A → B" / "stopped at A"
   - Manual PageDown overrides cleanly (auto skips its own fire)
5. If anything misbehaves, paste the terminal log + a panel screenshot. The 1b
   path (`data_tools/capture_game.py`) is the comparison baseline — it's known
   working.

After live-validation, the natural next bite is **dynamic 900/1200m threshold**
per the user's "remaining last PA length" spec.

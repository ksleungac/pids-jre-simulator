# Auto-Input — OCR-driven PA firing from JR EAST Train Sim HUD

Companion module that automates PA-firing in the simulator by reading JR EAST Train Simulator game's HUD via screen capture. Removes need to press PageDown manually during normal driving.

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
> **Voice:** new reference-shaped entries (schema, OCR pipeline rules, event tables, layer specs, contracts) — caveman-full voice (drop articles, fragments OK, `=` for definitional equivalence). Rationale-shaped passages ("Mental model" framings, "Why not X" framings, narrative examples) — stay normal voice. See [CLAUDE.md § Chat output style](CLAUDE.md).
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](.claude/rules/principles.md).

## Mental model

The auto-driver is an **input layer** — it observes game state via OCR on the game window, detects state transitions, and emits PA-fire events. The simulator's existing state machine (`AppState`, `_next_pa`, `state.curr_stop`) is the source of truth for *what* PA to play; the auto-driver only decides *when* to advance the queue.

This split keeps fidelity work (LCD rendering, route data, audio cuts) decoupled from input automation. The auto-driver can be disabled and the simulator behaves exactly as today, with manual PageDown control.

**Two integrations.** Both live in this repo and share OCR + state-machine implementation:

- **In-process** (`auto_input/driver.py` `AutoDriver`) — spawned from `main.py` when **OCR Auto-PA** toggle enabled on setup screen. Runs in daemon thread, sets `PASimulator.pending_next_pa = True` at fire-time, same code path as manual PageDown. Manual-press precedence implicit: driver inspects `sim.state.curr_stop` / `sim.state.cnt_pa` each cycle, skips its fire on mismatch. Includes in-window debug panel.
- **Separate-process** (`_dev_scripts/capture_game.py`) — standalone diagnostic script. Synthesizes PageDown via `keyboard` library, uses self-press timestamp guard for manual-press precedence. No debug panel.

## State machine layering

Auto-driver subsystem involves three distinct state machines. They align in normal flow but diverge after manual user action — keeping them separate in vocabulary prevents wrong fix landing in wrong layer.

### Layer 1 — App (sim's own state machine)

State on `AppState` (`curr_stop`, `cnt_pa`, `cnt_pa_at_station`, `at_station`). Exists whether auto-driver enabled or not. Three press-driven sub-states per stop: `APPROACHING_EARLY` → `APPROACHING_FINAL` → `STOPPING`. Spec in [DISPLAY.md § Unified State Machine](DISPLAY.md); mental-model summary in [CLAUDE.md § App state machine](CLAUDE.md). Auto-driver triggers transitions by setting `pending_next_pa=True`, same code path as manual PageDown.

### Layer 2 — AutoDriver belief

Per-segment flag set on `_Detector` instance: `_segment_start_stop`, `departure_observed`, `arrival_observed`, `at_station_observed`. Auto-driver's belief about which segment App layer is mid-way through and which fires it has already dispatched. Lives across samples; all flags reset on `BADGE_STOPPED→(MOVING|PASSING)` (segment boundary).

### Layer 3 — AutoDriver's inferred game state

What auto-driver thinks IRL game train is doing — expressed as one of five canonical named states + sentinel:

| Canonical name | Panel label | Game-side meaning |
|---|---|---|
| `IDLE` | Idle | At platform, no in-segment arrival was observed (boot, post-click, or arrival trigger missed by OCR). |
| `DEPARTING` | Departing | In-transit, rolling out, speed not yet >30 km/h (dep-trigger not observed). |
| `CRUISING` | Cruising | In-transit at full speed, dep-trigger observed, arr-trigger not yet observed. |
| `ARRIVING` | Arriving | In-transit, dist crossed below arrival lead (~900m), decelerating to platform. |
| `STOPPED` | Stopped | At platform, arr-trigger observed in this segment. |
| `UNKNOWN` | — | OCR FAIL or insufficient context. Sentinel. |

**2026-05-09 rename.** Old wire names embedded the detector's trigger-fire shape (`STOPPING_FRESH`, `APPROACHING_BEFORE_DEP`, `APPROACHING_AFTER_DEP`, `MOVING_AFTER_ARR`, `STOPPING_AFTER_ARR`) which leaked internal logic into the state name. New names describe what the train is *doing* in plain transit verbs and line up 1:1 with the user-facing panel labels.

**Cross-layer token sharing.** Layer 1's vocabulary (`STOPPING` / `APPROACHING_EARLY` / `APPROACHING_FINAL`) is now disjoint from Layer 3 — old suffix discipline isn't needed there. **Layer 2 ↔ Layer 3 share one token by design:** `STOPPED` is both a Layer 2 badge value (raw OCR input) and a Layer 3 inferred-state value (output). `MOVING` and `PASSING` appear only in Layer 2; `IDLE` / `DEPARTING` / `CRUISING` / `ARRIVING` / `UNKNOWN` appear only in Layer 3. The collision on `STOPPED` is intentional — the badge is one input to the inference, and at the platform with `arrival_observed=True` they collapse to the same semantic. **In code and discussion, always disambiguate by field name** (`status['badge']` vs `status['inferred_state']`) rather than by raw string match. The panel disambiguates visually too: badges render in UPPERCASE, Layer 3 states in Title Case ("Stopped").

These = **inference outputs**, not direct OCR reads. Inputs:

- **Raw OCR observations**: `badge_read ∈ {STOPPED, MOVING, PASSING}`, `speed_read`, `distance_read` — single-sample reads of game HUD.
- **Layer 2 cache** (per-segment): `departure_observed`, `arrival_observed`, `at_station_observed`. Necessary because OCR alone doesn't distinguish `DEPARTING` from `CRUISING` — both show `badge∈{MOVING,PASSING}`; cache disambiguates. Flags semantically record "we observed the trigger condition this segment," not "we dispatched a fire" — dispatcher's mismatch-skip = separate concern.

**Streaming inference truth table** (per-sample, with cache):

| `badge` | `arrival_observed` | `departure_observed` | → state |
|---|---|---|---|
| `STOPPED` | False | * | `IDLE` |
| `STOPPED` | True | * | `STOPPED` |
| `MOVING` or `PASSING` | True | * | `ARRIVING` |
| `MOVING` or `PASSING` | False | True | `CRUISING` |
| `MOVING` or `PASSING` | False | False | `DEPARTING` |
| `None` | * | * | `UNKNOWN` |

(`at_station_observed` doesn't appear — gates dispatch of FIRE_AT_STATION, not inferred state.)

**Entry-point inference** (no Layer 2 cache; toggle-ON, click reanchor): substitute `distance ≤ lead` for `arrival_observed`. `IDLE` ≡ `STOPPED` (collapsed at entry — functionally identical anchoring). `DEPARTING` lumped into `CRUISING` (brief acceleration window functionally equivalent at entry).

Inference function pluggable; future cross-attribute hardening enriches it without changing named-state vocabulary.

**Vocabulary discipline.** In design conversations and code comments:

1. **Use Layer 1 / 2 / 3 named states verbatim** — say *"AutoDriver thinks the game is in `IDLE`"*, not *"badge is STOPPED"* or any invented parallel vocabulary. Badge = one input to the inference; inferred state = what design reasons about. Vocabulary separation lets us harden inference without re-litigating design conclusions.
2. **Use arrow-flow notation for state progressions** — write `STOPPING(queue) → STOPPING(queue exhausted) → APPROACHING_EARLY`, not multi-column table. Tables fit orthogonal cross-products (Layer 3 × Layer 1 alignment table); progressions = sequence, read as arrows. Tables on transitions read as over-engineered.
3. **Don't redesign the state machine** — named states already implemented in `_Detector.update`. Design how flows interact with them, not what they should be.

### Layer interaction

Normal flow:

```
Layer 3 observation → event → Layer 2 dispatch (mismatch-skip) → pending_next_pa
                                                                    ↓
                                                         Layer 1 advance via _next_pa
```

Layer 2 follows Layer 3. Layer 1 follows Layer 2. Reverse direction — Layer 1 drifting from Layer 2 due to user action — reconciled via dispatcher mismatch-skip + flag reset on next `BADGE_STOPPED→(MOVING|PASSING)`.

### When layers diverge

| Cause | Effect | Reconciled by |
|---|---|---|
| Manual PageDown | Layer 1 advances by one press; Layer 2 unchanged | Dispatcher mismatch-skip on next event; full flag reset on next `STOPPED→(MOVING\|PASSING)` |
| Click-jump on lower LCD | Layer 1 jumps to STOPPING@target; Layer 2 unchanged | Explicit re-anchor on next capture cycle — `_reanchor_to_app` mirrors Layer 2 onto Layer 1 (`_segment_start_stop=target`, flags → parked, `prev_badge=STOPPED`, Layer 3 derives `IDLE`). Signalled by single-shot `PASimulator.click_jump_pending` (set in `_handle_lcd_click`, consumed by the driver). Parked case only; mid-transit click-jump (Layer 3 driving) not yet aligned — see WIP_autodriver.md |
| Auto-driver toggled ON mid-drive | Layer 1 = whatever user advanced to; Layer 2 has no belief yet | Entry-point flow probes Layer 3, anchors Layer 2 to match detected segment context |

Layer 3 stays accurate at all times — observes the game, not the sim. Reconciling Layer 1 ↔ Layer 2 = what mismatch-skip and entry-point flow exist to do.

## Architecture

```
[JR EAST Train Sim window — DirectX]
              │
              │ DXGI Output Duplication (dxcam) with region=profile.capture_region
              ▼
[Desktop quadrant BGRA  (1280×720 @ 1440p  |  960×540 @ 1080p)]
              │
              │ profile.hud_bbox_in_capture crop (region-relative coords)
              ▼
[HUD region  (350×480 @ 1440p  |  262×360 @ 1080p)]
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

Supported: **2560×1440** and **1920×1080**. `auto_input/driver.py` auto-detects at startup via bootstrap full-frame grab → `PROFILES[(w, h)]` → fatal if not found. `_dev_scripts/capture_game.py` does the same; `--res 1080p|1440p` overrides.

**`ResolutionProfile`** (frozen dataclass, `auto_input/hud_layout.py`) — carries all per-resolution constants: `capture_region`, `hud_bbox`, `hud_bbox_in_capture`, cell bboxes (`badge_bbox`, `distance_value_bbox`, `speed_value_bbox`, `speed_limit_value_bbox`), `templates_subdir`, `badges_subdir`, `scale`. `PROFILES` dict maps `(desktop_w, desktop_h)` → profile. Adding a new resolution = add a `ResolutionProfile` entry to `PROFILES`.

**Template strategy across resolutions:**
- **Dark digit templates** (0–9): extracted at 1440p; reused at all resolutions via NN-resize in `compare()` (template resized to match glyph at comparison time). No re-extraction per resolution.
- **Red digit templates**: resolution-specific (bolder font at different px dimensions). 1440p: `ocr_templates/digits_red/`. 1080p: `ocr_templates/1080p/digits_red/`.
- **Badge anchors**: resolution-specific (pentagon dimensions differ). 1440p: `ocr_templates/badges/`. 1080p: `ocr_templates/1080p/badges/`.

**`SegConfig`** — frozen dataclass of all segmentation thresholds (`digit_min_h`, `digit_min_w`, text-band Y bounds, gap limits, etc.). `SEG_DEFAULT` = 1440p values. `seg_for_scale(s)` returns a proportionally scaled copy. All OCR readers accept optional `seg=` param; `None` = use `SEG_DEFAULT`. Capture loops pass `seg=seg_for_scale(profile.scale)`.

## HUD layout

All bboxes = `(x, y, w, h)`. Cell bboxes = HUD-relative; HUD bbox = canonical screen-relative; capture region + HUD-in-region derived. Values below are 1440p baseline; 1080p = ×0.75 rounded. Live in `PROFILE_1920_1080` / `PROFILE_2560_1440` in `auto_input/hud_layout.py`. The flat constants below are backward-compat (consumed by `*_from_surface` dev-tool helpers + calibration extractor).

| Constant | Value | Notes |
|---|---|---|
| `CAPTURE_REGION_2560_1440` | `(1280, 0, 2560, 720)` | dxcam region= signature (left, top, right, bottom). Top-right quadrant of desktop. Production grab path; cuts capture work ~75% vs full-desktop |
| `HUD_BBOX` | `(2200, 20, 350, 480)` | Canonical screen-relative position. Consumed by `*_from_surface` helpers (1b dev tool) + calibration extractor |
| `HUD_BBOX_IN_CAPTURE` | `(920, 20, 350, 480)` | Derived: `HUD_BBOX` minus `CAPTURE_REGION_2560_1440` origin. Consumed by production `_crop_cell` against region-grabbed frame |
| `DISTANCE_VALUE_BBOX` | `(120, 314, 230, 55)` | Right side of "Distance" / "残距離" row (shared with stopping-offset) |
| `SPEED_VALUE_BBOX` | `(120, 165, 230, 55)` | Right side of "Speed" / "速度" row |
| `SPEED_LIMIT_VALUE_BBOX` | `(120, 215, 230, 55)` | Right side of "Speed Limit" / "最高速度" row — red digits, line-dependent |
| `BADGE_BBOX` | `(29, 122, 111, 40)` | Green/blue pentagon — left + top scenery bleed trimmed |

Position invariant across language modes (EN/JA), game states (running/stopped/at-platform), and scenes — verified against 7 reference screenshots.

**Resolution gate.** Production AutoDriver runs a bootstrap full-frame `camera.grab()` at startup → probes `(w, h)` → `PROFILES.get((w, h))` → fatal if not found. Prevents OCR running with wrong-resolution bboxes / templates. Sibling to other fail-loud invariants in [critical_lessons.md](.claude/rules/critical_lessons.md).

## Capture: dxcam (DXGI Output Duplication)

**Why not Win32 PrintWindow or BitBlt-from-desktop:** the game renders via DirectX, and the swap chain isn't visible to GDI. Both APIs return all-black frames even with `PW_RENDERFULLCONTENT` flag set. **dxcam** uses DXGI Output Duplication (the same GPU-level capture API used by Discord/OBS), reading the GPU framebuffer directly.

```python
import dxcam
from auto_input.hud_layout import PROFILES
profile = PROFILES[(desktop_w, desktop_h)]  # resolved at startup from bootstrap grab
camera = dxcam.create(output_color="BGRA")  # native, skips cv2 conversion
frame = camera.grab(region=profile.capture_region)  # right-half quadrant, resolution-dependent
```

Notes:
- BGRA output = DXGI's native format; choosing it avoids requiring opencv as dep
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

Text band excludes HUD's top/bottom borders and any scenery bleed-through near cell edges.

### Stage 2 — filtering

Three filters in sequence:

1. **Digit-shape filter**: keep only bboxes with `h ≥ 22` and `7 ≤ w ≤ 30`. Drops 'm' suffix strokes (h≈10), label tail fragments, scenery blobs.
2. **Decimal-stop** (speed only): scan raw bboxes for small bbox (`h ≤ 10, w ≤ 7`) in bottom half of text band — that's the decimal point. Stop accepting digits at its x-position. **Robust against gap variance**; replaces gap-based heuristic that was failing on `1x.x` and `11x.x`.
3. **Gap-stop** (safety net): stop accepting digits at first horizontal gap greater than `MAX_GAP`. Distance: 20 (anything past 'm' has bigger gap). Speed: 25 (relaxed because decimal-stop = primary boundary; 25 catches scenery blobs but lets through wide kerning like '1' to '1' which can be 18px).

### Stage 3 — template matching

Templates: 10 binary glyphs (digits 0-9) extracted from labeled reference screenshots via `KNOWN_VALUES` dict in `auto_input/ocr.py`.

Matching: each segmented bbox's binary glyph padded to size of template, then compared pixel-equality. Score = fraction of matching pixels (0.5 = random for binary). Best-scoring template wins per glyph; concatenate to integer.

Live scores observed: 0.75–1.00. Below 0.6 = danger zone (random match territory).

### Tunable constants (in `auto_input/ocr.py`)

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

These are fields on `SegConfig` (frozen dataclass, `auto_input/ocr.py`). `SEG_DEFAULT` uses the 1440p values above. `seg_for_scale(s)` scales all pixel-threshold fields proportionally — pass the result as `seg=` to any OCR reader to run at a different resolution.

## Stopping offset (cm) — shared distance cell

`DISTANCE_VALUE_BBOX` cell is content-shared and self-identifies via color:

- **Dark text `Nm`** — distance to next stopping station. Shown during transit, AND at the platform after the cm display dismisses (~5s post-arrival).
- **Green text `±Ncm`** — stopping offset from the platform's stop mark. Shown briefly after `MOVING→STOPPED` (~5s window). Sign shown only for negative (train stopped past the mark); `0` and positives omit the sign character.

Both readers run unconditionally each capture cycle. Their masks are mutually exclusive (`gray < 70` for m-distance, `(G - max(R,B)) > 30` for cm-offset), so at most one returns non-None per frame. JSONL records both fields each sample; display priority gives cm precedence (transient signal of interest), falls through to m otherwise.

Two pipeline differences in `read_stopping_offset` vs `read_distance`:
- **Color mask** as above.
- **Sign detection**: small bbox (h ≤ 12, w ≤ 18) in vertical center of text band, left of first digit, treated as leading minus. No `+` glyph template — positive case has no sign character at all.

`cm` suffix = same green color but smaller than digits, excluded by existing `DIGIT_MIN_H=22` shape filter. Digit templates reused unchanged — binarization is colour-agnostic, shape matches dark-text version.

**Overrun semantics.** The game prevents the user from physically stopping in the red-text zone — overrun → game resets the train to `0cm`, briefly shows it, then black-screens to fast-forward past to the next station. Red text is unreachable in normal play. The "no cm reading" state at STOPPED is the normal post-display-dismissal state, **not** an out-of-bound signal — interpreting overrun requires examining the surrounding badge transitions and the brief `0cm` read, not a single null cm sample.

## Speed limit (最高速度) — red digits

Cell at `SPEED_LIMIT_VALUE_BBOX`, between speed and distance rows. Red digits + dark `km/h` suffix. **Line-dependent** — many lines don't post a cab speed limit; empty cell = normal "no posted limit" state, not OCR fault. `read_speed_limit` returns `None` for those frames; speed limits always in 5/10 km/h increments when present (5, 10, …, 75, 95, 110, 120).

Reader uses `(R - max(G,B)) > RED_TEXT_DELTA` as color mask — dark `km/h` suffix excluded automatically. Three complications the reader handles:

- **Tight kerning glues digit pairs** — at 80, 90, 110 the column-density threshold never drops below `COLUMN_TEXT_MIN` between digit pairs (typically ?-`0`), so segmentation sees one over-wide run instead of two digits. `segment_red_digits` supports two split strategies:
  - **`argmin` (default)**: find deepest column-density valley and split there, recursively until each sub-bbox fits `DIGIT_MAX_W`. Precise for cases with clear inter-digit dip.
  - **`equal_width` (fallback)**: divide each over-wide run into N equal parts where N = round(width / 18). Ignores column density entirely. Robust to cases where `0`-shaped digits' natural hollows look deeper than actual digit boundary (limit_100's `0+0` merged blob).
  `read_speed_limit` runs `argmin` first; if grammar-valid AND `min_score >= ARGMIN_TRUST_SCORE` (0.85, in `ocr.py`), return immediately. Otherwise — argmin grammar-invalid OR low-confidence valid — also runs `equal_width` and prefers its grammar-valid result. Threshold gates against argmin's `0+0` misread mode where split lands inside a digit hollow and produces a confident-but-wrong grammar-valid read; equal_width's symmetric split repairs it (calibrated against 31-frame `100` corpus — low band 0.65-0.66, high band 0.92+).
- **Stroke-weight mismatch** — red font is bolder than dark-text font the original digit templates were extracted from, so dark templates alone consistently mismatch certain digit pairs (8 / 6 misread as 4). Two-tier matching: (a) red-text digit templates extracted from limit screenshots into `ocr_templates/digits_red/` (one PNG per digit, full 0–9 coverage as of 2026-05-09); (b) dark templates dilated by `SPEED_LIMIT_TEMPLATE_DILATION` (3 px) as fallback for any digit without a red template. Best-of-both score wins per glyph. Re-extract via `_dev_scripts/extract_ocr_assets.py` after adding new `_ocr_calibration/limit_*.png` reference screenshots.
- **Domain validation** — observed range in JR EAST Train Sim Real is 25–130 km/h in 5/10 km/h increments. Reader validates final integer against `VALID_SPEED_LIMITS = {25, 30, 35, …, 130}` and returns `None` on out-of-grammar reads. Catches fallout of split contamination (e.g. 110 occasionally read as 114 because `0`'s left curve bleeds into `1`'s split bbox), single-digit corruptions (90 sometimes read as 1), and any future misclassification mode that produces a non-grammar value. Better to return `None` and miss a frame than write a wrong value to JSONL.

**Debugging misreads.** Live-frame OCR misreads don't round-trip cleanly through pipeline: dxcam BGRA frame and `pygame.image.save`'d PNG of same instant can produce different `segment_red_digits` bboxes via sub-pixel column-density variance. A live `100`→`110` misread may replay to `100`→`160` on saved PNG (grammar-fail → equal_width fallback → correct), masking original mode. To collect a usable corpus, AutoDriver dumps `sl_cell` to `_ocr_calibration/_misread_dumps/sl_<ts_ms>_score<NN>_read<NNN>.png` whenever a grammar-valid `speed_limit` read scores below `SUSPICIOUS_SPEED_LIMIT_SCORE` (0.75, in `auto_input/driver.py`); `ts_ms = int(ts * 1000)` matches JSONL row.

## Badge classification (state cell)

Game shows pentagon badge in next-station row, with text inside:

| State | EN text | JA text | Color | Meaning |
|---|---|---|---|---|
| MOVING | "Next" | "次停車駅" | green | Train heading to next stopping station (badge displays target) |
| STOPPED | "Stopping at" | "停車中" | green | Train at platform |
| PASSING | "Pass" | "通過" | **blue** | Train crossing a station that won't be stopped at; badge still displays the next *stopping* station, but **HUD distance is to the passing station, not the stopping target** |

**Critical observations:**
- Pentagon shape **identical** across all three states — only text content + fill colour differ.
- MOVING and STOPPED both use same green pentagon; pixel-diff against text-content anchors discriminates them.
- PASSING's blue fill gives classifier wide separation margin: cross-state mean diff to MOVING/STOPPED ≈ 43, vs within-state ~6–10.
- **STOPPED is canonical, never transient.** Game only shows STOPPED badge when train is actually stopped within platform's stopping range OR when game has reset train to a platform. NEVER flickers STOPPED briefly during deceleration or overrun. Detector logic relies on this: single STOPPED frame sufficient to flip `at_station_observed=True`, no debouncing or N-frame consensus needed. Also rules out recurrence-shape hypothesis ("brief STOPPED reading during overrun resets atstn_obs from prior segment") — that scenario can't happen by game design.

### Classifier

Pixel-diff against 6 anchor templates:

```python
BADGE_ANCHOR_FILES = {
    "MOVING":  ["running_en",  "running_ja"],
    "STOPPED": ["stopping_en", "stopping_next_station", "stopping_ja"],  # stopping_ja = 1080p alt
    "PASSING": ["passing_en",  "passing_jp",            "passing_ja"],   # passing_ja  = 1080p alt
}
```

`load_badge_anchors(badges_dir)` silently skips missing files — each resolution dir loads its own 6 available crops. 1440p dir has the original 6 stems; 1080p dir has `stopping_ja` + `passing_ja` in place of `stopping_next_station` + `passing_jp`.

Per frame: crop badge cell, compute mean-abs-diff against each anchor, pick state with lowest-diff anchor. Language-agnostic — whichever anchor matches best determines state, regardless of which language user plays in.

Diff < 15 = high confidence; real reads sit there. Diff > `BADGE_DIFF_REJECT` (50) rejected at classifier — `classify_badge_state` returns `(None, diff)` so detector treats it as OCR FAIL. Black-screen / dark-cell garbage frames diff 60-110; mid-animation transient spikes at exact transitions hit >70. 50 cleanly separates real from garbage with margin on both sides. Detector's `None` tolerance preserves `prev_badge` across rejected frames, so one-cycle delay on transition detection = only cost.

## State machine — `PaEventDetector`

Lives in `_dev_scripts/capture_game.py` (1b) + `auto_input/driver.py` `_Detector` (1a, kept in sync). Tracks distance + speed + badge across samples, emits PA-fire event names on transitions.

### State vocabulary

State machine works in Layer 3 named-state vocabulary — see "State machine layering" above for canonical names + inference truth table. The 5 states (`IDLE`, `DEPARTING`, `CRUISING`, `ARRIVING`, `STOPPED`) + `UNKNOWN` sentinel describe autodriver's inferred view of where IRL game train is in its segment cycle. They map onto per-sample event emissions below.

**When designing flows that interact with the state machine** (entry-point, resync, click-to-jump): say *"AutoDriver thinks the game is in `IDLE`"*, not *"badge is STOPPED."* The badge is one input to the inference; the inferred state is what the design reasons about. The separation matters for hardening — and avoids design conclusions accidentally over-trusting a single OCR attribute.

### Events

| Event | Trigger | Effect |
|---|---|---|
| `BADGE_STOPPED→MOVING` | badge transition | New segment begins; reset all three observed-flags + segment_start_ts |
| `BADGE_MOVING→STOPPED` | badge transition | Train just arrived at platform (logged only — see `FIRE_AT_STATION`) |
| `SPEED_UP_30` | speed crossed 30 km/h upward AND `departure_observed=False` | Fire departure PA, set `departure_observed=True` |
| `DIST_DOWN_<lead>` | `badge==MOVING` AND `distance ≤ arrival_lead_m` AND `arrival_observed=False` | Fire arrival PA, set `arrival_observed=True` |
| `FIRE_AT_STATION` | `badge==STOPPED` AND `arrival_observed=True` AND `at_station_observed=False` | Fire silent press that flips sim into STOPPING (sets `state.at_station=True`); set `at_station_observed=True` |

`arrival_lead_m` defaults to **900m**. For 1a, adjust on setup-screen Lead stepper (range 500–1500, ±100m) before launching. For 1b, override with `--lead` on `_dev_scripts/capture_game.py` invocation. Use 1200m for transfer-heavy lines (Tokyo, Shinjuku scenarios).

**Per-segment observed flags** prevent double-firing within a single segment when OCR misreads transiently flip a threshold-crossing condition (e.g. speed misread as `7` between two real `>30` reads would fire `SPEED_UP_30` twice without the flag). All three flags (`departure_observed`, `arrival_observed`, `at_station_observed`) reset on `BADGE_STOPPED→MOVING`. PASSING transitions do NOT reset flags — PASSING = transient sub-state of MOVING within a segment, not new segment.

**`at_station_observed` gated on `arrival_observed`** so it only triggers in this segment's stopping moment. Without that gate, level test would fire on first capture cycle (train parked at session start with `badge==STOPPED`) and desync simulator before first real drive begins. Pa-empty stops still get the at-station fire — `_fire_at_station` accepts `pa==[]` because APPROACHING→STOPPING transition silent regardless of pa contents.

### Arrival is a level test, not a downward crossing

Arrival trigger fires whenever `badge==MOVING AND distance ≤ arrival_lead_m`, gated by per-segment `arrival_observed` flag. Does **not** require downward-crossing of threshold.

This matters because of PASSING. While badge reads PASSING, HUD distance is to the passing-through station (NOT to next stopping target). Detector ignores those samples entirely:

- **Arrival check gated on `badge==MOVING`** — PASSING-relative sample at, say, 300m to passing station doesn't trigger arrival for actual stopping station that's still 1500m away.
- **`prev_distance` no longer tracked** — level test doesn't need it. Old downward-crossing test (`prev > lead >= curr`) couldn't handle case where `PASSING→MOVING` resumed with distance already < lead (first MOVING sample's distance jumps *up* relative to PASSING-relative prev, defeating the crossing check). Level test handles it cleanly: any MOVING sample with `distance ≤ lead` fires arrival, exactly once per segment.

Speed/departure logic unchanged — speed = own-train and badge-independent.

**Manual-press precedence.** When a `fire ... PA` event would auto-send PageDown, dispatcher first checks `keys.last_user_pagedown_ts > detector.segment_start_ts`. If user already pressed PageDown manually since segment began, auto-fire skipped (logged as `SKIPPED auto-fire (user already pressed ...)`). This means: pressing PageDown manually always wins; auto-driver fills in only where you didn't.

**Self-press guard.** `keyboard.on_press_key` global hook fires on ALL PageDown events including synthetic ones we send. Within `SELF_PRESS_GUARD_S` (500ms) of an auto-send, key callbacks ignore press as our own. Prevents self-detection that would mark segment as "user already pressed".

`None` values for distance/speed/badge tolerated individually — OCR FAIL frames don't reset state, so transient unreadable frames don't break segment continuity.

**Cross-attribute reject (black-screen guard).** When `prev_badge == "STOPPED"` and new badge would transition to `MOVING` or `PASSING`, transition rejected (badge forced to `None`) unless `speed > 0`. The game black-screens briefly to fast-forward simulated time, but only while parked at a platform — never mid-transit. During that window the badge cell goes uniform-dark and the classifier picks whichever anchor pixel-diffs lowest (typically PASSING — blue is closer to black than green); the distance cell drops out consistently while the speed cell sometimes survives showing the parked-at-platform `0`. The structural rule exploits that asymmetry: a real platform departure always shows speed climbing from 0 (the game can't fake movement without rendering it), so `speed == 0` or `speed is None` at a STOPPED→moving transition is the black-screen signature. Without this the spurious PASSING fires a phantom `STOPPED→PASSING` and resets the observed-flags as if a new segment began. First concrete instance of the cross-attribute hardening philosophy ([TODO.md § Auto-input/OCR](TODO.md)).

## Debug panel (in-process integration only)

When OCR Auto-PA enabled at setup screen, `PASimulator` allocates extra `DEBUG_PANEL_HEIGHT = 80` row above LCD via pygame sub-surfaces. Window becomes 730×500 instead of 730×420; LCD code **completely unchanged** because it gets sub-surface positioned at `(0, 80)` and thinks it's drawing to a regular 730×420 screen.

**Strict separation per user requirement:** panel render logic lives entirely in `auto_input/driver.py` (function `draw_debug_panel`). `app.py`'s `_render_panel()` helper just hands sub-surface to auto-input module. Simulator **doesn't know** how panel renders — colors, layout, fonts, text — all owned by `auto_input/driver.py`. Zero `displays/` imports in panel render code.

Panel and LCD never overlap render areas. Panel uses its own background color `_PANEL_BG = (18, 22, 28)` (visually distinct from LCD's `DARK_BG`).

### Layout

3 lines, font ShinGoPr6N-Medium @ 14pt (loaded lazily, supports both Latin + CJK so station names in state line render correctly):

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

`dep✓ arr·` flags reflect `auto_input_status["departure_observed"]` and `auto_input_status["arrival_observed"]` — per-segment observed flags reset on `BADGE_STOPPED→MOVING` transitions.

State line uses simulator's `state.curr_stop` + captured `segment_start_stop` to display "between A → B" or "stopped at A".

### Width adaptivity

Panel uses whatever surface width the caller provides (`PASimulator` allocates the sub-surface at `S_WIDTH` from the active train model). When future train models with different LCD widths are added, panel follows automatically.

### Status dict (single-writer / single-reader, atomic dict assignment)

`AutoDriver` thread populates `sim.auto_input_status` after each capture:

```python
{
    "badge": "MOVING" | "STOPPED" | "PASSING" | None,
    "badge_diff": float | None,            # template-match diff (lower = better)
    "speed": int | None,                   # km/h, integer (decimal stripped)
    "speed_score": float,                  # OCR confidence 0..1
    "distance": int | None,                # meters to next stop
    "distance_score": float,
    "stopping_offset_cm": int | None,      # cm offset at platform (briefly populated post-arrival)
    "stopping_offset_score": float,
    "speed_limit": int | None,             # km/h speed limit (line-dependent, often empty)
    "speed_limit_score": float,
    "segment_start_stop": int,             # sim.state.curr_stop snapshot at last STOPPED→MOVING
    "departure_observed": bool,
    "arrival_observed": bool,
    "at_station_observed": bool,
    "inferred_state": str,                 # canonical Layer 3 state name (see § "Layer 3" truth table)
    "ts": float,                           # time.time() of capture
    "paused": bool,                        # True when the user has clicked Pause (capture loop idle)
    "last_fire": dict | None,              # {"ts": float, "type": "departure"|"arrival"|"at-station"} — most recent successful auto-fire; panel renders a transient chip when ts is recent
}
```

**Paused-frame variant.** During paused cycles loop preserves prior status dict and overlays only `"paused": True` (no fresh OCR fields). Readers should treat any field that's stale-looking against `paused=True` accordingly.

CPython dict assignment is atomic. No lock needed for single writer (BG thread) + single reader (main thread).

## Sample interval

**5 seconds.** Trade-off:

- **Tighter** would catch threshold crossings more precisely but burns more CPU and could flood logs with redundant identical reads
- **Wider** would miss events; at 100 km/h train moves ~140m in 5s, so wider sample could miss 900m threshold entirely

5s = good balance for both threshold detection and event cadence.

State machine robust to granularity — `prev_<X>` carries forward between samples, threshold-crossings fire on first sample after boundary crossed.

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

# Force resolution (default = auto-detect from first frame)
uv run python _dev_scripts/capture_game.py --res 1080p
```

**Offline calibration validation** (no live game required):

```bash
uv run python _dev_scripts/validate_ocr.py           # default: 1080p
uv run python _dev_scripts/validate_ocr.py --res 1440p
```

Stop with Ctrl+C. Script prints one line per sample (badge state, speed, distance, scores) plus indented `>>>` lines for state-machine events and auto/manual key activity.

## Files

| Path | Role |
|---|---|
| `auto_input/` | Package — public surface re-exports `AutoDriver`, `draw_debug_panel`, `handle_panel_click` from `__init__.py`. Internal submodules below. |
| `auto_input/driver.py` | **Primary** — `AutoDriver` class (in-process daemon thread) + `draw_debug_panel()` (panel render) + `_Detector` state machine + `handle_panel_click()` dispatcher (in-panel buttons, currently the Report download). All auto-input logic lives here. |
| `auto_input/hud_layout.py` | HUD + cell bbox constants for 2560×1440 (canonical desktop coords + region-cut derived coords) |
| `auto_input/ocr.py` | OCR pipeline + badge classifier; runnable for offline validation (`uv run python -m auto_input.ocr`) |
| `main.py` | Reads `auto_input` / `lead_m` / `interval_s` from setup-screen config dict. Spawns `AutoDriver` when `auto_input=True` and passes same flag to `PASimulator`. |
| `setup.py` | OCR Auto-PA toggle pill + Lead/Interval steppers under route list. `_handle_band_click` updates state; selected route's Enter returns config dict including auto-input fields. |
| `app.py` | `PASimulator`: allocates debug sub-surface in `_init_pygame`; `pending_next_pa` flag checked alongside keyboard in `_handle_input_main`; `auto_input_status` dict written by AutoDriver, read by `_render_panel()` which delegates to `auto_input.draw_debug_panel`. `MOUSEBUTTONDOWN` events landing in panel area get forwarded to `auto_input.handle_panel_click`. `drive_log_path` attribute stashes live JSONL path so Report button can find it. **No panel rendering logic lives in app.py.** |
| `constants.py` | `DEBUG_PANEL_HEIGHT = 80` |
| `_dev_scripts/capture_game.py` | Standalone observation/debug script (separate process, synthetic keystrokes, optional `--route` flag for PA-count check) |
| `_dev_scripts/test_dxcam.py` | Diagnostic — full-desktop dxcam capture + brightness check |
| `ocr_templates/digits/*.png` | **Runtime input** — 10 pre-extracted digit glyphs (~20×30 binary PNGs). Loaded by `build_templates()`. Reused at all resolutions via NN-resize. Committed. |
| `ocr_templates/digits_red/*.png` | **Runtime input** — 10 red-font digit glyphs (1440p). Loaded by `build_templates(red_dir)`. Committed. |
| `ocr_templates/badges/*.png` | **Runtime input** — 6 badge cell crops (111×40 RGB, 1440p). Loaded by `load_badge_anchors()`. Committed. |
| `ocr_templates/1080p/digits_red/*.png` | **Runtime input** — 10 red-font digit glyphs (1080p, ~14×20 px). Committed. |
| `ocr_templates/1080p/badges/*.png` | **Runtime input** — 6 badge cell crops (83×30 RGB, 1080p). Committed. |
| `_ocr_calibration/*.png` | **Local-only** 1440p source screenshots (~33 MB). Gitignored. Source for `extract_ocr_assets.py`. |
| `_ocr_calibration_1080p/*.png` | **Local-only** 1080p source screenshots. Gitignored. Source for 1080p extraction passes. |
| `_dev_scripts/extract_ocr_assets.py` | One-shot extractor: reads `_ocr_calibration*/` → writes `ocr_templates/`. Run after re-capturing sources, then commit diff. |
| `_dev_scripts/validate_ocr.py` | Offline validation: badge + speed-limit + stopping-offset reads against labeled calibration screenshots. `--res 1080p\|1440p`. All tests PASS before deploying at that resolution. |
| `_recordings/drive_<line>_<diagram>_<TS>.jsonl` | **Blackbox / drive recorder log** — one file per AutoDriver lifetime. Line 0 = `_type: "meta"` (route/diagram/dest/stops); subsequent lines mix `_type: "event"` (badge transitions: arrival / departure / passing_start / passing_end) and `_type: "sample"` (one OCR cycle, ~5s, all OCR fields + sim state including `at_station` / `cnt_pa_at_station` / `at_station_observed` / `inferred_state` / `segment_start_stop`). Written inside `auto_input/driver.py`'s capture loop with per-line `flush()` for crash safety. Local-only / gitignored. Field additions backward-compatible (plot_drive ignores unknowns); field removals or renames require coordinated update with `plot_drive.py`. |
| `_experiments/live_captures/` | Saved HUD crops from prior live testing (gitignored — `_experiments/` itself = artifact-only folder; OCR + layout modules now bundled into `auto_input/` package) |
| `fonts/ShinGoPr6N-Medium.otf` | Latin + CJK font used by debug panel for station names |

## Recalibration for a new resolution

1. Capture native screenshots at target resolution — same content states as existing `_ocr_calibration/` set (running_en/ja, stopping_en/ja, passing_en/ja, all `limit_*`, `stopping_position`).
2. Add a `ResolutionProfile` to `auto_input/hud_layout.py` with scaled `hud_bbox` + cell bboxes; add to `PROFILES`. `_scale_bbox(bbox, s)` helper scales the 1440p reference.
3. Save source screenshots to `_ocr_calibration_<res>/` (gitignored parallel dir).
4. Add `BADGE_ANCHOR_FILES_<res>` + `KNOWN_LIMIT_VALUES_<res>` to `_dev_scripts/extract_ocr_assets.py`; add extraction passes in `main()` for the new resolution.
5. Run `uv run python _dev_scripts/extract_ocr_assets.py` → produces `ocr_templates/<res>/badges/` + `ocr_templates/<res>/digits_red/`. **Dark digit templates are not re-extracted** — `compare()` NN-resizes 1440p templates to match glyph size at runtime.
6. Run `uv run python _dev_scripts/validate_ocr.py --res <res>` (after adding the resolution's ground-truth to `CAL_DATA`). All tests should PASS before committing.
7. Commit the `ocr_templates/<res>/` diff.

## Limitations

- **Supported resolutions**: 2560×1440 and 1920×1080. Adding new resolutions = `ResolutionProfile` entry + template extraction + validation. See "Recalibration".
- **Game must be visible**: HUD area (top-right) must not be covered.
- **Game must be actively rendering**: minimized/alt-tabbed games may stop rendering and produce stale captures.
- **Scenery bleed**: HUD background is semi-transparent; very dark scenery behind reduces match scores (still reads correctly above ~0.7).
- **No station-name OCR**: auto-driver doesn't validate which station the user is at; trusts simulator's `state.curr_stop`. If they desync, manual PageDown is the recovery.
- **Game DRM**: irrelevant to the OCR pipeline (works on legit + cracked installs identically since dxcam reads GPU output regardless of game's startup path).

Pending design (entry-point flow), validation history, calibration insights / guardrails, and priority-ordered backlog all live in [WIP_autodriver.md](WIP_autodriver.md).

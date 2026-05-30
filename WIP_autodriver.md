# WIP — Auto-driver (pending design + history)

Working notes for the auto-input subsystem. Current-state facts live in [auto_input/README.md](auto_input/README.md). This doc holds:

- **Pending design** — entry-point flow + Layer 1 silent-advance, yet to be implemented.
- **Validation history** — chronological record of live + offline validation milestones.
- **Calibration insights** — rationale and "we tried X, settled on Y" guardrails.
- **Future enhancements** — priority-ordered backlog.

Click-jump on the lower LCD shipped 2026-04-29 (App-state side). The autodriver re-anchor (Layer 2 → Layer 1) shipped 2026-05-30 for the **parked case** — see "Click-jump entry-point" below. Mid-transit click-jump (Layer 3 driving at re-anchor time) still pending.

---

## Pending — Entry-point flow

The autodriver needs a single procedure for state reconciliation, used at:

- AutoDriver toggle ON.
- After click-jump (sim's `curr_stop` changed authoritatively from a click).
- After manual PageDown drift the autodriver didn't initiate.

### Two triggers, two procedures

**Click-jump entry-point** (App-authoritative — click is user intent):

- Skip Layer 3 probe entirely.
- Anchor Layer 2 to App: `_segment_start_stop = App.curr_stop`, `departure_observed = arrival_observed = False`, `at_station_observed = True` (suppresses immediate FIRE_AT_STATION).
- No App alignment (App was just authoritatively set by `jump_to_stop`).

✅ **Shipped 2026-05-30 (parked case).** `AutoDriver._reanchor_to_app` does exactly the anchor above, plus `prev_badge="STOPPED"` (Layer 3 → IDLE) and `prev_speed=None` (drop stale speed so a transient parked-platform speed misread can't satisfy the departure crossing test on the first post-jump cycle). Signalled by single-shot `PASimulator.click_jump_pending` (set in `_handle_lcd_click`, consumed at the top of the capture loop before the OCR grab so `prev_badge` is in place for the same cycle's `detector.update`).

⚠️ **Deferred — mid-transit click-jump.** The parked anchor assumes the game train is at a platform when the user clicks (the realistic desync-correction case). If the user click-jumps while the game is driving (Layer 3 `DEPARTING`/`CRUISING`/`ARRIVING`), the parked anchor mis-advances — `prev_badge="STOPPED"` + the next MOVING read fires a phantom `STOPPED→MOVING` departure from `target`. Needs the alignment rule below (advance App silently by one), same machinery as the toggle-ON flow. Won't crash; just mis-fires.

**Toggle-ON entry-point** (game-authoritative for App alignment):

- Mute fires.
- Probe Layer 3 with sliding-window consensus (probe 3 must agree with probe 2; stale probes discarded).
- Apply alignment rule (below).
- Anchor Layer 2 per inferred state.
- Resume normal event flow.

### Alignment rule (shape resolved; mechanism TBD)

Align ONLY when game is in-transit AND `App.at_station=True` (advance App by one stop). Otherwise no-op. Lockstep ±1 stop assumption stands.

| Layer 3 inferred state | App.at_station | Action |
|---|---|---|
| `IDLE` / `STOPPED` | * | no-op |
| `CRUISING` (absorbs `DEPARTING` at entry) | True | advance App: land at APPROACHING_EARLY of curr_stop+1 (silent — no audio) |
| `CRUISING` | False | no-op |
| `ARRIVING` | True | advance App: land at APPROACHING_FINAL of curr_stop+1 (silent — no audio) |
| `ARRIVING` | False | no-op |

### `jump_to_stop` is single-purpose

`jump_to_stop` lands `STOPPING@target` only. It is NOT the right tool for the silent advance — never extend it with `APPROACHING_*` variants. The mechanism for the two "advance App" rows is **TBD**, to be designed alongside Layer 1 work. Candidate mechanisms (NOT pre-committed):

- A separate, narrow autodriver-only helper on `PASimulator` that sets `at_station=False` + `cnt_pa` directly without audio.
- Reuse `pending_next_pa` to fire the natural advance, accepting audio replay (probably wrong UX).
- Something else — App-layer side will inform the choice.

### Detection of "unexpected curr_stop change"

AutoDriver tracks last-known `curr_stop`. If it differs from current and the change wasn't from its own `pending_next_pa` fire, invoke the entry point. Confirm at resume.

### Resolved Qs (from previous design sessions)

- **`DEPARTING` dep-PA loss at entry**: lumped into `CRUISING`. Accepted: dep PA is structurally unrecoverable mid-segment.
- **`CRUISING` vs `ARRIVING` disambiguation**: distinguish via distance — `distance ≤ lead → ARRIVING`.
- **Probe consensus**: sliding window — probe 3 must agree with probe 2; stale probes discarded.
- **PASSING vs MOVING anchor**: same anchor. PASSING-specific gating happens in normal event flow afterward, not at anchor time.

---

## Validation history

- **2026-04-26 evening (Phase 1)**: dxcam capture pipeline; distance OCR (HUD bbox calibration, digit segmentation, template matching, scenery-bleed handling, gap filter, m-stroke filter); validated against 6 reference screenshots + live drive (24 distance reads through one full station segment, all correct).
- **2026-04-26 evening (Phase 2)**: speed OCR (decimal-place stripping, gap tuning); badge classifier (4-anchor pixel-diff); event state machine with per-segment observed-flags; validated against multi-station live drive (2 segments, all transitions detected correctly).
- **2026-04-26 late evening (Phase 3)**: speed OCR robustness — decimal-point detection (replaces gap heuristic for boundary), gap relaxation for narrow-digit kerning; validated on 17 live frames spanning 0–120+ km/h.
- **2026-04-27 (Phase 4)**: PASSING badge added (rapid-service "Pass" / "通過" blue pentagon); classifier expanded from 4 to 6 anchors. Arrival logic switched from downward-crossing to level test gated on `badge==MOVING` so post-PASSING under-threshold cases fire correctly. OCR + layout modules promoted from `_experiments/` to project root. Auto-input toggle + Lead/Interval steppers moved from CLI flags to setup screen. Offline OCR validation 6/6 PASS; detector scenarios cover normal segment, mid-segment PASSING, post-PASSING already-under-threshold, double-fire prevention, STOPPED gate.
- **2026-04-27 evening (1b live)**: 1b (separate-process, `_dev_scripts/capture_game.py`) on Keihin-Tōhoku 727B Omiya→Kanda full route — flawless.
- **2026-04-27 evening (1a live)**: 1a (in-process) live-validated on Keiyo 780Y_1510Y 蘇我→東京 (765 samples). Surfaced detector bug — `STOPPED→PASSING` didn't reset flags; PA fires suppressed on Keiyo's 千葉みなと→稲毛海岸 PASSING-through-freight-terminal leg. Fixed in commit `8ac2b67` (symmetric reset on `STOPPED→(MOVING|PASSING)`).
- **2026-04-28**: STOPPING badge-state hook landed — display + state-machine (`b9fe153`); autodriver `_fire_at_station` via `pending_next_pa` reuse (`8ef2eba`). Drive-recorder JSONL streaming logger (`5039d24`); Report button + plot generator HTML (`5e86d25`).
- **2026-04-29**: Layer 2 cache rename `*_fired` → `*_observed`; `_Detector.inferred_state()` accessor extracted; `inferred_state` surfaced in status dict + JSONL drive log + debug panel.
- **2026-05-08**: cross-attribute hardening (`7fa9242`) — black-screen guard (`prev_badge=STOPPED + speed=0|None` forces `badge=None`), cm stopping-offset reader, speed-limit reader (red-digit OCR). Silent `pa_at_station` drain at FIRE_DEPARTURE (`b95e7b1`).
- **2026-05-09**: Layer 3 vocabulary renamed (`STOPPING_FRESH / STOPPING_AFTER_ARR / APPROACHING_BEFORE_DEP / APPROACHING_AFTER_DEP / MOVING_AFTER_ARR` → `IDLE / STOPPED / DEPARTING / CRUISING / ARRIVING`) per commit `0190983`; debug-panel redesign same commit. Single-shot signal-flag consumption fix in `app.py` — gate `pending_next_pa` reset on `not is_pa_playing()` so at-station auto-fire isn't dropped when arrival PA still playing (see [critical_lessons.md § "Single-shot signal flags"](.claude/rules/critical_lessons.md)).
- **2026-05-30**: Click-jump re-anchor (parked case) shipped — `AutoDriver._reanchor_to_app` mirrors Layer 2 onto Layer 1's authoritative `STOPPING@target` after a lower-LCD click; signalled by single-shot `PASimulator.click_jump_pending`. Live-drive validated. Mid-transit click-jump deferred (see "Click-jump entry-point").

## Calibration insights (rationale / guardrails)

- **PrintWindow returns black for DirectX games.** Even with `PW_RENDERFULLCONTENT`. Same for BitBlt-from-desktop. dxcam (DXGI Output Duplication) is the only path that works reliably. Don't simplify to PrintWindow.
- **`output_color="BGRA"`** in dxcam is native; `"RGB"` requires opencv-python.
- **Set DPI awareness** before any window measurement: `ctypes.windll.shcore.SetProcessDpiAwareness(2)`. At 2560×1440 + DPI scaling, omitting this misaligns coordinates.
- **HUD text varies in pixel-population** by anti-aliasing. Fixed binarization threshold (70) is more stable than Otsu, which gets confused by 3-population distributions (text + bg + scenery bleed-through).
- **Decimal point detection by shape** (small bbox in bottom half of text band) is more robust than gap-based heuristics. Speed values like `110.7` have inter-`1` gaps of ~18px, exceeding any reasonable digit-gap threshold; only decimal-stop reliably catches the integer/decimal boundary.
- **Right-most green pixel test failed** as a badge state discriminator — both Next/Stopping pentagons are identical shapes. Pixel-diff against text-content anchors is what works.

## Future enhancements

Full backlog lives in [TODO.md § Auto-input / OCR](TODO.md). Two items gate the entry-point flow above:

- [ ] **Layer 1 silent-advance design.** Required before entry-point flow can land. NOT a `jump_to_stop` variant. Discussion-first.
- [ ] **Implement entry-point flow** (toggle-ON + click-jump variants) on the cleaned abstraction.

## For next-session Claude (zero-context pickup)

Context to load:

- [auto_input/README.md](auto_input/README.md) — current-state facts.
- This doc — entry-point flow design + history + calibration.
- `memory/2026-05-09.md` + `memory/2026-05-09-overnight.md` — Layer 3 rename + panel redesign + signal-flag fix.
- `memory/2026-05-08.md` — black-screen-at-platform crisis + cross-attribute hardening.

**Highest-value next step:** Layer 1 silent-advance design discussion. Entry-point flow is unblocked once silent-advance has a chosen mechanism.

Manual smoke-test hint for live drives:

1. Boot `uv run main.py`, toggle OCR Auto-PA on the setup screen, select a calibrated route. Game running fullscreen at 2560×1440 with HUD visible top-right.
2. Drive 2 stations. Confirm via debug panel: `inferred_state` cycles `IDLE` → `DEPARTING` → `CRUISING` → `ARRIVING` → `STOPPED`; observed-flags light in order (`dep✓`, `arr✓`, `at✓`); auto-fires land at expected events; manual PageDown overrides cleanly (auto skips its own fire on `curr_stop` mismatch).
3. If anything misbehaves, dump the JSONL log (`_recordings/drive_<line>_<diagram>_<TS>.jsonl`) + a panel screenshot. The 1b path (`_dev_scripts/capture_game.py`) is the offline-replay baseline.

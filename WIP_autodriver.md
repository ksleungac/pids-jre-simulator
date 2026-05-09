# WIP — Auto-driver (pending design + history)

Working notes for the auto-input subsystem. Current-state facts live in [AUTO_INPUT.md](AUTO_INPUT.md). This doc holds:

- **Pending design** — entry-point flow + Layer 1 silent-advance, yet to be implemented.
- **Validation history** — chronological record of live + offline validation milestones.
- **Calibration insights** — rationale and "we tried X, settled on Y" guardrails.
- **Future enhancements** — priority-ordered backlog.

Click-jump on the lower LCD shipped 2026-04-29 (App-state side only, no autodriver re-anchor yet).

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
- **2026-04-27 evening**: live-validated 1b (separate-process, `_dev_scripts/capture_game.py`) on Keihin-Tōhoku 727B Omiya→Kanda full route — flawless. 1a (in-process) feature-complete + compiles cleanly but **not yet live-validated**.
- **2026-04-29**: Layer 2 cache rename `*_fired` → `*_observed`; `_Detector.inferred_state()` accessor extracted; `inferred_state` surfaced in status dict + JSONL drive log + debug panel. Layer 3 vocabulary (canonical names + truth table) now mirrored between code and AUTO_INPUT.md.

## Calibration insights (rationale / guardrails)

- **PrintWindow returns black for DirectX games.** Even with `PW_RENDERFULLCONTENT`. Same for BitBlt-from-desktop. dxcam (DXGI Output Duplication) is the only path that works reliably. Don't simplify to PrintWindow.
- **`output_color="BGRA"`** in dxcam is native; `"RGB"` requires opencv-python.
- **Set DPI awareness** before any window measurement: `ctypes.windll.shcore.SetProcessDpiAwareness(2)`. At 2560×1440 + DPI scaling, omitting this misaligns coordinates.
- **HUD text varies in pixel-population** by anti-aliasing. Fixed binarization threshold (70) is more stable than Otsu, which gets confused by 3-population distributions (text + bg + scenery bleed-through).
- **Decimal point detection by shape** (small bbox in bottom half of text band) is more robust than gap-based heuristics. Speed values like `110.7` have inter-`1` gaps of ~18px, exceeding any reasonable digit-gap threshold; only decimal-stop reliably catches the integer/decimal boundary.
- **Right-most green pixel test failed** as a badge state discriminator — both Next/Stopping pentagons are identical shapes. Pixel-diff against text-content anchors is what works.

## Future enhancements

Priority-ordered for next session pickup:

- [ ] **Layer 1 silent-advance design**. Required before entry-point flow can land. NOT a `jump_to_stop` variant. Discussion-first.
- [ ] **Implement entry-point flow** (toggle-ON + click-jump variants) on the cleaned abstraction.
- [ ] **Live-validate 1a (in-process integration)**. 1b is the only path live-tested end-to-end (Keihin 727B Omiya→Kanda). 1a should behave identically but needs a real drive to confirm.
- [ ] **Dynamic arrival threshold**: per-stop 1200m vs 900m based on whether the stop's last PA is "significantly longer" than the route's average PA duration (transfer guides are characteristically longer). User's exact words: *"if it's significantly longer than the average length of other PA, then it's a long arriving PA, if no please go and have the most fun"*. In-process driver has direct access to `sim.stops` + can probe audio durations via `mutagen` or `soundfile` — no extra `--route` flag needed. Currently uses the static Lead value chosen on the setup screen.
- [ ] **Multi-PA queue auto-advance**: simulator's `_next_pa()` plays one PA per invocation. For multi-PA stops (transfer hubs with 3+ PAs), only the first arrival PA fires automatically; user manually fires the rest with PageDown. Auto-advance would either fire multiple `pending_next_pa` flags spaced by PA audio durations, or have the simulator auto-chain when configured.
- [ ] **Multi-resolution support**: bboxes + digit templates are pixel-fixed at 2560×1440. Future: proportional layout + template scaling.
- [ ] **Separate-window debug panel**: today the panel shares the LCD's pygame window via sub-surfaces (no overlap, but same window). User has flagged preference for further decoupling — possible via `pygame._sdl2.video.Window` for a fully separate OS window. Not a blocker; deferred.
- [ ] **STA auto-fire**: not modeled. STA is IRL-manual (station master, not driver), per user spec. Plumbing for synthetic PageUp + user-press monitoring exists in 1b if needed later.

## For next-session Claude (zero-context pickup)

Context to load:

- [AUTO_INPUT.md](AUTO_INPUT.md) — current-state facts (state-machine layering, code architecture, OCR pipeline, debug panel, files).
- This doc — pending design, history, future work.
- `memory/2026-04-29.md` — most recent session.
- `memory/2026-04-27.md` — original autodriver phase-4 milestone.

**Highest-value next step:** Layer 1 silent-advance design discussion. Refactor was completed 2026-04-29 — `_Detector.inferred_state()` is live, flags renamed, code now mirrors the Layer 3 truth table. Implementing the entry-point flow is unblocked once silent-advance has a chosen mechanism.

Manual smoke-test hint for live-validating 1a:

1. Boot `uv run main.py`, toggle OCR Auto-PA on the setup screen, select Keihin 727B (validated route on 1b). Game must be running fullscreen at 2560×1440 with HUD visible at top-right.
2. Drive 2 stations. Confirm:
   - Debug panel renders correctly (4 lines: header, speed/distance/cnt_pa/observed flags, app/game state)
   - Speed/distance values track HUD readings
   - `dep✓` / `arr✓` flags light up at expected times
   - `inferred_state` value matches expectations (`IDLE` / `DEPARTING` / `CRUISING` / `ARRIVING` / `STOPPED`)
   - `app:` line shows correct App-state description
   - Manual PageDown overrides cleanly (auto skips its own fire)
3. If anything misbehaves, paste the terminal log + a panel screenshot. The 1b path (`_dev_scripts/capture_game.py`) is the comparison baseline — known working.

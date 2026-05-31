# TODO

Centralized backlog. Source-of-truth pointers under each section so the detail is one click away — keep this file an index, not a repository of context.

> **Conventions.** `[ ]` open, `[x]` done (rare here — done items move out, not get checked). Each item has a 1-line "what" + a parenthesized source pointer. Items rot — sweep this file when you touch a related area, prune what's no longer real, add what is.

---

## Auto-input / OCR

The OCR auto-PA feature shipped in `feat(auto-input): OCR-driven auto-PA — in-process driver, PASSING badge, setup-screen toggle` (commit `65d0cd3`). Open work that didn't make that scope:

- [ ] **Re-entry probe consensus (anti-transient-misread hardening).** Entry-point flow shipped 2026-05-31 as re-entry (`_maybe_reentry` — subsumes both mid-transit click-jump and toggle-ON cold entry; live-validated). It acts on a *single* cycle's OCR read, guarded by `inferred_state` + the black-screen cross-reject + the speed≥30 gate. A sliding-window consensus (require ~2 agreeing probes before a silent-advance) would further harden against a lone transient misread while parked. Not blocking. (`auto_input/README.md` § "Re-entry (Layer 3 → Layer 2 reconciliation)".)
- [ ] **Dynamic arrival threshold.** Replace the static Lead value with per-stop 900m vs 1200m derived from "is this stop's last PA significantly longer than the route average?" (transfer guides are characteristically longer). 1a has direct access to `sim.stops` + can probe audio durations via `mutagen`/`soundfile`. (`auto_input/README.md` § "Future enhancements".)
- [ ] **Multi-PA queue auto-advance.** `_next_pa()` plays one PA per call; multi-PA stops (transfer hubs with 3+ PAs) currently auto-fire only the first arrival, user manually fires the rest. Either fire multiple `pending_next_pa` flags spaced by audio duration, or have the simulator auto-chain. (`auto_input/README.md` § "Future enhancements".)
- [ ] **Resolution selector in main program.** `driver.py` auto-detects from bootstrap grab (no user input needed today). If multi-monitor or non-native-fullscreen edge cases surface, expose override in setup screen. (Deferred — auto-detect sufficient for current use.)
- [ ] **Separate-window debug panel.** Today the panel shares the LCD pygame window via sub-surfaces (no overlap, but same window). Could decouple via `pygame._sdl2.video.Window` for a fully separate OS window. Not blocking; deferred. (`auto_input/README.md` § "Future enhancements".)
- [ ] **STA auto-fire.** Not modeled — STA is IRL-manual (station master, not driver). Plumbing exists in 1b if needed later. (`auto_input/README.md` § "Future enhancements".)
- [ ] **Cross-attribute hardening, further cases.** Cross-attribute corroboration is primary; per-attribute confidence gates are secondary and fine where the element has a naturally wide real-vs-garbage gap. The two layers collaborate. 2026-05-08 black-screen-at-platform incident shipped both: (a) confidence gate in `classify_badge_state` — badge_diff > 50 returns `(None, diff)`, badge has a clean separator (real <15, garbage 60-110) so the gate is cheap and correct ([auto_input/README.md § Badge classification](auto_input/README.md)); (b) structural cross-attribute rule in `_Detector.update` — prev_badge=STOPPED + speed=0|None forces badge to None, exploits "black-screens only happen at platforms, real departures monotonically increase speed" ([auto_input/README.md § Cross-attribute reject](auto_input/README.md)). Further cases as misfires surface. (Project memory: `~/.claude/projects/D--pids-jre-simulator/memory/project_hardening_philosophy.md`.)
- [ ] **First-run OCR warning + intro screen.** When user toggles OCR Auto-PA on (or first time per session), show a small confirmation/intro modal before activation. Two disclaimers: (1) **preview feature, unstable** — auto-fires may misfire, manual PageDown still works as override; (2) **screen-capture notice** — we capture the game-window region of the desktop to read the HUD, and the project does NOT collect, transmit, or use OCR data for any purpose beyond the in-process decision. Plus a brief "what does OCR Auto-PA do" intro with a small graphic / diagram showing the HUD region being read (HUD bbox illustration — distance / speed / badge cells highlighted). Single OK-to-continue button.
- [ ] **Luminance-aware adapter for pale-brand line colours.** Sobu yellow `#FFD400`, Yamanote yellow-green — currently render at full saturation on white card top accents and the eyebrow text would be hard to read. Need W3C relative-luminance darkening for the eyebrow/accent uses while the wide accent strip stays vivid. Drafted in earlier session and reverted; re-add when a Sobu/Yamanote drive recording surfaces a real readability problem.
- [ ] **OCR — distinguish legitimate `0cm` from reset-after-overrun `0cm`.** Both render as identical green `0cm` text — same OCR read, different game-state context. A perfect stop by the player and a game-forced reset after the player overran the platform mark currently look the same in the data; the plot's "stopping accuracy" metric would be misleading if reset stops are counted as perfect ones. Possible disambiguating signals (per-arrival, evaluated within a context window): (a) was there a black-screen / OCR-FAIL frame near the `MOVING→STOPPED` transition (reset uses a black-screen fast-forward); (b) speed trace just before stop — legitimate stop decelerates smoothly to 0, reset jumps from non-zero to 0 abruptly; (c) distance trace — overrun has distance crossing through 0/negative before the reset frame. Out of scope for the OCR layer; lives in `plot_drive.py`'s arrival-event analysis. Tabled 2026-05-09; revisit when the plot tool actually renders stopping-accuracy data and the false-perfect-stops bias becomes visible.

## Display / LCD fidelity

- [ ] **New train models — re-skin work, not re-architecture.** Priority order: E235-0 Yamanote (in progress — see below), then E231-500, then E233 series. Each model lives under `displays/train_models/{model}/`. (CLAUDE.md § "Mental Model — Direction of travel".)
  - [ ] E235-0 lower LCD — **5-station zoomed view** (replaces inherited 8-station). Universal replacement for the EIGHT slot on E235-0 (used for Yamanote AND any other route loaded into the model). Currently the EIGHT slot inherits E235-1000's `JapaneseEightStationDisplay` as interim. Design discussion deferred per "full-route first." (DISPLAY_E235.md § "Sub-series catalog".)
  - [ ] E235-0 lower LCD — ENGLISH renderer. FULL slot uses inherited e235_1000 `EnglishDisplay` (linear) — works but not Yamanote-circular. EIGHT slot falls back to Japanese.
  - [ ] E235-0 lower LCD — transfer-info slot integration. The full-route + 8-station slots ship in `LowerDisplay` subclass; transfer-info inherits from E235-1000 parent unchanged but hasn't been visually verified for E235-0.
- [ ] **DISPLAY_E235.md — caveman-full voice + Voice EDIT-CONTRACT line.** Deferred from 2026-05-11 caveman adoption push (DATA_FORMAT / DISPLAY / auto_input/README.md rewritten that session). Skipped due to active E235-0 churn — mass rewrite mid-flight risks conflicts with in-flight content. Apply when E235-0 stabilizes (5-station zoom + ENGLISH renderer + transfer-info verification above all shipped).
- [ ] **Through-service: display range / `display_end`.** Combined frame currently shows `pre_stops + all of stops`; IRL the frame truncates at major continuation junctions (e.g. Sōbu/1217F's frame ends at 千葉 even though sim continues to 成田空港). Needs schema + windowing design — possibly a `display_end: "千葉"` field, or a different mechanism. User explicitly tabled during pre_stops feature discussion. (DATA_FORMAT.md § "pre_stops Array" — "Out of scope (deferred)".)
- [ ] **Through-service: frame-swap-at-junction.** Sister problem to display_end. At Chiba for Sōbu/1217F the LCD swaps from "Yokosuka→Sōbu Rapid combined" to "Sōbu→Sōtobō / Narita Line continuation". User: "similar problem (different line, through service)". Deferred alongside display_end.
- [ ] **Transfer-info — stations data population.** Extend beyond current ~48 (code_3 catalog + JO Sōbu Rapid done). Curation priority: stations served by ≥1 LCD-equipped line (E233+/E235). Skip 戸塚, 高輪ゲートウェイ, JY-only, JO-only east. `transfers_by_view` populated as raw observations, not derived. Note: 赤羽 JK/JA inner spacing observation pending verification. **Deferred until E235-0 + E233 models land** — no point adding e.g. Chūō transfers when there aren't enough in-spec train models to calibrate against. ([DISPLAY_E235.md § Transfer Info](DISPLAY_E235.md))
- [ ] **Transfer-info — per-train-model badge rendering policy (E233 sub-series).** E235-1000's `_universal + color → color square` rule landed. Different E233 sub-series render certain transfer entries as color-squares instead of icons (JK E233: Kawagoe; JA E233: all JR except Shinkansen). When E233 lands, declare its policy in its own `transfer_info.py` (no parameterized DSL). Color data entry is opportunistic — fill when an IRL ref is on hand. ([DISPLAY_E235.md § Color-square policy](DISPLAY_E235.md))
- [ ] **Transfer-info — recalibrate Step-1 N=5 tier.** Currently 1.8× extrapolated from N=7/N=9 anchors; 千葉 JO_east row 0 cramped is the known case. Need more IRL refs at N=5. ([DISPLAY_E235.md § Pipeline](DISPLAY_E235.md))
- [ ] **Transfer-info — EN size constraint trade-off (deferred).** Shinkansen row currently parked at EN 12 pt. Fixes parked.
- [ ] **Transfer-info — data-driven pattern analysis (future).** Once `transfers_by_view` populates ~10+ views × ~3+ drops, pivot the `(station, view, dropped_slug)` tuples to look for clusters that suggest IRL rules (upstream-coverage suppression, parallel-corridor redundancy, direction-aware suppression). If a pattern emerges, codify as a derivation rule with per-station data preserved as fallback for exceptions.
- [ ] **Transfer-info — `render_transfer` monolith refactor (future, when 2nd train-model lands).** ~770 lines with 6 nested closures sharing implicit outer scope. Real fix is a `LayoutContext` dataclass holding per-render state. Premature without a 2nd consumer. Trigger to revisit: when E233 sub-series adds a sibling `transfer_info.py` and starts to share/diverge code with E235.

## Distribution

Speculative side-quest from the future-direction discussion. Competing for budget against further auto-input polish. (CLAUDE.md § "Direction of travel".)

- [ ] **Signed Windows installer.** Replace the zip-extract distribution with a proper signed installer for the lightly-public audience.
- [ ] **First-run smoothness.** Whatever needs polishing for the ~1800 video-play / occasional-railfan audience.

## Chrome / i18n / OOBE

The chrome i18n foundation shipped 2026-04-29 evening: `i18n.py`, language picker, setup-screen translation, EN-mode font swap to HelveticaNeue-Bold, line-marker badges, lifted theme. Open follow-ups:

- [ ] **OOBE — game-pairing screenshots.** Placeholders implied in step 3 (~25s departure cue) + step 5 (~1200-800m approach distance) + step 8 recap. User provides screenshots later.
- [ ] **Add EN data translations for routes not covered by `translations.json` / `train_types.json`.** Today's EN mode falls back to kanji + CJK font for line 2 when a dest/type entry is missing. **Joban data pending** (e.g. `土浦`) — same logic as transfer-info: no point without a Jōban-line train model to calibrate against. Mock-route fake dests (e.g. `品川・高輪ゲートウェイ`) don't count — no point translating unreal data. Long-term: add `english` field to route.json for route names + line-name itself, expand `translations.json` for missing dests. User: "in the future all of those will be in English."

## Housekeeping (small, do-when-you-touch-the-area)

- [ ] **Decide 1b debug-frame dump behaviour.** `_dev_scripts/capture_game.py:320` saves a HUD crop every sample interval to `_experiments/live_captures/`. Gitignored, but disk spam if 1b runs long. Options: leave (debugging tool), gate behind `--save-frames` flag (default off), or remove. (Discussed 2026-04-27, deferred.)
- [ ] **Re-grab `passing_en.png` at native 2560×1440.** Current capture is 2559×1439 — pygame blit handles it, classifier diff=0.00, but a clean re-capture is tidier.

---

## Deferred review findings

Open items surfaced by `/review+fix` that were deferred (not blocking, scope-creep, or dead-in-practice). Dedup by `<file>:<line>` + summary; bump recurrence counts when re-flagged. Mark `[x]` and strikethrough when fixed; remove entirely when user says "not real".

### From 2026-05-02 (dual-stream audio)

- [ ] **PA paused-state asymmetry vs STA's explicit `_sta_paused` flag** — `app.py:115` (lens 1, info; first flagged 2026-05-02) — `is_pa_playing()` returns True even while PA is paused (pygame `mixer.music.get_busy()` quirk). Pause is idempotent so no live-incorrect behavior, but mental model is asymmetric. Revisit when an unpause UI key is added.

### From 2026-05-02 (transfer-info schema)

- [ ] **Variant-only base slugs raise KeyError downstream rather than at resolver** — `DATA_FORMAT.md:254` (lens 1, info; first flagged 2026-05-02) — `yokosuka_sobu` has no `name_ja`/`name_en` at base; if referenced plain (no `.variant` suffix), the entry resolves without name fields → KeyError downstream. Today's data always uses variants for these slugs. Revisit when validator pass surfaces, or add explicit resolver guard.
- [ ] **`ueno_tokyo.tohoku` variant inherits non-IRL `name_ja`/`name_en`** — `data/lines.json:28` (lens 1, info; first flagged 2026-05-02) — IRL on JU-zone (Takasaki/Utsunomiya) the LCD typically labels by 宇都宮線/高崎線, not "Ueno-Tōkyō Line". Out of scope until first JU-zone station with `transfers` is added.

### From 2026-05-03 (transfer-info LowerDisplay hookup)

- [ ] **`_resolve_transfers` called twice per frame at LowerDisplay layer** — `displays/train_models/e235_1000/lower_lcd.py:_station_has_transfers` (lens 1, info; first flagged 2026-05-03) — Once for slot-membership decision in `_available_slots`, again on render in `TransferInfoDisplay.show_stops`. Reaches past underscore-prefix private boundary. Perf is fine (dict lookup + small list comps); cache once per frame at LowerDisplay level if needed.

### From 2026-05-04 (transfer-info per-N scaling)

- [ ] **`_N >= 10` clause in dense-tier scaling is anticipatory** — `displays/train_models/e235_1000/transfer_info.py:168` (lens 1, info; principles.md § Implementation-completion-as-spec; first flagged 2026-05-04) — Max station N in current dataset is ~9; the `N >= 10` branch is uncalibrated. Defer until either (a) an N=10+ station enters the dataset, or (b) algorithm-redesign Step 1 formally calibrates the full ladder.

### From 2026-05-07 (E235-0 circular full-route + clock fine-tune)

- [ ] **Cycler-lock lambda fragility in preview** — `preview_display.py:200` (lens 1, info; first flagged 2026-05-07) — `sim.lower._tick_cycle = lambda current_time: None` and `sim.lower._handle_at_station_edge = lambda state, current_time: None` duplicate the bound-method signatures and will silently rot if those methods gain a parameter. Deferred because: preview-only; the clean fix would add a `_cycler_locked` boolean to the production `LowerDisplay` class for a preview-only feature.
- [ ] **Wrap-around minute undercount at loop terminal** — `displays/train_models/e235_0/lower_lcd.py:747` (lens 1, info; first flagged 2026-05-07) — `_compute_minutes_for_ahead` dedups by `sta_code`; when the duplicate JY24 marker at the loop terminal (Yamanote's `stops[0] = stops[-1]`) is skipped, its `time` value isn't credited to the next surviving entry's first-cumulative. Deferred because: dead in practice — IRL the wrap-back marker is `at_station=True` which uses the static branch.
- [ ] **CLOCK_RECT magic-number duplication** — `displays/train_models/e235_1000/upper_lcd.py:217` + `e235_0/upper_lcd.py:195` (lens 2, info; smell #5 within-file constant duplication; first flagged 2026-05-07) — `S_WIDTH - 170` and `80` repeat as both `CLOCK_RECT` const + inline `clock_x` / `clock_w` magic numbers in both `draw_clock` methods of each model. Deferred because: pre-existing pattern in e235_1000, not introduced by this session's diff. Worth a `/vibe-check` sweep to refactor inline references to `CLOCK_RECT.x` / `CLOCK_RECT.width`.

### From 2026-05-08 (E235-0 polish + font-path migration)

- [ ] **EnglishDisplay single-line dest sibling-divergence (e235_1000)** — `displays/train_models/e235_1000/upper_lcd.py` EnglishDisplay.draw_destination single-line branch (lens 3, warning; sibling-drift; first flagged 2026-05-08) — User asked for single-line English dest in **e235_0** to be LEFT-aligned at x=5 mirroring the 2-line branch (was previously centered via `draw_text_given_width(..., collapse=True)`). Same pattern exists in e235_1000 but was not touched. Deferred because: user-stated scope was "in E235-0" specifically (per `principles.md` § Scope fidelity for codified feedback); whether to propagate to e235_1000 is a separate question. Decide whether IRL e235_1000 PIDS centers or left-aligns its single-line English dest, then either propagate or codify the divergence.

### From 2026-05-09 (OCR speed-limit + stopping-offset feature shipping)

- [ ] **Cross-attribute reject is invisible in JSONL** — `auto_input/driver.py:620` (lens 1, info; first flagged 2026-05-09) — `_Detector.update`'s cross-reject mutates `badge → None` internally before the transition logic runs, but the recorded JSONL `badge` field stores the raw `classify_badge_state` output. A downstream replay tool reading the JSONL sees badge=PASSING transitions that the live detector silently ignored, with no signal that they were rejected. Print log captures it (`[AD] >>> CROSS-REJECT raw_badge=...`) but the structured stream does not. Deferred because: layering is intentional (raw OCR is preserved separately from detector decisions); only matters when `plot_drive.py` grows logic that depends on detector decisions vs raw observations. Fix path: emit a JSONL event (`_write_event(log_file, "CROSS_REJECT", ...)`) similar to badge transitions.
- [ ] **`MISREAD_DUMP_DIR` placement under `_ocr_calibration/`** — `auto_input/driver.py:120` (lens 3, info; sibling of `critical_lessons.md` 2026-04-27 § "naming carries semantics"; first flagged 2026-05-09) — Misread dumps land at `_ocr_calibration/_misread_dumps/`, but `_ocr_calibration/` is documented elsewhere as "OCR calibration sources" (input screenshots consumed by `extract_ocr_assets.py`). Mixing runtime debug-output into a sources-named folder conflates two dev-material categories; sibling precedent is `_recordings/` for runtime blackbox. Deferred because: thematic locality wins (both are OCR-related) + 31 existing dumps already in the path. Revisit if the mixed-purpose folder causes navigation friction.

### From 2026-05-28 (multi-res OCR)

- [ ] **`_crop_cell` forked across three dev scripts** — `_dev_scripts/validate_ocr.py`, `_dev_scripts/capture_game.py`, `_dev_scripts/extract_ocr_assets.py` (lens 2, warning; vibe-check #1 duplicated helpers; first flagged 2026-05-28) — Three byte-identical profile-aware surface croppers (read `profile.hud_bbox`, blit HUD-relative cell, transpose to H×W×3). All dev-only (`_*/`) so no production blast radius. Deferred because: low urgency, dev-only. Fix path: promote a single `crop_cell(surf, profile, cell_bbox)` into `auto_input/ocr.py` alongside the existing 1440p `crop_cell_from_surface`, import from all three scripts.

### From 2026-05-09 PM (debug-panel redesign + audio-busy fix + Layer 3 rename)

- [ ] **`_LAYER3_HUMAN` near-identity map** — `auto_input/driver.py:85` (lens 2, info; vibe-check #4 speculative architecture; first flagged 2026-05-09 PM) — After the Layer 3 rename, the dict is essentially `{IDLE: "Idle", STOPPED: "Stopped", ...}` title-case identity, justified as "a hook for future divergence (i18n, customization)." But auto-input has no i18n surface and isn't on the roadmap. Deferred because: explicit panel labels separable from wire names is a defensible design choice (one centralized place to retune labels without touching wire constants). Revisit if the dict stays purely identity for >2 months — at that point fold into `inferred.title()` at the call site.
- [ ] **Silent click-absorb when `sim.auto_driver=None`** — `auto_input/driver.py:402` (lens 2, info; vibe-check #3 half-finished; first flagged 2026-05-09 PM) — `handle_panel_click` returns True (absorbs click) even when `sim.auto_driver is None`, with no behavior. Unreachable in production today (panel only renders when `auto_input=True` AND `main.py` always sets `sim.auto_driver = driver` immediately after construction). Deferred because: defensive-hardening polish, no observable user impact. Either log a hint matching the Report button's empty-log path, or fall through (return False).
- [ ] **Pause-loop resume latency up to `interval_s`** — `auto_input/driver.py:786` (lens 1, info; first flagged 2026-05-09 PM) — When user clicks Resume, the OCR thread can sleep up to 5s (`interval_s`) before checking `self.paused` again and resuming capture. Panel re-renders the button instantly (main thread), but actual OCR resume lags. Deferred because: minor UX nit, not a bug. Fix: shorten poll interval inside the paused branch to e.g. `min(interval_s, 0.5)`.

---

## Closed-off paths (don't re-propose)

Recording the ground we've explicitly decided NOT to walk, so future sessions don't re-litigate:

- **Memory hooking the game's `*saf.dll` modules.** Tried, dead end.
- **Decrypting SimDATA assets.** Encrypted; not pursuing.
- **Audio fingerprinting** for stop detection. Replaced by HUD OCR which works.
- **Full-desktop OCR** instead of window-bound capture. Privacy + perf concerns.
- **Tesseract-based OCR.** Too heavy; pixel-perfect template match works.
- **Mac build.** The companion game (JR EAST Train Sim Real) is Windows-only — no Mac audience exists for this app. Not worth the porting cost.
- **Scaling to lines the game already covers** (Sobu local, Yokosuka, etc. — newer game routes ship with PA, don't duplicate).
- **OCR-as-display-layer fidelity-purity argument.** OCR is an *input layer* (replaces PageDown press), not display. Don't recycle.

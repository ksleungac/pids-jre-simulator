# TODO

Centralized backlog. Source-of-truth pointers under each section so the detail is one click away — keep this file an index, not a repository of context.

> **Conventions.** `[ ]` open, `[x]` done (rare here — done items move out, not get checked). Each item has a 1-line "what" + a parenthesized source pointer. Items rot — sweep this file when you touch a related area, prune what's no longer real, add what is.

---

## Auto-input / OCR

The OCR auto-PA feature shipped in `feat(auto-input): OCR-driven auto-PA — in-process driver, PASSING badge, setup-screen toggle` (commit `65d0cd3`). Open work that didn't make that scope:

- [x] **Live-validate 1a (in-process integration).** Done 2026-04-27 evening on Keiyo 780Y_1510Y (蘇我→東京). 765 samples captured. Validation revealed a state-machine bug: detector previously only reset fired-flags on `STOPPED→MOVING`, missing `STOPPED→PASSING`. On Keiyo's 千葉みなと→稲毛海岸 leg the OCR badge stays PASSING for ~80s while the train crosses 千葉貨物 freight terminal — flags inherited True from the previous segment, both PA fires were suppressed silently. Fixed in commit `8ac2b67`: `STOPPED→(MOVING|PASSING)` now both reset flags symmetrically.
- [ ] **Dynamic arrival threshold.** Replace the static Lead value with per-stop 900m vs 1200m derived from "is this stop's last PA significantly longer than the route average?" (transfer guides are characteristically longer). 1a has direct access to `sim.stops` + can probe audio durations via `mutagen`/`soundfile`. (`AUTO_INPUT.md` § "Future enhancements".)
- [ ] **Multi-PA queue auto-advance.** `_next_pa()` plays one PA per call; multi-PA stops (transfer hubs with 3+ PAs) currently auto-fire only the first arrival, user manually fires the rest. Either fire multiple `pending_next_pa` flags spaced by audio duration, or have the simulator auto-chain. (`AUTO_INPUT.md` § "Future enhancements".)
- [ ] **Multi-resolution support.** HUD bboxes + digit templates are pixel-fixed at 2560×1440. Other resolutions need full recalibration. Future: proportional layout + template scaling. (`AUTO_INPUT.md` § "Recalibration" + § "Future enhancements".)
- [ ] **Separate-window debug panel.** Today the panel shares the LCD pygame window via sub-surfaces (no overlap, but same window). Could decouple via `pygame._sdl2.video.Window` for a fully separate OS window. Not blocking; deferred. (`AUTO_INPUT.md` § "Future enhancements".)
- [ ] **STA auto-fire.** Not modeled — STA is IRL-manual (station master, not driver). Plumbing exists in 1b if needed later. (`AUTO_INPUT.md` § "Future enhancements".)
- [ ] **Cross-attribute hardening, when needed.** User's framing: "consider every case where identification is wrong, how can other attributes augment it." NOT per-attribute confidence gates; cross-attribute corroboration (e.g. badge says PASSING but distance trend doesn't match → distrust badge). Tabled until a misfire actually bites. (Project memory: `~/.claude/projects/D--pids-jre-simulator/memory/project_hardening_philosophy.md`.)
- [ ] **First-run OCR warning + intro screen.** When user toggles OCR Auto-PA on (or first time per session), show a small confirmation/intro modal before activation. Two disclaimers: (1) **preview feature, unstable** — auto-fires may misfire, manual PageDown still works as override; (2) **screen-capture notice** — we capture the game-window region of the desktop to read the HUD, and the project does NOT collect, transmit, or use OCR data for any purpose beyond the in-process decision. Plus a brief "what does OCR Auto-PA do" intro with a small graphic / diagram showing the HUD region being read (HUD bbox illustration — distance / speed / badge cells highlighted). Single OK-to-continue button.
- [x] **Hook STOPPED badge state into the lower LCD.** Step 1 (display + state machine) shipped 2026-04-28; step 2 (OCR-driven) shipped same day: AutoDriver's `_Detector` gained `at_station_fired` flag + a level test (`badge==STOPPED AND arrival_fired AND not at_station_fired`) that emits `FIRE_AT_STATION`. Dispatcher's `_fire_at_station` queues the silent press that flips `sim.state.at_station=True` (re-uses `pending_next_pa` so the same `_next_pa` path runs as for manual PageDown — no parallel mutation race). Guards mirror `_fire_arrival`: skip if already STOPPING, curr_stop mismatch, or cnt_pa not at last approach pa.
- [ ] **Reduce screen-capture area to top-right ¼.** Today `dxcam.grab()` returns the full 2560×1440 desktop frame, then we crop. dxcam supports `grab(region=(left, top, right, bottom))` natively — restricting to the top-right quadrant `(1280, 0, 2560, 720)` cuts capture work by ~75% and the cropped frame is smaller for the HUD-region slicing too. HUD lives within that quadrant (HUD_BBOX = `(2200, 20, 350, 480)`). After this change, all cell-bbox math needs to shift from desktop-coords to quadrant-relative coords (subtract 1280 from x). Tighter region (e.g. just the HUD `(2150, 0, 2560, 520)`) is even faster but more brittle to recalibration. Background: prior experiments couldn't reliably scope capture to the *game window only* (DirectX swap-chain not visible to GDI per `AUTO_INPUT.md`); desktop-region capture is the realistic compromise.
- [x] **Drive recorder / blackbox — JSONL streaming + interactive HTML plot generator.** Both data-capture and plot-render done. `_recordings/drive_<line>_<diagram>_<TS>.jsonl` written by AutoDriver; `plot_drive.py` renders a multi-section dashboard HTML with speed/STOPPED/PASSING bands, station signposts (start green, terminus red, middle accent blue), per-line brand-colour accent strip, schedule-style metric card, per-section stats. Open follow-ups below ↓
- [x] **Hook plot generator into the debug bar — "Report ↓" button.** Done 2026-04-28. Pill-styled button in the top-right of the OCR debug panel; click forwards through `app.py`'s MOUSEBUTTONDOWN handler to `auto_input.handle_panel_click`, which spawns a daemon thread that reads the live JSONL and renders HTML next to the project root. Re-runnable mid-drive (JSONL partial-write-safe — each click produces a fresh snapshot of progress so far).
- [ ] **Broader line-colour theme application.** Today the line colour shows on the top accent strip only. Could extend to: section number badges (`.section-num`), eyebrow text (`.page-eyebrow`), the speed line + fill in each chart. Add a luminance-aware adapter so pale brands (Sobu yellow `#FFD400`, Yamanote yellow-green) get darkened for stroke-readability while the brand strip stays vivid. Helper functions for hex→rgb, relative luminance (W3C), and darkening were drafted in this session and reverted; re-add when wiring.
- [ ] **OCR — stopping-position data.** The game's HUD shows the train's distance offset from the stop mark (`-12cm` / `+8cm` style — how precisely you stopped relative to the platform mark). New OCR cell + reader. Schema-add to JSONL: per-sample `stopping_offset_cm` (signed int). Display in plot: a "stopping accuracy" metric per arrival (the offset captured at the moment of `MOVING→STOPPED`); maybe a histogram or per-stop scorecard.
- [ ] **OCR — speed limit data.** The game's HUD also shows the current track speed limit. New OCR cell + reader. Schema-add: per-sample `speed_limit_kmh` (int|null). Plot enhancement: overlay the speed limit as a dashed line on top of the speed trace — over-limit segments become visually obvious (speed line above the limit line).

## Display / LCD fidelity

- [ ] **New train models — re-skin work, not re-architecture.** Priority order: E235-0 Yamanote (in progress — see below), then E231-500, then E233 series. Each model lives under `displays/train_models/{model}/`. (CLAUDE.md § "Mental Model — Direction of travel".)
  - [x] E235-0 upper LCD — forked from E235-1000, train-type cell removed (Yamanote runs single service type IRL). Shipped 2026-05-07. (`displays/train_models/e235_0/upper_lcd.py` + DISPLAY_E235.md.)
  - [x] E235-0 lower LCD — circular full-route renderer for Yamanote (rounded-rect track, JY-code row mapping, breath-animated pentagon, chevron arrow when between stations, major-station bold for Ueno/Tokyo/Shinagawa/Shinjuku/Shibuya). Linear E235-1000 fallback when route ≠ 山手線. Shipped 2026-05-07.
  - [ ] E235-0 lower LCD — **5-station zoomed view** (replaces inherited 8-station). Universal replacement for the EIGHT slot on E235-0 (used for Yamanote AND any other route loaded into the model). Currently the EIGHT slot inherits E235-1000's `JapaneseEightStationDisplay` as interim. Design discussion deferred per "full-route first." (DISPLAY_E235.md § "Sub-series catalog".)
  - [ ] E235-0 lower LCD — ENGLISH renderer (still falls back to JapaneseDisplay; same gap as E235-1000 § "ENGLISH lower-LCD" below).
  - [ ] E235-0 lower LCD — transfer-info slot integration. The full-route + 8-station slots ship in `LowerDisplay` subclass; transfer-info inherits from E235-1000 parent unchanged but hasn't been visually verified for E235-0.
- [x] **~~Yamanote 東京・上野 destination `\n` cleanup.~~** Shipped 2026-05-07. `data/translations.json` updated; `DATA_FORMAT.md § Compound Destinations` rule reframed as case-by-case based on length, not always-newline.
- [x] **~~Clock font + position fine-tune.~~** Shipped 2026-05-07. CLOCK_RECT shifted 10px left (`S_WIDTH - 170`), font 26→27pt. Applied to both E235-1000 and E235-0.
- [x] **~~Triage-policy rewrite for `/review+fix` deferred findings.~~** Shipped 2026-05-07. All deferred findings now route to TODO.md `## Deferred review findings` (memory daily logs are narrative-only). 22 entries migrated from past daily logs (2026-04-30 through 2026-05-04). `.claude/skills/review-plus-fix-relentlessly/SKILL.md` triage policy rewritten to match.
- [ ] **ENGLISH lower-LCD.** Still a stub — falls back to Japanese rendering. View-cycler timer already ticks regardless of language mode, so wiring an English renderer should be additive. (`memory/2026-04-25.md` § "Open follow-ups".)
- [ ] **`code_3` (3-letter Roman badge) edge cases.** Catalog is finite (~22 stations). General polish around fonts / placement / fallback for stations without a code. (CLAUDE.md § "Direction of travel".)
- [ ] **Continuity-arrow reconciliation** between the 8-station view's reserved-space arrows (`side_margin = 44`) and the user's existing buggy full-route helper. `JapaneseEightStationDisplay._draw_continuation_marker` is defined-but-deliberately-uncalled, awaiting that review. When wiring it in, also switch its `len(self.stops) - 1` early-return guard to `len(self.display_stops) - 1` for pre_stops compatibility (flagged inline in the dormant-scaffolding comment block above the method). (`memory/2026-04-25.md` § "Open follow-ups".)
- [ ] **Through-service: display range / `display_end`.** Combined frame currently shows `pre_stops + all of stops`; IRL the frame truncates at major continuation junctions (e.g. Sōbu/1217F's frame ends at 千葉 even though sim continues to 成田空港). Needs schema + windowing design — possibly a `display_end: "千葉"` field, or a different mechanism. User explicitly tabled during pre_stops feature discussion. (DATA_FORMAT.md § "pre_stops Array" — "Out of scope (deferred)".)
- [ ] **Through-service: frame-swap-at-junction.** Sister problem to display_end. At Chiba for Sōbu/1217F the LCD swaps from "Yokosuka→Sōbu Rapid combined" to "Sōbu→Sōtobō / Narita Line continuation". User: "similar problem (different line, through service)". Deferred alongside display_end.
- [ ] **Transfer-info — stations data population.** Extend beyond current ~48 (code_3 catalog + JO Sōbu Rapid done). Curation priority: stations served by ≥1 LCD-equipped line (E233+/E235). Skip 戸塚, 高輪ゲートウェイ, JY-only, JO-only east. `transfers_by_view` populated as raw observations, not derived. Note: 赤羽 JK/JA inner spacing observation pending verification. ([DISPLAY_E235.md § Transfer Info](DISPLAY_E235.md))
- [ ] **Transfer-info — per-train-model badge rendering policy (E233 sub-series).** E235-1000's `_universal + color → color square` rule landed. Different E233 sub-series render certain transfer entries as color-squares instead of icons (JK E233: Kawagoe; JA E233: all JR except Shinkansen). When E233 lands, declare its policy in its own `transfer_info.py` (no parameterized DSL). Color data entry is opportunistic — fill when an IRL ref is on hand. ([DISPLAY_E235.md § Color-square policy](DISPLAY_E235.md))
- [ ] **Transfer-info — recalibrate Step-1 N=5 tier.** Currently 1.8× extrapolated from N=7/N=9 anchors; 千葉 JO_east row 0 cramped is the known case. Need more IRL refs at N=5. ([DISPLAY_E235.md § Pipeline](DISPLAY_E235.md))
- [ ] **Transfer-info — EN size constraint trade-off (deferred).** Shinkansen row currently parked at EN 12 pt. Fixes parked.
- [ ] **Transfer-info — data-driven pattern analysis (future).** Once `transfers_by_view` populates ~10+ views × ~3+ drops, pivot the `(station, view, dropped_slug)` tuples to look for clusters that suggest IRL rules (upstream-coverage suppression, parallel-corridor redundancy, direction-aware suppression). If a pattern emerges, codify as a derivation rule with per-station data preserved as fallback for exceptions.
- [x] **~~Consolidate `project_root()` — sweep `upper_lcd.py:get_base_dir()`.~~** Done 2026-05-06 as part of v0.5.3 release-build crash investigation. `app_paths.py` is now the canonical home; `upper_lcd.py:get_base_dir`, `i18n.py:app_root`, `displays/utils.py:project_root` all collapsed to thin re-exports/aliases. The earlier "leave i18n.app_root alone, _MEIPASS is intentional" claim was wrong (cached PyInstaller mythology) — caused 4 release-build crashes. See `critical_lessons.md` § "PyInstaller deployment-frame divergence — path resolution + bundle coverage".
- [x] **~~Drop remaining `i18n.app_root` alias callers.~~** Done 2026-05-06. `setup.py` + `tutorial.py` now import `project_root` directly from `app_paths`; `i18n.app_root` alias removed; `i18n.py` internal callers also switched.
- [x] **~~`/release` skill: print bash-compatible upload command.~~** Done 2026-05-06. Step 7 now emits a single-line `gh release create` with literal version substituted (no PowerShell backticks, no shell variables) — runs in PowerShell, Git Bash, or cmd identically.
- [ ] **`data_tools/` directory at root.** Per `critical_lessons.md` § "Lazy import ≠ optional dep" (2026-04-30), `data_tools/` was renamed to `_dev_scripts/`. Yet `data_tools/` exists at project root again (untracked, listed in `/build` skill `$shipExclude`). Housekeeping: complete the rename per the 2026-04-30 lesson, OR update the lesson to reflect dual existence.
- [ ] **Transfer-info — `render_transfer` monolith refactor (future, when 2nd train-model lands).** ~770 lines with 6 nested closures sharing implicit outer scope. Real fix is a `LayoutContext` dataclass holding per-render state. Premature without a 2nd consumer. Trigger to revisit: when E233 sub-series adds a sibling `transfer_info.py` and starts to share/diverge code with E235.
- [x] **Interactive lower LCD — click station icon to jump.** Shipped 2026-04-29 (App-state side). Hit-test in both full-route and 8-station Japanese renderers; click lands `STOPPING@target` via `jump_to_stop` (which now also pauses audio); pre_stops + past-dest cells filtered; pointer-hand cursor on hover. **Autodriver re-anchor on click-jump still pending** — see [WIP_autodriver.md](WIP_autodriver.md) "Pending — Entry-point flow → Click-jump entry-point". Today's MVP relies on the existing dispatcher mismatch-skip + `STOPPED→(MOVING|PASSING)` flag reset for reconciliation.

## Distribution

Speculative side-quest from the future-direction discussion. Competing for budget against further auto-input polish. (CLAUDE.md § "Direction of travel".)

- [ ] **Signed Windows installer.** Replace the zip-extract distribution with a proper signed installer for the lightly-public audience.
- [ ] **First-run smoothness.** Whatever needs polishing for the ~1800 video-play / occasional-railfan audience.

## Chrome / i18n / OOBE

The chrome i18n foundation shipped 2026-04-29 evening: `i18n.py`, language picker, setup-screen translation, EN-mode font swap to HelveticaNeue-Bold, line-marker badges, lifted theme. Open follow-ups:

- [x] **OOBE first-time start guide — basic walkthrough.** Shipped 2026-04-29 overnight, refined 2026-04-30 (vibe-pass: 9→8 steps, dropped Driving phase; flashing route-bar callout for click-jump; flashing red box around yellow pa_hint square on steps 2/5; CJK chrome refactor with language-aware font dispatch + atom-based CJK char-level wrapping; keycap baseline alignment for CJK button labels; bilingual zh-HK / zh-CN translations shipped). 8-step tutorial in `tutorial.py` + `preview_tutorial.py`, gated by `settings["oobe_completed"]` between picker and setup; boots tokaido/1865E at 国府津, walks one full press cycle + click-jump demo + recap. `? Tutorial` button on setup re-runs. OCR-Auto-PA preview-feature disclaimer + screen-capture privacy notice is a separate TODO under § Auto-input/OCR (line 20) — not part of this scope.
- [ ] **OOBE — game-pairing screenshots.** Placeholders implied in step 3 (~25s departure cue) + step 5 (~1200-800m approach distance) + step 8 recap. User provides screenshots later.
- [ ] **Add EN data translations for routes not covered by `translations.json` / `train_types.json`.** Today's EN mode falls back to kanji + CJK font for line 2 when a dest/type entry is missing (e.g. joban's `土浦`, mock route's `品川・高輪ゲートウェイ`). Long-term: add `english` field to route.json for route names + line-name itself, expand `translations.json` for missing dests. User: "in the future all of those will be in English."

## Housekeeping (small, do-when-you-touch-the-area)

- [ ] **Decide 1b debug-frame dump behaviour.** `_dev_scripts/capture_game.py:320` saves a HUD crop every sample interval to `_experiments/live_captures/`. Gitignored, but disk spam if 1b runs long. Options: leave (debugging tool), gate behind `--save-frames` flag (default off), or remove. (Discussed 2026-04-27, deferred.)
- [ ] **Re-grab `passing_en.png` at native 2560×1440.** Current capture is 2559×1439 — pygame blit handles it, classifier diff=0.00, but a clean re-capture is tidier.

---

## Deferred review findings

Open items surfaced by `/review+fix` that were deferred (not blocking, scope-creep, or dead-in-practice). Dedup by `<file>:<line>` + summary; bump recurrence counts when re-flagged. Mark `[x]` and strikethrough when fixed; remove entirely when user says "not real".

### From 2026-04-30 (post-commit `51c7b07` + dep-misclassification cleanup)

- [ ] **Severity-tier overlap in review-dirty: Lens 2 #10 IS a Lens 3 violation** — `.claude/skills/review-dirty/SKILL.md:86` (lens 1, warning; first flagged 2026-04-30) — Need explicit "deepest applicable lens wins" rule, OR reframe Lens 2 #10 as a mechanical safety net for the Lens 3 rule.
- [ ] **Stale `_dev_scripts/validate_pa.py` reference** — `.claude/skills/sta-make/SKILL.md:602` (lens 1, warning; first flagged 2026-04-30) — points to a file that doesn't exist anywhere in the repo. Likely just delete the line.
- [ ] **Stale `_dev_scripts/` description** — `.claude/rules/conventions.md:9` (lens 2, warning; first flagged 2026-04-30) — still lists "drive-recorder CLI" as content, but `plot_drive.py` was moved to project root.
- [ ] **Silent except-Exception swallows traceback** — `auto_input.py:273` (lens 3, warning; first flagged 2026-04-30) — Lazy `from plot_drive import …` wrapped in `except Exception` silently swallows all failure modes. Should add `traceback.print_exc()`.
- [ ] **`info` severity auto-defer "Drop" silently buries unanswered ASK-flagged findings** — `.claude/skills/review-plus-fix-relentlessly/SKILL.md:126` (lens 2, info; first flagged 2026-04-30). NOTE: triage policy fully rewritten 2026-05-07 — verify whether this still applies under the new "all → TODO.md" routing.
- [ ] **JSON schema example hard-codes single severity** — `.claude/skills/review-dirty/SKILL.md:117` (lens 2, info; first flagged 2026-04-30) — should show full enum.
- [ ] **Recurrence-detection step implies unbounded scan** — `.claude/skills/review-plus-fix-relentlessly/SKILL.md:134` (lens 1, info; first flagged 2026-04-30) — "Already in any `memory/2026-*.md`" should be bound to last 30 days. NOTE: triage policy rewritten 2026-05-07 — recurrence step itself was simplified, may be obsolete.
- [ ] **Bash regex extraction contradicts skill's PowerShell-only directive** — `.claude/skills/review-plus-fix-relentlessly/SKILL.md:67` (lens 1, info; first flagged 2026-04-30) — Show PowerShell variant alongside.
- [ ] **Promote-out example chronologically inaccurate** — `.claude/rules/conventions.md:10` (lens 3, info; first flagged 2026-04-30) — reads `_dev_scripts/plot_drive.py` → `plot_drive.py`; was actually in `data_tools/` pre-rename.

### From 2026-04-30 (meta — broader release-readiness gap)

- [ ] **Smell #10 only fires on already-`_`-prefixed paths** — `.claude/rules/conventions.md` + `.claude/skills/vibe-check/SKILL.md` (meta, post-2026-04-30 dep-misclassification) — A fresh `tools/` or `helpers/` folder created for dev-only purposes could repeat the exact same chain. Closing requires a `conventions.md` rule about top-level non-`_`-prefixed folders, OR a vibe-check smell extending #10.

### From 2026-05-02 (dual-stream audio)

- [ ] **PA paused-state asymmetry vs STA's explicit `_sta_paused` flag** — `app.py:489` (lens 1, info; first flagged 2026-05-02) — `is_pa_playing()` returns True even while PA is paused (pygame `mixer.music.get_busy()` quirk). Pause is idempotent so no live-incorrect behavior, but mental model is asymmetric. Revisit when an unpause UI key is added.
- [ ] **`_load_and_play_sta` exception branch doesn't reset `_sta_paused`** — `audio.py:200` (lens 1, info; first flagged 2026-05-02) — If a fresh `play_sta` call hits an exception before the explicit reset, the flag stays True from the prior pause. Low priority — exception path only fires on genuinely unrecoverable errors.
- [ ] **`mixer.Channel(0)` hardcoded without `mixer.set_reserved(1)`** — `audio.py:83` (lens 3, info; first flagged 2026-05-02) — No collision today (only `mixer.music` + `_sta_channel` use audio). Fix when a second `Sound`-based caller is added.
- [ ] **PageUp lacks `KEY_REPEAT_DELAY` throttle** — `app.py:487` (lens 1, info; first flagged 2026-05-02) — Held PageUp restarts STA from `sta_cut` every frame at 15 Hz. Pre-existing behavior, not introduced by dual-stream-audio session.

### From 2026-05-02 (transfer-info schema)

- [ ] **Variant-only base slugs raise KeyError downstream rather than at resolver** — `DATA_FORMAT.md:254` (lens 1, info; first flagged 2026-05-02) — `yokosuka_sobu` has no `name_ja`/`name_en` at base; if referenced plain (no `.variant` suffix), the entry resolves without name fields → KeyError downstream. Today's data always uses variants for these slugs. Revisit when validator pass surfaces, or add explicit resolver guard.
- [ ] **`ueno_tokyo.tohoku` variant inherits non-IRL `name_ja`/`name_en`** — `data/lines.json:27` (lens 1, info; first flagged 2026-05-02) — IRL on JU-zone (Takasaki/Utsunomiya) the LCD typically labels by 宇都宮線/高崎線, not "Ueno-Tōkyō Line". Out of scope until first JU-zone station with `transfers` is added.

### From 2026-05-03 (transfer-info LowerDisplay hookup)

- [ ] **`_resolve_transfers` called twice per frame at LowerDisplay layer** — `displays/train_models/e235_1000/lower_lcd.py:_station_has_transfers` (lens 1, info; first flagged 2026-05-03) — Once for slot-membership decision in `_available_slots`, again on render in `TransferInfoDisplay.show_stops`. Reaches past underscore-prefix private boundary. Perf is fine (dict lookup + small list comps); cache once per frame at LowerDisplay level if needed.
- [ ] **Speculative `del current_time` in `_render`** — `displays/train_models/e235_1000/transfer_info.py:_render` (lens 2, info; first flagged 2026-05-03) — Comment says "animations may consume it later" but no concrete plan. Drop the param if no animations land within a few months.
- [ ] **`jump_to_stop`'s at_station semantics ambiguous for cross-stop jumps** — `displays/train_models/e235_1000/lower_lcd.py:_handle_at_station_edge` (lens 1, info; first flagged 2026-05-03) — When user click-jumps from STOPPING@A → STOPPING@B, `_prev_at_station` was already True so no rising edge fires → no force-switch to TRANSFER at the new stop. Mid-route → click-stop fires the edge correctly. User judgment needed on whether cross-stop jumps should also trigger TRANSFER.

### From 2026-05-04 (transfer-info per-N scaling)

- [ ] **`resolve_entry(ref, lines)` called 3× per render for the same slug refs** — `preview_transfers.py:172` (lens 1, info; vibe-check #1; first flagged 2026-05-04) — Line 172 (shinkansen count), line 312 (cat_order sort), per-badge at line 786. Cheap (no I/O). Pre-existing pattern doubled by 2026-05-04 PM edit. Per-N scaling block may be replaced under algorithm-redesign Step 1+2 work — no point optimizing throwaway code. Revisit when algorithm work resumes.
- [ ] **`_N >= 10` clause in dense-tier scaling is anticipatory** — `preview_transfers.py:175` (lens 1, info; principles.md § Implementation-completion-as-spec; first flagged 2026-05-04) — Max station N in current dataset is ~9; the `N >= 10` branch is uncalibrated. Defer until either (a) an N=10+ station enters the dataset, or (b) algorithm-redesign Step 1 formally calibrates the full ladder.

### From 2026-05-07 (E235-0 circular full-route + clock fine-tune)

- [ ] **Cycler-lock lambda fragility in preview** — `preview_display.py:200` (lens 1, info; first flagged 2026-05-07) — `sim.lower._tick_cycle = lambda current_time: None` and `sim.lower._handle_at_station_edge = lambda state, current_time: None` duplicate the bound-method signatures and will silently rot if those methods gain a parameter. Deferred because: preview-only; the clean fix would add a `_cycler_locked` boolean to the production `LowerDisplay` class for a preview-only feature.
- [ ] **Wrap-around minute undercount at loop terminal** — `displays/train_models/e235_0/lower_lcd.py:569` (lens 1, info; first flagged 2026-05-07) — `_compute_minutes_for_ahead` dedups by `sta_code`; when the duplicate JY24 marker at the loop terminal (Yamanote's `stops[0] = stops[-1]`) is skipped, its `time` value isn't credited to the next surviving entry's first-cumulative. Deferred because: dead in practice — IRL the wrap-back marker is `at_station=True` which uses the static branch.
- [ ] **CLOCK_RECT magic-number duplication** — `displays/train_models/e235_1000/upper_lcd.py:215` + `e235_0/upper_lcd.py:214` (lens 2, info; smell #5 within-file constant duplication; first flagged 2026-05-07) — `S_WIDTH - 170` and `80` repeat as both `CLOCK_RECT` const + inline `clock_x` / `clock_w` magic numbers in both `draw_clock` methods of each model. Deferred because: pre-existing pattern in e235_1000, not introduced by this session's diff. Worth a `/vibe-check` sweep to refactor inline references to `CLOCK_RECT.x` / `CLOCK_RECT.width`.

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

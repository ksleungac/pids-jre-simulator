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
- [ ] **Hook STOPPED badge state into the lower LCD.** When the auto-input detects the STOPPED badge (train at platform), surface that state on the lower LCD as a visible status indicator / "logged" element. **Two-step: change the display first, hook second** — figure out what the STOPPED state should look like on the lower LCD (per-train-model design choice) before wiring the auto-input STOPPED→display path. Status dict already publishes `badge` field on each capture, so hooking is just reading `sim.auto_input_status["badge"]` from the lower LCD's draw method.
- [ ] **Reduce screen-capture area to top-right ¼.** Today `dxcam.grab()` returns the full 2560×1440 desktop frame, then we crop. dxcam supports `grab(region=(left, top, right, bottom))` natively — restricting to the top-right quadrant `(1280, 0, 2560, 720)` cuts capture work by ~75% and the cropped frame is smaller for the HUD-region slicing too. HUD lives within that quadrant (HUD_BBOX = `(2200, 20, 350, 480)`). After this change, all cell-bbox math needs to shift from desktop-coords to quadrant-relative coords (subtract 1280 from x). Tighter region (e.g. just the HUD `(2150, 0, 2560, 520)`) is even faster but more brittle to recalibration. Background: prior experiments couldn't reliably scope capture to the *game window only* (DirectX swap-chain not visible to GDI per `AUTO_INPUT.md`); desktop-region capture is the realistic compromise.
- [x] **Drive recorder / blackbox — JSONL streaming + interactive HTML plot generator.** Both data-capture and plot-render done. `_recordings/drive_<line>_<diagram>_<TS>.jsonl` written by AutoDriver; `data_tools/plot_drive.py` renders a multi-section dashboard HTML with speed/STOPPED/PASSING bands, station signposts (start green, terminus red, middle accent blue), per-line brand-colour accent strip, schedule-style metric card, per-section stats. Open follow-ups below ↓
- [x] **Hook plot generator into the debug bar — "Report ↓" button.** Done 2026-04-28. Pill-styled button in the top-right of the OCR debug panel; click forwards through `app.py`'s MOUSEBUTTONDOWN handler to `auto_input.handle_panel_click`, which spawns a daemon thread that reads the live JSONL and renders HTML next to the project root. Re-runnable mid-drive (JSONL partial-write-safe — each click produces a fresh snapshot of progress so far).
- [ ] **Broader line-colour theme application.** Today the line colour shows on the top accent strip only. Could extend to: section number badges (`.section-num`), eyebrow text (`.page-eyebrow`), the speed line + fill in each chart. Add a luminance-aware adapter so pale brands (Sobu yellow `#FFD400`, Yamanote yellow-green) get darkened for stroke-readability while the brand strip stays vivid. Helper functions for hex→rgb, relative luminance (W3C), and darkening were drafted in this session and reverted; re-add when wiring.
- [ ] **OCR — stopping-position data.** The game's HUD shows the train's distance offset from the stop mark (`-12cm` / `+8cm` style — how precisely you stopped relative to the platform mark). New OCR cell + reader. Schema-add to JSONL: per-sample `stopping_offset_cm` (signed int). Display in plot: a "stopping accuracy" metric per arrival (the offset captured at the moment of `MOVING→STOPPED`); maybe a histogram or per-stop scorecard.
- [ ] **OCR — speed limit data.** The game's HUD also shows the current track speed limit. New OCR cell + reader. Schema-add: per-sample `speed_limit_kmh` (int|null). Plot enhancement: overlay the speed limit as a dashed line on top of the speed trace — over-limit segments become visually obvious (speed line above the limit line).

## Display / LCD fidelity

- [ ] **New train models — re-skin work, not re-architecture.** Priority order: E235-0 Yamanote (lowest-modification re-skin, leaning next), then E231-500, then E233 series. Each model lives under `displays/train_models/{model}/`. (CLAUDE.md § "Mental Model — Direction of travel".)
- [ ] **ENGLISH lower-LCD.** Still a stub — falls back to Japanese rendering. View-cycler timer already ticks regardless of language mode, so wiring an English renderer should be additive. (`memory/2026-04-25.md` § "Open follow-ups".)
- [ ] **`code_3` (3-letter Roman badge) edge cases.** Catalog is finite (~22 stations). General polish around fonts / placement / fallback for stations without a code. (CLAUDE.md § "Direction of travel".)
- [ ] **Continuity-arrow reconciliation** between the 8-station view's reserved-space arrows (`side_margin = 44`) and the user's existing buggy full-route helper. `JapaneseEightStationDisplay._draw_continuation_marker` is defined-but-deliberately-uncalled, awaiting that review. (`memory/2026-04-25.md` § "Open follow-ups".)
- [ ] **Interactive lower LCD — click station icon to jump.** Hit-test on the lower LCD's station cells; clicking a station calls `app.state.curr_stop = <clicked_idx>` (with the cnt_pa / skip / departure_time housekeeping). Doubles as the **manual resync mechanism for OCR**: when the auto-driver's segment-start anchor and the simulator's `curr_stop` desync (route reload, manual jump, OCR misfire), the user clicks the right station and the auto-driver's existing mismatch-skip logic re-anchors on the next sample. Station hit-test rects available in both full-route and 8-station views — adapt to whichever is currently rendered.

## Distribution

Speculative side-quest from the future-direction discussion. Competing for budget against further auto-input polish. (CLAUDE.md § "Direction of travel".)

- [ ] **Signed Windows installer.** Replace the zip-extract distribution with a proper signed installer for the lightly-public audience.
- [ ] **Mac build investigation.** Confirm whether pygame + win32-only deps (e.g. `keyboard` library, `win32gui`, `dxcam`) can be cleanly excluded behind `sys.platform == "win32"` guards.
- [ ] **First-run smoothness.** Whatever needs polishing for the ~1800 video-play / occasional-railfan audience.

## Housekeeping (small, do-when-you-touch-the-area)

- [ ] **Delete iteration screenshots from project root** once eyeballed: `screenshot_v1_setup_off.png`, `screenshot_v1_setup_on.png`. They're gitignored but cluttering. (`memory/2026-04-27.md` § "Status for next session".)
- [ ] **Decide 1b debug-frame dump behaviour.** `data_tools/capture_game.py:320` saves a HUD crop every sample interval to `_experiments/live_captures/`. Gitignored, but disk spam if 1b runs long. Options: leave (debugging tool), gate behind `--save-frames` flag (default off), or remove. (Discussed 2026-04-27, deferred.)
- [ ] **Re-grab `passing_en.png` at native 2560×1440.** Current capture is 2559×1439 — pygame blit handles it, classifier diff=0.00, but a clean re-capture is tidier.

---

## Closed-off paths (don't re-propose)

Recording the ground we've explicitly decided NOT to walk, so future sessions don't re-litigate:

- **Memory hooking the game's `*saf.dll` modules.** Tried, dead end.
- **Decrypting SimDATA assets.** Encrypted; not pursuing.
- **Audio fingerprinting** for stop detection. Replaced by HUD OCR which works.
- **Full-desktop OCR** instead of window-bound capture. Privacy + perf concerns.
- **Tesseract-based OCR.** Too heavy; pixel-perfect template match works.
- **Scaling to lines the game already covers** (Sobu local, Yokosuka, etc. — newer game routes ship with PA, don't duplicate).
- **OCR-as-display-layer fidelity-purity argument.** OCR is an *input layer* (replaces PageDown press), not display. Don't recycle.

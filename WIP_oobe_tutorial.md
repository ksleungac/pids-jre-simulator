# WIP: OOBE Tutorial — implementation plan

Pending design for the first-run tutorial that follows the language picker. Captures decisions from the 2026-04-29 OOBE discussion. Status: plan, awaiting /review+fix and user sign-off before implementation.

---

## Goal & scope

Teach a new user the **manual** usage flow of the simulator (no OCR feature) via a hands-on tutorial that runs immediately after the language picker, before the setup screen. Tutorial runs the real simulator on **tokaido/1865E**, boots at **国府津 (idx 13)** via `jump_to_stop`, and walks the user through one full press cycle (国府津 → 鴨宮) plus a click-to-jump demo.

**Out of scope** (deferred / later):
- OCR Auto-PA teaching — has its own pending TODO (first-run OCR warning + intro screen).
- Game-pairing screenshots — slots reserved in step content; user provides later.
- ZH-HK / ZH-CN tutorial strings — EN only for v1; flow refines first, then translation.
- Display-cycling passive observation step — user dropped per discussion.
- Mid-tutorial click-to-jump — locked except in dedicated step 8.

---

## Flow & gating

```
main.py:
  picker (if no language saved)
  → OOBE tutorial  (if not settings["oobe_completed"])
  → setup screen
  → app.run()
```

- New settings field: `settings["oobe_completed"]: bool`. Default missing/False → run tutorial. Set True only on tutorial [Done] or [Skip Tutorial].
- Existing users (have `language` set, no `oobe_completed`) → see tutorial once on next launch.
- Setup screen gains a small `?` icon top-right (only visible when `oobe_completed=True`); click → re-runs tutorial; on completion, returns to setup. Re-trigger does **not** unset `oobe_completed` on disk.
- Tutorial outcome (Done / [Skip Tutorial] / window-close / asset-missing) all set `oobe_completed=True` so the user isn't re-prompted on next launch. The replay affordance is the "? Tutorial" button on the setup screen. (Earlier draft said window-close kept `oobe_completed=False` — superseded; "set True regardless" wins.)

---

## Window & layout

**Tutorial owns its own pygame window**, sized **1100×500**:

```
┌─────────────────────────────────────────────────────────┐  40px
│ progress bar — 7 phase cells, current highlighted        │
├──────────────────────────────────┬──────────────────────┤
│  LCD region (730×420)            │  Side panel (370×420) │
│  ┌────────────────────┐          │  ┌──────────────────┐ │
│  │ UPPER LCD          │          │  │ Step N of 9      │ │
│  ├────────────────────┤          │  │ Title            │ │
│  │ LOWER LCD          │          │  │ Body text        │ │
│  └────────────────────┘          │  │ (game ss slot)   │ │
│                                  │  │                  │ │
│  callouts (overlay)              │  │  ◀ Back  Next ▶  │ │
│                                  │  │  Skip step       │ │
│                                  │  │  Skip tutorial   │ │
│                                  │  └──────────────────┘ │
└──────────────────────────────────┴──────────────────────┘  40px footer for buttons
```

- LCD blits to sub-surface at `(0, 40, 730, 420)`.
- Side panel `(730, 40, 370, 420)`.
- Buttons live in the bottom of the side panel.
- Callouts (small outlined-box + arrow line to a region) overlay the LCD area as needed.
- Background: lifted slate `(62, 68, 80)` matching setup/picker palette.
- **LCD region is live throughout** — sim runs continuously, mode cycler ticks, lower view alternates, audio plays during action steps. Step 1 and step 9 (wrap-up) keep the LCD at 国府津 STOPPING (where boot left it / where step 8 click-jump landed); the side panel's wrap-up content sits next to a still-live LCD. (No special "blank" state.)
- **Progress bar during steps 8 & 9:** all 7 phase cells rendered dim (post-cycle complete); no cell highlighted. Optional checkmark or "✓" overlay on each cell to convey "you've completed the cycle." Vibe-pass during implementation.

**On tutorial exit**, the 1100×500 window is destroyed; main flow proceeds to setup with its native 730×420 window.

---

## Step content (9 steps total)

Boot: `PASimulator` instantiated on tokaido/1865E, `jump_to_stop(13)` lands STOPPING@国府津. Tutorial in step 1.

### Progress bar phase mapping

```
🚉 At station → 🔔 Pre-departure → 🎵 Departure melody → 📢 Departed → 🚆 Train Driving → 📢 Approaching → 🚉 Approached
```

Steps 1–7 each illuminate exactly one phase cell. Step 8 illuminates none (post-cycle). Step 9 is wrap-up panel.

### Step table

| # | Phase | Action expected | Predicate (enables [Next]) | Side-panel body |
|---|---|---|---|---|
| 1 | 🚉 At station | none | passive — [Next] always | "You're at 国府津. The 'ただいま' prefix on the upper LCD = currently at the platform. The pentagon on the lower LCD shows your position." |
| 2 | 🔔 Pre-departure | `PageDown` | PA audio finished | "Press `PageDown` to play the at-platform announcement. The yellow hint square means there's more than one PA queued — press again to hear them all." |
| 3 | 🎵 Departure melody | `PageUp` | STA audio finished | "Press `PageUp` for the 発車メロディ (departure melody). IRL this signals the doors are about to close. (Game-pairing slot.)" |
| 4 | 📢 Departed | `PageDown` | dep PA (`pa[0]`) audio finished | "Press `PageDown`. The train departs 国府津 and announces 鴨宮. Watch the prefix change to '次は' (next stop)." |
| 5 | 🚆 Train Driving | none | passive — min 5s dwell, then [Next] | "The countdown on the lower LCD ticks down toward 鴨宮 in real-time at 60× speed. Watch the red arrow walk through the cells." |
| 6 | 📢 Approaching | `PageDown` | arr PA (`pa[1]`) audio finished | "Press `PageDown`. The prefix flips to 'まもなく' (final approach) — always the last announcement before a stop." |
| 7 | 🚉 Approached | `PageDown` | sim lands STOPPING@鴨宮 | "Press `PageDown` once more. The train arrives at 鴨宮; the cycle repeats every stop." |
| 8 | (post-cycle, no phase) | click any lower-LCD station | click → `jump_to_stop` fired | Pre-click: "You don't have to ride the whole route. Click any station on the lower LCD to jump there. Try it." Post-click (dynamic): "Nice — you just jumped to {station_kanji} ({station_english if available, else omit}). The cycle restarts there." |
| 9 | wrap-up panel | none | [Done] | Cheat-sheet: `PageDown`=PA, `PageUp`=STA, `End`=pause, `Esc`=quit, click-station=jump. (Game-pairing slot table.) |

### Step 5 minimum dwell

[Next] grays out for the first 5s **measured from step-5 entry time** (`step_entered_at`) so the user actually sees the countdown move. After 5s, [Next] enables. No max — they can keep watching.

### Step 4 / 6 audio completion

`pa[0]="25"` already played before tutorial boot (国府津 had been approached). The tutorial uses `pa` of **国府津's next stop (鴨宮 idx 14, `pa=["29","30"]`)**:
- Step 4 fires the dep PA `29` (= "{国府津 を発車しました} 次は 鴨宮").
- Step 6 fires the arr PA `30` (= "まもなく 鴨宮").

This works because after 国府津 STOPPING + (forced pa_at_station exhaustion via step 2's [Next] handler — see below) + STA, the next `PageDown` calls `_advance_to_next_stop` (cnt_pa_at_station already at exhausted sentinel), advances curr_stop to 14 (鴨宮), `cnt_pa=0`, plays `pa[0]=29`. Following PgDn plays `pa[1]=30`. Following PgDn lands STOPPING@鴨宮 via `_next_in_approaching`'s pa-exhausted branch (`cnt_pa < len(pa)-1` False → at_station=True).

### 国府津's pa_at_station has 2 entries — predicate AND [Next] handler

`pa_at_station=["27","28"]`. Step 2 satisfies on **first audio completion** (one entry plays — keeps the step quick). User can press `PageDown` again to hear `28`; yellow square is visible throughout demonstrating the multi-PA hint.

**State-coherence requirement:** Step 2's [Next] click must silently force `sim.state.cnt_pa_at_station = len(pa_at_station) - 1` before transitioning. Otherwise: user hears only `27`, clicks [Next], proceeds to step 3 (STA, fine), then step 4's `PageDown` plays `28` instead of 鴨宮's `29` because the sim is still in pa_at_station-cycling state. Forcing cnt_pa_at_station to "exhausted" ensures the next non-STA `PageDown` triggers `_advance_to_next_stop`. (Pure state mutation, no audio fired.) Same logic applies if step 2 is Skip-Step'd (see "Skip step" below).

---

## Tutorial-state machine

Internal Tutorial class state:

```
TutorialState:
  current_step: int            # 1..9
  predicate_satisfied: bool    # gates [Next]
  step_entered_at: float       # for step 5's min-dwell
  state_stack: list[Snapshot]  # one per step entered, for [Back]
```

Per-step descriptor (declarative):

```
Step:
  phase: str | None            # progress bar cell, or None for step 8/9
  body_key: str                # i18n lookup
  callout_target: Region | None
  allowed_actions: set[Action] # {PgDn} / {PgUp} / {Click} / {} / {} (passive)
  predicate: Callable          # given sim/audio state → bool
  min_dwell_s: float = 0       # step 5 = 5.0
```

### Action lock-down

The tutorial owns its own pygame event loop (1100×500 window) and ticks the sim manually each frame — it does NOT call `sim.run()`. `PASimulator.__init__` accepts a new `tutorial=True` parameter that suppresses the keyboard-library polling path entirely (same pattern as `preview=True`); the tutorial's input arrives via pygame events only and is dispatched by the tutorial's filter.

The sim is driven by direct method calls — NOT via `pending_next_pa` (which is for AutoDriver's background-thread → main-loop pattern and is incompatible with the tutorial's own loop):

- Tutorial calls `sim._next_pa()` to fire a PA press.
- Tutorial calls `sim._next_sta()` (or equivalent) to fire an STA press.
- Tutorial calls `sim.jump_to_stop(idx)` for click-to-jump in step 8 and the boot-time positioning at idx 13.

Each frame, tutorial ticks the LCD render path in this exact order (verified against `sim.run()`):

```python
sim.state.update_skip_progress(ts)   # FIRST — mutates skip_progress that cursor_pos derives from
sim.upper.update(ts)
sim.upper.draw(time_str)
sim.lower.draw(ts)
# tutorial then draws side panel + callouts + progress bar to its own surface
# tutorial owns the parent-window pygame.display.flip()
```

The order matters: `update_skip_progress` must run before `lower.draw` so the cursor position is fresh that frame. Tutorial does NOT call `_render_panel()` (debug panel; auto_input only) or `_handle_input()` (real-app event loop) or `_update_hover_cursor()` (real-app; tutorial manages its own cursor for side-panel buttons).

Filter dispatches based on the active step's `allowed_actions`:

- Always allowed (side-panel handler): clicks on Back/Next/Skip-step/Skip-tutorial.
- Always allowed: window close (`QUIT`) → exit tutorial without setting `oobe_completed`.
- Always allowed (intercepted): `Esc` → confirm-quit modal → either ignore or trigger Skip-tutorial.
- Allowed per step's `allowed_actions`:
  - `K_PAGEDOWN` → tutorial calls `sim._next_pa()` if step allows. Multiple presses within a step are fine — sim cycles forward, predicate latches True on first audio completion. Press AFTER predicate-satisfied is rejected if it would cross a phase boundary (so Driving phase can't be skipped via spamming PgDn).
  - `K_PAGEUP` → tutorial calls `sim._next_sta()` if step allows.
  - `K_END` → `sim.audio.pause()` (always allowed; safety/comfort).
  - `MOUSEBUTTONDOWN` on lower-LCD area → tutorial computes hit-test via `sim.lower.hit_test(state, mx, my)` and calls `sim.jump_to_stop(target)` if step 8 (otherwise swallowed; renderer hover-cursor returns arrow not hand).
- Everything else → swallowed silently.

### Snapshot / restore (for [Back])

`AppState` is a plain class (NOT decorated with `@dataclass`), with scalar-only fields (verified at `app.py:18–47`). Snapshot via `copy.copy(sim.state)` (shallow is sufficient — no list/dict fields on AppState itself; any collections live on `PASimulator`, not on its `state`).

On step entry: push `Snapshot(state_copy=copy.copy(sim.state))` to stack. Restore on [Back]:

```python
sim.audio.stop()                              # truncate any in-flight audio
sim.state.__dict__.update(snap.state_copy.__dict__)  # restore scalar fields
predicate_satisfied = step_predicate(prev_step, sim) # re-eval; often True since user already acted
```

[Back] from step 1 is disabled. [Back] from step 9 (wrap-up) goes to step 8.

### Skip step

**Skip-step applies the step's underlying state mutation directly (no audio replay)** so the sim stays in the state downstream steps expect, without forcing the user to listen to audio they've explicitly skipped. Per-step skip-handlers:

| Step | Skip-handler |
|---|---|
| 1 (At station) | step++ (no sim mutation) |
| 2 (Pre-departure) | `state.cnt_pa_at_station = len(pa_at_station) - 1`; step++. Same idempotent force-set that the [Next] handler applies — works whether predicate was satisfied or not. |
| 3 (Departure melody) | step++ (STA is independent of cnt_* counters; skipping just doesn't play it). |
| 4 (Departed) | call `sim._advance_to_next_stop()` directly (state-only, since `_advance_to_next_stop` does play `pa[0]` audio — actually firing audio is unavoidable here; **resolved: accept the audio fires**, since state coherence requires the curr_stop advance + cnt_pa init that only `_advance_to_next_stop` provides). step++. |
| 5 (Train Driving) | step++ (passive). |
| 6 (Approaching) | call `sim._next_pa()` (fires arr `pa[1]=30` audio; same accept-audio rationale as step 4 — `_next_in_approaching` does the cnt_pa increment we need). step++. |
| 7 (Approached) | call `sim._next_pa()` (fires the pa-exhausted-branch transition into STOPPING@鴨宮; no audio since the branch doesn't call `play_pa`). step++. |
| 8 (Click-to-jump) | step++ (no jump applied; sim stays at 鴨宮 if user reached it cleanly, else wherever cycle left it). |

The mixed pattern (state-only for 2/3/5/7/8, audio-fires for 4/6) is acceptable — Skip-step is an escape hatch, not a hot path. [Back] after Skip restores the per-step snapshot regardless.

### Skip tutorial

Confirm-modal → if confirmed: jumps directly to step 9 (wrap-up panel) → [Done] sets `oobe_completed=True`.

---

## File-level changes

### New files

- **`tutorial.py`** — `Tutorial` class. Owns 1100×500 window, instantiates `PASimulator(tokaido/1865E, tutorial=True)`, drives the step machine, renders progress bar + side panel + callouts on top of LCD subsurface. ~300–400 lines.
- **`WIP_oobe_tutorial.md`** — this doc. Removed once shipped + memory entry written.

### Modified files

- **`main.py`** — between picker and setup, gate on `settings.get("oobe_completed", False)`; if False, run `Tutorial`. On Done/Skip, set `settings["oobe_completed"] = True` and `i18n.save_settings()`. Then proceed to setup. **Cleanup decision (resolved cycle 2 + 3): tutorial does NOT call `PASimulator.cleanup()`** — that method calls `pygame.quit()` (full subsystem teardown), which would invalidate the mixer + display + everything; the existing setup screen would then fail. Instead, tutorial teardown:
  1. `sim.audio.stop()` to silence any in-flight audio.
  2. `pygame.display.set_mode((730, 420))` to switch the window back to setup's expected size.
  3. Drop the `sim` reference (Python GC handles the AudioPlayer finalizer harmlessly — see `audio.py` change below).

  Pygame mixer + display remain initialized for the setup screen and main app to inherit. `PASimulator.cleanup()` is reserved for full app exit (called from `main.py`'s `finally` block).
- **`audio.py`** — remove the `mixer.quit()` from `AudioPlayer.__del__` (or remove the `__del__` finalizer entirely; cleanup is called explicitly on app exit). Today `__del__` calls `self.cleanup()` → `mixer.quit()`, which would fire at GC time when the tutorial drops its sim reference, tearing down the mixer the setup screen + main app are about to use. Fix: `__del__` either becomes `self.stop()` only, or is deleted (relying on explicit `PASimulator.cleanup()` → `audio.cleanup()` on app exit, which is the only place teardown actually needs to happen). **Lean: delete `__del__`.** Finalizers calling subsystem-quit functions are fragile in general — this is a correctness fix beyond just the tutorial use case.
- **`app.py`** — three additions:
  1. `PASimulator.__init__` accepts optional `tutorial=False` flag (matches existing `preview` and `auto_input` parameter shape). When True, suppresses the keyboard-library polling path in `_handle_input_main` (selecting a pygame-events-only path equivalent to `_handle_input_preview` semantics) so the tutorial's filter has full control.
  2. `PASimulator.snapshot_state()` and `restore_state(snap)` methods. Implementation: `snapshot = copy.copy(self.state)`; restore = `self.state.__dict__.update(snap.__dict__)` + `self.audio.stop()`. Scalar-only fields verified.
  3. The window/surface handoff: `PASimulator` accepts an optional `target_surface` so the tutorial can render the LCD into a sub-surface of its 1100×500 window. Today `app.py` calls `pygame.display.set_mode((730, 420 + panel_h))`; refactor to use the provided surface if non-None, else create its own. **Verify scope before implementing** — `display.flip()` calls happen inside renderers; with a sub-surface, the tutorial owns the flip on the parent window. Renderers may need to skip flip when running under tutorial.
- **`setup.py`** — top-right **"? Tutorial"** labeled button (text, not icon-only), only renders when `oobe_completed=True` per settings. Click → `setup.run()` returns `{"action": "run_tutorial"}` (a typed-action dict). Existing return becomes `{"action": "select", "config": {...}}` (or stays `dict` with action key added; `main.py` dispatches on the action key). New i18n key: `setup.tutorial_button` ("? Tutorial" in EN). Title centering currently uses screen-width // 2 with no right-edge reservation — flag for visual-adjust pass to ensure the labeled button doesn't visually collide with the centered title at 730px width.
- **`i18n.py`** — no API changes. New keys consumed via `t()`.
- **`data/translations_app.json`** — ~35–45 new EN-only keys broken down as: 7 phase names, 9 step titles, 9 step bodies, 5 button labels (Next/Back/Skip step/Skip Tutorial/Done), 2–3 confirm-modal strings, 2–3 chrome strings ("Step N of 9", "Welcome to the tutorial", etc.). ZH-HK / ZH-CN slots left as `null` or absent; `t()` already falls back to EN. Add note in `_comment` flagging tutorial keys as EN-only-pending until flow is finalized.

### Not modified (verify during implementation)

- `displays/` — tutorial uses LCD as-is. No display changes.
- `auto_input.py` — tutorial doesn't run in auto_input mode.
- `audio.py` — tutorial uses existing `is_playing()` to gate predicates. **Verify** `is_playing` returns False as soon as the audio file ends, not just on explicit stop. (Pygame mixer behavior — `pygame.mixer.music.get_busy()` should suffice.)

---

## Implementation order

All draw methods in `tutorial.py` must use the **tuneable-params block** convention (`.claude/rules/conventions.md` § "UI code style"): magic numbers as labeled local variables at the top of the method, downstream coordinates derived from them. Apply at every step below that touches draw code.

1. **Refactor `app.py` for surface/window handoff + snapshot/restore.** Smoke test by running normally — must be a pure refactor with zero behavior change. Verify `AppState` field-list is still scalar-only; verify `audio.stop()` semantics; verify mixer init/cleanup ordering survives. Snapshot/restore is technically reusable infra, but its only consumer is the tutorial — keep scoped to this PR.
2. **Build `Tutorial` skeleton in `tutorial.py`** — window, progress bar, side panel chrome, button rects, all in tuneable-params blocks. No steps yet. Smoke test: shows blank progress bar + dummy LCD + dummy side panel.
3. **Wire LCD subsurface render path.** Tutorial owns a `PASimulator(tutorial=True, target_surface=lcd_subsurf)`, ticks it each frame manually (mirroring `sim.run()`'s render path minus event ownership). Verify LCD renders inside the 1100×500 window at the right offset.
4. **Startup-failure handling.** If `audio/tokaido/1865E/route.json` is absent (no-audio build, user deleted, etc.), tutorial logs a warning, sets `oobe_completed=True` (so we don't re-prompt every launch), and returns immediately to main.py which proceeds to setup. Same for `pa/27.mp3` etc. — if any file required by the cycle is missing, abort tutorial gracefully.
5. **Step machine + step descriptors for steps 1–9.** Body strings stubbed (`"step 1 body"`). Test step transitions manually via [Next]/[Back]/[Skip step].
6. **Predicates + audio-completion gating.** Wire `mixer.music.get_busy()` polling each tick. Test that [Next] grays/un-grays correctly. Step 2's [Next] handler also force-sets `cnt_pa_at_station = len(pa_at_station) - 1`.
7. **Action lock-down filter.** Test that PgDn in step 1 is swallowed, PgDn in step 2 fires the PA via direct `sim._next_pa()` call.
8. **Snapshot/restore on [Back].** Test backing from step 4 to step 3 — sim state restores, audio stops.
9. **Skip-step "execute behind scenes."** Verify state coherence: skip step 2 → cnt_pa_at_station correct; skip step 4 → 鴨宮 pa[0] fired; etc.
10. **Step 5 min-dwell timer.**
11. **Callout overlay primitives.** Outlined-box + arrow line; positioned via per-step `callout_target` region. (Vibe first per user.)
12. **Wire `?` button on setup.py + action-key return.** Tag with visual-adjust pass for title-collision check.
13. **i18n keys — EN authoritative; tag tutorial keys in `_comment` as EN-only-pending.**
14. **Smoke test full happy path** end-to-end: picker → tutorial steps 1–9 → setup → app. Plus failure paths: no audio, mid-tutorial close, [Skip Tutorial] from intro.
15. **Run /review+fix on the implementation.**

---

## Open questions for review

Resolved during /review+fix cycle 1 (kept here for traceability):

- ~~**Skip-step semantics** — execute behind the scenes vs no-op?~~ **Resolved: execute behind the scenes.** State coherence requires it; downstream step bodies stay truthful.
- ~~**Snapshot field types** — dataclass.replace?~~ **Resolved: `AppState` is a plain class (not `@dataclass`), all scalar fields. Use `copy.copy()`; `__dict__.update()` for restore.**
- ~~**`audio.is_playing()` precision** — latency?~~ **Resolved: `mixer.music.get_busy()` returns False immediately on clip end; at 15 FPS the predicate fires within ~67 ms, invisible.**
- ~~**Step 7 predicate viability**~~ **Resolved: `_next_in_approaching` falls through to STOPPING@鴨宮 via the pa-exhausted branch on the last PgDn; predicate `state.curr_stop == 14 AND at_station == True` is reached cleanly.**

Still open: none. All design Qs resolved through cycles 1–3.

Resolved post-cycle-3:
- ~~Re-trigger button affordance~~ → labeled button "? Tutorial" top-right of setup.
- ~~Step 8 click-to-jump constraints~~ → accept any station; tutorial responds dynamically with "Nice — you just jumped to {station}." Reads `sim.stops[sim.state.curr_stop]["name"]` (kanji) + optional English from `data/translations.json`.

---

## Refinements (post-implementation, 2026-04-29 → 2026-04-30)

Original plan above is preserved for traceability. The points below supersede it where they overlap.

### Progress bar — stepper, not phase-cell row
- 7 phase cells → **9 numbered circles** on a connecting line, labels below. Phase 8 = "Click jump", phase 9 = "Recap" (steps 8 / 9 are no longer post-cycle-dim — they're regular phases with their own active state).
- Completed = filled `ACCENT_COLOR`; current = filled `ACCENT_COLOR` + bright outer ring (`ACCENT_BRIGHT`); future = `DOT_FUTURE` slate. Connecting line: `LINE_DIM` base, `ACCENT_COLOR` overlay through completed segments.
- **Phase columns are click targets** — clicking a phase jumps to that step. Forward jumps run intermediate `skip_handler`s via `_skip_step` (so state stays coherent); backward jumps restore the snapshot taken on entry to the target step (same mechanic as [Back], multi-step).
- `PROGRESS_H` grew 40 → 64 to fit circles + labels.

### Panel header — phase name, not "Step N of 9"
- Header line is now the phase name (matches the progress-bar label for the current step).
- Old "Step N of 9" demoted to a small dim subtitle line under the header.
- On the wrap-up step (no skip buttons), the primary [Back] / [Done] row drops to the panel bottom — frees the body's vertical budget for the cheat sheet.

### Body / action split
- Each step's translation now has TWO keys: `tutorial.step.{n}.body` (explanation) + `tutorial.step.{n}.action` (the "do this" prompt).
- Body renders in `TEXT_COLOR`; action renders in `ACCENT_BRIGHT` with a small left-side accent stripe — visual callout without a horizontal divider.
- Step 8 has post-click variants of both (`body_after_click` + `action_after_click`).

### Inline keycap rendering
- Body strings use `[[KeyName]]` markup; the run-splitter (`_split_runs`) now yields three kinds: Latin / CJK / keycap.
- Keycap visual: **sunken slate chip** — fill darker than panel bg (`(38, 44, 56)`), thin cool-gray border (`(148, 158, 178)`), soft white text. Inline-`<kbd>` aesthetic, no fake-3D shadow strips.
- Used for both keyboard keys (`[[PgDn]]`, `[[PgUp]]`, `[[End]]`, `[[Esc]]`) and side-panel button names (`[[Next]]`, `[[Done]]`).

### Font swap — bundled OTFs, mixed-script renderer
- Chrome no longer uses `pygame.font.SysFont("microsoftjhenghei", ...)`. SysFont JhengHei tofu'd Latin Extended-A glyphs (macron `ō` in `Kōzu`); the bold variant dropped even more.
- Now uses bundled `HelveticaNeue-Roman/Medium/Bold.otf` for Latin (incl. macrons) and `ShinGoPr6N-Medium/Heavy.otf` for CJK.
- `_render_mixed(text, latin_font, cjk_font, color)` splits into runs and concatenates with baseline alignment via `font.get_ascent()`. `_measure_mixed` mirrors it for word-wrap width measurement.
- `_draw_wrapped_text` updated to take both fonts.

### State-jump convention — pause audio + reset state
- Every state transition in the tutorial pauses (not stops) in-flight audio first. This silences the soundtrack but keeps the mixer warm; it also clears `_next_pa`'s audio guard so skip-chains advance state cleanly even when previous-step audio is still playing.
- Applied at:
  - `_enter_step(n)`: `audio.pause()` → run target step's `entry_handler` → snapshot.
  - `_skip_step()`: `audio.pause()` → `skip_handler` → `_advance_step`.
  - `_dispatch_action` ACT_CLICK: `audio.pause()` → `sim.jump_to_stop(target)`.
- `app.py:PASimulator.restore_state` switched `audio.stop()` → `audio.pause()` for consistency.

### Step.entry_handler — deterministic step entry state
- New field on `Step` descriptor: `entry_handler: Callable[Tutorial, None]`. Runs inside `_enter_step` AFTER the audio pause and BEFORE the snapshot — the snapshot captures the post-handler state, so future [Back] also lands on the canonical state.
- **Step 8** is the only consumer: `_entry_step8` calls `sim.audio.pause() + sim.jump_to_stop(14)` to force STOPPING @ Kamonomiya regardless of how the user got here. Skip-paths that left state lagging are no longer a concern for step 8's demo.

### Step 2 — PgDn capped at pa_at_station length
- `lock_after_first_action=False` on step 2 (multi-press allowed for both at-station entries).
- Inline guard in `_dispatch_action`: once `cnt_pa_at_station >= len(pa_at_station) - 1`, the dispatcher swallows further PgDn before it reaches `_next_pa`. Otherwise the press would fall through to the pa-exhausted branch and advance to the next stop — that's step 4's job, not step 2's.

### Step 8 specifics
- `lock_after_first_action=False` — user can click as many stations as they want; predicate `_pred_step8_clicked` just needs `_action_in_step` set once.
- Each click pauses audio + jumps; entry_handler force-resets to Kamonomiya STOPPING.
- Side-panel **station example card**: `_draw_station_illustration` mirrors a route-bar cell (kanji + romaji), hides after first click. Border **flashes** via a sine cycle between `ACCENT_COLOR` and `ACCENT_BRIGHT` (1.2 s period).
- LCD callout outline (originally added) **removed pending a better design** — `_draw_callout` now only honors `Step.callout_rect` (still unset on all steps).

### Step 1 wording — `ただいま` gloss corrected
- Old: `'ただいま' = 'currently at the platform'`.
- New: `'ただいま 国府津' on the upper LCD reads 'Now Stopping at Kōzu'` — closer to the actual PIDS semantic.

### preview_tutorial.py
- Now imports `STEPS` and invokes `STEPS[step - 1].entry_handler(tut)` after sim boot — so step 8 preview shows Kamonomiya STOPPING (matching runtime).
- Now mirrors `_tick_sim`'s final overlay step (`tut._draw_callout()`) so step-specific callouts appear in screenshots.
- `--pre-action` flag (NEW): renders the pre-action UI state — needed to capture step 8's flashing example card before the spoofed `_action_in_step=True` hides it.

### Still open / next iteration

- Steps 3 / 4 / 5 / 6 / 7 / 9 wording — same body+action split, but copy hasn't been reviewed yet (only steps 1, 2, 8 sweep'd).
- Step 8 LCD callout — needs a clearer "click these station cells" cue. Maybe a subtle chevron animation, individual cell highlight, or a connector line from the side-panel example to a real cell. Deferred.
- ZH translations — still EN-only.
- Game-pairing screenshot slots in step 3 / 6 / 9 bodies.
- ESC confirm-quit modal (TODO comment in `_handle_events`).

---

## Acceptance criteria

- New launch (no `settings.json`): picker → tutorial → setup → app, all in sequence.
- Existing user: `language` saved, no `oobe_completed` → tutorial runs once on next launch.
- After completion: `oobe_completed=True` persisted; subsequent launches go picker (skipped if language saved) → setup directly.
- `?` button on setup re-runs tutorial; doesn't unset on-disk `oobe_completed`.
- All 9 steps reachable, [Back] restores sim state correctly, [Skip step] / [Skip tutorial] / window-close don't crash or persist incorrect state.
- Audio plays correctly at every PA/STA-firing step; [Next] gates on audio completion.
- Action lock-down: pressing the wrong key swallows silently (no audio, no state change, no flash).
- LCD renders pixel-identical to standalone preview when shown inside the tutorial window.
- /review+fix passes (target: 2 cycles).

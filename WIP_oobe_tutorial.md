# WIP: OOBE Tutorial — design notes (post-implementation, refining)

Living doc for the first-run tutorial. Original plan landed via /review+fix in 3 cycles; this doc has been edited down to the parts still load-bearing for ongoing refinement. Step-by-step body/action copy and visual polish are still in flight — see "Open refinement items" at the bottom.

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

Tutorial owns its own pygame window, **1100×500**. Layout (current code, see `tutorial.py` for tuneable params):

- **Top strip (`PROGRESS_H = 64`)**: 9-circle stepper with connecting line + labels below each circle. Circles 1–7 are the audio cycle phases (At station / Pre-departure / Departure melody / Departed / Driving / Approaching / Approached); circles 8–9 cover the click-jump demo + recap. Each phase column is a click-target — clicking jumps to that step (forward via `_skip_step` chain, backward via snapshot restore).
- **LCD subsurface `(0, PROGRESS_H, 730, 420)`**: live sim renders here every frame.
- **Side panel `(730, PROGRESS_H, 370, 436)`**: phase-name header + small "Step N of 9" subtitle + body text + (step 8) flashing station-example card + action prompt (accent-green with left stripe) + button stack at the bottom (Back / Next, then Skip step / Skip tutorial below — both skip rows hidden on the wrap-up step so the recap body has full vertical budget).
- **Background** = lifted slate `(62, 68, 80)`, matching picker / setup chrome.
- LCD region is live throughout; mode cycler ticks, lower-view alternation runs, audio plays during action steps.

On tutorial exit: stop in-flight audio, drop the sim ref (no `cleanup()` — that calls `pygame.quit()`), `pygame.display.set_mode((730, 420))` to hand the window back to the setup screen.

---

## Step machine

Boot: `PASimulator(work_dir="audio/tokaido/1865E", tutorial=True, target_surface=lcd_subsurface)`, then `jump_to_stop(13)` lands STOPPING@国府津.

Step content lives entirely in `data/translations_app.json` under `tutorial.step.{n}.body` + `tutorial.step.{n}.action` keys (step 8 also has `body_after_click` + `action_after_click` variants). Phase labels live under `tutorial.phase.{name}`. EN-only pending flow finalization.

### Step descriptor (`tutorial.py:Step`)

Frozen dataclass. Per-step fields:
- `n: int` — 1..9
- `phase_idx: int | None` — progress-bar circle index (currently 0..8 for all steps)
- `allowed: frozenset[str]` — subset of {`pgdn`, `pgup`, `click`}
- `predicate: Callable[Tutorial, bool]` — gates [Next]
- `next_handler` — runs on [Next], BEFORE advancing (e.g. step 2's pa_at_station exhaustion)
- `skip_handler` — runs on [Skip step], BEFORE advancing
- `entry_handler` — runs inside `_enter_step` AFTER `audio.pause()` and BEFORE the snapshot. Used for steps that need a deterministic starting state regardless of inbound path. Currently only step 8 (`_entry_step8`: `audio.pause()` + `jump_to_stop(14)`).
- `min_dwell_s: float` — step 5 = 5.0; gates `_pred_min_dwell`
- `lock_after_first_action: bool` — True for steps where chained presses would cross a phase boundary; False for step 2 (multi-press through `pa_at_station`), step 3 (STA can be replayed), step 8 (multi-click jumps).
- `callout_rect: tuple | None` — optional LCD-local outline. Currently unset on every step (step 8's route-bar callout was prototyped then removed — see Open items).

### State-jump convention

Every state transition pauses (not stops) in-flight audio first, then mutates state. This silences the soundtrack but keeps the mixer warm; it ALSO clears `_next_pa`'s audio guard so skip-chains advance cleanly even when previous-step audio is still playing.

Applied at three sites:
- `_enter_step`: `audio.pause()` → `entry_handler(tut)` → snapshot.
- `_skip_step`: `audio.pause()` → step's `skip_handler` → `_advance_step` (which runs `next_handler` + `_enter_step(n+1)`).
- `_dispatch_action` ACT_CLICK: `audio.pause()` → `sim.jump_to_stop(target)`.

`PASimulator.restore_state` (used by [Back]) also pauses (was `audio.stop()`).

### Step 2 — pa_at_station cap

`国府津.pa_at_station = ["27", "28"]`. Step 2 allows multi-press (`lock_after_first_action=False`) so the user can hear both. **Inline guard in `_dispatch_action`:** once `cnt_pa_at_station >= len(pa_at_station) - 1`, further PgDn is swallowed before reaching `_next_pa`. Otherwise the press would fall into the pa-exhausted branch and advance to the next stop — that's step 4's job, and it'd create a state mismatch with the panel telling the user they're still pre-departure.

`next_handler` (and `skip_handler`) for step 2 force-set `cnt_pa_at_station = len - 1` so that step 4's PgDn correctly triggers `_advance_to_next_stop` even if the user only listened to the first entry.

### Step 4 / 6 / 7 cycle

After step 2 + step 3 (STA — independent of cycle counters), the train is still STOPPING@国府津 with `cnt_pa_at_station` exhausted.
- Step 4 PgDn → `_advance_to_next_stop` fires `pa[0]="29"` ("国府津を発車しました 次は 鴨宮"); curr_stop=14, cnt_pa=0.
- Step 5 = passive 5s dwell to watch the countdown move.
- Step 6 PgDn → `_next_pa` plays `pa[1]="30"` ("まもなく 鴨宮"); cnt_pa=1.
- Step 7 PgDn → `_next_pa` falls into STOPPING@鴨宮 via the pa-exhausted branch (no audio).

### Step 8 — click-jump demo

Entry handler forces STOPPING@鴨宮 regardless of inbound state. Side panel shows a flashing station-example card (`_draw_station_illustration`, sine-pulse border between `ACCENT_COLOR` and `ACCENT_BRIGHT` over 1.2 s; hides after first click). User can click any visible station — each click pauses audio + `jump_to_stop(target)`. Predicate `_pred_step8_clicked` just needs `_action_in_step` set once.

### Step 9 — recap

Wrap-up panel. Body = quick-reference cheat sheet using `[[Key]]` markup; action = "Press [[Done]] to finish." Skip buttons hidden — primary [Back]/[Done] row drops to bottom.

---

## UI rendering

### Mixed-script + keycap renderer

Chrome uses bundled OTFs, not `pygame.font.SysFont`:
- `HelveticaNeue-Roman/Medium/Bold.otf` for Latin (covers macron `ō` etc., which SysFont JhengHei tofu'd).
- `ShinGoPr6N-Medium/Heavy.otf` for CJK glyphs.

`_render_mixed(text, latin_font, cjk_font, color)` splits text into Latin / CJK / keycap runs and concatenates with baseline alignment via `font.get_ascent()`. `_measure_mixed` mirrors it for word-wrap.

Body strings can embed `[[KeyName]]` markup; the run-splitter (`_split_runs`) yields a `RUN_KEYCAP` segment which renders via `_render_keycap(label, font)`. Keycap visual = sunken slate chip (fill darker than panel bg, thin cool-gray border, soft white text); used for both keyboard keys (`[[PgDn]]`, `[[Esc]]`) and side-panel button names (`[[Next]]`, `[[Done]]`).

### Body / action split

Each step has TWO i18n keys:
- `tutorial.step.{n}.body` — explanation, rendered in `TEXT_COLOR`.
- `tutorial.step.{n}.action` — "do this" prompt, rendered in `ACCENT_BRIGHT` with a small left-side accent stripe.

Step 8 has post-click variants (`body_after_click` + `action_after_click`).

### Snapshot / restore (for [Back] and progress-bar backward jumps)

`AppState` is a plain class with scalar-only fields (verified at `app.py:18–47`). Snapshot via `copy.copy(sim.state)` (shallow is sufficient).

Snapshots are taken inside `_enter_step` AFTER `audio.pause()` + `entry_handler` so the saved state matches the canonical step-entry state. Restore via `PASimulator.restore_state(snap)` → `audio.pause()` + `state.__dict__.update(snap.__dict__)` + `upper.set_state(...)` to re-bind the upper LCD's cached fields.

[Back] from step 1 is disabled. Progress-bar backward clicks restore from the target step's snapshot directly (multi-step [Back]). Forward clicks run intermediate `_skip_step`s in a loop.

### Skip step

Each step's `skip_handler` applies the underlying state mutation so downstream steps stay coherent. Mixed pattern (state-only for steps 2/3/5/7/8, audio-fires for steps 4/6) — Skip-step is an escape hatch, not a hot path. [Back] after Skip restores via snapshot regardless. The audio.pause at the top of `_skip_step` clears `_next_pa`'s audio guard so chained skips with audio in flight don't silently no-op.

### Skip tutorial

Jumps directly to step 9 (no confirm-modal yet — TODO).

---

## Action filter (lock-down)

The tutorial owns its own pygame event loop and ticks the sim manually; `PASimulator(tutorial=True)` suppresses the keyboard-library polling path. All input arrives via pygame events and is dispatched by `_dispatch_action` (or `_handle_panel_click` / `_handle_progress_click` for chrome).

`_dispatch_action(action)` dispatches the user's action only when:
1. `action in step.allowed`
2. Not (`step.lock_after_first_action and self._action_in_step`)
3. Sim is alive
4. Step-specific guards pass (currently only step 2's `cnt_pa_at_station >= len-1` cap)

Actions:
- `pgdn` → `sim._next_pa()`
- `pgup` → `sim._next_sta()`
- `click` → `audio.pause()` + `sim.jump_to_stop(target)` (target via `sim._click_target(lcd_x, lcd_y)`)

Window close (`QUIT`) and `Esc` exit the tutorial. `K_END` always pauses audio.

---

## Open refinement items

- **Step bodies + action wording** for steps 3 / 4 / 5 / 6 / 7 / 9 — only steps 1, 2, 8 sweep'd. Same body+action split applies; copy still in flight.
- **Step 8 LCD callout** — original prototype (outline of route bar) read as too loud and didn't direct the eye to *one* clickable thing. Removed pending a clearer design — maybe per-cell highlight, chevron animation, or a connector line from the side-panel example to a real cell.
- **ESC confirm-quit modal** — currently exits without confirm (TODO comment in `_handle_events`).
- **Game-pairing screenshot slots** — placeholders implied in step 3 / 6 / 9 bodies; user provides screenshots later.
- **ZH-HK / ZH-CN translations** — EN-only for now; flow stabilizes first.

---

## File touchpoints

- `tutorial.py` (new) — Tutorial class + Step descriptor + STEPS tuple + render helpers.
- `preview_tutorial.py` (new) — chrome screenshot tool. `--no-sim` for headless smoke; `--pre-action` to capture pre-click UI cues.
- `app.py` — `PASimulator(tutorial=True, target_surface=...)` params; `snapshot_state` / `restore_state`.
- `audio.py` — `AudioPlayer.__del__` deleted (was tearing down mixer at GC time when tutorial drops its sim ref).
- `main.py` — OOBE gate between picker and setup; setup re-trigger loop.
- `setup.py` — "? Tutorial" button when `oobe_completed=True`; action-keyed dict return.
- `data/translations_app.json` — phase names, step bodies + actions, button labels, `setup.tutorial_button`. EN-only.

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

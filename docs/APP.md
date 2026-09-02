# APP.md — Application Architecture

App-level runtime and the setup / chrome flow. This is the canonical home for app-level specs that do not belong to a narrower domain doc: LCD (`DISPLAY.md`), data grammar (`DATA_FORMAT.md`), OCR (`auto_input/README.md`), per-line audio (`audio/README.md`). Project scope and mental model stay in `CLAUDE.md`. Chrome, font and interaction rules stay in `conventions.md`; this doc points at them rather than restating them.

> **EDIT-CONTRACT** — what this doc holds, what it refuses.
>
> **Holds:** runtime orchestration (`main.py` entry → setup↔drive loop), the launch-config shape, the setup/chrome flow (screens + register codes, selection flow, status band, model/tutorial pickers), the `tims/` package map. The catch-all for an app-level spec with no narrower home.
>
> **Refuses:**
> - LCD render internals → [DISPLAY.md](DISPLAY.md); JSON field defs → [DATA_FORMAT.md](DATA_FORMAT.md); OCR pipeline → [auto_input/README.md](../auto_input/README.md)
> - Chrome / font / interaction *rules* → [conventions.md § UI code style](../.claude/rules/conventions.md) — cross-reference, don't restate
> - History notes / change logs / iteration tuning numbers — `git log` + `memory/YYYY-MM-DD.md` have this
> - Code-snippet illustrations of how a class looks — link `file:line` instead
> - Speculative future designs ("when X is implemented …") — GitHub Issues is the home
> - Facts already in [CLAUDE.md](../CLAUDE.md) mental model — cross-reference, don't restate
>
> **Voice:** reference-shaped entries (runtime map, screen table, flow contracts) stay compressed — tables, `=` for definitional equivalence, no narrative padding. Rationale-shaped passages (incident traces, "why" framings) run as ordinary prose. Both in complete sentences where they use prose at all, per [CLAUDE.md § Writing tone](../CLAUDE.md).
>
> **Before adding:** name the section your edit merges into OR the content it replaces. If neither — you're appending, which is the failure mode this contract fights.
>
> **Additions > ~10 lines:** present the diff to the user first. Heavy additions get gated, not auto-applied.
>
> Periodic sweep via `/distill-docs`. Underlying principle: [principles.md § "Tighten before appending"](../.claude/rules/principles.md).

---

## Runtime map (`main.py`)
`main()`:
1. `pygame.init()` + `mixer.init()`; `update_check.check_async()` fires early (3 s network window overlaps setup).
2. **Language resolution.** There is no standalone picker. The saved `settings["language"]` wins; otherwise `detect_default_lang()` maps the OS locale to `zh_CN` for Simplified locales and **`zh_HK` for everything else**. `zh_HK` is the clean-install default, not English; `DEFAULT_LANG="en"` stays the separate translation fallback. The result is persisted on genuine first-run, then `i18n.init(lang)` runs. Runtime switching and persistence belong to the TIMS home's language knobs (`tims/setup/home.py`). The pre-TIMS grey `LanguagePicker` was removed as stale and redundant beside those knobs (critical_lessons §6).
3. **Setup ↔ drive loop:**
   - `_run_setup()` returns a launch config, or `None` to exit.
   - `pygame.display.quit()` tears the setup window down. The drive builds its own taller, panel-carved one.
   - `_run_drive(config)` returns `"home"` (band Home re-enters setup, with pygame and mixer left alive) or `"quit"` (window close or ESC, a full exit).

**`_run_setup()`** runs `tims.setup.run(surface)` in a 730×610 window and returns the launch config or `None`. There is no forced first-run tutorial; TIMS owns OOBE itself. The 教學 card flashes until visited, and `home._mark_oobe_done` persists `oobe_completed`.

**`_run_drive(config)`** builds `PASimulator(work_dir, route_data, auto_input=, model=)` and calls `jump_to_stop(start_idx)` if a start station was picked. With `auto_input` set it spins up `AutoDriver(lead_m, interval_s)` and assigns `sim.auto_driver = driver`, which exposes pause to the band. `sim.run()` returns the exit action, and the driver is stopped in a `finally` block.

Window size is `TIMS_SIZE=(730,610)`. No window is created before the flow starts: `_run_setup` creates the first one itself, so first-run goes straight to the correctly-sized screen with no blank pre-flash.

**Always-on-top:** the app is a companion overlay for the game, so the window stays `HWND_TOPMOST`. `main()` calls `window_utils.install_topmost_hook()` once, after `pygame.init()`. The hook wraps `pygame.display.set_mode` so every window it creates re-pins topmost, which keeps the behaviour at one seam as screens are added. It is needed because every `set_mode` drops the topmost style and the TIMS flow re-`set_mode`s on each screen transition. The old monolith re-pinned inline after each call; the modular rewrite kept the pin only in the sim, so the setup flow lost it. Previews and dev scripts do not call the hook and stay unpinned. It is a no-op off Windows, or if pywin32 is absent.

## Launch config (setup → `main._run_drive`)
The dict `tims.setup.run()` returns:

| Key | Meaning |
|---|---|
| `action` | always `"select"` (drive). The classic flow's `"run_tutorial"` went with it on 2026-07-30 |
| `work_dir` | route folder (`audio/<line>/<diagram>/`) |
| `route_data` | always `None` — `PASimulator` loads it via `route_loader.load_route_from_dir`, which is the only reader that also attaches the line's `system.json` sheet. The TIMS flow used to parse `route.json` itself here, and that second read silently dropped the sheet on the one path a real user takes |
| `model` | train-model key (override > route default > global default) |
| `start_idx` | start-station stop index (tims setup only; classic has none) |
| `auto_input` | OCR Auto-PA armed (adds `lead_m` / `interval_s`) |

## App run loop (`app.py::PASimulator.run`)
The main loop drives events into PA, STA and pause handling plus the render path. `_handle_band_click` dispatches the status-band cluster (pause / save-record / home). `exit_action` defaults to `"quit"` and is set to `"home"` by band Home. On exit the loop calls `cleanup(full_quit = exit_action != "home")` and returns `exit_action` to `_run_drive`. The state-machine spec is `DISPLAY.md § Unified State Machine`.

## Window mirroring — the remote terminal (`frame_stream.py`)
Mirrors **the whole app window**, setup, tutorial and drive alike, to a browser over HTTP, and takes taps back. The point is screen real estate: the display sits on a tablet instead of covering the game. It is named リモート端末 after the flightsim *remote CDU*. Since touch landed it is a second instance of the console, not a video feed.

**Where it is set.** TIMS 設定 (`tims/setup/stream_setting.py`) persists one tri-state and a port. There are no launch flags; the page is the only switch. It applies immediately via `apply_mode`, which stops the server and starts it again, because a bind address cannot change on a live socket.

| mode | binds | cost |
|---|---|---|
| `off` | — | — |
| `local` | `127.0.0.1` | none. A loopback socket is unreachable from the network, so Windows raises no firewall prompt. **The shipped default.** |
| `lan` | `0.0.0.0` | the firewall prompt, once. Any device that can reach it can drive the app. |

`clean_mode` / `clean_port` are the only place a persisted value becomes a usable one. `settings.json` is hand-editable and is read before any window exists, so nothing but the literal `"lan"` may bind past loopback.

**Finding it.** The status band draws one green row, `リモート <addr>:<port>`, on the setup screens only (`band._stream_rows`; a drive's rows carry OCR state). Clicking it opens the PC's browser. Hovering underlines it and drops a QR to scan, encoded by `qr.py`, a self-contained encoder written to hold the zero-dependency invariant below. `lan_candidates()` returns several addresses ranked private-first (192.168 → 172.16 → 10/8, where VPNs land) and never public ones. The band shows the first.

**Client.** One `<img src="/stream">` on a `multipart/x-mixed-replace` feed of PNGs, with no JavaScript on the display path. JS adds only the segmented view control (BOTH / BELL / PIDS, when the bell box is open), a 1:1 zoom toggle, and the tap POST. The controls are browser chrome dressed as TIMS bevel buttons. The palette and the view ids are **injected** from Python at a `<!--PRELUDE-->` marker so the page cannot restate them.

**Security posture.** The server is unauthenticated by design, and `/tap` means someone on your Wi-Fi can drive the app, not merely watch it. Two gates close that, and both are what a same-origin client already sends. The first is `Content-Type: application/json`, which forces a preflight the server answers with 501, having no `do_OPTIONS`. The second is a `Host` check on **every** endpoint, reads included; without it a page in the user's own browser can point a short-TTL name at loopback and read the screen off a canvas. The allow-list holds what was **bound**, plus this machine's names, never what the UI chose to display.

**Load-bearing invariants.** Each one fixed a real defect. Re-read the reason before changing any of them.
- **Capture on present, never on request.** `_publish` runs from a `flip`/`update` wrapper on the main thread. Sampling the live surface from a server thread catches renderers mid-clear, which shows as flicker.
- **PNG, not JPEG.** Measured on this content, PNG is 4× smaller and pixel-exact, where JPEG damaged ~7% of subpixels. Flat fills and AA-off glyphs are JPEG's worst case.
- **The cap evicts, never refuses.** Switching view abandons a request that the server cannot see until its send buffer fills, about 8.5 s, so refusing locked users out with a broken image. The victim is the stalest handler.
- **A tap for a view that is not there misses.** Showing a fallback frame is a kindness. Resolving a tap against it presses whatever occupies that point.
- **Zero new dependencies** (`critical_lessons §3`, `§4`): stdlib `http.server` and pygame's own PNG writer.

**Rejected, so they are not re-proposed:**

- WebSocket / SSE / WebRTC — dependency weight for a LAN image feed.
- JPEG or WebP.
- Server-side scaling — it forces a per-client stream.
- A pygame-drawn view control — it would appear on the PC window too, or make the stream stop matching it.
- `image-rendering: pixelated` — the stream carries AA-off chrome *and* AA-on LCD text, so no one filter serves both, and on a phone's downscale it destroys 1px strokes.

Why streaming rather than a mobile port: `TODO.md § Directions`.

Hooks are installed once at `main()` entry and are idempotent regardless of order: `install_present_hook` (capture and replay taps), `band.install_overlay_hook` (the QR, which must draw after each screen paints over the band), and `install_display_quit_guard`.

## Setup flow (TIMS — default; `tims/setup/`)
A console re-skin of the setup flow to the JR East TIMS cab look, and since 2026-07-30 the only setup flow. Primitives live in `tims/widgets.py` and shared vocabulary in `tims/chrome.py`. Chrome, font and interaction rules live in `conventions.md`.

### Package map
- `home.py`: page-1 menu and the setup entry (`run()` re-exported as `tims.setup.run`).
- `pa_setting.py`: C07AA PA-setting page and the launch-config builder (`_build_config`).
- `route_select.py`: route / start-station / run-pattern pickers.
- `model_select.py`: X00AA train-model picker.
- `tutorial_select.py` / `tutorial_basic.py`: tutorial menu and the reskinned walkthrough.
- `ocr_setting.py`: OCR consent and settings.
- `dims.py`: setup-window dims (`SCREEN_W/H`, plus the band-height re-export).
- `band.py`: the persistent top band. It lives one level up at `tims/band.py`, shared with the live drive and not part of the `setup` subpackage.

### Screens + register codes
Codes mirror the real TIMS register. `C07AC` and `X00AA` are photographed; the rest are plausible siblings, droppable but kept for fidelity.

| Code | Screen | Module |
|---|---|---|
| — | Home menu (報站設定 / 教學 / 設定 / 行車記錄) | `home.py` |
| C07AA | 案内設定 PA-setting | `pa_setting.py` |
| C07AB | route-selection grid | `route_select.py` |
| C07AC | 始発駅選択 start-station grid | `route_select.py` |
| C07AF | 運用パターン選択 run-pattern (diagram) twin-table | `route_select.py` |
| C07AD | 教學選擇 tutorial menu | `tutorial_select.py` |
| C07AE | 基本操作 basic tutorial | `tutorial_basic.py` |
| C07AG | OCR consent | `ocr_setting.py` |
| C07AH | OCR settings | `ocr_setting.py` |
| X00AA | 番台選択 / 列車型號 model picker | `model_select.py` |

### Home (page 1)
Four flush action cards: **報站設定** (→ C07AA), **教學** (→ tutorial), **設定**, **行車記錄**. The last two are **out of scope this release**, so they render silver and disabled (`chrome.DISABLED`, same geometry) and are fully inert, with no press beat and no nav. `home.INACTIVE_ACTIONS` drives both the palette and the click skip, so re-enabling either later is a one-line change. Three language knobs sit top-right; yellow there is a momentary press, not a selected state. The version tag sits bottom-left (`Version ０５４`, full-width numerals) and flashes an update hint when `update_check.get_update()` returns a newer release. **OOBE:** while `oobe_completed` is False the 教學 card flashes, and the first visit persists the flag (`home._mark_oobe_done`). This replaces the forced first-run fullscreen tutorial.

### Route selection (route → station → diagram)
Reached from **C07AA's 選擇路綫** button. These are real TIMS route-selection screens backed by the existing `route.json`, with no bespoke per-line logic. Flow: **C07AB route → C07AC start station → C07AF run-pattern (diagram).**
- Boxes show the **basic line name**: `route.json`'s `route` stripped to the primary line, with through-service (直通) combined names dropped. That mapping is deferred, see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues). This `route` is also the LCD upper-display name.
- The start-station grid **excludes passing stations** (empty `pa`, `sta` and `time` per `DATA_FORMAT.md § Skipping Stations`) and maps the pick back to the full stop index.
- C07AF lists **only diagrams that stop at the chosen start station**. The station grid is built from `variants[0]`, which always stops there, so it is never empty. Changing the start resets the pattern pick.

### PA-setting (C07AA)
Reached from the home 報站設定 card. A manual-first adaptation of the IRL `tims_pa_setting_done.png`.
- **自動放送始発起動 is a launch action, not a toggle.** It arms OCR Auto-PA and goes straight to the live LCD. There is no persistent on/off switch.
- The bottom OCR launch cluster is three equal bevel buttons, one over two, in a white L-notch frame. `OCR自動報站起動` passes through the consent gate and launches with `auto_input=True`. `手動報站起動` launches manually, un-armed by default. `OCR自動報站設定` opens the settings page directly, with no gate.
- The `列車型號` row opens the model picker (X00AA), and shows the model in effect.

### Model picker (X00AA)
Reached from C07AA's 列車型號. The grid holds built models (blue, from the train-model registry) alongside grayed roadmap models (silver, disabled, `_GRAYED`). A click commits; there is no confirm and no back, so band Home or ESC is the way out. The current pick flashes. The override is session-persistent (`pa_setting._model_override`). Out-of-spec picks are allowed, best-effort.

### Tutorial (C07AD)
The 教學 card opens the `tutorial_select` menu, one bevel button per feature, and a click enters directly with no 設定 confirm.
- **基本操作 is the legacy `tutorial.py` walkthrough, reskinned and reflowed vertically.** `BasicTutorial(Tutorial)` subclasses the legacy step machine unchanged, overriding only the layout to stack band → title → live LCD → progress strip → step panel. The LCD is native and unscaled, so the click-to-jump math survives.
- **OCR自動報站 is the OCR consent view, read-only** (`ocr_setting.run_consent(read_only=True)`).

### Persistent status band
A full-width near-black status strip across every setup screen and the live in-drive OCR panel, from one module, `tims/band.py`. The entry point is `render(surf, status, sim_state, stops, save_notice=)`; `status=None` in setup draws the placeholder, with no readings. The live drive feeds `auto_input_status` and wires the `[pause][save][home]` cluster via `app.py::_handle_band_click`. Detail: `auto_input/README.md § Debug panel`.
- **Static labels render in every state; only readings and effects gate on live status.** The `制限` speed-limit row label and the `km/h` and `m` units are static chrome, so they show even in the no-readings setup band, beside the dim `--`. Live-only, and absent until OCR runs: the actual numbers, the limit's cyan change-flash, the yellow message strips and the save confirmation. The limit's cyan block is a change cue rather than a resting highlight. It blinks for about `LIMIT_FLASH_WINDOW` s on a value-to-value change, with `driver` stamping `limit_change_ts` the way it stamps `last_fire`.
- **Live-drive control cluster interaction.** `[save]` and `[home]` each flash yellow on press (`tims.band.press_flash` → `press_transition`), which is the TIMS press-flash every clickable button gets; the setup band already did this. **Pause was removed 2026-08-30.** It was a play/pause toggle on the auto-driver that the author had never once used. `AutoDriver.paused` survives as driver state with nothing setting it, so a control can return on the tap surface without the band holding a 64px square for it in the meantime.
- **Three fixed regions and one elastic one, so a narrower canvas is absorbed entirely by the elastic one.** The band spans `surf.get_width()`, which is the train model's own `S_WIDTH`. The left column (`LEFT_X`), the readout cell (`CELL_X` and `CELL_W`) and the right-hand button cluster are all anchored, so only the message strips flex. E233-0's 640px canvas against E235's 730 therefore took all 90px off the strips: they fell to 72px against messages measuring 102–142, while every other element stayed correct. Dropping pause returned 70px and brought them back to 142. Before adding a model, know that the band does not degrade evenly. It degrades in one place.
- **The left column compresses rather than truncating.** A row wider than the gap to the readout cell steps its AA-off native size down (`LEFT_FIT_STEP`, capped at `LEFT_FIT_STEPS`). The whole row steps together so chunks keep their relative sizes; the mirror row's address is deliberately larger than its label. Author, 2026-08-30: *"even if it overflows, we should be able to comperss it."*
- **The mirror address surfaces on a timer during a drive**, for `STREAM_SHOW_MS` in every `STREAM_SHOW_MS + STREAM_HIDE_MS`, taking row 0 from the green notif and giving it back. It is periodic rather than once at drive start, because the case is a mid-drive reconnect. **A hover suspends the timer.** The QR popup exists only while the row's hit-rect does, so hiding the row mid-hover would take the code away while it was being scanned. That hold needs its own flag, because `_hovered_url` is *consumed* by the flip hook on every present and reads None by the time the next frame builds its rows.

### Band Home
Every setup screen's band Home returns to the home menu rather than one level up, with a press and a loading beat. Deep pages return the sentinel `"home"`, which bubbles up through the parents (`route_select` / `model_select` → `pa_setting` → home; `tutorial_basic` → `tutorial_select` → home).

## Retired: the classic flow
`setup.py` (`SetupScreen`), its `--classic` flag, `preview_chrome.py`, and `i18n`'s per-language OTF chrome table (`_LANG_CHROME_FONT` / `font()` / `font_for_lang()`) were **deleted 2026-07-30**. TIMS reached feature parity 2026-07-11 and the classic path had no remaining user. Its keyboard-navigable route picker went with it, dropped deliberately for the console style. `tutorial.py` survives: `tims/setup/tutorial_basic.py` imports `Tutorial`, `STEPS`, `PHASE_KEYS` and the mixed-text helpers from it, so it is shared rather than legacy.

## Cross-references
- Window mirroring / remote terminal → § "Window mirroring" above.
- Chrome / font / interaction rules → `conventions.md § UI code style`, `§ "TIMS chrome text"`.
- App state machine → `DISPLAY.md § Unified State Machine`.
- LCD displays → `DISPLAY.md`, `DISPLAY_E235.md`.
- Data grammar → `DATA_FORMAT.md`.
- OCR / auto-input → `auto_input/README.md`.
- Project scope / mental model → `CLAUDE.md`.

# APP.md — Application Architecture

App-level runtime + the setup / chrome flow. Canonical home for app-level specs that don't belong to a narrower domain doc — LCD (`DISPLAY.md`), data grammar (`DATA_FORMAT.md`), OCR (`auto_input/README.md`), per-line audio (`audio/README.md`). Project scope + mental model stay in `CLAUDE.md`; chrome/font/interaction RULES stay in `conventions.md` — this doc points, doesn't restate.

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
2. **Language resolution** — NO standalone picker. Saved `settings["language"]`, else `detect_default_lang()` (OS locale → `zh_CN` for Simplified locales, **`zh_HK` for everything else** — the HK-primary clean-install default, NOT English; `DEFAULT_LANG="en"` stays the separate translation fallback), persisted on genuine first-run; then `i18n.init(lang)`. Runtime switching + persistence is owned by the TIMS home's language knobs (`tims/setup/home.py`). (The pre-TIMS grey `LanguagePicker` was removed — stale + redundant beside the knobs; critical_lessons §6.)
3. **Setup ↔ drive loop:**
   - `_run_setup()` → launch config, or `None` → exit.
   - `pygame.display.quit()` (tear down setup window — the drive builds its own taller, panel-carved one).
   - `_run_drive(config)` → `"home"` (band Home → re-enter setup; pygame/mixer stay alive) or `"quit"` (window close / ESC → full exit).

**`_run_setup()`** — `tims.setup.run(surface)` in a 730×610 window. Returns the launch config or `None`. No forced first-run tutorial: TIMS owns OOBE itself (the 教學 card flashes until visited, `home._mark_oobe_done` persisting `oobe_completed`).

**`_run_drive(config)`** — builds `PASimulator(work_dir, route_data, auto_input=, model=)`; `jump_to_stop(start_idx)` if a start station was picked; if `auto_input`, spins `AutoDriver(lead_m, interval_s)` + `sim.auto_driver = driver` (exposes pause to the band). `sim.run()` returns the exit action; driver stopped in `finally`.

Window size: `TIMS_SIZE=(730,610)`. No premature window is created before the flow — `_run_setup` creates its own first window, so first-run goes straight to the correctly-sized screen (no blank pre-flash).

**Always-on-top:** the app is a companion overlay for the game, so the window stays `HWND_TOPMOST`. `main()` calls `window_utils.install_topmost_hook()` once (after `pygame.init()`), wrapping `pygame.display.set_mode` so EVERY window it creates re-pins topmost — one seam, regression-proof as screens are added. Needed because every `set_mode` drops the topmost style and the TIMS flow re-`set_mode`s per screen transition; the old monolith re-pinned inline after each call, the modular rewrite kept the pin only in the sim → the setup flow lost it. Previews / dev scripts don't call the hook (stay unpinned). No-op off-Windows / if pywin32 absent.

## Launch config (setup → `main._run_drive`)
The dict `tims.setup.run()` returns:

| Key | Meaning |
|---|---|
| `action` | `"select"` (drive) / `"run_tutorial"` (classic replay) |
| `work_dir` | route folder (`audio/<line>/<diagram>/`) |
| `route_data` | finalized route closure (`route_loader`) |
| `model` | train-model key (override > route default > global default) |
| `start_idx` | start-station stop index (tims setup only; classic has none) |
| `auto_input` | OCR Auto-PA armed (adds `lead_m` / `interval_s`) |

## App run loop (`app.py::PASimulator.run`)
Main loop drives events → PA/STA/pause + the render path; `_handle_band_click` dispatches the status-band cluster (pause / save-record / home). `exit_action` defaults `"quit"`, set `"home"` by band Home. On exit: `cleanup(full_quit = exit_action != "home")`, returns `exit_action` to `_run_drive`. State-machine spec: `DISPLAY.md § Unified State Machine`.

## Window mirroring — the remote terminal (`frame_stream.py`)
Mirrors **the whole app window** — setup, tutorial, drive alike — to a browser over HTTP, and takes taps back. The point is screen real estate: the display sits on a tablet instead of covering the game. Named リモート端末 after the flightsim *remote CDU* — since touch landed it is a second instance of the console, not a video feed.

**Where it is set.** TIMS 設定 (`tims/setup/stream_setting.py`), which persists one tri-state and a port. There are no launch flags — the page is the only switch, and it applies immediately via `apply_mode` (stop-then-start; a bind address cannot change on a live socket).

| mode | binds | cost |
|---|---|---|
| `off` | — | — |
| `local` | `127.0.0.1` | none — a loopback socket is unreachable from the network, so Windows raises no firewall prompt. **The shipped default.** |
| `lan` | `0.0.0.0` | the firewall prompt, once; and any device that can reach it can DRIVE the app |

`clean_mode` / `clean_port` are the only place a persisted value becomes a usable one — `settings.json` is hand-editable and read before any window exists, so nothing but the literal `"lan"` may bind past loopback.

**Finding it.** The status band draws one green row, `リモート <addr>:<port>`, on the setup screens only (`band._stream_rows`; a drive's rows carry OCR state). Clicking opens the PC's browser; hovering underlines it and drops a QR to scan — `qr.py`, a self-contained encoder, because D3 below makes new dependencies the signal to re-examine the design. `lan_candidates()` returns SEVERAL addresses ranked private-first (192.168 → 172.16 → 10/8, where VPNs land) and never public ones; the band shows the first.

**Client.** One `<img src="/stream">` on a `multipart/x-mixed-replace` feed of PNGs — no JavaScript on the display path. JS adds only the segmented view control (BOTH / BELL / PIDS, when the bell box is open), a 1:1 zoom toggle, and the tap POST. Controls are browser chrome dressed as TIMS bevel buttons, with the palette and the view ids **injected** from Python at a `<!--PRELUDE-->` marker so the page cannot restate them.

**Security posture.** Unauthenticated by design, and `/tap` means "someone on your Wi-Fi can drive", not merely watch. Two gates, both what a same-origin client already sends: `Content-Type: application/json` (which forces a preflight the server answers 501, having no `do_OPTIONS`) and a `Host` check on **every** endpoint, reads included — without it a page in the user's own browser can point a short-TTL name at loopback and read the screen off a canvas. The allow-list is what was BOUND (plus this machine's names), never what the UI chose to display.

**Load-bearing invariants** — each fixed a real defect; change one and re-read why:
- **Capture on present, never on request.** `_publish` runs from a `flip`/`update` wrapper on the main thread; sampling the live surface from a server thread catches renderers mid-clear and shows as flicker.
- **PNG, not JPEG.** Measured on this content: 4× smaller *and* pixel-exact, where JPEG damaged ~7% of subpixels. Flat fills and AA-off glyphs are JPEG's worst case.
- **The cap EVICTS, never refuses.** Switching view abandons a request the server cannot see until its send buffer fills (~8.5 s), so refusing locked users out with a broken image. The victim is the stalest handler.
- **A tap for a view that is not there MISSES.** Showing a fallback frame is a kindness; resolving a tap against it presses whatever occupies that point.
- **Zero new dependencies** (`critical_lessons §3`, `§4`) — stdlib `http.server` + pygame's own PNG writer.

**Rejected, so they are not re-proposed:** WebSocket / SSE / WebRTC (dependency weight for a LAN image feed) · JPEG or WebP · server-side scaling (forces a per-client stream) · a pygame-drawn view control (it would appear on the PC window too, or make the stream stop matching it) · `image-rendering: pixelated` (the stream carries AA-off chrome *and* AA-on LCD text; no one filter serves both, and on a phone's downscale it destroys 1px strokes). Why streaming rather than a mobile port: `TODO.md § Directions`.

Hooks are installed once at `main()` entry and are idempotent regardless of order: `install_present_hook` (capture + replay taps), `band.install_overlay_hook` (the QR, which must draw AFTER each screen paints over the band), `install_display_quit_guard`.

## Setup flow (TIMS — default; `tims/setup/`)
Console re-skin of the setup flow to the JR East TIMS cab look, and since 2026-07-30 the ONLY setup flow. Primitives in `tims/widgets.py`; shared vocabulary in `tims/chrome.py`. Chrome/font/interaction RULES → `conventions.md`.

### Package map
- `home.py` — page-1 menu + the setup entry (`run()` re-exported as `tims.setup.run`).
- `pa_setting.py` — C07AA PA-setting page + the launch-config builder (`_build_config`).
- `route_select.py` — route / start-station / run-pattern pickers.
- `model_select.py` — X00AA train-model picker.
- `tutorial_select.py` / `tutorial_basic.py` — tutorial menu + the reskinned walkthrough.
- `ocr_setting.py` — OCR consent + settings.
- `dims.py` — setup-window dims (`SCREEN_W/H`; band height re-export).
- `band.py` — the persistent top band. Lives one level up at `tims/band.py` (shared with the live drive; not part of the `setup` subpackage).

### Screens + register codes
Codes mirror the real TIMS register (`C07AC` / `X00AA` photographed; the rest plausible siblings — droppable, kept for fidelity).

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
4 flush action cards — **報站設定** (→ C07AA) / **教學** (→ tutorial) / **設定** / **行車記錄**. The last two are **out of scope this release** → rendered silver/disabled (`chrome.DISABLED`, same geometry) + fully inert (no press beat, no nav); `home.INACTIVE_ACTIONS` drives both the palette and the click skip, so re-enabling either later is a one-line change. 3 language knobs top-right (yellow = momentary press, NOT a selected state). Version tag bottom-left (`Version ０５４`, full-width numerals; flashes an update hint when `update_check.get_update()` returns a newer release). **OOBE:** while `oobe_completed` is False the 教學 card flashes; the first visit persists the flag (`home._mark_oobe_done`) — replaces the forced first-run fullscreen tutorial.

### Route selection (route → station → diagram)
Reached from **C07AA's 選擇路綫** button. Real TIMS route-selection screens backed by existing `route.json` (no bespoke per-line logic). Flow: **C07AB route → C07AC start station → C07AF run-pattern (diagram).**
- Boxes show the **basic line name** (`route.json` `route` stripped to the primary line; through-service / 直通 combined names dropped — mapping DEFERRED, see [GitHub Issues](https://github.com/ksleungac/pids-jre-simulator/issues)). This `route` is also the LCD upper-display name.
- Start-station grid **excludes passing stations** (empty `pa`/`sta`/`time` per `DATA_FORMAT.md § Skipping Stations`); maps the pick back to the full stop index.
- C07AF lists **only diagrams that STOP at the chosen start station**; the station grid is built from `variants[0]` (always stops there → never empty). Changing start resets the pattern pick.

### PA-setting (C07AA)
Reached from the home 報站設定 card. Manual-first adaptation of IRL `tims_pa_setting_done.png`.
- **自動放送始発起動 = a LAUNCH ACTION, not a toggle** — arms OCR Auto-PA + goes straight to the live LCD. No persistent on/off switch.
- Bottom OCR launch cluster — 3 equal bevel buttons, 1-over-2, in a white L-notch frame: `OCR自動報站起動` → consent gate → launch `auto_input=True`; `手動報站起動` → manual launch (default un-armed); `OCR自動報站設定` → settings page directly (no gate).
- `列車型號` row → the model picker (X00AA); the table row shows the model in effect.

### Model picker (X00AA)
From C07AA's 列車型號. Grid = built models (blue, from the train-model registry) + grayed roadmap models (silver, disabled — `_GRAYED`). Click commits (no confirm / no back — band Home / ESC return); current pick FLASHES. Override is session-persistent (`pa_setting._model_override`). Out-of-spec picks allowed (best-effort).

### Tutorial (C07AD)
教學 card → `tutorial_select` menu (one bevel button per feature) → click enters directly (no 設定 confirm).
- **基本操作 = the legacy `tutorial.py` walkthrough, reskinned + reflowed vertical** (`BasicTutorial(Tutorial)` subclasses the legacy step machine UNCHANGED, overriding only layout to stack band → title → live LCD (native, unscaled — click-to-jump math survives) → progress strip → step panel).
- **OCR自動報站 = the OCR consent view read-only** (`ocr_setting.run_consent(read_only=True)`).

### Persistent status band
Full-width near-black status strip across every setup screen AND the live in-drive OCR panel — one module, `tims/band.py`. `render(surf, status, sim_state, stops, save_notice=)`; `status=None` in setup → placeholder (no readings). Live drive feeds `auto_input_status` + wires the `[pause][save][home]` cluster via `app.py::_handle_band_click`. Detail: `auto_input/README.md § Debug panel`.
- **Static labels render in EVERY state; only readings/effects gate on live status.** The `制限` speed-limit row label + the `km/h`/`m` units are static chrome → shown even in the no-readings setup band (beside the dim `--`). Live-only (absent until OCR runs): the actual numbers, the limit's cyan change-flash, the yellow message strips + save confirmation. The limit's cyan block is a CHANGE cue (blinks ~`LIMIT_FLASH_WINDOW` s on a value→value change, `driver` stamps `limit_change_ts` like `last_fire`), not a resting highlight.
- **Live-drive control cluster interaction.** `[save][home]` each flash yellow on press (`tims.band.press_flash` → `press_transition`, the TIMS press-flash every clickable button gets — the setup band already did this). **Pause was removed 2026-08-30** — a play/pause toggle on the auto-driver the author had never once used. `AutoDriver.paused` survives as driver state with nothing setting it, so a control can return on the tap surface without the band holding a 64px square for it meanwhile.
- **THREE FIXED REGIONS AND ONE ELASTIC ONE, so a narrower canvas is absorbed entirely by the elastic one.** The band spans `surf.get_width()`, which is the train model's own `S_WIDTH` — and the left column (`LEFT_X`), the readout cell (`CELL_X` + `CELL_W`) and the right-hand button cluster are all anchored, so only the message strips flex. E233-0's 640px canvas against E235's 730 therefore took all 90px off the strips: they fell to 72px against messages measuring 102–142, while every other element stayed correct. Dropping pause returned 70px and brought them to 142. Worth knowing before adding a model: the band does not degrade evenly, it degrades in one place.
- **The left column COMPRESSES rather than truncating.** A row wider than the gap to the readout cell steps its AA-off native size down (`LEFT_FIT_STEP`, capped at `LEFT_FIT_STEPS`), the whole row together so chunks keep their relative sizes — the mirror row's address is deliberately larger than its label. Author, 2026-08-30: *"even if it overflows, we should be able to comperss it."*
- **The mirror address surfaces on a TIMER during a drive**, `STREAM_SHOW_MS` in every `STREAM_SHOW_MS + STREAM_HIDE_MS`, taking row 0 from the green notif and giving it back. Periodic rather than once at drive start, because the case is a mid-drive reconnect. **A hover suspends the timer**: the QR popup exists only while the row's hit-rect does, so hiding the row mid-hover would take the code away while it was being scanned. That hold needs its own flag — `_hovered_url` is *consumed* by the flip hook every present, so it reads None by the time the next frame builds its rows.

### Band Home
Every setup screen's band Home returns to the HOME MENU (not one level up) with a press + loading beat. Deep pages return the sentinel `"home"`, bubbled up through parents (`route_select`/`model_select` → `pa_setting` → home; `tutorial_basic` → `tutorial_select` → home).

## Retired: the classic flow
`setup.py` (`SetupScreen`), its `--classic` flag, `preview_chrome.py`, and `i18n`'s per-language OTF chrome table (`_LANG_CHROME_FONT` / `font()` / `font_for_lang()`) were **deleted 2026-07-30** — TIMS reached feature parity 2026-07-11 and the classic path had no remaining user. Its keyboard-navigable route picker went with it, dropped deliberately for the console style. `tutorial.py` SURVIVES: `tims/setup/tutorial_basic.py` imports `Tutorial` / `STEPS` / `PHASE_KEYS` / the mixed-text helpers from it, so it is shared, not legacy.

## Cross-references
- Window mirroring / remote terminal → § "Window mirroring" above.
- Chrome / font / interaction RULES → `conventions.md § UI code style`, `§ "TIMS chrome text"`.
- App state machine → `DISPLAY.md § Unified State Machine`.
- LCD displays → `DISPLAY.md`, `DISPLAY_E235.md`.
- Data grammar → `DATA_FORMAT.md`.
- OCR / auto-input → `auto_input/README.md`.
- Project scope / mental model → `CLAUDE.md`.

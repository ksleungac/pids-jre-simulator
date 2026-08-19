# WIP — LAN frame streaming (browser / tablet second screen)

**Tracking:** [#127](https://github.com/ksleungac/pids-jre-simulator/issues/127) "Touch input from the mirrored window" · grew out of [#1](https://github.com/ksleungac/pids-jre-simulator/issues/1) (contributor request for mobile/tablet support). #71 / #73 / #76 were closed `NOT_PLANNED` on 2026-08-18 into `TODO.md` § Directions.

**Status:** spec locked 2026-07-20 after a `/third-man` design consult. **Stage 1 built and smoke-tested against the live app** (`e08c5b2`). **Stage 2 (touch) built 2026-08-19** — see § "Stage 2 — touch input". What remains is the in-app toggle (D15), which is this doc's graduation trigger.

Files: `frame_stream.py` · `main.py` (flags + server start/stop) · T1 `test_stream.py` · T3 `test_stream.py`. **`app.py` and `tims/` untouched, stage 2 included** — see § "Stage 2" for why touch needed neither.

**Read this doc for its MODEL, not its state** (`conventions.md` § WIP-doc graduation). Two of its stage-2 premises were true when written and are not now — see § "What changed under this doc".

Run: `uv run main.py --stream` → `http://127.0.0.1:8541/` · `--stream-lan` for a tablet.

---

## EDIT-CONTRACT

- **Holds:** the locked spec, the rejected alternatives (so they are not re-proposed), and transitional notes while the feature is in flight.
- **Does NOT hold:** anything already true of shipped code — that belongs in `APP.md`. Measurements that stop being decision-relevant get cut, not archived.
- **Rejected alternatives stay** until graduation — they are the record of what was already considered.
- **Graduation trigger:** when mirroring becomes a real user-facing feature (an in-app toggle rather than a launch flag), dissolve into `APP.md` (§ streaming) and delete this doc. Single-commit restructure, no parallel-existence period. Stage 1 shipping as a launch-flag-only feature is NOT the trigger — the doc still holds the stage-2 spec and the rejected alternatives.

---

## What changed under this doc

Written 2026-08-19 from git + code, not from the doc. Stage 1 shipped 2026-07-20 and the window-zoom work landed 2026-08-14 between them; it moved three things this spec had assumed.

- **The window↔LCD coordinate transform exists.** `app.py::window_to_canvas` (undo the zoom) and `window_to_lcd` (zoom first, then the status-band offset — the order matters, the band's height is a canvas measurement). Both click consumers go through it; it carries a `# CONTRACT:` naming #73, and T1 `test_window.py` covers it. **This was the expensive half of stage 2.** Two sections of this doc still described it as unbuilt and have been corrected in place.
- **The app window is now a whole multiple of the canvas.** `PASimulator._present` blits `self.canvas` into a window of exactly `k × canvas` (`window_utils.snap_zoom` / `pick_default_zoom`; 1× on 1080p and 1440p, 2× on 4K, persisted to `settings.json`). The present hook publishes what `flip` presented, so **the stream carries the ZOOMED window**: at zoom k it ships k² pixels of nearest-neighbour upscale, which is exactly reconstructible and therefore carries no information the canvas did not. The client then resamples it back down, which is the resampling D5 exists to avoid.
  - Capturing `self.canvas` instead would cut encode and bandwidth by k² and remove that round trip. It costs the one thing stage 1 protected — `frame_stream` would need a registered source and `app.py` would register it — which is why it waits for stage 2, where `app.py` is being touched anyway. It also decides the tap coordinate frame, so it is a stage-2 *prerequisite*, not a stage-2 optimisation.
  - Not urgent on its own: zoom defaults to 1× at 1080p and 1440p, so only 4K users and anyone who dragged the window bigger pay it today.
- **#72 is closed and its premise is retired.** The app declares DPI awareness (`window_utils.declare_dpi_awareness`), so the window is no longer bitmap-stretched by Windows. The stream is no longer sharper than the app.
- **Tracking moved.** #71, #73 and #76 were closed `NOT_PLANNED` on 2026-08-18 into `TODO.md` § Directions → "The mirrored window becomes a real second screen". Stage 2 was promoted back out on 2026-08-19 as #127 "Touch input from the mirrored window", and the Directions entry trimmed to what is left (the in-app toggle, and stream speed).

---

## Why streaming and not a port

Decided 2026-07-20. Do not re-litigate without new information.

- A React/DOM/Kivy/WASM rewrite means **owning two renderers**. Every train model (E233-0, E231-500 next) and every calibration round paid twice, on a project whose whole value is calibration fidelity.
- `audio/` is **423 MB** (Tōkaidō 117 · Chūō 69 · Keihin 54 · Yamanote 45; measured 2026-08-19, after the 2026-08-08 pooling took it down from 558). Not bundleable into a mobile/WASM build. Streaming leaves assets on the PC.
- The #1 contributor independently hit the same wall from the other side (pygame font-metric dependency under Kivy) and shelved their own investigation.
- **OCR auto-input is structurally PC-only.** A standalone mobile build permanently forks the product into "with auto-drive" and "without" — an ongoing triage tax on every future feature.

Streaming costs **zero per train model**: a new model appears on the tablet the day it ships on PC.

### What this does NOT answer

**Streaming strictly requires the PC.** It does not address "usable as a separate device without a PC entirely" — that question stays **open**, not answered. If real demand appears, the door is pygbag/WASM with per-route asset download, the only path that reuses the renderer instead of duplicating it. Not now, and not foreclosed.

---

## Scope

**Stage 1 is display-only. No touch input.** Stage 2 (touch) is specified at the bottom so stage 1 does not foreclose it, but is not built now.

### The offscreen render target is NOT part of this

An earlier draft made a standalone offscreen `pygame.Surface` a prerequisite. The `/third-man` consult established that **the coupling was invented**: `self.screen` is already a subsurface, and `.copy()` on a subsurface already returns a standalone Surface. Streaming works with zero changes to `_init_pygame`.

Two justifications for bundling it in also failed against the code:

- **"Headless operation"** — empty. The setup flow (`main.py` → `tims.setup`) calls `set_mode` unconditionally and `convert()`/`convert_alpha()` throughout it require a display. The app also runs beside a PC game; the PC has a screen.
- **"Renderers need no changes, so it's free"** — true but misleading. `_handle_lcd_click` and `_update_hover_cursor` mapped window→LCD coords by subtracting a fixed `panel_h`, so the moment the window blitted a *scaled* surface, click-to-jump and the hover cursor silently misfired. Converting the surface did not do that work — it only made the bug reachable.

That change belonged to the **reactive-window** roadmap item, whose real deliverable is a shared window↔LCD coordinate transform consumed by both call sites. **It shipped 2026-08-14 with the window-zoom work** (see § "What changed under this doc"), so it is no longer a cost stage 2 has to pay.

### What is mirrored: the whole window

Per the user (*"if enabled it copies whatever the app is on PC and on remote device"*), the stream mirrors the **entire app window** — TIMS setup, tutorial, and drive alike — not just the LCD region.

This is what collapsed the design. pygame has **one** display surface globally, so the server reads `pygame.display.get_surface()` directly. No frame-source registration, no `PASimulator` involvement, **zero touches to the render path**. The surface changes size across `set_mode` calls (setup 730×610, drive 730×420+band, tutorial 1100×500); an `<img>` re-renders at the new size and CSS handles it.

### Scaffolding that IS in scope

Per the user's directive (*"architecture needs support this. scaffolding for future!"*):

- **Server ownership above the setup↔drive loop** (D8) — required for correctness now, and the right permanent home.
- **One-seam display-teardown guard** (D14) — regression-proof as new teardown sites appear.
- **Per-consumer composition.** The stream composites its own frame, which is what lets stage 2 add a touch strip that never appears on the PC window.

---

## Measured (730×420, verified end-to-end)

| | result |
|---|---|
| new dependencies | **zero** — stdlib `http.server` + `pygame.image.save` to `BytesIO` |
| PNG frame (AA-off content) | **3.4 KB, pixel-exact round-trip** |
| JPEG frame (same content) | 14.0 KB, **6.8% of subpixels damaged**, worst delta 107/255 |
| main-thread cost | 0.37 ms/frame (one surface copy, 1.1% of a 30 fps budget) |
| dirty-detect (`tobytes`+`crc32`) | 1.11 ms/frame |
| bandwidth @15 fps | ~51 KB/s |
| end-to-end | 12/12 valid **distinct** PNG parts pulled across threads |

---

## Design decisions — locked

Each states the choice, the reason, and what was rejected. Rejected options stay listed so they are not re-proposed.

### D1. Transport → `multipart/x-mixed-replace` over stdlib `http.server`

Client is `<img src="/stream">`. Browser-native, no JavaScript on the display path.

**Rejected:** WebSocket (needs a dep; bidirectional value only arrives at stage 2) · SSE (text-only, base64 costs +33%) · WebRTC (enormous dep weight for a LAN image feed) · HTTP polling as the *primary* path (worse latency, more requests) · raw TCP + custom client (throws away the browser).

### D2. Encoding → **PNG**

Measured, not assumed: on AA-off glyphs and flat fills, PNG is **4× smaller than JPEG *and* pixel-exact**, where JPEG damages 6.8% of subpixels. LCD content is JPEG's worst case. Fidelity is the project's whole point; a lossy codec on a hand-calibrated display is the wrong trade in both directions here.

**Rejected:** JPEG (larger *and* lossy on this content) · WebP (pygame cannot write it without a new dep) · raw RGB (920 KB/frame) · video codec (dep weight, latency, lossy).

### D3. Zero new dependencies — hard constraint

No `[project.dependencies]` entry, nothing new for PyInstaller to bundle, no new `check_deps.py` alias. Serves `critical_lessons §3` (dep classification) and `§4` (deployment frame). If any part of this design starts to require a dependency, that is the signal to re-examine the design, not to add the dep.

### D4. Client page → **embedded Python string, not a shipped asset file**

The HTML lives as a module constant; PyInstaller bundles it into the exe automatically.

A `web/index.html` asset would need `project_root()` resolution, would have to be tracked by `/build` Step 2d staging, and would be a fresh instance of the `critical_lessons §2` / `§4b` class (program reads a file the build script does not ship). A short string has none of those failure modes.

### D5. Scaling → client-side, **fit-to-screen by default, 1:1 on tap**

The stream sends the surface at native size; the client decides how to present it. Server-side scaling would require a per-client stream.

**Default is fit-to-screen; tap toggles to 1:1 device-pixel mapping** (`naturalWidth / devicePixelRatio`, one source pixel on one *physical* device pixel, no resampling). Both modes carry `max-width:100vw; max-height:100vh`, so neither can overflow — the body is `overflow:hidden`, so an oversized frame is *clipped*, not scrolled, and the edges of the display silently vanish. 1:1 is therefore "1:1 unless that would overflow".

**Revised 2026-08-19: 1:1 was the default and is now the opt-in.** Author: *"as for zoom, i don't care as long as it's reactive of some sorts, meaning it does not overflow on a 'normal' resolution. resolution even smaller than my app's 1x drawing resolution i don't care."* Not-overflowing outranks not-resampling, and downscaling below 1× is explicitly acceptable. The original default also rested on a premise that has since gone — see the next paragraph.

**Revised from an earlier `image-rendering: pixelated` decision, which was wrong.** That reasoning assumed the stream carries one kind of content. It carries two: TIMS chrome drawn **anti-aliasing-off**, and LCD text drawn **anti-aliasing-on**. No single filter serves both — smooth blurs the chrome, `pixelated` wrecks the text. And the assumed direction was wrong too: on a phone the image is **downscaled** (730px into ~390 CSS px), where `pixelated` is at its most destructive, dropping 1px strokes outright.

The correct framing is not *"which filter?"* but *"can we avoid resampling?"* — at a non-integer ratio the AA-off look is unrecoverable regardless of filter, so the only faithful answer is not to resample.

**No longer true, and it was half the case for the 1:1 default:** 1:1 read visibly sharper than the app's own window because the process was DPI-unaware and Windows bitmap-stretched the window at 125% (#72 — *"the stream is a more faithful view of the app than the app is"*). `window_utils.declare_dpi_awareness` plus whole-multiple nearest-neighbour zoom fixed that at the source on 2026-08-14, closing #72. The window is now crisp on its own, so 1:1 buys only the absence of the *client's* resample.

### D6. Threading → main copies, server thread encodes

Main loop: `self.screen.copy()` + atomic reference rebind (0.37 ms, no lock — rebind is atomic under the GIL, and the copy is never mutated after publish). Server thread: encode + write.

**Rejected:** encoding on the main thread (4–7.5 ms into a 33 ms budget) · a lock (unnecessary; a one-frame-stale read is harmless) · sharing the live surface without a copy (torn frames mid-draw).

### D7. Frame pacing → fixed cap, no dirty detection

15 fps cap. At 3.4 KB that is ~51 KB/s — nothing on LAN or loopback.

Dirty detection was measured (1.11 ms) and **deliberately deferred**: it buys bandwidth that is not scarce. Revisit only if a real client proves it necessary.

**The client-count gate this decision specified was never built, and should not be** (corrected 2026-08-19 — it read "zero clients means the main loop does not even pay the copy", which the code has never done). `_clients` counts `/stream` handlers only, so gating `_publish` on it would freeze `_frame` for a client polling the D12 `/frame.png` fallback — the endpoint that exists precisely because multipart-in-an-`<img>` is historically flaky on iOS Safari. Publishing is unconditional once the hook is installed; the cost is one `surf.copy()` per present (measured 0.37 ms, 1.1% of a 30 fps budget) and it is bounded by the feature being off by default.

### D8. Server owned by `main.py`, above the setup↔drive loop

**Not** owned by `PASimulator`. `run()` returns `"home"` and `main.py` builds a *new* `PASimulator` for the next drive; a sim-owned server would hit a bind failure on drive #2 — and Windows `allow_reuse_address` semantics are worse than POSIX (it permits stealing a live socket, so the failure could be silent rather than loud).

The server spans the whole session. This means the tablet never sees the stream drop when the user returns to setup — so the page needs no reconnect JavaScript.

**The "swappable frame source" this decision originally specified was not built, deliberately** — § "What is mirrored" collapsed it away in the same design round, and `_publish` reads `pygame.display.get_surface()` on the present hook instead. There is nothing to register and no placeholder frame; between drives the hook simply publishes the setup screen, which is the desired behaviour anyway. Stage 2 may reintroduce a registered source (see § "What changed under this doc" on capturing the canvas) — if so it is a new decision, not this one being honoured late.

### D9. Bind mode → localhost default, LAN opt-in

`127.0.0.1` serves a same-PC browser (second monitor, free resize) with zero network exposure and no firewall prompt. `0.0.0.0` is required for a tablet and triggers the Windows Defender dialog on first run.

LAN ships **off by default**, opt-in, with the URL surfaced in-app. Bind-address resolution is a pure `config → address` function — same shape as `i18n.resolve_language`, and the natural unit-test seam.

### D10. Bind failure must be loud

A declined firewall prompt, or a public-Wi-Fi profile block, leaves a dead port. `except: pass` here would be a `critical_lessons §2` silent-skip. Bind failure surfaces a visible state (console + status band) and never fails silently.

### D11. Connection hygiene

Mobile browsers reconnect aggressively on screen-lock and network roam; each reconnect spawns a handler thread while the stale one blocks on write until an OS timeout. Explicit socket timeout, and `BrokenPipeError` / `ConnectionAbortedError` / `ConnectionResetError` handled as normal disconnects. Client count capped (browsers routinely open a speculative second connection, so a cap of 1 misbehaves — cap at 3).

### D12. `/frame.png` single-frame fallback endpoint

`multipart/x-mixed-replace` in an `<img>` is historically flaky on iOS Safari. A one-shot `/frame.png` endpoint is a handful of extra lines and lets the page fall back to polling if the multipart stream does not render. Cheap insurance against the target device being an iPad.

### D14. Display-teardown guard installed as a hook, not scattered

`main.py` (setup→drive) and `app.py:879` (`cleanup` on home-return) both call `pygame.display.quit()`, freeing the surface a streaming thread may be about to copy — a read-after-free race.

`frame_stream.install_display_quit_guard()` wraps `pygame.display.quit` so every teardown holds the frame lock, mirroring `window_utils.install_topmost_hook`. That codebase already learned this lesson once: the topmost pin regressed because it was scattered across `set_mode` sites instead of hooked. Guarding the call itself means a future teardown site cannot forget.

**Rejected:** wrapping each site by hand (two today, and the next one silently races) · importing `frame_stream` into `app.py` (couples the sim to an optional feature).

**The race it was built for is already closed, by a different change** (noted 2026-08-19). Capture moved to the present hook, so `_publish` fetches the surface on the MAIN thread and stores a copy, and `_snapshot` (server thread) only encodes that copy — no server thread ever touches the display surface. The guard is kept as belt-and-braces for a future teardown site, and the `paused` context manager it was paired with was deleted as dead code with no callers.

### D15. Launch flags first, in-app toggle later

`--stream` / `--stream-lan`, off by default. A launch argument is the cheapest thing to test against and needs no UI work; the in-app toggle can follow once the behaviour is proven.

### D13. No authentication

The LAN port is unauthenticated. Acceptable for an opt-in, off-by-default, home-LAN feature streaming a train display. Recorded as a known property, not a gap to close.

**Stage 2 widened what that means, and it is worth stating plainly:** the port is no longer read-only. `POST /tap` lets anything that can reach it click anywhere in the app — pick a route, change OCR settings, jump the train. The mitigations are unchanged and still the right ones (off by default, LAN is a separate opt-in flag, and the blast radius is a train display on a home LAN), but "someone on your Wi-Fi can watch" became "someone on your Wi-Fi can drive". If that ever stops being acceptable, the lever is a token in the URL the app prints, not a login screen.

**The caller is checked even so** (2026-08-19, review finding). A write endpoint on loopback is reachable from any page in the user's own browser — a CORS-*simple* `POST` (`text/plain`) needs no preflight and is sent — so `--stream` alone was NOT the zero-exposure posture D9 describes. `/tap` requires `Content-Type: application/json` (which forces a preflight this server answers with 501, having no `do_OPTIONS`) and a `Host` header among the bound addresses (which also closes DNS rebinding against `/stream` and `/frame.png`). Both are what the client already sends. T3 `test_stream.py` covers it, mutation-proven by removing the type gate.

---

## Known cosmetic issue

`press_transition` (`tims/widgets.py:404-410`) blocks ~130 ms with `pygame.time.delay` and its own `display.flip()`. The stream visibly freezes on every band button press. Cosmetic, not worth fixing for stage 1 — recorded so it is not mistaken for a streaming bug.

---

## Testing plan

Per `principles.md § "Test real logic, not ceremony"` — name the independent oracle or skip the test. Most of this feature is I/O plumbing with no logic core; these are the genuine seams.

| tier | test | oracle |
|---|---|---|
| T1 | bind-address resolution (`config → address`) | table of expected addresses per config; pure function |
| T3 | stream liveness — pull N frames, assert **distinct** as the source changes | a stale/hung server serves identical frames; a working one does not. Independent of implementation |
| T1 | tap mapping (`fraction, frame size → pixel`) | a tap lands where the finger was; corners are corners; nothing outside the image resolves to a pixel |
| T3 | tap round-trip — POST a tap, assert the click reaches the app's own event queue | stated in what every consumer reads (`event.pos`, `button == 1`), not in how the tap got there. Also pins that nothing reaches the queue before the main thread presents |
| — | fidelity of the streamed frame | **by-eye, exempt** per the project's rendering-exclusion rule |

T3 stream-liveness is the one that matters: the realistic silent failure is the server thread dying or pinning a stale frame, which no amount of "the page loads" checking catches. The probe already demonstrated it is buildable.

---

## Stage 2 — touch input (BUILT 2026-08-19)

**Scope, from the author:** *"IRL this thing is automatic. the PAs. so i don't expect user pressing touch screen will have any values. i think i only do what is accessible from the original program by mouse click."* And: *"setup flow is the biggest value for touch screen."*

That decided the design by deletion. A tap is a **synthetic left `MOUSEBUTTONDOWN`** posted into pygame's own queue, and nothing else:

- Production contains **no** `MOUSEBUTTONUP`, `MOUSEMOTION` or `mouse.get_pressed`. All 13 click consumers across 8 files — the whole TIMS setup flow, the tutorial, and the drive's click-to-jump — read `event.pos` off a `MOUSEBUTTONDOWN` with `button == 1`. So one forged event reaches every existing target with no change to any of them.
- The scope rule is then enforced by the **mechanism**, not by a list anyone has to maintain: a synthetic click cannot reach anything a real click cannot, and cannot miss anything a real click hits. Nothing has to be re-audited when a screen gains a button.
- Because the stream mirrors the **window**, a tap's frame is the window's frame — the coordinates every consumer already expects. No transform, no `app.py` change, and the capture-source question (§ "What changed under this doc") decouples from touch entirely.

**Dropped from the original stage-2 spec, all of it:** virtual PA/STA/pause buttons, `pending_next_sta` / `pending_pause`, per-consumer composition, the `tims.widgets` touch strip, the canvas capture. The PAs are automatic; a remote key for them has no value.

**The wire carries fractions, not pixels.** The client sends `{x, y}` in 0..1 of its `<img>` box; `frame_point` resolves them against the frame actually published. The client cannot know the frame's true size — it knows what its `<img>` last decoded, and the frame changes size under it (setup 730×610 → drive 730×420+band → tutorial 1100×500). Fractions also keep the arithmetic on the Python side, where a test can reach it.

**Threading.** A server thread only records the tap; the present hook replays it on the **main thread**, the same shape as the auto-driver's `pending_next_pa`. Draining happens *before* the frame is published, so `_frame` still holds the frame the remote was looking at.

**Zoom moved to its own button** (author: *"this means you use a separate zoom button for this"*). The whole-page tap gesture is gone — a tap now means "press the thing under my finger", so a page gesture would fight every button in the app. It is browser chrome rather than a pygame-drawn control: drawing it into the frame would either put it on the PC window too, or make the stream a composited view that no longer matches what the PC shows.

**Verified:** T1 `test_stream.py` (tap mapping, mutation-proven against removing the edge clamp) · T3 `test_stream.py` (tap → left click at the right pixel; ordering check mutation-proven by posting from the server thread) · end-to-end against the real app, where a tap on the TIMS home screen changed the screen and a dead-corner tap did not.

### The original stage-2 spec, for the record

- **Mouse half is easy.** `run()` already handles `MOUSEBUTTONDOWN`. Touch coords unscale to LCD-local and reuse `_click_target`. **Confirmed, and it turned out to be the whole feature** — see above.
  - **The coordinate half is already built, and the frames line up.** `app.py::window_to_canvas` / `window_to_lcd` (2026-08-14, `# CONTRACT:` naming #73, covered by T1 `test_window.py`) are the shared transform this doc listed as an unbuilt prerequisite. And because the stream mirrors the whole *window* surface, a tap's coordinates in the streamed image ARE window coordinates — so `window_to_lcd` is exactly the right call, not one to route around. The earlier note here said the opposite (call `_click_target` directly, because a streamed frame has no panel offset); that was written when the stream was assumed to carry the LCD region alone.
  - **This inverts if the capture source moves to the canvas** (§ "What changed under this doc"): the tap frame becomes canvas coords, `window_to_canvas` drops out of the path, and only the band-offset term remains. Decide the capture source BEFORE wiring taps.
- **Do NOT synthesize OS keystrokes.** `_handle_input_main` polls globally via `keyboard.is_pressed()` (`app.py:539`) because the app is a companion overlay while the *game* holds focus. `keyboard.press()` would inject a real keypress straight into JRE Train Sim Real.
- ~~**Reuse the existing pending-flag channel.** A tap sets `pending_next_pa` and inherits its retry semantics; add symmetric `pending_next_sta` / `pending_pause`.~~ **Not built** — no remote PA/STA/pause keys exist to need it. The threading SHAPE was kept: a server thread records, the main thread acts.
- ~~**Virtual buttons render in pygame, into the streamed frame**, with the web client a dumb image + coordinate reporter.~~ **Not built** — there are no virtual buttons. The argument still stands and still binds anything future: a control drawn into the frame is the only kind that can carry TIMS design, and the client stays a dumb image + coordinate reporter. The one browser-chrome control (the zoom button) is exempt because it is a property of the *viewer*, not of the app, and must not appear on the PC window.
- ~~**Press-flash over a stream** may be swallowed by latency. Plan local optimistic flash on tap.~~ **Moot for now** — real buttons flash themselves, and the flash is rendered by the app, so it arrives on the stream like any other frame. Revisit only if latency makes a real press feel unacknowledged.
- **The client's whole-page tap gesture has to move.** Tap currently toggles fit ↔ 1:1 (D5). Once a tap means "press the thing under my finger" that binding collides, so the zoom toggle needs its own affordance — a corner control or a double-tap — before the first virtual button lands.

---

## Cleanup surfaced by the consult

- ~~`small_size()` has no callers. Delete rather than carry.~~ Done — it survives only in `old_version.py`, which is retained reference (`conventions.md` § Tooling).

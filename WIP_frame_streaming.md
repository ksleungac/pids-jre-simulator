# WIP — LAN frame streaming (browser / tablet second screen)

**Tracking:** [#71](https://github.com/ksleungac/pids-jre-simulator/issues/71) · grew out of [#1](https://github.com/ksleungac/pids-jre-simulator/issues/1) (contributor request for mobile/tablet support).

**Status:** spec locked 2026-07-20 after a `/third-man` design consult. **Stage 1 built and smoke-tested against the live app.**

Files: `frame_stream.py` (new) · `main.py` (flags + server start/stop) · `_tests/t1_unit/test_stream_bind.py` · `_tests/t3_invariant/test_stream_liveness.py`. **`app.py` untouched.**

Run: `uv run main.py --stream` → `http://127.0.0.1:8420/` · `--stream-lan` for a tablet.

---

## EDIT-CONTRACT

- **Holds:** the locked spec, the rejected alternatives (so they are not re-proposed), and transitional notes while the feature is in flight.
- **Does NOT hold:** anything already true of shipped code — that belongs in `APP.md`. Measurements that stop being decision-relevant get cut, not archived.
- **Rejected alternatives stay** until graduation — they are the record of what was already considered.
- **Graduation trigger:** when mirroring becomes a real user-facing feature (an in-app toggle rather than a launch flag), dissolve into `APP.md` (§ streaming) and delete this doc. Single-commit restructure, no parallel-existence period. Stage 1 shipping as a launch-flag-only feature is NOT the trigger — the doc still holds the stage-2 spec and the rejected alternatives.

---

## Why streaming and not a port

Decided 2026-07-20. Do not re-litigate without new information.

- A React/DOM/Kivy/WASM rewrite means **owning two renderers**. Every train model (E233-0, E231-500 next) and every calibration round paid twice, on a project whose whole value is calibration fidelity.
- `audio/` is **558 MB** (Tōkaidō 140 · Keihin 111 · Chūō 93 · Yamanote 45 · Sōbu 12). Not bundleable into a mobile/WASM build. Streaming leaves assets on the PC.
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
- **"Renderers need no changes, so it's free"** — true but misleading. `_handle_lcd_click` (`app.py:480-482`) and `_update_hover_cursor` (`app.py:495-498`) map window→LCD coords by subtracting a fixed `panel_h`. The moment the window blits a *scaled* surface, click-to-jump and the hover cursor silently misfire. Converting the surface does not do that work — it only makes the bug reachable.

That change belongs to the **reactive-window** roadmap item, where its real deliverable is a shared window↔LCD coordinate transform consumed by both call sites, and where its cost is visible and paid deliberately. Filed separately.

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

### D5. Scaling → client-side, **1:1 device-pixel by default**

The stream sends the surface at native size; the client decides how to present it. Server-side scaling would require a per-client stream.

**Default is 1:1 device-pixel mapping** — the image is sized `naturalWidth / devicePixelRatio` so one source pixel lands on one *physical* device pixel, with no resampling at all. Tap toggles to fit-to-screen.

**Revised from an earlier `image-rendering: pixelated` decision, which was wrong.** That reasoning assumed the stream carries one kind of content. It carries two: TIMS chrome drawn **anti-aliasing-off**, and LCD text drawn **anti-aliasing-on**. No single filter serves both — smooth blurs the chrome, `pixelated` wrecks the text. And the assumed direction was wrong too: on a phone the image is **downscaled** (730px into ~390 CSS px), where `pixelated` is at its most destructive, dropping 1px strokes outright.

The correct framing is not *"which filter?"* but *"can we avoid resampling?"* — at a non-integer ratio the AA-off look is unrecoverable regardless of filter, so the only faithful answer is not to resample.

Confirmed against the device: 1:1 is visibly sharper than the app's own window, because that window is bitmap-stretched by Windows display scaling (125%). See #72 — **the stream is currently a more faithful view of the app than the app is.**

### D6. Threading → main copies, server thread encodes

Main loop: `self.screen.copy()` + atomic reference rebind (0.37 ms, no lock — rebind is atomic under the GIL, and the copy is never mutated after publish). Server thread: encode + write.

**Rejected:** encoding on the main thread (4–7.5 ms into a 33 ms budget) · a lock (unnecessary; a one-frame-stale read is harmless) · sharing the live surface without a copy (torn frames mid-draw).

### D7. Frame pacing → fixed cap, no dirty detection

15 fps cap. At 3.4 KB that is ~51 KB/s — nothing on LAN or loopback.

Dirty detection was measured (1.11 ms) and **deliberately deferred**: it buys bandwidth that is not scarce. Revisit only if a real client proves it necessary.

**Publishing is gated on connected-client count** — zero clients means the main loop does not even pay the copy.

### D8. Server owned by `main.py`, above the setup↔drive loop

**Not** owned by `PASimulator`. `run()` returns `"home"` and `main.py` builds a *new* `PASimulator` for the next drive; a sim-owned server would hit a bind failure on drive #2 — and Windows `allow_reuse_address` semantics are worse than POSIX (it permits stealing a live socket, so the failure could be silent rather than loud).

The server spans the whole session, with a **swappable frame source**: the sim registers on entry, unregisters on exit, and the server serves a placeholder frame when no drive is active. This also means the tablet never sees the stream drop when the user returns to setup — so the page needs no reconnect JavaScript.

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

### D15. Launch flags first, in-app toggle later

`--stream` / `--stream-lan`, off by default. A launch argument is the cheapest thing to test against and needs no UI work; the in-app toggle can follow once the behaviour is proven.

### D13. No authentication

The LAN port is unauthenticated. Acceptable for an opt-in, off-by-default, home-LAN feature streaming a train display. Recorded as a known property, not a gap to close.

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
| — | fidelity of the streamed frame | **by-eye, exempt** per the project's rendering-exclusion rule |

T3 stream-liveness is the one that matters: the realistic silent failure is the server thread dying or pinning a stale frame, which no amount of "the page loads" checking catches. The probe already demonstrated it is buildable.

---

## Stage 2 — touch input (specified, NOT built)

- **Mouse half is easy.** `run()` already handles `MOUSEBUTTONDOWN` (`app.py:397-412`). Touch coords unscale to LCD-local and reuse `_click_target`.
  - **Coordinate-frame trap:** `_handle_lcd_click` takes *window* coords and subtracts the panel offset itself (`app.py:481`). A streamed frame has no such offset. The touch path must call `_click_target` directly rather than reuse the window-coord contract, or clicks land on the wrong station. Same trap the reactive-window work has to solve — shared solution.
- **Do NOT synthesize OS keystrokes.** `_handle_input_main` polls globally via `keyboard.is_pressed()` (`app.py:539`) because the app is a companion overlay while the *game* holds focus. `keyboard.press()` would inject a real keypress straight into JRE Train Sim Real.
- **Reuse the existing pending-flag channel.** `pending_next_pa` is the proven background-thread → main-thread signal (the OCR driver sets it; `_handle_input_main` consumes it behind the audio-busy gate from `critical_lessons §5`). A tap sets the same flag and inherits the retry semantics. Add symmetric `pending_next_sta` / `pending_pause`.
- **Virtual buttons render in pygame, into the streamed frame** — reusing `tims.widgets.draw_tims_button` + `tims.chrome` presets — with the web client staying a dumb image + coordinate reporter. HTML/CSS buttons would be a second UI toolkit and a second design language, destined to drift from the TIMS conventions. Same "do not own two renderers" argument that decided the whole feature.
- **Press-flash over a stream** may be swallowed by latency. Plan local optimistic flash on tap, with the pygame-rendered flash as authoritative confirmation.

---

## Cleanup surfaced by the consult

- `small_size()` (`app.py:881`) has no callers. Delete rather than carry.

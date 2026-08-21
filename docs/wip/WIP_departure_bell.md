# WIP — Departure-bell box (発車ベル)

**Tracking:** [#131](https://github.com/ksleungac/pids-jre-simulator/issues/131) (parent outcome —
a second window that mirrors the STA action) → [#132](https://github.com/ksleungac/pids-jre-simulator/issues/132)
the drawing, [#133](https://github.com/ksleungac/pids-jre-simulator/issues/133) window + wiring,
[#134](https://github.com/ksleungac/pids-jre-simulator/issues/134) streaming.

**Status:** stage 1 only. `departure_bell.py` renders all four states and nothing imports it — the
app is untouched, so the box exists solely under `_dev_scripts/preview_bell.py`. Author signed the
drawing off 2026-08-21. Stages 2 and 3 are unstarted.

---

## EDIT-CONTRACT

- **Holds:** the mental model, the author's spec verbatim, the platform facts stages 2–3 depend on
  (each one cost a probe to establish), and the rejected alternatives.
- **Does NOT hold:** anything already true of shipped code. Drawing rules live in the
  `# CONTRACT:` blocks in `departure_bell.py`; geometry lives in its `_TUNEABLES_BELL_*` dicts.
  Neither is restated here — a second copy is what drifts.
- **Graduation trigger:** when the bell window and its stream view both ship, dissolve the
  remaining platform facts into `docs/APP.md` (window lifetime) and `frame_stream.py`, and delete
  this doc.

---

## Mental model

The conductor steps off the train and presses **ON**. It latches — stays pressed in — and the
departure melody starts and repeats. Pressing **OFF** (momentary, does not stay in) releases the ON
latch: the melody stops and the door-closing announcement plays.

That is exactly what Page Up already does. So the box is **a second face on an action that already
exists**, not a new feature with its own state. Its ON button being pressed in is a picture of
`AudioPlayer.is_sta_looping()` and nothing more.

The consequence that shapes everything: the box may be closed, minimised or never opened, and the
Page Up path must be untouched by that. A bell that owned state would break this; a bell that only
reads audio cannot.

## The author's spec

Stated 2026-08-21, kept verbatim because a re-derived scope comes back narrower:

- a new separate window alongside the PA program, showing only the drawn bell "as if like IRL"
- synced with the Page Up action; the user can also click it with the mouse
- also streamed to the remote LAN stream alongside the other screen, with **touchscreen press**
- the user can close or minimise it and **nothing** is affected — "our sta page up logic works no
  matter what"
- **always on, same residency as the PA window**
- **no** way to reopen it once closed
- **keep the photo's wording** — 発車ベル, not 発車メロディー
- the reference photo is drawing reference only; no licensing or source concerns
- implementation order: "UI first, enumerate this button in all states, nail the graphics first,
  then wire the app window up and function. then last is frame streaming"

## Stage 1 — the drawing (done)

`departure_bell.py` (project root, production) + `_dev_scripts/preview_bell.py` (state strip,
`--compare` against the photo, `--state` for one).

The one thing worth carrying forward is the **framing**, because it was arrived at by getting it
wrong first. An early draft rendered the caps with a receding side wall — a photographic cue — and
the author's reaction was *"your button now looks like a 3d, but let me think, are me modelling a
front side view of a 3d object in 2d?"*, then the resolution: *"think of you are modelling asset for
a 2d pixel game. this is the mental model. so do whatever you can to make it look good."*

So there is no camera. Depth is one convention applied everywhere, and it lives in `_panel(raised=)`.
The reference settles proportion and colour; it does not settle how a surface is shaded.

**Rejected along the way** (do not re-propose):

- *A chamfered silhouette for the enclosure.* The casting is three levels — an outer body carrying
  the screws on a low shelf, a raised plateau whose corners are cut to clear them, and a lit ramp on
  the step between. One chamfer loses the shelf. (Author: *"first the 4 corners of where the screws
  are, those needs fixing. the geometric shapes changes as there"*.)
- *Typesetting ON / OFF.* The cap lettering is engraved industrial signage with a capsule `O`.
  None of the four Latin faces we ship draws that — Helvetica and Frutiger are both round — and a
  new font file is a `THIRD-PARTY.md` entry plus a licence question for four characters.
- *A pressed cap drawn as a recess.* See the `_draw_cap` CONTRACT; it is the error that reads as
  wrong without being nameable.

## Stage 2 — window and wiring (unstarted)

Each of these cost a probe; they are the reason this doc exists.

| Fact | Consequence |
|---|---|
| `pygame._sdl2.video.Window` coexists with `display.set_mode` (pygame 2.6.1 / SDL 2.28.4) | a real second OS window is available with no new dependency |
| `MOUSEBUTTONDOWN` carries `event.window` (`None` = main window) — pygame's own docs are stale on this | per-window click routing works; `app.py`'s existing handlers (band click, LCD click-to-jump) need `event.window is None` guards or they will claim bell clicks |
| `WS_EX_NOACTIVATE` and SDL `tooltip` both fail to keep focus | remember-and-restore via `GetForegroundWindow` / `SetForegroundWindow` works — Windows permits it because focus is being *given away*, not stolen |
| **`pygame.display.quit()` destroys `_sdl2` windows silently** — read-after-free, garbage `.size`, no exception | the bell's lifetime must be drive-start to drive-end. `set_mode()` alone does not do this |
| `install_topmost_hook` wraps `set_mode` only | the bell window needs its own pin (`win32gui.FindWindow` by title) |

Wiring: ON and OFF call the same entry Page Up calls. `BellState.of()` is the sole audio → picture
mapping and is pure, so a test can drive it with no mixer, window or route.

`on_flash` and `on_latched` render identically — pressing ON starts the loop immediately, so there
is no in-between. The flash only matters at a stop with no melody, where nothing latches.

**The atlas gate:** the 発車ベル plate goes through `lcd_font`, so the baker must reach that label
or a shipped build raises on it. ON/OFF are drawn, not typeset, so they need nothing.

## Stage 3 — streaming (unstarted)

A second view on the existing `frame_stream` page, docked beside the LCD, plus a tap route.

`departure_bell.hit_test` already takes canvas coordinates and already serves the local window, so
one geometry answers both and the hit-rects cannot drift from what is drawn. Taps are fractional,
not pixel. The `Content-Type: application/json` + `Host` checks guarding `POST /tap` apply unchanged
— see `conventions.md § Tooling` on why a write endpoint on loopback is not "no exposure".

## Open

- The author is looking for a **straight-on reference photo**. The one we have is shot from
  below-left and is a 387px JPEG, so it cannot settle anything to the pixel — and it happens to
  show the box **mid-state** (ON low, OFF proud), which is the *ringing* picture, not the resting
  one. There is no photograph of the box at rest.
- Registering the bell in `_dev_scripts/calibration_editor.py` was offered and not taken. Worth it
  if stage 2 turns into another tuning round, since it would let the author drag rather than
  describe.

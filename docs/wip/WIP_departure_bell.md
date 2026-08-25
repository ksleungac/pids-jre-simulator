# WIP — Departure-bell box (発車ベル)

**Tracking:** [#131](https://github.com/ksleungac/pids-jre-simulator/issues/131) (parent outcome —
a second window that mirrors the STA action) → [#132](https://github.com/ksleungac/pids-jre-simulator/issues/132)
the drawing, [#133](https://github.com/ksleungac/pids-jre-simulator/issues/133) window + wiring,
[#134](https://github.com/ksleungac/pids-jre-simulator/issues/134) streaming.

**Status:** all three stages built, none committed, and the author has not yet met the box in a live
drive. The drawing was signed off 2026-08-21 and again 2026-08-22 after a second tuning round against
two further photographs. `bell_window.py` opens the box beside the PA window during a drive and
routes its clicks; `frame_stream` docks it into the streamed frame and routes taps back; both press
paths land on `PASimulator._bell_press`, which is the only place the latch/momentary rule lives.
`_tests/t1_unit/test_bell.py` and `test_stream.py` § 3 lock the pure halves.

**The graduation trigger below is now met** — deliberately not acted on yet. Dissolving this doc
into `docs/APP.md` and `frame_stream.py` deletes the design record, and it should outlive the first
live drive rather than the first green test run.

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

## Stage 2 — window and wiring (done)

`bell_window.py` holds the window; the platform facts behind its shape are in its module docstring,
where an editor meets them. Two things belong here rather than there, because they are about how the
knowledge was arrived at and what it costs stage 3.

**One recorded fact in this doc was wrong, and it was wrong in the direction that reads as working.**
The line above said `WS_EX_NOACTIVATE` fails and remember-and-restore via `SetForegroundWindow`
works. Measured 2026-08-22, it is the other way round: handing the foreground back desynchronises
SDL's mouse-focus tracking, so the FIRST press registers and every later one is swallowed — 1 of 4
presses under restore, against 6 of 6 under `WS_EX_NOACTIVATE`, with the foreground never leaving
the unrelated app that held it. The earlier probe most likely conflated two things: SDL activates a
window when it SHOWS it, whatever ex-style it carries, so a window created visible steals focus once
at birth and `WS_EX_NOACTIVATE` looks ineffective. Creating it `hidden=True` and revealing it with
`SW_SHOWNOACTIVATE` separates them. A platform fact carried across a context boundary is a claim
with a date on it, not a settled result — re-measure the one your design turns on.

The click-routing note also over-specified: `event.window` is real, but the existing handlers need no
`event.window is None` guards. One branch at the top of the run loop matches the bell's `Window`
object by identity and consumes, so nothing below it sees a bell event — and that stays true as
handlers are added, which per-handler guards would not.

**The box is a peer of the PA window, not a satellite of it** (author, 2026-08-23). Two consequences,
and the first cut got both wrong:

- *Always-on-top is a property it carries continuously, not a state set once.* The PA window
  re-pins on every `set_mode` through `install_topmost_hook`; this window never goes through
  `set_mode`, so it re-asserts every frame instead. It has to: **SDL's own `SetWindowSize` clears
  `WS_EX_TOPMOST`**, so the box silently fell out of the topmost band the first time it was resized.
- *Its zoom is its own.* It opens from the screen alone (`window_utils.pick_default_zoom` at a 0.25
  share against the PA window's 0.40 — one rule, parameterised, not a second copy), is resizable
  with the same whole-multiple snap, and remembers its choice as `bell_zoom` in settings. The PA
  window's zoom neither drives it nor is driven by it.

Wiring notes worth keeping:

- ON and OFF both route to `_next_sta`, and the box's whole contribution is the asymmetry: ON
  latches so it only acts when nothing is looping, OFF is momentary so it only acts when something
  is. Collapsing that into one unconditional call is the natural simplification and is silently
  wrong — locked by `test_bell.py` § 4.
- `on_flash` and `on_latched` render identically, because pressing ON starts the loop immediately.
  The flash only matters at a stop with no melody, where nothing latches.
- **The atlas gate is met by a render inside the baker's `sweep()`, not by a declaration alone.** A
  `draws=` declaration widens the domain of a combo the recording SAW; a call site no swept state
  reaches is never recorded at all, and the box lives in a window the sweep does not open. The
  literal audit was widened at the same time, from `displays/**` to that plus any root module
  importing `lcd_font`, so a future never-drawn label in the box is caught rather than assumed.
  Proven in the frame that matters: `--verify-shipped` renders the box with no ShinGo on disk.

## Stage 3 — streaming (done)

The box is docked into the published frame rather than served as a second stream: one `<img>`, one
connection, one tap route, and the page needs no change at all — it already handles the frame
changing size, which is the only thing docking does to it.

**The load-bearing decision is that the dock is legitimate at all.** `frame_stream`'s existing
comment on the 1:1/FIT button says a control drawn into the frame would "make the stream a
composited view that no longer matches what the PC shows", and reads as a prohibition on exactly
this. It is not: the box is a real second OS window on the PC, so putting it in the frame mirrors
what the PC displays rather than inventing a remote-only control. That reading has a consequence
that settles a question the issue left open — **when the user closes the box on the PC, it must
leave the stream too**, which is why `BellWindow.surface()` returns None once closed and why the
frame drops back to the LCD's own size.

The box is docked at whatever size the PC window is showing it, not at 1x, for the same reason.

Three seams, so the layout and the routing cannot disagree:

- `frame_stream.compose(main, side)` returns the frame AND where the dock landed. One arithmetic,
  used by both the blit and the hit-routing.
- `frame_stream.tap_event(pt, side)` is the whole routing decision: a tap inside the dock carries
  `side_view=True` and the dock's OWN coordinates, so its consumer never learns where the dock was
  placed. Everything else is the unmarked event this file has always posted.
- `BellWindow.tap()` resolves through the same `_cap_at` a local click uses, and lights the same
  flash — so a remote press is acknowledged on the PC's box as well.

`frame_stream` never learns what the docked view IS. It is `set_side_view(surface_or_none)` and a
rect; `app.py` knows it is a bell. Only the page's button copy names it, because "SIDE VIEW" would
tell a reader nothing.

**Each viewer picks what to look at** (author, 2026-08-23) — BOTH / PIDS / BELL, because docking
costs the PIDS about a fifth of its width on a phone, and someone standing away from the PC to press
the bell wants the box full-screen and finger-sized. Three decisions behind it:

- **A query parameter on `/stream`, not a POST.** It is a READ, so no write endpoint is added and
  the `POST /tap` posture is untouched — and being per-request it is per-viewer with no server
  state, so two devices can watch different things. The cost is one reconnect on switch, which the
  page's existing `onerror` already handles.
- **Composition moved from publish to snapshot.** `_publish` now stores the two sources; `compose`
  runs per view on the server thread, cached per view. So a view nobody is watching costs nothing,
  and the render thread does one surface copy as before. Both sources are copies — the
  never-hold-the-display-Surface contract is about `_publish`, which is still the only thing that
  touches the live surface.
- **A tap carries the view it was measured against.** The same fraction is a different point in
  each view: 0.5/0.42 is the ON cap in BELL and a point in the route bar in BOTH. Verified both
  ways round rather than assumed.

Asking for BELL when nothing is docked falls back to the PIDS rather than serving an empty frame —
the rule stays "show what the PC shows".

**That fallback had a bug in it, reported from the setup menu and worth keeping written down.** The
BELL view was offered everywhere, including the setup flow where no bell window exists. There it
served the setup screen, so the button looked dead — and a tap in that state was silently RE-AIMED
at the fallback: measured, a tap at the ON cap's position resolved to (365, 256) of the 730x610
setup screen, which is inside a TIMS button. A dead-looking control was the symptom; pressing a
real button the user never aimed at was the defect.

Two fixes, and they are independent on purpose:

- **`tap_target(view, has_dock)` drops a tap for a view that is not on screen.** Showing a fallback
  frame is a kindness — a frame beats a broken `<img>`. Resolving a tap against it is not. A miss
  is the correct outcome and the one a real mouse gives, which is the same reasoning `_drain_taps`
  already applies to a tap arriving across a screen change. This half holds for a stale bookmark
  and for a client that has not polled yet, so it does not depend on the next fix.
- **`GET /views` tells the page whether a dock exists**, and the control hides itself when there is
  none. On the setup menu there is one window, so all three views are the same picture and there is
  no choice to offer. Polled at 2s rather than pushed — an `<img>` stream carries no side channel,
  and the setup→drive transition is human-paced. It is a READ endpoint, so no write surface is
  added; the one bit it discloses is already visible in the frames.

The `Content-Type: application/json` + `Host` checks guarding `POST /tap` apply unchanged — see
`conventions.md § Tooling` on why a write endpoint on loopback is not "no exposure". No endpoint was
added, so the endpoint set did not grow and the posture is unchanged.

## Open

- The straight-on reference arrived 2026-08-22 — two of them, and they are **not the same casting**
  as `_references/bell/sta-bell.jpg`. Which photograph settles which question is recorded in
  `departure_bell.py`'s docstring, where the anchors are. The one thing to carry: a shot taken from
  below the box compresses it vertically, so sizes transfer from `sta-bell.jpg` and placements down
  the box do not — the cap gap reads 0.19 of a cap there against 0.31 straight on.
- **The two new photographs are untracked at the repo root** (`bell_2.png`, `bell_3.png`, plus a
  re-crop as `bell_1.png`) and a tidy pass will delete them. They are third-party reference imagery,
  so moving them under `_references/bell/` is a `THIRD-PARTY.md` question, not a `git add` — ask
  before either.
- Registering the bell in `_dev_scripts/calibration_editor.py` was offered and not taken. Worth it
  if the drawing turns into another tuning round, since it would let the author drag rather than
  describe.
- **A press sound is deliberately deferred, not rejected** (author, 2026-08-23: *"don't let this
  block us"*, noting the STA press has no feedback either). The sound is the **KAK** — the same
  artifact `/sta-make` documents and splices out: the attendant's spring-release on OFF, and
  sometimes a press-on click at the melody's start. So it is a recording we already made and
  removed, recoverable from `audio_src/` or `audio/_archive/`, not something to synthesise. The
  author's objection to the obvious implementation is that one sample repeated is what makes a box
  sound like a UI button; the answer to that is a pool cut from a SINGLE line (~20 files each carry
  one, so ~20 real presses of one machine) rather than pitch-jitter or a cross-line mix, which
  would sound like a different machine each press. Undecided and unscoped — do not open an issue
  for it, and do not go near the recordings without `/sta-make` loaded.

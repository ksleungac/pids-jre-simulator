# WIP — Pre-rendered font atlas (drop proprietary font software from the ship)

**Tracking:** [#114](https://github.com/ksleungac/pids-jre-simulator/issues/114) (parent outcome —
the shipped build stops carrying font software) → [#115](https://github.com/ksleungac/pids-jre-simulator/issues/115)
ShinGo atlas, [#116](https://github.com/ksleungac/pids-jre-simulator/issues/116) Helvetica/Frutiger
(`deferred`, so `fonts/` still ships).

**Status:** the shipped path for ShinGo, and verified as such. Committed 2026-07-30 (`6e5a04a`,
coverage from `draws=` declarations rather than a state sweep). On 2026-08-01 a real PyInstaller
build ran with no ShinGo font files staged and the author smoke-tested it — the first time the atlas
had rendered a character outside the dev tree, and it did **not** work until two deployment-frame
bugs were fixed that day (§ The frame nothing tested). Remaining scope is
[#116](https://github.com/ksleungac/pids-jre-simulator/issues/116) — Helvetica and Frutiger are
unbaked, so `fonts/` still ships and this doc stays alive until they follow.

---

## EDIT-CONTRACT

- **Holds:** the goals in priority order, the design, the numbers the design rests on, the rejected
  alternatives, and the gates. Transitional notes while in flight.
- **Does NOT hold:** anything already true of shipped code — that belongs in
  `conventions.md § Tooling` (font rules) and `/build`. Measurements that stop being
  decision-relevant get cut, not archived.
- **Graduation trigger:** when the atlas is the shipped path and the proprietary faces are out of
  the tracked tree, dissolve into `conventions.md § Tooling` + `/build` and delete this doc.

---

## Goals, in priority order

Stated by the author 2026-07-27. This ordering decides every trade-off below — do not re-rank it.

1. **The atlas produces 100% identical output to current rendering.** Binary bar, not a tolerance.
   Zero pixel difference.
2. **The development flow is exactly the same.** Editing an LCD — position, font size — behaves as
   it does today with direct font rendering. No regeneration step in the iteration loop.
3. **The problematic fonts leave shipping and distribution.**

Everything else is a bonus and must never be traded against those three. Atlas byte size is **not**
a goal — author: *"no matter how you compress it's not going to be bigger than a font file, even it
is bigger i don't care"* — conditional on only what is needed going in, not an indiscriminate dump.

## Why

`fonts/` holds three commercial families — `ShinGoPr6N` (Morisawa), `HelveticaNeue` and
`NeueFrutigerWorld-Bold` (Monotype), 17.0 MB across 7 files, all seven in the release zip. A licence
was bought for the ShinGo but does not extend to redistribution.

Copyright protects font **software** — outlines and hinting as a program — not the typeface
**design**. Shipping the `.otf` redistributes the protected artifact and is hash-identifiable;
shipping raster output of the same design is a materially different act. No history rewrite (decided
2026-07-27) — forward-clean only.

---

## Design

**The atlas stores what the production code produced.** Not glyphs, not a layout model, not a
declaration of what text exists. That single rule is what the design is, and everything below
follows from it.

**One layout implementation.** `displays/utils.py::compose_text_parts` is the only place LCD text
layout exists — the four branches (latin, compression, collapse, even-spacing-with-`exp`) live there
and nowhere else. It carries a `# CONTRACT:` block saying so. `draw_text_given_width` blits what it
returns.

**The unit of storage is that function's return value: a part list.** `[(offset_from_x, surface)]`,
each surface already coloured and already scaled, each offset an integer. Runtime blits them in
order — the same sequence of blits the LCD has always performed — so LIVE and ATLAS differ only in
where the surfaces came from.

**Deliberately not flattened into one block surface.** Measured: flattening cost **90 differing
pixels across 36 frames.** The compression branch can place adjacent characters a pixel apart from
their scaled widths, and compositing an overlap onto transparency then blitting the result is not
the same operation as blitting each part onto the background in turn. Handing back the parts makes
the atlas exact by construction instead of by measurement.

**Everything the renderers ask a font for is recorded, not just layout.** Several elements bypass
`compose_text_parts` and call the font directly, so the atlas also holds `render` output, the opaque
`render(..., background)` form as SDL composited it, `size` results, per-character `metrics`, and the
`get_height` / `get_ascent` scalars.

Two constraints that are load-bearing rather than incidental:

- **`metrics` must never conflate "no glyph in this face" with "not baked".**
  `transfer_info.py:86` uses `metrics(ch)[0] is None` as a live coverage probe driving CJK fallback.
  An unbaked character raises; it does not return `None`.
- **Font identity travels ON the font object** (`font_atlas.LcdFont`, a `pygame.font.Font`
  subclass). A side table keyed by `id(font)` looked equivalent and was not: `force_mode` clears the
  font cache, CPython reuses the freed address, and the stale entry claimed an unrelated font — a
  bare `HelveticaNeue-Medium@24` was identified as `ShinGoPr6N-Medium@11` and routed into the atlas.
  Subclassing is what makes the attribute possible; the C type rejects attributes directly.

**Colour is part of the key** rather than reapplied at blit time. The part surfaces are already
coloured, several of them scaled; re-deriving a flat colour from that is an argument that would have
to keep being made, and the colour set is small.

**Dev renders live, so goal 2 holds by construction.** Mode is chosen by what exists: `fonts/`
present → LIVE, absent → ATLAS. Every dev run, `preview_display.py` and the calibration editor load
the real fonts as before; a nudged size renders immediately with no atlas in the loop. Only the
shipped artifact reads the atlas, and a layout edit is a re-bake at build time.

**Nothing in `_dev_scripts/` reasons about layout or text sources.** The baker drives the real app
and keeps what it gets. Two earlier versions did reason for themselves — a declared combo table and
a text domain read out of `route.json` — and both were wrong in ways that render as plausible-looking
output. The failure they share is a second implementation of a production decision, which is the same
shape as a proof script that re-derived `draw_train_type`'s box geometry and consequently showed
two-character train types without their `exp=7` spread while reporting zero pixel difference.

**Coverage rests on the sweep being exhaustive, not on a declaration.** Every shipped route × every
stop × every mode × every view × every PA phase = **10,476 states**. Sampling cannot substitute: a
61-state sweep missed all nine transfer-panel sizes because no sampled stop had an interchange in
window, and a data-derived domain missed the 18 stations in `sobu/1217F`'s `pre_stops`.

**Staleness is loud.** The manifest carries a fingerprint of `data/*.json` + every shipped
`audio/**/route.json`. On mismatch the atlas refuses to load and names the fix, so new route or
transfer data cannot silently render as tofu. Author's stated requirement: *"if i add new
informations in transfer or audio data that covers outside yout atlas, it must fail loud or
automatically refresh."*

### Current numbers

16 combos, **2.1 MB**, 14 sheets + manifest, one sheet per combo named for the face and size. The
route-bar labels (Medium@25/@30) come through as direct `render` calls per character; the station
names (Medium@78) as 366 laid-out texts totalling 1366 parts.

---

## The gates

Five, all mechanical, all required, all wired into `/build` (which stops on any non-zero). Goal 1 is
binary so its test is binary. Grouped by what they can and cannot see:

**Inside the bake** — these run before anything is written:

1. **Source-literal audit** — a Japanese literal in display code that no swept state drew. It is a
   gate rather than a cook input because the scan finds the string but cannot know which combo draws
   it; baking it blind would put the 50-character route disclaimer at size 78.
2. **Declared coverage** — every text a call site's `draws=` resolves to must be present in the
   manifest just written. **The only gate whose oracle is not the sweep**: the domain comes from
   `resolve()`, the witness from the written manifest. It reads the manifest rather than
   `cook_from_data`'s own record on purpose — checking a generator against its own log is
   `critical_lessons § 9` one level down, and the packing/write path sits between the two.
3. **Undeclared-site ratchet** — an `lcd_font` call with no `draws=` fails the bake. The migration
   reached zero; an undeclared site silently reverts that combo to coverage-by-reachability, which
   is the dependency the declarations exist to remove. This is the gate a NEW TRAIN MODEL meets:
   forking adds a dozen call sites at once and the copy-the-sibling convention carries the renderer,
   not the judgement about where its text comes from.

**Sweep-driven** — breadth, not coverage:

4. **`--verify`** — re-drive every shipped state in ATLAS mode with the baked faces made unreadable
   (`pygame.font.Font` patched to raise on an atlas face), so a path that *constructs* one is caught
   even though the dev tree has every file. *0 raised across 21,978 frames.*
5. **`--pixel-verify`** — render every state twice, LIVE then ATLAS, compare frame digests. Coverage
   says an entry existed; this says it was the right pixels. *0 of 21,978 differ.*

**Outside the dev frame** — see § The frame nothing tested:

6. **`--verify-shipped`** — build the staged shape in a temp dir (`fonts/` with the baked families
   deleted, no `displays/`) and drive the real app there in a subprocess, redirecting the project
   root before any display module imports. Seconds, no PyInstaller run needed.

**Retired: the pre-atlas worktree diff.** It caught the one thing the others could not — a refactor
that changed rendering and then got faithfully stored (the 90-pixel flattening cost) — and it
expires structurally, since a model authored after the atlas has no pre-atlas commit to diff
against. It was never committed as a script and is not worth reconstructing now that `--pixel-verify`
covers 21,978 states.

**Both sweeps must pin every clock, including SDL's.** Freezing Python's `time` is not enough:
the multi-PA hint blinks on `(pygame.time.get_ticks() // 500) % 2`
(`e235_1000/upper_lcd.py:709`), which patching the `time` module cannot reach. Unpinned, the two
passes catch the blink in opposite phases and the run reports ~1150 phantom mismatches — a
*different* ~1150 each time. Localising one of them showed zero difference when that state was
rendered in isolation.

**A multi-pair comparison must score each pair on its own availability.** Gating both pairs on all
three trees succeeding let a failure in the third empty the first pair's sum, which then printed `0`
and read as a pass.

---

## The frame nothing tested (2026-08-01)

Five gates and 21,978 states of pixel-identical proof, and the atlas had **never rendered a character
outside the dev tree**. It did not work there. Two bugs, stacked, both invisible to everything above:

1. **`mode()` answered LIVE in the staged folder.** It asked "does `fonts/` exist" to decide "can I
   load ShinGo". Those are the same question only while `fonts/` is all-or-nothing — and `/build`
   staging a **partial** `fonts/` (Helvetica and Frutiger stay, the Morisawa faces go) is exactly
   what separates them. So the atlas was never consulted and every ShinGo load went at a file the
   build had just deleted: `FileNotFoundError` on the first station name, for every user.
2. **Forcing ATLAS did not save it.** `code_fingerprint()` globs `displays/**/*.py`, which `/build`
   excludes from the staged folder because PyInstaller bundles it into the exe. It therefore hashed
   an *empty file list* — `e3b0c442…`, the hash of nothing — against a stamped dev-time value, and
   the atlas refused to load as STALE.

**The lesson is not either bug.** It is that adding a sixth gate in the same frame would have found
neither. A suite that shares one environment verifies that environment, never deployment — the same
shape as `critical_lessons § 9` (a check consuming the generator's own enumeration verifies
fidelity, never coverage) one level up. → `critical_lessons.md § 10`.

**Fixes, at the root rather than patched:**

- `mode()` keys on `_baked_faces_available()` — are the atlas-backed families loadable as files.
- `code_fingerprint()` derives its file set from the tree (root `*.py` + `displays/**`, `_`-excluded)
  instead of naming files, and is **compared only where the sources exist** (`code_sources_present`).
  The check is only ever reached when mode is ATLAS, which in dev never happens — so its real
  audience is the verification arm, and in the shipped frame its inputs are absent by design.
  Freshness there is guaranteed differently: `/build` re-bakes from the same tree in the same run.
  The DATA fingerprint still runs in the shipped build, because `data/` and `audio/` do ship.
- `--verify-shipped` exists so this class cannot return. Mutation-tested: restoring the folder test
  makes it print `mode() -> live` and fail.

Two smaller things fixed alongside, same family — a hand-maintained list standing in for what
production reads: `data_fingerprint` and `walk_shipped_json` each re-spelled the shipped-JSON glob
with a comment asserting they agreed (now one `_shipped_json_files`), and `code_fingerprint` omitted
`route_loader.py`, which *transforms* drawn text (`_fill_dest_closure` decides each stop's rendered
destination).

## Rejected

- **Substitute open fonts in the public build.** No open ShinGo analogue; Noto Sans JP and Source
  Han Sans do not read as ShinGo, and station names are the most prominent element on the upper LCD.
  Fails goal 1 outright. (BIZ UDGothic was compared side by side and parked by the author on feel;
  weight-matching first — Regular reads too thin against ShinGo Medium.)
- **Ship the fonts and rely on the repo being small.** Rejected, but the reason first given —
  *"the release zip is the larger exposure"* — is wrong and worth correcting, because it
  under-states what goal 3 needs. **`fonts/` is tracked**: `git ls-files fonts` lists 13 files, 7 of
  them the proprietary faces, on a public repo. That is at least as exposed as a zip and arguably
  more — clonable, indexable, and permanent in history by the no-rewrite decision (2026-07-27).
  So goal 3 takes three things, not one: the atlas (ShinGo done), `'fonts'` added to `/build`'s
  `$shipExclude`, and `git rm --cached` on master. History keeps them by choice. **ShinGo has all
  three bar the `$shipExclude` line, which waits on #116** — the staged `fonts/` still carries
  Helvetica and Frutiger, so the folder cannot go wholesale and `/build` deletes the ShinGo files
  from staging instead.
- **Tell users to obtain the fonts themselves.** Not a path a hobbyist can walk, and every load site
  is unguarded — absence is a crash, not degradation.
- **A glyph atlas — per-character bitmaps recomposed at runtime.** Recomposing from individual glyph
  renders at `metrics()` advances is 26–100% pixel-exact depending on size, collapsing at small
  sizes because adjacent antialiased ink overlaps. Storing output sidesteps the whole question.
- **Character-level storage with runtime layout.** Workable and proven on one element, but it leaves
  `size()` lookups, the compression `smoothscale` and the spacing arithmetic running at blit time —
  three things that have to be argued correct separately. Storing the laid-out parts leaves nothing
  to argue. The author's framing: pre-rendered means no blit-time layout at all.
- **Compression / sheet-packing optimisation.** Not a goal; see § Goals.

---

## State — pick up here

**The ShinGo half is done and shipped-verified.** `6e5a04a` (2026-07-30) put every LCD draw on the
seam with coverage from `draws=` declarations; `a108e76`-era work on 2026-08-01 added the two bake
gates, fixed the deployment-frame bugs below, and a real `/build` at `0.6.3` produced an exe with no
ShinGo `.otf` staged that the author smoke-tested.

`font_atlas/` is a **gitignored build artifact** — `/build` re-bakes it every run, so it can never be
stale. Consequence: a build requires the licensed fonts present on the machine. **Since 2026-08-08
ShinGo is untracked**, so that is now real rather than prospective — a fresh clone has neither the
faces nor an atlas and cannot render LCD text until one or the other is supplied by hand. Helvetica
and Frutiger are still tracked, so only the ShinGo half of the constraint bites today.

**Commands, and where they stood on 2026-08-01** (both models, 14 routes, 21,978 states):

```
uv run python -u _dev_scripts/bake_font_atlas.py                  # cook   -> 26 combos, 4.7 MB
uv run python -u _dev_scripts/bake_font_atlas.py --verify         # cover  -> 0 raised
uv run python -u _dev_scripts/bake_font_atlas.py --pixel-verify   # ident  -> 0 frames differ
uv run python -u _dev_scripts/bake_font_atlas.py --verify-shipped # frame  -> resolves ATLAS, renders
```

Both sweeps need `python -u` to see progress, and output goes through
`PYTHONIOENCODING=utf-8` (Japanese in the report crashes a cp1252 pipe). `libpng warning: iCCP` lines
are the transfer icons and are pre-existing noise — filter them, don't chase them.

**The migration's finish line is printed by the bake**, not tracked here: `N combo(s) cooked from a
`draws=` declaration, M from sweep provenance`, with the M listed by face and size. **Currently 11
declared / 10 provenance.** A provenance-cooked combo still owes its coverage to some state being
reachable, which is the dependency being removed; zero means the atlas no longer cares what the LCD
can be driven to. The 10 outstanding are the E235-1000 upper faces (Heavy@26bi train type,
Medium@35 dest, Medium@78 station), the 8-station label (Medium@30), and E235-0's set
(19/28/38/40/42/84).

**Gate 3 (against pre-atlas code) is not a committed script.** Reconstruct it with a detached
worktree at the last pre-atlas commit `385727f`, render matched states there and here under a frozen
clock, and diff. It found the one thing the other two cannot — a refactor that changed rendering and
then got faithfully stored (the 90-pixel flattening cost). `git worktree list` will show the
worktree if it still exists; `git worktree remove` when done.

**Code map:**

- `displays/utils.py::compose_text_parts` — the only layout implementation, with the `# CONTRACT:`
  block. `draw_text_given_width` blits the parts it returns.
- `font_atlas.py` — `lcd_font` (the seam, `draws=` declares text), `ATLAS_FACES` (the one place
  deciding which families are baked), `Source` / `at` / `lit` / `resolve` / `STATION_NAMES` (the
  declaration vocabulary), `check_declared` (validates every dev draw against its declaration),
  `walk_shipped_json` (total JSON traversal, naming no key), `data_fingerprint` +
  `code_fingerprint` (staleness on data AND on renderer source), `text_parts`, `LcdFont`,
  `AtlasFont`, `RecordingFont`, `force_mode`, `_suppress`.
- `_dev_scripts/bake_font_atlas.py` — `sweep` (routes × **models** × stops × modes × **slots** × PA
  × **frames**, every axis read from production: `TRAIN_MODELS`, `_SLOT_BEATS`, `_frame_count`,
  `DisplayMode`), `cook_from_data` (declaration-first, provenance fallback),
  `audit_source_literals` (fails the bake on a Japanese literal no state drew), `bake`, `verify`,
  `pixel_verify`, `freeze_clock`.
- Iteration loop while migrating declarations: a scratch `declcheck.py` drives ONE route in LIVE mode
  and reports every string outside its declaration — seconds, versus minutes for a bake. Scratchpad
  only, deliberately not graduated to `_dev_scripts/`.

**Loose end:** the Yamanote contact sheet took 駒込 for its transfer row — nearest-to-midpoint stop
with transfers, which on a loop is a thin one. Re-shoot at 池袋 or 新宿 if a richer panel is wanted.

---

## Decided — cook from the data, verify by the sweep

Author delegated the design 2026-07-30: *"whatever design you like … I only care the things i've
mentioned to you, as for how it's implemented i don't care. i just want the whole thing used as it
is, and i accept a bit more time in baking, but if that can be speed up i am more happy."* Their
framing, same day: *"this is not a shader, we are cooking, baking the texture"* and *"i think just a
mechanism that ensures nothing fails to ship."*

**The inversion: coverage comes from the DATA, not from the state sweep.**

### Why the sweep cannot be the coverage mechanism

It shipped a crash. `sobu/1217F` carries a `frames` array — frame 0 is 久里浜→千葉, frame 1 is
千葉→成田空港 — and the atlas has **no lower-LCD raster at any size for 7 of the route's 37 station
names** (東千葉, 都賀, 四街道, 物井, 佐倉, 酒々井, 空港第2ビル). That set is exactly frame 1's
interior; the three frame-1 names that survive leak in from elsewhere (千葉 is the shared junction,
成田空港 is the destination at size 35). Mechanism: the sweep pins the lower view by writing
`_current_slot`, which sets `scheduler.enabled = False`, so `lower.update()` never runs,
`_advance_frame` never fires, and `_active_frame_idx` never leaves 0. In a fontless build, driving
past 千葉 flips the frame and the route bar raises `KeyError` on 東千葉 at size 25.

**All three gates passed on it**, and that is the structural point rather than the bug: `--verify`
re-drives *the same sweep*, so it can only confirm the atlas covers what the sweep visited — a
tautology against its own coverage. `--pixel-verify` compares two renders of the same unvisited set.
Gate 3 sampled 36 states. A mechanism that ensures nothing fails to ship therefore cannot be another
sweep.

### The cook

**Total traversal, never a named key.** Walk every string value in every shipped JSON
(`data/*.json` + `audio/**/route.json`, skipping `_`-prefixed). Measured: 19 files → 1789 distinct
strings, 754 containing CJK, **821 distinct CJK characters**. This is the repair of attempt 3, which
read `stops` and missed `pre_stops` — naming keys was the failure, so the walk names none and found
both arrays without knowing either existed.

**Provenance binds text to combos.** The walk gives totality but not which sizes a string needs. For
each text the sweep observed at a combo, reverse-map it to the JSON paths that contain it; the union
of those paths is that combo's domain; bake every value at those paths. Derived, not declared —
`remarks` never reaches size 78 because no observed 78-text maps to a `remarks` path. A blind full
cross-product would instead bake 20-character remark strings at 78px, which is the indiscriminate
dump § Goals bars.

**Cost.** Layout path measured at 561 cross-product vs 398 stored (**1.4×**) because width and
colour are 1 and 1–6 per combo. Character path at size 25 goes 223 → up to 821 (**3.7×**). Content-
hash dedup of identical part surfaces is what keeps this cheap: parts are stored per character, so
the same glyph currently repeats once per string it appears in.

**This makes the author's contract structurally true rather than guarded.** *"If i add new
informations in transfer or audio data that covers outside your atlas, it must fail loud or
automatically refresh"* — under a data-driven cook there is no outside, because new data IS the
cook's input. The fingerprint stays as a cheap second net, no longer the primary guard.

### What the sweep becomes

**Parameter discovery, not coverage.** It remains the only honest source for the role→size mapping
and for width / colour / collapse / script, and each combination needs observing exactly **once** —
so discovery can be a small sample instead of 10,476 states. The frame hole is not fixed; it stops
mattering, because frame 1 uses frame 0's sizes and 四街道 is baked from `route.json` whether or not
any state reaches it. Unreachable state goes from *shipped crash* to *nothing at all*.

Residual, stated rather than assumed: a data *location* never observed feeding a combo is outside the
domain, because the location→combo binding is still learned by watching the sweep draw. Adding a
station to an existing location is covered; a wholly new drawn field is not. **This residual is what
§ Side 2 removes.**

### Side 2 — the code declares its needs

Author's call, 2026-07-30: *"the architecture should not fail on like slot change, these kind of LCD
things, it should be LCD invariant, unaware to LCD. maybe better i think is the LCD declares what
kind of font it needs"*, and earlier — *"at the end it's a collaboration of both sides."*

The evidence for it is the day's own history: three axes were patched in sequence — through-service
frames, train models, lower-LCD slots — and each was a hole that had shipped or would have. An axis
list is never provably complete, so any design where coverage depends on **traversing LCD state** is
one new view away from a fontless-build crash. The `駅` finding is the same thing in miniature:
`e235_0/lower_lcd.py:1932` draws `station_name + "駅"`, a composed string in no JSON file, covered
only because the sweep reached every station that can be a current stop.

**Each renderer declares, at the point it loads the font, what it draws:** face, size, and the
*source* of the text — a data location (`audio/*/route.json:stops[].name`), a literal set, or a
derivation of one (`stops[].name + "駅"`). A source, never a state. The cook joins the declarations
against the § The cook walk; nothing about LCD state is in the correctness path.

**What stops this being the declared table that failed three times.** That is the real objection —
`_dev_scripts` tables are exactly what produced the missed transfer sizes and the missed `pre_stops`.
The difference is *where it lives* and *when it is checked*: the declaration sits at the call site,
and is **validated at use**. In dev, `lcd_font` / `text_parts` check that the face, size and text
being drawn fall inside the declaring renderer's declaration, and drawing something undeclared raises
on the first frame that does it. A declaration cannot drift from the code it sits in when using
something undeclared is an error at the moment of use rather than a gap found at ship time. Same
shape as a pipeline validating a shader's declared resource bindings.

**The sweep then keeps only goal 1** — zero pixel difference LIVE vs ATLAS — and stops being
load-bearing for coverage. A new slot, view, frame, mode or model can no longer break coverage; it
can only go un-pixel-verified, which is a weaker and honest failure. That is what "LCD invariant,
unaware to LCD" buys: a display author writes a renderer, declares its text sources, and never thinks
about the atlas. The three axis patches stay in the pixel gate, where breadth is still worth having,
and stop being mistaken for coverage.

**The vocabulary** (`font_atlas.at` / `lit`). `at()` takes fnmatch patterns over the walk's own
location keys, so `data/lines.json:*.name_ja` covers every line id without naming one. Options exist
only for text a renderer DERIVES, which is text present in no JSON and therefore covered by
reachability alone if undeclared. Applied in order — `replace=(a, b)`, `wrap="sep"`,
`split=True | "sep"`, `prefix=/suffix=` — because a renderer that substitutes and then splits is
splitting on the substituted character. Recurring declarations are named once (`STATION_NAMES`,
`STATION_NAMES_EKI` reusing its locations) so two models cannot hold diverging copies of a location
list.

Every option exists because a real renderer forced it, and each was found by the validator rather
than by reading:

| option | the derivation it covers |
|---|---|
| `replace=` | transfer panel swaps the JSON's `・` for a narrower `·` before drawing |
| `split="·"` | then splits on it, rendering each part **and** the `·` alone |
| `split=True` | a space inside a station name is the data format's line-break marker — and the two LCDs disagree, the lower route bar honouring it (`さいたま` over `新都心`) while the upper station name strips it (`さいたま新都心`). Both are declared by one source. |
| `wrap="･"` | shinkansen names wrap to ≤2 lines at a width-dependent boundary, keeping the separator on the leading line, so every boundary is a possible cut |
| `suffix="駅"` | E235-0's transfer header composes `{name}駅` at draw time |

**The cook reads declarations; shape is still observed.** A declared combo's domain comes from
`resolve()`, never from what the sweep drew. *How* it is drawn — laid-out parts, per character, whole
string — is read off the observed texts that declaration covers, so ShinGo Medium @25 renders
route-bar names per character and PA prefixes whole rather than applying both shapes to the union of
the two roles it serves. A declaration covering nothing yet drawn (the transfer panel's `name_en` CJK
fallback) bakes as a whole string, so its first real fire is not its first miss. The bake prints how
many combos are still cooked from provenance; **zero is the finish line**, and until then those
combos still owe their coverage to reachability.

**What it caught in its first hour**, each a text in no JSON that was previously covered only because
some state happened to reach it:

- `さいたま` / `新都心` — a space inside a station name is the data format's own two-line break marker
  (author, 2026-07-30). Was undocumented; now in `DATA_FORMAT.md`, and `STATION_NAMES` carries
  `split=True`.
- `·` and the `·`-split parts of a line name — `compact_dots` swaps the JSON's `・` for a narrower
  U+00B7 and `render_with_dot_pad` then renders each part *and* the dot alone. Neither the substituted
  whole nor the parts are values anywhere.
- `station_name + "駅"` — the E235-0 transfer-panel header, composed at draw time.

Mutation-tested rather than assumed: narrowing `STATION_NAMES` to drop `pre_stops` took a route from
1026 clean states to 912 and named 久里浜; dropping the dot substitution took 810 to 783 and named
日暮里.

### Atlas every face, swap nothing

*"The whole thing used as it is"* — so all three families go through the seam and none is
substituted. That keeps goal 1 (zero pixel difference) for Helvetica and Frutiger too, and removes
every appearance decision from the author's plate. It also retires the open-face swap track: no
Nimbus Sans, no BIZ UDGothic.

The continuous-value objection dissolves for the current app: the clock and countdown are Helvetica
digits, and digits are 10 characters. Enumerable trivially. **The constraint on future LCDs is
therefore narrow — atlas-backed text must be traceable to a shipped file or to a closed character
set; genuinely open runtime text needs a shippable face.**

### Gates

Keep both sweeps, exhaustive, and keep `force_mode(LIVE)` as a verification arm rather than the dev
default (third-man, 2026-07-30: collapsing to one path does not make agreement true by construction,
it makes disagreement *unobservable*, and goal 1 is a binary bar only a second arm can falsify).
Their job changes from *providing* coverage to *verifying* it. Gate 3 expires structurally once a
model is authored after the atlas — no pre-atlas commit exists to diff against — so commit it as a
script, spend it on the E235-0 conversion, then retire it.

Two gates were added that fail in the opposite direction from the sweeps, so they can over-report but
not miss:

- **`--verify` runs with the baked faces unreadable.** Coverage alone was not the whole risk: the
  shipped build has no ShinGo *files*, so a path that constructs one is a `FileNotFoundError` there
  even though the atlas could have served it. The pass patches `pygame.font.Font` to raise on a face
  in `ATLAS_FACES`, which makes that unmissable — the dev tree has every face, so it is otherwise
  invisible (`critical_lessons.md §4`).
- **The source-literal audit** (`audit_source_literals`) fails the bake on a Japanese literal in
  display code that no swept state drew. It found two real cases on its first runs: `・`, which
  `compact_dots` substitutes away before rendering (a predicate — marked `# not-drawn`), and `駅`,
  composed into `{name}駅`.

A third, still unbuilt: assert every text in the cooked domain has a raster at every size its
declaration binds it to.

### Speed

Bake gets *faster*, not slower: discovery drops from 10,476 states to a small sample, and cooking
821 characters plus the bound strings is seconds. The exhaustive dual-arm pixel gate keeps the
10,476-state cost, and it parallelises per route across cores — 14 routes, embarrassingly parallel.

## Superseded — the write-through memo cache

Considered and dropped 2026-07-30. Kept because the reasoning error is instructive.

**Design.** The atlas becomes a write-through memo cache of `compose_text_parts`, and the read path
is the only path. Always read from the atlas. On a miss: dev composes, stores, and serves from
storage; ship treats a miss as a hard error. One rendering path in both; the only difference is
absence handling, not how pixels are produced.

This retires two gates — `--pixel-verify` and the pre-atlas diff both go vacuous, with no second
path left to disagree. What remains is the build-time exhaustive bake plus miss-is-fatal.

**Incremental, not compile-on-launch.** A full sweep is minutes, so it cannot gate every
`uv run preview_display.py` without breaking goal 2. A miss costs exactly one `compose_text_parts`
call — what live rendering costs today — so the dev loop and the calibration editor stay as fast as
they are, paying one compose per nudge.

**The hazard the single path introduces, and its guard.** The key covers face, size, style, text,
colour, width, collapse and script, so editing a size or a position misses and self-heals. Editing
the *arithmetic inside* `compose_text_parts` (`exp = 7` → `8`) changes no key, so dev would serve
stale pixels and look correct. Fingerprint the layout source into the manifest alongside the data
fingerprint; touching the function invalidates everything. Without this the single-path design has a
silent-staleness hole the dual-path one does not.

## Open — to discuss before the single-path rewrite lands

Author, 2026-07-30: the design choices and the state sweep need discussing explicitly, *"because it
deeply changes how our later LCD designs direction as well."* Correct — under a stored-output atlas
the sweep is the coverage mechanism, so it quietly constrains what a future LCD may render. Not
decided; this is the agenda.

**1. ~~The sweep's axis list is hand-declared~~ — RESOLVED 2026-07-30.** Every axis now reads from
production (`TRAIN_MODELS`, `_SLOT_BEATS`, `_frame_count`, `DisplayMode`), and more importantly the
sweep stopped being the coverage mechanism at all, so an axis it misses can no longer cost coverage —
only pixel-verification breadth. Codified as `critical_lessons.md § 9`.

**2. What an enumerable state space costs the LCD design.** A stored-output atlas needs the set of
`(text, colour, width, collapse, script)` tuples to be finite and reachable. Two future designs
would break that rather than merely enlarge it: text derived from a *continuous* value rendered in a
proprietary face (a live speed or clock readout in ShinGo — today the clock and countdown are
Helvetica, so this is not yet a problem), and a width derived from something outside the state tuple.
Worth deciding whether that is an accepted constraint on future LCDs or whether the atlas must
eventually handle open text.

**3. Exhaustive enumeration vs. recording a soak run.** Enumeration is provable and is why coverage
is currently 0 misses; a long fuzz/soak recording is easier to grow but proves nothing. Related:
whether the sweep stays a build-time cost that scales with models × routes × stops (today 10,476
states for one model) or gets partitioned.

**4. Miss behaviour in a shipped build.** Still fatal, and now a more defensible default than it was:
coverage no longer depends on any state being reachable, and `--verify-shipped` renders the staged
frame before it can reach a user, so a miss means the declarations are wrong rather than that some
state went unvisited. The alternative — degrading to Noto (already shipped, OFL) with a loud log — is
graceful but silently the wrong face on the most prominent element of the upper LCD. Left fatal
deliberately; revisit only if a real miss ever escapes the gates.

**5. Animation and the clock stay live** — they are the one part of the LCD that is not a pure
function of persistent state, and they are also why any frame-comparison harness has to pin both
Python's clock and SDL's. Worth stating as a boundary the atlas never crosses.

## Also remaining

**ShinGo leaves the shipped build (2026-07-30, verified 2026-08-01).** `/build` stages `fonts/` then
deletes `ShinGoPr6N-*.otf` from it and throws if any survive. Everything that drew ShinGo now
resolves from the atlas, and `i18n._LANG_CHROME_FONT["zh_HK"]` — the last reference outside the LCD,
reachable only via `--classic` — moved to `NotoSansTC`, which also stops classic and TIMS disagreeing
about zh_HK chrome (TIMS already used a Noto TC face there). `font_for_lang` synthesizes bold for a
locale whose face ships in one weight, so bold labels do not silently become regular.

The staged folder resolves **ATLAS**, because `mode()` asks whether the *baked families* are loadable
(`_baked_faces_available`), not whether `fonts/` exists. An earlier version tested the folder — see
§ The frame nothing tested for why that was wrong and what it cost.

Remaining, deliberately:

- **`HelveticaNeue` and `NeueFrutigerWorld-Bold` stay in `fonts/` and stay shipped** — author's call,
  2026-07-30 (*"leave helvetica and frtiger still"*). Baking them is mechanically identical (add the
  family to `font_atlas.ATLAS_FACES`, extend the `lint_primitives` alternation, declare the sites);
  no swap to an open face is needed or wanted, so the earlier Nimbus Sans / BIZ UDGothic track is
  retired. Until then `fonts/` ships and the folder cannot be dropped wholesale.
- **ShinGo is out of the tracked tree (2026-08-08).** `git rm --cached fonts/ShinGoPr6N-*.otf` on
  the author's instruction, with `/fonts/ShinGoPr6N-*.otf` added to `.gitignore` so it cannot return
  by accident. The files stay on the author's machines; only tracking changed. History keeps the
  blobs by the no-rewrite decision (2026-07-27), so this closes the *forward* exposure — a clone of
  HEAD no longer carries Morisawa font software — not the historical one.
  **Consequence, stated because nothing enforces it:** `font_atlas/` is a gitignored build artifact,
  so a machine with neither the ShinGo files nor a baked atlas cannot render LCD text or run the
  bake. Every machine that builds must hold a licensed copy locally. `THIRD-PARTY.md § Fonts` says
  so for anyone forking.
- **`HelveticaNeue` / `NeueFrutigerWorld-Bold` stay tracked** until #116 bakes them — untracking a
  face the atlas cannot serve would leave no source for it at all. That is what keeps this doc alive:
  the graduation trigger reads *the proprietary faces* (plural), and two of three remain.
- **Recap + commit.** Nothing from 2026-07-30 is committed or recapped.

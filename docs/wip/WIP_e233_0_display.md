# WIP — E233-0 display (中央線快速)

Spec-first build of the E233-0 LCD. This doc is the **spec**; code follows it, not the
other way round. Nothing is implemented yet.

**EDIT-CONTRACT.** A value that came from a script says `[measured]`; a value read off a
reference by eye says `[observed]` and is not to be trusted until a script measures it. An
unresolved decision is an `OPEN` bullet and stays one until the author settles it — do not
fill gaps autonomously (`principles.md` § Implementation-completion-as-spec).

**Status (2026-08-23).** The model is registered and previewable
(`--model e233_0`), drawing its chrome and the one upper element whose drill-down has
happened. The working loop is the author's: **confirm spec → implement → refine until
mostly happy → next element.**

Whole-display basics **settled and drawn** — aspect, upper/lower
divide, backgrounds, divide rule, screen border, canvas (§ 2). `displays/train_models/e233_0/__init__.py`
holds them.
Per-view specs are deliberately NOT written — each view gets its own drill-down session with
the author (§ 6). The view inventory is still growing.

**Graduation trigger.** Dissolves into `docs/DISPLAY_E233.md` when the Japanese-mode views
ship and Chūō's two diagrams declare `"model": "e233_0"`.

---

## 1. What this model is

E233-0 runs the **中央線快速**. Its LCD is a generation older than the E235's — flatter,
squarer, more diagrammatic — but the **feature set is largely the same as E235-1000**: a
next-stop plate up top, a route bar below, view alternation, per-stop countdown minutes.

Three properties shape everything downstream:

- **Same upper/lower structure as E235.** One upper band, one lower area, the upper drawn
  identically whatever the lower is showing. The architecture carries over; the proportions
  and the drawing do not.
- **The line is linear.** No loop, no horseshoe. This is the project's first native linear
  model, so it is also the natural host for out-of-spec routes — a linear model on a linear
  line needs no adaptation (`CLAUDE.md` § Per-model IRL line scope).
- **E233-1000 is next and looks very similar.** Anything decided here that is not
  Chūō-specific should be decided as *family* behaviour, because -1000 (and later -5000 /
  -7000 / -8000) inherit it as a re-skin.

**Font is ShinGo throughout** (author-stated). Weights are per-element, decided per view.

---

## 2. Ratios — the whole display

Measured from three references at two different pixel sizes, by colour-run detection.
Ratios are the deliverable here: they survive a canvas change, pixels do not.

### 2.1 Whole-display aspect

| Reference | Pixels | Aspect |
|---|---|---|
| Full route | 1502 × 1124 | 1.3363 |
| 6-station | 1084 × 812 | 1.3350 |
| Patterns overview | 1502 × 1124 | 1.3363 |

**E233-0 is a 4:3 panel** (1.3333). The residual above it is capture crop, consistent in
sign and size across all three. For contrast, E235-1000 and E235-0 are both 730 × 420 =
**1.738 (≈16:9)**, so the canvas does not carry over from the fork source at all — this is
the first thing the fork cannot inherit.

### 2.2 Upper / lower divide

| Reference | Split `y/H` |
|---|---|
| Full route | 0.3105 |
| 6-station | 0.3103 |
| Patterns overview | 0.3105 |

**`UPPER_HEIGHT / S_HEIGHT` = 0.3105 `[measured]`** — agreement to within a pixel across
three independent captures, tighter than any other figure here. (E235-1000 is 0.279;
e235_0's hand-calibrated 0.3095 is close, which is coincidence, not inheritance.)

### 2.3 Background colours `[measured]`

| Role | RGB |
|---|---|
| Upper background | `(168, 177, 202)` — blue-grey |
| Lower background | `(213, 223, 239)` — paler blue |
| `RULE_GREY` — divide, border, beyond-service bar | `(135, 145, 165)` |
| Route bar, served | `(225, 92, 18)` — JC orange |
| Plate fill | `(254, 254, 254)` |

Both backgrounds are flat fills, no gradient `[observed]`. Every other colour (name black
vs grey, marker green, badge orange, train-type red, transfer-name blue) is element-level
and gets measured in its view's drill-down.

**Chrome is state-invariant** (author, 2026-08-22): backgrounds, divide and border never
change — not per train type, not per approach/stop state, not per view. Written as a
`# CONTRACT:` block in the model's `__init__.py` so no view starts tinting its own
background. If a future reference contradicts it, it changes in that one place.

### 2.3.1 The divide is a drawn rule, and so is the screen border

Neither is a bare colour change, and both are the same grey:

- **Divide.** Upper background ends at `y/H` 0.3052; ~2px of `RULE_GREY` follows; lower
  background begins at 0.3105. So `UPPER_HEIGHT` is *where the lower area begins*, and the
  rule occupies the last 2px above it.
- **Border.** A dark rim runs around all four edges of every reference —
  author-confirmed as **real, a border on the screen**, not a capture artifact. Measured one
  pixel in from each edge, every edge of both references lands on the same grey:
  `(136,145,165)` / `(144,151,168)` / `(147,152,165)`. The *outermost* pixel reads darker and
  disagrees per edge (105–145), which is what a crop clipping through the border into a dark
  surround looks like — so that is treated as contamination, not as the colour.

One `RULE_GREY` constant serves the divide, the border and the beyond-service route bar
rather than three values that drift apart. Widths stay separate because they genuinely
differ: divide 2px, border 1px.

- OPEN — border width is 1px by inference (~0.26% of the dimension in the refs, which are
  upscales). A reference at native resolution would settle it. Cheap to change; it is a
  single rect outline.

### 2.4 Canvas — DECIDED

**`S_WIDTH = 640`, `S_HEIGHT = 480`, `UPPER_HEIGHT = 149`** (author, 2026-08-22).

Exactly 4:3; the measured 1.336 is capture crop and is not carried into the canvas.
`UPPER_HEIGHT` = round(0.3105 × 480) = 149, leaving a 331px lower area.

The canvas is 60px taller than E235's 730 × 420 and 90px narrower, so the app window
changes size when the model changes — already supported, since `TRAIN_MODELS` carries
`S_WIDTH` / `S_HEIGHT` per model.

This had to be settled before any drawing, because **font size is part of the atlas key** —
picking it late means re-baking and re-tuning every element.

```
640 × 480, aspect 1.3333
+----------------------------------+  <- 0
|          UPPER  149px            |
+----------------------------------+  <- 149
|                                  |
|          LOWER  331px            |
|                                  |
+----------------------------------+  <- 480
```

---

## 3. View inventory

**The inventory is incomplete.** Three views have references; the author is collecting more,
so this table grows before building starts.

| # | View | What it is | Status |
|---|---|---|---|
| 1 | **Full route** | The whole line on two rows, right-to-left, with the section beyond this train's service in grey | v1 — **first** |
| 2 | **6-station** | Six stations, one thick bar, current stop at the right | v1 — second |
| 3 | **Transfer info** | Connecting lines per station | v1 — third · structure deferred, see below |
| 4 | **Patterns overview** | All six Chūō service patterns as parallel coloured lines with per-station stop markers | noted, **not scoped** |
| … | *further views* | author collecting references | pending |

**Transfer info — deferred to its own session, and not an E233-0 distinctive.** In the
6-station reference the transfer entries are drawn as an **inline band beneath the bar**,
aligned to each station's column. That is *not* a difference from E235: **E235 has the same
inline band, we simply have not implemented it** (author, 2026-08-22). So the question of
inline-vs-standalone is a shared-architecture question, not something E233-0 settles on its
own, and it waits for its own discussion.

- OPEN — inline band, standalone view, or both — and the same answer for E235.
- OPEN — the lower-LCD slot count follows from that, which is the `ChangeScheduler` beat
  schedule rather than a detail.

---

## 4. Scope

**In, v1:** full route → 6-station → transfer info, **Japanese only**, on Chūō
(`chuo/1654T`, `chuo/916H`).

**Deferred, not abandoned:**

- Furigana and English modes. **Until they exist, all three modes render the kanji
  renderer** (author, 2026-08-22) — the model ships usable from the first view, the cycler
  keeps ticking, and the later renderers drop in with no structural change.
- The patterns-overview view (§ 3 row 4). It is the only view needing data about services
  *other than the one being driven*, which nothing in the app models today — that, not the
  drawing, is what makes it expensive.
- Ōme, and the -1000 / -5000 / -7000 / -8000 re-skins that inherit this work.

**Out of scope:**

- The in-car advertising / news screen (already in `TODO.md`'s closed-off ledger — IRL the
  second screen above a door runs ads; only the service screen is modelled).
- **Full-screen and non-view states.** E233-0 has none that matter (author, 2026-08-22) —
  no startup animation, no logo, no out-of-service screen. The model is always upper +
  lower with a view showing, so E235's restart transition is not forked.

**View cycling: mirror E235's cadence for now** (author, 2026-08-22). Reuse
`ChangeScheduler` with the existing beat schedule and slot cycle. Order and dwell times are
only observable from motion and all three references are the same instant, so the real
cadence is a tuneable to correct once a moving reference exists — not a guess to defend.

**Out-of-spec routes.** E233-0 becomes the natural host for arbitrary linear routes, and
that path gets specced deliberately rather than falling out of the Chūō work. The decisions
it needs are per-view, so they belong to the drill-downs; the whole-display commitment is
that best-effort means *this model's own native norm applied to any route*, never a
borrowed E235 behaviour.

---

## 5. References

| View | File | Captured state |
|---|---|---|
| Full route | `full-takao-stopping-ja.png` | 通勤特快 東京行, at 高尾, ただいま, 8:36, car 10 |
| 6-station | `6stations-takao-stopping-ja.png` | same train, same moment |
| Patterns overview | `overview-tokao-different-patterns-stopping-ja.png` | same train, same moment |
| 6-station, 4-char name | `6stations-ochanomizu-ja.png` | 御茶ノ水 — added 2026-08-25 for the station-name span; a 4-character name, which the takao set cannot show |

The first three are the same train at the same instant, which is what made the upper-LCD
ratios cross-checkable between them — and which is also their limit: one station name, one
train type, one state. The ochanomizu capture was added to break the first of those.

**Home: `_references/lcd/e233_0/`** — moved there 2026-08-26, from the `e233_0/` drop folder at
the repo root they were collected in. Not taste: `_references/lcd/` is the path already
inventoried in `THIRD-PARTY.md` § "Reference material", so a file placed there is covered by an
existing carve-out, whereas a root folder is an uninventoried asset class (`conventions.md`
§ Tooling, "A new asset class must update THIRD-PARTY.md"). They moved at the point they were
first committed, which is the point the classification starts mattering.

---

## 6. Working method

**Canonical home: [`docs/DISPLAY.md` § "Specifying a new display"](../DISPLAY.md).** The
workflow was established on this model and generalised out of it in the same session, so it
is written once, there, and not restated here — it is cross-model process, and it must
outlive this doc's dissolution. `conventions.md` § "Display module structure" carries the
pointer that makes it fire before any renderer file exists.

This model's progress against it:

| Step | State |
|---|---|
| 1. Reference per view | partial — 3 collected, author still gathering |
| 2. Whole-display basics | **done** (§ 2) |
| 3. Ratios by script | **done** for whole-display; per-view pending |
| 4. Base canvas drawn | **done** — `e233_0/__init__.py`, plate deliberately excluded (§ 2.4) |
| 5. Per-view drill-downs | **upper LCD in progress** — train type settled + built; prefix / destination measured, not settled |
| 6. Build + tune | **in progress, element by element** — see § 8.6 |
| 7. Graduate | trigger at the top of this doc |

---

## 7. Parked — first-pass observations

Raw notes taken while measuring, held here so the drill-downs start from something.
**None of this is decided, and none of it is a spec.** Every line is `[observed]`.

- **Upper LCD, nine elements:** train-type label (red, 2×2 characters, top-left) · prefix
  `ただいま` · destination `東京 行` above the plate, with a space before `行` · the white
  next-stop plate (`x/W` 0.190→0.806, `y/H` 0.0765, height 0.674 × upper) · station-code
  badge `JC`/`24` stacked, orange rounded-square outline · station name in **green** ·
  car number `10` · `号車` · clock. Three have no E235 counterpart: the coloured train-type
  element, the car number, and `号車` — and the car number has no source in `route.json`.
- **Full route:** two orange bars, `h/H` ≈ 0.045, centrelines at `y/H` 0.578 and 0.877 ·
  reads right-to-left on both rows, wrapping top-left → bottom-right · orange stops at the
  current stop and **grey continues to the right edge** carrying eight further station
  names, i.e. the diagram draws *the line*, not *the run* · vertical station names,
  bottom-aligned, black when the train stops and grey when it passes · white minute boxes
  on the bar at stopping stations, chevrons elsewhere · green pentagon at the current stop,
  sitting exactly on the orange/grey boundary.
- **6-station:** one bar, `h/H` 0.0714 — **60% thicker relative to the screen** than the
  full-route bar, and the current-stop marker is 2.6× wider. The two views are separately
  proportioned, not one renderer at two scales · station codes render `JC-19`, hyphenated
  and horizontal, where the upper badge stacks them without a hyphen · transfer entries
  below the bar, line names in blue, non-JR operators taking a plain badge.
- **Patterns overview:** six coloured service lines on the same two-row right-to-left wrap ·
  square stop markers per line per station · legend bottom-left where the **active** service
  is highlighted with a filled box and reversed text · a grey rounded pill behind `立川`
  marking the branch node · spurs to `青梅・武蔵五日市・高麗川 方面` and `千葉方面` · each
  service's line terminating where that service terminates.

---

## 8. Upper LCD — DRAFT, under discussion

**Nothing in this section is settled.** It is the starting draft for the per-element
drill-downs (`docs/DISPLAY.md` § "Specifying a new display", step 5). Geometry is
`[measured]` off `full-takao-stopping-ja.png` by ink threshold; *behaviour* is
`[observed]` from a single frozen frame and is exactly what the drill-downs exist to
settle.

The upper band is drawn identically under every lower view (author-stated). Diffing the
two references' upper bands, normalised to a common width, gives a mean channel delta of
6.7 with 2.8% of pixels over threshold — resampling noise between two different upscales,
no element-shaped difference. Consistent with view-invariance, and not proof of it: both
captures are the same instant.

### 8.1 Element inventory `[measured]`

Ratios are against screen width `W` and upper-band height `UH`. The px column is those
ratios on the decided 640 × 149 canvas, rounded — a starting point for tuning, not a spec.

| # | Element | x/W | y/UH | @640×149 |
|---|---|---|---|---|
| 1 | Train type — red, 2 × 2 characters | 0.0186–0.1338 | 0.0344–0.5444 | x 12–86, y 5–81 |
| 2 | Prefix `ただいま` | 0.0120–0.1758 | 0.7593–0.9427 | x 8–112, y 113–140 |
| 3 | Destination `東京 行` | 0.2111–0.3502 | 0.0315–0.2063 | x 135–224, y 5–31 |
| 4 | Next-stop plate (white, dark rule) | 0.1877–0.8089 | 0.2321–0.9341 | x 120–518, y 35–139 |
| 5 | Station-code badge `JC` / `24` | 0.2104–0.2989 | 0.4327–0.8138 | 57 × 57 square |
| 6 | Station name (green) | 0.4068–0.6704 | 0.3467–0.8367 | x 260–429, y 52–125 |
| 7 | Car number `10` (white box) | 0.9141–0.9834 | 0.0573–0.3524 | 44 × 44 square |
| 8 | `号車` label | 0.9261–0.9814 | 0.4069–0.5244 | x 593–628, y 61–78 |
| 9 | Clock `8:36` (white box) | 0.8675–0.9880 | 0.7163–0.9226 | 77 × 31 |

Ink colours `[measured]`: train type `(212, 3, 5)` · destination / prefix `(9, 13, 20)` ·
station name `(3, 120, 2)` · badge outline `(224, 93, 27)`.

Two of those are already data-driven and want no new source: the badge outline sits within
rounding of `route.json`'s `color` `(233, 91, 31)`, and the red type ink is that diagram's
`type_color` — `chuo/916H` carries `(45, 0, 255)` for 中央特快, so per-type colour is
authored data, not a table this model owns.

- OPEN — station name `(3, 120, 2)` against `chuo/*/route.json`'s `contrast_color`
  `(0, 92, 0)`. The reference is an upscale, so the brightening may be capture. Settle in
  the station-name drill-down; do not introduce a second green.

### 8.2 Three elements move; six do not `[observed]`

Against the app's state machine (`docs/DISPLAY.md` § Unified State Machine):

| Element | APPROACHING_EARLY | APPROACHING_FINAL | STOPPING | Driven by |
|---|---|---|---|---|
| Prefix | `次は` | `まもなく` | `ただいま` | `set_state`, unchanged from E235 |
| Badge | \|←—— `stops[curr_stop].sta_code` ——→\| | | | stop index |
| Station name | \|←—— `stops[curr_stop].name` ——→\| | | | stop index |
| Train type | \|←——————— constant ———————→\| | | | `route.type` + `type_color` |
| Destination | \|←——————— constant ———————→\| | | | `route.dest`, stop-level override |
| Plate · car no. · `号車` | \|←——————— constant ———————→\| | | | — |
| Clock | ticks | ticks | ticks | `TIME_SCALE = 60` |

So the upper band has **three moving parts**. Everything else is either chrome or set once
per run. That is the same shape as E235's upper, which is why the architecture carries over
even though not one coordinate does.

### 8.3 Open questions spanning the whole upper

- OPEN — **Car number has no data source.** `route.json` has no formation or car field, and
  the number is a property of *which car the passenger is standing in*, not of the run. It
  is a setup-time choice, a fixed literal, or the element is dropped. `号車` is only a label
  on it and shares its fate.
- OPEN — **PA hint.** E235 blinks a yellow square when a stop has multiple PA tracks
  (`CLAUDE.md` § Controls). It is our own affordance, not IRL, so it appears in no
  reference. Carry it into this model, or leave it out.
- OPEN — **Furigana / English.** v1 renders the kanji renderer in all three modes (§ 4). The
  destination stays kanji IRL even in furigana mode; what the *prefix* and *train type* do is
  a later question, not a v1 one.
- OPEN — **Out-of-spec routes.** Every element above has a Chūō-shaped input. A route with a
  null `sta_code`, a 7-character train type, or a long station name is the adaptive case, and
  it is settled per element rather than as one blanket rule.

### 8.4 Element 1 — train type

#### Settled

- **Position is fixed** (author, 2026-08-23). The block sits at one place on the screen
  whatever the type is; the prefix below it and the destination to its right are placed
  absolutely and never react to it.
- **Colour is `route.json`'s `type_color`, as authored** (author, 2026-08-23). The model
  reads it and owns no type→colour table, so an out-of-spec route brings its own colour and
  a wrong one is fixed in the data rather than in this model.
- **Four characters render as a 2 × 2 grid** `[measured]`, reading 通勤 / 特快 — top row
  first, left to right.

#### Geometry `[measured]`

From the 通勤特快 reference, ink bboxes at threshold. `@640` = the ratio on the decided
canvas, rounded.

| | ratio | @640×149 |
|---|---|---|
| Block ink bbox | x/W 0.0186–0.1338, y/UH 0.0344–0.5444 | x 12–86, y 5–81 (74 × 76) |
| Character cell | 0.0559 W × 0.2378 UH | ≈ 36 × 35 — **square** |
| Column gap | 0.0020 W (3 px of 1502) | ≈ 1 — characters set nearly touching |
| Row gap | 0.0344 UH (12 px of 349) | ≈ 5 — a real gap, 5× the column gap |
| Ink colour | `(212, 3, 5)` | = that diagram's `type_color` |
| White outline | dilation radius 1.0 | see below |

The row gap being five times the column gap is the one non-obvious number here: this is two
lines of text set tight, not a symmetric grid of four boxes.

#### The glyphs carry a white outline — SETTLED

Author-reported, then measured. Sampling colour rings outward from the red ink, both
references run **red → pink → near-white → background**, the near-white rings reading
`(254,220,220)` with individual pixels at `(255,255,255)`. That cannot be antialiasing: a
blend between the ink `(213,3,4)` and the background `(168,177,202)` is never BRIGHTER in
red than either endpoint. So the outline is real and it is pure white.

**Width — the reference's white extends 1.28 px beyond its red.** Measured on the horizontal
axis of the bottom row, which is the one trustworthy number available here for two reasons.
*Same glyphs*: 特快 is the bottom row of the reference (通勤特快) **and** of `chuo/916H`
(中央特快), so red and silhouette are compared glyph for glyph — an earlier attempt compared
通勤特快 against 中央特快 and got a contradiction, silhouette unchanged vertically but grown
horizontally, because kanji widths are per-glyph. *Horizontal only*: padding the row band far
enough to catch the halo above and below also catches the halo of the row **above**, and not
padding clips it, so the vertical figure moved between 1.49 and 2.78 with the padding and is
not used.

`outline_w = 1.0` delivers 1.49 px against that 1.28. It is a **dilation radius**, so the
number is not the visual width — the measured boundary sits at the 50 % point of the glyph's
own antialiased edge, which is inside the nominal outline.

**It looks inward, and it is not.** The halo composites over the glyph's own antialiased edge,
so adding one *visually thins* the red: our natural glyph is 38.00 px tall, with the halo it
measures 36.61, and the reference's red measures 35.86 against a larger silhouette. Same
signature — this outward implementation already reproduces what the reference does, so do not
re-derive it as an inset-red design.

#### How the halo is built — a supersampled max-dilation

The obvious implementation, a ring of integer-offset stamps, has two visible defects. The
author saw both, as *"the aliasing"* and *"the halo transition looks softer?"*:

1. **A polygonal boundary.** Integer offsets can only place the halo edge on whole pixels, so
   the outer edge is a staircase — most obvious on the diagonals these kanji are full of.
2. **Accumulated alpha.** A normal blit composites, so two overlapping antialiased edges give
   0.5 + 0.5 = 0.75 rather than 0.5. The halo comes out thicker and harder than the radius
   asks for, and the falloff at its outer edge is eaten.

Dilation is a *max* over the structuring element, so `BLEND_RGBA_MAX` is the correct operator
and fixes (2) exactly. Doing it at 4× scale and `smoothscale`-ing back down fixes (1): the
offsets become quarter pixels and the downscale resolves the staircase into real coverage.
Result: 34 % more intermediate pixels in the falloff, and the same number now delivers *more*
white, because the accumulating version was eating its own outer rings.

The supersample is of the **already-rendered glyph**, never of a larger font — a font size is
part of the atlas key, so rendering at 4× would put a second set of huge rasters in the atlas
for glyphs never drawn at that size. Every intermediate surface is pre-filled with the halo
colour at zero alpha rather than left transparent-black, because `smoothscale` does not
premultiply and would otherwise pull a grey fringe out of pixels meant to be white fading out.

Cost: 0.02 s to build all four outlined glyphs, then 0.07 ms/frame from cache.

### 8.5 Elements 2 and 3 — prefix and destination

Measured together because they share a question: both are plain kanji/kana runs on the
background with no box, and neither has a reference showing it at a length other than the
one captured.

#### Geometry `[measured]`

Both are **monospaced on a full-width cell**, like the train type but smaller.

| | prefix `ただいま` | destination `東京 行` |
|---|---|---|
| Ink bbox x/W | 0.0120–0.1758 | 0.2111–0.3502 |
| Ink bbox y/UH | 0.7593–0.9427 | 0.0315–0.2063 |
| @640×149 | x 8–112, y 113–140 | x 135–224, y 5–31 |
| Cell advance | 0.0430 W ≈ 27.5 px | 0.0406 W ≈ 26 px |
| Ink height | 0.1834 UH ≈ 27 px | 0.1748 UH ≈ 26 px |

The prefix's four cells advance by 0.0426 / 0.0433 / 0.0432 W — constant to within a pixel of
the capture, so it is a fixed cell, not proportional text. (Its ink splits into five column
runs because い is two disjoint strokes, not because a cell is irregular.)

Both run **smaller than the train type's 0.0559 W cell**, and about equal to each other.

#### Two alignment facts, one of them probably deliberate `[measured]`

- **The destination's left edge sits on the badge's left edge.** Destination ink starts at
  x/W 0.2111; the badge outline starts at 0.2104 — 1 px apart in a 1502-wide capture, under
  half a pixel on the 640 canvas. It is explicitly *not* aligned to the plate, whose left
  edge is 0.1877, nor to anything else on the screen.
- **The prefix is not aligned to the train type above it.** Prefix ink starts at x/W 0.0120,
  the train type's at 0.0186, and their centres (0.0939 vs 0.0762) do not agree either — so
  they are neither left-flush nor concentric. Part of the 0.0066 W difference is kana side
  bearing (だ) against a dense kanji (通), which is not enough to account for all of it.

#### `行` is composed, not authored

`route.json` holds `"dest": "東京"`; the reference reads `東京 行`. So the renderer appends
the particle, and the gap between them is a real measured 0.0160 W (≈ 10 px @640) against a
0.0013 W (≈ 1 px) gap between 東 and 京 — a deliberate space, not letter-spacing. This
matches E235, where the destination is composed the same way.

#### Destination — SETTLED

Drawn 2026-08-25. `{dest}` + a half-width space + `行` (author), monospaced on a fixed cell
like the train type but smaller and in one row.

| | value | how it was arrived at |
|---|---|---|
| face | `ShinGoPr6N-Medium` | ink COVERAGE inside each glyph's own bbox, which separates weight from size: the reference's 東 fills 0.470, against 0.324 Light / **0.506 Medium** / 0.575 DeBold / 0.671 Heavy. Medium misses HIGH, and a captured glyph loses coverage at its edges, so the true face is at or a hair under Medium |
| size, x, y | 27, 134, 4 | fitted |
| cell advance | 27.75 | fitted; ink starts measure 27.2, constant across both kanji |
| the space | the face's own ASCII space, 9px | the reference's extra gap is 8.5px, so the space is drawn as a space rather than as a fraction of the cell |
| colour | black | core ink samples (0,0,2) |
| halo | none | the type's white outline is a type-block feature; this is flat black on the background |

**Fitted, not read off the ink figures** — the region carries nothing but this element on flat
background, so it is scored pixel for pixel. Exhaustive over size 25–28 × x 132–137 × y 2–8 ×
advance 26.5–27.75: best **RMS 17.0**. The run lands at x 135–224 against the reference's
135–224, glyph for glyph. The left edge is the badge's, as § 8.5 measured.

`stops[].dest` rather than the route-level field, so a stop-level override renders — the
loader fills it on every stop by sticky propagation.

#### Station-name plate — SETTLED

The big white box. Drawn before the prefix and the name so both have something to be
positioned against, which is why it went in ahead of them (author, 2026-08-25).

**Outer box x 120, y 35, 398 × 103, outline 1px** — interior white 121–516 × 36–136 against a
measured 122–515 × 37–136.

The outline is **black, not `RULE_GREY`**, and it is a **diagonal gradient**: near black at
the top-left corner, fading to nothing before the bottom-right (author — *"if you probe the
ref carefully, it's a boarder with gradient"*). The plate reads as lit from the upper left
rather than as a boxed rectangle, and drawing it flat looks wrong.

The probe is **integrated ink** — `background − luminance` summed over a 6px band straddling
the line — sampled all the way round and plotted against the diagonal coordinate
`u = ((x−x₀)/w + (y−y₀)/h) / 2`:

| u | 0.01 | 0.13 | 0.25 | 0.37 | 0.42 | 0.46 | 0.51 | 0.59 | 0.67 | 0.75 | 0.83 | 0.87 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ink | 209 | 207 | 208 | 208 | 194 | 184 | 178 | 132 | 87 | 40 | 7 | 0 |

Top and left interleave along the flat; right and bottom interleave along the ramp. All four
edges landing on **one** curve is what makes this a gradient across the box rather than four
differently-drawn sides — a bevel would put top+left on one value and right+bottom on another,
with no ramp between. So: full strength to u = 0.40, linear to zero at u = 0.87.

Integration rather than the darkest pixel, because a ~1.2px line lands on a different
sub-pixel phase in each capture: the LEFT edge's darkest pixel reads 43 on one reference and
64 on the other, while their integrals agree to within 1%. Reading the phase instead of the
quantity is what makes the two captures look like they disagree — and it is also what the
extent comes from, since the outline's own shoulder moves where a white-threshold thinks the
white starts. Ink centroids put the left line at x 120.13, the right at 517.3, the top at
y 34.83, the bottom at 137.6.

The flat's 209 is 1.16px of solid black at this background. Rendered as 1px: the residual is
the capture's own resampling ringing (pixels *above* background sit on the light side of every
edge), not a second pixel.

The white does **not** run under the outline — at the faded end the edge pixel reads 178–194
against a 252 interior, so it fades into the background, not into the fill.

All three references are STOPPING frames, so nothing says whether the plate changes between
approaching and at-station. Treated as invariant until a reference says otherwise.

#### Prefix — SETTLED

次は / まもなく / ただいま, left-flush at the bottom left, in the corner the train type leaves
free. Same monospaced cell as the destination and the same face.

| | value | how it was arrived at |
|---|---|---|
| face | `ShinGoPr6N-Medium` | coverage: the reference's ま fills 0.463 / 0.466, against 0.26 Light / **0.48 Medium** / 0.53 DeBold |
| size | 28 | fitted |
| cell advance | 27.0 | float — the cursor accumulates and rounds per cell, so a fractional advance is expressible. Ink starts measure ~27.5 |
| x, y | 6, 113 | integers by design: the row is a raster blitted at a whole pixel |
| colour | black | and **no halo** — the brightest pixel anywhere in its band is (184,188,209), barely above background, where a white outline would pin near 255 |

**Fitted, not read off the ink starts.** The region carries nothing but this element on flat
background, so it can be scored pixel for pixel over the whole region rather than at hand-picked
cuts — which means no parameter can go unconstrained the way the plate's `w` did. Exhaustive over
size 28–31 × x 5–10 × y 110–116 × advance 26.5–27.75: best **RMS 37.1** at size 28 / x 6 / y 113 /
advance 27.0, against **69.7** for drawing nothing at all.

The run then reproduces the reference run for run — five column runs for four characters, because
い is two disjoint strokes:

| | | | | | |
|---|---|---|---|---|---|
| ours | 8–31 | 35–59 | 62–74 | 78–85 | 90–111 |
| reference | 8–31 | 35–59 | 63–74 | 78–85 | 90–112 |

The RMS floor is high because text is high-frequency and the reference's rasters came back through
a 2.35× upscale — position and size are what this settles, not per-pixel identity.

#### Two clipping defects in the cell renderer — FIXED

Both were silent: nothing raised, the row just lost ink.

**Horizontal — a glyph wider than its cell.** Kana carry ~2px of side bearing so they sit inside a
27px cell at this size; 次 fills its em edge to edge and hung 2px off the left of a row surface
sized to the cells alone. No reference frame could have shown it, because all three read ただいま
(author: *"found your 'tsugi wa', left part has like 5 px cut off"*). `_render_cells` now measures
the overhang over the glyphs actually drawn, pads for it, and returns that pad so the caller still
positions the cell origin.

**Vertical — pygame's own `Font.render`.** It returns a surface exactly `get_height()` tall
(`ascent + |descent|`), and at small sizes FreeType's grid-fitting can inflate a glyph past that.
The overflow is only ever one pixel, but it is a pixel of ink. Over the 251 distinct characters
this display draws it hits **向 城 成 片 行 越** at the destination's size and **越** at the
prefix's — and `行` is on *every* destination, which is how the author caught it (*"your dest has
some px cutoff at bottom as well"*). By size 38 no glyph overflows.

So a row under that threshold is rendered at a whole multiple above it and resolved down
(`_cell_scale`, `_CELL_MIN_RENDER = 48`). Three consequences: the clipping is gone, the downscale
is real antialiasing, and the glyph gets its **true** proportions rather than its grid-fitted ones
— 東's ink measures 1.000 of the em at 26 and 0.950 at 80, and 0.950 is the outline. The reference
agrees with the outline. The factor is derived per size, so an element already drawn large enough
pays nothing; the station name at 76 is such an element.

Every figure fitted against the old raster was **re-fitted** after this landed rather than kept.

**Detector note.** The first pass at checking this used edge alpha and reported 57 clipped rows
including ones that were fine — after a downscale the antialiasing tail legitimately reaches the
surface edge. The two real tests are the SOURCE render (does a glyph need more rows than
`Font.render` gives it, from `metrics`) and the RECT (does drawn ink land outside the clip). Both
now report zero across 16 destinations, 3 prefixes and 237 station names, and both were observed
failing before the fix.

#### Station-code badge — DRAWN, 2026-08-26

Wired to the **shared** helper `displays.utils.draw_station_code_badge` — the same one
E235 uses for its upper badge and its 8-station cells (author — *"there's already the badge
utility, wire that up and use, but adjust the size to the ref"*). Only the sizes are this
model's.

**The shape differs from E235's and the helper already reaches it.** E233-0's badge is an
orange rounded-square OUTLINE on white with **no black frame**; E235's carries a black ring
outside its colour ring. `ring_black = 0` with `outer_radius == color_radius` gets there: the
helper still lays its black rect down first, but the colour rect that follows has the same
rect AND the same radius, so it covers that black exactly. Unequal radii are what would let
black corners show.

| | value | how it was arrived at |
|---|---|---|
| outer square | x 134, y 64, 58 × 57 | 50% ink crossings on the straight runs: 133.9 / 64.2, 57.5 × 57.6 |
| stroke | 5 | measured 5.3–6.2 per side across the two references |
| corner radius | 8 | circle fit to the left edge's walk over the corner rows — 8.31 in BOTH references, rms 0.3px |
| interior radius | 4 | fitted |
| `JC` / `24` | 19 pt / 27 pt | fitted; the digits run half again the letters' ink height |
| gap, offsets | 3, `text_y_offset` 0, `prefix_x_offset` 1 | the block is centred in the interior and the reference agrees |
| colour | `route.json`'s `color` | reference stroke samples (226,92,17) against Chūō's authored (233,91,31), inside what an upscale moves a colour by. The model owns no orange |

**Fitted over the whole badge region across BOTH references at once**, so no parameter is
left free the way the plate's `w` was: **RMS 34.0** against **94.7** for drawing no badge at
all. Ink then lands where the reference's does — letters y 74–88 and digits y 91–110 against
74–88 and 91–111, both rows centred within a pixel.

The two references are the one genuine cross-check available here: JC24 at 高尾 and JC03 at
御茶ノ水 measure the same frame to within half a pixel, and the plate behind them lands in the
same place, so the crops are aligned and the badge is confirmed state- and view-invariant.

- OPEN — the 3-letter interchange band (`code_3`, the top band E235 grows for TYO / SJK).
  Neither 高尾 nor 御茶ノ水 carries a `code_3` in `data/stations.json`, so no reference can say
  whether this model draws one. Not drawn until one does.

#### Station name — SETTLED

**One mechanism: `displays.utils.draw_text_given_width`**, the same one E235 uses — horizontal
compression only, never a change of size (author, 2026-08-26 — *"only horizontal compression,
just like the draw text given width, but only you need to have the advance set correct"*). So
the element is a SPAN, plus — for names shorter than the span's natural capacity — the width
that puts the advance where the author put it.

| | value | how it was arrived at |
|---|---|---|
| face | `ShinGoPr6N-Medium` | coverage 0.523 reference against 0.303 Light / **0.511 Medium** / 0.569 DeBold / 0.686 Heavy |
| size | 75 | fitted; NEVER varies with the name |
| span | x 205, width 296, y 54 | fitted on the 御茶ノ水 capture |
| centre, 4+ | 353 | the span's own centre; the reference's 御茶ノ水 run measures 353.5 |
| centre, 1–3 | 345 | measured off the reference's 高尾 run |
| advance, 2 | 96 | measured — the reference sets 高尾's glyphs 95.66 apart |
| advance, 1 and 3 | the em (75) | **authored**, no reference — natural, no letter spacing |
| colour | (0, 114, 0) | darkest ink sampled (0,113,0) / (0,107,0) |

**The span comes from 御茶ノ水, which is the capture that shows a name at its NATURAL length**
— four characters filling the span with no spread and no compression (author — *"the left and
right is defined by ochanomizu screenshot … natural length is 4 chars"*). Fitted over the plate
interior pixel for pixel: **RMS 29.5** against **110.7** for drawing no name at all.

**Five and up need nothing more.** The same call compresses them into the same span, which is
what `compose_text_parts` does once the text is wider than the width it is given.

**One to three do not spread to the span, and that is the only per-length thing here.** Left to
itself the even-spread branch would push 高尾 to a 136px advance where the reference measures
96. So the advance is authored and the WIDTH is derived from it, rather than the other way
round: `width = (n + 1) * (advance − exp) − em`, where `exp` is 14 for a two-character run —
`compose_text_parts`'s `exp = 7` kick, which pushes the pair outwards by 7px each.

**Short names carry their own centre, and the 8.5px is real.** The references put 御茶ノ水 at
353.5 and 高尾 at 345.0, and the two captures agree to within half a pixel on the plate behind
them, so the difference is the display's rather than the crop's. Author — *"then follow the
fucking ref"*.

Against all three references, ink lands within 2px:

| | ours | reference |
|---|---|---|
| 高尾 (2) | 262–429, advance 95.5 | 260–430, 95.66 |
| 御茶ノ水 (4) | 206–500 | 206–501 |
| 武蔵小金井 (5) | 206–499 | 208–501 |

A space inside a name is the data format's line-break marker; this element has one row, so it
is dropped rather than drawn.

- OPEN — a 1-character and a 3-character name are authored, not measured. If a reference for
  either turns up, it settles `adv_1` / `adv_3` and possibly gives the short branch a per-length
  centre instead of the one it shares now.

#### Clock — SETTLED

A white box in the bottom-right corner with the time in black. **Found by mapping the band, not
by eye**: the stub had inherited the description "white box, bottom right" from a session that
never measured it, and a white-region scan of the right-hand end found nothing — because the
box's edge is soft and the scan was looking for a hard one.

**The box has no outline, and its corners are ROUNDED** — both unlike the station-name plate.
Reading across any edge gives background → ramp → white with nothing darker than the background
anywhere, and the left edge walks 556.74 → 555.59 → 555.08 → 554.70 → 554.50 over four rows before
holding, which a **5.15px** circular corner reproduces to within 0.2px per row. The plate is square
by the same measurement — its left edge sits at 121.73 from y 37 through y 136 without moving, where
a 5px radius would put the y=37 edge 2.3px right of that. One builder serves both: the radius
defaults to 0, which reduces the distance field to the square case exactly.

**`H:MM`, not `HH:MM`.** The reference reads 8:36 and the hour's leading cell is empty white — 16px
of it, exactly one digit. `app.py` hands every model `time.strftime("%H:%M")`, which *is*
zero-padded, so the strip happens in this renderer: it is a presentation choice of this model, and
E235 draws the padded form. Stripping one character rather than `lstrip("0")`, which would turn
midnight into `:36`. The run is right-aligned so the minutes hold their place when the hour loses
a digit.

The time was read out of the pixels as a character grid, not off the image by eye.

**A two-digit hour is CENTRED, and that is authored rather than measured** (author, 2026-08-25).
No reference shows one. The reference's own position is not centred — its run sits +4.65px right
of the box centre, margins 16.0 left and 6.7 right — so carrying that straight into `18:36` would
put the leading digit flush on the box's left edge with 6.7px still spare on the right, which
reads as bad spacing. So the long form centres and the short form keeps the measured position:
`8:36` at margins 16.4 / 9.1, `18:36` at 5.4 / 7.1.

**Monospaced, with the colon on its own narrower cell.** All three reference digits carry ink
exactly 15px wide on a 16px pitch, which no proportional setting produces; the colon's ink is 4px.

| | value |
|---|---|
| box | x 554.6, y 106.1, 78.45 × 31.85, `fill_feather` 1.45, `corner_r` 5.15 |
| face | **`HelveticaNeue-Medium`** — e235 independently uses `HelveticaNeue-Roman` for its clock, so the family is corroborated; the weight is this model's own |
| size, y, right edge | 31, 111, 624 |
| digit pitch / colon cell | 15.5 / 7.0 |

**The face is Latin, not ShinGo.** The model's "ShinGo throughout" is about its Japanese text:
ShinGo sets a digit 19px wide at the height this needs, against the reference's 15, and no size
fixes an aspect ratio. Fitting the whole region settles it — Medium **24.2** / Roman 32.4 / Bold
49.6 / Frutiger Bold 89.3 / ShinGo Medium 79.2 / ShinGo Light 83.6, against **92.4** for the box
with no digits at all. The ShinGo candidates barely beat drawing nothing.

**The first pass of that fit picked ShinGo Light, and was wrong for a reason worth keeping:** it
compared faces at a *fixed* `y`. Each face seats its digits at a different height in the font box,
so a fixed y is a handicap that has nothing to do with the face. Giving every candidate its own
best y and right edge before comparing reversed the answer and took the score from 75 to 24. Same
shape as the plate's `w` drifting while its RMS improved — **a parameter the score cannot see is
not being fit.**

Ink lands at x 571–624, y 111–133; the reference measures 571–624, 111–133.

### 8.6 Build state

| File | What it holds |
|---|---|
| `displays/train_models/e233_0/__init__.py` | canvas + palette (§ 2), chrome `# CONTRACT:` |
| `displays/train_models/e233_0/upper_lcd.py` | `JapaneseDisplay` + `UpperDisplay`. Drawn: train type (with its white halo), destination, the station-name plate, the station-code badge, the name inside it, the prefix and the clock. Car number is the one element still absent, and it is blocked on § 8.3's data-source question rather than on drawing |
| `displays/train_models/e233_0/lower_lcd.py` | background + border placeholder. Every renderer slot points at ONE `_PendingView`, deliberately — an empty view is a state the author can see, a borrowed E235 one is not |

Registered in `TRAIN_MODELS` as **"E233-0 (WIP)"**, so it is selectable, previewable and
calibratable while half-built. The label carries the warning rather than a doc doing it.

All three `DisplayMode` values resolve to the same `JapaneseDisplay` instance (§ 4), so the
mode cycler keeps ticking with nothing to switch between.

#### Editor changes this required

The calibration editor was `e235_0`-only, and `preview_display --edit` refused every other
model — correctly, because the edit window was sized from a hardcoded `e235_0` import while
the sim rendered whatever was asked for. Both are now derived:

- `_REGISTRY` entries carry `model`; the editor filters hit-testing, handle drawing, focus
  and the `V` view list on it (`set_active_model`, bound from `sim._train_model.key`).
- `--edit`'s accepted models come from `calibration_editor.editable_models()`, derived from
  the registry, so registering the first element of a model is the only step.
- The edit window reads `s_width` / `s_height` / `upper_height` from the loaded model's
  `TrainModel` record. `upper_height` was added to that namedtuple.
- The reference overlay letterboxed into `e235_0.lower_lcd.ARC_RECT`, meaningless on a
  640 × 480 canvas and not covering the upper band at all. A model without that rect now
  fits the whole LCD; e235_0 is unchanged.

The model filter was mutation-proved both ways at birth: `train_type` is reachable under
`e233_0` and not under `e235_0`, `full_route` the reverse, and `e235_0`'s edit-window
dimensions are unchanged by the move (730 × 420 × 130, registry == module).

### 8.7 Layout by character count — SETTLED

Two layouts, chosen by length (author, 2026-08-23):

| length | layout |
|---|---|
| **2 or 4** | **SLOTS** — the fixed 2 × 2 grid at `font_size` (§ 8.4), unchanged |
| everything else (1, 3, 5, 6, 7) | **STACK** |

Those two lengths are the ones the measured grid fills exactly. Every other
length leaves it ragged, and the stack reads better than a half-empty grid.

**STACK** = rows drawn **flush left at `box_x`**, one under the other, all at one
constant `long_font_size`, at **natural spacing with no compression**. Rows are
placed by their **ink** box, not their surface, because the surface carries layout
padding — aligning the surface would align the padding.

Committed: `long_font_size = 18`, `long_line_gap = 2` (clear ink between rows).
The line pitch comes from the row's own size, not the 41 px cell pitch, which is
calibrated for 38 px glyphs and leaves a hole at this size.

At 18 a 5-character row runs 90 px from `box_x`, past the 73 px slot box — so
`TRAIN_TYPE_RECT` is sized for the **stack** (104 px wide), not for the box. Still
clear of the plate (x = 120) and the destination (x = 135).

| type | renders |
|---|---|
| `快速` · `普通` · `中央特快` · `各駅停車` | SLOTS |
| `快速アーバン` · `快速ラビット` | STACK — 快速 / アーバン |
| `快速アクティー` | STACK — 快速 / アクティー |

**Where the split goes.** Every long type in the corpus is 快速 plus a katakana
nickname, so the split is the **ideograph → kana boundary** — the semantic break.
A type with no such boundary splits evenly. One function, `_split_type`.

Three things had to be got right, each of which had been silently wrong:

- **`collapse=True`.** `compose_text_parts`'s default branch spreads characters to
  fill the given width *and* pushes a two-character run outwards by a fixed 7 px,
  placing the first glyph at a **negative** offset. That is correct for E235's
  train-type box and wrong for a stack, where it opens a gap inside 快速 and, on a
  surface cut to the text, clipped the first glyph. `collapse=True` skips that
  branch entirely. It is the same `exp = 7` `principles.md` records a proof script
  missing.
- **No compression.** An earlier version squeezed a 5-character row into the box
  width. At a size where it fits on its own, squeezing only makes it a different
  shape from the 4-character rows.
- **Surface sized from the core.** The composite was sized from the layout width
  while the core carried an inset, cropping the row.

### 8.8 Every route draws its type — SETTLED

**Reversed** (author, 2026-08-25). An earlier pass suppressed the train type on
the Yamanote, on the reasoning that an all-stations line's designation carries no
information; the author reversed that, so every route draws its type, the Yamanote
included. `route.json` already records 各駅停車 for it, so there is nothing to
special-case — the type and its colour come from the data like every other
route's. `_LINES_WITHOUT_TRAIN_TYPE` is gone.

Verified across all 16 shipped routes × every stop × 3 states: 0 failures.

### 8.9 Antialiasing and the halo — SETTLED

**The whole element is built at 4× and resolved once.** The font is asked for
`size × _TYPE_SUPERSAMPLE`, the halo is dilated in those large pixels, the glyph
is composited onto the halo while still large, and one `smoothscale` resolves the
result. Area-averaging a 4× raster is analytic antialiasing: every edge, and the
red/white boundary between them, gets its coverage computed rather than
rasterised. Prompted by the author, 2026-08-25 — *"AA needs improving, jagged
edges."* Previously only the halo was supersampled, so the red carried FreeType's
own hinted 38px raster against a halo that no longer did — the highest-contrast
edge in the element was the one not being antialiased.

**Cost, measured.** A font size is part of the atlas key, so this bakes 4×
rasters: 11 slot glyphs at 152px and 4 stack rows at 72px. Nothing else in this
display asks this renderer for a font, and the atlas stores alpha coverage, so
one baked entry still serves both the red fill and the white halo.

#### The halo has two axes, and conflating them cost three rounds

`outline_w` is the total extent beyond the ink; `outline_feather` is how much of
that extent is spent fading, measured inward from the outer edge. **Settled at
2.0 / 2.0** — feather equal to extent, so no solid white core at all.

Three findings, in the order they were made, each one a correction of the last:

1. **Removing the blur dropped a load-bearing property.** The old construction
   dilated a `smoothscale` upscale, which blurred the glyph (the bug) *and* gave
   the halo its falloff (not a bug). Measured: old = 987 halo px at 6% pure
   white; new = 597 px at 27% pure — narrower and four times harder. The
   reference is almost all gradient. `outline_feather` makes that falloff
   authored rather than inherited from whatever the resampler happened to do.
2. **A floored quantisation level drew a polygon.** `max(1, ceil(cov * levels))`
   gave every offset in the disc a floor of one level, so the outermost ring was
   a flat ~6% plateau shaped like the *digital* disc — 5.0px on the axes, 4.24px
   on the diagonal, hence 15% thinner at 45°. The author saw it as *"the white
   halo is not uniform on the edges."* Fixed by rounding to nearest and dropping
   what rounds away; 1167 of 9568 pixels changed, max channel delta 50.
3. **"White beyond red" is the wrong instrument for a gradient.** It classifies
   each pixel as the nearest of {ink, white, background}, so it reports the 50%
   crossing — 1.28px on the reference, which made `ow` 1.25 look like a match
   while the two looked nothing alike. A **radial profile** (mean whiteness
   against the background, binned by distance from the ink) separates the axes:

   | d from ink | 1px | 2px | 3px |
   |---|---|---|---|
   | reference | 0.10 | **0.53** | 0.11 |
   | ow 1.25 / f 0.5 | 0.34 | 0.07 | 0.00 |

   The reference *peaks outside the first ring* and ours was dead by 2px — wider
   AND softer, which is what the author asked directly (*"is it because the
   reference just have a bigger halo and more feather?"*). Yes, both.

**One instrument was built and thrown away.** A per-boundary-pixel distance
measure of halo evenness returned a p10 of 0.00px on the reference, meaning it
was measuring "is there any halo here" rather than how even it is. Finding 2 came
from reading the construction, not from that measurement. Recorded so it is not
rebuilt (`critical_lessons.md` §11).

### 8.10 Weight — SETTLED

**ShinGo DeBold**, "the most accurate weight for train type" (author,
2026-08-25), chosen against the reference over Heavy / Medium / Light. It is the
**Pro** cut (Adobe-Japan1-4), not Pr6N; renamed from Morisawa's own
`A-OTF Shin Go Pro DB.otf` to `ShinGoPro-DeBold.otf`, and deliberately NOT to
`Pr6N`, which would misstate the glyph set. The face lives in one constant,
`_TYPE_FACE`.

Two mechanical consequences of that filename, both fixed in the same change:

- **It was untracked AND unignored** — the one state `git add -A` publishes. The
  ignore rule read `/fonts/ShinGoPr6N-*.otf`, which names one naming convention;
  the exposure is a property of the FAMILY. Widened to match `ShinGo` however it
  is spelled, against the 2026-08-08 decision to untrack Morisawa faces.
- **`ATLAS_FACES` keyed on the same one convention**, so the Pro cut would have
  classified as a shipped face — loading live in both modes and having to travel
  with the build, which is the posture the bake exists to end. Now keys on
  `ShinGo`.

**Not drawable in production, correctly.** 通勤特快 — the type in the reference
capture — raises the declaration check: the atlas domain indexes JSON *values*
and that type exists only as a KEY in `data/train_types.json`. No shipped
`route.json` carries it. Comparison harnesses mute the check in their own file;
the renderer is untouched, and a 通勤特快 diagram would make it a declared value
automatically.

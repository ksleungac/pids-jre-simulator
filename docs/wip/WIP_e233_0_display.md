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
| 1 | **Full route** | The whole line on two rows, right-to-left, with the section beyond this train's service in grey | v1 — **first** · **COMPLETE**, § 9 |
| 2 | **6-station** | Six stations, one thick bar, current stop at the right | v1 — second |
| 3 | **Transfer info** | Connecting lines per station | **BUILT**, § 11 — inline band (§ 10.3.4) and standalone view |
| 3a | **優先席** | Priority-seat placard, static | **BUILT** 2026-08-29 · `priority_seat.py` · reference `priority-seats.png` |
| 3b | **マナーモード** | Mobile-phone notice, static | **BUILT** 2026-08-29 · `manner_mode.py` · reference `manner-mode.png` |
| 4 | **Patterns overview** | All six Chūō service patterns as parallel coloured lines with per-station stop markers | noted, **not scoped** |
| … | *further views* | author collecting references | pending |

**Transfer info — deferred to its own session, and not an E233-0 distinctive.** In the
6-station reference the transfer entries are drawn as an **inline band beneath the bar**,
aligned to each station's column. That is *not* a difference from E235: **E235 has the same
inline band, we simply have not implemented it** (author, 2026-08-22). So the question of
inline-vs-standalone is a shared-architecture question, not something E233-0 settles on its
own, and it waits for its own discussion.

**Both, and E235 keeps its own** — settled 2026-08-29, § 11.1. The inline band is built (§ 10.3.4)
and the standalone view is specced; E235's horizontal panel is unchanged. The slot count that
follows is three, on the existing beat schedule and the existing `at_station` force-switch.

---

## 4. Scope

**In, v1:** full route → 6-station → transfer info, **Japanese only**, on Chūō
(`chuo/1654T`, `chuo/916H`).

**Deferred, not abandoned:**

- **Furigana — BUILT 2026-08-30.** `upper_lcd.FuriganaDisplay`, a two-element override of the
  kanji renderer: the prefix (`次は` → `つぎは`; まもなく and ただいま are already kana) and the
  station name (readings from `translations.json`, declared against `STATION_READINGS` with its
  own font cache — a merged declaration would let an undeclared reading pass `check_declared` on
  the strength of some kanji name). Everything else stays kanji, matching
  `transfer-hachioji-ja.png`, which is a capture of this mode. A station with no reading falls
  back to kanji through the parent's font rather than showing a blank plate.
- **English — STILL DEFERRED, and now the model's only gap.** `english_display` resolves to the
  kanji renderer in both the upper and lower managers, so the cycler ticks through a third
  identical page. Same shape of work as furigana: an override per element that differs, not a
  second renderer. Nothing structural blocks it.
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
| Transfer | `transfer-hachioji-ja.png` | 八王子 — added 2026-08-26. Two entries, `(1,1)` |
| Transfer | `transfer-tachikawa-ja.png` · `transfer-ocha-ja.png` · `transfer-shinjuku.png` · `transfer-kanda.png` | added 2026-08-29 **during** the build, after § 11 was first written. They are what settled the grouping: `(1,1,1)` · `(1,2)` · `(2,2,2,3)`. The 新宿 one is a photograph of a real screen rather than a clean capture, and carries a ticker line the others do not |
| Priority seat | `priority-seats.png` | added 2026-08-29 |
| Manner mode | `manner-mode.png` | added 2026-08-29 |
| 6-station, ENGLISH | `6stations-yotsuya-ja.png` | 四ツ谷 — added 2026-08-29. The first capture in a mode other than Japanese, and it confirms the **lower LCD stays kanji** in English mode (§ 4). It is also the only frame showing a **coded station behind the train** (新宿 JC-05, greyed), which is what settled § 10.3.2 |

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

**A loop line takes 方面, not 行 — SETTLED 2026-08-26** (author). 山手線 has no terminus, so its
destination is a direction: `品川･東京方面`. Same rule and same predicate E235 applies
(`"方面" if route_name == "山手線"`), only this model's other particle is `行` where E235's is
`ゆき`. Keyed on the route NAME rather than on `circular`, so both models answer it the same way.
The run grows by exactly one cell (174 px → 202 px on `品川･東京`), still well inside the
destination rect; every non-loop route is byte-identical across the change.

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

**The interchange variant — SETTLED 2026-08-26.** At a station carrying a `code_3` in
`data/stations.json` the badge grows a black frame and the 3-letter band above it; everywhere
else it is the plain orange outline the references show. On Chūō that is 東京 TYO, 神田 KND and
新宿 SJK. `ring_black` is therefore not a constant of this model — 0 unless the station has a
code, which is what keeps the two shapes ONE element.

The frame grows OUTWARD: the rect handed to the helper is the badge's own `x/y/w/h` expanded by
the frame thickness, so the helper's colour rect lands back on the measured orange square and
the white interior does not move. The band clears the plate's top edge (45 against 36).

**The band's figures are the helper's, reused** — frame 7, band 12, 20pt, `y_offset` 4. No
reference shows this variant, and the logic is already calibrated on E235, so it is taken as it
stands rather than re-fitted. Tuneable if a capture at 東京 or 新宿 turns up.

**The interior was the wrong white, and the badge fit could not see it.** The helper fills its
interior with the LCD `WHITE_BG` (230) that E235's badge sits on; this badge sits inside the
plate, whose fill is 254, so it rendered as a grey square in a white box. The reference's
interior samples 252–254 against a 254 plate — the same white, no square. Fixed by giving the
helper an `interior_color` (default unchanged, so E235 is byte-identical — verified: 0 differing
pixels in its badge region across the change), which E233-0 passes `PLATE_WHITE`. The RMS fit
that settled the badge varied only geometry, so a 24-level fill error sat inside its residual —
`principles.md` § "A parameter the score cannot see is not being fit".

- OPEN — the 3-letter band's own geometry on this model. Inherited, not measured.

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
| `displays/train_models/e233_0/lower_lcd.py` | `JapaneseFullRouteDisplay` — the full-route view, complete (§ 9). The zoomed and transfer slots still point at ONE `_PendingView`, deliberately — an empty view is a state the author can see, a borrowed E235 one is not |

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

**Not drawable in production, correctly (§ 8.10).** 通勤特快 — the type in the reference
capture — raises the declaration check: the atlas domain indexes JSON *values*
and that type exists only as a KEY in `data/train_types.json`. No shipped
`route.json` carries it. Comparison harnesses mute the check in their own file;
the renderer is untouched, and a 通勤特快 diagram would make it a declared value
automatically.

---

## 9. Lower LCD, full-route view — COMPLETE

**Specced 2026-08-26, finished 2026-08-29.** § 9.1 is the author's; § 9.2 is measured; § 9.3 holds
the per-element specs in the order they were settled, and § 9.4 records what remains open. Every
element has been through the loop and signed off; the view is done.

### 9.1 What the view is

**The diagram is the LINE, not the run.** Chūō's full-route view always draws 大月 → 東京:
**row 1 is always 大月 → 武蔵境, row 2 always 三鷹 → 東京**, twenty stations each, whatever
service is loaded. The split is a fact of the line, not something derived from the route's
length.

**Both rows read RIGHT TO LEFT**, wrapping row 1's left end into row 2's right end. So screen
order is the reverse of index order and *behind the train is to the right* — which is why the
grey tail in the reference sits right of the marker at 高尾, the run's own first stop.

**The eight west of 高尾 arrive as `pre_stops`** (author — *"use pre-stops pattern. like
sobu"*): 大月 JC32 · 猿橋 JC31 · 鳥沢 JC30 · 梁川 JC29 · 四方津 JC28 · 上野原 JC27 · 藤野 JC26 ·
相模湖 JC25. They exist in no other file in the repo. The mechanism is the existing display-only
one (`docs/DATA_FORMAT.md` § pre_stops) reused for a line that extends beyond its origin rather
than for a through service; both render identically, as always-passed cells. 8 + 32 = 40 = 20+20,
and that arithmetic is the check on the whole model.

**Colour follows E235's rule** (author): grey for stations the train has passed AND for stations
it passes through; black for this station and every stopping station ahead. One index test covers
both greys, since a `pre_stop` is simply a cell with a lower index.

**Elements:** the two bars · a white box on the bar at each stopping station, carrying the minutes
to it · an arrow on the bar where the train passes · a green triangle at the train · vertical
station names above the bar on **both** rows · continuity arrows at the wrap.

**Names are never compressed.** Chūō's longest is five characters, the spacing allows six, so the
box is six characters and short names bottom-align onto the bar.

### 9.2 Geometry `[measured]`

Off `full-takao-stopping-ja.png` by colour-run detection
(`_dev_scripts/_e233_lower_geometry.py`), as ratios against the reference's own 1502 × 1124:

| | ratio | @640×480 |
|---|---|---|
| bar row 1 centre | y/H 0.5783 | 278 |
| bar row 2 centre | y/H 0.8768 | 421 |
| bar height | h/H 0.0485 | 23 |
| bar extent | x/W 0.0353 … 0.9627 | x 23, w 593 |
| slot pitch | extent / 20 | 29.65 |
| served bar | (225, 92, 18) | route `color` |
| behind / beyond | (134, 144, 164) | = `RULE_GREY` |
| position marker | (51, 168, 58) | |

**The slot count is confirmed rather than assumed.** The green marker measures centre x 853.5 in
the reference; 高尾 is the ninth cell from the right of a twenty-slot row, whose computed centre
is 853.4.

**Behind the train the bar carries nothing at all** — the grey run right of the marker measures
568 px unbroken across its eight slots, so no box and no arrow is drawn there. That is measured,
not inferred from the state.

### 9.3 Build state

`displays/train_models/e233_0/lower_lcd.py` — `JapaneseFullRouteDisplay`, wired into the editor as
`e233_full_route` over three dicts (bars · marks · names). The zoomed and transfer slots are still
`_PendingView`. Structural patterns come from E235-**1000**'s linear full-route, which is where the
minute box, the passing arrow, the position marker and the continuity pair already live; E235-0
supplied the two-row layout shape and the uncompressed vertical name stack.

### 9.3.1 Station name — SETTLED 2026-08-27

Vertical, above the bar on both rows, bottom-aligned onto it, **never compressed**.

| | value | how it was arrived at |
|---|---|---|
| face | `ShinGoPr6N-Medium` | the model's own; not re-probed for this element |
| size | 15 | [measured] the reference sets 14px of ink on a ~15.5px pitch — one 3-character column runs 218–231, 233–246, 249–261, so the inter-character gaps give the pitch directly |
| line gap | 1 | ditto |
| bar gap | 5 | the reference leaves 5.5px between the stack's bottom and the bar |
| colour | black ahead, grey behind and at passed-through stations | author; the grey value itself is authored, not measured |

**The slot pitch was the real defect, and the name only exposed it.** Deriving pitch as
`bar_w / 20` is right at the middle of a row and wrong at both ends, because the bar stops
3–4px short of a half-slot past each end station — so the quotient runs 1.4% small, which is
0.4px per slot and 7px by the nineteenth (author — *"scales are not matches at non-center
stations"*). The slots are now a least-squares fit over the reference's twenty name-column
centroids, and the two rows were fitted **independently** as the cross-check: row 1
`centre(k)/W = 0.94521 − k·0.04698`, row 2 `0.94649 − k·0.04705`, agreeing to 0.15% of pitch.
Ours lands at `0.94558 − k·0.04706`; per-column error against the reference is ≤1.8px with no
direction to it, which is per-glyph ink balance rather than drift.

Two things that were deriving from the same wrong number moved with it: the orange/grey
boundary is now a slot edge, and click-to-jump rounds to the nearest slot centre. `bar_x` /
`bar_w` stay measured and now describe only the bar.

**A space in a name is a line break, and the handling is E235-1000's** (author, 2026-08-27 —
that model mimics an E233-1000, so it is this family's own): `utils.draw_stops_text`'s
structure — the right column reads first and is raised, the left hangs from the bar — but
**without its compression**, since names here are never compressed. Chūō has no compound name;
the case exists only on borrowed routes.

- OPEN — at an out-of-spec **shrunk** pitch a two-column name is wider than its slot: the pair
  measures ~31px against Keihin's 25.8px, so さいたま 新都心 crowds 大宮. A narrower column gap,
  a smaller face for compound names, or the strict-20 split would each answer it.

### 9.3.2 Position marker — SETTLED 2026-08-27

A green **pentagon**, nose left, sitting on the orange/grey boundary. Author-signed-off;
the shape was probed rather than taken from the word "triangle" (*"don't trust my word,
probe it"*).

| | value | how it was arrived at |
|---|---|---|
| vertices | `(6.56,−11.08) (6.56,10.65) (0.25,10.65) (−9.39,−0.41) (−0.06,−11.08)` | each of the five EDGES least-squares fitted at native resolution; the vertices are where those lines meet, so they carry sub-pixel positions a ±1px classified map cannot. Free vertices, not a parametric shape — `conventions.md` § "Single-slot, fixed-orientation marker" |
| two tones | `(65,176,60)` above, `(0,103,0)` below, split on the bar's centre row | a vertical slice reads flat either side; the dark one is the route's own `contrast_color` within capture drift |
| rim | white, **1.5px, all the way round** | author: *"the polygon has white outline all sides"* |
| shadow | `(52,62,59)`, reach 3.2px beyond the rim, **bottom and right only** | author: *"it should be only on bottom and right"*; measured 3.0 right and ~3.8 below |

**The rim and the shadow are independent, and conflating them cost two rounds.** A probe
walking outward from the green shows the shadow's `(52,62,59)` immediately past the base
with no bright pixel between, which reads as "no rim there" and is not: the rim is under
the shadow. The author's eye on the artifact settled it against the walk
(`critical_lessons.md` § 11).

Three construction facts, each of which was silently wrong first:

- **The rim is 1.5px where the reference measures ~0.85.** A sub-pixel band never fills a
  pixel, so it resolves as a half-and-half mix with whatever is OUTSIDE it — reading `245`
  against the pale background and `124` against the shadow. Same rim, opposite appearance.
  1.5 guarantees one fully-covered pixel, which is what makes it survive next to the shadow.
- **The shadow ramp is WRITTEN, not composited.** `pygame.draw` replaces pixels, so nested
  rings drawn outermost-first leave every point holding the alpha of the smallest ring that
  reaches it — the linear ramp. Compositing them as translucent layers accumulates
  (`1−(1−a)^n`) and saturates into a black edge wearing a gradient's construction.
- **The surface is pre-filled with the rim colour at zero alpha**, and its bounds are whole
  pixels. `smoothscale` does not premultiply, so opaque white against transparent *black*
  resolved to a half-grey — the "white" rim measured `(176,183,195)` against a
  `(213,223,239)` background, i.e. darker than what it sat on. And `int(w*ss)` disagreeing
  with `round(w)` made the 4× downscale really 3.94×.

**Sub-pixel placement lives in the image, not in the blit.** `int(round(cx + ox))` discards
up to half a pixel, and `ox` is the surface's own padding — so retuning the shadow walked the
whole marker off the bar by a row. The fractional part of the anchor is drawn into the
surface and only the whole part is a blit offset; the cache keys on it, quantised to the
supersample.

The mitred polygon offset this all rests on is `_offset_polygon`, module-level because the
continuity chevrons need it too.

### 9.3.3 Minute box and continuity chevrons — 2026-08-27

Measured together because the box is what the chevrons are spaced against (author: *"it's a
good anchor to our continuity arrows"*).

**The box is a fixed rectangle with a feathered edge, not a halo round the digits.** The
reference's two boxes carry a one-digit and a two-digit number — ink 20px and 42px native —
and their white measures 52 and 53. A halo could not do that.

| | value |
|---|---|
| box | 24.1 × 18.1, feather 1.7, corners **square**, centred on the bar |
| digits | size 17, ink 11.9 tall — reference 11.9; 8.5 wide for one digit against 8.5, 17.9 for two against 17.9 |

**Three digits are reachable, and the NUMBER gives, not the box** (author, 2026-08-28/29 — *"either
by compressing or lowering font size"*). Keihin from its own origin reaches 104 and 101, so this is
a real case rather than a guard. The run is squeezed horizontally into the measured box, which is
what this model already does to a long station name and what `docs/DISPLAY_E235.md` records as the
real PIDS's answer — a uniform horizontal squeeze, never a condensed cut. Widening the box instead
would put a wider one at a single station than at its neighbours, which reads as a mistake.

**The box never crosses its row's wall.** Centred on its slot it overhangs by 1.6px at a leaving
edge and 1.5px at the square origin, because the outermost slot sits closer to the end than the box
is wide. That overhang lands on background and its feather then eats the taper's outermost columns.
Only ever the outermost slot, and only by a pixel or two, so the box stays visually on its station.

**Sizes are 50% CROSSINGS, not a white-threshold bbox.** A `>240` bbox reports the solid
core and throws the ramp away — 22.4 × 16.0 here, 1.7px short on each axis. Feeding that back
in would shrink the box by the width of its own feather on every re-measurement. Drawn by the
upper LCD's `_build_soft_box`, the same builder the clock and the station-name plate use.

#### The unit label — 分

One at the LEFT end of each bar, which is where the row stops reading — the right end on a model
whose rows read left to right.

**It is fixed to the bar's end and never moves with the service** (author, 2026-08-28): E233-0
always draws it at the route bar's ends, whatever station this particular train terminates at. So
both rows carry one, permanently, and a train ending early does not gain, lose or relocate a 分.

**Anchored to the ROW'S OUTERMOST SLOT, not to the screen.** The reference puts its ink centre at
14.27 on row 2 and 14.91 on row 1 against one slot centre of 33.59 — the same 19px offset on both
rows, even though their walls differ by 16px. Screen-anchoring reproduces Chūō and then strands the
label in the background as soon as a shorter route centres its bar, or pushes it off-screen
entirely when a longer one shrinks its pitch.

**The 分 and the bar's length are two separate things** (author, 2026-08-28 — *"imagine the char
is happened to be there"*). The bar's extent is decided by the bar's own rules; the label is drawn
on top of whatever is there. It is not a 分-area the bar grows to accommodate, and reasoning the
other way round is what coupled the two and let a label nudge move the bar.

**Dark ink with a white outline on the bar** — the upper LCD's `outlined`, not a second implementation of it (author:
*"text, white outline maybe some feathering, like train type display"*). Core samples
`(5,0,3)`; the white peaks ~1.5px out and is gone by 3.

Placed by its **ink** box, not its font box: 分 sits high and narrow in its em, so putting the
font box where the ink was measured lands the glyph elsewhere. `get_bounding_rect` gives the
offset and `outlined` pads by a known `ceil(ow)`, so the position is arithmetic.

| | reference | ours |
|---|---|---|
| ink | 11.93 × 11.50 / 11.50 × 11.50 | 12.0 × 13.0 |
| ink centre x | 14.91 / 14.27 | 15.0 |

- OPEN — ours runs 1.5px taller, all of it at the bottom; the tops agree exactly. Size 14 is
  set from the WIDTH, and 13 would take that below the reference.

#### The two bar ends are padded differently

Measured at rows clear of the 分, on the two ends that terminate SQUARE — row 2's left, the
terminus, and row 1's right, the line's origin end. The other two carry the wrap's chevrons at
every row, so a bar edge cannot be separated from a chevron arm there at all.

| end | edge | against slot centre | pad |
|---|---|---|---|
| left | 5.16 | 33.59 | **28.43** |
| right | 616.3 | 605.3 | **11.00** |

**The left pad decomposes exactly, which is what confirms the measurement**: box half-width 12.05
+ a 1.1 gap + 分 11.7 + 3.6 to the edge = 28.45. That decomposition is a CHECK, not the rule — the
bar is not extended in order to carry the label (see § "The unit label" above). Ours started 15px
right of the measured edge, so the 分 hung off the bar (author, 2026-08-28: *"the end of route
color bar should be longer"*). Each end keeps its own measured pad; the values in the code are the
ones the author has accepted.

The right pad is the reference's 11.0 **plus 3**, because 11.0 is narrower than a minute box's
own half-width and the reference never has to hold one there — its outermost marks are narrow
passing arrows, and on row 1 slot 0 is a `pre_stop` that is always grey. `bar_x` **5.2**,
`bar_w` **614.1**.

#### The chevrons carry no outline — that was capture ringing

Three, w 13.8, stroke 3.0, pitch 5.97, full bar height, plain orange. An earlier pass profiled
across the group, found pale bands brighter than the background between the chevrons, and read
them as a white outline. **They are the 2.35× upscale's ringing.** At a plain
orange-to-background edge with nothing else near it the reference overshoots to `(238,211,205)`
— R above *both* endpoints while G and B fall — and across a 3px gap the overshoots from either
side meet and pile up. The tell was in the numbers: the peaks ran pink `(252,187,151)`, never
neutral, and a white outline cannot be pink. Author, 2026-08-28: *"your cont arrows should not
have that white shadow, what was that?"* Same artefact § 8.5 records for the plate's outline.

`cont_chev_out` = how many pitches the outermost sits beyond the bar's end. The reference runs
1 against its own shorter bar; lengthening the bar moved the group out with it and put the
outermost through the screen border, so it steps back to 0 (author: *"they should be closer"*).

### 9.3.4 The route bar's ends — SETTLED 2026-08-28

**The continuity marks are not their own element.** They are the bar's END TREATMENT and belong
to the bar's spec (author — *"the continuity arrows is a part of the route bar, shouldn't be
split anyway"*). Splitting them is what let the bar's length be retuned while the marks anchored
on it moved silently.

**One predicate per edge: does the route continue past it?** Whether the continuation is the
next row or the next frame makes no difference — it is the same claim, so it takes the same mark.
A square end is reserved for an edge where the route genuinely stops.

**One triangle, added at one edge and subtracted at the other.** The leaving edge adds it, so the
bar tapers out to a point. The arriving edge subtracts it — the same triangle cut into the end wall
in the background colour, apex pointing the direction of travel, so the bar ends in a V-shaped bite.
Chevrons then follow the taper at one edge and precede the wall at the other.

| edge | route continues? | the bar's own end | arrows |
|---|---|---|---|
| leaving | yes | the triangle ADDED — tapers to a point | chevrons behind it |
| arriving | yes | the triangle SUBTRACTED — a notch cut in | chevrons before it |
| start / end of the route | no | square | none |

**The structure above is cross-model; the numbers are not.** How many chevrons, their pitch, their
pointiness and their fatness are per-model (author, 2026-08-28) — **two on E233-0**, at both edges.
E235-1000 answers each of those differently and that is not a divergence to reconcile.

**An arriving edge needs a LONGER bar than a square one, so the bar's end is per-edge.** The notch
is cut INTO the bar, so it lands under the outermost station's minute box unless the wall stands
clear of it (author, 2026-08-28 — *"the subtracted triangle should clear the white box of the
station to the left of it"*). Slot 0's box reaches x 616.5, so the apex starts at 617 and the wall
sits 11 further out at `bar_arrive_x` 628. Row 1's right end is the line's ORIGIN, square, and keeps
its own measured 615 — one shared `bar_x + bar_w` would have grown 大月's end for the notch's sake.
That makes three different walls, which is why the geometry follows the edge KIND rather than the
row: `_row_edges`.

**Every wall snaps to a whole pixel before anything reads it, and that is load-bearing.** The bar
is a rect and ROUNDS its edge; `draw_aapolygon` TRUNCATES the triangle's. A wall derived as
`605.3 − 19×30.09 − 9.59` lands on 23.999999999999996, which rounds to 24 and truncates to 23 — so
the taper stopped one column short of the bar it grows out of, and the background between read as a
1px vertical gap (author, 2026-08-29 — *"the triangles is not touching with the route bar"*). It
appeared the moment the walls became derived pads; as integer literals the two roundings had nothing
to disagree about.

- Accepted with two chevrons: the outer tail reaches x 640 against the border at 639, so its last
  column sits under it. `cont_chev_n_arrive` drops this edge to one if that ever reads wrong.

**Direction is a property of the MODEL, not of the element.** One constant per model, read by
every directional mark on the display — the taper, the notch's apex, the continuity chevrons, the
passing-station arrows and the position marker's nose — so a fork cannot end up with one mark
disagreeing with the rest.

| model | rows read | every arrowhead points |
|---|---|---|
| E233-0 | right → left | left |
| E235-1000 | left → right | right |

Arrowheads never point outward from the bar and are never mirrored per end. The shapes are laid
out in **travel order** at both ends, so the eye follows the flow either way: leaving is
bar → taper → chevron → chevron, arriving is chevron → chevron → notch → bar. Only their position
relative to the bar changes, which is what makes the two ends read as departure and arrival rather
than as one shape drawn twice.

The taper-versus-notch asymmetry follows from that rather than from an IRL quirk: at a leaving edge
the bar is the thing departing, so it sharpens to a point; at an arriving edge the bar is entered
from behind, so its trailing edge is notched to receive the tip landing in it. Same shape E235-1000
draws at its slot 1 (`e235_1000/lower_lcd.py:751`), mirrored.

Chūō's four edges: row 1's left is leaving, row 2's right is arriving, and row 2's left (東京) and
row 1's right (大月) are square.

**The end shapes dim with the bar, because they are part of it** (author, 2026-08-28 — *"grey,
because it is A PART OF THE ROUTE BAR"*). Once the train is past the junction both its ends go
grey together; they are not separately coloured and they are not exempt from the passed/ahead
split the rest of the bar obeys.

**The nearest chevron's tip pokes INTO the notch** (author, 2026-08-28), so it nestles in the V
rather than stopping short of the wall. E235-1000 draws the chevrons over the notch in the bar's
own colour for exactly this — the tip reads as sitting inside the bite instead of vanishing into
the background that fills it.

**Spacing is measured between DRAWN EDGES, not between bounding boxes** (author, 2026-08-28). The
visible background margin from the notch to chevron 1 is the same as from chevron 1 to chevron 2,
and the tips overlap into the shape ahead to make that true — so the boxes overlap while the gaps
read uniform. Spacing the boxes evenly instead puts a wide margin at the notch and a narrow one
between the chevrons, which is what makes an otherwise-correct group look uneven. Same relation at
the leaving edge, between the taper and the chevrons behind it.

**On E233-0 that gap is about the chevron's own stroke** (author, 2026-08-28): picture the
identical chevron laid alongside in the background colour, so the negative space between two
chevrons is itself a chevron of the same thickness. That is the mental model for why the group
reads evenly — it is **not** a formula to enforce. The pitch stays an authored measurement, and the
value in the code is right (author: *"don't touch that, it looks good … sub-pixel level i can't see
either"*). The same gap separates the notch from the chevron beside it.

**Which edge faces the gap differs by treatment, so the first chevron's offset does too.** At a
LEAVING edge the triangle is solid and its leading slant faces the chevron's TRAILING slant, which
sits `stroke` behind the tip — so stepping a full pitch back leaves `pitch − stroke` of background.
At an ARRIVING edge the bar's boundary IS the notch's apex slant, and it faces the chevron's
LEADING slant at the tip itself — so a full pitch there leaves a whole pitch, twice the gap between
the chevrons. The first chevron starts at `pitch − stroke` instead, which puts both gaps on one
number (author, 2026-08-28 — *"you can push more the chevs into the notch"*). The two formulas are
not a special case; they are the same rule read off whichever slant is doing the facing.

**Pointiness is ONE property of the display, shared by everything with a point** (author,
2026-08-28) — the chevron tips, the leaving edge's taper, the arriving edge's notch, the passing-
station arrows and the position marker's nose all carry the same slant. It is not a per-shape
choice, and a shape that reads pointier or blunter than its neighbours is a defect rather than a
variation.

**And every one of them is the bar's own height** (author, 2026-08-28) — the chevrons, the taper's
triangle and the notch all stand exactly as tall as the route bar, 22. Nothing at an edge is
inset from it or proud of it.

That closes the depth: with one shared slant and one shared height, the notch and the taper are
the same triangle at the same size, and it is only added at one edge and subtracted at the other.
`cont_tri_w` 11 against a 22 bar is the chevron's `(w − stroke) : h` slant.
- OPEN — row 1's RIGHT end (大月). Square today, because the diagram starts there. The line itself
  runs west of 大月, so whether the real display treats that as the route ending or only as the
  drawing ending is unconfirmed.

### 9.3.5 When the train terminates before the line does — 2026-08-28

**A real case, not a hypothetical**: Chūō services sometimes end at 新宿 (author, 2026-08-28), and
the diagram is the LINE, so the bar is still drawn all the way to 東京 with the stations beyond the
service's last stop on it.

| | behaviour |
|---|---|
| bar past the train's terminus | **grey**, the same grey as behind the train — the line is drawn, this train does not go there |
| the 分 | does not move. It is fixed to the bar's ends and ignores the service (§ "The unit label") |
| the row's end arrow | still shown, provisionally — the line continues, so the edge's predicate still says yes |

The arrow half is the author's *"not sure, but you can treat it as a yes for now"* — taken as the
default because it follows from the end-treatment predicate being about the line, and flagged
because it is uncommon enough that no reference has shown it.

**The bar and the names above it are ONE thing** (author, 2026-08-28 — *"if route bar it's gray,
then station names should be gray as well"*). Grey bar ⇒ grey names, with no second rule to keep in
step. The implication runs one way only: an orange stretch can still carry grey names, because a
station the train passes through is greyed on its own account. So a name is black only where the
bar is orange AND the train stops there.

Nothing is drawn on the bar past the terminus — no box, no arrow, bare grey, the same as behind the
train. And **the destination station itself carries no special mark**: it is simply the last one
that still has a box and a number.

**The data mechanism already exists — it is Keihin 727B's** (author, 2026-08-28). That route's
`dest` is 磯子 at index 40 and its `stops` run on to 大船 at 45; the extra stations are ORDINARY
entries past the route-level destination, not a second list. So the diagram extends at the back
with plain stops and `dest_stop_idx` is what separates served from drawn — the mirror of `pre_stops`
at the front, using a mechanism that ships (`docs/DISPLAY.md` § Terminus).

- IMPLEMENTATION GAP — this renderer does not read the destination at all. `_draw_bars` splits only
  at the cursor, so a route whose stops continue past `dest` draws them orange. Everything above is
  specced; none of it is built.

### 9.3.6 The marker while the train is moving — 2026-08-28

**It sits BETWEEN stations, not parked on one** (author, 2026-08-28 — *"it sits in between, as the
case for all models, just e235-0 is more fancy with it"*). So the position marker is not a
station-cell decoration that hops; while the train is running it occupies the gap it is crossing.

**But not at the midpoint — the spacing does not allow it** (author, 2026-08-28 — *"i tell you place
in the middle, but spacing does not allow it, so itself it should clear the white box at the next
station"*). Half a pitch is 15.0 and the marker's nose reaches 9.4 ahead of its own centre, so the
midpoint puts the nose 5.6px INSIDE the box of the station being approached. The offset is therefore
DERIVED from what it has to clear — that box's half width, plus the nose's reach, plus a 1px gap —
rather than authored as a fraction of the leg, which also keeps it right when the box widens for a
three-digit number. It lands at 72% of the leg on Chūō, and is clamped inside the pitch so a
shrunken out-of-spec row cannot walk it onto the station behind.

One position serves both cases: at a passing station the mark is a narrow arrow, so the same offset
simply leaves about 8px more air (author — *"it should looks fine when next station is a passing
arrow"*). Reaching that frame needs `preview_display.py --skip N`, because `jump_to_stop` rolls a
passing index back to the nearest stopping station and no combination of `--stop` / `--pa` puts the
cursor on a station the train runs through.

**Skip is E235-1000's behaviour unchanged** (author): the marker walks station by station across
the stations run through, driven by `cursor_pos` lagging `curr_stop`, and lands in the middle of
each leg rather than jumping. That is the machinery this renderer already keys on
(`docs/DISPLAY.md` § "Station Skip Logic"), so nothing new is needed for it.

**The shape does NOT change** (author, 2026-08-28). E235-1000 swaps its pentagon for a chevron on
approach and E235-0 runs an arrow cascade; E233-0 does neither. One marker, one shape, and only its
position moves — so APPROACHING and STOPPING differ by where the pentagon sits, nothing else.

### 9.3.7 Layout for a route that is not Chūō — SETTLED 2026-08-29

Chūō's diagram is exactly the display's capacity: two rows of twenty. Everything else is one of
three cases, and they are decided by cell count alone.

| cells | layout |
|---|---|
| ≤ 20 | **ONE ROW**, centred, midway between the two measured row lines |
| 21 … 40 | two rows, `ceil(n/2)` each, bar **shortened and centred** |
| > 40 | two rows of twenty, **windowed** — first forty, then last forty |

**One row when one row fits** (author, 2026-08-29). Halving a 17-cell line into 9 + 8 draws a wrap
the diagram does not have, and the end treatment then claims a continuation at both halves of a
junction that is not there. Keiyō is the only shipped case. The row's y is **authored** — no E233-0
line is short enough to have a reference.

**Shorten and centre, don't stretch** (author, 2026-08-28 — *"for lines that has less than 40
stations, we should shorten the route bar and centers the route bar"*). The pitch is a fact about
the real display, so a short route draws a shorter bar rather than spacing its stations wider than
any E233 does. What is centred is the BAR, not the station group: the two differ by the wall pads,
which are not equal, so centring the group leaves the bar 3px off and its left wall outside the
border on the longest routes. One anchor serves both rows, so their columns stay aligned; a final
row holding fewer cells is simply shorter on the left.

**Windowing above the capacity is E235-1000's own long-route flip** (author, 2026-08-29), including
its `display_offset` branch — a route with an always-passed prefix holds the window at the start
until the train is forced off its right edge, instead of flipping at boot. Keihin-Tōhoku's 46 cells
are the case. **Row 1's right edge becomes an ARRIVING edge automatically** once the window does not
start at 0, because the end-treatment predicate asks about the whole diagram rather than the window
— no new case, which is what the author anticipated on 2026-08-28.

**Chūō is unaffected by all of it.** The measured anchor holds only when the row is exactly twenty
cells, and the four walls are expressed as pads from the outermost slot that reproduce the measured
absolutes exactly (33.59 − 28.59 = 5, 33.59 − 9.59 = 24, 605.3 + 9.70 = 615, 605.3 + 22.70 = 628).

### 9.4 Refinement order, and what is known wrong

Each is its own pass with the author:

1. ~~The bars and the wrap's continuity arrows~~ — **settled, §§ 9.3.3–9.3.4.** The end treatment
   is the bar's own, one predicate per edge, one triangle added or subtracted.
2. ~~The names~~ — **settled, § 9.3.1.**
3. ~~The minute box~~ — **§ 9.3.3.** The passing ARROW is signed off but never measured — the
   author put its residual down to the reference's own non-uniformity.
4. ~~The green pentagon~~ — **settled, §§ 9.3.2, 9.3.6.**
5. ~~**State behaviour**~~ — **settled, §§ 9.3.5–9.3.6**: approaching versus stopping, the skip
   animation, a service terminating before the line does. Click-to-jump is `docs/DISPLAY.md`'s
   cross-model `jump_to_stop` and needs nothing of this model's own.

6. ~~**Out-of-spec layout**~~ — **settled, § 9.3.7**: one row, shorten-and-centre, or window,
   by cell count.

**THE VIEW IS COMPLETE** (author, 2026-08-29 — *"everything about lower full route displays should
be complete"*). Verified across an 18-cell coverage sheet: both Chūō diagrams in every PA phase, at
boot, past the junction and at the terminus, mid-skip with the cursor on a run-through station, and
every other shipped line — Keihin either side of its window swap and at three-digit minutes, Sōbu
either side of 千葉, Yamanote, Nambu, Saikyō, Tōkaidō and Keiyō.

- OPEN — the **even-spread split** for a route between one row and the capacity is still the
  author's *"i am not sure"* from 2026-08-26. It renders and it is defensible; it has not been
  chosen over a strict twenty per row. `_per_row` is the one function to change.
- **Side effect worth knowing:** adding `pre_stops` to the two Chūō diagrams also changes how
  they render on E235, which is where they still land until the model field flips — eight more
  grey cells, and 40 cells crosses E235's 28-cell window threshold. Chūō on an E235 is
  out-of-spec anyway.

---

## 10. Lower LCD, 6-station view — BAR, NAMES, CODES, MARKS AND MARKER DONE

**Drill-down opened 2026-08-29.** § 10.1 is the author's and is settled; § 10.2 is what the
references measure; § 10.3 holds the per-element specs in the order they were settled.

Everything but the **transfer band** has been through the loop and accepted (author, 2026-08-29 —
*"i saw the overview. it's good"*). Verified two ways: an overlay against the takao reference, where
our slot pitch matches to five decimals (0.14754 W both) and the anchor to 0.35px; and an 18-cell
full-screen coverage sheet over every state, both junction sides and every shipped line.

Two OPENs remain, both parked by the author: the **far-end skip** (§ 10.1) and the **transfer band**
(§ 10.3.4), which is next.

### 10.1 What the view is

**Six cells, and the train's cell is the RIGHTMOST** — the rows read right to left, as the
full-route view's do. The window carries **one already-passed cell** behind the train, and a
`pre_stop` is eligible to be it (author, 2026-08-29). Near the end of the run the window
**locks to the last six** and the marker walks leftward inside it while passed cells accumulate
on the right. That is E235-1000's 8-station rule with `VISIBLE_COUNT` 6, mirrored — three
regimes, every one of them keyed on `cursor_pos` (`docs/DISPLAY.md` § "Position-locked views
always show the pointer"). All three references satisfy this exactly.

**The FURTHEST-AHEAD cell is a station the train STOPS at** — settled by the kokubunji reference
(author, 2026-08-29). Six consecutive cells would otherwise end on a run-through station and name no
reachable stop. The window still holds six; only the last one moves.

That capture is the case: its far cell jumps 武蔵小金井 JC-14 straight to **新宿 JC-05**, skipping
eight stations, and carries the true 33 minutes to 新宿 rather than a next-door number.

**The omission is marked by an S-shaped break in the bar**, at the midpoint between the jumped cell
and its neighbour. `[measured]` on that capture (1337 wide, scale 2.089): a ~3.4px slit whose left
edge walks cols 22 / 22 / 20 / 19 / 20 / 24 / 30 / 31 / 29 / 28 down the bar's height — one S,
leaning left in the upper half and right in the lower — centred at canvas ~134 against 新宿 at ~88
and 武蔵小金井 at ~182. Drawn as a strip of quads following a sine so the slit keeps a constant
width around the curve; a single polygon with two sine edges pinches at the steep part.

**The window is therefore NOT a consecutive range**, which is why every consumer reads its slot
position from `_cells()` rather than from an index offset.

**The bar is ONE LEFT-POINTING ARROW.** Its left end always tapers to a point and its right end
always runs flush off the screen edge, whatever is beyond either. This is **not** the full-route
view's end treatment: there the taper answers *does the route continue past this edge?*, here it
is the direction of travel and is drawn unconditionally (author, 2026-08-29). The ochanomizu
capture is the case that separates the two — 東京 is the end of the line *and* of the service and
the bar still tapers past it.

**The bar does not dim.** One colour end to end, whatever the train has passed (author). Only the
NAMES grey, and they grey on their own account at a station the train runs through. So the bar
reads identically either side of the marker, and the full-route view's orange/grey split has no
counterpart here.

**Elements:** the bar, with its arrow end and one `（分）` · vertical station names above it ·
the station code under each name · marks on the bar (minute box, passing chevron, position
marker) · the transfer band below it.

**The transfer band is IN SCOPE for this view** (author, 2026-08-29), which makes this the
session that answers § 3's shared-architecture question. Its entries and their order come from
the **existing** E235 path — `data/stations.json` `transfers` through `apply_transfer_filter`
with the route's `line_code` / `transfer_view` — and a non-JR operator's mark is whatever that
pipeline already resolves. Nothing new is authored.

### 10.2 Geometry `[measured]`

Off `6stations-takao-stopping-ja.png` (1084 × 812) by colour-run detection, same instrument as
§ 9.2 — `_dev_scripts/_e233_lower_geometry.py`, which takes the image as an argument so the
reference and our own render answer the identical question.

| | ratio | @640×480 |
|---|---|---|
| bar centre | y/H 0.6650 | 319 |
| bar height | h/H 0.0751 | 36 |
| bar left tip | x/W 0.0054 | 5.9 |
| bar right end | x/W 1.0000 | flush at the screen edge |
| slot pitch · slot 0 centre | from the minute boxes | 94.2 · 558.5 |
| name box | y 186.5 … 277 | 90.5 tall |
| code row | ink centre y 289.2 | 13.0 tall, 39.0 wide for `JC-21` |
| minute box | >240 core 28.9 × 24.2 | authored 31.4 × 26.3 |
| minute digit | ink 14.1 × 20.3 | size 30 |
| passing chevron | 11.3 × 19.8 | |
| marker body | 33.6 wide, full bar height | |

**Nothing scales from the full-route view.** Its bar is 22 and this one is 36 (×1.64), but the
minute box goes 22.4 → 31.4 (×1.40) and the chevron 8 → 11.3 (×1.41), and the marker is
proportionally much WIDER (w/h 0.93 here against 0.73 there) rather than bigger. Three different
factors and one changed shape — the two views are separately proportioned exactly as § 7 says.

**A white-threshold bbox under-reports a feathered box by its feather**, so the references' 28.9 ×
24.2 minute box is a solid CORE and not a geometric size (§ 9.3.3 records the same trap). The
tuneable is therefore sized so OUR core measures the reference's, with the same instrument asking
the identical question of both — authoring 29.0 × 24.1 directly rendered a core of 26.5 × 22.0,
short by exactly one feather on each axis.

### 10.3 Element specs

#### 10.3.1 The bar and its `（分）` — settled, not yet built

- **One left-pointing arrow**, per § 10.1. The taper is unconditional and the right end is flush.
- **`（分）` with parentheses**, one per bar, at the LEFT end — on the bar's **square part, right
  of the arrow**, and **bottom-aligned with the minute box's bottom** rather than centred on the
  bar (author, 2026-08-29). Note the parentheses: the full-route view draws a bare `分`.
- **WHITE and flat, with no outline**, and sized at **roughly half the minute box's height**
  (author, 2026-08-29). Not the full-route `分`'s construction: that one is dark ink carrying a
  white halo because it has to survive the bar's colour. The size is derived from the box rather
  than authored, so the two stay in proportion when the box is retuned.
- **The bar's length is the bar's own.** The label sits on whatever is there; the square part is
  not extended to carry it. Same relation § 9.3.3 records, and the same trap — reasoning the other
  way round is what let a label nudge move a bar.

#### 10.3.1a Station names — built

**The box is exactly THREE character slots, and a name grows ABOVE it rather than squeezing into
it.** `[measured]` per character on both references — a whole stack's ink extent cannot say this,
because a stack ending on a short glyph measures shorter at the same layout, so these are
centre-to-centre PITCHES:

| | pitch | |
|---|---|---|
| 立川 (2, takao) · 神田 (2, ocha) | 60.52 · 60.55 | the FIRST and LAST of three slots |
| 八王子 (3, takao) · 市ケ谷 (3, ocha) | 30.1 · 29.85 | fills all three |
| 西八王子 (4, takao) | 30.1 | the 3-char pitch KEPT, one slot above the box |
| 武蔵小金井 (5+) | compressed | into the same span as four |

`utils.draw_1col_text` executes all three regimes from one number, the span it is given — it
distributes into it and compresses only when the characters cannot fit. Ours reproduces the
reference: 2-char 60.5, 3-char 29.5/31.5, 4-char 29.5/29.5/31.5.

**Four characters keep their natural length** (author, 2026-08-29 — *"4 chars should be natural
length as well, nothing says station names should all same height"*), and **five and up compress
into the four-character extent** at that same pitch (author — 武蔵小金井 *"compress into 4 chars
spacing, but it's the 西八王子's pitch"*). So the stack has a ceiling of four slots and can never
reach the upper band — the extent tops out at ~158 against a lower area starting at 149 — which is
why no screen clamp is written: the cap is the rule, not a guard bolted onto it.

**The ochanomizu frame's 4-character name is set aside** (author — *"generally i don't understand
why as well, let's just forget about ochanomizu"*). 御茶ノ水 sets a 27.3 pitch, 9% tighter, and it
is not a crop artefact: the whole ochanomizu name band sits ~2.8px below takao's and correcting for
that leaves the compression untouched. Nothing found selects between the two — not
passing-versus-stopping, and not a kana in the name, since a kana changes nothing at three
characters (市ケ谷 sets the same 29.85 as the all-kanji 水道橋). Recorded so it is not re-derived.

**The name is the only thing carrying state on this view**, since the bar does not dim: grey
behind the train, grey at a station it runs through, grey past the service's terminus, black
otherwise.

**A compound name draws TWO columns**, right column first and raised, left hanging from the box's
bottom — the full-route view's treatment and E235's, i.e. this model's own norm. Dropping the space
and compressing instead crammed さいたま新都心's seven characters into one column, which the
coverage sheet showed at once. Chūō has no compound name; the case exists only on a borrowed route.

#### 10.3.2 The station code

`JC-19` — hyphenated and horizontal, under the name and above the bar, where the upper LCD's
badge stacks the same code without a hyphen and boxes it. **Drawn whenever the station HAS a code**,
greyed with the name.

**It is NOT gated on whether the train stops**, and the three references agree once the data is
read rather than the picture:

- ochanomizu shows nothing under 水道橋 / 飯田橋 / 市ケ谷 because those three carry
  `"sta_code": null` — the JC series numbers only 中央線快速 stations and they are 各駅停車-only.
- takao's train is 通勤特快, which **passes** 日野 / 豊田 / 西八王子, and it draws all three codes
  greyed. They hold JC20 / JC21 / JC23.
- yotsuya settles it: 新宿 is **behind** the train and shows **JC-05 greyed**, while its four
  JB-only neighbours show none.

So the earlier reading of the first two frames as a passing-station rule was wrong — they never
disagreed. The difference bites only on a diagram that runs through a JC-numbered station, which is
中央特快, where gating on `pa` would blank a code the reference plainly shows.
- The face is the JR signage one — a station code is the same artefact boxed or not, so it is not
  a per-view typeface choice (`conventions.md` § "Station-code badge typeface is fixed").
- OPEN — sized to the reference's cap height of 13.0, the run comes out **~14% wider** than the
  reference's. That is a FACE difference rather than a size one, and only the **Bold** cut of the
  signage face ships. Left as it stands rather than swapped for a Latin face that would fit the
  width and be the wrong typeface.

#### 10.3.3 Marks on the bar

**The mark says what KIND of station it is, and the number is content that may be absent** — a
white box where the train stops, a white left-pointing chevron where it runs through. So the box
is drawn **empty** at a stopping station BEHIND the train (author, 2026-08-29); past the service's
own terminus nothing is drawn on the bar at all.

- The yotsuya reference contradicts this and is a **reference error** (author, 2026-08-29): 通勤特快
  stops at 新宿, 新宿 sits behind the train there, and the frame draws it a chevron. Measured rather
  than eyeballed — at that capture's 1.4266 scale its slot 0 mark is 10.5 × 19.6 against the
  chevron's 11 × 20, while 四ツ谷's is 28.7 × 23.8, the box. Recorded so the frame is not read as
  evidence next time.

It **sits between two cells while the train is running** — the ochanomizu capture shows it between
飯田橋 and 市ケ谷 mid-leg, which is § 9.3.6's rule unchanged, and its offset is derived from the
approached station's box exactly as that section specifies.

**The marker is a different SHAPE, not a bigger pentagon** `[measured]`. Same five-vertex topology
as § 9.3.2's, and the shoulders sit in a different place: there they are near the centre so the nose
is most of the width, here they are far left, so the body is a long flat block with a short 7px
point. Green body x 538.5–575.7 (37.2) × y 303.2–333.3 (30.1), a right edge vertical on every row,
and the two slants meeting at y 318.2. **It is INSET from the bar** — 30 tall in a 36 bar, where the
full-route marker stands its bar's full height.

Its two tones are the model's rather than the view's: a vertical slice reads `(64,177,62)` above and
`(0,103,0)` below, the same pair the full-route marker carries, changing exactly on the anchor row.

**Out-of-spec routes re-tint the pair** (author, 2026-08-29 — *"it's a out of spec compatibility
thing, where it applies a contrast color on non in spec lines for better contrast like yamanote and
saikyo"*). The greens are the Chūō article and they read against the Chūō bar; on a route this model
is not stock for, the bar takes that route's own `color`, and a green marker on a green bar is what
the mechanism is for. `_marker_tones` gates on the LINE, not on the colour: an in-spec route is
never re-tinted whatever it declares, which is what keeps Chūō's accepted marker exactly `(0,103,0)`
rather than re-deriving to its own `contrast_color` of `(0,92,0)`. Off-spec, `contrast_color` becomes
the dark tone and the light one is derived by the lift the native pair already carries, read off the
tuneables so retuning the greens carries it. Both views get it — the construction is shared.

**Hue distance is the measure, and luminance actively misleads here.** Saikyō's bar scores a better
WCAG ratio against the marker than Chūō's own does (1.52 against 1.25) while looking far worse: it
sits 26.5° of hue away where Chūō sits 102°. Yamanote is the other one, 31.7°. The two the author
named are exactly the two the hue metric picks, and the two the luminance metric does not.

Stretching the full-route pentagon to the right bbox was tried first and reproduced the extent
without the shape — the overlay showed it as a wedge against a block, which no measurement of
width and height could have caught.

**The construction is shared, not forked.** `_marker_image`, `_box_width`, `_blit_box`,
`_blit_number` and `_arrow_left` take the VIEW'S marks dict as an argument and the 6-station class
binds the full-route ones as plain function attributes — one implementation of each, so a
supersampled rim or a three-digit squeeze cannot drift between the two views.

#### 10.3.4 The transfer band

Its list and order are the existing pipeline's (§ 10.1), and it is built.

**ONE ROW IS ONE LINE, and a line compresses only if the NEIGHBOURING station has a line at that
same row** — decided row by row, not for the block as a whole (author, 2026-08-29 — *"line
compresses itself if it touches the neighbouring stations transfer lists (IF IT EXISTS, and it is a
by row basis), if row 10 does not have neibouring it means it can just span naturally"*).

That is what makes only ONE of a wrapped shinkansen's two lines come out compressed, which the
author had noted before the rule was stated: the two lines sit at different depths and the
neighbour's list has usually run out by the lower one. A block-level rule cannot express it —
it would squeeze both lines or neither.

The references show the rule directly. At 東京 the rows run:

| row | extent | neighbour |
|---|---|---|
| 0–2 | 40.5 … **135.6** | 神田's column starts at **136.9** — they touch, so these compress |
| 3 | 42.6 … 114.3 | 神田 has only three entries, so nothing is there — natural |

**A column starts at its cell's LEFT edge**, measured twice: 東京's block at 42.2 against a cell
left of 43.6, 神田's at 136.9 against 136.4. So the room between two columns is exactly one cell.

`[measured]` band top **341.25** (4.25 below the bar), row pitch **14.07**. Takao's own block reads
15.35 and the overlay is what settled it — at 15.35 our 東京 block runs a row short of the
reference's nine. Line names are **near-black**, ink `(3,6,9)` / `(12,13,14)`; § 7's "line names in
blue" was an eyeball note and is wrong.

**Wrapping is not a width fallback — compression is.** A `･`-separated name wraps only when
squeezing it onto one row would fall below a floor, and it then splits at its MIDDLE separator.
That reproduces the reference exactly: 東海道･山陽新幹線 needs 0.94 and stays on one row, while
東北･山形･秋田･北海道･上越･北陸新幹線 needs 0.40 and cuts 3 + 3. A width-driven greedy cut put the
break a segment early and left the second line squeezed to nothing.

**Placement — TWO POSITIONS.** A block sits at a nominal anchor inset into its cell, and one too
wide for the room is pulled LEFT by its overrun, bounded (author, 2026-08-29). The sign of every
measured offset from the cell's left edge follows block WIDTH rather than entry count: 東京 (9
entries) −1.4, 神田 (3) −5.9, 御茶ノ水 (4, long names) −5.8, against 水道橋 (1) +6.7, 飯田橋 (4,
short) +14.0, 市ケ谷 (4, short) +15.9. 御茶ノ水 and 飯田橋 both hold four entries and land 20px
apart, because the first carries 中央・総武線（各駅停車）.

- The exact anchors are NOT measurable from these references: adjacent blocks ABUT — 東京's rows run
  right up to 神田's, which is what makes them compress — so a per-station window catches the
  neighbour's overflowing row and every number but 東京's is contaminated. Tuned by eye instead;
  `nominal_inset` / `max_shift` are the knobs.

**Vertical — the band hangs off the BAR and tightens when crowded.** `bar_gap` is clear px below
the bar's bottom edge, so retuning the bar carries the band rather than stranding it, and the
author's ask is that it almost touch. A station with a long list runs its last row into the screen's
bottom edge, and the whole band then pushes up a few px rather than clipping — one top for the
band, so adjacent stations' rows stay on shared lines, which is what makes the row-wise rule below
mean anything.

**A gutter, enforced PER ROW.** Two lists never touch; a row compresses to stop short of the
neighbour's row (`list_gap`). A row whose neighbour has nothing at that depth keeps its natural
width and needs no gutter — which is why the gutter belongs to the row bound, not to the block.

**Wrapping is not a width fallback — compression is.** A `･`-separated name wraps only when
squeezing it onto one row would fall below `min_squeeze`, and it then splits at its MIDDLE
separator. 東海道･山陽新幹線 needs 0.94 and stays on one row; 東北･山形･秋田･北海道･上越･北陸新幹線
needs 0.40 and cuts 3 + 3, which is the reference's own cut. A width-driven greedy cut put the break
a segment early and left the second line squeezed to nothing.

**A wrapped entry's two rows share ONE ratio** (author — *"if line 2 compresses, line 1 should
follow"*), computed before anything is drawn, since a row cannot know what its partner needs until
both are measured. Its continuation row carries no badge and indents to the TEXT column.

**The badge centres on the text's INK**, not on its font box — a box carries ascent and descent the
glyphs never reach, and they are not equal, so box-centring left the badge above the line the text
draws on. The same trap as the minute digits.

- OPEN — **八高線's badge**, a blank grey square on the standalone screen against an `HC` badge in
  the 6-station band. Deferred to a later data audit (author, 2026-08-29). It renders `_universal`
  today because no `HC` icon asset exists.
- The separator in `横須賀線・総武線快速` is the FULL-width `・`; the corpus reserves half-width `･`
  for shinkansen names. One character in `lines.json` if the reference says otherwise.

#### 10.3.5 A data gap the band exposes — 横須賀線･総武線快速

**The reference draws ONE entry where our data holds two.** At 東京 a Chūō train's band reads
`横須賀線・総武線快速` on a single row; `data/stations.json` lists `yokosuka_sobu.yokosuka` and
`yokosuka_sobu.sobu` separately, so we draw two rows — which also pushes 丸ノ内線 off the bottom.

**The current ops cannot express the collapse**, and this is the audit the author called for:

- `yokosuka_sobu` has **no base `name_ja`** — only the two variants — so there is nothing to
  reference for the combined form.
- `drop` matches by BASE slug, so it removes both entries, not one.
- `edit` is applied to EVERY entry whose base matches, so mapping the base to a combined ref would
  render that name **twice**.
- `add` only re-admits a ref already in `transfers[]`, and `docs/DATA_FORMAT.md` calls a
  `drop` + `add` of the same base dead config, since drop runs last.

The smallest fix is a combined variant plus **de-duplication after `edit`**: map both variants to
one ref and let the dedupe collapse them. That makes the existing op express it exactly and changes
no current behaviour, because no station today maps two entries onto the same ref. It needs
authored data either way, which is the author's call.

**A shinkansen's two-line wrap already has its mechanism and needs no data change.**
`data/lines.json` stores the name with half-width `･` (U+FF65) separators,
`docs/DATA_FORMAT.md` § "Punctuation in `name_ja`" names that codepoint as the wrap point, and
`e235_0/lower_lcd.py::_wrap_two_lines` is the working greedy split on it — the dot stays at the end
of line 1 and the cut position is a width TUNEABLE, not authored data, which is what pins the IRL
cut 東北･山形･秋田 ｜ 北海道･上越･北陸新幹線. The ochanomizu capture breaks in exactly that place.
It lives on E235-0's class today and wants lifting to a shared primitive rather than copying
(`conventions.md` § "Display module structure").

---

## 13. Open, carried forward

Neither is a defect; both are things a later capture or session settles. Kept here rather than as
issues (author, 2026-08-30) — an issue is an outcome, and these are conditions on work already done.

- **The shinkansen row's alignment is UNVERIFIED.** Every row now shares one left edge set by the
  widest row, which is E235's shape rule rather than a JC observation — no capture of `東京` or
  `上野` exists to check it against. § 11.3 carries the reasoning and the measured offsets the
  previous per-row centring produced; a capture of either station decides it.
- **English mode**, § 4 — the model's only remaining gap now that furigana has landed.
- **The E235 corpus row for `新宿` `JY_inner`** is marked re-verify in `docs/DISPLAY_E235.md`: its
  recorded `(3,3,3)` predates the JB rename and the grouping moved. Both E235 panels still lay out
  cleanly; only the recorded figure is stale.

---

## 12. The two standing notices — BUILT 2026-08-29

`優先席` and `マナーモード`, both static, both language-invariant, both on the same 3-beat dwell
(~12s) as FULL and EIGHT. Rarity is FREQUENCY, not duration: at most one joins the rotation and
only every third lap, alternating — so a notice about every 108s and each page about every 216s.
Appended at the lap's end, so the `at_station` force-switch still lands on TRANSFER.

**Both placards are DRAWN, not imported**, and `THIRD-PARTY.md` § "Renditions of signage designs"
records what that does and does not mean: no image file ships, but the underlying designs are
JR East's.

**The pictograms are TRACED CONTOURS, not a parametric body.** The first attempt built each figure
from a torso, a thigh, a shin and a per-figure attribute, and the fourth pictogram is where that
broke — an adult holding an infant is ONE fused silhouette, and the part model drew it as unrelated
blocks (author: *"completely bugged"*). The fix is the author's own suggestion, *"extract the
drawings using a color filter"*, done as `_e233_lower_geometry.py --trace`:

- **A COVERAGE FIELD, not a binary mask.** Each pixel's position along the white→blue axis, traced
  with marching squares at half coverage. A threshold is both too strict and too coarse, and those
  are one fault: it discards the antialiased rim, so shapes come out eroded, and it puts every
  vertex on an integer, so curves come out as staircases. Both were what the author saw.
- **Thin strokes need the coverage too.** A one-pixel stroke has no interior to a mask walk, so the
  cane, the crutch and every seat bar came back as hairlines. At coverage level they trace.
- **Holes come free, and are decided by WINDING.** The heart is a *white* shape inside the blue —
  invisible to a blue-only filter — and marching squares emits it as its own loop wound the other
  way. Keyed on the sign of the figure's LARGEST loop rather than on the algorithm's convention:
  screen-space y flips it, and assuming it rendered every body white and every hole blue.

Same call as this model's current-stop marker (`conventions.md` § "Display module structure"): a
fixed-orientation mark is a free vertex list, and the vertices ARE the shape.

---

## 11. Lower LCD, transfer view — BUILT

**Built and accepted 2026-08-29.** Every grouping the four references show is reproduced —
`八王子` `(1,1)` · `立川` `(1,1,1)` · `御茶ノ水` `(1,2)` · `新宿` `(2,2,2,3)` — and the reference
case matches within ~2px on every element. Spot-checked across the hardest station on all nine
other shipped routes (`東京` at ten entries with two shinkansen, `上野`, `武蔵小杉`, `新宿` on JA):
nothing overflows, wraps or clips.

**Drill-down held 2026-08-29.** § 11.1 is the author's. § 11.2 is what the one reference measures.
§ 11.3 is what one reference cannot say and what is therefore still open.

### 11.1 What the view is

A **standalone lower-LCD slot** showing one station's connecting lines as a **vertical list**: a
rounded blue banner reading `のりかえ / Transfer`, then one row per line — a square line badge, the
line name in kanji, and the English name beneath it.

It is the same data reaching the screen a third way, after the 6-station view's inline band. `八王子`
resolves through `apply_transfer_filter` to `横浜線 · 八高線`, which is exactly what the reference
draws, so this view needs **no data work** — only a renderer.

**It wraps into columns when the list is long — two normally, three where the station is
congested** (author, 2026-08-29). `新宿` on this line resolves to nine entries against `八王子`'s
two; the rows keep a readable size and the list wraps rather than paging. At the reference's 68px
pitch a single column holds three entries in the 331px lower region, so the wrap is not an edge
case on this line — it is the normal state at every interchange.

**The reference is not authoritative on the parts it cannot show, and E235's experience is**
(author, 2026-08-29: *"I think the ref is not always perfect. probably borrow experiences from
e235-1000 and 0"*). Two of its lessons carry, as experience rather than as code:

- **Fit on WIDTH as well as height, and step down when it does not.** E235's `name_size_ladder`
  keys on entry COUNT, which under-predicts width when a line name is long, so a low-N station
  can still overflow — `docs/DISPLAY_E235.md` records `秋葉原` rendering two names touching at
  620px against 618px of row. Ours must measure the laid-out block and step down a rung when it
  does not fit, rather than trusting a count.
- **Centre the block horizontally once it wraps.** E235's pipeline step 5 equalises the left and
  right gutters after placement. Measured at `新宿`, our two-column block runs `199`..`570` — a
  `199`px left gutter against `70` on the right — which is the same defect its centring exists to
  fix. The single-column case keeps the reference's measured left anchor; the wrap centres.

**What does not carry is the Rule 1–4 cascade**, which is horizontal-packing machinery for a wide
short region. See below.

**It rotates during approach and force-switches at the stop** (author, 2026-08-29: *"approach, and
full switch at the stop"*). That is `LowerDisplayBase`'s existing rule and needs no new mechanism:
the view takes its turn on the `ChangeScheduler` beat like the other two — which is why the
reference catches it under `つぎは` — and the rising edge of `at_station` switches to it at once,
bypassing the change floor. `docs/DISPLAY.md` § "Change scheduler" already classifies that
force-switch as Preemptive.

**E235 does not change** (author, 2026-08-29). Its horizontal panel with the Rule 1–4 column
cascade stays exactly as it is. This is the per-model native-norm rule doing its job in the
opposite direction from usual: E235 packs horizontally because its lower region is wide and short,
E233-0 stacks vertically because its own is 640 × 331, and neither borrows from the other. **Shared
*utilities* are welcome and shared *layout algorithms* are not** — `load_icon` already sits on
`displays/transfer_info.py` for exactly this reason, and a name-wrap or a badge-composition helper
can follow it; nothing from the cascade does.

### 11.2 Geometry `[measured]`

From `transfer-hachioji-ja.png` via `_dev_scripts/_e233_lower_geometry.py --transfer`, in 640 × 480
canvas units. That mode measures **what is not the background** rather than ink, because the banner
is a mid-blue pill whose luminance sits between the background and the text — no single ink
threshold finds both it and the rows.

| | value |
|---|---|
| banner box | x `184.9`..`445.7` (`260.8` wide), y `181.9`..`210.9` (`29.0` tall) |
| banner top, below the divide | `32.9` |
| banner centre x | `315.3` against a canvas centre of `320` |
| row 1 band | y `238.2`..`288.9` |
| row 2 band | y `307.2`..`356.6` |
| row pitch | `67.8` (JA ink top to JA ink top; band mids give `68.4`) |
| badge box | `49.9` wide (JH) · `46.4` (`_universal`) — both assets are 128 × 128, so the difference is padding inside the PNG, not layout |
| text left edge | `246.0` |
| JA ink height | `31.5`, identical on both rows |
| EN ink height | `14.5`, identical on both rows |
| JA → EN step | `26.0`, identical on both rows |

The per-row figures agreeing to the pixel across both rows is the useful part: the row is a fixed
block, not something that sizes to its own content.

`八高線` takes a plain grey square because it carries no line code — the `_universal` fallback,
which is what IRL draws too, and the author has confirmed keeping it (2026-08-29).

### 11.3 What the reference cannot say

**It has two entries.** Everything the wrap turns on — where the threshold sits, whether the fill
is column-major or row-major, how an odd count splits, whether the pitch survives the wrap — is
invisible in it. The author has ruled that the reference does not get to decide those (§ 11.1), so
they are settled by the author and by the geometry: **row-major** — the list fills across a row and
then drops to the next (author, 2026-08-29: *"fill the row first"*), so `新宿`'s nine entries make
five rows of two rather than columns of five; **largest rung that fits**, measured on the real
laid-out block; **centred once it wraps**.

**A trailing row of ONE folds into the row above it, and its third entry overhangs.** `新宿` on JC
is `(2,2,2,3)` with the last row's third sticking out past the two-column grid (author,
2026-08-29). It is a FITTING device, not a style: nine entries pair into `(2,2,2,2,1)` — five rows,
which no rung holds at a readable size — and folding the orphan gives four, which rung 1 does. So
the fold is gated on the list being at least four rows tall, which is why `新宿`'s nine fold and
`武蔵小杉`'s five keep their orphan at `(2,2,1)`. **A block with an overhang anchors LEFT rather
than centring** — the reference starts its list hard against the left margin, and centring the grid
pushes the sticking-out entry off the right edge. The overhang is also excluded from the block's
measured width, which is what "sticks out" means; measuring it in is what rejected `(2,2,2,3)` at
every rung.

**ONE LEFT EDGE FOR EVERY ROW, and the WIDEST row sets the page width — E235's shape rule, ported
2026-08-30** (author: *"find overall rule of shape from e235 transfers, that is well tuned, just
that for e233 max cols are 3, and spaces are a bit different, plus its shape should originates from
in-spec chuo route"*). E235 states the principle in its column-system blueprint
(`e235_1000/transfer_info.py:756`): *"justifying is right whenever the anchor row is the TOP row: it
is then the widest row by construction, so it defines the page width and nothing can stick out past
it."* So every row — solo, paired or shinkansen — anchors on one left edge, which is what makes a
badge column uniform down the block. What does NOT come across is the Rule 1–4 cascade (§ 11.1);
this is the *shape*, and the numbers stay E233-0's own.

Two exceptions, both from the in-spec references rather than from E235: a **single column** sits at
the measured `col0_x` (`transfer-hachioji-ja.png`) rather than centring, yielding only when a row
would not fit beside it; and a block with an **overhang** anchors at `side_pad`, because centring
the grid pushes the sticking-out entry off the right edge.

**What this replaced, and why the old rule looked reasonable.** The shinkansen row was centred on
the canvas and the grid was centred on the canvas *independently*, so their badge columns agreed
only by coincidence — the offset is exactly `|grid_w − shink_w| / 2`. On top sat a
`len(shink_rows) >= 2` gate. That count was a **proxy for "is the grid at least as wide as the
shinkansen row"**: with two shinkansen the block is 3-column or wide, so the grid wins and sharing
an edge is nearly free (measured 2–41px across `東京` on five views). With one it never wins — the
shinkansen is the wider row in every case in the corpus — and the columns sat up to **174px** apart
(`宇都宮` at `宇都宮`: a 153px grid against a 501px shinkansen row). Measured by
`_dev_scripts/_e233_transfer_cases.py`, which drives the production `_layout`.

The out-of-spec cost is real and accepted: a 564px shinkansen row on a 612px usable width forces
any shared edge left, so a two-entry grid beside it keeps ~200px of right margin. Aligned and
left-heavy is the trade E235 already makes — its `anchor_overhang_trim` exists to bound the same
effect, and it never breaks the shared edge to fix it.

In-spec is untouched but for `東京`, whose block moves 21px left onto its shinkansen's badge column.
**UNVERIFIED** — there is still no JC capture of `東京` or `上野`, so this is judgement rather than
fidelity and a capture could overturn it.

**A wide shinkansen does NOT wrap to two lines — measured, not assumed.** The mechanism is built
and off (`shink_wrap_block`), because the condition the author set for it never occurs here: *"wrap
effect is not so good. i think generally when the shinkansen is a small size like in those dense
station, it's better"* (2026-08-30). Every station where the shinkansen is the widest row — 上野
JU/JY, 大宮 JU/JA, 品川 JY/JK/JT, 小山, 宇都宮 — sits at rung 0.84 or 1.0, the large end; at every
dense station (0.71, 0.6) the grid is already wider and there is nothing to wrap. Gated on the small
rungs, exactly one case fired — 宇都宮 東京 — and it fell 0.71 → 0.6, because the second line costs a
row and the row broke the cap. So the residual right margin beside a 564px name on a 612px canvas
stands, which is the trade E235 also makes: its `anchor_overhang_trim` bounds that effect and never
breaks the shared edge to fix it.

**A LONG NAME TAKES A ROW TO ITSELF — but the row YIELDS when keeping it would cost a column.**
E235 reaches its groupings by trying and repairing rather than from an absolute table
(`docs/DISPLAY_E235.md` § Pipeline step 2, "greedy walk + cascade dry-run"), and that is the shape
this view now uses: the strict form is tried first at every column count, and only where it does not
place may the long row pair. A shinkansen is never relaxed — its own row is the `category` treatment
E235 gives it, not a width judgement.

`上野` on JY is the case (author, 2026-08-30: *"JU utsu and JU takasaki can be one 1 row?"*).
`宇都宮線(東北線)` measures 266px against the 245px bar, clearing it by 21 — so it took a row, which
made seven entries need five rows against a cap of four, which sent the station to THREE columns.
Paired with `高崎線` (139) the row is 420px inside 612 and it places in two. The same relaxation
improved `赤羽` on JK and JA (both to `(2,2)` a rung larger) and `上野` on JK (`(1,3,3,2)` at 0.84
rather than five rows at 0.71). In-spec Chūō is unchanged at all fourteen stations.

Moving the threshold instead would have been wrong: at a common scale `宇都宮線(東北線)` is ~317px
against `青梅・五日市線`'s reference-confirmed 285, so by the length rule it *is* long. Worth knowing
for any later retune — the bar compares a **rung-scaled** width against a **fixed** fraction of the
canvas, so `中央線各駅停車` counts as long at rung 1.0 (285) and would not at 0.84 (239). Left as it
is, since normalising it makes more entries solo, not fewer.

**The rule the pairing falls out of:** The author's rule
(2026-08-29: *"when the line got a very long transfer name, it has it's own row"*), and the
references draw it: `transfer-ocha-ja.png` is `(1,2)` — `中央・総武線(各駅停車)` alone above
`丸ノ内線` | `千代田線` — and `transfer-tachikawa-ja.png` is `(1,1,1)`, where `南武線` is short and
still ends up alone because both its neighbours are long. So this is a per-ENTRY property, not a
per-N grouping table, and the tempting reading — E235's *"N=3: always (2,1)"* — is wrong here.

Measured as a fraction of the usable width rather than a glyph count, so a two-badge group or a
long English name counts toward it. The references bracket the threshold: `中央・総武線(各駅停車)`
is 450px and alone, `青梅・五日市線` and `多摩モノレール` are 285px and alone, `丸ノ内線` is 186px
and pairs. `long_row_frac` 0.40 of 612 is 245, between the two.

**N = 2 never pairs**, per `transfer-hachioji-ja.png`, which stacks `横浜線` over `八高線` with room
to spare either side. That is where this model parts from E235, which pairs N=2 when the widths
allow.

**No unconditional parenthetical break in this view** (author, 2026-08-29: *"so maybe no need to
split to 2 lines"*). The 6-station band puts `（各駅停車）` on its own line because its columns are
one station wide; `transfer-ocha-ja.png` draws `中央・総武線(各駅停車)` on ONE line and gives the
entry a row to itself instead. Same name, two views, two answers — because the two views have
different room.

**And the JB is named a fourth way again.** `transfer-shinjuku.png` reads `中央線各駅停車` /
`Chūō Line ( Local )` where `6stations-kokubunji-ja.png` reads `中央・総武線` and this view's other
stations read `中央・総武線（各駅停車）`. Confirmed by the author and carried as a `JC_up` edit to a
`sobu_local.chuo_local` variant — data, not code, which is what `transfers_by_view` is for. The
same reference also orders `山手線` ahead of it, against the author's stated JB-JY-JA order; the
author's word outranks the photograph, so the `order` op stands.

**It is captured in the hiragana mode** (`つぎは` / `はちおうじ`), where `6stations-kokubunji-ja.png`
is kanji (`次は` / `国分寺`). Furigana is deferred by § 4, so this reference's upper band is not
reproducible today. It does not touch the lower view — but it does mean the reference cannot say
whether the list itself changes between modes, and the working assumption stays § 4's: all three
modes render the kanji renderer, and this list carries both scripts in every mode because the
banner and every row do so in the only capture there is.

**A shinkansen entry takes a row to itself, exactly as on E235** (author, 2026-08-29: *"about
tokyo, same treatment as E235, shinkansen in it's separate line?"*). Driven by the same data field
E235 reads — `category == "shinkansen"` in `data/lines.json` — so neither model matches on the
name, and a line reclassified in the data moves on both.

`東京` is what forces it. Its nine entries include `東北･山形･秋田･北海道･上越･北陸新幹線`, which
overflows the canvas at every rung of the ladder, so a row-major grid ran the block off both edges
however far it shrank. Given a full row it fits, and where it still does not it **wraps onto two
lines**: at the half-width `･` for the Japanese (`docs/DATA_FORMAT.md` § "Punctuation in
`name_ja`" names that codepoint as the wrap point), at `（` with the bracket carried to line 2 so a
parenthetical qualifier stays whole, and at a space for the English.

**Shrink before you wrap, and never break mid-word.** A two-line entry beside one-line neighbours
reads loose, so a candidate layout that needs a wrap is held and the search continues down the
ladder — `中央・総武線（各駅停車）` overran a column by a few pixels at the top rung and one rung
down it fits whole. And a name offering none of the three separators can only be cut mid-word,
which `上野東京ライン` showed as `上野東京ラ` / `イン` at three columns: that disqualifies the
candidate outright rather than being drawn, which is what sends the search to a wider column at a
smaller size.

**Columns size to their content, so the wrap test is not `width / cols`.** Asking each entry to fit
an equal share is a stricter question than the layout actually answers — `御茶ノ水` shrank two rungs
on that test with 168px still free, because `中央・総武線（各駅停車）` overran half the canvas while
the pair `中央・総武線（各駅停車）` + `丸ノ内線` did not. The fit therefore wraps only what cannot
fit the WHOLE width, measures the real columns, and falls back to the equal share only when that
genuinely overflows. With all of the above in place **no station on this line or on any of the six
out-of-spec routes reaches a wrap** — the mechanism is still needed, because it is what the search
is choosing between.

That makes `e235_0/lower_lcd.py::_wrap_two_lines` the third caller of one greedy `･` split, which
is the lift § 10.3.5 already asked for: it moves to `displays/transfer_info.py` as
`wrap_two_lines`. A shared *utility*, which the author has blessed; the Rule 1–4 cascade is what
stays put.
- OPEN — a multi-badge entry (`湘南新宿ライン` draws `JT`+`JU` in the inline band). No capture shows
  one in this view, and the author has separately said that reference is wrong on it — it should be
  `JS` (2026-08-29).

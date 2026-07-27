# WIP — Pre-rendered font atlas (drop proprietary font software from the ship)

**Tracking:** not yet filed. Outcome is user-visible (the shipped build stops carrying font
software), so it wants a parent issue + stages rather than a `Refs`-only ticket.

**Status:** design only, nothing built. Feasibility measured 2026-07-27 — see § Measured.
Sequenced after the licensing work (`LICENSE` / `THIRD-PARTY.md`, landed 2026-07-27).

---

## EDIT-CONTRACT

- **Holds:** the design, the measured numbers it rests on, the rejected alternatives, and the
  gate the approach requires. Transitional notes while in flight.
- **Does NOT hold:** anything already true of shipped code — that belongs in
  `conventions.md § Tooling` (font rules) and `/build`. Measurements that stop being
  decision-relevant get cut, not archived.
- **Graduation trigger:** when the atlas is the shipped path and the proprietary faces are out
  of the tracked tree, dissolve into `conventions.md § Tooling` (replacing the "TIMS chrome
  text" / font-loading rules where they change) + `/build` (the generation step) and delete
  this doc.

---

## Why

Two drivers, either sufficient on its own.

**Licensing.** `fonts/` holds three commercial faces — `ShinGoPr6N` (Light/Medium/Heavy,
Morisawa), `HelveticaNeue` (Roman/Medium/Bold) and `NeueFrutigerWorld-Bold` (Monotype), 17.0 MB
across 7 files. A licence was bought for the ShinGo but does not extend to redistribution, and
the ~629 MB release zip ships all seven. Copyright protects font **software** — the outlines and
hinting as a program — not the typeface **design**, which is unprotected in the US and sits below
Japan's high bar for logos and applied art. So shipping the `.otf` redistributes the protected
artifact and is hash-identifiable; shipping raster glyphs of the same design is a materially
different act with nothing matchable in it. History is not being rewritten (decided
2026-07-27) — this is a forward-clean measure.

**Engineering, independent of the above:**

- **Pixel determinism.** Fidelity currently depends on the end user's SDL_ttf/freetype hinting
  and AA matching the dev box. A version bump can move a stroke on a machine we never see, and
  there is no test for it. A baked atlas ships the calibrated pixels.
- **Removes a live crash class.** All 76 call sites are bare `pygame.font.Font(path)` with no
  existence check — a mis-staged `fonts/` is an unhandled exception, the `critical_lessons.md §4`
  deployment-frame mode.
- No `SysFont` path can ever regress back in for these faces (`conventions.md § Tooling`).
- **−17.0 MB shipped**, plus no 17 MB CJK parse at startup.

---

## Measured (2026-07-27)

Method: monkeypatch `pygame.font.Font` to record `(filename, size)`, run `preview_display.py`
headless across the matrix, accumulate. Throwaway probe, not a committed harness.

**43 distinct (face, size) pairs, and the set is CLOSED.** Invariant across 2 models × 3 modes ×
3 lower-views, then 5 routes (`sobu/1217F`, `yamanote`, `chuo/1654T`, `keihin/1275A`,
`_mock/main`) × 4 stops. Cumulative never moved off 43 — nothing sizes itself off content.

| Face | n | Sizes |
|---|---|---|
| `ShinGoPr6N-Medium` | 14 | 9 10 11 14 18 19 25 26 30 35 40 42 78 84 |
| `ShinGoPr6N-Heavy` | 2 | 19 26 |
| `HelveticaNeue-Bold` | 11 | 11 14 15 17 21 22 31 42 68 75 88 |
| `HelveticaNeue-Medium` | 5 | 9 20 24 27 28 |
| `HelveticaNeue-Roman` | 2 | 27 31 |
| `NeueFrutigerWorld-Bold` | 9 | 8 11 13 14 15 17 18 20 22 |

**849 unique characters across all committed data** (`data/*.json` + every `audio/**/route.json`):
643 kanji, 65 hiragana, 37 katakana, 83 ASCII, 21 other.

So the atlas is ~16k glyph bitmaps (ShinGo 16 pairs × ~849, Helvetica 18 × ~110, Frutiger 9 ×
~40) — single-digit MB packed as alpha PNGs, i.e. **smaller than the fonts it replaces**.

**Glyph coverage is not a constraint anywhere.** Every bundled face, including the Noto subsets,
renders the full 41-char station-kanji/kana probe plus Latin and digits (checked via
`Font.metrics()` returning non-None).

**Call sites: 76 across 9 files** — `e235_1000/lower_lcd.py` 16, `e235_0/lower_lcd.py` 14,
`e235_1000/upper_lcd.py` 13, `e235_0/upper_lcd.py` 11, `e235_1000/transfer_info.py` 7,
`setup.py` 6, `i18n.py` 5, `displays/utils.py` 3, `tutorial.py` 1.

**Not probed:** `setup.py`, `tutorial.py`, the `auto_input/driver.py` debug panel. Latin chrome
mostly, and TIMS chrome is already Noto. Treat 43 as the LCD floor plus a handful, not a
different order of magnitude.

---

## Design

**Generate at build time from the local licensed fonts. Dev keeps rendering live.**

The `.otf` files stay on the dev machine, gitignored. `preview_display.py`, the calibration
editor and every dev run load them as today, so tuneable font sizes remain discoverable AND
reactive (`conventions.md § UI code style`) and the calibration loop is untouched. Only the
shipped artifact is pre-rendered. The repo carries neither the fonts nor the atlas — the atlas
is build output, so nothing derivative enters the tree either.

**One funnel.** `text_font(role, size)` returns either a real `pygame.font.Font` (dev) or an
atlas-backed shim duck-typing enough of the `Font` API that call sites cannot tell. The 76 sites
change once, mechanically, and never again. This funnel is the enabling refactor regardless of
which direction the font question ultimately goes.

**Scope: proprietary faces only.** Noto is OFL and free to ship; leaving chrome on live font
rendering keeps i18n flexible. Bake ShinGo, Helvetica Neue, Frutiger.

**Known cost.** Per-glyph blitting loses kerning and shaping. Near-invisible for Japanese
(roughly uniform advances); Helvetica Neue does kern, so Latin runs will not be pixel-identical
unless kerning pairs are baked into the advance table. Wants a side-by-side before commitment.

---

## The gate this approach requires

A frozen atlas introduces two failures that are invisible in dev and only appear in the shipped
build — this project's recurring silent-drift class, so it needs a mechanical gate, not
discipline:

1. A font size is retuned and the atlas is not regenerated → no atlas entry for that size.
2. A new route adds a station whose kanji is outside the 849 → tofu in the exe, correct in dev.

Gate: `/build` regenerates unconditionally, plus a build-time check that every (face, size) the
code requests and every character the committed data contains exists in the atlas manifest.
Same tier as `check_deps.py` (`conventions.md § Tooling`, automated sensor tiers).

---

## Rejected

- **Substitute open fonts in the public build.** No open ShinGo analogue exists; Noto Sans JP and
  Source Han Sans do not read as ShinGo, and station names are the most prominent element on the
  upper LCD. Also fights `conventions.md`'s fixed-badge-typeface rule, which exists because a
  wrong face already shipped once. Helvetica Neue would have been easy (Nimbus Sans is
  metric-compatible); the Japanese face is what kills it.
- **Ship the fonts and rely on the repo being small.** The release zip is the larger exposure,
  not the tree; removing from `git` while continuing to ship the zip fixes the scannable half
  only.
- **Tell users to obtain the fonts themselves.** Morisawa sells by subscription, so this is not a
  path a hobbyist user can walk, and all 76 sites are unguarded — absence is a crash, not
  degradation.
- **Pre-render whole strings rather than glyphs.** Preserves kerning perfectly but explodes
  combinatorially across sizes, and the long tail (numbers, 3-locale chrome, debug panels) has no
  closed enumeration the way the glyph set does.

---

## Open

- **`/third-man` on the shim interface** before touching 76 sites — offered, not yet taken. The
  question worth a second opinion: how much of the `pygame.font.Font` surface the shim must
  implement. Call sites are known to use `render`, `size`, `get_height`, `get_ascent` and
  `metrics`; needs a survey rather than a guess, since a missing method fails at a render path
  that may not be exercised in dev.
- Whether the atlas ships as one packed sheet per (face, size) or one sheet per face with a
  size-indexed offset table.
- Kerning: bake pairs into the advance table, or accept the Latin difference.

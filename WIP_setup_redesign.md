# WIP: Setup Screen Redesign (TIMS-style)

In-flight redesign of the setup / home screen to the JR East TIMS cab-console look (glossy
raised-bevel blue buttons + low-res pixel text). Draft: `_dev_scripts/setup_redesign_draft.py`;
primitives: `_dev_scripts/button_style_sandbox.py` (+ `_test_button_primitive.py`). This doc holds the
design + decisions until graduation, then dissolves into canonical homes.

## EDIT-CONTRACT
- **Holds:** page layout, the press / transition model, the font decision, the graduation plan.
- **Refuse:** blow-by-blow iteration history (git has it), render screenshots, render-tuning numbers.
- **Dissolves when:** `setup.py` adopts the design AND the primitives graduate to a chrome `widgets.py`.

## Page 1 layout (730×610 — setup is its OWN window, taller than the 420 LCD frame, free to size)
- **Language knobs**, top-right: 3 square buttons, content-tight 2×2 CJK self-name + a margin off the
  bevel (EN stays a short code). All rest in **default state — yellow = PRESSED (momentary), NOT a
  selected/active indicator.** Pressing one switches chrome language.
- **Action cards**, centered: 4 **flush** (no-gap) taller cards — Route Selection / Tutorial /
  Settings / Driving Record. Sized so 3–4 fit side by side (the eventual layout); text pinned k=2 so
  it stays crisp. Settings + Driving Record are clickable **placeholders** (no behavior yet).
  **Tutorial** opens the tutorial screen (below) AND is the **OOBE hook**: while `oobe_completed` is
  False, the Tutorial card **flashes** to hint a click; the first click stops the flash + sets the
  flag. Replaces the old forced first-run fullscreen tutorial — the OOBE trigger is now just the flash.
- **Version**, bottom-left: `Version ０５４` — word label + dot-stripped full-width numerals (no
  `v` / dots / colon), TIMS off-white.
- Later: page 2 + page nav (not designed yet).

## Persistent top band (= the OCR debug panel)
Full-width (730px = main-app / setup width) near-black status strip, **persistent across all screens**
(home, route-selection, …). It IS the OCR debug panel — the running app already carves a 730×
`DEBUG_PANEL_HEIGHT` top strip when auto-input is on; this band graduates into that (draft height is a
free choice, reconciles with `DEBUG_PANEL_HEIGHT` at graduation). Draft:
`setup_redesign_draft._render_topband`. Mirrors the real TIMS top register; everything **except station
names is i18n** (develop/preview in **zh_HK**).

Layout, left→right:
- **Left column (small, crisp k=1)** — green katakana notification + the OCR **state**: segment
  `from → to` (station names, JP) · inferred Layer-3 state word · played `N/M`. **Badge (Layer-2 raw
  read: STOPPED/MOVING/PASSING/UNKNOWN) is grouped HERE with the state.**
- **Centre readout cell** (right-aligned, between separators) — speed limit / speed / **distance
  (ALWAYS metres** — OCR reads m; finer than rounded km). **Wide TIMS numerals** (`draw_lowres_number`).
  Speed limit is **plain until it CHANGES, then flashes cyan a few seconds and settles** (change cue,
  not a permanent highlight).
- **Message strips (centre-right)** — the original TIMS **two dim bars** = message displays. House the
  OCR **fire event**, **stopping-position** reading, **re-aligning** signal, paused/frozen-OCR, etc.
  **Message text = bright YELLOW, flashing, auto-clears after a while** (per IRL recollection — to
  confirm against reference).
- **Right control cluster** — `[pause] [save-record] [home]`, **uniform square** TIMS buttons (all
  content-sized to the home label). Home always rightmost (return-to-home, persistent). Pause +
  save-record are the migrated debug-panel controls (save-record = the old Report / driving-record
  download).

**OCR-panel migration — grand-check decisions (vs old `auto_input/driver.py draw_debug_panel`):**
- **Confidence colour DROPPED** (the green/yellow/red OCR-score tint) — too debug for the public band.
- **Badge → grouped with the state** (above).
- **Re-aligning + paused-frozen → message-strip entries** (yellow flashing).
- Likely-dropped debug detail: `badge_diff`, raw `_score` numbers, the literal "OCR" label.
- Carried: pause, save-record(Report), inferred state, segment, played `N/M`, speed, limit, distance,
  stopping position, auto-played fire chip.
- **DONE:** `_render_topband` is **status-driven** (`status` / `sim_state` / `stops`, auto_input shape)
  + wired into `_dev_scripts/preview_band_ocr.py` (reuses `preview_debug_panel`'s mock scenarios; under
  `_dev_scripts/` so it may import the draft band — a root preview would trip the `_*/`-import linter).
  Implements badge-with-state, yellow flashing/auto-clearing message strips, pause-lights-when-paused.
  Still placeholder-ish: i18n state words (draft `_STATE_WORDS`), limit cyan-flash-on-change (only fires
  in placeholder mode), exact yellow/flash timing.

## Route selection flow (confirmed)
**route → diagram → pick station.** Mimic the **real TIMS route-selection screens** (we have reference
photos → can hit the fidelity bar) rather than reskin an invented screen, but **back them with existing
`route.json`** (no per-line bespoke logic). Diagram list = the diagrams a route's data supports;
**destinations + train types are fixed** (from the data). Reference: `tims-route-selection.jpg`.

## Font decision — Ark Pixel 12px MONOSPACED, per-locale, ONE build
- **IRL TIMS is monospaced**, so the whole chrome uses the **monospaced** Ark build (latin / zh_hk /
  zh_cn), dispatched per-locale via `i18n.pixel_font_for_lang(lang, native)` (sibling of
  `font_for_lang`). CJK is full-width either way; mono also gives Latin + numerals uniform TIMS cells.
  Numerals go through `draw_lowres_number` (see recipe below), NOT full-width forms.
- **TIMS numeral recipe (REUSABLE — version, train numbers, diagram codes, clocks):** `draw_lowres_number`
  — each glyph **trimmed to its ink** (drops the cell side-bearings) + an **explicit gap**, with digit
  **width (`xscale`) and gap independent**. TIMS digits read **wider than half-width but not full-width**;
  `xscale` widens, `gap` spaces (may be negative). *Rejected: full-width forms (U+FFxx) + whole-render
  squeeze — full-width centers each digit in a fat em cell, and squeezing scales the GAP down with the
  glyph so it never closes. Trimming removes the side-bearings outright, which is the real fix.*
- **NOT a single face** — Han-unification needs per-locale files. *Supersedes the "single face" claim
  in `TODO.md` (reconcile at graduation step 6).*
- **MS Gothic = the gold-standard look, but NON-SHIPPABLE** (reference bar only, confirmed 2026-06-26):
  Microsoft system font, non-redistributable (license) AND JIS-only (no Simplified — tofus 简; Ark
  resolves Simplified). **Why it wins = embedded bitmap STRIKES** (EBDT/EBLC): it ships ~13 hand-tuned
  bitmaps, one per px **10–22** (crisp + size-growing detail at each), then smooth outline from 23px up.
  Ark has ZERO strikes — a single 12px outline design — so 14–22px is the 12px shape RESCALED with no
  added strokes, and supersampling can't add detail never drawn. So "Ark looks worse than MS Gothic" is
  STRUCTURAL: the whole 16–22px band (readout @18, button labels @16) gets strike-detail Ark physically
  can't produce. The free-font goal is therefore a **multi-strike bitmap face**, not just "more kanji."
- **Pixel detail is bounded by the DESIGN GRID, not the render size** (*supersedes the earlier "crisp at
  k=2 / keep small" framing AND the `conventions.md` "k=2 ceiling" rule — revise at graduation*). Per
  Motoya (real embedded JP fonts = hand-designed bitmaps, a **separate design per dot-grid** 12/16/24…,
  pure bitmap / **no AA**, legibility from per-grid craft): a 12px grid physically can't hold complex-
  kanji detail, and **nearest-upscaling (k≥2) goes chunky/squary while supersampling can't ADD detail
  the 12px source never had.** Ref: `motoyafont.jp/embedded-font/bitmap.html` (parked in `TODO.md`).
- **Render rule LOCKED:** max **display size ≤ 24px** (maybe 20). Small status → **crisp** (native px,
  AA off, **no upscale**). Anything bigger → **supersample DOWN** (render at a high native AA-on,
  smoothscale to target — "hi native, **sub-1 k**"; k0.5 vs k0.25 is a visual wash). **Never nearest-
  upscale.** 12px Ark renders kanji legibly when crisp — the perceived "detail loss" was mostly upscale
  chunkiness, which the cap + supersample fix.
- **Integer-k size constraint — the recurring band-tuning wall (2026-06-25):** crisp pixel renders
  ONLY at integer ×12 native — **12px = 1px stroke, 24px = 2px stroke**, nothing between. So every "a
  bit bigger / smaller" nudge (14/16px buttons, an 18px number) forces ONE of two looks: **sub-grid**
  (render the 12-grid OTF at an off-grid native, AA off → blocky, strokes read too heavy small) OR
  **supersample** (high native AA-on → smoothscale DOWN → smooth, proportional, but NOT crisp-pixel).
  Applied this session: **speed-readout numbers → supersampled to 18px** (`READOUT_NUM_H` /
  `READOUT_NUM_SS_NATIVE` + `_draw_number_ss`; user rejected the native-9×2 sub-grid as "pixelated,
  strokes too wide"); **band-button labels → native-16 sub-grid** (`BAND_BTN_TEXT_NATIVE`, mild
  unevenness, accepted). The readout went smooth, the version number stayed crisp — they no longer
  match exactly, by necessity. **This is the strongest argument for the font-family swap below:** a
  face designed at MORE dot-grids (or a finer one) yields more crisp sizes and cuts the supersample
  reliance — i.e. the "free font for download" question is really "which font frees us from 12/24."
- **16px-Ark dead-end (CORRECTED):** the 16px Ark build is **missing the kanji** — only ~78 of 6,355
  JIS kanji (≈1.2%), so the tofu was genuine `.notdef`, NOT a pygame render bug. (My earlier
  `metrics`-based check was fooled: `font.metrics(ch)` returns the `.notdef` box's metrics, so non-None
  ≠ glyph present — the RENDER is the truth.) More kanji detail needs a *different family*, not a bigger
  Ark grid.
- OFL-licensed (shippable). Eval dir: `_dev_scripts/_fonts_eval/` (12px mono shipped; 12px prop + 16px
  prop + PixelMplus10/12 present). Font investigation harnesses: `_dev_scripts/_ark_size_eval.py`
  (size×multiplier), `_ark_detail_eval.py` (12 vs 16 grid), `_font_check.py` (glyph-coverage / tofu
  probe), `_pixelmplus_eval.py` (coverage + detail vs Ark), `_msgothic_eval.py` + `_msgothic_sizes.py`
  (MS-Gothic strike walk / reference benchmark). **Strike-vs-outline probe:** render AA-ON on an OPAQUE
  bg + count unique colours (2 = bitmap strike, >2 = outline greys); AA-without-bg hides coverage in
  ALPHA so RGB falsely reads 2.
- **Detail-upgrade path (font research #1+#2, 2026-06-25):** real TIMS green status is an *unnamed
  proprietary embedded bitmap* — nothing to cite (that absence IS the finding). **Prefer TTF (glyf)
  over OTF (CFF) for pygame/SDL_ttf**; `pygame.freetype` is the escape hatch for CFF/BDF/PCF. Ranked
  free substitutes (all bundlable, full JIS L1+2 kanji, TTF unless noted):
  1. **JF Dot – Shinonome / jiskan16** (`jikasei.me/font/jf-dotfont/` → 404, use Wayback; public-domain
     set: Shinonome / jiskan16**s** / k12x10 / K14) — **TRY FIRST**. Real bitmap STRIKES at 12/14/16px
     (jiskan16 = the free analog of MS Gothic's 16px kanji strike) — the multi-strike property is the
     thing Ark/PixelMplus lack. JIS-only, so realistic split = jiskan16 for the always-Japanese station
     names + Ark stays for per-locale chrome labels (zh_CN). Raw set is BDF/PCF → convert to TTF or load
     via `pygame.freetype`. Benchmark it in `_msgothic_sizes.py` against MS Gothic @12/14/16.
  2. **PixelMplus12/10** (`github.com/itouhiro/PixelMplus`) — **TESTED 2026-06-26 → REJECTED as a swap.**
     LATERAL detail vs Ark (both 12px grids, no win); single grid per file (12 or 10), NOT multi-strike;
     JA-only (zh_HK 97.3% — tofus 錄; zh_CN 61.5%), so can't serve the per-locale chrome. On disk at
     `_fonts_eval/PixelMplus-20130602/` if a crisp-20px JA-only element ever wants the 10px grid ×2.
  3. **Cubic 11** (`github.com/ACh-K/Cubic-11`) / **Galmuri 11** (`github.com/quiple/galmuri`) — most
     detail-per-grid (11px) but single grid; Cubic targets Big5 so spot-check JIS kanji, Galmuri
     guarantees full JIS X 0208. Reject Misaki / k12x8 (less detail than Ark 12px).
  Aside — real in-car LCD (E235, Hitachi) = **UD Shin Go + Helvetica** [community-attributed]; free
  recipe = BIZ UDGothic / Noto Sans JP. **Motoya is automotive (車載), NOT rail.**

## Tutorial screen (reached from the Tutorial card)
- **Window-in-window master-detail.** LEFT: a column of vertically-stacked TIMS buttons (one per
  feature tutorial), **4-char label on ONE line**. RIGHT: a recessed detail region that hosts the
  selected tutorial. Pressing a left button switches which tutorial the region shows. Two features
  today: **normal usage** + **OCR auto-PA** (more later).
- **Active-tab indicator = lit vs unlit**, NOT yellow (yellow stays reserved for PRESSED). The
  selected tab renders lit (normal blue); the others dim under a dark scrim ("unlit"). This is the
  selected-vs-pressed resolution for a persistent tab selector.
- **Path (a) — reuse the interactive walkthrough.** The "normal usage" tutorial reuses the EXISTING
  `tutorial.py` interactive walkthrough (live 730×420 LCD + progress stepper + step side-panel), so the
  detail region IS that ~1100×500 layout and the tab column slots to its left → a **wide window
  (~1298×588)**. The inner tutorial chrome (progress / LCD / step panel) gets **reskinned to TIMS
  fonts + buttons**. "OCR auto-PA" becomes a NEW walkthrough built the same way. (Rejected: a simpler
  reskinned info panel — drops the hands-on press-cycle, which is the whole point.)
- **OOBE shift** (see Page-1 Tutorial card): no more forced first-run launch; the card flashes until
  first clicked.
- Draft: `_dev_scripts/tutorial_redesign_draft.py` (shell + real-proportion block-out).

## Press / transition model
- **Yellow = pressed** (momentary feedback), never a persistent selected state.
- Any decisive / navigational action (page change, language switch): show the **pressed-state reaction
  beat** first → **~0.5 s blank** loading beat → repaint (in the new language, for a lang switch). One
  shared transition wrapper, reused everywhere.

## Primitives (GRADUATED to `widgets.py`; `button_style_sandbox.py` is now a thin preview)
- `draw_lowres_text(..., align, pad)` — render at native px (antialias off) + nearest-upscale by the
  largest integer k that fits. `align`: `"justify"` (両端揃え) / `"center"` (tight-pack, centered).
  `pad`: margin inset, decoupled from inter-char gap.
- `lowres_fit_k(...)` — the k `draw_lowres_text` would pick (pin a row to uniform size via the min).
- `draw_tims_button` / `tims_button_size` — bevel + delegates label; reads `text_align` / `text_pad`
  from the tuneable.

## Graduation plan
**Steps 1–4 DONE (2026-06-24):** 3 mono Ark `.otf` + OFL → `fonts/`; `i18n.pixel_font_for_lang`
dispatch added; primitives in `widgets.py` taking a **pre-resolved `Font`** (per `/third-man` — zero
font-loading in `widgets.py`); hatches dropped; `_vgradient_rounded` cached. Draft + sandbox + test
rewired; linters green. (Refinement vs the original plan: fonts route through `i18n`, not a local
`widgets._font`.)

**Remaining:**
5. **Wire `setup.py`** — but REDIRECTED: build the **tutorial screen first** (reskin `tutorial.py`
   inner chrome to TIMS + wrap in the tab-shell + add the OCR-auto-PA tab), then the home menu, then
   the Tutorial-card flash + simplified OOBE in `main.py`. Real i18n strings (`translations_app.json`),
   not draft placeholders. `main.py SETUP_SIZE` → the taller own-window size.
6. **Codify as this doc dissolves** — `conventions.md` (pixel = small-size aesthetic; TIMS chrome =
   monospaced Ark; the `draw_lowres_number` trim-ink numeral recipe; the `widgets.py` boundary +
   font-via-i18n); fix the `TODO.md` single-face claim.

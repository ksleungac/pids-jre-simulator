# WIP: Setup Screen Redesign (TIMS-style)

In-flight redesign of the setup / home screen to the JR East TIMS cab-console look (glossy
raised-bevel blue buttons + low-res pixel text). **Live home: the `setup_tims/` production package**
(promoted 2026-06-27 — see § Promotion); primitives in `widgets.py`. The original drafts
(`_dev_scripts/setup_redesign_draft.py`, `button_style_sandbox.py`) are historical. This doc holds the
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

Layout, left→right. **All three left rows bottom-align to the SAME row baselines as the readout** so the
state column and the speed column line up row-for-row.
- **Left column (small, crisp k=1)**, 3 rows: (0) **green katakana notification — persistent on every
  scenario** (`ツウコク　ジョウホウ` = 通告情報, matched to `tims_002`, full-width word gap); (1) segment
  `from → to` (station names, JP); (2) inferred Layer-3 state word · played `N/M` · **badge (Layer-2 raw
  read) FOLDED onto this line**, dim (NO confidence colour). **Per-line font:** station names → JP face
  (`pixel_font_for_lang("en", …)` = NotoSansJP); localized chrome → the ACTIVE locale face (TC/SC) — fixes
  the zh_CN tofu (the TC face lacks Simplified-only glyphs).
- **Centre readout cell** (right-aligned, between separators) — speed limit / speed / **distance
  (ALWAYS metres** — OCR reads m; finer than rounded km). **Fat full-width (全角) numerals** (digits on a
  monospace cell, separators/units half-width), ink **bottom-aligned to the row baselines**. Speed limit
  is **plain until it CHANGES, then flashes cyan a few seconds and settles** (change cue); the cyan block
  **hugs the number ink**, not the font's tall leading box.
- **Message strips (centre-right)** — the original TIMS **two dim bars** = message displays. House the
  OCR **fire event**, **stopping-position** reading, **re-aligning** signal, paused/frozen-OCR, etc.
  **Message text = bright YELLOW, flashing, auto-clears after a while** — the auto-played fire chip's ~3 s
  expiry lives in `_band_vals`; other strips clear when their condition ends.
- **Right control cluster** — `[pause] [save-record] [home]`, **uniform square** TIMS buttons. Sized to
  the **worst-case label across ALL locales** (so en/zh_HK/zh_CN don't jump size); the box px is **frozen
  and decoupled from the label px** (label can grow without the box growing). Cluster **hugs the top-right
  corner**. Home always rightmost (return-to-home, persistent). Pause + save-record are the migrated
  debug-panel controls (save-record = the old Report / driving-record download).

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

**Route-name basic form + through-service deferral (2026-06-27).** The selection boxes show only the
**basic line name** — route.json `route` was stripped to the primary line, dropping the through-service /
combined secondary: 上野東京ライン・常磐線直通→常磐線, 総武快速線・成田線直通→総武快速線, 京浜東北・根岸線→京浜東北線,
埼京線・川越線→埼京線, 中央線快速電車→中央線快速 (the already-basic lines — 南武線 / 山手線 / 京葉線 / 東海道線 /
高崎線 — unchanged). **This `route` field is also the LCD upper-display route name (`app.py`), so the LCD
shows the basic form now too.** DEFERRED: proper **direct-connect / through-service (直通) mapping** — the
combined names encode real through-running (Negishi / Narita / Kawagoe / Jōban-via-Ueno-Tōkyō); to be
mapped out after the user samples IRL PIDS behaviour. Side-effect: lines with >1 diagram now share a box
label (train type was dropped from the box) → selection-screen disambiguation is its own open item.

**Start-station grid excludes passing stations (2026-06-27).** The station picker lists only stopping
stations — passing stations (empty `pa`, no `sta` / `time`) are filtered via the documented predicate
(`DATA_FORMAT.md § Skipping Stations`); the picker maps the filtered selection back to the full stop
index (`stop_idxs`) on return.

## PA-setting page (C07AA — 案内設定) (2026-06-27)
Reached after route / diagram / station selection. Screen code **C07AA**. Mirrors IRL
`tims_pa_setting_done.png` but adapted to this app's manual-first model.
- **自動放送始発起動 = a LAUNCH ACTION, not a toggle.** Pressing it arms OCR auto-PA and goes
  **straight to the live LCD**. There is no persistent on/off switch on this page.
- **Manual mode = the default un-armed launch (起動).** Launching without arming OCR starts the live
  LCD in manual (PageDown-driven) mode — the existing behaviour.
- **OCR tuning lives behind a separate 自動放送設定 button** (lead distance / interval + the consent
  step), NOT inline — keeps the launch page a clean go-button.
- **"Train type display" = the train MODEL / LCD skin**, per-route — realized as the **列車型號** model
  picker (§ "Model picker"). Legacy `setup.py` does it via the per-route dropdown (2026-06-21);
  `setup_tims` via the X00AA 番台選択 screen. Out-of-spec model picks are allowed (best-effort).
- **Bottom button row (2026-06-28):** 確認 (manual launch) and 列車型號 share one y (`BTN_ROW_Y`); the area
  BELOW is reserved for the coming OCR-choice buttons (自動放送始発起動 / 自動放送設定).

## Model picker (X00AA — 番台選択 / 列車型號) (2026-06-28)
Reached from C07AA's **列車型號** button (the IRL 番線 platform slot, repurposed — we removed the real 番線,
no platform model). Mirrors IRL `tims_bandai_choice.png`.
- **Grid = built models (selectable) + grayed roadmap models.** Built come from the train-model registry
  (`model_choices()`, blue); grayed ones are a small hardcoded list (`model_select._GRAYED`: E231-500,
  E233-0/1000/5000) shown DISABLED — per the reference, unavailable 番台 are dimmed, not hidden. Ordered by
  series number: E231 → E233 → E235 (built last).
- **2-line staggered buttons:** series 系 (`E235系`) line 1 hugs LEFT, sub-series 番台 (`1000番台`) line 2 hugs
  RIGHT, chars spaced (justify). Designations are FIXED across locales (Latin + 系/番台), parsed by splitting
  the registry label (`E235-1000` → `E235` / `1000`).
- **No confirm / no back button** (per the reference): clicking a model commits it; band Home / ESC return.
  The **current model FLASHES** lit↔normal (active = last user pick this run, else the route default).
- **Grayed = silver palette** (`_GRAY_T`), not a dark scrim — see conventions.md § UI code style.
- **Override is session-persistent:** `pa_setting._model_override` (set on pick) overrides the route default
  in `_build_config`, surviving route changes within one app run. `model_select.run_on(screen, current)`
  returns the chosen key / None (ESC) / "home".
- OPEN: whether to DISPLAY the current model on C07AA (recommended yes — compact, by the 列車型號 button —
  awaiting user go).

## Font decision — Noto Sans (per-locale), AA-OFF native, no upscale  [LOCKED 2026-06-27]
**Core insight that resolves the whole multi-session font hunt:** the TIMS / embedded-system "pixel
text" look is simply an ordinary outline font rendered with **anti-aliasing OFF** — NOT a pixel font,
NOT embedded bitmap strikes, NOT nearest-upscaling. Render a normal gothic AA-off at the native display
px and it reads as crisp single-stroke. Everything below follows from that one fact.

- **Font = Noto Sans, per-locale: JP / TC / SC** (`NotoSansJP` / `NotoSansTC` / `NotoSansSC`, OFL,
  shippable). JP serves station names (always Japanese) + Latin/JP chrome; TC = zh_HK chrome; SC =
  zh_CN chrome. JP **Han-unifies / tofus** Chinese (proven: JP renders 选报动线 as identical `.notdef`
  boxes — uniform ink across distinct chars is the tell), so the siblings are required — same 3-file
  per-locale structure the old Ark build used. User picked Noto Sans JP by eye over BIZ UDGothic / M+ 1
  Code / MS Gothic.
- **Render = native ×1, AA OFF, NO upscaling.** Nearest-upscale (×2) was tried and rejected — it
  thickens the stroke (16×2 reads heavier than native 32). Render Noto AA-off at the raw display px,
  full stop.
- **Size envelope ≤ ~36–40px native.** Above ~40px the outline thickens past the single-stroke look;
  below that, every size reads clean. Chrome text lives in a ≤~40px envelope. (The giant TIMS
  train-number readout is OUT of scope — user won't build it.) Nothing upscales to grow.
- **Numerals = full-width (全角) numeric chars + half-width (半角) unit letters.** Per TIMS (`tims_002`
  top-center): digits AND numeric separators (`:` clock, `.` decimal) are wide full-width glyphs on a
  MONOSPACE cell; unit letters (`km/h`, `km`) are narrow half-width Latin. So the speed `3` is
  intentionally much wider than `km/h` — that's the 全角/半角 convention, **not a bug**. Noto's default
  full-width cell is too wide → pack digits+separators onto `cell = max digit ink + gap` (gap tunable,
  may be negative), glyph ink centered; unit letters render natural inline. **Ported into the draft band
  readout** (`setup_redesign_draft._tims_digit_cell` cached + `_draw_number_ss`, AA-off); helper origin
  `_dev_scripts/_noto_numbers.py tims_number`. Shared `widgets.draw_lowres_number` NOT yet on it.
- **Rejected (one-liners):** MS Gothic = best look but NON-SHIPPABLE (MS license + JIS-only → tofus
  zh_CN); system-load is legal but presence-not-guaranteed + still needs a zh_CN fallback — not worth
  it. Ark Pixel = disliked glyph shapes (the trigger to abandon the pixel-font path). The entire
  "multi-strike bitmap pixel font" hunt (jiskan16 / Shinonome / PixelMplus) is **MOOT** — the look is
  AA-off, no special font needed.
- **Weight = Thin, shipped as Subset OTF (2026-06-27).** The original look was Noto **Thin** (not
  Regular — a Regular swap visibly thickened the stroke; user caught it). Ships as the small static
  **Subset OTF** files (`NotoSans{JP,SC,TC}.otf`, `-Thin` weight), NOT the heavy ~39MB variable fonts —
  so no `/build` subsetting step is needed for the chrome fonts. `.otf` keeps the `.otf`-only
  convention intact (the earlier `.ttf` carve-out plan is moot).
- **Supersedes:** the Ark "single-face / 12px monospaced" decision; the `conventions.md` **k=2 ceiling**
  rule; the "supersample-down / max ≤24px" lock; the `TODO.md` single-face claim; the
  `draw_lowres_text` / `lowres_fit_k` / `draw_lowres_number` nearest-upscale + trim-ink premise.
  Reconcile all at graduation step 6. Eval harnesses (dev): `_noto_size_ladder.py` (native size sweep),
  `_noto_numbers.py` (numeral packer), `_gothic_compare.py` (font shortlist), `_noto_locale_check.py`
  (per-locale coverage); fonts in `_dev_scripts/_fonts_eval/`.

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

## Primitives (in `widgets.py`; `button_style_sandbox.py` is a thin preview)
- **AA-OFF NATIVE, no upscale (2026-06-27).** Callers load the font at the DISPLAY px (via `i18n`) and
  pass `max_k=1` / `k=1`; the k-upscale machinery is now dormant (renders native). (k-machinery left in
  place; simplify at graduation.)
- **Systematic vertical layout via `_ink_vbox(font, label)` → `(ink_top, ink_h)`.** The ONE reference
  for all chrome vertical positioning (replaces ad-hoc per-element nudges): line stacking + box height
  use `ink_h` (not `font.get_height()` — Noto's tall leading would balloon inter-line gaps past the
  tight char spacing), and glyphs blit at `line_ink_top - ink_top*k` so they keep their natural
  baseline. Result: `line_gap` is the TRUE visual gap, boxes hug the text, single lines center on
  their ink (no leading-induced 'pushed down' / box-too-short clipping), and mixed kanji/digit/latin
  on one line baseline-align. **Follow-up:** `draw_lowres_number` is NOT yet on this model — the
  version tag bridges it by rendering the number to a temp + ink-centering against the word's band
  (`_render_version_tag`); harmonize `draw_lowres_number` onto `_ink_vbox` to drop that bridge.
- `draw_lowres_text(..., align, pad)` — render AA-off at the font's native px; `align` justify/center;
  `pad` margin inset decoupled from inter-char gap.
- `draw_lowres_number` — TIMS numerals, AA-off native (trim-ink + gap). NOTE: the user-approved style is
  full-width digits (全角) + half-width units (半角). The **draft band readout now uses a fat full-width
  packer** (`setup_redesign_draft._tims_digit_cell` / `_draw_number_ss`); the shared `widgets.draw_lowres_number`
  (version tag only) is STILL trim-ink — harmonize it onto the full-width packer + `_ink_vbox` model.
- `draw_tims_button` / `tims_button_size` — bevel + delegates label; reads `text_align` / `text_pad`.

## Promotion to setup_tims/ package (2026-06-27)
The three drafts graduated into a **production package `setup_tims/`** (per `/third-man` — a package,
not a monolith), running **side-by-side with the legacy `setup.py`** (not replacing it yet):
- `band.py` — persistent OCR status band + screen dims (`SCREEN_W/H`, `BAND_H`, `BG_COLOR`).
- `chrome.py` — **shared reuse layer**: `title_row` (was copy-pasted 3×) + `blit_lowres` (promoted
  from the band-private `_blit_lowres`).
- `home.py` — page-1 menu (split out of the band monolith).
- `pa_setting.py` (C07AA), `route_select.py` (C07AB/AC/AF) — the PA-setting + picker pages.
- `__init__.py` — package API. Dev launcher: `_dev_scripts/preview_setup_tims.py --screen home|pa|route`.

**Launch bridge — DONE (manual mode, 2026-06-28).** `main.py --tims` launches the `setup_tims` flow
side-by-side with the legacy `setup.py` (no flag → classic path, untouched; `--tims` avoids regressing
OCR-auto-PA since OCR-launch isn't wired yet). Flow: `setup_tims.run(screen)` (re-exported from `home`)
runs the home menu → 報站設定 → `pa_setting` → **確認/起動** → `pa_setting._build_config` returns a config
shaped like `setup.SetupScreen.run()` (`action`/`work_dir`/`route_data`/`model`/`start_idx`), bubbled up
through `home.run`; `main.py` builds `PASimulator` + `jump_to_stop(start_idx)`. `route_select` variants now
carry `path` (→`work_dir`) + `model`. Start is resolved by NAME against the committed variant (closed the
v0-index carry-forward). STILL open: per-module `ACTIVE_LANG` → single `i18n._current_lang` (deferred);
OCR-launch (the 自動放送設定 page + consent).

## Graduation plan
**Steps 1–4 DONE (2026-06-24):** 3 mono Ark `.otf` + OFL → `fonts/`; `i18n.pixel_font_for_lang`
dispatch added; primitives in `widgets.py` taking a **pre-resolved `Font`** (per `/third-man` — zero
font-loading in `widgets.py`); hatches dropped; `_vgradient_rounded` cached. Draft + sandbox + test
rewired; linters green. (Refinement vs the original plan: fonts route through `i18n`, not a local
`widgets._font`.)

**Remaining:**
5. **Wire `main.py` to launch the `setup_tims/` flow.** DONE: the launch bridge (`--tims`, manual mode —
   see § "Launch bridge"); real i18n strings (`translations_app.json`, zh_CN user-confirmed) replacing the
   draft `*_BY_LANG` dicts; the model picker (§ "Model picker"); `--tims` sets its own 730×610 window.
   STILL remaining: the **tutorial screen** (reskin `tutorial.py` inner chrome to TIMS + tab-shell +
   OCR-auto-PA tab), the Tutorial-card flash + simplified OOBE, OCR-launch (自動放送設定 page + consent),
   flip `--tims` to default once at parity.
6. **Codify as this doc dissolves** — `conventions.md` (TIMS chrome = Noto, AA-OFF native, no upscale,
   ink-based line height; the full-width/half-width numeral convention; the `widgets.py` boundary +
   font-via-i18n); DROP the now-stale Ark / k=2-ceiling / supersample / trim-ink rules; fix the
   `TODO.md` single-face claim.

## Integration progress — Noto swap (2026-06-27)
**DONE this session:** Noto decision LOCKED (§ Font decision) + wired into the DRAFT (`setup_redesign_draft.py`)
+ `i18n` + `widgets.py`, AA-off native. Main-setup preview renders clean (`_setup_noto.png`) — user: "looks so good."
- `i18n._LANG_PIXEL_FONT` → `NotoSans{JP,SC,TC}.otf` (Subset OTF Thin, in `fonts/` + `NotoSans-OFL.txt`).
- `widgets.py`: ink-based line height (`_ink_line_h`) so `line_gap` is the true visual gap + boxes hug text;
  k-machinery dormant (callers pass k=1 → native).
- Draft: per-element native px — CHROME 22, band-button 16, SMALL split into NOTIF 11 (green notif) /
  STATE 16 (OCR state + badge); readout supersample → AA-off native; version word+number re-aligned
  under the ink model.

**OPEN — tuning (user is visual judge):**
- Message-strip vertical position (`STRIP_Y1`) — ambiguous ("dimmed grey too close to band top"); nudged to 15, needs the user's eye.
- Numeral style — readout + version still trim-ink; port the full-width(全角)/half-width(半角) `tims_number` look.
- Final px / sizes — left-col (`NOTIF_NATIVE`/`STATE_NATIVE`), squares (`HOME_TEXT_MARGIN`/`LANG_TEXT_MARGIN`), line gaps.

**RESOLVED — shippability (2026-06-27):**
- **`.otf`, not `.ttf`** — switched to the Subset **OTF** Thin files, so the `check_fonts.py` `.ttf` ban + the `.otf`-only convention both hold with no carve-out.
- **Size** — Subset OTF Thin files are small; no `/build` subsetting needed for the chrome fonts.
- **Noto OFL** — `fonts/NotoSans-OFL.txt` ships alongside (critical_lessons §2).

**NEXT:** finish draft tuning → wire `setup.py` (step 5) → reconcile widgets.py k-machinery + the conventions/TODO codification (step 6).

## Integration progress — OCR band refinement (2026-06-27, cont.)
Iterated `_render_topband` against the OCR mock scenarios via `_dev_scripts/preview_band_ocr.py` (wires the
draft band to `preview_debug_panel`'s status dicts; `1-6` scenario, `L` locale, `P` pause).

**DONE (all in the DRAFT + dev preview):**
- **Fat full-width numerals ported** into the readout (`_tims_digit_cell` / `_draw_number_ss`) — closes the
  "port the 全角/半角 numeral style" OPEN item for the draft. Shared `widgets.draw_lowres_number` still trim-ink.
- **zh_CN tofu fixed** — per-line band fonts (station names → JP face; localized chrome → active-locale TC/SC);
  numbers/units locale-independent. Was hardcoding the TC face everywhere.
- **Green notif** matched to `tims_002` (`ツウコク　ジョウホウ`, full-width gap), now persistent on all scenarios.
- **Badge folded** onto the state line (`state · played · badge`, dim); boot/placeholder unified to the live
  layout. The wider folded line forced the readout + message strips to shift right.
- **Columns aligned** — left state rows share the readout's row baselines; readout values bottom-align; cyan
  limit block hugs the number ink.
- **Control cluster** — uniform squares across locales (worst-case-label sizing); box px frozen + decoupled
  from the label px so text grows without the box growing; cluster hugs the corner.
- **Message auto-clear** — preview stamps the fire ts at scenario-entry (not every frame), so the chip flashes
  its ~3 s window then clears; re-press the scenario key to re-arm.

**OPEN:**
- **en control label at its size ceiling** — `Back Home` at the current label px exactly fills the box (≈0 margin,
  touches the bevel); zh comfortable. Shorten the en label or dial the label px back if en matters.
- **`widgets.draw_lowres_number`** still trim-ink (version tag) — harmonize onto the full-width packer + `_ink_vbox`.
- Final px / positions remain the user's visual call.

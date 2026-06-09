---
name: visual-adjust
description: Visually iterate on UI layout by comparing screenshots against ground truth
triggers:
  - /visual-adjust
  - adjust ui
  - visual adjust
  - fix layout
---

## Visual UI Iteration Workflow

You are adjusting pygame display layout by comparing rendered screenshots against
a real-world ground truth photo provided by the user.

## Prerequisites

- `preview_display.py` supports `--screenshot`, `--mode`, `--stop`, `--pa` flags
- User provides a ground truth photo (real train display photo or reference image)
- Read the relevant display renderer code before starting (e.g., `upper_lcd.py`)

## Workflow

### Step 1: Get ground truth
Ask the user for a reference screenshot if they haven't provided one.
Study it carefully — note font sizes, spacing, alignment, colors, margins.

### Step 2: Screenshot current state
```bash
uv run preview_display.py --screenshot screenshot_<name>.png --mode english --stop 0 --pa 2
```
Read the PNG to see the current rendering. Compare against ground truth.

### Step 3: Identify discrepancies
Call out specific differences:
- Font size (too big/small)
- Position (margins, alignment, vertical centering vs bottom-aligned)
- Font artifacts (macron bars, clipping)
- Colors (wrong shade, missing contrast)
- Spacing between elements

### Step 4: Make ONE adjustment
Edit the renderer code. Change one thing at a time:
- Font size
- Position coordinates
- Font file (e.g., .ttf → .otf for better glyph metrics)
- Color values

### Step 5: Screenshot and compare
Take a new screenshot, read it, compare against ground truth.
Present to user for feedback.

For non-trivial size/position/font work, build a **side-by-side composite**
that stacks the reference photo above the cropped render, height-aligned —
see "Side-by-side composites" below.

### Step 6: Iterate or move on
- If user says it's off → go back to Step 4
- If user approves → clean up screenshots, move to next element

## Rules

- **One element at a time**: Don't adjust station name and destination simultaneously
- **Never delete the latest iteration's screenshot.** The user reviews each frame after
  it's saved — they need to be able to open it after the response ends. Only clean up
  *older* screenshots once a *newer* one exists on disk for the same scenario. Pattern:
  before each new screenshot, `rm screenshot_v<N-1>_*.png`; the freshly-rendered
  `screenshot_v<N>_*.png` stays. Never end a turn with no recent screenshot present
- **Show multiple examples**: After getting one station right, render 3-4 others
  (short names, long names, macrons) to verify it works broadly
- **Self-iterate for pixel perfection**: When adjusting values (font size, position),
  take screenshots and compare against ground truth yourself. Don't ask the user to
  review every intermediate screenshot — iterate autonomously until it looks right,
  then present the final result. Only show intermediates if the user specifically asks.
- **When the user IS in the loop, don't re-read the PNG.** The previous rule covers
  claude-alone iteration against fixed ground truth. The opposite mode — user providing
  rapid feedback ("color bar wider", "stroke 2px narrower", "10px more gap") — has the
  user as the eye. Render, save the PNG, present to user; do NOT Read the PNG yourself
  to verify. The user already opened it. Reading it adds latency without adding signal,
  and the user has named this costly: "u no need to read the png, this is slowing you
  down" (2026-05-07, circular full-route iteration). Mode tell: if claude's last action
  was "applied user's tweak request, rendered" → next action is "present to user", NOT
  "Read the PNG."
- **Loose iteration language is approximate**: when the user says "half" or "5–10 px
  more", treat it as approximate — verify with screenshots, don't over-fit to the
  literal number. The user is describing an outcome, not specifying an exact value.
- **User is the final judge**: Present your best result; user decides if it's right
- **Don't batch background tasks**: These shells can be flaky — run one screenshot
  at a time with `cd` prefix to avoid path issues

## Side-by-side composites for direct comparison

When iterating on size, vertical placement, weight, or font choice, eyeballing
two separate images side-by-side is unreliable. Build a composite that:

1. Crops the rendered screenshot to the relevant LCD strip (e.g. upper LCD =
   top 117px, x=270 onward to focus on the station-name region)
2. Scales **both** the reference photo and the cropped render to the **same
   height** (not width — height-aligned keeps the LCD strip itself the same
   size in both, so glyph proportions and bottom-margin gaps read correctly)
3. Stacks them vertically with labels: `REFERENCE: <name>` on top, `RENDER
   (<label>): <name>` below
4. Saves as `compare_<label>_<station>.png`

`_dev_scripts/compare_fonts.py` is a working implementation. Pattern:
```bash
# 1. render variants under a label
uv run preview_display.py --screenshot screenshot_v1_bold_tokyo.png --mode english --stop 0 --pa 2
# ... one per reference station

# 2. build composites
uv run _dev_scripts/compare_fonts.py v1_bold
```

For A/B/C comparison of multiple variants at once, see `_dev_scripts/compare_grid.py` —
stacks reference + N candidate renders for each station.

Use this whenever there's a static reference photo and you're iterating —
much more reliable than mental overlay.

## Reactive Layout Principle

**Your eyes are not precise enough — write code so the user can fine-tune it.**

When writing or adjusting layout code:

1. **Extract all tuneable values into a labeled params block** at the top of the
   method (or `__init__` for fonts). Group them visually so they're easy to find:
   ```python
   # --- Badge params (adjust freely) ---
   badge_x    = 222
   badge_w    = 68
   ring_black = 7
   text_gap   = -10
   # -------------------------------------
   ```

2. **All positioning must derive from those params** — no magic numbers scattered
   below. If the user changes `badge_w`, interior width, centering, and text
   positions should all recompute automatically.

3. **Font sizes** live in `__init__` (must be preloaded), but add a comment pointing
   to the method so the user knows where to look. Layout in the draw method should
   use `font.get_size()` / `surface.get_size()` to react to whatever size was set.

4. **Do not add overflow guards** (e.g. `max(0, ...)`). If the user sets a font too
   large for the container, they should see the overflow — that's their signal to
   tune the value.

5. **Discuss alignment approach before coding**: before writing a new element,
   briefly describe the intended reactive behaviour (e.g. "text group centered
   vertically in the white interior, both rows horizontally centered on the same
   axis") and confirm with the user. Saves back-and-forth on the wrong layout model.

## Preview Script Reference

```bash
# Flags
--screenshot <file.png>    # Save one frame and exit
--mode <kanji|furigana|english>  # Force display mode
--stop <index>             # Station index (0-based)
--pa <0|1|2>               # 0=次は/Next, 1=まもなく/Arriving at, 2=ただいま/Now stopping at
--route <name|path>        # Route shorthand (e.g. yamanote, sobu/1217F) or path; default _mock/main
--lower-view <full|eight|cycle>  # Force lower LCD view; default 'cycle' (24s alternation).
                                 # 'eight' or 'full' freezes the view-cycler for deterministic frames.
--debug-grid               # Tint each upper-LCD region's clear rect with a unique color

# Examples
uv run preview_display.py --screenshot out.png --mode english --stop 0 --pa 2
uv run preview_display.py --screenshot out.png --mode kanji --stop 3 --pa 0
uv run preview_display.py --screenshot 8sta.png --route sobu/1217F --stop 7 --lower-view eight
uv run preview_display.py --debug-grid --route sobu/1217F --mode english --stop 18 --pa 2
```

## Debug-grid mode

When the work is about **region territory** (where an element's drawing should and should not land) rather than glyph appearance, use `--debug-grid`. Each region's clear rect paints in a distinct color (red=dest, blue=prefix, yellow=clock, magenta=station, orange=pa_hint, gray=upper_bg). What it surfaces:

- **Clear-rect overlaps** — one region's tint bleeding into another's bounds means the later-drawn region is clobbering the earlier one
- **Under-clears** — untinted patches *inside* what should be a fully-painted region mean the clear rect is smaller than the region's confinement
- **Glyph escapes** — text/glyphs landing on top of a *neighboring* region's tint is a containment violation

The principle: **anything a region draws (bg fill, glyphs, decorations) must visually stay inside that region's confinement.** Clear rect is not special — it's just one of the things drawn. Same rule for all of them. See `DISPLAY.md` "Element Clear-Background Convention" for the full statement.

### Two checks: D1 (cheap) and D2 (real)

Pygame font surfaces include **leading** — empty (transparent) pixels above visible glyph caps, ~10–15px for big fonts. So:

- **D1 (surface check, cheap)**: `blit_y ≥ confinement.top`. Pure analytical, no probing. If it passes → containment guaranteed by construction. If it fails → *signal to probe*, not auto-violation.
- **D2 (visible-pixel check, real)**: actual glyph caps at y ≥ confinement.top. Requires pixel-probe a rendered screenshot. Tighter — allows surfaces to extend above confinement when leading absorbs the overshoot.

**D2 is the rule that ships.** D1 is a useful pre-check. If the user requires a specific font size for IRL accuracy and D1 would forbid it, that's not actually a violation — probe D2 to confirm what visible pixels do.

### Probing methodology (gotcha)

When pixel-probing for containment, **isolate the region** so neighbors' content doesn't masquerade as the target's:

- Use a scenario where the neighbor is empty or short — for station vs prefix, test the short "Next" prefix (x≤280), leaving x=302+ purely station territory. With "Now stopping at" (long, x=222–460), prefix text glyphs in the overlap zone (x=302–460, y=20-something) get easily mistaken for station glyphs.
- Or probe at "exclusive x ranges" where only the target paints. For station that's x=522–570 and x=650–686 (the gaps between prefix/clock).
- A real example from this codebase: I (Claude) misread prefix text glyph pixels at x=315, y=22-24 as the station's "Narita Airport" line 1 caps and reported a false D2 violation. Pick clean test scenarios.

## Common Pitfalls

- **`.ttf` Helvetica** has macron artifacts at large sizes → use `.otf` variants
  (`fonts/HelveticaNeue-Bold.otf` is the canonical English-station font; the
  old `HelveticaNeueBold.ttf` has been removed)
- **Vertical positioning**: Real displays are usually bottom-aligned, not centered
- **Element clear-bg convention**: every changeable element clears its **full territory**
  via `_bg("<region>")` as the first step of its draw method — not just the current
  glyph footprint. All three mode renderers (Japanese / Furigana / English) share the
  same territory for the same element. Adding a new region: register it in
  `_DEBUG_COLORS` AND the Region Map comment block at the top of the LCD module.
  See `DISPLAY.md` "Element Clear-Background Convention" for full rules,
  including the band-bottom clamp that prevents the station's tall 2-line variant
  from clobbering the prefix/clock above.
- **Shell flakiness**: paths in this repo can vary between machines; rely on
  pwd-relative commands rather than hardcoding an absolute project path
- **Background tasks**: The first command may run in background. DO NOT retry immediately — the msys bash crashes when two shells fork simultaneously. Wait for the background task to complete instead.
- **Headless mode**: Screenshot mode uses `SDL_VIDEODRIVER=dummy` automatically — no window needed
- **Mock data**: The mock route is a real `route.json` at `audio/_mock/main/route.json`
  (not in code). Default for `preview_display.py`. Edit that file directly to add
  test cases. Reference station indices for compare scripts: see
  [`audio/_mock/main/README.md`](../../../audio/_mock/main/README.md).

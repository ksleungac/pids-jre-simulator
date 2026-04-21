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

- `preview_upper_lcd.py` supports `--screenshot`, `--mode`, `--stop`, `--pa` flags
- User provides a ground truth photo (real train display photo or reference image)
- Read the relevant display renderer code before starting (e.g., `upper_lcd.py`)

## Workflow

### Step 1: Get ground truth
Ask the user for a reference screenshot if they haven't provided one.
Study it carefully — note font sizes, spacing, alignment, colors, margins.

### Step 2: Screenshot current state
```bash
uv run preview_upper_lcd.py --screenshot screenshot_<name>.png --mode english --stop 0 --pa 2
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

### Step 6: Iterate or move on
- If user says it's off → go back to Step 4
- If user approves → clean up screenshots, move to next element

## Rules

- **One element at a time**: Don't adjust station name and destination simultaneously
- **Clean up screenshots** as you go — delete old PNGs after user has seen them
- **Show multiple examples**: After getting one station right, render 3-4 others
  (short names, long names, macrons) to verify it works broadly
- **Self-iterate for pixel perfection**: When adjusting values (font size, position),
  take screenshots and compare against ground truth yourself. Don't ask the user to
  review every intermediate screenshot — iterate autonomously until it looks right,
  then present the final result. Only show intermediates if the user specifically asks.
- **User is the final judge**: Present your best result; user decides if it's right
- **Don't batch background tasks**: These shells can be flaky — run one screenshot
  at a time with `cd` prefix to avoid path issues

## Preview Script Reference

```bash
# Flags
--screenshot <file.png>    # Save one frame and exit
--mode <kanji|furigana|english>  # Force display mode
--stop <index>             # Station index (0-based)
--pa <0|1|2>               # 0=次は/Next, 1=まもなく/Arriving at, 2=ただいま/Now stopping at

# Examples
uv run preview_upper_lcd.py --screenshot out.png --mode english --stop 0 --pa 2
uv run preview_upper_lcd.py --screenshot out.png --mode kanji --stop 3 --pa 0
```

## Common Pitfalls

- **HelveticaNeueBold.ttf** has macron artifacts at large sizes → use `.otf` variants
- **Vertical positioning**: Real displays are usually bottom-aligned, not centered
- **Shell flakiness**: Always prefix with `cd C:/Users/oscar.leung/Documents/pids-jre-simulator &&`
- **Background tasks**: The first command may run in background. DO NOT retry immediately — the msys bash crashes when two shells fork simultaneously. Wait for the background task to complete instead.
- **Headless mode**: Screenshot mode uses `SDL_VIDEODRIVER=dummy` automatically — no window needed
- **Mock data**: If you need a specific station name, add it to `MOCK_STOPS` in the preview script

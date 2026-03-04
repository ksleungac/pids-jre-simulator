# Font Rendering & Text Measurement Guide

**Project**: JRE-PA-Simulator
**Font**: ShinGoPr6N-Medium.otf
**Date**: 2026-03-02

---

## Quick Reference

### Measuring Text Width with Pygame

```python
import pygame

font = pygame.font.Font('fonts/ShinGoPr6N-Medium.otf', 78)
text = "東京駅"
width, height = font.size(text)  # Returns (234, 78) for 3 kanji at size 78
```

### Key Character Dimensions (at 78px)

| Character Type | Width × Height |
|----------------|----------------|
| Kanji          | 78×78 px (square) |
| Katakana       | 78×78 px (square) |
| Hiragana       | 78×78 px (square) |
| Latin (A-Z)    | ~64×78 px (proportional) |
| Digits (0-9)   | ~59×78 px (proportional) |

---

## draw_text_given_width Logic

**Location**: `utils.py:45-87`

This function draws text with **even character spacing** across a fixed width.

### Function Signature

```python
draw_text_given_width(
    x: int,           # Starting X position
    y: int,           # Y position
    width: int,       # Maximum width to fill
    font: Font,       # Pygame font object
    text: str,        # Text to render
    color: tuple,     # RGB color
    screen: Surface,  # Pygame surface
    collapse: bool    # If True, center without spacing (default: False)
)
```

### Two Rendering Modes

#### Mode 1: Text FITS within width (`t_w <= width`)

```python
# Line 78-87: Expand/add spacing
sep = (width - t_w) // (len(text) + 1)  # Gap between chars
exp = 7 if len(text) == 2 else 0        # Extra adjustment for 2-char text

for i, char in enumerate(text):
    x_coord = x + sep * (i + 1) + i * t_w_s + (exp if i > 0 else -exp)
    img = draw_text(char, font, color, int(x_coord), y)  # NO scaling
    screen.blit(img, (int(x_coord), y))
```

**Behavior**:
- Characters rendered at **full font size** (no scaling)
- Even **spacing added between characters**
- `sep` = gap calculated to distribute characters evenly

**Example** (3-char name "東京駅" in 394px width):
- Original width: 234px
- `sep = (394 - 234) // 4 = 40px`
- Each character stays 78×78px, spaced 40px apart

#### Mode 2: Text EXCEEDS width (`t_w > width`)

```python
# Line 70-76: Compress characters horizontally
sep = width / len(text)
hr = width / (len(text) * t_w_s) if t_w_s > 0 else 1.0

for i, char in enumerate(text):
    x_coord = x + sep * i
    img = draw_text(char, font, color, int(x_coord), y, h_ratio=hr)  # SCALED
    screen.blit(img, (int(x_coord), y))
```

**Behavior**:
- Characters **compressed horizontally** via `h_ratio`
- `h_ratio` = scale factor < 1.0
- Each character rendered individually with `pygame.transform.smoothscale`

**Example** (7-char name "東京テレポート" in 394px width):
- Original width: 546px
- `hr = 394 / 546 = 0.72` (72% horizontal scale)

---

## Upper LCD Station Name Rendering

**Location**: `display.py:_draw_station_name()` (lines 160-189)

```python
# Constants
FONT_STATION_SIZE = 78  # Intentionally oversized
S_WIDTH = 730
station_area_width = int(S_WIDTH * 0.54)  # = 394px

# Rendering
name_x = int(S_WIDTH * 0.40)  # Starting position
max_width = S_WIDTH * 0.54    # 394px available

draw_text_given_width(
    name_x,
    name_y,
    int(max_width),
    self.font_station,  # Size 78
    name,
    self.white_bg,
    self.screen
)
```

### Character Count vs. Scaling

| Characters | Example | Original Width | Action | Result |
|------------|---------|----------------|--------|--------|
| 3 | 東京駅 | 234px | Add spacing | Full 78px chars, spaced out |
| 5 | 新宿御苑前 | 390px | Minimal spacing | Full 78px chars |
| 7 | 東京テレポート | 546px | Compress to 72% | 56px-wide chars |
| 11 | 成田空港第 1 ターミナル | 858px | Compress to 46% | 36px-wide chars |

---

## Helper Scripts

### `ai_utils/check_font_station.py`

Measures font dimensions and calculates scaling ratios.

```bash
.venv/Scripts/python ai_utils/check_font_station.py
```

**Output**: `ai_utils/font_station_metrics.txt`

### Quick Measurement Snippet

```python
import pygame
pygame.init()

font = pygame.font.Font('fonts/ShinGoPr6N-Medium.otf', 78)

# Single character
char_w, char_h = font.size("東")  # (78, 78)

# Full string
text_w, text_h = font.size("東京駅")  # (234, 78)

# Per-character average
avg_char_width = text_w / len(text)  # 78.0
```

---

## Visual Behavior Summary

1. **Font size 78 is intentionally oversized** - ensures short names are always full-size
2. **Spacing is added, not scaled** - when text fits, characters stay at 78×78px
3. **Compression only when necessary** - long names get horizontally compressed
4. **Even distribution** - all characters equally spaced across the available width
5. **Kanji/Kana are square** - 78×78px at size 78
6. **Latin/digits are proportional** - narrower than kanji

---

## Constants Reference

| Constant | Value | Purpose |
|----------|-------|---------|
| `S_WIDTH` | 730 | Screen width in pixels |
| `S_HEIGHT` | 420 | Screen height in pixels |
| `FONT_STATION_SIZE` | 78 | Station name font size |
| `STATION_DISPLAY_INTERVAL` | 4 | Seconds between kanji/furigana cycling |

---

## Notes for Future AI Work

1. **Always use `font.size(text)`** to get actual pixel dimensions
2. **`draw_text_given_width` handles spacing automatically** - don't pre-calculate positions
3. **Unicode handling** - use `'\uXXXX'` notation in scripts to avoid encoding issues on Windows
4. **Font file path** - relative to project root: `fonts/ShinGoPr6N-Medium.otf`
5. **Test with actual Japanese text** - kanji/kana dimensions differ from Latin

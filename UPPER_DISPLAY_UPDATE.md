# Upper LCD Display Update - 3-Mode Cycling System

**Date:** 2026-03-05

## Overview

Refactored the Upper LCD display cycling system from a dual-layer approach (language_mode + japanese_mode) to a **single 3-mode cycling system** that cycles through all display states uniformly.

---

## Changes Made

### 1. New `DisplayMode` Enum

Replaced the 2-mode `LanguageMode` enum with a 3-mode `DisplayMode` enum:

```python
class DisplayMode(IntEnum):
    """Display modes for Upper LCD - cycles through all 3 modes."""
    KANJI = 0      # Japanese kanji
    FURIGANA = 1   # Japanese furigana (phonetic)
    ENGLISH = 2    # English romanized
```

**Previous approach (removed):**
- `LanguageMode.JAPANESE` and `LanguageMode.ENGLISH`
- Separate `japanese_mode` string state (`'kanji'` or `'furigana'`)
- Two independent cycling timers and logics

**New approach:**
- Single enum with 3 modes
- Single cycling logic
- Cleaner, more maintainable code

---

### 2. Single Cycling System

**Method:** `_update_display_mode()` (renamed from `_update_language_mode()`)

**Cycle:** KANJI → FURIGANA → ENGLISH → KANJI ...

**Logic:**
```python
# Determine which modes are available for current station
available_modes = [DisplayMode.KANJI]  # Always available
if has_furigana:
    available_modes.append(DisplayMode.FURIGANA)
if has_english:
    available_modes.append(DisplayMode.ENGLISH)

# Cycle to next mode
current_idx = available_modes.index(self.display_mode)
next_idx = (current_idx + 1) % len(available_modes)
self.display_mode = available_modes[next_idx]
```

**Graceful fallback:** If a station lacks furigana or English data, that mode is skipped in the cycle.

---

### 3. Programmatically Shared Layout Configuration

KANJI and FURIGANA use the same layout (both are Japanese text). Instead of duplicating the configuration, it's defined once and reused:

```python
# Define KANJI layout once
kanji_base = {
    "_draw_prefix.font": self.font_prefix,
    "_draw_prefix.y": 5,
    "_draw_prefix.script": "japanese",
    "_draw_station_name.font": self.font_station,
    "_draw_station_name.y_offset": 5,
    "_draw_station_name.collapse": False,
    "_draw_station_name.script": "japanese",
}

# FURIGANA reuses KANJI layout (programmatically, not duplicated)
self.layouts = {
    DisplayMode.KANJI: kanji_base,
    DisplayMode.FURIGANA: kanji_base.copy(),  # ← Reuse, no duplication
    DisplayMode.ENGLISH: {
        # Different layout for English (different fonts, collapse=True, script='latin')
        ...
    },
}
```

**Benefits:**
- No duplicated configuration code
- Easy to maintain (change once, applies to both KANJI and FURIGANA)
- Clear intent: FURIGANA uses same styling as KANJI

---

### 4. Updated Helper Methods

#### `_get_prefix_display()`
```python
def _get_prefix_display(self) -> str:
    """Get prefix text based on display mode."""
    if self.display_mode == DisplayMode.ENGLISH:
        # Return English translation
        return {"次は": "Next", "ただいま": "Now stopping at", ...}[self.prefix_text]

    if self.display_mode == DisplayMode.FURIGANA:
        # Return furigana for specific prefixes
        if self.prefix_text == "次は":
            return "つぎは"

    # KANJI mode (default)
    return self.prefix_text
```

#### `_get_station_display()`
```python
def _get_station_display(self) -> str:
    """Get station name based on display mode."""
    if self.display_mode == DisplayMode.ENGLISH:
        return self.stops[curr_stop].get(DisplayMode.ENGLISH, "")
    elif self.display_mode == DisplayMode.FURIGANA:
        return self.stops[curr_stop].get("furigana", "").replace(" ", "")
    else:  # KANJI
        return self.stops[curr_stop].get("name", "").replace(" ", "")
```

---

### 5. Updated Method/Variable Names

| Old Name | New Name |
|----------|----------|
| `LanguageMode` | `DisplayMode` |
| `language_mode` | `display_mode` |
| `_update_language_mode()` | `_update_display_mode()` |
| `japanese_mode` | (removed - no longer needed) |

---

## Cycling Behavior

### Default Configuration
- **Interval:** 2 seconds (`STATION_DISPLAY_INTERVAL`)
- **Default mode:** `DisplayMode.ENGLISH` (for prototyping)
- **Cycling:** Enabled by default (`cycling_enabled = True`)

### Full Cycle Example (station with all data)

| Time | Display Mode | Prefix | Station Name |
|------|--------------|--------|--------------|
| 0-2s | KANJI | 次は | 東京 |
| 2-4s | FURIGANA | つぎは | とうきょう |
| 4-6s | ENGLISH | Next | Tōkyō |
| 6-8s | KANJI | 次は | 東京 |
| ... | ... | ... | ... |

### Partial Data Example (no English)

| Time | Display Mode | Prefix | Station Name |
|------|--------------|--------|--------------|
| 0-2s | KANJI | 次は | 東京 |
| 2-4s | FURIGANA | つぎは | とうきょう |
| 4-6s | KANJI | 次は | 東京 |
| ... | ... | ... | ... |

(ENGLISH mode is skipped since data is unavailable)

---

## Files Modified

- `preview_upper_lcd.py` - Standalone preview script for Upper LCD prototyping
- `fonts/HelveticaNeue-Medium.otf` - English font for preview script

---

## Status: PROTOTYPING IN PROGRESS

**The preview script (`preview_upper_lcd.py`) is for user testing and tuning.**

Once the display layouts (fonts, sizes, positions) are finalized by the user, the changes will be integrated into the main `display.py` file.

**Integration checklist (TODO - after user approval):**
1. Update `display.py` with `DisplayMode` enum
2. Add English fonts to `UpperDisplay.__init__()`
3. Implement 3-mode cycling logic in `_update_display_mode()`
4. Update `_get_prefix_display()` for 3-mode support
5. Update `_get_station_display()` for 3-mode support
6. Add layout configuration system with shared KANJI/FURIGANA layout
7. Integrate English translations from `translations.json` (using `DisplayMode.ENGLISH` key)

---

## Testing (Preview Script Only)

Run the preview script to verify cycling:

```bash
python preview_upper_lcd.py
```

**Controls:**
- **Page Down:** Next station
- **Page Up:** Next PA (cycles prefix: 次は → まもなく → ただいま)
- **ESC:** Quit

**Observe:**
- Display cycles through KANJI → FURIGANA → ENGLISH every 2 seconds
- Debug output shows mode switches: `[DEBUG] Display mode switched to: KANJI`
- Prefix and station name update together on mode switch

---

## Next Steps

Once the preview logic is validated, integrate these changes into the main `display.py` file:
1. Update `UpperDisplay` class with `DisplayMode` enum
2. Replace `language_mode` with `display_mode`
3. Apply the 3-mode cycling logic
4. Apply the programmatically shared layout pattern

---

## Related Documentation

- `CLAUDE.md` - Project overview and architecture
- `DATA_FORMAT.md` - JSON data format specifications (translations.json structure)
- `constants.py` - Timing constant `STATION_DISPLAY_INTERVAL = 2`

---

## Notes for Integration (When Ready)

**DO NOT integrate until user has finalized styling in preview script.**

When the user confirms the preview is ready for integration:
1. Compare `preview_upper_lcd.py` with `display.py` to identify all changes
2. Port the 3-mode system to `display.py`
3. Ensure English translations are loaded from `translations.json`
4. Test thoroughly before committing

---

## Major Refactor: Modular Display Architecture (2026-03-07)

**Status:** COMPLETED

The display system has been completely refactored from a monolithic `preview_upper_lcd.py` to a **modular, multi-train-model architecture** that supports:
- Multiple train models (E235-1000, E231-500, etc.) with different display styles
- Separate Upper LCD and Lower LCD implementations per train model
- Clean separation of display modes (KANJI, FURIGANA, ENGLISH) into independent renderer classes

---

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Factory Layer (displays/)                                  │
│  - get_train_display() returns model-specific display       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Train Model Layer (displays/train_models/e235_1000/)      │
│  - UpperDisplay (manager)                                   │
│  - LowerDisplay (manager, placeholder)                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Mode Renderer Layer (upper_lcd.py)                         │
│  - JapaneseDisplay (KANJI mode)                             │
│  - FuriganaDisplay (FURIGANA mode)                          │
│  - EnglishDisplay (ENGLISH mode)                            │
└─────────────────────────────────────────────────────────────┘
```

---

### File Structure

```
displays/
├── __init__.py              # Package entry point
│   # Exports: DisplayMode, ModeCycler, get_train_display
├── base.py                  # Shared utilities
│   - DisplayMode (IntEnum: KANJI, FURIGANA, ENGLISH)
│   - ModeCycler (handles mode switching timing)
└── train_models/
    ├── __init__.py          # Factory registry
    │   - TRAIN_DISPLAYS dict, get_train_display()
    └── e235_1000/           # E235-1000 series (directory per model)
        ├── __init__.py      # Exports: UpperDisplay, LowerDisplay
        ├── upper_lcd.py     # Upper LCD implementation
        │   - JapaneseDisplay
        │   - FuriganaDisplay
        │   - EnglishDisplay
        │   - UpperDisplay (manager)
        └── lower_lcd.py     # Lower LCD (placeholder)
            - LowerDisplay (placeholder)
```

---

### Naming Conventions

| Level | Pattern | Example |
|-------|---------|---------|
| Train model | Directory: `snake_case` | `e235_1000/`, `e231_500/` |
| Display section | File: `{section}_lcd.py` | `upper_lcd.py`, `lower_lcd.py` |
| Mode renderer | Class: `{Mode}Display` | `JapaneseDisplay`, `EnglishDisplay` |
| Manager | Class: `{Section}Display` | `UpperDisplay`, `LowerDisplay` |

**Key principle:** No redundant prefixes in class names (e.g., `JapaneseDisplay` not `E235_1000JapaneseDisplay`) because each train model has its own directory scope.

---

### Mode Renderer Classes

Each mode renderer is **self-contained** with its own fonts, positions, and drawing logic:

```python
# displays/train_models/e235_1000/upper_lcd.py

class JapaneseDisplay:
    """Upper LCD Japanese (KANJI) rendering for E235-1000."""

    def __init__(self, screen, route_data, stops):
        # E235-1000 specific fonts
        self.font_dest = pygame.font.SysFont("shingopr6nmedium", 35)
        self.dest_box_x, self.dest_box_y = 15, 50
        # ... positions, colors

    def draw_destination(self, dest_text, route_name):
        # Japanese layout: kanji dest + suffix on right
        ...

class FuriganaDisplay:
    """Upper LCD Furigana rendering for E235-1000."""
    # Inherits same structure, overrides prefix/station for furigana
    # Destination stays as kanji (same as JapaneseDisplay)

class EnglishDisplay:
    """Upper LCD English rendering for E235-1000."""

    def __init__(self, screen, route_data, stops):
        # E235-1000 specific English fonts
        self.font_dest = pygame.font.SysFont("helveticaneuebold", 33)
        self.font_suffix = pygame.font.SysFont("helveticaneuemedium", 20)  # "Bound for"
        # English-specific positions (suffix becomes prefix)
        self.suffix_x_offset = -20  # Negative = appears before dest

    def draw_destination(self, dest_text, route_name):
        # English layout: "Bound for" prefix + English dest
        # Handles multiline: "Ikebukuro&\nShinjuku"
```

---

### Manager Class (UpperDisplay)

The manager handles mode cycling and delegates all rendering:

```python
class UpperDisplay:
    """E235-1000 Upper LCD manager."""

    def __init__(self, screen, route_data, stops):
        # Create mode-specific displays
        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.furigana_display = FuriganaDisplay(screen, route_data, stops)
        self.english_display = EnglishDisplay(screen, route_data, stops)

        # Initialize mode cycler
        self.mode_cycler = ModeCycler({
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            DisplayMode.ENGLISH: self.english_display,
        })

    def update(self, current_time):
        self.mode_cycler.update(current_time)  # Handles cycling

    def draw(self, current_time_str):
        display = self.mode_cycler.get_current_display()
        display.draw_destination(...)
        display.draw_prefix(...)
        display.draw_station(...)
```

---

### Key Design Decisions

1. **Duplication OK:** Each mode renderer defines its own fonts/positions. JapaneseDisplay and FuriganaDisplay are ~90% similar but separate for flexibility.

2. **No shared mode renderers across train models:** E235-1000's `JapaneseDisplay` is completely independent from future E231-500's `JapaneseDisplay`. Different trains have different layouts.

3. **Destination/Suffix behavior:**
   - **KANJI/FURIGANA:** Destination stays as kanji, suffix (ゆき/方面) on right
   - **ENGLISH:** Destination shows English, "Bound for" prefix appears before destination

4. **Centralized translations:** All displays load from `data/translations.json` (station names, destinations, prefixes). Prefix translations (次は/まもなく/ただいま → English/furigana) are defined inline in the display classes.

5. **Graceful fallback:** If station lacks English/furigana data, that mode is skipped in cycling

---

### Usage Examples

```python
# Option 1: Factory (for Upper LCD)
from displays import get_train_display
display = get_train_display("e235_1000", screen, route_data, stops)
display.update()
display.draw()

# Option 2: Direct import (gives both Upper and Lower)
from displays.train_models.e235_1000 import UpperDisplay, LowerDisplay
upper = UpperDisplay(screen, route_data, stops)
lower = LowerDisplay(screen, route_data, stops)
```

---

### Adding New Train Model

1. Create `displays/train_models/e231_500/` directory
2. Copy `upper_lcd.py` → modify fonts/positions for E231-500
3. Implement `lower_lcd.py` with LowerDisplay
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay`
5. Register in `displays/train_models/__init__.py`:
   ```python
   TRAIN_DISPLAYS["e231_500"] = E231_500UpperDisplay
   ```

---

### Files Modified/Created

**Created:**
- `displays/__init__.py` - Package entry
- `displays/base.py` - DisplayMode, ModeCycler
- `displays/train_models/__init__.py` - Factory
- `displays/train_models/e235_1000/__init__.py` - Module exports
- `displays/train_models/e235_1000/upper_lcd.py` - Upper LCD implementation
- `displays/train_models/e235_1000/lower_lcd.py` - Lower LCD placeholder

**Updated:**
- `preview_upper_lcd.py` - Now uses new architecture

**Deleted:**
- `displays/train_models/e235_1000.py` - Replaced by directory structure

---

### Testing

```bash
# Run preview script (uses new architecture)
uv run preview_upper_lcd.py

# Test imports
python -c "from displays import get_train_display, DisplayMode; print('OK')"
```

**Controls:**
- Page Down: Next station
- Page Up: Next PA
- ESC: Quit

---

### Migration Path to main.py

The current `main.py` and `display.py` still use the old monolithic structure. When ready to integrate:

1. Replace `display.py` UpperDisplay with `displays.train_models.e235_1000.UpperDisplay`
2. Update `main.py` to use factory: `get_train_display(train_model, ...)`
3. Remove old display cycling code from `display.py`
4. Update CLAUDE.md with new architecture

---

## Related Documentation

- `CLAUDE.md` - Project overview (updated with new file structure)
- `DATA_FORMAT.md` - JSON data format specifications
- `displays/base.py` - ModeCycler implementation details

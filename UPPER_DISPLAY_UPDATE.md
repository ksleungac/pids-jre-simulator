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

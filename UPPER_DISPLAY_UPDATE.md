# Upper LCD Display System - Modular Architecture

**Date:** 2026-04-25 (Updated)

**Status:** COMPLETED & INTEGRATED

> **Companion doc:** [LOWER_DISPLAY_UPDATE.md](LOWER_DISPLAY_UPDATE.md). Sections marked **🔁 Shared with LOWER** below are duplicated in both files — keep them in sync when editing.

---

## Overview

The Upper LCD display system uses a **modular, multi-train-model architecture** with **mode cycling** (KANJI → FURIGANA → ENGLISH). The system is fully integrated into the main application.

**Key features:**
- Multiple train models (E235-1000, future E231-500, etc.) with different display styles
- Display mode cycling every 2 seconds (English mode currently disabled until fonts verified)
- Graceful fallback when furigana/English data is unavailable
- English train type display with optional `english_short` for narrow boxes
- Centralized translations in `data/translations.json` and `data/train_types.json`
- **Font loading:** Uses `pygame.font.Font()` with direct file paths for cross-platform compatibility (avoids Windows font registry issues on non-English systems)
- **JSON loading:** Uses `sys.executable` for path resolution in PyInstaller exe (avoids temp folder issues)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Factory Layer (displays/)                                  │
│  - get_train_display() returns model-specific display       │
│  - DisplayMode enum (KANJI, FURIGANA, ENGLISH)              │
│  - ModeCycler (handles mode switching timing)               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Train Model Layer (displays/train_models/e235_1000/)      │
│  - UpperDisplay (manager)                                   │
│  - LowerDisplay (placeholder - not yet implemented)         │
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

## File Structure

```
displays/
├── __init__.py              # Package entry point
│   # Exports: DisplayMode, ModeCycler, get_train_display
├── base.py                  # Shared utilities
│   - DisplayMode (IntEnum: KANJI=0, FURIGANA=1, ENGLISH=2)
│   - ModeCycler (handles mode switching timing)
├── utils.py                 # Shared drawing utilities
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

## Naming Conventions

| Level | Pattern | Example |
|-------|---------|---------|
| Train model | Directory: `snake_case` | `e235_1000/`, `e231_500/` |
| Display section | File: `{section}_lcd.py` | `upper_lcd.py`, `lower_lcd.py` |
| Mode renderer | Class: `{Mode}Display` | `JapaneseDisplay`, `EnglishDisplay` |
| Manager | Class: `{Section}Display` | `UpperDisplay`, `LowerDisplay` |

**Key principle:** No redundant prefixes in class names (e.g., `JapaneseDisplay` not `E235_1000JapaneseDisplay`) because each train model has its own directory scope.

---

## Mode Renderer Design

Each mode renderer (`JapaneseDisplay`, `FuriganaDisplay`, `EnglishDisplay`) is **self-contained**:

- **Fonts** are shared as class members (defined in `__init__`) - use `pygame.font.Font()` with file paths
- **Position constants** are inlined in each method (not shared)
- **Destinations** stay as kanji in KANJI/FURIGANA modes (IRL behavior)
- **English mode** uses "Bound for" prefix + English destination

### Example: JapaneseDisplay

```python
class JapaneseDisplay:
    """Upper LCD Japanese (KANJI) rendering for E235-1000."""

    def __init__(self, screen, route_data, stops):
        # Fonts are shared (defined once in __init__) - load from fonts/ folder
        self.font_type_bold = pygame.font.Font("fonts/ShinGoPr6N-Heavy.otf", 26)
        self.font_type_bold.set_bold(True)
        self.font_type_bold.set_italic(True)
        self.font_dest = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
        self.font_prefix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 25)
        self.font_station = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 78)
        self.font_clock = pygame.font.Font("fonts/HelveticaNeue-Roman.otf", 26)
        self.font_suffix = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 18)

    def draw_station(self, station_text: str) -> None:
        # Position constants are inline (not shared)
        name_x = int(S_WIDTH * 0.40)
        max_width = S_WIDTH * 0.54
        # ... drawing logic
```

### Font Loading Note

All mode renderers use `pygame.font.Font()` with direct file paths instead of `pygame.font.SysFont()`:
- **Reason:** `SysFont()` scans Windows font registry, which can fail on non-English Windows systems (Chinese, Japanese locale)
- **Solution:** Load fonts directly from `fonts/` folder using relative paths
- **Distribution:** `fonts/` folder must be placed alongside the exe at runtime

---

## 3-Mode Cycling System

### DisplayMode Enum

```python
class DisplayMode(IntEnum):
    """Display modes for Upper LCD - cycles through all 3 modes."""
    KANJI = 0      # Japanese kanji
    FURIGANA = 1   # Japanese furigana (phonetic)
    ENGLISH = 2    # English romanized (Hepburn with macrons)
```

### Cycling Behavior

| Time | Display Mode | Prefix | Station Name |
|------|--------------|--------|--------------|
| 0-2s | KANJI | 次は | 東京 |
| 2-4s | FURIGANA | つぎは | とうきょう |
| 4-6s | ENGLISH | Next | Tōkyō |
| 6-8s | KANJI | 次は | 東京 |

**Note:** All three modes are currently active in the upper. (English was temporarily disabled in 2026-03-14 during the font-loading migration, and re-enabled once `pygame.font.Font` file-path loading was confirmed working on non-English Windows locales.)

**Graceful fallback:** If a station lacks furigana or English data, that mode is skipped in the cycle.

### JSON Loading (PyInstaller exe compatibility)

The `load_json_relative()` function uses `sys.executable` for path resolution when running as a compiled exe:

```python
def get_base_dir() -> Path:
    """Get base directory - works for both dev and PyInstaller exe."""
    if getattr(sys, "frozen", False):
        # Running as compiled exe - use exe directory
        return Path(sys.executable).parent
    else:
        # Running as script - go up 4 levels from this file
        return Path(__file__).parent.parent.parent.parent
```

**Reason:** In PyInstaller one-file exe, `__file__` points to temp extraction folder (`_MEIxxxxx`), not the actual exe location. Using `sys.executable` ensures JSON files are loaded from the exe directory at runtime.

---

## Data Files

### translations.json (Station Names)

```json
{
    "東京": {
        "furigana": "とうきょう",
        "english": "Tōkyō"
    },
    "品川・東京": {
        "english": "Shinagawa&\nTōkyō"
    }
}
```

- Keys are Japanese station names (kanji/kana)
- `english` field uses Hepburn romanization with macrons (ō, ū)
- Compound destinations use `"&\n"` for multiline (e.g., `"Shinagawa&\nTōkyō"`)

### train_types.json (Train Type Names)

```json
{
    "快速": {
        "english": "Rapid"
    },
    "中央特快": {
        "english": "Chūō Special Rapid",
        "english_short": "Chūō Sp. Rapid"
    }
}
```

- `english_short` is optional - used for narrow display boxes
- Falls back to `english` if `english_short` doesn't exist
- Falls back to Japanese train type if neither exists

---

## Manager Class (UpperDisplay)

The manager handles mode cycling and delegates rendering:

```python
class UpperDisplay:
    """E235-1000 Upper LCD manager."""

    def __init__(self, screen, route_data, stops):
        # Create mode-specific displays
        self.japanese_display = JapaneseDisplay(screen, route_data, stops)
        self.furigana_display = FuriganaDisplay(screen, route_data, stops)
        self.english_display = EnglishDisplay(screen, route_data, stops)

        # Initialize mode cycler (all three modes active)
        self.mode_cycler = ModeCycler({
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            DisplayMode.ENGLISH: self.english_display,
        }, default_mode=DisplayMode.KANJI)

        # Load translations (uses sys.executable for exe compatibility)
        self.translations = load_json_relative("data/translations.json")
        self.train_types = load_json_relative("data/train_types.json")

    def set_state(self, curr_stop: int, cnt_pa: int) -> None:
        """Update display state (current stop and PA count)."""
        self.curr_stop = curr_stop
        self.cnt_pa = cnt_pa

    def update(self, current_time: float = None) -> None:
        """Update mode cycling."""
        self.mode_cycler.update(current_time)

    def draw(self, current_time_str: str = None) -> None:
        """Draw the upper display with current mode's renderer."""
        display = self.mode_cycler.get_current_display()
        display.draw_train_type(...)
        display.draw_destination(...)
        display.draw_prefix(...)
        display.draw_station(...)
        display.draw_clock(...)
```

---

## Integration with Main Application

### app.py

```python
from displays.train_models.e235_1000 import UpperDisplay, LowerDisplay

class PASimulator:
    def __init__(self, work_dir: str, route_data: Optional[Dict] = None):
        # ...
        self.upper = UpperDisplay(self.screen, self.route_data, self.stops)
        # Lower shares the upper's mode_cycler — modes stay in lockstep.
        self.lower = LowerDisplay(self.screen, self.route_data, self.stops, self.upper.mode_cycler)
        self.lower.set_state(self.state)

    def run(self) -> None:
        while self.running:
            timestamp = time.time()

            # Advance skip animation (state-machine logic on AppState).
            self.state.update_skip_progress(timestamp)

            # Update and draw upper display
            self.upper.update(timestamp)
            self.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))

            # Draw lower display
            self.lower.draw(timestamp)

            pygame.display.flip()
```

### Key Changes from Legacy display.py

| Old Method | New Method |
|------------|------------|
| `draw_init()` | `set_state()` + `draw()` |
| `draw_clock(timestamp)` | `update(timestamp)` + `draw(time_str)` |
| `draw_current_station()` | `set_state()` + `draw()` |
| State in `self.state` | Internal state + `set_state()` API |

---

## Usage Examples

```python
# Option 1: Direct import (recommended for single train model)
from displays.train_models.e235_1000 import UpperDisplay
upper = UpperDisplay(screen, route_data, stops)
upper.set_state(curr_stop=0, cnt_pa=0)
upper.update(timestamp)
upper.draw()

# Option 2: Factory (for multiple train models)
from displays import get_train_display
display = get_train_display("e235_1000", screen, route_data, stops)
display.update(timestamp)
display.draw()
```

---

## Adding New Train Model

1. Create `displays/train_models/{model_name}/` directory
2. Copy `upper_lcd.py` → modify fonts/positions for the new train model
3. Implement `lower_lcd.py` with `LowerDisplay`
4. Create `__init__.py` exporting `UpperDisplay`, `LowerDisplay`
5. Register in `displays/train_models/__init__.py`:
   ```python
   TRAIN_DISPLAYS["{model_name}"] = {ModelName}UpperDisplay
   ```

---

## Element Clear-Background Convention

Every upper-LCD region has a declared **confinement** — a rectangle inside which everything the region draws must visually land. The clear rect is not special; it's just one of the things drawn for the region (alongside glyphs, decorations). The same containment rule applies to all of them.

### The principle

> Anything a region draws — bg fill, glyph pixels, shapes — must visually stay inside that region's confinement.

That's it. Clear rect ⊆ confinement. Glyph visible pixels ⊆ confinement. Period.

### Why declare confinements at all

- **Correctness**: every frame's `pygame.draw.rect` for a region's bg should respect this; otherwise it clobbers a neighbor's bg.
- **Debug visibility**: with `--debug-grid` enabled, each region's clear paints in a region-specific tint (red dest, blue prefix, etc.). Anything one region draws that lands on a *neighbor's tint* is a containment violation, surfaced visually.
- **Cross-mode parity**: the three mode renderers (Japanese / Furigana / English) share the same confinement per element. Internal content layout can differ; the boundary doesn't.

### Two checks: D1 (cheap pre-check) and D2 (the rule)

Pygame font surfaces have **leading** — empty (transparent) pixels above the visible glyph caps. Surface_top is at `blit_y`, but visible glyph caps appear `~10–15px below` for big fonts. This causes the two-check distinction:

- **D1 (surface containment, analytical)**: `blit_y ≥ confinement.top`. If true, no pixel — visible or transparent — is rendered above confinement.top. Sufficient for compliance, no probing needed.
- **D2 (visible-pixel containment, empirical)**: actual visible glyph caps land at y ≥ confinement.top. Requires probing or per-font knowledge of leading. Tighter — allows surfaces to extend above confinement *as long as the leading absorbs the overshoot* and no painted pixel actually crosses.

**D2 is the rule.** D1 is a useful pre-check: if it passes, you're done. If D1 fails, that's a *signal to probe*, not an automatic violation — the leading might absorb the overshoot. **Pixel-perfect tuning often requires D2** (e.g., 78pt kanji surfaces extend into the prefix's y-range, but visible caps stay at y≥35 thanks to leading; D1 would forbid the IRL-accurate font size unnecessarily).

### Probing methodology (gotcha)

When pixel-probing a region's glyphs for containment, **isolate the region** so that neighboring regions' content can't masquerade as the target's:

- Use a scenario where the neighbor is empty or short. For station containment vs prefix, test with the short "Next" prefix (x≤280) — that leaves x=302+ purely station territory. The long "Now stopping at" prefix overlaps station's x-range, and *its* text glyphs landing at y=20-something in the prefix-text overlap zone get mistaken for station glyphs.
- Or probe at "exclusive x ranges" — for station, that's x=522–570 (between prefix right edge and clock left edge) and x=650–686 (right of clock). Any non-bg pixel in these strips at y<confinement.top must be the target region's drawing.
- I (Claude) made the mistake once this session: probed at x=315–320 with PA=2, read the prefix's "Now stopping at" text pixels as if they were the station's "Narita Airport" line 1 caps, and reported a false D2 violation at 42pt. Don't repeat this.

### Other rules

- All three mode renderers clear the **same** confinement for the same element. Internal layout can differ per mode; the boundary doesn't.
- Sub-text-bg parameters (e.g., `font.render(text, True, fg, bg)`) inside a region should pass `_bg("<same region>")` as `bg` so they don't punch holes in the tint when debug-grid is on.
- A region's clear rect must not extend into a neighbor's confinement. The `station` clear is clamped to `band_bottom_y=35` (top) and `UPPER_HEIGHT=117` (bottom) for this reason — same clamp pattern duplicated in all three mode renderers' `draw_station`.

### Pygame rendering gotchas (recurring review false positives)

Two facts about pygame text rendering that look like bugs to a fresh reviewer:

- **Transparent leading does NOT clobber.** `font.render(text, True, color)` (no bg arg) returns an SRCALPHA surface. Default `blit` alpha-blends; transparent leading pixels don't overwrite the destination. So a station-glyph surface starting above `band_bottom_y` is safe — the prefix text underneath survives in the leading strip.
- **`font.get_height()` is smaller than folk wisdom suggests** — roughly `pt_size × 0.92` for both HelveticaNeue-Medium and ShinGoPr6N-Medium, NOT `pt_size × 1.2`. Probed examples: 24pt → 22, 78pt → 78. **Probe via `pygame.font.Font(...).get_height()` before claiming overflow.**

### Current state (E235-1000 upper, post-2026-04-25)

- All 4 station modes (Kanji 78pt, Furigana 78pt, English 1-line 75pt, English 2-line 42pt) comply with **D2**: visible glyph caps land at y≥35 in every mode.
- All 4 station modes' **clear rects** are clamped to `(302, 35, 384, ≤82)` — they fit inside the declared station confinement.
- The Region Map's `station = (302, 35, 384, 82)` entry is now truthful for both bg fills and visible glyphs, even though some modes' surface bounds (kanji `name_y=34`) technically extend 1px above pre-clamp. The clamp + leading absorption keep visible compliance.

### Debug-grid mode

`uv run preview_display.py --debug-grid` flips `DEBUG_GRID` in `upper_lcd.py` so every region's `_bg("<region>")` returns its assigned tint instead of `DARK_BG`. Keys live in `_DEBUG_COLORS`. Adding a new region: register key in `_DEBUG_COLORS` AND in the Region Map comment. Forgetting either keeps debug-grid silent on the new region.

### Region map

Bounds + drawn-by + debug color for every region live as a comment block at the top of `displays/train_models/e235_1000/upper_lcd.py`, alongside `_DEBUG_COLORS`. Per-train-model — different train models will have different layouts, so the map stays with the code, not in this doc.

History note: Pre-2026-04-25, the English `draw_destination` had no clear rect at all, and Japanese/Furigana cleared only their narrow 150x35 text box. Bug only surfaced when 2-line station rendering revealed a similar clobbering issue elsewhere — prompted unifying the territory definitions across modes.

---

## Design Decisions

1. **Duplication OK:** Mode renderers may have ~90% similar code, but are separate for flexibility. Different trains may need different layouts.

2. **No shared mode renderers across train models:** E235-1000's `JapaneseDisplay` is independent from future E231-500's `JapaneseDisplay`.

3. **Position constants inlined:** Position values are local to each method (not shared as `self.xxx`), making it clear they're method-specific.

4. **Fonts shared:** Fonts are defined once in `__init__` and reused across methods.

5. **Destination always kanji:** In KANJI/FURIGANA modes, destination stays as kanji (IRL behavior).

6. **English suffix becomes prefix:** In ENGLISH mode, "Bound for" appears before the destination.

7. **Centralized translations:** All displays load from `data/translations.json` and `data/train_types.json`.

---

## Files

**Core Module Files:**
- `displays/__init__.py` - Package entry point
- `displays/base.py` - DisplayMode enum, ModeCycler class
- `displays/utils.py` - Shared drawing utilities
- `displays/train_models/__init__.py` - Factory registry
- `displays/train_models/e235_1000/__init__.py` - Module exports
- `displays/train_models/e235_1000/upper_lcd.py` - Upper LCD implementation
- `displays/train_models/e235_1000/lower_lcd.py` - Lower LCD implementation (see [LOWER_DISPLAY_UPDATE.md](LOWER_DISPLAY_UPDATE.md))

**Data Files:**
- `data/translations.json` - Station names (furigana, english)
- `data/train_types.json` - Train type translations

**Fonts Files:**
- `fonts/ShinGoPr6N-Medium.otf` - Japanese text (destinations, stations, prefixes)
- `fonts/ShinGoPr6N-Heavy.otf` - Train type (bold/italic)
- `fonts/HelveticaNeue-Roman.otf` - English clock, Roman text
- `fonts/HelveticaNeue-Medium.otf` - English destinations, prefixes
- `fonts/HelveticaNeue-Bold.otf` - English station names (large) — `.otf` (the older `.ttf` cut had macron artifacts at large sizes)

**Preview Script:**
- `preview_display.py` - Standalone preview for testing (uses new architecture)

---

## Distribution (PyInstaller exe)

**Folder structure - folders must be alongside exe at runtime:**

```
your-folder/
├── JRE-PA-Simulator.exe
├── fonts/
├── data/
│   ├── translations.json
│   └── train_types.json
└── audio/
    ├── chuo/
    ├── yamanote/
    └── ...
```

**Build command:**
```bash
uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm
```

**Key notes:**
- `--console` enabled for error visibility on non-English Windows systems
- Fonts/data/audio not bundled inside exe - loaded from runtime directory
- Uses `sys.executable` for path resolution (not `__file__`) to handle PyInstaller temp folder

---

## Testing

```bash
# Run preview script
uv run preview_display.py

# Test imports
python -c "from displays import get_train_display, DisplayMode; print('OK')"
python -c "from displays.train_models.e235_1000 import UpperDisplay; print('OK')"
```

**Controls (preview script):**
- Page Down: Next station
- Page Up: Next PA
- ESC: Quit

**Observe:**
- Display cycles through KANJI → FURIGANA every 2 seconds (English currently disabled)
- Prefix and station name update together on mode switch
- English train type uses `english_short` if available (for narrow box)

---

## Changes Log

### 2026-04-25
- **Lower LCD refactored** into `displays/train_models/e235_1000/lower_lcd.py` mirroring this architecture (see [LOWER_DISPLAY_UPDATE.md](LOWER_DISPLAY_UPDATE.md)). Legacy `display.py` deleted.
- **English mode re-enabled** in upper (was temporarily disabled during the SysFont migration — file-path font loading verified, no fallback needed).
- **`pygame.display.flip()`** moved out of the lower display into `app.run()` so both displays paint into the same frame.
- **Integration section** updated to reflect the new `LowerDisplay` constructor signature (takes `mode_cycler` shared with upper) and the `state.update_skip_progress` step in the main loop.

### 2026-03-14
- **Font loading fix:** Changed all `pygame.font.SysFont()` to `pygame.font.Font()` with direct file paths to fix crashes on non-English Windows systems (Chinese locale)
- **JSON loading fix:** Updated `load_json_relative()` to use `sys.executable` instead of `__file__` for PyInstaller exe compatibility
- **English mode disabled:** Temporarily disabled English display mode until fonts are verified
- **Build command updated:** Changed from `--windowed` to `--console` for error visibility

### 2026-03-11
- Initial modular architecture implementation
- 3-mode display cycling (KANJI → FURIGANA → ENGLISH)
- Integration with main application

---

## Related Documentation

- `CLAUDE.md` - Project overview (updated with new architecture)
- `DATA_FORMAT.md` - JSON data format specifications
- `displays/base.py` - ModeCycler implementation details
- `data/translations.json` - Station translation database
- `data/train_types.json` - Train type translation database

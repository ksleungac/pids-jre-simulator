# Upper LCD Display System - Modular Architecture

**Date:** 2026-03-14 (Updated)

**Status:** COMPLETED & INTEGRATED

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

**Note:** English mode is currently disabled (as of 2026-03-14) until font loading is verified. Default mode is KANJI with KANJI → FURIGANA cycling.

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

        # Initialize mode cycler (ENGLISH disabled until fonts verified)
        self.mode_cycler = ModeCycler({
            DisplayMode.KANJI: self.japanese_display,
            DisplayMode.FURIGANA: self.furigana_display,
            # DisplayMode.ENGLISH: self.english_display,  # DISABLED
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
from displays.train_models.e235_1000 import UpperDisplay
from display import LowerDisplay  # Old display.py until LowerDisplay is refactored

class PASimulator:
    def __init__(self, work_dir: str, route_data: Optional[Dict] = None):
        # ...
        self.upper = UpperDisplay(self.screen, self.route_data, self.stops)
        self.lower = LowerDisplay(self.screen, self.route_data, self.state, self.stops)

    def run(self) -> None:
        while self.running:
            timestamp = time.time()

            # Update and draw upper display
            self.upper.update(timestamp)
            self.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))

            # Update lower display
            self.lower.show_stops(current_time=timestamp)
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
- `displays/train_models/e235_1000/lower_lcd.py` - Lower LCD placeholder

**Data Files:**
- `data/translations.json` - Station names (furigana, english)
- `data/train_types.json` - Train type translations

**Fonts Files:**
- `fonts/ShinGoPr6N-Medium.otf` - Japanese text (destinations, stations, prefixes)
- `fonts/ShinGoPr6N-Heavy.otf` - Train type (bold/italic)
- `fonts/HelveticaNeue-Roman.otf` - English clock, Roman text
- `fonts/HelveticaNeue-Medium.otf` - English destinations, prefixes
- `fonts/HelveticaNeueBold.ttf` - English station names (large)

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

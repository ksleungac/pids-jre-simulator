# PA Simulator - Data Format Specification

## Overview

This document defines the JSON data formats used by the PA Simulator for route configurations and station databases.

---

## File Structure

```
project_root/
├── data/
│   ├── translations.json        # Central translation database (furigana, english)
│   ├── train_types.json         # Train type English translations (with optional english_short)
│   └── stations.json            # Station metadata (3-letter codes; more fields over time)
└── audio/
    └── [line]/                  # Line name (e.g., chuo, keihin, saikyo)
        └── [diagram]/           # Train diagram folder (e.g., 1349F, 759K)
            └── route.json       # Route configuration
```

---

## translations.json Format (Central Translation Database)

**Location:** `data/translations.json` (project root)

### Purpose

Centralized translation lookup for **any Japanese text** used in the simulator:
- Station names (for furigana/english cycling display)
- UI text (prefixes, suffixes)
- Any other Japanese text needing translation

### Structure

```json
{
    "東京": {
        "furigana": "とうきょう",
        "english": "Tokyo"
    },
    "新宿": {
        "furigana": "しんじゅく",
        "english": "Shinjuku"
    },
    "次は": {
        "furigana": "つぎは",
        "english": "Next"
    },
    "ゆき": {
        "furigana": "ゆき",
        "english": "Bound"
    }
}
```

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Japanese text]` | Any Japanese text needing translation | `東京`, `新宿`, `次は` |

**Important:** Keys are the **raw Japanese text** (kanji/kana), not station codes.

### Lookup Rules (in app.py)

1. **Direct lookup by Japanese text** (e.g., `"東京"` → `translations.json["東京"]`)
2. No fallback needed - station name is always available from route.json

### Value Fields

| Field | Description |
|-------|-------------|
| `furigana` | Hiragana reading for the text |
| `english` | English translation/romanization |

### Compound Destinations (e.g., Yamanote Line)

For routes that display multiple destinations (like 品川・東京), use the `&` character as a separator with a newline after it for multi-line display:

```json
{
    "品川・東京": {
        "english": "Shinagawa&\nTokyo"
    },
    "東京・上野": {
        "english": "Tokyo&\nUeno"
    }
}
```

**Format:** `"StationA&\nStationB"` - The `&` indicates a line break point. No space before `&`.

**Note:** Compound destinations typically don't need `furigana` field as they are used for English display only (not for furigana cycling on the upper LCD).

### English Translation Convention (Hepburn Romanization)

English translations use **modified Hepburn romanization with macrons** to indicate long vowels:

| Long Vowel | Source | Example |
|------------|--------|---------|
| **ō** | おう, おお | 東京 → T**ō**ky**ō**, 大宮 → **Ō**miya |
| **ū** | う, うう, うう | 越中島 → Etch**ū**jima |

**Modified Hepburn notes:**
- Macrons (¯) indicate long vowels
- Some spellings follow IRL JR East usage (e.g., "Etchūjima" not "Ecchūjima")
- Not all vowels get macrons - only true long vowels (e.g., Ebisu stays as-is)

**Examples:**
```json
{
    "東京": { "english": "Tōkyō" },
    "大宮": { "english": "Ōmiya" },
    "大久保": { "english": "Ōkubō" },
    "十条": { "english": "Jūjō" },
    "越中島": { "english": "Etchūjima" },
    "港南台": { "english": "Kōnandai" }
}
```

### Stop-Level Destination Override

Routes can override the route-level `dest` at individual stops using the `dest` field:

```json
{
    "name": "田町",
    "pa": ["3"],
    "dest": "東京・上野",  // Overrides route-level destination
    "time": 3
}
```

This allows displaying different destinations at different points along the route (useful for circular lines like Yamanote).

**Implementation behavior:**
- The `dest` value is read from the current stop when drawing the upper display
- If no stop-level `dest` exists, falls back to route-level `dest`
- Destination always displays as kanji (no furigana cycling)
- The `dest` value is looked up in `data/translations.json` for English display

**Yamanote Line Example:**
The Yamanote line uses stop-level `dest` overrides to show changing destinations as the train travels around the loop:

| Station | Displayed Dest |
|---------|----------------|
| 大崎 (start) | 品川・東京 (route-level) |
| 田町 | 東京・上野 |
| 神田 | 上野・池袋 |
| 鶯谷 | 池袋・新宿 |
| 目白 | 新宿・渋谷 |
| 代々木 | 渋谷・品川 |
| 恵比寿 | 品川・東京 |

This matches real-world behavior where the "bound for" destination changes based on current position.

### Benefits of Centralized Design

- **No duplication**: Station like 東京 appear once, even though used by multiple lines
- **Separation of concerns**: Translations separate from line-specific data
- **Easy maintenance**: Update translation in one place
- **Extensible**: Can add any Japanese text, not just station names
- **Destination furigana**: `dest` in route.json is automatically looked up in translations.json (no `dest_furigana` field needed)

---

## train_types.json Format (Train Type Translations)

**Location:** `data/train_types.json` (project root)

### Purpose

English translations for train type names (列車種別). Unlike stations, train types do **not** have furigana since they are only displayed in kanji or English.

### Structure

```json
{
    "快速": {
        "english": "Rapid"
    },
    "中央特快": {
        "english": "Chūō Special Rapid",
        "english_short": "Chūō Sp. Rapid"
    },
    "普通": {
        "english": "Local"
    },
    "内回り": {
        "english": "Inner Loop"
    },
    "外回り": {
        "english": "Outer Loop"
    }
}
```

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Japanese train type]` | Any train type name | `快速`, `普通`, `内回り`, `外回り` |

### Value Fields

| Field | Description | Required |
|-------|-------------|----------|
| `english` | Full English translation | Yes |
| `english_short` | Abbreviated version for narrow display boxes | No |

### english_short Fallback

The `english_short` field is optional and used for narrow train type display boxes (150px wide on E235-1000):

1. Check for `english_short` first (if available)
2. Fall back to `english` if `english_short` doesn't exist
3. Fall back to Japanese kanji if neither exists

**Example:**
```json
{
    "中央特快": {
        "english": "Chūō Special Rapid",
        "english_short": "Chūō Sp. Rapid"
    }
}
```

- Full English (18 chars): "Chūō Special Rapid" - may not fit in narrow box
- Short English (15 chars): "Chūō Sp. Rapid" - fits comfortably

### English Translation Convention

Train type English translations follow the same **modified Hepburn romanization with macrons** as station names:

| Train Type | English | Notes |
|------------|---------|-------|
| 中央特快 | Chūō Special Rapid | "ō" for long vowel |
| 通勤特快 | Commuter Special Rapid | No macrons needed |
| 各駅停車 | Local | Standard translation |

---

## stations.json Format (Station Metadata)

**Location:** `data/stations.json` (project root)

### Purpose

Line-independent station metadata, keyed by Japanese station name. Shares the same key space as `translations.json` but separated by concern:
- `translations.json` → display text (furigana, english)
- `stations.json` → operational/physical facts (3-letter codes; future: transfer lines, platforms, etc.)

A station has a single entry even if it appears on multiple routes (e.g., 秋葉原 is on both Yamanote and Keihin-Tohoku — one row).

### Structure

```json
{
    "東京": {"code_3": "TYO"},
    "秋葉原": {"code_3": "AKB"},
    "武蔵小杉": {"code_3": "MKG"}
}
```

### Fields

| Field | Description |
|-------|-------------|
| `code_3` | JR East 3-letter station code. Only 22 stations total have one — the rule is "3+ JR East systems converge" (with 浜松町 and 高輪ゲートウェイ as explicit exceptions). Absent on all other stations. |

### Notes

- Not every station needs an entry. Only add rows for stations with metadata to record.
- Stations without a 3-letter code simply omit the `code_3` key.
- 3-letter Roman codes (`code_3`) are distinct from 2-character katakana telegraph codes (電略) — the latter is a separate internal JR system and is not stored here.

---

## route.json Format

**Location:** `audio/[line]/[diagram]/route.json`

### Route-Level Fields

```json
{
    "route": "路線名",              // Route name (e.g., 中央線快速電車，埼京線)
    "color": [R, G, B],            // Main route color for UI elements
    "contrast_color": [R, G, B],   // Contrast color for pointers/highlights
    "type_color": [R, G, B],       // Color for train type text (optional, default: black)
    "type": "列車種別",             // Train type (e.g., 快速，普通，各駅停車)
    "dest": "終点"                  // Final destination (kanji) - furigana loaded from data/translations.json
}
```

### Stop-Level Fields

Each stop in the `stops` array:

```json
{
    "name": "駅名",                 // Station name (kanji)
    "pa": ["1", "2"],              // PA track numbers (empty array = no announcement)
    "sta": ["JC01", "JC01_ALT"],   // STA audio filename(s) without .mp3 extension
    "sta_code": "JC01",            // JR official station numbering code (or null)
    "sta_cut": 10,                 // STA melody: seconds where melody stops & door chime starts
    "time": 3                      // Travel time to next station (minutes, 0 for first station)
}
```

**Note:** The `time` field represents the scheduled travel time in minutes. The lower LCD displays this value with real-time countdown:
- Countdown starts when train departs (first PA of segment)
- Display shows `time - elapsed_minutes` (floor division, only decrements when full minute passes)
- Minimum display value is "1" (never shows 0)
- On last PA of current station, display forces to "1" (arriving now)
- Configurable via `TIME_SCALE` constant (60 = real-time, lower = faster)

### Field Details

#### `pa` Array (PA Announcements)

| Value | Meaning |
|-------|---------|
| `[]` | No PA announcement - train doesn't stop OR first station |
| `["tokyo_dep"]` | Single PA track using filename |
| `["tokyo_dep", "shinagawa_arr"]` | Multiple PA tracks using filenames |

**PA Track Filename Convention:**

The `pa` array contains **descriptive filenames** (without `.mp3` extension) that map directly to audio files in the `pa/` folder:

- Track reference `"tokyo_dep"` → `audio/[line]/[diagram]/pa/tokyo_dep.mp3`
- Allows meaningful names like `{station}_{dep|arr}` instead of sequential numbers
- Common pattern:
  - `{station}_dep` = Departure announcement (played after departing, announcing next station)
  - `{station}_arr` = Arrival announcement (played when approaching station)

**Example:**
```json
{
    "name": "品川",
    "pa": ["shimbashi_dep", "shinagawa_arr"],  // shimbashi_dep.mp3, shinagawa_arr.mp3
    "sta": ["JT03_SGW"],
    "sta_cut": 17,
    "time": 5,
    "sta_code": "JT03"
}
```

**Skipping Stations:**
Stations with empty `pa: []` are skipped automatically (train passes through without stopping). The `time` field should still be set for proper countdown behavior between active stops.

```json
{
    "name": "辻堂",
    "pa": [],        // Empty = train skips this station
    "sta": ["JT09"],
    "sta_cut": 14,
    "time": 3,       // Still countdowns, but doesn't stop
    "sta_code": "JT09"
}
```

#### `sta` Array (STA Melodies)

| Value | Meaning |
|-------|---------|
| `[]` or `[""]` | No STA melody for this station |
| `["JC01"]` | Single STA audio file |
| `["JC01", "JC01_1"]` | Multiple STA audio files (variants) |

**Note:** The `sta` field contains actual audio filenames (without `.mp3`). It may include suffixes like `_OSK`, `_SBY`, `_TYO` for disambiguation.

#### `sta_code` Field (Station Numbering)

| Value | Meaning |
|-------|---------|
| `"JC01"` | Official JR East station code (used for line-specific data lookup) |
| `null` | Station has no official code (e.g., Kawagoe Line stations) |

**Format:** `[Line Prefix][Number]` (e.g., `JC01`, `JK47`, `JA08`)
- Line prefixes: JC (Chuo), JK (Keihin-Tohoku), JA (Saikyo), JE (Keiyo), JY (Yamanote), JT (Tokaido)
- No 3-letter suffixes in `sta_code` (those go in `sta` field only)
- **Note:** `sta_code` is route-local — used by `upper_lcd.py` to render the station code badge. Line-independent station metadata lives in `data/stations.json`.

#### `sta_cut` Field

| Value | Meaning |
|-------|---------|
| `0` | No STA melody / full track plays |
| `>0` | Seconds into STA track where melody **stops** and door chime begins |

---

## Supported Lines (as of 2026-03-03)

All lines share the central `data/translations.json` (display text) and `data/stations.json` (operational metadata).

| Line | Code Prefix |
|------|-------------|
| Chuo Main (中央線) | JC |
| Keihin-Tohoku (京浜東北) | JK |
| Keiyo (京葉線) | JE |
| Saikyo (埼京線) | JA |
| Tokaido (東海道線) | JT |
| Yamanote (山手線) | JY |

---

## Data Conventions

1. **Separation of concerns across data files:**
   - `data/translations.json`: Central furigana/english translations (keyed by Japanese text)
   - `data/train_types.json`: Train type English translations (optional `english_short` for narrow boxes)
   - `data/stations.json`: Line-independent station metadata — 3-letter codes and future fields (keyed by Japanese station name)

2. **Translation lookup:**
   - By station name: `"東京"` → `translations.json["東京"]`
   - By train type: `"快速"` → `train_types.json["快速"]`

3. **Empty values:**
   - No PA: `"pa": []`
   - No STA: `"sta": []` or `"sta": [""]`
   - No code: `"sta_code": null`

4. **Travel time:**
   - First station: `"time": 0`
   - Other stations: minutes to next station

5. **Circular routes:**
   - First and last station have the same name
   - Handled automatically by the simulator
   - Example: Yamanote Line (大崎 appears twice in stops array)

6. **Stop-level destination override:**
   - Individual stops can have a `dest` field to override the route-level destination
   - Useful for circular routes where destination changes based on current position
   - The `dest` value is looked up in `data/translations.json` like station names

---

## Data Validation Checklist

Use this checklist when adding or modifying route data to ensure consistency.

### Manual Checklist

- [ ] **data/translations.json exists** and contains translations for all station names
- [ ] **data/train_types.json exists** and contains translations for train types used in routes
- [ ] **sta_code** is present in every stop (value or `null`)
- [ ] **sta_code format** is simple (e.g., `JC05`, not `JC05_SJK`)
- [ ] **sta field** can have suffixes for audio files (e.g., `JC05_SJK`, `TYO`)
- [ ] **data/stations.json** entries (if present) use raw Japanese station names as keys
- [ ] **No duplicate keys** in JSON files
- [ ] **PA tracks** are assigned to correct stations (do not renumber subsequent stations when modifying)
- [ ] **Station names in route.json** have entries in `data/translations.json`
- [ ] **Train types in route.json** have entries in `data/train_types.json` (optional, falls back to kanji)

### Automated Validation Script

Run this Python script to validate all route data:

```python
import json
import os
import re

# Lines to validate
lines = [
    ('chuo', 'JC'),
    ('keihin', 'JK'),
    ('keiyo', 'JE'),
    ('saikyo', 'JA'),
    ('tokaido', 'JT'),
    ('yamanote', 'JY'),
]

# Load central translations
translations_file = 'data/translations.json'
if os.path.exists(translations_file):
    with open(translations_file, encoding='utf-8') as f:
        translations = json.load(f)
    print(f'Central translations.json: OK ({len(translations)} entries)')
else:
    print('ERROR: data/translations.json missing!')
    translations = {}

# Load train type translations
train_types_file = 'data/train_types.json'
if os.path.exists(train_types_file):
    with open(train_types_file, encoding='utf-8') as f:
        train_types = json.load(f)
    print(f'Train types train_types.json: OK ({len(train_types)} entries)')
else:
    print('WARNING: data/train_types.json missing (train types will fall back to kanji)')
    train_types = {}

# Pattern to detect if sta_code has a suffix (wrong!)
suffix_pattern = re.compile(r'_[A-Z]{2,}$')  # e.g., _OSK, _SBY, _TYO

def validate_line(line_name, prefix):
    print(f'\n=== {line_name.upper()} Line ===')

    # Get all route.json files for this line
    route_dir = f'audio/{line_name}'
    for root, dirs, files in os.walk(route_dir):
        for file in files:
            if file == 'route.json':
                route_file = os.path.join(root, file)
                validate_route(route_file)

def validate_route(route_file):
    diag_name = os.path.basename(os.path.dirname(route_file))
    issues = []

    try:
        with open(route_file, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'  {diag_name}: JSON ERROR - {e}')
        return

    # Check train type translation exists
    route_type = data.get('type', '')
    if route_type and route_type not in train_types:
        issues.append(f'Train type "{route_type}": No translation in data/train_types.json (will fall back to kanji)')

    # Check stops
    for i, stop in enumerate(data.get('stops', [])):
        name = stop.get('name', '?')

        # Check sta_code exists
        if 'sta_code' not in stop:
            issues.append(f'Stop {i} ({name}): Missing sta_code')
            continue

        sta_code = stop.get('sta_code')

        # Check sta_code doesn't have suffix
        if sta_code and suffix_pattern.search(sta_code):
            issues.append(f'Stop {i} ({name}): sta_code="{sta_code}" should not have suffix')

        # Check translation exists for station name
        if name and name not in translations:
            issues.append(f'Stop {i} ({name}): No translation in data/translations.json')

    if issues:
        print(f'  {diag_name}: ISSUES FOUND')
        for issue in issues:
            print(f'    - {issue}')
    else:
        print(f'  {diag_name}: OK ({len(data.get("stops", []))} stops)')

# Run validation
print('\n=== PA Simulator Data Validation ===')
for line_name, prefix in lines:
    validate_line(line_name, prefix)

print('\nValidation complete.')
```

### Expected Output (All Passing)

```
=== PA Simulator Data Validation ===

Central translations.json: OK (120 entries)
Train types train_types.json: OK (10 entries)

=== CHUO Line ===
  1654T: OK (32 stops)
  916H: OK (32 stops)

=== KEIHIN Line ===
  1275A: OK (46 stops)
  727B: OK (46 stops)

=== KEIYO Line ===
  780Y_1510Y: OK (17 stops)

=== SAIKYO Line ===
  1349F: OK (24 stops)
  759K: OK (24 stops)

=== TOKAIDO Line ===
  1865E: OK (21 stops)

=== YAMANOTE Line ===
  yamanote: OK (30 stops)

Validation complete.
```

### Common Issues and Fixes

| Issue | Example | Fix |
|-------|---------|-----|
| sta_code with suffix | `"sta_code": "JC05_SJK"` | Change to `"sta_code": "JC05"` |
| Missing sta_code | Stop has no `sta_code` field | Add `"sta_code": "JC05"` or `null` |

---

## Windows Console Encoding Note

When running validation scripts or Python commands that print Japanese characters on Windows, you may encounter encoding errors:

```
UnicodeEncodeError: 'charmap' codec can't encode characters
```

**Solution:** Set the `PYTHONUTF8` environment variable before running Python:

```bash
# Command Prompt
set PYTHONUTF8=1
python validate.py

# PowerShell
$env:PYTHONUTF8=1
python validate.py

# Git Bash
PYTHONUTF8=1 python validate.py
```

Alternatively, add this to the top of your Python script:

```python
import sys
sys.stdout.reconfigure(encoding='utf-8')  # Python 3.7+
```

**Note:** File I/O in this project already uses `encoding='utf-8'` explicitly, so the issue only affects console output.
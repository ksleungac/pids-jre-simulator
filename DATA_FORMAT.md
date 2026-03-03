# PA Simulator - Data Format Specification

## Overview

This document defines the JSON data formats used by the PA Simulator for route configurations and station databases.

---

## File Structure

```
project_root/
├── data/
│   └── translations.json        # Central translation database (furigana, english)
└── audio/
    ├── [line]/                  # Line name (e.g., chuo, keihin, saikyo)
    │   ├── stations.json        # Line-specific station data (interchange, facilities, etc.)
    │   └── [diagram]/           # Train diagram folder (e.g., 1349F, 759K)
    │       └── route.json       # Route configuration
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

### Benefits of Centralized Design

- **No duplication**: Station like 東京 appear once, even though used by multiple lines
- **Separation of concerns**: Translations separate from line-specific data
- **Easy maintenance**: Update translation in one place
- **Extensible**: Can add any Japanese text, not just station names
- **Destination furigana**: `dest` in route.json is automatically looked up in translations.json (no `dest_furigana` field needed)

---

## stations.json Format (Line-Specific Data)

**Location:** `audio/[line]/stations.json`

### Purpose

Line-specific station data that is **not** related to translations:
- Interchange lines
- Station facilities (elevators, escalators)
- Exit information
- Future line-specific features

### Structure

```json
{
    "JC01": {},
    "JC02": {},
    "name_蘇我": {}
}
```

**Note:** Currently keys are placeholders for future line-specific data. Translation data has been moved to `data/translations.json`.

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Prefix][Number]` | Stations with official JR codes | `JC01`, `JK47`, `JA08` |
| `name_駅名` | Stations without official codes | `name_蘇我`, `name_日進` |

**Important:** These keys are for **line-specific data organization**, not translation lookup.

---

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
| `["1"]` | Single PA track |
| `["1", "2"]` | Multiple PA tracks (user cycles with Page Down) |

**PA Track Numbering Convention:**

- PA tracks are numbered sequentially across the route (1, 2, 3, ...)
- Track numbers correspond to `audio/[line]/[diagram]/pa/[number].mp3` files
- General pattern (varies by route):
  - Track 1 at a station = "Next station is [Station]" (played after departing previous station)
  - Track 2 at a station = "Arriving at [Station]" (played when approaching)
  - Subsequent tracks = departure announcements, connecting trains, safety messages, etc.
- First station may have `["1"]` for pre-departure announcement (played while stopped at platform)

**Important:** The `pa` array defines which tracks belong to which station. When modifying route data:
- Only add/remove/reassign PA tracks at the specific station being edited
- Do NOT renumber subsequent stations' PA tracks
- Example: If moving track 1 from Station B to Station A, only change those two stations; leave Station C's tracks unchanged even if numbering becomes non-sequential

```json
// Before (track 1 incorrectly at Shinbashi):
"東京": { "pa": [] }
"新橋": { "pa": ["1", "2"] }
"品川": { "pa": ["3", "4"] }

// After (track 1 moved to Tokyo):
"東京": { "pa": ["1"] }      // Only this station changed
"新橋": { "pa": ["2"] }      // Only this station changed
"品川": { "pa": ["3", "4"] } // Unchanged - do NOT renumber to ["2", "3"]
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
- Line prefixes: JC (Chuo), JK (Keihin-Tohoku), JA (Saikyo), JE (Keiyo), JY (Yamanote)
- No 3-letter suffixes in `sta_code` (those go in `sta` field only)
- **Note:** `sta_code` is now used for line-specific data lookup in `audio/[line]/stations.json`, not for translations

#### `sta_cut` Field

| Value | Meaning |
|-------|---------|
| `0` | No STA melody / full track plays |
| `>0` | Seconds into STA track where melody **stops** and door chime begins |

---

## stations.json Format (Line-Specific Data)

**Location:** `audio/[line]/stations.json`

### Purpose

Line-specific station data that is **not** related to translations:
- Interchange lines
- Station facilities (elevators, escalators)
- Exit information
- Future line-specific features

**Note:** Translation data (furigana, english) has been moved to `data/translations.json`.

### Structure

```json
{
    "JC01": {},
    "JC02": {},
    "name_蘇我": {}
}
```

**Note:** Currently keys are placeholders for future line-specific data. Values are empty objects `{}`.

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Prefix][Number]` | Stations with official JR codes | `JC01`, `JK47`, `JA08` |
| `name_駅名` | Stations without official codes | `name_蘇我`, `name_日進` |

**Important:** These keys are for **line-specific data organization**, not translation lookup.

---

## Supported Lines (as of 2026-03-03)

All lines share the central `data/translations.json` for translations. Line-specific `stations.json` files are placeholders for future line-specific data.

| Line | Code Prefix | stations.json Location |
|------|-------------|------------------------|
| Chuo Main (中央線) | JC | `audio/chuo/stations.json` |
| Keihin-Tohoku (京浜東北) | JK | `audio/keihin/stations.json` |
| Keiyo (京葉線) | JE | `audio/keiyo/stations.json` |
| Saikyo (埼京線) | JA | `audio/saikyo/stations.json` |
| Tokaido (東海道線) | JT | `audio/tokaido/stations.json` |

---

## Data Conventions

1. **Separation of translations and line-specific data:**
   - `data/translations.json`: Central furigana/english translations (keyed by Japanese text)
   - `audio/[line]/stations.json`: Line-specific data (keyed by sta_code or name_)

2. **Translation lookup:**
   - By station name: `"東京"` → `translations.json["東京"]`

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

---

## Data Validation Checklist

Use this checklist when adding or modifying route data to ensure consistency.

### Manual Checklist

- [ ] **data/translations.json exists** and contains translations for all station names
- [ ] **dest_furigana** is present in route.json (exactly once, at route level)
- [ ] **sta_code** is present in every stop (value or `null`)
- [ ] **sta_code format** is simple (e.g., `JC05`, not `JC05_SJK`)
- [ ] **sta field** can have suffixes for audio files (e.g., `JC05_SJK`, `TYO`)
- [ ] **stations.json keys** match sta_code values (for line-specific data)
- [ ] **Name-based keys** (`name_駅名`) used for stations without official codes
- [ ] **No duplicate keys** in JSON files (especially `dest_furigana`)
- [ ] **PA tracks** are assigned to correct stations (do not renumber subsequent stations when modifying)
- [ ] **Station names in route.json** have entries in `data/translations.json`

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

# Pattern to detect if sta_code has a suffix (wrong!)
suffix_pattern = re.compile(r'_[A-Z]{2,}$')  # e.g., _OSK, _SBY, _TYO

def validate_line(line_name, prefix):
    print(f'\n=== {line_name.upper()} Line ===')

    # Load line-specific stations.json
    stations_file = f'audio/{line_name}/stations.json'
    if not os.path.exists(stations_file):
        print(f'  ERROR: stations.json missing!')
        return

    with open(stations_file, encoding='utf-8') as f:
        stations_db = json.load(f)
    print(f'  stations.json: OK ({len(stations_db)} entries)')

    # Get all route.json files for this line
    route_dir = f'audio/{line_name}'
    for root, dirs, files in os.walk(route_dir):
        for file in files:
            if file == 'route.json':
                route_file = os.path.join(root, file)
                validate_route(route_file, stations_db)

def validate_route(route_file, stations_db):
    diag_name = os.path.basename(os.path.dirname(route_file))
    issues = []

    with open(route_file, encoding='utf-8') as f:
        content = f.read()

    # Check for duplicate dest_furigana
    dest_furigana_count = len(re.findall(r'"dest_furigana"', content))
    if dest_furigana_count != 1:
        issues.append(f'dest_furigana appears {dest_furigana_count} times (should be 1)')

    # Parse JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f'  {diag_name}: JSON ERROR - {e}')
        return

    # Check route-level fields
    if 'dest_furigana' not in data:
        issues.append('Missing dest_furigana at route level')

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

=== CHUO Line ===
  stations.json: OK (24 entries)
  1654T: OK (32 stops)
  916H: OK (32 stops)

=== KEIHIN Line ===
  stations.json: OK (46 entries)
  1275A: OK (46 stops)
  727B: OK (46 stops)

=== KEIYO Line ===
  stations.json: OK (17 entries)
  780Y_1510Y: OK (17 stops)

=== SAIKYO Line ===
  stations.json: OK (24 entries)
  1349F: OK (24 stops)
  759K: OK (24 stops)

=== TOKAIDO Line ===
  stations.json: OK (21 entries)
  1865E: OK (21 stops)

Validation complete.
```

### Common Issues and Fixes

| Issue | Example | Fix |
|-------|---------|-----|
| Duplicate `dest_furigana` | Appears at top and bottom of file | Remove duplicate, keep only one |
| sta_code with suffix | `"sta_code": "JC05_SJK"` | Change to `"sta_code": "JC05"` |
| Missing sta_code | Stop has no `sta_code` field | Add `"sta_code": "JC05"` or `null` |
| stations.json key mismatch | sta_code is `JA08`, key is `JA08_OSK` | Change key to `JA08` |
| stations.json missing | No `audio/[line]/stations.json` | Create file with all stations |

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
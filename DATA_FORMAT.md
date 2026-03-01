# PA Simulator - Data Format Specification

## Overview

This document defines the JSON data formats used by the PA Simulator for route configurations and station databases.

---

## File Structure

```
audio/
├── [line]/                    # Line name (e.g., chuo, keihin, saikyo)
│   ├── stations.json          # Station database (furigana, english names)
│   └── [diagram]/             # Train diagram folder (e.g., 1349F, 759K)
│       └── route.json         # Route configuration
```

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
    "dest": "終点",                 // Final destination (kanji)
    "dest_furigana": "とうきょう"   // Furigana for destination (optional, for cycling)
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

### Field Details

#### `pa` Array (PA Announcements)

| Value | Meaning |
|-------|---------|
| `[]` | No PA announcement - train doesn't stop OR first station |
| `["1"]` | Single PA track |
| `["1", "2"]` | Multiple PA tracks (user cycles with Page Down) |

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
| `"JC01"` | Official JR East station code (used for stations.json lookup) |
| `null` | Station has no official code (e.g., Kawagoe Line stations) |

**Format:** `[Line Prefix][Number]` (e.g., `JC01`, `JK47`, `JA08`)
- Line prefixes: JC (Chuo), JK (Keihin-Tohoku), JA (Saikyo), JE (Keiyo), JY (Yamanote)
- No 3-letter suffixes in `sta_code` (those go in `sta` field only)

#### `sta_cut` Field

| Value | Meaning |
|-------|---------|
| `0` | No STA melody / full track plays |
| `>0` | Seconds into STA track where melody **stops** and door chime begins |

---

## stations.json Format

**Location:** `audio/[line]/stations.json`

### Purpose

Provides furigana and English names for stations to enable:
- Kanji/furigana cycling display (every 4 seconds)
- Lookup by `sta_code` from route.json

### Structure

```json
{
    "JC01": {
        "name": "東京",
        "furigana": "とうきょう",
        "english": "Tokyo"
    },
    "JC02": {
        "name": "神田",
        "furigana": "かんだ",
        "english": "Kanda"
    },
    "name_蘇我": {
        "name": "蘇我",
        "furigana": "そが",
        "english": "Soga"
    }
}
```

### Key Format

| Pattern | Use Case | Example |
|---------|----------|---------|
| `[Prefix][Number]` | Stations with official JR codes | `JC01`, `JK47`, `JA08` |
| `name_駅名` | Stations without official codes | `name_蘇我`, `name_日進` |

**Important:** Keys must match the `sta_code` values in route.json (simple format, no 3-letter suffixes).

### Lookup Rules (in app.py)

1. **Primary:** Lookup by `sta_code` (e.g., `"JA08"` → `stations.json["JA08"]`)
2. **Fallback:** Lookup by `name_駅名` key for stations with `sta_code: null`

### Value Fields

| Field | Description |
|-------|-------------|
| `name` | Station name in kanji (must match route.json `name` for fallback) |
| `furigana` | Hiragana reading for the station |
| `english` | Romanized station name |

---

## Supported Lines (as of 2026-03-01)

| Line | stations.json Location | Code Prefix |
|------|----------------------|-------------|
| Chuo Main (中央線) | `audio/chuo/stations.json` | JC |
| Keihin-Tohoku (京浜東北) | `audio/keihin/stations.json` | JK |
| Keiyo (京葉線) | `audio/keiyo/stations.json` | JE |
| Saikyo (埼京線) | `audio/saikyo/stations.json` | JA |
| Tokaido (東海道線) | `audio/tokaido/stations.json` | JT |

---

## Example: Complete Station Entry

### route.json entry
```json
{
    "name": "大宮",
    "pa": ["21"],
    "sta": ["JA26_OMY", "JA26_OMY_1"],
    "sta_code": "JA26",
    "sta_cut": 10,
    "time": 3
}
```

### stations.json entry
```json
{
    "JA26": {
        "name": "大宮",
        "furigana": "おおみや",
        "english": "Omiya"
    }
}
```

**Note:** The `sta` field uses `JA26_OMY` (with suffix for audio file), but `sta_code` uses `JA26` (simple format) for lookup.

---

## Example: Station Without Official Code

### route.json entry (Kawagoe Line stations)
```json
{
    "name": "日進",
    "pa": ["22", "23"],
    "sta": ["20"],
    "sta_code": null,
    "sta_cut": 10,
    "time": 3
}
```

### stations.json entry
```json
{
    "name_日進": {
        "name": "日進",
        "furigana": "にっしん",
        "english": "Nisshin"
    }
}
```

---

## Data Conventions

1. **sta vs sta_code separation:**
   - `sta`: Audio filename (can have suffixes like `_OSK`, `_SBY`)
   - `sta_code`: Lookup key for stations.json (simple `JA08` format)

2. **Empty values:**
   - No PA: `"pa": []`
   - No STA: `"sta": []` or `"sta": [""]`
   - No code: `"sta_code": null`

3. **Travel time:**
   - First station: `"time": 0`
   - Other stations: minutes to next station

4. **Circular routes:**
   - First and last station have the same name
   - Handled automatically by the simulator

---

## Data Validation Checklist

Use this checklist when adding or modifying route data to ensure consistency.

### Manual Checklist

- [ ] **stations.json exists** for the line (`audio/[line]/stations.json`)
- [ ] **dest_furigana** is present in route.json (exactly once, at route level)
- [ ] **sta_code** is present in every stop (value or `null`)
- [ ] **sta_code format** is simple (e.g., `JC05`, not `JC05_SJK`)
- [ ] **sta field** can have suffixes for audio files (e.g., `JC05_SJK`, `TYO`)
- [ ] **stations.json keys** match sta_code values (simple format)
- [ ] **Name-based keys** (`name_駅名`) used for stations without official codes
- [ ] **No duplicate keys** in JSON files (especially `dest_furigana`)

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

# Pattern to detect if sta_code has a suffix (wrong!)
suffix_pattern = re.compile(r'_[A-Z]{2,}$')  # e.g., _OSK, _SBY, _TYO

def validate_line(line_name, prefix):
    print(f'=== {line_name.upper()} Line ===')

    # Load stations.json
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

        # Check sta_code lookup exists in stations.json
        if sta_code and sta_code not in stations_db:
            # Check name-based fallback
            name_key = f'name_{name}'
            if name_key not in stations_db:
                issues.append(f'Stop {i} ({name}): sta_code="{sta_code}" not found in stations.json')

    if issues:
        print(f'  {diag_name}: ISSUES FOUND')
        for issue in issues:
            print(f'    - {issue}')
    else:
        print(f'  {diag_name}: OK ({len(data.get("stops", []))} stops)')

# Run validation
print('=== PA Simulator Data Validation ===\n')
for line_name, prefix in lines:
    validate_line(line_name, prefix)
    print()

print('Validation complete.')
```

### Expected Output (All Passing)

```
=== PA Simulator Data Validation ===

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
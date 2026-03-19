# Audio Splitting Workflow - PA/STA

## Overview

This document describes the workflow for splitting continuous MP3 audio files into individual station announcement (PA) and departure melody (STA) tracks.

## Source Material Format

- **Single continuous MP3** for all station melodies (STA) or announcements (PA)
- **Timestamps file** with start times for each segment

---

## STA (Departure Melody) Splitting

### Source File: `timestamps.txt`

**Format:** `駅名 ＝ 曲名 M:SS`

```
上野 ＝ ベル 0:00
尾久 ＝ 線路の彼方 0:24
赤羽 ＝ 高原 0:43
浦和 ＝ すすきの高原 1:01
...
```

### Splitting Script Pattern

```python
# Station name mapping (kanji -> romaji)
STATIONS = [
    ("上野", "ueno"),
    ("尾久", "oku"),
    ("赤羽", "akabane"),
    ...
]

# Timestamps from timestamps.txt (start time in seconds)
TIMESTAMPS = [0, 24, 43, 61, ...]

# Calculate duration for each station
for i in range(len(TIMESTAMPS)):
    if i < len(TIMESTAMPS) - 1:
        duration = TIMESTAMPS[i + 1] - TIMESTAMPS[i]
    else:
        duration = total_length - TIMESTAMPS[i]  # Last station

# FFmpeg split command
cmd = [
    'ffmpeg', '-y',
    '-ss', str(start),
    '-i', src,
    '-t', str(duration),
    '-c', 'copy',
    output_file
]
```

### Output Naming
- **Format:** `{station}.mp3` (lowercase, no song name)
- **Examples:** `ueno.mp3`, `kita-ageo.mp3`, `saitama-shintoshin.mp3`

---

## PA (Announcement) Splitting

### Source File: `pa_timestamps.txt`

**Format:** `M:SS station_action`

```
0:09 ueno_dep
1:10 akabane_arr
2:15 akabane_dep
...
```

### Splitting Script Pattern

```python
# Parse timestamp and station action from each line
for line in lines:
    parts = line.strip().split()
    timestamp = parts[0]  # "0:09"
    action = parts[1]     # "ueno_dep"

    # Convert M:SS to seconds
    m, s = map(int, timestamp.split(':'))
    start_sec = m * 60 + s

    # Calculate duration to next timestamp
    # (same logic as STA splitting)
```

### Output Naming
- **Format:** `{station}-{dep|arr}.mp3`
- **Examples:**
  - `ueno-dep.mp3` (departure from Ueno)
  - `akabane-arr.mp3` (arrival at Akabane)

---

## route.json Mapping

### Station Melodies (`sta` field)
```json
{
    "name": "上野",
    "sta": ["ueno"],
    "sta_cut": 17
}
```
- **Array of filenames** without `.mp3` extension (code adds it when loading)
- Multiple files for stations with multiple melodies

### PA Announcements (`pa` field)
```json
{
    "name": "赤羽",
    "pa": ["ueno-dep", "akabane-arr"]
}
```
- **Array of filenames** without extension (code adds `.mp3`)
- Pattern: `{prev_station}-dep`, `{current_station}-arr`

### `sta_cut` Field
- Seconds from end where melody stops and door chime begins
- Example: `sta_cut: 17` means melody plays for (duration - 17) seconds, then 17 seconds of silence/door chime

---

## Example: Complete Workflow

### Step 1: Prepare Source Files
```
pa_sta_split_workflow/
├── takasaki_sta_src.mp3       # Continuous STA melody
├── timestamps.txt              # Station timestamps
├── takasaki_rapid_urban_pa.mp3 # Continuous PA announcements
└── pa_timestamps.txt          # PA timestamps
```

### Step 2: Run Splitting Scripts
```bash
python split_sta_takasaki.py  # Creates 24 STA files
python split_pa.py            # Creates 30 PA files
```

### Step 3: Move to Audio Directory
```
audio/takasaki/3922E/
├── sta/
│   ├── ueno.mp3
│   ├── oku.mp3
│   └── ...
├── pa/
│   ├── ueno-dep.mp3
│   ├── akabane-arr.mp3
│   └── ...
└── route.json
```

### Step 4: Update route.json
Map each station to its corresponding audio files.

---

## Common Issues

### Windows Console Encoding
Python scripts with Japanese output need UTF-8:
```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
```

### FFmpeg Japanese Filename Errors
Ensure source file paths don't contain Japanese characters, or rename:
```bash
mv "高崎線.mp3" takasaki_src.mp3
```

### Duration Calculation
Last station needs explicit end time or total duration:
```python
# If total length is 8:00 (480 seconds)
duration = 480 - TIMESTAMPS[-1]  # Last station
```

---

## Reference Scripts
- `pa_sta_split_workflow/split_sta_takasaki.py` - STA splitting example
- `pa_sta_split_workflow/split_pa.py` - PA splitting example

## Related Documents
- [DATA_FORMAT.md](../DATA_FORMAT.md) - route.json field definitions
- [notes.md](notes.md) - Implementation patterns

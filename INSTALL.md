# JRE-PA-Simulator - User Installation Guide

## Quick Start

### Option 1: Download from Releases (Recommended for Users)

1. **Download the executable**
   - Go to [Releases](https://github.com/ksleungac/pids-jre-simulator/releases)
   - Download `JRE-PA-Simulator.exe`

2. **Download the data pack**
   - Download `data-pack.zip` from the same release
   - Extract it next to `JRE-PA-Simulator.exe`

3. **Install fonts**
   - Open `data-pack/fonts/` folder
   - Select all `.otf` and `.ttf` files
   - Right-click → "Install for all users"

4. **Get audio files** (Required for sound)
   - Audio files are too large for GitHub releases (~475MB)
   - Download/clone the repository: https://github.com/ksleungac/pids-jre-simulator
   - Copy the `audio/` folder next to `JRE-PA-Simulator.exe`

### Final File Structure
```
your-folder/
├── JRE-PA-Simulator.exe
├── data-pack/
│   ├── fonts/
│   │   ├── ShinGoPr6N-Medium.otf
│   │   ├── ShinGoPr6N-Heavy.otf
│   │   ├── HelveticaNeue-Roman.otf
│   │   └── HelveticaNeueBold.ttf
│   ├── translations.json
│   └── train_types.json
└── audio/
    ├── chuo/
    ├── yamanote/
    ├── keihin/
    └── ...
```

---

## Option 2: From Source (Recommended for Developers)

### Requirements
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Steps
```bash
# Clone the repository
git clone https://github.com/ksleungac/pids-jre-simulator.git
cd pids-jre-simulator

# Install dependencies
uv sync

# Run the simulator
uv run main.py
```

---

## Controls

| Key | Action |
|-----|--------|
| Page Down | Next PA announcement |
| Page Up | Next station (STA) |
| End | Pause/Resume |
| ESC | Quit |

---

## Troubleshooting

### "Font not found" error
- Ensure fonts are installed in Windows or placed in `fonts/` folder next to exe

### "Audio file not found" error
- Verify `audio/` folder is in the same directory as the executable
- Check that route.json references valid audio file paths

### Japanese characters not displaying
- Install the ShinGoPr6N fonts (included in data-pack)
- On Windows: Set `PYTHONUTF8=1` environment variable if running from source

---

## For More Information

- [CLAUDE.md](../CLAUDE.md) - Project overview
- [DATA_FORMAT.md](../DATA_FORMAT.md) - Route data format specification
- [UPPER_DISPLAY_UPDATE.md](../UPPER_DISPLAY_UPDATE.md) - Display system documentation

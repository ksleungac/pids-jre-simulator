# Session Scratch Log

Recent interaction notes - kept concise, detailed for recent sessions.

---

## 2026-03-14

### Font Loading Fix for Non-English Windows
- **Problem**: `pygame.font.SysFont()` crashes on Chinese Windows with `TypeError: expected str, bytes or os.PathLike object, not int`
- **Cause**: SysFont scans Windows font registry which fails on non-English locale systems
- **Solution**: Changed all `SysFont()` calls to `pygame.font.Font("fonts/filename.otf", size)` with direct file paths
- **Files modified**:
  - `displays/train_models/e235_1000/upper_lcd.py` (JapaneseDisplay, FuriganaDisplay, EnglishDisplay)
  - `display.py` (UpperDisplay, LowerDisplay)
  - `setup.py` (SetupScreen fonts)
  - `app.py` (mini display font)
- **Distribution**: `fonts/` folder must be alongside exe at runtime

### JSON Loading Fix for PyInstaller Exe
- **Problem**: `__file__` points to temp folder (`_MEIxxxxx`) in PyInstaller one-file exe
- **Solution**: Added `get_base_dir()` using `sys.executable.parent` when `sys.frozen`
- **Pattern**:
  ```python
  def get_base_dir() -> Path:
      if getattr(sys, "frozen", False):
          return Path(sys.executable).parent  # Exe directory
      else:
          return Path(__file__).parent.parent.parent.parent  # Project root
  ```
- **Files modified**: `displays/train_models/e235_1000/upper_lcd.py`

### English Mode Temporarily Disabled
- Mode cycler updated: KANJI → FURIGANA only (English commented out)
- Default mode changed to KANJI
- Will re-enable after fonts are verified

### Build Command Update
- Changed from `--windowed` to `--console` for error visibility
- Command: `uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm`
- Updated: `.claude/commands/build.md`, `JRE-PA-Simulator.spec`

### Documentation Updates
- `UPPER_DISPLAY_UPDATE.md`: Font loading, JSON loading, distribution structure
- `CLAUDE.md`: Last Update, Known Behaviors, Critical Notes
- `.claude/rules/notes.md`: Font loading pattern, JSON loading pattern, distribution notes

---

## 2026-03-13

### Station Skip Logic Bug Fix
- **Bug**: Single-station skips failed when destination had 2+ PA tracks (e.g., skipping 辻堂 on Tokaido 3535E)
- **Root cause**: Condition checked `len(pa_tracks) == 1` instead of `skip == 1`
- **Fix**: `display.py:increment_current_stop_display()` - single-skip jumps directly, multi-skip preserves two-phase
- Files modified: `display.py` (LowerDisplay class, ~10 lines)

### Audio Cutting & Tokaido 3535E Diagram
- Created new diagram `audio/tokaido/3535E/` for 快速アクティー (Rapid Acty) service
- Cut audio from single MP3 using ffmpeg: 34 segments with descriptive filenames
- PA tracks use filename-based references (e.g., `"tokyo_dep"`, `"shinagawa_arr"`) not sequential numbers
- Added `快速アクティー` → "Rapid" to `data/train_types.json`
- Skipped stations (辻堂，大磯，二宮，鴨宮) have `pa: []` but retain `time` values

### ffmpeg Audio Cutting Workflow
```bash
# Add dev dependencies
uv add --dev pydub ffmpeg-python

# Cut audio using ffmpeg subprocess (no re-encoding, copy codec)
cmd = ['ffmpeg', '-y', '-ss', start_sec, '-i', input_file, '-t', duration, '-c', 'copy', output_file]
```

### Documentation Updates
- DATA_FORMAT.md: Documented filename-based PA track naming convention
- CLAUDE.md: Added note about filename-based PA tracks

---

## 2026-03-12

### v0.5.0 Release
- GitHub Actions workflow: `.github/workflows/release.yml` - auto-builds exe on tag push
- Bilingual README (EN/中文) with installation, usage, planned features
- Distribution folder structure (CRITICAL):
  - EXE must be alongside `audio/`, `data/`, `fonts/` at same directory level
  - Folders are siblings to exe, not nested inside subfolders
  - Relative path loading from exe directory

### Automemory Removal
- User requested removal of automemory references from skills and documentation
- Updated `.claude/skills/session-recap/SKILL.md`:
  - Removed "Auto Memory (MEMORY.md)" section from documentation updates
  - Removed point #5 about updating auto memory from Important Notes
- Added project rules files to session-recap scope:
  - `.claude/rules/notes.md`
  - `.claude/rules/preferences.md`
- SCRATCH.md created as lightweight interaction log (this file)

---

## 2026-03-19

### Takasaki Line - Complete STA/PA Setup Workflow
- Created full Takasaki Line diagrams: `audio/takasaki/831M/` (Local) and `audio/takasaki/3922E/` (Rapid Urban)
- **STA splitting workflow** (`pa_sta_split_workflow/split_sta_takasaki.py`):
  - Source: `takasaki_sta_src.mp3` - single continuous departure melody
  - `timestamps.txt` format: `駅名 ＝ 曲名 M:SS` (station name, song name, start time)
  - Parse timestamps, calculate duration to next station
  - Output: lowercase English station names with `.mp3` (e.g., `ueno.mp3`, `kita-ageo.mp3`)
- **PA splitting workflow** (`pa_sta_split_workflow/split_pa.py`):
  - Source: `takasaki_rapid_urban_pa.mp3` - continuous PA announcements
  - `pa_timestamps.txt` format: `M:SS station_action` (e.g., `0:09 ueno_dep`, `1:10 akabane_arr`)
  - Output: `{station}-{dep|arr}.mp3` format
- **route.json mapping**: `sta` array uses filenames with `.mp3` extension
- **Verification lesson**: Always Glob files BEFORE modifying route.json references (learned the hard way with `kita-ageo.mp3`)

### Files Added
- `audio/takasaki/831M/route.json` - Local service (no PA, 24 stations)
- `audio/takasaki/3922E/route.json` - Rapid Urban (with PA + STA)
- `audio/takasaki/3922E/sta/*.mp3` - 24 station melodies
- `audio/takasaki/3922E/pa/*.mp3` - 30 PA announcements
- `data/translations.json` - 20 Takasaki stations (Hepburn with macrons: Kōnosu, Gyōda, Honjō, etc.)
- `data/train_types.json` - `快速アーバン` → `Rapid Service Urban`

### Critical Lesson Documented
- `.claude/rules/critical_lessons.md` - Verify files BEFORE destructive operations

---

## Template for Future Sessions

```markdown
## YYYY-MM-DD

### [Session Topic]
- [Key changes or decisions]
- [Files modified]
- [Preferences discovered]

```

---

## Guidelines

1. **Date each entry** - Use YYYY-MM-DD format
2. **Keep concise** - Focus on what changed and why
3. **Trim old entries** - Shorten older sessions as new ones are added
4. **Stay under 200 lines** - Remove or consolidate old entries when approaching limit
5. **Misc items only** - Items that don't fit in CLAUDE.md, DATA_FORMAT.md, UPPER_DISPLAY_UPDATE.md, or rules/

---

*Lines: ~30 | Last updated: 2026-03-12*

---

## 2026-03-16

### v0.5.0b Release & Release Workflow
- Created `release.ps1` - local PowerShell script for full release flow
  - Builds exe, creates distribution zip, publishes GitHub release
  - Uses `gh` CLI instead of git push tag (avoids PAT workflow scope issues)
- Updated `.github/workflows/release.yml` to manual dispatch only
- Distribution zip includes: exe + fonts/ + data/ + empty audio/
- Uploaded `JRE-PA-Simulator-v0.5.0b-distribution.zip` to release
- Release command: `.\release.ps1 v0.5.0b`

### gh CLI Setup
- Installed GitHub CLI via winget
- Authenticated with workflow scope: `gh auth login --scopes workflow`
- `gh` location: `C:\Program Files\GitHub CLI\gh.exe`

### Documentation Updates
- `.claude/commands/build.md`: Added release script usage, gh CLI workflow
- `CLAUDE.md`: Updated Last Update with v0.5.0b release notes

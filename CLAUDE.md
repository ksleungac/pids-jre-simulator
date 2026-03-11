# PA Simulator Project - CLAUDE.md

## Project Overview

**Japanese Train PA (Public Address) Simulator** - A pygame-based application that simulates train station announcements and arrival melodies with visual LCD display.

**Current Date:** 2026-03-11

**Last Update:**
- Modular UpperDisplay integrated from `displays/train_models/e235_1000/upper_lcd.py`
- English train type display with `data/train_types.json` (`english_short` for narrow boxes)
- Code refactor: inlined position constants, fonts shared as class members
- Hepburn romanization with macrons (中央特快 → Chūō Special Rapid)

---

## File Structure

```
pids_jre_simulator/
├── main.py, app.py, audio.py, display.py (LowerDisplay), constants.py, utils.py
├── displays/                          # Modular display system
│   ├── base.py                        # DisplayMode enum, ModeCycler
│   └── train_models/e235_1000/
│       ├── upper_lcd.py               # Japanese/Furigana/EnglishDisplay, UpperDisplay
│       └── lower_lcd.py               # Placeholder
├── data/
│   ├── translations.json              # Station names (furigana, english)
│   └── train_types.json               # Train type English translations
└── audio/[line]/[diagram]/route.json
```

---

## Key Features

1. **3-Mode Display Cycling** (2s each): KANJI → FURIGANA → ENGLISH
   - Destination: always kanji (IRL behavior)
   - Prefix/Station: cycle with translations
   - Train type: cycles, uses `english_short` if available

2. **Modular Architecture**: Per-train-model displays (E235-1000, E231-500...)
   - Mode renderers: self-contained (JapaneseDisplay, etc.)
   - Manager: UpperDisplay handles cycling + delegates rendering

3. **Stop-Level Dest Override**: Circular routes (Yamanote) change destination mid-route

4. **Real-Time Countdown**: `TIME_SCALE=60` (60s = 1 travel minute), floor division

5. **Audio**: -15 LUFS normalization, double-buffered temp files

---

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `constants.py` | S_WIDTH=730, S_HEIGHT=420, TIME_SCALE=60, FRAME_RATE=15 |
| `utils.py` | draw_text, draw_text_given_width (even spacing), draw_aapolygon |
| `audio.py` | AudioPlayer class, play_pa/sta, pause, is_playing |
| `display.py` | LowerDisplay (legacy, still in use) |
| `displays/` | UpperDisplay (E235-1000): set_state(), update(), draw() |
| `app.py` | PASimulator, AppState, translation loading, PA/STA handling |
| `main.py` | Entry point, setup screen, error handling |

---

## Known Behaviors

1. PA: Page Down (blocked while playing)
2. STA: Page Up (jumps to sta_cut if playing)
3. Pause: End key
4. Yellow hint: Multiple PA tracks indicator
5. Destination: always kanji (no cycling)
6. Graceful fallback: Skip missing furigana/English modes
7. Countdown: Full minute rule, forces "1" on last PA
8. Black formatting: Pre-commit hook

---

## Critical Notes for Next AI

1. **Dictionary keys are strings** - Use `"english"` not `DisplayMode.ENGLISH` for stop data lookups
2. **DisplayMode enum internally** - Use enum for mode state tracking, strings for data keys
3. **Translation lookup** - Keys are raw Japanese text (「東京」), not station codes
4. **Hepburn macrons** - Long vowels: ō (おう/おお), ū (う)
5. **Position constants inline** - Method-local variables; fonts as `self.font_xxx` members
6. **english_short fallback** - Check short → full → kanji
7. **PYTHONUTF8=1** - Windows console encoding for Japanese output

---

## Running

```bash
uv run main.py
```

---

**Full docs:** [DATA_FORMAT.md](DATA_FORMAT.md) | [UPPER_DISPLAY_UPDATE.md](UPPER_DISPLAY_UPDATE.md)

**Implementation notes:** [.claude/rules/notes.md](.claude/rules/notes.md) - Detailed patterns, edge cases, validation rules


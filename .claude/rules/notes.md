# Project Notes — Cross-Cutting Patterns

> **Before adding here, check this is the right home.** This file is for *cross-cutting* code patterns only — things that span modules and don't belong in any one domain doc.
>
> | Domain | Right home |
> |---|---|
> | LCD architecture, mode rendering, skip animation, layout gotchas | [DISPLAY.md](../../DISPLAY.md) |
> | Real-world JR East context, train family, Hepburn convention, in-spec/best-effort policy | [CLAUDE.md](../../CLAUDE.md) "Mental Model" (preloaded — already in head) |
> | JSON shapes (`route.json`, `translations.json`, `stations.json`), validation rules | [DATA_FORMAT.md](../../DATA_FORMAT.md) |
> | Build/distribution, PyInstaller invocation, version metadata | [.claude/skills/build/SKILL.md](../skills/build/SKILL.md) |
> | User preferences, collaboration style | [preferences.md](preferences.md) |
> | Lessons from past mistakes | [critical_lessons.md](critical_lessons.md) |
>
> The full placement table lives in [.claude/skills/session-recap/SKILL.md](../skills/session-recap/SKILL.md). It applies *during* the session whenever you edit a doc, not only at recap time. **`notes.md` is not the kitchen sink** — when in doubt, the placement table picks the right home.

---

## Critical Implementation Notes

### Dictionary Keys vs Enum Usage
- **Data keys are strings**: stop data uses `"english"`, `"furigana"`, `"name"` as keys.
- **Internal state uses enum**: `DisplayMode.KANJI`, `DisplayMode.ENGLISH` for mode tracking.
- **Correct pattern**: `self.stops[self.curr_stop].get("english", "")` NOT `DisplayMode.ENGLISH`.

### Font Loading (CRITICAL for non-English Windows)
- **Problem**: `pygame.font.SysFont()` scans Windows font registry, which can fail on Chinese/Japanese locale systems.
- **Error**: `TypeError: expected str, bytes or os.PathLike object, not int`.
- **Solution**: use `pygame.font.Font("fonts/filename.otf", size)` with direct file paths.
- **Distribution**: `fonts/` folder must be placed alongside exe at runtime.

```python
# WRONG - crashes on Chinese Windows
self.font = pygame.font.SysFont("shingopr6nmedium", 35)

# CORRECT - loads from file
self.font = pygame.font.Font("fonts/ShinGoPr6N-Medium.otf", 35)
```

### JSON Loading (PyInstaller Exe Compatibility)
- **Problem**: in PyInstaller one-file exe, `__file__` points to a temp extraction folder (`_MEIxxxxx`), not the actual exe location.
- **Solution**: use `sys.executable` when `sys.frozen` is True.

```python
def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent          # exe directory
    else:
        return Path(__file__).parent.parent.parent.parent  # project root
```

Usage: `load_json_relative("data/translations.json")` resolves to `exe/data/translations.json` at runtime.

### Countdown System (app.py state machine)
- `TIME_SCALE = 60` means 60 real seconds = 1 travel minute.
- Floor division: time only decrements after a **full minute** elapses.
- Formula: `max(1, time - floor(elapsed_minutes))`.
- Last PA behavior: forces display to "1" (arriving now).
- `departure_time` set when `curr_stop` increments (train departs).

### Windows Console Encoding
- Set `PYTHONUTF8=1` before running Python scripts with Japanese output.
- File I/O uses `encoding='utf-8'` explicitly.
- Console output requires the env var or `sys.stdout.reconfigure('utf-8')`.
- **PyInstaller exe**: use `--console` flag to enable a console window for error visibility.

---

## Preview Mode (testing harness)

`PASimulator(preview=True)` runs the real app with two swaps: `_SilentAudio` replaces `AudioPlayer`, and `_handle_input_preview` (pygame events) replaces the `keyboard`-library polling. `pygame.mixer.init()` and `win32gui.SetWindowPos` are skipped. Everything else — route loading, `_next_pa`, `_next_sta`, draw loop — is shared with the real app. Bug fixes to state-machine code automatically apply to preview.

`preview_display.py` is the thin entry point (~110 lines of CLI plumbing + screenshot mode). No duplicated state machine.

### Mock route
- Path: `audio/_mock/main/route.json`. Default when `--route` is omitted. (`_` prefix on folder = preserved-but-not-shipped, applies to `_archive/` too.)
- Curated 11-stop fictional line — reference stations integrated as test stations so each does double duty (logic test + visual font reference). Covers: `code_3` badge presence/absence, PA-track counts 0/1/2/3, 1-station skip to single-PA target (reproduces the single-PA skip-flush bug), 2-station skip to multi-PA target (happy path), long-name wrap (高輪ゲートウェイ), compound destination (品川・高輪ゲートウェイ).
- Stop indices used by `compare_fonts.py`: 0=東京 (Tokyo ref + multi-PA + TYO code_3), 1=新日本橋 (Shin-Nihombashi ref + 1-skip source), 3=錦糸町 (Kinshicho ref + 1-skip target → REPRO bug), 7=船橋 (Funabashi ref + 2-skip multi-PA target), 8=津田沼 (Tsudanuma ref + single-PA).
- Lives as a real `route.json` file — not in-code constants. Loads via the same path as real routes. Edit freely to experiment.

### `jump_to_stop(target, direction=-1)`
- Hard-jumps to a stop, bypassing the PA cycle. Used by `--stop` CLI and ←/→ arrow keys.
- If target is a passing station (`pa == []`), rolls in `direction` to the nearest PA station. Default `-1` (backward) — lands on pre-skip state so PageDown exercises the skip logic.
- Consequence: `→` key is a no-op when the next station is passing. Cross skips via PageDown, not arrow keys.
- Resets `skip` / `skip_progress` / `time_to_next` / `departure_time` — preview starts from a clean state.

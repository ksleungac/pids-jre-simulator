"""App-chrome internationalisation.

Surfaces: language picker + setup screen + auto-input debug panel (`panel.*`
keys; de-jargoned for the lightly-public audience, 2026-05-31). OOBE still to
come. LCD station-name rendering is unrelated and stays on its own
translations.json — but note the debug panel mixes both: chrome labels via
`font()` here, station names via its own CJK face (see conventions.md §
"Mixed-script i18n chrome needs two fonts").

Three concerns colocated here:
- Settings persistence (alongside-exe writable file, one field for now).
- Locale detection (OS user locale → one of SUPPORTED_LANGS).
- Translation lookup + per-language bundled-OTF font.
"""

import json
import locale
from pathlib import Path

import pygame

from app_paths import project_root

SUPPORTED_LANGS = ("en", "zh_HK", "zh_CN")
DEFAULT_LANG = "en"


# ---------------------------------------------------------------------------
# Settings file. Writable, lives next to exe in frozen builds / project root in
# dev. Survives across the user's two PCs as separate state — never committed.
# ---------------------------------------------------------------------------


def settings_path() -> Path:
    return project_root() / "settings.json"


def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(data: dict) -> None:
    """Best-effort write. Never crashes the app — a read-only install dir
    just means the picker will show again next launch, which is acceptable."""
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"Warning: could not save settings to {settings_path()}: {e}")


# ---------------------------------------------------------------------------
# Locale detection. Maps OS user locale to one of SUPPORTED_LANGS.
# Bare "zh" / zh_TW / zh_HK / zh_MO / zh_Hant → Traditional (zh_HK).
# zh_CN / zh_SG / zh_Hans → Simplified.
# Anything else → English.
# ---------------------------------------------------------------------------


def detect_default_lang() -> str:
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        loc = ""
    if loc.startswith("zh"):
        if any(tag in loc for tag in ("cn", "sg", "hans")):
            return "zh_CN"
        return "zh_HK"
    return "en"


# ---------------------------------------------------------------------------
# Translation lookup. Module-global active language; t(key, **fmt) returns the
# localized string with optional .format() substitutions; falls back through
# en → key.
# ---------------------------------------------------------------------------

_translations: dict = {}
_current_lang: str = DEFAULT_LANG


def init(lang: str) -> None:
    """Set the active language. First call also loads the translations file;
    later calls only switch `_current_lang` (the JSON is not re-read)."""
    global _translations, _current_lang
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    _current_lang = lang
    if not _translations:
        path = project_root() / "data" / "translations_app.json"
        with open(path, encoding="utf-8") as f:
            _translations = json.load(f)


def set_language(lang: str) -> None:
    """Switch the active language at runtime (used for picker hover-preview)."""
    global _current_lang
    if lang in SUPPORTED_LANGS:
        _current_lang = lang


def current_lang() -> str:
    return _current_lang


def t(key: str, **fmt) -> str:
    """Return the localized string for `key`. EN fallback, then key itself."""
    entry = _translations.get(key) or {}
    text = entry.get(_current_lang) or entry.get(DEFAULT_LANG) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text


# ---------------------------------------------------------------------------
# Font — per-language chrome font, all bundled OTFs.
#
# Every language routes to a file under fonts/ — never pygame.font.SysFont().
# SysFont scans the Windows font registry, which raises TypeError on
# Chinese-locale Windows (2026-03-14 incident). The same CONTRACT block in
# displays/train_models/*/upper_lcd.py codifies the rule for the LCD path;
# this module enforces it for app-chrome.
#
# Per-language bundled face:
#   en    — HelveticaNeue (Latin, Latin Extended for macrons).
#   zh_HK — ShinGoPr6N (JIS overlap covers Traditional Chinese).
#   zh_CN — Noto Sans CJK SC (Simplified-specific glyphs ShinGoPr6N tofus).
# ---------------------------------------------------------------------------

# {lang: (regular_filename, bold_filename)} — both files must exist in fonts/.
# fmt: off
_LANG_CHROME_FONT: dict[str, tuple[str, str]] = {
    "en":    ("HelveticaNeue-Roman.otf",   "HelveticaNeue-Bold.otf"),
    "zh_HK": ("ShinGoPr6N-Medium.otf",     "ShinGoPr6N-Heavy.otf"),
    "zh_CN": ("NotoSansCJKsc-Regular.otf", "NotoSansCJKsc-Bold.otf"),
}
# fmt: on

_font_cache: dict = {}


def font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Cached chrome font for the active language. Requires
    pygame.font.init() (called by pygame.init())."""
    return font_for_lang(_current_lang, size, bold=bold)


def font_for_lang(lang: str, size: int, *, bold: bool = False) -> pygame.font.Font:
    """Cached chrome font for an explicit language code, bypassing the
    active language. Used by the picker to render each row's label in its
    own script's font regardless of which row is hovered."""
    regular, bold_fname = _LANG_CHROME_FONT.get(lang, _LANG_CHROME_FONT["en"])
    fname = bold_fname if bold else regular
    key = (fname, size)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.Font(str(project_root() / "fonts" / fname), size)
    return _font_cache[key]

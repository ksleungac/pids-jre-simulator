"""App-chrome internationalisation.

v1 surface: language picker + setup screen. OOBE / debug panel come later.
LCD station-name rendering is unrelated and stays on its own translations.json.

Three concerns colocated here:
- Settings persistence (alongside-exe writable file, one field for now).
- Locale detection (OS user locale → one of SUPPORTED_LANGS).
- Translation lookup + locale-aware font (SysFont fallback chain).
"""

import json
import locale
import sys
from pathlib import Path

import pygame

SUPPORTED_LANGS = ("en", "zh_HK", "zh_CN")
DEFAULT_LANG = "en"


# ---------------------------------------------------------------------------
# Settings file. Writable, lives next to exe in frozen builds / project root in
# dev. Survives across the user's two PCs as separate state — never committed.
# ---------------------------------------------------------------------------

def settings_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "settings.json"


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


def app_root() -> Path:
    """Tree where read-only bundled files (data/, fonts/, etc) live.
    Project root in dev; sys._MEIPASS in frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


def init(lang: str) -> None:
    """Set the active language. First call also loads the translations file;
    later calls only switch `_current_lang` (the JSON is not re-read)."""
    global _translations, _current_lang
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    _current_lang = lang
    if not _translations:
        path = app_root() / "data" / "translations_app.json"
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
# Font — Windows-bundled CJK font per active language. Drops ShinGoPr6N from
# chrome (Japanese-glyph forms read wrong for Chinese); ShinGoPr6N stays for
# LCD station-name rendering where its JP forms are right.
#
# One CJK font per language (not a comma-fallback chain): pygame.font.SysFont
# treats comma lists as font-installation fallback only, NOT glyph-level
# fallback. So Arial-leading would render Arial for everything, and CJK
# glyphs come out as .notdef boxes. Single CJK font sidesteps this — JhengHei
# / YaHei both include Latin glyphs, so "English" labels render fine through
# them, and route names with kanji always render. JhengHei (EN) and YaHei
# (HK/CN) match heights at the same point size, so no per-language scaling
# is needed and one UI design works across locales.
# ---------------------------------------------------------------------------

_LANG_CHROME_FONT = {
    "en":    "microsoftjhenghei",
    "zh_HK": "microsoftyahei",
    "zh_CN": "microsoftyahei",
}

_font_cache: dict = {}


def font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Return a cached SysFont for the active language's chrome.
    Requires pygame.font.init() (called by pygame.init())."""
    name = _LANG_CHROME_FONT.get(_current_lang, "microsoftjhenghei")
    return font_named(name, size, bold=bold)


def font_named(name: str, size: int, *, bold: bool = False) -> pygame.font.Font:
    """Direct font access bypassing active language. Used by the language
    picker to lock each row's label to its own script's primary font, so
    fonts don't jump as the user hovers across rows."""
    key = (name, size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont(name, size, bold=bold)
    return _font_cache[key]

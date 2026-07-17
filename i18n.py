"""App-chrome internationalisation.

Surfaces: setup screen (classic + TIMS flow, incl. the home language knobs) +
auto-input debug panel (`panel.*` keys; de-jargoned for the lightly-public
audience, 2026-05-31). OOBE still to come. LCD station-name rendering is unrelated and stays on its own
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
    just means the language re-detects to the OS default each launch (and any
    OCR/interval overrides revert to defaults), which is acceptable."""
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"Warning: could not save settings to {settings_path()}: {e}")


# ---------------------------------------------------------------------------
# Locale detection. Maps OS user locale to one of SUPPORTED_LANGS.
# Bare "zh" / zh_TW / zh_HK / zh_MO / zh_Hant → Traditional (zh_HK).
# zh_CN / zh_SG / zh_Hans → Simplified.
# Anything else → zh_HK — the clean-install default is the app's HK-primary home
# language (the audience is HK railfans), NOT English. Users switch via the TIMS
# home language knobs. (DEFAULT_LANG="en" stays the TRANSLATION fallback — distinct.)
# ---------------------------------------------------------------------------


def detect_default_lang() -> str:
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        loc = ""
    # Simplified-Chinese OS → zh_CN; EVERYTHING else (incl. non-Chinese locales) → zh_HK,
    # the HK-primary clean-install default.
    if loc.startswith("zh") and any(tag in loc for tag in ("cn", "sg", "hans")):
        return "zh_CN"
    return "zh_HK"


def resolve_language(settings: dict) -> str:
    """First-run language resolution — PURE (dict in, lang out), no I/O, no screen.
    Saved language if valid, else the OS-locale default (`detect_default_lang`). The
    caller persists the result when it differs from what's stored (see `main.py`).

    Deliberately SCREEN-FREE: there is no interactive first-run picker. The pre-TIMS
    grey `LanguagePicker` was removed (redundant beside the TIMS home's language
    knobs) — critical_lessons §6. This function's total-over-a-dict contract is the
    regression guard: reintroducing an interactive language step in the first-run
    path would have to bypass it (locked by `_tests/t1_unit/test_resolve_language.py`
    + `_tests/t4_clean_frame/test_clean_frame_startup.py`)."""
    lang = settings.get("language")
    return lang if lang in SUPPORTED_LANGS else detect_default_lang()


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
    """Switch the active in-memory language at runtime (e.g. the TIMS home
    language knobs). Does NOT persist — callers that need durability write
    settings.json themselves (see setup_tims/home.py knob handler)."""
    global _current_lang
    if lang in SUPPORTED_LANGS:
        _current_lang = lang


def current_lang() -> str:
    return _current_lang


def t(key: str, *, lang: str | None = None, **fmt) -> str:
    """Return the localized string for `key`, in `lang` (default: the active
    language). EN fallback, then key itself. `lang=` lets a caller measure a
    key across all locales (e.g. worst-case button sizing) without disturbing
    the active language."""
    entry = _translations.get(key) or {}
    text = entry.get(lang or _current_lang) or entry.get(DEFAULT_LANG) or key
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

# Per-language TIMS chrome face — Noto Sans, rendered ANTIALIAS OFF at the native display px, NO
# upscale. The TIMS/embedded "pixel text" look is just an ordinary outline font with AA off (not a
# pixel font, not bitmap strikes, not upscaling). See conventions.md § "TIMS chrome text" (LOCKED
# 2026-06-27). Per-locale because Noto Sans JP Han-unifies / tofus Chinese (zh_HK = Traditional,
# zh_CN = Simplified); JP also serves station names + Latin/EN chrome. OFL — Noto's license must ship
# alongside the .otf (runtime-required, per critical_lessons §2); see fonts/NotoSans-OFL.txt. Faces
# are the Noto Sans Subset OTF (notofonts/noto-cjk Sans2.004, THIN weight — matches the prior
# NotoSans*-Thin.ttf the UI was tuned against); CFF outlines render identically to those TTFs with
# AA off, and .otf satisfies the fonts/ .otf-only rule.
# fmt: off
_LANG_PIXEL_FONT: dict[str, str] = {
    "en":    "NotoSansJP.otf",
    "zh_HK": "NotoSansTC.otf",
    "zh_CN": "NotoSansSC.otf",
}
# fmt: on

_font_cache: dict = {}


def font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Cached chrome font for the active language. Requires
    pygame.font.init() (called by pygame.init())."""
    return font_for_lang(_current_lang, size, bold=bold)


def font_for_lang(lang: str, size: int, *, bold: bool = False) -> pygame.font.Font:
    """Cached chrome font for an explicit language code, bypassing the
    active language — for rendering a label in a specific script's font
    regardless of the active locale (e.g. the setup-screen route rows)."""
    regular, bold_fname = _LANG_CHROME_FONT.get(lang, _LANG_CHROME_FONT["en"])
    fname = bold_fname if bold else regular
    key = (fname, size)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.Font(str(project_root() / "fonts" / fname), size)
    return _font_cache[key]


def pixel_font_for_lang(lang: str, size: int) -> pygame.font.Font:
    """Cached per-language TIMS chrome face (Noto Sans, per-locale) at `size` px — the DISPLAY size,
    rendered antialias-OFF with NO upscale (widgets.draw_lowres_text). One weight (no bold); per-locale
    like font_for_lang (Han unification). Routes through project_root()/fonts — never SysFont
    (Chinese-locale crash, 2026-03-14)."""
    fname = _LANG_PIXEL_FONT.get(lang, _LANG_PIXEL_FONT["en"])
    key = (fname, size)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.Font(str(project_root() / "fonts" / fname), size)
    return _font_cache[key]

# TIER: T1 — resolve_language() saved-or-detect logic
"""Locks first-run language resolution (`i18n.resolve_language`) as a PURE,
screen-free function — the unit-level regression guard for the 2026-07-16
language-picker incident (a stale interactive first-run picker no dev ever saw,
because settings.json is always populated locally; critical_lessons §6).

Pure: dict in, lang out. No disk, no display, no interactive step. The fact that
this is a TOTAL function over a settings dict is itself the invariant — a first-run
path can't reintroduce an interactive picker without bypassing it.

`detect_default_lang()` reads the OS locale, so the no-valid-saved-language cases
assert only that the result is a SUPPORTED language (not a specific one): the point
is that resolution always yields a usable language, on any machine, without a screen.
"""

import sys
from pathlib import Path

# _tests/ is dev harness (never shipped, exempt from the production path-resolver
# ban) — Path(__file__) here is fine. Put the repo root on sys.path for the import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import i18n  # noqa: E402


def main():
    failures = []

    # Valid saved language → returned verbatim, independent of the OS locale.
    for lang in i18n.SUPPORTED_LANGS:
        got = i18n.resolve_language({"language": lang})
        if got != lang:
            failures.append(f"  saved {lang!r} → {got!r}, expected {lang!r}")

    # Absent / null / unsupported / wrong-typed → falls back to a SUPPORTED language
    # (the OS default); never crashes, never returns the bad value. Returning any
    # unsupported value (e.g. "xx") fails the membership check below.
    for bad in ({}, {"language": None}, {"language": "xx"}, {"language": "en_US"}, {"language": 5}, {"other": 1}):
        got = i18n.resolve_language(bad)
        if got not in i18n.SUPPORTED_LANGS:
            failures.append(f"  {bad!r} → {got!r}, not a SUPPORTED language")

    if failures:
        print("FAIL: resolve_language")
        print("\n".join(failures))
        sys.exit(1)
    print(f"PASS: resolve_language (valid pass-through x{len(i18n.SUPPORTED_LANGS)} + absent/corrupt -> OS default, screen-free)")


if __name__ == "__main__":
    main()

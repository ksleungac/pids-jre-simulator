# SPDX-License-Identifier: MIT
# TIER: T4 — clean-frame startup (state-absent FIXTURE of the integration tier)
"""First-run / clean-install startup, exercised over the settings.json fixture no dev
machine ever has: ABSENT. This is the frame that shipped the stale language picker in
v0.6.0 — invisible in dev because settings.json is always populated locally, so the
first-run branch never executes (critical_lessons §6).

T4 is NOT a separate scope from T3 (integration). It IS the integration tier run with
the state-absent fixture. The FIXTURE axis (settings absent / present-valid / present-
corrupt) is orthogonal to the tier ladder; the absent row is singled out only because
it's the invisible-in-dev one. This module parametrizes over all three fixtures so the
first-run path and the normal-launch path sit side by side, same scope.

Integration, headless: redirects `i18n.settings_path` to a temp dir (never touches the
real repo-root settings.json) and drives the actual load/resolve/save path. No display.
Importing i18n pulls pygame in as a module but does not initialize it.
"""

import contextlib
import importlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import i18n  # noqa: E402


@contextlib.contextmanager
def settings_fixture(content):
    """Point i18n.settings_path at a temp dir. `content` None -> no file on disk
    (clean frame); a dict -> written as settings.json (populated frame)."""
    orig = i18n.settings_path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        if content is not None:
            path.write_text(json.dumps(content), encoding="utf-8")
        i18n.settings_path = lambda: path
        try:
            yield path
        finally:
            i18n.settings_path = orig


def _startup_resolve(settings):
    """Mirror of main.py's language-resolution block: resolve, persist iff changed."""
    lang = i18n.resolve_language(settings)
    changed = settings.get("language") != lang
    if changed:
        settings["language"] = lang
        i18n.save_settings(settings)
    return lang, changed


def main():
    failures = []

    # --- Fixture: ABSENT (genuine first-run / clean install) --------------------
    with settings_fixture(None):
        settings = i18n.load_settings()
        if settings != {}:
            failures.append(f"  absent -> load_settings()={settings!r}, expected {{}}")

        # First-run gates default deterministically with NO file present.
        if settings.get("oobe_completed", False) is not False:
            failures.append("  absent -> oobe_completed default not False (first-run OOBE would be skipped)")
        if settings.get("ocr_consent", False) is not False:
            failures.append("  absent -> ocr_consent default not False (consent gate would be bypassed)")

        # Language resolves to a usable language with no screen, and persists.
        lang, changed = _startup_resolve(settings)
        if lang not in i18n.SUPPORTED_LANGS:
            failures.append(f"  absent -> resolved language {lang!r} not SUPPORTED")
        if not changed:
            failures.append("  absent -> first-run did not persist a language (settings.json stays uninitialized)")

        # Idempotent: the persisted choice is re-read next launch, unchanged.
        reloaded = i18n.load_settings()
        if reloaded.get("language") != lang:
            failures.append(f"  absent -> after persist, reloaded language={reloaded.get('language')!r}, expected {lang!r}")
        _, changed2 = _startup_resolve(reloaded)
        if changed2:
            failures.append("  absent -> second launch re-persisted (not idempotent); a settled first-run must be stable")

    # --- Fixture: PRESENT-VALID (normal launch) --------------------------------
    with settings_fixture({"language": "zh_CN", "oobe_completed": True, "ocr_consent": True}):
        settings = i18n.load_settings()
        lang, changed = _startup_resolve(settings)
        if lang != "zh_CN":
            failures.append(f"  present-valid -> resolved {lang!r}, expected 'zh_CN'")
        if changed:
            failures.append("  present-valid -> normal launch re-persisted an already-valid language")
        if settings.get("oobe_completed", False) is not True:
            failures.append("  present-valid -> oobe_completed not read back True (first-run OOBE would re-fire)")

    # --- Fixture: PRESENT-CORRUPT (bad language value) -------------------------
    with settings_fixture({"language": "xx", "oobe_completed": True}):
        settings = i18n.load_settings()
        lang, changed = _startup_resolve(settings)
        if lang not in i18n.SUPPORTED_LANGS:
            failures.append(f"  present-corrupt -> resolved {lang!r} not SUPPORTED (bad value survived)")
        if not changed:
            failures.append("  present-corrupt -> invalid language not self-healed (no re-persist)")

    # --- Regression guard: the removed first-run picker stays removed ----------
    with contextlib.suppress(ImportError):
        importlib.import_module("language_picker")
        failures.append("  language_picker is importable again -- the stale first-run picker returned (critical_lessons #6)")

    if failures:
        print("FAIL: clean-frame startup")
        print("\n".join(failures))
        sys.exit(1)
    print("PASS: clean-frame startup (absent / present-valid / present-corrupt fixtures + picker-removed guard)")


if __name__ == "__main__":
    main()

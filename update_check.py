# SPDX-License-Identifier: MIT
"""Background check for a newer GitHub release — fail-silent update hint.

On launch, ``main.py`` kicks off ``check_async()`` in a daemon thread. It queries
the GitHub Releases API once, compares the latest tag against the running app's
version (``app_paths.app_version()`` — read from the exe's embedded PE metadata;
None in dev, so the check no-ops there), and stashes the result. The setup screen
polls ``get_update()`` each frame and, if a strictly-newer release exists, shows
a small clickable hint.

# CONTRACT: NEVER block the app, NEVER raise into it. Offline / GitHub down /
# SSL failure / rate-limit / malformed JSON → silent no-op (no hint). The app
# must launch and run identically with or without network. This is the app's
# ONLY outward network call; it sends no user data (GET only, no telemetry).
"""

import json
import ssl
import threading
import urllib.request

from app_paths import app_version

_REPO = "ksleungac/pids-jre-simulator"
_API_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_TIMEOUT_S = 3.0

# Set by the worker thread on success (newer release found); read by get_update().
_latest: tuple[str, str] | None = None  # (version_string, release_url)


def _parse(v: str) -> tuple[int, int, int, int]:
    """Parse ``v0.5.4`` / ``0.5.4b`` → ``(major, minor, patch, sub)``.

    Mirrors the /build version scheme: a trailing letter maps to ``sub``
    (a=1, b=2, …); no letter → sub=0. Unparseable components default to 0.
    """
    v = v.strip().lstrip("v")
    sub = 0
    if v and v[-1].isalpha():
        sub = ord(v[-1].lower()) - ord("a") + 1
        v = v[:-1]
    parts = (v.split(".") + ["0", "0", "0"])[:3]
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return (nums[0], nums[1], nums[2], sub)


def _worker() -> None:
    global _latest
    try:
        # certifi ships transitively; route SSL through it so HTTPS verification
        # works in the frozen exe (where the bundled Python may not find CA certs).
        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": "JRE-PA-Simulator", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S, context=ctx) as resp:
            data = json.load(resp)
        local = app_version()
        if local is None:
            return  # defensive — check_async already gates on this
        tag = data.get("tag_name", "")
        url = data.get("html_url") or f"https://github.com/{_REPO}/releases/latest"
        if tag and _parse(tag) > _parse(local):
            _latest = (tag.lstrip("v"), url)
    except Exception:
        pass  # fail-silent — any failure simply means "no hint"


def check_async() -> None:
    """Start the one-shot background check. Call once at startup.

    No-op in dev (``app_version()`` is None when not frozen) — update hints
    only make sense for the shipped exe, whose version is read from its own
    embedded PE metadata.
    """
    if app_version() is None:
        return
    threading.Thread(target=_worker, daemon=True, name="update-check").start()


def get_update() -> tuple[str, str] | None:
    """Return ``(latest_version, release_url)`` if a newer release exists, else None.

    Non-blocking — returns None until the worker succeeds (or forever if offline
    / failed). Safe to poll every frame.
    """
    return _latest

# TODO — moved to GitHub Issues

The active backlog now lives in **GitHub Issues**: https://github.com/ksleungac/pids-jre-simulator/issues

- **Browse / triage** on the Issues tab. Filter by area label: `auto-input`, `display`, `chrome-i18n`, `distribution`, `housekeeping`, `review-finding`, `build-incident`.
- **Status lives in labels:** `in-progress` (a session is actively on it), `deferred` (parked — see the issue's reason comment). Closure is authoritative: a pushed commit with `Closes #N` closes the issue.
- **Working loop:** session start (`_harness/session_init.py`) prints the open / in-progress / recently-closed / stale summary · `/commit` writes the `Closes #N` / `Refs #N` trailer · `/session-recap` reconciles against `gh issue list`.

Only the **closed-off paths** ledger stays in-repo below — it's an anti-backlog (ground we've decided NOT to walk), not work items, so it never becomes an issue.

---

## Closed-off paths (don't re-propose)

Recording the ground we've explicitly decided NOT to walk, so future sessions don't re-litigate:

- **Memory hooking the game's `*saf.dll` modules.** Tried, dead end.
- **Decrypting SimDATA assets.** Encrypted; not pursuing.
- **Audio fingerprinting** for stop detection. Replaced by HUD OCR which works.
- **Full-desktop OCR** instead of window-bound capture. Privacy + perf concerns.
- **Tesseract-based OCR.** Too heavy; pixel-perfect template match works.
- **Mac build.** The companion game (JR EAST Train Sim Real) is Windows-only — no Mac audience exists for this app. Not worth the porting cost.
- **Scaling to lines the game already covers** (Sobu local, Yokosuka, etc. — newer game routes ship with PA, don't duplicate).
- **OCR-as-display-layer fidelity-purity argument.** OCR is an *input layer* (replaces PageDown press), not display. Don't recycle.

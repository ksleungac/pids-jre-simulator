---
name: build
description: Build the JRE-PA-Simulator Windows executable + staged distribution folder (no GitHub release). Embeds version in exe metadata.
triggers:
  - /build
  - build exe
  - build executable
  - build distribution
---

## Purpose

Reproduce the PyInstaller build locally: produce a one-file exe with version metadata embedded, stage the distribution folder (`dist-release/JRE-PA-Simulator/`), and stop there. Zipping and GitHub release are separate, opt-in steps — `release.ps1` is the all-in-one path; this skill is the "just build and let me test" path.

## Required input

**Version** (e.g. `0.5.2`, `v0.5.2`, `0.5.2b`).

- If the user didn't provide a version in the invocation, **ask for it first**. Do not guess, do not reuse a version from a prior session, do not read it from git tags — ask.
- **Subversion letters are NOT betas.** `a`, `b`, `c` are sequential sub-revisions of the same patch (user's scheme). Do not treat `b` as "beta" and suppress it anywhere — it must survive into the exe metadata and filenames verbatim.
- **Normalize for filenames/display**: strip any leading `v`, then always re-add `v` in output filenames (see Step 6). So `0.5.2` and `v0.5.2` both produce `JRE-PA-Simulator-v0.5.2-distribution.zip`.
- **Parse into a 4-tuple `(major, minor, patch, sub)`** for the Windows version resource:
  - `major.minor.patch` from the numeric components (missing → `0`).
  - `sub` from the trailing letter: `a`→1, `b`→2, `c`→3, … (one-letter case `ord(letter) - ord('a') + 1`). No letter → `sub = 0`.
  - Examples: `0.5.2` → `(0, 5, 2, 0)`; `0.5.2a` → `(0, 5, 2, 1)`; `0.5.2b` → `(0, 5, 2, 2)`; `v0.5.2c` → `(0, 5, 2, 3)`.
  - Multi-letter or non-`[a-z]` trailing suffix: stop, ask the user to clarify — do not silently drop it.
- **String fields** (`FileVersion`, `ProductVersion`): preserve the full normalized string *without* the `v` prefix, letter intact. E.g. `v0.5.2b` → `"0.5.2b"`.

## Process

### Step 1 — Confirm version

If not provided, ask: *"What version should I tag this build? (e.g. 0.5.2)"*. Wait for answer before proceeding.

### Step 2 — Generate `version_info.txt`

Write a PyInstaller Windows version resource to the project root. Overwrite any existing file. Template:

```python
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(MAJOR, MINOR, PATCH, BUILD),
    prodvers=(MAJOR, MINOR, PATCH, BUILD),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u''),
         StringStruct(u'FileDescription', u'JR East PA Simulator'),
         StringStruct(u'FileVersion', u'VERSION_STRING'),
         StringStruct(u'InternalName', u'JRE-PA-Simulator'),
         StringStruct(u'OriginalFilename', u'JRE-PA-Simulator.exe'),
         StringStruct(u'ProductName', u'JRE-PA-Simulator'),
         StringStruct(u'ProductVersion', u'VERSION_STRING')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
```

Substitute `MAJOR/MINOR/PATCH/BUILD` (numbers, per the parsing rules above — `BUILD` comes from the subversion letter) and `VERSION_STRING` (the user's string, leading `v` stripped, trailing letter preserved).

The file lives at project root and is **gitignored** — it's a per-build artifact, not source. Overwrite freely.

### Step 3 — Clean & build

`dist-release/JRE-PA-Simulator/audio` may be a **junction** from a previous run (pointing at the project's real `audio/`). A naive `Remove-Item -Recurse` will follow the junction and delete your real audio files. Always break the junction first:

```powershell
# Break audio junction if it exists (don't recurse into the real audio/!)
$audioJunction = "dist-release\JRE-PA-Simulator\audio"
if (Test-Path $audioJunction) {
    $item = Get-Item $audioJunction -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        [System.IO.Directory]::Delete($item.FullName, $false)
    }
}
Remove-Item -Path "dist", "dist-release", "build" -Recurse -Force -ErrorAction SilentlyContinue

uv run --no-dev --group build pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm --version-file version_info.txt --collect-data plotly
```

`--no-dev --group build` isolates the build venv to **prod deps + pyinstaller only** — no `librosa` / `ffmpeg-python` / `black` / `pyright` visible to PyInstaller's static analysis. Defense-in-depth against accidental dev-dep bundling. The `build` dependency group is declared in `pyproject.toml`; if a future build step needs another tool (e.g. UPX), add it there.

`--console` is required — a console window is needed for error visibility on non-English Windows (where Japanese stdout requires `PYTHONUTF8=1` or `sys.stdout.reconfigure('utf-8')`, and silent crashes are otherwise invisible). If the build fails, surface the pyinstaller error verbatim and stop.

`--collect-data plotly` ships plotly's `package_data/` subdirectory — specifically `plotly.min.js`, the ~3MB JS bundle that `fig.to_html(include_plotlyjs='inline')` reads at runtime. PyInstaller's static import analysis bundles plotly's `.py` files but skips non-Python data files; without this flag, the Report ↓ button in the OCR debug panel silently breaks in release builds (lib loads, but its JS bundle is missing → render-time crash swallowed by the `try/except` in `auto_input.py:_render_report_async`). Discovered by /review+fix Lens 1 on 2026-04-30 reviewing commit `51c7b07`. If a future runtime-asset-shipping lib enters `dependencies` (matplotlib, bokeh, ...), add a sibling `--collect-data <lib>` here.

### Step 4 — Stage distribution folder (with audio junction for testing)

The shipped zip ships the audio folder populated with all real route data (excluding `audio/_*/` — preserved-but-not-shipped). During smoke-test we want the staged folder to be **immediately runnable** without first copying ~600 MB of audio, so we use a **junction**: `dist-release/JRE-PA-Simulator/audio` points at the project's real `audio/`. At zip time, Step 6 breaks the junction and replaces it with a real directory containing the shippable subset.

**Inclusion model — default-ship, not hand-picked.** Stage every top-level project-root directory by default; maintain only an exclusion list. This solves the recurring "we forgot to add the new asset folder" class (2026-05-05 line_icons + ocr_templates) — new folders ship automatically; if a folder shouldn't ship, you add it to `$shipExclude` in a single visible action. The cost asymmetry is heavy in favor of over-shipping: missing-required-asset = release crash; extra-shipped-folder = a few MB in the zip.

```powershell
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator" | Out-Null
Copy-Item "dist\JRE-PA-Simulator.exe" "dist-release\JRE-PA-Simulator\"

# Default-ship every top-level directory at project root, excluding:
# - `_*` prefix (preserved-not-shipped: _archive, _mock, _dev_scripts, ...)
# - `.*` prefix (.git, .venv, .claude, .github, .vscode, .idea, ...)
# - Hard-listed dev / repo-only / build-output folders below.
$shipExclude = @(
    'dist', 'dist-release', 'build',  # build outputs (would self-recurse)
    'displays',                        # Python source — bundled INTO exe by PyInstaller, not alongside
    'memory', 'lcd_references',        # repo-only / dev refs
    'audio_src', 'docs'                # dev tooling / repo-only
)

$shipDirs = Get-ChildItem -Path "." -Directory | Where-Object {
    $_.Name -notmatch '^[_.]' -and $_.Name -notin $shipExclude
}

Write-Host "Shipping top-level directories:" -ForegroundColor Cyan
$shipDirs | ForEach-Object { Write-Host "  $($_.Name)" }

foreach ($dir in $shipDirs) {
    if ($dir.Name -eq 'audio') {
        # audio/ — junction during smoke test (Step 6 breaks + replaces with real copy at zip time)
        $projectAudio = (Resolve-Path "audio").Path
        New-Item -ItemType Junction -Path "dist-release\JRE-PA-Simulator\audio" -Target $projectAudio | Out-Null
    } else {
        # Recursive copy, excluding `_*` harness subdirs (matches the audio/_*/ pattern)
        $destDir = "dist-release\JRE-PA-Simulator\$($dir.Name)"
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Get-ChildItem -Path $dir.FullName | Where-Object { $_.Name -notmatch '^_' } | ForEach-Object {
            Copy-Item -Path $_.FullName -Destination $destDir -Recurse -Force
        }
    }
}
```

- **The print-out of `$shipDirs`** is a soft guard — eyeball-confirm what's being staged at the start of every build. If something appears that shouldn't, add to `$shipExclude` (a deliberate, visible action) and re-run.
- **Adding a new top-level dev-only folder** (e.g. `_visual_iter/`, `_recordings/`, `audio_src/`) — convention is `_*` prefix or `.*` prefix; otherwise add to `$shipExclude`. New shipped folders need no skill edit at all.
- **The `_*` filter applies recursively** — `data/_*`, `fonts/_*`, `ocr_templates/_*` would all be excluded if added in future, matching the `audio/_*/` Step-6 pattern.
- Junction caveats:
  - Works without admin rights (junctions ≠ symlinks on Windows).
  - The exe sees it as an ordinary `audio/` directory — `Path(sys.executable).parent / "audio" / ...` resolves through transparently.
  - Never `Remove-Item -Recurse` the staged folder without breaking the junction first (see Step 3's guard).
  - `Compress-Archive` follows the junction transparently. We still break + replace before zipping in Step 6 — both because we need to *exclude* `audio/_*/` from the shipped zip (the junction would pull them in) and because junctions inside zips are messy on extraction.

### Step 5 — Launch exe for user + HARD STOP for smoke test

**Auto-launch the exe from the staged folder** so the user doesn't have to hunt for it. Use `Start-Process` (non-blocking — it returns immediately; the exe runs in its own window and does not tie up this shell):

```powershell
Start-Process -FilePath "dist-release\JRE-PA-Simulator\JRE-PA-Simulator.exe" `
              -WorkingDirectory "dist-release\JRE-PA-Simulator"
```

Setting `-WorkingDirectory` matches what happens when the user double-clicks in Explorer. The exe itself uses `sys.executable` for path resolution, so CWD doesn't affect `fonts/` / `data/` / `audio/` loading — but log files and crash dumps land next to the working directory.

Then report:
- Exe path + size (`dist\JRE-PA-Simulator.exe`)
- Staged folder path (`dist-release\JRE-PA-Simulator\` — audio/ is a junction to `<project-root>/audio/`, so real routes are testable)
- Embedded version (readable via right-click → Properties → Details on Windows)
- "I launched it for you — check the setup screen and pick a diagram to smoke-test."

**Do not proceed further until the user explicitly confirms the smoke test passed.** Launching the exe ≠ verifying it works — fonts can fail to load, JSON can be missing, audio routes can misbehave, and you will not see any of that from here. Only the user can verify.

Do NOT:
- Zip the folder preemptively.
- Assume `Start-Process` succeeding means the app is running correctly — it only means the OS accepted the launch request. Font loading, JSON path resolution, and mixer init all fail post-launch if they fail at all.
- Try to read the exe's stdout/stderr to "check" (it's detached; output goes to its own console window).

Wait for an explicit "works / ok / ship it / zip it" from the user before Step 6.

### Step 6 (ONLY after user confirms smoke test passed) — Break audio junction, copy shippable audio, then zip

The staged `audio/` is a junction to the project's real `audio/`. We need to break it and replace with a real directory containing only the line folders that ship — *excluding* `audio/_*/` (preserved-but-not-shipped: `_archive/`, `_mock/`).

```powershell
# Break the audio junction (deletes the junction entry, NOT the target)
$audioJunction = "dist-release\JRE-PA-Simulator\audio"
$item = Get-Item $audioJunction -Force
if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    [System.IO.Directory]::Delete($item.FullName, $false)
} else {
    # Defensive: if it's not a junction, something is off — abort rather than risk deleting real audio
    throw "Expected $audioJunction to be a junction, found $($item.Attributes). Aborting zip."
}
New-Item -ItemType Directory -Force -Path $audioJunction | Out-Null

# Copy each line folder under audio/ that is NOT `_`-prefixed (~600 MB at time of writing)
Get-ChildItem -Path "audio" -Directory | Where-Object { $_.Name -notmatch '^_' } | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $audioJunction -Recurse -Force
}

# Zip
Compress-Archive -Path "dist-release\JRE-PA-Simulator" -DestinationPath "dist-release\JRE-PA-Simulator-v<VERSION>-distribution.zip" -Force
```

The `_*` exclusion is critical: `_archive/` (working backups, Sobu reference recordings, etc.) and `_mock/` (preview-only test catalog) must never reach end users — those are repo-internal scaffolding.

**Never** use `Remove-Item -Recurse -Force $audioJunction` — `Remove-Item` with `-Recurse` on a junction follows the reparse point and deletes the real audio directory. Use `[System.IO.Directory]::Delete(path, false)` instead, which removes only the junction entry.

**Filename version**: always `v` + the normalized numeric+letter string (e.g. `v0.5.2`, `v0.5.2b`). If the user typed `v0.5.2`, strip their `v` first and re-add one — never produce `vv0.5.2`.

**After zipping**: the staged folder now has a populated real `audio/` directory (~600 MB), not the junction. If the user wants to keep iterating with the staged folder against live audio edits, re-run `/build` to recreate the junction in Step 4. Mention zip size in the final report — typical ship: ~660 MB (exe + fonts + data + audio); GitHub release file limit is 2 GB so there's headroom.

## Next step (when user wants to publish)

After the user has confirmed the smoke test and zipped (Step 6), the publish flow continues in `/release`. That skill picks up here: pre-flights the build artifacts, drafts `release_notes.md` with the criteria below, tags the commit, and hands the `gh release create` command to the user.

Don't run `/release` automatically — wait for the user to invoke it. `/build` ends at "zip ready on disk."

## Out of scope

- **GitHub release**: never run `gh release create` from this skill. That's `/release`'s job. If the user wants a release, point them at `/release <version>`.
- **Committing/pushing**: do not touch git.
- **Version bumping**: this skill does not modify `pyproject.toml` or any other source. The version is a build-time label only.

## `_*` folder convention (preserved-but-not-shipped)

Folders prefixed with `_` under `audio/` (e.g. `audio/_mock/`, `audio/_archive/`) are preserved in the repo but **must not ship** to end users. Step 6 explicitly enforces this via the `Where-Object { $_.Name -notmatch '^_' }` filter when copying line folders into the staged audio directory. Same convention applies recursively to any future `data/_*`, `fonts/_*`, `ocr_templates/_*` — Step 4's per-dir `Get-ChildItem ... | Where-Object { $_.Name -notmatch '^_' }` block already excludes them, so no skill edit is needed when new harness subdirs appear under shipped trees.

The smoke-test junction in Step 4 transparently includes `_*/` folders — that's intentional. The user can preview-test against the mock catalog from inside the staged folder before the zip excludes them.

## Release notes criteria (for when `release.ps1` eventually runs)

Even though this skill doesn't generate notes, when you *do* help assemble them (pre-writing `release_notes.md` before the user runs `release.ps1`), apply this rule:

> **Include a change in user-facing release notes iff the artifact it affects ships inside the distribution zip.**

What ships: the exe, `fonts/`, `data/*.json`, `audio/**` (excluding `audio/_*/`). Anything that lands in `dist-release/JRE-PA-Simulator/` qualifies.

What does **not** ship: `README*.md` (repo-only), `CLAUDE.md`, `.claude/**`, `.github/**`, `memory/**`, `pyproject.toml`, test/preview harnesses, the mock route catalog (`audio/mock/**`). Changes to these are invisible to end users of the exe → omit from notes.

Future: if manuals/guides are ever bundled into the distribution (e.g. `dist-release/JRE-PA-Simulator/manual.pdf`), they flip from "repo-only" to "shipped" and start qualifying.

Mixed commits (one commit touches both shipped and repo-only paths): report only the shipped-facing portion. The commit-hygiene skill (`/commit`) should catch cases where the shipped and repo-only pieces were bundled into one commit unnecessarily — read it for the reasonable-mixing vs. unrelated-mixing distinction.

## Why these choices

- **Version in metadata, not filename**: keeps the exe name stable (`JRE-PA-Simulator.exe`) so the `fonts/` + `data/` folder layout stays canonical and any external scripts/shortcuts don't break per release. Version is discoverable via Windows' native Properties dialog.
- **Build stops before zipping**: user has explicitly preferred "let me test the exe first" — zipping is trivial to run on confirmation and prevents wasting disk on untested builds.
- **Ask for version, never guess**: a wrong version silently embedded in a shipped exe is worse than a 2-second round trip to ask.

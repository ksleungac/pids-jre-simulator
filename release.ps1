# JRE-PA-Simulator Release Script
# Usage: .\release.ps1 v0.5.0b

param(
    [Parameter(Mandatory=$true)]
    [string]$VERSION
)

Write-Host "=== Building JRE-PA-Simulator Release $VERSION ===" -ForegroundColor Cyan

# Clean previous builds
Remove-Item -Path "dist", "dist-release", "build" -Recurse -Force -ErrorAction SilentlyContinue

# Parse $VERSION into tuple + string for Windows version resource (matches /build skill)
# Subversion letters are sub-revisions, not beta: a=1, b=2, c=3 → 4th tuple slot.
$versionString = $VERSION -replace '^v', ''
if ($versionString -notmatch '^(\d+)\.(\d+)\.(\d+)([a-z])?$') {
    throw "Cannot parse version '$versionString'. Expected format: MAJOR.MINOR.PATCH[a-z] (e.g. 0.5.2, 0.5.2b)."
}
$major = [int]$matches[1]
$minor = [int]$matches[2]
$patch = [int]$matches[3]
$sub   = if ($matches[4]) { [int][char]$matches[4] - [int][char]'a' + 1 } else { 0 }

# Write version_info.txt for PyInstaller --version-file
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($major, $minor, $patch, $sub),
    prodvers=($major, $minor, $patch, $sub),
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
         StringStruct(u'FileVersion', u'$versionString'),
         StringStruct(u'InternalName', u'JRE-PA-Simulator'),
         StringStruct(u'OriginalFilename', u'JRE-PA-Simulator.exe'),
         StringStruct(u'ProductName', u'JRE-PA-Simulator'),
         StringStruct(u'ProductVersion', u'$versionString')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
$versionInfo | Out-File -FilePath "version_info.txt" -Encoding ascii

# Build executable
Write-Host "`n[1/5] Building executable (embedding version $versionString)..." -ForegroundColor Yellow
uv run --no-dev --group build pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm --version-file version_info.txt --collect-data plotly
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

# Create distribution folder structure
Write-Host "`n[2/5] Creating distribution folder..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator\fonts" | Out-Null
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator\data" | Out-Null
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator\audio" | Out-Null

Copy-Item "dist\JRE-PA-Simulator.exe" "dist-release\JRE-PA-Simulator\"
Copy-Item "fonts\*" "dist-release\JRE-PA-Simulator\fonts\"
Copy-Item "data\*.json" "dist-release\JRE-PA-Simulator\data\"

# Copy audio data — excluding `_*`-prefixed folders (preserved-but-not-shipped: _archive, _mock, etc.)
Get-ChildItem -Path "audio" -Directory | Where-Object { $_.Name -notmatch '^_' } | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "dist-release\JRE-PA-Simulator\audio" -Recurse -Force
}

# Create distribution zip
Write-Host "`n[3/5] Creating distribution zip..." -ForegroundColor Yellow
Compress-Archive -Path "dist-release\JRE-PA-Simulator" -DestinationPath "dist-release\JRE-PA-Simulator-$VERSION-distribution.zip" -Force

# Generate (or reuse) release notes
# If release_notes.md already exists, honor it — Claude may have pre-written prose notes
# with the shipped-artifact rule applied and mixed commits split. Only fall back to the
# auto-classifier when no prose exists.
$notesExistedBeforehand = Test-Path "release_notes.md"

if ($notesExistedBeforehand) {
    Write-Host "`n[4/5] Using pre-written release_notes.md (skipping auto-classifier)..." -ForegroundColor Yellow
} else {
    Write-Host "`n[4/5] Generating release notes..." -ForegroundColor Yellow

    # Find the previous release tag: the tag immediately before $VERSION in creation order,
    # or (if $VERSION isn't tagged yet) the most recent existing tag. No tags -> full history.
    $allTags = @(git tag --list --sort=-creatordate)
    $prevTag = $null
    $hitCurrent = $false
    foreach ($t in $allTags) {
        if ($hitCurrent) { $prevTag = $t; break }
        if ($t -eq $VERSION) { $hitCurrent = $true }
    }
    if (-not $prevTag -and $allTags.Count -gt 0 -and -not $hitCurrent) {
        $prevTag = $allTags[0]
    }

    if ($prevTag) {
        $range = "$prevTag..HEAD"
        Write-Host "  Changelog range: $range" -ForegroundColor DarkGray
    } else {
        $range = "HEAD"
        Write-Host "  Changelog range: full history (no prior tags)" -ForegroundColor DarkGray
    }

    # Classify each commit: "Data" = every touched file is shipped data (under data/ or audio/,
    # but NOT under audio/_*/ — those are harness/archive folders that don't ship to users).
    # Anything else (code, docs, harness-only, mixed) → "Program".
    $dataLines = @()
    $programLines = @()
    $commits = @(git log $range --pretty=format:"%H|%s" --no-merges --reverse)
    foreach ($c in $commits) {
        if (-not $c) { continue }
        $parts = $c -split '\|', 2
        $hash = $parts[0]
        $subject = $parts[1]
        $files = @(git show --pretty=format: --name-only $hash | Where-Object { $_ -ne "" })
        if ($files.Count -eq 0) { continue }
        $isDataOnly = $true
        foreach ($f in $files) {
            $isShippedData = ($f -match '^data/' -and $f -notmatch '^data/_') `
                          -or ($f -match '^audio/' -and $f -notmatch '^audio/_')
            if (-not $isShippedData) { $isDataOnly = $false; break }
        }
        if ($isDataOnly) { $dataLines += "- $subject" }
        else             { $programLines += "- $subject" }
    }

    $sections = @()
    if ($programLines.Count -gt 0) { $sections += "### Program`n" + ($programLines -join "`n") }
    if ($dataLines.Count    -gt 0) { $sections += "### Data`n"    + ($dataLines    -join "`n") }
    $changelogBody = if ($sections.Count -gt 0) { $sections -join "`n`n" } else { "_No changes since previous release._" }

    $notes = @"
## $VERSION Release

$changelogBody

---
**Distribution:** JRE-PA-Simulator.exe must be placed alongside ``fonts/``, ``data/``, and ``audio/`` folders at the same directory level.
"@
    $notes | Out-File -FilePath "release_notes.md" -Encoding utf8
}

# Create GitHub release
Write-Host "`n[5/5] Creating GitHub release..." -ForegroundColor Yellow
gh release create $VERSION `
    --title "$VERSION" `
    --notes-file "release_notes.md" `
    --verify-tag `
    "dist/JRE-PA-Simulator.exe" `
    "dist-release/JRE-PA-Simulator-$VERSION-distribution.zip"

Write-Host "`n=== Release $VERSION completed! ===" -ForegroundColor Green
Write-Host "View at: https://github.com/ksleungac/pids-jre-simulator/releases/tag/$VERSION" -ForegroundColor Green

# Cleanup (but preserve user-written notes)
if (-not $notesExistedBeforehand) {
    Remove-Item "release_notes.md" -Force -ErrorAction SilentlyContinue
}

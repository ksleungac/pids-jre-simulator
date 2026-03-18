# JRE-PA-Simulator Release Script
# Usage: .\release.ps1 v0.5.0b

param(
    [Parameter(Mandatory=$true)]
    [string]$VERSION
)

Write-Host "=== Building JRE-PA-Simulator Release $VERSION ===" -ForegroundColor Cyan

# Clean previous builds
Remove-Item -Path "dist", "dist-release", "build" -Recurse -Force -ErrorAction SilentlyContinue

# Build executable
Write-Host "`n[1/5] Building executable..." -ForegroundColor Yellow
uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

# Create distribution folder structure
Write-Host "`n[2/5] Creating distribution folder..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator\fonts" | Out-Null
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator\data" | Out-Null
New-Item -ItemType Directory -Force -Path "dist-release\JRE-PA-Simulator\audio" | Out-Null

Copy-Item "dist\JRE-PA-Simulator.exe" "dist-release\JRE-PA-Simulator\"
Copy-Item "fonts\*" "dist-release\JRE-PA-Simulator\fonts\"
Copy-Item "data\translations.json" "dist-release\JRE-PA-Simulator\data\"
Copy-Item "data\train_types.json" "dist-release\JRE-PA-Simulator\data\"

# Create distribution zip
Write-Host "`n[3/5] Creating distribution zip..." -ForegroundColor Yellow
Compress-Archive -Path "dist-release\JRE-PA-Simulator" -DestinationPath "dist-release\JRE-PA-Simulator-$VERSION-distribution.zip" -Force

# Generate release notes from git changelog
Write-Host "`n[4/5] Generating release notes..." -ForegroundColor Yellow
$changelog = git log --pretty=format:"- %s" --no-merges --reverse
$notes = @"
## $VERSION Release

### Changes
$changelog

---
**Distribution:** JRE-PA-Simulator.exe must be placed alongside `fonts/`, `data/`, and `audio/` folders at the same directory level.
"@
$notes | Out-File -FilePath "release_notes.md" -Encoding utf8

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

# Cleanup
Remove-Item "release_notes.md" -Force -ErrorAction SilentlyContinue

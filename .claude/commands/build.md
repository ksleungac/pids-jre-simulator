# Build JRE-PA-Simulator

Build the executable with PyInstaller.

## Command to run

```bash
uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm
```

## Notes

- Output: `dist/JRE-PA-Simulator.exe` (~57MB)
- **Distribution structure** - folders must be alongside exe at runtime:
  ```
  your-folder/
  ├── JRE-PA-Simulator.exe
  ├── fonts/
  ├── data/
  └── audio/
  ```
- Version in `pyproject.toml`
- Console enabled (`--console`) for error visibility on non-English Windows systems

## Create Release

Use the release script (requires `gh` CLI authenticated with `workflow` scope):

```powershell
# Build exe, create zip, and publish release in one command
.\release.ps1 v0.5.0b
```

**What the script does:**
1. Builds executable with PyInstaller
2. Creates distribution folder (exe + fonts + data + empty audio)
3. Creates distribution zip
4. Generates release notes from git changelog
5. Creates GitHub release and uploads both files

**Manual alternative:**
```powershell
# Build
uv run pyinstaller --onefile --console --name "JRE-PA-Simulator" main.py --clean --noconfirm

# Create tag
git tag v0.5.0b

# Create release with files
gh release create v0.5.0b --title "v0.5.0b" --generate-notes --verify-tag `
    dist/JRE-PA-Simulator.exe
```

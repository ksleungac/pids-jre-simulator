# Build Executable

Builds the JRE-PA-Simulator with PyInstaller.

## Command

```bash
uv run pyinstaller --onefile --windowed --name "JRE-PA-Simulator" main.py --clean --noconfirm
```

## Output

`dist/JRE-PA-Simulator.exe` (~57MB)

## Notes

- Audio/fonts not bundled - keep alongside exe at runtime
- Version in `pyproject.toml`

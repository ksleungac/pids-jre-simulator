# Build JRE-PA-Simulator

Build the executable with PyInstaller.

## Command to run

```bash
uv run pyinstaller --onefile --windowed --name "JRE-PA-Simulator" main.py --clean --noconfirm
```

## Notes

- Output: `dist/JRE-PA-Simulator.exe` (~57MB)
- Audio/fonts not bundled - keep alongside exe at runtime
- Version in `pyproject.toml`

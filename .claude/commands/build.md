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

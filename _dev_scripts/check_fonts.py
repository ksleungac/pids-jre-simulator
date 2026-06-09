"""Ban .ttf fonts in fonts/ — .otf only. See conventions.md § Tooling."""

import sys

if sys.argv[1:]:
    for f in sys.argv[1:]:
        print(f"{f}: .ttf fonts banned — use .otf only. See conventions.md § Tooling.")
    sys.exit(1)

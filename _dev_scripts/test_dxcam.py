# SPDX-License-Identifier: MIT
"""Minimal dxcam test — capture whole desktop, save PNG. No window detection, no OCR.

Run: uv run python _dev_scripts/test_dxcam.py
Then open _experiments/live_captures/desktop_test.png to see what dxcam returned.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import dxcam
import pygame

sys.path.insert(0, str(Path(__file__).parent.parent))

from window_utils import declare_dpi_awareness  # noqa: E402

# Production's declaration, not a local copy — awareness decides what a capture SEES, so a
# diagnostic that declares it differently from the app is measuring a different desktop
# (`principles.md` § "A second implementation of a production decision drifts silently").
declare_dpi_awareness()


def main() -> int:
    pygame.init()

    print("Creating dxcam camera (default = primary monitor)...")
    camera = dxcam.create(output_color="BGRA")
    if camera is None:
        print("dxcam.create() returned None — DXGI capture unavailable.")
        return 1

    print("Grabbing full desktop frame (with retries)...")
    frame = None
    for attempt in range(10):
        frame = camera.grab()
        if frame is not None:
            break
        time.sleep(0.3)
        print(f"  attempt {attempt + 1}: grab() returned None")

    if frame is None:
        print("All retries returned None — dxcam did not produce a frame.")
        return 1

    height, width = frame.shape[:2]
    brightness = float(frame[:, :, :3].mean())
    print(f"Got frame: {width}x{height}, brightness_mean={brightness:.1f} (0=black, 255=white)")

    out_dir = Path(__file__).parent.parent / "_experiments" / "live_captures"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "desktop_test.png"
    surf = pygame.image.frombuffer(frame.tobytes(), (width, height), "BGRA")
    pygame.image.save(surf, str(path))
    print(f"saved -> {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

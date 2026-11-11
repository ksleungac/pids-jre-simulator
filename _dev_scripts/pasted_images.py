# SPDX-License-Identifier: MIT
"""List, or save, the images the author pasted into a Claude Code session.

KEEP — the desktop app does not write a pasted image to disk, so a reference the
author pastes into chat exists only inside the session transcript, base64-encoded
(author, 2026-11-11: saving references is claude's call, and automated). This
reads the transcript and writes the image out, so a pasted reference can be
measured like any other.

    uv run _dev_scripts/pasted_images.py                    # list this project's newest session
    uv run _dev_scripts/pasted_images.py --save N out.png   # write image N
    uv run _dev_scripts/pasted_images.py --session <id|path.jsonl> ...

A pasted image is one of two record shapes: an image block at the top level of a
`user` message (pasted with the message that starts a turn), or an `attachment`
record (pasted while a turn is running). Images inside a `tool_result` are
claude's own reads and screenshots, and `api-request-blob` records repeat what
was sent, so neither is listed.
"""

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import project_root  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def _transcript(session) -> Path:
    """The session's transcript: a path, a session id, or this project's newest."""
    if session and Path(session).suffix == ".jsonl":
        return Path(session)
    folder = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project_root()))
    if session:
        return folder / f"{session}.jsonl"
    return max(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def pasted(path: Path) -> list:
    """`[(line, timestamp, media_type, bytes), ...]` in transcript order."""
    out = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "user":
                content = (rec.get("message") or {}).get("content")
                blocks = content if isinstance(content, list) else []
            elif rec.get("type") == "attachment":
                blocks = (rec.get("attachment") or {}).get("prompt") or []
            else:
                continue
            for b in blocks:
                if not isinstance(b, dict):
                    continue  # a content list may carry bare strings
                src = b.get("source") or {}
                if b.get("type") == "image" and src.get("type") == "base64":
                    out.append((ln, rec.get("timestamp"), src.get("media_type"), base64.b64decode(src["data"])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", help="session id or transcript path (default: this project's newest)")
    ap.add_argument("--save", nargs=2, metavar=("N", "PATH"), help="write image N to PATH, converted by extension")
    args = ap.parse_args()

    path = _transcript(args.session)
    images = pasted(path)
    if args.save:
        n, dest = int(args.save[0]), Path(args.save[1])
        pygame.image.save(pygame.image.load(io.BytesIO(images[n][3])), str(dest))
        print(f"saved image {n} ({pygame.image.load(str(dest)).get_size()}) to {dest}")
        return 0
    print(f"{path.name}: {len(images)} pasted image(s)")
    for i, (ln, ts, mt, raw) in enumerate(images):
        size = pygame.image.load(io.BytesIO(raw)).get_size()
        print(f"  {i}  {ts}  {mt:10s}  {size[0]}x{size[1]}  ({len(raw)} bytes, transcript line {ln})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

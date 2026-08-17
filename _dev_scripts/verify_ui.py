# SPDX-License-Identifier: MIT
"""Shared UI + audio primitives for the by-ear verifiers.

`verify_sta_listen.py` and `verify_pa_listen.py` are separate tools with genuinely
different playback models — STA cycles head→gap→tail around `sta_cut`, PA previews a
head and scrubs. Those parts stay in each tool. What lives here is the set of pieces
that are the same question for both: which font, which ffmpeg, what does the file look
like as a waveform.

Only functions that were already byte-identical (or differed solely in comments and
Black's line-wrapping) were merged. `draw_seek_bar` and `Player` diverge in behaviour
between the two tools and were deliberately left where they are — merging them would
risk the STA tool for no gain.

`draw_wave` gained one thing in the move: `cut` is now optional, because PA files have
no `sta_cut` to mark. Everything else renders pixel-identically to the pre-extraction
version, which `_tests/t1_unit/test_verify_ui_primitives.py` pins.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pygame

WAVE_GAMMA = 0.5  # amplitude curve; a KAK quieter than the melody is invisible at linear scale
CUT_MARKER = (255, 255, 255)


def find_font(size: int) -> pygame.font.Font:
    for candidate in ("fonts/ShinGoPr6N-Medium.otf", "fonts/HelveticaNeue-Bold.otf"):
        p = Path(candidate)
        if p.exists():
            return pygame.font.Font(str(p), size)
    return pygame.font.SysFont(None, size)


def draw_button(
    screen: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    color: tuple[int, int, int],
    font: pygame.font.Font,
    hover: bool,
) -> None:
    fill = tuple(min(255, c + 30) for c in color) if hover else color
    pygame.draw.rect(screen, fill, rect, border_radius=8)
    pygame.draw.rect(screen, (255, 255, 255), rect, width=2, border_radius=8)
    txt = font.render(label, True, (255, 255, 255))
    screen.blit(txt, txt.get_rect(center=rect.center))


def find_ffmpeg() -> str:
    """Return path to ffmpeg.exe / ffmpeg. Falls back to common Windows install
    locations when not on PATH (winget Gyan.FFmpeg, chocolatey, etc.)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        Path.home()
        / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe",
        Path("C:/ProgramData/chocolatey/bin/ffmpeg.exe"),
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
    ]
    # Also try winget glob — version dirs change
    winget_root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if winget_root.exists():
        candidates.extend(winget_root.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"))
    for c in candidates:
        if c.exists():
            return str(c)
    return "ffmpeg"  # last resort — let subprocess raise its FileNotFoundError


_WAVE_CACHE: dict[tuple[str, float], np.ndarray] = {}


def wave_peaks(path: Path, columns: int) -> np.ndarray:
    """(2, columns) min/max envelope of the file, for the waveform strip.

    Cached per (path, mtime) so a splice invalidates it automatically. Decoding is via
    ffmpeg to mono f32 — the same route every other tool here uses.
    """
    key = (str(path), path.stat().st_mtime)
    hit = _WAVE_CACHE.get(key)
    if hit is not None and hit.shape[1] == columns:
        return hit
    try:
        raw = subprocess.run(
            [find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "8000", "-"],
            capture_output=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return np.zeros((2, columns), dtype=np.float32)
    y = np.frombuffer(raw, dtype=np.float32)
    if y.size < columns:
        y = np.pad(y, (0, columns - y.size))
    step = y.size // columns
    body = y[: step * columns].reshape(columns, step)
    out = np.vstack([body.min(axis=1), body.max(axis=1)]).astype(np.float32)
    _WAVE_CACHE.clear()
    _WAVE_CACHE[key] = out
    return out


def draw_wave(
    screen: pygame.Surface,
    rect: pygame.Rect,
    path: Path,
    duration: float,
    sel: tuple[float, float] | None,
    cut: float | None,
    font: pygame.font.Font,
) -> None:
    """Waveform strip spanning the same [0, duration] as the seek bar.

    Exists so an artifact can be found by eye and removed by hand: on hot/limited
    sources the click is often QUIETER than the wanted audio, so no automatic
    threshold separates them.

    `cut` draws the white marker (STA's `sta_cut`). Pass None where there is no such
    moment — PA files have none.
    """
    pygame.draw.rect(screen, (22, 26, 32), rect, border_radius=3)
    if duration <= 0 or rect.w <= 2:
        return
    peaks = wave_peaks(path, rect.w)
    mid = rect.y + rect.h // 2
    half = rect.h // 2 - 1
    # Amplitude guides at the raw levels the curve maps to — so "how loud is that blip"
    # stays answerable by eye rather than by running a probe.
    guides = ((1.0, "0"), (0.316, "-10"), (0.1, "-20"), (0.0316, "-30"))
    for frac, _ in guides:
        dy = int((frac**WAVE_GAMMA) * half)
        for yy in (mid - dy, mid + dy):
            pygame.draw.line(screen, (44, 52, 62), (rect.x + 1, yy), (rect.right - 1, yy))
    pygame.draw.line(screen, (58, 68, 80), (rect.x + 1, mid), (rect.right - 1, mid))
    for i in range(rect.w):
        lo, hi = float(peaks[0, i]), float(peaks[1, i])
        hs = (abs(hi) ** WAVE_GAMMA) * (1 if hi >= 0 else -1)
        ls = (abs(lo) ** WAVE_GAMMA) * (1 if lo >= 0 else -1)
        pygame.draw.line(screen, (86, 150, 200), (rect.x + i, mid - int(hs * half)), (rect.x + i, mid - int(ls * half)))
    if sel:
        a, b = sorted(sel)
        xa = rect.x + int(rect.w * max(0.0, min(1.0, a / duration)))
        xb = rect.x + int(rect.w * max(0.0, min(1.0, b / duration)))
        ov = pygame.Surface((max(1, xb - xa), rect.h), pygame.SRCALPHA)
        ov.fill((255, 70, 70, 90))
        screen.blit(ov, (xa, rect.y))
        for xx in (xa, xb):
            pygame.draw.line(screen, (255, 90, 90), (xx, rect.y), (xx, rect.y + rect.h), 1)
        label = font.render(f"{(b - a) * 1000:.0f} ms", True, (255, 190, 190))
        lx = min(max(xa + 4, rect.x + 4), rect.right - label.get_width() - 6)
        pad = label.get_rect(topleft=(lx, rect.y + 5)).inflate(8, 4)
        chip = pygame.Surface(pad.size, pygame.SRCALPHA)
        chip.fill((120, 30, 30, 210))
        screen.blit(chip, pad.topleft)
        screen.blit(label, (lx, rect.y + 5))
    for frac, lbl in guides:
        dy = int((frac**WAVE_GAMMA) * half)
        tag = font.render(lbl, True, (128, 140, 154))
        for yy in (mid - dy, mid + dy):
            tr = tag.get_rect(midright=(rect.right - 5, yy))
            back = pygame.Surface(tr.inflate(6, 2).size, pygame.SRCALPHA)
            back.fill((22, 26, 32, 190))
            screen.blit(back, tr.inflate(6, 2).topleft)
            screen.blit(tag, tr.topleft)
    if cut is None:
        return
    cx = rect.x + int(rect.w * max(0.0, min(1.0, cut / duration)))
    pygame.draw.line(screen, CUT_MARKER, (cx, rect.y), (cx, rect.y + rect.h), 2)
    pygame.draw.polygon(screen, CUT_MARKER, [(cx - 5, rect.y), (cx + 5, rect.y), (cx, rect.y + 7)])


EDGE_EPS = 0.03  # below this a remaining piece is nothing — mp3 frames are ~26 ms


def splice_out(src: Path, a: float, b: float, duration: float | None = None) -> None:
    """Lossless-remove [a, b] from an mp3, in place.

    A selection that reaches either END of the file leaves only ONE piece, and that
    case must not go through the concat demuxer: `ffmpeg -t 0` writes a zero-frame mp3,
    and concatenating it fails with "Failed to find two consecutive MPEG audio frames".
    Selecting from the very start to cut a leading passage is an ordinary thing to do,
    so all three shapes are handled — head only, tail only, both.

    Paths in the concat list are resolved absolute POSIX strings because the list is
    read by ffmpeg itself, which does not understand an MSYS-style path and answers a
    bad one by SKIPPING that entry and still exiting 0 — so a caller must verify the
    resulting duration, never just the exit code.
    """
    if duration is None:
        duration = probe_duration(src)
    have_head = a > EDGE_EPS
    have_tail = duration <= 0 or b < duration - EDGE_EPS
    if not have_head and not have_tail:
        raise ValueError("selection covers the whole file — nothing would remain")

    tmp_dir = src.parent
    head = tmp_dir / f".{src.stem}._head.mp3"
    tail = tmp_dir / f".{src.stem}._tail.mp3"
    listing = tmp_dir / f".{src.stem}._concat.txt"
    merged = tmp_dir / f".{src.stem}._merged.mp3"
    ff = find_ffmpeg()
    try:
        if have_head:
            subprocess.run(
                [ff, "-y", "-v", "error", "-i", str(src), "-t", f"{a:.3f}", "-c", "copy", str(head)],
                check=True,
            )
        if have_tail:
            subprocess.run(
                [ff, "-y", "-v", "error", "-ss", f"{b:.3f}", "-i", str(src), "-c", "copy", str(tail)],
                check=True,
            )
        if have_head and have_tail:
            listing.write_text(
                f"file '{head.resolve().as_posix()}'\nfile '{tail.resolve().as_posix()}'\n",
                encoding="utf-8",
            )
            subprocess.run(
                [ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(merged)],
                check=True,
            )
            merged.replace(src)
        elif have_head:
            head.replace(src)  # selection ran to EOF — keep the head
        else:
            tail.replace(src)  # selection started at the head — keep the tail
    finally:
        for p in (head, tail, listing, merged):
            p.unlink(missing_ok=True)


def probe_duration(path: Path) -> float:
    """Seconds, via ffmpeg's own decoder. 0.0 when the file cannot be read."""
    ff = find_ffmpeg()
    probe = Path(ff).with_name("ffprobe.exe" if ff.lower().endswith(".exe") else "ffprobe")
    exe = str(probe) if probe.exists() else "ffprobe"
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, OSError, ValueError):
        return 0.0

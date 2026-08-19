# SPDX-License-Identifier: MIT
"""Quick by-ear STA cut verifier.

For each STA in a route, plays the first HEAD_DURATION seconds, brief pause,
then [sta_cut - TAIL_LEAD, EOF] so you hear the music tail → cut → voice
transition. A short beep marks the exact sta_cut moment during tail playback.
Click/key in PASS or FAIL per station; final report to stdout.

    uv run python _dev_scripts/verify_sta_listen.py audio/takasaki

Keys: P=Pass  F=Fail  R=Replay  E=Edit note  N=Next without verdict  Q/Esc=Quit
      ←/→ or drag the marker = move sta_cut    C = commit it
      drag on the WAVEFORM then X/Del = splice that region out of the mp3
      U = undo — restore the file and its pre-splice sta_cut from the snapshot
      M = play the whole melody [0 → sta_cut], to judge complete loops
      [/] adjust start-trim  ,/. adjust end-trim  T apply trim  Z reset pending
      click either timeline to play from that point
      (hold Shift while adjusting for fine 0.01s steps)

Adjusting sta_cut: ←/→ nudge the cut marker, R replays so you hear the new
placement, C writes it to route.json. No audio is modified — this only moves
where the simulator jumps to. Contrast with the trim controls below, which
splice the mp3 itself.

While a cut nudge is pending, replay starts at [sta_cut - TAIL_LEAD] and skips
the head segment — you just moved the cut, so the head is not what you are
listening for, and replaying it costs HEAD_DURATION + the inter-gap on every
nudge. Releasing a marker drag does the same. Once the cut is committed with C
or dropped with Z, R goes back to the full head+tail pass.

Interactive trim: when an audio file has a stutter / extra content at the start
or end that the propose+splice pipeline can't fix algorithmically, use the
trim controls to nudge a red overlay marker on the seek bar. T commits the
trim by lossless-cutting the mp3 with ffmpeg AND shifting sta_cut down by the
start-trim amount (so the cut moment stays anchored to the same content).

Per-station notes: click the ✎ row above the seek bar (or press E) to add /
edit a note for the current station. Enter to save, Esc to cancel. Notes
survive across runs (stored in audio_src/<line>/sta_verify_results.json
under the `note` field). Marking PASS auto-resolves the current note (display
goes dim with strike-through, indicating the concern was checked and OK).
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pygame

from audio_layout import discover_route_sources, order_by_reference_count

WINDOW_W, WINDOW_H = 1180, 680

# fmt: off
# Detail-pane vertical layout. Every row DERIVES from the one above it, so growing the
# waveform can never silently land on top of something again — which is exactly what
# happened when it went 44px -> 230px and the status lines stayed at a fixed y.
PAD_X        = 20   # panel inner margin
ROW_PROGRESS = 36   # "n / m"
ROW_TITLE    = 64   # station name
ROW_SUB      = 104  # <sta>.mp3  sta_cut = ...
ROW_NOTE     = 132  # note row (click to edit)
NOTE_H       = 26
ROW_PHASE    = ROW_NOTE + NOTE_H + 10          # playback phase
PHASE_H      = 24
ROW_WAVE     = ROW_PHASE + PHASE_H + 8         # waveform top
WAVE_H       = 260                             # the point of the window; artifacts are 40-500 ms
ROW_SEEK     = ROW_WAVE + WAVE_H + 14
SEEK_H       = 18
ROW_STATUS   = ROW_SEEK + SEEK_H + 12          # pending trim / pending cut
STATUS_LINE  = 20
ROW_HINTS    = ROW_STATUS + STATUS_LINE * 2 + 10
HINT_LINE    = 22
BTN_H        = 56
ROW_BUTTONS  = ROW_HINTS + HINT_LINE * 2 + 14
# fmt: on

WAVE_GAMMA = 0.5  # amplitude curve; a KAK quieter than the melody is invisible at linear scale
LIST_W = 280  # left-column station list width
LIST_TOP = 60
ROW_H = 26
HEAD_DURATION = 3.0  # seconds played from start of file
TAIL_LEAD = 3.0  # seconds before sta_cut where tail playback starts
INTER_GAP_MS = 400  # silence between head and tail segments
FADE_MS = 120  # fade-out when stopping head segment

BG = (24, 24, 28)
PANEL = (38, 38, 44)
LIST_BG = (32, 32, 38)
ROW_HOVER = (50, 50, 60)
ROW_ACTIVE = (70, 70, 90)
FG = (235, 235, 235)
DIM = (150, 150, 160)
ACCENT = (250, 200, 80)
PASS_COLOR = (60, 170, 90)
FAIL_COLOR = (210, 70, 70)
REPLAY_COLOR = (90, 120, 200)

# Seek-bar region tints (head played, music lead-in to cut, voice after cut, untouched)
HEAD_TINT = (60, 130, 90)  # green-ish — head segment that gets played
CUT_LEAD_TINT = (180, 130, 60)  # amber — TAIL_LEAD seconds before sta_cut (also played)
VOICE_TINT = (170, 70, 70)  # red — voice region from sta_cut to EOF (also played)
UNTOUCHED_TINT = (60, 60, 70)  # dim gray — region between head end and tail start (skipped)
CUT_MARKER = (255, 255, 255)
CURSOR = (255, 240, 100)


def find_font(size: int) -> pygame.font.Font:
    for candidate in ("fonts/ShinGoPr6N-Medium.otf", "fonts/HelveticaNeue-Bold.otf"):
        p = Path(candidate)
        if p.exists():
            return pygame.font.Font(str(p), size)
    return pygame.font.SysFont(None, size)


def draw_button(screen: pygame.Surface, rect: pygame.Rect, label: str, color: tuple[int, int, int], font: pygame.font.Font, hover: bool) -> None:
    fill = tuple(min(255, c + 30) for c in color) if hover else color
    pygame.draw.rect(screen, fill, rect, border_radius=8)
    pygame.draw.rect(screen, (255, 255, 255), rect, width=2, border_radius=8)
    txt = font.render(label, True, (255, 255, 255))
    screen.blit(txt, txt.get_rect(center=rect.center))


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
            [_find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "8000", "-"],
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
    cut: float,
    font: pygame.font.Font,
) -> None:
    """Waveform strip spanning the same [0, duration] as the seek bar.

    Exists so a KAK can be found by eye and removed by hand: on hot/limited sources the
    click is often QUIETER than the melody, so no automatic threshold separates them.
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
    cx = rect.x + int(rect.w * max(0.0, min(1.0, cut / duration)))
    pygame.draw.line(screen, CUT_MARKER, (cx, rect.y), (cx, rect.y + rect.h), 2)
    pygame.draw.polygon(screen, CUT_MARKER, [(cx - 5, rect.y), (cx + 5, rect.y), (cx, rect.y + 7)])


def draw_seek_bar(
    screen: pygame.Surface,
    rect: pygame.Rect,
    duration: float,
    sta_cut: float,
    position: float | None,
    font: pygame.font.Font,
    trim_start: float = 0.0,
    trim_end: float | None = None,
    cut_hot: bool = False,
) -> None:
    """Static colored regions for head/skipped/cut-lead/voice + sta_cut marker + live cursor.

    Whole bar is the file [0, duration]. Played regions get tints; the skipped
    middle region (from end of head to start of tail) is dimmed so the user can
    see what they did NOT hear. Pending trim regions [0, trim_start] and
    [trim_end, duration] get a stronger overlay tint to indicate "will be cut"."""
    if duration <= 0:
        return
    if trim_end is None:
        trim_end = duration

    def x_for(t: float) -> int:
        return rect.x + int(rect.w * (max(0.0, min(duration, t)) / duration))

    head_end = min(HEAD_DURATION, duration)
    tail_start = max(0.0, sta_cut - TAIL_LEAD)
    cut_x = x_for(sta_cut)
    head_end_x = x_for(head_end)
    tail_start_x = x_for(tail_start)

    # base bar (untouched gray) — covers the skipped middle by default
    pygame.draw.rect(screen, UNTOUCHED_TINT, rect, border_radius=4)
    # head played
    if head_end_x > rect.x:
        pygame.draw.rect(screen, HEAD_TINT, (rect.x, rect.y, head_end_x - rect.x, rect.h))
    # cut-lead (3s before sta_cut up to sta_cut) — note tail_start may be < head_end (overlap)
    lead_left = max(tail_start_x, head_end_x)
    if cut_x > lead_left:
        pygame.draw.rect(screen, CUT_LEAD_TINT, (lead_left, rect.y, cut_x - lead_left, rect.h))
    # voice (sta_cut → EOF)
    if rect.right > cut_x:
        pygame.draw.rect(screen, VOICE_TINT, (cut_x, rect.y, rect.right - cut_x, rect.h))
    # outline
    pygame.draw.rect(screen, (90, 90, 100), rect, width=1, border_radius=4)
    # sta_cut marker — taller than the bar so it's obvious. Thickens with a grab
    # handle when the mouse is close enough to drag it (cut_hot).
    if cut_hot:
        pygame.draw.line(screen, CUT_MARKER, (cut_x, rect.y - 10), (cut_x, rect.bottom + 10), 4)
        pygame.draw.circle(screen, CUT_MARKER, (cut_x, rect.y - 12), 5)
    else:
        pygame.draw.line(screen, CUT_MARKER, (cut_x, rect.y - 6), (cut_x, rect.bottom + 6), 2)

    # Pending-trim overlays: striped/dark hatch over regions that would be cut.
    trim_overlay = (200, 60, 60)
    if trim_start > 0:
        ts_x = x_for(trim_start)
        s = pygame.Surface((ts_x - rect.x, rect.h), pygame.SRCALPHA)
        s.fill((*trim_overlay, 140))
        screen.blit(s, (rect.x, rect.y))
        # red marker line at trim-start
        pygame.draw.line(screen, trim_overlay, (ts_x, rect.y - 8), (ts_x, rect.bottom + 8), 2)
    if trim_end < duration:
        te_x = x_for(trim_end)
        s = pygame.Surface((rect.right - te_x, rect.h), pygame.SRCALPHA)
        s.fill((*trim_overlay, 140))
        screen.blit(s, (te_x, rect.y))
        pygame.draw.line(screen, trim_overlay, (te_x, rect.y - 8), (te_x, rect.bottom + 8), 2)

    # live cursor
    if position is not None:
        cur_x = x_for(position)
        pygame.draw.line(screen, CURSOR, (cur_x, rect.y - 4), (cur_x, rect.bottom + 4), 2)

    # labels
    label_0 = font.render("0.0s", True, DIM)
    screen.blit(label_0, (rect.x, rect.bottom + 8))
    label_dur = font.render(f"{duration:.1f}s", True, DIM)
    screen.blit(label_dur, (rect.right - label_dur.get_width(), rect.bottom + 8))
    label_cut = font.render(f"sta_cut {sta_cut:.2f}s", True, FG)
    cut_label_x = max(rect.x, min(rect.right - label_cut.get_width(), cut_x - label_cut.get_width() // 2))
    screen.blit(label_cut, (cut_label_x, rect.y - 24))


def _find_ffmpeg() -> str:
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


def _make_beep(duration_s: float = 0.08, freq: float = 880.0, volume: float = 0.4) -> pygame.mixer.Sound:
    """Short sine-wave beep used to mark sta_cut moment during tail playback."""
    import numpy as np

    sr = 22050
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Soft envelope to avoid click on attack/release
    env = np.minimum(np.minimum(t * 200, (duration_s - t) * 200), 1.0)
    wave = np.sin(2 * np.pi * freq * t) * env * volume
    samples = (wave * 32767).astype(np.int16)
    # pygame stereo: duplicate mono to two channels
    stereo = np.column_stack([samples, samples])
    return pygame.sndarray.make_sound(stereo)


class Player:
    """Tiny state machine: IDLE → HEAD → GAP → TAIL → DONE."""

    def __init__(self) -> None:
        self.state = "IDLE"
        self.head_stop_at = 0  # ms tick at which to fade out head
        self.gap_until = 0  # ms tick at which to start tail
        self.tail_path: Path | None = None
        self.tail_start: float = 0.0
        self.head_start_offset: float = 0.0  # head playback starts at this file-time offset
        self.tail_end: float | None = None  # absolute file time to stop tail (early stop for trim preview)
        self.segment_started_ms = 0  # tick when current HEAD or TAIL segment began playing
        self.cut_time: float = 0.0  # absolute file-time position where sta_cut sits
        self.beep_played: bool = False
        self.beep = _make_beep()
        self.melody_until: float | None = None
        self.skip: tuple[float, float] | None = None
        self.skipped: bool = False

    def begin(
        self,
        path: Path,
        sta_cut: float,
        head_start: float = 0.0,
        tail_end: float | None = None,
        tail_only: bool = False,
        melody_until: float | None = None,
        from_time: float | None = None,
        skip: tuple[float, float] | None = None,
    ) -> None:
        """Start playback. head_start/tail_end let the caller preview pending trim
        without touching the file: head plays from `head_start` (skipping the
        soon-to-be-trimmed prefix), tail stops at `tail_end` (skipping the
        soon-to-be-trimmed suffix).

        `tail_only` skips the head segment and the inter-gap, starting straight at
        [sta_cut - TAIL_LEAD]. That is the cut-tuning loop: when you have just MOVED
        the cut, the head tells you nothing you did not already hear, and replaying
        it costs HEAD_DURATION + INTER_GAP_MS on every nudge."""
        self.tail_path = path
        self.tail_start = from_time if from_time is not None else max(head_start, sta_cut - TAIL_LEAD)
        self.cut_time = sta_cut
        self.head_start_offset = head_start
        self.tail_end = tail_end
        self.beep_played = False
        self.skip = skip
        self.skipped = False
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        pygame.mixer.music.load(str(path))
        if melody_until is not None:
            # Whole melody, head_start -> sta_cut. The only way to judge whether the
            # recording holds COMPLETE loops, which the 3 s head cannot show.
            try:
                pygame.mixer.music.play(start=head_start)
            except pygame.error:
                pygame.mixer.music.play()
            self.melody_until = melody_until
            self.segment_started_ms = pygame.time.get_ticks()
            self.state = "MELODY"
            return
        if tail_only:
            try:
                pygame.mixer.music.play(start=self.tail_start)
            except pygame.error:
                pygame.mixer.music.play()
            self.segment_started_ms = pygame.time.get_ticks()
            self.state = "TAIL"
            return
        try:
            pygame.mixer.music.play(start=head_start)
        except pygame.error:
            pygame.mixer.music.play()
        now = pygame.time.get_ticks()
        self.head_stop_at = now + int(HEAD_DURATION * 1000)
        self.segment_started_ms = now
        self.state = "HEAD"

    def tick(self) -> None:
        now = pygame.time.get_ticks()
        if self.state == "MELODY":
            pos = self.head_start_offset + (now - self.segment_started_ms) / 1000.0
            if (self.melody_until is not None and pos >= self.melody_until) or not pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(FADE_MS)
                self.state = "DONE"
            return
        if self.state == "HEAD" and now >= self.head_stop_at:
            pygame.mixer.music.fadeout(FADE_MS)
            self.gap_until = now + INTER_GAP_MS + FADE_MS
            self.state = "GAP"
        elif self.state == "GAP" and now >= self.gap_until:
            assert self.tail_path is not None
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            pygame.mixer.music.load(str(self.tail_path))
            try:
                pygame.mixer.music.play(start=self.tail_start)
            except pygame.error:
                # some MP3s fail with start= — fall back to no-offset
                pygame.mixer.music.play()
            self.segment_started_ms = pygame.time.get_ticks()
            self.state = "TAIL"
        elif self.state == "TAIL":
            pos = self.tail_start + (now - self.segment_started_ms) / 1000.0
            # Pending splice: jump the gap so you hear the RESULT before committing it.
            if self.skip and not self.skipped and pos >= self.skip[0]:
                self.skipped = True
                self.tail_start = self.skip[1]
                try:
                    pygame.mixer.music.play(start=self.skip[1])
                except pygame.error:
                    pass
                self.segment_started_ms = pygame.time.get_ticks()
                return
            # Marker beep at sta_cut moment (only once per playback)
            if not self.beep_played and pos >= self.cut_time:
                self.beep.play()
                self.beep_played = True
            # Early stop for trim preview: don't play past tail_end
            if self.tail_end is not None and pos >= self.tail_end:
                pygame.mixer.music.stop()
                self.state = "DONE"
                return
            if not pygame.mixer.music.get_busy():
                self.state = "DONE"

    def position(self) -> float | None:
        """Return current playback position in seconds (file-relative), or None when idle/gap/done."""
        if self.state == "HEAD":
            return self.head_start_offset + (pygame.time.get_ticks() - self.segment_started_ms) / 1000.0
        if self.state == "TAIL":
            return self.tail_start + (pygame.time.get_ticks() - self.segment_started_ms) / 1000.0
        return None

    def stop(self) -> None:
        pygame.mixer.music.stop()
        self.state = "DONE"


def load_route_sources(work_dir: Path) -> tuple[list[Path], Path, list[dict]]:
    """Resolve the route.json(s) + sta folder for either audio layout.

    Per-diagram:  <work_dir>/route.json      + <work_dir>/sta/
    Pooled line:  <work_dir>/*/route.json    + <work_dir>/sta/

    A pooled line (the default — route.json writes no audio_root) shares one sta folder
    across several diagrams, so one mp3 is referenced by several route.json
    files — and sometimes by several STOPS within one — and a sta_cut edit has to
    land in every one of them. `validate_data.check_pool_sta_cut_sync` gates that;
    see docs/DATA_FORMAT.md § audio_root Field. The returned stop list is the union across diagrams,
    ordered by the diagram that references the most STAs.

    Raises FileNotFoundError when neither layout is present.
    """
    route_paths, sta_dir, loaded = discover_route_sources(work_dir, "sta")
    if len(route_paths) == 1 and route_paths[0].parent == work_dir:
        return route_paths, sta_dir, loaded[0][1]  # per-diagram: nothing to merge

    merged: dict[str, dict] = {}
    for p, stops in order_by_reference_count(loaded, ("sta",)):
        for stop in stops:
            cut = stop.get("sta_cut")
            for sta in stop.get("sta", []):
                if sta in merged:
                    prev = merged[sta]["sta_cut"]
                    if cut is not None and prev is not None and cut != prev:
                        print(
                            f"warning: {sta} has sta_cut {prev} and {cut} across diagrams " f"— the pool is desynced; fix before trusting this run",
                            file=sys.stderr,
                        )
                    continue
                merged[sta] = {"name": stop["name"], "sta": [sta], "sta_cut": cut}

    print(f"pooled layout: {len(route_paths)} route.json, {len(merged)} STAs — " f"{', '.join(p.parent.name for p in route_paths)}")
    return route_paths, sta_dir, list(merged.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir", type=Path, help="audio/<line>/<diagram>, or audio/<line> for a pooled line")
    ap.add_argument(
        "--only",
        help="comma-separated sta basenames to test (e.g. 'kumagaya' or 'kumagaya,konosu'). Existing JSON verdicts for un-tested stations are preserved.",
    )
    args = ap.parse_args()
    only: set[str] | None = set(s.strip() for s in args.only.split(",")) if args.only else None

    try:
        route_paths, sta_dir, stops = load_route_sources(args.work_dir)
    except (FileNotFoundError, KeyError) as e:
        print(e, file=sys.stderr)
        return 1

    items: list[dict] = []
    for stop in stops:
        sta_cut = stop.get("sta_cut")
        for sta in stop.get("sta", []):
            path = sta_dir / f"{sta}.mp3"
            if not path.exists() or sta_cut is None:
                continue
            if only is not None and sta not in only:
                continue
            items.append({"stop": stop["name"], "sta": sta, "sta_cut": float(sta_cut), "path": path})

    if not items:
        msg = f"no matching STAs (filter --only={args.only})" if only else "no playable STA entries (need sta + sta_cut + file on disk)"
        print(msg, file=sys.stderr)
        return 1
    if only:
        unmatched = only - {it["sta"] for it in items}
        if unmatched:
            print(f"warning: --only names not found in route: {sorted(unmatched)}", file=sys.stderr)

    # Output: audio_src/<line>/sta_verify_results.json. Mid-products of audio
    # workflows live under audio_src/ (gitignored), mirroring the operational hierarchy.
    # Falls back to project-root `_sta_verify_<slug>.json` if work_dir isn't under audio/.
    rel_under_audio = [p for p in args.work_dir.parts if p not in (".", "..", "audio")]
    if rel_under_audio:
        out_path = Path("audio_src") / Path(*rel_under_audio) / "sta_verify_results.json"
    else:
        slug = "_".join(args.work_dir.parts) or "results"
        out_path = Path(f"_sta_verify_{slug}.json")

    # Migrate legacy project-root file if present (one-shot — keeps prior verdicts).
    legacy = Path(f"_sta_verify_{'_'.join(rel_under_audio) or 'results'}.json")
    if rel_under_audio and legacy.exists() and not out_path.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        legacy.rename(out_path)
        print(f"migrated {legacy} -> {out_path}")

    # Load prior verdicts + notes so the list shows pre-existing marks/comments.
    # Notes are editable in-app (click ✎ pen icon). Notes survive across runs.
    # PASS auto-marks the current note as resolved (display dimmed + strike-through).
    prior_verdicts: dict[str, str] = {}
    notes: dict[str, str] = {}  # sta -> note text (live, editable)
    notes_resolved: dict[str, bool] = {}  # sta -> resolved flag
    if out_path.exists():
        try:
            prior = json.loads(out_path.read_text(encoding="utf-8"))
            for it in prior.get("items", []):
                if it.get("verdict") in ("PASS", "FAIL"):
                    prior_verdicts[it["sta"]] = it["verdict"]
                if it.get("note"):
                    notes[it["sta"]] = it["note"]
                    notes_resolved[it["sta"]] = bool(it.get("note_resolved", False))
        except (json.JSONDecodeError, KeyError):
            pass

    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(f"STA verifier — {args.work_dir}")
    clock = pygame.time.Clock()
    font_h1 = find_font(28)
    font_h2 = find_font(22)
    font_body = find_font(18)
    font_btn = find_font(20)
    font_small = find_font(14)
    font_row = find_font(16)

    # precompute duration per file (Sound.get_length forces a load — fine for short STAs)
    for it in items:
        try:
            it["duration"] = pygame.mixer.Sound(str(it["path"])).get_length()
        except pygame.error:
            it["duration"] = 0.0

    player = Player()
    idx = 0
    list_scroll = 0  # row offset for sidebar scroll (in row units)
    visible_rows = max(1, (WINDOW_H - LIST_TOP) // ROW_H)
    verdicts: dict[str, str] = {}  # sta -> "PASS"/"FAIL" — this session's verdicts
    player.begin(items[idx]["path"], items[idx]["sta_cut"])

    def begin_with_trim(tail_only: bool = False) -> None:
        """Start playback for current item, previewing any pending trim + cut nudge.

        `tail_only` is set by the cut-tuning path — see Player.begin. R also uses it
        whenever a cut nudge is pending, so the whole nudge→listen loop stays short;
        once the cut is committed or discarded, R goes back to the full head+tail check."""
        item = items[idx]
        head_s = trim_start
        tail_e = item.get("duration", 0.0) - trim_end_offset if trim_end_offset > 0 else None
        player.begin(item["path"], eff_cut(), head_start=head_s, tail_end=tail_e, tail_only=tail_only)

    btn_w, btn_h = 150, 56
    detail_x = LIST_W + 40
    pass_rect = pygame.Rect(detail_x, ROW_BUTTONS, btn_w, btn_h)
    fail_rect = pygame.Rect(detail_x + btn_w + 20, ROW_BUTTONS, btn_w, btn_h)
    replay_rect = pygame.Rect(detail_x + 2 * (btn_w + 20), ROW_BUTTONS, btn_w, btn_h)
    # Note row sits above the seek bar; click anywhere in this rect to edit.
    note_rect = pygame.Rect(detail_x, ROW_NOTE, WINDOW_W - detail_x - PAD_X, NOTE_H)
    # Seek bar geometry is fixed — hoisted out of the draw block so mouse handling
    # (which runs earlier in the frame) can hit-test against it.
    seek_rect = pygame.Rect(detail_x, ROW_SEEK, WINDOW_W - detail_x - PAD_X, SEEK_H)
    # Vertical grab band: the sta_cut marker is drawn taller than the bar itself.
    seek_grab_rect = seek_rect.inflate(0, 24)
    CUT_GRAB_PX = 14  # horizontal slop for grabbing the marker
    # Waveform strip, same [0, duration] span as the seek bar. Drag on it to select a
    # region, X/DEL to splice that region out — the manual path for artifacts (KAK) that
    # no automatic detector separates reliably on a hot source.
    wave_rect = pygame.Rect(detail_x, ROW_WAVE, WINDOW_W - detail_x - PAD_X, WAVE_H)
    wave_sel: list[float] | None = None
    dragging_sel = False

    # Edit-mode state for in-app note editing
    edit_mode = False
    edit_buffer = ""
    # Pending trim state (per-station, applied via T key)
    trim_start: float = 0.0  # seconds to trim from start (file head)
    trim_end_offset: float = 0.0  # seconds to trim from end (file tail)
    # Pending sta_cut nudge (per-station, applied via C key). None = no pending change.
    # Distinct from trim: this moves WHERE the cut lands and touches no audio.
    cut_pending: float | None = None

    dragging_cut = False  # True while the sta_cut marker is held with the mouse
    cut_before_splice: dict[str, float] = {}  # sta -> sta_cut as it was before this session spliced it

    def eff_cut() -> float:
        """sta_cut in effect right now — the pending nudge if one is staged."""
        return items[idx]["sta_cut"] if cut_pending is None else cut_pending

    def cut_x_now() -> int:
        """Screen x of the current cut marker on the seek bar."""
        dur = items[idx].get("duration", 0.0)
        if dur <= 0:
            return seek_rect.x
        return seek_rect.x + int(seek_rect.w * (max(0.0, min(dur, eff_cut())) / dur))

    def wave_time_at_x(x: int) -> float:
        """Screen x on the waveform strip -> time. Same span as the seek bar."""
        dur = items[idx].get("duration", 0.0)
        if dur <= 0 or wave_rect.w <= 0:
            return 0.0
        return max(0.0, min(dur, (x - wave_rect.x) / wave_rect.w * dur))

    def time_at_x(x: int) -> float:
        """Seek-bar x -> file time, clamped inside the file."""
        dur = items[idx].get("duration", 0.0)
        if dur <= 0 or seek_rect.w <= 0:
            return 0.0
        frac = (x - seek_rect.x) / seek_rect.w
        return max(0.05, min(dur - 0.05, frac * dur))

    def current_verdict_for(sta: str) -> str:
        if sta in verdicts:
            return verdicts[sta]
        return prior_verdicts.get(sta, "")

    def jump_to(new_idx: int) -> None:
        nonlocal idx, edit_mode, trim_start, trim_end_offset, list_scroll, cut_pending
        edit_mode = False  # cancel any in-progress edit on navigation
        trim_start = 0.0  # discard pending trim — moving on to new station
        trim_end_offset = 0.0
        cut_pending = None  # discard pending cut nudge too
        idx = max(0, min(len(items) - 1, new_idx))
        # auto-scroll sidebar to keep idx in view
        if idx < list_scroll:
            list_scroll = idx
        elif idx >= list_scroll + visible_rows:
            list_scroll = idx - visible_rows + 1
        begin_with_trim()

    def record(verdict: str) -> None:
        sta = items[idx]["sta"]
        verdicts[sta] = verdict
        # Auto-resolve note on PASS (it survived scrutiny)
        if verdict == "PASS" and sta in notes:
            notes_resolved[sta] = True
        elif verdict == "FAIL":
            notes_resolved[sta] = False  # FAIL keeps note active for follow-up
        if idx + 1 < len(items):
            jump_to(idx + 1)
        else:
            player.stop()

    def start_edit() -> None:
        nonlocal edit_mode, edit_buffer
        edit_mode = True
        edit_buffer = notes.get(items[idx]["sta"], "")
        try:
            pygame.key.start_text_input()
        except AttributeError:
            pass  # older pygame — text input is always on

    def commit_edit() -> None:
        nonlocal edit_mode
        sta = items[idx]["sta"]
        text = edit_buffer.strip()
        if text:
            notes[sta] = text
            # New/edited note → unresolved (regardless of verdict)
            notes_resolved[sta] = False
        else:
            notes.pop(sta, None)
            notes_resolved.pop(sta, None)
        edit_mode = False
        try:
            pygame.key.stop_text_input()
        except AttributeError:
            pass

    def cancel_edit() -> None:
        nonlocal edit_mode
        edit_mode = False
        try:
            pygame.key.stop_text_input()
        except AttributeError:
            pass

    def persist_cut(sta: str, new_cut: float) -> list[str]:
        """Write sta_cut to EVERY route.json referencing this mp3.

        On a pooled line several diagrams share one file, so patching a single
        route.json desyncs the pool. Returns the diagram names written.
        """
        written = []
        for rp in route_paths:
            route_obj = json.loads(rp.read_text(encoding="utf-8"))
            hit = False
            for stop in route_obj["stops"]:
                if sta in stop.get("sta", []):
                    stop["sta_cut"] = new_cut
                    hit = True
                    # No break: one slug can be referenced from SEVERAL stops in the SAME
                    # route.json — yamanote's loop lists 大崎 twice, keihin points 新子安 at
                    # 鶴見's melody, nambu shares one file across 矢川 and 西国立. Stopping at
                    # the first match desyncs the pool inside a single file, which is the
                    # exact invariant this helper exists to hold.
            if hit:
                rp.write_text(json.dumps(route_obj, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
                written.append(rp.parent.name)
        return written

    def commit_cut() -> bool:
        """Persist the pending sta_cut nudge. Audio is untouched — this only moves
        where the simulator jumps to."""
        nonlocal cut_pending
        if cut_pending is None:
            return False
        item = items[idx]
        new_cut = round(cut_pending, 2)
        old = item["sta_cut"]
        item["sta_cut"] = new_cut
        cut_pending = None
        written = persist_cut(item["sta"], new_cut)
        print(f"sta_cut {item['sta']}: {old} → {new_cut}  ({', '.join(written)})")
        return True

    def apply_trim() -> bool:
        """Splice the current item's mp3 by trim_start/trim_end_offset, shift sta_cut
        by -trim_start, persist to route.json, and reload the player. Returns True on success."""
        nonlocal trim_start, trim_end_offset
        if trim_start <= 0 and trim_end_offset <= 0:
            return False  # nothing to apply
        item = items[idx]
        src = Path(item["path"])
        dur = item.get("duration", 0.0)
        keep_start = max(0.0, trim_start)
        keep_end = max(keep_start + 0.1, dur - max(0.0, trim_end_offset))
        new_dur = keep_end - keep_start
        # Stop playback so the file is not locked
        player.stop()
        pygame.mixer.music.unload()
        tmp = src.with_suffix(".tmp.mp3")
        # Use ffmpeg -ss + -t for lossless cut from both ends
        cmd = [_find_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{keep_start:.3f}", "-i", str(src), "-t", f"{new_dur:.3f}", "-c", "copy", str(tmp)]
        try:
            subprocess.run(cmd, check=True)
            shutil.move(str(tmp), str(src))
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"trim failed for {src.name}: {e}", file=sys.stderr)
            return False
        # Update sta_cut: shift by -trim_start
        new_cut = round(item["sta_cut"] - keep_start, 2)
        item["sta_cut"] = new_cut
        item["duration"] = new_dur
        written = persist_cut(item["sta"], new_cut)
        print(f"trimmed {item['sta']}: cut [0,{keep_start:.3f}] + [{keep_end:.3f},{dur:.3f}]  " f"sta_cut → {new_cut}  ({', '.join(written)})")
        # Reset pending trim, reload player
        trim_start = 0.0
        trim_end_offset = 0.0
        player.begin(src, new_cut)
        return True

    def restore_original() -> bool:
        """U — undo every splice made to this file, from the snapshot taken before the first one.

        Restores the audio AND the sta_cut it had at that moment, so a file cannot be left with a
        cut that refers to samples no longer in it. The snapshot lives in
        audio_src/<line>/sta_wave_backup/ and predates this session's first splice of the file.
        """
        nonlocal wave_sel
        item = items[idx]
        src = Path(item["path"])
        bak = Path("audio_src") / src.parent.parent.name / "sta_wave_backup" / src.name
        # Session-scoped, matching the write side. `bak.exists()` alone is a CROSS-session
        # fact — snapshots are never deleted — so on a file an earlier session spliced and
        # this one has not, U would restore that session's starting audio and report
        # success, discarding its hand work. `cut_before_splice` holds exactly the slugs
        # this run has spliced; both halves of undo must key on the same event.
        if item["sta"] not in cut_before_splice:
            print(f"nothing spliced this session for {src.name}", file=sys.stderr)
            return False
        if not bak.exists():
            print(f"snapshot missing for {src.name} — cannot restore", file=sys.stderr)
            return False
        player.stop()
        pygame.mixer.music.unload()
        try:
            shutil.copy2(bak, src)
        except OSError as e:
            print(f"restore failed for {src.name}: {e}", file=sys.stderr)
            return False
        try:
            item["duration"] = pygame.mixer.Sound(str(src)).get_length()
        except pygame.error:
            pass
        old_cut = cut_before_splice.pop(item["sta"], item["sta_cut"])
        item["sta_cut"] = old_cut
        written = persist_cut(item["sta"], old_cut)
        wave_sel = None
        print(f"restored {item['sta']} from snapshot  sta_cut -> {old_cut}  ({', '.join(written)})")
        player.begin(src, old_cut, tail_only=True)
        return True

    def splice_selection() -> bool:
        """Delete the highlighted region from the mp3 and shift sta_cut per sta-make Step 7.5.

        kak_end <= cut -> cut - width ; kak_start >= cut -> unchanged ;
        straddling -> snap to kak_start.
        """
        nonlocal wave_sel
        if not wave_sel:
            return False
        a, b = sorted(wave_sel)
        item = items[idx]
        dur = item.get("duration", 0.0)
        a, b = max(0.0, a), min(dur, b)
        if b - a < 0.005:
            print("selection too short to splice", file=sys.stderr)
            return False
        src = Path(item["path"])
        # Snapshot before THIS SESSION's first splice of the file, overwriting whatever an
        # earlier session left. The previous form wrote only when absent, which silently
        # aimed U at a different generation: on a line spliced in a prior session, one
        # keystroke restored the audio that session STARTED from and discarded everything
        # it had done — 24 files and 64.1 s of hand work, on Nambu, with the status line
        # reporting a successful restore. `cut_before_splice` already records the same
        # event session-scoped, so gating both on it restores audio and cut to one moment.
        bak_dir = Path("audio_src") / src.parent.parent.name / "sta_wave_backup"
        bak_dir.mkdir(parents=True, exist_ok=True)
        if item["sta"] not in cut_before_splice:
            shutil.copy2(src, bak_dir / src.name)
        cut_before_splice.setdefault(item["sta"], item["sta_cut"])
        player.stop()
        pygame.mixer.music.unload()
        tmp = src.with_suffix(".tmp.mp3")
        cmd = [
            _find_ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-filter_complex",
            f"[0]atrim=0:{a:.3f},asetpts=N/SR/TB[p];[0]atrim={b:.3f},asetpts=N/SR/TB[q];" f"[p][q]concat=n=2:v=0:a=1[o]",
            "-map",
            "[o]",
            str(tmp),
        ]
        try:
            subprocess.run(cmd, check=True)
            shutil.move(str(tmp), str(src))
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"splice failed for {src.name}: {e}", file=sys.stderr)
            return False
        width = b - a
        cut = item["sta_cut"]
        new_cut = round(cut - width, 2) if b <= cut else (round(a, 2) if a < cut < b else cut)
        item["sta_cut"] = new_cut
        item["duration"] = max(0.1, dur - width)
        written = persist_cut(item["sta"], new_cut)
        print(f"spliced {item['sta']}: removed [{a:.3f},{b:.3f}] ({width*1000:.0f}ms)  " f"sta_cut {cut} → {new_cut}  ({', '.join(written)})")
        wave_sel = None
        # Tail only: the splice you just made is at the cut, so that is what you need
        # to hear. Replaying the head costs HEAD_DURATION + the inter-gap on every pass,
        # and an artifact routinely takes two or three passes to bracket cleanly.
        player.begin(src, new_cut, tail_only=True)
        return True

    def list_row_at(pos: tuple[int, int]) -> int | None:
        x, y = pos
        if x >= LIST_W or y < LIST_TOP:
            return None
        i = (y - LIST_TOP) // ROW_H + list_scroll
        return int(i) if 0 <= i < len(items) else None

    running = True
    while running:
        mouse = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if edit_mode:
                    # In edit mode, all keypresses go to the note buffer
                    if ev.key == pygame.K_RETURN:
                        commit_edit()
                    elif ev.key == pygame.K_ESCAPE:
                        cancel_edit()
                    elif ev.key == pygame.K_BACKSPACE:
                        edit_buffer = edit_buffer[:-1]
                else:
                    fine = bool(ev.mod & pygame.KMOD_SHIFT)
                    step = 0.01 if fine else 0.1
                    cur_dur = items[idx].get("duration", 0.0)
                    if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        running = False
                    elif ev.key == pygame.K_p:
                        record("PASS")
                    elif ev.key == pygame.K_f:
                        record("FAIL")
                    elif ev.key == pygame.K_n:
                        if idx + 1 < len(items):
                            jump_to(idx + 1)
                    elif ev.key == pygame.K_r:
                        # Mid-nudge, R is part of the cut-tuning loop → tail only.
                        begin_with_trim(tail_only=cut_pending is not None)
                    elif ev.key == pygame.K_UP:
                        jump_to(idx - 1)
                    elif ev.key == pygame.K_DOWN:
                        jump_to(idx + 1)
                    elif ev.key == pygame.K_e:
                        start_edit()
                    # Trim controls: [/] adjust start, ,/. adjust end, T apply, Z reset
                    elif ev.key == pygame.K_LEFTBRACKET:  # [
                        trim_start = max(0.0, trim_start - step)
                    elif ev.key == pygame.K_RIGHTBRACKET:  # ]
                        trim_start = min(eff_cut() - 0.05, trim_start + step)
                    elif ev.key == pygame.K_COMMA:
                        trim_end_offset = min(cur_dur - eff_cut() - 0.05, trim_end_offset + step)
                    elif ev.key == pygame.K_PERIOD:
                        trim_end_offset = max(0.0, trim_end_offset - step)
                    elif ev.key == pygame.K_t:
                        apply_trim()
                    # sta_cut nudge: ←/→ move the cut, C commits (no audio change)
                    elif ev.key == pygame.K_LEFT:
                        cut_pending = max(trim_start + 0.05, eff_cut() - step)
                    elif ev.key == pygame.K_RIGHT:
                        cut_pending = min(cur_dur - 0.05, eff_cut() + step)
                    elif ev.key == pygame.K_m:
                        # Whole melody [0 -> sta_cut]: is it a COMPLETE loop, or cut short?
                        player.begin(items[idx]["path"], eff_cut(), head_start=trim_start, melody_until=eff_cut())
                    elif ev.key == pygame.K_c:
                        commit_cut()
                    elif ev.key in (pygame.K_x, pygame.K_DELETE):
                        splice_selection()
                    elif ev.key == pygame.K_u:
                        restore_original()
                    elif ev.key == pygame.K_z:
                        trim_start = 0.0
                        trim_end_offset = 0.0
                        cut_pending = None
                        wave_sel = None
            elif ev.type == pygame.TEXTINPUT and edit_mode:
                edit_buffer += ev.text
            elif ev.type == pygame.MOUSEWHEEL:
                max_scroll = max(0, len(items) - visible_rows)
                list_scroll = max(0, min(max_scroll, list_scroll - ev.y * 3))
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if edit_mode:
                    # Click outside note rect cancels edit
                    if not note_rect.collidepoint(ev.pos):
                        cancel_edit()
                else:
                    if note_rect.collidepoint(ev.pos):
                        start_edit()
                    elif wave_rect.collidepoint(ev.pos):
                        t0 = wave_time_at_x(ev.pos[0])
                        wave_sel = [t0, t0]
                        dragging_sel = True
                    elif seek_grab_rect.collidepoint(ev.pos) and abs(ev.pos[0] - cut_x_now()) <= CUT_GRAB_PX:
                        # Grabbed the sta_cut marker — drag to reposition.
                        dragging_cut = True
                        cut_pending = round(time_at_x(ev.pos[0]), 2)
                    elif seek_rect.collidepoint(ev.pos):
                        # Anywhere else on the timeline: play from there.
                        player.begin(items[idx]["path"], eff_cut(), from_time=max(0.0, time_at_x(ev.pos[0])), tail_only=True)
                    else:
                        row = list_row_at(ev.pos)
                        if row is not None:
                            jump_to(row)
                        elif pass_rect.collidepoint(ev.pos):
                            record("PASS")
                        elif fail_rect.collidepoint(ev.pos):
                            record("FAIL")
                        elif replay_rect.collidepoint(ev.pos):
                            begin_with_trim(tail_only=cut_pending is not None)
            elif ev.type == pygame.MOUSEMOTION and dragging_cut:
                cut_pending = round(time_at_x(ev.pos[0]), 2)
            elif ev.type == pygame.MOUSEMOTION and dragging_sel and wave_sel:
                wave_sel[1] = wave_time_at_x(ev.pos[0])
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and dragging_cut:
                dragging_cut = False
                # Play the new placement straight away so the drag is self-verifying —
                # from sta_cut - TAIL_LEAD, not from the top: you just moved the cut,
                # so the head is not what you are listening for.
                begin_with_trim(tail_only=True)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and dragging_sel:
                dragging_sel = False
                # A click (not a drag) on the waveform is a SEEK: play from there. Dropping a
                # zero-width selection was the old behaviour and threw the click away.
                if wave_sel and abs(wave_sel[1] - wave_sel[0]) < 0.004:
                    at = wave_sel[0]
                    wave_sel = None
                    player.begin(items[idx]["path"], eff_cut(), from_time=max(0.0, at), tail_only=True)

        player.tick()
        item = items[idx]

        screen.fill(BG)

        # left: station list
        pygame.draw.rect(screen, LIST_BG, (0, 0, LIST_W, WINDOW_H))
        list_header = font_h2.render(f"{len(items)} stations", True, DIM)
        screen.blit(list_header, (16, 24))
        for i in range(list_scroll, min(len(items), list_scroll + visible_rows)):
            it = items[i]
            row_y = LIST_TOP + (i - list_scroll) * ROW_H
            row_rect = pygame.Rect(0, row_y, LIST_W, ROW_H)
            if i == idx:
                pygame.draw.rect(screen, ROW_ACTIVE, row_rect)
            elif row_rect.collidepoint(mouse):
                pygame.draw.rect(screen, ROW_HOVER, row_rect)
            verdict = current_verdict_for(it["sta"])
            marker, marker_color = {
                "PASS": ("✓", PASS_COLOR),
                "FAIL": ("✗", FAIL_COLOR),
            }.get(verdict, ("·", DIM))
            screen.blit(font_row.render(marker, True, marker_color), (12, row_y + 4))
            label = font_row.render(f"{it['stop']}", True, FG if i == idx else (210, 210, 215))
            screen.blit(label, (32, row_y + 4))
            cut_label = font_small.render(f"{it['sta_cut']:.1f}s", True, DIM)
            screen.blit(cut_label, (LIST_W - 12 - cut_label.get_width(), row_y + 7))
        # scroll indicator: small arrows when content above/below viewport
        if list_scroll > 0:
            screen.blit(font_small.render("▲", True, DIM), (LIST_W - 16, LIST_TOP - 14))
        if list_scroll + visible_rows < len(items):
            screen.blit(font_small.render("▼", True, DIM), (LIST_W - 16, WINDOW_H - 16))

        # right: detail panel
        panel_rect = pygame.Rect(LIST_W + PAD_X, 20, WINDOW_W - LIST_W - 2 * PAD_X, ROW_BUTTONS - 34)
        pygame.draw.rect(screen, PANEL, panel_rect, border_radius=10)

        progress = font_h2.render(f"{idx + 1} / {len(items)}", True, DIM)
        screen.blit(progress, (detail_x, ROW_PROGRESS))

        head = font_h1.render(f"{item['stop']}", True, FG)
        screen.blit(head, (detail_x, ROW_TITLE))

        if cut_pending is None:
            sub_txt, sub_col = f"{item['sta']}.mp3   sta_cut = {item['sta_cut']:.1f}s", DIM
        else:
            sub_txt = f"{item['sta']}.mp3   sta_cut = {item['sta_cut']:.1f}s → {cut_pending:.2f}s"
            sub_col = ACCENT
        screen.blit(font_body.render(sub_txt, True, sub_col), (detail_x, ROW_SUB))

        # Note row: ✎ icon + text. Click anywhere in the rect to edit.
        # States: editing (live buffer + cursor), resolved (dim + strike-through),
        # active (amber), empty (placeholder text).
        sta = item["sta"]
        is_hover_note = note_rect.collidepoint(mouse) and not edit_mode
        if is_hover_note:
            pygame.draw.rect(screen, ROW_HOVER, note_rect, border_radius=4)
        if edit_mode:
            pygame.draw.rect(screen, ROW_ACTIVE, note_rect, border_radius=4)
            cursor = "▍" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            txt = font_body.render(f"✎  {edit_buffer}{cursor}", True, FG)
            screen.blit(txt, (note_rect.x + 4, note_rect.y + 2))
        else:
            note_text = notes.get(sta, "")
            resolved = notes_resolved.get(sta, False)
            if note_text:
                color = DIM if resolved else ACCENT
                prefix = "✓" if resolved else "✎"
                txt = font_body.render(f"{prefix}  {note_text}", True, color)
                screen.blit(txt, (note_rect.x + 4, note_rect.y + 2))
                # Strike-through for resolved
                if resolved:
                    pygame.draw.line(screen, DIM, (note_rect.x + 4, note_rect.y + 13), (note_rect.x + 4 + txt.get_width(), note_rect.y + 13), 1)
            else:
                placeholder = font_body.render("✎  (click to add note)", True, (90, 90, 100))
                screen.blit(placeholder, (note_rect.x + 4, note_rect.y + 2))

        phase_label = {
            "HEAD": f"head  [0 → {HEAD_DURATION:.0f}s]",
            "GAP": "(silence)",
            "TAIL": f"tail  [sta_cut − {TAIL_LEAD:.0f}s → end]",
            "MELODY": "melody  [0 → sta_cut]   full loops?",
            "DONE": "playback done — verdict?",
            "IDLE": "",
        }[player.state]
        phase_color = ACCENT if player.state in ("HEAD", "TAIL") else DIM
        phase = font_h2.render(phase_label, True, phase_color)
        screen.blit(phase, (detail_x, ROW_PHASE))

        # seek bar: full file timeline with head/cut-lead/voice tints, sta_cut marker, live cursor
        # Trim overlays (trim_start, trim_end_offset) show pending cuts; sta_cut display
        # is offset by trim_start so user can preview where the cut would land post-trim.
        cur_dur = item["duration"]
        trim_end_pos = max(trim_start + 0.1, cur_dur - trim_end_offset)
        # Display sta_cut adjusted by trim_start so the marker shows post-trim placement preview.
        # Internally the marker still represents the cut moment in the (current) file timeline.
        draw_wave(screen, wave_rect, Path(item["path"]), cur_dur, tuple(wave_sel) if wave_sel else None, eff_cut(), font_small)
        cut_hot = dragging_cut or (seek_grab_rect.collidepoint(mouse) and abs(mouse[0] - cut_x_now()) <= CUT_GRAB_PX)
        draw_seek_bar(
            screen, seek_rect, cur_dur, eff_cut(), player.position(), font_small, trim_start=trim_start, trim_end=trim_end_pos, cut_hot=cut_hot
        )

        # Status line: pending trim and/or pending sta_cut nudge
        status_y = ROW_STATUS
        if trim_start > 0 or trim_end_offset > 0:
            preview_cut = round(eff_cut() - trim_start, 2)
            preview_dur = trim_end_pos - trim_start
            trim_msg = f"pending trim: -{trim_start:.2f}s start, -{trim_end_offset:.2f}s end → new dur {preview_dur:.2f}s, sta_cut {preview_cut:.2f}s"
            screen.blit(font_small.render(trim_msg, True, (250, 130, 130)), (detail_x, status_y))
            status_y += STATUS_LINE
        if cut_pending is not None:
            delta = cut_pending - item["sta_cut"]
            verb = "dragging" if dragging_cut else "pending"
            cut_msg = f"{verb} sta_cut: {item['sta_cut']:.2f}s → {cut_pending:.2f}s " f"({delta:+.2f}s)   R to hear it, C to commit, Z to discard"
            screen.blit(font_small.render(cut_msg, True, ACCENT), (detail_x, status_y))

        if edit_mode:
            hint = font_body.render("Enter save   Esc cancel", True, ACCENT)
        else:
            hint_lines = [
                "P pass   F fail   R replay   E edit note   ↑↓ navigate   Q quit",
                "sta_cut: drag or ←/→, C commit   M whole melody   click timeline to play from there",
                "waveform: drag + X splices it out,  U undo the file to its original    Trim [/] ,/.  T apply",
            ]
            for i, line in enumerate(hint_lines):
                screen.blit(font_body.render(line, True, DIM), (detail_x, ROW_HINTS + i * HINT_LINE))
            hint = None
        if hint is not None:
            screen.blit(hint, (detail_x, ROW_HINTS))

        draw_button(screen, pass_rect, "PASS  (P)", PASS_COLOR, font_btn, pass_rect.collidepoint(mouse))
        draw_button(screen, fail_rect, "FAIL  (F)", FAIL_COLOR, font_btn, fail_rect.collidepoint(mouse))
        draw_button(screen, replay_rect, "REPLAY  (R)", REPLAY_COLOR, font_btn, replay_rect.collidepoint(mouse))

        pygame.display.flip()
        clock.tick(60)

    player.stop()
    pygame.quit()

    # Report
    print()
    print(f"Reviewed: {len(verdicts)} / {len(items)}")
    passed = [s for s, v in verdicts.items() if v == "PASS"]
    failed = [s for s, v in verdicts.items() if v == "FAIL"]
    print(f"  PASS: {len(passed)}")
    print(f"  FAIL: {len(failed)}")
    if failed:
        print("\nFailed (need re-listen / re-cut):")
        for sta in failed:
            sta_cut = next(it["sta_cut"] for it in items if it["sta"] == sta)
            print(f"  - {sta:30s}  sta_cut={sta_cut}")
    if len(verdicts) < len(items):
        skipped = [it["sta"] for it in items if it["sta"] not in verdicts]
        print(f"\nNot reviewed: {len(skipped)}  ({', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''})")

    # Persist for follow-up. out_path was computed at startup; reuse it so the
    # merge target matches what we loaded prior_verdicts from.
    # Merge with existing JSON so a partial run (e.g. --only kumagaya) doesn't
    # clobber verdicts for stations that weren't tested this time.
    prior_by_sta: dict[str, dict] = {}
    if out_path.exists():
        try:
            prior = json.loads(out_path.read_text(encoding="utf-8"))
            prior_by_sta = {it["sta"]: it for it in prior.get("items", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    # `stops` is the startup snapshot, so its sta_cut is PRE-session. C (commit a
    # nudge) and T (interactive trim) both write route.json via persist_cut and
    # update items[idx], but items entries are fresh dicts built at line ~548 —
    # nothing propagates back into `stops`. Recording it unmodified would file a
    # verdict against a cut the run itself replaced, and this JSON is the committed
    # record of what the ear approved (#118). Overlay by slug: only an item that was
    # playable this run can have been edited, and persist_cut writes per-slug across
    # every referencing stop, so keying on sta matches what landed on disk.
    session_cuts = {it["sta"]: float(it["sta_cut"]) for it in items}

    # build the full route's items list (unfiltered) so the JSON always reflects route order
    full_items = []
    for stop in stops:
        sta_cut_v = stop.get("sta_cut")
        for sta in stop.get("sta", []):
            if sta_cut_v is None:
                continue
            full_items.append({"stop": stop["name"], "sta": sta, "sta_cut": session_cuts.get(sta, float(sta_cut_v))})

    # Verdicts carry the DATE they were given. Without it a PASS from months ago and one
    # from ten minutes ago are identical in this file, so a run that splices a file but
    # never re-passes it leaves a green verdict describing audio that no longer exists —
    # and `audio/README.md`, which is written from here, inherits the claim. Stamped only
    # when THIS run recorded the verdict; otherwise the prior stamp carries through.
    today = datetime.date.today().isoformat()

    merged_items = []
    for fi in full_items:
        sta = fi["sta"]
        checked = prior_by_sta.get(sta, {}).get("checked")
        if sta in verdicts:
            verdict = verdicts[sta]  # this run's verdict wins
            checked = today
        elif sta in prior_by_sta:
            verdict = prior_by_sta[sta].get("verdict", "NOT_REVIEWED")
        else:
            verdict = "NOT_REVIEWED"
        # Notes: live in-app edits win, fall back to prior JSON
        note = notes.get(sta, prior_by_sta.get(sta, {}).get("note", ""))
        resolved = notes_resolved.get(sta, prior_by_sta.get(sta, {}).get("note_resolved", False))
        item = {**fi, "verdict": verdict, "note": note}
        if checked:
            item["checked"] = checked
        if note:
            item["note_resolved"] = bool(resolved)
        merged_items.append(item)

    summary_pass = sum(1 for it in merged_items if it["verdict"] == "PASS")
    summary_fail = sum(1 for it in merged_items if it["verdict"] == "FAIL")
    summary_nr = sum(1 for it in merged_items if it["verdict"] == "NOT_REVIEWED")

    payload = {
        "work_dir": str(args.work_dir).replace("\\", "/"),
        "items": merged_items,
        "summary": {
            "total": len(merged_items),
            "pass": summary_pass,
            "fail": summary_fail,
            "not_reviewed": summary_nr,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nResults written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

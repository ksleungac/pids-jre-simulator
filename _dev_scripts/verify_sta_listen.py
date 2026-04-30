"""Quick by-ear STA cut verifier.

For each STA in a route, plays the first HEAD_DURATION seconds, brief pause,
then [sta_cut - TAIL_LEAD, EOF] so you hear the music tail → cut → voice
transition. A short beep marks the exact sta_cut moment during tail playback.
Click/key in PASS or FAIL per station; final report to stdout.

    uv run python _dev_scripts/verify_sta_listen.py audio/takasaki/3922E

Keys: P=Pass  F=Fail  R=Replay  E=Edit note  N=Next without verdict  Q/Esc=Quit
      [/] adjust start-trim  ,/. adjust end-trim  T apply trim  Z reset trim
      (hold Shift while adjusting for fine 0.01s steps)

Interactive trim: when an audio file has a stutter / extra content at the start
or end that the propose+splice pipeline can't fix algorithmically, use the
trim controls to nudge a red overlay marker on the seek bar. T commits the
trim by lossless-cutting the mp3 with ffmpeg AND shifting sta_cut down by the
start-trim amount (so the cut moment stays anchored to the same content).

Per-station notes: click the ✎ row above the seek bar (or press E) to add /
edit a note for the current station. Enter to save, Esc to cancel. Notes
survive across runs (stored in audio_src/<line>/<diagram>/sta_verify_results.json
under the `note` field). Marking PASS auto-resolves the current note (display
goes dim with strike-through, indicating the concern was checked and OK).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pygame

WINDOW_W, WINDOW_H = 1040, 540
LIST_W = 280             # left-column station list width
LIST_TOP = 60
ROW_H = 26
HEAD_DURATION = 3.0      # seconds played from start of file
TAIL_LEAD = 3.0          # seconds before sta_cut where tail playback starts
INTER_GAP_MS = 400       # silence between head and tail segments
FADE_MS = 120            # fade-out when stopping head segment

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
HEAD_TINT = (60, 130, 90)       # green-ish — head segment that gets played
CUT_LEAD_TINT = (180, 130, 60)  # amber — TAIL_LEAD seconds before sta_cut (also played)
VOICE_TINT = (170, 70, 70)      # red — voice region from sta_cut to EOF (also played)
UNTOUCHED_TINT = (60, 60, 70)   # dim gray — region between head end and tail start (skipped)
CUT_MARKER = (255, 255, 255)
CURSOR = (255, 240, 100)


def find_font(size: int) -> pygame.font.Font:
    for candidate in ("fonts/ShinGoPr6N-Medium.otf", "fonts/HelveticaNeue-Bold.otf"):
        p = Path(candidate)
        if p.exists():
            return pygame.font.Font(str(p), size)
    return pygame.font.SysFont(None, size)


def draw_button(screen: pygame.Surface, rect: pygame.Rect, label: str,
                color: tuple[int, int, int], font: pygame.font.Font, hover: bool) -> None:
    fill = tuple(min(255, c + 30) for c in color) if hover else color
    pygame.draw.rect(screen, fill, rect, border_radius=8)
    pygame.draw.rect(screen, (255, 255, 255), rect, width=2, border_radius=8)
    txt = font.render(label, True, (255, 255, 255))
    screen.blit(txt, txt.get_rect(center=rect.center))


def draw_seek_bar(screen: pygame.Surface, rect: pygame.Rect, duration: float,
                  sta_cut: float, position: float | None, font: pygame.font.Font,
                  trim_start: float = 0.0, trim_end: float | None = None) -> None:
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
    # sta_cut marker — taller than the bar so it's obvious
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
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe",
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
        self.head_stop_at = 0     # ms tick at which to fade out head
        self.gap_until = 0        # ms tick at which to start tail
        self.tail_path: Path | None = None
        self.tail_start: float = 0.0
        self.head_start_offset: float = 0.0  # head playback starts at this file-time offset
        self.tail_end: float | None = None   # absolute file time to stop tail (early stop for trim preview)
        self.segment_started_ms = 0  # tick when current HEAD or TAIL segment began playing
        self.cut_time: float = 0.0   # absolute file-time position where sta_cut sits
        self.beep_played: bool = False
        self.beep = _make_beep()

    def begin(self, path: Path, sta_cut: float,
              head_start: float = 0.0, tail_end: float | None = None) -> None:
        """Start playback. head_start/tail_end let the caller preview pending trim
        without touching the file: head plays from `head_start` (skipping the
        soon-to-be-trimmed prefix), tail stops at `tail_end` (skipping the
        soon-to-be-trimmed suffix)."""
        self.tail_path = path
        self.tail_start = max(head_start, sta_cut - TAIL_LEAD)
        self.cut_time = sta_cut
        self.head_start_offset = head_start
        self.tail_end = tail_end
        self.beep_played = False
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        pygame.mixer.music.load(str(path))
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir", type=Path, help="audio/<line>/<diagram>")
    ap.add_argument("--only", help="comma-separated sta basenames to test (e.g. 'kumagaya' or 'kumagaya,konosu'). Existing JSON verdicts for un-tested stations are preserved.")
    args = ap.parse_args()
    only: set[str] | None = set(s.strip() for s in args.only.split(",")) if args.only else None

    route_path = args.work_dir / "route.json"
    sta_dir = args.work_dir / "sta"
    if not route_path.exists():
        print(f"route.json not found: {route_path}", file=sys.stderr)
        return 1

    route = json.loads(route_path.read_text(encoding="utf-8"))
    items: list[dict] = []
    for stop in route["stops"]:
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

    # Output: audio_src/<line>/<diagram>/sta_verify_results.json. Mid-products of audio
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
    notes: dict[str, str] = {}                    # sta -> note text (live, editable)
    notes_resolved: dict[str, bool] = {}          # sta -> resolved flag
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
    verdicts: dict[str, str] = {}  # sta -> "PASS"/"FAIL" — this session's verdicts
    player.begin(items[idx]["path"], items[idx]["sta_cut"])

    def begin_with_trim() -> None:
        """Start playback for current item, applying any pending trim as preview."""
        item = items[idx]
        head_s = trim_start
        tail_e = item.get("duration", 0.0) - trim_end_offset if trim_end_offset > 0 else None
        player.begin(item["path"], item["sta_cut"], head_start=head_s, tail_end=tail_e)

    btn_w, btn_h = 150, 56
    detail_x = LIST_W + 40
    pass_rect = pygame.Rect(detail_x, WINDOW_H - 90, btn_w, btn_h)
    fail_rect = pygame.Rect(detail_x + btn_w + 20, WINDOW_H - 90, btn_w, btn_h)
    replay_rect = pygame.Rect(detail_x + 2 * (btn_w + 20), WINDOW_H - 90, btn_w, btn_h)
    # Note row sits above the seek bar; click anywhere in this rect to edit.
    note_rect = pygame.Rect(detail_x, 134, WINDOW_W - detail_x - 20, 26)

    # Edit-mode state for in-app note editing
    edit_mode = False
    edit_buffer = ""
    # Pending trim state (per-station, applied via T key)
    trim_start: float = 0.0      # seconds to trim from start (file head)
    trim_end_offset: float = 0.0 # seconds to trim from end (file tail)

    def current_verdict_for(sta: str) -> str:
        if sta in verdicts:
            return verdicts[sta]
        return prior_verdicts.get(sta, "")

    def jump_to(new_idx: int) -> None:
        nonlocal idx, edit_mode, trim_start, trim_end_offset
        edit_mode = False  # cancel any in-progress edit on navigation
        trim_start = 0.0   # discard pending trim — moving on to new station
        trim_end_offset = 0.0
        idx = max(0, min(len(items) - 1, new_idx))
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
        cmd = [_find_ffmpeg(), "-y", "-loglevel", "error",
               "-ss", f"{keep_start:.3f}",
               "-i", str(src),
               "-t", f"{new_dur:.3f}",
               "-c", "copy",
               str(tmp)]
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
        # Persist sta_cut to route.json
        route_obj = json.loads(route_path.read_text(encoding="utf-8"))
        for stop in route_obj["stops"]:
            if item["sta"] in stop.get("sta", []):
                stop["sta_cut"] = new_cut
                break
        route_path.write_text(json.dumps(route_obj, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
        print(f"trimmed {item['sta']}: cut [0,{keep_start:.3f}] + [{keep_end:.3f},{dur:.3f}]  sta_cut → {new_cut}")
        # Reset pending trim, reload player
        trim_start = 0.0
        trim_end_offset = 0.0
        player.begin(src, new_cut)
        return True

    def list_row_at(pos: tuple[int, int]) -> int | None:
        x, y = pos
        if x >= LIST_W or y < LIST_TOP:
            return None
        i = (y - LIST_TOP) // ROW_H
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
                        begin_with_trim()
                    elif ev.key == pygame.K_UP:
                        jump_to(idx - 1)
                    elif ev.key == pygame.K_DOWN:
                        jump_to(idx + 1)
                    elif ev.key == pygame.K_e:
                        start_edit()
                    # Trim controls: [/] adjust start, ,/. adjust end, T apply, Z reset
                    elif ev.key == pygame.K_LEFTBRACKET:   # [
                        trim_start = max(0.0, trim_start - step)
                    elif ev.key == pygame.K_RIGHTBRACKET:  # ]
                        trim_start = min(items[idx]["sta_cut"] - 0.05, trim_start + step)
                    elif ev.key == pygame.K_COMMA:
                        trim_end_offset = min(cur_dur - items[idx]["sta_cut"] - 0.05, trim_end_offset + step)
                    elif ev.key == pygame.K_PERIOD:
                        trim_end_offset = max(0.0, trim_end_offset - step)
                    elif ev.key == pygame.K_t:
                        apply_trim()
                    elif ev.key == pygame.K_z:
                        trim_start = 0.0
                        trim_end_offset = 0.0
            elif ev.type == pygame.TEXTINPUT and edit_mode:
                edit_buffer += ev.text
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if edit_mode:
                    # Click outside note rect cancels edit
                    if not note_rect.collidepoint(ev.pos):
                        cancel_edit()
                else:
                    if note_rect.collidepoint(ev.pos):
                        start_edit()
                    else:
                        row = list_row_at(ev.pos)
                        if row is not None:
                            jump_to(row)
                        elif pass_rect.collidepoint(ev.pos):
                            record("PASS")
                        elif fail_rect.collidepoint(ev.pos):
                            record("FAIL")
                        elif replay_rect.collidepoint(ev.pos):
                            begin_with_trim()

        player.tick()
        item = items[idx]

        screen.fill(BG)

        # left: station list
        pygame.draw.rect(screen, LIST_BG, (0, 0, LIST_W, WINDOW_H))
        list_header = font_h2.render(f"{len(items)} stations", True, DIM)
        screen.blit(list_header, (16, 24))
        for i, it in enumerate(items):
            row_y = LIST_TOP + i * ROW_H
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

        # right: detail panel
        panel_rect = pygame.Rect(LIST_W + 20, 20, WINDOW_W - LIST_W - 40, WINDOW_H - 130)
        pygame.draw.rect(screen, PANEL, panel_rect, border_radius=10)

        progress = font_h2.render(f"{idx + 1} / {len(items)}", True, DIM)
        screen.blit(progress, (detail_x, 36))

        head = font_h1.render(f"{item['stop']}", True, FG)
        screen.blit(head, (detail_x, 72))

        sub = font_body.render(f"{item['sta']}.mp3   sta_cut = {item['sta_cut']:.1f}s", True, DIM)
        screen.blit(sub, (detail_x, 110))

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
                    pygame.draw.line(screen, DIM,
                                     (note_rect.x + 4, note_rect.y + 13),
                                     (note_rect.x + 4 + txt.get_width(), note_rect.y + 13), 1)
            else:
                placeholder = font_body.render("✎  (click to add note)", True, (90, 90, 100))
                screen.blit(placeholder, (note_rect.x + 4, note_rect.y + 2))

        phase_label = {
            "HEAD": f"head  [0 → {HEAD_DURATION:.0f}s]",
            "GAP": "(silence)",
            "TAIL": f"tail  [sta_cut − {TAIL_LEAD:.0f}s → end]",
            "DONE": "playback done — verdict?",
            "IDLE": "",
        }[player.state]
        phase_color = ACCENT if player.state in ("HEAD", "TAIL") else DIM
        phase = font_h2.render(phase_label, True, phase_color)
        screen.blit(phase, (detail_x, 160))

        # seek bar: full file timeline with head/cut-lead/voice tints, sta_cut marker, live cursor
        # Trim overlays (trim_start, trim_end_offset) show pending cuts; sta_cut display
        # is offset by trim_start so user can preview where the cut would land post-trim.
        seek_rect = pygame.Rect(detail_x, 230, WINDOW_W - detail_x - 20, 18)
        cur_dur = item["duration"]
        trim_end_pos = max(trim_start + 0.1, cur_dur - trim_end_offset)
        # Display sta_cut adjusted by trim_start so the marker shows post-trim placement preview.
        # Internally the marker still represents the cut moment in the (current) file timeline.
        draw_seek_bar(screen, seek_rect, cur_dur, item["sta_cut"], player.position(), font_small,
                      trim_start=trim_start, trim_end=trim_end_pos)

        # Trim status line: only show if any pending trim
        if trim_start > 0 or trim_end_offset > 0:
            preview_cut = round(item["sta_cut"] - trim_start, 2)
            preview_dur = trim_end_pos - trim_start
            trim_msg = f"pending trim: -{trim_start:.2f}s start, -{trim_end_offset:.2f}s end → new dur {preview_dur:.2f}s, sta_cut {preview_cut:.2f}s"
            screen.blit(font_small.render(trim_msg, True, (250, 130, 130)), (detail_x, 268))

        if edit_mode:
            hint = font_body.render("Enter save   Esc cancel", True, ACCENT)
        else:
            hint_lines = [
                "P pass   F fail   R replay   E edit note   ↑↓ navigate   Q quit",
                "Trim:  [/] start   ,/. end   T apply   Z reset   (Shift = fine 0.01s)",
            ]
            screen.blit(font_body.render(hint_lines[0], True, DIM), (detail_x, WINDOW_H - 148))
            screen.blit(font_body.render(hint_lines[1], True, DIM), (detail_x, WINDOW_H - 124))
            hint = None
        if hint is not None:
            screen.blit(hint, (detail_x, WINDOW_H - 130))

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

    # build the full route's items list (unfiltered) so the JSON always reflects route order
    full_items = []
    for stop in route["stops"]:
        sta_cut_v = stop.get("sta_cut")
        for sta in stop.get("sta", []):
            if sta_cut_v is None:
                continue
            full_items.append({"stop": stop["name"], "sta": sta, "sta_cut": float(sta_cut_v)})

    merged_items = []
    for fi in full_items:
        sta = fi["sta"]
        if sta in verdicts:
            verdict = verdicts[sta]  # this run's verdict wins
        elif sta in prior_by_sta:
            verdict = prior_by_sta[sta].get("verdict", "NOT_REVIEWED")
        else:
            verdict = "NOT_REVIEWED"
        # Notes: live in-app edits win, fall back to prior JSON
        note = notes.get(sta, prior_by_sta.get(sta, {}).get("note", ""))
        resolved = notes_resolved.get(sta, prior_by_sta.get(sta, {}).get("note_resolved", False))
        item = {**fi, "verdict": verdict, "note": note}
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

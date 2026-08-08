# SPDX-License-Identifier: MIT
"""Quick by-ear PA verifier with manual start-trim controls.

For each PA in a route, plays the first PREVIEW_DURATION seconds (head→tail cycle).
Click/key PASS or FAIL per station. Persists verdicts to
audio_src/<line>/pa_verify_results.json.

    uv run python _dev_scripts/verify_pa_listen.py audio/tokaido

Keys: P=Pass  F=Fail  R=Replay  E=Edit note  N=Next without verdict  Q/Esc=Quit
      ↑↓ navigate  Wheel=scroll sidebar
      [/] adjust start-trim  T apply trim  Z reset trim
      (hold Shift while adjusting for fine 0.01s steps)

Interactive trim: drag the red marker on the seek bar (or use [/]) to set the cut
point. R replays from the trim offset in continuous scrub mode (no 3s cycle) so you
can hear exactly where voice starts. T commits the trim by lossless-cutting the mp3
with ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pygame

from audio_layout import discover_route_sources, order_by_reference_count

WINDOW_W, WINDOW_H = 1040, 540
LIST_W = 280
LIST_TOP = 60
ROW_H = 26
FADE_MS = 120
PREVIEW_DURATION = 3.0
TARGET_PAD = 0.08  # silence before voice onset after trim

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
PLAYED_TINT = (60, 130, 90)
UNTOUCHED_TINT = (60, 60, 70)
TRIM_OVERLAY = (200, 60, 60)
CURSOR = (255, 240, 100)


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


def draw_seek_bar(
    screen: pygame.Surface,
    rect: pygame.Rect,
    duration: float,
    position: float | None,
    font: pygame.font.Font,
    trim_start: float = 0.0,
) -> None:
    if duration <= 0:
        return

    def x_for(t: float) -> int:
        return rect.x + int(rect.w * (max(0.0, min(duration, t)) / duration))

    head_end = min(PREVIEW_DURATION, duration)

    # Base bar (untouched gray)
    pygame.draw.rect(screen, UNTOUCHED_TINT, rect, border_radius=4)

    # Head preview region (0 → PREVIEW_DURATION, offset by trim_start)
    head_end_x = x_for(head_end)
    if head_end_x > rect.x:
        pygame.draw.rect(screen, PLAYED_TINT, (rect.x, rect.y, head_end_x - rect.x, rect.h))

    # Played portion up to cursor (tinted on top)
    if position is not None and position > 0:
        pos_x = x_for(position)
        if pos_x > rect.x:
            pygame.draw.rect(screen, PLAYED_TINT, (rect.x, rect.y, pos_x - rect.x, rect.h))

    # Pending trim overlay: red hatch over [0, trim_start] — what will be cut
    if trim_start > 0:
        ts_x = x_for(trim_start)
        s = pygame.Surface((ts_x - rect.x, rect.h), pygame.SRCALPHA)
        s.fill((*TRIM_OVERLAY, 140))
        screen.blit(s, (rect.x, rect.y))
        # Red marker line at trim-start
        pygame.draw.line(screen, TRIM_OVERLAY, (ts_x, rect.y - 8), (ts_x, rect.bottom + 8), 2)

    pygame.draw.rect(screen, (90, 90, 100), rect, width=1, border_radius=4)

    if position is not None:
        cur_x = x_for(position)
        pygame.draw.line(screen, CURSOR, (cur_x, rect.y - 4), (cur_x, rect.bottom + 4), 2)

    label_0 = font.render("0.0s", True, DIM)
    screen.blit(label_0, (rect.x, rect.bottom + 8))
    dur_label = font.render(f"{duration:.1f}s", True, DIM)
    screen.blit(dur_label, (rect.right - dur_label.get_width(), rect.bottom + 8))
    if position is not None:
        pos_label = font.render(f"{position:.1f}s", True, FG)
        label_x = max(rect.x, min(rect.right - pos_label.get_width(), x_for(position) - pos_label.get_width() // 2))
        screen.blit(pos_label, (label_x, rect.y - 24))


class Player:
    """IDLE -> HEAD -> GAP -> TAIL -> DONE. Scrub mode: HEAD plays indefinitely (no stop/cycle)."""

    def __init__(self) -> None:
        self.state = "IDLE"
        self._head_stop_at = 0
        self._gap_until = 0
        self._tail_start = 0.0
        self._seg_start_ms = 0
        self._head_start_offset = 0.0
        self._path: Path | None = None
        self._scrub = False

    def begin(self, path: Path, duration: float = 0.0, head_start: float = 0.0, scrub: bool = False) -> None:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        pygame.mixer.music.load(str(path))
        try:
            pygame.mixer.music.play(start=head_start)
        except pygame.error:
            pygame.mixer.music.play()
        self._path = path
        self._head_start_offset = head_start
        self._tail_start = max(head_start, duration - PREVIEW_DURATION)
        self._scrub = scrub
        self._head_stop_at = 0  # scrub mode: no auto-stop
        if not scrub:
            now = pygame.time.get_ticks()
            self._head_stop_at = now + int(PREVIEW_DURATION * 1000)
        self._seg_start_ms = pygame.time.get_ticks()
        self.state = "HEAD"

    def position(self) -> float | None:
        now = pygame.time.get_ticks()
        if self.state == "HEAD":
            return self._head_start_offset + (now - self._seg_start_ms) / 1000.0
        if self.state == "TAIL":
            return self._tail_start + (now - self._seg_start_ms) / 1000.0
        if self.state == "GAP":
            return self._head_start_offset + PREVIEW_DURATION
        return None

    def tick(self) -> None:
        now = pygame.time.get_ticks()
        if self.state == "HEAD":
            if not pygame.mixer.music.get_busy():
                self.state = "GAP" if (not self._scrub and self._tail_start > self._head_start_offset) else "DONE"
            elif not self._scrub and self._head_stop_at > 0 and now >= self._head_stop_at:
                pygame.mixer.music.fadeout(FADE_MS)
                self._gap_until = now + FADE_MS + 300
                self.state = "GAP"
        elif self.state == "GAP":
            if now >= self._gap_until and self._tail_start > self._head_start_offset:
                assert self._path is not None
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
                pygame.mixer.music.load(str(self._path))
                try:
                    pygame.mixer.music.play(start=self._tail_start)
                except pygame.error:
                    pygame.mixer.music.play()
                self._seg_start_ms = pygame.time.get_ticks()
                self.state = "TAIL"
            elif now >= self._gap_until:
                self.state = "DONE"
        elif self.state == "TAIL":
            if not pygame.mixer.music.get_busy():
                self.state = "DONE"

    def stop(self) -> None:
        pygame.mixer.music.fadeout(FADE_MS)
        self.state = "DONE"


def _find_ffmpeg() -> str:
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
    winget_root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if winget_root.exists():
        candidates.extend(winget_root.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"))
    for c in candidates:
        if c.exists():
            return str(c)
    return "ffmpeg"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir", type=Path, help="audio/<line>")
    ap.add_argument(
        "--only",
        help="comma-separated pa basenames to test (e.g. 'tokyo-dep' or 'tokyo-dep,shimbashi-arr')",
    )
    args = ap.parse_args()
    only: set[str] | None = set(s.strip() for s in args.only.split(",")) if args.only else None

    try:
        route_paths, pa_dir, loaded = discover_route_sources(args.work_dir, "pa")
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    pooled = not (len(route_paths) == 1 and route_paths[0].parent == args.work_dir)
    if pooled:
        print(f"pooled layout: {len(route_paths)} route.json — " f"{', '.join(p.parent.name for p in route_paths)}")

    items: list[dict] = []
    seen: set[str] = set()

    def _add(stop: dict, pa_list: list[str]) -> None:
        for pa in pa_list:
            # On a pool the same mp3 is referenced by several diagrams — play it once.
            if pa in seen:
                continue
            path = pa_dir / f"{pa}.mp3"
            if not path.exists():
                continue
            if only is not None and pa not in only:
                continue
            seen.add(pa)
            items.append({"stop": stop["name"], "pa": pa, "path": path})

    for _p, stops in order_by_reference_count(loaded, ("pa", "pa_at_station")):
        for stop in stops:
            _add(stop, stop.get("pa", []))
            _add(stop, stop.get("pa_at_station", []))

    if not items:
        msg = f"no matching PAs (filter --only={args.only})" if only else "no playable PA entries"
        print(msg, file=sys.stderr)
        return 1
    if only:
        unmatched = only - {it["pa"] for it in items}
        if unmatched:
            print(f"warning: --only names not found in route: {sorted(unmatched)}", file=sys.stderr)

    rel_under_audio = [p for p in args.work_dir.parts if p not in (".", "..", "audio")]
    if rel_under_audio:
        out_path = Path("audio_src") / Path(*rel_under_audio) / "pa_verify_results.json"
    else:
        slug = "_".join(args.work_dir.parts) or "results"
        out_path = Path(f"_pa_verify_{slug}.json")

    prior_verdicts: dict[str, str] = {}
    notes: dict[str, str] = {}
    notes_resolved: dict[str, bool] = {}
    if out_path.exists():
        try:
            prior = json.loads(out_path.read_text(encoding="utf-8"))
            for it in prior.get("items", []):
                if it.get("verdict") in ("PASS", "FAIL"):
                    prior_verdicts[it["pa"]] = it["verdict"]
                if it.get("note"):
                    notes[it["pa"]] = it["note"]
                    notes_resolved[it["pa"]] = bool(it.get("note_resolved", False))
        except (json.JSONDecodeError, KeyError):
            pass

    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(f"PA verifier — {args.work_dir}")
    clock = pygame.time.Clock()
    font_h1 = find_font(28)
    font_h2 = find_font(22)
    font_body = find_font(18)
    font_btn = find_font(20)
    font_small = find_font(14)
    font_row = find_font(16)

    for it in items:
        try:
            it["duration"] = pygame.mixer.Sound(str(it["path"])).get_length()
        except pygame.error:
            it["duration"] = 0.0

    player = Player()
    idx = 0
    list_scroll = 0
    visible_rows = max(1, (WINDOW_H - LIST_TOP) // ROW_H)
    verdicts: dict[str, str] = {}
    edit_mode = False
    edit_buffer = ""
    trim_start: float = 0.0
    dragging_trim = False

    def begin_with_trim(replay: bool = False) -> None:
        nonlocal trim_start
        # Start playback with optional trim offset. In scrub mode (trim>0+replay) plays continuously without cycling.
        item = items[idx]
        offset = trim_start if replay else 0.0
        scrub = trim_start > 0 and replay
        if not replay:
            trim_start = 0.0  # fresh navigation resets trim
        player.begin(item["path"], item.get("duration", 0.0), head_start=offset, scrub=scrub)

    player.begin(items[idx]["path"], items[idx].get("duration", 0.0))

    btn_w, btn_h = 150, 56
    detail_x = LIST_W + 40
    pass_rect = pygame.Rect(detail_x, WINDOW_H - 90, btn_w, btn_h)
    fail_rect = pygame.Rect(detail_x + btn_w + 20, WINDOW_H - 90, btn_w, btn_h)
    replay_rect = pygame.Rect(detail_x + 2 * (btn_w + 20), WINDOW_H - 90, btn_w, btn_h)
    note_rect = pygame.Rect(detail_x, 134, WINDOW_W - detail_x - 20, 26)
    seek_rect = pygame.Rect(detail_x, 230, WINDOW_W - detail_x - 20, 18)

    def current_verdict_for(pa: str) -> str:
        if pa in verdicts:
            return verdicts[pa]
        return prior_verdicts.get(pa, "")

    def jump_to(new_idx: int) -> None:
        nonlocal idx, edit_mode, list_scroll, trim_start
        edit_mode = False
        trim_start = 0.0
        idx = max(0, min(len(items) - 1, new_idx))
        if idx < list_scroll:
            list_scroll = idx
        elif idx >= list_scroll + visible_rows:
            list_scroll = idx - visible_rows + 1
        begin_with_trim()

    def record(verdict: str) -> None:
        pa = items[idx]["pa"]
        verdicts[pa] = verdict
        if verdict == "PASS" and pa in notes:
            notes_resolved[pa] = True
        elif verdict == "FAIL":
            notes_resolved[pa] = False
        if idx + 1 < len(items):
            jump_to(idx + 1)
        else:
            player.stop()

    def start_edit() -> None:
        nonlocal edit_mode, edit_buffer
        edit_mode = True
        edit_buffer = notes.get(items[idx]["pa"], "")
        try:
            pygame.key.start_text_input()
        except AttributeError:
            pass

    def commit_edit() -> None:
        nonlocal edit_mode
        pa = items[idx]["pa"]
        text = edit_buffer.strip()
        if text:
            notes[pa] = text
            notes_resolved[pa] = False
        else:
            notes.pop(pa, None)
            notes_resolved.pop(pa, None)
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
        nonlocal trim_start
        if trim_start <= 0:
            return False
        item = items[idx]
        src = Path(item["path"])
        dur = item.get("duration", 0.0)
        keep_start = trim_start
        if keep_start >= dur - 0.1:
            return False
        new_dur = dur - keep_start
        player.stop()
        pygame.mixer.music.unload()
        tmp = src.with_suffix(".tmp.mp3")
        cmd = [
            _find_ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{keep_start:.3f}",
            "-i",
            str(src),
            "-t",
            f"{new_dur:.3f}",
            "-c",
            "copy",
            str(tmp),
        ]
        try:
            subprocess.run(cmd, check=True)
            shutil.move(str(tmp), str(src))
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"trim failed for {src.name}: {e}", file=sys.stderr)
            return False
        item["duration"] = new_dur
        print(f"trimmed {item['pa']}: -{keep_start:.3f}s start  new dur {new_dur:.2f}s")
        trim_start = 0.0
        begin_with_trim()
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
                        begin_with_trim(replay=True)
                    elif ev.key == pygame.K_UP:
                        jump_to(idx - 1)
                    elif ev.key == pygame.K_DOWN:
                        jump_to(idx + 1)
                    elif ev.key == pygame.K_e:
                        start_edit()
                    elif ev.key == pygame.K_LEFTBRACKET:  # [
                        trim_start = max(0.0, trim_start - step)
                    elif ev.key == pygame.K_RIGHTBRACKET:  # ]
                        trim_start = min(cur_dur - 0.1, trim_start + step)
                    elif ev.key == pygame.K_t:
                        apply_trim()
                    elif ev.key == pygame.K_z:
                        trim_start = 0.0
                        begin_with_trim()  # replay from 0
            elif ev.type == pygame.TEXTINPUT and edit_mode:
                edit_buffer += ev.text
            elif ev.type == pygame.MOUSEWHEEL:
                max_scroll = max(0, len(items) - visible_rows)
                list_scroll = max(0, min(max_scroll, list_scroll - ev.y * 3))
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if edit_mode:
                    if not note_rect.collidepoint(ev.pos):
                        cancel_edit()
                else:
                    if note_rect.collidepoint(ev.pos):
                        start_edit()
                    elif seek_rect.collidepoint(ev.pos):
                        # Start trim drag: set trim marker to click position
                        dragging_trim = True
                        dur = items[idx].get("duration", 0.0)
                        frac = (ev.pos[0] - seek_rect.x) / max(1, seek_rect.w)
                        trim_start = round(max(0.0, min(dur - 0.1, frac * dur)), 2)
                    else:
                        row = list_row_at(ev.pos)
                        if row is not None:
                            jump_to(row)
                        elif pass_rect.collidepoint(ev.pos):
                            record("PASS")
                        elif fail_rect.collidepoint(ev.pos):
                            record("FAIL")
                        elif replay_rect.collidepoint(ev.pos):
                            begin_with_trim(replay=True)
            elif ev.type == pygame.MOUSEMOTION and dragging_trim:
                dur = items[idx].get("duration", 0.0)
                frac = (ev.pos[0] - seek_rect.x) / max(1, seek_rect.w)
                trim_start = round(max(0.0, min(dur - 0.1, frac * dur)), 2)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if dragging_trim:
                    dragging_trim = False
                    if trim_start > 0:
                        begin_with_trim(replay=True)

        player.tick()
        item = items[idx]

        screen.fill(BG)

        # Left: station list
        pygame.draw.rect(screen, LIST_BG, (0, 0, LIST_W, WINDOW_H))
        list_header = font_h2.render(f"{len(items)} segments", True, DIM)
        screen.blit(list_header, (16, 24))
        for i in range(list_scroll, min(len(items), list_scroll + visible_rows)):
            it = items[i]
            row_y = LIST_TOP + (i - list_scroll) * ROW_H
            row_rect = pygame.Rect(0, row_y, LIST_W, ROW_H)
            if i == idx:
                pygame.draw.rect(screen, ROW_ACTIVE, row_rect)
            elif row_rect.collidepoint(mouse):
                pygame.draw.rect(screen, ROW_HOVER, row_rect)
            verdict = current_verdict_for(it["pa"])
            marker, marker_color = {
                "PASS": ("\u2713", PASS_COLOR),
                "FAIL": ("\u2717", FAIL_COLOR),
            }.get(verdict, ("·", DIM))
            screen.blit(font_row.render(marker, True, marker_color), (12, row_y + 4))
            label = font_row.render(f"{it['stop']}", True, FG if i == idx else (210, 210, 215))
            screen.blit(label, (32, row_y + 4))
            pa_label = font_small.render(it["pa"], True, DIM)
            screen.blit(pa_label, (LIST_W - 12 - pa_label.get_width(), row_y + 7))
        if list_scroll > 0:
            screen.blit(font_small.render("\u25b2", True, DIM), (LIST_W - 16, LIST_TOP - 14))
        if list_scroll + visible_rows < len(items):
            screen.blit(font_small.render("\u25bc", True, DIM), (LIST_W - 16, WINDOW_H - 16))

        # Right: detail panel
        panel_rect = pygame.Rect(LIST_W + 20, 20, WINDOW_W - LIST_W - 40, WINDOW_H - 130)
        pygame.draw.rect(screen, PANEL, panel_rect, border_radius=10)

        progress = font_h2.render(f"{idx + 1} / {len(items)}", True, DIM)
        screen.blit(progress, (detail_x, 36))

        head = font_h1.render(f"{item['stop']}", True, FG)
        screen.blit(head, (detail_x, 72))

        sub = font_body.render(f"{item['pa']}.mp3   {item['duration']:.1f}s", True, DIM)
        screen.blit(sub, (detail_x, 110))

        # Note row
        pa = item["pa"]
        is_hover_note = note_rect.collidepoint(mouse) and not edit_mode
        if is_hover_note:
            pygame.draw.rect(screen, ROW_HOVER, note_rect, border_radius=4)
        if edit_mode:
            pygame.draw.rect(screen, ROW_ACTIVE, note_rect, border_radius=4)
            cursor_symbol = "\u258d" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            txt = font_body.render(f"\u270e  {edit_buffer}{cursor_symbol}", True, FG)
            screen.blit(txt, (note_rect.x + 4, note_rect.y + 2))
        else:
            note_text = notes.get(pa, "")
            resolved = notes_resolved.get(pa, False)
            if note_text:
                color = DIM if resolved else ACCENT
                prefix = "\u2713" if resolved else "\u270e"
                txt = font_body.render(f"{prefix}  {note_text}", True, color)
                screen.blit(txt, (note_rect.x + 4, note_rect.y + 2))
                if resolved:
                    pygame.draw.line(
                        screen,
                        DIM,
                        (note_rect.x + 4, note_rect.y + 13),
                        (note_rect.x + 4 + txt.get_width(), note_rect.y + 13),
                        1,
                    )
            else:
                placeholder = font_body.render("\u270e  (click to add note)", True, (90, 90, 100))
                screen.blit(placeholder, (note_rect.x + 4, note_rect.y + 2))

        offset_str = f" [from {trim_start:.2f}s]" if trim_start > 0 else ""
        if player._scrub:
            phase_label = f"scrubbing from {trim_start:.1f}s — listen for voice onset"
        else:
            phase_label = {
                "HEAD": f"playing head  [0 → {PREVIEW_DURATION:.0f}s]",
                "GAP": "head done — loading tail...",
                "TAIL": f"playing tail  [{PREVIEW_DURATION:.0f}s from end]",
                "DONE": "playback done — verdict?",
                "IDLE": "",
            }.get(player.state, "")
        phase_color = ACCENT if player.state in ("HEAD", "TAIL") else DIM
        phase = font_h2.render(phase_label, True, phase_color)
        screen.blit(phase, (detail_x, 160))

        dur = item["duration"]
        pos = player.position()
        if dur > 0 and pos is not None and pos > dur:
            pos = dur

        draw_seek_bar(screen, seek_rect, dur, pos, font_small, trim_start=trim_start)

        # Trim status line
        if trim_start > 0:
            new_dur = dur - trim_start
            trim_msg = f"pending trim: -{trim_start:.2f}s start  →  new dur {new_dur:.2f}s"
            screen.blit(font_small.render(trim_msg, True, TRIM_OVERLAY), (detail_x, 268))

        if edit_mode:
            hint = font_body.render("Enter save   Esc cancel", True, ACCENT)
        else:
            hint_lines = [
                "P pass   F fail   R replay   E edit note   ↑↓ navigate   Q quit",
                "Trim:  drag seek bar  or  [/] adjust   T apply   Z reset   (Shift = fine 0.01s)",
            ]
            screen.blit(font_body.render(hint_lines[0], True, DIM), (detail_x, WINDOW_H - 148))
            screen.blit(font_body.render(hint_lines[1], True, DIM), (detail_x, WINDOW_H - 124))

        draw_button(screen, pass_rect, "PASS  (P)", PASS_COLOR, font_btn, pass_rect.collidepoint(mouse))
        draw_button(screen, fail_rect, "FAIL  (F)", FAIL_COLOR, font_btn, fail_rect.collidepoint(mouse))
        draw_button(screen, replay_rect, "REPLAY  (R)", REPLAY_COLOR, font_btn, replay_rect.collidepoint(mouse))

        pygame.display.flip()
        clock.tick(60)

    player.stop()
    pygame.quit()

    print()
    print(f"Reviewed: {len(verdicts)} / {len(items)}")
    passed = [s for s, v in verdicts.items() if v == "PASS"]
    failed = [s for s, v in verdicts.items() if v == "FAIL"]
    print(f"  PASS: {len(passed)}")
    print(f"  FAIL: {len(failed)}")
    if failed:
        print("\nFailed:")
        for pa_val in failed:
            print(f"  - {pa_val}")
    if len(verdicts) < len(items):
        skipped = [it["pa"] for it in items if it["pa"] not in verdicts]
        print(f"\nNot reviewed: {len(skipped)}  ({', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''})")

    prior_by_pa: dict[str, dict] = {}
    if out_path.exists():
        try:
            prior = json.loads(out_path.read_text(encoding="utf-8"))
            prior_by_pa = {it["pa"]: it for it in prior.get("items", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    full_items = []
    seen_full: set[str] = set()
    for _p, stops in order_by_reference_count(loaded, ("pa", "pa_at_station")):
        for stop in stops:
            for key in ("pa", "pa_at_station"):
                for pa_val in stop.get(key, []):
                    if pa_val in seen_full:
                        continue  # pooled: one entry per mp3, not per referring diagram
                    seen_full.add(pa_val)
                    full_items.append({"stop": stop["name"], "pa": pa_val})

    merged_items = []
    for fi in full_items:
        pa_val = fi["pa"]
        if pa_val in verdicts:
            verdict = verdicts[pa_val]
        elif pa_val in prior_by_pa:
            verdict = prior_by_pa[pa_val].get("verdict", "NOT_REVIEWED")
        else:
            verdict = "NOT_REVIEWED"
        note = notes.get(pa_val, prior_by_pa.get(pa_val, {}).get("note", ""))
        resolved = notes_resolved.get(pa_val, prior_by_pa.get(pa_val, {}).get("note_resolved", False))
        item_out = {**fi, "verdict": verdict, "note": note}
        if note:
            item_out["note_resolved"] = bool(resolved)
        merged_items.append(item_out)

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

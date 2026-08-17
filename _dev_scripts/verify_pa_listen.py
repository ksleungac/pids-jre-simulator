# SPDX-License-Identifier: MIT
"""Quick by-ear PA verifier with waveform, trim and splice controls.

For each PA in a route, plays the file straight through from wherever you started it.
Click/key PASS or FAIL per station. Persists verdicts to
audio_src/<line>/pa_verify_results.json.

    uv run python _dev_scripts/verify_pa_listen.py audio/tokaido

Keys: P=Pass  F=Fail  R=Replay  E=Edit note  N=Next without verdict  Q/Esc=Quit
      ↑↓ navigate  Wheel=scroll sidebar
      [/] adjust start-trim   ,/. adjust end-trim   T apply trim   Z reset pending
      CLICK the waveform or seek bar = play from there, straight through to the end
      DRAG on the waveform then X/Del = splice that region out of the mp3
      U = undo — restore the file from the snapshot taken before this run's first edit
      (hold Shift while adjusting for fine 0.01s steps)

Click-to-play matches the STA verifier's idiom, minus everything about `sta_cut` — a
PA file has no cut moment, so the waveform draws no marker and playback simply runs
from wherever you clicked to EOF rather than cycling head→tail.

Two different edits, deliberately distinct. TRIM removes from the head or the tail;
SPLICE removes a region from the MIDDLE, which is the only way to take out something
like a live-conductor announcement sitting between two automated ones. Both are
lossless stream copies, and both are destructive — hence the snapshot behind U.

The waveform exists because no automatic threshold separates wanted speech from
unwanted speech; you have to see it and judge it. Shares `draw_wave` with the STA
verifier via verify_ui.
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
from verify_ui import draw_button, draw_wave, find_font
from verify_ui import find_ffmpeg as _find_ffmpeg
from verify_ui import splice_out

# fmt: off
# Detail-pane vertical layout. Every row DERIVES from the one above it, so growing the
# waveform can never silently land on top of something — the same rule the STA verifier
# learned the hard way.
LIST_W       = 280
LIST_TOP     = 60
ROW_H        = 26
PAD_X        = 20
ROW_PROGRESS = 36
ROW_TITLE    = 72
ROW_SUB      = 110
ROW_NOTE     = 134
NOTE_H       = 26
ROW_PHASE    = ROW_NOTE + NOTE_H + 10
PHASE_H      = 24
ROW_WAVE     = ROW_PHASE + PHASE_H + 10
WAVE_H       = 230
ROW_SEEK     = ROW_WAVE + WAVE_H + 30      # +30 leaves room for the seek bar's own top label
SEEK_H       = 18
ROW_STATUS   = ROW_SEEK + SEEK_H + 14
STATUS_LINE  = 20
ROW_HINTS    = ROW_STATUS + STATUS_LINE * 2 + 10
HINT_LINE    = 22
BTN_H        = 56
ROW_BUTTONS  = ROW_HINTS + HINT_LINE * 3 + 12
WINDOW_W     = 1180
WINDOW_H     = ROW_BUTTONS + BTN_H + 22
# fmt: on

FADE_MS = 120
TARGET_PAD = 0.08  # silence before voice onset after trim
MIN_SPLICE_S = 0.02  # below this a selection is a stray click, not an edit

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


def draw_seek_bar(
    screen: pygame.Surface,
    rect: pygame.Rect,
    duration: float,
    position: float | None,
    font: pygame.font.Font,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
) -> None:
    """`trim_start` / `trim_end` are PENDING cut amounts in seconds, measured inward
    from each end of the file. Both render as a red hatch over what would be removed."""
    if duration <= 0:
        return

    def x_for(t: float) -> int:
        return rect.x + int(rect.w * (max(0.0, min(duration, t)) / duration))

    # Base bar (unplayed gray). Playback now runs to EOF, so there is no "preview
    # region" to shade — the only meaningful tint is how far the cursor has reached.
    pygame.draw.rect(screen, UNTOUCHED_TINT, rect, border_radius=4)

    # Played portion up to cursor
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

    # Pending end-trim overlay: red hatch over [duration - trim_end, duration]
    if trim_end > 0:
        te_x = x_for(max(0.0, duration - trim_end))
        s = pygame.Surface((max(1, rect.right - te_x), rect.h), pygame.SRCALPHA)
        s.fill((*TRIM_OVERLAY, 140))
        screen.blit(s, (te_x, rect.y))
        pygame.draw.line(screen, TRIM_OVERLAY, (te_x, rect.y - 8), (te_x, rect.bottom + 8), 2)

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
    """IDLE -> PLAYING -> DONE. Plays from an offset straight through to EOF.

    There is deliberately no head/tail preview cycle. PA segments are short and the
    judgement being made is about their whole content — where the announcement starts,
    whether anything foreign is inside it — so sampling 3 seconds off each end hides
    exactly the middle you need to hear.
    """

    def __init__(self) -> None:
        self.state = "IDLE"
        self._seg_start_ms = 0
        self._from = 0.0
        self._path: Path | None = None

    def begin(self, path: Path, duration: float = 0.0, from_time: float = 0.0) -> None:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        pygame.mixer.music.load(str(path))
        try:
            pygame.mixer.music.play(start=from_time)
        except pygame.error:
            # Some builds refuse a start offset on mp3; fall back to the head so the
            # file still plays rather than silently doing nothing.
            pygame.mixer.music.play()
            from_time = 0.0
        self._path = path
        self._from = from_time
        self._seg_start_ms = pygame.time.get_ticks()
        self.state = "PLAYING"

    def position(self) -> float | None:
        if self.state == "PLAYING":
            return self._from + (pygame.time.get_ticks() - self._seg_start_ms) / 1000.0
        return None

    def tick(self) -> None:
        if self.state == "PLAYING" and not pygame.mixer.music.get_busy():
            self.state = "DONE"

    def stop(self) -> None:
        pygame.mixer.music.fadeout(FADE_MS)
        self.state = "DONE"


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
    trim_end: float = 0.0
    sel: tuple[float, float] | None = None  # waveform selection, absolute file seconds
    dragging_wave = False
    scrub_from: float | None = None  # where a click-to-play started, for the phase label
    # Session-scoped record of which slugs THIS RUN has destructively edited (trim or
    # splice). Both halves of undo key on it, never on the snapshot file existing:
    # snapshots are never deleted, so `bak.exists()` is a CROSS-session fact, and on a
    # file an earlier session edited it would restore that older generation — silently
    # discarding this session's work while printing success.
    edited_this_run: set[str] = set()

    def begin_with_trim(replay: bool = False) -> None:
        """Play the current item from its head — or from the pending head-trim on replay,
        so R lets you hear what the trim would leave."""
        nonlocal trim_start, scrub_from
        item = items[idx]
        offset = trim_start if replay else 0.0
        if not replay:
            trim_start = 0.0  # fresh navigation resets trim
        scrub_from = offset
        player.begin(item["path"], item.get("duration", 0.0), from_time=offset)

    player.begin(items[idx]["path"], items[idx].get("duration", 0.0))

    btn_w, btn_h = 150, BTN_H
    detail_x = LIST_W + 40
    detail_w = WINDOW_W - detail_x - PAD_X
    pass_rect = pygame.Rect(detail_x, ROW_BUTTONS, btn_w, btn_h)
    fail_rect = pygame.Rect(detail_x + btn_w + 20, ROW_BUTTONS, btn_w, btn_h)
    replay_rect = pygame.Rect(detail_x + 2 * (btn_w + 20), ROW_BUTTONS, btn_w, btn_h)
    note_rect = pygame.Rect(detail_x, ROW_NOTE, detail_w, NOTE_H)
    wave_rect = pygame.Rect(detail_x, ROW_WAVE, detail_w, WAVE_H)
    seek_rect = pygame.Rect(detail_x, ROW_SEEK, detail_w, SEEK_H)

    def wave_time_at_x(x: int) -> float:
        dur = items[idx].get("duration", 0.0)
        if dur <= 0 or wave_rect.w <= 0:
            return 0.0
        frac = (x - wave_rect.x) / wave_rect.w
        return max(0.0, min(dur, frac * dur))

    def seek_time_at_x(x: int) -> float:
        dur = items[idx].get("duration", 0.0)
        if dur <= 0 or seek_rect.w <= 0:
            return 0.0
        frac = (x - seek_rect.x) / seek_rect.w
        return max(0.0, min(dur, frac * dur))

    def play_from(t: float) -> None:
        """Play from `t` to EOF — the click-to-play path."""
        nonlocal scrub_from
        item = items[idx]
        scrub_from = max(0.0, t)
        player.begin(item["path"], item.get("duration", 0.0), from_time=scrub_from)

    def measure(path: Path) -> float:
        """Re-read a file's duration after an edit. The mixer holds the previous bytes,
        so unload before asking."""
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        try:
            return pygame.mixer.Sound(str(path)).get_length()
        except pygame.error:
            return 0.0

    def current_verdict_for(pa: str) -> str:
        if pa in verdicts:
            return verdicts[pa]
        return prior_verdicts.get(pa, "")

    def jump_to(new_idx: int) -> None:
        nonlocal idx, edit_mode, list_scroll, trim_start, trim_end, sel
        edit_mode = False
        trim_start = 0.0
        trim_end = 0.0
        sel = None
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

    def _snapshot_dir(src: Path) -> Path:
        return Path("audio_src") / src.parent.parent.name / "pa_wave_backup"

    def _snapshot_once(item: dict) -> None:
        """Copy the file aside before THIS RUN's first destructive edit of it.

        Overwrites whatever an earlier session left, so the snapshot always describes
        the bytes this run started from. Keyed on `edited_this_run` — see its
        declaration for why `bak.exists()` is the wrong gate.
        """
        if item["pa"] in edited_this_run:
            return
        src = Path(item["path"])
        bak_dir = _snapshot_dir(src)
        bak_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, bak_dir / src.name)
        edited_this_run.add(item["pa"])

    def apply_trim() -> bool:
        """T — remove `trim_start` from the head and `trim_end` from the tail."""
        nonlocal trim_start, trim_end
        if trim_start <= 0 and trim_end <= 0:
            return False
        item = items[idx]
        src = Path(item["path"])
        dur = item.get("duration", 0.0)
        new_dur = dur - trim_start - trim_end
        if new_dur <= 0.1:
            print("trim would leave nothing", file=sys.stderr)
            return False
        player.stop()
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        _snapshot_once(item)
        tmp = src.with_suffix(".tmp.mp3")
        cmd = [
            _find_ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{trim_start:.3f}",
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
            tmp.unlink(missing_ok=True)
            return False
        item["duration"] = measure(src) or new_dur
        print(f"trimmed {item['pa']}: -{trim_start:.3f}s head  -{trim_end:.3f}s tail  " f"new dur {item['duration']:.2f}s")
        trim_start = 0.0
        trim_end = 0.0
        begin_with_trim()
        return True

    def do_splice() -> bool:
        """X / Del — remove the selected region from the middle of the file."""
        nonlocal sel
        if sel is None:
            return False
        item = items[idx]
        src = Path(item["path"])
        dur = item.get("duration", 0.0)
        a, b = sorted(sel)
        a, b = max(0.0, a), min(dur, b)
        if b - a < MIN_SPLICE_S:
            print("selection too short to splice", file=sys.stderr)
            return False
        player.stop()
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        _snapshot_once(item)
        try:
            splice_out(src, a, b, duration=dur)
        except (subprocess.CalledProcessError, OSError, ValueError) as e:
            print(f"splice failed for {src.name}: {e}", file=sys.stderr)
            return False
        # ffmpeg's concat demuxer answers a bad path by SKIPPING that entry and still
        # exiting 0, so the resulting duration is the gate here — never the return code.
        actual = measure(src)
        expected = dur - (b - a)
        if actual <= 0 or abs(actual - expected) > 0.5:
            print(
                f"WARNING {src.name}: expected ~{expected:.2f}s after splice, measured {actual:.2f}s — check it",
                file=sys.stderr,
            )
        item["duration"] = actual or expected
        print(f"spliced {item['pa']}: removed [{a:.3f},{b:.3f}] ({(b - a) * 1000:.0f}ms)  " f"new dur {item['duration']:.2f}s")
        sel = None
        begin_with_trim()
        return True

    def undo_edit() -> bool:
        """U — restore the file from the snapshot taken before this run's first edit."""
        nonlocal sel, trim_start, trim_end
        item = items[idx]
        src = Path(item["path"])
        if item["pa"] not in edited_this_run:
            print(f"nothing edited this session for {src.name}", file=sys.stderr)
            return False
        bak = _snapshot_dir(src) / src.name
        if not bak.exists():
            print(f"snapshot missing for {src.name} — cannot restore", file=sys.stderr)
            return False
        player.stop()
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        shutil.copy2(bak, src)
        edited_this_run.discard(item["pa"])
        item["duration"] = measure(src)
        sel = None
        trim_start = 0.0
        trim_end = 0.0
        print(f"restored {item['pa']} from snapshot  dur {item['duration']:.2f}s")
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
                    elif ev.key == pygame.K_COMMA:  # ,
                        trim_end = max(0.0, trim_end - step)
                    elif ev.key == pygame.K_PERIOD:  # .
                        trim_end = min(cur_dur - 0.1, trim_end + step)
                    elif ev.key == pygame.K_t:
                        apply_trim()
                    elif ev.key in (pygame.K_x, pygame.K_DELETE):
                        do_splice()
                    elif ev.key == pygame.K_u:
                        undo_edit()
                    elif ev.key == pygame.K_z:
                        trim_start = 0.0
                        trim_end = 0.0
                        sel = None
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
                    elif wave_rect.collidepoint(ev.pos):
                        # Anchor both ends at the press. Whether this becomes a selection
                        # or a play-from depends on whether the mouse moves before release.
                        dragging_wave = True
                        t0 = wave_time_at_x(ev.pos[0])
                        sel = (t0, t0)
                    elif seek_rect.collidepoint(ev.pos):
                        play_from(seek_time_at_x(ev.pos[0]))
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
            elif ev.type == pygame.MOUSEMOTION and dragging_wave:
                if sel is not None:
                    sel = (sel[0], wave_time_at_x(ev.pos[0]))
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if dragging_wave:
                    dragging_wave = False
                    # A press that never moved is a click, and a click means "play from
                    # here" — the same thing the seek bar does. Only an actual drag
                    # leaves a region behind for X to splice out.
                    if sel is not None and abs(sel[1] - sel[0]) < MIN_SPLICE_S:
                        play_from(sel[0])
                        sel = None

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
        panel_rect = pygame.Rect(LIST_W + 20, 20, WINDOW_W - LIST_W - 40, ROW_HINTS - 34)
        pygame.draw.rect(screen, PANEL, panel_rect, border_radius=10)

        progress = font_h2.render(f"{idx + 1} / {len(items)}", True, DIM)
        screen.blit(progress, (detail_x, ROW_PROGRESS))

        head = font_h1.render(f"{item['stop']}", True, FG)
        screen.blit(head, (detail_x, ROW_TITLE))

        edited_mark = "  ·  edited this session" if item["pa"] in edited_this_run else ""
        sub = font_body.render(f"{item['pa']}.mp3   {item['duration']:.1f}s{edited_mark}", True, DIM)
        screen.blit(sub, (detail_x, ROW_SUB))

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

        from_t = scrub_from if scrub_from is not None else 0.0
        phase_label = {
            "PLAYING": f"playing from {from_t:.2f}s → end",
            "DONE": "playback done — verdict?",
            "IDLE": "",
        }.get(player.state, "")
        phase_color = ACCENT if player.state == "PLAYING" else DIM
        phase = font_h2.render(phase_label, True, phase_color)
        screen.blit(phase, (detail_x, ROW_PHASE))

        dur = item["duration"]
        pos = player.position()
        if dur > 0 and pos is not None and pos > dur:
            pos = dur

        # PA files carry no sta_cut, so the waveform draws no cut marker.
        draw_wave(screen, wave_rect, item["path"], dur, sel, None, font_small)
        draw_seek_bar(screen, seek_rect, dur, pos, font_small, trim_start=trim_start, trim_end=trim_end)

        # Pending-edit status lines
        status_y = ROW_STATUS
        if trim_start > 0 or trim_end > 0:
            new_dur = dur - trim_start - trim_end
            trim_msg = f"pending trim: -{trim_start:.2f}s head  -{trim_end:.2f}s tail  →  new dur {new_dur:.2f}s   [T apply]"
            screen.blit(font_small.render(trim_msg, True, TRIM_OVERLAY), (detail_x, status_y))
            status_y += STATUS_LINE
        if sel is not None:
            a, b = sorted(sel)
            sel_msg = f"selection: [{a:.2f}s → {b:.2f}s]  {(b - a) * 1000:.0f}ms   [X splice it out]"
            screen.blit(font_small.render(sel_msg, True, TRIM_OVERLAY), (detail_x, status_y))

        if edit_mode:
            hint = font_body.render("Enter save   Esc cancel", True, ACCENT)
            screen.blit(hint, (detail_x, ROW_HINTS))
        else:
            hint_lines = [
                "P pass   F fail   R replay   E edit note   ↑↓ navigate   Q quit",
                "Click anywhere on the waveform or seek bar to play from there",
                "Trim: [/] head  ,/. tail  T apply   ·   Drag waveform: X splice  U undo  Z clear",
            ]
            for n, line in enumerate(hint_lines):
                screen.blit(font_body.render(line, True, DIM), (detail_x, ROW_HINTS + n * HINT_LINE))

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

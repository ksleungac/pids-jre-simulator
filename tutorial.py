"""OOBE Tutorial — first-run hands-on walkthrough.

Runs after the language picker, before the setup screen on first launch
(gated by ``settings["oobe_completed"]``). Boots the real simulator on
tokaido/1865E at 国府津 (idx 13) inside a 1100×500 window; LCD lives in a
sub-surface on the left, side-panel chrome on the right (step text +
buttons + progress bar at top). Walks the user through one full press
cycle plus a click-to-jump demo.

See WIP_oobe_tutorial.md for the full design spec including step content,
state-machine details, and snapshot/restore semantics.
"""

from __future__ import annotations

import copy
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import pygame

import i18n
from app import AppState, PASimulator
from displays.train_models.e235_1000 import S_HEIGHT, S_WIDTH

# ── tuneable params (window / layout) ───────────────────────────────────────
WINDOW_W, WINDOW_H = 1100, 500
PROGRESS_H = 64                                   # top progress strip (stepper + labels)
LCD_X, LCD_Y = 0, PROGRESS_H                      # LCD sub-surface origin
LCD_W, LCD_H = S_WIDTH, S_HEIGHT                  # LCD = full simulator output
PANEL_X, PANEL_Y = LCD_W, PROGRESS_H              # side panel origin
PANEL_W, PANEL_H = WINDOW_W - LCD_W, WINDOW_H - PROGRESS_H

# Palette — mirrors picker / setup chrome (lifted slate; high luminance contrast).
BG_COLOR = (62, 68, 80)
PANEL_BG = (54, 60, 72)                           # slightly darker than window bg
TEXT_COLOR = (240, 242, 248)
DIM_COLOR = (175, 182, 195)
ACCENT_COLOR = (96, 168, 84)                      # completed phase / primary button
ACCENT_BRIGHT = (132, 212, 110)                   # current-step outer ring
BTN_BG = (88, 96, 112)
BTN_BG_DIM = (70, 76, 90)
BTN_BORDER = (118, 126, 142)
PROGRESS_BG = (44, 49, 60)
LINE_DIM = (76, 84, 100)                          # incomplete progress-line segments
DOT_FUTURE = (70, 76, 92)                         # fill for not-yet-reached phase dots


# ── fonts ───────────────────────────────────────────────────────────────────
# Tutorial chrome uses the project's bundled OTFs:
#   - HelveticaNeue: Latin + Latin Extended (covers macron ō in 'Kōzu' which
#     SysFont JhengHei tofus). Frutiger is also bundled but only as Bold —
#     using the Helvetica family keeps Roman/Medium/Bold consistent.
#   - ShinGoPr6N: kanji + kana for embedded Japanese (国府津, ただいま).
# Mixed strings render via ``_render_mixed`` which switches font per-codepoint
# and baseline-aligns the runs.

def _font_helv(size: int, *, bold: bool = False, medium: bool = False) -> pygame.font.Font:
    """Cached HelveticaNeue from the bundled OTFs. ``medium`` picks the Medium
    weight (used for body); ``bold`` picks Bold (headers, button labels);
    default is Roman (light reading weight)."""
    if bold:
        fname = "HelveticaNeue-Bold.otf"
    elif medium:
        fname = "HelveticaNeue-Medium.otf"
    else:
        fname = "HelveticaNeue-Roman.otf"
    key = ("helv", fname, size)
    cached = _FONT_CACHE.get(key)
    if cached is None:
        cached = pygame.font.Font(str(i18n.app_root() / "fonts" / fname), size)
        _FONT_CACHE[key] = cached
    return cached


def _font_shingo(size: int, *, heavy: bool = False) -> pygame.font.Font:
    """Cached ShinGoPr6N for embedded Japanese glyphs."""
    fname = "ShinGoPr6N-Heavy.otf" if heavy else "ShinGoPr6N-Medium.otf"
    key = ("shingo", fname, size)
    cached = _FONT_CACHE.get(key)
    if cached is None:
        cached = pygame.font.Font(str(i18n.app_root() / "fonts" / fname), size)
        _FONT_CACHE[key] = cached
    return cached


_FONT_CACHE: dict = {}


def _is_cjk(ch: str) -> bool:
    """True for codepoints we want rendered with ShinGoPr6N rather than the
    Latin font: CJK ideographs, kana, and CJK punctuation/symbols. Latin
    Extended (macrons etc.) returns False — those go to HelveticaNeue."""
    cp = ord(ch)
    return (
        0x3000 <= cp <= 0x303F        # CJK symbols + punctuation
        or 0x3040 <= cp <= 0x309F     # Hiragana
        or 0x30A0 <= cp <= 0x30FF     # Katakana
        or 0x4E00 <= cp <= 0x9FFF     # CJK Unified Ideographs
        or 0xFF00 <= cp <= 0xFFEF     # Halfwidth/Fullwidth Forms
    )


RUN_LATIN = "latin"
RUN_CJK = "cjk"
RUN_KEYCAP = "keycap"

import re                                                              # noqa: E402
_KEYCAP_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _split_script(text: str):
    """Inner splitter — yield (RUN_LATIN | RUN_CJK, segment) tuples by
    codepoint script. Used as a sub-step of ``_split_runs`` (which also
    handles inline keycap markup)."""
    if not text:
        return
    cur_is_cjk = _is_cjk(text[0])
    cur_seg = text[0]
    for ch in text[1:]:
        ch_cjk = _is_cjk(ch)
        if ch_cjk == cur_is_cjk:
            cur_seg += ch
        else:
            yield (RUN_CJK if cur_is_cjk else RUN_LATIN), cur_seg
            cur_is_cjk = ch_cjk
            cur_seg = ch
    yield (RUN_CJK if cur_is_cjk else RUN_LATIN), cur_seg


def _split_runs(text: str):
    """Yield ``(kind, segment)`` tuples splitting ``text`` at script
    boundaries AND ``[[Key]]`` keycap markers. ``kind`` is one of
    ``RUN_LATIN`` / ``RUN_CJK`` / ``RUN_KEYCAP``; the segment for keycap
    runs is the inner key label (without brackets).
    """
    pos = 0
    for m in _KEYCAP_RE.finditer(text):
        before = text[pos:m.start()]
        if before:
            yield from _split_script(before)
        yield RUN_KEYCAP, m.group(1)
        pos = m.end()
    tail = text[pos:]
    if tail:
        yield from _split_script(tail)


def _render_keycap(label: str, font: pygame.font.Font) -> pygame.Surface:
    """Render a small inline key-chip — sunken slate pill with a thin cool
    border. Matches the dark slate panel theme; reads like an inline-code
    <kbd> element rather than a fake-3D keycap. Sits inline with body text
    via ``_render_mixed``'s ascent alignment.
    """
    # ── tuneable params ──────────────────────────────────────
    pad_x = 8
    pad_y = 1
    cap_bg = (38, 44, 56)                    # darker than panel — sunken chip
    cap_border = (148, 158, 178)             # cool gray, low-contrast
    cap_text = (240, 244, 252)               # soft white
    border_w = 1
    radius = 5
    # ─────────────────────────────────────────────────────────

    label_img = font.render(label, True, cap_text)
    cap_w = label_img.get_width() + 2 * pad_x
    cap_h = label_img.get_height() + 2 * pad_y

    # Surface = font's line box; cap rect centered vertically inside so the
    # chip's baseline matches surrounding text glyphs.
    surface_h = max(font.get_height(), cap_h)
    surf = pygame.Surface((cap_w, surface_h), pygame.SRCALPHA)
    cap_y = (surface_h - cap_h) // 2

    cap_rect = pygame.Rect(0, cap_y, cap_w, cap_h)
    pygame.draw.rect(surf, cap_bg, cap_rect, border_radius=radius)
    pygame.draw.rect(surf, cap_border, cap_rect, width=border_w, border_radius=radius)
    surf.blit(label_img, (pad_x, cap_y + pad_y))
    return surf


def _render_mixed(text: str, latin_font: pygame.font.Font, cjk_font: pygame.font.Font, color) -> pygame.Surface:
    """Render mixed-script (and mixed-element) text. Latin/CJK runs use the
    matching font; ``[[Key]]`` runs render as small key-cap graphics. Runs
    composite horizontally, baseline-aligned via ascent.
    """
    if not text:
        return latin_font.render("", True, color)
    rendered: list[tuple[pygame.Surface, int]] = []   # (surface, ascent_for_alignment)
    for kind, seg in _split_runs(text):
        if kind == RUN_KEYCAP:
            cap = _render_keycap(seg, latin_font)
            rendered.append((cap, latin_font.get_ascent()))
        elif kind == RUN_CJK:
            rendered.append((cjk_font.render(seg, True, color), cjk_font.get_ascent()))
        else:
            rendered.append((latin_font.render(seg, True, color), latin_font.get_ascent()))
    total_w = sum(s.get_width() for s, _ in rendered)
    max_h = max(s.get_height() for s, _ in rendered)
    max_ascent = max(a for _, a in rendered)
    surf = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
    x = 0
    for s, asc in rendered:
        y = max_ascent - asc
        surf.blit(s, (x, y))
        x += s.get_width()
    return surf


def _measure_mixed(text: str, latin_font: pygame.font.Font, cjk_font: pygame.font.Font) -> int:
    """Width-only measurement for word-wrap. Computes keycap widths via
    a one-shot render (cheap; called only for word-wrap candidates)."""
    if not text:
        return 0
    total = 0
    for kind, seg in _split_runs(text):
        if kind == RUN_KEYCAP:
            total += _render_keycap(seg, latin_font).get_width()
        elif kind == RUN_CJK:
            total += cjk_font.size(seg)[0]
        else:
            total += latin_font.size(seg)[0]
    return total

# Phase progress-bar i18n keys. Labels are looked up via i18n.t() each frame
# (cheap — the SysFont surfaces are cached separately). Plain text values, no
# emoji prefix; JhengHei doesn't ship emoji glyphs and the color + highlight
# already carries the "current vs done" distinction cleanly.
PHASE_KEYS = (
    "tutorial.phase.at_station",
    "tutorial.phase.pre_departure",
    "tutorial.phase.departure_melody",
    "tutorial.phase.departed",
    "tutorial.phase.driving",
    "tutorial.phase.approaching",
    "tutorial.phase.approached",
    "tutorial.phase.click_jump",
    "tutorial.phase.recap",
)

# Action keys in `Step.allowed`. String constants (not enum) keep the descriptor
# JSON-friendly if we ever want to declare these in data.
ACT_PGDN = "pgdn"
ACT_PGUP = "pgup"
ACT_CLICK = "click"


# ─── predicates ─────────────────────────────────────────────────────────────
# Each takes (tut: Tutorial) and returns True if [Next] should enable for the
# step. Tutorial state holds `_action_in_step: bool` (reset on step entry, set
# True when the user performs the step's allowed action via the dispatcher).

def _pred_passive(tut: "Tutorial") -> bool:
    """Always-true: step is observation-only; [Next] enabled from entry."""
    return True


def _pred_audio_done_after_action(tut: "Tutorial") -> bool:
    """Step 2/3/4/6: user did the action AND audio finished playing.

    `_action_in_step` flips True when the dispatcher fires the step's action;
    `audio.is_playing()` returning False means the clip has ended (mixer's
    music channel is idle). At 15 FPS the predicate observes the transition
    within ~67ms of clip end — invisible to the user.
    """
    return tut._action_in_step and tut.sim is not None and not tut.sim.audio.is_playing()


def _pred_min_dwell(tut: "Tutorial") -> bool:
    """Passive step that requires ``step.min_dwell_s`` seconds of dwell from
    step entry before [Next] enables. Used by step 5 (Train Driving) so the
    user actually sees the countdown move; reads dwell from the descriptor
    so the constant lives in one place."""
    return (time.time() - tut.step_entered_at) >= tut._step().min_dwell_s


def _pred_step7_approached(tut: "Tutorial") -> bool:
    """Approached: sim has landed STOPPING@鴨宮 (idx 14, at_station=True).

    State-based predicate (not action-based) because the falling-into-STOPPING
    transition happens silently — `_next_in_approaching`'s pa-exhausted branch
    flips at_station=True without firing audio. So we read sim state directly.
    """
    if tut.sim is None:
        return False
    s = tut.sim.state
    return s.at_station and s.curr_stop == 14 and not tut.sim.audio.is_playing()


def _pred_step8_clicked(tut: "Tutorial") -> bool:
    """Click-to-jump: any station clicked. Action-based — _click_target() in
    the dispatcher sets _action_in_step on a successful jump_to_stop call."""
    return tut._action_in_step


# ─── per-step skip handlers (state mutation, no audio replay where possible) ─
# Skip-step "executes the step's underlying state mutation" so downstream
# steps stay coherent. Per the table in WIP_oobe_tutorial.md § "Skip step":
# steps 2/3/5/7/8 are state-only / no-op; steps 4/6 must fire audio because
# the state advance happens inside the audio-firing methods.

def _skip_noop(tut: "Tutorial") -> None:
    """No state mutation needed."""
    pass


def _skip_step2(tut: "Tutorial") -> None:
    """Force pa_at_station to exhausted sentinel so the next-step PgDn (after
    STA) advances to 鴨宮 instead of replaying pa_at_station[1]."""
    if tut.sim is None:
        return
    pa_at = tut.sim.stops[13].get("pa_at_station", [])
    if pa_at:
        tut.sim.state.cnt_pa_at_station = len(pa_at) - 1


def _skip_step4(tut: "Tutorial") -> None:
    """Advance to 鴨宮 (fires pa[0]=29 audio — unavoidable, only path that
    sets curr_stop=14 / cnt_pa=0 / departure_time correctly)."""
    if tut.sim is None:
        return
    # Make sure pa_at_station was exhausted first (in case user skipped step 2
    # WITHOUT the [Next] handler running). _advance_to_next_stop is unconditional.
    tut.sim._advance_to_next_stop()


def _skip_step6(tut: "Tutorial") -> None:
    """Fire arr PA at 鴨宮 (pa[1]=30). Audio plays."""
    if tut.sim is None:
        return
    tut.sim._next_pa()


def _skip_step7(tut: "Tutorial") -> None:
    """Final PgDn in cycle — falls into STOPPING@鴨宮 via pa-exhausted branch.
    No audio fired by this transition."""
    if tut.sim is None:
        return
    tut.sim._next_pa()


# ─── per-step entry handlers (force-set sim state on step entry) ────────────
# Run inside ``_enter_step`` BEFORE the snapshot is taken — used for steps
# whose canonical starting state must be deterministic regardless of how the
# user got here (skip-step chains can leave audio in flight, which suppresses
# the natural state advance via the audio guard in _next_pa).

def _entry_noop(tut: "Tutorial") -> None:
    pass


def _entry_step8(tut: "Tutorial") -> None:
    """Force state to STOPPING @ 鴨宮 (idx 14). Step 8 demos click-jump from
    a known platform state — without this, a user who skipped step 7 with
    audio still playing would land in step 8 with stale APPROACHING state.
    Pauses (not stops) any in-flight audio per the tutorial's state-jump
    convention: state changes silence the soundtrack but don't free it."""
    if tut.sim is None:
        return
    tut.sim.audio.pause()
    tut.sim.jump_to_stop(14)


@dataclass(frozen=True)
class Step:
    n: int                                          # 1..9
    phase_idx: Optional[int]                        # progress bar index, or None
    allowed: frozenset                              # subset of {ACT_PGDN, ACT_PGUP, ACT_CLICK}
    predicate: Callable[["Tutorial"], bool]
    next_handler: Callable[["Tutorial"], None] = _skip_noop  # fires on [Next] before advancing
    skip_handler: Callable[["Tutorial"], None] = _skip_noop  # fires on [Skip step]
    min_dwell_s: float = 0.0
    # If True, only the first action in this step is dispatched to the sim;
    # further presses are swallowed. Prevents accidentally chaining past the
    # phase (e.g. step 4 PgDn fires pa[0]=29; a second PgDn would fire pa[1]=30
    # which is step 6's job). Steps where natural cycling is desired (step 2
    # has 2 pa_at_station entries; step 3 STA can be restarted) override False.
    lock_after_first_action: bool = True
    # Optional LCD-local rectangle (x, y, w, h) to outline as a callout. None =
    # no overlay. Vibe-pass populates these — outline alone is the minimal v1
    # primitive; arrow-line + speech-bubble can land in a follow-up.
    callout_rect: Optional[tuple[int, int, int, int]] = None
    # Runs inside ``_enter_step`` after audio.pause() and BEFORE the snapshot.
    # Used for steps whose canonical starting state must be deterministic
    # regardless of how the user got here — currently step 8 (click-jump demo
    # always begins STOPPING @ Kamonomiya). Skip-step chains can leave audio
    # in flight which suppresses natural state advance via _next_pa's audio
    # guard; entry_handler is the belt-and-suspenders fix.
    entry_handler: Callable[["Tutorial"], None] = _entry_noop


STEPS: tuple[Step, ...] = (
    Step(1, 0,    frozenset(),                _pred_passive),
    # Step 2: pa_at_station has 2 entries, allow multiple PgDn so user can
    # hear both. [Next] handler exhausts pa_at_station so step 4's PgDn
    # correctly calls _advance_to_next_stop instead of replaying entry [1].
    Step(2, 1,    frozenset({ACT_PGDN}),      _pred_audio_done_after_action,
         next_handler=_skip_step2,
         skip_handler=_skip_step2,
         lock_after_first_action=False),
    # Step 3: STA can be restarted (each PgUp re-cuts from sta_cut position).
    Step(3, 2,    frozenset({ACT_PGUP}),      _pred_audio_done_after_action,
         lock_after_first_action=False),
    Step(4, 3,    frozenset({ACT_PGDN}),      _pred_audio_done_after_action,
         skip_handler=_skip_step4),
    Step(5, 4,    frozenset(),                _pred_min_dwell, min_dwell_s=5.0),
    Step(6, 5,    frozenset({ACT_PGDN}),      _pred_audio_done_after_action,
         skip_handler=_skip_step6),
    Step(7, 6,    frozenset({ACT_PGDN}),      _pred_step7_approached,
         skip_handler=_skip_step7),
    # Step 8: click-to-jump demo. Allow multiple clicks so the user can hop
    # between stations and feel out the gesture; predicate just needs ≥1 click.
    # entry_handler forces STOPPING @ 鴨宮 — the canonical starting state for
    # the demo, regardless of skip-path inconsistencies.
    Step(8, 7,    frozenset({ACT_CLICK}),     _pred_step8_clicked,
         lock_after_first_action=False,
         entry_handler=_entry_step8),
    Step(9, 8,    frozenset(),                _pred_passive),
)


class Tutorial:
    """OOBE tutorial controller. Owns the 1100×500 window + sim instance.

    Caller (main.py) invokes ``run()`` after the language picker and consumes
    the boolean return: True = tutorial completed (set ``oobe_completed`` in
    settings); False = tutorial aborted (window closed, missing assets, etc.
    — ``oobe_completed`` decision left to the caller, but the recommendation
    is to set True regardless so the user isn't re-prompted on next launch).
    """

    # Boot at 国府津 (idx 13) — the only stop that exercises every phase in
    # one cycle: pa_at_station=["27","28"] (multi at-station PA, demonstrates
    # yellow square hint), pa=["25","26"] (already-played approach), and
    # downstream 鴨宮 (idx 14, pa=["29","30"]) provides distinct dep+arr PAs.
    BOOT_STOP_IDX = 13

    # Audio files the cycle plays. If any are missing, the tutorial aborts
    # at startup and the caller sets oobe_completed=True so we don't re-prompt.
    REQUIRED_PA = ("27.mp3", "28.mp3", "29.mp3", "30.mp3")
    REQUIRED_STA = ("JT14.mp3",)
    REQUIRED_ROUTE = "route.json"

    @classmethod
    def tutorial_route_dir(cls) -> str:
        """Absolute path to the tutorial's route directory.

        Resolved through ``i18n.app_root()`` so it works in both dev (project
        root) and frozen builds (sys._MEIPASS). A relative path would fail
        if the app is launched from a non-project cwd (e.g. installer-launched
        with cwd=user home).
        """
        return str(i18n.app_root() / "audio" / "tokaido" / "1865E")

    def __init__(self, screen: pygame.Surface):
        """Initialize tutorial chrome. Caller has already created the display.

        Args:
            screen: The 1100×500 display surface (caller-managed).
        """
        self.screen = screen
        self.clock = pygame.time.Clock()

        # Step state.
        self.current_step = 1                     # 1..9 (1-indexed for human-readable)
        self.step_entered_at = time.time()
        self.state_stack: list[AppState] = []     # per-step snapshots for [Back]
        self._action_in_step: bool = False        # set by dispatcher when user fires the step's action

        # Sim — wired in step 3.
        self.sim: Optional[PASimulator] = None
        self.lcd_surface: Optional[pygame.Surface] = None

        # Hit-test rects, populated by _draw_panel() / _draw_progress_bar() each frame.
        self._btn_rects: dict[str, pygame.Rect] = {}
        # Per-phase column rects (column above each label) — clicking one jumps to
        # the corresponding step (0-indexed phase → 1-indexed step). Populated each
        # frame by _draw_progress_bar(); empty list while the bar hasn't drawn yet.
        self._phase_rects: list[pygame.Rect] = []

        self.running = True
        self.completed = False                    # True iff user reached [Done]

    # ────────────────────────────── lifecycle ────────────────────────────────

    @classmethod
    def assets_ok(cls) -> tuple[bool, str]:
        """Verify the tutorial's tokaido/1865E assets are on disk.

        Returns (ok, message). If False, caller should skip the tutorial and
        set ``oobe_completed=True`` (we don't want to re-prompt every launch
        on a no-audio install).
        """
        base = cls.tutorial_route_dir()
        route = os.path.join(base, cls.REQUIRED_ROUTE)
        if not os.path.isfile(route):
            return False, f"missing {route}"
        for f in cls.REQUIRED_PA:
            p = os.path.join(base, "pa", f)
            if not os.path.isfile(p):
                return False, f"missing {p}"
        for f in cls.REQUIRED_STA:
            p = os.path.join(base, "sta", f)
            if not os.path.isfile(p):
                return False, f"missing {p}"
        return True, ""

    def run(self) -> bool:
        """Main tutorial loop. Returns True if user completed [Done]."""
        # Asset pre-flight: missing route or mp3 → log + bail. Caller sets
        # oobe_completed=True so the user isn't re-prompted (this is a
        # no-audio-build scenario; the tutorial isn't recoverable).
        ok, msg = self.assets_ok()
        if not ok:
            print(f"[tutorial] assets unavailable, skipping: {msg}")
            return False

        # Set up the window + sub-surfaces. Caller already called set_mode at
        # 1100×500 — we just allocate the LCD sub-surface for the sim.
        self.lcd_surface = self.screen.subsurface((LCD_X, LCD_Y, LCD_W, LCD_H))

        try:
            self.sim = PASimulator(
                work_dir=self.tutorial_route_dir(),
                tutorial=True,
                target_surface=self.lcd_surface,
            )
        except Exception as e:
            print(f"[tutorial] sim boot failed, skipping: {e}")
            return False
        self.sim.jump_to_stop(self.BOOT_STOP_IDX)

        # Establish the step-1 snapshot so [Back] from step 2 restores the
        # boot state cleanly.
        self._enter_step(1)

        try:
            while self.running:
                self.clock.tick(15)
                self._tick_sim()

                # Draw chrome on top of sim render.
                self._draw_progress_bar()
                self._draw_panel()
                pygame.display.flip()

                self._handle_events()
        finally:
            self._teardown_sim()

        return self.completed

    def _handle_events(self) -> None:
        """Drain pygame events and dispatch via the action lock-down filter.

        Side-panel button clicks always pass; LCD-area mouse clicks gate on
        ``ACT_CLICK in step.allowed``; ``K_PAGEDOWN`` / ``K_PAGEUP`` gate on
        ``ACT_PGDN`` / ``ACT_PGUP`` respectively. ``K_END`` always pauses
        audio (safety/comfort). Everything else is swallowed.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # TODO(vibe-pass): replace with confirm-quit modal.
                    self.running = False
                elif event.key == pygame.K_PAGEDOWN:
                    self._dispatch_action(ACT_PGDN)
                elif event.key == pygame.K_PAGEUP:
                    self._dispatch_action(ACT_PGUP)
                elif event.key == pygame.K_END and self.sim is not None:
                    self.sim.audio.pause()
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Progress-bar phase clicks jump to that step (skip-forward via
                # skip handlers, or restore-back via snapshot).
                if self._handle_progress_click(event.pos):
                    continue
                # Side panel buttons (Back/Next/Skip) take priority — they sit
                # entirely inside the panel rect which doesn't overlap the LCD.
                if self._handle_panel_click(event.pos):
                    continue
                # Click in LCD area — only step 8 forwards to the sim's jumper.
                self._dispatch_action(ACT_CLICK, click_pos=event.pos)

    def _dispatch_action(self, action: str, *, click_pos: Optional[tuple[int, int]] = None) -> None:
        """Forward an action to the sim if the current step allows it.

        Maintains ``_action_in_step`` (set on first successful dispatch — used
        by predicates) and respects ``lock_after_first_action`` so chaining
        past the step's phase boundary is impossible (e.g. spamming PgDn in
        step 4 won't fire 鴨宮's pa[1] which is step 6's job).
        """
        step = self._step()
        if action not in step.allowed:
            return
        if step.lock_after_first_action and self._action_in_step:
            return
        if self.sim is None:
            return

        # Step 2 cap: once every pa_at_station entry has played, a further
        # PgDn would call _next_pa's pa-exhausted branch and advance to the
        # next stop — that's step 4's job, not step 2's. Swallow extra
        # presses; user must click [Next] to proceed.
        if self.current_step == 2 and action == ACT_PGDN:
            pa_at = self.sim.stops[self.sim.state.curr_stop].get("pa_at_station", [])
            if pa_at and self.sim.state.cnt_pa_at_station >= len(pa_at) - 1:
                return

        if action == ACT_PGDN:
            self.sim._next_pa()
        elif action == ACT_PGUP:
            self.sim._next_sta()
        elif action == ACT_CLICK:
            if click_pos is None:
                return
            target = self._lcd_click_target(click_pos)
            if target is None:
                return  # click outside any clickable cell — no action recorded
            # State-jump convention: pause audio + reset state cleanly. The
            # pause silences any in-flight PA before the new platform state.
            self.sim.audio.pause()
            self.sim.jump_to_stop(target)
        else:
            return

        self._action_in_step = True

    def _lcd_click_target(self, pos: tuple[int, int]) -> Optional[int]:
        """Translate a window-coords click into a sim-stop index, or None.

        Subtracts the LCD sub-surface origin to get LCD-local coords, then
        delegates to ``sim._click_target`` (which layers the past-dest filter
        on top of the renderer's ``hit_test``).
        """
        if self.sim is None:
            return None
        x, y = pos
        lcd_x = x - LCD_X
        lcd_y = y - LCD_Y
        if lcd_x < 0 or lcd_y < 0 or lcd_x >= LCD_W or lcd_y >= LCD_H:
            return None
        return self.sim._click_target(lcd_x, lcd_y)

    def _handle_progress_click(self, pos: tuple[int, int]) -> bool:
        """Progress-bar phase dispatch. Each phase column is a hit target for
        jumping to its step. Returns True if a phase was hit.

        Backward jumps restore the snapshot taken on entry of the target step
        (same mechanic as [Back] but multi-step). Forward jumps run the
        intervening skip handlers via ``_skip_step`` so downstream sim state
        stays coherent (e.g. step 4's _advance_to_next_stop has to fire to
        land at 鴨宮 with cnt_pa=0).
        """
        for i, rect in enumerate(self._phase_rects):
            if rect.collidepoint(pos):
                self._jump_to_step(i + 1)               # phase 0 → step 1
                return True
        return False

    def _jump_to_step(self, target: int) -> None:
        """Multi-step jump in either direction. No-op if target == current."""
        if target < 1 or target > len(STEPS) or target == self.current_step:
            return
        if target < self.current_step:
            # Backward: restore the snapshot that was captured on entry to the
            # target step. Mirrors _back_step's restore path.
            target_idx = target - 1
            if self.sim is not None and 0 <= target_idx < len(self.state_stack):
                self.sim.restore_state(self.state_stack[target_idx])
            self.current_step = target
            self.step_entered_at = time.time()
            self._action_in_step = False
            return
        # Forward: skip through intervening steps. _skip_step calls skip_handler
        # then _advance_step (which calls next_handler + _enter_step). Running
        # mode flag halts the loop if we hit the wrap-up step's [Done] sentinel.
        while self.running and self.current_step < target:
            self._skip_step()

    def _handle_panel_click(self, pos: tuple[int, int]) -> bool:
        """Side-panel button dispatch. Returns True if a button was hit
        (caller stops further processing for the click)."""
        if self._btn_rects.get("next") and self._btn_rects["next"].collidepoint(pos):
            if self.predicate_satisfied:
                self._advance_step()
            return True
        if self._btn_rects.get("back") and self._btn_rects["back"].collidepoint(pos):
            if self.current_step > 1:
                self._back_step()
            return True
        if self._btn_rects.get("skip_step") and self._btn_rects["skip_step"].collidepoint(pos):
            self._skip_step()
            return True
        if self._btn_rects.get("skip_tutorial") and self._btn_rects["skip_tutorial"].collidepoint(pos):
            self._skip_tutorial()
            return True
        return False

    def _tick_sim(self) -> None:
        """Per-frame sim render. Order matches sim.run(): update_skip_progress
        first (mutates state.skip_progress that lower.draw reads via cursor_pos),
        then upper.update/draw, then lower.draw."""
        ts = time.time()
        # Window-bg fill happens once per frame here (covers progress bar +
        # any chrome bg outside the sim's LCD region).
        self.screen.fill(BG_COLOR)
        self.sim.state.update_skip_progress(ts)
        self.sim.upper.update(ts)
        self.sim.upper.draw(time.strftime("%H:%M", time.localtime(ts)))
        self.sim.lower.draw(ts)
        self._draw_callout()

    def _draw_callout(self) -> None:
        """Outline the current step's callout region on the LCD (if any).

        Uses the static ``Step.callout_rect`` descriptor field. Step-specific
        dynamic rects (e.g. the step-8 route-bar highlight, deferred pending
        a clearer design) layer on top here when re-introduced.
        """
        rect = self._step().callout_rect
        if rect is None:
            return
        # ── tuneable params ──────────────────────────────────────
        outline_w = 3
        # ─────────────────────────────────────────────────────────
        x, y, w, h = rect
        callout_rect = pygame.Rect(LCD_X + x, LCD_Y + y, w, h)
        pygame.draw.rect(self.screen, ACCENT_COLOR, callout_rect, width=outline_w, border_radius=4)

    def _teardown_sim(self) -> None:
        """Tutorial-only teardown. Does NOT call PASimulator.cleanup() — that
        method calls pygame.quit() (full subsystem teardown), which would
        invalidate the mixer + display the setup screen + main app are about
        to inherit. We only stop in-flight audio; the mixer + display stay
        alive. AudioPlayer.__del__ no longer fires mixer.quit() (deleted in
        the same PR), so dropping the sim ref here is safe at GC time."""
        if self.sim is not None:
            try:
                self.sim.audio.stop()
            except Exception:
                pass
        # Drop reference; Python GC will collect when the Tutorial instance dies.
        self.sim = None

    # ─────────────────────────────── drawing ─────────────────────────────────

    def _draw_progress_bar(self) -> None:
        """Render the 7-phase stepper at the top of the window.

        Numbered circles connected by a horizontal line, labels under each
        circle. Color states: completed = filled accent, current = bright
        accent + outer ring, future = dim filled. Whole column above each
        label is a click target (populates ``self._phase_rects``).
        """
        # ── tuneable params ──────────────────────────────────────
        bar_y = 0
        bar_h = PROGRESS_H
        side_pad = 26
        circle_r = 11                                  # main dot radius
        ring_r = 16                                    # outer ring on current step
        line_thickness = 3
        circle_y = bar_y + 18
        label_top = circle_y + circle_r + 9            # gap below circle
        label_size = 11
        num_size = 11                                  # number rendered inside circle
        # ─────────────────────────────────────────────────────────

        pygame.draw.rect(self.screen, PROGRESS_BG, pygame.Rect(0, bar_y, WINDOW_W, bar_h))

        active_phase = self._active_phase_idx()
        cells_total = len(PHASE_KEYS)

        # Even spacing of circle centers across available width.
        avail_w = WINDOW_W - 2 * side_pad
        spacing = avail_w // (cells_total - 1)
        centers_x = [side_pad + i * spacing for i in range(cells_total)]

        # Connecting line: dim base across full width, accent overlay across
        # completed segments (segment 0..k connects circle 0..circle k).
        pygame.draw.line(self.screen, LINE_DIM,
                         (centers_x[0], circle_y), (centers_x[-1], circle_y), line_thickness)
        if active_phase > 0:
            pygame.draw.line(self.screen, ACCENT_COLOR,
                             (centers_x[0], circle_y),
                             (centers_x[active_phase], circle_y), line_thickness)

        # Circles + labels + click rects. Helvetica throughout — phase labels
        # and step numbers are pure Latin.
        label_font = _font_helv(label_size, medium=True)
        num_font = _font_helv(num_size, bold=True)
        self._phase_rects = []

        for i, (cx, key) in enumerate(zip(centers_x, PHASE_KEYS)):
            is_current = (i == active_phase)
            is_done = (i < active_phase)

            if is_current:
                pygame.draw.circle(self.screen, ACCENT_BRIGHT, (cx, circle_y), ring_r)
                pygame.draw.circle(self.screen, PROGRESS_BG, (cx, circle_y), ring_r - 3)
                fill = ACCENT_COLOR
                num_color = TEXT_COLOR
                label_color = TEXT_COLOR
            elif is_done:
                fill = ACCENT_COLOR
                num_color = TEXT_COLOR
                label_color = TEXT_COLOR
            else:
                fill = DOT_FUTURE
                num_color = DIM_COLOR
                label_color = DIM_COLOR

            pygame.draw.circle(self.screen, fill, (cx, circle_y), circle_r)
            num_img = num_font.render(str(i + 1), True, num_color)
            self.screen.blit(num_img,
                             (cx - num_img.get_width() // 2,
                              circle_y - num_img.get_height() // 2))

            label_img = label_font.render(i18n.t(key), True, label_color)
            label_x = cx - label_img.get_width() // 2
            self.screen.blit(label_img, (label_x, label_top))

            # Click-target column: full bar height, centered on this phase. Width
            # is half the spacing on either side (so adjacent columns abut without
            # overlap). Edge phases get clipped to bar bounds.
            col_left = max(0, cx - spacing // 2)
            col_right = min(WINDOW_W, cx + spacing // 2)
            self._phase_rects.append(
                pygame.Rect(col_left, bar_y, col_right - col_left, bar_h)
            )

    def _draw_panel(self) -> None:
        """Render the side panel: step header, body, buttons."""
        # ── tuneable params ──────────────────────────────────────
        panel_pad = 16
        header_size = 22
        subtitle_size = 11
        body_size = 15
        subtitle_gap = 2                          # gap between header + subtitle
        body_gap = 14                             # vertical gap between subtitle + body
        body_line_gap = 4
        btn_h = 38
        btn_gap = 8
        primary_btn_h = 46
        # ─────────────────────────────────────────────────────────

        panel_rect = pygame.Rect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)

        # Header — phase name (large, bold). Helvetica Bold for the Latin
        # labels; phase names are EN-only so no CJK fallback needed yet.
        header_font = _font_helv(header_size, bold=True)
        header = self._step_header_text()
        header_img = header_font.render(header, True, TEXT_COLOR)
        self.screen.blit(header_img, (PANEL_X + panel_pad, PANEL_Y + panel_pad))

        # Subtitle — small step counter "Step N of 9" under the phase name.
        subtitle_font = _font_helv(subtitle_size, medium=True)
        subtitle = self._step_subtitle_text()
        subtitle_img = subtitle_font.render(subtitle, True, DIM_COLOR)
        subtitle_y = PANEL_Y + panel_pad + header_img.get_height() + subtitle_gap
        self.screen.blit(subtitle_img, (PANEL_X + panel_pad, subtitle_y))

        # Body — multi-line wrapped, mixed-script (Helvetica for Latin incl.
        # macrons, ShinGoPr6N for embedded kanji/kana).
        body_latin = _font_helv(body_size, medium=True)
        body_cjk = _font_shingo(body_size)
        body = self._step_body_text()
        body_top = subtitle_y + subtitle_img.get_height() + body_gap
        body_bottom = self._draw_wrapped_text(
            body, body_latin, body_cjk, TEXT_COLOR,
            x=PANEL_X + panel_pad,
            y=body_top,
            max_w=PANEL_W - 2 * panel_pad,
            line_gap=body_line_gap,
        )

        # Step 8 has a mock station-name card under the body so "click a
        # station" isn't abstract — the user can see the shape they're looking
        # for on the route map. Skipped post-click (the body already names the
        # station they landed on).
        next_y = body_bottom
        if self.current_step == 8 and not self._action_in_step:
            next_y = self._draw_station_illustration(
                x=PANEL_X + panel_pad,
                y=body_bottom + 10,
                w=PANEL_W - 2 * panel_pad,
            )

        # Action prompt — the 'do this' instruction split out from the body so
        # the user doesn't have to parse explanatory prose to find the next
        # action. Renders in ACCENT_BRIGHT with a small left-side stripe so it
        # reads as a callout.
        action_text = self._step_action_text()
        if action_text:
            action_top = next_y + 14
            stripe_w = 3
            stripe_pad = 8
            action_x = PANEL_X + panel_pad + stripe_w + stripe_pad
            action_max_w = PANEL_W - 2 * panel_pad - stripe_w - stripe_pad
            action_latin = _font_helv(body_size, medium=True)
            action_cjk = _font_shingo(body_size)
            action_bottom = self._draw_wrapped_text(
                action_text, action_latin, action_cjk, ACCENT_BRIGHT,
                x=action_x,
                y=action_top,
                max_w=action_max_w,
                line_gap=body_line_gap,
            )
            # Vertical accent stripe to the left of the action text — visual
            # separator from explanatory body without a horizontal divider.
            pygame.draw.rect(
                self.screen, ACCENT_BRIGHT,
                pygame.Rect(PANEL_X + panel_pad, action_top, stripe_w, action_bottom - action_top),
                border_radius=2,
            )

        # Buttons — stacked at bottom of panel. Helvetica Bold for the labels.
        btn_font = _font_helv(15, bold=True)
        btn_w = PANEL_W - 2 * panel_pad

        # Layout from bottom up. On the wrap-up step the skip-step / skip-tutorial
        # rows aren't rendered, so the primary row drops to the bottom — this gives
        # the recap body the full panel-height for its cheat-sheet.
        bottom_y = PANEL_Y + PANEL_H - panel_pad
        if self.current_step == len(STEPS):
            primary_row_y = bottom_y - primary_btn_h
            skip_step_y = skip_tutorial_y = 0      # unused; cleared below
        else:
            skip_tutorial_y = bottom_y - btn_h
            skip_step_y = skip_tutorial_y - btn_gap - btn_h
            primary_row_y = skip_step_y - btn_gap - primary_btn_h

        self._btn_rects.clear()

        # Primary row: [Back] [Next ▶] (next is highlighted)
        half_w = (btn_w - btn_gap) // 2
        back_rect = pygame.Rect(PANEL_X + panel_pad, primary_row_y, half_w, primary_btn_h)
        next_rect = pygame.Rect(back_rect.right + btn_gap, primary_row_y, half_w, primary_btn_h)
        self._btn_rects["back"] = back_rect
        self._btn_rects["next"] = next_rect
        self._draw_button(back_rect, i18n.t("tutorial.btn.back"), btn_font,
                          enabled=self.current_step > 1, primary=False)
        # On the wrap-up step (last), [Next] becomes [Done].
        next_label = i18n.t("tutorial.btn.done") if self.current_step == len(STEPS) else i18n.t("tutorial.btn.next")
        self._draw_button(next_rect, next_label, btn_font,
                          enabled=self.predicate_satisfied, primary=True)

        # Skip-step / Skip-tutorial only render on non-wrap-up steps. On step 9
        # they'd be no-ops (skip-step from the last step is functionally [Done];
        # skip-tutorial from the wrap-up is a self-loop). Keeping them hidden
        # avoids the UX confusion of clickable-but-effectless buttons.
        if self.current_step != len(STEPS):
            skip_step_rect = pygame.Rect(PANEL_X + panel_pad, skip_step_y, btn_w, btn_h)
            skip_tut_rect = pygame.Rect(PANEL_X + panel_pad, skip_tutorial_y, btn_w, btn_h)
            self._btn_rects["skip_step"] = skip_step_rect
            self._btn_rects["skip_tutorial"] = skip_tut_rect
            self._draw_button(skip_step_rect, i18n.t("tutorial.btn.skip_step"), btn_font,
                              enabled=True, primary=False)
            self._draw_button(skip_tut_rect, i18n.t("tutorial.btn.skip_tutorial"), btn_font,
                              enabled=True, primary=False)

    def _draw_station_illustration(self, *, x: int, y: int, w: int) -> int:
        """Draw a mock station-name card for step 8 (click-to-jump).

        Conveys 'this is the kind of thing you click on the route map' without
        re-rendering the LCD. Outlined card with the station's kanji + romaji
        names, mirroring how stations appear on the lower-LCD route bar.
        Returns the y-coord after the card's bottom edge.
        """
        # ── tuneable params ──────────────────────────────────────
        card_h = 76
        bg = (44, 50, 62)
        label_size = 11
        name_size = 22
        romaji_size = 13
        label_inset_x = 10
        label_inset_y = 6
        name_top_offset = 28
        flash_period_s = 1.2                      # full bright→dim→bright cycle
        flash_min = ACCENT_COLOR                  # dim end of pulse
        flash_max = ACCENT_BRIGHT                 # bright end
        flash_border_w = 3
        # ─────────────────────────────────────────────────────────

        # Border pulses to draw the eye — sine in [0,1], lerps min↔max. Stops
        # rendering once the user has clicked (handled by the caller's gate),
        # so the cue serves its purpose then quietly disappears.
        import math
        phase = (time.time() % flash_period_s) / flash_period_s
        t = (math.sin(phase * 2 * math.pi - math.pi / 2) + 1) / 2  # 0..1, starts at 0
        border_color = tuple(
            int(flash_min[i] + (flash_max[i] - flash_min[i]) * t) for i in range(3)
        )

        card_rect = pygame.Rect(x, y, w, card_h)
        pygame.draw.rect(self.screen, bg, card_rect, border_radius=8)
        pygame.draw.rect(self.screen, border_color, card_rect, width=flash_border_w, border_radius=8)

        # "Example" label tucked into the top-left.
        label_font = _font_helv(label_size, bold=True)
        label_img = label_font.render("Example", True, DIM_COLOR)
        self.screen.blit(label_img, (x + label_inset_x, y + label_inset_y))

        # Station name (kanji + romaji) centered horizontally. Kanji renders
        # via ShinGoPr6N (matches LCD), romaji via HelveticaNeue (which has
        # macrons; the SysFont path tofu'd the ō in 'Kōzu').
        name_font = _font_shingo(name_size, heavy=True)
        romaji_font = _font_helv(romaji_size, medium=True)
        name_img = name_font.render("国府津", True, TEXT_COLOR)
        romaji_img = romaji_font.render("Kōzu", True, DIM_COLOR)
        cx = card_rect.centerx
        name_y = y + name_top_offset
        romaji_y = name_y + name_img.get_height() + 1
        self.screen.blit(name_img, (cx - name_img.get_width() // 2, name_y))
        self.screen.blit(romaji_img, (cx - romaji_img.get_width() // 2, romaji_y))

        return y + card_h

    def _draw_button(self, rect: pygame.Rect, label: str, font: pygame.font.Font,
                     *, enabled: bool, primary: bool) -> None:
        if not enabled:
            bg = BTN_BG_DIM
            fg = DIM_COLOR
        elif primary:
            bg = ACCENT_COLOR
            fg = TEXT_COLOR
        else:
            bg = BTN_BG
            fg = TEXT_COLOR
        pygame.draw.rect(self.screen, bg, rect, border_radius=6)
        pygame.draw.rect(self.screen, BTN_BORDER, rect, width=1, border_radius=6)
        img = font.render(label, True, fg)
        self.screen.blit(
            img,
            (rect.centerx - img.get_width() // 2,
             rect.centery - img.get_height() // 2),
        )

    def _draw_wrapped_text(self, text: str,
                           latin_font: pygame.font.Font, cjk_font: pygame.font.Font,
                           color, *, x: int, y: int, max_w: int, line_gap: int) -> int:
        """Word-wrap `text` into max_w with mixed-script rendering. Latin
        codepoints render via ``latin_font``, CJK via ``cjk_font`` (per-run
        switch). Preserves explicit ``\\n`` newlines as forced line breaks
        (so cheat-sheet bodies render line-per-control). Returns the y after
        the last line.
        """
        line_h = max(latin_font.get_height(), cjk_font.get_height())
        cy = y
        for paragraph in text.split("\n"):
            if not paragraph:
                cy += line_h + line_gap
                continue
            words = paragraph.split()
            line = ""
            for word in words:
                trial = (line + " " + word).strip() if line else word
                if _measure_mixed(trial, latin_font, cjk_font) <= max_w:
                    line = trial
                    continue
                if line:
                    self.screen.blit(_render_mixed(line, latin_font, cjk_font, color), (x, cy))
                    cy += line_h + line_gap
                line = word
            if line:
                self.screen.blit(_render_mixed(line, latin_font, cjk_font, color), (x, cy))
                cy += line_h + line_gap
        return cy

    # ─────────────────────── step descriptor accessors ───────────────────────

    def _step(self) -> Step:
        """Current step descriptor."""
        return STEPS[self.current_step - 1]

    def _active_phase_idx(self) -> int:
        """Progress-bar phase index for the current step, or -1 (steps 8/9)."""
        idx = self._step().phase_idx
        return -1 if idx is None else idx

    def _step_header_text(self) -> str:
        """Header line — phase name (matches the progress-bar label) so the
        panel and stepper agree on the step's identity. Step counter renders
        as a smaller subtitle (see ``_step_subtitle_text``)."""
        idx = self._step().phase_idx
        if idx is not None and 0 <= idx < len(PHASE_KEYS):
            return i18n.t(PHASE_KEYS[idx])
        return i18n.t("tutorial.step_header", n=self.current_step, total=len(STEPS))

    def _step_subtitle_text(self) -> str:
        """Small subtitle line under the header — 'Step N of 9'."""
        return i18n.t("tutorial.step_header", n=self.current_step, total=len(STEPS))

    def _step_body_text(self) -> str:
        # Step 8 has a dynamic body — after the user clicks a station, swap to
        # the post-click message with the landed-on station name interpolated.
        if self.current_step == 8 and self._action_in_step and self.sim is not None:
            stop = self.sim.stops[self.sim.state.curr_stop]
            kanji = stop.get("name", "")
            english = stop.get("english", "")
            display = f"{kanji} ({english})" if english and english != kanji else kanji
            return i18n.t("tutorial.step.8.body_after_click", station=display)
        return i18n.t(f"tutorial.step.{self.current_step}.body")

    def _step_action_text(self) -> str:
        """Action prompt for the current step — the 'do this' line, rendered
        below the explanatory body in an accent color so the user can see at
        a glance what to do without parsing prose. Step 8 has post-click variant
        ('click another or press Next') matching the post-click body."""
        if self.current_step == 8 and self._action_in_step:
            return i18n.t("tutorial.step.8.action_after_click")
        return i18n.t(f"tutorial.step.{self.current_step}.action")

    @property
    def predicate_satisfied(self) -> bool:
        """Live evaluation of the current step's predicate — read each frame
        by the panel renderer to gate [Next]'s enabled state."""
        try:
            return self._step().predicate(self)
        except Exception:
            return False

    # ─────────────────────────── step transitions ───────────────────────────

    def _enter_step(self, n: int) -> None:
        """Forward entry for a new step (or re-entry via Skip / forward after
        Back).

        State-jump convention: ``audio.pause()`` first to silence in-flight
        audio (also clears the audio guard inside ``_next_pa``), then run the
        target step's ``entry_handler`` to force any required canonical state,
        THEN snapshot for future ``[Back]`` restores. Order matters — the
        snapshot must capture the post-entry-handler state, not the inbound
        state.
        """
        target = STEPS[n - 1]
        if self.sim is not None:
            self.sim.audio.pause()
            target.entry_handler(self)
            snap = self.sim.snapshot_state()
            idx = n - 1
            if idx < len(self.state_stack):
                self.state_stack[idx] = snap
            else:
                # Append, padding with the current snap to fill any gap (shouldn't
                # happen in practice — we only ever advance by 1 — but defensive).
                while len(self.state_stack) < idx:
                    self.state_stack.append(snap)
                self.state_stack.append(snap)
        self.current_step = n
        self.step_entered_at = time.time()
        self._action_in_step = False

    def _advance_step(self) -> None:
        """Advance to the next step. Runs the current step's next_handler
        first (state-coherence side effects, e.g. step 2's pa_at_station
        exhaustion). [Done] on step 9."""
        self._step().next_handler(self)
        if self.current_step >= len(STEPS):
            self.completed = True
            self.running = False
            return
        self._enter_step(self.current_step + 1)

    def _back_step(self) -> None:
        """Go to previous step, restoring sim state to the snapshot taken
        when that step was originally entered."""
        if self.current_step <= 1:
            return
        target = self.current_step - 1
        target_idx = target - 1
        if self.sim is not None and 0 <= target_idx < len(self.state_stack):
            self.sim.restore_state(self.state_stack[target_idx])
        self.current_step = target
        self.step_entered_at = time.time()
        self._action_in_step = False

    def _skip_step(self) -> None:
        """Apply the step's skip handler (state mutation) + advance.

        Pauses audio first per the state-jump convention. This also clears
        ``_next_pa``'s audio guard so skip handlers that fire ``_next_pa``
        (steps 6/7) advance state cleanly even when the previous step's
        audio is still playing.
        """
        if self.sim is not None:
            self.sim.audio.pause()
        self._step().skip_handler(self)
        self._advance_step()

    def _skip_tutorial(self) -> None:
        """Jump to wrap-up panel (no state coherence guarantees — user opted
        out of the cycle entirely)."""
        self._enter_step(len(STEPS))

"""OOBE Tutorial — first-run hands-on walkthrough.

Runs after the language picker, before the setup screen on first launch
(gated by ``settings["oobe_completed"]``). Boots the real simulator on
tokaido/1865E at 国府津 (idx 13) inside a 1100×500 window; LCD lives in a
sub-surface on the left, side-panel chrome on the right (step text +
buttons + progress bar at top). Walks the user through one full press
cycle plus a click-to-jump demo. Step copy lives in
``data/translations_app.json`` under ``tutorial.*`` keys.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
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


def _font_cjk(size: int, *, heavy: bool = False) -> pygame.font.Font:
    """Language-aware CJK font for chrome rendering.

    zh_CN routes through Microsoft YaHei (a SysFont) — ShinGoPr6N is built
    from Japanese JIS and tofus Simplified-only glyphs (开, 进, 这, etc.)
    that aren't in JIS. Other languages keep ShinGoPr6N: Japanese forms read
    correctly for embedded JP kanji on the LCD line (国府津, 鴨宮), and
    Traditional Chinese (zh-HK) chars overlap with JIS so render fine."""
    if i18n.current_lang() == "zh_CN":
        return i18n.font_named("microsoftyahei", size, bold=heavy)
    return _font_shingo(size, heavy=heavy)


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
RUN_KEYCAP = "keycap"   # `[[X]]` — sunken slate <kbd> chip; physical keyboard key
RUN_BUTTON = "button"   # `[[btn:X]]` — green chip matching the panel's primary button

import re                                                              # noqa: E402
# Capture optional `btn:` prefix to discriminate buttons from keys; group 1 is
# the prefix (None for keys), group 2 is the inline label.
_KEYCAP_RE = re.compile(r"\[\[(?:(btn):)?([^\]]+)\]\]")


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


def _wrap_atoms(text: str):
    """Yield ``(atom, is_space)`` tuples sized for line-wrap granularity.

    - Each CJK codepoint is its own atom (lines may break between any two
      adjacent CJK chars — pure-CJK paragraphs have no spaces, so without
      this they'd never wrap).
    - Each ``[[...]]`` markup block is one atomic atom (don't break in
      the middle of a chip).
    - Each Latin run between spaces / CJK / markup is one atom.
    - Spaces yielded separately so the wrap loop can drop trailing ones at
      line breaks instead of treating them as content.
    """
    pos = 0
    n = len(text)
    while pos < n:
        ch = text[pos]
        if ch == ' ':
            yield ' ', True
            pos += 1
            continue
        if text[pos:pos+2] == '[[':
            end = text.find(']]', pos + 2)
            if end == -1:                      # unclosed markup — treat rest as one atom
                yield text[pos:], False
                pos = n
            else:
                yield text[pos:end+2], False
                pos = end + 2
            continue
        if _is_cjk(ch):
            yield ch, False
            pos += 1
            continue
        # Latin run — gather until next space, CJK, or markup boundary
        start = pos
        while pos < n:
            c = text[pos]
            if c == ' ' or _is_cjk(c) or text[pos:pos+2] == '[[':
                break
            pos += 1
        yield text[start:pos], False


def _split_runs(text: str):
    """Yield ``(kind, segment)`` tuples splitting ``text`` at script
    boundaries AND ``[[X]]`` / ``[[btn:X]]`` keycap markers. ``kind`` is one
    of ``RUN_LATIN`` / ``RUN_CJK`` / ``RUN_KEYCAP`` / ``RUN_BUTTON``; the
    segment for keycap/button runs is the inner label (without brackets).
    """
    pos = 0
    for m in _KEYCAP_RE.finditer(text):
        before = text[pos:m.start()]
        if before:
            yield from _split_script(before)
        kind = RUN_BUTTON if m.group(1) == "btn" else RUN_KEYCAP
        yield kind, m.group(2)
        pos = m.end()
    tail = text[pos:]
    if tail:
        yield from _split_script(tail)


def _render_keycap(label: str, latin_font: pygame.font.Font,
                   cjk_font: pygame.font.Font, *, kind: str = RUN_KEYCAP) -> tuple[pygame.Surface, int]:
    """Render a small inline chip. Two visual flavors discriminated by
    ``kind``: physical keys (``RUN_KEYCAP``) get a sunken slate <kbd>
    appearance; on-screen buttons (``RUN_BUTTON``) get an accent-green fill
    matching the panel's primary button so an inline ``[[btn:Next]]`` reads
    as a pointer to the actual Next button. The inner label uses
    mixed-script rendering so localized button labels (e.g. ``[[btn:下一步]]``
    in zh-HK) don't tofu through a Latin-only font.
    """
    # ── tuneable params ──────────────────────────────────────
    pad_x = 8
    pad_y = 1
    if kind == RUN_BUTTON:
        cap_bg = ACCENT_COLOR
        cap_border = ACCENT_BRIGHT
        cap_text = TEXT_COLOR
    else:
        cap_bg = (38, 44, 56)                # darker than panel — sunken chip
        cap_border = (148, 158, 178)         # cool gray, low-contrast
        cap_text = (240, 244, 252)           # soft white
    border_w = 1
    radius = 5
    # ─────────────────────────────────────────────────────────

    # Per-codepoint script switch: Latin glyphs through latin_font, CJK
    # through cjk_font. Most key chips are Latin-only ("PgDn") so this is
    # a no-op fast path; button chips with CJK labels need it.
    label_img, label_ascent = _render_label_script(label, latin_font, cjk_font, cap_text)
    cap_w = label_img.get_width() + 2 * pad_x
    cap_h = label_img.get_height() + 2 * pad_y

    # Surface = max font line-box; cap rect centered vertically inside so the
    # chip's baseline matches surrounding text glyphs.
    surface_h = max(latin_font.get_height(), cap_h)
    surf = pygame.Surface((cap_w, surface_h), pygame.SRCALPHA)
    cap_y = (surface_h - cap_h) // 2

    cap_rect = pygame.Rect(0, cap_y, cap_w, cap_h)
    pygame.draw.rect(surf, cap_bg, cap_rect, border_radius=radius)
    pygame.draw.rect(surf, cap_border, cap_rect, width=border_w, border_radius=radius)
    surf.blit(label_img, (pad_x, cap_y + pad_y))
    # Effective ascent = where the inner label baseline sits relative to
    # surface top. Used by _render_mixed for line-alignment so the chip's
    # text baseline lines up with surrounding glyph baselines (especially
    # important for CJK labels whose ascent > Latin ascent).
    effective_ascent = cap_y + pad_y + label_ascent
    return surf, effective_ascent


def _render_label_script(text: str, latin_font: pygame.font.Font,
                         cjk_font: pygame.font.Font, color) -> tuple[pygame.Surface, int]:
    """Mixed Latin/CJK render used by keycap inner labels. Splits at script
    boundaries only — keycap markup inside a label isn't expected, so we
    skip the ``_split_runs`` keycap path and call ``_split_script`` directly
    to avoid recursion. Returns ``(surface, baseline_y)`` so callers can
    pass the right effective-ascent to line-alignment when embedding the
    label into a chip."""
    if not text:
        return latin_font.render("", True, color), latin_font.get_ascent()
    parts: list[tuple[pygame.Surface, int]] = []
    for kind, seg in _split_script(text):
        f = cjk_font if kind == RUN_CJK else latin_font
        parts.append((f.render(seg, True, color), f.get_ascent()))
    total_w = sum(s.get_width() for s, _ in parts)
    max_h = max(s.get_height() for s, _ in parts)
    max_ascent = max(a for _, a in parts)
    surf = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
    x = 0
    for s, asc in parts:
        surf.blit(s, (x, max_ascent - asc))
        x += s.get_width()
    return surf, max_ascent


def _render_mixed(text: str, latin_font: pygame.font.Font, cjk_font: pygame.font.Font, color) -> pygame.Surface:
    """Render mixed-script (and mixed-element) text. Latin/CJK runs use the
    matching font; ``[[Key]]`` runs render as small key-cap graphics. Runs
    composite horizontally, baseline-aligned via ascent.
    """
    if not text:
        return latin_font.render("", True, color)
    rendered: list[tuple[pygame.Surface, int]] = []   # (surface, ascent_for_alignment)
    for kind, seg in _split_runs(text):
        if kind in (RUN_KEYCAP, RUN_BUTTON):
            cap, cap_ascent = _render_keycap(seg, latin_font, cjk_font, kind=kind)
            rendered.append((cap, cap_ascent))
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


def _fmt_time(s: float) -> str:
    """Format seconds as ``M:SS`` for the seek-bar's elapsed/total labels."""
    s = max(0.0, s)
    return f"{int(s // 60)}:{int(s % 60):02d}"


def _measure_mixed(text: str, latin_font: pygame.font.Font, cjk_font: pygame.font.Font) -> int:
    """Width-only measurement for word-wrap. Computes keycap widths via
    a one-shot render (cheap; called only for word-wrap candidates)."""
    if not text:
        return 0
    total = 0
    for kind, seg in _split_runs(text):
        if kind in (RUN_KEYCAP, RUN_BUTTON):
            total += _render_keycap(seg, latin_font, cjk_font, kind=kind)[0].get_width()
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
    "tutorial.phase.approaching",
    "tutorial.phase.stopped_at_next",
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
    """Click-to-jump predicate. Function name retained for git-history
    continuity — currently serves step 7 (the click-jump demo) after the
    9→8 step renumber. Any allowed action (click, PgDn, PgUp) satisfies it,
    not just clicks; the demonstrated feature is click-jump but key presses
    are accepted too (free exploration).
    """
    return tut._action_in_step


# ─── per-step skip handlers (state mutation, no audio replay where possible) ─
# When a forward jump on the progress bar skips past a step, the step's
# skip_handler runs to keep downstream sim state coherent. Mixed pattern:
# steps 2/3/6/7 are state-only / no-op; steps 4/5 must fire audio because the
# state advance happens inside the audio-firing methods (``_advance_to_next_stop``
# fires pa[0]; ``_next_pa`` plays pa[1]). The ``audio.pause()`` at the top of
# ``_skip_step`` clears ``_next_pa``'s audio guard so chained skips with audio
# in flight don't silently no-op.

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
    """Force state to STOPPING @ 鴨宮 (idx 14). The click-jump demo (now
    step 7 after the 9→8 renumber; function name retained for git-history
    continuity) needs a known platform state — without this, a user who
    skipped the prior step with audio still playing would land here with
    stale APPROACHING state. Pauses (not stops) any in-flight audio per the
    tutorial's state-jump convention: state changes silence the soundtrack
    but don't free it."""
    if tut.sim is None:
        return
    tut.sim.audio.pause()
    tut.sim.jump_to_stop(14)


@dataclass(frozen=True)
class Step:
    n: int                                          # 1..8 (1-indexed for human-readable)
    phase_idx: Optional[int]                        # progress bar index, or None
    allowed: frozenset                              # subset of {ACT_PGDN, ACT_PGUP, ACT_CLICK}
    predicate: Callable[["Tutorial"], bool]
    next_handler: Callable[["Tutorial"], None] = _skip_noop  # fires on [Next] before advancing
    # Runs when this step is skipped past (forward jump on the progress bar).
    # The explicit [Skip step] button was dropped; skip mechanic survives via
    # the bar's phase-column click chain.
    skip_handler: Callable[["Tutorial"], None] = _skip_noop
    # If True, only the first action in this step is dispatched to the sim;
    # further presses are swallowed. Prevents accidentally chaining past the
    # phase (e.g. step 4 PgDn fires pa[0]=29; a second PgDn would fire pa[1]=30
    # which is step 5's job). Steps where natural cycling is desired (step 2
    # has 2 pa_at_station entries; step 3 STA can be restarted; step 7 allows
    # multi-click and PgDn/PgUp exploration) override False.
    lock_after_first_action: bool = True
    # Optional LCD-local rectangle (x, y, w, h) to outline as a callout. None =
    # no overlay. Pulses BG → ACCENT_BRIGHT each cycle so it visibly appears
    # and disappears.
    callout_rect: Optional[tuple[int, int, int, int]] = None
    # If True, a flashing red box is drawn around the upper-LCD's yellow hint
    # square. Set on steps that reference the yellow square in their body
    # (steps 2 + 5) so the user can locate the cue immediately.
    highlight_pa_hint: bool = False
    # Runs inside ``_enter_step`` after audio.pause() and BEFORE the snapshot.
    # Used for steps whose canonical starting state must be deterministic
    # regardless of how the user got here — currently step 7 (click-jump demo
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
         lock_after_first_action=False,
         highlight_pa_hint=True),
    # Step 3: STA can be restarted (each PgUp re-cuts from sta_cut position).
    Step(3, 2,    frozenset({ACT_PGUP}),      _pred_audio_done_after_action,
         lock_after_first_action=False),
    Step(4, 3,    frozenset({ACT_PGDN}),      _pred_audio_done_after_action,
         skip_handler=_skip_step4),
    # Step 5 (Approaching): arrival announcement. Tokaido 1865E has no passing
    # stations between 国府津 and 鴨宮, so a separate "driving" dwell phase to
    # showcase station-skipping + countdown was dropped — countdown still
    # ticks visibly on the LCD between step 4 and this step.
    Step(5, 4,    frozenset({ACT_PGDN}),      _pred_audio_done_after_action,
         skip_handler=_skip_step6,
         highlight_pa_hint=True),
    Step(6, 5,    frozenset({ACT_PGDN}),      _pred_step7_approached,
         skip_handler=_skip_step7),
    # Step 7: click-to-jump demo. PgDn / PgUp are also unlocked so the user
    # can freely explore the cycle from anywhere they jump to. callout_rect
    # frames the actually-clickable region (the two station-name rows +
    # their color bars) — excludes the bottom disclaimer line which isn't
    # interactive. Pulses while no click has fired, hides after first
    # click. entry_handler forces STOPPING @ 鴨宮 as the canonical state.
    Step(7, 6,    frozenset({ACT_CLICK, ACT_PGDN, ACT_PGUP}), _pred_step8_clicked,
         lock_after_first_action=False,
         entry_handler=_entry_step8,
         callout_rect=(5, 130, S_WIDTH - 10, 275)),
    Step(8, 7,    frozenset(),                _pred_passive),
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
        self.current_step = 1                     # 1..8 (1-indexed for human-readable)
        self.step_entered_at = time.time()
        self.state_stack: list[AppState] = []     # per-step snapshots for [Back]
        self._action_in_step: bool = False        # set by dispatcher when user fires the step's action
        # Step 3 (departure melody) walks the user through 3 PgUps: 1st full
        # play, 2nd start, 3rd cut. Action prompt switches per press count.
        self._step3_pgup_count: int = 0
        # Step 7 (click-jump) allows PgDn/PgUp for free exploration alongside
        # clicks. The post-click body swap should fire on click only — track
        # clicks separately so a PgDn/PgUp press doesn't claim "you just
        # jumped to ...".
        self._step7_clicked: bool = False

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
                self._update_hover_cursor()
                pygame.display.flip()

                self._handle_events()
        finally:
            self._teardown_sim()

        return self.completed

    def _update_hover_cursor(self) -> None:
        """Pointer-hand cursor when over a clickable progress-bar phase column.
        Surfaces the bar's clickability without an inline hint line — users
        learn the affordance on mouse exploration."""
        mx, my = pygame.mouse.get_pos()
        over_phase = any(rect.collidepoint(mx, my) for rect in self._phase_rects)
        cursor = pygame.SYSTEM_CURSOR_HAND if over_phase else pygame.SYSTEM_CURSOR_ARROW
        pygame.mouse.set_cursor(cursor)

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
                # Click in LCD area — only step 7 forwards to the sim's jumper.
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
            if self.current_step == 3:
                self._step3_pgup_count += 1
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
            if self.current_step == 7:
                self._step7_clicked = True
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
            self._step3_pgup_count = 0
            self._step7_clicked = False
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
        self._draw_pa_hint_highlight()

    def _draw_callout(self) -> None:
        """Outline the current step's callout region on the LCD (if any),
        with a pulsing accent border. The pulse fades all the way from
        bright accent down to the window BG so the rectangle visibly
        appears and disappears each cycle (a subtle ACCENT_COLOR ↔
        ACCENT_BRIGHT pulse reads as static). Suppressed for step 7 once
        the user has clicked — the cue served its purpose.
        """
        rect = self._step().callout_rect
        if rect is None:
            return
        if self.current_step == 7 and self._step7_clicked:
            return
        x, y, w, h = rect
        callout_rect = pygame.Rect(LCD_X + x, LCD_Y + y, w, h)
        self._draw_pulsing_outline(callout_rect, ACCENT_BRIGHT, outline_w=4)

    def _draw_pulsing_outline(self, rect: pygame.Rect, bright: tuple, *,
                              outline_w: int = 3, period_s: float = 1.2,
                              radius: int = 4) -> None:
        """Draw a rectangle outline whose color sine-pulses from BG_COLOR
        (effectively invisible) to ``bright`` over ``period_s`` seconds. The
        wide BG → bright range gives a clear "appears and disappears" feel
        rather than a faint shimmer."""
        phase = (time.time() % period_s) / period_s
        t = (math.sin(phase * 2 * math.pi - math.pi / 2) + 1) / 2   # 0..1
        border_color = tuple(
            int(BG_COLOR[i] + (bright[i] - BG_COLOR[i]) * t) for i in range(3)
        )
        pygame.draw.rect(self.screen, border_color, rect, width=outline_w, border_radius=radius)

    def _draw_pa_hint_highlight(self) -> None:
        """Flashing red box around the upper-LCD's yellow hint square. Drawn
        when ``Step.highlight_pa_hint`` is True (steps 2 + 5 reference the
        yellow square in their copy)."""
        if not self._step().highlight_pa_hint:
            return
        # The pa_hint square renders at (S_WIDTH-20, UPPER_HEIGHT-20, 20, 20)
        # in upper-LCD-local coords (see upper_lcd.py UpperDisplay.draw). Pad
        # 5 px on each side so the highlight surrounds rather than overlaps it.
        from displays.train_models.e235_1000 import S_WIDTH as _SW, UPPER_HEIGHT as _UH
        pad = 5
        rect = pygame.Rect(
            LCD_X + _SW - 20 - pad,
            LCD_Y + _UH - 20 - pad,
            20 + 2 * pad,
            20 + 2 * pad,
        )
        self._draw_pulsing_outline(rect, (235, 80, 80), outline_w=3, radius=3)

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

        # Circles + labels + click rects. Phase labels go through the mixed
        # renderer so zh-HK / zh-CN translations (停站中, 出發前, ...) render
        # via the language-aware CJK font; step numbers stay Latin-only.
        label_font = _font_helv(label_size, medium=True)
        label_cjk = _font_cjk(label_size)
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

            label_img = _render_mixed(i18n.t(key), label_font, label_cjk, label_color)
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

        # Header — phase name (large, bold). Mixed-font render so CJK phase
        # labels (zh-HK / zh-CN) don't tofu — Helvetica handles Latin runs,
        # ShinGoPr6N covers Han / kana.
        header_latin = _font_helv(header_size, bold=True)
        header_cjk = _font_cjk(header_size, heavy=True)
        header = self._step_header_text()
        header_img = _render_mixed(header, header_latin, header_cjk, TEXT_COLOR)
        self.screen.blit(header_img, (PANEL_X + panel_pad, PANEL_Y + panel_pad))

        # Subtitle — small step counter "Step N of M" under the phase name.
        subtitle_latin = _font_helv(subtitle_size, medium=True)
        subtitle_cjk = _font_cjk(subtitle_size)
        subtitle = self._step_subtitle_text()
        subtitle_img = _render_mixed(subtitle, subtitle_latin, subtitle_cjk, DIM_COLOR)
        subtitle_y = PANEL_Y + panel_pad + header_img.get_height() + subtitle_gap
        self.screen.blit(subtitle_img, (PANEL_X + panel_pad, subtitle_y))

        # Buttons — laid out bottom-up first so the action prompt can anchor
        # right above the primary row. On the wrap-up step the skip-tutorial
        # row isn't rendered, so primary drops to the bottom. Latin + CJK
        # fonts feed the mixed renderer in _draw_button so zh-HK / zh-CN
        # button labels (e.g. 下一步) don't tofu under the Helvetica-only path.
        btn_latin = _font_helv(15, bold=True)
        btn_cjk = _font_cjk(15, heavy=True)
        btn_w = PANEL_W - 2 * panel_pad
        bottom_y = PANEL_Y + PANEL_H - panel_pad
        if self.current_step == len(STEPS):
            primary_row_y = bottom_y - primary_btn_h
            skip_tutorial_y = 0                   # unused; not drawn
        else:
            skip_tutorial_y = bottom_y - btn_h
            primary_row_y = skip_tutorial_y - btn_gap - primary_btn_h

        # Action prompt — bottom-anchored just above the primary row so the
        # 'do this' instruction always sits next to the button it references.
        # Pre-measured so action_top can be computed before draw.
        action_text = self._step_action_text()
        action_gap_above_btns = 14
        stripe_w = 3
        stripe_pad = 8
        action_x = PANEL_X + panel_pad + stripe_w + stripe_pad
        action_max_w = PANEL_W - 2 * panel_pad - stripe_w - stripe_pad
        action_latin = _font_helv(body_size, medium=True)
        action_cjk = _font_cjk(body_size)
        action_h = 0
        if action_text:
            action_h = self._measure_wrapped_text(
                action_text, action_latin, action_cjk,
                max_w=action_max_w, line_gap=body_line_gap,
            )
        action_top = primary_row_y - action_gap_above_btns - action_h

        # Body — multi-line wrapped, mixed-script (Helvetica for Latin incl.
        # macrons, ShinGoPr6N for embedded kanji/kana). Flows from top down.
        body_latin = _font_helv(body_size, medium=True)
        body_cjk = _font_cjk(body_size)
        body = self._step_body_text()
        body_top = subtitle_y + subtitle_img.get_height() + body_gap
        self._draw_wrapped_text(
            body, body_latin, body_cjk, TEXT_COLOR,
            x=PANEL_X + panel_pad,
            y=body_top,
            max_w=PANEL_W - 2 * panel_pad,
            line_gap=body_line_gap,
        )

        # Audio progress seek bar — only when audio is playing. Anchored just
        # above the action prompt; renders elapsed/total labels under a slim
        # filled bar. Mirrors the inline visualization pattern from
        # _dev_scripts/verify_sta_listen.py (head/tail tints stripped — tutorial
        # only needs simple progress).
        if self.sim is not None and self.sim.audio.is_playing():
            pos = self.sim.audio.position()
            dur = self.sim.audio.duration()
            if pos is not None and dur and dur > 0:
                # ── tuneable params ──────────────────────────────────────
                seek_h = 6
                seek_gap_below = 8                # space between seek bar block and action stripe
                label_size = 11
                label_gap = 4                     # space between bar and labels
                # ─────────────────────────────────────────────────────────
                time_font = _font_helv(label_size, medium=True)
                label_h = time_font.get_height()
                seek_block_h = seek_h + label_gap + label_h
                seek_y = action_top - seek_gap_below - seek_block_h
                seek_w = btn_w
                seek_rect = pygame.Rect(PANEL_X + panel_pad, seek_y, seek_w, seek_h)
                pygame.draw.rect(self.screen, BTN_BG_DIM, seek_rect, border_radius=3)
                progress = max(0.0, min(1.0, pos / dur))
                fill_w = int(seek_rect.w * progress)
                if fill_w > 0:
                    pygame.draw.rect(
                        self.screen, ACCENT_COLOR,
                        pygame.Rect(seek_rect.x, seek_rect.y, fill_w, seek_rect.h),
                        border_radius=3,
                    )
                elapsed_img = time_font.render(_fmt_time(pos), True, DIM_COLOR)
                total_img = time_font.render(_fmt_time(dur), True, DIM_COLOR)
                self.screen.blit(elapsed_img, (seek_rect.x, seek_rect.bottom + label_gap))
                self.screen.blit(total_img,
                                 (seek_rect.right - total_img.get_width(),
                                  seek_rect.bottom + label_gap))

        # Action prompt render — accent text + left stripe. Stripe height uses
        # action_h (visible-glyph height) rather than the wrapped-draw return
        # so the stripe's vertical center matches the text's visual midline.
        if action_text:
            self._draw_wrapped_text(
                action_text, action_latin, action_cjk, ACCENT_BRIGHT,
                x=action_x,
                y=action_top,
                max_w=action_max_w,
                line_gap=body_line_gap,
            )
            pygame.draw.rect(
                self.screen, ACCENT_BRIGHT,
                pygame.Rect(PANEL_X + panel_pad, action_top, stripe_w, action_h),
                border_radius=2,
            )

        self._btn_rects.clear()

        # Primary row: [Back] [Next] (next is highlighted, becomes [Done] on wrap-up).
        half_w = (btn_w - btn_gap) // 2
        back_rect = pygame.Rect(PANEL_X + panel_pad, primary_row_y, half_w, primary_btn_h)
        next_rect = pygame.Rect(back_rect.right + btn_gap, primary_row_y, half_w, primary_btn_h)
        self._btn_rects["back"] = back_rect
        self._btn_rects["next"] = next_rect
        self._draw_button(back_rect, i18n.t("tutorial.btn.back"), btn_latin, btn_cjk,
                          enabled=self.current_step > 1, primary=False)
        next_label = i18n.t("tutorial.btn.done") if self.current_step == len(STEPS) else i18n.t("tutorial.btn.next")
        self._draw_button(next_rect, next_label, btn_latin, btn_cjk,
                          enabled=self.predicate_satisfied, primary=True)

        # Skip-tutorial — only on non-wrap-up steps (would be a self-loop on
        # the recap). Skip-step's mechanic is replicated by clicking the next
        # phase column on the progress bar, which runs the same skip-handler
        # chain — the explicit Skip step button was dropped to declutter.
        if self.current_step != len(STEPS):
            skip_tut_rect = pygame.Rect(PANEL_X + panel_pad, skip_tutorial_y, btn_w, btn_h)
            self._btn_rects["skip_tutorial"] = skip_tut_rect
            self._draw_button(skip_tut_rect, i18n.t("tutorial.btn.skip_tutorial"), btn_latin, btn_cjk,
                              enabled=True, primary=False)

    def _draw_button(self, rect: pygame.Rect, label: str,
                     latin_font: pygame.font.Font, cjk_font: pygame.font.Font,
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
        img = _render_mixed(label, latin_font, cjk_font, fg)
        self.screen.blit(
            img,
            (rect.centerx - img.get_width() // 2,
             rect.centery - img.get_height() // 2),
        )

    def _measure_wrapped_text(self, text: str,
                              latin_font: pygame.font.Font, cjk_font: pygame.font.Font,
                              *, max_w: int, line_gap: int) -> int:
        """Visible height of ``text`` after wrap to ``max_w``. Returns
        ``N*line_h + (N-1)*line_gap`` — drops the trailing inter-line gap
        that ``_draw_wrapped_text``'s return value carries (which is the
        y-cursor for the next element).

        Used to bottom-anchor the action prompt: the stripe rendered next to
        the text must match visible-glyph height, not next-element advance.
        """
        line_h = max(latin_font.get_height(), cjk_font.get_height())
        cy = 0
        for paragraph in text.split("\n"):
            if not paragraph:
                cy += line_h + line_gap
                continue
            for _ in self._wrap_lines(paragraph, latin_font, cjk_font, max_w):
                cy += line_h + line_gap
        if cy > 0:
            cy -= line_gap
        return cy

    def _draw_wrapped_text(self, text: str,
                           latin_font: pygame.font.Font, cjk_font: pygame.font.Font,
                           color, *, x: int, y: int, max_w: int, line_gap: int) -> int:
        """Wrap ``text`` into ``max_w`` with mixed-script rendering. CJK
        runs break at character boundaries (no whitespace required); Latin
        runs stay whole; ``[[...]]`` markup blocks are atomic. Explicit
        ``\\n`` is a forced line break. Returns the y after the last line.
        """
        line_h = max(latin_font.get_height(), cjk_font.get_height())
        cy = y
        for paragraph in text.split("\n"):
            if not paragraph:
                cy += line_h + line_gap
                continue
            for line in self._wrap_lines(paragraph, latin_font, cjk_font, max_w):
                self.screen.blit(_render_mixed(line, latin_font, cjk_font, color), (x, cy))
                cy += line_h + line_gap
        return cy

    @staticmethod
    def _wrap_lines(paragraph: str, latin_font: pygame.font.Font,
                    cjk_font: pygame.font.Font, max_w: int):
        """Yield successive line strings from a paragraph, breaking at atom
        boundaries (CJK char, Latin word, or chip markup) so a line never
        exceeds ``max_w``. Trailing whitespace at line breaks is dropped."""
        line = ""
        had_atom = False
        for atom, is_space in _wrap_atoms(paragraph):
            if is_space:
                if not had_atom:
                    continue                   # leading space — drop
                trial = line + atom
                if _measure_mixed(trial, latin_font, cjk_font) <= max_w:
                    line = trial
                # else: keep `line` as-is; trailing space gets dropped at break
                continue
            trial = line + atom if line else atom
            if _measure_mixed(trial, latin_font, cjk_font) <= max_w:
                line = trial
                had_atom = True
                continue
            if line.strip():
                yield line.rstrip()
            line = atom
            had_atom = True
        if line.strip():
            yield line.rstrip()

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
        """Small subtitle line under the header — 'Step N of M'."""
        return i18n.t("tutorial.step_header", n=self.current_step, total=len(STEPS))

    def _step_body_text(self) -> str:
        # Step 7 (click-jump) has a dynamic body — after the user clicks a
        # station, swap to the post-click message with the landed-on station
        # name interpolated.
        if self.current_step == 7 and self._step7_clicked and self.sim is not None:
            stop = self.sim.stops[self.sim.state.curr_stop]
            kanji = stop.get("name", "")
            english = stop.get("english", "")
            display = f"{kanji} ({english})" if english and english != kanji else kanji
            return i18n.t("tutorial.step.7.body_after_click", station=display)
        return i18n.t(f"tutorial.step.{self.current_step}.body")

    def _step_action_text(self) -> str:
        """Action prompt for the current step — the 'do this' line, rendered
        below the explanatory body in an accent color so the user can see at
        a glance what to do without parsing prose. Step 7 has post-click variant
        ('click another or press Next') matching the post-click body. Step 2
        switches from "play one" to "play the remaining" once the first
        pa_at_station's audio has completed."""
        if self.current_step == 2 and self.sim is not None:
            # Trigger for the second prompt: either second press already
            # dispatched (cnt>=1, definitively past first), or first audio
            # has finished (cnt==0 and not playing). Otherwise keep prompt 1.
            cnt = self.sim.state.cnt_pa_at_station
            audio_done = not self.sim.audio.is_playing()
            if cnt >= 1 or (cnt == 0 and audio_done):
                return i18n.t("tutorial.step.2.action_after_first")
        if self.current_step == 3 and self.sim is not None:
            # 3-press flow: 1st = full play, 2nd = restart, 3rd-during-2nd = cut.
            # Action prompt walks the user through it. After cut (n>=3) or if
            # the user lets the 2nd play finish naturally (n==2 and not
            # playing), drop to a "press Next" hint.
            n = self._step3_pgup_count
            playing = self.sim.audio.is_playing()
            if n == 0:
                pass                                       # initial prompt
            elif n == 1 and not playing:
                return i18n.t("tutorial.step.3.action_after_first")
            elif n == 2 and playing:
                return i18n.t("tutorial.step.3.action_during_second")
            elif n >= 3 or (n == 2 and not playing):
                return i18n.t("tutorial.step.3.action_done")
            # n == 1 and playing → 1st play in progress, fall through to base.
        if self.current_step == 6 and self._action_in_step:
            return i18n.t("tutorial.step.6.action_done")
        if self.current_step == 7 and self._step7_clicked:
            return i18n.t("tutorial.step.7.action_after_click")
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

        # CONTRACT: state-jump convention — every state transition pauses
        # in-flight audio BEFORE mutating sim state. Three sites uphold this:
        # _enter_step (here), _skip_step, and _dispatch_action's ACT_CLICK
        # branch. PASimulator.restore_state (used by [Back]) also pauses.
        # Why: _next_pa has an audio-playing guard that silently no-ops; if a
        # skip handler fires _next_pa while previous-step audio is still
        # playing, the state advance is suppressed and the panel desyncs from
        # the sim. Pausing first clears the guard. Order within this method:
        # audio.pause() → entry_handler (force canonical state) → snapshot
        # (capture post-entry state, not inbound).
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
        self._step3_pgup_count = 0
        self._step7_clicked = False

    def _advance_step(self) -> None:
        """Advance to the next step. Runs the current step's next_handler
        first (state-coherence side effects, e.g. step 2's pa_at_station
        exhaustion). [Done] on the wrap-up step (currently step 8)."""
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
        self._step3_pgup_count = 0
        self._step7_clicked = False

    def _skip_step(self) -> None:
        """Apply the step's skip handler (state mutation) + advance.

        Pauses audio first per the state-jump convention. This also clears
        ``_next_pa``'s audio guard so skip handlers that fire ``_next_pa``
        (steps 5/6) advance state cleanly even when the previous step's
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
